import asyncio
import statistics
import time
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from core.db import persist_signal, persist_snapshot
from core.drift import update_drift
from core.self_model import update_self_model
from core.state import GlobalState, MusicVector

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
]


def compute_derived(state: GlobalState) -> None:
    state.world_temperature = (
        state.excitement + state.anxiety + state.frustration + state.curiosity + state.creativity
    ) / 5.0

    openai_crisis = 1.0 - state.openai_status
    latency_crisis = min(state.openai_latency_ms / 5000.0, 1.0)
    state.crisis_level = min(
        openai_crisis * 0.5 + latency_crisis * 0.2 + state.gdelt_conflict_intensity * 0.3, 1.0
    )

    viewers_norm = state.viewers / max(state.viewers_peak_today, 1)
    chat_rate_norm = min(state.chat_rate / 100.0, 1.0)
    state.audience_energy = viewers_norm * chat_rate_norm * (1.0 + state.regulars_ratio)

    state.musical_tension = state.anxiety * 0.5 + state.frustration * 0.5
    state.harmonic_complexity = state.curiosity * 0.6 + state.creativity * 0.4
    state.rhythmic_entropy = state.frustration * 0.5 + state.crisis_level * 0.5

    active = [getattr(state, s) for s in _SOURCE_SIGNAL_FIELDS if getattr(state, s) != 0.0]
    state.source_divergence = statistics.stdev(active) if len(active) >= 2 else 0.0

    divergence_vol = state.signal_volatilities.get("gdelt_conflict_intensity", 0.05)
    divergence_err = state.prediction_errors.get("gdelt_conflict_intensity", 0.0)
    state.world_event_burst = abs(divergence_err) > divergence_vol * 2

    state.anomaly_score = (
        max(abs(v) for v in state.prediction_errors.values()) if state.prediction_errors else 0.0
    )


class StateUpdater:
    def __init__(self, state: GlobalState, db_conn: aiosqlite.Connection) -> None:
        self.state = state
        self.db = db_conn
        self.queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._vec = MusicVector(
            bpm=state.drift_bpm,
            key=state.drift_key,
            timbre=state.drift_timbre,
            territory=state.drift_territory,
        )
        self._last_ts = time.monotonic()

    async def enqueue(self, signal: str, value: Any) -> None:
        await self.queue.put((signal, value))

    def _apply(self, signal: str, value: Any) -> None:
        if signal in _DICT_FIELDS:
            current: dict = getattr(self.state, signal)
            current.update(value)
        else:
            setattr(self.state, signal, value)
            field_info = GlobalState.model_fields.get(signal)
            if field_info and field_info.annotation in (float, int):
                update_self_model(self.state, signal, float(value))

    async def run(self) -> None:
        while True:
            signal, value = await self.queue.get()
            try:
                self._apply(signal, value)
                compute_derived(self.state)

                now = time.monotonic()
                dt_h = (now - self._last_ts) / 3600.0
                self._last_ts = now

                self._vec = update_drift(self._vec, self.state, dt_h)
                self.state.drift_bpm = self._vec.bpm
                self.state.drift_key = self._vec.key
                self.state.drift_timbre = self._vec.timbre
                self.state.drift_territory = self._vec.territory

                self.state.updated_at = datetime.now(timezone.utc)
                await persist_snapshot(self.db, self.state)

                annotation = GlobalState.model_fields.get(signal, None)
                if annotation and annotation.annotation in (float, int):
                    baseline = self.state.signal_baselines.get(signal, 0.0)
                    error = self.state.prediction_errors.get(signal, 0.0)
                    vol = self.state.signal_volatilities.get(signal, 0.1)
                    await persist_signal(self.db, signal, float(value), baseline, error, vol)

            finally:
                self.queue.task_done()
