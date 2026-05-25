# ADR-0005 — Connexion DB unique, pas d'écriture directe depuis collecteurs

**Statut :** VALIDÉ  
**Date :** 2026-05-17

## Contexte

Avec plusieurs collecteurs asyncio tournant en parallèle, chacun pourrait ouvrir sa propre connexion SQLite → contention de verrous, corruption possible.

## Décision

- Une seule connexion `aiosqlite.Connection` créée dans `main.py` et passée aux modules qui en ont besoin
- Les collecteurs ne font **jamais** d'écriture SQLite directement — ils poussent des tuples `(signal, value)` dans `StateUpdater.queue`
- `StateUpdater` est le seul consommateur de la queue et le seul écrivain SQLite pour les snapshots/signaux

## Conséquences

- Pas de contention de verrous
- Toutes les écritures sont sérialisées dans `StateUpdater.run()`
- Exception : `audio_queue`, `journal`, `memory` ont besoin de la connexion pour leur propre table — ils la reçoivent en paramètre, ne l'ouvrent pas eux-mêmes
