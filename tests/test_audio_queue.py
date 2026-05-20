"""Tests for core/audio_queue.py — track naming integration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.db import init_db
from core.state import GlobalState


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_conn(tmp_path: Path):
    db_path = str(tmp_path / "test.db")
    return await init_db(db_path)


# ── generate_track_name called during generation path ─────────────────────────


@pytest.mark.asyncio
async def test_generate_track_name_called_concurrently(tmp_path):
    """generate_track_name is called during the audio generation path."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue()

    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_audio,
        patch(
            "core.audio_queue.generate_track_name", new_callable=AsyncMock
        ) as mock_name,
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock) as mock_reuse,
        patch("core.audio_queue.find_reference", new_callable=AsyncMock) as mock_ref,
        patch("core.audio_queue._build_prompt", return_value="ambient test prompt"),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"STABILITY_API_KEY": "test-key"}),
    ):
        mock_audio.return_value = b"fake_mp3_bytes"
        mock_name.return_value = "Void Cartographer - Cold Signal"
        mock_reuse.return_value = None
        mock_ref.return_value = None

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_name.assert_called()
    await conn.close()


# ── display_name pushed to state_queue ────────────────────────────────────────


@pytest.mark.asyncio
async def test_current_track_name_pushed_to_state_queue(tmp_path):
    """display_name is pushed to state_queue when non-empty."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue()

    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_audio,
        patch(
            "core.audio_queue.generate_track_name", new_callable=AsyncMock
        ) as mock_name,
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock) as mock_reuse,
        patch("core.audio_queue.find_reference", new_callable=AsyncMock) as mock_ref,
        patch("core.audio_queue._build_prompt", return_value="ambient test prompt"),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"STABILITY_API_KEY": "test-key"}),
    ):
        mock_audio.return_value = b"fake_mp3_bytes"
        mock_name.return_value = "Ghost Protocol - Fading Signal"
        mock_reuse.return_value = None
        mock_ref.return_value = None

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Drain state_queue and look for current_track_name update
    updates = []
    while not state_queue.empty():
        updates.append(await state_queue.get())

    track_name_updates = [u for u in updates if "current_track_name" in u]
    assert any(
        u["current_track_name"] == "Ghost Protocol - Fading Signal"
        for u in track_name_updates
    )
    await conn.close()


# ── empty display_name must not be pushed ─────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_display_name_not_pushed(tmp_path):
    """Empty display_name must not be pushed to state_queue."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()

    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_audio,
        patch(
            "core.audio_queue.generate_track_name", new_callable=AsyncMock
        ) as mock_name,
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock) as mock_reuse,
        patch("core.audio_queue.find_reference", new_callable=AsyncMock) as mock_ref,
        patch("core.audio_queue._build_prompt", return_value="ambient test prompt"),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"STABILITY_API_KEY": "test-key"}),
    ):
        mock_audio.return_value = b"fake_mp3_bytes"
        mock_name.return_value = ""  # empty — API error scenario
        mock_reuse.return_value = None
        mock_ref.return_value = None

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, None)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    updates = []
    while not state_queue.empty():
        updates.append(await state_queue.get())

    assert not any("current_track_name" in u for u in updates)
    await conn.close()


