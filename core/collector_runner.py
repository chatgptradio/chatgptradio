import asyncio
import importlib
import inspect
import pkgutil
from typing import Any

import structlog

import collectors as collectors_pkg
from core.config import AppConfig
from core.state import GlobalState

log = structlog.get_logger()


def _discover_collectors() -> list[Any]:
    found = []
    for info in pkgutil.iter_modules(collectors_pkg.__path__):
        try:
            mod = importlib.import_module(f"collectors.{info.name}")
            if hasattr(mod, "COLLECTOR_META") and hasattr(mod, "collect"):
                found.append(mod)
        except Exception as exc:
            log.warning("collector_import_failed", module=info.name, error=str(exc))
    return found


def _call_collector(fn: Any, state: GlobalState, queue: asyncio.Queue) -> Any:  # type: ignore[type-arg]
    """Call *fn* with ``(state, queue)`` if it accepts two positional parameters,
    otherwise fall back to the legacy single-argument ``(state,)`` signature."""
    try:
        sig = inspect.signature(fn)
        params = [
            p
            for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]
        if len(params) >= 2:
            return fn(state, queue)
    except (ValueError, TypeError):
        pass
    return fn(state)


async def run_collector(
    name: str,
    fn: Any,
    interval_s: int,
    queue: asyncio.Queue,  # type: ignore[type-arg]
    state: GlobalState,
) -> None:
    while True:
        try:
            updates: dict[str, Any] = await asyncio.wait_for(
                _call_collector(fn, state, queue), timeout=max(interval_s * 0.8, 0.05)
            )
            for signal, value in updates.items():
                await queue.put((signal, value))
            await queue.put(("source_health", {name: True}))
        except Exception as exc:
            await queue.put(("source_health", {name: False}))
            log.warning("collector_error", collector=name, error=str(exc))
        await asyncio.sleep(interval_s)


def start_all_collectors(
    config: AppConfig,
    queue: asyncio.Queue,
    state: GlobalState,
) -> list[asyncio.Task]:
    modules = _discover_collectors()
    mod_by_name = {m.COLLECTOR_META["name"]: m for m in modules}

    tasks = []
    for cfg_entry in config.collectors:
        name = cfg_entry.name
        interval_s = cfg_entry.interval_s
        mod = mod_by_name.get(name)
        if mod is None:
            log.warning("collector_not_found", name=name)
            continue
        task = asyncio.create_task(
            run_collector(name, mod.collect, interval_s, queue, state)
        )
        tasks.append(task)
    return tasks
