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
_search_backoff_until: float = 0.0  # epoch seconds; don't search before this time
_SEARCH_BACKOFF_NO_LIVE = 120.0    # 2 min when no live found
_SEARCH_BACKOFF_QUOTA = 3600.0     # 1 hr when quota exceeded

_viewers_cache: int = 0
_viewers_last_fetch: float = 0.0
_VIEWERS_FETCH_INTERVAL = 120.0   # call YouTube API at most once every 2 min


async def _fetch_viewer_count(video_id: str) -> int:
    """Fetch concurrent viewer count via YouTube Data API v3 (1 quota unit)."""
    global _viewers_cache, _viewers_last_fetch
    now = time.time()
    if now - _viewers_last_fetch < _VIEWERS_FETCH_INTERVAL:
        return _viewers_cache

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return _viewers_cache

    try:
        import asyncio as _aio
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        loop = _aio.get_event_loop()

        def _call() -> int:
            svc = build("youtube", "v3", developerKey=api_key)
            resp = svc.videos().list(part="liveStreamingDetails", id=video_id).execute()
            items = resp.get("items", [])
            if not items:
                return _viewers_cache
            details = items[0].get("liveStreamingDetails", {})
            return int(details.get("concurrentViewers", _viewers_cache))

        count = await loop.run_in_executor(None, _call)
        _viewers_cache = count
        _viewers_last_fetch = now
        return count
    except Exception:
        log.exception("youtube_viewer_count_error")
        return _viewers_cache


async def _resolve_video_id() -> str | None:
    global _video_id_cache, _search_backoff_until
    if _video_id_cache:
        return _video_id_cache

    vid = os.environ.get("YOUTUBE_VIDEO_ID", "").strip()
    if vid:
        _video_id_cache = vid
        return vid

    now = time.time()
    if now < _search_backoff_until:
        return None

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
        from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

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
            _search_backoff_until = time.time() + _SEARCH_BACKOFF_NO_LIVE
            return None
        _video_id_cache = items[0]["id"]["videoId"]
        log.info("youtube_chat_video_found", video_id=_video_id_cache)
        return _video_id_cache
    except HttpError as exc:  # type: ignore[possibly-unbound]
        if exc.status_code == 403:
            log.warning("youtube_chat_quota_exceeded", backoff_s=_SEARCH_BACKOFF_QUOTA)
            _search_backoff_until = time.time() + _SEARCH_BACKOFF_QUOTA
        else:
            log.exception("youtube_chat_search_error")
            _search_backoff_until = time.time() + _SEARCH_BACKOFF_NO_LIVE
        return None
    except Exception:
        log.exception("youtube_chat_search_error")
        _search_backoff_until = time.time() + _SEARCH_BACKOFF_NO_LIVE
        return None


# Module-level deque shared across invocations within a process lifetime.
_msg_times: collections.deque[float] = collections.deque()

# Persistent pytchat session — created once, reused across polls so messages
# accumulate between calls and are not missed by session-recreation races.
_chat_session: Any = None

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
    import pytchat.util as _ptutil

    global _chat_session, _video_id_cache

    # pytchat scrapes YouTube to resolve channelId, but YouTube now returns
    # hex-encoded JSON to scrapers, breaking the regex. Bypass entirely by
    # injecting the known channel ID from env — no scraping needed.
    _known_channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "")
    if _known_channel_id:
        _ptutil.get_channelid = lambda _c, _v: _known_channel_id

    video_id = await _resolve_video_id()
    if not video_id:
        return {}

    # Reuse persistent session — avoids recreating every 10s which causes messages
    # to be missed (fresh session starts fetching from NOW, not from last poll).
    if _chat_session is None or not _chat_session.is_alive():
        _chat_session = pytchat.create(video_id=video_id)
        if not _chat_session.is_alive():
            log.warning("youtube_chat_not_alive", video_id=video_id)
            _video_id_cache = None
            _chat_session = None
            return {}
        log.info("youtube_chat_session_created", video_id=video_id)

    now = time.time()

    # chat.get() is synchronous and blocks up to ~1s — run in executor to avoid
    # freezing the event loop while waiting for the chat poll response.
    loop = asyncio.get_event_loop()
    try:
        chat_data = await loop.run_in_executor(None, _chat_session.get)
    except Exception:
        log.exception("youtube_chat_get_error")
        _chat_session = None
        return {}

    async for item in chat_data.async_items():  # type: ignore[union-attr]
        msg = item.message.strip()
        _msg_times.append(now)

        if msg.startswith("!") and _engine is not None and _conn is not None:
            from core.chat_commands import handle_command  # local import avoids circular

            author = getattr(getattr(item, "author", None), "name", "") or ""
            try:
                response = await handle_command(
                    msg, author, state, _engine, state_queue, _conn
                )
                if response:
                    log.info("chat_command_executed", cmd=msg.split()[0], response=response)
            except Exception:
                log.exception("chat_command_error", raw=msg)

    # Purge messages older than 5 min, then compute msgs/min.
    cutoff = now - 300.0
    while _msg_times and _msg_times[0] < cutoff:
        _msg_times.popleft()
    chat_rate = len(_msg_times) / 5.0  # msgs/min (5-min rolling window)

    viewers = await _fetch_viewer_count(video_id)

    return {"chat_rate": chat_rate, "viewers": viewers}
