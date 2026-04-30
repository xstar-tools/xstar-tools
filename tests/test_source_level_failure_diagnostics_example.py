from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def test_source_level_failure_diagnostics_fake_run(tmp_path: Path):
    run = tmp_path / "c5_solver_source_fit_density_xstar_grid"
    fit = run / "fit_ne_1"
    cdir = fit / "combined_source_validation"
    cdir.mkdir(parents=True)
    summary = {
        "element": "C", "ion_stage": 5, "temperature_K": 1.0e6, "electron_density_cm^-3": 1.0,
        "combined_source_validation": {
            "R_f_over_i": None, "G_f_plus_i_over_r": None,
            "solver_diagnostics": {"linear_residual_l2": 12.3, "solver_warning": "rank deficient"},
        },
    }
    (fit / "c5_solver_source_fit_summary.json").write_text(json.dumps(summary))
    _write_csv(fit / "c5_solver_response_matrix.csv", [
        {"source_level": 2, "raw_forbidden": 0.0, "raw_intercombination": 0.0, "raw_resonance": 0.0, "response_forbidden_norm": 0.0, "response_intercombination_norm": 0.0, "response_resonance_norm": 0.0},
        {"source_level": 3, "raw_forbidden": 1.0, "raw_intercombination": -0.1, "raw_resonance": 0.2, "response_forbidden_norm": 0.8, "response_intercombination_norm": 0.0, "response_resonance_norm": 0.2},
    ])
    _write_csv(fit / "c5_solver_source_fit_weights.csv", [
        {"source_level": 2, "fit_weight_norm": 0.4, "fit_source_rate_s^-1": 1.0, "fit_contribution_forbidden": 0.0, "fit_contribution_intercombination": 0.0, "fit_contribution_resonance": 0.0},
        {"source_level": 3, "fit_weight_norm": 0.6, "fit_source_rate_s^-1": 1.0, "fit_contribution_forbidden": 0.48, "fit_contribution_intercombination": 0.0, "fit_contribution_resonance": 0.12},
    ])
    _write_csv(cdir / "c5_combined_solver_lines.csv", [
        {"lower_level": 1, "upper_level": 3, "lower_label": "1s2.1S_0", "upper_label": "1s1.2p1.3P_0", "A_s^-1": 100.0},
    ])
    out = tmp_path / "diag"
    subprocess.run([
        sys.executable, "examples/36_source_level_failure_diagnostics.py", str(run), "--out-dir", str(out), "--print-summary"
    ], check=True)
    rows = list(csv.DictReader((out / "helike_source_level_diagnostics.csv").open()))
    assert len(rows) == 2
    zero_row = next(row for row in rows if row["source_level"] == "2")
    assert "zero f/i/r response" in zero_row["level_failure_flags"]
    assert float(zero_row["response_forbidden_norm"]) == 0.0
    assert float(zero_row["fit_contribution_forbidden"]) == 0.0
    summary_rows = list(csv.DictReader((out / "helike_source_level_density_summary.csv").open()))
    assert float(summary_rows[0]["zero_response_fitted_weight_sum"]) == 0.4
    assert (out / "helike_source_level_diagnostics.md").exists()


def test_source_level_failure_diagnostics_empty_run_reports_warning(tmp_path: Path):
    run = tmp_path / "c5_solver_source_fit_density_xstar_grid_v030"
    run.mkdir()
    out = tmp_path / "empty_diag"
    completed = subprocess.run([
        sys.executable, "examples/36_source_level_failure_diagnostics.py", str(run), "--out-dir", str(out), "--print-summary"
    ], check=True, capture_output=True, text=True)
    assert "levels=0" in completed.stdout
    assert "warning=No fit_ne_* directories found" in completed.stdout
    rows = list(csv.DictReader((out / "helike_source_level_density_summary.csv").open()))
    assert len(rows) == 1
    assert rows[0]["n_source_levels"] == "0"
    assert "No fit_ne_* directories found" in rows[0]["run_warning"]


def test_source_level_failure_diagnostics_uses_build_index_api():
    text = Path("examples/36_source_level_failure_diagnostics.py").read_text()
    assert "db.build_index()" in text
    assert "db.index_records()" not in text.split("if hasattr(db, \"index_records\"):", 1)[0]
