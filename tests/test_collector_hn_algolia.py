"""Tests for collectors/hn_algolia.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.hn_algolia import COLLECTOR_META, _parse_hn, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _parse_hn unit tests
# ---------------------------------------------------------------------------


def test_parse_hn_normal_hits():
    data = {
        "hits": [
            {"points": 200},
            {"points": 300},
            {"points": 100},
        ]
    }
    result = _parse_hn(json.dumps(data))
    # avg = 200, normalise over [0, 500] → 0.4
    assert result == pytest.approx(0.4)


def test_parse_hn_empty_hits():
    data = {"hits": []}
    result = _parse_hn(json.dumps(data))
    assert result == pytest.approx(0.0)


def test_parse_hn_missing_points_field():
    data = {"hits": [{"title": "No points key"}]}
    result = _parse_hn(json.dumps(data))
    assert result == pytest.approx(0.0)


def test_parse_hn_clamps_high_score():
    data = {"hits": [{"points": 9999}]}
    result = _parse_hn(json.dumps(data))
    assert result == pytest.approx(1.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "hn_algolia"
    assert COLLECTOR_META["interval_s"] == 300


# ---------------------------------------------------------------------------
# collect() integration test with mocked HTTP
# ---------------------------------------------------------------------------


async def test_collect_returns_hn_ai_score():
    payload = json.dumps({"hits": [{"points": 250}, {"points": 250}]})

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

    assert "hn_ai_score" in result
    assert 0.0 <= result["hn_ai_score"] <= 1.0
    assert result["hn_ai_score"] == pytest.approx(0.5)
