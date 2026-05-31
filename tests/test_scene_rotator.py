"""Tests for SceneRotator — SCENE_CYCLE and run_scene_rotator coroutine."""
import asyncio

import pytest

from core.scene_rotator import SCENE_CYCLE, run_scene_rotator
from core.state import GlobalState


def test_scene_cycle_order():
    assert SCENE_CYCLE == ["chaos", "globe", "network", "logo"]


def test_scene_cycle_has_four_modes():
    assert len(SCENE_CYCLE) == 4


@pytest.mark.asyncio
async def test_rotator_advances_from_chaos():
    state = GlobalState()
    state.visual_mode = "chaos"
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_scene_rotator(state, q, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "globe"


@pytest.mark.asyncio
async def test_rotator_advances_from_globe():
    state = GlobalState()
    state.visual_mode = "globe"
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_scene_rotator(state, q, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "network"


@pytest.mark.asyncio
async def test_rotator_advances_from_network():
    state = GlobalState()
    state.visual_mode = "network"
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_scene_rotator(state, q, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "logo"


@pytest.mark.asyncio
async def test_rotator_wraps_around_from_logo():
    state = GlobalState()
    state.visual_mode = "logo"
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_scene_rotator(state, q, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "chaos"


@pytest.mark.asyncio
async def test_rotator_fallback_unknown_mode_starts_from_chaos():
    state = GlobalState()
    state.visual_mode = "unknown_mode"
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_scene_rotator(state, q, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "globe"  # unknown → SCENE_CYCLE[0]="chaos" → next="globe"


@pytest.mark.asyncio
async def test_rotator_cancels_cleanly():
    state = GlobalState()
    q: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_scene_rotator(state, q, interval_s=3600))
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert task.cancelled()
