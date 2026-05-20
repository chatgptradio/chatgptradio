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
        await updater.enqueue("excitement", float(i) * 0.1)

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
        await updater.enqueue("excitement", v)

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.excitement == pytest.approx(0.7)


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

    await updater.enqueue("anxiety", 0.6)
    await updater.enqueue("frustration", 0.4)

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.musical_tension == pytest.approx(0.6 * 0.5 + 0.4 * 0.5)


async def test_updated_at_is_refreshed(state, db):
    original_ts = state.updated_at

    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())
    await updater.enqueue("excitement", 0.3)
    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.updated_at >= original_ts


def test_compute_derived_world_temperature():
    s = GlobalState(excitement=1.0, anxiety=0.5, frustration=0.0, curiosity=0.0, creativity=0.0)
    compute_derived(s)
    assert s.world_temperature == pytest.approx(0.3)


def test_compute_derived_crisis_level_from_openai_outage():
    s = GlobalState(openai_status=0.0)
    compute_derived(s)
    assert s.crisis_level > 0.0


def test_compute_derived_harmonic_complexity():
    s = GlobalState(curiosity=1.0, creativity=1.0)
    compute_derived(s)
    assert s.harmonic_complexity == pytest.approx(0.6 + 0.4)


def test_wonder_positive_when_curiosity_pe_high():
    s = GlobalState()
    s.prediction_errors["curiosity"] = 2.0
    s.signal_volatilities["curiosity"] = 0.1
    compute_derived(s)
    assert s.wonder > 0


def test_melancholy_positive_when_low_audience_long_territory():
    s = GlobalState()
    s.audience_energy = 0.0
    s.time_in_territory_h = 8.0
    compute_derived(s)
    assert s.melancholy > 0.5


def test_urgency_positive_when_world_event_burst():
    s = GlobalState()
    # Trigger world_event_burst via gdelt PE > 2× vol, and set a real crisis
    s.prediction_errors["gdelt_conflict_intensity"] = 1.0
    s.signal_volatilities["gdelt_conflict_intensity"] = 0.1
    s.openai_status = 0.0  # drives crisis_level via openai_crisis = 1.0
    compute_derived(s)
    assert s.urgency > 0


async def test_wonder_prediction_error_set_after_updater_cycle(db):
    s = GlobalState()
    # Seed a low curiosity baseline so that enqueueing a high value produces a real PE,
    # which in turn makes compute_derived yield wonder > 0 and register it in self-model.
    s.signal_baselines["curiosity"] = 0.0
    s.signal_volatilities["curiosity"] = 0.1
    updater = StateUpdater(s, db)
    task = asyncio.create_task(updater.run())

    # Cycle 1: curiosity = 1.0 vs baseline 0.0 → PE = 1.0 → wonder > 0 → wonder baseline set
    await updater.enqueue("curiosity", 1.0)
    await updater.queue.join()
    # Cycle 2: curiosity = 0.0 → PE negative → wonder drops → wonder PE != 0
    await updater.enqueue("curiosity", 0.0)
    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert s.prediction_errors.get("wonder", 0) != 0
