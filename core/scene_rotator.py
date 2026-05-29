"""SceneRotator — cycles visual_mode through SCENE_CYCLE every interval_s seconds."""
from __future__ import annotations

import asyncio

from core.state import GlobalState

SCENE_CYCLE: list[str] = ["chaos", "globe", "network", "nexus", "warp"]


async def run_scene_rotator(
    state: GlobalState,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
    interval_s: int = 300,
) -> None:
    """Advance visual_mode to the next scene in SCENE_CYCLE every interval_s seconds.

    Picks up from whatever visual_mode is currently set — viewer !switch commands
    are respected because the next rotation advances from the current mode.
    """
    while True:
        await asyncio.sleep(interval_s)
        current = state.visual_mode if state.visual_mode in SCENE_CYCLE else SCENE_CYCLE[0]
        next_mode = SCENE_CYCLE[(SCENE_CYCLE.index(current) + 1) % len(SCENE_CYCLE)]
        await state_queue.put({"visual_mode": next_mode})
