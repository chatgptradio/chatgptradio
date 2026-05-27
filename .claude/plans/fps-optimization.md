# Plan d'implémentation — FPS Optimization & CPU Reduction

**Spec** : `docs/specs/2026-05-27-fps-optimization-design.md`
**Date** : 2026-05-27

---

## Étape 1 — Chromium EGL (`core/browser_display.py`)

**Risque** : moyen — rollback 30s si Chromium ne démarre pas

### Tâche 1.1 — Remplacer SwiftShader par EGL

Dans `_start_chromium()`, remplacer :
```python
"--disable-gpu",
"--enable-unsafe-swiftshader",
"--use-gl=swiftshader",
```
par :
```python
"--use-gl=egl",
"--enable-gpu-rasterization",
```

### Tâche 1.2 — Mettre à jour le commentaire inline

```python
"nice", "-n", "5",  # slight yield to FFmpeg; EGL path — GPU-accelerated via virgl
```

### Validation étape 1

- Redémarrer : `uv run python main.py`
- Logs : pas de `chromium_died` dans les 10s
- CPU : `ps aux --sort=-%cpu | head -12` → Chromium GPU < 20%
- Overlay : `http://localhost:8080/visualizer_dev.html` — rendu correct
- **Si KO** : remettre les 3 lignes supprimées → redémarrer

---

## Étape 2 — Renderer Three.js

**Risque** : faible — changement JS pur, reload overlay suffit

### Tâche 2.1 — `overlays/visualizer.html`

1. `powerPreference:'low-power'` → `powerPreference:'high-performance'`
2. Ajouter après `renderer.setPixelRatio(1.0)` :
   ```js
   renderer.debug.checkShaderErrors = false;
   ```

### Tâche 2.2 — `overlays/visualizer_dev.html`

Mêmes deux changements que 2.1.

### Validation étape 2

- Recharger l'overlay dans le navigateur
- Tous les modes : pas d'écran noir, pas d'artefact
- CPU renderer process stable ou en baisse

---

## Étape 3 — FFmpeg cleanup (`core/dsp.py`)

**Risque** : faible

### Tâche 3.1

Dans `video_encode`, supprimer :
```python
"-vf", "fps=30",
```
Vérifier que `-x264opts` contient `force-cfr=1` (déjà présent — ne pas toucher).

### Validation étape 3

- Redémarrer le stream
- `/tmp/ffmpeg_live.log` : pas de `fps mismatch`, pas de `DTS/PTS` warning
- Vidéo RTMP confirmée à 30fps

---

## Étape 4 — WebSocket 10fps (`config.yaml`)

**Risque** : très faible

### Tâche 4.1

```yaml
websocket:
  fps: 10   # was 4
```

### Validation étape 4

- Redémarrer `uv run python main.py`
- Console navigateur : signaux mis à jour ~10×/s
- CPU Python : pas d'augmentation significative

---

## Quality gate (avant commit final)

```bash
cd /home/stream/streaming && uv run pytest && uv run pyright && uv run ruff check .
```

---

## Résumé des fichiers modifiés

| Fichier | Étape | Changement |
|---|---|---|
| `core/browser_display.py` | 1 | SwiftShader → EGL |
| `overlays/visualizer.html` | 2 | powerPreference + checkShaderErrors |
| `overlays/visualizer_dev.html` | 2 | powerPreference + checkShaderErrors |
| `core/dsp.py` | 3 | suppression `-vf fps=30` |
| `config.yaml` | 4 | websocket fps 4 → 10 |

## Rollback complet

```python
# browser_display.py — remettre exactement
"--disable-gpu",
"--enable-unsafe-swiftshader",
"--use-gl=swiftshader",
# supprimer "--use-gl=egl", "--enable-gpu-rasterization",
```
Redémarrage ~30s. Les étapes 2-4 sont sans risque et n'ont pas besoin de rollback.
