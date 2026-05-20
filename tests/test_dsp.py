import asyncio
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from core.state import GlobalState


def _silence_wav(path: Path, duration_s: float = 1.0, sr: int = 44100) -> None:
    import wave
    n = int(duration_s * sr)
    with wave.open(str(path), "w") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(b"\x00" * n * 2 * 2)


def test_dsp_module_importable() -> None:
    import core.dsp  # noqa: F401


def test_build_chain_returns_pedalboard() -> None:
    from pedalboard._pedalboard import Pedalboard
    from core.dsp import _build_chain
    assert isinstance(_build_chain(GlobalState()), Pedalboard)


def test_build_chain_normal_state() -> None:
    from pedalboard import Reverb
    from core.dsp import _build_chain
    chain = _build_chain(GlobalState())
    reverb = next(e for e in chain if isinstance(e, Reverb))
    assert reverb.room_size == pytest.approx(0.2, abs=0.01)


def test_build_chain_crisis_state() -> None:
    from pedalboard import Reverb
    from core.dsp import _build_chain
    chain = _build_chain(GlobalState(crisis_level=1.0, world_temperature=1.0))
    reverb = next(e for e in chain if isinstance(e, Reverb))
    assert reverb.room_size == pytest.approx(0.85, abs=0.05)


def test_build_chain_has_limiter() -> None:
    from pedalboard import Limiter
    from core.dsp import _build_chain
    assert any(isinstance(e, Limiter) for e in _build_chain(GlobalState()))


async def test_run_dsp_no_rtmp_exits_gracefully() -> None:
    from core.dsp import run_dsp
    state = GlobalState()
    with patch.dict("os.environ", {}, clear=True):
        await asyncio.wait_for(
            run_dsp(state, asyncio.Queue(), asyncio.Queue()), timeout=2.0
        )


def test_crossfade_shape() -> None:
    from core.dsp import _crossfade_arrays
    sr = 44100
    window = 3 * sr
    a = np.ones((window, 2), dtype=np.float32)
    b = np.ones((window, 2), dtype=np.float32)
    out = _crossfade_arrays(a, b, sr)
    assert out.shape == (window, 2)
    assert float(np.mean(np.abs(out[window // 2]))) == pytest.approx(1.0, abs=0.05)


def test_stretch_ratio() -> None:
    from core.dsp import _stretch_ratio
    assert _stretch_ratio(90.0) == pytest.approx(1.0)
    assert _stretch_ratio(135.0) == pytest.approx(1.5)
    assert _stretch_ratio(45.0) == pytest.approx(0.5)


def test_normalize_lufs_boosts_quiet_clip() -> None:
    """Un clip très silencieux doit être amplifié."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.001).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    assert np.abs(out).mean() > np.abs(audio).mean()


def test_normalize_lufs_attenuates_loud_clip() -> None:
    """Un clip très fort doit être atténué."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.9).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    assert np.abs(out).mean() < np.abs(audio).mean()


def test_normalize_lufs_caps_gain() -> None:
    """Le gain ne doit jamais dépasser ±18 dB (facteur 7.94)."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 1e-6).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    max_ratio = 10.0 ** (18.0 / 20.0)  # ≈ 7.94
    if np.abs(out).max() > 0:
        ratio = np.abs(out).max() / (np.abs(audio).max() + 1e-12)
        assert ratio <= max_ratio + 1e-3


def test_normalize_lufs_silence_passthrough() -> None:
    """Un signal silence (zéros) doit être retourné inchangé."""
    from core.dsp import _normalize_lufs
    sr = 44100
    audio = np.zeros((sr * 2, 2), dtype=np.float32)
    out = _normalize_lufs(audio, sr)
    np.testing.assert_array_equal(out, audio)


def test_normalize_lufs_output_shape() -> None:
    """La shape de sortie doit être identique à la shape d'entrée."""
    from core.dsp import _normalize_lufs
    sr = 44100
    t = np.linspace(0, 1.0, sr, dtype=np.float32)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.3).reshape(-1, 1).repeat(2, axis=1)
    out = _normalize_lufs(audio, sr)
    assert out.shape == audio.shape
