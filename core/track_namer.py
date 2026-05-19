"""Track name generator — GPT-4o-mini produces 'Artist - Track Title' per clip."""
import json
import os

import openai
import structlog

from core.state import GlobalState

log = structlog.get_logger()

_SYSTEM = """\
You name AI-generated music tracks for a 24/7 AI radio stream.
Given the emotional state of the stream, invent a fictional artist name and a track title.
Return JSON only: {"artist": "...", "title": "..."}.
2-3 words each. English. Evocative, slightly cryptic. No quotes inside values.\
"""

_EMOTION_ORDER = [
    "excitation", "anxiete", "frustration", "curiosite",
    "creativite", "emerveillement", "melancolie", "urgence",
]
_EMOTION_EN: dict[str, str] = {
    "excitation": "excitement",
    "anxiete": "anxiety",
    "frustration": "frustration",
    "curiosite": "curiosity",
    "creativite": "creativity",
    "emerveillement": "wonder",
    "melancolie": "melancholy",
    "urgence": "urgency",
}


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
    top2_en = [_EMOTION_EN[e] for e in top2]

    user_msg = (
        f"territory: {state.drift_territory}, BPM: {state.drift_bpm:.0f}, key: {state.drift_key}\n"
        f"dominant emotions: {', '.join(top2_en)}\n"
        f"crisis: {state.crisis_level:.2f}, world_temperature: {state.world_temperature:.2f}"
    )

    try:
        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=20,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            return ""
        data = json.loads(content)
        return f"{data['artist']} - {data['title']}"
    except Exception:
        log.warning("track_namer_error", territory=state.drift_territory)
        return ""
