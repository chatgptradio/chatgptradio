import asyncio
import os
import time
from typing import Callable

import orjson
import websockets
from websockets.asyncio.server import ServerConnection

from core.node import get_registry
from core.state import GlobalState

_connected: set[ServerConnection] = set()
_RESTART_FLAG = "/tmp/stream_restarting"


async def _connection_handler(ws: ServerConnection) -> None:
    _connected.add(ws)
    try:
        async for _ in ws:
            pass
    except Exception:
        pass
    finally:
        _connected.discard(ws)


async def broadcast_loop(
    state: GlobalState,
    registry_fn: Callable[[], list],
    connected: set,
    fps: int,
) -> None:
    interval = 1.0 / fps
    while True:
        if connected:
            restarting = os.path.exists(_RESTART_FLAG)
            if restarting:
                try:
                    os.unlink(_RESTART_FLAG)
                except OSError:
                    pass
            payload = orjson.dumps(
                {
                    "state": state.model_dump(mode="json"),
                    "nodes": registry_fn(),
                    "ts": time.time(),
                    **({"_restarting": True} if restarting else {}),
                }
            )
            await asyncio.gather(
                *[ws.send(payload.decode()) for ws in set(connected)],
                return_exceptions=True,
            )
        await asyncio.sleep(interval)


async def start_websocket_server(
    state: GlobalState,
    port: int = 8765,
    fps: int = 4,
) -> tuple[asyncio.Task, asyncio.Task]:
    server = await websockets.serve(_connection_handler, "localhost", port)

    broadcast_task = asyncio.create_task(
        broadcast_loop(state, get_registry, _connected, fps)
    )
    server_task = asyncio.create_task(_serve_forever(server))
    return server_task, broadcast_task


async def _serve_forever(server) -> None:
    async with server:
        await server.serve_forever()
