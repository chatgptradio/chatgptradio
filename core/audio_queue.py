"""Audio queue — generates clips via Stable Audio API and manages the playback queue."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path

import aiosqlite
import structlog

from core.audio_library import find_reusable, index_clip
from core.state import GlobalState
from core.track_namer import generate_track_name

log = structlog.get_logger()

_POLL_INTERVAL    = 5.0          # seconds between queue-fill attempts
_QUEUE_TARGET     = 2            # desired minimum clips in playback_queue
_RESCAN_INTERVAL  = 60.0         # seconds between references directory rescans
_CLIPS_DIR        = Path("streams/audio")
_FALLBACK_DIR     = Path("assets/fallback")
_REFERENCES_DIR   = Path("streams/references")
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_ref_duration(path: Path) -> int:
    """Return audio duration in seconds via ffprobe, or 0 on failure."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    try:
        return int(float(stdout.decode().strip()))
    except (ValueError, UnicodeDecodeError):
        return 0


async def _wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Convert raw WAV bytes to MP3 via ffmpeg (192k CBR)."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "wav", "-i", "pipe:0",
        "-codec:a", "libmp3lame", "-b:a", "192k",
        "-f", "mp3", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    mp3_bytes, _ = await proc.communicate(input=wav_bytes)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg WAV→MP3 conversion failed")
    return mp3_bytes


# ── Internal audio generation helpers ────────────────────────────────────────


async def _generate_audio(prompt: str) -> bytes:
    """Generate audio bytes via Stable Audio 2.5 / fal.ai text-to-audio endpoint."""
    import fal_client  # type: ignore[import-untyped]

    result = await fal_client.run_async(
        "fal-ai/stable-audio-25/text-to-audio",
        arguments={
            "prompt": prompt,
            "total_seconds": 47,
            "num_inference_steps": 8,
        },
    )
    audio_url: str = result["audio"]["url"]

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as resp:
            resp.raise_for_status()
            wav_bytes = await resp.read()
    return await _wav_to_mp3(wav_bytes)


async def _generate_from_reference(ref_path: Path, prompt: str, state: GlobalState) -> bytes:
    """Derive a new clip from *ref_path* using the fal.ai audio-to-audio endpoint."""
    import base64

    import fal_client  # type: ignore[import-untyped]

    with ref_path.open("rb") as fh:
        ref_bytes = fh.read()

    mime = "audio/wav" if ref_path.suffix.lower() == ".wav" else "audio/mpeg"
    data_uri = f"data:{mime};base64,{base64.b64encode(ref_bytes).decode()}"

    strength = max(0.3, min(0.9,
        0.3 + state.drift_velocity * 0.4 + state.crisis_level * 0.3
    ))
    guidance_scale = max(1.0, min(1.2,
        1.0 + state.source_divergence * 0.2
    ))

    # Use reference file's actual duration (no arbitrary cap) — max 190s (Stable Audio limit)
    ref_secs = await _get_ref_duration(ref_path)
    total_seconds = min(max(ref_secs, 30), 190) if ref_secs else 90

    result = await fal_client.run_async(
        "fal-ai/stable-audio-25/audio-to-audio",
        arguments={
            "prompt": prompt,
            "audio_url": data_uri,
            "strength": strength,
            "guidance_scale": guidance_scale,
            "num_inference_steps": 8,
            "total_seconds": total_seconds,
        },
    )
    audio_url: str = result["audio"]["url"]

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as resp:
            resp.raise_for_status()
            wav_bytes = await resp.read()
    return await _wav_to_mp3(wav_bytes)


async def find_reference(
    conn: aiosqlite.Connection,
    state: GlobalState,
) -> Path | None:
    """Return a reference clip path to derive from, scored by state match."""
    import json as _json

    async with conn.execute(
        """
        SELECT path, territory, mood_snapshot FROM audio_clips
        WHERE (source = 'reference')
           OR (source IN ('generated', 'fal_derived') AND play_count >= 1)
        ORDER BY last_played_at ASC
        LIMIT 20
        """,
    ) as cur:
        rows = [dict(zip(["path", "territory", "mood_snapshot"], row)) async for row in cur]

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
    return Path(best[0]["path"])


