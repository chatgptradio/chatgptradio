# Plan — Headless Visual Pipeline

Ref PRD: `.claude/prds/headless-visual-pipeline.md`

## Issues

### Issue #A1 — core: HTTP server + browser_display coroutine

**Files**: `core/browser_display.py` (new), `main.py`, `pyproject.toml`

1. `uv add aiohttp` (si pas déjà présent)
2. Créer `core/browser_display.py` :
   - `async def run_browser_display(overlay_url: str, ready_event: asyncio.Event, display: str = ":99") -> None`
   - Lance `Xvfb {display} -screen 0 1280x720x24`
   - Attend 1 seconde
   - Lance `chromium-browser --no-sandbox --disable-gpu --window-size=1280,720 --display={display} --app={overlay_url}`
   - Attend 3 secondes → `ready_event.set()`
   - Loop infinie : check si l'un des process est mort → restart
3. Dans `main.py` :
   - Ajouter import `aiohttp.web`
   - Créer `_make_overlay_server(port)` → `aiohttp.web.Application` avec route statique vers `overlays/`
   - Dans `run()` : créer `browser_ready = asyncio.Event()`, démarrer l'HTTP server + `run_browser_display`, attendre `browser_ready`
4. Lire `OVERLAY_HTTP_PORT` (défaut 8080) et `OVERLAY_DISPLAY` (défaut `:99`) depuis env

### Issue #A2 — dsp: use x11grab instead of lavfi color

**Files**: `core/dsp.py`

1. `run_dsp` accepte un nouveau paramètre optionnel `ready_event: asyncio.Event | None = None`
2. Si `ready_event` fourni : `await ready_event.wait()` avant de construire `ffmpeg_cmd`
3. Remplacer dans `ffmpeg_cmd` :
   ```
   "-f", "lavfi", "-i", "color=c=0x0a0a1a:s=1280x720:r=30",
   ```
   par :
   ```
   "-f", "x11grab", "-framerate", "30", "-video_size", "1280x720", "-i", display + ".0",
   ```
   où `display` vient de `os.environ.get("OVERLAY_DISPLAY", ":99")`
4. Si `OVERLAY_DISPLAY` n'est pas set ou xvfb pas disponible → fallback sur `lavfi color` (log warning)
5. Wirer le `ready_event` dans `main.py` : passer depuis `run()` à `run_dsp`

## Dépendances entre issues

#A1 peut être implémenté en parallèle avec les autres features.
#A2 dépend de #A1 (utilise le `ready_event` défini dans #A1).

## Quality gate

```bash
uv run python -m pytest -q && uv run pyright && uv run ruff check .
```

## Note prérequis système (non automatisé)

```bash
sudo apt-get install -y xvfb chromium-browser
```
