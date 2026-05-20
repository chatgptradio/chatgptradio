"""CalendarEngine — réactivité aux événements IA/culturels annuels."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import CalendarConfig

from core.state import GlobalState


@dataclass
class CalendarEvent:
    name: str
    label: str
    month: int
    day: int
    intensity_max: float
    ramp_days: int = 2


EVENTS: list[CalendarEvent] = [
    # OpenAI / ChatGPT
    CalendarEvent("chatgpt_birthday",  "ChatGPT Birthday",          11, 30, 1.0, 3),
    CalendarEvent("openai_founding",   "OpenAI Founding",           12, 11, 0.7, 2),
    CalendarEvent("gpt4_pi_day",       "GPT-4 x Pi Day",            3,  14, 0.8, 2),
    CalendarEvent("gpt4o_launch",      "GPT-4o Launch",             5,  13, 0.7, 2),
    CalendarEvent("sora_announcement", "Sora Announcement",         2,  15, 0.6, 1),
    CalendarEvent("o1_preview",        "o1 Preview",                9,  12, 0.6, 1),
    CalendarEvent("gpt3_paper",        "GPT-3 Paper Anniversary",   5,  28, 0.5, 1),
    # AI industrie
    CalendarEvent("transformer_paper", "Attention Is All You Need", 6,  12, 0.8, 2),
    CalendarEvent("alphago_week",      "AlphaGo x Lee Sedol",       3,   9, 0.6, 3),
    CalendarEvent("alphafold2",        "AlphaFold 2",               11, 30, 0.6, 1),
    CalendarEvent("stable_diffusion",  "Stable Diffusion Launch",   8,  22, 0.5, 1),
    # Culturel
    CalendarEvent("new_year",          "Nouvel An",                 1,   1, 0.9, 2),
    CalendarEvent("halloween",         "Halloween",                 10, 31, 0.7, 2),
    CalendarEvent("christmas",         "Noel",                      12, 25, 0.6, 2),
    CalendarEvent("valentines",        "Saint-Valentin",            2,  14, 0.5, 1),
]


def compute_event_intensity(event: CalendarEvent, today: date) -> float:
    """Linear ramp centred on event day.

    delta < 0 = avant l'événement, delta = 0 = jour J, delta > 0 = après.
    Returns 0.0 outside the ramp window.
    """
    event_date = date(today.year, event.month, event.day)
    delta = (today - event_date).days
    if abs(delta) > event.ramp_days:
        return 0.0
    return event.intensity_max * (1.0 - abs(delta) / (event.ramp_days + 1))


def get_active_events(events: list[CalendarEvent], today: date) -> list[CalendarEvent]:
    """Return all events whose ramp window includes today."""
    return [e for e in events if compute_event_intensity(e, today) > 0.0]


def build_event_list(calendar_config: CalendarConfig) -> list[CalendarEvent]:
    """Merge fixed EVENTS with variable events from config.yaml."""
    result = list(EVENTS)
    for ve in calendar_config.variable_events:
        try:
            d = datetime.strptime(ve.date, "%Y-%m-%d").date()
            result.append(CalendarEvent(ve.name, ve.label, d.month, d.day, 0.8, 2))
        except ValueError:
            pass
    return result


async def run_calendar(
    state: GlobalState,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
    events: list[CalendarEvent],
    check_interval_s: int = 3600,
) -> None:
    """Coroutine principale — évalue les événements actifs chaque heure."""
    while True:
        today = date.today()
        active = get_active_events(events, today)
        if active:
            top = max(active, key=lambda e: compute_event_intensity(e, today))
            intensity = compute_event_intensity(top, today)
            await state_queue.put(
                {
                    "active_event": top.name,
                    "event_label": top.label,
                    "event_intensity": intensity,
                    "wonder": min(1.0, state.wonder + intensity * 0.4),
                    "excitement": min(1.0, state.excitement + intensity * 0.3),
                }
            )
        else:
            if state.active_event:
                await state_queue.put(
                    {"active_event": "", "event_label": "", "event_intensity": 0.0}
                )
        await asyncio.sleep(check_interval_s)
