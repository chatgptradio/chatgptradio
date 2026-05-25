import asyncio
import json
import pytest

from core.state import GlobalState
from core.websocket_server import broadcast_loop


TEST_PORT = 18765


async def test_broadcast_loop_sends_frames_with_state_and_nodes():
    state = GlobalState(excitement=0.42)
    connected = set()
    frames = []

    class MockWS:
        async def send(self, payload):
            frames.append(json.loads(payload))

    mock_ws = MockWS()
    connected.add(mock_ws)

    task = asyncio.create_task(
        broadcast_loop(state, lambda: [{"name": "n1"}], connected, fps=60)
    )
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(frames) >= 3
    for frame in frames[:3]:
        assert "state" in frame
        assert "nodes" in frame
        assert "ts" in frame
        assert frame["state"]["excitement"] == pytest.approx(0.42)


async def test_broadcast_loop_skips_when_no_clients():
    state = GlobalState()
    connected: set = set()
    task = asyncio.create_task(
        broadcast_loop(state, lambda: [], connected, fps=60)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # No assertion needed — just must not raise


async def test_broadcast_loop_handles_client_disconnect_gracefully():
    state = GlobalState()
    connected = set()

    class FailingWS:
        async def send(self, payload):
            raise ConnectionError("client gone")

    connected.add(FailingWS())
    task = asyncio.create_task(
        broadcast_loop(state, lambda: [], connected, fps=60)
    )
    # Must not raise; return_exceptions=True swallows the error
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_broadcast_fps_timing():
    state = GlobalState()
    connected = set()
    frame_times = []

    class TimingWS:
        async def send(self, payload):
            import time
            frame_times.append(time.monotonic())

    connected.add(TimingWS())
    target_fps = 10
    task = asyncio.create_task(
        broadcast_loop(state, lambda: [], connected, fps=target_fps)
    )
    await asyncio.sleep(0.35)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(frame_times) >= 2
    intervals = [frame_times[i+1] - frame_times[i] for i in range(len(frame_times)-1)]
    avg_interval = sum(intervals) / len(intervals)
    expected = 1.0 / target_fps
    assert abs(avg_interval - expected) < expected * 0.3
