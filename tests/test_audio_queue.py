"""Tests for core/audio_queue.py — track naming integration."""

from __future__ import annotations

import asyncio
import itertools
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
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
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
    """Generated clip with display_name is put in playback_queue as (path, name) tuple."""
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
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
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

    # clip should be queued as (path, display_name) tuple — current_track_name is
    # pushed by dsp.py at playback time, not here.
    assert not playback_queue.empty()
    item = await playback_queue.get()
    assert isinstance(item, tuple) and len(item) == 2
    assert item[1] == "Ghost Protocol - Fading Signal"
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
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
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


# ── _analyze_clip_async persists detected_bpm ────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_clip_persists_detected_bpm(tmp_path):
    """_analyze_clip_async must include detected_bpm in the mood_snapshot written to DB."""
    import orjson
    from unittest.mock import patch

    from core.audio_queue import _analyze_clip_async

    conn = await _make_conn(tmp_path)
    path = tmp_path / "test.mp3"
    path.touch()

    await conn.execute(
        "INSERT INTO audio_clips (path, territory, mood_snapshot) VALUES (?, ?, ?)",
        (str(path), "ambient", '{"drift_bpm": 120}'),
    )
    await conn.commit()

    fake_analysis = {
        "detected_bpm": 127.5,
        "detected_key": "C major",
        "mfcc_fingerprint": [0.1] * 20,
        "duration_s": 30.0,
        "trim_start_s": 0.1,
        "trim_end_s": 29.9,
        "energy_rms": 0.5,
        "fill_ratio": 0.95,
    }

    running_loop = asyncio.get_running_loop()
    fut = running_loop.create_future()
    fut.set_result(fake_analysis)

    with (
        patch.object(running_loop, "run_in_executor", return_value=fut),
        patch("core.audio_queue._HAS_LIBROSA", True),
    ):
        await _analyze_clip_async(conn, path)

    async with conn.execute(
        "SELECT mood_snapshot FROM audio_clips WHERE path=?", (str(path),)
    ) as cur:
        row = await cur.fetchone()

    snap = orjson.loads(row[0])
    assert "detected_bpm" in snap
    assert snap["detected_bpm"] == pytest.approx(127.5)

    await conn.close()


# ── find_reusable tuple unpacking ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reusable_display_name_pushed(tmp_path):
    """When find_reusable returns (path, display_name), clip is put in playback_queue as tuple."""
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
        # Prevent real reference files from being indexed (would set _pending_ref=True,
        # causing the reuse path to be skipped in favour of A2A generation)
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        # Prevent background crisis cache generation (makes HTTP requests, competes for event loop)
        patch("core.audio_queue._build_crisis_cache", new_callable=AsyncMock),
        patch("core.audio_queue._POLL_INTERVAL", 9999),  # prevent second loop
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
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

    # playback_queue receives (path, display_name) — current_track_name pushed by dsp.py
    assert not playback_queue.empty()
    item = await playback_queue.get()
    assert item == (fake_clip, "Reuse Artist - Reuse Track")
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
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
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

    async def capturing_index_clip(conn, path, state, prompt, *, source, display_name="", territory=""):
        recorded.append({"path": path, "display_name": display_name, "source": source})
        await real_index_clip(conn, path, state, prompt, source=source, display_name=display_name, territory=territory)

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
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
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


