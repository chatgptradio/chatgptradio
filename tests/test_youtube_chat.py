"""Unit tests for collectors/youtube_chat.py.

All network / external calls are mocked — no real YouTube API traffic.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.state import GlobalState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_module_state() -> None:
    """Reset module-level globals between tests to avoid cross-contamination."""
    import collectors.youtube_chat as yt

    yt._video_id_cache = None
    yt._chat_session = None
    yt._msg_times.clear()
    yt._engine = None
    yt._conn = None


def _make_chat_item(message: str) -> MagicMock:
    item = MagicMock()
    item.message = message
    return item


def _make_pytchat_mock(items: list[MagicMock]) -> MagicMock:
    """Build a pytchat.create() return-value mock."""

    async def _async_items():
        for it in items:
            yield it

    chat_data = MagicMock()
    chat_data.async_items = _async_items

    chat = MagicMock()
    chat.is_alive.return_value = True
    chat.get.return_value = chat_data
    return chat


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_video_id_uses_env_var(monkeypatch):
    """YOUTUBE_VIDEO_ID in env → returned immediately, no API call made."""
    _reset_module_state()

    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "abc123")
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)

    # googleapiclient must never be imported / called
    with patch.dict("sys.modules", {"googleapiclient.discovery": MagicMock()}):
        from collectors.youtube_chat import _resolve_video_id

        result = await _resolve_video_id()

    assert result == "abc123"


@pytest.mark.asyncio
async def test_collect_skipped_without_credentials(monkeypatch):
    """No YOUTUBE_VIDEO_ID, no YOUTUBE_CHANNEL_ID → collect() returns {} gracefully."""
    _reset_module_state()

    monkeypatch.delenv("YOUTUBE_VIDEO_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    from collectors.youtube_chat import collect

    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]

    # pytchat is a local import inside collect(); patch at sys.modules level.
    mock_pytchat = MagicMock()
    with patch.dict("sys.modules", {"pytchat": mock_pytchat, "pytchat.util": MagicMock()}):
        result = await collect(state, queue)

    mock_pytchat.create.assert_not_called()
    assert result == {}


@pytest.mark.asyncio
async def test_command_parsed_and_routed(monkeypatch):
    """Message '!switch chaos' → handle_command called with the right raw string."""
    _reset_module_state()

    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "vid_cmd")
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)

    import collectors.youtube_chat as yt

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    yt.make_collector(mock_engine, mock_conn)

    chat_mock = _make_pytchat_mock([_make_chat_item("!switch chaos")])
    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]

    # Both pytchat and handle_command are local imports inside collect(); patch
    # them at sys.modules level so the import-inside-function picks them up.
    mock_pytchat = MagicMock()
    mock_pytchat.create.return_value = chat_mock
    mock_handle = AsyncMock(return_value="switched")
    mock_chat_commands = MagicMock()
    mock_chat_commands.handle_command = mock_handle

    with patch.dict("sys.modules", {
        "pytchat": mock_pytchat,
        "pytchat.util": MagicMock(),
        "core.chat_commands": mock_chat_commands,
    }):
        await yt.collect(state, queue)

    mock_handle.assert_awaited_once()
    call_args = mock_handle.call_args
    assert call_args.args[0] == "!switch chaos"


@pytest.mark.asyncio
async def test_non_command_message_ignored(monkeypatch):
    """Ordinary chat message (no '!') → handle_command never called."""
    _reset_module_state()

    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "vid_plain")
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)

    import collectors.youtube_chat as yt

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    yt.make_collector(mock_engine, mock_conn)

    chat_mock = _make_pytchat_mock([_make_chat_item("hello stream!")])
    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]

    mock_pytchat = MagicMock()
    mock_pytchat.create.return_value = chat_mock
    mock_handle = AsyncMock()
    mock_chat_commands = MagicMock()
    mock_chat_commands.handle_command = mock_handle

    with patch.dict("sys.modules", {
        "pytchat": mock_pytchat,
        "pytchat.util": MagicMock(),
        "core.chat_commands": mock_chat_commands,
    }):
        await yt.collect(state, queue)

    mock_handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_rate_updated(monkeypatch):
    """10 messages in the rolling window → chat_rate > 0 in the returned dict."""
    _reset_module_state()

    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "vid_rate")
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)

    import collectors.youtube_chat as yt

    # No engine/conn so commands are silently skipped
    yt._engine = None
    yt._conn = None

    items = [_make_chat_item(f"msg {i}") for i in range(10)]
    chat_mock = _make_pytchat_mock(items)
    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]

    mock_pytchat = MagicMock()
    mock_pytchat.create.return_value = chat_mock

    with patch.dict("sys.modules", {"pytchat": mock_pytchat, "pytchat.util": MagicMock()}):
        result = await yt.collect(state, queue)

    assert "chat_rate" in result
    assert result["chat_rate"] > 0.0


@pytest.mark.asyncio
async def test_collect_returns_regulars_ratio(monkeypatch):
    """collect() must include regulars_ratio when active regulars exist."""
    import time

    _reset_module_state()

    monkeypatch.setenv("YOUTUBE_VIDEO_ID", "vid_regulars")
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    import collectors.youtube_chat as yt

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    yt.make_collector(mock_engine, mock_conn)

    # Populate msg window so len(_msg_times) > 0
    yt._msg_times.extend([time.time()] * 5)

    # Pre-set the chat session to avoid pytchat.create() call
    chat_mock = _make_pytchat_mock([])
    yt._chat_session = chat_mock

    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()  # type: ignore[type-arg]

    mock_pytchat = MagicMock()
    mock_pytchat.create.return_value = chat_mock

    with (
        patch("core.memory.get_active_regulars", new_callable=AsyncMock, return_value=["viewer1", "viewer2"]),
        patch.dict("sys.modules", {"pytchat": mock_pytchat, "pytchat.util": MagicMock()}),
    ):
        result = await yt.collect(state, queue)

    yt._chat_session = None  # cleanup
    assert "regulars_ratio" in result
    assert result["regulars_ratio"] > 0.0


def test_youtube_chat_registered_in_node_registry():
    """make_collector() must register youtube_chat in NODE_REGISTRY."""
    from unittest.mock import MagicMock

    import collectors.youtube_chat as yt
    from core.node import NODE_REGISTRY

    yt.make_collector(MagicMock(), MagicMock())
    assert "youtube_chat" in NODE_REGISTRY
