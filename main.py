import asyncio
import signal
import sys

import structlog

from core.collector_runner import start_all_collectors
from core.config import load_config
from core.db import init_db
from core.state import GlobalState
from core.updater import StateUpdater
from core.websocket_server import start_websocket_server

log = structlog.get_logger()


async def run() -> None:
    config = load_config("config.yaml")

    db_conn = await init_db(config.sqlite.path)
    state = GlobalState()

    updater = StateUpdater(state, db_conn)
    collector_tasks = start_all_collectors(config, updater.queue, state)
    ws_server_task, ws_broadcast_task = await start_websocket_server(
        state, config.websocket.port, config.websocket.fps
    )
    updater_task = asyncio.create_task(updater.run())

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

    all_tasks = collector_tasks + [ws_server_task, ws_broadcast_task, updater_task]
    for task in all_tasks:
        task.cancel()
    await asyncio.gather(*all_tasks, return_exceptions=True)

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
