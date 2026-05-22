"""Tests for the audio feedback loop: _maybe_emit_audio_feedback in core/dsp.py."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from core.db import init_db
from core.dsp import _maybe_emit_audio_feedback
from core.state import GlobalState


@pytest.fixture
async def db_conn(tmp_path):
    conn = await init_db(str(tmp_path / "test.db"))
    yield conn
    await conn.close()


@pytest.fixture
def clip_path(tmp_path) -> Path:
    return tmp_path / "test_clip.wav"


async def _insert_clip(conn, path: Path, audio_key: str, mood_snapshot: dict) -> None:
    await conn.execute(
        """
        INSERT INTO audio_clips (path, prompt, source, display_name, created_at, mood_snapshot, audio_key)
        VALUES (?, '', 'generated', '', 0, ?, ?)
        """,
        (str(path), orjson.dumps(mood_snapshot).decode(), audio_key),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_feedback_emits_bpm_delta(db_conn, clip_path):
    """Emits audio_bpm_delta, audio_key_match, audio_energy_level when row exists."""
    await _insert_clip(
        db_conn,
        clip_path,
        audio_key="G",
        mood_snapshot={"drift_bpm": 100.0, "energy_rms": 0.3},
    )

    state = GlobalState(drift_bpm=120.0, drift_key="C major")
    queue: asyncio.Queue = asyncio.Queue()

    await _maybe_emit_audio_feedback(db_conn, clip_path, state, queue)

    assert not queue.empty()
    payload = queue.get_nowait()

    # |100 - 120| / 80 = 0.25
    assert "audio_bpm_delta" in payload
    assert payload["audio_bpm_delta"] == pytest.approx(0.25, abs=1e-6)

    # "G" vs "C" — no match
    assert "audio_key_match" in payload
    assert payload["audio_key_match"] == 0.0

    # energy_rms = 0.3
    assert "audio_energy_level" in payload
    assert payload["audio_energy_level"] == pytest.approx(0.3, abs=1e-6)


@pytest.mark.asyncio
async def test_feedback_key_match_true(db_conn, clip_path):
    """audio_key_match is 1.0 when the root note matches."""
    await _insert_clip(
        db_conn,
        clip_path,
        audio_key="C",
        mood_snapshot={"drift_bpm": 90.0, "energy_rms": 0.5},
    )

    state = GlobalState(drift_bpm=90.0, drift_key="C major")
    queue: asyncio.Queue = asyncio.Queue()

    await _maybe_emit_audio_feedback(db_conn, clip_path, state, queue)

    assert not queue.empty()
    payload = queue.get_nowait()

    assert "audio_key_match" in payload
    assert payload["audio_key_match"] == 1.0


@pytest.mark.asyncio
async def test_feedback_no_row_no_emit(db_conn, clip_path):
    """When no DB row exists for the clip, nothing is emitted."""
    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()

    await _maybe_emit_audio_feedback(db_conn, clip_path, state, queue)

    assert queue.empty()


@pytest.mark.asyncio
async def test_feedback_error_no_crash(clip_path):
    """A broken connection must not propagate an exception."""
    broken_conn = MagicMock()
    broken_conn.execute = MagicMock(side_effect=RuntimeError("db exploded"))

    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()

    # Should not raise
    await _maybe_emit_audio_feedback(broken_conn, clip_path, state, queue)

    assert queue.empty()
