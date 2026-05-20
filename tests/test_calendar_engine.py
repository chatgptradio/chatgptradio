"""Tests for core/calendar_engine.py — CalendarEngine issue #63."""
import asyncio
from datetime import date
from unittest.mock import patch

import pytest

from core.calendar_engine import (
    EVENTS,
    CalendarEvent,
    build_event_list,
    compute_event_intensity,
    get_active_events,
    run_calendar,
)
from core.state import GlobalState


# ── helpers ──────────────────────────────────────────────────────────────────

def event_by_name(name: str) -> CalendarEvent:
    return next(e for e in EVENTS if e.name == name)


# ── 1. Peak intensity on day J ────────────────────────────────────────────────

def test_intensity_peak_on_event_day():
    evt = event_by_name("chatgpt_birthday")  # nov 30, max=1.0
    assert compute_event_intensity(evt, date(2026, 11, 30)) == pytest.approx(1.0)


# ── 2. Zero outside ramp window ───────────────────────────────────────────────

def test_intensity_zero_outside_ramp():
    evt = event_by_name("chatgpt_birthday")  # ramp_days=3
    assert compute_event_intensity(evt, date(2026, 11, 26)) == pytest.approx(0.0)
    assert compute_event_intensity(evt, date(2026, 12, 4)) == pytest.approx(0.0)


# ── 3. Ramp before event (J-1) ────────────────────────────────────────────────

def test_intensity_ramp_day_before():
    evt = CalendarEvent("test_evt", "Test", 6, 15, 1.0, 2)
    # J-1 → 1.0 * (1 - 1/3) = 2/3
    result = compute_event_intensity(evt, date(2026, 6, 14))
    assert result == pytest.approx(2 / 3)


# ── 4. Ramp after event (J+1) ─────────────────────────────────────────────────

def test_intensity_ramp_day_after():
    evt = CalendarEvent("test_evt", "Test", 6, 15, 1.0, 2)
    # J+1 → same as J-1 by symmetry
    result = compute_event_intensity(evt, date(2026, 6, 16))
    assert result == pytest.approx(2 / 3)


# ── 5. Nov 30 double event: chatgpt_birthday + alphafold2 both active ─────────

def test_nov30_double_event():
    today = date(2026, 11, 30)
    active_names = {e.name for e in get_active_events(EVENTS, today)}
    assert "chatgpt_birthday" in active_names
    assert "alphafold2" in active_names


# ── 6. Inactive day returns empty list ────────────────────────────────────────

def test_inactive_day_returns_empty():
    # July 4 has no event defined
    active = get_active_events(EVENTS, date(2026, 7, 4))
    assert active == []


# ── 7. Variable events are included in build_event_list ───────────────────────

def test_variable_events_included():
    from core.config import CalendarConfig, VariableEvent

    cfg = CalendarConfig(
        variable_events=[
            VariableEvent(name="test_conf", label="Test Conf", date="2026-07-10"),
        ]
    )
    events = build_event_list(cfg)
    names = [e.name for e in events]
    assert "test_conf" in names
    assert len(events) == len(EVENTS) + 1


# ── 8. run_calendar puts active event on queue ────────────────────────────────

@pytest.mark.asyncio
async def test_run_calendar_puts_active_event():
    state = GlobalState()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    # Use an event that is definitely active on a specific date
    events = [CalendarEvent("test_now", "Test Now", 1, 1, 0.9, 2)]

    with patch("core.calendar_engine.date") as mock_date:
        mock_date.today.return_value = date(2026, 1, 1)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        task = asyncio.create_task(run_calendar(state, queue, events, check_interval_s=9999))
        # Let one iteration run
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert not queue.empty()
    item = await queue.get()
    assert item["active_event"] == "test_now"
    assert item["event_intensity"] == pytest.approx(0.9)


# ── 9. run_calendar resets state when no active event ─────────────────────────

@pytest.mark.asyncio
async def test_run_calendar_resets_when_no_active_event():
    state = GlobalState(active_event="old_event")
    queue: asyncio.Queue[dict] = asyncio.Queue()

    # No events → no active event possible
    events: list[CalendarEvent] = []

    with patch("core.calendar_engine.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 4)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        task = asyncio.create_task(run_calendar(state, queue, events, check_interval_s=9999))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert not queue.empty()
    item = await queue.get()
    assert item["active_event"] == ""
    assert item["event_intensity"] == pytest.approx(0.0)
