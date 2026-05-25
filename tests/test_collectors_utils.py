"""Tests for collectors/utils.py — vader_sentiment, normalize, fetch_text."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from collectors.utils import fetch_text, normalize, vader_sentiment


# ---------------------------------------------------------------------------
# vader_sentiment
# ---------------------------------------------------------------------------


def test_vader_positive_text():
    score = vader_sentiment("I love this! It is absolutely wonderful and fantastic.")
    assert score > 0.0


def test_vader_negative_text():
    score = vader_sentiment("This is terrible, awful, and utterly dreadful.")
    assert score < 0.0


def test_vader_empty_string():
    assert vader_sentiment("") == 0.0


def test_vader_whitespace_only():
    assert vader_sentiment("   ") == 0.0


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_midpoint():
    assert normalize(5.0, 0.0, 10.0) == pytest.approx(0.5)


def test_normalize_lower_bound():
    assert normalize(0.0, 0.0, 10.0) == pytest.approx(0.0)


def test_normalize_upper_bound():
    assert normalize(10.0, 0.0, 10.0) == pytest.approx(1.0)


def test_normalize_clamp_below_low():
    assert normalize(-5.0, 0.0, 10.0) == pytest.approx(0.0)


def test_normalize_clamp_above_high():
    assert normalize(20.0, 0.0, 10.0) == pytest.approx(1.0)


def test_normalize_degenerate_range():
    assert normalize(7.0, 3.0, 3.0) == pytest.approx(0.5)


def test_normalize_arbitrary_range():
    # val=3 in [2, 4] → (3-2)/(4-2) = 0.5
    assert normalize(3.0, 2.0, 4.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# fetch_text
# ---------------------------------------------------------------------------


def _make_mock_session(body: str = "hello", raise_for_status: bool = False) -> MagicMock:
    """Build a mock aiohttp.ClientSession context manager."""
    mock_resp = AsyncMock()
    if raise_for_status:
        mock_resp.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=404,
            )
        )
    else:
        mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return mock_session


async def test_fetch_text_success():
    mock_session = _make_mock_session(body="response body")
    with patch("collectors.utils.aiohttp.ClientSession", return_value=mock_session):
        result = await fetch_text("https://example.com/data")
    assert result == "response body"


async def test_fetch_text_http_error_raises():
    mock_session = _make_mock_session(raise_for_status=True)
    with patch("collectors.utils.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(aiohttp.ClientResponseError):
            await fetch_text("https://example.com/missing")


async def test_fetch_text_passes_timeout():
    """Verify timeout_s is forwarded to aiohttp.ClientTimeout."""
    mock_session = _make_mock_session(body="ok")
    with patch("collectors.utils.aiohttp.ClientSession", return_value=mock_session):
        with patch("collectors.utils.aiohttp.ClientTimeout") as mock_timeout:
            await fetch_text("https://example.com/", timeout_s=5.0)
    mock_timeout.assert_called_once_with(total=5.0)
