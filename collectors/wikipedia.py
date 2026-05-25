"""Wikipedia pageviews collector — ChatGPT, OpenAI, GPT-4.

Uses the MediaWiki pageviews API to sum the most recent daily view counts
for the three pages, then normalises to [0, 1] over 0–50 000 views.
"""

from typing import Any

import orjson

from collectors.utils import fetch_text, normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "wikipedia", "interval_s": 900}

_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&prop=pageviews&titles=ChatGPT|OpenAI|GPT-4&format=json"
)
_VIEWS_LOW = 0.0
_VIEWS_HIGH = 50_000.0


def _parse_views(text: str) -> float:
    data = orjson.loads(text)
    pages = data.get("query", {}).get("pages", {})
    total = 0
    for page in pages.values():
        pv = page.get("pageviews") or {}
        # pageviews is a dict of date→count; take the most recent non-None value
        for count in reversed(list(pv.values())):
            if count is not None:
                total += int(count)
                break
    return normalize(float(total), _VIEWS_LOW, _VIEWS_HIGH)


@node(
    name="wikipedia",
    produces="wikipedia_views_ai",
    color="#000000",
    label="Wikipedia AI Page Views",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    text = await fetch_text(_URL, timeout_s=15.0)
    return {"wikipedia_views_ai": _parse_views(text)}
