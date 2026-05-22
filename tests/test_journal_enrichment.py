"""Tests for journal enrichment and rhythmic_entropy real-signal logic (issue #182)."""

import pytest

from core.state import GlobalState
from core.updater import compute_derived
import core.journal as jmod


def _make_state(**kwargs) -> GlobalState:
    state = GlobalState()
    for k, v in kwargs.items():
        setattr(state, k, v)
    return state


# ── journal enrichment tests ────────────────────────────────────────────────


def test_build_user_prompt_includes_urgency() -> None:
    """Urgency field must appear in the prompt when set."""
    state = _make_state(urgency=0.7)
    prompt = jmod._build_user_prompt(state)
    assert "Urgency:" in prompt


def test_build_user_prompt_includes_drift_velocity() -> None:
    """Drift velocity field must appear in the prompt."""
    state = _make_state(drift_velocity=0.5)
    prompt = jmod._build_user_prompt(state)
    assert "Drift velocity:" in prompt


def test_build_user_prompt_event_label() -> None:
    """event_label appears in the prompt when set with high intensity."""
    state = _make_state(event_label="chatgpt_birthday", event_intensity=0.8)
    prompt = jmod._build_user_prompt(state)
    assert "chatgpt_birthday" in prompt


def test_build_user_prompt_no_event() -> None:
    """When event_label is empty, 'Event: none' must appear."""
    state = _make_state(event_label="")
    prompt = jmod._build_user_prompt(state)
    assert "Event: none" in prompt


# ── rhythmic_entropy tests ───────────────────────────────────────────────────


def test_rhythmic_entropy_uses_real_when_available() -> None:
    """When audio_ioi_variance is set in signal_baselines, rhythmic_entropy must use it."""
    state = _make_state(signal_baselines={"audio_ioi_variance": 0.8})
    compute_derived(state)
    assert state.rhythmic_entropy == pytest.approx(0.8)


def test_rhythmic_entropy_fallback_proxy() -> None:
    """When signal_baselines has no audio_ioi_variance, rhythmic_entropy uses proxy formula."""
    state = GlobalState()
    # Force deterministic values for frustration and crisis_level
    state.frustration = 0.4
    state.crisis_level = 0.2
    # Ensure signal_baselines does not contain audio_ioi_variance
    state.signal_baselines = {}
    # Call compute_derived — emotions will be re-synthesized but we just check
    # that when audio_ioi_variance is absent the fallback path is taken (no exception).
    compute_derived(state)
    # The proxy formula clamps to [0, 1], so the result must be in range
    assert 0.0 <= state.rhythmic_entropy <= 1.0
    # And audio_ioi_variance must NOT be in signal_baselines (unchanged by compute_derived)
    assert "audio_ioi_variance" not in state.signal_baselines
