# Design : DSP Engine + GlobalState Refactor

**Date** : 2026-05-18
**Scope** : `core/dsp.py` (nouveau) + `core/state.py` + `core/updater.py` (refactor)
**Issues à créer** : DSP Engine (#31-next) + GlobalState Refactor (#31-next+1)

---

## Vision

GlobalState est un vecteur d'état ouvert — pas un schéma figé. L'entité grandit avec
ses sources. Chaque nouveau collecteur Phase 3 enrichit automatiquement la musique sans
modifier l'architecture DSP. Le DJ vivant réagit à son environnement en continu.

---

## Partie 1 — GlobalState Refactor

### 1.1 Suppressions

Retirer de `state.py` (volumes bruts, inutiles sans baseline relative) :

```
reddit_volume, twitter_volume, newsapi_volume, media_cloud_ai_volume
```

Fusionner :
```
google_trends_chatgpt + google_trends_openai  →  google_trends_ai: float = 0.0
```

Corriger `drift_energy` : soit calculé dans `compute_derived()`, soit supprimé.
Décision : **calculé** — `drift_energy = drift_velocity * 0.5 + drift_bpm_norm * 0.5`
où `drift_bpm_norm = (drift_bpm - 60) / 80` (normalisé 0–1 sur plage 60–140).

### 1.2 Nouvelles dimensions émotionnelles

Ajouter dans Catégorie 1 (après les 5 existantes) :

```python
wonder: float = 0.0   # wonder, percée, breakthrough
melancholy: float = 0.0       # déclin, tristesse, dégradation prolongée
urgency: float = 0.0          # breaking news, rapidité, tension temporelle
```

### 1.3 Couche manquante — `compute_emotions()`

Nouvelle fonction dans `updater.py`, appelée par `compute_derived()` avant les
dérivations musicales. Calcule les 8 dimensions émotionnelles depuis les signaux bruts.

Les formules Phase 2 (signaux bruts tous à 0.0) sont des stubs qui s'activent
naturellement à l'arrivée des collecteurs Phase 3 :

```python
def compute_emotions(state: GlobalState) -> None:
    pe = state.prediction_errors

    # Arousal positif : buzz communauté + activité marché
    state.excitement = _clamp(
        pe.get("reddit_sentiment", 0.0) * 0.3
        + pe.get("google_trends_ai", 0.0) * 0.3
        + pe.get("msft_delta", 0.0) * 0.2
        + pe.get("nvda_delta", 0.0) * 0.2,
        -1.0, 1.0
    )

    # Tension + incertitude
    state.anxiety = _clamp(
        pe.get("gdelt_conflict_intensity", 0.0) * 0.4
        + pe.get("fear_greed_index", 0.0) * -0.3   # fear_greed bas = anxiété
        + pe.get("newsapi_sentiment", 0.0) * -0.3,
        -1.0, 1.0
    )

    # Frustration système + conflits
    state.frustration = _clamp(
        (1.0 - state.openai_status) * 0.5
        + pe.get("gdelt_conflict_intensity", 0.0) * 0.3
        + pe.get("twitter_sentiment", 0.0) * -0.2,
        0.0, 1.0
    )

    # Curiosité intellectuelle + recherche
    state.curiosity = _clamp(
        pe.get("hn_ai_score", 0.0) * 0.4
        + pe.get("wikipedia_views_ai", 0.0) * 0.3
        + pe.get("arxiv_papers_today", 0.0) * 0.3,
        0.0, 1.0
    )

    # Momentum créatif + innovation
    state.creativity = _clamp(
        pe.get("github_ai_stars", 0.0) * 0.5
        + pe.get("arxiv_papers_today", 0.0) * 0.3
        + pe.get("hn_ai_score", 0.0) * 0.2,
        0.0, 1.0
    )

    # Wonder : anomalie positive confirmée
    state.wonder = _clamp(
        max(pe.get("arxiv_papers_today", 0.0), 0.0) * 0.5
        + max(pe.get("fear_greed_index", 0.0), 0.0) * 0.3
        + (state.anomaly_score if state.anomaly_score > 0.5 else 0.0) * 0.2,
        0.0, 1.0
    )

    # Mélancolie : dégradation prolongée + monde triste
    state.melancholy = _clamp(
        max(0.0, -pe.get("hedonometer_happiness", 0.0)) * 0.4
        + (state.openai_incident_age_h / 24.0) * 0.4   # incident long = mélancolie
        + max(0.0, -pe.get("msft_delta", 0.0)) * 0.2,
        0.0, 1.0
    )

    # Urgence : événement burst + conflit en hausse
    burst_float = 1.0 if state.world_event_burst else 0.0
    state.urgency = _clamp(
        burst_float * 0.5
        + max(pe.get("gdelt_conflict_intensity", 0.0), 0.0) * 0.5,
        0.0, 1.0
    )
```

### 1.4 Formules `compute_derived()` corrigées

```python
def compute_derived(state: GlobalState) -> None:
    compute_emotions(state)   # ← nouveau, en premier

    # world_temperature : baseline 0.5 (neutre), pondéré par valence
    # Positif : excitement, curiosity, wonder, creativity
    # Négatif : anxiety, frustration, melancholy
    valence = (
        state.excitement * 0.2 + state.curiosity * 0.2
        + state.wonder * 0.15 + state.creativity * 0.1
        - state.anxiety * 0.15 - state.frustration * 0.1 - state.melancholy * 0.1
    )
    # Incorpore signaux globaux directs quand disponibles
    gdelt_contribution = state.gdelt_global_tone * 0.1       # −1..+1 → petit poids
    hedo_contribution = (state.hedonometer_happiness - 0.5) * 0.1  # centré sur 0
    state.world_temperature = _clamp(0.5 + valence + gdelt_contribution + hedo_contribution, 0.0, 1.0)

    # crisis_level : inchangé
    openai_crisis = 1.0 - state.openai_status
    latency_crisis = min(state.openai_latency_ms / 5000.0, 1.0)
    state.crisis_level = _clamp(
        openai_crisis * 0.5 + latency_crisis * 0.2 + state.gdelt_conflict_intensity * 0.3,
        0.0, 1.0
    )

    # musical_tension : prediction errors (delta), pas valeurs brutes
    pe = state.prediction_errors
    state.musical_tension = _clamp(
        abs(pe.get("anxiety", 0.0)) * 0.35
        + abs(pe.get("frustration", 0.0)) * 0.35
        + state.anomaly_score * 0.3,
        0.0, 1.0
    )

    # harmonic_complexity : curiosité + divergence sources
    state.harmonic_complexity = _clamp(
        abs(pe.get("curiosity", 0.0)) * 0.4
        + abs(pe.get("creativity", 0.0)) * 0.25
        + state.source_divergence * 0.35,
        0.0, 1.0
    )

    # rhythmic_entropy : chaos système
    state.rhythmic_entropy = _clamp(
        state.crisis_level * 0.4
        + state.anomaly_score * 0.35
        + state.urgency * 0.25,
        0.0, 1.0
    )

    # drift_energy : calculé depuis momentum BPM
    bpm_norm = _clamp((state.drift_bpm - 60.0) / 80.0, 0.0, 1.0)
    vel_norm = _clamp(abs(state.drift_velocity), 0.0, 1.0)
    state.drift_energy = bpm_norm * 0.6 + vel_norm * 0.4

    # audience_energy : inchangé
    viewers_norm = state.viewers / max(state.viewers_peak_today, 1)
    chat_rate_norm = min(state.chat_rate / 100.0, 1.0)
    state.audience_energy = viewers_norm * chat_rate_norm * (1.0 + state.regulars_ratio)

    # source_divergence : inchangé
    active = [getattr(state, s) for s in _SOURCE_SIGNAL_FIELDS if getattr(state, s) != 0.0]
    state.source_divergence = statistics.stdev(active) if len(active) >= 2 else 0.0

    # world_event_burst : inchangé
    divergence_vol = state.signal_volatilities.get("gdelt_conflict_intensity", 0.05)
    divergence_err = pe.get("gdelt_conflict_intensity", 0.0)
    state.world_event_burst = abs(divergence_err) > divergence_vol * 2

    # anomaly_score : inchangé
    state.anomaly_score = max(abs(v) for v in pe.values()) if pe else 0.0
```

---

## Partie 2 — DSP Engine (`core/dsp.py`)

### 2.1 Pipeline

```
playback_queue: asyncio.Queue[Path]  (alimentée par audio_queue.py)
      ↓  await get()
pedalboard.io.AudioFile  →  numpy f32 stereo 44100 Hz
      ↓  pyrubberband.time_stretch(ratio = drift_bpm / 90.0)
      ↓  Pedalboard chain (paramètres interpolés depuis GlobalState)
      ↓  crossfade 3s avec clip suivant (si disponible)
      ↓  .astype(np.int16).tobytes()  — PCM s16le
FFmpeg stdin pipe  →  aac 192k  →  rtmp://...
```

### 2.2 Mapping GlobalState → effets DSP

| Effet Pedalboard | Paramètre | Formule | Driver |
|---|---|---|---|
| `Reverb` | `room_size` | `0.2 + world_temperature * 0.4 + crisis_level * 0.25` | monde chaud + crise = espace dense |
| `Reverb` | `wet_level` | `0.1 + crisis_level * 0.5 + melancholy * 0.2` | crise + mélancolie = plus noyé |
| `HighShelfFilter` | `gain_db` | `-crisis_level * 18 - musical_tension * 4` | coupure haute fréquence sous tension |
| `Compressor` | `threshold_db` | `-18 - musical_tension * 12 - urgency * 6` | plus compressé = plus tendu |
| `Gain` | `gain_db` | `audience_energy * 3 + wonder * 2` | public engagé + wonder = plus présent |
| `PitchShift` | `semitones` | `urgency * 0.5 - melancholy * 0.3` | urgency monte, mélancolie descend |
| `Chorus` | `depth` | `harmonic_complexity * 0.8` | complexité harmonique = chorus riche |
| `Limiter` | `threshold_db` | `-1.0` | constant (sécurité) |
| `time_stretch` ratio | pyrubberband | `drift_bpm / 90.0` | tempo suit La Dérive |

### 2.3 Interface publique

```python
async def run_dsp(
    state: GlobalState,
    playback_queue: asyncio.Queue[Path],
    state_queue: asyncio.Queue,
) -> None: ...
```

- Si `RTMP_URL` absent → log warning + return (pattern identique à journal/audio_queue)
- Pousse dans `state_queue` : `{"current_song_progress": float, "stream_bitrate": float, "dropped_frames": float}`

### 2.4 FFmpeg process

```bash
ffmpeg -f s16le -ar 44100 -ac 2 -i pipe:0 \
       -c:a aac -b:a 192k -f flv {RTMP_URL}
```

- Processus unique persistant, stdin=PIPE
- Si mort : restart exponentiel (2s → 4s → 8s → max 60s)
- `stream_bitrate` et `dropped_frames` lus depuis stderr FFmpeg (regex sur `bitrate=` et `drop=`)

### 2.5 Crossfade

- Fenêtre : 3 secondes (132 300 samples à 44100 Hz)
- Fin de clip : fade-out linéaire sur les 3 dernières secondes
- Début du clip suivant : fade-in linéaire sur les 3 premières secondes
- Si `playback_queue` vide à la fin du clip : répéter le clip en cours avec warning log

### 2.6 `main.py` changes

```python
playback_queue: asyncio.Queue[Path] = asyncio.Queue(maxsize=4)

audio_task = asyncio.create_task(
    run_audio_queue(state, updater.queue, playback_queue)   # ← signature change
)
dsp_task = asyncio.create_task(
    run_dsp(state, playback_queue, updater.queue)
)
```

`run_audio_queue` reçoit `playback_queue` en paramètre et y pousse les `Path` générés
(en plus de pousser les métriques dans `state_queue`).

---

## Partie 3 — Décisions d'architecture

### Interface audio_queue → DSP
`asyncio.Queue[Path]` — pattern standard du projet, backpressure gratuite, `await get()` propre.

### Durée audio
45s par clip Stable Audio 2.5 (limite API). Crossfade 3s entre clips = nappe continue.
Pas de "chansons" discrètes — l'entité est un flux, pas une radio.

### Paramètres DSP
Interpolation continue depuis GlobalState — pas de seuils binaires. ADR-0002 compliant.

### Extensibilité
Ajouter un signal = 1 champ `state.py` + 1 collecteur `collectors/` + 1 ligne `compute_emotions()`.
Ajouter un effet DSP = 1 ligne dans `_build_chain()`. Aucune modification d'architecture.

---

## Tests

### GlobalState refactor
- `test_compute_emotions` : champs 0.0 → world_temperature = 0.5 (neutre)
- `test_world_temperature_neutral` : tous signaux absents → 0.5
- `test_world_temperature_crisis` : openai_status=0.0 → world_temperature < 0.5
- `test_new_dimensions_range` : wonder/melancholy/urgency ∈ [0.0, 1.0]
- `test_compute_emotions_prediction_errors` : pe positifs → excitement monte

### DSP
- `test_build_chain_normal` : crisis=0.0 → reverb.room_size ≈ 0.2
- `test_build_chain_crisis` : crisis=1.0 → reverb.room_size ≈ 0.85
- `test_run_dsp_no_rtmp_url` : exit gracieux sans RTMP_URL
- `test_crossfade_shape` : fade-out + fade-in = énergie préservée
- `test_ffmpeg_restart_on_death` : process mort → relancé avec backoff

---

## Out of scope

- Détection BPM automatique des clips (ratio fixe drift_bpm/90.0 suffit)
- DSP mid-fichier (paramètres mis à jour entre clips, pas pendant)
- Rotation 8h YouTube (géré par `core/youtube.py` Phase 2)
- Collecteurs Phase 3 (alimenteront `compute_emotions()` automatiquement)
