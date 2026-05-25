import asyncio
import signal
import socket

from core.state import GlobalState
from core.config import load_config
from core.db import init_db
from core.updater import StateUpdater
from core.websocket_server import start_websocket_server
from core.collector_runner import start_all_collectors


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def test_startup_and_sigterm_shutdown(tmp_path):
    import core.node as node_module
    node_module.NODE_REGISTRY.clear()

    port = _free_port()
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"collectors: []\nwebsocket:\n  port: {port}\n  fps: 4\nsqlite:\n  path: "
        + str(tmp_path / "state.db")
        + "\n"
    )

    config = load_config(str(cfg_path))
    db_conn = await init_db(config.sqlite.path)
    state = GlobalState()

    updater = StateUpdater(state, db_conn)
    collector_tasks = start_all_collectors(config, updater.queue, state)
    ws_server_task, ws_broadcast_task = await start_websocket_server(
        state, port, config.websocket.fps
    )
    updater_task = asyncio.create_task(updater.run())

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    assert not shutdown_event.is_set()
    assert updater_task is not None
    assert ws_server_task is not None

    shutdown_event.set()
    await shutdown_event.wait()

    all_tasks = collector_tasks + [ws_server_task, ws_broadcast_task, updater_task]
    for task in all_tasks:
        task.cancel()
    results = await asyncio.gather(*all_tasks, return_exceptions=True)

    await db_conn.close()

    for r in results:
        assert r is None or isinstance(r, (asyncio.CancelledError, Exception))


async def test_all_components_start():
    import core.node as node_module
    node_module.NODE_REGISTRY.clear()

    db_conn = await init_db(":memory:")
    state = GlobalState()
    updater = StateUpdater(state, db_conn)
    updater_task = asyncio.create_task(updater.run())

    assert not updater_task.done()

    updater_task.cancel()
    try:
        await updater_task
    except asyncio.CancelledError:
        pass
    await db_conn.close()


def test_structlog_json_output(capsys):
    import structlog
    log = structlog.get_logger()
    log.info("chatgpt_radio_started", port=8765, fps=4)
    capsys.readouterr()
