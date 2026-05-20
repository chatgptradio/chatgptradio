"""
Index reference tracks into the audio library.

Scans streams/references/ for audio files, analyses them with librosa
(BPM, key, energy, spectral features), maps to GlobalState fields,
and inserts into audio_clips with source='reference'.

No renaming — original artist/title filenames are kept.
The DB is the source of truth for what a clip sounds like.

Usage:
    # Move your reference tracks to streams/references/ first, then:
    uv run python scripts/index_references.py [--force]

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

def _detect_key(y: np.ndarray, sr: int) -> str:
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
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

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    key = _detect_key(y, sr)
    territory = _detect_territory(path.name, bpm)

    rms = float(np.sqrt(np.mean(y ** 2)))
    # Normalise RMS → excitation [0, 1] (typical RMS range for music: 0.02 – 0.25)
    excitation = float(np.clip(rms / 0.15, 0.0, 1.0))

    spectral_centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    # Normalise centroid → harmonic_complexity [0, 1] (typical range: 500 – 4000 Hz)
    harmonic_complexity = float(np.clip((spectral_centroid - 500) / 3500, 0.0, 1.0))

    spectral_rolloff = float(librosa.feature.spectral_rolloff(y=y, sr=sr).mean())
    # Normalise rolloff → musical_tension [0, 1]
    musical_tension = float(np.clip((spectral_rolloff - 1000) / 7000, 0.0, 1.0))

    zcr = float(librosa.feature.zero_crossing_rate(y).mean())
    # High ZCR → anxious/tense texture
    anxiete = float(np.clip(zcr / 0.15, 0.0, 1.0))

    print(f"BPM={bpm:.0f} key={key} territory={territory}")
    return {
        "drift_bpm": bpm,
        "drift_key": key,
        "drift_territory": territory,
        "drift_timbre": "warm",   # default — librosa doesn't distinguish timbre well
        "excitation": excitation,
        "harmonic_complexity": harmonic_complexity,
        "musical_tension": musical_tension,
        "anxiete": anxiete,
        "world_temperature": 0.5,
        "crisis_level": 0.0,
    }


def _make_state(fields: dict) -> GlobalState:
    state = GlobalState()
    for k, v in fields.items():
        setattr(state, k, v)
    return state


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
            state  = _make_state(fields)
            prompt = f"reference track: {path.stem}"
            await index_clip(conn, path, state, prompt, source="reference", display_name=display_name)
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
