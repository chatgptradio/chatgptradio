# PRD — Modes `synapse` et `chaos` pour visualizer.html

## Problème

Les 4 modes visuels actuels (neural/particles/globe/nebula) ne montrent pas explicitement le "cerveau" de l'IA en train de penser, réagir et créer. Les viewers ne peuvent pas observer la computation du modèle sous forme de graphe ou de dynamiques mathématiques vivantes.

## Hypothèse

En ajoutant deux modes inspirés de templates Three.js existants — un réseau neuronal 3D signal-driven (`synapse`) et un système de particules à attracteurs mathématiques (`chaos`) — les viewers auront une représentation visuelle directe de l'état cognitif du modèle, 100% pilotée par GlobalState.

## Scope

### In scope
- Nouveau mode `synapse` dans `visualizer.html` : réseau neuronal 3D avec 4 formations, pulses d'énergie, taille de nœuds et palette pilotés par GlobalState
- Nouveau mode `chaos` dans `visualizer.html` : 15 000 particules morphant entre 4 attracteurs mathématiques (torusKnot / halvorsen / dualHelix / deJong) pilotés par GlobalState
- Extension de `SCENE_CYCLE` de 4 à 6 : `["neural", "synapse", "particles", "chaos", "globe", "nebula"]`
- Mise à jour de `DIRECTION.md` et `docs/TASKS.md`
- Tests de non-régression des 4 modes existants

### Out of scope
- Nouveaux collecteurs GlobalState
- Modifications de `core/scene_rotator.py` (déjà correct avec 4 modes — à mettre à jour pour 6)
- Nouveaux champs GlobalState

## Spec de mapping signaux → visuels

### Mode `synapse`
| Paramètre visuel | Signal GlobalState | Logique |
|---|---|---|
| Formation (default/spread/cluster/linear) | `drift_territory` | quartile : <0.25→default, 0.25–0.5→spread, 0.5–0.75→cluster, ≥0.75→linear |
| Intensité pulses | `world_event_burst` | direct [0,1] |
| Taille nœuds | `max(prediction_errors.values(), default=0)` | [0,1] → [minSize, maxSize] |
| Palette couleur | `drift_territory` | même quartile que formation |
| Caméra | — | rotation orbitale contemplatif libre (navigation, pas une donnée) |
| Fallback (tout à 0) | — | formation default, taille min, zéro pulse |

### Mode `chaos`
| Attracteur | Signal dominant | Condition |
|---|---|---|
| `torusKnot` | repos / fallback | aucun signal au-dessus du seuil |
| `halvorsen` | `max(signal_volatilities.values())` | > 0.3 ET dominant |
| `dualHelix` | `drift_territory` | ∈ [0.5, 0.75) ET dominant |
| `deJong` | `max(prediction_errors.values())` | > 0.3 ET dominant |
| Morph trigger | `world_event_burst` > 0.1 OU changement d'attracteur dominant | réévalué toutes les 30s |
| Fallback | torusKnot fixe, morphing suspendu | tous signaux < seuil |

## NO FAKE — fixes obligatoires

### Template 1 (`synapse`)
- Supprimer `autoRotate: true, autoRotateSpeed: 0.15` → rotation gérée par code
- Remplacer `sin(uTime * 0.8 + distanceFromRoot * 0.2)` dans vertex shader par uniforme `uNodeScale` piloté par `max(prediction_errors)`
- Remplacer click-to-pulse par `world_event_burst` spike trigger

### Template 2 (`chaos`)
- Supprimer le bouton "Morph Shape" et la logique `prog += morphSpeed * dt` continue
- Implémenter `targetAttractorIndex` calculé depuis GlobalState, morph déclenché sur changement
- Garder `Math.random()` uniquement à l'initialisation des positions (déjà correct)

## Acceptation

- [ ] `visualizer.html` charge les 6 modes sans erreur console
- [ ] `!switch synapse` et `!switch chaos` fonctionnent
- [ ] SCENE_CYCLE à 6 éléments dans `core/scene_rotator.py`
- [ ] Couper WebSocket → toute motion cesse dans synapse et chaos (sauf caméra)
- [ ] Les 4 modes existants ne régressent pas
- [ ] `uv run pytest && uv run pyright && uv run ruff check .` pass
