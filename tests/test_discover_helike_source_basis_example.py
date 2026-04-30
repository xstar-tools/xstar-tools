from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def test_discover_helike_source_basis_fake_run(tmp_path: Path):
    run = tmp_path / "c5_solver_source_fit_density_xstar_grid_v031"
    fit = run / "fit_ne_1"
    fit.mkdir(parents=True)
    _write_csv(fit / "o7_solver_response_matrix.csv", [
        {"source_level": 2, "source_label": "positive", "raw_forbidden": 2.0, "raw_intercombination": 1.0, "raw_resonance": 1.0},
        {"source_level": 3, "source_label": "zero", "raw_forbidden": 0.0, "raw_intercombination": 0.0, "raw_resonance": 0.0},
        {"source_level": 4, "source_label": "negative", "raw_forbidden": -1.0, "raw_intercombination": 1.0, "raw_resonance": 0.0},
    ])
    _write_csv(fit / "o7_solver_source_fit_weights.csv", [
        {"source_level": 2, "fit_weight_norm": 0.2},
        {"source_level": 3, "fit_weight_norm": 0.5},
        {"source_level": 4, "fit_weight_norm": 0.3},
    ])
    (fit / "o7_solver_source_fit_summary.json").write_text(json.dumps({
        "element": "C", "ion_stage": 5, "electron_density_cm^-3": 1.0,
        "target_components_normalized": {"forbidden": 0.5, "intercombination": 0.25, "resonance": 0.25},
    }))
    out = tmp_path / "discover"
    subprocess.run([
        sys.executable, "examples/38_discover_helike_source_basis.py", str(run), "--out-dir", str(out), "--print-summary"
    ], cwd=Path(__file__).resolve().parents[1], check=True)
    density_rows = list(csv.DictReader((out / "helike_discovered_source_basis_density_summary.csv").open()))
    assert len(density_rows) == 1
    assert density_rows[0]["discovered_source_levels"] == "2"
    assert int(float(density_rows[0]["n_positive_nonzero_source_levels"])) == 1
    run_rows = list(csv.DictReader((out / "helike_discovered_source_basis_run_summary.csv").open()))
    assert run_rows[0]["status"] == "basis_found"
    level_rows = list(csv.DictReader((out / "helike_discovered_source_basis_levels.csv").open()))
    classes = {r["source_level"]: r["response_class"] for r in level_rows}
    assert classes["2"] == "positive_nonzero"
    assert classes["3"] == "zero"
    assert "negative" in classes["4"]


def test_discover_helike_source_basis_empty_run_reports_warning(tmp_path: Path):
    run = tmp_path / "empty_run"
    run.mkdir()
    out = tmp_path / "out"
    completed = subprocess.run([
        sys.executable, "examples/38_discover_helike_source_basis.py", str(run), "--out-dir", str(out), "--print-summary"
    ], cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, text=True)
    assert "no fit_ne_* directories found" in completed.stdout
    assert (out / "helike_discovered_source_basis_summary.md").exists()
