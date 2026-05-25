"""NewsAPI.ai collector — newsapi_volume, newsapi_sentiment.

Uses the EventRegistry / NewsAPI.ai REST endpoint to fetch articles
mentioning "ChatGPT" (English, up to 50 per call).  Volume is normalised
against a 200-article ceiling; sentiment is averaged VADER on article titles.
"""

import os
from typing import Any
from urllib.parse import urlencode

import orjson
import structlog

from collectors.utils import fetch_text, normalize, vader_sentiment
from core.node import node
from core.state import GlobalState

log = structlog.get_logger()

COLLECTOR_META = {"name": "newsapi", "interval_s": 300}

_BASE_URL = "https://newsapi.ai/api/v1/article/getArticles"
_ARTICLES_COUNT = 50
_VOLUME_MAX = 200.0


def _parse_response(text: str) -> tuple[float, float]:
    """Return (volume_normalised, sentiment_avg) from a NewsAPI.ai JSON response.

    Handles missing / malformed responses defensively.
    """
    try:
        data = orjson.loads(text)
    except (orjson.JSONDecodeError, ValueError):
        return 0.0, 0.0

    # EventRegistry envelope: {"articles": {"results": [...], "totalResults": N}}
    articles_obj = data.get("articles") or {}

    # Flat-list fallback: some endpoints return {"articles": [...]}
    if isinstance(articles_obj, list):
        results = articles_obj
    else:
        results = articles_obj.get("results") or []

    count = float(len(results))
    volume = normalize(count, 0.0, _VOLUME_MAX)

    if results:
        titles = [
            (a.get("title") or a.get("headline") or "") for a in results
        ]
        sentiments = [vader_sentiment(t) for t in titles if t]
        sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
    else:
        sentiment = 0.0

    return volume, sentiment


@node(
    name="newsapi",
    produces="newsapi_volume",
    color="#0080FF",
    label="NewsAPI.ai Volume/Sentiment",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    api_key = os.environ.get("NEWSAPI_AI_KEY")
    if not api_key:
        log.warning(
            "collector_disabled",
            collector="newsapi",
            reason="NEWSAPI_AI_KEY not set",
        )
        return {}

    params = {
        "keyword": "ChatGPT",
        "lang": "eng",
        "articlesCount": _ARTICLES_COUNT,
        "apiKey": api_key,
    }
    url = f"{_BASE_URL}?{urlencode(params)}"
    text = await fetch_text(url, timeout_s=15.0)
    volume, sentiment = _parse_response(text)

    return {
        "newsapi_volume": volume,
        "newsapi_sentiment": sentiment,
    }
