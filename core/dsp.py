"""DSP Engine — Pedalboard + pyrubberband → FFmpeg stdin → RTMP."""
import asyncio
import os
import shutil
import subprocess
import time as _time
from pathlib import Path

import aiosqlite
import numpy as np
import orjson
import pyloudnorm as pyln
import pyrubberband
import structlog
from pedalboard import (  # type: ignore[attr-defined]
    Bitcrush,
    Chorus,
    Compressor,
    Delay,
    Gain,
    GSMFullRateCompressor,
    HighShelfFilter,
    LadderFilter,
    Limiter,
    LowShelfFilter,
    MP3Compressor,
    Phaser,
    Reverb,
)
from pedalboard._pedalboard import Pedalboard
from pedalboard.io import AudioFile

from core.state import GlobalState

log = structlog.get_logger()

_SR = 44100
_CROSSFADE_S = 3
_CROSSFADE_SAMPLES = _CROSSFADE_S * _SR
_FFMPEG_RESTART_MAX_S = 60
_TARGET_LUFS = -14.0
_MAX_GAIN_DB = 18.0
_CHUNK_SAMPLES = 4096  # ~93 ms at 44100 Hz — throttles pipe writes to real-time
_5S_CHUNKS = int(5 * _SR / _CHUNK_SAMPLES)  # ≈ 54 chunks — DSP chain rebuild interval


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _stretch_ratio(drift_bpm: float) -> float:
    return drift_bpm / 90.0


