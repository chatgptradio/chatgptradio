"""Tests for collectors/media_cloud.py."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from collectors.media_cloud import (
    COLLECTOR_META,
    _story_count_sync,
    collect,
)
from core.state import GlobalState

_START = date(2026, 5, 19)
_END = date(2026, 5, 20)


# ---------------------------------------------------------------------------
# _story_count_sync unit tests (mocked mediacloud SearchApi)
# ---------------------------------------------------------------------------


def test_story_count_sync_returns_integer():
    mock_mc = MagicMock()
    mock_mc.story_count.return_value = {"count": 42}

    mock_mc_api = MagicMock()
    mock_mc_api.SearchApi.return_value = mock_mc

    with patch.dict("sys.modules", {"mediacloud.api": mock_mc_api}):
        result = _story_count_sync("key", _START, _END)

    assert result == 42


def test_story_count_sync_handles_dict_result():
    """SearchApi.story_count returns a StoryCount dict with a 'count' key."""
    mock_mc = MagicMock()
    mock_mc.story_count.return_value = {"count": 77}

    mock_mc_api = MagicMock()
    mock_mc_api.SearchApi.return_value = mock_mc

    with patch.dict("sys.modules", {"mediacloud.api": mock_mc_api}):
        result = _story_count_sync("key", _START, _END)

    assert result == 77


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
async def test_collect_count_500_normalized():
    # 500 / 1000 = 0.5
    with patch.dict("os.environ", {"MEDIA_CLOUD_API_KEY": "testkey"}):
        with patch("collectors.media_cloud._story_count_sync", return_value=500):
            result = await collect(GlobalState())

    assert "media_cloud_ai_volume" in result
    assert result["media_cloud_ai_volume"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_collect_count_zero_returns_zero():
    with patch.dict("os.environ", {"MEDIA_CLOUD_API_KEY": "testkey"}):
        with patch("collectors.media_cloud._story_count_sync", return_value=0):
            result = await collect(GlobalState())

    assert result["media_cloud_ai_volume"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_collect_count_exceeds_max_clamped_to_one():
    # 2000 > 1000 max → 1.0
    with patch.dict("os.environ", {"MEDIA_CLOUD_API_KEY": "testkey"}):
        with patch("collectors.media_cloud._story_count_sync", return_value=2000):
            result = await collect(GlobalState())

    assert result["media_cloud_ai_volume"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_collect_value_in_range():
    with patch.dict("os.environ", {"MEDIA_CLOUD_API_KEY": "testkey"}):
        with patch("collectors.media_cloud._story_count_sync", return_value=123):
            result = await collect(GlobalState())

    assert 0.0 <= result["media_cloud_ai_volume"] <= 1.0


# ---------------------------------------------------------------------------
# COLLECTOR_META
# ---------------------------------------------------------------------------


def test_collector_meta():
    assert COLLECTOR_META["name"] == "media_cloud"
    assert COLLECTOR_META["interval_s"] == 900
