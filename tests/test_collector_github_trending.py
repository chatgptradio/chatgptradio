"""Tests for collectors/github_trending.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.github_trending import COLLECTOR_META, _sum_stars, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _sum_stars unit tests
# ---------------------------------------------------------------------------


def test_sum_stars_ten_repos():
    data = {"items": [{"stargazers_count": 50_000} for _ in range(10)]}
    assert _sum_stars(data) == pytest.approx(500_000.0)


def test_sum_stars_empty_items():
    data = {"items": []}
    assert _sum_stars(data) == pytest.approx(0.0)


def test_sum_stars_missing_items_key():
    data = {}
    assert _sum_stars(data) == pytest.approx(0.0)


def test_sum_stars_missing_stargazers_count():
    data = {"items": [{"name": "repo-without-stars"}]}
    assert _sum_stars(data) == pytest.approx(0.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "github_trending"
    assert COLLECTOR_META["interval_s"] == 3600


# ---------------------------------------------------------------------------
# collect() integration tests with mocked HTTP
# ---------------------------------------------------------------------------


def _make_mock_session(response_data: dict):
    """Build an aiohttp mock that returns *response_data* as JSON."""
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=response_data)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session


@pytest.mark.asyncio
async def test_collect_ten_repos_returns_normalized_value():
    data = {"items": [{"stargazers_count": 200_000} for _ in range(10)]}
    # total = 2_000_000 / 5_000_000 = 0.4
    mock_session = _make_mock_session(data)

    with patch("collectors.github_trending.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert "github_ai_stars" in result
    assert 0.0 <= result["github_ai_stars"] <= 1.0
    assert result["github_ai_stars"] == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_collect_empty_results_returns_zero():
    data = {"items": []}
    mock_session = _make_mock_session(data)

    with patch("collectors.github_trending.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert "github_ai_stars" in result
    assert result["github_ai_stars"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_collect_clamps_to_one_when_stars_exceed_max():
    # 10 repos with 1_000_000 stars each = 10_000_000 > 5_000_000 max
    data = {"items": [{"stargazers_count": 1_000_000} for _ in range(10)]}
    mock_session = _make_mock_session(data)

    with patch("collectors.github_trending.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert result["github_ai_stars"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_collect_http_error_propagates():
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock(
        side_effect=Exception("403 Forbidden")
    )
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("collectors.github_trending.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception, match="403"):
            await collect(GlobalState())