def _build_chain(
    state: GlobalState,
    progress: float = 0.0,
    burst_reverb: bool = False,
) -> Pedalboard:
    wt = state.world_temperature
    cr = state.crisis_level
    mt = state.musical_tension
    me = state.anxiety
    hc = state.harmonic_complexity

    # RT1 — Intra-clip DSP automation (NO FAKE: only active when excitement > 0.3 OR urgency > 0.4)
    active = state.excitement > 0.3 or state.urgency > 0.4

    # Build-up phase: progress 0→0.5 — LadderFilter opens progressively
    if active:
        if progress <= 0.5:
            auto_cutoff = 300.0 + (progress / 0.5) * 19700.0  # 300→20000 Hz
        else:
            auto_cutoff = 20000.0  # fully open after drop
    else:
        auto_cutoff = 0.0  # unused when inactive

    # Release phase: progress 0.8→1.0 — Reverb wet level decreases
    if active and progress >= 0.8:
        release_t = (progress - 0.8) / 0.2  # 0→1 over [0.8, 1.0]
        auto_reverb_factor = 1.0 - release_t
    else:
        auto_reverb_factor = 1.0

    # DSP+2 — LadderFilter: cutoff tracks drift_velocity.
    # BUG FIX: min cutoff raised to 4000 Hz (was 200 Hz → silenced entire audio at rest).
    # With drift_velocity=0, 200 Hz LPF cuts everything above 200 Hz = silent music.
    # 4000 Hz minimum preserves the "muffled at rest" artistic intent without silence.
    ladder_cutoff = _clamp(4000.0 + state.drift_velocity * 16000.0, 4000.0, 20000.0)
    # RT1 override: if automation is active, use progress-driven cutoff
    if active:
        ladder_cutoff = _clamp(auto_cutoff, 4000.0, 20000.0)
    ladder_resonance = _clamp(hc * 0.8, 0.0, 1.0)

    # Reverb wet level: state-driven, then scaled by release factor.
    # Ceiling lowered to 0.20 (was 0.35) — a2a clips already carry the reference
    # track's acoustic space; adding heavy wet on top created double-reverb mud.
    # dry_level=0.85 keeps the source clearly audible (was 0.7 — over-attenuated dry).
    wet = _clamp(cr * 0.25 + me * 0.1, 0.0, 0.20)
    wet = _clamp(wet * auto_reverb_factor, 0.0, 1.0)

    # RT2 — world_event_burst: push reverb noticeably higher for this rebuild window
    if burst_reverb:
        wet = 0.5
        room = 0.85
    else:
        # Room size cap lowered to 0.60 (was 1.0) — room_size=1.0 added a cathedral
        # reverb tail that persisted audibly for several seconds per chunk.
        room = _clamp(0.15 + wt * 0.3 + cr * 0.15, 0.0, 0.60)

    effects: list = [
        Reverb(
            room_size=room,
            wet_level=wet,
            dry_level=0.85,
        ),
        HighShelfFilter(
            cutoff_frequency_hz=8000.0,
            gain_db=_clamp(-cr * 18 - mt * 4, -40.0, 0.0),
        ),
        # Compressor + Gain removed from real-time chain — they change average level
        # and defeat LUFS normalization. Both are applied in _build_level_chain(),
        # which processes the full clip once at load time before a second LUFS pass.
        Chorus(depth=_clamp(hc * 0.8, 0.0, 1.0)),
        # DSP+2 — LadderFilter: resonant sweep driven by drift_velocity and harmonic_complexity
        LadderFilter(
            mode=LadderFilter.LPF12,
            cutoff_hz=ladder_cutoff,
            resonance=ladder_resonance,
            drive=1.0,
        ),
    ]

    # DSP+3 — Delay: territory-conditional (psych/experimental only — NO FAKE)
    # Feedback cap lowered 0.6→0.35, mix cap 0.4→0.25 — at source_divergence=1.0 the
    # previous values produced an audible 3-echo trail that sat on top of a2a reverb.
    if state.drift_territory in ("psych", "experimental"):
        delay_feedback = _clamp(state.source_divergence * 0.25, 0.0, 0.35)
        delay_mix = _clamp(state.source_divergence * 0.15, 0.0, 0.25)
        effects.append(Delay(delay_seconds=0.375, feedback=delay_feedback, mix=delay_mix))

        # DSP+4 — Phaser: territory-conditional (psych/experimental only — NO FAKE)
        # Rate and depth driven by drift_velocity and harmonic_complexity respectively
        # mix lowered 0.5→0.30 — at 0.5 the phaser dominated the mix noticeably.
        phaser_depth = _clamp(hc * 0.8, 0.0, 1.0)
        phaser_rate = _clamp(0.5 + state.drift_velocity * 2.0, 0.1, 3.0)
        effects.append(Phaser(rate_hz=phaser_rate, depth=phaser_depth, mix=0.30))

    # DSP+1 — Crisis hierarchy tier 3: telephony artefacts (cr > 0.71, proportional)
    # gsm_mix is 0 at cr=0.7, 1 at cr=0.9 — only included when contribution is non-zero
    if cr > 0.71:
        effects.append(GSMFullRateCompressor())

    # DSP+1 — Crisis hierarchy tier 4: system falling apart (cr > 0.91)
    # bitcrush_depth degrades from 8 bits down to 2 bits as crisis peaks
    if cr > 0.91:
        mp3_mix = _clamp((cr - 0.9) / 0.1, 0.0, 1.0)
        bitcrush_depth = int(_clamp(8.0 - mp3_mix * 6.0, 2.0, 8.0))
        effects.extend([
            MP3Compressor(vbr_quality=9.0),
            Bitcrush(bit_depth=bitcrush_depth),
        ])

    effects.append(Limiter(threshold_db=-1.0))
    return Pedalboard(effects)


def _build_level_chain(state: GlobalState) -> Pedalboard:
    """Level-management chain — applied once to the full clip at load time.

    Compressor + Gain are isolated here so they never distort the LUFS-normalised
    baseline mid-playback.  After this chain runs, _normalize_lufs() re-targets
    -14 LUFS, guaranteeing a consistent output level regardless of state.
    """
    mt = state.musical_tension
    ur = state.excitement
    ae = state.audience_energy
    em = state.curiosity
    threshold_db = _clamp(-18 - mt * 12 - ur * 6, -60.0, 0.0)
    return Pedalboard([
        Compressor(threshold_db=threshold_db, ratio=4.0),
        Gain(gain_db=_clamp(ae * 3 + em * 2, -12.0, 12.0)),
    ])


