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

### À faire — câblage prod

| Tâche | Fichier | État |
|-------|---------|------|
| `run_audio_queue()` dans main.py | `main.py` | 🔄 en cours |
| `run_journal()` dans main.py | `main.py` | 🔄 en cours |
| `CommandEngine` instancié dans main.py | `main.py` | 🔄 en cours |
| DB schema : table `journal_entries` | `core/db.py` | 🔄 en cours |
| DB schema : colonne `viewers.display_name` | `core/db.py` | 🔄 en cours |
| GlobalState : champ `journal_text` | `core/state.py` | 🔄 en cours |

### Bloqué — activation YouTube requise

| Module | Fichier | État |
|--------|---------|------|
| YouTube broadcast lifecycle | `core/youtube.py` | ❌ bloqué activation YouTube |
| YouTube Live Chat polling | `collectors/chat.py` | ❌ bloqué activation YouTube |
| GPT-4o-mini réponses in-character | `collectors/chat.py` | ❌ bloqué activation YouTube |

### Prérequis manuels

| Prérequis | État |
|-----------|------|
| FFmpeg installé | ✅ OK |
| `fal-client` installé | ✅ OK (PR #83) |
| `openai` installé | ✅ OK (PR #79) |
| `FAL_API_KEY` dans `.env` | ✅ OK |
| `OPENAI_API_KEY` dans `.env` | ✅ OK |
| YouTube Studio → activation live streaming | ❌ en cours |
| Stream Key + RTMP URL dans `.env` | ❌ après activation YouTube |

---

## Phase 3 — Température du Monde (À FAIRE ❌)

Tous les collecteurs sociaux. Chaque collecteur échoue proprement (source_health=False) si la clé API est absente.

| Module | Fichier | État | Clé requise |
|--------|---------|------|-------------|
| Shared utilities (VADER, normalize, fetch) | `collectors/utils.py` | ❌ à créer | — |
| HN Algolia | `collectors/hn_algolia.py` | ❌ à créer | — |
| Wikipedia pageviews | `collectors/wikipedia.py` | ❌ à créer | — |
| Google Trends RSS | `collectors/google_trends.py` | ❌ à créer | — |
| CNN Fear & Greed | `collectors/cnn_fear_greed.py` | ❌ à créer | — |
| GDELT global tone | `collectors/gdelt.py` | ❌ à créer | — |
| Hedonometer happiness | `collectors/hedonometer.py` | ❌ à créer | — |
| yfinance MSFT/NVDA | `collectors/yfinance_proxy.py` | ❌ à créer | — |
| ArXiv papers | `collectors/arxiv.py` | ❌ à créer | — |
| GitHub trending | `collectors/github_trending.py` | ❌ à créer | — |
| Reddit PRAW | `collectors/reddit.py` | ❌ à créer | `REDDIT_CLIENT_ID/SECRET` |
| NewsAPI.ai | `collectors/newsapi.py` | ❌ à créer | `NEWSAPI_AI_KEY` |
| Media Cloud | `collectors/media_cloud.py` | ❌ à créer | `MEDIA_CLOUD_API_KEY` |

---

## Phase 4 — DSP & Visuel

| Module | Fichier | État |
|--------|---------|------|
| Pedalboard DSP engine | `core/dsp.py` | ❌ à créer |
| FFmpeg → RTMP pipe | `core/dsp.py` | ❌ à créer |
| Three.js overlay graph complet | `overlays/graph.html` | ❌ à créer |
| DJ commentary | `core/commentary.py` | ❌ à créer |

---

## Phase 5 — Unicité Maximale

- [ ] Spectrogram ARG : messages cachés dans l'audio
- [ ] Latent Space : vraie inférence ONNX visible
- [ ] Calendrier événements automatisé (ChatGPT Birthday, DevDay)
