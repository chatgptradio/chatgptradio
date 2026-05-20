# PRD — Headless Visual Pipeline (Xvfb + Chromium + x11grab)

## Problem

Le stream YouTube affiche un écran noir statique. Le visualiseur `overlays/visualizer.html`
est prévu pour OBS Browser Source, mais le VPS est headless (pas de display physique, pas d'OBS).
Il faut rendre le visualiseur dans un virtual display et le capturer via FFmpeg x11grab.

## Hypothesis

En lançant Xvfb (virtual framebuffer) + Chromium headless sur `:99`, en servant
`overlays/visualizer.html` via HTTP local, et en branchant FFmpeg sur `-f x11grab :99.0`
au lieu de la couleur statique, le stream YouTube affichera le visualiseur réactif en temps réel.

## Scope

### Dans le périmètre
- Serveur HTTP statique aiohttp dans `main.py` pour servir `overlays/` sur `localhost:8080`
- `core/browser_display.py` : coroutine qui gère les sous-processus Xvfb + Chromium
  - Display `:99`, résolution `1280x720x24`
  - Chromium `--app=http://localhost:8080/visualizer.html --no-sandbox --disable-gpu --display=:99`
  - Séquence : Xvfb → sleep(1) → Chromium → sleep(3) → signal ready
  - Restart automatique si l'un des deux crash
- DSP : remplacer `-f lavfi -i color=...` par `-f x11grab -framerate 30 -video_size 1280x720 -i :99.0`
- `OVERLAY_HTTP_PORT` (env var, défaut `8080`) pour le port HTTP
- `OVERLAY_DISPLAY` (env var, défaut `:99`) pour le display Xvfb
- Wiring dans `main.py` : browser_display démarre AVANT run_dsp, transmet signal ready via asyncio.Event
- Prérequis système (à installer une fois manuellement) : `xvfb`, `chromium-browser`

### Hors périmètre
- Authentification sur le serveur HTTP overlay
- Support multi-overlay (HUD séparé)
- OBS integration
- Changement de l'overlay en runtime

## Acceptance criteria

1. `run_browser_display(overlay_url, ready_event)` lance Xvfb + Chromium, set `ready_event` après 3s
2. `run_dsp` attend `ready_event` avant de démarrer FFmpeg avec x11grab
3. FFmpeg capture bien `:99.0` à 1280×720 30fps
4. Si Chromium crash, il est redémarré automatiquement
5. HTTP server sert `overlays/visualizer.html` sur `localhost:8080`
6. `uv run pytest && uv run pyright && uv run ruff check .` : 0 erreur
7. Prérequis documentés dans un commentaire de l'issue (pas de code d'installation automatique)
