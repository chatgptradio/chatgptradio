"""YouTube Live Chat collector — reads chat via pytchat, routes !commands."""
from __future__ import annotations

import asyncio
import collections
import os
import time
from typing import Any

import structlog

from core.state import GlobalState

log = structlog.get_logger()

SOURCE_NAME = "youtube_chat"
COLLECTOR_META = {"name": SOURCE_NAME, "interval_s": 10}

_video_id_cache: str | None = None


async def _resolve_video_id() -> str | None:
    global _video_id_cache
    if _video_id_cache:
        return _video_id_cache

    vid = os.environ.get("YOUTUBE_VIDEO_ID", "").strip()
    if vid:
        _video_id_cache = vid
        return vid

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not channel_id or not api_key:
        log.warning(
            "youtube_chat_disabled",
            reason="no YOUTUBE_VIDEO_ID or YOUTUBE_CHANNEL_ID+YOUTUBE_API_KEY",
        )
        return None

    try:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        service = build("youtube", "v3", developerKey=api_key)
        resp = (
            service.search()
            .list(
                channelId=channel_id,
                eventType="live",
                type="video",
                part="id",
            )
            .execute()
        )
        items = resp.get("items", [])
        if not items:
            log.warning("youtube_chat_no_live", channel_id=channel_id)
            return None
        _video_id_cache = items[0]["id"]["videoId"]
        log.info("youtube_chat_video_found", video_id=_video_id_cache)
        return _video_id_cache
    except Exception:
        log.exception("youtube_chat_search_error")
        return None


# Module-level deque shared across invocations within a process lifetime.
_msg_times: collections.deque[float] = collections.deque()

# Injected via make_collector(); kept as module-level so _discover_collectors
# can reach the plain `collect` symbol while still benefiting from closure deps.
_engine: Any = None
_conn: Any = None


def make_collector(engine: Any, conn: Any) -> None:
    """Inject CommandEngine and aiosqlite.Connection into this module.

    Called once from main.py after both are available.  After this call the
    module-level ``collect`` coroutine function will use these dependencies.
    """
    global _engine, _conn
    _engine = engine
    _conn = conn


async def collect(
    state: GlobalState,
    state_queue: asyncio.Queue,  # type: ignore[type-arg]
) -> dict[str, Any]:
    """Read one batch of YouTube live chat messages and route !commands."""
    import pytchat  # type: ignore[import-untyped]

    video_id = await _resolve_video_id()
    if not video_id:
        return {}

    chat = pytchat.create(video_id=video_id)
    if not chat.is_alive():
        log.warning("youtube_chat_not_alive", video_id=video_id)
        # Reset cache so the next poll re-resolves the live video ID.
        global _video_id_cache
        _video_id_cache = None
        return {}

    now = time.time()
    async for item in chat.get().async_items():  # type: ignore[union-attr]
        msg = item.message.strip()
        _msg_times.append(now)

        if msg.startswith("!") and _engine is not None and _conn is not None:
            from core.chat_commands import handle_command  # local import avoids circular

            try:
                response = await handle_command(
                    msg, state, _engine, state_queue, _conn
                )
                if response:
                    log.info(
                        "chat_command_executed",
                        cmd=msg.split()[0],
                        response=response,
                    )
            except Exception:
                log.exception("chat_command_error", raw=msg)

    # Purge messages older than 5 min, then compute msgs/min.
    cutoff = now - 300.0
    while _msg_times and _msg_times[0] < cutoff:
        _msg_times.popleft()
    chat_rate = len(_msg_times) / 5.0  # msgs/min (5-min rolling window)

    return {"chat_rate": chat_rate}
