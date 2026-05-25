"""Tests for collectors/hedonometer.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.hedonometer import COLLECTOR_META, _parse_happiness, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _parse_happiness unit tests
# ---------------------------------------------------------------------------


def test_parse_happiness_average_score():
    data = {"objects": [{"happiness": 6.0}]}
    result = _parse_happiness(json.dumps(data))
    # 6.0 in [5.0, 7.0] → 0.5
    assert result == pytest.approx(0.5)


def test_parse_happiness_high_score():
    data = {"objects": [{"happiness": 7.0}]}
    result = _parse_happiness(json.dumps(data))
    assert result == pytest.approx(1.0)


def test_parse_happiness_low_score():
    data = {"objects": [{"happiness": 5.0}]}
    result = _parse_happiness(json.dumps(data))
    assert result == pytest.approx(0.0)


def test_parse_happiness_empty_objects():
    data = {"objects": []}
    result = _parse_happiness(json.dumps(data))
    assert result == pytest.approx(0.5)  # neutral default


def test_parse_happiness_clamps_above_range():
    data = {"objects": [{"happiness": 9.0}]}
    result = _parse_happiness(json.dumps(data))
    assert result == pytest.approx(1.0)


def test_parse_happiness_clamps_below_range():
    data = {"objects": [{"happiness": 3.0}]}
    result = _parse_happiness(json.dumps(data))
    assert result == pytest.approx(0.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "hedonometer"
    assert COLLECTOR_META["interval_s"] == 21600


# ---------------------------------------------------------------------------
# collect() integration test
# ---------------------------------------------------------------------------


async def test_collect_returns_hedonometer_happiness():
    payload = json.dumps({"objects": [{"happiness": 6.5}]})

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

    assert "hedonometer_happiness" in result
    assert result["hedonometer_happiness"] == pytest.approx(0.75)
