"""Tests for collectors/newsapi.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from collectors.newsapi import (
    COLLECTOR_META,
    _parse_response,
    collect,
)
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _parse_response unit tests
# ---------------------------------------------------------------------------


def _make_response(titles: list[str]) -> str:
    """Build a NewsAPI.ai-style JSON response with the given article titles."""
    results = [{"title": t} for t in titles]
    return json.dumps({"articles": {"results": results}})


def test_parse_response_five_articles_volume():
    text = _make_response(["title"] * 5)
    volume, _sentiment = _parse_response(text)
    # 5 / 200 = 0.025
    assert volume == pytest.approx(0.025)


def test_parse_response_sentiment_positive():
    text = _make_response(["ChatGPT is amazing and wonderful"] * 3)
    _volume, sentiment = _parse_response(text)
    assert sentiment > 0.0


def test_parse_response_empty_results():
    text = json.dumps({"articles": {"results": []}})
    volume, sentiment = _parse_response(text)
    assert volume == pytest.approx(0.0)
    assert sentiment == pytest.approx(0.0)


def test_parse_response_max_volume_clamped():
    # 200 articles → exactly 1.0
    text = _make_response(["x"] * 200)
    volume, _ = _parse_response(text)
    assert volume == pytest.approx(1.0)


def test_parse_response_above_max_clamped_to_one():
    text = _make_response(["x"] * 300)
    volume, _ = _parse_response(text)
    assert volume == pytest.approx(1.0)


def test_parse_response_invalid_json():
    volume, sentiment = _parse_response("not json")
    assert volume == pytest.approx(0.0)
    assert sentiment == pytest.approx(0.0)


def test_parse_response_flat_list_fallback():
    """Some endpoint variants return {"articles": [...]} directly."""
    results = [{"title": "AI news"} for _ in range(10)]
    text = json.dumps({"articles": results})
    volume, _sentiment = _parse_response(text)
    assert volume == pytest.approx(10 / 200)


# ---------------------------------------------------------------------------
# collect() — missing env var
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_missing_key_returns_empty():
    with patch.dict("os.environ", {}, clear=True):
        result = await collect(GlobalState())
    assert result == {}


# ---------------------------------------------------------------------------
# collect() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_returns_volume_and_sentiment():
    payload = _make_response(["ChatGPT is brilliant"] * 20)

    with patch.dict("os.environ", {"NEWSAPI_AI_KEY": "testkey"}):
        with patch("collectors.newsapi.fetch_text", new=AsyncMock(return_value=payload)):
            result = await collect(GlobalState())

    assert "newsapi_volume" in result
    assert "newsapi_sentiment" in result
    assert 0.0 <= result["newsapi_volume"] <= 1.0
    assert -1.0 <= result["newsapi_sentiment"] <= 1.0
    assert result["newsapi_volume"] == pytest.approx(20 / 200)


@pytest.mark.asyncio
async def test_collect_empty_articles_returns_zero():
    payload = json.dumps({"articles": {"results": []}})

    with patch.dict("os.environ", {"NEWSAPI_AI_KEY": "testkey"}):
        with patch("collectors.newsapi.fetch_text", new=AsyncMock(return_value=payload)):
            result = await collect(GlobalState())

    assert result["newsapi_volume"] == pytest.approx(0.0)
    assert result["newsapi_sentiment"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# COLLECTOR_META
# ---------------------------------------------------------------------------


def test_collector_meta():
    assert COLLECTOR_META["name"] == "newsapi"
    assert COLLECTOR_META["interval_s"] == 300
