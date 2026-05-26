"""Audio queue — generates clips via Stable Audio API and manages the playback queue."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path

import aiosqlite
import orjson
import structlog

from core.audio_library import cleanup_ghost_paths, find_reusable, index_clip
from core.state import GlobalState
from core.track_namer import generate_track_name

log = structlog.get_logger()

try:
    import librosa as _librosa  # type: ignore[import-untyped]
    import numpy as _np  # type: ignore[import-untyped]
    _HAS_LIBROSA = True
except ImportError:
    _HAS_LIBROSA = False

_CIRCLE_OF_FIFTHS = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _key_distance(key_a: str, key_b: str) -> float:
    """Circle of fifths distance 0.0–1.0. 0=same key root, 1=tritone (6 steps)."""
    ka_parts = (key_a or "").split("/")[0].strip().split()
    kb_parts = (key_b or "").split("/")[0].strip().split()
    ka = ka_parts[0] if ka_parts else ""
    kb = kb_parts[0] if kb_parts else ""
    if not ka or not kb:
        return 0.0
    try:
        ia = _CIRCLE_OF_FIFTHS.index(ka)
        ib = _CIRCLE_OF_FIFTHS.index(kb)
        dist = min(abs(ia - ib), 12 - abs(ia - ib))
        return dist / 6.0  # normalize: 0=same, 1=tritone (6 steps)
    except ValueError:
        return 0.0


async def _prestretch_reference(
    ref_path: Path,
    ref_bytes: bytes,
    target_bpm: float,
    ref_bpm: float | None,
) -> bytes:
    """Time-stretch *ref_bytes* so its tempo matches *target_bpm*.

    Returns the original bytes unchanged when the delta is below 2 BPM
    (inaudible difference) or when the BPM information is unavailable.
    """
    if ref_bpm is None or ref_bpm <= 0 or abs(ref_bpm - target_bpm) < 2.0:
        return ref_bytes

    ratio = target_bpm / ref_bpm
    ratio = _clamp(ratio, 0.5, 2.0)  # cap at ±1 octave

    try:
        import io

        import numpy as np
        import pyrubberband
        import soundfile as sf

        loop = asyncio.get_running_loop()

        def _stretch() -> bytes:
            audio, sr = sf.read(io.BytesIO(ref_bytes))
            if audio.ndim == 1:
                audio = audio[:, np.newaxis]
            stretched = pyrubberband.time_stretch(audio.astype(np.float32), sr, ratio)
            buf = io.BytesIO()
            sf.write(buf, stretched, sr, format="WAV")
            return buf.getvalue()

        return await loop.run_in_executor(None, _stretch)
    except Exception:
        log.exception("prestretch_failed", path=str(ref_path))
        return ref_bytes

_POLL_INTERVAL        = 5.0          # seconds between queue-fill attempts
_QUEUE_TARGET         = 2            # desired minimum clips in playback_queue
_RESCAN_INTERVAL      = 10.0         # seconds between references directory rescans
_CRISIS_CACHE_COOLDOWN = 1800.0      # minimum seconds between crisis cache rebuilds
_CLIPS_DIR        = Path("streams/audio")
_FALLBACK_DIR     = Path("assets/fallback")
_REFERENCES_DIR   = Path("streams/references")
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_ref_territory(conn: aiosqlite.Connection, path: Path) -> str:
    """Return the territory stored in the DB for *path*, or '' if not found."""
    async with conn.execute(
        "SELECT territory FROM audio_clips WHERE path = ?", (str(path),)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row and row[0] else ""


async def _analyze_clip_async(conn: aiosqlite.Connection, path: Path) -> None:
    """Run librosa analysis on a generated clip and persist the results to the DB.

    Computes BPM, musical key, MFCC fingerprint, duration, trim boundaries and
    energy RMS. Results are merged into the existing mood_snapshot JSON and the
    audio_key / duration_s columns are updated in-place. Fire-and-forget; any
    exception is caught and logged.
    """
    if not _HAS_LIBROSA:
        log.warning("librosa_not_available", path=str(path), effect="no BPM/key/MFCC analysis, A2A ref_bpm will be None")
        return

    try:
        loop = asyncio.get_running_loop()

        def _load_and_analyze() -> dict:  # type: ignore[return]
            y, sr = _librosa.load(str(path), sr=44100, mono=True)  # type: ignore[possibly-unbound]

            tempo, _ = _librosa.beat.beat_track(y=y, sr=sr)  # type: ignore[possibly-unbound]
            detected_bpm = float(_np.atleast_1d(tempo)[0])  # type: ignore[possibly-unbound]

            chroma = _librosa.feature.chroma_cqt(y=y, sr=sr)  # type: ignore[possibly-unbound]
            pcp_mean = chroma.mean(axis=1)
            key_idx = int(_np.argmax(pcp_mean))  # type: ignore[possibly-unbound]
            detected_key = _CIRCLE_OF_FIFTHS[key_idx % 12]

            mfcc = _librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)  # type: ignore[possibly-unbound]
            mfcc_fingerprint: list[float] = mfcc.mean(axis=1).tolist()

            duration_s = float(_librosa.get_duration(y=y, sr=sr))  # type: ignore[possibly-unbound]

            _, (trim_start_samp, trim_end_samp) = _librosa.effects.trim(y)  # type: ignore[possibly-unbound]
            trim_start_s = float(trim_start_samp) / sr
            trim_end_s = float(trim_end_samp) / sr

            rms = float(_np.sqrt(_np.mean(y ** 2)))  # type: ignore[possibly-unbound]
            energy_rms = min(rms / 0.5, 1.0)

            # fill_ratio: fraction of non-silent content (trim-based estimate).
            # Used by find_reference() to deprioritise thin/mostly-silent clips.
            total_samples = max(len(y), 1)
            fill_ratio = float((trim_end_samp - trim_start_samp) / total_samples)

            return {
                "detected_bpm": detected_bpm,
                "detected_key": detected_key,
                "mfcc_fingerprint": mfcc_fingerprint,
                "duration_s": duration_s,
                "trim_start_s": trim_start_s,
                "trim_end_s": trim_end_s,
                "energy_rms": energy_rms,
                "fill_ratio": fill_ratio,
            }

        results = await loop.run_in_executor(None, _load_and_analyze)

        detected_bpm = results["detected_bpm"]
        detected_key = results["detected_key"]
        mfcc_fingerprint = results["mfcc_fingerprint"]
        duration_s = results["duration_s"]
        trim_start_s = results["trim_start_s"]
        trim_end_s = results["trim_end_s"]
        energy_rms = results["energy_rms"]
        fill_ratio = results["fill_ratio"]

        async with conn.execute(
            "SELECT mood_snapshot FROM audio_clips WHERE path=?", (str(path),)
        ) as cur:
            row = await cur.fetchone()
        existing = orjson.loads(row[0] or "{}") if row else {}
        existing.update({
            "detected_bpm": detected_bpm,
            "mfcc_fingerprint": mfcc_fingerprint,
            "trim_start_s": trim_start_s,
            "trim_end_s": trim_end_s,
            "energy_rms": energy_rms,
            "fill_ratio": fill_ratio,
        })

        await conn.execute(
            "UPDATE audio_clips SET audio_key=?, duration_s=?, mood_snapshot=? WHERE path=?",
            (detected_key, duration_s, orjson.dumps(existing).decode(), str(path)),
        )
        await conn.commit()

        log.info(
            "clip_analyzed",
            path=str(path),
            bpm=detected_bpm,
            key=detected_key,
            duration_s=round(duration_s, 2),
        )

    except Exception:
        log.exception("clip_analyze_error", path=str(path))


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
        "-ar", "44100",
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


async def _generate_audio(prompt: str, state: GlobalState) -> bytes:
    """Generate audio bytes via Stable Audio 2.5 / fal.ai text-to-audio endpoint."""
    from builders.music_prompt import get_inference_steps

    import fal_client  # type: ignore[import-untyped]

    steps = get_inference_steps(state)
    result = await fal_client.run_async(
        "fal-ai/stable-audio-25/text-to-audio",
        arguments={
            "prompt": prompt,
            "total_seconds": 180,
            "num_inference_steps": steps,
        },
    )
    audio_url: str = result["audio"]["url"]

    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as resp:
            resp.raise_for_status()
            wav_bytes = await resp.read()
    return await _wav_to_mp3(wav_bytes)


async def _generate_from_reference(
    ref_path: Path,
    prompt: str,
    state: GlobalState,
    conn: aiosqlite.Connection,
) -> bytes:
    """Derive a new clip from *ref_path* using the fal.ai audio-to-audio endpoint."""
    import base64

    import fal_client  # type: ignore[import-untyped]

    with ref_path.open("rb") as fh:
        ref_bytes = fh.read()

    # ── R1: Pre-stretch reference to drift_bpm ────────────────────────────────
    async with conn.execute(
        "SELECT mood_snapshot FROM audio_clips WHERE path = ?", (str(ref_path),)
    ) as cur:
        snap_row = await cur.fetchone()
    ref_snap: dict = orjson.loads(snap_row[0] or "{}") if snap_row else {}
    ref_bpm: float | None = ref_snap.get("detected_bpm") or ref_snap.get("drift_bpm")
    ref_bytes = await _prestretch_reference(ref_path, ref_bytes, state.drift_bpm, ref_bpm)

    mime = "audio/wav" if ref_path.suffix.lower() == ".wav" else "audio/mpeg"
    data_uri = f"data:{mime};base64,{base64.b64encode(ref_bytes).decode()}"

    # ── R3: Strength data-driven with key distance ────────────────────────────
    async with conn.execute(
        "SELECT audio_key FROM audio_clips WHERE path = ?", (str(ref_path),)
    ) as cur:
        key_row = await cur.fetchone()
    ref_key: str = (key_row[0] or "") if key_row else ""
    key_dist = _key_distance(ref_key, state.drift_key)
    strength = _clamp(
        0.3 + state.drift_velocity * 0.3 + state.crisis_level * 0.2 + key_dist * 0.2,
        0.3, 0.9,
    )
    guidance_scale = _clamp(1.0 + state.source_divergence * 0.2, 1.0, 1.2)

    ref_duration = await _get_ref_duration(ref_path)
    total_seconds = min(ref_duration, 180) if ref_duration > 0 else 180

    from builders.music_prompt import get_inference_steps

    steps = get_inference_steps(state)
    result = await fal_client.run_async(
        "fal-ai/stable-audio-25/audio-to-audio",
        arguments={
            "prompt": prompt,
            "audio_url": data_uri,
            "strength": strength,
            "guidance_scale": guidance_scale,
            "num_inference_steps": steps,
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
    import orjson as _json

    async with conn.execute(
        """
        SELECT path, territory, mood_snapshot FROM audio_clips
        WHERE source = 'reference' AND play_count = 0
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
            # R4: deprioritise low fill_ratio clips (thin/mostly-silent content)
            fill_ratio = snap.get("fill_ratio", 1.0)  # default 1.0 = don't penalise if unknown
            if fill_ratio < 0.7:
                s -= 2.0
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
            audio_bytes = await _generate_audio(prompt, crisis_state)
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
        # Kick off in-process librosa analysis so BPM/MFCC are ready before first A2A call.
        asyncio.create_task(_analyze_clip_async(conn, path))
        new_count += 1

    if new_count:
        log.info("references_auto_indexed", count=new_count)
        _trigger_librosa_analysis()
    return new_count


