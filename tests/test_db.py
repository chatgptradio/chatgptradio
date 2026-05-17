import asyncio
import time
import pytest
import orjson

from core.db import init_db, persist_snapshot, persist_signal, purge_old_data
from core.state import GlobalState


@pytest.fixture
async def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    c = await init_db(db_path)
    yield c
    await c.close()


async def test_init_creates_tables(conn):
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        tables = {row[0] async for row in cur}
    assert "state_snapshots" in tables
    assert "signal_history" in tables
    assert "viewers" in tables


async def test_wal_mode(conn):
    async with conn.execute("PRAGMA journal_mode") as cur:
        row = await cur.fetchone()
    assert row[0] == "wal"


async def test_persist_snapshot_writes_json(conn):
    state = GlobalState(excitation=0.7, crisis_level=0.2)
    await persist_snapshot(conn, state)
    async with conn.execute("SELECT state_json FROM state_snapshots ORDER BY id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    assert row is not None
    data = orjson.loads(row[0])
    assert data["excitation"] == pytest.approx(0.7)
    assert data["crisis_level"] == pytest.approx(0.2)


async def test_persist_snapshot_roundtrip(conn):
    state = GlobalState(viewers=42, drift_bpm=110.0)
    await persist_snapshot(conn, state)
    async with conn.execute("SELECT state_json FROM state_snapshots LIMIT 1") as cur:
        row = await cur.fetchone()
    restored = GlobalState.model_validate(orjson.loads(row[0]))
    assert restored.viewers == 42
    assert restored.drift_bpm == pytest.approx(110.0)


async def test_persist_signal(conn):
    await persist_signal(conn, "excitation", 0.5, 0.4, 0.1, 0.05)
    async with conn.execute("SELECT signal, value, baseline, error, vol FROM signal_history") as cur:
        row = await cur.fetchone()
    assert row[0] == "excitation"
    assert row[1] == pytest.approx(0.5)
    assert row[3] == pytest.approx(0.1)


async def test_purge_old_data(conn):
    old_ts = time.time() - 40 * 86400
    await conn.execute(
        "INSERT INTO state_snapshots (ts, state_json) VALUES (?, ?)", (old_ts, '{"x":1}')
    )
    await conn.execute(
        "INSERT INTO signal_history (ts, signal, value, baseline, error, vol) VALUES (?, ?, ?, ?, ?, ?)",
        (old_ts, "s", 0.0, 0.0, 0.0, 0.0),
    )
    await conn.commit()

    state = GlobalState()
    await persist_snapshot(conn, state)
    await persist_signal(conn, "fresh", 1.0, 1.0, 0.0, 0.01)

    await purge_old_data(conn, snapshot_days=30, history_days=30)

    async with conn.execute("SELECT COUNT(*) FROM state_snapshots") as cur:
        count = (await cur.fetchone())[0]
    assert count == 1

    async with conn.execute("SELECT COUNT(*) FROM signal_history") as cur:
        count = (await cur.fetchone())[0]
    assert count == 1