# ── find_reusable tuple unpacking ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reusable_display_name_pushed(tmp_path):
    """When find_reusable returns (path, display_name), display_name is pushed to state_queue."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue()

    conn = await _make_conn(tmp_path)

    # Create a real file so the candidate exists
    fake_clip = tmp_path / "clip_reuse.mp3"
    fake_clip.write_bytes(b"fake")

    with (
        patch(
            "core.audio_queue.find_reusable", new_callable=AsyncMock
        ) as mock_reuse,
        patch("core.audio_queue.mark_played", new_callable=AsyncMock),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._POLL_INTERVAL", 9999),  # prevent second loop
        patch.dict("os.environ", {"STABILITY_API_KEY": "test-key"}),
    ):
        mock_reuse.return_value = (fake_clip, "Reuse Artist - Reuse Track")

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    updates = []
    while not state_queue.empty():
        updates.append(await state_queue.get())

    assert any(
        u.get("current_track_name") == "Reuse Artist - Reuse Track"
        for u in updates
    )
    await conn.close()


@pytest.mark.asyncio
async def test_find_reusable_empty_display_name_not_pushed(tmp_path):
    """When find_reusable returns empty display_name, state_queue is not updated with it."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue()

    conn = await _make_conn(tmp_path)

    fake_clip = tmp_path / "clip_no_name.mp3"
    fake_clip.write_bytes(b"fake")

    with (
        patch(
            "core.audio_queue.find_reusable", new_callable=AsyncMock
        ) as mock_reuse,
        patch("core.audio_queue.mark_played", new_callable=AsyncMock),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"STABILITY_API_KEY": "test-key"}),
    ):
        mock_reuse.return_value = (fake_clip, "")  # empty display_name

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    updates = []
    while not state_queue.empty():
        updates.append(await state_queue.get())

    assert not any("current_track_name" in u for u in updates)
    await conn.close()


# ── _build_crisis_cache ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_crisis_cache_names_each_clip(tmp_path):
    """_build_crisis_cache calls generate_track_name for each generated clip."""
    from core.audio_queue import _build_crisis_cache

    state = GlobalState(crisis_level=0.9)
    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_audio,
        patch(
            "core.audio_queue.generate_track_name", new_callable=AsyncMock
        ) as mock_name,
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
    ):
        mock_audio.return_value = b"crisis_bytes"
        mock_name.return_value = "Crisis Band - Dark Signal"

        paths = await _build_crisis_cache(conn, state, "crisis ambient", count=2)

    assert mock_name.call_count == 2
    assert len(paths) == 2

    # Verify display_name was stored in DB
    async with conn.execute("SELECT display_name FROM audio_clips") as cur:
        rows = [row async for row in cur]
    assert all(row[0] == "Crisis Band - Dark Signal" for row in rows)

    await conn.close()


@pytest.mark.asyncio
async def test_build_crisis_cache_empty_display_name_still_indexes(tmp_path):
    """_build_crisis_cache indexes clip even when display_name is empty."""
    from core.audio_queue import _build_crisis_cache

    state = GlobalState(crisis_level=0.9)
    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_audio,
        patch(
            "core.audio_queue.generate_track_name", new_callable=AsyncMock
        ) as mock_name,
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
    ):
        mock_audio.return_value = b"crisis_bytes"
        mock_name.return_value = ""  # naming failed

        paths = await _build_crisis_cache(conn, state, "crisis ambient", count=1)

    assert len(paths) == 1
    async with conn.execute("SELECT display_name FROM audio_clips") as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == ""

    await conn.close()


# ── index_clip receives display_name ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_clip_called_with_display_name(tmp_path):
    """index_clip is called with the display_name from generate_track_name."""
    from core.audio_queue import run_audio_queue
    from core.audio_library import index_clip as real_index_clip

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue()

    conn = await _make_conn(tmp_path)
    recorded: list[dict] = []

    async def capturing_index_clip(conn, path, state, prompt, *, source, display_name=""):
        recorded.append({"path": path, "display_name": display_name, "source": source})
        await real_index_clip(conn, path, state, prompt, source=source, display_name=display_name)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_audio,
        patch(
            "core.audio_queue.generate_track_name", new_callable=AsyncMock
        ) as mock_name,
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock) as mock_reuse,
        patch("core.audio_queue.find_reference", new_callable=AsyncMock) as mock_ref,
        patch("core.audio_queue.index_clip", side_effect=capturing_index_clip),
        patch("core.audio_queue._build_prompt", return_value="test prompt"),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"STABILITY_API_KEY": "test-key"}),
    ):
        mock_audio.return_value = b"audio_data"
        mock_name.return_value = "Test Artist - Test Track"
        mock_reuse.return_value = None
        mock_ref.return_value = None

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(recorded) >= 1
    assert all(r["display_name"] == "Test Artist - Test Track" for r in recorded)
    await conn.close()
