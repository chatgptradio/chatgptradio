"""Google Trends daily RSS collector — ChatGPT and OpenAI mentions.

Parses the US daily trending searches RSS feed, counts how many item titles
contain "chatgpt" or "openai" (case-insensitive), and normalises the counts
over 0–10 → [0, 1].
"""

import xml.etree.ElementTree as ET
from typing import Any

from collectors.utils import fetch_text, normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "google_trends", "interval_s": 900}

_URL = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
_COUNT_LOW = 0.0
_COUNT_HIGH = 10.0


def _parse_trends(text: str) -> tuple[float, float]:
    root = ET.fromstring(text)
    chatgpt_count = 0
    openai_count = 0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").lower()
        if "chatgpt" in title:
            chatgpt_count += 1
        if "openai" in title:
            openai_count += 1
    return (
        normalize(float(chatgpt_count), _COUNT_LOW, _COUNT_HIGH),
        normalize(float(openai_count), _COUNT_LOW, _COUNT_HIGH),
    )


@node(
    name="google_trends",
    produces=["google_trends_chatgpt", "google_trends_openai"],
    color="#4285F4",
    label="Google Trends AI",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    text = await fetch_text(_URL, timeout_s=20.0)
    chatgpt_score, openai_score = _parse_trends(text)
    return {
        "google_trends_chatgpt": chatgpt_score,
        "google_trends_openai": openai_score,
    }
