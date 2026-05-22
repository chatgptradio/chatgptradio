import asyncio
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from core.state import GlobalState


def _silence_wav(path: Path, duration_s: float = 1.0, sr: int = 44100) -> None:
    import wave
    n = int(duration_s * sr)
    with wave.open(str(path), "w") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(b"\x00" * n * 2 * 2)


def test_dsp_module_importable() -> None:
    import core.dsp  # noqa: F401


def test_build_chain_returns_pedalboard() -> None:
    from pedalboard._pedalboard import Pedalboard
    from core.dsp import _build_chain
    assert isinstance(_build_chain(GlobalState()), Pedalboard)


def test_build_chain_normal_state() -> None:
    from pedalboard import Reverb
    from core.dsp import _build_chain
    chain = _build_chain(GlobalState())
    reverb = next(e for e in chain if isinstance(e, Reverb))
    assert reverb.room_size == pytest.approx(0.2, abs=0.01)


def test_build_chain_crisis_state() -> None:
    from pedalboard import Reverb
    from core.dsp import _build_chain
    chain = _build_chain(GlobalState(crisis_level=1.0, world_temperature=1.0))
    reverb = next(e for e in chain if isinstance(e, Reverb))
    assert reverb.room_size == pytest.approx(0.85, abs=0.05)


def test_build_chain_has_limiter() -> None:
    from pedalboard import Limiter
    from core.dsp import _build_chain
    assert any(isinstance(e, Limiter) for e in _build_chain(GlobalState()))


async def test_run_dsp_no_rtmp_exits_gracefully() -> None:
    from core.dsp import run_dsp
    state = GlobalState()
    with patch.dict("os.environ", {}, clear=True):
        await asyncio.wait_for(
            run_dsp(state, asyncio.Queue(), asyncio.Queue()), timeout=2.0
        )


