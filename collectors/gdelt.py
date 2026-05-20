"""GDELT collector — global tone and conflict intensity.

Fetches the GDELT v2 last-update manifest to locate the latest export CSV,
reads the first 500 rows, extracts AvgTone (column index 34) and EventCode
(column index 26), then:
  - gdelt_global_tone: average AvgTone, normalised from [-10, +10] → [0, 1]
  - gdelt_conflict_intensity: fraction of rows where EventCode starts with "1"
    (verbal conflict) normalised to [0, 1].
"""

import io
import csv
import zipfile
from typing import Any

import aiohttp

from collectors.utils import normalize
from core.node import node
from core.state import GlobalState

COLLECTOR_META = {"name": "gdelt", "interval_s": 900}

_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
_MAX_ROWS = 500
_TONE_LOW = -10.0
_TONE_HIGH = 10.0

# GDELT GKG export column indices (0-based, tab-separated)
# We use the events export: EventCode is col 26, AvgTone is col 34.
_COL_EVENTCODE = 26
_COL_AVGTONE = 34
_TIMEOUT_S = 30.0


async def _fetch_bytes(url: str, timeout_s: float = _TIMEOUT_S) -> bytes:
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.read()


def _csv_url_from_manifest(manifest: str) -> str:
    """Return the export CSV (zip) URL from the lastupdate.txt manifest."""
    for line in manifest.splitlines():
        parts = line.strip().split()
        # Each line: <size> <md5> <url>
        if len(parts) >= 3 and "export" in parts[2]:
            return parts[2]
    raise ValueError("No export CSV URL found in GDELT lastupdate.txt")


def _parse_csv_bytes(raw_bytes: bytes) -> tuple[float, float]:
    """Parse the zipped GDELT events CSV; return (avg_tone_norm, conflict_frac)."""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t")
            tones: list[float] = []
            conflict_count = 0
            total_count = 0
            for i, row in enumerate(reader):
                if i >= _MAX_ROWS:
                    break
                total_count += 1
                # AvgTone
                if len(row) > _COL_AVGTONE:
                    try:
                        tones.append(float(row[_COL_AVGTONE]))
                    except (ValueError, IndexError):
                        pass
                # EventCode — verbal conflict codes start with "1"
                if len(row) > _COL_EVENTCODE:
                    ec = row[_COL_EVENTCODE].strip()
                    if ec.startswith("1"):
                        conflict_count += 1

    avg_tone = sum(tones) / len(tones) if tones else 0.0
    conflict_frac = conflict_count / total_count if total_count else 0.0
    return (
        normalize(avg_tone, _TONE_LOW, _TONE_HIGH),
        float(conflict_frac),
    )


@node(
    name="gdelt",
    produces="gdelt_global_tone",
    color="#C0392B",
    label="GDELT Global Tone",
)
async def collect(state: GlobalState) -> dict[str, Any]:
    manifest = (await _fetch_bytes(_LASTUPDATE_URL)).decode("utf-8", errors="replace")
    csv_url = _csv_url_from_manifest(manifest)
    raw_bytes = await _fetch_bytes(csv_url)
    tone, conflict = _parse_csv_bytes(raw_bytes)
    return {
        "gdelt_global_tone": tone,
        "gdelt_conflict_intensity": conflict,
    }
