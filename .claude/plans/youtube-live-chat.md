# Plan — YouTube Live Chat Collector

Ref PRD: `.claude/prds/youtube-live-chat.md`

## Issues

### Issue #B1 — collectors: youtube_chat.py

**Files**: `collectors/youtube_chat.py` (new), `pyproject.toml`, `config.yaml`

1. `uv add pytchat`
2. `uv add google-api-python-client` (pour `search.list` auto-détection VIDEO_ID)
3. Créer `collectors/youtube_chat.py` :
   ```python
   SOURCE_NAME = "youtube_chat"

   async def collect(state: GlobalState, state_queue: asyncio.Queue) -> dict[str, object]:
       ...
   ```
   - `_resolve_video_id()` :
     - Check `YOUTUBE_VIDEO_ID` env var → return si présent
     - Sinon : appel `googleapiclient.discovery.build("youtube","v3",developerKey=API_KEY).search().list(channelId=CHANNEL_ID, eventType="live", type="video", part="id").execute()`
     - Return `items[0].id.videoId` ou `None`
   - `_run_chat_loop(video_id, state, state_queue)` :
     - `chat = pytchat.create(video_id=video_id)`
     - Loop while `chat.is_alive()`:
       - `async for c in chat.get().async_items():`
       - Si message commence par `!` : appeler `handle_command(cmd, arg, state, engine, state_queue, conn)`
         - Note : `handle_command` nécessite `CommandEngine` et `conn` → les stocker dans le state ou les passer en paramètre depuis `main.py` via une closure
         - Alternative plus simple : juste mettre `{"pending_command": message}` dans state_queue et laisser main.py le traiter
         - **Décision** : injecter `engine` + `conn` via paramètre dans `collect()` (signature étendue)
       - Compter les messages pour `chat_rate`
     - Après la loop : log warning stream non actif
   - `collect()` wrapper : appelle `_resolve_video_id()` au 1er appel, cache le résultat, lance `_run_chat_loop()`
4. Ajouter `youtube_chat` dans `config.yaml` sous `collectors`
5. Gérer le cas où `YOUTUBE_CHANNEL_ID` et `YOUTUBE_VIDEO_ID` sont tous les deux absents → skip silencieux (log warning)

### Issue #B2 — tests: youtube_chat collector

**Files**: `tests/test_youtube_chat.py` (new)

1. `test_resolve_video_id_uses_env_var` — si `YOUTUBE_VIDEO_ID` dans env → retourné sans appel API
2. `test_collect_skipped_without_credentials` — sans `YOUTUBE_CHANNEL_ID` ni `VIDEO_ID` → collecteur désactivé
3. `test_command_parsed_from_chat_message` — message `!switch chaos` → `handle_command` appelé
4. `test_non_command_message_ignored` — message ordinaire → pas de `handle_command`
5. `test_chat_rate_updated` — N messages en fenêtre 5 min → `chat_rate` correct dans state_queue

## Dépendances

#B2 dépend de #B1.
#B1 et les issues du pipeline visuel (#A1, #A2) sont indépendants.

## Quality gate

```bash
uv run python -m pytest -q && uv run pyright && uv run ruff check .
```
