"""Tests for collectors/yfinance_proxy.py."""

from unittest.mock import MagicMock, patch

import pytest

from collectors.yfinance_proxy import COLLECTOR_META, _get_delta, _normalise_delta, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _get_delta unit tests
# ---------------------------------------------------------------------------


def test_get_delta_positive():
    mock_info = {"lastPrice": 110.0, "previousClose": 100.0}
    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_info

    with patch("collectors.yfinance_proxy.yf.Ticker", return_value=mock_ticker):
        delta = _get_delta("MSFT")

    assert delta == pytest.approx(0.1)


def test_get_delta_negative():
    mock_info = {"lastPrice": 90.0, "previousClose": 100.0}
    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_info

    with patch("collectors.yfinance_proxy.yf.Ticker", return_value=mock_ticker):
        delta = _get_delta("NVDA")

    assert delta == pytest.approx(-0.1)


def test_get_delta_zero_prev_close_returns_zero():
    mock_info = {"lastPrice": 100.0, "previousClose": 0.0}
    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_info

    with patch("collectors.yfinance_proxy.yf.Ticker", return_value=mock_ticker):
        delta = _get_delta("MSFT")

    assert delta == pytest.approx(0.0)


def test_get_delta_missing_price_returns_zero():
    mock_info = {}
    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_info

    with patch("collectors.yfinance_proxy.yf.Ticker", return_value=mock_ticker):
        delta = _get_delta("MSFT")

    assert delta == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _normalise_delta unit tests
# ---------------------------------------------------------------------------


def test_normalise_delta_flat():
    assert _normalise_delta(0.0) == pytest.approx(0.5)


def test_normalise_delta_max_gain():
    assert _normalise_delta(0.1) == pytest.approx(1.0)


def test_normalise_delta_max_loss():
    assert _normalise_delta(-0.1) == pytest.approx(0.0)


def test_normalise_delta_clamps_extreme():
    assert _normalise_delta(0.5) == pytest.approx(1.0)
    assert _normalise_delta(-0.5) == pytest.approx(0.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "yfinance_proxy"
    assert COLLECTOR_META["interval_s"] == 14400


# ---------------------------------------------------------------------------
# collect() integration test
# ---------------------------------------------------------------------------


async def test_collect_returns_both_fields():
    def mock_get_delta(ticker: str) -> float:
        return 0.05 if ticker == "MSFT" else -0.03

    with patch("collectors.yfinance_proxy._get_delta", side_effect=mock_get_delta):
        result = await collect(GlobalState())

    assert "msft_delta" in result
    assert "nvda_delta" in result
    assert 0.0 <= result["msft_delta"] <= 1.0
    assert 0.0 <= result["nvda_delta"] <= 1.0
    assert result["msft_delta"] == pytest.approx(0.75)   # 0.05 in [-0.1, 0.1]
    assert result["nvda_delta"] == pytest.approx(0.35)   # -0.03 in [-0.1, 0.1]
