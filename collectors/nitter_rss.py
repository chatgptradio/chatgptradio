"""Nitter RSS collector — twitter_volume + twitter_sentiment.

Tries multiple Nitter instances in order and silently returns {} if all fail,
because Nitter instances go down frequently and noise in logs is unhelpful.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from collectors.utils import fetch_text, normalize, vader_sentiment
from core.node import node
from core.state import GlobalState

logger = logging.getLogger(__name__)

COLLECTOR_META = {"name": "nitter_rss", "interval_s": 300}

_NITTER_INSTANCES = [
    "https://nitter.privacydev.net/OpenAI/rss",
    "https://nitter.poast.org/OpenAI/rss",
    "https://nitter.1d4.us/OpenAI/rss",
]

_WINDOW_S = 60 * 60  # 60 minutes
_VOLUME_MAX = 100.0


def _parse_rss(xml_text: str) -> tuple[float, float]:
    """Parse Nitter RSS XML.

    Returns:
        (twitter_volume, twitter_sentiment)
        - twitter_volume: count of items published in last 60 min, normalized [0, 1]
        - twitter_sentiment: average VADER compound of item titles in [-1, 1]
    """
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")

    now = datetime.now(timezone.utc)
    recent_titles: list[str] = []

    for item in items:
        pub_date_raw = item.findtext("pubDate") or ""
        title = item.findtext("title") or ""

        if not pub_date_raw:
            continue

        try:
            from email.utils import parsedate_to_datetime

            pub_dt = parsedate_to_datetime(pub_date_raw)
            age_s = (now - pub_dt).total_seconds()
        except Exception:
            continue

        if 0 <= age_s <= _WINDOW_S:
            recent_titles.append(title)

    count = float(len(recent_titles))
    volume = normalize(count, 0.0, _VOLUME_MAX)

    if recent_titles:
        sentiment = sum(vader_sentiment(t) for t in recent_titles) / len(recent_titles)
    else:
        sentiment = 0.0

    return volume, sentiment


@node(
    name="nitter_rss",
    produces="twitter_volume",
    color="#1DA1F2",
    label="Nitter RSS (@OpenAI)",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    for url in _NITTER_INSTANCES:
        try:
            xml_text = await fetch_text(url, timeout_s=10.0)
            volume, sentiment = _parse_rss(xml_text)
            return {"twitter_volume": volume, "twitter_sentiment": sentiment}
        except Exception as exc:
            logger.debug("nitter_rss: instance %s failed: %s", url, exc)

    logger.debug("nitter_rss: all instances failed, returning {}")
    return {}
