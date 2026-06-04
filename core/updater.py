import asyncio
import statistics
import time
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import structlog

from core.db import persist_signal, persist_snapshot
from core.drift import update_drift
from core.self_model import update_self_model
from core.state import GlobalState, MusicVector

log = structlog.get_logger()

# Tracks the last time crisis_level exceeded 0.6 (epoch seconds).
# Initialised to 0.0; days_since_crisis stays 0 until the first crisis is observed.
_last_crisis_ts: float = 0.0

_DICT_FIELDS = {
    "source_health",
    "signal_baselines",
    "signal_adaptation_rates",
    "signal_volatilities",
    "prediction_errors",
    "drift_momentum",
    "drift_weights",
}

_NUMERIC_FIELDS = {
    name
    for name, field in GlobalState.model_fields.items()
    if field.annotation in (float, int) or str(field.annotation) in ("float", "int")
}

_SOURCE_SIGNAL_FIELDS = [
    "reddit_sentiment",
    "twitter_sentiment",
    "gdelt_global_tone",
    "newsapi_sentiment",
    "hedonometer_happiness",
    "openai_status",
    "reddit_volume",
    "fear_greed_index",
    "github_ai_stars",
    "arxiv_papers_today",
]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _synthesize_emotions(state: GlobalState) -> None:
    pe = state.prediction_errors
    vol = state.signal_volatilities

    def _z(s: str) -> float:
        return pe.get(s, 0.0) / max(vol.get(s, 0.1), 0.001)

    state.excitement = _clamp(
        0.25 * _z("reddit_volume") + 0.25 * _z("twitter_volume")
        + 0.2 * _z("hn_ai_score") + 0.15 * _z("hedonometer_happiness")
        + 0.15 * _z("google_trends_chatgpt")
        + state.event_intensity * 0.3, -1.0, 1.0
    )
    state.anxiety = _clamp(
        0.4 * _z("gdelt_conflict_intensity") + 0.3 * (1.0 - state.openai_status)
        + 0.2 * _z("newsapi_volume") + 0.1 * _z("fear_greed_index"), -1.0, 1.0
    )
    state.frustration = _clamp(
        -0.4 * _z("reddit_sentiment") - 0.3 * _z("twitter_sentiment")
        - 0.2 * _z("newsapi_sentiment") - 0.1 * _z("hedonometer_happiness"), -1.0, 1.0
    )
    state.curiosity = _clamp(
        0.4 * _z("arxiv_papers_today") + 0.3 * _z("github_ai_stars")
        + 0.2 * _z("wikipedia_views_ai") + 0.1 * _z("hn_ai_score"), -1.0, 1.0
    )
    state.creativity = _clamp(
        0.4 * _z("media_cloud_ai_volume") + 0.3 * state.source_divergence
        + 0.3 * _z("github_ai_stars"), -1.0, 1.0
    )


def compute_derived(state: GlobalState) -> None:
    global _last_crisis_ts

    _synthesize_emotions(state)

    today = datetime.now(timezone.utc).date().isoformat()
    if state.songs_played_today_date != today:
        state.songs_played_today = 0
        state.songs_played_today_date = today

    state.world_temperature = (
        state.excitement + state.anxiety + state.frustration + state.curiosity + state.creativity
    ) / 5.0

    openai_crisis = 1.0 - state.openai_status
    latency_crisis = min(state.openai_latency_ms / 5000.0, 1.0)
    state.crisis_level = min(
        openai_crisis * 0.5 + latency_crisis * 0.2 + state.gdelt_conflict_intensity * 0.3, 1.0
    )

    # Track days since last crisis (crisis_level > 0.6)
    if state.crisis_level > 0.6:
        _last_crisis_ts = time.time()
    if _last_crisis_ts > 0.0:
        state.days_since_crisis = (time.time() - _last_crisis_ts) / 86400.0

    viewers_norm = state.viewers / max(state.viewers_peak_today, 1)
    chat_rate_norm = min(state.chat_rate / 100.0, 1.0)
    state.audience_energy = viewers_norm * chat_rate_norm * (1.0 + state.regulars_ratio)

    state.musical_tension = state.anxiety * 0.5 + state.frustration * 0.5
    state.harmonic_complexity = state.curiosity * 0.6 + state.creativity * 0.4

    # Use real IOI variance from audio analysis if available, else proxy fallback
    real_re = state.signal_baselines.get("audio_ioi_variance")
    if real_re is not None and real_re > 0:
        rhythmic_entropy = _clamp(real_re, 0.0, 1.0)
    else:
        rhythmic_entropy = _clamp(state.frustration * 0.5 + state.crisis_level * 0.5, 0.0, 1.0)
    state.rhythmic_entropy = rhythmic_entropy

    active = [getattr(state, s) for s in _SOURCE_SIGNAL_FIELDS if getattr(state, s) != 0.0]
    state.source_divergence = statistics.stdev(active) if len(active) >= 2 else 0.0

    # Feed synthesized emotions + derived scalars into the self-model so drift.py
    # can read them from prediction_errors like any other signal.
    for _name, _val in (
        ("excitement",         state.excitement),
        ("anxiety",            state.anxiety),
        ("frustration",        state.frustration),
        ("curiosity",          state.curiosity),
        ("creativity",         state.creativity),
        ("world_temperature",  state.world_temperature),
        ("source_divergence",  state.source_divergence),
        ("audience_energy",    state.audience_energy),
        ("crisis_level",       state.crisis_level),
        ("harmonic_complexity", state.harmonic_complexity),
    ):
        update_self_model(state, _name, _val)

    # Audio feedback loop: feed audio analysis fields into self-model so
    # prediction_errors track deviations from learned baselines.
    # Guard: skip default values (0.0 / 0) to avoid polluting baselines
    # with absence-of-signal noise.
    if state.audio_bpm_delta > 0:
        update_self_model(state, "audio_bpm_delta", state.audio_bpm_delta)
    if state.audio_key_match != 0:
        update_self_model(state, "audio_key_match", state.audio_key_match)
    if state.audio_energy_level > 0:
        update_self_model(state, "audio_energy_level", state.audio_energy_level)

    pe = state.prediction_errors
    vol = state.signal_volatilities

    divergence_vol = vol.get("gdelt_conflict_intensity", 0.05)
    divergence_err = pe.get("gdelt_conflict_intensity", 0.0)
    state.world_event_burst = (
        abs(divergence_err) > divergence_vol * 2
        or pe.get("openai_status", 0.0) < -0.3
        or pe.get("reddit_volume", 0.0) > vol.get("reddit_volume", 0.1) * 3
        or pe.get("arxiv_papers_today", 0.0) > vol.get("arxiv_papers_today", 0.1) * 2
    )

    state.anomaly_score = (
        max(abs(v) for v in state.prediction_errors.values()) if state.prediction_errors else 0.0
    )

    def _z(signal: str) -> float:
        return pe.get(signal, 0.0) / max(vol.get(signal, 0.1), 0.001)

    state.wonder = max(0.0, min(1.0,
        0.4 * _z("curiosity")
        + 0.3 * _z("arxiv_papers_today")
        + 0.2 * _z("github_ai_stars")
        + 0.1 * _z("hedonometer_happiness")
        + state.event_intensity * 0.4
    ))
    state.melancholy = max(0.0, min(1.0,
        0.4 * (1.0 - state.audience_energy)
        + 0.3 * max(0.0, -_z("hedonometer_happiness"))
        + 0.3 * min(state.time_in_territory_h / 4.0, 1.0)
    ))
    state.urgency = max(0.0, min(1.0,
        0.4 * min(abs(state.drift_velocity) * 5.0, 1.0)
        + 0.3 * state.crisis_level
        + 0.3 * float(state.world_event_burst)
    ))


