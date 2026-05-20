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

### Câblage prod — TERMINÉ ✅ (vérifié 2026-05-20)

| Tâche | Fichier | État |
|-------|---------|------|
| `run_audio_queue()` dans main.py | `main.py` | ✅ mergé (PRs Phase 2) |
| `run_journal()` dans main.py | `main.py` | ✅ mergé (PRs Phase 2) |
| DB schema : table `journal_entries` | `core/db.py` | ✅ mergé |
| DB schema : colonne `viewers.display_name` | `core/db.py` | ✅ mergé |
| GlobalState : champ `journal_text` | `core/state.py` | ✅ mergé |
| `CommandEngine` instancié dans main.py | `main.py` | ⏳ dépend YouTube Live Chat |

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

Vérifié 2026-05-20 — 298 tests verts. NO FAKE validé sur tous les overlays.

| Module | Fichier | État | PR/Commit |
|--------|---------|------|-----------|
| Pedalboard DSP engine | `core/dsp.py` | ✅ mergé | 2f763f1 |
| FFmpeg → RTMP pipe | `core/dsp.py` | ✅ mergé | 2f763f1 |
| CalendarEngine 15 événements | `core/calendar_engine.py` | ✅ mergé | 2f763f1 |
| Three.js graph @node | `overlays/graph.html` | ✅ mergé | 2f763f1 |
| Three.js 4 modes (neural/particles/globe/nebula) | `overlays/visualizer.html` | ✅ mergé | 2f763f1 |
| CNN Fear & Greed collecteur | `collectors/cnn_fear_greed.py` | ✅ mergé | 2f763f1 |

---

## Phase 5 — Unicité Maximale

- [ ] Spectrogram ARG : messages cachés dans l'audio
- [ ] Latent Space : vraie inférence ONNX visible
- [ ] Calendrier événements automatisé (ChatGPT Birthday, DevDay)
