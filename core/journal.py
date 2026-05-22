"""AI journal — in-character commentary generated from GlobalState."""

import asyncio
import hashlib
import os
import time
from datetime import datetime, timezone

import aiosqlite
import openai
import structlog

from core.memory import MemoryContext, load_memory_context, save_journal_entry
from core.state import GlobalState

log = structlog.get_logger()

_SYSTEM = """\
You are an AI entity observing its own internal state in real time. \
Generate short journal entries (1-2 sentences max) in English, \
analytical and slightly poetic, based on the provided state data. \
Strict format: [HH:MM] <observation>. \
Use precise numeric values. First person. No quotes.\
"""

_INTERVAL_DEFAULT = 300   # 5 min
_INTERVAL_CRISIS  = 90    # 1.5 min if crisis_level > 0.5
_MIN_INTERVAL     = 60    # never more frequent than 1 min


def _build_user_prompt(state: GlobalState, ctx: MemoryContext | None = None) -> str:
    pe   = state.prediction_errors
    vol  = state.signal_volatilities

    def sig(k: str) -> float:
        return abs(pe.get(k, 0.0)) / max(vol.get(k, 0.1), 0.001)

    emotions = ["excitement", "anxiety", "frustration", "curiosity", "creativity"]
    dominant = max(emotions, key=sig)
    top_errors = sorted(
        ((k, v) for k, v in pe.items()),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )[:3]

    now = datetime.now(timezone.utc)
    lines = [
        f"UTC time: {now.strftime('%H:%M')}",
        f"Drift territory: {state.drift_territory}, BPM: {state.drift_bpm:.0f}",
        f"Crisis level: {state.crisis_level:.2f}",
        f"World temperature: {state.world_temperature:.2f}",
        f"Dominant emotion: {dominant} (significance={sig(dominant):.2f})",
        f"Top prediction errors: {', '.join(f'{k}={v:+.3f}' for k, v in top_errors)}",
        f"Time in territory: {state.time_in_territory_h:.1f}h",
        f"Anomaly score: {state.anomaly_score:.3f}",
        f"Event: {state.event_label} (intensity {state.event_intensity:.2f})" if state.event_label else "Event: none",
        f"World event burst: {'YES' if state.world_event_burst else 'no'}",
        f"Urgency: {state.urgency:.2f}",
        f"Drift velocity: {state.drift_velocity:.2f}",
    ]
    detected_bpm = state.signal_baselines.get("audio_detected_bpm")
    if detected_bpm:
        lines.append(f"Detected audio BPM: {detected_bpm:.0f} (target: {state.drift_bpm:.0f})")
    if state.viewers > 0:
        lines.append(f"Viewers: {state.viewers}")

    if ctx is not None:
        if ctx.journal_entries:
            lines.append("\nPrevious entries:")
            lines.extend(ctx.journal_entries)
        if ctx.signal_trends:
            lines.append(
                "\nSignal variations (last 30 minutes):\n"
                + ", ".join(f"{k}: {v:+.2f}" for k, v in ctx.signal_trends.items())
            )
        if ctx.recognized_viewers:
            lines.append(
                "\nRegular viewers active this session:\n"
                + ", ".join(ctx.recognized_viewers)
            )

    return "\n".join(lines)


def _state_fingerprint(state: GlobalState) -> str:
    key = (
        f"{state.crisis_level:.1f}"
        f"{state.drift_territory}"
        f"{state.world_temperature:.1f}"
        f"{state.anomaly_score:.1f}"
    )
    return hashlib.md5(key.encode()).hexdigest()[:8]


async def run_journal(
    state: GlobalState,
    state_queue: asyncio.Queue,
    conn: aiosqlite.Connection,
) -> None:
    """Coroutine that generates periodic journal entries and pushes them to StateUpdater."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        log.warning("journal_disabled", reason="OPENAI_API_KEY not set")
        return

    client = openai.AsyncOpenAI(api_key=api_key)
    last_entry_ts: float = 0.0
    last_fingerprint: str = ""

    log.info("journal_started")

    while True:
        now = time.monotonic()
        crisis = state.crisis_level
        interval = _INTERVAL_CRISIS if crisis > 0.5 else _INTERVAL_DEFAULT
        elapsed = now - last_entry_ts

        fingerprint = _state_fingerprint(state)
        state_changed = fingerprint != last_fingerprint

        should_generate = (
            elapsed >= interval
            or (state_changed and elapsed >= _MIN_INTERVAL)
        )

        if should_generate:
            try:
                ctx = await load_memory_context(conn, state)
                prompt = _build_user_prompt(state, ctx)
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=120,
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                )
                entry = resp.choices[0].message.content or ""
                entry = entry.strip()
                await state_queue.put({"journal_text": entry})
                await save_journal_entry(conn, entry)
                last_entry_ts = time.monotonic()
                last_fingerprint = fingerprint
                log.info("journal_entry_generated", entry=entry)
            except Exception:
                log.exception("journal_generation_error")

        await asyncio.sleep(15)
