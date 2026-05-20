from core.node import node
from core.state import GlobalState

# Maps territory → (genre descriptor, primary instruments, production keyword)
_TERRITORY_PROFILE: dict[str, tuple[str, str, str]] = {
    "ambient":      ("ambient electronic",      "evolving shimmer pads, sparse piano",              "meditative reverb"),
    "electronic":   ("electronic",              "driving synths, 808 bass, arpeggios",               "44.1kHz stereo"),
    "jazz":         ("jazz instrumental",       "upright bass, brushed drums, piano",                "warm, intimate"),
    "industrial":   ("industrial",              "distorted synths, heavy percussion, abrasive noise", "harsh, relentless"),
    "neoclassical": ("neoclassical",            "piano, chamber strings, sparse arrangement",        "refined, melancholic"),
    "experimental": ("experimental electronic", "granular synthesis, glitch textures, atonal pads",  "avant-garde, unpredictable"),
    "drone":        ("drone ambient",           "sustained tones, subharmonics, morphing pads",      "hypnotic, minimal"),
}

_EMOTION_DESCRIPTORS: dict[str, tuple[str, str]] = {
    "excitement":    ("euphoric, driving, bright",         "dissolving energy, fading pulse"),
    "anxiety":       ("tense, sparse, hollow",             "releasing, resolving, open space"),
    "frustration":   ("dissonant, unresolved tension",     "harmonic resolution, clearing"),
    "curiosity":     ("exploratory, modal, open-ended",    "settling, familiar patterns"),
    "creativity":    ("experimental, textural, playful",   "minimal, foundational"),
    "wonder":("wondrous, expansive, ethereal",     "grounded, intimate"),
    "melancholy":    ("melancholic, introspective, muted", "warming, hopeful"),
    "urgency":       ("urgent, propulsive, relentless",    "decelerating, resolving"),
}

_EMOTIONS = list(_EMOTION_DESCRIPTORS)


@node(
    name="music_prompt",
    produces="music_prompt",
    color="#00D4FF",
    label="Music Prompt",
    reads=[
        "prediction_errors",
        "signal_volatilities",
        "drift_bpm",
        "drift_key",
        "drift_timbre",
        "drift_territory",
        "crisis_level",
        "audience_energy",
        "source_divergence",
    ],
)
def build_music_prompt(state: GlobalState, prev_prompt: str | None = None) -> str:
    pe = state.prediction_errors
    vol = state.signal_volatilities

    def significance(signal: str) -> float:
        return abs(pe.get(signal, 0.0)) / max(vol.get(signal, 0.1), 0.001)

    dominant = max(_EMOTIONS, key=significance)
    error = pe.get(dominant, 0.0)
    pos_desc, neg_desc = _EMOTION_DESCRIPTORS[dominant]
    emotional_color = pos_desc if error >= 0 else neg_desc

    territory = state.drift_territory.lower()
    genre, instruments, prod_kw = _TERRITORY_PROFILE.get(
        territory,
        ("ambient electronic", "evolving pads, sparse textures", "44.1kHz stereo"),
    )

    # Crisis overrides genre and adds degradation descriptors
    if state.crisis_level > 0.5:
        genre = "glitch ambient"
        instruments = "fragmented pads, broken rhythms, hollow drones"
        emotional_color += ", signal degradation, system failure undertone"
    elif state.crisis_level > 0.2:
        emotional_color += ", slight instability, tension without resolution"

    audience_mod = ""
    if pe.get("audience_energy", 0.0) > vol.get("audience_energy", 0.1):
        audience_mod = ", collective presence, social energy"

    divergence_mod = ""
    if pe.get("source_divergence", 0.0) > vol.get("source_divergence", 0.05):
        divergence_mod = ", ambiguous tonality, conflicting signals"

    return (
        f"{genre}, {int(state.drift_bpm)} BPM, Key of {state.drift_key}, "
        f"{instruments}, "
        f"{emotional_color}"
        f"{audience_mod}{divergence_mod}, "
        f"{prod_kw}, no vocals, 60 seconds"
    )