async def mark_played(conn: aiosqlite.Connection, path: Path) -> None:
    """Increment play_count and update last_played_at for *path*."""
    import time

    await conn.execute(
        """
        UPDATE audio_clips
        SET play_count = play_count + 1,
            last_played_at = ?
        WHERE path = ?
        """,
        (time.time(), str(path)),
    )
    await conn.commit()


# ── Crisis cache ──────────────────────────────────────────────────────────────


async def _build_crisis_cache(
    conn: aiosqlite.Connection,
    state: GlobalState,
    prompt: str,
    count: int = 3,
) -> list[Path]:
    """Pre-generate *count* crisis clips in the background."""
    _CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # Use a minimal state snapshot that signals high crisis for naming
    import copy
    crisis_state = copy.copy(state)

    for i in range(count):
        try:
            name_task = asyncio.create_task(generate_track_name(crisis_state))
            audio_bytes = await _generate_audio(prompt)
            display_name = await name_task

            path = _CLIPS_DIR / f"crisis_{i:03d}.mp3"
            path.write_bytes(audio_bytes)
            await index_clip(
                conn,
                path,
                crisis_state,
                prompt,
                source="generated",
                display_name=display_name,
            )
            paths.append(path)
            log.info(
                "crisis_clip_cached",
                index=i,
                display_name=display_name,
            )
        except Exception:
            log.exception("crisis_clip_generation_error", index=i)

    return paths


# ── Fallback clip naming ───────────────────────────────────────────────────────


async def _backfill_fallback_names(
    conn: aiosqlite.Connection,
    state: GlobalState,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
) -> None:
    """For fallback clips already indexed with display_name == '', generate and persist names."""
    async with conn.execute(
        "SELECT path FROM audio_clips WHERE source = 'uploaded' AND display_name = ''"
    ) as cur:
        rows = [row async for row in cur]

    for row in rows:
        p = Path(row[0])
        if not p.exists():
            continue
        try:
            dn = await generate_track_name(state)
            if dn:
                await conn.execute(
                    "UPDATE audio_clips SET display_name = ? WHERE path = ? AND display_name = ''",
                    (dn, str(p)),
                )
                await conn.commit()
                await state_queue.put({"current_track_name": dn})
                log.info("fallback_clip_named", path=str(p), display_name=dn)
        except Exception:
            log.exception("fallback_name_error", path=str(p))


async def _index_fallback_clips(
    conn: aiosqlite.Connection,
    state: GlobalState,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
) -> list[Path]:
    """Index fallback clips from *_FALLBACK_DIR* that are not yet in the DB."""
    if not _FALLBACK_DIR.exists():
        return []

    paths: list[Path] = []
    for fallback in sorted(_FALLBACK_DIR.glob("*.mp3")):
        # Check if already indexed
        async with conn.execute(
            "SELECT display_name FROM audio_clips WHERE path = ?",
            (str(fallback),),
        ) as cur:
            row = await cur.fetchone()

        if row is None:
            # New fallback — index with empty display_name first
            await index_clip(
                conn, fallback, state, prompt="", source="uploaded", display_name=""
            )
            row = ("",)

        if row[0] == "":
            dn = await generate_track_name(state)
            if dn:
                await conn.execute(
                    "UPDATE audio_clips SET display_name = ? WHERE path = ? AND display_name = ''",
                    (dn, str(fallback)),
                )
                await conn.commit()
                await state_queue.put({"current_track_name": dn})

        paths.append(fallback)

    return paths


# ── Auto-index references on startup ─────────────────────────────────────────


async def _auto_index_references_on_startup(
    conn: aiosqlite.Connection,
    state: GlobalState,
) -> int:
    """Index any new files in streams/references/ that are not yet in the DB.

    Runs at startup — no librosa analysis (use scripts/index_references.py for
    BPM/territory enrichment). Guarantees references are immediately available
    as audio-to-audio sources even before the script is run manually.
    """
    if not _REFERENCES_DIR.exists():
        return 0

    async with conn.execute(
        "SELECT path FROM audio_clips WHERE source = 'reference'"
    ) as cur:
        indexed = {row[0] async for row in cur}

    new_count = 0
    for path in sorted(_REFERENCES_DIR.iterdir()):
        if path.suffix.lower() not in _AUDIO_EXTENSIONS:
            continue
        if str(path) in indexed:
            continue
        await index_clip(conn, path, state, prompt="", source="reference", display_name=path.stem)
        new_count += 1

    if new_count:
        log.info("references_auto_indexed", count=new_count)
    return new_count


