# PRD — Auto-gain LUFS normalization

## Problem

Les clips audio générés par Stable Audio ont des niveaux sonores très variables (±10 dB entre clips). Le résultat pour l'auditeur : des sauts de volume perceptibles à chaque transition, nuisant à l'expérience stream 24/7.

## Hypothesis

Mesurer le niveau LUFS intégré de chaque clip au moment de la lecture dans le DSP, puis appliquer un gain de correction vers -14 LUFS (standard YouTube/Spotify EBU R128), éliminera les écarts de volume entre clips sans modifier les fichiers source.

## Scope

### Dans le périmètre
- Mesure LUFS intégrés avec `pyloudnorm` (EBU R128 Mode 3)
- Application d'un gain de correction avant la chaîne Pedalboard dans `run_dsp`
- Cible : -14.0 LUFS (standard streaming)
- Cap : ±18 dB (évite d'amplifier le silence ou de saturer)
- Fallback silencieux si mesure impossible (clip quasi-silencieux)
- Ajout de `pyloudnorm` dans `pyproject.toml`
- Tests unitaires : mesure LUFS, calcul gain, cap, fallback silencieux

### Hors périmètre
- Normalisation à la génération (modification des MP3 sources)
- Persistance du gain mesuré en DB
- Two-pass loudnorm ffmpeg (trop lourd pour clip déjà en mémoire)
- Modification de la cible LUFS via GlobalState (future évolution si besoin)

## Acceptance criteria

1. Le gain de correction est calculé et appliqué clip par clip dans `run_dsp`, entre `_read_and_stretch` et `_process_audio`
2. Si le clip mesure -20 LUFS, le gain appliqué est +6 dB
3. Si le clip mesure -4 LUFS, le gain appliqué est -10 dB (capped à -18 max)
4. Si la mesure LUFS échoue (silence, clip trop court), le clip passe sans modification
5. `pyloudnorm>=0.4.2` est dans `pyproject.toml`
6. Tests : ≥ 4 cas (normal, loud, quiet, silence)
7. `uv run pytest && uv run pyright && uv run ruff check .` : 0 erreur
