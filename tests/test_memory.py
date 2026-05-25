"""Tests for core/memory.py — journal, self-model restore, viewer tracking."""
import time

import orjson
import pytest

from core.db import init_db
from core.memory import (
    get_active_regulars,
    load_memory_context,
    restore_self_model,
    save_journal_entry,
    upsert_viewer,
)
from core.state import GlobalState


@pytest.fixture
async def conn(tmp_path):
    db_path = str(tmp_path / "test_memory.db")
    c = await init_db(db_path)
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# restore_self_model — MusicVector
# ---------------------------------------------------------------------------


async def test_restore_self_model_restores_music_vector(conn):
    """MusicVector fields are loaded from the most recent snapshot."""
    snap = GlobalState(
        drift_bpm=128.0,
        drift_key="A major",
        drift_timbre="bright",
        drift_territory="euphoric",
    )
    snap_json = orjson.dumps(snap.model_dump(mode="json")).decode()
    await conn.execute(
        "INSERT INTO state_snapshots (ts, state_json) VALUES (?, ?)",
        (time.time(), snap_json),
    )
    await conn.commit()

    state = GlobalState()  # defaults: 90 BPM, C minor, warm, ambient
    await restore_self_model(conn, state)

    assert state.drift_bpm == pytest.approx(128.0)
    assert state.drift_key == "A major"
    assert state.drift_timbre == "bright"
    assert state.drift_territory == "euphoric"


async def test_restore_self_model_uses_latest_snapshot(conn):
    """Only the most recent snapshot is used when multiple exist."""
    for bpm in (90.0, 100.0, 115.0):
        snap = GlobalState(drift_bpm=bpm)
        snap_json = orjson.dumps(snap.model_dump(mode="json")).decode()
        await conn.execute(
            "INSERT INTO state_snapshots (ts, state_json) VALUES (?, ?)",
            (time.time(), snap_json),
        )
    await conn.commit()

    state = GlobalState()
    await restore_self_model(conn, state)

    assert state.drift_bpm == pytest.approx(115.0)


async def test_restore_self_model_with_empty_db_keeps_defaults(conn):
    """Empty state_snapshots table → GlobalState defaults are preserved."""
    state = GlobalState()
    default_bpm = state.drift_bpm
    default_key = state.drift_key
    default_timbre = state.drift_timbre
    default_territory = state.drift_territory

    await restore_self_model(conn, state)  # no rows in DB

    assert state.drift_bpm == pytest.approx(default_bpm)
    assert state.drift_key == default_key
    assert state.drift_timbre == default_timbre
    assert state.drift_territory == default_territory


async def test_restore_self_model_also_restores_ema_fields(conn):
    """Existing EMA restore behaviour is unaffected by the MusicVector change."""
    snap = GlobalState(
        signal_baselines={"excitement": 0.42},
        drift_bpm=110.0,
    )
    snap_json = orjson.dumps(snap.model_dump(mode="json")).decode()
    await conn.execute(
        "INSERT INTO state_snapshots (ts, state_json) VALUES (?, ?)",
        (time.time(), snap_json),
    )
    await conn.commit()

    state = GlobalState()
    await restore_self_model(conn, state)

    assert state.signal_baselines.get("excitement") == pytest.approx(0.42)
    assert state.drift_bpm == pytest.approx(110.0)


# ---------------------------------------------------------------------------
# save_journal_entry / load_memory_context
# ---------------------------------------------------------------------------


async def test_save_and_load_journal_entries(conn):
    state = GlobalState()
    await save_journal_entry(conn, "entry one")
    await save_journal_entry(conn, "entry two")

    ctx = await load_memory_context(conn, state, journal_limit=10)
    assert "entry one" in ctx.journal_entries
    assert "entry two" in ctx.journal_entries
    # chronological order — older entry first
    assert ctx.journal_entries.index("entry one") < ctx.journal_entries.index("entry two")


async def test_load_memory_context_respects_journal_limit(conn):
    state = GlobalState()
    for i in range(15):
        await save_journal_entry(conn, f"entry {i}")

    ctx = await load_memory_context(conn, state, journal_limit=5)
    assert len(ctx.journal_entries) == 5


# ---------------------------------------------------------------------------
# upsert_viewer / get_active_regulars
# ---------------------------------------------------------------------------


async def test_upsert_viewer_increments_session_count(conn):
    await upsert_viewer(conn, "uid1", "Alice")
    await upsert_viewer(conn, "uid1", "Alice")

    async with conn.execute(
        "SELECT session_count FROM viewers WHERE viewer_id = ?", ("uid1",)
    ) as cur:
        row = await cur.fetchone()
    assert row[0] == 2


async def test_get_active_regulars_filters_by_min_sessions(conn):
    await upsert_viewer(conn, "uid_rare", "Rare")
    for _ in range(3):
        await upsert_viewer(conn, "uid_regular", "Regular")

    regulars = await get_active_regulars(conn, min_sessions=3)
    assert "Regular" in regulars
    assert "Rare" not in regulars
