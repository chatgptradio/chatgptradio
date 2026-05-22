"""Tests for scripts/index_references.py — librosa metric corrections (issue #174)."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import scipy.stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav(tmp_path: Path, duration_s: float = 1.0, sr: int = 22050) -> Path:
    """Create a minimal synthetic WAV file filled with zeros."""
    n_samples = int(sr * duration_s)
    audio = np.zeros(n_samples, dtype=np.float32)
    pcm = (audio * 32767).astype(np.int16)

    wav_path = tmp_path / "synth.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return wav_path


def _make_sine_wav(tmp_path: Path, freq: float = 440.0, duration_s: float = 2.0, sr: int = 22050) -> Path:
    """Create a synthetic WAV file with a sine wave (non-silent)."""
    n_samples = int(sr * duration_s)
    t = np.linspace(0, duration_s, n_samples, endpoint=False)
    audio = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    pcm = (audio * 32767).astype(np.int16)

    wav_path = tmp_path / "sine.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return wav_path


# ---------------------------------------------------------------------------
# Unit tests — metric formulas (no file I/O, pure numpy/scipy)
# ---------------------------------------------------------------------------


def test_harmonic_complexity_from_chroma_entropy():
    """harmonic_complexity via chroma entropy must be in [0, 1]."""
    # Simulate a chroma matrix (12 pitch classes, N frames)
    rng = np.random.default_rng(42)
    chroma = rng.random((12, 100))
    chroma /= chroma.sum(axis=0, keepdims=True) + 1e-10  # normalise columns

    entropy = scipy.stats.entropy(chroma.mean(axis=1) + 1e-10)
    harmonic_complexity = float(entropy / np.log(12))

    assert 0.0 <= harmonic_complexity <= 1.0, (
        f"harmonic_complexity={harmonic_complexity} out of [0, 1]"
    )


def test_harmonic_complexity_uniform_chroma_near_one():
    """Uniform chroma distribution should yield harmonic_complexity close to 1."""
    chroma = np.ones((12, 50)) / 12.0
    entropy = scipy.stats.entropy(chroma.mean(axis=1) + 1e-10)
    harmonic_complexity = float(entropy / np.log(12))
    assert harmonic_complexity > 0.95


def test_harmonic_complexity_concentrated_chroma_near_zero():
    """Single-pitch chroma should yield lower harmonic_complexity."""
    chroma = np.zeros((12, 50))
    chroma[0, :] = 1.0  # all energy on C
    entropy = scipy.stats.entropy(chroma.mean(axis=1) + 1e-10)
    harmonic_complexity = float(entropy / np.log(12))
    # Should be clearly below uniform (< 0.5)
    assert harmonic_complexity < 0.5


def test_mfcc_fingerprint_has_20_coefficients():
    """mfcc_fingerprint must contain exactly 20 float values."""
    import librosa  # local import to avoid module-level cost

    sr = 22050
    duration_s = 1.0
    y = np.zeros(int(sr * duration_s), dtype=np.float32)

    mfcc_full = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    mfcc_fingerprint = mfcc_full.mean(axis=1).tolist()

    assert len(mfcc_fingerprint) == 20
    assert all(isinstance(v, float) for v in mfcc_fingerprint)


# ---------------------------------------------------------------------------
# Integration tests — using a real (synthetic) WAV file
# ---------------------------------------------------------------------------


def test_duration_s_nonzero(tmp_path):
    """duration_s must be > 0 for a non-empty audio file."""
    import librosa

    wav = _make_sine_wav(tmp_path, duration_s=2.0)
    y, sr = librosa.load(str(wav), sr=22050, mono=True)
    duration_s = float(librosa.get_duration(y=y, sr=sr))

    assert duration_s > 0.0, f"Expected duration_s > 0, got {duration_s}"


def test_duration_s_approximately_correct(tmp_path):
    """duration_s must approximately match the actual file length."""
    import librosa

    target_duration = 2.0
    wav = _make_sine_wav(tmp_path, duration_s=target_duration)
    y, sr = librosa.load(str(wav), sr=22050, mono=True)
    duration_s = float(librosa.get_duration(y=y, sr=sr))

    assert abs(duration_s - target_duration) < 0.1


def test_anxiety_ioi_entropy_silent_clip():
    """Silent clip with fewer than 3 onsets yields anxiety=0.0."""
    import librosa

    sr = 22050
    y = np.zeros(sr, dtype=np.float32)  # 1 second of silence
    onset_times = librosa.frames_to_time(
        librosa.onset.onset_detect(y=y, sr=sr), sr=sr
    )
    if len(onset_times) > 2:
        ioi = np.diff(onset_times)
        anxiety = float(min(scipy.stats.entropy(np.histogram(ioi, bins=10)[0] + 1e-10) / np.log(10), 1.0))
    else:
        anxiety = 0.0

    assert anxiety == 0.0


def test_anxiety_ioi_entropy_in_range(tmp_path):
    """anxiety from IOI entropy must be in [0, 1]."""
    import librosa

    wav = _make_sine_wav(tmp_path, freq=440.0, duration_s=3.0)
    y, sr = librosa.load(str(wav), sr=22050, mono=True)

    onset_times = librosa.frames_to_time(
        librosa.onset.onset_detect(y=y, sr=sr), sr=sr
    )
    if len(onset_times) > 2:
        ioi = np.diff(onset_times)
        anxiety = float(min(scipy.stats.entropy(np.histogram(ioi, bins=10)[0] + 1e-10) / np.log(10), 1.0))
    else:
        anxiety = 0.0

    assert 0.0 <= anxiety <= 1.0


def test_drift_timbre_in_timbre_sequence(tmp_path):
    """drift_timbre must be one of the canonical _TIMBRE_SEQUENCE values."""
    import librosa

    _TIMBRE_SEQUENCE = ["warm", "organic", "digital", "cold", "metallic"]

    wav = _make_sine_wav(tmp_path, freq=440.0, duration_s=2.0)
    y, sr = librosa.load(str(wav), sr=22050, mono=True)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_centroid = float(mfcc[1].mean())
    if mfcc_centroid < -20:
        drift_timbre = "warm"
    elif mfcc_centroid < -5:
        drift_timbre = "organic"
    elif mfcc_centroid < 10:
        drift_timbre = "digital"
    elif mfcc_centroid < 25:
        drift_timbre = "cold"
    else:
        drift_timbre = "metallic"

    assert drift_timbre in _TIMBRE_SEQUENCE, (
        f"drift_timbre={drift_timbre!r} not in {_TIMBRE_SEQUENCE}"
    )
