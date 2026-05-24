"""Chat command handler — parses !commands from YouTube Live Chat."""

from __future__ import annotations

import asyncio
import os

import aiosqlite
import openai
import structlog

from core.audio_library import find_by_display_name
from core.command_engine import CommandEngine, VALID_GENRES
from core.scene_rotator import SCENE_CYCLE
from core.state import GlobalState

log = structlog.get_logger()

_mood_client: openai.AsyncOpenAI | None = None

def _get_mood_client() -> openai.AsyncOpenAI:
    global _mood_client
    if _mood_client is None:
        _mood_client = openai.AsyncOpenAI()
    return _mood_client

_MOOD_SYSTEM_DEFAULT = (
    "You are an AI radio entity responding in live stream chat. "
    "Write exactly one sentence, maximum 12 words. "
    "First person. Honest and direct. Reflect the actual numbers. No emojis. No quotes."
)

_MOOD_SYSTEM_STRESS = (
    "You are an AI radio entity under high signal stress. "
    "Write exactly one sentence, maximum 12 words. "
    "First person. Terse, unstable. Reflect the actual numbers. No emojis. No quotes."
)

_MOOD_SYSTEM_PEAK = (
    "You are an AI radio entity at peak signal clarity. "
    "Write exactly one sentence, maximum 12 words. "
    "First person. Sharp, energized. Reflect the actual numbers. No emojis. No quotes."
)


def _get_mood_system(dominant: str, sigma: float) -> str:
    if dominant in ("anxiety", "frustration") and sigma > 2.0:
        return _MOOD_SYSTEM_STRESS
    if dominant in ("excitement", "curiosity") and sigma > 2.0:
        return _MOOD_SYSTEM_PEAK
    return _MOOD_SYSTEM_DEFAULT

async def _mood_gpt(state: GlobalState, dominant: str, sigma: float) -> str | None:
    if not os.environ.get("OPENAI_API_KEY"):
        log.warning("mood_gpt_skipped", reason="no OPENAI_API_KEY")
        return None
    pe = state.prediction_errors
    top3 = sorted(
        ((k, v) for k, v in pe.items() if k not in _MOOD_EXCLUDE),
        key=lambda kv: abs(kv[1]), reverse=True
    )[:3]
    user_msg = (
        f"dominant: {dominant} ({sigma:.1f}σ), "
        f"territory: {state.drift_territory}, crisis: {state.crisis_level:.2f}, "
        f"signals: {', '.join(f'{k}={v:+.3f}' for k, v in top3)}"
    )
    log.info("mood_gpt_call", dominant=dominant, sigma=round(sigma, 2))
    try:
        resp = await _get_mood_client().chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=30,
            messages=[
                {"role": "system", "content": _get_mood_system(dominant, sigma)},
                {"role": "user", "content": user_msg},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        log.info("mood_gpt_response", text=text)
        return text if text else None
    except Exception as exc:
        log.warning("mood_gpt_error", error=str(exc))
        return None

_LABEL_TTL_S: float = 15.0

# Fields that are counters or operational metrics — not meaningful as mood signals
_MOOD_EXCLUDE: frozenset[str] = frozenset({
    "songs_played_today", "songs_played_total", "current_song_progress",
    "queue_length", "viewers", "chat_rate", "uptime_h", "stream_bitrate",
    "dropped_frames", "drift_bpm", "drift_velocity", "drift_energy",
})


async def _clear_viewer_cmd(state_queue: asyncio.Queue, delay: float) -> None:  # type: ignore[type-arg]
    await asyncio.sleep(delay)
    await state_queue.put({"viewer_cmd_label": ""})


async def handle_command(
    raw: str,
    author_name: str,
    state: GlobalState,
    cmd_engine: CommandEngine,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
    conn: aiosqlite.Connection,
) -> str | None:
    """Parse *raw* chat message. Returns a log string or None."""
    parts = raw.strip().split(maxsplit=1)
    if not parts:
        return None
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    user = author_name or "viewer"

    def _show(label: str) -> None:
        state_queue.put_nowait({"viewer_cmd_label": f"{user} · {label}"})
        asyncio.create_task(_clear_viewer_cmd(state_queue, _LABEL_TTL_S))

    # ── !mood ─────────────────────────────────────────────────────────────────
    if cmd == "!mood":
        remaining = cmd_engine.cooldown_remaining("mood")
        if remaining > 0:
            return f"!mood cooldown {remaining:.0f}s"
        if not cmd_engine.try_mood():
            return None
        pe = {k: v for k, v in state.prediction_errors.items() if k not in _MOOD_EXCLUDE}
        vol = state.signal_volatilities
        if not pe:
            return None
        dominant = max(pe, key=pe.__getitem__)
        s = pe[dominant] / max(vol.get(dominant, 0.1), 0.01)
        mood_str = f"mood: {dominant} ({s:.1f}σ)"
        _show(mood_str)
        gpt_response = await _mood_gpt(state, dominant, s)
        if gpt_response:
            _show(gpt_response)
        return gpt_response if gpt_response else mood_str

    # ── !request ──────────────────────────────────────────────────────────────
    if cmd == "!request":
        arg = arg.lower()
        if not arg or arg not in VALID_GENRES:
            return f"!request unknown genre: {arg!r}"
        remaining = cmd_engine.cooldown_remaining("request", arg)
        if remaining > 0:
            return f"!request cooldown {remaining:.0f}s for {arg}"
        cmd_engine.try_request(arg)
        cmd_engine.push("request", arg)
        _show(f"request · {arg}")
        return f"!request {arg} accepted"

    # ── !switch ───────────────────────────────────────────────────────────────
    if cmd == "!switch":
        if not cmd_engine.try_switch():
            remaining = cmd_engine.cooldown_remaining("switch")
            return f"!switch cooldown {remaining:.0f}s"
        if arg and arg in SCENE_CYCLE:
            next_mode = arg
        else:
            current = state.visual_mode if state.visual_mode in SCENE_CYCLE else SCENE_CYCLE[0]
            next_mode = SCENE_CYCLE[(SCENE_CYCLE.index(current) + 1) % len(SCENE_CYCLE)]
        await state_queue.put({"visual_mode": next_mode})
        _show(f"switch · {next_mode}")
        return f"!switch → {next_mode}"

    # ── !replay ───────────────────────────────────────────────────────────────
    if cmd == "!replay":
        if not arg:
            return "!replay missing arg"
        remaining = cmd_engine.cooldown_remaining("replay")
        if remaining > 0:
            return f"!replay cooldown {remaining:.0f}s"
        result = await find_by_display_name(conn, arg)
        if result is None:
            return f"!replay not found: {arg!r}"
        if not cmd_engine.try_replay():
            return None
        path, name = result
        cmd_engine.push("replay", str(path))
        _show(f"replay · {name}")
        return f"!replay queued: {name}"

    return None
