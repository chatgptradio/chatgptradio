"""
Deduplicate fal_derived clips using MFCC cosine similarity.

Usage:
    uv run python scripts/dedup_clips.py [--dry-run] [--threshold 0.88]

For each pair of clips with cosine similarity above threshold, keep the one
with the highest play_count (most validated). Delete the rest from disk + DB.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import aiosqlite
import numpy as np
import structlog

log = structlog.get_logger()

DB_PATH = Path(__file__).parent.parent / "streams" / "state.db"
SAMPLE_DURATION_S = 15  # analyse the first 15s only — fast enough, representative


async def _load_mfcc(path: Path) -> np.ndarray | None:
    """Return mean MFCC vector (20 coefficients) or None on error."""
    try:
        import librosa  # type: ignore[import]

        y, sr = librosa.load(str(path), sr=22050, mono=True, duration=SAMPLE_DURATION_S)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        return mfcc.mean(axis=1).astype(np.float32)
    except Exception as e:
        log.warning("mfcc_load_error", path=str(path), error=str(e))
        return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if norm == 0:
        return 0.0
    return float(np.dot(a, b) / norm)


async def run(dry_run: bool, threshold: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT path, play_count FROM audio_clips WHERE source = 'fal_derived' ORDER BY play_count DESC"
        ) as cur:
            rows = [{"path": Path(r[0]), "play_count": r[1]} async for r in cur]

    print(f"\nLoading MFCC for {len(rows)} fal_derived clips (first {SAMPLE_DURATION_S}s each)…")
    vectors: list[tuple[dict, np.ndarray]] = []
    for i, row in enumerate(rows):
        if not row["path"].exists():
            print(f"  [MISSING] {row['path'].name}")
            continue
        vec = await _load_mfcc(row["path"])
        if vec is not None:
            vectors.append((row, vec))
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(rows)} done…")

    print(f"\nAnalyzed {len(vectors)} clips. Computing similarity matrix…")

    # Greedy dedup: iterate in play_count DESC order (already sorted).
    # A clip is a "duplicate" if it's similar to any already-kept clip.
    kept: list[dict] = []
    kept_vecs: list[np.ndarray] = []
    to_delete: list[dict] = []

    for row, vec in vectors:
        is_dup = any(_cosine(vec, kv) >= threshold for kv in kept_vecs)
        if is_dup:
            to_delete.append(row)
        else:
            kept.append(row)
            kept_vecs.append(vec)

    print(f"\n── Results (threshold={threshold:.2f}) ──────────────────────────────")
    print(f"  Kept   : {len(kept)} clips")
    print(f"  Deleted: {len(to_delete)} clips")
    if to_delete:
        print("\n  Clips to delete:")
        for r in to_delete:
            print(f"    pc={r['play_count']:3d}  {r['path'].name}")

    if dry_run:
        print("\n[DRY RUN] No files deleted. Re-run without --dry-run to apply.")
        return

    if not to_delete:
        print("\nNothing to delete.")
        return

    print(f"\nDeleting {len(to_delete)} clips from disk + DB…")
    deleted = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for row in to_delete:
            try:
                row["path"].unlink(missing_ok=True)
                await db.execute("DELETE FROM audio_clips WHERE path = ?", (str(row["path"]),))
                deleted += 1
            except Exception as e:
                print(f"  ERROR deleting {row['path'].name}: {e}")
        await db.commit()

    print(f"\nDone. {deleted}/{len(to_delete)} clips removed.")
    print(f"Library now: {len(kept)} fal_derived clips.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate fal_derived clips by MFCC similarity.")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not delete.")
    parser.add_argument("--threshold", type=float, default=0.88, help="Cosine similarity threshold (default 0.88).")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, threshold=args.threshold))


if __name__ == "__main__":
    main()
