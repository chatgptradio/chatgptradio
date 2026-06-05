# Design — Mémoire Persistante inter-sessions

> Spec validée le 2026-05-18
> Réf : DIRECTION.md § "Mémoire Persistante" (priorité #2 V1), ADR-0005

---

## Contexte

Phase 2 implémente la génération musicale et le DSP. La mémoire persistante est la couche qui
donne à l'entité une continuité inter-sessions : elle se souvient de ce qu'elle a "pensé",
reprend sa trajectoire musicale sans reset à 0.0, et reconnaît les viewers réguliers.

Sans cette couche :
- Chaque redémarrage repart d'un GlobalState vierge (signal_baselines = {}, drift_momentum = {})
- Le journal génère des entrées sans connaissance de ce qui précède
- `regulars_ratio` et `unique_viewers_total` restent à 0 indéfiniment

---

## Architecture

```
Démarrage :
  init_db() → restore_self_model(conn, state)
                  ↑
         lit le dernier state_snapshot
         restaure : signal_baselines, signal_volatilities,
                    drift_momentum, drift_weights
                    (pas viewers, cpu, ni champs live)

Boucle journal (toutes les 5 min) :
  load_memory_context(conn, state)
    → journal_entries (10 dernières)
    → signal_trends (deltas 30 min depuis signal_history)
    → recognized_viewers (actifs ≥ 3 sessions)
  ↓
  _build_user_prompt(state, memory_ctx)
  ↓
  GPT call → entry text
  ↓
  save_journal_entry(conn, entry)
  state_queue.put({"journal_text": entry})

Viewers (infrastructure prête, branchée lors de l'activation YouTube) :
  upsert_viewer(conn, viewer_id, display_name)
  → INSERT OR REPLACE + session_count += 1 + last_seen = now()

Maintenance (toutes les 24h via run_maintenance()) :
  purge_old_data(snapshot_days=30, history_days=30,
                 journal_days=30, viewer_inactive_days=90)
  + rotation decisions.log si > 10 MB
```

---

## Schéma DB

### Nouvelle table : `journal_entries`

```sql
CREATE TABLE IF NOT EXISTS journal_entries (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    REAL    NOT NULL,
    entry TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_je_ts ON journal_entries(ts);
```

### Migration additive : `viewers.display_name`

```sql
-- exécuté au démarrage si la colonne est absente
ALTER TABLE viewers ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
```

`purge_old_data()` reçoit deux nouveaux paramètres :
- `journal_days: int = 30` — supprime les entrées journal plus anciennes
- `viewer_inactive_days: int = 90` — supprime les viewers inactifs depuis > 90j

---

## Module `core/memory.py`

Interface publique complète :

```python
@dataclass
class MemoryContext:
    journal_entries: list[str]       # N dernières entrées texte
    signal_trends: dict[str, float]  # delta 30 min par signal clé
    recognized_viewers: list[str]    # display_name des réguliers actifs

async def load_memory_context(
    conn: aiosqlite.Connection,
    state: GlobalState,
    *,
    journal_limit: int = 10,
    trend_window_min: int = 30,
) -> MemoryContext: ...
# signal_trends : calcule delta = valeur courante − moyenne signal_history
# sur les 5 signaux : excitement, anxiety, crisis_level,
#                     world_temperature, anomaly_score

async def save_journal_entry(conn: aiosqlite.Connection, entry: str) -> None: ...

async def restore_self_model(conn: aiosqlite.Connection, state: GlobalState) -> None: ...
# Lit le dernier state_snapshot, copie dans state :
#   signal_baselines, signal_volatilities, drift_momentum, drift_weights
# Ne touche pas : viewers, cpu_percent, memory_percent, drift_bpm,
#                 journal_text, viewers, chat_rate, etc.
# No-op si aucun snapshot existant (premier démarrage)

async def upsert_viewer(
    conn: aiosqlite.Connection,
    viewer_id: str,
    display_name: str,
) -> None: ...
# INSERT OR REPLACE + session_count += 1 + last_seen = now()

async def get_active_regulars(
    conn: aiosqlite.Connection,
    min_sessions: int = 3,
) -> list[str]: ...
# Retourne display_name des viewers session_count >= min_sessions
```

---

## Modifications `core/journal.py`

`run_journal` reçoit `conn: aiosqlite.Connection` en paramètre supplémentaire.

`_build_user_prompt(state, ctx: MemoryContext | None)` — quand `ctx` est présent,
trois blocs s'ajoutent au prompt existant :

```
Tes 10 dernières entrées :
[03:14] Delta émotionnel ...
[03:22] Divergence détectée ...

Variations 30 dernières minutes :
excitement: +0.12, anxiety: -0.05, crisis_level: 0.00,
world_temperature: +0.08, anomaly_score: +0.03

Viewers réguliers actifs cette session :
nightowl_42 (session #34), morningbird (session #7)
```

Boucle modifiée :
1. `ctx = await load_memory_context(conn, state)`
2. `prompt = _build_user_prompt(state, ctx)`
3. appel GPT
4. `await save_journal_entry(conn, entry)`

---

## Modifications `main.py`

```python
# après init_db, avant tout collecteur
db_conn = await init_db(config.sqlite.path)
await restore_self_model(db_conn, state)

# run_journal reçoit db_conn
asyncio.create_task(run_journal(state, updater.queue, db_conn))

# nouvelle coroutine de maintenance
async def run_maintenance(conn):
    while True:
        await purge_old_data(conn,
            snapshot_days=30, history_days=30,
            journal_days=30, viewer_inactive_days=90)
        _rotate_decisions_log()
        await asyncio.sleep(86400)
```

`_rotate_decisions_log()` : si `streams/decisions.log` > 10 MB,
rename → `decisions.log.1` (écrase), crée nouveau fichier vide.

`run_maintenance` ajouté à `all_tasks` dans le graceful shutdown.

---

## Décisions de test

**Ce qu'on teste (comportement externe, pas implémentation) :**
- `restore_self_model` : après persist_snapshot + restore, signal_baselines correspondent
- `restore_self_model` : no-op si DB vide (premier démarrage)
- `save_journal_entry` + `load_memory_context` : les entrées sauvegardées apparaissent dans le contexte
- `signal_trends` : delta correct calculé depuis signal_history
- `upsert_viewer` : session_count s'incrémente à chaque appel
- `get_active_regulars` : retourne uniquement les viewers >= min_sessions
- `purge_old_data` étendu : supprime journal_entries et viewers inactifs anciens
- `run_journal` avec `conn` : sauvegarde l'entrée générée en SQLite
- `_build_user_prompt` avec MemoryContext : blocs history/trends/viewers présents

**Prior art dans le codebase :**
- `tests/test_db.py` — pattern fixture `conn` (tmp_path + init_db) à réutiliser
- `tests/test_journal.py` — pattern mock client API à réutiliser

---

## Hors scope

- Lecture de la mémoire depuis un dashboard externe
- Export/import de la DB entre machines
- Compression des snapshots (SQLite WAL suffit pour V1)
- Recherche full-text dans journal_entries
