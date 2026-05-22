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
| !commands (song/request/vibe) | `core/chat_commands.py` | ✅ PR #130 |
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

PRD : `.claude/prds/phase3-collectors.md` | Plan : `.claude/plans/phase3-collectors.md`
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
| Three.js 6 modes (neural/synapse/particles/chaos/globe/nebula) | `overlays/visualizer.html` | ✅ mergé | PR #118 + suite |
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
| Watchdog cron (every 2min) | `scripts/check_stream.sh`, `scripts/setup_crons.sh` | ✅ mergé | #138 |
| Audio clip rotation (7j / 2GB) | `scripts/rotate_clips.sh` | ✅ mergé | #138 |
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

PRD : `.claude/prds/fps-optimization.md` | Plan : `.claude/plans/fps-optimization.md`

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

## Audio Transitions & Librosa — Sprint 1+2 (2026-05-22)

PRD : `.claude/prds/audio-transitions-librosa.md` | Plan : `.claude/plans/quizzical-tinkering-feather.md`
ADR : [ADR-0007](adr/0007-emotion-synthesis.md)
410 tests verts après Sprint 1+2 (partiel).

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

### Sprint 3 — DJ transitions (après Sprint 2)

| Issue | Titre | Fichier(s) | État |
|-------|-------|------------|------|
| #178 | Automation DSP intra-clip + reverb throw + BPM rate limit (Blocs 10-RT1+RT2+RT3) | `core/dsp.py`, `core/drift.py` | ❌ AFK ready-for-agent |
| #179 | Effects chain enrichie — 4 niveaux crisis + LadderFilter + Delay + Phaser (Bloc 13-DSP) | `core/dsp.py` | ❌ AFK ready-for-agent |
| #180 | Transitions DJ — EQ crossfade 3-bandes + filter sweep + reverb throw (Blocs 9-T1+T2+T3) | `core/dsp.py` | ❌ AFK ready-for-agent |
| #181 | Workflow audio-to-audio amélioré — pre-stretch + strength data-driven (Bloc 7) | `core/audio_queue.py` | ❌ AFK ready-for-agent |
| #182 | `rhythmic_entropy` réel + enrichir journal prompt + track_namer valeurs réelles (Bloc 6) | `core/updater.py`, `core/journal.py`, `core/track_namer.py` | ❌ AFK ready-for-agent |
| #183 | Enrichissement prompt musical — event_intensity + inference steps adaptatif (Bloc 12) | `builders/music_prompt.py` | ❌ AFK ready-for-agent |

---

## Phase 5 — Unicité Maximale

- [ ] Spectrogram ARG : messages cachés dans l'audio
- [ ] Latent Space : vraie inférence ONNX visible
- [ ] Calendrier événements automatisé (ChatGPT Birthday, DevDay)
