import pytest
import core.node as node_module

from core.state import GlobalState


@pytest.fixture(autouse=True)
def clear_registry():
    node_module.NODE_REGISTRY.clear()
    yield
    node_module.NODE_REGISTRY.clear()


def _import_fresh():
    import importlib
    import builders.music_prompt as m
    importlib.reload(m)
    return m


def test_returns_nonempty_string_for_default_state():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState()
    result = bmp(state)
    assert isinstance(result, str)
    assert len(result) > 0


def test_bpm_key_in_output():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(
        drift_bpm=110.0,
        drift_key="F# major",
        drift_territory="electronic",
    )
    result = bmp(state)
    assert "110 BPM" in result
    assert "F# major" in result


def test_crisis_modifier_present_above_0_2():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(crisis_level=0.6)
    result = bmp(state)
    assert "signal degradation" in result


def test_crisis_modifier_present_between_0_2_and_0_5():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(crisis_level=0.3)
    result = bmp(state)
    assert "slight instability" in result


def test_no_crisis_modifier_when_crisis_zero():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(crisis_level=0.0)
    result = bmp(state)
    assert "signal degradation" not in result
    assert "slight instability" not in result


def test_dominant_emotion_drives_descriptor():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState()
    state.prediction_errors = {"excitement": 1.0}
    state.signal_volatilities = {"excitement": 0.1}
    result = bmp(state)
    assert "euphoric" in result or "driving" in result or "bright" in result


def test_no_random_in_file():
    import inspect
    import builders.music_prompt as m
    src = inspect.getsource(m)
    assert "import random" not in src
    assert "random." not in src


def test_no_vocals_always_present():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState()
    result = bmp(state)
    assert "no vocals" in result


def test_genre_in_output():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="lo-fi")
    result = bmp(state)
    assert "lo-fi" in result
