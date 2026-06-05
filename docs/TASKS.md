# ChatGPT Radio — Tracker de Tâches

> Source de vérité de l'avancement par phase.
> Mise à jour à chaque issue fermée ou tâche complétée.
> Cross-refs : [DECISIONS.md](DECISIONS.md) · [DIRECTION.md](../DIRECTION.md)

---

## Phase 0+1 — Fondation (TERMINÉE ✅)

Vérifié le 2026-05-20 — smoke test OK : GlobalState 77 champs, WebSocket 4fps, SQLite WAL, collecteur OpenAI Status RSS, self_model EMA, drift momentum.

| Issue | Titre | PR | État |
|-------|-------|----|------|
| #2 | Scaffolding : structure projet, uv, pyproject.toml, config loader | #15 | ✅ |
| #3 | Core : GlobalState Pydantic v2 (77 champs) | #16 | ✅ |
| #4 | Core : SQLite WAL persistence (aiosqlite, schema) | #17 | ✅ |
| #5 | Core : @node decorator + registre global | #18 | ✅ |
| #6 | Core : StateUpdater — asyncio.Queue pipeline central | #20 | ✅ |
| #7 | Core : WebSocket server — broadcast GlobalState JSON 4-10fps | #23 | ✅ |
| #8 | Core : collector_runner — auto-découverte, boucles, source_health | #24 | ✅ |
| #9 | Collector : OpenAI Status RSS → openai_status, crisis_level | #25 | ✅ |
| #10 | Self-model : update_self_model() — EMA baselines, volatilités, τ | #19 | ✅ |
| #11 | La Dérive : update_drift() — PE pondéré, momentum, circle of fifths | #22 | ✅ |
| #12 | Self-model : drift_weights + Hebbian reinforcement | #21 | ✅ |
| #13 | Builder : build_music_prompt() — GlobalState → Stable Audio prompt | #26 | ✅ |
| #14 | main.py — event loop asyncio + graceful shutdown | #27 | ✅ |

---

## Phase 2 — Contenu & Mémoire (TERMINÉE ✅ — 2026-05-20)

### Implémenté mais non câblé

| Module | Fichier | État | PR |
|--------|---------|------|----|
| Bibliothèque audio (index, search, reuse) | `core/audio_library.py` | ✅ mergé | #78 |
| Stable Audio 2.5 queue | `core/audio_queue.py` | ✅ mergé | #83 |
| Track namer GPT-4o-mini | `core/track_namer.py` | ✅ mergé | #80 |
| Journal IA GPT-4o | `core/journal.py` | ✅ mergé | #79 |
| Mémoire persistante (viewers, trends) | `core/memory.py` | ✅ mergé | #79 |
| Chat commands handler | `core/chat_commands.py` | ✅ mergé | #81 |
| CommandEngine (cooldowns, dispatch) | `core/command_engine.py` | ✅ mergé | #81 |
| GlobalState : current_track_name | `core/state.py` | ✅ mergé | #77 |
| Index references (script CLI) | `scripts/index_references.py` | ✅ mergé | #82 |

### Génération audio intelligente (issues #84–#95 — PRs #96–#105, 2026-05-20)

| Issue | Module | Fichier | État | PR |
|-------|--------|---------|------|----|
| #84 A1 | Alignement territoires drift ↔ music_prompt (7→ même 7) | `core/drift.py`, `builders/music_prompt.py` | ✅ | #96 |
| #85 A2 | find_reference() inclut source='reference' | `core/audio_queue.py` | ✅ | #97 |
| #86 A3 | librosa dans pyproject.toml (group scripts) | `pyproject.toml` | ✅ | #98 |
| #87 A4 | _EMOTION_ORDER : supprimer phantom wonder/melancholy/urgency | `core/track_namer.py` | ✅ | #99→#100 |
| #88 B1 | GlobalState : wonder, melancholy, urgency (champs dérivés) | `core/state.py` | ✅ | #101 |
| #89 B2 | updater.py : compute_derived() + update_self_model() pour 3 nouveaux | `core/updater.py` | ✅ | #102 |
| #90 B3 | drift.py : 15 territoires (7 existants + 8 nouveaux) | `core/drift.py` | ✅ | #103 |
| #91 B4 | music_prompt.py : profils pour 15 territoires | `builders/music_prompt.py` | ✅ | #103 |
| #92 C1-C3 | strength/guidance_scale/total_seconds state-driven | `core/audio_queue.py` | ✅ | #100 |
| #93 C4 | find_reference() : scoring state-aware (territoire+BPM+mood) | `core/audio_queue.py` | ✅ | #104 |
| #94 C5 | find_reusable() : scoring state-aware | `core/audio_library.py` | ✅ | #105 |
| #95 C6 | last_prompt_hash : skip génération redondante | `core/audio_queue.py` | ✅ | #100 |
| #87b A4b | _EMOTION_ORDER : ré-ajouter wonder/melancholy/urgency (réels) | `core/track_namer.py` | ✅ | #100 |

### Corrections bibliothèque audio (2026-05-20)

| Correctif | Fichiers | État |
|-----------|---------|------|
| `find_reusable` : exclut `source='reference'` (jamais en lecture directe) | `core/audio_library.py` | ✅ |
| `find_reference` : références éligibles dès `play_count=0` (plus de deadlock) | `core/audio_queue.py` | ✅ |
| Auto-scan `streams/references/` au démarrage (indexation sans librosa) | `core/audio_queue.py` | ✅ |
| `.gitignore` : patterns répertoire + `.gitkeep` (tous formats audio exclus) | `.gitignore` | ✅ |

### Câblage prod — TERMINÉ ✅ (vérifié 2026-05-20)

