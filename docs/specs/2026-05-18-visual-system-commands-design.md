# Design — Système Visuel + Bibliothèque Audio + Commandes Viewers

> Spec validée le 2026-05-18
> Réf : DIRECTION.md § "Interactivité chat", "Visuels", "Système d'événements"

---

## Contexte

Trois systèmes interconnectés :
1. **AudioLibrary** — les clips Stable Audio deviennent une bibliothèque sémantique réutilisable
2. **CommandEngine** — moteur de commandes viewers avec momentum voting (réutilisable pour tous les !commands)
3. **Système visuel** — 4 modes Three.js switchables + `visual_mode` dans GlobalState

---

## 1. AudioLibrary

### Table SQLite `audio_clips`

```sql
CREATE TABLE IF NOT EXISTS audio_clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL UNIQUE,
    path            TEXT    NOT NULL,
    created_at      REAL    NOT NULL,
    -- Paramètres musicaux
    drift_territory TEXT    NOT NULL DEFAULT 'ambient',
    drift_bpm       REAL    NOT NULL DEFAULT 90.0,
    drift_key       TEXT    NOT NULL DEFAULT 'C minor',
    drift_timbre    TEXT    NOT NULL DEFAULT 'warm',
    -- Vecteur émotionnel à la génération
    world_temperature   REAL NOT NULL DEFAULT 0.5,
    crisis_level        REAL NOT NULL DEFAULT 0.0,
    musical_tension     REAL NOT NULL DEFAULT 0.0,
    harmonic_complexity REAL NOT NULL DEFAULT 0.0,
    excitation          REAL NOT NULL DEFAULT 0.0,
    anxiete             REAL NOT NULL DEFAULT 0.0,
    -- Prompt
    prompt_hash     TEXT NOT NULL DEFAULT '',
    prompt_text     TEXT NOT NULL DEFAULT '',
    -- Usage
    played_count    INTEGER NOT NULL DEFAULT 0,
    last_played_at  REAL    NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_ac_territory ON audio_clips(drift_territory);
CREATE INDEX IF NOT EXISTS idx_ac_created   ON audio_clips(created_at);
```

### Convention de nommage

```
{YYYY-MM-DD}T{HH-MM-SS}_{territory}_{bpm:03d}.mp3

Exemples :
  2026-05-18T14-32-45_ambient_075.mp3
  2026-05-18T16-15-03_industrial_120.mp3
  2026-05-19T02-44-11_drone_062.mp3
```

### `core/audio_library.py`

```python
async def index_clip(conn, path: Path, state: GlobalState, prompt: str) -> None:
    """Indexer un clip nouvellement généré."""

async def find_reusable(
    conn,
    state: GlobalState,
    *,
    cooldown_s: float = 1800.0,  # pas rejoué dans les 30 min
) -> Path | None:
    """
    Chercher un clip réutilisable :
    1. WHERE drift_territory = state.drift_territory
    2. AND last_played_at < now - cooldown_s
    3. ORDER BY distance émotionnelle ASC
    4. Seuil adaptatif :
       - bibliothèque < 10 clips → seuil 2.0
       - bibliothèque ≥ 10 clips → seuil 0.8
    Retourne None si aucun match sous seuil.
    """

async def mark_played(conn, path: Path) -> None:
    """Incrémenter played_count + mettre à jour last_played_at."""

async def library_size(conn) -> int:
    """Nombre total de clips indexés."""
```

### Refactoring `core/audio_queue.py`

1. Nouveau nommage : `f"{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')}_{territory}_{bpm:03d}.mp3"`
2. Avant chaque génération : `find_reusable(conn, state)` — si match → utiliser, skip Stable Audio
3. Après génération : `index_clip(conn, path, state, prompt)`
4. Signature : ajouter `conn: aiosqlite.Connection` en paramètre

---

## 2. CommandEngine

### `core/command_engine.py`

```python
@dataclass
class CommandEngine:
    decay_rate: float = 0.05    # par seconde (half-life ≈ 14s)
    threshold: float  = 5.0     # momentum pour déclenchement
    cooldown_s: float = 120.0   # cooldown après déclenchement

    # {command: {value: momentum}}
    _votes: dict[str, dict[str, float]] = field(default_factory=dict)
    _cooldowns: dict[str, float] = field(default_factory=dict)  # command → ts unlock

    def push(self, command: str, value: str) -> None:
        """Ajouter +1.0 au momentum de command/value."""

    def tick(self, dt: float) -> dict[str, str] | None:
        """
        Appeler toutes les secondes.
        1. Décroît tous les compteurs × exp(-decay_rate × dt)
        2. Si momentum ≥ threshold et pas en cooldown :
           → retourne {command: winning_value}, reset votes, set cooldown
        3. Sinon → None
        """

    def cooldown_remaining(self, command: str) -> float:
        """Secondes restantes de cooldown pour cette commande."""
```

### Commandes V1

| Commande | Type | Mécanique | Effet |
|---|---|---|---|
| `!vibe [mode]` | momentum | voting | `state.visual_mode = mode` |
| `!request <genre>` | momentum | voting | biaise `drift_territory` via state_queue |
| `!song` | immédiat | — | réponse chat : territory/BPM/key en cours |
| `!mood` | immédiat | — | réponse chat : émotion dominante + significance |

Modes `!vibe` valides : `neural`, `particles`, `globe`, `nebula`.
`!vibe` sans argument → cycle au suivant.

Genres `!request` valides : `ambient`, `electronic`, `jazz`, `industrial`, `neoclassical`, `experimental`, `drone`.

