import asyncio
import os
import time

import orjson
import structlog
import websockets
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

log = structlog.get_logger()

_state_cache: dict = {}

WS_URL = "ws://localhost:8765"
_DOWN_DEBOUNCE_S = 30.0

RESTART_SCRIPT = "/home/stream/streaming/scripts/restart.sh"
RESTART_LOG = "/tmp/stream_restart.log"


async def watch_websocket(app) -> None:
    """Connects to the stream WebSocket, caches GlobalState, sends DOWN/UP alerts."""
    was_down = False
    down_since: float | None = None
    delay = 1.0

    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                delay = 1.0
                if was_down:
                    await app.bot.send_message(chat_id=CHAT_ID, text="🟢 Stream UP — reconnecté")
                    log.info("telegram_alert_up")
                    was_down = False
                    down_since = None
                async for raw in ws:
                    payload = orjson.loads(raw)
                    global _state_cache
                    _state_cache = payload.get("state", {})
        except Exception as exc:
            log.warning("websocket_disconnect", error=str(exc))
            if down_since is None:
                down_since = time.monotonic()
            elapsed = time.monotonic() - down_since
            if not was_down and elapsed >= _DOWN_DEBOUNCE_S:
                was_down = True
                await app.bot.send_message(chat_id=CHAT_ID, text="🔴 Stream DOWN — WebSocket déconnecté")
                log.info("telegram_alert_down")
            await asyncio.sleep(min(delay, 30.0))
            delay = min(delay * 2, 30.0)


async def _allowlist_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ignore silently any update not from CHAT_ID."""
    if update.effective_chat and update.effective_chat.id != CHAT_ID:
        return


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("pong")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    # systemd service status
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "--user", "is-active", "chatgpt-radio.service",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    svc_status = stdout.decode().strip()

    if not _state_cache:
        await update.message.reply_text(
            f"⚠️ WebSocket indisponible\nService: {svc_status}"
        )
        return

    lines = [
        "🟢 Stream actif" if svc_status == "active" else f"🔴 Service: {svc_status}",
        f"⏱ Uptime: {_state_cache.get('uptime_h', 0):.1f}h",
        f"🎵 Titres aujourd'hui: {_state_cache.get('songs_played_today', 0)} ({_state_cache.get('songs_played_total', 0)} total)",
        f"🌡 Température monde: {_state_cache.get('world_temperature', 0):.2f}",
        f"⚠️ Crise: {_state_cache.get('crisis_level', 0):.2f}",
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not _state_cache:
        await update.message.reply_text("⚠️ WebSocket indisponible")
        return
    lines = [
        f"🎵 {_state_cache.get('current_track_name') or '—'}",
        f"🗺 Territoire: {_state_cache.get('drift_territory', '—')}",
        f"🥁 BPM: {_state_cache.get('drift_bpm', 0):.0f}",
        f"🌡 Température: {_state_cache.get('world_temperature', 0):.2f}",
        f"😱 Crise: {_state_cache.get('crisis_level', 0):.2f}  Wonder: {_state_cache.get('wonder', 0):.2f}",
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_viewers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not _state_cache:
        await update.message.reply_text("⚠️ WebSocket indisponible")
        return
    lines = [
        f"👥 Viewers: {_state_cache.get('viewers', 0)}",
        f"📈 Pic aujourd'hui: {_state_cache.get('viewers_peak_today', 0)}",
        f"💬 Chat rate: {_state_cache.get('chat_rate', 0):.1f}/min",
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not _state_cache:
        await update.message.reply_text("⚠️ WebSocket indisponible")
        return
    source_health: dict = _state_cache.get("source_health", {})
    collector_lines = [
        f"{'✅' if ok else '❌'} {name}"
        for name, ok in sorted(source_health.items())
    ]
    lines = [
        f"🖥 CPU: {_state_cache.get('cpu_percent', 0) * 100:.1f}%",
        f"💾 Mémoire: {_state_cache.get('memory_percent', 0) * 100:.1f}%",
        "",
        "Collecteurs:",
        *collector_lines,
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("🔄 Relancement en cours...")
    proc = await asyncio.create_subprocess_exec(
        "bash", RESTART_SCRIPT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    # Return last 20 lines of restart log
    try:
        with open(RESTART_LOG) as f:
            lines = f.readlines()
        tail = "".join(lines[-20:])
    except FileNotFoundError:
        tail = "(log introuvable)"
    await update.message.reply_text(f"📋 Log:\n<pre>{tail}</pre>", parse_mode="HTML")


async def _post_init(app) -> None:
    asyncio.create_task(watch_websocket(app))


def main() -> None:
    app = ApplicationBuilder().token(TOKEN).post_init(_post_init).build()
    # Allowlist: drop updates from other chat_ids
    app.add_handler(MessageHandler(~filters.Chat(CHAT_ID), _allowlist_filter))
    app.add_handler(CommandHandler("ping",    cmd_ping,    filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("status",  cmd_status,  filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("music",   cmd_music,   filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("viewers", cmd_viewers, filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("health",  cmd_health,  filters=filters.Chat(CHAT_ID)))
    app.add_handler(CommandHandler("restart", cmd_restart, filters=filters.Chat(CHAT_ID)))
    log.info("telegram_bot_starting", chat_id=CHAT_ID)
    app.run_polling()


if __name__ == "__main__":
    main()
