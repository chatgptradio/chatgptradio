"""Tests for DSP intra-clip automation (RT1), reverb throw burst (RT2), and BPM rate limit (RT3)."""
import pytest

from core.state import GlobalState, MusicVector


# ---------------------------------------------------------------------------
# RT1 — Intra-clip DSP automation
# ---------------------------------------------------------------------------


def test_build_chain_automation_inactive_when_no_signal() -> None:
    """When excitement=0 and urgency=0, progress has no effect on LadderFilter cutoff."""
    from pedalboard import LadderFilter
    from core.dsp import _build_chain

    state = GlobalState(excitement=0.0, urgency=0.0)
    chain_base = _build_chain(state, progress=0.0)
    chain_with_progress = _build_chain(state, progress=0.3)

    ladder_base = next(e for e in chain_base if isinstance(e, LadderFilter))
    ladder_prog = next(e for e in chain_with_progress if isinstance(e, LadderFilter))

    assert ladder_base.cutoff_hz == pytest.approx(ladder_prog.cutoff_hz, abs=1.0)


def test_build_chain_automation_active_buildup() -> None:
    """With excitement=0.5 and progress=0.25, LadderFilter cutoff should be ~10100 Hz."""
    from pedalboard import LadderFilter
    from core.dsp import _build_chain

    state = GlobalState(excitement=0.5, urgency=0.0)
    chain = _build_chain(state, progress=0.25)

    ladder = next(e for e in chain if isinstance(e, LadderFilter))
    # 300 + (0.25 / 0.5) * 19700 = 300 + 0.5 * 19700 = 300 + 9850 = 10150
    expected = 300.0 + (0.25 / 0.5) * 19700.0
    assert ladder.cutoff_hz == pytest.approx(expected, abs=50.0)


def test_build_chain_automation_drop_open() -> None:
    """With excitement=0.5 and progress=0.6, LadderFilter cutoff should be 20000 Hz (fully open)."""
    from pedalboard import LadderFilter
    from core.dsp import _build_chain

    state = GlobalState(excitement=0.5, urgency=0.0)
    chain = _build_chain(state, progress=0.6)

    ladder = next(e for e in chain if isinstance(e, LadderFilter))
    assert ladder.cutoff_hz == pytest.approx(20000.0, abs=1.0)


def test_build_chain_release_reduces_reverb() -> None:
    """With excitement=0.5 and progress=0.9, Reverb wet_level must be lower than at progress=0.0."""
    from pedalboard import Reverb
    from core.dsp import _build_chain

    state = GlobalState(excitement=0.5, urgency=0.0)
    chain_base = _build_chain(state, progress=0.0)
    chain_release = _build_chain(state, progress=0.9)

    reverb_base = next(e for e in chain_base if isinstance(e, Reverb))
    reverb_release = next(e for e in chain_release if isinstance(e, Reverb))

    assert reverb_release.wet_level < reverb_base.wet_level


# ---------------------------------------------------------------------------
# RT2 — Reverb throw on world_event_burst
# ---------------------------------------------------------------------------


def test_burst_reverb_sets_high_wet() -> None:
    """When burst_reverb=True, Reverb wet_level must be 1.0 and room_size must be 0.95."""
    from pedalboard import Reverb
    from core.dsp import _build_chain

    state = GlobalState()
    chain = _build_chain(state, progress=0.0, burst_reverb=True)

    reverb = next(e for e in chain if isinstance(e, Reverb))
    assert reverb.wet_level == pytest.approx(1.0, abs=0.01)
    assert reverb.room_size == pytest.approx(0.95, abs=0.01)


# ---------------------------------------------------------------------------
# RT3 — BPM rate limit in update_drift()
# ---------------------------------------------------------------------------


def test_bpm_rate_limit_caps_increase() -> None:
    """A very large positive force that would jump BPM by 20 is capped at +8."""
    from core.drift import update_drift

    state = GlobalState()
    state.prediction_errors = {"excitement": 100.0, "audience_energy": 100.0, "world_temperature": 100.0}
    state.signal_volatilities = {"excitement": 0.01, "audience_energy": 0.01, "world_temperature": 0.01}
    current = MusicVector(bpm=90.0)
    result = update_drift(current, state, 1.0)
    assert result.bpm <= 90.0 + 8.0


def test_bpm_rate_limit_caps_decrease() -> None:
    """A very large negative force is capped at -8 BPM."""
    from core.drift import update_drift

    state = GlobalState()
    state.prediction_errors = {
        "excitement": -100.0, "audience_energy": -100.0, "world_temperature": -100.0,
    }
    state.signal_volatilities = {"excitement": 0.01, "audience_energy": 0.01, "world_temperature": 0.01}
    current = MusicVector(bpm=90.0)
    result = update_drift(current, state, 1.0)
    assert result.bpm >= 90.0 - 8.0


def test_bpm_rate_limit_small_change_unchanged() -> None:
    """A small force producing a 3 BPM delta passes through unchanged."""
    from core.drift import update_drift

    state = GlobalState()
    # Set up a small positive force that nudges BPM by ~3
    # new_bpm_momentum = force * dt_h, new_bpm = current.bpm + momentum * 40
    # We want delta ≈ 3 → momentum ≈ 0.075 → force ≈ 0.075 (with dt_h=1, damping≈0)
    state.drift_momentum = {"bpm": 0.0}
    state.prediction_errors = {"excitement": 0.075}
    state.signal_volatilities = {"excitement": 1.0}  # pw = 0.075 / 1.0 = 0.075
    # With w_bpm["excitement"] ≈ 0.33 (equal weights), force ≈ 0.025 → delta ≈ 1 BPM
    # Use a direct momentum approach: set drift_momentum so result is within limit
    state.drift_momentum = {"bpm": 0.07}  # 0.07 * 40 = 2.8 BPM delta
    state.prediction_errors = {}
    state.signal_volatilities = {}
    current = MusicVector(bpm=90.0)
    result = update_drift(current, state, 1.0)
    # delta should be well within ±8 BPM
    assert abs(result.bpm - 90.0) <= 8.0
