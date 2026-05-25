# ADR-0006 — fal.ai Stable Audio 2.5 — endpoints et paramètres canoniques

**Statut :** VALIDÉ  
**Date :** 2026-05-20

## Contexte

L'API fal.ai Stable Audio 2.5 a des noms de paramètres spécifiques, une structure de réponse précise, et des limites documentées par tests empiriques.

## Décision

### Endpoints

| Usage | Endpoint |
|-------|----------|
| Génération text-to-audio | `fal-ai/stable-audio-25/text-to-audio` |
| Dérivation audio-to-audio | `fal-ai/stable-audio-25/audio-to-audio` |

### Paramètres canoniques (text-to-audio)

```python
fal_client.run_async(
    "fal-ai/stable-audio-25/text-to-audio",
    arguments={
        "prompt": prompt,          # str
        "total_seconds": 90,       # int, max 180 — 90s = équilibre coût/continuité
        "num_inference_steps": steps,  # 6 normal / 8 si crisis_level > 0.6 (voir get_inference_steps)
    }
)
```

### Paramètres canoniques (audio-to-audio)

```python
# strength et guidance_scale sont state-driven (NO HARDCODE)
strength = max(0.3, min(0.9,
    0.3 + state.drift_velocity * 0.3 + state.crisis_level * 0.2 + key_dist * 0.2
))
guidance_scale = max(1.0, min(1.2,
    1.0 + state.source_divergence * 0.2
))

fal_client.run_async(
    "fal-ai/stable-audio-25/audio-to-audio",
    arguments={
        "prompt": prompt,
        "audio_url": data_uri,           # data:audio/mpeg;base64,...
        "strength": strength,            # [0.3, 0.9] — piloté par drift_velocity + crisis_level + key_dist
        "guidance_scale": guidance_scale,  # [1.0, 1.2] — piloté par source_divergence
        "num_inference_steps": steps,    # 6 normal / 8 si crisis_level > 0.6
        "total_seconds": total_seconds,  # min(ref_duration, 180) — respecte la structure temporelle de la référence
    }
)
```

### Structure de réponse

```python
audio_url: str = result["audio"]["url"]  # WAV, toujours convertir en MP3
seed: int = result["seed"]               # reproductibilité
```

### Variable d'environnement

`FAL_API_KEY` dans `.env` → mappé automatiquement vers `FAL_KEY` au démarrage de `run_audio_queue()` (le SDK fal_client lit `FAL_KEY`).

### Pipeline WAV → MP3

fal.ai retourne toujours du WAV. La conversion est faite par `_wav_to_mp3()` dans `core/audio_queue.py` via ffmpeg pipe.

## Conséquences

- `STABILITY_API_KEY` est rejeté — utiliser `FAL_API_KEY` uniquement
- `guidance_scale > 1.5` est interdit — artifacts audio documentés
- `num_inference_steps > 8` est interdit pour audio-to-audio — API rejette avec 422
