# Telegram Bot — Design Spec

**Date:** 2026-05-28
**Scope:** Bot Telegram bidirectionnel pour monitoring et contrôle du stream ChatGPT Radio
**Statut:** VALIDÉ

---

## Contexte

ChatGPT Radio tourne 24/7 sans supervision constante. Il faut un canal d'alerte et de contrôle accessible depuis un téléphone. Le bot doit pouvoir signaler un crash même quand `main.py` est mort.

---

## Architecture

### Processus séparé (hors main.py)

Le bot tourne comme service systemd indépendant (`chatgpt-radio-tg.service`). Il **ne vit pas dans `main.py`** — c'est la contrainte fondamentale : il doit survivre au crash du stream pour pouvoir alerter.

```
chatgpt-radio-tg.service
  └── telegram_bot.py
        ├── PTB Application (polling)
        ├── WebSocket client → ws://localhost:8765
        └── AlertWatcher (tâche asyncio)
```

Communication avec le stream : lecture du WebSocket `:8765` (GlobalState JSON à 10fps). Le bot ne modifie jamais l'état — read-only sur GlobalState.

### Fichiers

```
streaming/
├── telegram_bot.py               ← point d'entrée du bot (processus autonome)
├── scripts/install_tg_service.sh ← installe chatgpt-radio-tg.service
└── .env                          ← TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (déjà gitignored)
```

---

## Sécurité

- `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env` uniquement, jamais hardcodés
- Middleware d'allowlist : toute commande d'un `chat_id` différent de `TELEGRAM_CHAT_ID` est ignorée silencieusement (pas de réponse d'erreur — évite la reconnaissance)
- `/restart` déclenche `scripts/restart.sh` via `asyncio.create_subprocess_exec` — aucune interpolation shell, pas de command injection possible

---

## Commandes

| Commande | Description | Champs GlobalState utilisés |
|---|---|---|
| `/status` | État service systemd, uptime, bitrate, dropped_frames | `uptime_h`, `stream_bitrate`, `dropped_frames` |
| `/music` | Track en cours, territoire drift, BPM | `current_track_name`, `drift_territory`, `drift_bpm`, `drift_energy` |
| `/viewers` | Viewers live, pic du jour, chat rate | `viewers`, `viewers_peak_today`, `chat_rate` |
| `/health` | Collecteurs OK/KO, CPU, mémoire | `source_health`, `cpu_percent`, `memory_percent` |
| `/restart` | Lance `scripts/restart.sh`, retourne les 20 dernières lignes du log | — |

Toutes les commandes de lecture nécessitent une connexion WebSocket active. Si le WebSocket est down, les commandes `/status`, `/music`, `/viewers`, `/health` répondent avec l'état du service systemd seulement.

---

## Alertes proactives

### Stream DOWN
- **Déclencheur :** WebSocket disconnect (connexion perdue ou refusée)
- **Message :** `🔴 Stream DOWN — WebSocket déconnecté`
- **Debounce :** 30s avant d'envoyer — évite le spam sur micro-coupure réseau

### Stream UP
- **Déclencheur :** Reconnexion WebSocket réussie après une alerte DOWN
- **Message :** `🟢 Stream UP — reconnecté`
- **Condition :** Envoyé uniquement si une alerte DOWN avait été émise (pas au démarrage initial)

---

## Reconnexion WebSocket

Backoff exponentiel : 1s → 2s → 4s → 8s → 16s → 30s (plafond). Le bot ne crashe jamais sur disconnect — il boucle indéfiniment jusqu'à reconnexion.

```python
# Pseudo-code
async def watch_websocket():
    delay = 1
    was_down = False
    while True:
        try:
            async with websockets.connect("ws://localhost:8765") as ws:
                delay = 1
                if was_down:
                    await send_alert("🟢 Stream UP — reconnecté")
                    was_down = False
                async for msg in ws:
                    _update_local_state(msg)
        except Exception:
            if not was_down:
                await asyncio.sleep(30)  # debounce
                was_down = True
                await send_alert("🔴 Stream DOWN — WebSocket déconnecté")
            await asyncio.sleep(min(delay, 30))
            delay *= 2
```

---

## Service systemd

Fichier : `~/.config/systemd/user/chatgpt-radio-tg.service`

```ini
[Unit]
Description=ChatGPT Radio — Telegram Bot
After=network.target

[Service]
WorkingDirectory=/home/stream/streaming
ExecStart=/home/stream/.local/bin/uv run python telegram_bot.py
Restart=always
RestartSec=5
EnvironmentFile=/home/stream/streaming/.env

[Install]
WantedBy=default.target
```

`Restart=always` + `RestartSec=5` : si le bot crashe (ex. token invalide, exception non gérée), systemd le relance après 5s.

---

## Dépendances

```
python-telegram-bot>=20.0  # PTB v20, asyncio natif
websockets>=12.0           # déjà présent dans le projet
```

Ajout dans `pyproject.toml` (ou `requirements.txt` selon ce qui est utilisé).

---

## Tests

- `tests/test_telegram_bot.py` — mock PTB Application + mock WebSocket
- Cas testés :
  - Allowlist : commande d'un chat_id non autorisé → ignorée
  - `/status` avec WebSocket up → retourne les champs GlobalState
  - `/status` avec WebSocket down → retourne état systemd seulement
  - Alerte DOWN : debounce 30s respecté, une seule alerte envoyée
  - Alerte UP : envoyée uniquement si DOWN précédent

---

## Ce qui est hors scope

- Notifications de changement de track (→ trop verbeux, user a choisi alertes critiques seulement)
- Permissions multi-utilisateurs
- Webhook Telegram (polling suffit, pas de domaine public requis)
- Commandes audio (skip, territoire) — Phase future si besoin
