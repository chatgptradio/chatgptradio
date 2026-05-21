"""Tests for _get_ref_territory in core/audio_queue.py."""

from __future__ import annotations

import pytest

from core.db import init_db
from core.state import GlobalState


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    return await init_db(db_path)


# ── _get_ref_territory ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ref_territory_returns_territory_when_row_exists(tmp_path):
    """_get_ref_territory returns the stored territory when the row is in the DB."""
    from core.audio_library import index_clip
    from core.audio_queue import _get_ref_territory

    conn = await _make_conn(tmp_path)
    state = GlobalState()

    clip = tmp_path / "ref_ambient.mp3"
    clip.write_bytes(b"fake")
    await index_clip(conn, clip, state, prompt="", source="reference", territory="ambient")

    result = await _get_ref_territory(conn, clip)

    assert result == "ambient"
    await conn.close()


@pytest.mark.asyncio
async def test_get_ref_territory_returns_empty_string_when_no_row(tmp_path):
    """_get_ref_territory returns '' when the path is not in the DB."""
    from core.audio_queue import _get_ref_territory

    conn = await _make_conn(tmp_path)

    result = await _get_ref_territory(conn, tmp_path / "nonexistent.mp3")

    assert result == ""
    await conn.close()


@pytest.mark.asyncio
async def test_get_ref_territory_returns_empty_string_when_territory_null(tmp_path):
    """_get_ref_territory returns '' when territory is NULL in the DB."""
    from core.audio_library import index_clip
    from core.audio_queue import _get_ref_territory

    conn = await _make_conn(tmp_path)
    state = GlobalState()

    clip = tmp_path / "ref_no_territory.mp3"
    clip.write_bytes(b"fake")
    # index without territory → stored as state.drift_territory (default "")
    await index_clip(conn, clip, state, prompt="", source="reference")

    # Force territory to NULL to test the null branch
    await conn.execute("UPDATE audio_clips SET territory = NULL WHERE path = ?", (str(clip),))
    await conn.commit()

    result = await _get_ref_territory(conn, clip)

    assert result == ""
    await conn.close()


# ── fal_derived clips inherit ref territory ───────────────────────────────────


@pytest.mark.asyncio
async def test_fal_derived_clip_inherits_ref_territory(tmp_path):
    """When a fal_derived clip is generated, index_clip receives the ref's territory."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from core.audio_library import index_clip as real_index_clip
    from core.audio_queue import run_audio_queue
    from core.audio_library import index_clip
    from core.state import GlobalState

    state = GlobalState(drift_territory="glitch")
    state_queue: asyncio.Queue = asyncio.Queue()
    conn = await _make_conn(tmp_path)

    ref_clip = tmp_path / "ref_dark.mp3"
    ref_clip.write_bytes(b"fake_ref")
    # Index the reference with its own territory, different from state.drift_territory
    await index_clip(conn, ref_clip, state, prompt="", source="reference", territory="dark")

    recorded: list[dict] = []

    async def capturing_index_clip(conn, path, state, prompt, *, source, display_name="", territory=""):
        recorded.append({"source": source, "territory": territory})
        await real_index_clip(conn, path, state, prompt, source=source, display_name=display_name, territory=territory)

    with (
        patch("core.audio_queue._generate_from_reference", new_callable=AsyncMock, return_value=b"audio"),
        patch("core.audio_queue.generate_track_name", new_callable=AsyncMock, return_value="Artist - Track"),
        patch("core.audio_queue.find_reusable", new_callable=AsyncMock, return_value=None),
        patch("core.audio_queue.find_reference", new_callable=AsyncMock, return_value=ref_clip),
        patch("core.audio_queue.mark_played", new_callable=AsyncMock),
        patch("core.audio_queue.index_clip", side_effect=capturing_index_clip),
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
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    fal_calls = [r for r in recorded if r["source"] == "fal_derived"]
    assert fal_calls, "Expected at least one fal_derived index_clip call"
    assert all(r["territory"] == "dark" for r in fal_calls), (
        f"Expected territory='dark' from ref, got: {fal_calls}"
    )
    await conn.close()
