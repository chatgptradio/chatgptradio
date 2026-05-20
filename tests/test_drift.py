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
    state.prediction_errors = {"excitement": 10.0, "audience_energy": 10.0, "world_temperature": 10.0}
    state.signal_volatilities = {"excitement": 0.1, "audience_energy": 0.1, "world_temperature": 0.1}
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
    state.prediction_errors = {"excitement": 1.0}
    state.signal_volatilities = {"excitement": 0.1}
    current = MusicVector(bpm=90.0)
    result = update_drift(current, state, 1.0)
    assert result.bpm > 90.0


def test_key_changes_when_tension_exceeds_volatility():
    state = make_state()
    state.prediction_errors = {"anxiety": 0.5, "frustration": 0.5}
    state.signal_volatilities = {"anxiety": 0.1, "frustration": 0.1}
    current = MusicVector(key="C minor")
    result = update_drift(current, state, 0.1)
    assert result.key != "C minor"


def test_key_stays_when_tension_within_volatility():
    state = make_state()
    state.prediction_errors = {"anxiety": 0.01, "frustration": 0.01}
    state.signal_volatilities = {"anxiety": 0.5, "frustration": 0.5}
    current = MusicVector(key="C minor")
    result = update_drift(current, state, 0.1)
    assert result.key == "C minor"


ALL_TERRITORIES = {
    "ambient", "electronic", "jazz", "industrial", "neoclassical", "experimental", "drone",
    "lo-fi", "cinematic", "darkwave", "techno", "psych", "noise", "minimalist", "blues",
}


def test_territory_is_valid():
    state = make_state()
    state.prediction_errors = {"excitement": 0.8, "curiosity": 0.5}
    state.signal_volatilities = {"excitement": 0.1, "curiosity": 0.1}
    state.drift_momentum = {"bpm": 2.0}
    current = MusicVector()
    result = update_drift(current, state, 0.1)
    assert result.territory in ALL_TERRITORIES


def test_no_random_import():
    import inspect
    import core.drift as drift_module
    src = inspect.getsource(drift_module)
    assert "import random" not in src
    assert "random." not in src


def test_derive_territory_industrial_on_crisis():
    # industrial differentiates from noise via creativity; moderate crisis + creativity signal
    pe = {"frustration": 0.1, "crisis_level": 0.1, "anxiety": 0.1, "creativity": 0.5}
    vol = {"frustration": 0.1, "crisis_level": 0.1, "anxiety": 0.1, "creativity": 0.1}
    territory = derive_territory_from_errors(pe, vol)
    assert territory == "industrial"


def test_circle_of_fifths_has_24_entries():
    assert len(CIRCLE_OF_FIFTHS) == 24


def test_default_key_in_circle_of_fifths():
    assert "C minor" in CIRCLE_OF_FIFTHS


def test_derive_territory_lo_fi():
    pe = {"melancholy": 2.0, "excitement": -1.0}
    vol = {"melancholy": 0.1, "excitement": 0.1}
    result = derive_territory_from_errors(pe, vol)
    assert result in {"lo-fi", "blues"}


def test_derive_territory_cinematic():
    pe = {"wonder": 2.0, "harmonic_complexity": 1.5}
    vol = {"wonder": 0.1, "harmonic_complexity": 0.1}
    result = derive_territory_from_errors(pe, vol)
    assert result in {"cinematic", "psych"}


def test_derive_territory_techno():
    pe = {"urgency": 2.0, "excitement": 1.5, "frustration": 1.0}
    vol = {"urgency": 0.1, "excitement": 0.1, "frustration": 0.1}
    result = derive_territory_from_errors(pe, vol)
    assert result == "techno"


def test_derive_territory_noise():
    pe = {"frustration": 3.0, "anxiety": 3.0, "crisis_level": 2.0}
    vol = {"frustration": 0.1, "anxiety": 0.1, "crisis_level": 0.1}
    result = derive_territory_from_errors(pe, vol)
    assert result == "noise"