# ── _auto_index_references_on_startup ────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_index_references_indexes_new_files(tmp_path):
    """_auto_index_references_on_startup indexes files not yet in DB."""
    from core.audio_queue import _auto_index_references_on_startup

    refs_dir = tmp_path / "references"
    refs_dir.mkdir()
    ref_file = refs_dir / "Artist - Track.mp3"
    ref_file.write_bytes(b"fake")

    state = GlobalState()
    conn = await _make_conn(tmp_path)

    with patch("core.audio_queue._REFERENCES_DIR", refs_dir):
        count = await _auto_index_references_on_startup(conn, state)

    assert count == 1

    async with conn.execute(
        "SELECT source, display_name FROM audio_clips WHERE path = ?", (str(ref_file),)
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == "reference"
    assert row[1] == "Artist - Track"
    await conn.close()


@pytest.mark.asyncio
async def test_auto_index_references_skips_already_indexed(tmp_path):
    """_auto_index_references_on_startup skips files already in DB."""
    from core.audio_library import index_clip
    from core.audio_queue import _auto_index_references_on_startup

    refs_dir = tmp_path / "references"
    refs_dir.mkdir()
    ref_file = refs_dir / "Artist - Track.mp3"
    ref_file.write_bytes(b"fake")

    state = GlobalState()
    conn = await _make_conn(tmp_path)
    await index_clip(conn, ref_file, state, prompt="", source="reference", display_name="Already Indexed")

    with patch("core.audio_queue._REFERENCES_DIR", refs_dir):
        count = await _auto_index_references_on_startup(conn, state)

    assert count == 0

    async with conn.execute(
        "SELECT display_name FROM audio_clips WHERE path = ?", (str(ref_file),)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "Already Indexed"
    await conn.close()


@pytest.mark.asyncio
async def test_auto_index_references_ignores_non_audio(tmp_path):
    """_auto_index_references_on_startup ignores non-audio files (.jpg, .txt, etc.)."""
    from core.audio_queue import _auto_index_references_on_startup

    refs_dir = tmp_path / "references"
    refs_dir.mkdir()
    (refs_dir / ".gitkeep").write_bytes(b"")
    (refs_dir / "cover.jpg").write_bytes(b"fake")

    state = GlobalState()
    conn = await _make_conn(tmp_path)

    with patch("core.audio_queue._REFERENCES_DIR", refs_dir):
        count = await _auto_index_references_on_startup(conn, state)

    assert count == 0
    await conn.close()


@pytest.mark.asyncio
async def test_auto_index_references_missing_dir_returns_zero(tmp_path):
    """_auto_index_references_on_startup returns 0 silently if directory doesn't exist."""
    from core.audio_queue import _auto_index_references_on_startup

    state = GlobalState()
    conn = await _make_conn(tmp_path)

    with patch("core.audio_queue._REFERENCES_DIR", tmp_path / "nonexistent"):
        count = await _auto_index_references_on_startup(conn, state)

    assert count == 0
    await conn.close()


# ── find_reference includes source='reference' clips ─────────────────────────


@pytest.mark.asyncio
async def test_find_reference_returns_reference_source_clip(tmp_path):
    """find_reference() selects clips with source='reference'."""
    from core.audio_library import index_clip
    from core.audio_queue import find_reference

    state = GlobalState()
    conn = await _make_conn(tmp_path)

    # Create a real file so the path existence check passes
    ref_clip = tmp_path / "ref_001.mp3"
    ref_clip.write_bytes(b"fake_ref_audio")

    # References are eligible as audio-to-audio sources from play_count=0
    await index_clip(conn, ref_clip, state, prompt="", source="reference")

    result = await find_reference(conn, state)

    assert result == ref_clip
    await conn.close()


# ── find_reference existence guard ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reference_returns_none_for_missing_file(tmp_path):
    """find_reference() returns None when the best candidate path does not exist on disk."""
    from core.audio_library import index_clip
    from core.audio_queue import find_reference

    state = GlobalState()
    conn = await _make_conn(tmp_path)

    ghost_clip = tmp_path / "ghost_ref.mp3"
    # ghost_clip is NOT created on disk

    await index_clip(conn, ghost_clip, state, prompt="", source="reference")

    result = await find_reference(conn, state)

    assert result is None
    await conn.close()


# ── find_reference territory scoring ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reference_prefers_territory_match(tmp_path):
    """find_reference returns the clip whose territory matches state.drift_territory."""
    from core.audio_library import index_clip
    from core.audio_queue import find_reference

    state = GlobalState(drift_territory="ambient")
    conn = await _make_conn(tmp_path)

    clip_ambient = tmp_path / "ref_ambient.mp3"
    clip_ambient.write_bytes(b"fake_audio")
    clip_jazz = tmp_path / "ref_jazz.mp3"
    clip_jazz.write_bytes(b"fake_audio")

    # References are eligible from play_count=0 — no manual update needed
    await index_clip(conn, clip_ambient, state, prompt="ambient", source="reference", territory="ambient")
    await index_clip(conn, clip_jazz, state, prompt="jazz", source="reference", territory="jazz")

    result = await find_reference(conn, state)

    assert result == clip_ambient
    await conn.close()


# ── _QUEUE_TARGET — no generation when queue is full ─────────────────────────


@pytest.mark.asyncio
async def test_audio_queue_skips_generation_when_queue_full(tmp_path):
    """When playback_queue.qsize() >= _QUEUE_TARGET, no new clip is generated."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)

    conn = await _make_conn(tmp_path)

    dummy = tmp_path / "dummy.mp3"
    dummy.write_bytes(b"fake")
    for _ in range(2):  # fill to _QUEUE_TARGET=2
        await playback_queue.put(dummy)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_gen,
        patch("core.audio_queue._generate_from_reference", new_callable=AsyncMock) as mock_ref_gen,
        patch("core.audio_queue._build_crisis_cache", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue.cleanup_ghost_paths", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_gen.assert_not_called()
    mock_ref_gen.assert_not_called()
    await conn.close()


# ── Periodic rescan of streams/references/ ────────────────────────────────────


@pytest.mark.asyncio
async def test_audio_queue_periodic_rescan_triggers(tmp_path):
    """_auto_index_references_on_startup is called again after _RESCAN_INTERVAL."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    conn = await _make_conn(tmp_path)

    # First call (last_refs_scan init) → 0.0; loop check → 61.0 (> 60s) → rescan
    time_seq = itertools.chain([0.0, 61.0], itertools.repeat(62.0))

    with (
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0) as mock_scan,
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock, return_value=b"bytes"),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value=""),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._build_prompt", return_value="test"),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch("core.audio_queue.time") as mock_time_mod,
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        mock_time_mod.time.side_effect = lambda: next(time_seq)

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, None)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # startup call + at least one periodic call (61s > 60s interval)
    assert mock_scan.call_count >= 2
    await conn.close()


