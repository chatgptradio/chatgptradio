from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class MusicVector:
    bpm: float = 90.0
    key: str = "C minor"
    timbre: str = "warm"
    territory: str = "ambient"


class GlobalState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ── CATEGORY 1: World Temperature ───────────────────────────────────────

    excitement: float = 0.0
    anxiety: float = 0.0
    frustration: float = 0.0
    curiosity: float = 0.0
    creativity: float = 0.0

    reddit_volume: float = 0.0
    reddit_sentiment: float = 0.0
    twitter_volume: float = 0.0
    twitter_sentiment: float = 0.0
    hn_ai_score: float = 0.0
    google_trends_chatgpt: float = 0.0
    google_trends_openai: float = 0.0
    wikipedia_views_ai: float = 0.0
    newsapi_volume: float = 0.0
    newsapi_sentiment: float = 0.0
    arxiv_papers_today: float = 0.0
    github_ai_stars: float = 0.0

    gdelt_global_tone: float = 0.0
    gdelt_conflict_intensity: float = 0.0
    hedonometer_happiness: float = 0.0
    media_cloud_ai_volume: float = 0.0
    fear_greed_index: float = 0.0

    msft_delta: float = 0.0
    nvda_delta: float = 0.0

    # ── CATEGORY 2: OpenAI Infrastructure ───────────────────────────────────

    openai_status: float = 1.0
    openai_latency_ms: float = 0.0
    openai_incident_age_h: float = 0.0
    anthropic_status: float = 1.0
    gemini_status: float = 1.0

    # ── CATEGORY 3: Temporal + Drift State ──────────────────────────────────

    hour_utc: int = 0
    day_of_week: int = 0

    drift_bpm: float = 90.0
    drift_key: str = "C minor"
    drift_energy: float = 0.5
    drift_timbre: str = "warm"
    drift_territory: str = "ambient"
    time_in_territory_h: float = 0.0
    drift_velocity: float = 0.0
    audio_bpm_delta: float = 0.0
    audio_key_match: float = 0.0
    audio_energy_level: float = 0.0

    # ── CATEGORY 4: Audience ─────────────────────────────────────────────────

    viewers: int = 0
    viewers_peak_today: int = 0
    chat_rate: float = 0.0
    chat_sentiment: float = 0.0
    regulars_ratio: float = 0.0
    new_viewers_today: int = 0
    avg_session_min: float = 0.0
    likes_today: int = 0
    subs_delta_today: int = 0

    # ── CATEGORY 5: Content State ────────────────────────────────────────────

    songs_played_today: int = 0
    songs_played_today_date: str = ""
    current_song_progress: float = 0.0
    current_track_name: str = ""
    journal_text: str = ""
    visual_mode: str = "neural"
    viewer_cmd_label: str = ""
    active_event: str = ""
    event_label: str = ""
    event_intensity: float = 0.0
    queue_length: int = 0
    last_prompt_hash: str = ""
    generation_lag_s: float = 0.0
    requested_genre: str = ""

    # ── CATEGORY 6: System ───────────────────────────────────────────────────

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    stream_bitrate: float = 0.0
    dropped_frames: float = 0.0
    source_health: dict[str, bool] = Field(default_factory=dict)

    # ── CATEGORY 7: Self-model ───────────────────────────────────────────────

    signal_baselines: dict[str, float] = Field(default_factory=dict)
    signal_adaptation_rates: dict[str, float] = Field(default_factory=dict)
    signal_volatilities: dict[str, float] = Field(default_factory=dict)
    prediction_errors: dict[str, float] = Field(default_factory=dict)
    drift_momentum: dict[str, float] = Field(default_factory=dict)
    drift_weights: dict[str, dict[str, float]] = Field(default_factory=dict)

    uptime_h: float = 0.0
    songs_played_total: int = 0
    unique_viewers_total: int = 0
    anomaly_score: float = 0.0
    days_since_crisis: float = 0.0

    # ── CATEGORY 8: Derived fields ───────────────────────────────────────────

    world_temperature: float = 0.0
    crisis_level: float = 0.0
    audience_energy: float = 0.0
    musical_tension: float = 0.0
    harmonic_complexity: float = 0.0
    rhythmic_entropy: float = 0.0
    source_divergence: float = 0.0
    world_event_burst: bool = False

    wonder: float = 0.0      # unexpected positive discovery signal
    melancholy: float = 0.0  # quiet contemplation, low engagement
    urgency: float = 0.0     # rate-of-change + crisis pressure

    mfcc_fingerprint: list[float] = Field(default_factory=list)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
