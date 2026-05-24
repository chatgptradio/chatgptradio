"""Tests for the enriched DSP effects chain — crisis hierarchy, LadderFilter, Delay, Phaser."""

from core.state import GlobalState


def _chain(state: GlobalState):
    from core.dsp import _build_chain
    return list(_build_chain(state))


# ---------------------------------------------------------------------------
# Crisis hierarchy — tier 3 (GSMFullRateCompressor)
# ---------------------------------------------------------------------------

def test_crisis_tier3_gsm_active() -> None:
    """crisis_level=0.8 is above the 0.71 threshold — GSMFullRateCompressor must be present."""
    from pedalboard import GSMFullRateCompressor
    chain = _chain(GlobalState(crisis_level=0.8))
    assert any(isinstance(e, GSMFullRateCompressor) for e in chain)


def test_no_crisis_no_gsm() -> None:
    """crisis_level=0.2 is well below threshold — GSMFullRateCompressor must be absent."""
    from pedalboard import GSMFullRateCompressor
    chain = _chain(GlobalState(crisis_level=0.2))
    assert not any(isinstance(e, GSMFullRateCompressor) for e in chain)


# ---------------------------------------------------------------------------
# Crisis hierarchy — tier 4 (MP3Compressor + Bitcrush)
# ---------------------------------------------------------------------------

def test_crisis_tier4_bitcrush_active() -> None:
    """crisis_level=0.95 exceeds the 0.91 threshold — Bitcrush must be present."""
    from pedalboard import Bitcrush
    chain = _chain(GlobalState(crisis_level=0.95))
    assert any(isinstance(e, Bitcrush) for e in chain)


def test_crisis_tier4_mp3_active() -> None:
    """crisis_level=0.95 — MP3Compressor must also be present alongside Bitcrush."""
    from pedalboard import MP3Compressor
    chain = _chain(GlobalState(crisis_level=0.95))
    assert any(isinstance(e, MP3Compressor) for e in chain)


def test_crisis_tier4_absent_below_threshold() -> None:
    """crisis_level=0.85 is above tier-3 but below tier-4 threshold — no Bitcrush."""
    from pedalboard import Bitcrush
    chain = _chain(GlobalState(crisis_level=0.85))
    assert not any(isinstance(e, Bitcrush) for e in chain)


# ---------------------------------------------------------------------------
# Territory-conditional effects — Delay
# ---------------------------------------------------------------------------

def test_psych_territory_has_delay() -> None:
    """drift_territory='psych' must include a Delay in the chain."""
    from pedalboard import Delay
    chain = _chain(GlobalState(drift_territory="psych"))
    assert any(isinstance(e, Delay) for e in chain)


def test_experimental_territory_has_delay() -> None:
    """drift_territory='experimental' must also include Delay."""
    from pedalboard import Delay
    chain = _chain(GlobalState(drift_territory="experimental"))
    assert any(isinstance(e, Delay) for e in chain)


def test_electronic_territory_no_delay() -> None:
    """drift_territory='electronic' is not psych/experimental — Delay must be absent."""
    from pedalboard import Delay
    chain = _chain(GlobalState(drift_territory="electronic"))
    assert not any(isinstance(e, Delay) for e in chain)


def test_ambient_territory_no_delay() -> None:
    """Default territory 'ambient' must not include Delay (NO FAKE)."""
    from pedalboard import Delay
    chain = _chain(GlobalState())
    assert not any(isinstance(e, Delay) for e in chain)


# ---------------------------------------------------------------------------
# Territory-conditional effects — Phaser
# ---------------------------------------------------------------------------

def test_psych_territory_has_phaser() -> None:
    """drift_territory='psych' must include a Phaser in the chain."""
    from pedalboard import Phaser
    chain = _chain(GlobalState(drift_territory="psych"))
    assert any(isinstance(e, Phaser) for e in chain)


def test_electronic_territory_no_phaser() -> None:
    """drift_territory='electronic' — Phaser must be absent."""
    from pedalboard import Phaser
    chain = _chain(GlobalState(drift_territory="electronic"))
    assert not any(isinstance(e, Phaser) for e in chain)


# ---------------------------------------------------------------------------
# LadderFilter — always present
# ---------------------------------------------------------------------------

def test_ladder_filter_always_present() -> None:
    """LadderFilter must be in the chain regardless of state."""
    from pedalboard import LadderFilter
    assert any(isinstance(e, LadderFilter) for e in _chain(GlobalState()))


def test_ladder_filter_present_in_crisis() -> None:
    """LadderFilter must still be present even at maximum crisis."""
    from pedalboard import LadderFilter
    chain = _chain(GlobalState(crisis_level=1.0))
    assert any(isinstance(e, LadderFilter) for e in chain)


def test_ladder_filter_present_in_psych() -> None:
    """LadderFilter must be present in psych territory."""
    from pedalboard import LadderFilter
    chain = _chain(GlobalState(drift_territory="psych"))
    assert any(isinstance(e, LadderFilter) for e in chain)


# ---------------------------------------------------------------------------
# Limiter — always last
# ---------------------------------------------------------------------------

def test_chain_ends_with_limiter() -> None:
    """The last effect in the chain must always be a Limiter."""
    from pedalboard import Limiter
    chain = _chain(GlobalState())
    assert isinstance(chain[-1], Limiter)


def test_chain_ends_with_limiter_in_full_crisis() -> None:
    """Limiter must remain last even at maximum crisis with all tiers active."""
    from pedalboard import Limiter
    chain = _chain(GlobalState(crisis_level=1.0, drift_territory="psych"))
    assert isinstance(chain[-1], Limiter)


# ---------------------------------------------------------------------------
# Chain order sanity — LadderFilter before Delay/Phaser/GSM
# ---------------------------------------------------------------------------

def test_ladder_filter_before_delay_in_psych() -> None:
    """LadderFilter must appear before Delay in psych territory."""
    from pedalboard import Delay, LadderFilter
    chain = _chain(GlobalState(drift_territory="psych"))
    ladder_idx = next(i for i, e in enumerate(chain) if isinstance(e, LadderFilter))
    delay_idx = next(i for i, e in enumerate(chain) if isinstance(e, Delay))
    assert ladder_idx < delay_idx


def test_gsm_before_limiter() -> None:
    """GSMFullRateCompressor must appear before the final Limiter."""
    from pedalboard import GSMFullRateCompressor, Limiter
    chain = _chain(GlobalState(crisis_level=0.8))
    gsm_idx = next(i for i, e in enumerate(chain) if isinstance(e, GSMFullRateCompressor))
    limiter_idx = next(i for i, e in enumerate(chain) if isinstance(e, Limiter))
    assert gsm_idx < limiter_idx