# ── _get_ref_duration ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ref_duration_returns_seconds(tmp_path):
    """_get_ref_duration returns the duration reported by ffprobe."""
    from core.audio_queue import _get_ref_duration

    fake_audio = tmp_path / "ref.mp3"
    fake_audio.write_bytes(b"fake")

    async def fake_ffprobe(*args, **kwargs):
        class FakeProc:
            async def communicate(self):
                return (b"183.4\n", b"")
        return FakeProc()

    with patch("core.audio_queue.asyncio.create_subprocess_exec", side_effect=fake_ffprobe):
        duration = await _get_ref_duration(fake_audio)

    assert duration == 183


@pytest.mark.asyncio
async def test_get_ref_duration_returns_zero_on_failure(tmp_path):
    """_get_ref_duration returns 0 when ffprobe output is unreadable."""
    from core.audio_queue import _get_ref_duration

    fake_audio = tmp_path / "ref.mp3"
    fake_audio.write_bytes(b"fake")

    async def fake_ffprobe(*args, **kwargs):
        class FakeProc:
            async def communicate(self):
                return (b"N/A\n", b"")
        return FakeProc()

    with patch("core.audio_queue.asyncio.create_subprocess_exec", side_effect=fake_ffprobe):
        duration = await _get_ref_duration(fake_audio)

    assert duration == 0


