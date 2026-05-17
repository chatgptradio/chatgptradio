import asyncio
import pytest

from core.db import init_db
from core.state import GlobalState
from core.updater import StateUpdater, compute_derived


@pytest.fixture
async def db(tmp_path):
    c = await init_db(str(tmp_path / "test.db"))
    yield c
    await c.close()


@pytest.fixture
def state():
    return GlobalState()


async def test_enqueue_5_updates_produces_5_snapshots(state, db):
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    for i in range(5):
        await updater.enqueue("excitation", float(i) * 0.1)

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    async with db.execute("SELECT COUNT(*) FROM state_snapshots") as cur:
        count = (await cur.fetchone())[0]
    assert count == 5


async def test_updates_are_applied_in_order(state, db):
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    values = [0.1, 0.2, 0.9, 0.4, 0.7]
    for v in values:
        await updater.enqueue("excitation", v)

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.excitation == pytest.approx(0.7)


async def test_dict_field_is_merged_not_replaced(state, db):
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    await updater.enqueue("source_health", {"reddit": True})
    await updater.enqueue("source_health", {"gdelt": False})

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.source_health == {"reddit": True, "gdelt": False}


async def test_derived_fields_recalculated(state, db):
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    await updater.enqueue("anxiete", 0.6)
    await updater.enqueue("frustration", 0.4)

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.musical_tension == pytest.approx(0.6 * 0.5 + 0.4 * 0.5)


async def test_updated_at_is_refreshed(state, db):
    from datetime import datetime, timezone
    original_ts = state.updated_at

    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())
    await updater.enqueue("excitation", 0.3)
    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.updated_at >= original_ts


def test_compute_derived_world_temperature():
    s = GlobalState(excitation=1.0, anxiete=0.5, frustration=0.0, curiosite=0.0, creativite=0.0)
    compute_derived(s)
    assert s.world_temperature == pytest.approx(0.3)


def test_compute_derived_crisis_level_from_openai_outage():
    s = GlobalState(openai_status=0.0)
    compute_derived(s)
    assert s.crisis_level > 0.0


def test_compute_derived_harmonic_complexity():
    s = GlobalState(curiosite=1.0, creativite=1.0)
    compute_derived(s)
    assert s.harmonic_complexity == pytest.approx(0.6 + 0.4)
