"""Tests for chat_commands — English responses, !song, !replay."""
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
async def test_song_with_track_name():
    state, eng, q, conn = _make_deps(track_name="Void Cartographer - Cold Signal")
    result = await handle_command("!song", state, eng, q, conn)
    assert result == "♪ Void Cartographer - Cold Signal"


@pytest.mark.asyncio
async def test_song_no_track_name_returns_none():
    state, eng, q, conn = _make_deps(track_name="")
    result = await handle_command("!song", state, eng, q, conn)
    assert result is None


@pytest.mark.asyncio
async def test_mood_english_emotion():
    state, eng, q, conn = _make_deps()
    state.prediction_errors = {"anxiety": 0.9}
    state.signal_volatilities = {"anxiety": 0.1}
    result = await handle_command("!mood", state, eng, q, conn)
    assert result is not None
    assert "anxiety" in result


@pytest.mark.asyncio
async def test_vibe_unknown_mode_english():
    state, eng, q, conn = _make_deps()
    result = await handle_command("!vibe badmode", state, eng, q, conn)
    assert result is not None
    assert "unknown mode" in result
    assert "inconnu" not in result


@pytest.mark.asyncio
async def test_request_unknown_genre_english():
    state, eng, q, conn = _make_deps()
    result = await handle_command("!request badgenre", state, eng, q, conn)
    assert result is not None
    assert "unknown genre" in result
    assert "inconnu" not in result


@pytest.mark.asyncio
async def test_replay_found():
    from pathlib import Path
    state, eng, q, conn = _make_deps()
    with patch("core.chat_commands.find_by_display_name", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = (Path("/fake/path.mp3"), "Void Cartographer - Cold Signal")
        result = await handle_command("!replay cold signal", state, eng, q, conn)
    assert result == "▶ queuing Void Cartographer - Cold Signal"
    eng.push.assert_called_once_with("replay", "/fake/path.mp3")


@pytest.mark.asyncio
async def test_replay_not_found():
    state, eng, q, conn = _make_deps()
    with patch("core.chat_commands.find_by_display_name", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = None
        result = await handle_command("!replay xyznotexist", state, eng, q, conn)
    assert result == "track not found: xyznotexist"


@pytest.mark.asyncio
async def test_replay_no_arg():
    state, eng, q, conn = _make_deps()
    result = await handle_command("!replay", state, eng, q, conn)
    assert result == "usage: !replay <track name>"


@pytest.mark.asyncio
async def test_switch_advances_to_next_mode():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "neural"
    eng.try_switch.return_value = True
    result = await handle_command("!switch", state, eng, q, conn)
    assert result == "◈ switching to particles"
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "particles"


@pytest.mark.asyncio
async def test_switch_explicit_valid_mode():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "neural"
    eng.try_switch.return_value = True
    result = await handle_command("!switch nebula", state, eng, q, conn)
    assert result == "◈ switching to nebula"
    update = await asyncio.wait_for(q.get(), timeout=1.0)
    assert update["visual_mode"] == "nebula"


@pytest.mark.asyncio
async def test_switch_invalid_explicit_mode_advances():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "globe"
    eng.try_switch.return_value = True
    result = await handle_command("!switch badmode", state, eng, q, conn)
    assert result == "◈ switching to nebula"


@pytest.mark.asyncio
async def test_switch_on_cooldown_returns_message():
    state, eng, q, conn = _make_deps()
    eng.try_switch.return_value = False
    eng.cooldown_remaining.return_value = 180.0
    result = await handle_command("!switch", state, eng, q, conn)
    assert result is not None
    assert "cooldown" in result
    assert "180" in result
    assert q.empty()


@pytest.mark.asyncio
async def test_switch_wraps_around_from_nebula():
    state, eng, q, conn = _make_deps()
    state.visual_mode = "nebula"
    eng.try_switch.return_value = True
    result = await handle_command("!switch", state, eng, q, conn)
    assert result == "◈ switching to neural"
