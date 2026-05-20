# PRD — YouTube Live Chat Collector

## Problem

Les commandes `!switch`, `!mode`, etc. ne peuvent pas être reçues du stream YouTube :
il n'y a pas de collecteur Live Chat. Le moteur de commandes (`core/chat_commands.py`) existe
mais rien ne l'alimente.

## Hypothesis

Un collecteur `collectors/youtube_chat.py` basé sur `pytchat` (bibliothèque Python qui lit
le chat en temps réel sans quota Data API) lira les messages du stream en cours, parsera les
commandes `!`, appellera `handle_command()` et mettra les résultats dans `state_queue`.
L'auto-détection du VIDEO_ID se fait via un appel `search.list` unique au démarrage
(100 unités quota, une fois par session).

## Approche technique

- `pytchat` : lib Python utilisant l'endpoint interne YouTube (pas l'API officielle).
  Pas de quota consommé pour la lecture du chat. Polling toutes les ~1-3 secondes.
- `YOUTUBE_CHANNEL_ID` dans `.env` pour l'auto-détection du VIDEO_ID
- Fallback : `YOUTUBE_VIDEO_ID` dans `.env` si fourni directement (évite le `search.list`)
- `handle_command()` depuis `core/chat_commands.py` pour traiter les commandes
- Mise à jour de `chat_rate` dans `state_queue` (messages/minute, fenêtre 5 min)

## Scope

### Dans le périmètre
- `collectors/youtube_chat.py` implémentant le protocole collecteur (`source_name`, `collect()`)
  - Auto-détection VIDEO_ID : `YOUTUBE_VIDEO_ID` en priorité, sinon `search.list` avec `YOUTUBE_CHANNEL_ID`
  - Lecture chat via `pytchat.create(video_id=video_id)`
  - Parser les messages pour `!command [arg]` → `handle_command()`
  - Calculer `chat_rate` (msgs/min, fenêtre glissante 5 min) → `state_queue`
  - Log `chat_message_received` pour chaque commande parsée
  - Graceful shutdown si le stream n'est pas en cours (pytchat non actif)
- `YOUTUBE_CHANNEL_ID` ajouté aux env vars documentées
- `YOUTUBE_VIDEO_ID` ajouté comme override optionnel
- Ajout de `pytchat` dans `pyproject.toml`
- Tests unitaires : parsing commande, chat_rate calculation, VIDEO_ID resolution
- Ajout dans `config.yaml` (collecteurs activés)

### Hors périmètre
- Réponses chat (TTS ou text reply) — REJETÉ dans DIRECTION.md V1
- `chat_sentiment` — reporté (VADER) 
- Tracking des viewers réguliers
- Modération automatique

## Acceptance criteria

1. `youtube_chat.py` est découvert automatiquement par `collector_runner` si `YOUTUBE_CHANNEL_ID` ou `YOUTUBE_VIDEO_ID` est dans `.env`
2. Un message `!switch` dans le chat YouTube déclenche bien le changement de mode visuel
3. Un message `!switch chaos` change le mode vers `chaos`
4. `chat_rate` est mis à jour dans `state_queue` après chaque batch de messages
5. Si le stream n'est pas actif (pas de live), le collecteur log un warning et attend sans crasher
6. `pytchat>=0.7.1` dans `pyproject.toml`
7. `uv run pytest && uv run pyright && uv run ruff check .` : 0 erreur
