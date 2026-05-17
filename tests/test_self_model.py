import pytest

from core.state import GlobalState
from core.self_model import update_self_model


def test_updates_all_four_dicts():
    state = GlobalState()
    update_self_model(state, "excitation", 0.5)
    assert "excitation" in state.signal_baselines
    assert "excitation" in state.signal_adaptation_rates
    assert "excitation" in state.signal_volatilities
    assert "excitation" in state.prediction_errors


def test_convergence_after_100_stable_calls():
    state = GlobalState()
    for _ in range(100):
        update_self_model(state, "excitation", 0.5)
    assert abs(state.signal_baselines["excitation"] - 0.5) < 0.01


def test_step_change_creates_large_then_decaying_error():
    state = GlobalState()
    for _ in range(50):
        update_self_model(state, "signal", 0.3)

    update_self_model(state, "signal", 0.9)
    large_error = abs(state.prediction_errors["signal"])
    assert large_error > 0.1

    for _ in range(50):
        update_self_model(state, "signal", 0.9)
    small_error = abs(state.prediction_errors["signal"])
    assert small_error < large_error


def test_tau_smaller_for_volatile_signal():
    state_low_vol = GlobalState()
    state_high_vol = GlobalState()

    state_low_vol.signal_volatilities["s"] = 0.01
    state_high_vol.signal_volatilities["s"] = 0.5

    update_self_model(state_low_vol, "s", 0.5)
    update_self_model(state_high_vol, "s", 0.5)

    tau_low = state_low_vol.signal_adaptation_rates["s"]
    tau_high = state_high_vol.signal_adaptation_rates["s"]
    assert tau_low > tau_high


def test_prediction_error_is_value_minus_baseline_before_update():
    state = GlobalState()
    state.signal_baselines["s"] = 0.3
    update_self_model(state, "s", 0.7)
    assert state.prediction_errors["s"] == pytest.approx(0.7 - 0.3)


def test_first_call_uses_value_as_bootstrap_baseline():
    state = GlobalState()
    update_self_model(state, "fresh", 0.6)
    assert state.prediction_errors["fresh"] == pytest.approx(0.0)
    assert state.signal_baselines["fresh"] == pytest.approx(0.6)


def test_volatility_increases_after_large_error():
    state = GlobalState()
    state.signal_baselines["s"] = 0.0
    state.signal_volatilities["s"] = 0.1
    update_self_model(state, "s", 1.0)
    assert state.signal_volatilities["s"] > 0.1
