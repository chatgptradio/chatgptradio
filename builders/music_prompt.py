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
    "lo-fi":        ("lo-fi hip hop",           "warm Rhodes, vinyl crackle, muted 808",             "loopable, cassette warmth"),
    "cinematic":    ("cinematic score",         "orchestral strings, piano, swelling brass",         "high quality, no vocals"),
    "darkwave":     ("darkwave",                "cold synths, minor arpeggios, distant reverb",      "bleak, cavernous"),
    "techno":       ("techno",                  "driving kick, acid bassline, mechanical arpeggios", "club-ready, relentless"),
    "psych":        ("psychedelic ambient",     "modular drones, phased guitars, spatial reverb",    "mind-expanding, surreal"),
    "noise":        ("harsh noise",             "saturated feedback, distorted drones, broken rhythms", "abrasive, maximal"),
    "minimalist":   ("minimalist",              "sparse piano, long tones, silence as texture",      "breathing room, austere"),
    "blues":        ("blues",                   "slide guitar, walking bass, brushed snare",         "raw, intimate, soulful"),
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

    # requested_genre (set by !request command) overrides drift_territory for one generation
    effective_territory = (
        state.requested_genre.lower() if state.requested_genre else state.drift_territory.lower()
    )
    territory = effective_territory
    genre, instruments, prod_kw = _TERRITORY_PROFILE.get(
        territory,
        ("ambient electronic", "evolving pads, sparse textures", "44.1kHz stereo"),
    )

    # Crisis level modifies emotional color; genre/instruments follow the territory
    if state.crisis_level > 0.5:
        emotional_color += ", signal degradation, system failure undertone"
    elif state.crisis_level > 0.2:
        emotional_color += ", slight instability, tension without resolution"

    audience_mod = ""
    if pe.get("audience_energy", 0.0) > vol.get("audience_energy", 0.1):
        audience_mod = ", collective presence, social energy"

    divergence_mod = ""
    if pe.get("source_divergence", 0.0) > vol.get("source_divergence", 0.05):
        divergence_mod = ", ambiguous tonality, conflicting signals"

    # Bloc 12-P2 — source_divergence → tonal ambiguity (data-driven, NO FAKE)
    tonal_mod = ""
    if state.source_divergence > 0.8:
        tonal_mod = ", atonal, no key center, free improvisation"
    elif state.source_divergence > 0.6:
        tonal_mod = ", polytonality, two conflicting keys, dissonant counterpoint"

    # Bloc 12-P1 — time_in_territory texture (only when territory is mature, NO FAKE)
    territory_age_mod = ""
    if state.time_in_territory_h > 4.0:
        territory_age_mod = ", late-night depth, worn-in quality"
    elif state.time_in_territory_h > 2.0:
        territory_age_mod = ", evolved, advanced stage, mature texture"

    # Bloc 12-I — event_label in prompt (only if event_intensity > 0.3, NO FAKE)
    event_mod = ""
    if state.event_label and state.event_intensity > 0.3:
        event_mod = f", {state.event_label.replace('_', ' ')}, euphoric celebratory feel"

    return (
        f"{genre}, {int(state.drift_bpm)} BPM, Key of {state.drift_key}, "
        f"{instruments}, {state.drift_timbre} texture, "
        f"{emotional_color}"
        f"{audience_mod}{divergence_mod}{tonal_mod}{territory_age_mod}{event_mod}, "
        f"high quality, no vocals, AI ambient electronic music"
    )


def get_inference_steps(state: GlobalState) -> int:
    """Adaptive inference steps: fast when urgent, quality when healthy. API max = 8."""
    if state.queue_length == 0:
        return 6
    return 8
