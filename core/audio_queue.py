"""Audio queue — generates clips via Stable Audio API and manages the playback queue."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiosqlite
import structlog

from core.audio_library import find_reusable, index_clip
from core.state import GlobalState
from core.track_namer import generate_track_name

log = structlog.get_logger()

_POLL_INTERVAL = 5.0          # seconds between queue-fill attempts
_QUEUE_TARGET  = 2            # desired minimum clips in playback_queue
_CLIPS_DIR     = Path("streams/audio")
_FALLBACK_DIR  = Path("assets/fallback")


# ── Helpers ───────────────────────────────────────────────────────────────────


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


async def _generate_from_reference(ref_path: Path, prompt: str) -> bytes:
    """Derive a new clip from *ref_path* using the fal.ai audio-to-audio endpoint."""
    import base64

    import fal_client  # type: ignore[import-untyped]

    with ref_path.open("rb") as fh:
        ref_bytes = fh.read()

    mime = "audio/wav" if ref_path.suffix.lower() == ".wav" else "audio/mpeg"
    data_uri = f"data:{mime};base64,{base64.b64encode(ref_bytes).decode()}"

    result = await fal_client.run_async(
        "fal-ai/stable-audio-25/audio-to-audio",
        arguments={
            "prompt": prompt,
            "audio_url": data_uri,
            "strength": 0.65,
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


async def find_reference(
    conn: aiosqlite.Connection,
    state: GlobalState,
) -> Path | None:
    """Return a reference clip path to derive from, or None."""
    async with conn.execute(
        """
        SELECT path FROM audio_clips
        WHERE source IN ('generated', 'fal_derived')
          AND play_count >= 1
        ORDER BY last_played_at DESC
        LIMIT 5
        """,
    ) as cur:
        rows = [row async for row in cur]

    for row in rows:
        p = Path(row[0])
        if p.exists():
            return p
    return None


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

    # Index fallback clips on startup
    fallback_paths = await _index_fallback_clips(conn, state, state_queue)
    ready: list[Path] = list(fallback_paths)

    log.info("audio_queue_started", fallbacks=len(fallback_paths))

    while True:
        # ── Reuse an existing clip if available ───────────────────────────────
        result = await find_reusable(conn, state)
        if result is not None:
            candidate, display_name = result
            await mark_played(conn, candidate)
            ready.append(candidate)
            if playback_queue is not None:
                await playback_queue.put(candidate)
            if display_name:
                await state_queue.put({"current_track_name": display_name})
            await state_queue.put({"queue_length": len(ready)})
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        # ── Generate a new clip ───────────────────────────────────────────────
        prompt = _build_prompt(state)
        ref_path = await find_reference(conn, state)

        try:
            # Launch name generation concurrently with audio generation
            name_task = asyncio.create_task(generate_track_name(state))

            if ref_path is not None:
                audio_bytes = await _generate_from_reference(ref_path, prompt)
            else:
                audio_bytes = await _generate_audio(prompt)

            display_name = await name_task

            import time as _time

            outpath = _CLIPS_DIR / f"clip_{int(_time.time() * 1000)}.mp3"
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

            ready.append(outpath)
            if playback_queue is not None:
                await playback_queue.put(outpath)
            await state_queue.put({"queue_length": len(ready)})

            log.info(
                "audio_clip_generated",
                path=str(outpath),
                display_name=display_name,
                source="fal_derived" if ref_path else "generated",
            )

        except Exception:
            log.exception("audio_generation_error", prompt=prompt)

        await asyncio.sleep(_POLL_INTERVAL)
