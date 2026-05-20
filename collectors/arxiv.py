"""ArXiv collector — papers submitted in the last 24 hours.

Queries the ArXiv API for the 50 most recent cs.AI / cs.LG submissions,
parses each <published> date, and counts how many were submitted within
the last 24 hours.
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
    text = await fetch_text(_URL, timeout_s=20.0)
    return {"arxiv_papers_today": _parse_arxiv(text)}
