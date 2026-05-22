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


def test_territory_ambient():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="ambient")
    result = bmp(state)
    assert "ambient" in result


def test_territory_electronic():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="electronic")
    result = bmp(state)
    assert "electronic" in result


def test_territory_jazz():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="jazz")
    result = bmp(state)
    assert "jazz" in result


def test_territory_industrial():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="industrial")
    result = bmp(state)
    assert "industrial" in result


def test_territory_neoclassical():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="neoclassical")
    result = bmp(state)
    assert "neoclassical" in result


def test_territory_experimental():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="experimental")
    result = bmp(state)
    assert "experimental" in result


def test_territory_drone():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="drone")
    result = bmp(state)
    assert "drone" in result


def test_territory_lo_fi():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="lo-fi")
    result = bmp(state)
    assert "lo-fi hip hop" in result


def test_territory_cinematic():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="cinematic")
    result = bmp(state)
    assert "cinematic" in result


def test_territory_darkwave():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="darkwave")
    result = bmp(state)
    assert "darkwave" in result


def test_territory_techno():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="techno")
    result = bmp(state)
    assert "techno" in result


def test_territory_psych():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="psych")
    result = bmp(state)
    assert "psychedelic" in result


def test_territory_noise():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="noise")
    result = bmp(state)
    assert "noise" in result


def test_territory_minimalist():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="minimalist")
    result = bmp(state)
    assert "minimalist" in result


def test_territory_blues():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState(drift_territory="blues")
    result = bmp(state)
    assert "blues" in result


def test_prompt_contains_drift_timbre():
    from builders.music_prompt import build_music_prompt as bmp
    for timbre in ("warm", "organic", "digital", "cold", "metallic"):
        state = GlobalState(drift_timbre=timbre)
        result = bmp(state)
        assert timbre in result, f"drift_timbre '{timbre}' not found in prompt: {result}"


def test_prompt_contains_high_quality_suffix():
    from builders.music_prompt import build_music_prompt as bmp
    state = GlobalState()
    result = bmp(state)
    assert "high quality" in result, f"'high quality' not found in prompt: {result}"
    assert "AI ambient electronic music" in result, f"suffix not found in prompt: {result}"


def test_all_15_territories_no_fallback():
    from builders.music_prompt import build_music_prompt as bmp
    territories = [
        "ambient", "electronic", "jazz", "industrial", "neoclassical",
        "experimental", "drone", "lo-fi", "cinematic", "darkwave",
        "techno", "psych", "noise", "minimalist", "blues",
    ]
    fallback_genre = "ambient electronic"
    for territory in territories:
        state = GlobalState(drift_territory=territory)
        result = bmp(state)
        if territory != "ambient":
            # The fallback genre only appears at the start of the prompt.
            # The fixed suffix now contains "AI ambient electronic music" for
            # all territories, so we check the prompt prefix specifically.
            assert not result.startswith(fallback_genre), (
                f"Territory '{territory}' fell back to default 'ambient electronic': {result}"
            )
