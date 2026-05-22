"""Tests for _synthesize_emotions() and songs_played_today reset (issues #158 / #161)."""
import pytest

from core.state import GlobalState
from core.updater import _SOURCE_SIGNAL_FIELDS, _synthesize_emotions, compute_derived


# ── Helpers ──────────────────────────────────────────────────────────────────


def _state_with_pe(**kwargs: float) -> GlobalState:
    """Return a GlobalState whose prediction_errors are set from kwargs."""
    s = GlobalState()
    s.prediction_errors.update(kwargs)
    return s


# ── Issue #158 — _synthesize_emotions ────────────────────────────────────────


def test_world_temperature_nonzero_with_active_pe() -> None:
    """world_temperature must be non-zero when prediction errors are active."""
    s = _state_with_pe(
        reddit_volume=1.0,
        twitter_volume=0.8,
        hn_ai_score=0.6,
    )
    compute_derived(s)
    assert s.world_temperature != 0.0


def test_anxiety_driven_by_openai_outage() -> None:
    """openai_status=0.0 drives anxiety > 0 via _synthesize_emotions."""
    s = GlobalState(openai_status=0.0)
    compute_derived(s)
    assert s.anxiety > 0.0


def test_emotions_clamped_to_minus_one_one() -> None:
    """Extreme PEs must not produce emotion values outside [-1.0, 1.0]."""
    s = _state_with_pe(
        reddit_volume=1_000.0,
        twitter_volume=1_000.0,
        hn_ai_score=1_000.0,
        hedonometer_happiness=1_000.0,
        google_trends_chatgpt=1_000.0,
        gdelt_conflict_intensity=1_000.0,
        newsapi_volume=1_000.0,
        fear_greed_index=1_000.0,
        reddit_sentiment=-1_000.0,
        twitter_sentiment=-1_000.0,
        newsapi_sentiment=-1_000.0,
        arxiv_papers_today=1_000.0,
        github_ai_stars=1_000.0,
        wikipedia_views_ai=1_000.0,
        media_cloud_ai_volume=1_000.0,
    )
    s.openai_status = 0.0
    compute_derived(s)
    for field in ("excitement", "anxiety", "frustration", "curiosity", "creativity"):
        val = getattr(s, field)
        assert -1.0 <= val <= 1.0, f"{field}={val} is outside [-1.0, 1.0]"


def test_emotions_zero_when_no_signals() -> None:
    """With empty PEs and default state, all five emotions must be 0.0.

    openai_status defaults to 1.0, so the anxiety term from (1 - openai_status)
    contributes 0.0 as well.
    """
    s = GlobalState()  # no PEs, openai_status=1.0
    _synthesize_emotions(s)
    for field in ("excitement", "anxiety", "frustration", "curiosity", "creativity"):
        assert getattr(s, field) == pytest.approx(0.0), f"{field} should be 0.0"


def test_source_fields_has_ten_signals() -> None:
    """_SOURCE_SIGNAL_FIELDS must contain exactly 10 signals."""
    assert len(_SOURCE_SIGNAL_FIELDS) == 10


# ── Issue #161 — songs_played_today reset ────────────────────────────────────


def test_songs_played_today_reset_on_new_day() -> None:
    """songs_played_today is reset to 0 when songs_played_today_date differs from today."""
    s = GlobalState()
    s.songs_played_today = 42
    s.songs_played_today_date = "1970-01-01"  # deliberately old date
    compute_derived(s)
    assert s.songs_played_today == 0


def test_songs_played_today_not_reset_same_day() -> None:
    """songs_played_today must NOT be zeroed when the date is already today."""
    from datetime import datetime, timezone

    s = GlobalState()
    s.songs_played_today = 7
    s.songs_played_today_date = datetime.now(timezone.utc).date().isoformat()
    compute_derived(s)
    assert s.songs_played_today == 7
