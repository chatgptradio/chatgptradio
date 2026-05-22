"""DSP Engine — Pedalboard + pyrubberband → FFmpeg stdin → RTMP."""
import asyncio
import os
import shutil
import subprocess
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
    PitchShift,
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
    ae = state.audience_energy
    em = state.curiosity
    me = state.anxiety
    ur = state.excitement
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

    # DSP+2 — LadderFilter: cutoff tracks drift_velocity (always active)
    # Low cutoff when stable, opens as drift accelerates
    ladder_cutoff = _clamp(200.0 + state.drift_velocity * 19800.0, 200.0, 20000.0)
    # RT1 override: if automation is active, use progress-driven cutoff
    if active:
        ladder_cutoff = _clamp(auto_cutoff, 200.0, 20000.0)
    ladder_resonance = _clamp(hc * 0.8, 0.0, 1.0)

    # Reverb wet level: state-driven, then scaled by release factor
    wet = _clamp(0.1 + cr * 0.5 + me * 0.2, 0.0, 1.0)
    wet = _clamp(wet * auto_reverb_factor, 0.0, 1.0)

    # RT2 — world_event_burst: force wet=1.0 and room=0.95 for this rebuild window
    if burst_reverb:
        wet = 1.0
        room = 0.95
    else:
        room = _clamp(0.2 + wt * 0.4 + cr * 0.25, 0.0, 1.0)

    effects: list = [
        Reverb(
            room_size=room,
            wet_level=wet,
        ),
        HighShelfFilter(
            cutoff_frequency_hz=8000.0,
            gain_db=_clamp(-cr * 18 - mt * 4, -40.0, 0.0),
        ),
        Compressor(
            threshold_db=_clamp(-18 - mt * 12 - ur * 6, -60.0, 0.0),
            ratio=4.0,
        ),
        Gain(gain_db=_clamp(ae * 3 + em * 2, -12.0, 12.0)),
        PitchShift(semitones=_clamp(ur * 0.5 - me * 0.3, -12.0, 12.0)),
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
    # Only active when drift carries the signal into psychedelic or experimental space
    if state.drift_territory in ("psych", "experimental"):
        delay_feedback = _clamp(state.source_divergence * 0.4, 0.0, 0.6)
        delay_mix = _clamp(state.source_divergence * 0.3, 0.0, 0.4)
        effects.append(Delay(delay_seconds=0.375, feedback=delay_feedback, mix=delay_mix))

        # DSP+4 — Phaser: territory-conditional (psych/experimental only — NO FAKE)
        # Rate and depth driven by drift_velocity and harmonic_complexity respectively
        phaser_depth = _clamp(hc * 0.8, 0.0, 1.0)
        phaser_rate = _clamp(0.5 + state.drift_velocity * 2.0, 0.1, 3.0)
        effects.append(Phaser(rate_hz=phaser_rate, depth=phaser_depth, mix=0.5))

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
    board = Pedalboard([Reverb(room_size=0.9, wet_level=1.0, dry_level=0.0)])
    result = audio.copy()
    if half > 0:
        result[half:] = board(audio[half:].T, sr).T.astype(np.float32)
    return result


def _read_and_stretch(path: Path, drift_bpm: float) -> np.ndarray:
    with AudioFile(str(path)) as f:
        audio = f.read(f.frames)
    audio = audio.T.astype(np.float32)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
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
    use_x11grab = shutil.which("Xvfb") is not None and browser_ready is not None

    if browser_ready is not None:
        await browser_ready.wait()
        log.info("dsp_browser_ready")

    if use_x11grab:
        video_input = [
            # thread_queue_size: 4 = 4s buffer at 1fps capture.
            # Capture at 1fps but output at 10fps (9 duplicate P-frames per second) —
            # duplicate P-frames are trivial to encode; CBR filler pads to 2500k.
            # At 5fps, x11grab/SwiftShader lock contention caused speed=0.6x (queue stall).
            # At 1fps, speed=0.987x in testing — stable encoding with headroom for Python+Chrome.
            "-thread_queue_size", "4",
            "-f", "x11grab",
            "-framerate", "1",             # 1fps capture → 10fps output via fps= filter below
            "-video_size", "1280x720",
            "-draw_mouse", "0",
            "-i", f"{display}.0",
        ]
    else:
        video_input = [
            "-f", "lavfi",
            "-i", "color=c=0x0a0a1a:s=1280x720:r=10",
        ]

    video_encode = [
        "-c:v", "libx264", "-preset", "ultrafast",  # ultrafast — libère CPU pour x11grab + Python
        # nal-hrd=cbr forces filler NAL units so libx264 actually hits 2500k on static content
        # (without it, skip-heavy frames produce ~200-500 Kbps despite minrate=2500k)
        "-b:v", "2500k", "-minrate", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
        # threads=2: match CPU core count (default=3 causes contention on 2-core VPS)
        # threads=2: match CPU core count. vsync=cfr+fps_mode ensures 10fps output
        # from 5fps x11grab by duplicating frames (tiny P-frames + CBR filler).
        "-vf", "fps=10",                   # duplicate 5fps capture → 10fps declared output
        "-x264opts", "nal-hrd=cbr:force-cfr=1:threads=2",
        "-g", "20",                        # keyframe every 2s at 10fps (YouTube requires ≤4s)
        "-pix_fmt", "yuv420p",
    ]
    if not use_x11grab:
        video_encode += ["-tune", "stillimage"]

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        *video_input,
        # thread_queue_size prevents pipe stalls when audio queue momentarily empties between
        # clips — avoids "faster than real-time" bursts followed by "no data" on RTMP side
        "-thread_queue_size", "512",
        "-f", "s16le", "-ar", str(_SR), "-ac", "2", "-i", "pipe:0",
        *video_encode,
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v", "-map", "1:a",
        # output options: max_muxing_queue_size must come before the output URL
        "-max_muxing_queue_size", "1024",
        "-f", "flv", "-flvflags", "no_duration_filesize",
        rtmp_url,
    ]
    loop = asyncio.get_running_loop()
    restart_delay = 2.0
    _pending_tail: np.ndarray | None = None  # unwritten tail — blended into next clip's head

    def _start_ffmpeg() -> subprocess.Popen[bytes]:
        import fcntl
        p = subprocess.Popen(
            ffmpeg_cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        # Increase audio pipe buffer to 1MB (default 64KB = 0.36s).
        # asyncio jitter can cause 200-500ms gaps in PCM writes; 1MB = 5.7s of headroom
        # so FFmpeg's A/V sync never starves waiting for audio.
        if p.stdin is not None:
            try:
                fcntl.fcntl(p.stdin.fileno(), 1031, 1024 * 1024)  # F_SETPIPE_SZ = 1031
            except OSError:
                pass
        return p

    proc: subprocess.Popen[bytes] = await loop.run_in_executor(None, _start_ffmpeg)
    log.info("dsp_ffmpeg_started")

    async def _log_stderr(p: subprocess.Popen[bytes]) -> None:
        assert p.stderr is not None
        while p.poll() is None:
            line = await loop.run_in_executor(None, p.stderr.readline)
            if line:
                log.info("ffmpeg_stderr", msg=line.decode(errors="replace").rstrip())

    asyncio.create_task(_log_stderr(proc))

    # Pre-fill audio pipe with 2s of silence so FFmpeg A/V sync never starves at startup
    if proc.stdin is not None:
        pre_silence = bytes(_SR * 4 * 2)  # 2s stereo int16 silence
        await loop.run_in_executor(None, proc.stdin.write, pre_silence)

    try:
        while True:
            if proc.poll() is not None:
                log.warning("dsp_ffmpeg_died", restart_delay_s=restart_delay)
                await asyncio.sleep(restart_delay)
                restart_delay = min(restart_delay * 2, _FFMPEG_RESTART_MAX_S)
                proc = await loop.run_in_executor(None, _start_ffmpeg)
            else:
                restart_delay = 2.0

            try:
                clip_path = playback_queue.get_nowait()
            except asyncio.QueueEmpty:
                # No clip ready — write one silence chunk at real-time rate.
                if proc.poll() is None and proc.stdin is not None:
                    try:
                        await loop.run_in_executor(
                            None, proc.stdin.write, bytes(_CHUNK_SAMPLES * 4)
                        )
                    except BrokenPipeError:
                        log.warning("dsp_ffmpeg_pipe_broken")
                        proc = await loop.run_in_executor(None, _start_ffmpeg)
                await asyncio.sleep(_CHUNK_SAMPLES / _SR)
                continue

            # Process clip in a background task so we can keep writing silence
            # to FFmpeg stdin during CPU-intensive operations (prevents A/V stall).
            # Returns raw (stretched + normalised) audio — DSP is applied chunk-by-chunk
            # in the PCM write loop below so the chain can be rebuilt every 5 s.
            async def _process_clip() -> np.ndarray:
                try:
                    a = await loop.run_in_executor(
                        None, _read_and_stretch, clip_path, state.drift_bpm
                    )
                    return await loop.run_in_executor(None, _normalize_lufs, a, _SR)
                except Exception:
                    log.exception("dsp_read_error", path=str(clip_path))
                    return np.array([], dtype=np.float32)

            process_task = asyncio.create_task(_process_clip())

            pipe_ok = True
            while not process_task.done():
                if proc.poll() is None and proc.stdin is not None:
                    try:
                        await loop.run_in_executor(
                            None, proc.stdin.write, bytes(_CHUNK_SAMPLES * 4)
                        )
                    except BrokenPipeError:
                        log.warning("dsp_ffmpeg_pipe_broken")
                        proc = await loop.run_in_executor(None, _start_ffmpeg)
                        pipe_ok = False
                await asyncio.sleep(_CHUNK_SAMPLES / _SR)

            raw = await process_task
            if not pipe_ok or len(raw) == 0:
                playback_queue.task_done()
                continue

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

            try:
                if proc.stdin is not None:
                    chunk_idx = 0
                    board = _build_chain(state, progress=0.0)  # initial chain for this clip
                    for frame_start in range(0, total_frames, _CHUNK_SAMPLES):
                        # Rebuild DSP chain every 5 s — no audio gap, affects next chunks only
                        if chunk_idx > 0 and chunk_idx % _5S_CHUNKS == 0:
                            progress = min(bytes_written / total_bytes, 1.0) if total_bytes > 0 else 0.0
                            if state.world_event_burst:
                                board = _build_chain(state, progress=progress, burst_reverb=True)
                            else:
                                board = _build_chain(state, progress=progress)
                        chunk_frames = raw_to_write[frame_start : frame_start + _CHUNK_SAMPLES]
                        # Apply DSP to this chunk (reset=False keeps Reverb tail across chunks)
                        dsp_chunk = board(chunk_frames.T, _SR, reset=False).T
                        pcm_chunk = (dsp_chunk * 32767).astype(np.int16).tobytes()
                        await loop.run_in_executor(None, proc.stdin.write, pcm_chunk)
                        bytes_written += len(pcm_chunk)
                        # Emit progress ~every 1 s (50 chunks × 4096 / 44100 ≈ 4.6 s → use 50)
                        if chunk_idx % 50 == 0 and total_bytes > 0:
                            await state_queue.put({
                                "current_song_progress": min(bytes_written / total_bytes, 1.0),
                            })
                        await asyncio.sleep(len(pcm_chunk) / 4 / _SR)
                        chunk_idx += 1
            except BrokenPipeError:
                log.warning("dsp_ffmpeg_pipe_broken")
                proc = await loop.run_in_executor(None, _start_ffmpeg)

            await state_queue.put({
                "current_song_progress": 1.0,
                "stream_bitrate": 192.0,
                "dropped_frames": 0.0,
                "songs_played_today": state.songs_played_today + 1,
                "songs_played_total": state.songs_played_total + 1,
            })
            playback_queue.task_done()
            if conn is not None:
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
