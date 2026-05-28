"""Unit tests for telegram_bot.py — allowlist, handlers, debounce, alerts."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Provide minimal env vars so the module-level code doesn't raise on import
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake-token-for-tests")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")


# ---------------------------------------------------------------------------
# Test 1 — Allowlist: chat_id non autorisé → handler ignoré
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allowlist_rejects_unknown_chat_id():
    """Messages from non-allowlisted chat_ids must be silently ignored."""
    import telegram_bot as tb

    update = MagicMock()
    update.effective_chat.id = tb.CHAT_ID + 1  # wrong ID
    update.message = AsyncMock()
    context = MagicMock()

    result = await tb._allowlist_filter(update, context)

    assert result is None
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_allowlist_passes_correct_chat_id():
    """Handler must not return early for the authorised chat_id."""
    import telegram_bot as tb

    update = MagicMock()
    update.effective_chat.id = tb.CHAT_ID
    update.message = AsyncMock()
    context = MagicMock()

    # No assertion needed beyond "does not raise"; function returns None normally
    result = await tb._allowlist_filter(update, context)
    assert result is None


# ---------------------------------------------------------------------------
# Test 2 — /status with populated _state_cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_status_with_cache(monkeypatch):
    """Status reply includes uptime, bitrate, and dropped frames from cache."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "_state_cache", {
        "uptime_h": 3.5,
        "stream_bitrate": 4500.0,
        "dropped_frames": 2.0,
    })

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"active\n", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        update = MagicMock()
        update.message = AsyncMock()
        await tb.cmd_status(update, MagicMock())

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "3.5" in text
    assert "4500" in text


# ---------------------------------------------------------------------------
# Test 3 — /status with empty _state_cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_status_no_cache(monkeypatch):
    """When _state_cache is empty, reply must mention WebSocket unavailable."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "_state_cache", {})

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"inactive\n", b""))

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        update = MagicMock()
        update.message = AsyncMock()
        await tb.cmd_status(update, MagicMock())

    text = update.message.reply_text.call_args[0][0]
    assert "indisponible" in text.lower()


# ---------------------------------------------------------------------------
# Test 4 — /restart uses create_subprocess_exec without shell=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_restart_no_shell_true(monkeypatch, tmp_path):
    """restart must invoke bash explicitly and never use shell=True."""
    import telegram_bot as tb

    log_file = tmp_path / "stream_restart.log"
    log_file.write_text("line1\nline2\nline3\n")
    monkeypatch.setattr(tb, "RESTART_LOG", str(log_file))

    mock_proc = AsyncMock()
    mock_proc.wait = AsyncMock(return_value=0)

    captured_args: list = []
    captured_kwargs: list = []

    async def fake_exec(*args, **kwargs):
        captured_args.extend(args)
        captured_kwargs.append(kwargs)
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        update = MagicMock()
        update.message = AsyncMock()
        await tb.cmd_restart(update, MagicMock())

    # Must NOT use shell=True
    assert "shell" not in captured_kwargs[0] or captured_kwargs[0].get("shell") is not True
    # Must call bash explicitly
    assert captured_args[0] == "bash"


@pytest.mark.asyncio
async def test_cmd_restart_log_not_found(monkeypatch, tmp_path):
    """restart handles a missing log file gracefully."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "RESTART_LOG", str(tmp_path / "nonexistent.log"))

    mock_proc = AsyncMock()
    mock_proc.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        update = MagicMock()
        update.message = AsyncMock()
        await tb.cmd_restart(update, MagicMock())

    # Second reply should mention that the log is unavailable
    second_call_text = update.message.reply_text.call_args_list[1][0][0]
    assert "introuvable" in second_call_text


# ---------------------------------------------------------------------------
# Test 5 — Debounce: DOWN alert sent only once after 30 s
# ---------------------------------------------------------------------------

