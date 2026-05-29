"""Wikipedia pageviews collector — ChatGPT, OpenAI, GPT-4.

Uses the Wikimedia REST v1 pageviews API (requires User-Agent per Wikimedia policy).
Sums yesterday's page views for the three articles, normalised to [0, 1].
"""

from datetime import date, timedelta
from typing import Any

from collectors.utils import fetch_json, normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "wikipedia", "interval_s": 900}

_TITLES = ["ChatGPT", "OpenAI", "GPT-4"]
_VIEWS_HIGH = 150_000.0
_HEADERS = {"User-Agent": "ChatGPTRadio/1.0 (https://github.com/x230png/chatgptradio)"}


def _views_url(title: str, day: str) -> str:
    return (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
        f"/en.wikipedia/all-access/user/{title}/daily/{day}/{day}"
    )


@node(
    name="wikipedia",
    produces="wikipedia_views_ai",
    color="#000000",
    label="Wikipedia AI Page Views",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    day = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    total = 0
    for title in _TITLES:
        try:
            data = await fetch_json(_views_url(title, day), timeout_s=10.0, headers=_HEADERS)
            for item in data.get("items", []):
                total += int(item.get("views", 0))
        except Exception:
            pass
    return {"wikipedia_views_ai": normalize(float(total), 0.0, _VIEWS_HIGH)}
