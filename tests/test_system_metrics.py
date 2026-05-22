"""Tests for collectors/system_metrics.py."""

import pytest

from collectors.system_metrics import collect
from core.state import GlobalState


@pytest.mark.asyncio
async def test_collect_returns_required_fields():
    state = GlobalState()
    result = await collect(state)
    assert "hour_utc" in result
    assert "day_of_week" in result
    assert "cpu_percent" in result
    assert "memory_percent" in result
    assert "uptime_h" in result


@pytest.mark.asyncio
async def test_hour_utc_in_range():
    state = GlobalState()
    result = await collect(state)
    assert 0 <= result["hour_utc"] <= 23


@pytest.mark.asyncio
async def test_uptime_h_positive():
    state = GlobalState()
    result = await collect(state)
    assert result["uptime_h"] >= 0


@pytest.mark.asyncio
async def test_day_of_week_in_range():
    state = GlobalState()
    result = await collect(state)
    assert 0 <= result["day_of_week"] <= 6


@pytest.mark.asyncio
async def test_cpu_percent_normalised():
    """cpu_percent must be in [0, 1]."""
    state = GlobalState()
    result = await collect(state)
    assert 0.0 <= result["cpu_percent"] <= 1.0


@pytest.mark.asyncio
async def test_memory_percent_normalised():
    """memory_percent must be in [0, 1]."""
    state = GlobalState()
    result = await collect(state)
    assert 0.0 <= result["memory_percent"] <= 1.0
