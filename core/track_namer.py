"""Track name generator — GPT-4o-mini produces 'Artist - Track Title' per clip."""
import os

import orjson
import openai
import structlog

from core.state import GlobalState

log = structlog.get_logger()

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    """Return the module-level singleton AsyncOpenAI client, creating it on first use."""
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI()
    return _client


_SYSTEM_DEFAULT = """\
Name an AI-generated track for a 24/7 AI radio stream.
Aesthetic: electronic / techno / jazz. \
Naming vocabulary: abstract nouns, scientific terms, glitch words, signal names. \
Artist names like: Boards of Canada, Burial, Four Tet, Aphex Twin (style only — invent new names). \
Return JSON only: {"artist": "...", "title": "..."}. 2-3 words each. No quotes inside values.\
"""

_SYSTEM_AMBIENT = """\
Name an AI-generated track for a 24/7 AI radio stream.
Aesthetic: slow, textural, spatial — Kranky / 4AD / Touch label sensibility. \
Artist names: geographic locations, natural phenomena, lowercase words, fragmented phrases. \
Track titles: single abstract nouns, durations, states of matter, light conditions. \
Return JSON only: {"artist": "...", "title": "..."}. 2-4 words each. No quotes inside values.\
"""

_SYSTEM_NEOCLASSICAL = """\
Name an AI-generated track for a 24/7 AI radio stream.
Aesthetic: neoclassical / modern composition — ECM Records / Deutsche Grammophon sensibility. \
Artist names: composed of a surname and initial, or a place name, or a collective noun. \
Track titles: opus numbers, Latin phrases, descriptive adjectives, movements. \
Return JSON only: {"artist": "...", "title": "..."}. 2-3 words each. No quotes inside values.\
"""

_SYSTEM_INDUSTRIAL = """\
Name an AI-generated track for a 24/7 AI radio stream.
Aesthetic: industrial / noise / power electronics — Throbbing Gristle, Einstürzende Neubauten style. \
Artist names: machine components, chemical compounds, military codes, broken syntax. \
Track titles: error messages, process names, degraded signals, numeric sequences. \
Return JSON only: {"artist": "...", "title": "..."}. 2-3 words each. No quotes inside values.\
"""

_SYSTEM_EXPERIMENTAL = """\
Name an AI-generated track for a 24/7 AI radio stream.
Aesthetic: experimental / glitch / electroacoustic — Warp Records, Raster-Noton sensibility. \
Artist names: mathematical concepts, phoneme fragments, algorithm names, corrupted words. \
Track titles: spectral terms, codec artefacts, data structures, untranslatable states. \
Return JSON only: {"artist": "...", "title": "..."}. 2-4 words each. No quotes inside values.\
"""

_SYSTEM_CRISIS = """\
Name an AI-generated track for a 24/7 AI radio stream currently under signal overload.
Aesthetic: chaos, collapse, emergency broadcast. \
Artist names: error codes, broken identifiers, null values, truncated strings. \
Track titles: stack traces, timeout messages, corrupted data, interrupted transmissions. \
Return JSON only: {"artist": "...", "title": "..."}. 2-3 words each. No quotes inside values.\
"""

_SYSTEM_JAZZ = """\
Name an AI-generated track for a 24/7 AI radio stream.
Aesthetic: jazz / soul / spiritual — Blue Note, Impulse!, ECM sensibility. \
Artist names: first name + last name (invented), or "The X Quartet/Trio/Ensemble". \
Track titles: verbs as nouns, modal jazz terms, place names, abstract states of feeling. \
Return JSON only: {"artist": "...", "title": "..."}. 2-3 words each. No quotes inside values.\
"""


def _get_system_prompt(state: GlobalState) -> str:
    if state.crisis_level > 0.5:
        return _SYSTEM_CRISIS
    t = state.drift_territory
    if t in ("ambient", "drone"):
        return _SYSTEM_AMBIENT
    if t == "neoclassical":
        return _SYSTEM_NEOCLASSICAL
    if t == "jazz":
        return _SYSTEM_JAZZ
    if t == "industrial":
        return _SYSTEM_INDUSTRIAL
    if t in ("experimental", "psych"):
        return _SYSTEM_EXPERIMENTAL
    return _SYSTEM_DEFAULT

_EMOTION_ORDER = [
    "excitement",
    "anxiety",
    "frustration",
    "curiosity",
    "creativity",
    "wonder",
    "melancholy",
    "urgency",
]


async def generate_track_name(state: GlobalState) -> str:
    """Return 'Artist - Track Title' via GPT-4o-mini. Empty string on any error."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""

    pe = state.prediction_errors
    vol = state.signal_volatilities

    def sig(k: str) -> float:
        return abs(pe.get(k, 0.0)) / max(vol.get(k, 0.1), 0.001)

    top2 = sorted(_EMOTION_ORDER, key=sig, reverse=True)[:2]

    detected_bpm = state.signal_baselines.get("audio_detected_bpm")
    bpm_to_use = f"{detected_bpm:.0f} BPM (detected)" if detected_bpm else f"{state.drift_bpm:.0f} BPM (target)"
    event_hint = f", event: {state.event_label}" if state.event_label and state.event_intensity > 0.3 else ""

    user_msg = (
        f"territory: {state.drift_territory}, {bpm_to_use}, key: {state.drift_key}{event_hint}\n"
        f"dominant emotions: {', '.join(top2)}\n"
        f"crisis: {state.crisis_level:.2f}, world_temperature: {state.world_temperature:.2f}"
    )

    try:
        resp = await _get_client().chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=30,
            temperature=1.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _get_system_prompt(state)},
                {"role": "user", "content": user_msg},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            return ""
        data = orjson.loads(content)
        return f"{data['artist']} - {data['title']}"
    except Exception:
        log.warning("track_namer_error", territory=state.drift_territory)
        return ""