### Auto-rotation

```python
async def run_visual_rotation(
    state: GlobalState,
    cmd_engine: CommandEngine,
    state_queue: asyncio.Queue,
    interval_s: int = 600,  # 10 min par défaut
) -> None:
    _CYCLE = ["neural", "particles", "globe", "nebula"]
    idx = 0
    while True:
        await asyncio.sleep(interval_s)
        if cmd_engine.cooldown_remaining("vibe") > 0:
            continue  # un viewer vient de voter → ne pas écraser
        idx = (idx + 1) % len(_CYCLE)
        await state_queue.put({"visual_mode": _CYCLE[idx]})
```

---

## 3. GlobalState — 1 ajout

```python
visual_mode: str = "neural"   # "neural" | "particles" | "globe" | "nebula"
```

Dans la catégorie 5 (État du Contenu).

---

## 4. Système visuel — `overlays/visualizer.html`

Fichier unique, modes switchables via `state.visual_mode`. Conserve `overlays/graph.html` existant.

### Architecture JS

```js
// Interface commune par mode
const MODE_API = {
  init(scene, camera) {},   // créer géométries
  update(state, dt) {},     // appelé chaque frame
  dispose(scene) {},        // cleanup
}

// Transition : fondu noir 0.3s → dispose → init → fondu retour 0.3s
```

### Mode NEURAL (lisible)

```
8 colonnes (une par catégorie GlobalState)
Sphères empilées par colonne :
  taille      = normalize(valeur, 0, 1) × [0.12, 0.5]
  emissive    = |prediction_error| / volatilité (z-score, capped à 3)
  couleur     = par catégorie

Connexions inter-colonnes :
  visibles si |PE| > 1σ
  particules glissant G→D, vitesse ∝ PE magnitude
  disparaissent si PE sous seuil

Catégories + couleurs :
  Monde       #FF6B35   Infrastructure  #10A37F
  Dérive      #00D4FF   Audience        #9B59B6
  Contenu     #F39C12   Système         #7F8C8D
  Self-model  #E74C3C   Dérivés         #2ECC71
```

### Mode PARTICLES (hypnotique)

```
~3000 particules THREE.Points
  attraction centre    ∝ crisis_level
  vélocité globale     ∝ world_temperature
  turbulence bruit 3D  ∝ anomaly_score
  teinte HSL :
    hue        = drift_bpm mappé 200°–280° (bleu→violet)
    saturation = musical_tension
    luminosité = excitation
Aucune légende
```

### Mode GLOBE (lisible)

```
Icosaèdre wireframe, rotation lente (0.002 rad/s)
Arcs lumineux sources → centre :
  Reddit      USA Ouest   #FF4500
  HN          USA Est     #FF6600
  GDELT       multi-arcs  #AAAAFF
  Hedonometer équateur    #FFDD00
  ArXiv       multi-pôles #FFFFFF
  Wikipedia   global      #88AAFF
  yfinance    NY + Tokyo  #44FF44
Intensité arc = valeur normalisée du signal
Teinte fond hémisphère = gdelt_global_tone (froid→chaud)
```

### Mode NEBULA (ésotérique)

```
Trajectoire dans espace émotionnel 3D :
  X = excitation - anxiete
  Y = curiosite  - melancolie
  Z = creativite - urgence

Point courant = sphère principale lumineuse
Trail 24h    = tube de particules, opacité ∝ âge
Fond         = shader noise procédural, teinte = drift_territory
  ambient        → bleu profond   #000820
  electronic     → cyan           #001820
  industrial     → rouge sombre   #200000
  experimental   → violet         #100020
  drone          → gris           #080808
Caméra orbit lente autour de la trajectoire
```

### HUD commun

```
Bas gauche  : territoire ◆ | BPM | key | crisis indicator
Bas droite  : journal_text
Haut droite : source_health (● / ○ par source)
Haut gauche : ws-status + mode indicator (discret, #334)
```

---

## 5. Intégration `main.py`

```python
cmd_engine = CommandEngine()
# passer cmd_engine à run_audio_queue et run_visual_rotation
asyncio.create_task(run_visual_rotation(state, cmd_engine, updater.queue))
```

---

## Issues verticales

```
#A AudioLibrary + audio_queue refactor   → pas de bloqueur
#B CommandEngine + visual_mode + rotation → pas de bloqueur
      ↓                    ↓
#C neural mode         #D particles mode    (bloqués par B)
#E globe mode          #F nebula mode       (bloqués par B)
      ↓
#G Commands (!song, !mood, !request, !vibe) → bloqué par A + B
```

A et B peuvent tourner en parallèle.
C, D, E, F peuvent tourner en parallèle après B.
G attend A + B.

---

## Décisions de test

- `CommandEngine` : `test_push_increments`, `test_decay`, `test_threshold_triggers`,
  `test_cooldown_blocks`, `test_cycle_without_arg`
- `AudioLibrary` : `find_reusable` avec fixtures SQLite, seuil adaptatif, cooldown,
  `index_clip` roundtrip, `mark_played`
- `audio_queue` refactoré : mock `find_reusable` retournant un Path → skip génération ;
  mock retournant None → génération déclenchée
- `run_visual_rotation` : mock state, vérifier cycle + respect cooldown
- Modes JS : validation visuelle dans OBS (pas de tests unitaires WebGL)

## Hors scope

- `!why`, `!ask`, `!predict`, `!memory`, `!state`, `!energy`, `!crisis`
- Rétention automatique (gestion manuelle par l'opérateur)
- OBS WebSocket automation
- Nitter RSS (déjà exclu)