# ── Reference rotation after generation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_played_called_on_reference_after_generation(tmp_path):
    """mark_played is called on the reference path after audio-to-audio generation."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    conn = await _make_conn(tmp_path)

    ref_file = tmp_path / "ref.mp3"
    ref_file.write_bytes(b"fake_ref")

    with (
        patch("core.audio_queue._generate_from_reference", new_callable=AsyncMock, return_value=b"audio") as mock_a2a,
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value="Artist - Track"),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=ref_file),
        patch("core.audio_queue.mark_played", new_callable=AsyncMock) as mock_mark,
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="test prompt"),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, None)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # mark_played must have been called with the reference path
    assert mock_a2a.called
    mark_calls = [call.args[1] for call in mock_mark.call_args_list]
    assert ref_file in mark_calls
    await conn.close()


# ── Crisis cache startup trigger ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crisis_cache_triggered_at_startup(tmp_path):
    """_build_crisis_cache is launched as a task immediately after startup."""
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)

    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._build_crisis_cache", new_callable=AsyncMock) as mock_cache,
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue.cleanup_ghost_paths", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="crisis test prompt"),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        mock_cache.return_value = []

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_cache.assert_called_once()
    await conn.close()


# ── Crisis delta > 0.15 triggers cache rebuild ───────────────────────────────


@pytest.mark.asyncio
async def test_crisis_cache_triggered_on_delta_above_threshold(tmp_path):
    """When crisis_level rises by more than 0.15 in one loop, _build_crisis_cache is called again."""
    from core.audio_queue import run_audio_queue

    state = GlobalState(crisis_level=0.1)
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)

    conn = await _make_conn(tmp_path)

    call_count: list[int] = [0]

    async def _fake_cache(*args, **kwargs):
        call_count[0] += 1
        # After startup call, simulate a crisis spike on next iteration
        if call_count[0] == 1:
            state.crisis_level = 0.8  # delta = 0.8 - 0.1 = 0.70 > 0.15
        return []

    with (
        patch("core.audio_queue._build_crisis_cache", side_effect=_fake_cache) as mock_cache,
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue.cleanup_ghost_paths", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="crisis prompt"),
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock, return_value=b"bytes"),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value=""),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 0),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        # Allow enough time for startup task + at least one main-loop iteration
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # At minimum: startup call (1) + delta-triggered call (≥1)
    assert mock_cache.call_count >= 2
    await conn.close()


# ── Generated clip marked played immediately — no double-queue ───────────────


@pytest.mark.asyncio
async def test_generated_clip_not_double_queued(tmp_path):
    """Generated clips must be marked played after index so find_reusable cannot
    re-queue them on the next poll.

    Regression: index_clip initialises last_played_at=0.0, which always passes
    the 2-hour cooldown check.  Without mark_played the same clip appeared in
    playback_queue twice, causing back-to-back identical playback.
    """
    from core.audio_queue import run_audio_queue

    state = GlobalState()
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock, return_value=b"audio") as mock_gen,
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value="Test Track"),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.mark_played", new_callable=AsyncMock) as mock_mark,
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue.cleanup_ghost_paths", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="test prompt"),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert mock_gen.called, "audio was generated"

    # mark_played must have been called on the generated outpath (not a ref).
    # Without this call, find_reusable() would see last_played_at=0 on the next
    # poll and enqueue the same clip a second time.
    marked_paths = [call.args[1] for call in mock_mark.call_args_list]
    generated_clips = [p for p in marked_paths if "clip_" in p.name]
    assert generated_clips, (
        "mark_played was never called on the generated clip — "
        "double-queue regression: find_reusable() will re-enqueue it"
    )

    await conn.close()


# ── Crisis bypass of prompt-hash stability guard ─────────────────────────────


@pytest.mark.asyncio
async def test_crisis_bypasses_prompt_hash_stability_guard(tmp_path):
    """When crisis_level > 0.6 and queue is empty, generation is forced even with duplicate prompt hash."""
    from core.audio_queue import run_audio_queue

    state = GlobalState(crisis_level=0.8)
    state_queue: asyncio.Queue = asyncio.Queue()
    playback_queue: asyncio.Queue = asyncio.Queue(maxsize=4)

    conn = await _make_conn(tmp_path)

    with (
        patch("core.audio_queue._build_crisis_cache", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._generate_audio", new_callable=AsyncMock) as mock_gen,
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value="Crisis Track"),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue._index_fallback_clips", new_callable=AsyncMock, return_value=[]),
        patch("core.audio_queue._auto_index_references_on_startup", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue.cleanup_ghost_paths", new_callable=AsyncMock, return_value=0),
        patch("core.audio_queue._build_prompt", return_value="crisis prompt"),
        patch("core.audio_queue._CLIPS_DIR", tmp_path),
        patch("core.audio_queue._POLL_INTERVAL", 9999),
        patch.dict("os.environ", {"FAL_API_KEY": "test-key"}),
    ):
        mock_gen.return_value = b"crisis_audio"
        # Pre-set last_prompt_hash to the same hash that _build_prompt will return,
        # so the stability guard would normally block generation
        import hashlib
        state.last_prompt_hash = hashlib.md5(b"crisis prompt").hexdigest()[:8]

        task = asyncio.create_task(
            run_audio_queue(state, state_queue, conn, playback_queue)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Generation must have been called despite duplicate hash, because crisis_level > 0.6
    mock_gen.assert_called()
    await conn.close()


def test_vibe_dead_code_removed():
    """B11: the !vibe branch (kind == 'vibe') is dead code — no push('vibe', ...) exists.
    Verify it has been removed from audio_queue.py to avoid misleading future readers."""
    import inspect
    import core.audio_queue as aq

    src = inspect.getsource(aq)
    assert 'kind == "vibe"' not in src, "dead !vibe branch must be removed from audio_queue"


def test_stream_bitrate_not_hardcoded_in_dsp():
    """B17: stream_bitrate and dropped_frames must not be hardcoded constants in dsp.py."""
    import inspect
    import core.dsp as dsp_module

    src = inspect.getsource(dsp_module)
    assert '"stream_bitrate": 192' not in src, "stream_bitrate must not be hardcoded"
    assert '"dropped_frames": 0' not in src, "dropped_frames must not be hardcoded"