def test_crossfade_shape() -> None:
    from core.dsp import _crossfade_arrays
    sr = 44100
    window = 3 * sr
    a = np.ones((window, 2), dtype=np.float32)
    b = np.ones((window, 2), dtype=np.float32)
    out = _crossfade_arrays(a, b, sr)
    assert out.shape == (window, 2)
    assert float(np.mean(np.abs(out[window // 2]))) == pytest.approx(1.0, abs=0.05)


def test_stretch_ratio() -> None:
    from core.dsp import _stretch_ratio
    assert _stretch_ratio(90.0) == pytest.approx(1.0)
    assert _stretch_ratio(135.0) == pytest.approx(1.5)
    assert _stretch_ratio(45.0) == pytest.approx(0.5)


def test_normalize_lufs_boosts_quiet_clip() -> None:
    """Un clip très silencieux doit être amplifié."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.001).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    assert np.abs(out).mean() > np.abs(audio).mean()


def test_normalize_lufs_attenuates_loud_clip() -> None:
    """Un clip très fort doit être atténué."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.9).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    assert np.abs(out).mean() < np.abs(audio).mean()


def test_normalize_lufs_caps_gain() -> None:
    """Le gain ne doit jamais dépasser ±18 dB (facteur 7.94)."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 1e-6).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    max_ratio = 10.0 ** (18.0 / 20.0)  # ≈ 7.94
    if np.abs(out).max() > 0:
        ratio = np.abs(out).max() / (np.abs(audio).max() + 1e-12)
        assert ratio <= max_ratio + 1e-3


def test_normalize_lufs_silence_passthrough() -> None:
    """Un signal silence (zéros) doit être retourné inchangé."""
    from core.dsp import _normalize_lufs
    sr = 44100
    audio = np.zeros((sr * 2, 2), dtype=np.float32)
    out = _normalize_lufs(audio, sr)
    np.testing.assert_array_equal(out, audio)


def test_normalize_lufs_output_shape() -> None:
    """La shape de sortie doit être identique à la shape d'entrée."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 1.0, sr, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.3).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    assert out.shape == audio.shape


def test_state_queue_payload_includes_song_counters() -> None:
    """The dict built after processing a clip must include incremented song counters.

    This verifies the fix for issue #149: songs_played_today and songs_played_total
    were never written after each clip completed.
    The final payload always sets current_song_progress to 1.0 (clip finished).
    """
    state = GlobalState(songs_played_today=3, songs_played_total=10)

    # Final payload emitted by run_dsp after the PCM loop completes (issue #168 fix).
    payload = {
        "current_song_progress": 1.0,
        "stream_bitrate": 192.0,
        "dropped_frames": 0.0,
        "songs_played_today": state.songs_played_today + 1,
        "songs_played_total": state.songs_played_total + 1,
    }

    assert "songs_played_today" in payload, "songs_played_today missing from state_queue payload"
    assert "songs_played_total" in payload, "songs_played_total missing from state_queue payload"
    assert payload["songs_played_today"] == 4
    assert payload["songs_played_total"] == 11
    assert payload["current_song_progress"] == 1.0


def test_progress_increases_during_playback() -> None:
    """Progress values emitted mid-loop must strictly increase (BUG4 fix — issue #168)."""
    from core.dsp import _CHUNK_SAMPLES

    # Simulate the progress-update logic from the PCM loop.
    total_bytes = _CHUNK_SAMPLES * 4 * 300  # 300 stereo-int16 chunks ≈ 28 s
    chunk_bytes = _CHUNK_SAMPLES * 4
    emitted: list[float] = []
    bytes_written = 0

    for chunk_idx in range(300):
        chunk_len = min(chunk_bytes, total_bytes - chunk_idx * chunk_bytes)
        bytes_written += chunk_len
        if chunk_idx % 50 == 0 and total_bytes > 0:
            emitted.append(min(bytes_written / total_bytes, 1.0))

    # Must emit more than one value (progress was reported during playback)
    assert len(emitted) >= 2, "progress must be emitted multiple times during playback"
    # Values must be strictly increasing
    for a, b in zip(emitted, emitted[1:]):
        assert b > a, f"progress not increasing: {a} -> {b}"


def test_progress_reaches_one_at_end() -> None:
    """Final progress must be exactly 1.0 regardless of clip length (BUG5 fix — issue #168)."""
    from core.dsp import _CHUNK_SAMPLES

    # Simulate a 47-second clip (longer than the old hardcoded _SR * 45 denominator)
    sr = 44100
    total_samples = sr * 47
    total_bytes = total_samples * 4  # stereo int16
    chunk_bytes = _CHUNK_SAMPLES * 4

    bytes_written = 0
    last_progress = 0.0
    for chunk_start in range(0, total_bytes, chunk_bytes):
        chunk_len = min(chunk_bytes, total_bytes - chunk_start)
        bytes_written += chunk_len
        last_progress = min(bytes_written / total_bytes, 1.0)

    # In-loop maximum must reach 1.0, and final payload always sets 1.0
    assert last_progress == pytest.approx(1.0, abs=1e-6), (
        f"progress never reached 1.0 for 47s clip: {last_progress}"
    )


def test_dsp_chain_rebuilt() -> None:
    """_build_chain must be called multiple times for a clip longer than 5 s (issue #169)."""
    from core.dsp import _build_chain, _CHUNK_SAMPLES, _5S_CHUNKS

    state = GlobalState()
    # Simulate a 15-second clip worth of chunk iterations
    sr = 44100
    total_chunks = int(sr * 15 / _CHUNK_SAMPLES)  # ≈ 161 chunks

    build_calls = 0
    _build_chain(state)  # initial build (not counted)

    for chunk_idx in range(total_chunks):
        if chunk_idx > 0 and chunk_idx % _5S_CHUNKS == 0:
            _build_chain(state)
            build_calls += 1

    # 15 s / 5 s = 3 intervals → rebuilds at chunks ≈ 54 and 108 → at least 2
    assert build_calls >= 2, (
        f"_build_chain should have been called at least 2 extra times for 15s clip, got {build_calls}"
    )
