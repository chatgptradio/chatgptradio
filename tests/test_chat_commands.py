"""Tests for chat_commands — handle_command dispatch and return values."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from core.chat_commands import handle_command
from core.state import GlobalState
from core.command_engine import CommandEngine


def _make_deps(track_name: str = ""):
    state = GlobalState()
    state.current_track_name = track_name
    cmd_engine = MagicMock(spec=CommandEngine)
    cmd_engine.cooldown_remaining.return_value = 0
    state_queue: asyncio.Queue = asyncio.Queue()
    conn = AsyncMock()
    return state, cmd_engine, state_queue, conn


@pytest.mark.asyncio
async def test_mood_returns_dominant_signal():
    state, eng, q, conn = _make_deps()
    state.prediction_errors = {"anxiety": 0.9}
    state.signal_volatilities = {"anxiety": 0.1}
    eng.try_mood.return_value = True
    result = await handle_command("!mood", "", state, eng, q, conn)
    assert result is not None
    assert "anxiety" in result


@pytest.mark.asyncio
async def test_mood_excludes_counter_fields():
    state, eng, q, conn = _make_deps()
    # Only counter fields — filtered out → no mood signal → returns None
    state.prediction_errors = {"songs_played_today": 5.0, "queue_length": 2.0}
    state.signal_volatilities = {}
    eng.try_mood.return_value = True
    result = await handle_command("!mood", "", state, eng, q, conn)
    assert result is None


@pytest.mark.asyncio
async def test_mood_prefers_signal_over_counter():
    state, eng, q, conn = _make_deps()
    state.prediction_errors = {"songs_played_today": 99.0, "openai_incident_score": 0.5}
    state.signal_volatilities = {"openai_incident_score": 0.1}
    eng.try_mood.return_value = True
    result = await handle_command("!mood", "", state, eng, q, conn)
    assert result is not None
    assert "openai_incident_score" in result
    assert "songs_played_today" not in result


@pytest.mark.asyncio
async def test_mood_dominant_uses_absolute_value():
    """!mood must report the emotion with the highest absolute PE, not just positive."""
    state, eng, q, conn = _make_deps()
    # anxiety PE = -5.0 (strong negative signal), excitement PE = 0.1 (weak positive)
    # Without abs fix: dominant = "excitement" (0.1 > -5.0 numerically)
    # With abs fix: dominant = "anxiety" (abs(-5.0)=5.0 > abs(0.1)=0.1)
    state.prediction_errors = {"anxiety": -5.0, "excitement": 0.1}
    state.signal_volatilities = {"anxiety": 0.1, "excitement": 0.1}
    eng.try_mood.return_value = True
    result = await handle_command("!mood", "", state, eng, q, conn)
    assert result is not None
    assert "anxiety" in result


@pytest.mark.asyncio
async def test_request_unknown_genre():
    state, eng, q, conn = _make_deps()
    result = await handle_command("!request badgenre", "", state, eng, q, conn)
    assert result is not None
    assert "unknown genre" in result


@pytest.mark.asyncio
async def test_request_valid_genre():
    state, eng, q, conn = _make_deps()
    eng.try_request.return_value = True
    result = await handle_command("!request ambient", "", state, eng, q, conn)
    assert result is not None
    assert "ambient" in result


@pytest.mark.asyncio
async def test_replay_found():
    from pathlib import Path
    state, eng, q, conn = _make_deps()
    eng.try_replay.return_value = True
    with patch("core.chat_commands.find_by_display_name", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = (Path("/fake/path.mp3"), "Void Cartographer - Cold Signal")
        result = await handle_command("!replay cold signal", "", state, eng, q, conn)
    assert result is not None
    assert "Void Cartographer - Cold Signal" in result
    eng.push.assert_called_once_with("replay", "/fake/path.mp3")


@pytest.mark.asyncio
async def test_replay_not_found():
    state, eng, q, conn = _make_deps()
    with patch("core.chat_commands.find_by_display_name", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = None
        result = await handle_command("!replay xyznotexist", "", state, eng, q, conn)
    assert result is not None
    assert "xyznotexist" in result


@pytest.mark.asyncio
async def test_replay_no_arg():
    state, eng, q, conn = _make_deps()
    result = await handle_command("!replay", "", state, eng, q, conn)
    assert result is not None
    assert "replay" in result.lower()


@pytest.mark.asyncio
async def test_switch_advances_to_next_mode():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "chaos"
    eng.try_switch.return_value = True
    result = await handle_command("!switch", "", state, eng, q, conn)
    assert result is not None
    assert "globe" in result
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "globe"


@pytest.mark.asyncio
async def test_switch_explicit_valid_mode():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "globe"
    eng.try_switch.return_value = True
    result = await handle_command("!switch chaos", "", state, eng, q, conn)
    assert result is not None
    assert "chaos" in result
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "chaos"


@pytest.mark.asyncio
async def test_switch_invalid_explicit_mode_advances():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "unknown_xyz"  # not in SCENE_CYCLE → fallback to chaos → next = globe
    eng.try_switch.return_value = True
    result = await handle_command("!switch badmode", "", state, eng, q, conn)
    assert result is not None
    assert "globe" in result


@pytest.mark.asyncio
async def test_switch_on_cooldown_returns_message():
    state, eng, q, conn = _make_deps()
    eng.try_switch.return_value = False
    eng.cooldown_remaining.return_value = 180.0
    result = await handle_command("!switch", "", state, eng, q, conn)
    assert result is not None
    assert "cooldown" in result
    assert "180" in result
    assert q.empty()


@pytest.mark.asyncio
async def test_switch_wraps_around_from_chaos():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "chaos"
    eng.try_switch.return_value = True
    result = await handle_command("!switch", "", state, eng, q, conn)
    assert result is not None
    assert "globe" in result


@pytest.mark.asyncio
async def test_switch_wraps_around_from_logo():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "logo"  # last in SCENE_CYCLE → wraps back to chaos
    eng.try_switch.return_value = True
    result = await handle_command("!switch", "", state, eng, q, conn)
    assert result is not None
    assert "chaos" in result
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "chaos"
