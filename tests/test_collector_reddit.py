"""Tests for collectors/reddit.py."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.reddit import (
    COLLECTOR_META,
    _posts_last_hour,
    _sentiment_for_post,
    collect,
)
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _posts_last_hour unit tests
# ---------------------------------------------------------------------------


def test_posts_last_hour_all_recent():
    now_ts = time.time()
    posts = [{"created_utc": now_ts - 100, "title": "t", "selftext": ""}] * 5
    result = _posts_last_hour(posts, now_ts)
    assert len(result) == 5


def test_posts_last_hour_filters_old():
    now_ts = time.time()
    old = {"created_utc": now_ts - 7200, "title": "old", "selftext": ""}  # 2 h ago
    recent = {"created_utc": now_ts - 30, "title": "new", "selftext": ""}
    result = _posts_last_hour([old, recent], now_ts)
    assert len(result) == 1
    assert result[0]["title"] == "new"


def test_posts_last_hour_empty_list():
    assert _posts_last_hour([], time.time()) == []


# ---------------------------------------------------------------------------
# _sentiment_for_post unit tests
# ---------------------------------------------------------------------------


def test_sentiment_for_post_positive():
    score = _sentiment_for_post("I love ChatGPT, it's amazing!", "")
    assert score > 0.0


def test_sentiment_for_post_negative():
    score = _sentiment_for_post("ChatGPT is broken and terrible", "")
    assert score < 0.0


def test_sentiment_for_post_truncates_selftext():
    # Body longer than 200 chars — should not raise
    long_body = "x" * 1000
    score = _sentiment_for_post("title", long_body)
    assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# collect() — missing env vars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_missing_client_id_returns_empty():
    env = {
        "REDDIT_CLIENT_SECRET": "secret",
        "REDDIT_USER_AGENT": "agent/1.0",
    }
    with patch.dict("os.environ", env, clear=True):
        result = await collect(GlobalState())
    assert result == {}


@pytest.mark.asyncio
async def test_collect_missing_all_keys_returns_empty():
    with patch.dict("os.environ", {}, clear=True):
        result = await collect(GlobalState())
    assert result == {}


# ---------------------------------------------------------------------------
# collect() — happy path with mocked asyncpraw
# ---------------------------------------------------------------------------


def _make_mock_submission(created_offset_s: float, title: str = "ChatGPT is great", selftext: str = "") -> MagicMock:
    """Return a mock asyncpraw Submission with the given age."""
    sub = MagicMock()
    sub.created_utc = time.time() - created_offset_s
    sub.title = title
    sub.selftext = selftext
    return sub


async def _async_iter(items):
    """Async generator over *items*."""
    for item in items:
        yield item


def _make_mock_reddit(submissions_per_sub: list) -> tuple[MagicMock, MagicMock]:
    """Return (mock_reddit_instance, mock_asyncpraw_module).

    The mock Reddit context manager will yield *submissions_per_sub* for every
    subreddit.new() call (same list reused across all 3 subreddits).
    """
    mock_subreddit = MagicMock()
    mock_subreddit.new = MagicMock(
        side_effect=lambda limit: _async_iter(submissions_per_sub)
    )

    mock_reddit_instance = AsyncMock()
    mock_reddit_instance.subreddit = AsyncMock(return_value=mock_subreddit)
    mock_reddit_instance.__aenter__ = AsyncMock(return_value=mock_reddit_instance)
    mock_reddit_instance.__aexit__ = AsyncMock(return_value=False)

    mock_asyncpraw = MagicMock()
    mock_asyncpraw.Reddit = MagicMock(return_value=mock_reddit_instance)

    return mock_reddit_instance, mock_asyncpraw


@pytest.mark.asyncio
async def test_collect_five_recent_posts_volume_and_sentiment():
    submissions = [_make_mock_submission(60) for _ in range(5)]  # 5 posts, 1 min ago
    _mock_instance, mock_asyncpraw = _make_mock_reddit(submissions)

    env = {
        "REDDIT_CLIENT_ID": "cid",
        "REDDIT_CLIENT_SECRET": "secret",
        "REDDIT_USER_AGENT": "agent/1.0",
    }
    with patch.dict("os.environ", env):
        with patch.dict("sys.modules", {"asyncpraw": mock_asyncpraw}):
            result = await collect(GlobalState())

    assert "reddit_volume" in result
    assert "reddit_sentiment" in result
    assert result["reddit_volume"] > 0.0
    assert -1.0 <= result["reddit_sentiment"] <= 1.0


@pytest.mark.asyncio
async def test_collect_empty_subreddits_returns_zero_volume():
    _mock_instance, mock_asyncpraw = _make_mock_reddit([])

    env = {
        "REDDIT_CLIENT_ID": "cid",
        "REDDIT_CLIENT_SECRET": "secret",
        "REDDIT_USER_AGENT": "agent/1.0",
    }
    with patch.dict("os.environ", env):
        with patch.dict("sys.modules", {"asyncpraw": mock_asyncpraw}):
            result = await collect(GlobalState())

    assert result["reddit_volume"] == 0.0
    assert result["reddit_sentiment"] == 0.0


# ---------------------------------------------------------------------------
# COLLECTOR_META
# ---------------------------------------------------------------------------


def test_collector_meta():
    assert COLLECTOR_META["name"] == "reddit"
    assert COLLECTOR_META["interval_s"] == 300
