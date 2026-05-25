"""Tests for CommandEngine wiring inside run_audio_queue (Issue #173)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.command_engine import CommandEngine
from core.db import init_db
from core.state import GlobalState


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_conn(tmp_path: Path):
    db_path = str(tmp_path / "test.db")
    return await init_db(db_path)


def _make_state() -> GlobalState:
    return GlobalState()


# ── replay puts path into playback_queue ─────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_puts_in_playback_queue(tmp_path):
    """push('replay', path) → playback_queue receives that Path."""
    from core.audio_queue import run_audio_queue

    state = _make_state()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    conn = await _make_conn(tmp_path)

    target = tmp_path / "cool_track.mp3"
    target.write_bytes(b"fake")

    cmd_engine = CommandEngine()
    cmd_engine.push("replay", str(target))

    with (
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="test"),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock, return_value=b"bytes"),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value=""),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue, cmd_engine=cmd_engine)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert not playback_queue.empty()
    item = await playback_queue.get()
    # playback_queue uses (path, display_name) tuples; replay has empty display_name
    assert item == (Path(str(target)), "")

    await conn.close()


# ── request sets requested_genre ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_sets_requested_genre(tmp_path):
    """push('request', 'jazz') → state.requested_genre == 'jazz'."""
    from core.audio_queue import run_audio_queue

    state = _make_state()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    conn = await _make_conn(tmp_path)

    cmd_engine = CommandEngine()
    cmd_engine.push("request", "jazz")

    genre_after: list[str] = []

    async def _fake_generate_audio(prompt: str, _state) -> bytes:
        genre_after.append(state.requested_genre)
        return b"bytes"

    with (
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="test"),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._generate_audio", side_effect=_fake_generate_audio),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value=""),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue, cmd_engine=cmd_engine)
        )
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # requested_genre was 'jazz' at the time of generation, then reset to ''
    assert "jazz" in genre_after
    assert state.requested_genre == ""

    await conn.close()


# ── vibe injects PE on territory ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vibe_injects_pe(tmp_path):
    """push('vibe', 'ambient') → state.prediction_errors['territory_ambient'] == 2.0."""
    from core.audio_queue import run_audio_queue

    state = _make_state()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    conn = await _make_conn(tmp_path)

    cmd_engine = CommandEngine()
    cmd_engine.push("vibe", "ambient")

    with (
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="test"),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock, return_value=b"bytes"),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value=""),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue, cmd_engine=cmd_engine)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert state.prediction_errors.get("territory_ambient") == 2.0

    await conn.close()
