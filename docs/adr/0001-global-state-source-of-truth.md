# ADR-0001 — GlobalState comme seule source de vérité

**Statut :** VALIDÉ  
**Date :** 2026-05-17

## Contexte

Plusieurs composants (collecteurs, builders, DSP) ont besoin de lire l'état courant. Sans point de vérité unique, chaque composant maintient son propre état local → désynchronisation, bugs difficiles à reproduire.

## Décision

`GlobalState` (Pydantic v2) est la **seule** source de vérité. Toutes les écritures passent par `StateUpdater.queue`. Aucun collecteur ne maintient d'état local persistant.

## Conséquences

- Chaque mise à jour passe par la queue asyncio → log automatique + drift + self-model
- Les collecteurs sont des fonctions pures : `state → dict[signal, value]`
- Les tests peuvent injecter un `GlobalState` arbitraire sans effets de bord