class StateUpdater:
    def __init__(self, state: GlobalState, db_conn: aiosqlite.Connection) -> None:
        self.state = state
        self.db = db_conn
        self.queue: asyncio.Queue[tuple[str, Any] | dict[str, Any]] = asyncio.Queue()
        self._vec = MusicVector(
            bpm=state.drift_bpm,
            key=state.drift_key,
            timbre=state.drift_timbre,
            territory=state.drift_territory,
        )
        self._last_ts = time.monotonic()
        self._last_snapshot_ts = 0.0  # throttle: persist snapshot at most every 30s

    async def enqueue(self, signal: str, value: Any) -> None:
        await self.queue.put((signal, value))

    def _apply(self, signal: str, value: Any) -> None:
        if signal in _DICT_FIELDS:
            current: dict = getattr(self.state, signal)
            current.update(value)
        else:
            setattr(self.state, signal, value)
            field_info = GlobalState.model_fields.get(signal)
            if field_info and (
                field_info.annotation in (float, int)
                or str(field_info.annotation) in ("float", "int")
            ):
                update_self_model(self.state, signal, float(value))

    async def run(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if isinstance(item, dict):
                    for signal, value in item.items():
                        self._apply(signal, value)
                    signals_to_persist = list(item.items())
                else:
                    signal, value = item
                    self._apply(signal, value)
                    signals_to_persist = [(signal, value)]

                compute_derived(self.state)
                for sig in ("wonder", "melancholy", "urgency"):
                    update_self_model(self.state, sig, getattr(self.state, sig))

                now = time.monotonic()
                dt_h = (now - self._last_ts) / 3600.0
                self._last_ts = now

                prev_territory = self._vec.territory
                self._vec = update_drift(self._vec, self.state, dt_h)
                self.state.drift_bpm = self._vec.bpm
                self.state.drift_key = self._vec.key
                self.state.drift_timbre = self._vec.timbre
                self.state.drift_territory = self._vec.territory

                if self._vec.territory != prev_territory:
                    self.state.time_in_territory_h = 0.0
                else:
                    self.state.time_in_territory_h += dt_h

                self.state.updated_at = datetime.now(timezone.utc)
                if now - self._last_snapshot_ts >= 30.0:
                    await persist_snapshot(self.db, self.state)
                    self._last_snapshot_ts = now

                for signal, value in signals_to_persist:
                    annotation = GlobalState.model_fields.get(signal, None)
                    if annotation and (
                        annotation.annotation in (float, int)
                        or str(annotation.annotation) in ("float", "int")
                    ):
                        baseline = self.state.signal_baselines.get(signal, 0.0)
                        error = self.state.prediction_errors.get(signal, 0.0)
                        vol = self.state.signal_volatilities.get(signal, 0.1)
                        await persist_signal(self.db, signal, float(value), baseline, error, vol)

            except Exception:
                log.exception("updater_error", item=str(item)[:120])
            finally:
                self.queue.task_done()
