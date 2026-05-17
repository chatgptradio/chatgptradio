from core.node import node
from core.state import GlobalState

PREDICTION_ERROR_MUSIC: dict[str, tuple[str, str]] = {
    "excitation": (
        "energetic, driving rhythm, bright synths, uplifting",
        "receding, dissolving energy, fading pulse",
    ),
    "anxiete": (
        "tense, sparse, uncertain harmonics, hollow",
        "releasing, resolving, open space",
    ),
    "frustration": (
        "dissonant, clashing elements, building tension, unresolved",
        "smoothing, harmonic resolution, clearing",
    ),
    "curiosite": (
        "exploratory, modal harmony, unexpected turns, open-ended",
        "settling, known patterns, familiar",
    ),
    "creativite": (
        "experimental, textural, non-standard timbres, playful",
        "minimal, foundational, stripped",
    ),
}

_EMOTIONS = list(PREDICTION_ERROR_MUSIC)


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
        v = max(vol.get(signal, 0.1), 0.001)
        return abs(pe.get(signal, 0.0)) / v

    dominant = max(_EMOTIONS, key=significance)
    error = pe.get(dominant, 0.0)
    pos_desc, neg_desc = PREDICTION_ERROR_MUSIC[dominant]
    emotional_color = pos_desc if error >= 0 else neg_desc

    crisis_mod = ""
    if state.crisis_level > 0.5:
        crisis_mod = ", glitch artifacts, signal degradation, system failure undertone"
    elif state.crisis_level > 0.2:
        crisis_mod = ", slight instability, latency feel, tension without resolution"

    audience_mod = ""
    if abs(pe.get("audience_energy", 0.0)) > vol.get("audience_energy", 0.1):
        if pe.get("audience_energy", 0.0) > 0:
            audience_mod = ", collective presence, social energy"

    divergence_mod = ""
    if pe.get("source_divergence", 0.0) > vol.get("source_divergence", 0.05):
        divergence_mod = ", ambiguous tonality, conflicting signals, unresolved tension"

    return (
        f"{int(state.drift_bpm)} BPM, key of {state.drift_key}, "
        f"{state.drift_timbre} timbre, {state.drift_territory}, "
        f"{emotional_color}"
        f"{crisis_mod}{audience_mod}{divergence_mod}, "
        "high quality, no vocals, AI ambient electronic music"
    )
