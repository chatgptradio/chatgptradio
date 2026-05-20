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
    session_count INTEGER DEFAULT 1,
    display_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    entry TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_je ON journal_entries(ts);

CREATE TABLE IF NOT EXISTS audio_clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    prompt TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'generated',
    display_name TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    last_played_at REAL NOT NULL DEFAULT 0,
    play_count INTEGER NOT NULL DEFAULT 0,
    duration_s REAL NOT NULL DEFAULT 0,
    mood_snapshot TEXT NOT NULL DEFAULT '',
    territory TEXT DEFAULT ''
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

    # Idempotent migration: rebuild audio_clips if the old legacy schema is detected.
    # The old schema used 'filename' as the UNIQUE key; the current schema uses 'path'.
    async with conn.execute("PRAGMA table_info(audio_clips)") as cur:
        cols = {row[1] async for row in cur}

    if "filename" in cols:
        # Legacy schema detected — rebuild the table preserving existing data.
        await conn.execute("ALTER TABLE audio_clips RENAME TO _audio_clips_legacy")
        await conn.execute(
            """
            CREATE TABLE audio_clips (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                path           TEXT NOT NULL UNIQUE,
                prompt         TEXT NOT NULL DEFAULT '',
                source         TEXT NOT NULL DEFAULT 'generated',
                display_name   TEXT NOT NULL DEFAULT '',
                created_at     REAL NOT NULL DEFAULT 0,
                last_played_at REAL NOT NULL DEFAULT 0,
                play_count     INTEGER NOT NULL DEFAULT 0,
                duration_s     REAL NOT NULL DEFAULT 0,
                mood_snapshot  TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Copy rows, mapping old columns to new ones; skip rows with duplicate path.
        await conn.execute(
            """
            INSERT OR IGNORE INTO audio_clips
                (path, prompt, source, display_name, created_at, last_played_at,
                 play_count, duration_s, mood_snapshot)
            SELECT
                path,
                COALESCE(prompt, prompt_text, ''),
                COALESCE(source, 'generated'),
                COALESCE(display_name, ''),
                created_at,
                COALESCE(last_played_at, 0),
                COALESCE(play_count, played_count, 0),
                COALESCE(duration_s, 0),
                COALESCE(mood_snapshot, '')
            FROM _audio_clips_legacy
            """
        )
        await conn.execute("DROP TABLE _audio_clips_legacy")
        await conn.commit()

    # Idempotent migration: add display_name to viewers if missing.
    async with conn.execute("PRAGMA table_info(viewers)") as cur:
        viewer_cols = {row[1] async for row in cur}
    if "display_name" not in viewer_cols:
        await conn.execute(
            "ALTER TABLE viewers ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
        )
        await conn.commit()

    # Add territory column if missing (idempotent)
    try:
        await conn.execute("ALTER TABLE audio_clips ADD COLUMN territory TEXT DEFAULT ''")
        await conn.commit()
    except Exception:
        pass

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
