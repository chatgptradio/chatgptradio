# ADR-0002 — Zéro constante hardcodée dans drift/self-model

**Statut :** VALIDÉ  
**Date :** 2026-05-17

## Contexte

Le principe NO FAKE (DIRECTION.md) interdit tout mouvement non justifié par un signal réel. `random.random()` dans drift ou self-model produirait du mouvement fake visible.

## Décision

- `import random` est **interdit** dans `core/drift.py`, `core/self_model.py`, `builders/`
- Toutes les valeurs de drift dérivent des `prediction_errors` et `signal_volatilities`
- `τ` (taux d'adaptation EMA) est appris par Hebb, pas fixé à la main
- Test automatisé : `assert "import random" not in inspect.getsource(m)` dans `test_music_prompt.py`

## Conséquences

- Le drift est 100% data-driven → auditabilité totale
- Un signal à zéro = pas de mouvement = écran statique acceptable
