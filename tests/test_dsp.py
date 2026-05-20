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
