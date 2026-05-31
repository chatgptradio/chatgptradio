"""Reddit collector — reddit_volume, reddit_sentiment.

Fetches new submissions from r/ChatGPT, r/OpenAI, r/artificial
over the past 60 minutes using asyncpraw, then normalises post
volume and computes aggregate VADER sentiment.
"""

import os
from datetime import datetime, timezone
from typing import Any

import structlog

from collectors.utils import normalize, vader_sentiment
from core.node import node
from core.state import GlobalState

log = structlog.get_logger()

COLLECTOR_META = {"name": "reddit", "interval_s": 300}

_SUBREDDITS = ["ChatGPT", "OpenAI", "artificial"]
_POSTS_PER_SUB = 50
_WINDOW_S = 3600  # 60-minute look-back
_VOLUME_MAX = 200.0  # posts/hour normalisation ceiling


def _posts_last_hour(
    submissions: list[dict],
    now_ts: float,
) -> list[dict]:
    """Return only the submissions created within the last hour."""
    cutoff = now_ts - _WINDOW_S
    return [s for s in submissions if s["created_utc"] >= cutoff]


def _sentiment_for_post(title: str, selftext: str) -> float:
    """VADER compound score for a post's title + first 200 chars of body."""
    text = title + " " + selftext[:200]
    return vader_sentiment(text)


@node(
    name="reddit",
    produces=["reddit_volume", "reddit_sentiment"],
    color="#FF4500",
    label="Reddit Volume/Sentiment",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT")

    if not client_id or not client_secret or not user_agent:
        log.warning(
            "collector_disabled",
            collector="reddit",
            reason="REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT not set",
        )
        return {"source_health": {"reddit": False}}

    import asyncpraw  # local import — optional dependency

    now_ts = datetime.now(timezone.utc).timestamp()
    all_posts: list[dict] = []

    async with asyncpraw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    ) as reddit:
        for sub_name in _SUBREDDITS:
            subreddit = await reddit.subreddit(sub_name)
            async for submission in subreddit.new(limit=_POSTS_PER_SUB):
                all_posts.append(
                    {
                        "created_utc": submission.created_utc,
                        "title": submission.title or "",
                        "selftext": submission.selftext or "",
                    }
                )

    recent = _posts_last_hour(all_posts, now_ts)

    reddit_volume = normalize(float(len(recent)), 0.0, _VOLUME_MAX)

    if recent:
        sentiments = [
            _sentiment_for_post(p["title"], p["selftext"]) for p in recent
        ]
        reddit_sentiment = sum(sentiments) / len(sentiments)
    else:
        reddit_sentiment = 0.0

    return {
        "reddit_volume": reddit_volume,
        "reddit_sentiment": reddit_sentiment,
    }
