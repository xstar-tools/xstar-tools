from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


def test_scan_helike_source_level_blocks_dry_run(tmp_path: Path):
    out = tmp_path / "scan"
    completed = subprocess.run([
        sys.executable,
        "examples/39_scan_helike_source_level_blocks.py",
        "dummy_atdb.fits",
        "--element", "C",
        "--ion-stage", "5",
        "--temperature", "1000000",
        "--electron-density", "1e8",
        "--wavelength-min", "40",
        "--wavelength-max", "42",
        "--xstar-lines-csv", "xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv",
        "--level-blocks", "2:4", "5:6",
        "--out-dir", str(out),
        "--dry-run",
        "--print-summary",
    ], cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, text=True)
    assert "dry_run" in completed.stdout
    rows = list(csv.DictReader((out / "helike_source_level_block_scan.csv").open()))
    assert len(rows) == 2
    assert rows[0]["block_tag"] == "levels_2_4"
    assert "--source-levels 2,3,4" in rows[0]["command"]
    summary = list(csv.DictReader((out / "helike_source_level_block_scan_summary.csv").open()))
    assert len(summary) == 2
    assert summary[0]["discovery_status"] == "not_run"
    assert (out / "helike_source_level_block_scan_summary.md").exists()
