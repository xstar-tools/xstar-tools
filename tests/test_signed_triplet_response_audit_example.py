from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_signed_triplet_response_audit_dry_run(tmp_path: Path):
    out = tmp_path / "signed_audit"
    completed = subprocess.run([
        sys.executable,
        "examples/40_audit_signed_triplet_response.py",
        "dummy_atdb.fits",
        "--element", "C",
        "--ion-stage", "5",
        "--temperature", "1000000",
        "--electron-density", "1e8",
        "--wavelength-min", "40",
        "--wavelength-max", "42",
        "--source-levels", "2,56",
        "--out-dir", str(out),
        "--dry-run",
        "--print-summary",
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    assert "Signed/absolute He-like triplet response audit" in completed.stdout
    rows = list(csv.DictReader((out / "helike_signed_triplet_response_audit.csv").open()))
    assert [row["source_level"] for row in rows] == ["2", "56"]
    assert all(row["run_status"] == "dry_run" for row in rows)
    commands = list(csv.DictReader((out / "helike_signed_triplet_response_commands.csv").open()))
    assert commands[0]["kind"] == "baseline"
    assert commands[1]["kind"] == "source"
    assert "--source-level 2" in commands[1]["command"]
    summary = json.loads((out / "helike_signed_triplet_response_summary.json").read_text())
    assert summary["dry_run"] is True
    assert summary["source_levels"] == [2, 56]
    assert (out / "helike_signed_triplet_response_audit.md").exists()
