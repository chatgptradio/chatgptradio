"""Tests for collectors/gdelt.py."""

import io
import csv
import zipfile
from unittest.mock import patch

import pytest

from collectors.gdelt import (
    COLLECTOR_META,
    _csv_url_from_manifest,
    _parse_csv_bytes,
    collect,
)
from core.state import GlobalState


# ---------------------------------------------------------------------------
# Helper: build a minimal GDELT events CSV zip
# ---------------------------------------------------------------------------

def _make_gdelt_zip(rows: list[list[str]]) -> bytes:
    """Create an in-memory zip containing a tab-separated CSV with *rows*."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t")
    for row in rows:
        writer.writerow(row)
    csv_bytes = buf.getvalue().encode("utf-8")

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.csv", csv_bytes)
    return zbuf.getvalue()


def _make_row(event_code: str = "010", avg_tone: str = "0.0") -> list[str]:
    """Return a tab-row with the correct number of columns for GDELT events."""
    row = [""] * 60
    row[26] = event_code  # EventCode
    row[34] = avg_tone    # AvgTone
    return row


# ---------------------------------------------------------------------------
# _csv_url_from_manifest
# ---------------------------------------------------------------------------


def test_csv_url_from_manifest_finds_export():
    manifest = (
        "12345 abc123 http://data.gdeltproject.org/gdeltv2/lastupdate-mentions.csv.zip\n"
        "67890 def456 http://data.gdeltproject.org/gdeltv2/20260519123000.export.CSV.zip\n"
    )
    url = _csv_url_from_manifest(manifest)
    assert "export" in url


def test_csv_url_from_manifest_raises_when_missing():
    manifest = "12345 abc123 http://data.gdeltproject.org/gdeltv2/mentions.csv.zip\n"
    with pytest.raises(ValueError, match="No export CSV URL"):
        _csv_url_from_manifest(manifest)


# ---------------------------------------------------------------------------
# _parse_csv_bytes
# ---------------------------------------------------------------------------


def test_parse_csv_positive_tone():
    rows = [_make_row("010", "5.0") for _ in range(10)]
    tone, conflict = _parse_csv_bytes(_make_gdelt_zip(rows))
    # avg_tone=5.0, range [-10,10] → 0.75; no conflict (EventCode "010" not starting with "1")
    assert tone == pytest.approx(0.75)
    assert conflict == pytest.approx(0.0)


def test_parse_csv_conflict_rows():
    rows = [_make_row("100", "0.0") for _ in range(5)]  # conflict
    rows += [_make_row("030", "0.0") for _ in range(5)]  # non-conflict
    tone, conflict = _parse_csv_bytes(_make_gdelt_zip(rows))
    assert tone == pytest.approx(0.5)  # 0.0 tone → midpoint
    assert conflict == pytest.approx(0.5)


def test_parse_csv_empty_zip():
    rows: list[list[str]] = []
    tone, conflict = _parse_csv_bytes(_make_gdelt_zip(rows))
    assert tone == pytest.approx(0.5)  # avg_tone = 0.0 → midpoint after norm
    assert conflict == pytest.approx(0.0)


def test_collector_meta():
    assert COLLECTOR_META["name"] == "gdelt"
    assert COLLECTOR_META["interval_s"] == 900


# ---------------------------------------------------------------------------
# collect() integration test
# ---------------------------------------------------------------------------


async def test_collect_returns_both_fields():
    manifest_text = b"100 abc http://data.gdeltproject.org/gdeltv2/20260519.export.CSV.zip\n"
    rows = [_make_row("010", "2.0") for _ in range(10)]
    csv_zip = _make_gdelt_zip(rows)

    call_count = 0

    async def fake_fetch_bytes(url: str, timeout_s: float = 30.0) -> bytes:
        nonlocal call_count
        call_count += 1
        if "lastupdate" in url:
            return manifest_text
        return csv_zip

    with patch("collectors.gdelt._fetch_bytes", side_effect=fake_fetch_bytes):
        result = await collect(GlobalState())

    assert "gdelt_global_tone" in result
    assert "gdelt_conflict_intensity" in result
    assert 0.0 <= result["gdelt_global_tone"] <= 1.0
    assert 0.0 <= result["gdelt_conflict_intensity"] <= 1.0
    assert call_count == 2
