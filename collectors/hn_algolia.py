"""Hacker News Algolia collector — AI/ChatGPT story scores.

Fetches the top 30 HN stories matching AI/ChatGPT, computes the average
points, and normalises to [0, 1] over the range 0–500 points.
"""

import json
from typing import Any

from collectors.utils import fetch_text, normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "hn_algolia", "interval_s": 300}

_URL = "https://hn.algolia.com/api/v1/search?tags=story&query=AI+ChatGPT&hitsPerPage=30"
_POINTS_LOW = 0.0
_POINTS_HIGH = 500.0


def _parse_hn(text: str) -> float:
    data = json.loads(text)
    hits = data.get("hits", [])
    if not hits:
        return 0.0
    points = [hit.get("points") or 0 for hit in hits]
    avg = sum(points) / len(points)
    return normalize(avg, _POINTS_LOW, _POINTS_HIGH)


@node(
    name="hn_algolia",
    produces="hn_ai_score",
    color="#FF6600",
    label="HN Algolia AI Score",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    text = await fetch_text(_URL, timeout_s=15.0)
    return {"hn_ai_score": _parse_hn(text)}
