"""Audio clip library — index, reuse, and search audio clips by display_name."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import aiosqlite
import orjson

from core.state import GlobalState

AudioSource = Literal["generated", "uploaded", "external"]


async def index_clip(
    conn: aiosqlite.Connection,
    path: Path,
    state: GlobalState,
    prompt: str,
    *,
    source: AudioSource = "generated",
    display_name: str = "",
) -> None:
    """Insert or replace an audio clip record in the library."""
    mood_snapshot = orjson.dumps(
        {
            "excitation": state.excitation,
            "anxiete": state.anxiete,
            "drift_bpm": state.drift_bpm,
        }
    ).decode()
    await conn.execute(
        """
        INSERT INTO audio_clips
            (path, prompt, source, display_name, created_at, last_played_at,
             play_count, duration_s, mood_snapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            prompt        = excluded.prompt,
            source        = excluded.source,
            display_name  = excluded.display_name,
            mood_snapshot = excluded.mood_snapshot
        """,
        (
            str(path),
            prompt,
            source,
            display_name,
            time.time(),
            0.0,
            0,
            0.0,
            mood_snapshot,
        ),
    )
    await conn.commit()


async def find_reusable(
    conn: aiosqlite.Connection,
    state: GlobalState,
    max_play_count: int = 3,
) -> tuple[Path, str] | None:
    """Return (path, display_name) of a reusable clip, or None if none found.

    A clip is reusable when it exists on disk and has been played fewer than
    *max_play_count* times.
    """
    async with conn.execute(
        """
        SELECT path, display_name FROM audio_clips
        WHERE play_count < ?
        ORDER BY last_played_at ASC
        LIMIT 10
        """,
        (max_play_count,),
    ) as cur:
        rows = [row async for row in cur]

    for row in rows:
        p = Path(row[0])
        if p.exists():
            return (p, row[1])
    return None


async def find_by_display_name(
    conn: aiosqlite.Connection,
    name: str,
) -> tuple[Path, str] | None:
    """Case-insensitive search by display_name. Returns (path, display_name) or None."""
    async with conn.execute(
        """
        SELECT path, display_name FROM audio_clips
        WHERE LOWER(display_name) LIKE LOWER(?)
        ORDER BY last_played_at DESC LIMIT 1
        """,
        (f"%{name}%",),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    p = Path(row[0])
    return (p, row[1]) if p.exists() else None
