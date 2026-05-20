"""DSP Engine — Pedalboard + pyrubberband → FFmpeg stdin → RTMP."""
import asyncio
import os
import subprocess
from pathlib import Path

import numpy as np
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


async def run_dsp(
    state: GlobalState,
    playback_queue: asyncio.Queue,
    state_queue: asyncio.Queue,
) -> None:
    rtmp_url = os.environ.get("RTMP_URL", "")
    if not rtmp_url:
        log.warning("dsp_disabled", reason="RTMP_URL not set")
        return

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "s16le", "-ar", str(_SR), "-ac", "2",
        "-i", "pipe:0",
        "-c:a", "aac", "-b:a", "192k",
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
                    await loop.run_in_executor(None, proc.stdin.write, pcm_s16)
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
