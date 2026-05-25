"""Tests for collectors/wikipedia.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.wikipedia import COLLECTOR_META, _parse_views, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _parse_views unit tests
# ---------------------------------------------------------------------------

_NORMAL_RESPONSE = {
    "query": {
        "pages": {
            "1": {
                "title": "ChatGPT",
                "pageviews": {"2026-05-18": 20000, "2026-05-19": 18000},
            },
            "2": {
                "title": "OpenAI",
                "pageviews": {"2026-05-18": 15000, "2026-05-19": 12000},
            },
            "3": {
                "title": "GPT-4",
                "pageviews": {"2026-05-18": None, "2026-05-19": 5000},
            },
        }
    }
}


def test_parse_views_normal():
    result = _parse_views(json.dumps(_NORMAL_RESPONSE))
    # Most recent non-None: 18000 + 12000 + 5000 = 35000
    assert result == pytest.approx(35000 / 50000)


def test_parse_views_empty_pages():
    data = {"query": {"pages": {}}}
    result = _parse_views(json.dumps(data))
    assert result == pytest.approx(0.0)


def test_parse_views_all_none_pageviews():
    data = {
        "query": {
            "pages": {
                "1": {"pageviews": {"2026-05-19": None, "2026-05-18": None}},
            }
        }
    }
    result = _parse_views(json.dumps(data))
    assert result == pytest.approx(0.0)


def test_parse_views_clamps_to_one():
    # Very high views should normalise to 1.0
    data = {
        "query": {
            "pages": {
                "1": {"pageviews": {"2026-05-19": 999999}},
            }
        }
    }
    result = _parse_views(json.dumps(data))
    assert result == pytest.approx(1.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "wikipedia"
    assert COLLECTOR_META["interval_s"] == 900


# ---------------------------------------------------------------------------
# collect() integration test
# ---------------------------------------------------------------------------


async def test_collect_returns_wikipedia_views_ai():
    payload = json.dumps(
        {"query": {"pages": {"1": {"pageviews": {"2026-05-19": 25000}}}}}
    )

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=payload)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("collectors.utils.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert "wikipedia_views_ai" in result
    assert 0.0 <= result["wikipedia_views_ai"] <= 1.0
