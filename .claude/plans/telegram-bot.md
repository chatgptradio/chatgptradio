# Plan — Telegram Bot bidirectionnel

**PRD:** `.claude/prds/telegram-bot.md`
**Spec:** `docs/specs/2026-05-28-telegram-bot-design.md`
**Date:** 2026-05-28

---

## Graphe de dépendances

```
#A (skeleton + dépendances + allowlist)
    └── #B (WebSocket client + AlertWatcher)
            └── #C (command handlers)
                    └── #E (tests)
#D (systemd service script)   ← indépendant de tout
```

Issues sans bloqueurs au départ : **#A et #D en parallèle**

---

## Issue A — Skeleton + dépendances + middleware allowlist

**Fichiers :** `pyproject.toml`, `telegram_bot.py` (squelette), `.env.example`

**Tâches :**
1. Ajouter `python-telegram-bot>=20.0` dans `pyproject.toml` (section `dependencies`)
2. Ajouter `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env.example` avec valeurs vides
3. Créer `telegram_bot.py` avec :
   - Import PTB, asyncio, websockets, structlog, dotenv
   - Chargement `.env` (TOKEN + CHAT_ID)
   - Middleware `allowlist_filter` : vérifie `update.effective_chat.id == TELEGRAM_CHAT_ID`, ignore sinon
   - `main()` : PTB `ApplicationBuilder`, ajout du filtre, `run_polling()`
   - Entrée `if __name__ == "__main__": main()`
4. Vérifier `uv run python telegram_bot.py --help` ne crashe pas (smoke test)

**Acceptance criteria :**
- `uv add python-telegram-bot>=20.0` passe
- `.env.example` contient les deux nouvelles vars
- Un message Telegram depuis un chat_id non autorisé produit 0 réponse

---

## Issue B — WebSocket client + cache état + AlertWatcher

**Fichiers :** `telegram_bot.py`
**Bloque :** Issue A

**Tâches :**
1. Ajouter `_state_cache: dict = {}` global (mis à jour par le WebSocket)
2. Implémenter `watch_websocket(bot, chat_id)` coroutine asyncio :
   - Connexion à `ws://localhost:8765`
   - Parsing JSON → mise à jour `_state_cache`
   - Disconnect → debounce 30s → alerte DOWN → backoff exponentiel 1→2→4→8→16→30s
   - Reconnexion → alerte UP (si DOWN précédent)
   - Utilise timestamp (pas `asyncio.sleep` bloquant) pour le debounce
3. Lancer `watch_websocket` comme tâche asyncio dans `main()` via `ApplicationBuilder.post_init`
4. Logger les événements DOWN/UP avec structlog

**Acceptance criteria :**
- Couper le WebSocket (arrêter main.py) → alerte DOWN reçue en < 35s
- Relancer main.py → alerte UP reçue
- Deux disconnects en < 30s → une seule alerte DOWN (debounce OK)
- `_state_cache` contient les champs GlobalState après connexion

---

## Issue C — Command handlers

**Fichiers :** `telegram_bot.py`
**Bloque :** Issue B

**Tâches :**
1. Implémenter handler `/status` :
   - Vérifier `systemctl --user is-active chatgpt-radio.service` via `asyncio.create_subprocess_exec`
   - Retourner : état service, `uptime_h`, `stream_bitrate`, `dropped_frames` depuis `_state_cache`
   - Si `_state_cache` vide (WebSocket down) : indiquer "état WebSocket indisponible" + statut systemd seulement
2. Implémenter handler `/music` :
   - Retourner : `current_track_name`, `drift_territory`, `drift_bpm`, `drift_energy`
3. Implémenter handler `/viewers` :
   - Retourner : `viewers`, `viewers_peak_today`, `chat_rate`
4. Implémenter handler `/health` :
   - Retourner : `source_health` (liste OK/KO), `cpu_percent`, `memory_percent`
5. Implémenter handler `/restart` :
   - Envoyer message "Relancement en cours..."
   - `asyncio.create_subprocess_exec("bash", "/home/stream/streaming/scripts/restart.sh")` (pas de shell=True)
   - Attendre fin + retourner les 20 dernières lignes de `/tmp/stream_restart.log`
6. Enregistrer tous les handlers dans `main()` avec le filtre allowlist

**Acceptance criteria :**
- `/status` retourne les champs attendus quand WebSocket up
- `/status` retourne état systemd seulement quand WebSocket down
- `/restart` lance `restart.sh`, retourne le log, sans injection possible
- `/health` liste correctement les collecteurs OK/KO

---

## Issue D — Service systemd + script d'installation

**Fichiers :** `scripts/install_tg_service.sh`
**Aucun bloqueur**

**Tâches :**
1. Créer `scripts/install_tg_service.sh` :
   - Écrit `~/.config/systemd/user/chatgpt-radio-tg.service`
   - `ExecStart=uv run python /home/stream/streaming/telegram_bot.py`
   - `WorkingDirectory=/home/stream/streaming`
   - `EnvironmentFile=/home/stream/streaming/.env`
   - `Restart=always`, `RestartSec=5`
   - `After=network.target`
   - `systemctl --user daemon-reload && systemctl --user enable chatgpt-radio-tg.service`
2. Documenter dans le script : `echo "Démarrer avec : systemctl --user start chatgpt-radio-tg.service"`
3. Rendre exécutable (`chmod +x`)

**Acceptance criteria :**
- `bash scripts/install_tg_service.sh` crée le fichier `.service` et l'active
- `systemctl --user status chatgpt-radio-tg.service` montre `enabled`

---

## Issue E — Tests

**Fichiers :** `tests/test_telegram_bot.py`
**Bloque :** Issues A + B + C

**Tâches :**
1. Test allowlist : message d'un chat_id non autorisé → handler non appelé
2. Test alertes : mock WebSocket disconnect → `send_message` DOWN appelé après 30s (freeze time)
3. Test debounce : 2 disconnects en < 30s → une seule alerte
4. Test alerte UP : reconnexion après DOWN → `send_message` UP appelé
5. Test `/status` avec `_state_cache` rempli → champs corrects dans la réponse
6. Test `/status` avec `_state_cache` vide → réponse "état WebSocket indisponible"
7. Test `/restart` : mock `asyncio.create_subprocess_exec` → vérifie args sans `shell=True`
8. Coverage ≥ 80% sur `telegram_bot.py`

**Acceptance criteria :**
- `uv run pytest tests/test_telegram_bot.py` : tous verts
- `uv run pyright` : 0 erreur
- `uv run ruff check .` : 0 warning
