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

## Phase 2 — Contenu & Mémoire (EN COURS 🔄)

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
| Three.js 4 modes (neural/synapse/particles/chaos) | `overlays/visualizer.html` | ✅ mergé | PR #118 |
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

---

## Phase 5 — Unicité Maximale

- [ ] Spectrogram ARG : messages cachés dans l'audio
- [ ] Latent Space : vraie inférence ONNX visible
- [ ] Calendrier événements automatisé (ChatGPT Birthday, DevDay)
