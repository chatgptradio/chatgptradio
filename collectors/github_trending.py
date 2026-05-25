"""GitHub trending collector — github_ai_stars.

Uses the GitHub Search API (unauthenticated, 60 req/h) to sum star counts
for the top 10 AI/ML repositories.
"""

from typing import Any

import aiohttp

from collectors.utils import normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "github_trending", "interval_s": 3600}

_SEARCH_URL = (
    "https://api.github.com/search/repositories"
    "?q=AI+machine+learning+in:description&sort=stars&order=desc&per_page=10"
)
_HEADERS = {"User-Agent": "chatgptradio/1.0"}
_TIMEOUT_S = 15.0
_STARS_MAX = 5_000_000.0


def _sum_stars(data: dict) -> float:
    """Return total star count from a GitHub Search API response dict."""
    items = data.get("items") or []
    return float(sum(repo.get("stargazers_count", 0) for repo in items))


@node(
    name="github_trending",
    produces="github_ai_stars",
    color="#24292E",
    label="GitHub AI Stars",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_S)
    async with aiohttp.ClientSession(headers=_HEADERS) as session:
        async with session.get(_SEARCH_URL, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()

    total_stars = _sum_stars(data)
    github_ai_stars = normalize(total_stars, 0.0, _STARS_MAX)
    return {"github_ai_stars": github_ai_stars}
