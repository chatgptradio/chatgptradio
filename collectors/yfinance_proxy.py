"""yfinance collector — MSFT and NVDA daily price deltas.

Uses yfinance's fast_info (synchronous) to read current_price and
previous_close, computes the fractional delta, clamps to [-0.1, +0.1],
then normalises to [0, 1] where 0 = -10%, 0.5 = flat, 1 = +10%.

The synchronous yfinance call is dispatched via run_in_executor to avoid
blocking the event loop.
"""

import asyncio
from typing import Any

import yfinance as yf

from collectors.utils import normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "yfinance_proxy", "interval_s": 14400}

_DELTA_LOW = -0.1
_DELTA_HIGH = 0.1


def _get_delta(ticker: str) -> float:
    info = yf.Ticker(ticker).fast_info
    current = info.get("lastPrice") or info.get("last_price")
    prev = info.get("previousClose") or info.get("previous_close")
    if current is None or prev is None or prev == 0:
        return 0.0
    return (current - prev) / prev


def _normalise_delta(delta: float) -> float:
    return normalize(delta, _DELTA_LOW, _DELTA_HIGH)


@node(
    name="yfinance_proxy",
    produces="msft_delta",
    color="#00A4EF",
    label="yfinance MSFT/NVDA",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    msft_delta = await loop.run_in_executor(None, lambda: _get_delta("MSFT"))
    nvda_delta = await loop.run_in_executor(None, lambda: _get_delta("NVDA"))
    return {
        "msft_delta": _normalise_delta(msft_delta),
        "nvda_delta": _normalise_delta(nvda_delta),
    }