def _crossfade_arrays(a: np.ndarray, b: np.ndarray, sr: int) -> np.ndarray:
    n = len(a)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, np.newaxis]
    return a * (1.0 - t) + b * t


def _apply_transition_eq(
    outgoing_tail: np.ndarray,
    incoming_head: np.ndarray,
    state: GlobalState,
    sr: int,
) -> tuple[np.ndarray, np.ndarray]:
    """T1 — EQ crossfade 3-band: cut bass from outgoing, cut bass from incoming head.

    Basses never double at transition — outgoing low-end fades before incoming
    low-end is restored by the normal DSP chain.
    """
    out_board = Pedalboard([LowShelfFilter(cutoff_frequency_hz=200.0, gain_db=-12.0)])
    in_board = Pedalboard([LowShelfFilter(cutoff_frequency_hz=200.0, gain_db=-12.0)])
    processed_out = out_board(outgoing_tail.T, sr).T.astype(np.float32)
    processed_in = in_board(incoming_head.T, sr).T.astype(np.float32)
    return processed_out, processed_in


def _apply_filter_sweep(
    audio: np.ndarray,
    state: GlobalState,
    sr: int,
    direction: str = "close",
) -> np.ndarray:
    """T2 — LadderFilter sweep driven by drift_velocity.

    direction="close": outgoing tail sweeps 20kHz → cutoff (filter closes).
    direction="open":  incoming head sweeps cutoff → 20kHz (filter opens).
    sweep_speed is proportional to drift_velocity so faster drift = more dramatic sweep.
    """
    n = len(audio)
    if n == 0:
        return audio
    sweep_speed = _clamp(0.3 + state.drift_velocity * 0.7, 0.3, 1.0)
    if direction == "close":
        start_hz = 20000.0
        end_hz = max(200.0, 20000.0 * (1.0 - sweep_speed))
    else:
        start_hz = max(200.0, 20000.0 * (1.0 - sweep_speed))
        end_hz = 20000.0
    chunk = max(1, n // 10)
    out = np.empty_like(audio)
    for i in range(10):
        t = i / 9.0
        cutoff = start_hz + (end_hz - start_hz) * t
        board = Pedalboard([LadderFilter(cutoff_hz=cutoff, resonance=0.3)])
        s = i * chunk
        e = s + chunk if i < 9 else n
        if s >= n:
            break
        seg = audio[s:e]
        out[s:e] = board(seg.T, sr, reset=False).T.astype(np.float32)
    return out


def _apply_reverb_throw(
    audio: np.ndarray,
    sr: int,
) -> np.ndarray:
    """T3 — Reverb throw on last beat of outgoing clip.

    Applies wet=1.0 reverb to the last half of the window (last ~0.5 s of a 1 s window),
    creating a hard DJ-style throw effect at the transition point.
    """
    n = len(audio)
    if n == 0:
        return audio
    half = n // 2
    board = Pedalboard([Reverb(room_size=0.85, wet_level=0.5, dry_level=0.5)])
    result = audio.copy()
    if half > 0:
        result[half:] = board(audio[half:].T, sr).T.astype(np.float32)
    return result


def _read_and_stretch(
    path: Path,
    drift_bpm: float,
    trim_start_s: float = 0.0,
    trim_end_s: float = 0.0,
) -> np.ndarray:
    with AudioFile(str(path)).resampled_to(_SR) as f:
        audio = f.read(f.frames)
    audio = audio.T.astype(np.float32)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    n = len(audio)
    if trim_start_s > 0.0 or (0.0 < trim_end_s < n / _SR):
        start = max(0, int(trim_start_s * _SR))
        end = int(trim_end_s * _SR) if trim_end_s > 0.0 else n
        end = min(max(end, start + _SR), n)  # keep at least 1 s
        audio = audio[start:end, :]
    ratio = _stretch_ratio(drift_bpm)
    if abs(ratio - 1.0) > 0.01:
        return pyrubberband.time_stretch(audio, _SR, ratio).astype(np.float32)
    return audio


def _process_audio(audio: np.ndarray, chain: Pedalboard) -> np.ndarray:
    return chain(audio.T, _SR).T


def _normalize_lufs(audio: np.ndarray, sr: int) -> np.ndarray:
    meter = pyln.Meter(sr)
    lufs = meter.integrated_loudness(audio.astype(np.float64))
    if lufs == float("-inf") or lufs < -70.0:
        return audio
    gain_db = _clamp(_TARGET_LUFS - lufs, -_MAX_GAIN_DB, _MAX_GAIN_DB)
    return (audio * 10.0 ** (gain_db / 20.0)).astype(np.float32)


async def _maybe_emit_audio_feedback(
    conn: aiosqlite.Connection,
    clip_path: Path,
    state: GlobalState,
    state_queue: asyncio.Queue,
) -> None:
    """Read librosa analysis from DB and emit audio feedback signals to self_model."""
    try:
        async with conn.execute(
            "SELECT audio_key, duration_s, mood_snapshot FROM audio_clips WHERE path=?",
            (str(clip_path),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return
        audio_key, duration_s, mood_snapshot_raw = row
        snap = orjson.loads(mood_snapshot_raw or "{}") if mood_snapshot_raw else {}
        detected_bpm = snap.get("drift_bpm") or snap.get("audio_bpm")
        energy_rms = snap.get("energy_rms")

        payload: dict[str, float] = {}

        if detected_bpm is not None:
            payload["audio_bpm_delta"] = min(abs(float(detected_bpm) - state.drift_bpm) / 80.0, 1.0)

        if audio_key:
            payload["audio_key_match"] = 1.0 if audio_key.split()[0] == state.drift_key.split()[0] else 0.0

        if energy_rms is not None:
            payload["audio_energy_level"] = float(min(energy_rms, 1.0))

        if payload:
            await state_queue.put(payload)
            log.info("audio_feedback_emitted", **payload)
    except Exception:
        log.exception("audio_feedback_error", path=str(clip_path))


async def run_dsp(
    state: GlobalState,
    playback_queue: asyncio.Queue,
    state_queue: asyncio.Queue,
    conn: aiosqlite.Connection | None = None,
    browser_ready: asyncio.Event | None = None,
) -> None:
    rtmp_url = os.environ.get("RTMP_URL", "")
    if not rtmp_url:
        base = os.environ.get("YOUTUBE_RTMP_URL", "").rstrip("/")
        key = os.environ.get("YOUTUBE_STREAM_KEY", "")
        if base and key:
            rtmp_url = f"{base}/{key}"
    if not rtmp_url:
        log.warning("dsp_disabled", reason="RTMP_URL not set")
        return

    display = os.environ.get("OVERLAY_DISPLAY", ":99")
    # USE_OVERLAY=0 disables x11grab (fallback to static black background).
    # Audio was silent due to PitchShift(reset=False) bug (now fixed), not x11grab.
    use_x11grab = (
        os.environ.get("USE_OVERLAY", "1") != "0"
        and shutil.which("Xvfb") is not None
        and browser_ready is not None
    )

    if browser_ready is not None:
        await browser_ready.wait()
        log.info("dsp_browser_ready")

    if use_x11grab:
        video_input = [
            "-thread_queue_size", "64",
            "-f", "x11grab",
            "-framerate", "10",
            "-video_size", "1280x720",
            "-draw_mouse", "0",
            "-i", f"{display}.0",
        ]
    else:
        video_input = [
            "-re",                           # read lavfi at native rate (10fps real-time)
            "-f", "lavfi",
            "-i", "color=c=0x0a0a1a:s=1280x720:r=10",  # static bg at 10fps
        ]

    video_encode = [
        "-c:v", "libx264", "-preset", "ultrafast",  # ultrafast — libère CPU pour x11grab + Python
        # nal-hrd=cbr forces filler NAL units so libx264 actually hits 2500k on static content
        # (without it, skip-heavy frames produce ~200-500 Kbps despite minrate=2500k)
        "-b:v", "2500k", "-minrate", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-vf", "fps=10",
        "-x264opts", "nal-hrd=cbr:force-cfr=1:threads=2",
        "-g", "20",                        # keyframe every 2s at 10fps (YouTube ≤4s)
        "-pix_fmt", "yuv420p",
    ]
    if not use_x11grab:
        video_encode += ["-tune", "stillimage"]

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        *video_input,
        # thread_queue_size -1 = unlimited: s16le demuxer never blocks even when the
        # mux temporarily pauses audio consumption. PCM timestamps from sample count
        # remain accurate regardless of queue depth, so A/V sync is preserved by the mux.
        # Memory: 44100 pkt/s × 4B × max_delay. With PCM thread at 94% and mux at 90%,
        # excess = 1588 pkt/s × 4B = 6.3KB/s max accumulation rate.
        # thread_queue_size 10M: never blocks even with PCM slightly faster than mux.
        # Memory: 10M × 4B = 40MB. A/V sync preserved by mux via PCM timestamps.
        "-thread_queue_size", "10000000",
        "-f", "s16le", "-ar", str(_SR), "-ac", "2", "-i", "pipe:0",
        *video_encode,
        "-c:a", "aac", "-b:a", "160k",
        "-map", "0:v", "-map", "1:a",
        # output options: max_muxing_queue_size must come before the output URL
        "-max_muxing_queue_size", "1024",
        "-f", "flv", "-flvflags", "no_duration_filesize",
        rtmp_url,
    ]
    loop = asyncio.get_running_loop()
    restart_delay = 2.0
    _pending_tail: np.ndarray | None = None   # unwritten tail — blended into next clip's head
    _prefetched_raw: np.ndarray | None = None  # next clip pre-processed during current playback
    _prefetched_path: Path | None = None
    _prefetched_display_name: str = ""

    def _start_ffmpeg() -> subprocess.Popen[bytes]:
        import fcntl
        import pathlib as _pl
        _log = _pl.Path("/tmp/ffmpeg_live.log")
        p = subprocess.Popen(
            ffmpeg_cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=_log.open("ab"),
        )
        if p.stdin is not None:
            fd = p.stdin.fileno()
            # Set pipe = one frame (4096 × 4 = 16,384 bytes ≈ 92ms of audio).
            # With pipe == frame: every write after the first blocks in C for ~92ms
            # while FFmpeg drains it — the blocking os.write() IS the real-time throttle.
            # GIL is released during the kernel block, so asyncio runs freely.
            # No time.sleep() needed → no GIL wake-up latency → continuous audio output.
            _frame_bytes = _CHUNK_SAMPLES * 4  # 16,384 bytes per frame
            try:
                fcntl.fcntl(fd, 1031, _frame_bytes)  # F_SETPIPE_SZ
            except OSError:
                pass
            # Keep pipe in BLOCKING mode — the PCM write thread uses blocking writes
        return p

    async def _pipe_write_async(p: subprocess.Popen[bytes], data: bytes) -> None:
        """Async write to FFmpeg stdin via executor (non-blocking for event loop)."""
        if p.stdin is None:
            return
        try:
            await loop.run_in_executor(None, p.stdin.write, data)
        except OSError:
            raise BrokenPipeError

    proc: subprocess.Popen[bytes] = await loop.run_in_executor(None, _start_ffmpeg)
    log.info("dsp_ffmpeg_started")

    # No pre-fill: pipe = one frame, self-regulating. First write is instant (empty pipe),
    # all subsequent writes block ~92ms until FFmpeg drains the previous frame.


    try:
        while True:
            if proc.poll() is not None:
                log.warning("dsp_ffmpeg_died", restart_delay_s=restart_delay)
                await asyncio.sleep(restart_delay)
                restart_delay = min(restart_delay * 2, _FFMPEG_RESTART_MAX_S)
                proc = await loop.run_in_executor(None, _start_ffmpeg)
            else:
                restart_delay = 2.0

            # Use prefetched clip if ready — zero silence at transition.
            # Otherwise fall back to normal get + process (with silence during processing).
            pipe_ok = True
            if _prefetched_raw is not None:
                clip_path = _prefetched_path  # type: ignore[assignment]
                clip_display_name = _prefetched_display_name
                raw = _prefetched_raw
                _prefetched_raw = None
                _prefetched_path = None
                _prefetched_display_name = ""
            else:
                try:
                    clip_path, clip_display_name = playback_queue.get_nowait()
                except asyncio.QueueEmpty:
                    # No clip ready — write one silence chunk at real-time rate.
                    _t0 = _time.monotonic()
                    if proc.poll() is None:
                        try:
                            await _pipe_write_async(proc, bytes(_CHUNK_SAMPLES * 4))
                        except BrokenPipeError:
                            log.warning("dsp_ffmpeg_pipe_broken")
                            proc = await loop.run_in_executor(None, _start_ffmpeg)
                    _elapsed = _time.monotonic() - _t0
                    await asyncio.sleep(max(0.0, _CHUNK_SAMPLES / _SR - _elapsed))
                    continue

                assert isinstance(clip_path, Path)

                _trim_start_s = 0.0
                _trim_end_s = 0.0
                if conn is not None:
                    try:
                        async with conn.execute(
                            "SELECT mood_snapshot FROM audio_clips WHERE path=?",
                            (str(clip_path),),
                        ) as _cur:
                            _row = await _cur.fetchone()
                        if _row and _row[0]:
                            _snap = orjson.loads(_row[0])
                            _trim_start_s = float(_snap.get("trim_start_s", 0.0))
                            _trim_end_s = float(_snap.get("trim_end_s", 0.0))
                    except Exception:
                        pass

                async def _process_clip(
                    _cp: Path = clip_path,
                    _ts: float = _trim_start_s,
                    _te: float = _trim_end_s,
                ) -> np.ndarray:
                    try:
                        a = await loop.run_in_executor(
                            None, _read_and_stretch, _cp, state.drift_bpm, _ts, _te
                        )
                        a = await loop.run_in_executor(None, _normalize_lufs, a, _SR)
                        # Level pre-bake: apply Compressor+Gain to full clip, then
                        # re-normalise so output LUFS is consistent regardless of state.
                        def _level_bake(_audio: np.ndarray) -> np.ndarray:
                            board = _build_level_chain(state)
                            processed = board(_audio.T, _SR).T.astype(np.float32)
                            return _normalize_lufs(processed, _SR)
                        return await loop.run_in_executor(None, _level_bake, a)
                    except Exception:
                        log.exception("dsp_read_error", path=str(_cp))
                        return np.array([], dtype=np.float32)

                process_task = asyncio.create_task(_process_clip())

                # While next clip loads, flush the pending tail through DSP instead of
                # writing silence. The tail (last 3 s of the previous clip) was held back
                # for crossfade, but in this fallback path the prefetch wasn't ready —
                # playing it now prevents an audible gap during the loading delay.
                _tail_flush_pcm = b""
                if _pending_tail is not None:
                    try:
                        _tf_board = _build_chain(state)
                        _tf_out = _tf_board(_pending_tail.T, _SR, reset=False).T
                        _tail_flush_pcm = (_tf_out * 32767).astype(np.int16).tobytes()
                    except Exception:
                        pass
                    _pending_tail = None  # consumed — no crossfade with incoming head
                _tail_flush_pos = 0

                while not process_task.done():
                    _t0 = _time.monotonic()
                    if proc.poll() is None:
                        try:
                            _tf_end = min(_tail_flush_pos + _CHUNK_SAMPLES * 4, len(_tail_flush_pcm))
                            _tf_chunk = _tail_flush_pcm[_tail_flush_pos:_tf_end]
                            _tail_flush_pos = _tf_end
                            chunk_out = _tf_chunk + bytes(_CHUNK_SAMPLES * 4 - len(_tf_chunk))
                            await _pipe_write_async(proc, chunk_out)
                        except BrokenPipeError:
                            log.warning("dsp_ffmpeg_pipe_broken")
                            proc = await loop.run_in_executor(None, _start_ffmpeg)
                            pipe_ok = False
                    _elapsed = _time.monotonic() - _t0
                    await asyncio.sleep(max(0.0, _CHUNK_SAMPLES / _SR - _elapsed))

                raw = await process_task
                if not pipe_ok or len(raw) == 0:
                    playback_queue.task_done()
                    continue

            # Write track name + reset progress bar now — playback is actually starting.
            if clip_display_name:
                await state_queue.put({"current_track_name": clip_display_name})
            await state_queue.put({"current_song_progress": 0.0})

            # Blend pending tail from previous clip (never written) with head of this clip.
            if _pending_tail is not None:
                blend_len = min(len(_pending_tail), len(raw))
                tail = _pending_tail[:blend_len].copy()
                head = raw[:blend_len].copy()

                # T1: EQ crossfade — cut bass on both sides (basses never double)
                tail, head = _apply_transition_eq(tail, head, state, _SR)

                # T2: filter sweep — outgoing closes, incoming opens (speed = drift_velocity)
                tail = _apply_filter_sweep(tail, state, _SR, direction="close")
                head = _apply_filter_sweep(head, state, _SR, direction="open")

                # T3: reverb throw on last ~1 s of outgoing tail
                last_s = min(_SR, len(tail))
                if last_s > 0:
                    tail[-last_s:] = _apply_reverb_throw(tail[-last_s:], _SR)

                xfade = _crossfade_arrays(tail, head, _SR)
                raw = np.concatenate([xfade, raw[blend_len:]])
                _pending_tail = None

            # Hold back the last tail — it will be blended into the next clip's head.
            tail_reserve = min(_CROSSFADE_SAMPLES, len(raw))
            _pending_tail = raw[-tail_reserve:].copy()
            raw_to_write = raw[:-tail_reserve] if tail_reserve < len(raw) else raw

            total_frames = len(raw_to_write)
            bytes_written = 0
            total_bytes = total_frames * 4  # stereo int16 = 4 bytes/sample frame

            # Run PCM write loop in a dedicated thread so time.sleep is used for
            # precise real-time pacing. asyncio.sleep has ~40ms event-loop scheduling
            # overhead per chunk under load, which causes audio to run at only 69% real-time.
            _pipe_broken = False

            def _pcm_write_thread() -> None:
                nonlocal bytes_written, _pipe_broken
                chunk_idx = 0
                _chunk_duration = _CHUNK_SAMPLES / _SR
                board = _build_chain(state, progress=0.0)
                fd = proc.stdin.fileno() if proc.stdin is not None else -1
                if fd < 0:
                    return
                # Explicit real-time throttle: sleep after each write to stay on schedule.
                # os.write blocking alone is insufficient — FFmpeg drains the pipe faster
                # than real-time when RTMP backpressure is low, causing the thread to
                # finish in seconds instead of clip_duration seconds.
                _t_start = _time.monotonic()
                for frame_start in range(0, total_frames, _CHUNK_SAMPLES):
                    chunk_frames = raw_to_write[frame_start : frame_start + _CHUNK_SAMPLES]
                    if chunk_idx > 0 and chunk_idx % _5S_CHUNKS == 0:
                        prog = min(bytes_written / total_bytes, 1.0) if total_bytes > 0 else 0.0
                        new_board = _build_chain(state, progress=prog, burst_reverb=bool(state.world_event_burst))
                        # Crossfade old→new over this chunk to avoid audible click at rebuild boundary
                        old_out = board(chunk_frames.T, _SR, reset=False).T.astype(np.float32)
                        new_out = new_board(chunk_frames.T, _SR, reset=False).T.astype(np.float32)
                        t = np.linspace(0.0, 1.0, len(old_out), dtype=np.float32)[:, np.newaxis]
                        dsp_chunk = old_out * (1.0 - t) + new_out * t
                        board = new_board
                    else:
                        dsp_chunk = board(chunk_frames.T, _SR, reset=False).T
                    pcm_chunk = (dsp_chunk * 32767).astype(np.int16).tobytes()
                    try:
                        os.write(fd, pcm_chunk)
                    except OSError:
                        _pipe_broken = True
                        return
                    bytes_written += len(pcm_chunk)
                    if chunk_idx % 50 == 0 and total_bytes > 0:
                        loop.call_soon_threadsafe(
                            state_queue.put_nowait,
                            {"current_song_progress": min(bytes_written / total_bytes, 1.0)},
                        )
                    chunk_idx += 1
                    # Sleep until the expected wall-clock time for this chunk — keeps
                    # audio arriving at real-time rate regardless of pipe drain speed.
                    _expected = _t_start + chunk_idx * _chunk_duration
                    _slack = _expected - _time.monotonic()
                    if _slack > 0.001:
                        _time.sleep(_slack)

            # Prefetch next clip during the ~47s PCM write — so it's ready at transition.
            # get_nowait() takes it off the queue now; task_done() fires at end of next iteration.
            _prefetch_task: asyncio.Task[np.ndarray] | None = None
            _next_clip_path: Path | None = None
            _next_display_name: str = ""
            try:
                _next_clip_path, _next_display_name = playback_queue.get_nowait()
                assert _next_clip_path is not None

                _p_trim_start = 0.0
                _p_trim_end = 0.0
                if conn is not None:
                    try:
                        async with conn.execute(
                            "SELECT mood_snapshot FROM audio_clips WHERE path=?",
                            (str(_next_clip_path),),
                        ) as _cur2:
                            _row2 = await _cur2.fetchone()
                        if _row2 and _row2[0]:
                            _snap2 = orjson.loads(_row2[0])
                            _p_trim_start = float(_snap2.get("trim_start_s", 0.0))
                            _p_trim_end = float(_snap2.get("trim_end_s", 0.0))
                    except Exception:
                        pass

                async def _prefetch_next(
                    _p: Path = _next_clip_path,
                    _ts: float = _p_trim_start,
                    _te: float = _p_trim_end,
                ) -> np.ndarray:
                    try:
                        a = await loop.run_in_executor(None, _read_and_stretch, _p, state.drift_bpm, _ts, _te)
                        a = await loop.run_in_executor(None, _normalize_lufs, a, _SR)
                        def _level_bake_pre(_audio: np.ndarray) -> np.ndarray:
                            board = _build_level_chain(state)
                            processed = board(_audio.T, _SR).T.astype(np.float32)
                            return _normalize_lufs(processed, _SR)
                        return await loop.run_in_executor(None, _level_bake_pre, a)
                    except Exception:
                        log.exception("dsp_prefetch_error", path=str(_p))
                        return np.array([], dtype=np.float32)

                _prefetch_task = asyncio.create_task(_prefetch_next())
                log.debug("dsp_prefetch_started", path=str(_next_clip_path))
            except asyncio.QueueEmpty:
                pass

            await loop.run_in_executor(None, _pcm_write_thread)

            # Collect prefetch result — should be instant (processed during 47s write)
            if _prefetch_task is not None:
                _result = await _prefetch_task
                if len(_result) > 0:
                    _prefetched_raw = _result
                    _prefetched_path = _next_clip_path
                    _prefetched_display_name = _next_display_name
                else:
                    # Prefetch failed — mark consumed, will fall back to normal path
                    playback_queue.task_done()

            if _pipe_broken:
                log.warning("dsp_ffmpeg_pipe_broken")
                proc = await loop.run_in_executor(None, _start_ffmpeg)

            await state_queue.put({
                "current_track_name": "",   # hide HUD between clips — silence is not "100%"
                "current_song_progress": 0.0,
                "stream_bitrate": 192.0,
                "dropped_frames": 0.0,
                "songs_played_today": state.songs_played_today + 1,
                "songs_played_total": state.songs_played_total + 1,
            })
            playback_queue.task_done()
            if conn is not None:
                assert isinstance(clip_path, Path)
                await _maybe_emit_audio_feedback(conn, clip_path, state, state_queue)
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
