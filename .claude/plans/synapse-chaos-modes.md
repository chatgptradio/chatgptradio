# Plan — Modes `synapse` et `chaos`

PRD: `.claude/prds/synapse-chaos-modes.md`

## Micro-tâches

### T1 — Étendre SCENE_CYCLE à 6 (core/scene_rotator.py)
- Changer `SCENE_CYCLE` : `["neural", "synapse", "particles", "chaos", "globe", "nebula"]`
- Mettre à jour tests `test_scene_rotator.py` (cycle order, wrap-around)
- Mettre à jour tests `test_chat_commands.py` (!switch next-mode depuis chaque position)
- **Bloquant pour** : T2, T3 (validation SCENE_CYCLE)

### T2 — Mode `synapse` dans visualizer.html
Fichier : `overlays/visualizer.html`

Étapes :
1. Extraire le code Three.js de `templates/interactive-neural-network-viz/src/index.html`
2. Créer classe `SynapseMode` suivant le pattern des modes existants (init/update/destroy)
3. NO FAKE fixes :
   - Supprimer `autoRotate`
   - Vertex shader : remplacer `sin(uTime * 0.8)` par `uNodeScale` uniform
   - Pulses : déclencher sur `world_event_burst` spike (threshold 0.1)
4. Signal mapping :
   - `uFormation` (0-3) ← `drift_territory` quartile
   - `uNodeScale` ← `max(prediction_errors.values(), default=0)`
   - `uPulseIntensity` ← `world_event_burst`
   - `uPaletteIndex` (0-3) ← `drift_territory` quartile
5. Ajouter `synapse: SynapseMode` dans MODES registry
- **Bloquant pour** : T4

### T3 — Mode `chaos` dans visualizer.html
Fichier : `overlays/visualizer.html`

Étapes :
1. Extraire le code Three.js de `templates/three-js-glsl-particle-metamorphosis/src/index.html`
2. Créer classe `ChaosMode` suivant le pattern des modes existants
3. NO FAKE fixes :
   - Supprimer bouton "Morph Shape" et `prog += morphSpeed * dt` continu
   - Implémenter `computeTargetAttractor(state)` → index 0-3
   - Morph déclenché sur changement d'attracteur OU `world_event_burst > 0.1`
4. Signal mapping :
   - Attractor index ← logique dominance signals (voir PRD)
   - Morph speed ← `world_event_burst` (événement fort = morph rapide)
   - Particle brightness/bloom ← `max(prediction_errors)`
5. Ajouter `chaos: ChaosMode` dans MODES registry
- **Bloquant pour** : T4

### T4 — Intégration + tests manuels NO FAKE
- Vérifier que les 6 modes se chargent sans erreur console
- Test NO FAKE : couper WebSocket → synapse et chaos se figent (sauf caméra)
- Test !switch avec les 6 modes
- Vérifier non-régression des 4 modes existants (neural/particles/globe/nebula)

### T5 — Mise à jour docs
- `DIRECTION.md` : ajouter `synapse` et `chaos` dans liste des modes visuels
- `docs/TASKS.md` : marquer tâches templates comme ✅

### T6 — Quality gate + PR
```bash
uv run pytest && uv run pyright && uv run ruff check .
```
- PR : `feat: add synapse and chaos visual modes`

## Dépendances

```
T1 ──► T2 ──► T4 ──► T5 ──► T6
T1 ──► T3 ──► T4
```

T2 et T3 peuvent s'exécuter en parallèle après T1.

## Issues GitHub à créer

| # | Titre | Label | Bloqueur |
|---|---|---|---|
| A | Extend SCENE_CYCLE to 6 modes (synapse, chaos) | AFK, ready-for-agent | — |
| B | Add SynapseMode to visualizer.html | AFK, ready-for-agent | A |
| C | Add ChaosMode to visualizer.html | AFK, ready-for-agent | A |
| D | NO FAKE validation + docs update | HITL | B, C |
