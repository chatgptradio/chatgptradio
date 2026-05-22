"""Tests for CommandEngine — cooldowns, push/pop, vibe/request routing."""
from core.command_engine import (
    VALID_GENRES,
    CommandEngine,
    _REQUEST_COOLDOWN_S,
    _SWITCH_COOLDOWN_S,
    _VIBE_COOLDOWN_S,
)


def test_push_and_pop_all():
    engine = CommandEngine()
    engine.push("vibe", "ambient")
    engine.push("request", "jazz")
    assert engine.pop_all() == [("vibe", "ambient"), ("request", "jazz")]


def test_pop_all_clears_queue():
    engine = CommandEngine()
    engine.push("vibe", "ambient")
    engine.pop_all()
    assert engine.pop_all() == []


def test_pop_all_empty():
    assert CommandEngine().pop_all() == []


def test_try_vibe_first_call_succeeds():
    assert CommandEngine().try_vibe("ambient") is True


def test_try_vibe_immediate_retry_blocked():
    engine = CommandEngine()
    engine.try_vibe("ambient")
    assert engine.try_vibe("ambient") is False


def test_try_vibe_different_modes_are_independent():
    engine = CommandEngine()
    engine.try_vibe("ambient")
    assert engine.try_vibe("jazz") is True


def test_try_request_first_call_succeeds():
    assert CommandEngine().try_request("ambient") is True


def test_try_request_immediate_retry_blocked():
    engine = CommandEngine()
    engine.try_request("ambient")
    assert engine.try_request("ambient") is False


def test_try_request_different_genres_are_independent():
    engine = CommandEngine()
    engine.try_request("ambient")
    assert engine.try_request("jazz") is True


def test_cooldown_remaining_vibe_fresh_is_zero():
    assert CommandEngine().cooldown_remaining("vibe", "ambient") == 0.0


def test_cooldown_remaining_vibe_after_use():
    engine = CommandEngine()
    engine.try_vibe("ambient")
    remaining = engine.cooldown_remaining("vibe", "ambient")
    assert 0.0 < remaining <= _VIBE_COOLDOWN_S


def test_cooldown_remaining_request_after_use():
    engine = CommandEngine()
    engine.try_request("jazz")
    remaining = engine.cooldown_remaining("request", "jazz")
    assert 0.0 < remaining <= _REQUEST_COOLDOWN_S


def test_cooldown_remaining_unknown_kind_is_zero():
    engine = CommandEngine()
    engine.try_vibe("ambient")
    assert engine.cooldown_remaining("unknown", "ambient") == 0.0


def test_cooldown_remaining_request_fresh_is_zero():
    assert CommandEngine().cooldown_remaining("request", "jazz") == 0.0


def test_valid_genres_is_non_empty_strings():
    assert len(VALID_GENRES) > 0
    assert all(isinstance(v, str) for v in VALID_GENRES)


def test_valid_genres_non_empty_strings():
    assert len(VALID_GENRES) > 0
    assert all(isinstance(g, str) for g in VALID_GENRES)


def test_try_switch_first_call_succeeds():
    assert CommandEngine().try_switch() is True


def test_try_switch_immediate_retry_blocked():
    engine = CommandEngine()
    engine.try_switch()
    assert engine.try_switch() is False


def test_cooldown_remaining_switch_fresh_is_zero():
    assert CommandEngine().cooldown_remaining("switch", "") == 0.0


def test_cooldown_remaining_switch_after_use():
    engine = CommandEngine()
    engine.try_switch()
    remaining = engine.cooldown_remaining("switch", "")
    assert 0.0 < remaining <= _SWITCH_COOLDOWN_S


def test_push_preserves_order():
    engine = CommandEngine()
    engine.push("vibe", "ambient")
    engine.push("vibe", "jazz")
    engine.push("request", "drone")
    result = engine.pop_all()
    assert result[0] == ("vibe", "ambient")
    assert result[1] == ("vibe", "jazz")
    assert result[2] == ("request", "drone")
