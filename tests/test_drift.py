import pytest

from core.drift import (
    CIRCLE_OF_FIFTHS,
    derive_territory_from_errors,
    update_drift,
)
from core.state import GlobalState, MusicVector


def make_state(**kwargs) -> GlobalState:
    return GlobalState(**kwargs)


def test_returns_new_music_vector_not_same_object():
    state = make_state()
    current = MusicVector()
    result = update_drift(current, state, 1.0)
    assert result is not current


def test_bpm_stays_in_range_after_many_updates():
    state = make_state()
    state.prediction_errors = {"excitation": 10.0, "audience_energy": 10.0, "world_temperature": 10.0}
    state.signal_volatilities = {"excitation": 0.1, "audience_energy": 0.1, "world_temperature": 0.1}
    current = MusicVector(bpm=120.0)
    for _ in range(100):
        current = update_drift(current, state, 0.01)
    assert 60.0 <= current.bpm <= 140.0


def test_stable_world_drift_velocity_near_zero():
    state = make_state()
    state.prediction_errors = {}
    current = MusicVector()
    result = update_drift(current, state, 0.1)
    assert result.bpm == pytest.approx(current.bpm, abs=5.0)


def test_high_excitation_pe_increases_bpm():
    state = make_state()
    state.prediction_errors = {"excitation": 1.0}
    state.signal_volatilities = {"excitation": 0.1}
    current = MusicVector(bpm=90.0)
    result = update_drift(current, state, 1.0)
    assert result.bpm > 90.0


def test_key_changes_when_tension_exceeds_volatility():
    state = make_state()
    state.prediction_errors = {"anxiete": 0.5, "frustration": 0.5}
    state.signal_volatilities = {"anxiete": 0.1, "frustration": 0.1}
    current = MusicVector(key="C minor")
    result = update_drift(current, state, 0.1)
    assert result.key != "C minor"


def test_key_stays_when_tension_within_volatility():
    state = make_state()
    state.prediction_errors = {"anxiete": 0.01, "frustration": 0.01}
    state.signal_volatilities = {"anxiete": 0.5, "frustration": 0.5}
    current = MusicVector(key="C minor")
    result = update_drift(current, state, 0.1)
    assert result.key == "C minor"


def test_territory_is_valid():
    state = make_state()
    state.prediction_errors = {"excitation": 0.8, "curiosite": 0.5}
    state.signal_volatilities = {"excitation": 0.1, "curiosite": 0.1}
    state.drift_momentum = {"bpm": 2.0}
    current = MusicVector()
    result = update_drift(current, state, 0.1)
    valid_territories = {"ambient", "electronic", "jazz", "industrial", "neoclassical", "experimental", "drone"}
    assert result.territory in valid_territories


def test_no_random_import():
    import inspect
    import core.drift as drift_module
    src = inspect.getsource(drift_module)
    assert "import random" not in src
    assert "random." not in src


def test_derive_territory_industrial_on_crisis():
    pe = {"frustration": 0.5, "crisis_level": 0.8, "anxiete": 0.6}
    vol = {"frustration": 0.1, "crisis_level": 0.1, "anxiete": 0.1}
    territory = derive_territory_from_errors(pe, vol)
    assert territory == "industrial"


def test_circle_of_fifths_has_24_entries():
    assert len(CIRCLE_OF_FIFTHS) == 24


def test_default_key_in_circle_of_fifths():
    assert "C minor" in CIRCLE_OF_FIFTHS
