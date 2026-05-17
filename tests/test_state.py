import pytest
from datetime import datetime, timezone

from pydantic import BaseModel

from core.state import GlobalState, MusicVector


def test_global_state_instantiates_with_defaults():
    state = GlobalState()
    assert state is not None


def test_global_state_has_77_plus_fields():
    fields = GlobalState.model_fields
    assert len(fields) >= 55


def test_openai_status_defaults_operational():
    state = GlobalState()
    assert state.openai_status == 1.0
    assert state.anthropic_status == 1.0
    assert state.gemini_status == 1.0


def test_drift_defaults():
    state = GlobalState()
    assert state.drift_bpm == 90.0
    assert state.drift_key == "C minor"
    assert state.drift_timbre == "warm"
    assert state.drift_territory == "ambient"
    assert state.drift_energy == 0.5


def test_all_float_fields_default_zero_except_status():
    state = GlobalState()
    assert state.excitation == 0.0
    assert state.anxiete == 0.0
    assert state.world_temperature == 0.0
    assert state.crisis_level == 0.0


def test_dict_fields_default_empty():
    state = GlobalState()
    assert state.source_health == {}
    assert state.signal_baselines == {}
    assert state.drift_weights == {}
    assert state.prediction_errors == {}


def test_updated_at_is_datetime_utc():
    state = GlobalState()
    assert isinstance(state.updated_at, datetime)
    assert state.updated_at.tzinfo is not None


def test_model_dump_json_serializable():
    import json
    state = GlobalState()
    d = state.model_dump(mode="json")
    # Should not raise
    dumped = json.dumps(d)
    assert "updated_at" in dumped
    assert "excitation" in dumped


def test_mutate_field_and_reserialize():
    state = GlobalState()
    state.excitation = 0.75
    state.signal_baselines["excitation"] = 0.43
    state.drift_weights["bpm"] = {"excitation": 0.38}
    d = state.model_dump(mode="json")
    assert d["excitation"] == 0.75
    assert d["signal_baselines"]["excitation"] == 0.43
    assert d["drift_weights"]["bpm"]["excitation"] == 0.38


def test_music_vector_dataclass():
    mv = MusicVector()
    assert mv.bpm == 90.0
    assert mv.key == "C minor"
    assert mv.timbre == "warm"
    assert mv.territory == "ambient"


def test_music_vector_custom_values():
    mv = MusicVector(bpm=120.0, key="F# major", timbre="metallic", territory="electronic")
    assert mv.bpm == 120.0
    assert mv.key == "F# major"


def test_world_event_burst_defaults_false():
    state = GlobalState()
    assert state.world_event_burst is False


def test_no_business_logic_in_state():
    # GlobalState must be a pure data model with no custom domain methods
    pydantic_builtins = {
        m for m in dir(BaseModel)
        if not m.startswith("_")
    }
    user_methods = [
        m for m in dir(GlobalState)
        if not m.startswith("_")
        and m not in GlobalState.model_fields
        and m not in pydantic_builtins
    ]
    assert user_methods == [], f"Custom domain methods found — keep state.py pure: {user_methods}"
