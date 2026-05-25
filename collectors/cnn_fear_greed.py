"""CNN Fear & Greed Index collector."""

import logging
from typing import Any

from collectors.utils import fetch_json
from core.node import node
from core.state import GlobalState

logger = logging.getLogger(__name__)

COLLECTOR_META = {"name": "cnn_fear_greed", "interval_s": 1800}

_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    "Accept": "application/json",
}


@node(
    name="cnn_fear_greed",
    produces="fear_greed_index",
    color="#CC0000",
    label="CNN Fear & Greed Index",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    data = await fetch_json(_URL, headers=_HEADERS)
    try:
        score = float(data["fear_and_greed"]["score"]) / 100.0
        return {"fear_greed_index": max(0.0, min(1.0, score))}
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("cnn_fear_greed: unexpected response shape: %s — returning {}", exc)
        return {}
