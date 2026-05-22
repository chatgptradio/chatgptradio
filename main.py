import asyncio
import os
import signal
import sys
from pathlib import Path as _PathType

import structlog
from aiohttp import web
from dotenv import load_dotenv

from core.audio_queue import run_audio_queue
from core.calendar_engine import build_event_list, run_calendar
from core.scene_rotator import run_scene_rotator
from core.collector_runner import start_all_collectors
from core.command_engine import CommandEngine
from core.config import load_config
from core.db import init_db
from core.dsp import run_dsp
from core.journal import run_journal
from core.memory import restore_self_model
from core.state import GlobalState
from core.updater import StateUpdater
from core.browser_display import run_browser_display
from core.websocket_server import start_websocket_server

load_dotenv()  # loads .env from cwd or any parent directory

log = structlog.get_logger()


def _make_overlay_app() -> web.Application:
    app = web.Application()
    app.router.add_static("/", _PathType("overlays"), show_index=True)
    return app


async def run() -> None:
    config = load_config("config.yaml")

    db_conn = await init_db(config.sqlite.path)
    state = GlobalState()

    # Restore self-model baselines from last session
    await restore_self_model(db_conn, state)

    updater = StateUpdater(state, db_conn)

    # Inject CommandEngine + db connection into the YouTube chat collector so it
    # can route !commands without breaking the standard collector protocol.
    cmd_engine = CommandEngine()
    try:
        import collectors.youtube_chat as _yt_chat

        _yt_chat.make_collector(cmd_engine, db_conn)
    except ImportError:
        pass

    collector_tasks = start_all_collectors(config, updater.queue, state)
    ws_server_task, ws_broadcast_task = await start_websocket_server(
        state, config.websocket.port, config.websocket.fps
    )
    updater_task = asyncio.create_task(updater.run())

    overlay_port = int(os.environ.get("OVERLAY_HTTP_PORT", "8080"))
    overlay_app = _make_overlay_app()
    overlay_runner = web.AppRunner(overlay_app)
    await overlay_runner.setup()
    overlay_site = web.TCPSite(overlay_runner, "localhost", overlay_port)
    await overlay_site.start()
    log.info("overlay_http_started", port=overlay_port)

    browser_ready = asyncio.Event()
    browser_task = asyncio.create_task(run_browser_display(browser_ready))

    playback_queue: asyncio.Queue[_PathType] = asyncio.Queue(maxsize=4)
    audio_task = asyncio.create_task(run_audio_queue(state, updater.queue, db_conn, playback_queue, cmd_engine=cmd_engine))
    dsp_task = asyncio.create_task(run_dsp(state, playback_queue, updater.queue, conn=db_conn, browser_ready=browser_ready))
    journal_task = asyncio.create_task(run_journal(state, updater.queue, db_conn))
    events = build_event_list(config.calendar)
    calendar_task = asyncio.create_task(run_calendar(state, updater.queue, events))
    scene_task = asyncio.create_task(run_scene_rotator(state, updater.queue))

    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    log.info(
        "chatgpt_radio_started",
        port=config.websocket.port,
        fps=config.websocket.fps,
        collectors=[c.name for c in config.collectors],
    )

    await shutdown_event.wait()

    log.info("chatgpt_radio_shutdown_started")

    all_tasks = collector_tasks + [ws_server_task, ws_broadcast_task, updater_task, audio_task, dsp_task, journal_task, calendar_task, scene_task, browser_task]
    for task in all_tasks:
        task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*all_tasks, return_exceptions=True),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        log.warning("shutdown_timeout", note="some tasks did not cancel in 10s")

    await overlay_runner.cleanup()
    await db_conn.close()
    log.info("chatgpt_radio_shutdown_complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
