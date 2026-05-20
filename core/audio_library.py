"""Audio clip library — index, reuse, and search audio clips by display_name."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import aiosqlite
import orjson

from core.state import GlobalState

AudioSource = Literal["generated", "uploaded", "external", "reference", "fal_derived"]


async def index_clip(
    conn: aiosqlite.Connection,
    path: Path,
    state: GlobalState,
    prompt: str,
    *,
    source: AudioSource = "generated",
    display_name: str = "",
    territory: str = "",
) -> None:
    """Insert or replace an audio clip record in the library."""
    mood_snapshot = orjson.dumps(
        {
            "excitement": state.excitement,
            "anxiety": state.anxiety,
            "drift_bpm": state.drift_bpm,
        }
    ).decode()
    clip_territory = territory or state.drift_territory
    await conn.execute(
        """
        INSERT INTO audio_clips
            (path, prompt, source, display_name, created_at, last_played_at,
             play_count, duration_s, mood_snapshot, territory)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            prompt        = excluded.prompt,
            source        = excluded.source,
            display_name  = excluded.display_name,
            mood_snapshot = excluded.mood_snapshot,
            territory     = excluded.territory
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
            clip_territory,
        ),
    )
    await conn.commit()


async def find_reusable(
    conn: aiosqlite.Connection,
    state: GlobalState,
    max_play_count: int = 3,
) -> tuple[Path, str] | None:
    """Return (path, display_name) of a reusable clip scored by state match, or None.

    A clip is reusable when it exists on disk and has been played fewer than
    *max_play_count* times. Candidates are ranked by territory, BPM proximity,
    and mood cosine similarity to the current state.
    """
    import json as _json

    async with conn.execute(
        """
        SELECT path, display_name, territory, mood_snapshot FROM audio_clips
        WHERE play_count < ? AND source != 'reference'
        ORDER BY last_played_at ASC
        LIMIT 20
        """,
        (max_play_count,),
    ) as cur:
        rows = [dict(zip(["path", "display_name", "territory", "mood_snapshot"], row)) async for row in cur]

    def _score(row: dict) -> float:
        s = 0.0
        if row.get("territory") == state.drift_territory:
            s += 3.0
        try:
            snap = _json.loads(row.get("mood_snapshot") or "{}")
            bpm_diff = abs(snap.get("drift_bpm", state.drift_bpm) - state.drift_bpm)
            s += max(0.0, 2.0 * (1.0 - bpm_diff / 15.0))
            ref_exc = snap.get("excitement", 0.0)
            ref_anx = snap.get("anxiety", 0.0)
            dot = ref_exc * state.excitement + ref_anx * state.anxiety
            norm = (ref_exc**2 + ref_anx**2) ** 0.5 * (state.excitement**2 + state.anxiety**2) ** 0.5
            if norm > 0:
                s += dot / norm
        except Exception:
            pass
        return s

    candidates = [(row, _score(row)) for row in rows if Path(row["path"]).exists()]
    if not candidates:
        return None
    best = max(candidates, key=lambda x: x[1])
    return (Path(best[0]["path"]), best[0].get("display_name", ""))


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
