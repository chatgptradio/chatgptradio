# Plan — Phase 3 : La Température du Monde

**PRD :** `.claude/prds/phase3-collectors.md`
**Date :** 2026-05-20

## Graphe de dépendances

```
#106 utils  ──→  #107 public APIs (7 collecteurs) ─┐
              ↘  #108 Nitter + GitHub             ──┼─→ (merge individuel)
              ↘  #109 API-key collecteurs (3)     ─┘
```

#107, #108, #109 sont parallèles entre eux, bloqués par #106.

---

## Issue #106 — collectors/utils.py

**Fichiers :** `collectors/utils.py`, `tests/test_collectors_utils.py`

**Tâches :**
1. `vader_sentiment(text: str) -> float` — score VADER composé, normalisé [-1, +1]
2. `normalize(val: float, low: float, high: float) -> float` — clamp + map vers [0, 1]
3. `async fetch_text(url: str, timeout_s: float = 10.0) -> str` — aiohttp GET, raise_for_status
4. Tests : couverture ≥ 80% (sentiment positif/négatif/neutre, normalize bornée, fetch mock)

**Dépendances Python :** `vaderSentiment` (ajouter à pyproject.toml)

---

## Issue #107 — 7 collecteurs sans clé API

**Fichiers :** `collectors/{hn_algolia,wikipedia,google_trends,gdelt,hedonometer,yfinance_proxy,arxiv}.py` + tests

| Collecteur | Endpoint | Champs | Intervalle |
|------------|----------|--------|-----------|
| `hn_algolia` | `https://hn.algolia.com/api/v1/search?tags=story&query=AI+ChatGPT` | `hn_ai_score` | 5 min |
| `wikipedia` | MediaWiki pageviews API (ChatGPT + OpenAI + GPT-4) | `wikipedia_views_ai` | 15 min |
| `google_trends` | `https://trends.google.com/trends/trendingsearches/daily/rss?geo=US` | `google_trends_chatgpt`, `google_trends_openai` | 15 min |
| `gdelt` | `http://data.gdeltproject.org/gdeltv2/lastupdate.txt` → CSV | `gdelt_global_tone`, `gdelt_conflict_intensity` | 15 min |
| `hedonometer` | `https://hedonometer.org/api/v1/happiness/?lang=en&format=json` | `hedonometer_happiness` | 6 h (quotidien) |
| `yfinance_proxy` | yfinance MSFT + NVDA (lib Python) | `msft_delta`, `nvda_delta` | 4 h |
| `arxiv` | ArXiv API (search cs.AI, dernières 24h) | `arxiv_papers_today` | 1 h |

**Tests :** mock réseau, retour plausible, dégradation gracieuse sur HTTP error

---

## Issue #108 — Nitter RSS + GitHub trending

**Fichiers :** `collectors/{nitter_rss,github_trending}.py` + tests

| Collecteur | Endpoint | Champs | Notes |
|------------|----------|--------|-------|
| `nitter_rss` | `https://nitter.privacydev.net/OpenAI/rss` (ou instance de secours) | `twitter_volume`, `twitter_sentiment` | Dégradation gracieuse si instance down |
| `github_trending` | `https://api.github.com/search/repositories?q=AI+in:name,description&sort=stars` | `github_ai_stars` | Unauthenticated = 60 req/h — suffisant |

**Tests :** mock RSS valide, mock RSS vide (Nitter down), mock GitHub API

---

## Issue #109 — 3 collecteurs à clé API

**Fichiers :** `collectors/{reddit,newsapi,media_cloud}.py` + tests

| Collecteur | Lib/Endpoint | Champs | Clé env |
|------------|-------------|--------|---------|
| `reddit` | PRAW async (asyncpraw) — r/ChatGPT + r/OpenAI + r/artificial | `reddit_volume`, `reddit_sentiment` | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` |
| `newsapi` | NewsAPI.ai REST — query ChatGPT | `newsapi_volume`, `newsapi_sentiment` | `NEWSAPI_AI_KEY` |
| `media_cloud` | mediacloud Python lib | `media_cloud_ai_volume` | `MEDIA_CLOUD_API_KEY` |

**Comportement si clé absente :** log warning, `source_health[name] = False`, retour `{}`
**Tests :** mock API, clé absente → retour `{}` propre

---

## Contraintes transversales

- Pattern obligatoire : `COLLECTOR_META = {"name": ..., "interval_s": ...}` + `@node(...)` + `async def collect(state: GlobalState) -> dict[str, Any]`
- Pas de `random`, pas de constante hard-codée dans les formules de normalisation
- Timeout = 80% de l'intervalle (déjà géré par `collector_runner.run_collector`)
- `vaderSentiment` → ajouter dans `[project] dependencies` (runtime, pas scripts)

## Quality gate

```bash
uv run python -m pytest && uv run python -m pyright && uv run python -m ruff check .
```
