import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import aiohttp

from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "openai_status", "interval_s": 30}

_RSS_URL = "https://status.openai.com/history.rss"
_TIMEOUT_S = 10

_OUTAGE_KEYWORDS = {"major outage", "partial outage", "investigating", "disruption"}
_DEGRADED_KEYWORDS = {"degraded", "elevated", "monitoring", "identified"}


def _parse_status(xml_text: str) -> tuple[float, float]:
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    if not items:
        return 1.0, 0.0

    latest = items[0]
    title = (latest.findtext("title") or "").lower()
    pub_date_raw = latest.findtext("pubDate") or ""

    incident_hours = 0.0
    if pub_date_raw:
        try:
            from email.utils import parsedate_to_datetime
            pub_dt = parsedate_to_datetime(pub_date_raw)
            incident_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
        except Exception:
            pass

    if any(kw in title for kw in _OUTAGE_KEYWORDS):
        return 0.0, 0.0
    if any(kw in title for kw in _DEGRADED_KEYWORDS):
        return 0.5, 0.0
    return 1.0, max(incident_hours, 0.0)


@node(
    name="openai_status",
    produces="openai_status",
    color="#10A37F",
    label="OpenAI Status RSS",
    reads=["openai_latency_ms", "openai_incident_age_h"],
)
async def collect(state: GlobalState) -> dict[str, Any]:
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        async with session.get(_RSS_URL, timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S)) as resp:
            resp.raise_for_status()
            text = await resp.text()
    latency_ms = (time.perf_counter() - t0) * 1000.0

    status, incident_age_h = _parse_status(text)
    return {
        "openai_status": status,
        "openai_incident_age_h": incident_age_h,
        "openai_latency_ms": latency_ms,
    }
