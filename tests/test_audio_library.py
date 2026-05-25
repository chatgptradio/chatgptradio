"""Tests for core/audio_library.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.audio_library import (
    _key_score,
    cleanup_ghost_paths,
    find_by_display_name,
    find_reusable,
    index_clip,
)
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
    state = GlobalState(excitement=0.5)
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


# ── find_reusable territory scoring ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reusable_excludes_references(tmp_db, tmp_path):
    """find_reusable must never return reference clips — they exist only as audio-to-audio sources."""
    state = GlobalState()
    ref_file = tmp_path / "ref.mp3"
    ref_file.write_bytes(b"fake")
    await index_clip(
        tmp_db, ref_file, state, prompt="ref", source="reference", display_name="Ref Track"
    )
    result = await find_reusable(tmp_db, state)
    assert result is None


@pytest.mark.asyncio
async def test_find_reusable_prefers_territory_match(tmp_db, tmp_path):
    """find_reusable returns the clip whose territory matches state.drift_territory."""
    state = GlobalState(drift_territory="ambient")

    clip_ambient = tmp_path / "clip_ambient.mp3"
    clip_ambient.write_bytes(b"fake")
    clip_jazz = tmp_path / "clip_jazz.mp3"
    clip_jazz.write_bytes(b"fake")

    await index_clip(
        tmp_db, clip_ambient, state, prompt="ambient clip",
        display_name="Ambient Track", territory="ambient",
    )
    await index_clip(
        tmp_db, clip_jazz, state, prompt="jazz clip",
        display_name="Jazz Track", territory="jazz",
    )

    result = await find_reusable(tmp_db, state)
    assert result is not None
    path, display_name = result
    assert path == clip_ambient
    assert display_name == "Ambient Track"


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


# ── cleanup_ghost_paths ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_ghost_paths_deletes_missing_files(tmp_db, tmp_path):
    """cleanup_ghost_paths removes rows whose paths no longer exist on disk."""
    state = GlobalState()

    real_file = tmp_path / "real.mp3"
    real_file.write_bytes(b"fake")
    ghost_file = tmp_path / "ghost.mp3"
    # ghost_file is NOT created on disk

    await index_clip(tmp_db, real_file, state, prompt="real", display_name="Real Track")
    await index_clip(tmp_db, ghost_file, state, prompt="ghost", display_name="Ghost Track")

    async with tmp_db.execute("SELECT COUNT(*) FROM audio_clips") as cur:
        row = await cur.fetchone()
    assert row[0] == 2

    deleted = await cleanup_ghost_paths(tmp_db)

    assert deleted == 1
    async with tmp_db.execute("SELECT path FROM audio_clips") as cur:
        remaining = [row[0] async for row in cur]
    assert str(real_file) in remaining
    assert str(ghost_file) not in remaining


@pytest.mark.asyncio
async def test_cleanup_ghost_paths_returns_zero_when_all_exist(tmp_db, tmp_path):
    """cleanup_ghost_paths returns 0 when every indexed path exists on disk."""
    state = GlobalState()

    real_file = tmp_path / "real.mp3"
    real_file.write_bytes(b"fake")
    await index_clip(tmp_db, real_file, state, prompt="real", display_name="Real Track")

    deleted = await cleanup_ghost_paths(tmp_db)

    assert deleted == 0
    async with tmp_db.execute("SELECT COUNT(*) FROM audio_clips") as cur:
        row = await cur.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_cleanup_ghost_paths_empty_db_returns_zero(tmp_db):
    """cleanup_ghost_paths returns 0 on an empty DB without error."""
    deleted = await cleanup_ghost_paths(tmp_db)
    assert deleted == 0


@pytest.mark.asyncio
async def test_cleanup_ghost_paths_deletes_all_when_all_missing(tmp_db, tmp_path):
    """cleanup_ghost_paths deletes all rows when no file exists on disk."""
    state = GlobalState()

    for i in range(3):
        ghost = tmp_path / f"ghost_{i}.mp3"
        # NOT created on disk
        await index_clip(tmp_db, ghost, state, prompt="ghost", display_name=f"Ghost {i}")

    deleted = await cleanup_ghost_paths(tmp_db)

    assert deleted == 3
    async with tmp_db.execute("SELECT COUNT(*) FROM audio_clips") as cur:
        row = await cur.fetchone()
    assert row[0] == 0


# ── _key_score ────────────────────────────────────────────────────────────────


def test_key_score_same_key():
    assert _key_score("C", "C") == 2.0


def test_key_score_adjacent_circle():
    # C and G are adjacent in the circle of fifths
    assert _key_score("C", "G") == 1.0
    assert _key_score("G", "C") == 1.0


def test_key_score_distant():
    # C and F# are diametrically opposite (distance 6) — score 0
    assert _key_score("C", "F#") == 0.0


def test_key_score_empty():
    assert _key_score("", "C") == 0.0
    assert _key_score("C", "") == 0.0
    assert _key_score("", "") == 0.0


# ── find_reusable key matching ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_reusable_prefers_key_match(tmp_db, tmp_path):
    """find_reusable returns the clip whose tonality is compatible with state.drift_key."""
    state = GlobalState(drift_territory="ambient", drift_key="C")

    clip_c = tmp_path / "clip_c.mp3"
    clip_c.write_bytes(b"fake")
    clip_fsharp = tmp_path / "clip_fsharp.mp3"
    clip_fsharp.write_bytes(b"fake")

    # Both clips share the same territory; only key differs
    await index_clip(
        tmp_db,
        clip_c,
        state,
        prompt="clip in C",
        display_name="Track C",
        territory="ambient",
        extra_mood={"drift_key": "C"},
    )
    await index_clip(
        tmp_db,
        clip_fsharp,
        state,
        prompt="clip in F#",
        display_name="Track F#",
        territory="ambient",
        extra_mood={"drift_key": "F#"},
    )

    result = await find_reusable(tmp_db, state)
    assert result is not None
    path, display_name = result
    assert path == clip_c
    assert display_name == "Track C"
