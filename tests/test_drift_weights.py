
from core.state import GlobalState
from core.self_model import update_drift_weights


def test_initial_weights_are_equal():
    state = GlobalState()
    update_drift_weights(state, "bpm", ["a", "b", "c"])
    w = state.drift_weights["bpm"]
    assert abs(w["a"] - w["b"]) < 1e-9
    assert abs(w["b"] - w["c"]) < 1e-9


def test_weights_sum_to_1():
    state = GlobalState()
    state.prediction_errors = {"a": 0.3, "b": -0.1, "c": 0.05}
    state.drift_momentum = {"bpm": 0.5}
    for _ in range(100):
        update_drift_weights(state, "bpm", ["a", "b", "c"])
    total = sum(state.drift_weights["bpm"].values())
    assert abs(total - 1.0) < 1e-9


def test_aligned_signal_gains_weight_over_1000_updates():
    state = GlobalState()
    # signal "a" always aligns with positive momentum
    state.drift_momentum = {"bpm": 0.5}
    state.prediction_errors = {"a": 0.3, "b": -0.1, "c": 0.0}
    for _ in range(1000):
        update_drift_weights(state, "bpm", ["a", "b", "c"])
    w = state.drift_weights["bpm"]
    assert w["a"] > w["b"]
    assert w["a"] > w["c"]


def test_weights_stay_within_bounds():
    state = GlobalState()
    state.drift_momentum = {"bpm": 1.0}
    state.prediction_errors = {"a": 1.0, "b": -1.0}
    for _ in range(5000):
        update_drift_weights(state, "bpm", ["a", "b"])
    w = state.drift_weights["bpm"]
    for v in w.values():
        assert v >= 0.0
        assert v <= 1.0


def test_zero_momentum_does_not_change_weights():
    state = GlobalState()
    state.prediction_errors = {"a": 0.5, "b": 0.3}
    state.drift_momentum = {"bpm": 0.0}
    update_drift_weights(state, "bpm", ["a", "b"])
    w = state.drift_weights["bpm"]
    # With zero momentum, neither condition fires → weights unchanged from 0.5
    assert abs(w["a"] - 0.5) < 1e-9
    assert abs(w["b"] - 0.5) < 1e-9


def test_new_dim_initializes_with_equal_weights():
    state = GlobalState()
    state.drift_weights["bpm"] = {"x": 0.5, "y": 0.5}
    update_drift_weights(state, "energy", ["p", "q", "r"])
    assert "energy" in state.drift_weights
    w = state.drift_weights["energy"]
    for v in w.values():
        assert abs(v - 1.0 / 3) < 1e-9