| Tâche | Fichier | État |
|-------|---------|------|
| `run_audio_queue()` dans main.py | `main.py` | ✅ mergé (PRs Phase 2) |
| `run_journal()` dans main.py | `main.py` | ✅ mergé (PRs Phase 2) |
| DB schema : table `journal_entries` | `core/db.py` | ✅ mergé |
| DB schema : colonne `viewers.display_name` | `core/db.py` | ✅ mergé |
| GlobalState : champ `journal_text` | `core/state.py` | ✅ mergé |
| `CommandEngine` instancié dans main.py | `main.py` | ✅ câblé (PR #130) |

### Activation YouTube — TERMINÉ ✅ (2026-05-20)

| Module | Fichier | État |
|--------|---------|------|
| YouTube Live Chat polling (pytchat) | `collectors/youtube_chat.py` | ✅ PR #130 |
| !commands (`!mood`/`!request`/`!switch`/`!replay`) | `core/chat_commands.py` | ✅ mis à jour 2026-05-23 |
| CommandEngine injecté via make_collector() | `main.py` | ✅ PR #130 |
| YouTube broadcast lifecycle (auto-start) | `core/youtube.py` | ❌ pas encore implémenté |

### Prérequis manuels

| Prérequis | État |
|-----------|------|
| FFmpeg installé | ✅ OK |
| `fal-client` installé | ✅ OK (PR #83) |
| `openai` installé | ✅ OK (PR #79) |
| `FAL_API_KEY` dans `.env` | ✅ OK |
| `OPENAI_API_KEY` dans `.env` | ✅ OK |
| YouTube Studio → activation live streaming | ✅ actif |
| Stream Key + RTMP URL dans `.env` | ✅ configuré |
| `YOUTUBE_CHANNEL_ID` dans `.env` | ✅ configuré |
| `YOUTUBE_VIDEO_ID` dans `.env` | ✅ configuré (issue #144) |
| Xvfb + Chromium installés | ✅ installés |

---

## Phase 3 — Température du Monde (TERMINÉE ✅ — 2026-05-20)

281 tests verts. VADER uniquement (V1), Nitter RSS dégradation gracieuse.

| Issue | Module | Fichier | PR | État | Clé requise |
|-------|--------|---------|-----|------|-------------|
| #106 | Shared utilities (VADER, normalize, fetch) | `collectors/utils.py` | #110 | ✅ | — |
| #107 | HN Algolia | `collectors/hn_algolia.py` | #111 | ✅ | — |
| #107 | Wikipedia pageviews | `collectors/wikipedia.py` | #111 | ✅ | — |
| #107 | Google Trends RSS | `collectors/google_trends.py` | #111 | ✅ | — |
| #107 | GDELT global tone | `collectors/gdelt.py` | #111 | ✅ | — |
| #107 | Hedonometer happiness | `collectors/hedonometer.py` | #111 | ✅ | — |
| #107 | yfinance MSFT/NVDA | `collectors/yfinance_proxy.py` | #111 | ✅ | — |
| #107 | ArXiv papers | `collectors/arxiv.py` | #111 | ✅ | — |
| #108 | Nitter RSS (Twitter/X) | `collectors/nitter_rss.py` | #112 | ✅ | — |
| #108 | GitHub trending | `collectors/github_trending.py` | #112 | ✅ | — |
| #109 | Reddit PRAW | `collectors/reddit.py` | #113 | ✅ | `REDDIT_CLIENT_ID/SECRET` |
| #109 | NewsAPI.ai | `collectors/newsapi.py` | #113 | ✅ | `NEWSAPI_AI_KEY` |
| #109 | Media Cloud | `collectors/media_cloud.py` | #113 | ✅ | `MEDIA_CLOUD_API_KEY` |

---

## Phase 4 — DSP & Visuel (EN COURS 🔄)

Vérifié 2026-05-20 — 353+ tests verts. NO FAKE validé sur tous les overlays. Stream live actif.

### Pipeline initial (2026-05-20)

| Module | Fichier | État | PR/Commit |
|--------|---------|------|-----------|
| Pedalboard DSP engine | `core/dsp.py` | ✅ mergé | 2f763f1 |
| FFmpeg → RTMP pipe | `core/dsp.py` | ✅ mergé | 2f763f1 |
| CalendarEngine 15 événements | `core/calendar_engine.py` | ✅ mergé | 2f763f1 |
| Three.js graph @node | `overlays/graph.html` | ✅ mergé | 2f763f1 |
| Three.js 5 modes (neural/synapse/chaos/globe/nebula) | `overlays/visualizer.html` | ✅ mergé | PR #118 + suite |
| CNN Fear & Greed collecteur | `collectors/cnn_fear_greed.py` | ✅ mergé | 2f763f1 |
| SceneRotator (rotation 6 modes auto) | `core/scene_rotator.py` | ✅ mergé | 2f763f1 |

### Pipeline visuel headless (2026-05-20)

| Module | Fichier | État | Notes |
|--------|---------|------|-------|
| LUFS normalization (-14 LUFS) | `core/dsp.py` | ✅ hotfix | pyloudnorm, ±18dB cap |
| Real-time audio throttle (4096-sample chunks) | `core/dsp.py` | ✅ hotfix | `asyncio.sleep` entre chunks |
| Overlay HTTP server (aiohttp static) | `main.py` | ✅ PR #129 | port 8080, sert `overlays/` |
| browser_display.py (Xvfb + Chromium) | `core/browser_display.py` | ✅ PR #129 | auto-restart Chromium |
| Chromium SwiftShader (WebGL headless) | `core/browser_display.py` | ✅ hotfix | `--enable-unsafe-swiftshader --use-gl=swiftshader` |
| x11grab DSP pipeline | `core/dsp.py` | ✅ PR #132 | `-f x11grab -i :99.0` |
| YouTube Live Chat (pytchat, no quota) | `collectors/youtube_chat.py` | ✅ PR #130 | `!commands` câblés |
| YouTube API quota backoff | `collectors/youtube_chat.py` | ✅ hotfix | 2 min / 1h selon erreur 403 |
| Silence filler PCM (gap entre clips) | `core/dsp.py` | ✅ hotfix | `get_nowait()` + silence real-time |
| Background DSP processing (silence pendant encoding) | `core/dsp.py` | ✅ hotfix | `asyncio.create_task` |
| FFmpeg stderr DEVNULL (évite deadlock pipe) | `core/dsp.py` | ✅ hotfix | buffer 64KB → plus de stall |
| FFmpeg CBR 2500k (débit YouTube recommandé) | `core/dsp.py` | ✅ hotfix | `-b:v 2500k -minrate -maxrate -bufsize` |

### Ops & Stabilité (2026-05-21)

| Module | Fichier | État | PR |
|--------|---------|------|----|
| fal_derived territory from ref (`_get_ref_territory`) | `core/audio_queue.py` | ✅ mergé | #136 |
| Tests territory inheritance (4 cas) | `tests/test_audio_queue_territory.py` | ✅ mergé | #136 |
| systemd user service (Restart=always) | `scripts/install_service.sh` | ✅ mergé | #137 |
| start.sh / stop.sh convenience wrappers | `scripts/start.sh`, `scripts/stop.sh` | ✅ mergé | #137 |
| Watchdog cron (every 2min) | `scripts/watchdog.sh`, `scripts/setup_crons.sh` | ✅ mergé | #138 |
| Audio clip rotation (cron 3h) | `scripts/rotate_clips.sh` | ⚠️ script présent, **retiré du cron 2026-06-05** — librairie audio protégée | #138 |
| Auto-index refs on new file (10s rescan + librosa bg) | `core/audio_queue.py` | ✅ hotfix | — |
| find_reusable cooldown 5min + max_play_count=10 | `core/audio_library.py` | ✅ hotfix | — |
| setup_crons.sh : fix grep exit 1 sur crontab vide | `scripts/setup_crons.sh` | ✅ hotfix | 8a0822d |
| loginctl enable-linger (service démarre au boot) | serveur | ✅ déployé | — |
| Cron watchdog (every 2min) + rotate (3h) | serveur | ✅ déployé | — |
| Swap 2GB `/swapfile` (protection OOM) | serveur | ✅ déployé | — |
| ExecStartPre : kill Xvfb/Chromium orphelins avant restart | `scripts/install_service.sh` | ✅ hotfix | — |
| Migration screen → systemd (Restart=always, linger) | serveur | ✅ déployé | — |

---

### FPS Optimization (2026-05-21)


| Issue | Module | Fichier | PR | État |
|-------|--------|---------|-----|------|
| #140 | RAF throttle 30fps + bloom demi-résolution + pixelRatio=1 | `overlays/visualizer.html` | #141 | ✅ mergé |

Résultat : Chromium GPU process 156% → 102% CPU (−35%).

---

### Fixes stabilité & visualiseur (2026-05-21)

| Issue | Module | Fichier | PR | État |
|-------|--------|---------|-----|------|
| #142 | StateUpdater : gestion items `dict` dans la queue (fix crash silencieux) | `core/updater.py` | #154 | ✅ mergé |
| #143 | WebSocket : frame texte au lieu de binaire (fix JSON.parse côté browser) | `core/websocket_server.py`, `overlays/visualizer.html` | #150 | ✅ mergé |
| #145 | `config.yaml` : 13 collecteurs Phase 3 activés | `config.yaml` | #153 | ✅ mergé |
| #146 | Shutdown gracieux : timeout 10s + cleanup FFmpeg stdin/terminate | `main.py`, `core/dsp.py` | #152 | ✅ mergé |
| #147 | Ghost paths : cleanup DB au démarrage (fichiers supprimés) | `core/audio_library.py`, `core/audio_queue.py` | #156 | ✅ mergé |
| #148 | `songs_played_today` / `songs_played_total` incrémentés après chaque clip | `core/dsp.py` | #155 | ✅ mergé |
| #149 | Log `audio_clip_queued` quand reuse depuis bibliothèque | `core/audio_queue.py` | #151 | ✅ mergé |
| #144 | YOUTUBE_VIDEO_ID : résolution video_id sans search.list (quota) | `collectors/youtube_chat.py` | — | ✅ HITL résolu (`.env`) |

---

### Overlays — Nouvelles scènes (en cours)

| Issue | Module | Fichier | PR | État |
|-------|--------|---------|-----|------|
| #116 | ChaosMode : particle metamorphosis (4 attracteurs mathématiques) | `overlays/visualizer.html` | — | ❌ AFK ready-for-agent |
| #117 | NO FAKE validation : synapse + chaos modes (test WebSocket coupé) | `overlays/visualizer.html` | — | ❌ HITL (validation manuelle) |

---

## Audio Transitions & Librosa — Sprints 1–4 (2026-05-22)

ADR : [ADR-0007](adr/0007-emotion-synthesis.md)
**474 tests verts** (Sprint 3 terminé).

### Sprint 1 — Fondations ✅ TERMINÉ (PRs #187 #189 #190 mergés — 2026-05-22)

| Issue | Titre | Fichier(s) | PR | État |
|-------|-------|------------|-----|------|
| #157 | ADR-0007 : couche de synthèse émotionnelle | `docs/adr/0007-emotion-synthesis.md` | commit 7e0a390 | ✅ |
| #158 | `_synthesize_emotions()` — activation couche émotionnelle | `core/updater.py` | #189 | ✅ |
| #159 | `mark_played()` après succès génération (BUG7) | `core/audio_queue.py` | #189 | ✅ |
| #160 | Fusionner VALID_VIBES/VALID_GENRES (BUG3) | `core/command_engine.py`, `core/chat_commands.py` | #189 | ✅ |
| #161 | `songs_played_today` reset UTC minuit (BUG6) | `core/updater.py`, `core/state.py` | #189 | ✅ |
| #162 | `drift_timbre` dans prompt + "47 seconds" (BUG9+BUG10) | `builders/music_prompt.py` | #189 | ✅ |
| #163 | `json` → `orjson` dans 7 fichiers (BUG11) | `core/audio_queue.py`, `collectors/newsapi.py`, et 5 autres | #189 | ✅ |
| #164 | `purge_old_data()` au démarrage (BUG8) | `main.py` | #189 | ✅ |
| #165 | Journal `gpt-4o` → `gpt-4o-mini` + client OpenAI singleton (Bloc 6) | `core/journal.py`, `core/track_namer.py` | #189 | ✅ |
| #166 | Restaurer MusicVector au redémarrage (Bloc 8-F) | `core/memory.py` | #189 | ✅ |
| #167 | `openai_latency_ms` mesuré (BUG12) | `collectors/openai_status.py` | #189 | ✅ |
| #168 | `current_song_progress` mis à jour en boucle PCM (BUG4+BUG5) | `core/dsp.py` | #190 | ✅ |
| #169 | DSP rebuild toutes les 5s (Bloc 8-A) | `core/dsp.py` | #190 | ✅ |
| #173 | CommandEngine wiring dans audio_queue (BUG1) | `core/audio_queue.py`, `main.py` | #189 | ✅ |
| #174 | Corrections métriques librosa (Blocs 2a-g + BUG15) | `scripts/index_references.py` | #189 | ✅ |
| #184 | Collecteur système (hour_utc, cpu_percent, memory_percent, uptime_h) | `collectors/system_metrics.py` | #189 | ✅ |
| BUG13/C5 | `drift_velocity` + `drift_energy` dans `update_drift()` | `core/drift.py` | #187 | ✅ |

**Résumé Sprint 1 :** couche émotionnelle active (world_temperature/musical_tension/harmonic_complexity non-nulles), 15 territoires atteignables, 13 bugs corrigés, métriques librosa correctes, 410 tests.

---

### Sprint 2 — Audio quality ✅ TERMINÉ (PRs #191 #192 #193 #194 #195 — 2026-05-22 — 419 tests)

| Issue | Titre | Fichier(s) | PR | État |
|-------|-------|------------|-----|------|
| #170 | Crossfade sans écho — `_pending_tail` entre clips | `core/dsp.py` | #191 | ✅ |
| #171 | Crisis cache au démarrage + delta trigger + bypass prompt-hash (Bloc 8-B+C) | `core/audio_queue.py` | #192 | ✅ |
| #175 | DB `audio_key` + cercle des quintes scoring + MFCC cosine dans `find_reusable()` (Blocs 3a-e) | `core/db.py`, `core/audio_library.py`, `core/state.py` | #193 | ✅ |
| #176 | Analyse librosa des clips générés en post-génération (Bloc 4a) | `core/audio_queue.py` | #194 | ✅ |
| #177 | Boucle feedback audio → self_model (audio_bpm_delta, audio_key_match) (Bloc 5a+5b) | `core/dsp.py`, `main.py` | #195 | ✅ |

**Résumé Sprint 2 :** crossfade sans écho, crisis cache opérationnel, clé harmonique en DB + scoring cercle des quintes, analyse librosa post-génération en background, boucle feedback audio → self_model via state_queue. 419 tests.

### Sprint 3 — DJ transitions + enrichissements ✅ TERMINÉ (PRs #196–#200 — 2026-05-22 — 474 tests)

| Issue | Titre | Fichier(s) | PR | État |
|-------|-------|------------|-----|------|
| #179 | Effects chain enrichie — 4 niveaux crisis + LadderFilter + Delay + Phaser (Bloc 13-DSP) | `core/dsp.py` | #200 | ✅ |
| #180 | Transitions DJ — EQ crossfade 3-bandes + filter sweep + reverb throw (Blocs 9-T1+T2+T3) | `core/dsp.py` | #196 | ✅ |
| #181 | Workflow audio-to-audio amélioré — pre-stretch + strength data-driven + quality gating (Bloc 7) | `core/audio_queue.py` | #198 | ✅ |
| #182 | `rhythmic_entropy` réel + journal enrichi + track_namer valeurs audio réelles (Bloc 6) | `core/updater.py`, `core/journal.py`, `core/track_namer.py` | #197 | ✅ |
| #183 | Enrichissement prompt musical — event_intensity + inference steps adaptatif + polytonalité (Bloc 12) | `builders/music_prompt.py`, `core/audio_queue.py` | #199 | ✅ |

**Résumé Sprint 3 :** hiérarchie crisis DSP 4 niveaux (GSM → Bitcrush), LadderFilter sweep, Delay/Phaser conditionnels territoire, transitions DJ T1+T2+T3 au crossfade, audio-to-audio pre-stretch + strength data-driven + quality gating, rhythmic_entropy réel, journal enrichi (event_label, urgency, burst), inference steps adaptatif. 474 tests.

### Sprint 4 — Automation intra-clip ✅ TERMINÉ (PR #201 — 2026-05-22 — 482 tests)

| Issue | Titre | Fichier(s) | PR | État |
|-------|-------|------------|-----|------|
| #178 | Automation DSP intra-clip + reverb throw world_event_burst + BPM rate limit (Blocs 10-RT1+RT2+RT3) | `core/dsp.py`, `core/drift.py` | #201 | ✅ |

**Résumé Sprint 4 :** automation RT1 conditionnelle (excitement/urgency), LadderFilter cutoff ramp 300Hz→20kHz build-up, reverb release 0.8→1.0, reverb throw world_event_burst, BPM rate limit ±8 BPM/clip dans update_drift(). 482 tests.

---

### Hotfixes production — 2026-05-23

| Titre | Fichier(s) | État |
|-------|------------|------|
| `current_track_name` au démarrage réel PCM (plus au queuing) — playback_queue porte `(Path, str)` | `core/audio_queue.py`, `core/dsp.py` | ✅ |
| `!song` supprimé ; `!vibe` supprimé (doublon `!request`) | `core/chat_commands.py`, `core/command_engine.py` | ✅ |
| Cooldowns anti-spam sur toutes les commandes : `!mood` 30 s, `!request` 60 s/genre, `!switch` 300 s, `!replay` 120 s | `core/command_engine.py`, `core/chat_commands.py` | ✅ |
| HUD `viewer_cmd_label` : notification 8 s overlay + `_show()` sur toutes les commandes | `core/chat_commands.py`, `core/state.py`, `overlays/visualizer.html` | ✅ |
| ON AIR badge HUD top-left : uptime masqué si < 1 min | `overlays/visualizer.html` | ✅ |
| `system_metrics` : `COLLECTOR_META` + entrée `config.yaml` + `psutil` installé → `uptime_h` / `cpu_percent` / `hour_utc` actifs | `collectors/system_metrics.py`, `config.yaml` | ✅ |
| `viewers` : YouTube Data API `videos.list?liveStreamingDetails` → viewer count réel, cache 120 s | `collectors/youtube_chat.py` | ✅ |
| pytchat channel ID bypass : `get_channelid` monkey-patché → contourne scraping YouTube hex-JSON | `collectors/youtube_chat.py` | ✅ |
| `num_inference_steps` plafonné à 8 (limite API fal.ai 2026-05) | `builders/music_prompt.py` | ✅ |
| SYNAPSE mode : bloom réduit (alpha 0.9→0.45, power 1.5→2.2, node size réduit, scale max 2.0→1.0) | `overlays/visualizer.html` | ✅ |
| SYNAPSE bloom — réduction complémentaire : nodes `g * 0.22` + pow 3.0, connexions cap ~0.35 (`0.28*vStr + 0.07*flow`) | `overlays/visualizer.html` | ✅ |
| Progress bar HUD : `wrapEl.style.display = 'block'` (était `''` → CSS `display:none` gagnait) | `overlays/visualizer.html` | ✅ |
| `current_track_name` loop au démarrage : suppression écritures `state_queue` parasites dans `_backfill_fallback_names()` + `_index_fallback_clips()` | `core/audio_queue.py` | ✅ |
| `total_seconds: 47 → 45` text-to-audio (audio-to-audio garde la durée de la référence) — optimisation coût fal.ai | `core/audio_queue.py` | ✅ |
| `find_reusable` : `max_play_count: 10 → 999`, `cooldown_s: 300 → 1800` — 94 clips disponibles non utilisés car seuil épuisé (avg play_count ≥ 10) | `core/audio_library.py` | ✅ |
| `restart.sh` : kill ordonné FFmpeg/Chromium/Xvfb/ports + vérification 5 composants post-démarrage | `scripts/restart.sh` | ✅ |
| `watchdog.sh` : 5 checks (service/main.py/FFmpeg→RTMP/Chromium/WS:8765), restart si check critique échoue ou ≥2 checks KO, cooldown 60s après démarrage | `scripts/watchdog.sh` | ✅ |
| `install_service.sh` : `ExecStartPre` ajoute kill FFmpeg+ports, `KillMode=control-group`, `TimeoutStopSec=15` | `scripts/install_service.sh` | ✅ |
| `setup_crons.sh` : watchdog.sh remplace check_stream.sh dans cron toutes les 2 min | `scripts/setup_crons.sh` | ✅ |

### Hotfixes production — 2026-05-23 (session 2)

| Titre | Fichier(s) | État |
|-------|------------|------|
| PCM thread real-time throttle : `time.sleep(_slack)` après chaque chunk — FFmpeg drainait le pipe plus vite que le temps réel → HUD clignotait toutes les 6-7 s | `core/dsp.py` | ✅ |
| `current_track_name = ""` en fin de clip — ancien nom restait affiché à 100% pendant le silence inter-clip | `core/dsp.py` | ✅ |
| Fallback `find_reusable(cooldown_s=0)` quand génération échoue ET queue vide (fal.ai credits épuisés) | `core/audio_queue.py` | ✅ |
| CSS progress bar `transition: width 0.25s` (était 1 s) | `overlays/visualizer.html` | ✅ |
| SYNAPSE mode : blending `NormalBlending → AdditiveBlending` (nœuds + connexions) — scène quasiment invisible sans bloom pass | `overlays/visualizer.html` | ✅ |
| CHAOS mode : caméra rapprochée `z=80 → z=55`, `maxDistance: 200 → 120` | `overlays/visualizer.html` | ✅ |
| `!mood` : filtrer `_MOOD_EXCLUDE` (songs_played_today, queue_length, etc.) de prediction_errors avant de chercher le signal dominant | `core/chat_commands.py` | ✅ |
| `SCENE_CYCLE` : supprimer `globe` et `nebula` (scènes retirées) → `["neural", "synapse", "chaos"]` | `core/scene_rotator.py` | ✅ |
| Génération audio text-to-audio : `total_seconds: 45 → 180` + bypass cooldown bibliothèque avant génération | `core/audio_queue.py` | ✅ |
| Tests `test_chat_commands.py` + `test_command_engine.py` + `test_scene_rotator.py` mis à jour (signature `author_name`, `SCENE_CYCLE` réduit, suppression `!vibe`/`!song`) | `tests/` | ✅ |

### Hotfixes production — 2026-05-23 (session 3) + nouvelle scène Kinect

| Titre | Fichier(s) | État |
|-------|------------|------|
| Silence inter-clip : `_read_and_stretch()` applique maintenant `trim_start_s`/`trim_end_s` (librosa) stockés dans `mood_snapshot` — 2-4 s de silence Stable Audio 2.5 supprimés à la lecture. DB interrogée avant chaque tâche de décodage et prefetch. | `core/dsp.py` | ✅ |
| SYNAPSE mode — nœuds quasi-invisibles : `float alpha = g * 0.12` → `g * 0.9` dans le fragment shader nœuds (valeur hardcodée proche de 0) | `overlays/visualizer.html` | ✅ |
| SYNAPSE mode — connexions quasi-invisibles : `0.16 * vStr` → `0.55 * vStr` dans le fragment shader connexions | `overlays/visualizer.html` | ✅ |
| SYNAPSE mode — bloom : `EffectComposer` + `UnrealBloomPass(strength=1.8, radius=0.5, threshold=0.0)`. Force varie `1.6 + maxPredError * 1.2` (data-driven, NO FAKE). | `overlays/visualizer.html` | ✅ |
| **Nouvelle scène KINECT** : nuage de points 3D (320×240 = 76 800 points) piloté par canvas procédural data-driven. Depth map = hotspots de `prediction_errors` + `crisis_level` + `world_event_burst`. Rotation mesh lerp vers `drift_territory`. Palette 4 couleurs par quartile de territoire. `pointSize` = `1.5 + maxPE*2.5 + tension*1.5`. | `overlays/visualizer.html` | ✅ |
| `SCENE_CYCLE` étendu à 4 : `["neural", "synapse", "chaos", "kinect"]`. Keyboard shortcut `4=kinect`. *(remplacé session 4 — voir ci-dessous)* | `core/scene_rotator.py`, `overlays/visualizer.html` | ✅ → mis à jour |
| Script dev `scripts/dev-overlay.sh` : serveur HTTP port 8081 sur `overlays/`, isolé du live (:8080). | `scripts/dev-overlay.sh` | ✅ |

---

### Hotfixes production — 2026-05-23 (session 4) — A2A, drift, bibliothèque

| Titre | Fichier(s) | État |
|-------|------------|------|
| SYNAPSE bloom augmenté : init `(sz, 0.4, 0.4, 0.15)`, dynamique `0.3 + maxPredError*0.3` ; GLOBE bloom `0.9 + maxPE*0.4` | `overlays/visualizer.html` | ✅ |
| Rotation caméra accélérée : `autoRotateSpeed: 1.5` (était 0.3) | `overlays/visualizer.html` | ✅ |
| `SCENE_CYCLE` : kinect retiré → `["neural","synapse","chaos","globe"]`. Keyboard : `1=neural 2=synapse 3=chaos 4=globe`. | `core/scene_rotator.py`, `overlays/visualizer.html` | ✅ |
| `visualizer_dev.html` créé : copie live + titre DEV. KinectMode, SynapseMode1, SynapseMode2 supprimés → 4 modes identiques au live. | `overlays/visualizer_dev.html` | ✅ |
| `find_reference()` : `AND play_count = 0` — chaque référence humaine ne sert qu'une seule fois pour A2A. | `core/audio_queue.py` | ✅ |
| Déduplication MFCC : 91/93 clips `fal_derived` supprimés (cascade A2A-sur-A2A, similarity ≥ 0.88). Script réutilisable créé. | `scripts/dedup_clips.py`, DB | ✅ |
| `find_reusable()` cooldown : 1 800 s (30 min) → 36 000 s (10 h). Favorise la génération fraîche. | `core/audio_library.py` | ✅ |
| **Bug drift critique** : `update_self_model()` jamais appelé pour les 8 champs dérivés (émotions, world_temperature, source_divergence, audience_energy) → `prediction_errors` vides → BPM/territory/key/timbre figés depuis le démarrage. Fix : 8 appels dans `compute_derived()` après calcul. | `core/updater.py` | ✅ |
| `!mood` : réponse GPT-4o-mini in-character (max 12 mots, données réelles). Singleton client. Fallback mécanique si GPT échoue. | `core/chat_commands.py` | ✅ |
| Test `test_a2a_decision_sets_ref_path_to_none` : fingerprints MFCC orthogonaux explicites (test écrit pour ancien bug `_mfcc_dist=1.0`). | `tests/test_audio_to_audio.py` | ✅ |

---

### Hotfixes production — 2026-05-24

| Titre | Fichier(s) | État |
|-------|------------|------|
| **Silence entre transitions** : dans le path fallback (prefetch raté), `_pending_tail` (3 s finales du clip précédent) est maintenant écrit via DSP au lieu du silence pendant que le clip suivant charge — plus de gap perceptible | `core/dsp.py` | ✅ |
| **`!replay` cassé** : `find_by_display_name()` convertit les espaces en wildcards (`echo frontier chasing shadows` → `%echo%frontier%chasing%shadows%`) pour matcher `"Echo Frontier - Chasing Shadows"` (le séparateur ` - ` était un non-match) | `core/audio_library.py` | ✅ |
| **`!replay` sans titre** : display_name récupéré depuis la DB quand le clip replay est mis dans `playback_queue` — nom de piste affiché correctement dans le HUD pendant la lecture | `core/audio_queue.py` | ✅ |
| **Librosa `float(tempo)` crash** : `librosa.beat.beat_track()` v0.10+ retourne un array → `float(tempo)` → `TypeError`. Fix : `float(np.atleast_1d(tempo)[0])` | `core/audio_queue.py` | ✅ |
| **System prompts contextuels — journal** : 3 variantes selon état — urgente/fragmentée (`crisis > 0.5`), contemplative (`ambient/neoclassical/drone`), neutre (défaut) | `core/journal.py` | ✅ |
| **System prompts contextuels — `!mood`** : terse/instable (`anxiety/frustration + σ > 2`), vive/énergisée (`excitement/curiosity + σ > 2`), neutre (défaut) | `core/chat_commands.py` | ✅ |
| **System prompts contextuels — track_namer** : atmospheric (`ambient/neoclassical/drone`), mechanical (`industrial`), abstract (`experimental/psych`), urgent/fragmentée (`crisis > 0.5`), neutre (défaut) | `core/track_namer.py` | ✅ |
| **Watchdog crash-loop** : compteur de skips consécutifs (`/tmp/stream_watchdog_skip_count`) — après 3 skips d'affilée (6 min), les vérifications sont forcées même si le service vient de démarrer | `scripts/watchdog.sh` | ✅ |
| **Watchdog nettoyage processus** : à chaque run (toutes les 2 min), tue les processus pytest orphelins et les shell-snapshots de session dev de plus de 5 min — évite l'OOM par accumulation de processus dev | `scripts/watchdog.sh` | ✅ |
| **Watchdog alerte mémoire** : log WARN si RAM disponible < 200 MB | `scripts/watchdog.sh` | ✅ |

---

### Audit pipeline & robustesse — 2026-05-24 (PRs #202 #205 #206)

| Titre | Fichier(s) | PR | État |
|-------|------------|-----|------|
| **Égalisation audio (mixage constant)** : `Compressor`+`Gain` déplacés dans `_build_level_chain()` (one-shot + second pass LUFS). Reverb wet max 0.35→0.20, room cap 1.0→0.60, `dry_level` 0.7→0.85, delay feedback cap 0.6→0.35, phaser mix 0.5→0.30. `AudioFile.resampled_to(_SR)` + `-ar 44100` ffmpeg | `core/dsp.py`, `core/audio_queue.py` | #202 | ✅ |
| **Génération text-to-audio 180s** (clips longs, moins d'appels API) ; **audio-to-audio : durée de la référence** via ffprobe (cap 180s) | `core/audio_queue.py` | #202 | ✅ |
| **Journal intervalle 15 min** (défaut), 3 min (crise), 5 min (min state-change) — trigger `state_changed` tirait toutes les 60s → −90 % appels GPT | `core/journal.py` | #202 | ✅ |
| **Track namer : 7 system prompts** (ambient/drone/neoclassical/jazz/industrial/experimental/crisis) avec références esthétiques + `temperature=1.1` + `max_tokens` 20→30 | `core/track_namer.py` | #202 | ✅ |
| **`pw()` tanh** dans `drift.py` : momentum BPM borné à ≤1.0 au lieu de 333+ quand volatilité proche de zéro | `core/drift.py` | #202 | ✅ |
| **CNN fear_greed parsing défensif** : `try/except (KeyError, TypeError, ValueError)` | `collectors/cnn_fear_greed.py` | #202 | ✅ |
| **Nitter RSS : `log.warning`** quand toutes les instances échouent (était `debug` — invisible en prod) | `collectors/nitter_rss.py` | #202 | ✅ |
| **Boucle feedback audio complète** (#203) : `audio_bpm_delta` / `audio_key_match` / `audio_energy_level` entrent dans `update_self_model()` via `compute_derived()`. `time_in_territory_h` comme signal de fatigue dans `update_drift()` (+0.05 max sur `bpm_force` après 3h) | `core/updater.py`, `core/drift.py` | #205 | ✅ |
| **Nitter RSS health tracking** (#204) : 4 instances, rotation vers la dernière fiable (`_last_ok_idx`), timeout 10s→6s, `source_health["nitter_rss"]` mis à jour | `collectors/nitter_rss.py` | #206 | ✅ |
| **arXiv delta normalisé** (#204) : rolling avg 7 derniers appels → `(today - avg) / max(avg, 1)` centré sur 0, actif en continu (vs count brut = 0 pendant 23h/24) | `collectors/arxiv.py`, `core/state.py` | #206 | ✅ |

---

### Optimisation coûts fal.ai — 2026-05-25

| Titre | Fichier(s) | État |
|-------|------------|------|
| **`total_seconds` T2A conservé à 180s** : clips longs = moins d'appels/h, meilleure continuité musicale. A2A : `min(ref_duration, 180)`. | `core/audio_queue.py` | ✅ |
| **`num_inference_steps` adaptatif** : 6 par défaut / 8 uniquement si `crisis_level > 0.6` | `builders/music_prompt.py` | ✅ |
| **Crisis cache startup conditionnel** : génération uniquement si `crisis_level > 0.5` au démarrage | `core/audio_queue.py` | ✅ |
| **Crisis cache rebuild cooldown 30 min** : `_CRISIS_CACHE_COOLDOWN = 1800s` — empêche les rebuilds en cascade lors des montées progressives de crise | `core/audio_queue.py` | ✅ |
| **`find_reusable` cooldown 2h** : 10h → 7 200s — clips reviennent en rotation après 2h, taux de génération réduit | `core/audio_library.py` | ✅ |
| **`_pending_ref` bypass supprimé** : `find_reusable()` n'est plus contourné quand des références A2A non traitées existent | `core/audio_queue.py` | ✅ |

---

### DSP & Transitions — 2026-05-24 (commits ef0a03a, dbf4f55, db59462)

| Titre | Fichier(s) | État |
|-------|------------|------|
| **Crossfade adaptatif 8-12s equal-power** : `_crossfade_samples()` par territoire (ambient/drone 10s, jazz 6s, industrial 3s, crisis 2s). `_crossfade_arrays()` linéaire → cos/sin (élimine le creux de volume). | `core/dsp.py` | ✅ |
| **Reverb global réduit** : wet 0.20→0.10, room 0.60→0.40, dry 0.85→0.92. burst_reverb 0.35/0.70. Delay feedback cap 0.25, mix cap 0.15. | `core/dsp.py` | ✅ |
| **T1 (EQ bass cut) supprimé** : LowShelfFilter statique sur la tête créait une discontinuité spectrale à la frontière xfade/body. Equal-power suffit pour éviter le doublement des basses. | `core/dsp.py` | ✅ |
| **T3 (reverb throw) supprimé** : wet=0.5 reverb sur la queue était re-processé par la chaîne DSP principale → reverb composée, transitions boueuses. | `core/dsp.py` | ✅ |
| **Bug tail_reserve corrigé** : réservait toujours `_CROSSFADE_SAMPLES` (12s) mais `blend_len` utilisait `_crossfade_samples(state)` (ex : 3s industrial) → 9s d'audio non jouées, silencieusement perdues. Fix : même valeur pour les deux. | `core/dsp.py` | ✅ |
| **Gap silence fallback path supprimé** : buffer circulaire sur `_pending_tail` — boucle la queue au lieu de silence quand le chargement du clip dépasse la durée de la queue. Fallback sans time-stretch (BPM 90.0 fixe) pour éviter 10-25s de latence pyrubberband. | `core/dsp.py` | ✅ |

### Ops & Robustesse — 2026-05-24 (commit ed9859c)

| Titre | Fichier(s) | État |
|-------|------------|------|
| **Purge DB au démarrage + périodique 6h** : `purge_old_data()` dans `main.py` + tâche asyncio `VACUUM` toutes les 6h *(remplacé 2026-05-31 — voir Optimisation RAM)* | `main.py` | ✅ |
| **Rétention réduite** : `snapshot_retention_days` 30→7j, `history_retention_days` 90→30j *(remplacé 2026-05-31 — voir Optimisation RAM)* | `config.yaml` | ✅ |
| **Watchdog OOM restart** : `memory_available < 150 MB` → restart (était WARN seulement). WARN étendu à 300 MB. Rotation `ffmpeg_live.log` à 50 MB. *(remplacé 2026-06-05 — voir Ops crash-only)* | `scripts/watchdog.sh` | ✅ → obsolète |

### Fixes production — 2026-05-25

| Titre | Fichier(s) | État |
|-------|------------|------|
| **Chromium priority nice=5** : chromium était lancé avec `nice -n 10` → préempté agressivement sur machine 2 cœurs → chutes FPS overlay. Réduit à `nice -n 5`. | `core/browser_display.py` | ✅ |
| **Audio double-queue corrigé** : `index_clip()` initialise `last_played_at=0.0` → `find_reusable()` re-sélectionnait le clip fraîchement généré 5s plus tard → double lecture. Fix : `mark_played(conn, outpath)` immédiatement après `index_clip`. Test de régression ajouté. | `core/audio_queue.py`, `tests/test_audio_queue.py` | ✅ |
| **Track names : 12 style hints rotatifs** — MD5(`current_track_name + territory`) sélectionne un vocabulaire orthogonal à chaque clip (haiku / géographique / biologique / cinématique / numérique / found-text / temporel / architectural / chimique / linguistique / cosmologique / taxonomique). User message enrichi : urgency, anomaly_score, style hint, interdiction de réutiliser les mots du clip précédent. | `core/track_namer.py` | ✅ |
| **Journal : 6 system prompts + 7 angles d'observation** — 3 nouveaux prompts (`_SYSTEM_TRANSITION`, `_SYSTEM_EVENT`, `_SYSTEM_URGENCY`). Tous les prompts interdisent "I notice"/"I observe". `_OBSERVATION_ANGLES` rotatif (MD5 de la dernière entrée) ajouté au user prompt — assure qu'aucun angle n'est répété consécutivement. `_SYSTEM` alias pour test backward-compat. | `core/journal.py`, `tests/test_journal_openai.py` | ✅ |

---

### Correctifs pipeline — 2026-05-26 (issues #207–#213)

Audit complet du pipeline — 17 bugs identifiés (B1–B17), tous corrigés en 7 commits.

| Issue | Bug | Fichier(s) | Commit | État |
|-------|-----|------------|--------|------|
| #207 | **B1** `time_in_territory_h` jamais remis à 0 lors d'un changement de territoire | `core/updater.py` | `496a68e` | ✅ |
| #207 | **B2** `crisis_level` / `harmonic_complexity` absents de `update_self_model` → PE toujours 0 | `core/updater.py` | `496a68e` | ✅ |
| #207 | **B4** `field_info.annotation` comparé à string au lieu du type → 0 champs couverts par annotation check | `core/updater.py` | `496a68e` | ✅ |
| #208 | **B6** `source_health` auto-True écrase le False auto-reporté par le collecteur | `core/collector_runner.py` | `3c4ee78` | ✅ |
| #209 | **B3** `detected_bpm` non persisté dans `mood_snapshot` → DSP reprenait toujours `drift_bpm` | `core/audio_queue.py`, `core/dsp.py` | `511db43` | ✅ |
| #211 | **B7** `!vibe` injectait directement dans `state.prediction_errors` (mutation hors queue) | `core/audio_queue.py` | `4c6234e` | ✅ |
| #211 | **B8** `@node reads=` déclarait des champs produits (pas consommés) pour openai_status + system_metrics | `collectors/openai_status.py`, `collectors/system_metrics.py` | `4c6234e` | ✅ |
| #210 | **B12** `asyncio.get_event_loop()` déprécié (Python 3.10+) → remplacé par `get_running_loop()` | `collectors/youtube_chat.py`, `collectors/yfinance_proxy.py` | `0c5793f` | ✅ |
| #210 | **B13** `regulars_ratio` toujours 0.0 (jamais mis à jour depuis `core.memory`) | `collectors/youtube_chat.py` | `0c5793f` | ✅ |
| #210 | **B14** `youtube_chat` absent du `NODE_REGISTRY` (make_collector ne l'enregistrait pas) | `collectors/youtube_chat.py` | `0c5793f` | ✅ |
| #210 | **B15** `!mood` utilisait `max(PE)` au lieu de `max(abs(PE))` → signal négatif fort ignoré | `core/chat_commands.py` | `0c5793f` | ✅ |
| #212 | **B5** `NodeMeta.produces: str` ne permet pas de déclarer plusieurs champs émis | `core/node.py` | `da1b326` | ✅ |
| #212 | **B9** 6 collecteurs multi-champs (newsapi, reddit, gdelt, nitter_rss, google_trends, yfinance_proxy) avec `produces` incomplet | 6 fichiers collectors | `da1b326` | ✅ |
| #213 | **B10** `wonder`/`excitement` poussés par `calendar_engine` immédiatement écrasés par `compute_derived` | `core/calendar_engine.py`, `core/updater.py` | `b28348c` | ✅ |
| #213 | **B11** Branch `kind == "vibe"` dead code dans `audio_queue` (aucun `push("vibe", ...)` n'existe) | `core/audio_queue.py` | `b28348c` | ✅ |
| #213 | **B17** `stream_bitrate=192.0` / `dropped_frames=0.0` hardcodés dans `run_dsp` (jamais mesurés) | `core/dsp.py` | `b28348c` | ✅ |

---

### Optimisation FPS & Robustesse — 2026-05-27

| Titre | Fichier(s) | État |
|-------|------------|------|
| **WAL VACUUM déplacé en tâche de fond** : startup VACUUM bloquait le démarrage quand le WAL dépassait 1 GB (cas extrême : 7.8 GB après kill -9 répétés). Déplacé dans `_periodic_purge()` avec délai 90s + `PRAGMA wal_checkpoint(TRUNCATE)` avant chaque VACUUM. Tâche tourne ensuite toutes les 6h. | `main.py` | ✅ (commit `7464e4c`) |
| **EGL testé et rejeté** : switch `--use-gl=egl` + `--enable-gpu-rasterization` testé — virglrenderer rend via `/dev/dri` en bypassant le framebuffer Xvfb → x11grab capturait uniquement la couche HTML/CSS → overlay bloqué sur "connecting...". Reverted. SwiftShader maintenu avec commentaire explicatif. | `core/browser_display.py` | ✅ (commit `8888a94`) |
| **UnrealBloomPass dead code supprimé** de `visualizer_dev.html` : 3 imports (EffectComposer, RenderPass, UnrealBloomPass) + `this._composer=null` dans 3 constructeurs + guards `if(_composer)` dans resize/render/dispose — jamais instancié dans aucun mode. | `overlays/visualizer_dev.html` | ✅ |
| **`powerPreference:'high-performance'`** : était `'low-power'` dans les deux overlays — signale au scheduler CPU/GPU de maintenir la clock. Gain : évite les downclock SwiftShader sur charge intermittente. | `overlays/visualizer.html`, `overlays/visualizer_dev.html` | ✅ |
| **`renderer.debug.checkShaderErrors = false`** : désactive la validation GLSL runtime dans les deux overlays. ~5% CPU saving sur les recompilations de shaders. | `overlays/visualizer.html`, `overlays/visualizer_dev.html` | ✅ |
| **`-vf fps=30` supprimé de FFmpeg** : filtre redondant — x11grab capture déjà à `-framerate 30` et `force-cfr=1` dans `-x264opts` garantit le CFR. | `core/dsp.py` | ✅ |
| **WebSocket 10fps** (était 4fps) : à 4fps (250ms entre updates), les lerps Three.js produisaient des sauts visibles malgré un render loop à 30fps. À 10fps (100ms), les animations suivent les signaux avec une fluidité perceptible. Coût négligeable (~2KB/s JSON). | `config.yaml` | ✅ (actif au prochain redémarrage) |

---

---

## Bot Telegram — Monitoring & Contrôle (TERMINÉ ✅ — 2026-05-28)

Spec : `docs/specs/2026-05-28-telegram-bot-design.md`
13 tests verts. Service systemd indépendant de `main.py`.

| Issue | Titre | Fichier(s) | PR | État |
|-------|-------|------------|-----|------|
| #214 | Skeleton + dépendances + middleware allowlist | `pyproject.toml`, `telegram_bot.py`, `.env.example` | #219 | ✅ |
| #215 | WebSocket client + cache état + AlertWatcher (debounce 30s) | `telegram_bot.py` | #220 | ✅ |
| #216 | Command handlers (/status /music /viewers /health /restart) | `telegram_bot.py` | #224 | ✅ |
| #217 | Service systemd + script d'installation | `scripts/install_tg_service.sh` | #224 | ✅ |
| #218 | Tests (13 tests) | `tests/test_telegram_bot.py` | #224 | ✅ |

---

---

### Optimisation RAM & FPS — 2026-05-31

Cause racine identifiée : `persist_snapshot()` appelée à chaque signal reçu (≈3 818 rows/h × 9 KB = 805 MB/jour). Avec rétention 7 jours = 5,5 GB de DB. VACUUM périodique toutes les 6h sur 5,5 GB saturait le disque → swap reads lents → drops de frames. Par ailleurs, x11grab à 40fps + Chromium SwiftShader à 80% CPU = l'encodeur x264 était préempté en permanence.

| Titre | Fichier(s) | État |
|-------|------------|------|
| **Throttle snapshots DB à 1/30s** : `_last_snapshot_ts` dans `StateUpdater` — persist_snapshot uniquement si `now - _last_snapshot_ts ≥ 30s`. Réduit de 3 818 rows/h à 120 rows/h (−97%), 805 MB/j → 25 MB/j. | `core/updater.py` | ✅ |
| **Rétention snapshots 7j → 1j** : régime permanent 25 MB vs 800 MB précédent. | `config.yaml` | ✅ |
| **Rétention history 30j → 7j** : signal_history sous 10 MB à régime. | `config.yaml` | ✅ |
| **Purge périodique 6h → 1h, sans VACUUM** : VACUUM sur une DB vivante (5,5 GB) saturait le disque 5–10 min toutes les 6h → drops de frames à intervalles réguliers. VACUUM conservé uniquement au startup (délai 90s, DB au plus petit). | `main.py` | ✅ |
| **x11grab 40fps → 30fps** : −25% charge x11grab + encodeur x264. `-g 80 → 60` (keyframe toutes les 2s). 30fps = standard YouTube, non perceptible pour les viewers. | `core/dsp.py` | ✅ |
| **`thread_queue_size` audio pipe 10M → 512** : ring buffer AVPacket réduit (~80 MB → quelques KB). 512 packets = largement suffisant, le queue réel en régime est ≤ 4 packets. | `core/dsp.py` | ✅ |
| **`CPUWeight=800` systemd** (cgroup v2) : main.py + ffmpeg ont 8× le poids CPU vs les autres processus user. Appliqué en live via `systemctl set-property`. | `~/.config/systemd/user/chatgpt-radio.service` | ✅ |
| **Chromium GPU renice +10** : SwiftShader (WebGL logiciel) cède les cycles à ffmpeg sans starvation. Persisté dans `restart.sh`. | `scripts/restart.sh` | ✅ |
| **Purge manuelle avant restart** : 212 147 state_snapshots + 209 490 signal_history supprimés (rétention 1j appliquée à la DB de 4,7 GB). | DB | ✅ |

---

---

### Debug FPS saccades — 2026-05-31 (sessions 1+2)

**Cause racine** : `NetworkMode.dispose()` dans `visualizer.html` ne libérait pas les ressources WebGL de ses enfants (`_boxHelper`, `_pointCloud`, `_linesMesh`) ni le `material` du `_starField`. Chaque sortie de la scène "network" laissait des ShaderMaterials compilés et des BufferGeometries en mémoire SwiftShader. Après 3 visites (à 10, 30, 50min — cycle 5min × 4 scènes), la pression GC V8 franchissait un seuil → pauses render > 33ms → drops x11grab → fps 30→21 à partir de ~67min. Pattern identique dans les deux runs consécutifs (old log + session courante).

| Titre | Fichier(s) | État |
|-------|------------|------|
| **`NetworkMode.dispose()` — traverse children** : ajout de `this._group.traverse(c => { c.geometry?.dispose(); c.material?.dispose(); })` avant `sc.remove(this._group)`. Sans cela, boxHelper + pointCloud + linesMesh (deux ShaderMaterials) leakaient à chaque sortie de scène. | `overlays/visualizer.html` | ✅ |
| **`_starField.material.dispose()` manquant** : `PointsMaterial` du fond étoilé non libéré à chaque sortie NetworkMode. | `overlays/visualizer.html` | ✅ |
| **`bm.geometry.dispose()` immédiat** : `BoxGeometry` temporaire créée pour `BoxHelper` disposée juste après construction (BoxHelper copie l'AABB immédiatement, ne conserve pas de référence). | `overlays/visualizer.html` | ✅ |
| **Chromium GPU renice dans restart périodique** : le restart automatique toutes les 3h dans `browser_display.py` ne renicait pas le nouveau GPU process. Ajout de `os.setpriority(PRIO_PROCESS, pid, 10)` après chaque restart Chromium périodique. | `core/browser_display.py` | ✅ |
| **watchdog `nc -z` → `ss -tnl`** : `nc -z localhost 8765` ouvrait une connexion TCP sans handshake WS → `InvalidMessage` toutes les 2min dans les logs. Remplacé par `ss -tnl | grep ':8765 '` (pas de connexion). | `scripts/watchdog.sh` | ✅ |
| **`visualizer_dev.html` synchronisé** : remplacé par copie exacte de `visualizer.html` (toutes les corrections incluses). Titre "DEV" supprimé de `visualizer.html`. | `overlays/visualizer.html`, `overlays/visualizer_dev.html` | ✅ |

---

### Debug FPS persistant — 2026-06-01 (session 3)

**Problème** : après les fixes de la session 2 (NetworkMode dispose), le fps continuait de chuter après 60-70min. Chromium redémarré à 07:20 → fps ne récupérait pas. DB corrompue au redémarrage.

**Root causes identifiées :**

| Titre | Fichier(s) | État |
|-------|------------|------|
| **DB corrompue après VACUUM INTO** : `os.replace(compact, db)` remplace `state.db` mais le `state.db-wal` de l'ancienne DB reste. Le service suivant ouvre le nouveau DB compact + l'ancien WAL → mismatch de pages → `database disk image is malformed`. Fix : supprimer le fichier `.compact` stale avant VACUUM + supprimer `-wal`/`-shm` après `os.replace`. | `scripts/restart.sh` | ✅ |
| **Overlay à 40fps vs x11grab à 30fps** : `_FRAME_MS = 1000/40` faisait tourner le render loop à 40fps mais x11grab capture à 30fps. Dès que SwiftShader dépasse 25ms/frame (seuil 40fps), le command buffer IPC Chromium→GPU sature → x11grab manque ses créneaux de capture → drops croissants. Timing identique à la dégradation constatée (~60-70min). | `overlays/visualizer.html` | ✅ |
| **ChaosMode `_starField.material` non disposé** : `PointsMaterial` laissé en heap à chaque sortie du mode chaos (exit à 5, 25, 45, 65min…). Leak léger mais contribue à l'augmentation du coût de rendu SwiftShader au fil du temps. | `overlays/visualizer.html` | ✅ |
| **Watchdog ne détectait pas la dégradation fps** : le stream tournait à 6-9fps pendant des heures sans restart automatique. Ajout Check 6 fps < 15/3 checks. *(seuil remonté à 20fps puis converti en alerte Telegram sans restart 2026-06-05)* | `scripts/watchdog.sh` | ✅ → mis à jour |

**Contexte du diagnostic** : 2 CPUs, GPU process SwiftShader à 109% CPU quand dégradé. Chromium restart (3h) ne récupérait pas le fps car la dégradation se re-produisait en 30min. La DB corrompue causait des crash loops répétés pendant le debug.

---

### Debug FPS persistant — 2026-06-03 (session 4)

**Problème** : le fps ne tournait toujours pas à 30fps constant. Le restart Chromium 3h ne suffisait pas — fps restait bas pendant 46min après chaque restart Chromium, puis récupérait brièvement avant de dégrader de nouveau à t≈60min.

**Root causes identifiées :**

| Titre | Fichier(s) | État |
|-------|------------|------|
| **`gl_PointSize` sans `clamp()` dans 3 shaders** : ChaosMode (`350/z`, max ~99px sans clamp), NetworkMode (`1200/z`, max ~80px sans clamp), LogoMode (`190/z`, max ~53px sans clamp). Sans borne, un point proche de la caméra peut atteindre plusieurs centaines de px → fill rate ×5 de la surface d'écran → SwiftShader à 100% CPU → fps=5-8. | `overlays/visualizer.html` | ✅ |
| **Chromium restart interval 3h > onset dégradation 60min** : analysis ffmpeg log (3 runs) montre fps=30 stable 0-60min, puis onset exact à 60min. Réduction à 55min puis 35min. *(restart périodique supprimé 2026-06-05 après correction de la vraie cause racine — voir session 5)* | `core/browser_display.py` | ✅ → obsolète |
| **Watchdog lit l'EMA `fps=` au lieu du fps instantané** : pendant 46min de fps=5-8 réel, l'EMA ffmpeg restait à 18-19fps (au-dessus du seuil 15fps) → watchdog affichait "OK" sans déclencher de restart. Nouveau calcul via `(frame2-frame1)/(time2-time1)` entre deux checks watchdog (2min d'intervalle). | `scripts/watchdog.sh` | ✅ |

**Contexte du diagnostic** : GPU process à 98-100% CPU constant. ffmpeg PID changé (respawn spontané à 09:38 dû à un drop RTMP suite au fps bas). Pattern clair : `drops=37` stable 50min, puis explosion exponentielle → onset SwiftShader exact à t=60min post-Chromium-start.

---

### Debug FPS — cause racine finale — 2026-06-04/05 (session 5)

**Root cause confirmée par DIAG** : LogoMode prenait **63ms/frame** (budget = 33ms) — 3 200 particules × 32px max + 2 hueShift (cos+sin) par fragment. Les autres modes (chaos, globe, network) tournaient à 33ms stable. L'EMA fps ffmpeg mettait 5–10min à récupérer après chaque sortie de LogoMode, donnant l'apparence d'une dégradation cumulative.

| Titre | Fichier(s) | État |
|-------|------------|------|
| **DIAG logging `frameAvgMs`/`frameP99Ms`** : `setInterval` 2min dans `visualizer.html` — log `renderer.info.memory` + JS heap + temps de frames (avg+P99) via `performance.now()`. Redirige `--enable-logging=stderr` Chromium vers `/tmp/chromium_console.log`. | `overlays/visualizer.html`, `core/browser_display.py` | ✅ |
| **LogoMode 3 200 → 1 500 particules** : réduit le vertex + fragment work de 53%. | `overlays/visualizer.html` | ✅ (commit `43e792b`) |
| **LogoMode `gl_PointSize` max 32px → 20px** : réduit l'aire fragment de 61% (32² → 20²). Résultat : fragment work total ≈ 23% du coût initial → frameAvgMs 63ms → ~14ms (budget 33ms respecté). | `overlays/visualizer.html` | ✅ (commit `43e792b`) |
| **hueShift trig → composante swap** : 2e `hueShift(col, uDivergence*...)` remplacé par `mix(col, col.zxy, uDivergence*abs(vR-0.5)*1.4)` — élimine cos+sin en fragment (NO FAKE : gated sur `uDivergence`). | `overlays/visualizer.html` | ✅ (commit `43e792b`) |
| **Restart Chromium périodique supprimé** : `_CHROMIUM_RESTART_INTERVAL = 35*60` retiré de `browser_display.py`. La cause racine corrigée, le restart préventif n'a plus de justification. Chromium redémarre uniquement sur crash (`returncode != None`). | `core/browser_display.py` | ✅ (commit `8ee1fcc`) |

---

### Ops crash-only + alertes Telegram — 2026-06-05

Politique : **le stream ne redémarre que sur crash confirmé**. Tous les checks non-critiques deviennent des alertes Telegram.

| Titre | Fichier(s) | État |
|-------|------------|------|
| **Watchdog crash-only** : restart déclenché uniquement si service/main.py/FFmpeg→RTMP mort ou ≥2 checks KO. | `scripts/watchdog.sh` | ✅ (commit `f04ad11`) |
| **Alertes Telegram** : crash → alerte + confirmation restart OK/KO. FPS < 20fps/6min → alerte. RAM < 200MB → alerte critique. Disque < 2GB → alerte. | `scripts/watchdog.sh` | ✅ |
| **Rotation logs** : `chromium_console.log` (5MB), `stream_restart.log` (2MB), `diag_monitor.log` (5MB) ajoutés à la rotation watchdog (s'ajoutent à `ffmpeg_live.log` 50MB et `stream_watchdog.log` 500KB). | `scripts/watchdog.sh` | ✅ |
| **`rotate_clips.sh` retiré du cron** : librairie audio protégée — les clips générés ne sont plus jamais supprimés. Le script est conservé mais désactivé. | crontab | ✅ |
| **`restart.sh` : nettoyage `.compact_ready`** : nettoie aussi l'ancien nom de convention (`state.db.compact_ready`) en plus de `state.db.compact`. Fix du 570MB stale laissé par une ancienne version après VACUUM interrompu. | `scripts/restart.sh` | ✅ (commit `f04ad11`) |

---

## Phase 5 — Unicité Maximale

- [ ] Spectrogram ARG : messages cachés dans l'audio
- [ ] Latent Space : vraie inférence ONNX visible
- [ ] Calendrier événements automatisé (ChatGPT Birthday, DevDay)
