"""ArXiv collector — prediction-error delta of AI papers submitted in last 24h.

Queries the ArXiv API for the 50 most recent cs.AI / cs.LG submissions,
counts how many were submitted within the last 24 hours, then emits a
normalised delta relative to a rolling 7-call average.

Emitted value:
    (papers_today - avg(history)) / max(avg(history), 1.0)

Centred on 0: positive when today's count exceeds the recent average, negative
when it falls short.  This is a genuine PE (prediction error) signal rather
than a raw count that is 0 for ~23 h per day.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from collectors.utils import fetch_text
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "arxiv", "interval_s": 3600}

_URL = (
    "http://export.arxiv.org/api/query"
    "?search_query=cat:cs.AI+OR+cat:cs.LG"
    "&start=0&max_results=50"
    "&sortBy=submittedDate&sortOrder=descending"
)

# Atom namespace used by the ArXiv API
_ATOM_NS = "http://www.w3.org/2005/Atom"

# Rolling window of the last 7 paper counts (one entry per collect() call).
_count_history: list[int] = []
_HISTORY_MAX = 7


def _parse_arxiv(text: str) -> int:
    root = ET.fromstring(text)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        pub_text = entry.findtext(f"{{{_ATOM_NS}}}published") or ""
        try:
            pub_dt = datetime.fromisoformat(pub_text.replace("Z", "+00:00"))
            if pub_dt >= cutoff:
                count += 1
        except ValueError:
            pass
    return count


@node(
    name="arxiv",
    produces="arxiv_papers_today",
    color="#B31B1B",
    label="ArXiv AI Papers Today",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    global _count_history

    text = await fetch_text(_URL, timeout_s=20.0)
    papers_today = _parse_arxiv(text)

    avg = sum(_count_history) / len(_count_history) if _count_history else 0.0
    delta = (papers_today - avg) / max(avg, 1.0)

    # Update rolling history (bounded to _HISTORY_MAX entries)
    _count_history.append(papers_today)
    if len(_count_history) > _HISTORY_MAX:
        _count_history.pop(0)

    return {"arxiv_papers_today": delta}
