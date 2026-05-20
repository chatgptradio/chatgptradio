# Plan — Auto-gain LUFS normalization

Ref PRD: `.claude/prds/auto-gain-lufs.md`

## Micro-tasks

### Issue #A — core: add LUFS normalization to DSP engine

**Files**: `core/dsp.py`, `pyproject.toml`, `uv.lock`

1. `uv add pyloudnorm` → ajoute dep dans `pyproject.toml`
2. Ajouter `import pyloudnorm as pyln` dans `core/dsp.py`
3. Ajouter `_TARGET_LUFS = -14.0` et `_MAX_GAIN_DB = 18.0` comme constantes module
4. Ajouter fonction `_normalize_lufs(audio: np.ndarray, sr: int) -> np.ndarray` :
   - Mesure LUFS intégrés via `pyln.Meter(sr).integrated_loudness(audio)`
   - Si `lufs == float('-inf')` ou `lufs < -70` : retourne `audio` inchangé (silence)
   - Calcule `gain_db = clamp(TARGET_LUFS - lufs, -MAX_GAIN_DB, MAX_GAIN_DB)`
   - Applique `audio * 10 ** (gain_db / 20.0)`
   - Note : `pyloudnorm` attend shape `(samples, channels)` — transpose si nécessaire
5. Dans `run_dsp`, appeler `_normalize_lufs(audio, _SR)` après `_read_and_stretch`, avant `_build_chain`
6. Logger `lufs_correction` avec les valeurs mesurées/corrigées (niveau DEBUG)

### Issue #B — tests: LUFS normalization unit tests

**Files**: `tests/test_dsp.py`

1. `test_normalize_lufs_boosts_quiet_clip` — clip synthétique -20 LUFS → gain positif appliqué
2. `test_normalize_lufs_attenuates_loud_clip` — clip synthétique loud → gain négatif
3. `test_normalize_lufs_caps_gain` — clip quasi-silencieux (-40 LUFS) → gain capé à +18 dB max
4. `test_normalize_lufs_silence_passthrough` — clip silence pur → retourné inchangé
5. `test_normalize_lufs_output_shape` — shape entrée == shape sortie

## Dépendances entre issues

Issue #B dépend de #A (les fonctions à tester doivent exister).
→ Implémenter #A en premier, puis #B dans le même PR ou en séquence.

## Quality gate

```bash
uv run pytest && uv run pyright && uv run ruff check .
```
