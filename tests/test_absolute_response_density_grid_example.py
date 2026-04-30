from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_absolute_response_density_grid_dry_run(tmp_path: Path):
    out = tmp_path / "abs_density_grid"
    completed = subprocess.run([
        sys.executable,
        "examples/41_fit_absolute_response_density_grid.py",
        "dummy_atdb.fits",
        "--element", "C",
        "--ion-stage", "5",
        "--temperature", "1000000",
        "--electron-densities", "1e4,1e8",
        "--wavelength-min", "40",
        "--wavelength-max", "42",
        "--source-levels", "2,56",
        "--xstar-lines-csv-template", str(tmp_path / "c5_ne{ne_tag}" / "xstar_c5_triplet_lines.csv"),
        "--out-dir", str(out),
        "--dry-run",
        "--print-summary",
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    assert "Absolute-response He-like triplet density-grid fit" in completed.stdout
    rows = list(csv.DictReader((out / "helike_absolute_response_density_grid_summary.csv").open()))
    assert [row["density_tag"] for row in rows] == ["1e4", "1e8"]
    assert all(row["fit_status"] == "dry_run" for row in rows)
    commands = list(csv.DictReader((out / "helike_absolute_response_density_grid_commands.csv").open()))
    assert len(commands) == 2
    assert "--fit-mode absolute-response" in commands[0]["command"]
    assert "dummy_atdb.fits" in commands[0]["command"]
    summary = json.loads((out / "helike_absolute_response_density_grid_summary.json").read_text())
    assert summary["n_density_points"] == 2
    assert (out / "helike_absolute_response_density_grid_summary.md").exists()
