"""Tests for collectors/arxiv.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


from collectors.arxiv import COLLECTOR_META, _parse_arxiv, collect
from core.state import GlobalState


# ---------------------------------------------------------------------------
# Helper: build minimal Atom XML
# ---------------------------------------------------------------------------

_ATOM_NS = "http://www.w3.org/2005/Atom"


def _make_atom(published_times: list[datetime]) -> str:
    entries = ""
    for dt in published_times:
        iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        entries += f"<entry xmlns='{_ATOM_NS}'><published>{iso}</published></entry>\n"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="{_ATOM_NS}">
{entries}
</feed>"""


# ---------------------------------------------------------------------------
# _parse_arxiv unit tests
# ---------------------------------------------------------------------------


def test_parse_arxiv_all_recent():
    now = datetime.now(timezone.utc)
    times = [now - timedelta(hours=i) for i in range(5)]
    result = _parse_arxiv(_make_atom(times))
    assert result == 5


def test_parse_arxiv_none_recent():
    now = datetime.now(timezone.utc)
    times = [now - timedelta(hours=48), now - timedelta(hours=36)]
    result = _parse_arxiv(_make_atom(times))
    assert result == 0


def test_parse_arxiv_mixed():
    now = datetime.now(timezone.utc)
    times = [
        now - timedelta(hours=2),    # recent
        now - timedelta(hours=12),   # recent
        now - timedelta(hours=30),   # old
    ]
    result = _parse_arxiv(_make_atom(times))
    assert result == 2


def test_parse_arxiv_empty_feed():
    xml = f'<?xml version="1.0"?><feed xmlns="{_ATOM_NS}"></feed>'
    result = _parse_arxiv(xml)
    assert result == 0


def test_parse_arxiv_malformed_date_skipped():
    xml = f"""<?xml version="1.0"?>
<feed xmlns="{_ATOM_NS}">
  <entry><published>NOT-A-DATE</published></entry>
  <entry><published>{(datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}</published></entry>
</feed>"""
    result = _parse_arxiv(xml)
    assert result == 1


def test_collector_meta():
    assert COLLECTOR_META["name"] == "arxiv"
    assert COLLECTOR_META["interval_s"] == 3600


# ---------------------------------------------------------------------------
# collect() integration test
# ---------------------------------------------------------------------------


async def test_collect_returns_arxiv_papers_today():
    now = datetime.now(timezone.utc)
    times = [now - timedelta(hours=i) for i in range(10)]
    payload = _make_atom(times)

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

    assert "arxiv_papers_today" in result
    assert isinstance(result["arxiv_papers_today"], int)
    assert result["arxiv_papers_today"] == 10
