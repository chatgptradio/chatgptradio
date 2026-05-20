"""Chat command handler — parses !commands from YouTube Live Chat.

All bot response strings are in English.
"""

from __future__ import annotations

import asyncio

import aiosqlite

from core.audio_library import find_by_display_name
from core.command_engine import CommandEngine, VALID_GENRES, VALID_VIBES
from core.scene_rotator import SCENE_CYCLE
from core.state import GlobalState


async def handle_command(
    raw: str,
    state: GlobalState,
    cmd_engine: CommandEngine,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
    conn: aiosqlite.Connection,
) -> str | None:
    """Parse *raw* chat message and return a bot reply, or None to stay silent."""
    parts = raw.strip().split(maxsplit=1)
    if not parts:
        return None
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # ── !song ─────────────────────────────────────────────────────────────────
    if cmd == "!song":
        if state.current_track_name:
            return f"♪ {state.current_track_name}"
        return None

    # ── !mood ─────────────────────────────────────────────────────────────────
    if cmd == "!mood":
        pe = state.prediction_errors
        vol = state.signal_volatilities
        if not pe:
            return None
        dominant = max(pe, key=pe.__getitem__)
        s = pe[dominant] / max(vol.get(dominant, 0.1), 0.01)
        return f"◈ {dominant} ({s:.1f}σ)"

    # ── !vibe ─────────────────────────────────────────────────────────────────
    if cmd == "!vibe":
        valid = ", ".join(VALID_VIBES)
        if not arg or arg not in VALID_VIBES:
            return f"unknown mode. available: {valid}"
        remaining = cmd_engine.cooldown_remaining("vibe", arg)
        if remaining > 0:
            return f"vibe +1 for {arg} (cooldown {remaining:.0f}s)"
        idx = VALID_VIBES.index(arg)
        next_mode = VALID_VIBES[(idx + 1) % len(VALID_VIBES)]
        cmd_engine.try_vibe(arg)
        cmd_engine.push("vibe", arg)
        return f"vibe +1 → {next_mode}"

    # ── !request ──────────────────────────────────────────────────────────────
    if cmd == "!request":
        valid = ", ".join(VALID_GENRES)
        if not arg:
            return f"usage: !request <genre>. genres: {valid}"
        if arg not in VALID_GENRES:
            return f"unknown genre. available: {valid}"
        remaining = cmd_engine.cooldown_remaining("request", arg)
        if remaining > 0:
            return f"request +1 for {arg} (cooldown {remaining:.0f}s)"
        cmd_engine.try_request(arg)
        cmd_engine.push("request", arg)
        return f"request +1 for {arg}"

    # ── !switch ───────────────────────────────────────────────────────────────
    if cmd == "!switch":
        if not cmd_engine.try_switch():
            remaining = cmd_engine.cooldown_remaining("switch", "")
            return f"switch on cooldown ({remaining:.0f}s)"
        if arg and arg in SCENE_CYCLE:
            next_mode = arg
        else:
            current = state.visual_mode if state.visual_mode in SCENE_CYCLE else SCENE_CYCLE[0]
            next_mode = SCENE_CYCLE[(SCENE_CYCLE.index(current) + 1) % len(SCENE_CYCLE)]
        await state_queue.put({"visual_mode": next_mode})
        return f"◈ switching to {next_mode}"

    # ── !replay ───────────────────────────────────────────────────────────────
    if cmd == "!replay":
        if not arg:
            return "usage: !replay <track name>"
        result = await find_by_display_name(conn, arg)
        if result is None:
            return f"track not found: {arg}"
        path, name = result
        cmd_engine.push("replay", str(path))
        return f"▶ queuing {name}"

    return None
