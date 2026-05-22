"""Hedonometer happiness collector.

Fetches the latest English daily happiness score from hedonometer.org
and normalises from [5.0, 7.0] → [0, 1].  The historical average is ~6.0,
so neutral maps to 0.5.
"""

from typing import Any

import orjson

from collectors.utils import fetch_text, normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "hedonometer", "interval_s": 21600}

_URL = "https://hedonometer.org/api/v1/happiness/?lang=en&format=json&limit=1"
_SCORE_LOW = 5.0
_SCORE_HIGH = 7.0


def _parse_happiness(text: str) -> float:
    data = orjson.loads(text)
    objects = data.get("objects", [])
    if not objects:
        return 0.5  # neutral default when no data
    score = float(objects[0].get("happiness", 6.0))
    return normalize(score, _SCORE_LOW, _SCORE_HIGH)


@node(
    name="hedonometer",
    produces="hedonometer_happiness",
    color="#F39C12",
    label="Hedonometer Happiness",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    text = await fetch_text(_URL, timeout_s=15.0)
    return {"hedonometer_happiness": _parse_happiness(text)}
