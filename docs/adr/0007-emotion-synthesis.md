# ADR-0007 — Couche de synthèse émotionnelle (_synthesize_emotions)

**Statut :** VALIDÉ  
**Date :** 2026-05-21

## Contexte

Les 5 champs émotionnels centraux de `GlobalState` — `excitement`, `anxiety`, `frustration`, `curiosity`, `creativity` — ne sont jamais écrits en production. `compute_derived()` les *lit* pour calculer `world_temperature`, `musical_tension`, `harmonic_complexity`, mais aucun chemin de code ne les *écrit*.

Conséquence mesurée :

| Champ dérivé | Formule | Valeur réelle |
|---|---|---|
| `world_temperature` | `(excitement + anxiety + frustration + curiosity + creativity) / 5` | **0.0 toujours** |
| `musical_tension` | `anxiety * 0.5 + frustration * 0.5` | **0.0 toujours** |
| `harmonic_complexity` | `curiosity * 0.6 + creativity * 0.4` | **0.0 toujours** |
| Key transition | `pe["anxiety"] + pe["frustration"] > volatility` | **jamais déclenché** |
| BPM drift | pondéré par `excitement`, `audience_energy`, `world_temperature` | **quasi-nul** |
| Territoires `electronic`, `industrial`, `jazz`, `neoclassical`, `noise` | scoring via PEs émotionnels | **score 0, jamais sélectionnés** |

Le système dérive uniquement via `wonder`, `melancholy`, `urgency` — correctement calculés depuis arxiv/hedonometer/github. Il est émotionnellement sourd aux volumes Reddit, conflits GDELT, sentiments négatifs, indicateurs financiers.

Cause racine : la couche de synthèse — qui devait mapper les prediction errors des collecteurs vers les champs émotionnels — n'a jamais été implémentée lors de la conception de `compute_derived()`.

## Décision

Ajouter `_synthesize_emotions(state: GlobalState) -> None` dans `core/updater.py`, appelée au **début** de `compute_derived()`, avant tous les calculs qui dépendent des 5 émotions.

Chaque émotion est une somme pondérée de z-scores de prediction errors :  
`_z(signal) = pe.get(signal, 0.0) / max(vol.get(signal, 0.1), 0.001)`

```python
def _synthesize_emotions(state: GlobalState) -> None:
    pe = state.prediction_errors
    vol = state.signal_volatilities
    def _z(s): return pe.get(s, 0.0) / max(vol.get(s, 0.1), 0.001)

    state.excitement = _clamp(
        0.25 * _z("reddit_volume") + 0.25 * _z("twitter_volume")
        + 0.2 * _z("hn_ai_score") + 0.15 * _z("hedonometer_happiness")
        + 0.15 * _z("google_trends_chatgpt"), -1.0, 1.0
    )
    state.anxiety = _clamp(
        0.4 * _z("gdelt_conflict_intensity") + 0.3 * (1.0 - state.openai_status)
        + 0.2 * _z("newsapi_volume") + 0.1 * _z("fear_greed_index"), -1.0, 1.0
    )
    state.frustration = _clamp(
        -0.4 * _z("reddit_sentiment") - 0.3 * _z("twitter_sentiment")
        - 0.2 * _z("newsapi_sentiment") - 0.1 * _z("hedonometer_happiness"), -1.0, 1.0
    )
    state.curiosity = _clamp(
        0.4 * _z("arxiv_papers_today") + 0.3 * _z("github_ai_stars")
        + 0.2 * _z("wikipedia_views_ai") + 0.1 * _z("hn_ai_score"), -1.0, 1.0
    )
    state.creativity = _clamp(
        0.4 * _z("media_cloud_ai_volume") + 0.3 * state.source_divergence
        + 0.3 * _z("github_ai_stars"), -1.0, 1.0
    )
```

### Justification des mappings

| Émotion | Signaux sources | Raisonnement |
|---------|----------------|--------------|
| `excitement` | reddit_volume, twitter_volume, hn_ai_score, hedonometer_happiness, google_trends_chatgpt | Activité collective en hausse → enthousiasme communautaire |
| `anxiety` | gdelt_conflict_intensity, openai_status (inverse), newsapi_volume, fear_greed_index | Conflits mondiaux + infra défaillante + volume news + peur marché |
| `frustration` | reddit_sentiment (inverse), twitter_sentiment (inverse), newsapi_sentiment (inverse), hedonometer_happiness (inverse) | Sentiment négatif persistant sur plusieurs canaux |
| `curiosity` | arxiv_papers_today, github_ai_stars, wikipedia_views_ai, hn_ai_score | Effervescence de la recherche et de l'exploration |
| `creativity` | media_cloud_ai_volume, source_divergence, github_ai_stars | Diversité des perspectives + projets actifs |

### Pondérations : provisoires et empiriques

**Ces pondérations ne sont pas des vérités physiques.** Elles constituent une hypothèse de départ raisonnée. Elles devront être ajustées empiriquement après observation du comportement réel du stream sur plusieurs sessions. La modification d'une pondération ne nécessite pas un nouvel ADR — c'est un paramètre d'ajustement, pas une décision architecturale.

### Relation avec ADR-0002

ADR-0002 interdit les constantes hardcodées dans `core/drift.py` et `core/self_model.py`. Les pondérations de `_synthesize_emotions` sont dans `core/updater.py:compute_derived()`, hors du périmètre d'ADR-0002. Elles ne produisent pas de mouvement "fake" — si tous les PEs sont à zéro, toutes les émotions restent à zéro.

## Alternatives considérées

**A. Nouveaux collecteurs dédiés aux émotions** — rejeté. Ajoute des dépendances externes sans signal nouveau ; les données existent déjà dans les PEs des collecteurs actuels.

**B. Écriture des émotions depuis les collecteurs individuels** — rejeté. Viole ADR-0001 (état local dans les collecteurs) et ADR-0005 (écriture directe hors StateUpdater).

**C. LLM pour synthèse émotionnelle** — rejeté. Latence incompatible avec le cycle `compute_derived()` (appelé à chaque update), coût unjustifié, viole ADR-0004 (pas de dépendance LLM dans le hot path).

## Conséquences

- `world_temperature`, `musical_tension`, `harmonic_complexity` deviennent actifs
- La dérive BPM, key, territory fonctionne sur les 8 dimensions prévues (pas 3)
- Les territoires `electronic`, `industrial`, `jazz`, `neoclassical`, `noise` deviennent atteignables
- Les transitions de tonalité (CIRCLE_OF_FIFTHS) se déclenchent maintenant
- `update_self_model()` apprend les baselines des 5 émotions → amélioration continue du self-model
- NO FAKE respecté : si aucun collecteur ne fournit de données, toutes les émotions restent à 0