def _trigger_librosa_analysis() -> None:
    """Launch scripts/index_references.py in the background for territory/BPM enrichment."""
    import subprocess

    script = Path(__file__).parent.parent / "scripts" / "index_references.py"
    if not script.exists():
        return
    subprocess.Popen(
        ["uv", "run", "--group", "scripts", "python", str(script)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _has_pending_reference(conn: aiosqlite.Connection) -> bool:
    """Return True when at least one reference file has never been used for A2A."""
    async with conn.execute(
        "SELECT 1 FROM audio_clips WHERE source = 'reference' AND play_count = 0 LIMIT 1"
    ) as cur:
        return await cur.fetchone() is not None


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
    cmd_engine: object | None = None,
) -> None:
    """Main audio queue coroutine.

    Continuously fills *playback_queue* with generated audio clips.
    Fills *playback_queue* with clips. When a viewer ``!request`` genre is
    pending, skips reuse and generates a fresh clip for that genre.
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
    ghosts_removed = await cleanup_ghost_paths(conn)

    log.info(
        "audio_queue_started",
        fallbacks=len(fallback_paths),
        refs_indexed=refs_indexed,
        ghosts_removed=ghosts_removed,
    )

    last_refs_scan = time.time()
    _prev_crisis: float = state.crisis_level
    _last_crisis_cache_at: float = 0.0

    # Pre-generate crisis clips only when crisis is already active at startup
    if state.crisis_level > 0.5:
        asyncio.create_task(_build_crisis_cache(conn, state, _build_prompt(state)))
        _last_crisis_cache_at = time.time()

    while True:
        # ── Drain CommandEngine — apply chat commands ──────────────────────────
        if cmd_engine is not None:
            for kind, value in cmd_engine.pop_all():  # type: ignore[union-attr]
                if kind == "replay":
                    p = Path(value)
                    _dn = ""
                    try:
                        async with conn.execute(
                            "SELECT display_name FROM audio_clips WHERE path=?", (str(p),)
                        ) as _rc:
                            _rr = await _rc.fetchone()
                        if _rr and _rr[0]:
                            _dn = _rr[0]
                    except Exception:
                        pass
                    try:
                        await playback_queue.put((p, _dn))  # type: ignore[union-attr]
                    except asyncio.QueueFull:
                        pass
                elif kind == "request":
                    state.requested_genre = value
                elif kind == "vibe":
                    pe_key = f"territory_{value}"
                    await state_queue.put({"prediction_errors": {pe_key: 2.0}})

        # ── Periodic rescan of streams/references/ for newly deposited files ──
        now = time.time()
        if now - last_refs_scan >= _RESCAN_INTERVAL:
            await _auto_index_references_on_startup(conn, state)
            last_refs_scan = now

        # ── Crisis delta — trigger cache rebuild on rapid escalation ──────────
        crisis_delta = state.crisis_level - _prev_crisis
        if crisis_delta > 0.15 and (now - _last_crisis_cache_at) >= _CRISIS_CACHE_COOLDOWN:
            log.info("crisis_escalation_detected", delta=crisis_delta, crisis_level=state.crisis_level)
            asyncio.create_task(_build_crisis_cache(conn, state, _build_prompt(state)))
            _last_crisis_cache_at = now
        _prev_crisis = state.crisis_level

        # ── Only fill queue when below target ─────────────────────────────────
        qsize = playback_queue.qsize() if playback_queue is not None else 0
        if qsize >= _QUEUE_TARGET:
            await state_queue.put({"queue_length": qsize})
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        # ── Reuse an existing clip if available ───────────────────────────────
        # Skip reuse only when a !request is pending. Pending references are
        # converted in the background via the normal generation path (find_reference)
        # and no longer block reuse of the existing library.
        _pending_ref = await _has_pending_reference(conn)
        result = None if state.requested_genre else await find_reusable(conn, state)
        if result is not None:
            candidate, display_name = result
            await mark_played(conn, candidate)
            log.info("audio_clip_queued", path=str(candidate), display_name=display_name, source="reused")
            if playback_queue is not None:
                await playback_queue.put((candidate, display_name))
            await state_queue.put({"queue_length": playback_queue.qsize() if playback_queue is not None else 1})
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        # ── Generate a new clip ───────────────────────────────────────────────
        prompt = _build_prompt(state)
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        # Skip stability guard during active crisis: queue low + crisis high → generate immediately
        in_crisis = state.crisis_level > 0.6 and qsize < _QUEUE_TARGET
        if prompt_hash == state.last_prompt_hash and qsize > 0 and not in_crisis and not _pending_ref:
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        ref_path = await find_reference(conn, state)
        ref_territory = await _get_ref_territory(conn, ref_path) if ref_path else ""

        # ── R5: Fall back to text-only when reference is too divergent ────────
        if ref_path is not None:
            async with conn.execute(
                "SELECT mood_snapshot FROM audio_clips WHERE path = ?", (str(ref_path),)
            ) as _cur:
                _snap_row = await _cur.fetchone()
            _ref_snap: dict = orjson.loads(_snap_row[0] or "{}") if _snap_row else {}
            _ref_mfcc = _ref_snap.get("mfcc_fingerprint")
            _mfcc_dist: float | None = None  # None = no data, skip MFCC gate
            if _ref_mfcc and state.mfcc_fingerprint:
                import numpy as _np_r5
                rv = _np_r5.array(_ref_mfcc, dtype=_np_r5.float32)
                sv = _np_r5.array(state.mfcc_fingerprint, dtype=_np_r5.float32)
                norm = float(_np_r5.linalg.norm(rv) * _np_r5.linalg.norm(sv))
                if norm > 0:
                    _mfcc_dist = 1.0 - float(_np_r5.dot(rv, sv) / norm)
            if state.source_divergence > 0.7 and _mfcc_dist is not None and _mfcc_dist > 0.6:
                log.info(
                    "a2a_skipped_divergence",
                    source_divergence=state.source_divergence,
                    mfcc_dist=round(_mfcc_dist, 3),
                )
                ref_path = None  # fall through to text-only generation

        try:
            name_task = asyncio.create_task(generate_track_name(state))

            if ref_path is not None:
                audio_bytes = await _generate_from_reference(ref_path, prompt, state, conn)
            else:
                audio_bytes = await _generate_audio(prompt, state)

            display_name = await name_task

            outpath = _CLIPS_DIR / f"clip_{int(time.time() * 1000)}.mp3"
            outpath.write_bytes(audio_bytes)

            # Rotate references: mark played only after successful generation
            if ref_path is not None and audio_bytes:
                await mark_played(conn, ref_path)

            await index_clip(
                conn,
                outpath,
                state,
                prompt,
                source="fal_derived" if ref_path else "generated",
                display_name=display_name,
                territory=ref_territory or state.drift_territory if ref_path else state.drift_territory,
            )
            # Mark the generated clip as played immediately after indexing so
            # find_reusable() cannot pick it up again on the next poll — the DB
            # initialises last_played_at=0.0 which always passes the 2-hour
            # cooldown, causing the same clip to be double-queued 5 s later.
            await mark_played(conn, outpath)
            asyncio.create_task(_analyze_clip_async(conn, outpath))

            if ref_path and ref_territory:
                log.info("fal_derived_territory_inherited", ref=str(ref_path), territory=ref_territory)

            # Consume requested_genre after generating for it
            state.requested_genre = ""

            await state_queue.put({"last_prompt_hash": prompt_hash})
            if playback_queue is not None:
                await playback_queue.put((outpath, display_name))
            await state_queue.put({"queue_length": playback_queue.qsize() if playback_queue is not None else 1})

            log.info(
                "audio_clip_generated",
                path=str(outpath),
                display_name=display_name,
                source="fal_derived" if ref_path else "generated",
            )

        except Exception:
            log.exception("audio_generation_error", prompt=prompt)
            # Generation failed (e.g. API credits exhausted). If queue is empty and
            # all clips are in cooldown, bypass cooldown so playback never stops.
            if playback_queue is not None and playback_queue.qsize() == 0:
                fallback = await find_reusable(conn, state, cooldown_s=0)
                if fallback is not None:
                    fb_path, fb_name = fallback
                    await mark_played(conn, fb_path)
                    await playback_queue.put((fb_path, fb_name))
                    log.warning("audio_fallback_no_cooldown", path=str(fb_path))

        await asyncio.sleep(_POLL_INTERVAL)