def test_derive_territory_minimalist():
    # minimalist has only curiosity; suppress competing curiosity-paired signals slightly
    pe = {"curiosity": 1.0, "excitement": -0.01, "creativity": -0.01, "anxiety": -0.05,
          "wonder": -0.01, "source_divergence": -0.01}
    vol = {k: 0.1 for k in pe}
    result = derive_territory_from_errors(pe, vol)
    assert result == "minimalist"


def test_derive_territory_darkwave():
    pe = {"anxiety": 2.0, "melancholy": 2.0, "excitement": -1.5}
    vol = {"anxiety": 0.1, "melancholy": 0.1, "excitement": 0.1}
    result = derive_territory_from_errors(pe, vol)
    assert result == "darkwave"


def test_all_15_territories_reachable():
    """Each of the 15 territories must be reachable by derive_territory_from_errors."""
    pe_configs: dict[str, tuple[dict[str, float], dict[str, float]]] = {
        "ambient":      ({"excitement": -2.0, "anxiety": -2.0, "crisis_level": -2.0},
                         {"excitement": 0.1, "anxiety": 0.1, "crisis_level": 0.1}),
        "electronic":   ({"excitement": 2.0, "curiosity": 2.0},
                         {"excitement": 0.1, "curiosity": 0.1}),
        "jazz":         ({"curiosity": 2.0, "creativity": 2.0, "frustration": -1.0},
                         {"curiosity": 0.1, "creativity": 0.1, "frustration": 0.1}),
        "industrial":   ({"frustration": 0.1, "crisis_level": 0.1, "anxiety": 0.1, "creativity": 0.5},
                         {"frustration": 0.1, "crisis_level": 0.1, "anxiety": 0.1, "creativity": 0.1}),
        "neoclassical": ({"anxiety": 2.0, "curiosity": 2.0, "excitement": -2.0},
                         {"anxiety": 0.1, "curiosity": 0.1, "excitement": 0.1}),
        "experimental": ({"creativity": 3.0, "source_divergence": 3.0},
                         {"creativity": 0.1, "source_divergence": 0.1}),
        "drone":        ({"crisis_level": 2.0, "excitement": -2.0},
                         {"crisis_level": 0.1, "excitement": 0.1}),
        "lo-fi":        ({"melancholy": 3.0, "excitement": -1.0},
                         {"melancholy": 0.1, "excitement": 0.1}),
        "cinematic":    ({"wonder": 3.0, "harmonic_complexity": 3.0},
                         {"wonder": 0.1, "harmonic_complexity": 0.1}),
        "darkwave":     ({"anxiety": 2.0, "melancholy": 2.0, "excitement": -1.5},
                         {"anxiety": 0.1, "melancholy": 0.1, "excitement": 0.1}),
        "techno":       ({"urgency": 2.0, "excitement": 1.5, "frustration": 1.0},
                         {"urgency": 0.1, "excitement": 0.1, "frustration": 0.1}),
        "psych":        ({"wonder": 2.0, "source_divergence": 2.0, "curiosity": 2.0},
                         {"wonder": 0.1, "source_divergence": 0.1, "curiosity": 0.1}),
        "noise":        ({"frustration": 3.0, "anxiety": 3.0, "crisis_level": 2.0},
                         {"frustration": 0.1, "anxiety": 0.1, "crisis_level": 0.1}),
        "minimalist":   ({"curiosity": 1.0, "excitement": -0.01, "creativity": -0.01,
                           "anxiety": -0.05, "wonder": -0.01, "source_divergence": -0.01},
                         {"curiosity": 0.1, "excitement": 0.1, "creativity": 0.1,
                          "anxiety": 0.1, "wonder": 0.1, "source_divergence": 0.1}),
        "blues":        ({"melancholy": 2.0, "frustration": 2.0, "excitement": -1.5},
                         {"melancholy": 0.1, "frustration": 0.1, "excitement": 0.1}),
    }

    reachable: set[str] = set()
    for territory, (pe, vol) in pe_configs.items():
        result = derive_territory_from_errors(pe, vol)
        reachable.add(result)

    assert ALL_TERRITORIES == reachable, (
        f"Territories not reachable: {ALL_TERRITORIES - reachable}"
    )
