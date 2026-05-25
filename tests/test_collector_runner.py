import asyncio

from core.collector_runner import run_collector
from core.state import GlobalState


async def test_successful_collector_puts_updates_and_sets_health_true():
    queue: asyncio.Queue = asyncio.Queue()
    state = GlobalState()

    async def good_collect(s):
        return {"excitement": 0.7}

    task = asyncio.create_task(
        run_collector("test_ok", good_collect, interval_s=1, queue=queue, state=state)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    items = []
    while not queue.empty():
        items.append(await queue.get())

    signals = {k for k, v in items}
    assert "excitement" in signals
    assert ("source_health", {"test_ok": True}) in items


async def test_failing_collector_sets_health_false_and_continues():
    queue: asyncio.Queue = asyncio.Queue()
    state = GlobalState()
    call_count = 0

    async def bad_collect(s):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("boom")
        return {"excitement": 0.5}

    task = asyncio.create_task(
        run_collector("test_fail", bad_collect, interval_s=0, queue=queue, state=state)
    )
    await asyncio.sleep(0.15)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    items = []
    while not queue.empty():
        items.append(await queue.get())

    health_false = [v for k, v in items if k == "source_health" and v == {"test_fail": False}]
    health_true = [v for k, v in items if k == "source_health" and v == {"test_fail": True}]
    assert len(health_false) >= 1
    assert len(health_true) >= 1


async def test_collector_timeout_is_treated_as_failure():
    queue: asyncio.Queue = asyncio.Queue()
    state = GlobalState()

    async def slow_collect(s):
        await asyncio.sleep(10)
        return {}

    task = asyncio.create_task(
        run_collector("slow", slow_collect, interval_s=0, queue=queue, state=state)
    )
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    items = []
    while not queue.empty():
        items.append(await queue.get())

    health_false = [v for k, v in items if k == "source_health" and v == {"slow": False}]
    assert len(health_false) >= 1


async def test_one_collector_crash_does_not_affect_others():
    queue: asyncio.Queue = asyncio.Queue()
    state = GlobalState()

    async def crash_collect(s):
        raise RuntimeError("crash")

    async def ok_collect(s):
        return {"anxiety": 0.3}

    t1 = asyncio.create_task(
        run_collector("crasher", crash_collect, interval_s=0, queue=queue, state=state)
    )
    t2 = asyncio.create_task(
        run_collector("healthy", ok_collect, interval_s=0, queue=queue, state=state)
    )

    await asyncio.sleep(0.1)
    t1.cancel()
    t2.cancel()
    for t in [t1, t2]:
        try:
            await t
        except asyncio.CancelledError:
            pass

    items = []
    while not queue.empty():
        items.append(await queue.get())

    healthy_signals = [k for k, v in items if k == "anxiety"]
    assert len(healthy_signals) >= 1
