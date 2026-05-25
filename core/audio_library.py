"""Audio clip library — index, reuse, and search audio clips by display_name."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import aiosqlite
import numpy as np
import orjson
import structlog

from core.state import GlobalState

log = structlog.get_logger()

AudioSource = Literal["generated", "uploaded", "external", "reference", "fal_derived"]

_CIRCLE = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]


def _key_score(key_a: str, key_b: str) -> float:
    """+2.0 same key, +1.0 adjacent in circle of fifths, 0.0 otherwise."""
    if not key_a or not key_b:
        return 0.0
    ka = key_a.split("/")[0].strip()
    kb = key_b.split("/")[0].strip()
    if ka == kb:
        return 2.0
    try:
        ia = _CIRCLE.index(ka)
        ib = _CIRCLE.index(kb)
        if min(abs(ia - ib), 12 - abs(ia - ib)) == 1:
            return 1.0
    except ValueError:
        pass
    return 0.0


async def index_clip(
    conn: aiosqlite.Connection,
    path: Path,
    state: GlobalState,
    prompt: str,
    *,
    source: AudioSource = "generated",
    display_name: str = "",
    territory: str = "",
    extra_mood: dict[str, object] | None = None,
) -> None:
    """Insert or replace an audio clip record in the library.

    *extra_mood* is merged into the mood_snapshot JSON alongside the core state
    fields.  Use it to store supplemental analysis values (e.g. trim_start_s,
    mfcc_fingerprint) that are not part of GlobalState.
    """
    mood_data: dict[str, object] = {
        "excitement": state.excitement,
        "anxiety": state.anxiety,
        "drift_bpm": state.drift_bpm,
        "harmonic_complexity": state.harmonic_complexity,
        "musical_tension": state.musical_tension,
        "drift_timbre": state.drift_timbre,
    }
    if extra_mood:
        mood_data.update(extra_mood)
    mood_snapshot = orjson.dumps(mood_data).decode()
    clip_territory = territory or state.drift_territory
    duration_s = float(extra_mood["duration_s"]) if extra_mood and "duration_s" in extra_mood else 0.0  # type: ignore[arg-type]
    if extra_mood and "drift_key" in extra_mood:
        audio_key = str(extra_mood["drift_key"])
    else:
        audio_key = state.drift_key
    await conn.execute(
        """
        INSERT INTO audio_clips
            (path, prompt, source, display_name, created_at, last_played_at,
             play_count, duration_s, mood_snapshot, territory, audio_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            prompt        = excluded.prompt,
            source        = excluded.source,
            display_name  = excluded.display_name,
            mood_snapshot = excluded.mood_snapshot,
            territory     = excluded.territory,
            audio_key     = excluded.audio_key
        """,
        (
            str(path),
            prompt,
            source,
            display_name,
            time.time(),
            0.0,
            0,
            duration_s,
            mood_snapshot,
            clip_territory,
            audio_key,
        ),
    )
    await conn.commit()


async def cleanup_ghost_paths(conn: aiosqlite.Connection) -> int:
    """Delete audio_clips rows whose files no longer exist on disk.

    Returns the number of rows deleted. Call this at startup to prevent
    DB bloat from accumulated stale references to deleted audio files.
    """
    async with conn.execute("SELECT path FROM audio_clips") as cur:
        all_rows = await cur.fetchall()
    ghosts = [r[0] for r in all_rows if not Path(r[0]).exists()]
    if ghosts:
        await conn.executemany(
            "DELETE FROM audio_clips WHERE path = ?", [(p,) for p in ghosts]
        )
        await conn.commit()
        log.info("ghost_paths_cleaned", count=len(ghosts))
    return len(ghosts)


async def find_reusable(
    conn: aiosqlite.Connection,
    state: GlobalState,
    max_play_count: int = 999,
    cooldown_s: float = 36000.0,
) -> tuple[Path, str] | None:
    """Return (path, display_name) of a reusable clip scored by state match, or None.

    A clip is reusable when it exists on disk, has been played fewer than
    *max_play_count* times, and was last played more than *cooldown_s* seconds
    ago (prevents back-to-back replays). Candidates are ranked by territory,
    BPM proximity, and mood cosine similarity to the current state.
    """
    import orjson as _json

    min_last_played = time.time() - cooldown_s
    async with conn.execute(
        """
        SELECT path, display_name, territory, mood_snapshot, audio_key FROM audio_clips
        WHERE play_count < ? AND source != 'reference'
          AND (last_played_at IS NULL OR last_played_at < ?)
        ORDER BY last_played_at ASC
        LIMIT 20
        """,
        (max_play_count, min_last_played),
    ) as cur:
        rows = [
            dict(zip(["path", "display_name", "territory", "mood_snapshot", "audio_key"], row))
            async for row in cur
        ]

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
            # Key compatibility scoring via circle of fifths
            audio_key = snap.get("audio_key") or row.get("audio_key") or ""
            s += _key_score(audio_key, state.drift_key)
            # MFCC cosine similarity
            ref_mfcc = snap.get("mfcc_fingerprint")
            if ref_mfcc and state.mfcc_fingerprint:
                ref_vec = np.array(ref_mfcc, dtype=np.float32)
                cur_vec = np.array(state.mfcc_fingerprint, dtype=np.float32)
                norm_mfcc = np.linalg.norm(ref_vec) * np.linalg.norm(cur_vec)
                if norm_mfcc > 0:
                    s += float(np.dot(ref_vec, cur_vec) / norm_mfcc)
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
    """Case-insensitive search by display_name. Returns (path, display_name) or None.

    Spaces in *name* are treated as wildcards so "echo frontier chasing shadows"
    matches "Echo Frontier - Chasing Shadows" (the ' - ' separator is skipped).
    """
    words = name.strip().split()
    pattern = "%" + "%".join(words) + "%"
    async with conn.execute(
        """
        SELECT path, display_name FROM audio_clips
        WHERE LOWER(display_name) LIKE LOWER(?)
        ORDER BY last_played_at DESC LIMIT 1
        """,
        (pattern,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    p = Path(row[0])
    return (p, row[1]) if p.exists() else None
