import datetime
import time

import psutil
import structlog

from core.node import node
from core.state import GlobalState

log = structlog.get_logger()

COLLECTOR_META = {"name": "system_metrics", "interval_s": 60}

_start_time = time.time()


@node(
    name="system_metrics",
    produces="cpu_percent",
    color="#6B7280",
    label="System Metrics",
)
async def collect(state: GlobalState) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    mem = psutil.virtual_memory()
    return {
        "hour_utc": now.hour,
        "day_of_week": now.weekday(),
        "cpu_percent": psutil.cpu_percent(interval=None) / 100.0,
        "memory_percent": mem.percent / 100.0,
        "uptime_h": (time.time() - _start_time) / 3600.0,
    }
