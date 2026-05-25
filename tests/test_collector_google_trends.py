"""Tests for collectors/google_trends.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.google_trends import COLLECTOR_META, _parse_trends, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# _parse_trends unit tests
# ---------------------------------------------------------------------------

_RSS_WITH_HITS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>ChatGPT breaks record again</title></item>
    <item><title>OpenAI launches new model</title></item>
    <item><title>ChatGPT used in schools</title></item>
    <item><title>Stock market rally</title></item>
    <item><title>OpenAI raises funding</title></item>
  </channel>
</rss>"""

_RSS_NO_AI = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>Football results</title></item>
    <item><title>Weather forecast</title></item>
  </channel>
</rss>"""

_RSS_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel></channel></rss>"""


def test_parse_trends_with_hits():
    chatgpt, openai = _parse_trends(_RSS_WITH_HITS)
    # 2 ChatGPT items, 2 OpenAI items out of 5
    assert chatgpt == pytest.approx(2 / 10)
    assert openai == pytest.approx(2 / 10)


def test_parse_trends_no_ai_mentions():
    chatgpt, openai = _parse_trends(_RSS_NO_AI)
    assert chatgpt == pytest.approx(0.0)
    assert openai == pytest.approx(0.0)


def test_parse_trends_empty_feed():
    chatgpt, openai = _parse_trends(_RSS_EMPTY)
    assert chatgpt == pytest.approx(0.0)
    assert openai == pytest.approx(0.0)


def test_parse_trends_clamps_high_count():
    items = "\n".join(f"<item><title>ChatGPT OpenAI story {i}</title></item>" for i in range(20))
    rss = f"""<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>"""
    chatgpt, openai = _parse_trends(rss)
    assert chatgpt == pytest.approx(1.0)
    assert openai == pytest.approx(1.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "google_trends"
    assert COLLECTOR_META["interval_s"] == 900


# ---------------------------------------------------------------------------
# collect() integration test
# ---------------------------------------------------------------------------


async def test_collect_returns_both_fields():
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=_RSS_WITH_HITS)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("collectors.utils.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert "google_trends_chatgpt" in result
    assert "google_trends_openai" in result
    assert 0.0 <= result["google_trends_chatgpt"] <= 1.0
    assert 0.0 <= result["google_trends_openai"] <= 1.0