# ── Music prompt builder ──────────────────────────────────────────────────────


def _build_prompt(state: GlobalState) -> str:
    """Derive a Stable Audio text prompt from GlobalState."""
    from builders.music_prompt import build_music_prompt

    return build_music_prompt(state)


# ── Main loop ─────────────────────────────────────────────────────────────────


async def run_audio_queue(
    state: GlobalState,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
    conn: aiosqlite.Connection,
    playback_queue: asyncio.Queue | None,  # type: ignore[type-arg]
) -> None:
    """Main audio queue coroutine.

    Continuously fills *playback_queue* with generated audio clips.
    Pushes ``{"current_track_name": name}`` to *state_queue* whenever a
    clip with a non-empty display name is queued.
    """
    api_key = os.environ.get("FAL_API_KEY", "") or os.environ.get("FAL_KEY", "")
    if not api_key:
        log.warning("audio_queue_disabled", reason="no API key")
        return
    # fal_client SDK only reads FAL_KEY; expose our key under that name if needed
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = api_key

    _CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    fallback_paths = await _index_fallback_clips(conn, state, state_queue)
    refs_indexed = await _auto_index_references_on_startup(conn, state)

    log.info("audio_queue_started", fallbacks=len(fallback_paths), refs_indexed=refs_indexed)

    last_refs_scan = time.time()

    while True:
        # ── Periodic rescan of streams/references/ for newly deposited files ──
        now = time.time()
        if now - last_refs_scan >= _RESCAN_INTERVAL:
            await _auto_index_references_on_startup(conn, state)
            last_refs_scan = now

        # ── Only fill queue when below target ─────────────────────────────────
        qsize = playback_queue.qsize() if playback_queue is not None else 0
        if qsize >= _QUEUE_TARGET:
            await state_queue.put({"queue_length": qsize})
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        # ── Reuse an existing clip if available ───────────────────────────────
        result = await find_reusable(conn, state)
        if result is not None:
            candidate, display_name = result
            await mark_played(conn, candidate)
            if playback_queue is not None:
                await playback_queue.put(candidate)
            if display_name:
                await state_queue.put({"current_track_name": display_name})
            await state_queue.put({"queue_length": playback_queue.qsize() if playback_queue is not None else 1})
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        # ── Generate a new clip ───────────────────────────────────────────────
        prompt = _build_prompt(state)
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        if prompt_hash == state.last_prompt_hash and qsize > 0:
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        ref_path = await find_reference(conn, state)

        try:
            name_task = asyncio.create_task(generate_track_name(state))

            if ref_path is not None:
                audio_bytes = await _generate_from_reference(ref_path, prompt, state)
                # Rotate references: update last_played_at so next generation favours others
                await mark_played(conn, ref_path)
            else:
                audio_bytes = await _generate_audio(prompt)

            display_name = await name_task

            outpath = _CLIPS_DIR / f"clip_{int(time.time() * 1000)}.mp3"
            outpath.write_bytes(audio_bytes)

            await index_clip(
                conn,
                outpath,
                state,
                prompt,
                source="fal_derived" if ref_path else "generated",
                display_name=display_name,
            )

            if display_name:
                await state_queue.put({"current_track_name": display_name})

            await state_queue.put({"last_prompt_hash": prompt_hash})
            if playback_queue is not None:
                await playback_queue.put(outpath)
            await state_queue.put({"queue_length": playback_queue.qsize() if playback_queue is not None else 1})

            log.info(
                "audio_clip_generated",
                path=str(outpath),
                display_name=display_name,
                source="fal_derived" if ref_path else "generated",
            )

        except Exception:
            log.exception("audio_generation_error", prompt=prompt)

        await asyncio.sleep(_POLL_INTERVAL)
