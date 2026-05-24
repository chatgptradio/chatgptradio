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

    # Emotions are now derived from PEs; use a non-emotion field for ordering test.
    values = [0.1, 0.2, 0.9, 0.4, 0.7]
    for v in values:
        await updater.enqueue("openai_latency_ms", v * 1000)

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.openai_latency_ms == pytest.approx(0.7 * 1000)


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

    # anxiety/frustration are now derived from PEs; drive them via gdelt PE.
    await updater.enqueue("prediction_errors", {"gdelt_conflict_intensity": 1.0})
    await updater.enqueue("signal_volatilities", {"gdelt_conflict_intensity": 0.05})

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # anxiety > 0 (gdelt PE driven), so musical_tension must be > 0
    assert state.musical_tension > 0.0


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
    # Emotions are now derived from PEs; inject a PE to produce non-zero world_temperature.
    s = GlobalState()
    s.prediction_errors["reddit_volume"] = 1.0
    s.signal_volatilities["reddit_volume"] = 0.1
    compute_derived(s)
    assert s.world_temperature != 0.0


def test_compute_derived_crisis_level_from_openai_outage():
    s = GlobalState(openai_status=0.0)
    compute_derived(s)
    assert s.crisis_level > 0.0


def test_compute_derived_harmonic_complexity():
    # curiosity/creativity are now derived from PEs; drive them via arxiv/github/media_cloud.
    s = GlobalState()
    s.prediction_errors["arxiv_papers_today"] = 2.0
    s.prediction_errors["github_ai_stars"] = 2.0
    s.prediction_errors["media_cloud_ai_volume"] = 2.0
    s.signal_volatilities["arxiv_papers_today"] = 0.1
    s.signal_volatilities["github_ai_stars"] = 0.1
    s.signal_volatilities["media_cloud_ai_volume"] = 0.1
    compute_derived(s)
    assert s.harmonic_complexity > 0.0


def test_wonder_positive_when_curiosity_pe_high():
    s = GlobalState()
    # Drive curiosity via arxiv PE (curiosity is synthesized, not set directly).
    # Pre-set curiosity baseline to 0 so update_self_model yields pe["curiosity"] > 0.
    s.prediction_errors["arxiv_papers_today"] = 2.0
    s.signal_volatilities["arxiv_papers_today"] = 0.1
    s.signal_baselines["curiosity"] = 0.0
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
    # Drive wonder via arxiv_papers_today PE (curiosity is synthesized, not directly settable).
    s.signal_volatilities["arxiv_papers_today"] = 0.1
    updater = StateUpdater(s, db)
    task = asyncio.create_task(updater.run())

    # Cycle 1: high arxiv PE → state.curiosity > 0 → wonder > 0 → wonder baseline established
    await updater.enqueue("prediction_errors", {"arxiv_papers_today": 2.0})
    await updater.queue.join()
    # Cycle 2: negative arxiv PE → curiosity drops → wonder drops → wonder PE != 0
    await updater.enqueue("prediction_errors", {"arxiv_papers_today": -2.0})
    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert s.prediction_errors.get("wonder", 0) != 0


async def test_dict_queue_item_single_key_updates_state(state, db):
    """Dict put directly into the queue (not via enqueue) must update state."""
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    await updater.queue.put({"journal_text": "hello"})

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.journal_text == "hello"


async def test_dict_queue_item_multi_key_updates_all_fields(state, db):
    """Multi-key dict put into the queue must update every field it contains."""
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    await updater.queue.put({"stream_bitrate": 192.0, "dropped_frames": 0.0})

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.stream_bitrate == pytest.approx(192.0)
    assert state.dropped_frames == pytest.approx(0.0)


async def test_tuple_queue_item_backward_compat(state, db):
    """Tuple payloads must still work after the dict-handling fix."""
    updater = StateUpdater(state, db)
    task = asyncio.create_task(updater.run())

    await updater.queue.put(("openai_status", 0.5))

    await updater.queue.join()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert state.openai_status == pytest.approx(0.5)
