"""Tests for CommandEngine — cooldowns, push/pop, request/switch routing."""
from core.command_engine import (
    VALID_GENRES,
    CommandEngine,
    _REQUEST_COOLDOWN_S,
    _SWITCH_COOLDOWN_S,
)


def test_push_and_pop_all():
    engine = CommandEngine()
    engine.push("request", "ambient")
    engine.push("request", "jazz")
    assert engine.pop_all() == [("request", "ambient"), ("request", "jazz")]


def test_pop_all_clears_queue():
    engine = CommandEngine()
    engine.push("request", "ambient")
    engine.pop_all()
    assert engine.pop_all() == []


def test_pop_all_empty():
    assert CommandEngine().pop_all() == []


def test_push_preserves_order():
    engine = CommandEngine()
    engine.push("request", "ambient")
    engine.push("request", "jazz")
    engine.push("replay", "drone")
    result = engine.pop_all()
    assert result[0] == ("request", "ambient")
    assert result[1] == ("request", "jazz")
    assert result[2] == ("replay", "drone")


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


def test_cooldown_remaining_request_after_use():
    engine = CommandEngine()
    engine.try_request("jazz")
    remaining = engine.cooldown_remaining("request", "jazz")
    assert 0.0 < remaining <= _REQUEST_COOLDOWN_S


def test_cooldown_remaining_request_fresh_is_zero():
    assert CommandEngine().cooldown_remaining("request", "jazz") == 0.0


def test_valid_genres_is_non_empty_strings():
    assert len(VALID_GENRES) > 0
    assert all(isinstance(v, str) for v in VALID_GENRES)


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


def test_cooldown_remaining_unknown_kind_is_zero():
    assert CommandEngine().cooldown_remaining("unknown", "ambient") == 0.0
