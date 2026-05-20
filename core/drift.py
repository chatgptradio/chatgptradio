from core.self_model import update_drift_weights
from core.state import GlobalState, MusicVector

CIRCLE_OF_FIFTHS = [
    "C major", "G major", "D major", "A major", "E major",
    "B major", "F# major", "Db major", "Ab major", "Eb major",
    "Bb major", "F major",
    "A minor", "E minor", "B minor", "F# minor", "C# minor",
    "G# minor", "Eb minor", "Bb minor", "F minor", "C minor",
    "G minor", "D minor",
]

_TIMBRE_SEQUENCE = ["warm", "organic", "digital", "cold", "metallic"]

_TERRITORY_PROFILES: dict[str, dict[str, int]] = {
    "ambient":      {"excitement": -1, "anxiety": -1, "crisis_level": -1},
    "electronic":   {"excitement": +1, "curiosity": +1},
    "jazz":         {"curiosity": +1, "creativity": +1, "frustration": -1},
    "industrial":   {"frustration": +1, "crisis_level": +1, "anxiety": +1},
    "neoclassical": {"anxiety": +1, "curiosity": +1, "excitement": -1},
    "experimental": {"creativity": +1, "source_divergence": +1},
    "drone":        {"crisis_level": +1, "excitement": -1},
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def derive_territory_from_errors(pe: dict[str, float], vol: dict[str, float]) -> str:
    scores = {
        territory: sum(
            pe.get(dim, 0.0) * direction / max(vol.get(dim, 0.1), 0.01)
            for dim, direction in profile.items()
        )
        for territory, profile in _TERRITORY_PROFILES.items()
    }
    return max(scores, key=scores.__getitem__)


def update_drift(current: MusicVector, state: GlobalState, dt_h: float) -> MusicVector:
    pe = state.prediction_errors
    vol = state.signal_volatilities

    def pw(signal: str) -> float:
        return pe.get(signal, 0.0) / max(vol.get(signal, 0.01), 0.01)

    # ── BPM ──────────────────────────────────────────────────────────────────
    bpm_signals = ["excitement", "audience_energy", "world_temperature"]
    update_drift_weights(state, "bpm", bpm_signals)
    w_bpm = state.drift_weights["bpm"]

    bpm_force = (
        pw("excitement") * w_bpm["excitement"]
        + pw("audience_energy") * w_bpm["audience_energy"]
        + pw("world_temperature") * w_bpm["world_temperature"]
    )

    energy_vol = (vol.get("excitement", 0.1) + vol.get("audience_energy", 0.1)) / 2
    damping = 1.0 - (1.0 / (1.0 + energy_vol * 50))

    new_bpm_momentum = state.drift_momentum.get("bpm", 0.0) * damping + bpm_force * dt_h
    state.drift_momentum["bpm"] = new_bpm_momentum
    new_bpm = _clamp(current.bpm + new_bpm_momentum * 40, 60.0, 140.0)

    # ── KEY ──────────────────────────────────────────────────────────────────
    tension_error = pe.get("anxiety", 0.0) + pe.get("frustration", 0.0)
    tension_vol = vol.get("anxiety", 0.1) + vol.get("frustration", 0.1)
    if abs(tension_error) > tension_vol:
        idx = CIRCLE_OF_FIFTHS.index(current.key) if current.key in CIRCLE_OF_FIFTHS else 0
        shift = 1 if tension_error > 0 else -1
        new_key = CIRCLE_OF_FIFTHS[(idx + shift) % len(CIRCLE_OF_FIFTHS)]
    else:
        new_key = current.key

    # ── TIMBRE ────────────────────────────────────────────────────────────────
    creativity_error = pe.get("creativity", 0.0)
    creativity_vol = vol.get("creativity", 0.1)
    if abs(creativity_error) > creativity_vol:
        idx = _TIMBRE_SEQUENCE.index(current.timbre) if current.timbre in _TIMBRE_SEQUENCE else 0
        direction = 1 if creativity_error > 0 else -1
        new_timbre = _TIMBRE_SEQUENCE[(idx + direction) % len(_TIMBRE_SEQUENCE)]
    else:
        new_timbre = current.timbre

    # ── TERRITORY ────────────────────────────────────────────────────────────
    divergence_error = pe.get("source_divergence", 0.0)
    divergence_vol = vol.get("source_divergence", 0.05)
    momentum_norm = abs(new_bpm_momentum) + abs(state.drift_momentum.get("energy", 0.0))
    if abs(divergence_error) > divergence_vol or momentum_norm > 1.5:
        new_territory = derive_territory_from_errors(pe, vol)
    else:
        new_territory = current.territory

    return MusicVector(bpm=new_bpm, key=new_key, timbre=new_timbre, territory=new_territory)
