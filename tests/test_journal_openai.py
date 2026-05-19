"""Tests verifying journal.py uses OpenAI SDK, not the legacy provider."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import core.journal as jmod
from core.state import GlobalState


def test_uses_openai_not_anthropic() -> None:
    """journal.py must use openai.AsyncOpenAI, not the legacy LLM SDK."""
    assert not hasattr(jmod, "anthropic"), "anthropic must not be imported"
    assert hasattr(jmod, "openai"), "openai module must be imported in journal"


@pytest.mark.asyncio
async def test_journal_uses_gpt4o() -> None:
    """Journal must use gpt-4o model and contain no legacy provider references."""
    source = open(jmod.__file__).read()
    assert "gpt-4o" in source, "gpt-4o model must be referenced in journal.py"
    assert "claude" not in source.lower(), "no legacy model references allowed"
    assert "anthropic" not in source.lower(), "anthropic must not appear in journal.py"


def test_build_user_prompt_english_labels() -> None:
    """_build_user_prompt must use English labels."""
    state = GlobalState()
    prompt = jmod._build_user_prompt(state)
    assert "UTC time:" in prompt
    assert "Drift territory:" in prompt
    assert "Dominant emotion:" in prompt
    # Ensure French labels are gone
    assert "Heure UTC" not in prompt
    assert "Territoire de d" not in prompt
    assert "motion dominante" not in prompt


def test_system_prompt_is_english() -> None:
    """_SYSTEM prompt must be in English."""
    assert "You are" in jmod._SYSTEM
    assert "Tu es" not in jmod._SYSTEM


@pytest.mark.asyncio
async def test_run_journal_uses_openai_client() -> None:
    """run_journal must instantiate AsyncOpenAI with OPENAI_API_KEY."""
    import asyncio
    import os

    state = GlobalState()
    queue: asyncio.Queue = asyncio.Queue()

    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.journal_entries = []
    mock_ctx.signal_trends = {}
    mock_ctx.recognized_viewers = []

    mock_choice = MagicMock()
    mock_choice.message.content = "[12:00] Signal nominal."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch("core.journal.load_memory_context", new=AsyncMock(return_value=mock_ctx)):
            with patch("core.journal.save_journal_entry", new=AsyncMock()):
                with patch("openai.AsyncOpenAI") as mock_openai_cls:
                    mock_client = AsyncMock()
                    mock_client.chat = MagicMock()
                    mock_client.chat.completions = MagicMock()
                    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
                    mock_openai_cls.return_value = mock_client

                    # Inject a high crisis level to trigger immediate generation
                    state.crisis_level = 1.0
                    # Patch asyncio.sleep to break after one iteration
                    call_count = 0

                    async def fake_sleep(_: float) -> None:
                        nonlocal call_count
                        call_count += 1
                        if call_count >= 1:
                            raise asyncio.CancelledError

                    with patch("asyncio.sleep", side_effect=fake_sleep):
                        try:
                            await jmod.run_journal(state, queue, mock_conn)
                        except asyncio.CancelledError:
                            pass

                    mock_openai_cls.assert_called_once_with(api_key="test-key")
                    mock_client.chat.completions.create.assert_called_once()
                    call_kwargs = mock_client.chat.completions.create.call_args
                    assert call_kwargs.kwargs.get("model") == "gpt-4o"
