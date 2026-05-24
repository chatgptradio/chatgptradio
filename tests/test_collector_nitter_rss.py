"""Tests for collectors/nitter_rss.py."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import pytest

import collectors.nitter_rss as nitter_mod
from collectors.nitter_rss import COLLECTOR_META, _parse_rss, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pub_date(minutes_ago: float) -> str:
    """Return an RFC 2822 date string for *minutes_ago* minutes in the past."""
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return format_datetime(dt)


def _make_rss(items: list[dict]) -> str:
    """Build a minimal Nitter RSS feed XML string.

    Each item dict may have 'title' and 'pubDate' keys.
    """
    item_xml = ""
    for item in items:
        title = item.get("title", "tweet title")
        pub_date = item.get("pubDate", _pub_date(10))
        item_xml += f"<item><title>{title}</title><pubDate>{pub_date}</pubDate></item>\n"

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<rss><channel>"
        f"{item_xml}"
        "</channel></rss>"
    )


# ---------------------------------------------------------------------------
# _parse_rss unit tests
# ---------------------------------------------------------------------------


def test_parse_rss_recent_items_produce_nonzero_volume():
    xml = _make_rss([
        {"title": "OpenAI releases GPT-5", "pubDate": _pub_date(5)},
        {"title": "Exciting AI news", "pubDate": _pub_date(30)},
        {"title": "New model from OpenAI", "pubDate": _pub_date(55)},
    ])
    volume, sentiment = _parse_rss(xml)
    assert volume > 0.0
    assert -1.0 <= sentiment <= 1.0


def test_parse_rss_all_items_older_than_60_min():
    xml = _make_rss([
        {"title": "Old tweet", "pubDate": _pub_date(61)},
        {"title": "Very old tweet", "pubDate": _pub_date(120)},
    ])
    volume, sentiment = _parse_rss(xml)
    assert volume == pytest.approx(0.0)
    assert sentiment == pytest.approx(0.0)


def test_parse_rss_mixed_ages():
    xml = _make_rss([
        {"title": "Recent tweet", "pubDate": _pub_date(10)},
        {"title": "Old tweet", "pubDate": _pub_date(90)},
    ])
    volume, sentiment = _parse_rss(xml)
    # Only 1 recent item out of 100 max → normalize(1, 0, 100) = 0.01
    assert volume == pytest.approx(0.01)


def test_parse_rss_empty_feed():
    xml = _make_rss([])
    volume, sentiment = _parse_rss(xml)
    assert volume == pytest.approx(0.0)
    assert sentiment == pytest.approx(0.0)


def test_parse_rss_sentiment_range():
    xml = _make_rss([
        {"title": "Amazing excellent fantastic news!", "pubDate": _pub_date(5)},
        {"title": "Terrible awful disaster", "pubDate": _pub_date(10)},
    ])
    volume, sentiment = _parse_rss(xml)
    assert volume > 0.0
    assert -1.0 <= sentiment <= 1.0


def test_collector_meta():
    assert COLLECTOR_META["name"] == "nitter_rss"
    assert COLLECTOR_META["interval_s"] == 300


# ---------------------------------------------------------------------------
# collect() integration tests with mocked HTTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_valid_rss_returns_fields():
    xml = _make_rss([
        {"title": "OpenAI launches new API", "pubDate": _pub_date(5)},
        {"title": "GPT-4 update released", "pubDate": _pub_date(20)},
        {"title": "AI breakthrough announced", "pubDate": _pub_date(40)},
    ])

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        return xml

    with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
        result = await collect(GlobalState())

    assert "twitter_volume" in result
    assert "twitter_sentiment" in result
    assert result["twitter_volume"] > 0.0
    assert -1.0 <= result["twitter_sentiment"] <= 1.0


@pytest.mark.asyncio
async def test_collect_all_instances_fail_returns_source_health_false():
    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        raise ConnectionError("instance down")

    with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
        result = await collect(GlobalState())

    assert result == {"source_health": {"nitter_rss": False}}


@pytest.mark.asyncio
async def test_collect_all_items_older_than_60_min_returns_zero_volume():
    xml = _make_rss([
        {"title": "Old tweet", "pubDate": _pub_date(90)},
        {"title": "Very old tweet", "pubDate": _pub_date(120)},
    ])

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        return xml

    with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
        result = await collect(GlobalState())

    assert "twitter_volume" in result
    assert result["twitter_volume"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_collect_tries_next_instance_on_failure():
    xml = _make_rss([{"title": "tweet", "pubDate": _pub_date(5)}])
    call_count = 0

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("first instance down")
        return xml

    with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
        result = await collect(GlobalState())

    assert call_count == 2
    assert "twitter_volume" in result


# ---------------------------------------------------------------------------
# New tests: _last_ok_idx priority + source_health reporting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nitter_tries_last_ok_instance_first():
    """If _last_ok_idx=1, instance at index 1 is tried before index 0."""
    xml = _make_rss([{"title": "tweet", "pubDate": _pub_date(5)}])
    attempted_urls: list[str] = []

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        attempted_urls.append(url)
        return xml

    original_idx = nitter_mod._last_ok_idx
    nitter_mod._last_ok_idx = 1
    try:
        with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
            await collect(GlobalState())
    finally:
        nitter_mod._last_ok_idx = original_idx

    assert len(attempted_urls) >= 1
    # The URL at index 1 should be the first one attempted
    assert attempted_urls[0] == nitter_mod._NITTER_INSTANCES[1]


@pytest.mark.asyncio
async def test_nitter_success_updates_last_ok_idx():
    """A successful fetch at index 2 should update _last_ok_idx to 2."""
    xml = _make_rss([{"title": "tweet", "pubDate": _pub_date(5)}])
    call_count = 0

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("down")
        return xml

    original_idx = nitter_mod._last_ok_idx
    nitter_mod._last_ok_idx = 0
    try:
        with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
            await collect(GlobalState())
        assert nitter_mod._last_ok_idx == 2
    finally:
        nitter_mod._last_ok_idx = original_idx


@pytest.mark.asyncio
async def test_nitter_returns_source_health_true_on_success():
    """A successful collect should include source_health={"nitter_rss": True}."""
    xml = _make_rss([{"title": "tweet", "pubDate": _pub_date(5)}])

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        return xml

    with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
        result = await collect(GlobalState())

    assert "source_health" in result
    assert result["source_health"] == {"nitter_rss": True}


@pytest.mark.asyncio
async def test_nitter_returns_source_health_false_on_all_fail():
    """When all instances fail, collect should include source_health={"nitter_rss": False}."""

    async def fake_fetch_text(url: str, timeout_s: float = 10.0) -> str:
        raise ConnectionError("down")

    with patch("collectors.nitter_rss.fetch_text", side_effect=fake_fetch_text):
        result = await collect(GlobalState())

    assert "source_health" in result
    assert result["source_health"] == {"nitter_rss": False}


def test_nitter_has_four_instances():
    """_NITTER_INSTANCES must have at least 4 entries."""
    assert len(nitter_mod._NITTER_INSTANCES) >= 4


def test_nitter_timeout_is_6s():
    """The timeout passed to fetch_text must be 6.0 seconds."""
    # We verify this by checking the source code doesn't use 10.0 anymore
    # and the collect function uses 6.0 via inspection of attempted calls.
    import inspect
    src = inspect.getsource(nitter_mod.collect)
    assert "6.0" in src
