"""Media Cloud collector — media_cloud_ai_volume.

Queries Media Cloud for the story count matching "artificial intelligence"
OR "ChatGPT" over the past 24 hours.  The synchronous mediacloud v4 client is
run in a thread-pool executor to avoid blocking the event loop.
"""

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from collectors.utils import normalize
from core.node import node
from core.state import GlobalState

log = structlog.get_logger()

COLLECTOR_META = {"name": "media_cloud", "interval_s": 900}

_QUERY = '"artificial intelligence" OR "ChatGPT"'
_VOLUME_MAX = 1000.0


def _story_count_sync(api_key: str, start: date, end: date) -> int:
    """Blocking call to Media Cloud story_count.  Run via executor.

    Uses the mediacloud v4 SearchApi which returns a StoryCount TypedDict
    with a "count" key.
    """
    from mediacloud.api import SearchApi  # local import — optional dependency

    mc = SearchApi(api_key)
    # collection_ids=[34412234] = global online news (requis par l'API v4 — 422 sans ça)
    result = mc.story_count(_QUERY, start, end, collection_ids=[34412234])
    # StoryCount is a TypedDict / dict subclass with a "count" key
    if isinstance(result, dict):
        return int(result.get("count", 0))
    return int(result)  # type: ignore[arg-type]


@node(
    name="media_cloud",
    produces="media_cloud_ai_volume",
    color="#8B5CF6",
    label="Media Cloud AI Volume",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    api_key = os.environ.get("MEDIA_CLOUD_API_KEY")
    if not api_key:
        log.warning(
            "collector_disabled",
            collector="media_cloud",
            reason="MEDIA_CLOUD_API_KEY not set",
        )
        return {}

    now = datetime.now(timezone.utc)
    end_date = now.date()
    start_date = (now - timedelta(days=1)).date()

    loop = asyncio.get_running_loop()
    count = await loop.run_in_executor(
        None,
        lambda: _story_count_sync(api_key, start_date, end_date),
    )

    media_cloud_ai_volume = normalize(float(count), 0.0, _VOLUME_MAX)
    return {"media_cloud_ai_volume": media_cloud_ai_volume}
