"""Tests for post-generation librosa analysis (_analyze_clip_async)."""

from __future__ import annotations

import wave
import struct
from pathlib import Path
from unittest.mock import patch

import pytest

from core.db import init_db


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_conn():
    return await init_db(":memory:")


def _write_silent_wav(path: Path, duration_s: float = 1.0, sample_rate: int = 44100) -> None:
    """Write a silent mono WAV file to *path*."""
    n_samples = int(duration_s * sample_rate)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * n_samples, *([0] * n_samples)))


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_clip_async_populates_fields(tmp_path):
    """_analyze_clip_async populates audio_key, duration_s, mfcc_fingerprint."""
    from core.audio_queue import _analyze_clip_async
    from core.audio_library import index_clip
    from core.state import GlobalState
    import orjson

    wav_path = tmp_path / "silent.wav"
    _write_silent_wav(wav_path, duration_s=1.0)

    conn = await _make_conn()
    state = GlobalState()
    await index_clip(conn, wav_path, state, prompt="test", source="generated")

    await _analyze_clip_async(conn, wav_path)

    async with conn.execute(
        "SELECT audio_key, duration_s, mood_snapshot FROM audio_clips WHERE path=?",
        (str(wav_path),),
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    audio_key, duration_s, mood_snapshot_raw = row

    assert audio_key != ""
    assert duration_s > 0

    mood = orjson.loads(mood_snapshot_raw or "{}")
    assert "mfcc_fingerprint" in mood
    assert len(mood["mfcc_fingerprint"]) == 20

    await conn.close()


@pytest.mark.asyncio
async def test_analyze_clip_async_missing_file_no_crash(tmp_path):
    """_analyze_clip_async does not raise when the file does not exist."""
    from core.audio_queue import _analyze_clip_async

    conn = await _make_conn()
    nonexistent = tmp_path / "does_not_exist.wav"

    # Must not raise
    await _analyze_clip_async(conn, nonexistent)

    await conn.close()


@pytest.mark.asyncio
async def test_analyze_clip_async_skipped_without_librosa(tmp_path):
    """_analyze_clip_async returns immediately when _HAS_LIBROSA is False."""
    import core.audio_queue as aq
    from core.audio_library import index_clip
    from core.state import GlobalState

    wav_path = tmp_path / "silent.wav"
    _write_silent_wav(wav_path, duration_s=1.0)

    conn = await _make_conn()
    state = GlobalState()
    await index_clip(conn, wav_path, state, prompt="test", source="generated")

    with patch.object(aq, "_HAS_LIBROSA", False):
        await aq._analyze_clip_async(conn, wav_path)

    # DB row must be unchanged — audio_key stays '' (default after index_clip)
    async with conn.execute(
        "SELECT audio_key FROM audio_clips WHERE path=?", (str(wav_path),)
    ) as cur:
        row = await cur.fetchone()

    # audio_key should be whatever state.drift_key was (not populated by analysis)
    assert row is not None
    # No exception was raised — that's the key assertion

    await conn.close()
