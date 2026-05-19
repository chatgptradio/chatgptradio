"""Persistent memory — journal history, self-model restore, viewer tracking."""
import time
from dataclasses import dataclass, field

import aiosqlite
import orjson

from core.state import GlobalState

_TREND_SIGNALS = ["excitation", "anxiete", "crisis_level", "world_temperature", "anomaly_score"]


@dataclass
class MemoryContext:
    journal_entries: list[str] = field(default_factory=list)
    signal_trends: dict[str, float] = field(default_factory=dict)
    recognized_viewers: list[str] = field(default_factory=list)


async def load_memory_context(
    conn: aiosqlite.Connection,
    state: GlobalState,
    *,
    journal_limit: int = 10,
    trend_window_min: int = 30,
) -> MemoryContext:
    # journal_entries: N most recent, returned in chronological order
    async with conn.execute(
        "SELECT entry FROM journal_entries ORDER BY ts DESC LIMIT ?",
        (journal_limit,),
    ) as cur:
        rows = list(await cur.fetchall())
    journal_entries = [row[0] for row in rows[::-1]]

    # signal_trends: delta = current state value − mean of history in window
    cutoff = time.time() - trend_window_min * 60
    signal_trends: dict[str, float] = {}
    for signal in _TREND_SIGNALS:
        async with conn.execute(
            "SELECT AVG(value) FROM signal_history WHERE signal = ? AND ts >= ?",
            (signal, cutoff),
        ) as cur:
            row = await cur.fetchone()
        avg = row[0] if row and row[0] is not None else None
        if avg is not None:
            current = float(getattr(state, signal, 0.0))
            signal_trends[signal] = current - avg

    recognized_viewers = await get_active_regulars(conn)

    return MemoryContext(
        journal_entries=journal_entries,
        signal_trends=signal_trends,
        recognized_viewers=recognized_viewers,
    )


async def save_journal_entry(conn: aiosqlite.Connection, entry: str) -> None:
    await conn.execute(
        "INSERT INTO journal_entries (ts, entry) VALUES (?, ?)",
        (time.time(), entry),
    )
    await conn.commit()


async def restore_self_model(conn: aiosqlite.Connection, state: GlobalState) -> None:
    async with conn.execute(
        "SELECT state_json FROM state_snapshots ORDER BY ts DESC LIMIT 1"
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return
    data = orjson.loads(row[0])
    for field_name in ("signal_baselines", "signal_volatilities", "drift_momentum", "drift_weights"):
        if field_name in data:
            setattr(state, field_name, data[field_name])


async def upsert_viewer(
    conn: aiosqlite.Connection,
    viewer_id: str,
    display_name: str,
) -> None:
    now = time.time()
    async with conn.execute(
        "SELECT viewer_id FROM viewers WHERE viewer_id = ?", (viewer_id,)
    ) as cur:
        existing = await cur.fetchone()
    if existing:
        await conn.execute(
            "UPDATE viewers SET last_seen = ?, session_count = session_count + 1, display_name = ? WHERE viewer_id = ?",
            (now, display_name, viewer_id),
        )
    else:
        await conn.execute(
            "INSERT INTO viewers (viewer_id, first_seen, last_seen, session_count, display_name) VALUES (?, ?, ?, ?, ?)",
            (viewer_id, now, now, 1, display_name),
        )
    await conn.commit()


async def get_active_regulars(
    conn: aiosqlite.Connection,
    min_sessions: int = 3,
) -> list[str]:
    async with conn.execute(
        "SELECT display_name FROM viewers WHERE session_count >= ? AND display_name != '' ORDER BY session_count DESC",
        (min_sessions,),
    ) as cur:
        rows = await cur.fetchall()
    return [row[0] for row in rows]