def _make_failing_ws_context(exc: Exception):
    """Return an async context manager whose __aenter__ raises exc."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=exc)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_watch_websocket_debounce(monkeypatch):
    """DOWN alert sent only once after 30s debounce, not on first disconnect."""
    import telegram_bot as tb

    sleep_call_count = [0]

    # asyncio.sleep: raise CancelledError on 3rd call to stop the loop
    async def fake_sleep(delay):
        sleep_call_count[0] += 1
        if sleep_call_count[0] >= 3:
            raise asyncio.CancelledError()

    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot

    # time.monotonic: first call (sets down_since) → 0.0, rest → 31.0
    call_count = [0]

    def fake_monotonic():
        call_count[0] += 1
        return 0.0 if call_count[0] == 1 else 31.0

    # websockets.connect always fails with ConnectionRefusedError
    def fake_connect(url):
        return _make_failing_ws_context(ConnectionRefusedError("refused"))

    with (
        patch("websockets.connect", side_effect=fake_connect),
        patch("time.monotonic", side_effect=fake_monotonic),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            await tb.watch_websocket(mock_app)

    down_calls = [
        c for c in mock_bot.send_message.call_args_list
        if "DOWN" in str(c)
    ]
    assert len(down_calls) == 1


@pytest.mark.asyncio
async def test_watch_websocket_no_alert_before_debounce(monkeypatch):
    """No DOWN alert sent while elapsed time is below the debounce threshold."""
    import telegram_bot as tb

    sleep_call_count = [0]

    async def fake_sleep(delay):
        sleep_call_count[0] += 1
        if sleep_call_count[0] >= 3:
            raise asyncio.CancelledError()

    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot

    # Always return a time below the debounce threshold
    def fake_monotonic_early():
        return 5.0  # well under _DOWN_DEBOUNCE_S = 30.0

    def fake_connect(url):
        return _make_failing_ws_context(ConnectionRefusedError("refused"))

    with (
        patch("websockets.connect", side_effect=fake_connect),
        patch("time.monotonic", side_effect=fake_monotonic_early),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            await tb.watch_websocket(mock_app)

    down_calls = [
        c for c in mock_bot.send_message.call_args_list
        if "DOWN" in str(c)
    ]
    assert len(down_calls) == 0


# ---------------------------------------------------------------------------
# Test 6 — /health displays collector OK/KO status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_health_shows_collectors(monkeypatch):
    """Health reply must show ✅/❌ per collector and list all collector names."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "_state_cache", {
        "cpu_percent": 45.2,
        "memory_percent": 62.0,
        "source_health": {
            "openai_status": True,
            "reddit": False,
            "wikipedia": True,
        },
    })

    update = MagicMock()
    update.message = AsyncMock()
    await tb.cmd_health(update, MagicMock())

    text = update.message.reply_text.call_args[0][0]
    assert "✅" in text
    assert "❌" in text
    assert "reddit" in text


@pytest.mark.asyncio
async def test_cmd_health_no_cache(monkeypatch):
    """Health reply mentions WebSocket unavailable when cache is empty."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "_state_cache", {})

    update = MagicMock()
    update.message = AsyncMock()
    await tb.cmd_health(update, MagicMock())

    text = update.message.reply_text.call_args[0][0]
    assert "indisponible" in text.lower()


# ---------------------------------------------------------------------------
# Test 7 — /ping returns pong
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_ping_returns_pong():
    """ping must reply with 'pong'."""
    import telegram_bot as tb

    update = MagicMock()
    update.message = AsyncMock()
    await tb.cmd_ping(update, MagicMock())

    update.message.reply_text.assert_called_once_with("pong")


# ---------------------------------------------------------------------------
# Test 8 — /music with populated cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_music_with_cache(monkeypatch):
    """Music reply includes track name, territory, BPM and energy."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "_state_cache", {
        "current_track_name": "Midnight Drift",
        "drift_territory": "deep_focus",
        "drift_bpm": 92.0,
        "drift_energy": 0.73,
    })

    update = MagicMock()
    update.message = AsyncMock()
    await tb.cmd_music(update, MagicMock())

    text = update.message.reply_text.call_args[0][0]
    assert "Midnight Drift" in text
    assert "deep_focus" in text
    assert "92" in text


# ---------------------------------------------------------------------------
# Test 9 — /viewers with populated cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cmd_viewers_with_cache(monkeypatch):
    """Viewers reply includes viewer count, peak, and chat rate."""
    import telegram_bot as tb

    monkeypatch.setattr(tb, "_state_cache", {
        "viewers": 154,
        "viewers_peak_today": 312,
        "chat_rate": 7.5,
    })

    update = MagicMock()
    update.message = AsyncMock()
    await tb.cmd_viewers(update, MagicMock())

    text = update.message.reply_text.call_args[0][0]
    assert "154" in text
    assert "312" in text
    assert "7.5" in text
