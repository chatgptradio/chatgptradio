"""Tests for Bloc 12 music prompt enrichment (issue #183).

Covers:
- Bloc 12-I: event_label in prompt gated on event_intensity > 0.3
- Bloc 12-P1: time_in_territory_h → territory maturity texture
- Bloc 12-P2: source_divergence → tonal ambiguity / polytonality
- Bloc 12-G: get_inference_steps adaptive logic
"""

import pytest
import core.node as node_module

from core.state import GlobalState


@pytest.fixture(autouse=True)
def clear_registry():
    node_module.NODE_REGISTRY.clear()
    yield
    node_module.NODE_REGISTRY.clear()


# ── Bloc 12-I: event_label ─────────────────────────────────────────────────────


def test_event_label_in_prompt_when_high_intensity():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(event_label="chatgpt_birthday", event_intensity=0.8)
    result = build_music_prompt(state)
    assert "chatgpt birthday" in result


def test_event_label_absent_when_low_intensity():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(event_label="chatgpt_birthday", event_intensity=0.1)
    result = build_music_prompt(state)
    assert "chatgpt_birthday" not in result
    assert "chatgpt birthday" not in result


def test_event_label_absent_when_empty():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(event_label="", event_intensity=0.9)
    result = build_music_prompt(state)
    assert "euphoric celebratory feel" not in result


# ── Bloc 12-P1: time_in_territory ─────────────────────────────────────────────


def test_territory_age_late_night():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(time_in_territory_h=5.0)
    result = build_music_prompt(state)
    assert "late-night depth" in result


def test_territory_age_evolved():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(time_in_territory_h=3.0)
    result = build_music_prompt(state)
    assert "evolved" in result


def test_territory_age_fresh_no_mod():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(time_in_territory_h=0.5)
    result = build_music_prompt(state)
    assert "late-night depth" not in result
    assert "evolved" not in result
    assert "mature texture" not in result


# ── Bloc 12-P2: source_divergence → tonal ambiguity ───────────────────────────


def test_tonal_atonal():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(source_divergence=0.85)
    result = build_music_prompt(state)
    assert "atonal" in result


def test_tonal_polytonal():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(source_divergence=0.65)
    result = build_music_prompt(state)
    assert "polytonality" in result


def test_tonal_stable_no_mod():
    from builders.music_prompt import build_music_prompt

    state = GlobalState(source_divergence=0.3)
    result = build_music_prompt(state)
    assert "atonal" not in result
    assert "polytonality" not in result


# ── Bloc 12-G: get_inference_steps ────────────────────────────────────────────


def test_get_inference_steps_empty_queue():
    from builders.music_prompt import get_inference_steps

    state = GlobalState(queue_length=0, cpu_percent=40.0)
    assert get_inference_steps(state) == 6


def test_get_inference_steps_healthy_low_cpu():
    from builders.music_prompt import get_inference_steps

    state = GlobalState(queue_length=3, cpu_percent=40.0)
    assert get_inference_steps(state) == 14


def test_get_inference_steps_busy_cpu():
    from builders.music_prompt import get_inference_steps

    state = GlobalState(queue_length=3, cpu_percent=80.0)
    assert get_inference_steps(state) == 8
