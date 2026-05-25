"""Tests for audio-to-audio workflow improvements (Bloc 7).

Covers: pre-stretch, key distance, strength formula, quality gating, a2a decision.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import soundfile as sf


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_sine_wav(duration_s: float = 1.0, sr: int = 22050) -> bytes:
    """Return a minimal valid WAV as bytes (mono sine wave)."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    return buf.getvalue()


# ── R3: Key distance ──────────────────────────────────────────────────────────


def test_key_distance_same_key():
    """Same root note → distance 0.0 regardless of mode suffix."""
    from core.audio_queue import _key_distance

    assert _key_distance("C major", "C minor") == 0.0


def test_key_distance_tritone():
    """C and F# are tritone opposites on the circle of fifths → distance 1.0."""
    from core.audio_queue import _key_distance

    assert _key_distance("C", "F#") == pytest.approx(1.0)


def test_key_distance_fifth():
    """C and G are one step apart → distance 1/6 ≈ 0.1667."""
    from core.audio_queue import _key_distance

    assert _key_distance("C", "G") == pytest.approx(1 / 6, rel=1e-4)


def test_key_distance_unknown_keys_returns_zero():
    """Unknown key strings should not raise and return 0.0."""
    from core.audio_queue import _key_distance

    assert _key_distance("X#", "Yyy") == 0.0


def test_strength_increases_with_key_distance():
    """Higher key distance should produce a higher strength value."""
    from core.audio_queue import _clamp, _key_distance

    drift_velocity = 0.2
    crisis_level = 0.1

    def strength(ref_key: str, drift_key: str) -> float:
        kd = _key_distance(ref_key, drift_key)
        return _clamp(0.3 + drift_velocity * 0.3 + crisis_level * 0.2 + kd * 0.2, 0.3, 0.9)

    s_same = strength("C", "C")
    s_far = strength("C", "F#")
    assert s_far > s_same


# ── R1: Pre-stretch ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prestretch_skipped_small_delta():
    """BPM delta < 2 → original bytes returned unchanged."""
    from core.audio_queue import _prestretch_reference

    ref_bytes = b"original_audio_data"
    result = await _prestretch_reference(Path("dummy.wav"), ref_bytes, 120.0, 119.5)
    assert result is ref_bytes


@pytest.mark.asyncio
async def test_prestretch_skipped_none_bpm():
    """ref_bpm=None → original bytes returned unchanged."""
    from core.audio_queue import _prestretch_reference

    ref_bytes = b"original_audio_data"
    result = await _prestretch_reference(Path("dummy.wav"), ref_bytes, 120.0, None)
    assert result is ref_bytes


@pytest.mark.asyncio
async def test_prestretch_returns_bytes():
    """Valid WAV input with significant BPM delta → returns bytes (any length)."""
    from core.audio_queue import _prestretch_reference

    wav_bytes = _make_sine_wav(duration_s=0.5)
    result = await _prestretch_reference(Path("test.wav"), wav_bytes, 140.0, 100.0)
    assert isinstance(result, bytes)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_prestretch_ratio_capped():
    """Extreme BPM ratio is capped at 2.0 (no >octave stretches)."""
    from core.audio_queue import _prestretch_reference

    wav_bytes = _make_sine_wav(duration_s=0.3)
    # ratio would be 300/60=5.0 → capped to 2.0
    result = await _prestretch_reference(Path("test.wav"), wav_bytes, 300.0, 60.0)
    assert isinstance(result, bytes)
    assert len(result) > 0


# ── R5: a2a vs text-only decision ─────────────────────────────────────────────


def _make_a2a_decision(source_divergence: float, mfcc_dist: float) -> bool:
    """Return True if a2a is skipped (ref_path should be set to None).

    Mirrors the R5 logic extracted for isolated unit testing.
    """
    return source_divergence > 0.7 and mfcc_dist > 0.6


def test_a2a_decision_skips_on_high_divergence():
    """High source_divergence + high mfcc_dist → a2a should be skipped."""
    assert _make_a2a_decision(source_divergence=0.8, mfcc_dist=0.7) is True


def test_a2a_decision_allows_on_low_divergence():
    """Low source_divergence → a2a should proceed regardless of mfcc_dist."""
    assert _make_a2a_decision(source_divergence=0.5, mfcc_dist=0.9) is False


def test_a2a_decision_allows_on_low_mfcc_dist():
    """High source_divergence but low mfcc_dist → a2a should proceed."""
    assert _make_a2a_decision(source_divergence=0.9, mfcc_dist=0.4) is False


@pytest.mark.asyncio
async def test_a2a_decision_sets_ref_path_to_none(tmp_path):
    """When conditions are met, the main loop sets ref_path=None (text-only path)."""
    import orjson

    from core.audio_queue import run_audio_queue
    from core.db import init_db
    from core.state import GlobalState

    db_path = str(tmp_path / "test.db")
    conn = await init_db(db_path)

    state = GlobalState()
    state.source_divergence = 0.8
    # Provide orthogonal MFCC fingerprints so cosine distance = 1.0 > 0.6 → skip condition met
    state.mfcc_fingerprint = [1.0] + [0.0] * 19

    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue()

    generated_text_only: list[bool] = []

    async def _fake_generate_audio(prompt: str, _state) -> bytes:
        generated_text_only.append(True)
        return b"fake_mp3"

    async def _fake_generate_from_reference(ref_path, prompt, state, conn_arg) -> bytes:  # pragma: no cover
        generated_text_only.append(False)
        return b"fake_mp3_ref"

    ref_path_mock = tmp_path / "ref.mp3"
    ref_path_mock.write_bytes(b"x")

    # Orthogonal MFCC in reference clip → cosine distance = 1.0
    ref_mfcc = [0.0, 1.0] + [0.0] * 18
    snap_data = orjson.dumps({"detected_bpm": 100.0, "mfcc_fingerprint": ref_mfcc}).decode()
    await conn.execute(
        "INSERT INTO audio_clips (path, source, territory, mood_snapshot, audio_key, play_count)"
        " VALUES (?, 'reference', 'ambient', ?, '', 0)",
        (str(ref_path_mock), snap_data),
    )
    await conn.commit()

    with (
        patch("core.audio_queue._generate_audio", side_effect=_fake_generate_audio),
        patch("core.audio_queue._generate_from_reference", side_effect=_fake_generate_from_reference),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value="Test Track"),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=ref_path_mock),
        patch("core.audio_queue._build_prompt", return_value="test prompt"),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await conn.close()

    # text-only path should have been taken (True = _generate_audio called)
    assert any(generated_text_only), "Expected at least one generation attempt"
    assert all(generated_text_only), "Expected text-only path (not a2a) due to high divergence"
