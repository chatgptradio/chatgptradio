"""DSP Engine — Pedalboard + pyrubberband → FFmpeg stdin → RTMP."""
import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
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


async def run_dsp(
    state: GlobalState,
    playback_queue: asyncio.Queue,
    state_queue: asyncio.Queue,
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
            "-f", "x11grab",
            "-framerate", "30",
            "-video_size", "1280x720",
            "-i", f"{display}.0",
        ]
    else:
        video_input = [
            "-f", "lavfi",
            "-i", "color=c=0x0a0a1a:s=1280x720:r=30",
        ]

    video_encode = [
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", "400k", "-pix_fmt", "yuv420p",
    ]
    if not use_x11grab:
        # static colour frame — stillimage tune cuts CPU/bitrate significantly
        video_encode += ["-tune", "stillimage"]

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        *video_input,
        # Audio from stdin (PCM 16-bit stereo)
        "-f", "s16le", "-ar", str(_SR), "-ac", "2", "-i", "pipe:0",
        *video_encode,
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v", "-map", "1:a",
        "-f", "flv", rtmp_url,
    ]
    loop = asyncio.get_running_loop()
    restart_delay = 2.0
    prev_audio: np.ndarray | None = None

    def _start_ffmpeg() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            ffmpeg_cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

    proc: subprocess.Popen[bytes] = await loop.run_in_executor(None, _start_ffmpeg)
    log.info("dsp_ffmpeg_started")

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
                clip_path: Path = await asyncio.wait_for(playback_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                audio = await loop.run_in_executor(
                    None, _read_and_stretch, clip_path, state.drift_bpm
                )
                audio = await loop.run_in_executor(None, _normalize_lufs, audio, _SR)
            except Exception:
                log.exception("dsp_read_error", path=str(clip_path))
                playback_queue.task_done()
                continue

            chain = _build_chain(state)
            processed = await loop.run_in_executor(None, _process_audio, audio, chain)

            if prev_audio is not None:
                tail_len = min(_CROSSFADE_SAMPLES, len(prev_audio), len(processed))
                xfade = _crossfade_arrays(prev_audio[-tail_len:], processed[:tail_len], _SR)
                processed = np.concatenate([xfade, processed[tail_len:]])

            prev_audio = processed
            pcm_s16 = (processed * 32767).astype(np.int16).tobytes()

            try:
                if proc.stdin is not None:
                    chunk_bytes = _CHUNK_SAMPLES * 4  # stereo int16 = 4 bytes/sample
                    for i in range(0, len(pcm_s16), chunk_bytes):
                        chunk = pcm_s16[i : i + chunk_bytes]
                        await loop.run_in_executor(None, proc.stdin.write, chunk)
                        await asyncio.sleep(len(chunk) / 4 / _SR)
            except BrokenPipeError:
                log.warning("dsp_ffmpeg_pipe_broken")
                proc = await loop.run_in_executor(None, _start_ffmpeg)

            frames = len(processed)
            await state_queue.put({
                "current_song_progress": min(frames / (_SR * 45), 1.0),
                "stream_bitrate": 192.0,
                "dropped_frames": 0.0,
            })
            playback_queue.task_done()
    finally:
        if proc.poll() is None:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.terminate()
