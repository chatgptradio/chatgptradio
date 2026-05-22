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
from pedalboard import Chorus, Compressor, Gain, HighShelfFilter, Limiter, PitchShift, Reverb  # type: ignore[attr-defined]
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


def _build_chain(state: GlobalState) -> Pedalboard:
    wt = state.world_temperature
    cr = state.crisis_level
    mt = state.musical_tension
    ae = state.audience_energy
    em = state.curiosity
    me = state.anxiety
    ur = state.excitement
    hc = state.harmonic_complexity

    return Pedalboard([
        Reverb(
            room_size=_clamp(0.2 + wt * 0.4 + cr * 0.25, 0.0, 1.0),
            wet_level=_clamp(0.1 + cr * 0.5 + me * 0.2, 0.0, 1.0),
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
        Limiter(threshold_db=-1.0),
    ])


def _crossfade_arrays(a: np.ndarray, b: np.ndarray, sr: int) -> np.ndarray:
    n = len(a)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, np.newaxis]
    return a * (1.0 - t) + b * t


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
            # thread_queue_size prevents x11grab queue blocking that silences video stream.
            # 32 = 2s buffer at 15fps. 512 would pre-alloc 512×3.5MB=1.8GB of X11 shared mem.
            "-thread_queue_size", "32",
            "-f", "x11grab",
            "-framerate", "15",            # 15fps — réduit charge CPU SwiftShader sur VPS sans GPU
            "-video_size", "1280x720",
            "-draw_mouse", "0",
            "-i", f"{display}.0",
        ]
    else:
        video_input = [
            "-f", "lavfi",
            "-i", "color=c=0x0a0a1a:s=1280x720:r=15",
        ]

    video_encode = [
        "-c:v", "libx264", "-preset", "ultrafast",  # ultrafast — libère CPU pour x11grab + Python
        # nal-hrd=cbr forces filler NAL units so libx264 actually hits 2500k on static content
        # (without it, skip-heavy frames produce ~200-500 Kbps despite minrate=2500k)
        "-b:v", "2500k", "-minrate", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
        "-x264opts", "nal-hrd=cbr:force-cfr=1",
        "-g", "30",                        # keyframe every 2s at 15fps (YouTube requires ≤4s)
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
        return subprocess.Popen(
            ffmpeg_cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

    proc: subprocess.Popen[bytes] = await loop.run_in_executor(None, _start_ffmpeg)
    log.info("dsp_ffmpeg_started")

    async def _log_stderr(p: subprocess.Popen[bytes]) -> None:
        assert p.stderr is not None
        while p.poll() is None:
            line = await loop.run_in_executor(None, p.stderr.readline)
            if line:
                log.info("ffmpeg_stderr", msg=line.decode(errors="replace").rstrip())

    asyncio.create_task(_log_stderr(proc))

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
                xfade = _crossfade_arrays(_pending_tail[:blend_len], raw[:blend_len], _SR)
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
                    board = _build_chain(state)  # initial chain for this clip
                    for frame_start in range(0, total_frames, _CHUNK_SAMPLES):
                        # Rebuild DSP chain every 5 s — no audio gap, affects next chunks only
                        if chunk_idx > 0 and chunk_idx % _5S_CHUNKS == 0:
                            board = _build_chain(state)
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
