"""Tests for core/track_namer.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.state import GlobalState


def _make_state(**kwargs) -> GlobalState:
    state = GlobalState()
    for k, v in kwargs.items():
        setattr(state, k, v)
    return state


@pytest.mark.asyncio
async def test_generate_track_name_valid_response():
    """Valid GPT response → 'Artist - Title'."""
    state = _make_state(drift_territory="ambient", drift_bpm=80.0, drift_key="C minor")
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = '{"artist": "Void Cartographer", "title": "Cold Signal"}'

    with patch("core.track_namer.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from core.track_namer import generate_track_name
            result = await generate_track_name(state)

    assert result == "Void Cartographer - Cold Signal"


@pytest.mark.asyncio
async def test_generate_track_name_missing_key():
    """JSON missing 'title' key → empty string, no raise."""
    state = _make_state()
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = '{"artist": "Only Artist"}'

    with patch("core.track_namer.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from core.track_namer import generate_track_name
            result = await generate_track_name(state)

    assert result == ""


@pytest.mark.asyncio
async def test_generate_track_name_api_error():
    """API exception → empty string, no raise."""
    state = _make_state()

    with patch("core.track_namer.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from core.track_namer import generate_track_name
            result = await generate_track_name(state)

    assert result == ""


@pytest.mark.asyncio
async def test_generate_track_name_no_api_key():
    """Missing OPENAI_API_KEY → empty string immediately, no API call."""
    state = _make_state()

    with patch("core.track_namer.openai.AsyncOpenAI") as mock_cls:
        import os
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            from core.track_namer import generate_track_name
            result = await generate_track_name(state)

    mock_cls.assert_not_called()
    assert result == ""


@pytest.mark.asyncio
async def test_generate_track_name_returns_str():
    """Return type is always str."""
    state = _make_state()
    with patch.dict("os.environ", {}, clear=True):
        from core.track_namer import generate_track_name
        result = await generate_track_name(state)
    assert isinstance(result, str)


def test_emotion_order_length():
    """_EMOTION_ORDER has exactly 8 entries."""
    from core.track_namer import _EMOTION_ORDER
    assert len(_EMOTION_ORDER) == 8


def test_wonder_in_top2_dominant_emotions():
    """wonder with high prediction_error and low volatility appears in top-2 dominant emotions."""
    from core.track_namer import _EMOTION_ORDER

    state = _make_state(
        prediction_errors={"wonder": 2.0},
        signal_volatilities={"wonder": 0.1},
    )

    pe = state.prediction_errors
    vol = state.signal_volatilities

    def sig(k: str) -> float:
        return abs(pe.get(k, 0.0)) / max(vol.get(k, 0.1), 0.001)

    top2 = sorted(_EMOTION_ORDER, key=sig, reverse=True)[:2]
    assert "wonder" in top2
