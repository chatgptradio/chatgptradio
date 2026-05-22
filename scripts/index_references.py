"""
Index reference tracks into the audio library.

Scans streams/references/ for audio files, analyses them with librosa
(BPM, key, energy, spectral features), maps to GlobalState fields,
and inserts into audio_clips with source='reference'.

No renaming — original artist/title filenames are kept.
The DB is the source of truth for what a clip sounds like.

Usage:
    uv run --group scripts python scripts/index_references.py [--force]

    --force : re-index already-indexed files (updates metadata)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Load .env before any project imports
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import numpy as np  # noqa: E402
import scipy.stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))
import librosa  # noqa: E402

from core.db import init_db  # noqa: E402
from core.audio_library import index_clip  # noqa: E402
from core.state import GlobalState  # noqa: E402

_REFERENCES_DIR = Path("streams/references")
_DB_PATH        = "streams/state.db"
_SUPPORTED_EXT  = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}

# Keyword → territory mapping (applied to lowercased filename)
_KEYWORD_TERRITORY: list[tuple[str, str]] = [
    ("ambient",     "ambient"),
    ("drone",       "drone"),
    ("drone",       "drone"),
    ("drifts",      "ambient"),   # Phendrana Drifts
    ("bog",         "ambient"),   # Torvus Bog
    ("jazz",        "jazz"),
    ("soul",        "jazz"),
    ("spiritual",   "jazz"),
    ("techno",      "electronic"),
    ("electronic",  "electronic"),
    ("lofi",        "experimental"),
    ("lo-fi",       "experimental"),
    ("hip hop",     "experimental"),
    ("hiphop",      "experimental"),
    ("industrial",  "industrial"),
    ("neoclassical","neoclassical"),
    ("classical",   "neoclassical"),
    ("orchestral",  "neoclassical"),
    ("strings",     "neoclassical"),
    ("piano",       "neoclassical"),
    ("glitch",      "experimental"),
    ("experimental","experimental"),
]

# BPM → default territory when filename gives no hint
def _bpm_territory(bpm: float) -> str:
    if bpm < 65:
        return "drone"
    if bpm < 85:
        return "ambient"
    if bpm < 105:
        return "jazz"
    if bpm < 115:
        return "experimental"
    if bpm < 135:
        return "electronic"
    return "industrial"


def _detect_territory(filename: str, bpm: float) -> str:
    lower = filename.lower()
    for keyword, territory in _KEYWORD_TERRITORY:
        if keyword in lower:
            return territory
    return _bpm_territory(bpm)


_CHROMATIC_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_TIMBRE_SEQUENCE = ["warm", "organic", "digital", "cold", "metallic"]

def _detect_key(y: np.ndarray, sr: int) -> str:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mean_chroma = chroma.mean(axis=1)
    root = int(np.argmax(mean_chroma))
    # Rough major/minor heuristic: compare 3rd vs minor 3rd energy
    major_3rd = mean_chroma[(root + 4) % 12]
    minor_3rd = mean_chroma[(root + 3) % 12]
    mode = "major" if major_3rd > minor_3rd else "minor"
    return f"{_CHROMATIC_NOTES[root]} {mode}"


def _analyse(path: Path) -> dict:
    """Analyse audio file with librosa. Returns dict of GlobalState-compatible fields."""
    print(f"  Analysing {path.name}…", end=" ", flush=True)
    y, sr = librosa.load(str(path), sr=22050, mono=True, duration=120.0)

    # 2f. Real duration (must be before musical_tension which uses it)
    duration_s = float(librosa.get_duration(y=y, sr=sr))

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    key = _detect_key(y, sr)
    territory = _detect_territory(path.name, bpm)

    rms = float(np.sqrt(np.mean(y ** 2)))
    # Normalise RMS → excitement [0, 1] (typical RMS range for music: 0.02 – 0.25)
    excitement = float(np.clip(rms / 0.15, 0.0, 1.0))

    # 2a. chroma_cqt already used in _detect_key; compute here for harmonic_complexity
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)

    # 2b. harmonic_complexity via chroma entropy (normalised to [0, 1])
    entropy = scipy.stats.entropy(chroma.mean(axis=1) + 1e-10)
    harmonic_complexity = float(entropy / np.log(12))

    # 2c. musical_tension via onset density (onset density 0–10 onsets/s → [0, 1])
    onsets = librosa.onset.onset_detect(y=y, sr=sr)
    musical_tension = min(float(len(onsets) / max(duration_s, 1.0)) / 10.0, 1.0)

    # 2d. drift_timbre via MFCC[1] centroid
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_centroid = float(mfcc[1].mean())
    if mfcc_centroid < -20:
        drift_timbre = "warm"
    elif mfcc_centroid < -5:
        drift_timbre = "organic"
    elif mfcc_centroid < 10:
        drift_timbre = "digital"
    elif mfcc_centroid < 25:
        drift_timbre = "cold"
    else:
        drift_timbre = "metallic"

    # 2e. Trim silence boundaries
    _, trim_indices = librosa.effects.trim(y, top_db=30)
    trim_start_s = float(trim_indices[0] / sr)
    trim_end_s = float(trim_indices[1] / sr)

    # 2g. MFCC fingerprint — 20 coefficients
    mfcc_full = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    mfcc_fingerprint = mfcc_full.mean(axis=1).tolist()

    # BUG15. anxiety via IOI (inter-onset interval) entropy
    onset_times = librosa.frames_to_time(
        librosa.onset.onset_detect(y=y, sr=sr), sr=sr
    )
    if len(onset_times) > 2:
        ioi = np.diff(onset_times)
        anxiety = float(min(scipy.stats.entropy(np.histogram(ioi, bins=10)[0] + 1e-10) / np.log(10), 1.0))
    else:
        anxiety = 0.0

    print(f"BPM={bpm:.0f} key={key} territory={territory}")
    return {
        "drift_bpm": bpm,
        "drift_key": key,
        "drift_territory": territory,
        "drift_timbre": drift_timbre,
        "excitement": excitement,
        "harmonic_complexity": harmonic_complexity,
        "musical_tension": musical_tension,
        "anxiety": anxiety,
        "world_temperature": 0.5,
        "crisis_level": 0.0,
        # Extra fields stored in mood_snapshot (not GlobalState fields)
        "_trim_start_s": trim_start_s,
        "_trim_end_s": trim_end_s,
        "_mfcc_fingerprint": mfcc_fingerprint,
        "_duration_s": duration_s,
    }


def _make_state(fields: dict) -> tuple[GlobalState, dict[str, object]]:
    """Return (state, extra_mood) — state contains GlobalState fields, extra_mood contains
    supplemental analysis values (prefixed with '_') to be merged into mood_snapshot."""
    state = GlobalState()
    extra_mood: dict[str, object] = {}
    for k, v in fields.items():
        if k.startswith("_"):
            # Strip leading underscore for storage key
            extra_mood[k[1:]] = v
        else:
            setattr(state, k, v)
    return state, extra_mood


async def index_references(force: bool = False) -> None:
    if not _REFERENCES_DIR.exists():
        print(f"Directory not found: {_REFERENCES_DIR}")
        print("Create it and move your reference tracks there:")
        print(f"  mkdir -p {_REFERENCES_DIR}")
        print(f"  mv 'streams/audio/Artist - Title.mp3' {_REFERENCES_DIR}/")
        return

    conn = await init_db(_DB_PATH)

    # Check which files are already indexed
    async with conn.execute(
        "SELECT path FROM audio_clips WHERE source = 'reference'"
    ) as cur:
        indexed = {row[0] async for row in cur}

    files = sorted(
        p for p in _REFERENCES_DIR.iterdir()
        if p.suffix.lower() in _SUPPORTED_EXT
    )

    if not files:
        print(f"No audio files found in {_REFERENCES_DIR}")
        await conn.close()
        return

    print(f"Found {len(files)} file(s) in {_REFERENCES_DIR}")
    new_count = skipped = 0

    for path in files:
        display_name = path.stem  # e.g. "Biosphere - Sphere Of No-Form"

        if str(path) in indexed and not force:
            print(f"  Skipped (already indexed): {path.name}")
            skipped += 1
            # Backfill display_name if missing (idempotent)
            await conn.execute(
                "UPDATE audio_clips SET display_name = ? WHERE path = ? AND display_name = ''",
                (display_name, str(path)),
            )
            await conn.commit()
            continue

        try:
            fields = await asyncio.to_thread(_analyse, path)
            state, extra_mood = _make_state(fields)
            prompt = f"reference track: {path.stem}"
            await index_clip(
                conn, path, state, prompt,
                source="reference", display_name=display_name, extra_mood=extra_mood,
            )
            print(f"  Indexed: {path.name}")
            new_count += 1
        except Exception as e:
            print(f"  ERROR: {path.name} — {e}")

    await conn.close()
    print(f"\nDone. {new_count} indexed, {skipped} skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index reference tracks into audio library")
    parser.add_argument("--force", action="store_true", help="Re-index already-indexed files")
    args = parser.parse_args()
    asyncio.run(index_references(force=args.force))
