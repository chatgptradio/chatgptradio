"""Shared utilities for Phase 3 collectors.

Provides:
- vader_sentiment: VADER compound sentiment score
- normalize: clamp + linear map to [0, 1]
- fetch_text: async HTTP GET returning response body as text
"""

import aiohttp
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def vader_sentiment(text: str) -> float:
    """Return VADER compound score in [-1, 1] for *text*.

    Returns 0.0 for empty or whitespace-only input.
    """
    if not text or not text.strip():
        return 0.0
    return float(_analyzer.polarity_scores(text)["compound"])


def normalize(val: float, low: float, high: float) -> float:
    """Clamp *val* to [low, high] then linearly map to [0, 1].

    Returns 0.5 when low == high (degenerate range).
    """
    if low == high:
        return 0.5
    clamped = max(low, min(high, val))
    return (clamped - low) / (high - low)


async def fetch_text(url: str, timeout_s: float = 10.0) -> str:
    """Async GET *url* and return the response body as text.

    Raises aiohttp.ClientError (including aiohttp.ClientResponseError) on
    HTTP errors or network failures.
    """
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.text()
