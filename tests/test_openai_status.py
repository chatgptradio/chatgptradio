from unittest.mock import AsyncMock, patch, MagicMock

from collectors.openai_status import _parse_status, COLLECTOR_META


_OUTAGE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Major Outage - API Unavailable</title>
      <pubDate>Sat, 17 May 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_DEGRADED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Degraded Performance - Elevated Error Rates</title>
      <pubDate>Sat, 17 May 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_OK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Resolved - API services operational</title>
      <pubDate>Sat, 17 May 2026 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_EMPTY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel></channel></rss>"""


def test_parse_major_outage():
    status, age = _parse_status(_OUTAGE_RSS)
    assert status == 0.0


def test_parse_degraded():
    status, age = _parse_status(_DEGRADED_RSS)
    assert status == 0.5


def test_parse_ok():
    status, age = _parse_status(_OK_RSS)
    assert status == 1.0
    assert age >= 0.0


def test_parse_empty_feed():
    status, age = _parse_status(_EMPTY_RSS)
    assert status == 1.0
    assert age == 0.0


def test_collector_meta_present():
    assert COLLECTOR_META["name"] == "openai_status"
    assert COLLECTOR_META["interval_s"] == 30


async def test_collect_returns_correct_keys_on_success():
    from collectors.openai_status import collect
    from core.state import GlobalState

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=_OK_RSS)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("collectors.openai_status.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert "openai_status" in result
    assert "openai_incident_age_h" in result
    assert "openai_latency_ms" in result
    assert result["openai_status"] == 1.0
    assert result["openai_latency_ms"] >= 0.0


async def test_collect_outage_returns_zero():
    from collectors.openai_status import collect
    from core.state import GlobalState

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=_OUTAGE_RSS)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("collectors.openai_status.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert result["openai_status"] == 0.0
    assert "openai_latency_ms" in result
    assert result["openai_latency_ms"] >= 0.0


async def test_collect_latency_ms_is_positive():
    from collectors.openai_status import collect
    from core.state import GlobalState

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=_OK_RSS)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("collectors.openai_status.aiohttp.ClientSession", return_value=mock_session):
        result = await collect(GlobalState())

    assert result["openai_latency_ms"] > 0.0
