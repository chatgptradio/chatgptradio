"""Tests for core/audio_library.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.audio_library import find_by_display_name, find_reusable, index_clip
from core.db import init_db
from core.state import GlobalState


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = await init_db(db_path)
    yield conn
    await conn.close()


@pytest.fixture
def real_audio_file(tmp_path) -> Path:
    """Create a real file on disk so path.exists() checks pass."""
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF")
    return p


# ── index_clip ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_clip_persists_display_name(tmp_db, real_audio_file):
    state = GlobalState(excitation=0.5)
    await index_clip(
        tmp_db,
        real_audio_file,
        state,
        prompt="ambient drift",
        display_name="Test Artist - Test Track",
    )
    async with tmp_db.execute(
        "SELECT display_name FROM audio_clips WHERE path = ?",
        (str(real_audio_file),),
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "Test Artist - Test Track"


@pytest.mark.asyncio
async def test_index_clip_default_display_name_empty(tmp_db, real_audio_file):
    state = GlobalState()
    await index_clip(tmp_db, real_audio_file, state, prompt="quiet")
    async with tmp_db.execute(
        "SELECT display_name FROM audio_clips WHERE path = ?",
        (str(real_audio_file),),
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == ""


@pytest.mark.asyncio
async def test_index_clip_upsert_updates_display_name(tmp_db, real_audio_file):
    state = GlobalState()
    await index_clip(
        tmp_db, real_audio_file, state, prompt="v1", display_name="Old Name"
    )
    await index_clip(
        tmp_db, real_audio_file, state, prompt="v2", display_name="New Name"
    )
    async with tmp_db.execute(
        "SELECT display_name, prompt FROM audio_clips WHERE path = ?",
        (str(real_audio_file),),
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == "New Name"
    assert row[1] == "v2"


# ── find_reusable ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reusable_returns_tuple(tmp_db, real_audio_file):
    state = GlobalState()
    await index_clip(
        tmp_db,
        real_audio_file,
        state,
        prompt="test",
        display_name="Void - Cold Signal",
    )
    result = await find_reusable(tmp_db, state)
    assert result is not None
    path, display_name = result
    assert isinstance(path, Path)
    assert isinstance(display_name, str)
    assert path == real_audio_file
    assert display_name == "Void - Cold Signal"


@pytest.mark.asyncio
async def test_find_reusable_returns_none_when_empty(tmp_db):
    state = GlobalState()
    result = await find_reusable(tmp_db, state)
    assert result is None


@pytest.mark.asyncio
async def test_find_reusable_skips_missing_file(tmp_db, tmp_path):
    state = GlobalState()
    ghost = tmp_path / "ghost.wav"
    # Do NOT create ghost on disk — it should be skipped
    await index_clip(tmp_db, ghost, state, prompt="ghost", display_name="Ghost Track")
    result = await find_reusable(tmp_db, state)
    assert result is None


@pytest.mark.asyncio
async def test_find_reusable_respects_max_play_count(tmp_db, real_audio_file):
    state = GlobalState()
    await index_clip(
        tmp_db, real_audio_file, state, prompt="played", display_name="Played Track"
    )
    # Manually set play_count above threshold
    await tmp_db.execute(
        "UPDATE audio_clips SET play_count = 5 WHERE path = ?",
        (str(real_audio_file),),
    )
    await tmp_db.commit()
    result = await find_reusable(tmp_db, state, max_play_count=3)
    assert result is None


# ── find_by_display_name ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_by_display_name_case_insensitive(tmp_db, real_audio_file):
    state = GlobalState()
    await index_clip(
        tmp_db,
        real_audio_file,
        state,
        prompt="void",
        display_name="Void Cartographer - Cold Signal",
    )
    result = await find_by_display_name(tmp_db, "cold signal")
    assert result is not None
    path, display_name = result
    assert path == real_audio_file
    assert display_name == "Void Cartographer - Cold Signal"


@pytest.mark.asyncio
async def test_find_by_display_name_partial_match(tmp_db, real_audio_file):
    state = GlobalState()
    await index_clip(
        tmp_db,
        real_audio_file,
        state,
        prompt="drift",
        display_name="Neon Cartographer - Deep Drift",
    )
    result = await find_by_display_name(tmp_db, "Neon")
    assert result is not None
    assert result[1] == "Neon Cartographer - Deep Drift"


@pytest.mark.asyncio
async def test_find_by_display_name_no_match(tmp_db):
    result = await find_by_display_name(tmp_db, "xyznotexist")
    assert result is None


@pytest.mark.asyncio
async def test_find_by_display_name_skips_missing_file(tmp_db, tmp_path):
    state = GlobalState()
    ghost = tmp_path / "missing.wav"
    # Do NOT create the file — find_by_display_name must return None
    await index_clip(
        tmp_db, ghost, state, prompt="ghost", display_name="Ghost - Missing File"
    )
    result = await find_by_display_name(tmp_db, "ghost")
    assert result is None


@pytest.mark.asyncio
async def test_find_by_display_name_parameterized_no_injection(tmp_db, real_audio_file):
    """SQL special chars in name must not cause errors."""
    state = GlobalState()
    await index_clip(
        tmp_db,
        real_audio_file,
        state,
        prompt="safe",
        display_name="Safe - Normal Track",
    )
    # This should not raise; it also should not match anything
    result = await find_by_display_name(tmp_db, "'; DROP TABLE audio_clips; --")
    assert result is None
    # Original record still intact
    async with tmp_db.execute("SELECT COUNT(*) FROM audio_clips") as cur:
        row = await cur.fetchone()
    assert row[0] == 1
