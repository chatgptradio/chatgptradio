# PRD — Phase 3 : La Température du Monde (13 collecteurs)

**Date :** 2026-05-20
**Statut :** APPROUVÉ

## Problème

GlobalState contient 13+ champs collecteur-driven qui sont en permanence à 0. La dérive musicale, le journal, et le music_prompt tournent sur des données manquantes. L'entité est sourde au monde.

## Hypothèse

Implémenter les 13 collecteurs en 4 waves dépendantes activera le GlobalState complet et rendra le stream réactif aux signaux réels du monde.

## Scope

### Inclus
- `collectors/utils.py` — VADER, normalize(), fetch() partagés (dépendance de base)
- 7 collecteurs sans clé API : HN Algolia, Wikipedia, Google Trends RSS, GDELT, Hedonometer, yfinance, ArXiv
- 2 collecteurs sans clé obligatoire : Nitter RSS (dégradation gracieuse), GitHub trending
- 3 collecteurs avec clé API : Reddit PRAW, NewsAPI.ai, Media Cloud

### Exclus
- RoBERTa / transformers (V2 si qualité VADER insuffisante sur Reddit)
- Twitter API officielle (abandonnée — ADR)
- Stanza (À EXPLORER plus tard)

## Décisions de design

| Décision | Choix |
|----------|-------|
| Sentiment lib | VADER uniquement (V1) |
| Nitter RSS | Inclure, dégradation gracieuse si instances down |
| Groupement | 4 waves logiques (utils → public → Nitter+GitHub → API-key) |
| Waves 2+3+4 | Parallèles entre elles, débloquées par wave 1 |

## Signaux produits

| Collecteur | Champs GlobalState |
|------------|-------------------|
| HN Algolia | `hn_ai_score` |
| Wikipedia | `wikipedia_views_ai` |
| Google Trends RSS | `google_trends_chatgpt`, `google_trends_openai` |
| GDELT | `gdelt_global_tone`, `gdelt_conflict_intensity` |
| Hedonometer | `hedonometer_happiness` |
| yfinance | `msft_delta`, `nvda_delta` |
| ArXiv | `arxiv_papers_today` |
| Nitter RSS | `twitter_volume`, `twitter_sentiment` |
| GitHub trending | `github_ai_stars` |
| Reddit PRAW | `reddit_volume`, `reddit_sentiment` |
| NewsAPI.ai | `newsapi_volume`, `newsapi_sentiment` |
| Media Cloud | `media_cloud_ai_volume` |

## Acceptation globale

- Chaque collecteur suit le pattern `openai_status.py` : `COLLECTOR_META` + `@node` + `async def collect(state) -> dict`
- Chaque collecteur échoue proprement : `source_health[name] = False` sans crash
- Si la clé API est absente : log warning + return `{}` (pas de crash)
- 80%+ coverage pytest sur chaque module
- pyright + ruff 0 erreur
