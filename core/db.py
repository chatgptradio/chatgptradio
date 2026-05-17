import time

import aiosqlite
import orjson

from core.state import GlobalState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS state_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    state_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_history (
    ts REAL NOT NULL,
    signal TEXT NOT NULL,
    value REAL,
    baseline REAL,
    error REAL,
    vol REAL
);
CREATE INDEX IF NOT EXISTS idx_sh ON signal_history(signal, ts);

CREATE TABLE IF NOT EXISTS viewers (
    viewer_id TEXT PRIMARY KEY,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    session_count INTEGER DEFAULT 1
);
"""


async def init_db(path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    for stmt in _SCHEMA.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            await conn.execute(stmt)
    await conn.commit()
    return conn


async def persist_snapshot(conn: aiosqlite.Connection, state: GlobalState) -> None:
    json_bytes = orjson.dumps(state.model_dump(mode="json"))
    await conn.execute(
        "INSERT INTO state_snapshots (ts, state_json) VALUES (?, ?)",
        (time.time(), json_bytes.decode()),
    )
    await conn.commit()


async def persist_signal(
    conn: aiosqlite.Connection,
    signal: str,
    value: float,
    baseline: float,
    error: float,
    vol: float,
) -> None:
    await conn.execute(
        "INSERT INTO signal_history (ts, signal, value, baseline, error, vol) VALUES (?, ?, ?, ?, ?, ?)",
        (time.time(), signal, value, baseline, error, vol),
    )
    await conn.commit()


async def purge_old_data(
    conn: aiosqlite.Connection,
    snapshot_days: int,
    history_days: int,
) -> None:
    now = time.time()
    snapshot_cutoff = now - snapshot_days * 86400
    history_cutoff = now - history_days * 86400
    await conn.execute("DELETE FROM state_snapshots WHERE ts < ?", (snapshot_cutoff,))
    await conn.execute("DELETE FROM signal_history WHERE ts < ?", (history_cutoff,))
    await conn.commit()
