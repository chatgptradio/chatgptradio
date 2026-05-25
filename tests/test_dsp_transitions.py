"""Tests for DJ-style transition effects: T1 (EQ crossfade), T2 (filter sweep), T3 (reverb throw)."""
import numpy as np

from core.state import GlobalState

_SR = 44100
_RNG = np.random.default_rng(42)
_AUDIO_3S: np.ndarray = _RNG.random((44100 * 3, 2)).astype(np.float32)


def test_transition_eq_reduces_bass_outgoing() -> None:
    """Outgoing tail after _apply_transition_eq should have lower low-freq RMS than input."""
    from core.dsp import _apply_transition_eq

    state = GlobalState()
    audio = _AUDIO_3S.copy()
    processed_out, _ = _apply_transition_eq(audio, audio, state, _SR)

    # Measure low-frequency RMS by comparing RMS of the output vs input.
    # A -12 dB shelf at 200 Hz must reduce overall energy (audio has low-freq content).
    rms_in = float(np.sqrt(np.mean(audio ** 2)))
    rms_out = float(np.sqrt(np.mean(processed_out ** 2)))
    assert rms_out < rms_in, (
        f"EQ should reduce bass: rms_in={rms_in:.4f}, rms_out={rms_out:.4f}"
    )


def test_transition_eq_same_shape() -> None:
    """Output shapes from _apply_transition_eq must match input shapes."""
    from core.dsp import _apply_transition_eq

    state = GlobalState()
    audio = _AUDIO_3S.copy()
    processed_out, processed_in = _apply_transition_eq(audio, audio, state, _SR)
    assert processed_out.shape == audio.shape, (
        f"outgoing shape mismatch: {processed_out.shape} != {audio.shape}"
    )
    assert processed_in.shape == audio.shape, (
        f"incoming shape mismatch: {processed_in.shape} != {audio.shape}"
    )


def test_filter_sweep_close_shape() -> None:
    """_apply_filter_sweep direction='close' must return same shape as input."""
    from core.dsp import _apply_filter_sweep

    state = GlobalState(drift_velocity=0.5)
    audio = _AUDIO_3S.copy()
    out = _apply_filter_sweep(audio, state, _SR, direction="close")
    assert out.shape == audio.shape, (
        f"filter sweep 'close' shape mismatch: {out.shape} != {audio.shape}"
    )


def test_filter_sweep_open_shape() -> None:
    """_apply_filter_sweep direction='open' must return same shape as input."""
    from core.dsp import _apply_filter_sweep

    state = GlobalState(drift_velocity=0.5)
    audio = _AUDIO_3S.copy()
    out = _apply_filter_sweep(audio, state, _SR, direction="open")
    assert out.shape == audio.shape, (
        f"filter sweep 'open' shape mismatch: {out.shape} != {audio.shape}"
    )


def test_reverb_throw_shape() -> None:
    """_apply_reverb_throw must return same shape as input."""
    from core.dsp import _apply_reverb_throw

    audio = _AUDIO_3S.copy()
    out = _apply_reverb_throw(audio, _SR)
    assert out.shape == audio.shape, (
        f"reverb throw shape mismatch: {out.shape} != {audio.shape}"
    )


def test_reverb_throw_changes_last_half() -> None:
    """Last half of reverb throw output must differ from input (reverb was applied)."""
    from core.dsp import _apply_reverb_throw

    # Use a 1-second window as wired in run_dsp (last_s = min(_SR, len(tail)))
    audio = _RNG.random((_SR, 2)).astype(np.float32)
    out = _apply_reverb_throw(audio, _SR)
    half = len(audio) // 2
    # The wet=1.0 reverb must change the second half
    assert not np.allclose(out[half:], audio[half:], atol=1e-5), (
        "reverb throw should alter the last half of the audio"
    )
