# FPS Optimization & CPU Reduction — Design Spec

**Date** : 2026-05-27  
**Objectif** : 30 FPS constant + réduction CPU (~-30% total)  
**Statut** : Approuvé — en attente d'implémentation

---

## Contexte

Le stream ChatGPT Radio tourne avec :
- Chromium headless + SwiftShader (`--use-gl=swiftshader`) → WebGL 100% CPU
- Xvfb 1280×720 + FFmpeg x11grab → libx264 ultrafast → RTMP
- Three.js overlay, render loop `setTimeout(1000/30)`
- WebSocket GlobalState broadcast à 4 fps

**Mesures CPU observées** :
| Composant | CPU |
|---|---|
| Chromium GPU process (SwiftShader) | ~45% |
| FFmpeg x11grab + encode | ~27% |
| Python / collecteurs | ~10% |

**Cause racine** : SwiftShader force tout le pipeline WebGL en CPU pur. Le GPU Virtio (`0x1af4`) est inutilisé malgré la présence de `virtio_gpu_dri.so` (Mesa 25.2.8) et du snap Chromium avec `mesa-2404:gpu-2404` connecté.

---

## Approche retenue : A + B

- **A** — Switch EGL (levier principal, ~-30% CPU attendu)
- **B** — Tuning renderer JS + FFmpeg (gains incrémentaux)

L'approche C (remplacement x11grab) est reportée.

---

## Changements

### 1. Chromium EGL — `core/browser_display.py`

Remplacer les flags SwiftShader :

```python
# SUPPRIMER
"--disable-gpu",
"--enable-unsafe-swiftshader",
"--use-gl=swiftshader",

# AJOUTER
"--use-gl=egl",
"--enable-gpu-rasterization",
```

`--ignore-gpu-blocklist` et `--disable-dev-shm-usage` restent en place.

**Rollback** : remettre les 3 lignes supprimées. Détection en <10s via log `chromium_died`.  
**Risque** : virglrenderer peut ne pas exposer WebGL2 → Three.js refuse → rollback immédiat.

### 2. Renderer Three.js — `overlays/visualizer.html` + `overlays/visualizer_dev.html`

```js
// powerPreference : low-power → high-performance
const renderer = new THREE.WebGLRenderer({antialias:false, powerPreference:'high-performance'});

// Désactiver la validation GLSL en runtime (après setPixelRatio)
renderer.debug.checkShaderErrors = false;
```

### 3. FFmpeg — `core/dsp.py`

Supprimer le filtre `-vf fps=30` (redondant, x11grab capture déjà à 30fps) :

```python
# SUPPRIMER dans video_encode
"-vf", "fps=30",
```

`force-cfr=1` dans `-x264opts` suffit à garantir le CFR.

### 4. WebSocket fps — `config.yaml`

```yaml
websocket:
  fps: 10   # était 4
```

Justification : 4fps = données toutes les 250ms → lerps Three.js saccadés malgré 30fps render. À 10fps (100ms), les animations suivent mieux les signaux. Coût négligeable (~2KB/s JSON).

---

## Ordre d'implémentation

1. **EGL** (`browser_display.py`) → redémarrer → observer CPU 2 min
2. Si EGL OK : **renderer JS** (visualizer.html + visualizer_dev.html) + **FFmpeg** (dsp.py)
3. **WebSocket 10fps** (`config.yaml`) → redémarrer Python

Chaque étape est indépendante et reversible.

---

## Critères de succès

- Chromium GPU process < 20% CPU (vs ~45% actuel)
- FFmpeg stable à 30fps sans drops dans les logs
- Aucun artefact visuel (overlay noir, scintillement, crash)
- `world_temperature` et émotions mises à jour à 10fps dans l'overlay (lerps plus fluides)

---

## Rollback complet

```python
# browser_display.py — remettre
"--disable-gpu",
"--enable-unsafe-swiftshader",
"--use-gl=swiftshader",
```
Redémarrage : ~30s.
