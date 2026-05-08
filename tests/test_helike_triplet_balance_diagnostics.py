from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _make_solver_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "xstar_detail_population_comparison_summary.json").write_text(
        json.dumps(
            {
                "triplet": {
                    "f_fraction": 0.8,
                    "i_fraction": 0.02,
                    "r_fraction": 0.18,
                    "R": 40.0,
                    "G": 4.55,
                    "target_f_fraction": 0.81,
                    "target_i_fraction": 0.006,
                    "target_r_fraction": 0.184,
                }
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        path / "xstar_like_element_solver_triplet_component_balance_audit.csv",
        [
            {"component": "f", "population_sum": 1.0, "incoming_rate_sum_s^-1": 10.0, "diagonal_loss_rate_sum_s^-1": 1.0, "type71_cascade_in_rate_sum_s^-1": 2.0},
            {"component": "i", "population_sum": 0.1, "incoming_rate_sum_s^-1": 30.0, "diagonal_loss_rate_sum_s^-1": 3.0, "type71_cascade_in_rate_sum_s^-1": 6.0},
            {"component": "r", "population_sum": 0.01, "incoming_rate_sum_s^-1": 15.0, "diagonal_loss_rate_sum_s^-1": 4.0, "type71_cascade_in_rate_sum_s^-1": 2.0},
        ],
    )
    _write_csv(
        path / "xstar_like_element_solver_triplet_coupling_record_audit.csv",
        [
            {
                "audit_kind": "triplet_3S_3P_coupling_audit_summary",
                "radiative_i_to_f_gain_rate_sum_s^-1": 100.0,
                "collisional_f_to_i_gain_rate_sum_s^-1": 0.01,
                "collisional_i_to_f_gain_rate_sum_s^-1": 0.01,
                "radiative_i_to_f_over_collisional_f_to_i_rate_ratio": 10000.0,
            }
        ],
    )
    _write_csv(
        path / "xstar_like_element_solver_type50_ucalc_rate_audit.csv",
        [
            {
                "row_kind": "type50_ucalc_rate_audit_summary",
                "n_type50_rows": 10,
                "n_helike_3p_to_3s_uv_drain_rows": 3,
                "sum_raw_A_helike_3p_to_3s_s^-1": 300.0,
                "sum_escaped_decay_helike_3p_to_3s_s^-1": 105.0,
                "treatment": "xstar-escape",
            }
        ],
    )
    _write_csv(
        path / "xstar_like_element_solver_intercombination_feed_audit.csv",
        [
            {"route_role": "incoming_feed_to_intercombination_upper", "transition_kind": "radiative_decay", "data_type": "", "rate_s^-1": 5.0, "population_weighted_rate_proxy_s^-1": 0.5}
        ],
    )
    _write_csv(
        path / "xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv",
        [
            {"destination_triplet_component": "f", "rate_s^-1": 2.0},
            {"destination_triplet_component": "i", "rate_s^-1": 6.0},
            {"destination_triplet_component": "r", "rate_s^-1": 2.0},
        ],
    )
    _write_csv(
        path / "xstar_like_element_solver_global_superlevel_source_matrix_terms.csv",
        [
            {"superlevel_level": 49, "superlevel_level_label": "sprlevlt", "type99_parent_mapping_source": "explicit", "rate_s^-1": 1.0, "type71_B_i": 0.3, "type99_records": 1}
        ],
    )


def test_diagnose_helike_triplet_balance_outputs(tmp_path: Path) -> None:
    solver = tmp_path / "solver"
    _make_solver_dir(solver)
    out = tmp_path / "diag"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "44_diagnose_helike_triplet_balance.py"),
            "--case",
            f"C V:{solver}",
            "--out-dir",
            str(out),
            "--print-summary",
        ],
        check=True,
        cwd=ROOT,
    )
    assert (out / "helike_triplet_balance_diagnostic.md").exists()
    assert (out / "helike_type50_triplet_coupling_summary.csv").exists()
    payload = json.loads((out / "helike_triplet_balance_diagnostic_summary.json").read_text(encoding="utf-8"))
    assert payload["triplet_summary"][0]["case_label"] == "C V"
    assert any("C V intercombination fraction is high" in c for c in payload["conclusions"])


def test_diagnose_helike_triplet_balance_skips_missing_optional_audits(tmp_path: Path) -> None:
    solver = tmp_path / "solver_missing_optional"
    _make_solver_dir(solver)
    # Simulate a partially copied or older solver output directory.  The
    # diagnostic should still write summaries and warn, instead of aborting.
    (solver / "xstar_like_element_solver_triplet_component_balance_audit.csv").unlink()
    out = tmp_path / "diag_missing"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "44_diagnose_helike_triplet_balance.py"),
            "--case",
            f"C V:{solver}",
            "--out-dir",
            str(out),
            "--print-summary",
        ],
        check=True,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert "missing optional audit xstar_like_element_solver_triplet_component_balance_audit.csv" in completed.stdout
    payload = json.loads((out / "helike_triplet_balance_diagnostic_summary.json").read_text(encoding="utf-8"))
    assert payload["warnings"]
    assert payload["component_balance"][0]["status"] == "missing_optional_audit"


def test_prepare_c5_xstar_triplet_reference_plan(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "45_prepare_c5_xstar_triplet_reference.py"),
            "--root",
            str(tmp_path),
            "--print-summary",
        ],
        check=True,
        cwd=ROOT,
    )
    assert (tmp_path / "xstar_runs" / "c5_ne1e8" / "run_xstar.sh").exists()
    assert (tmp_path / "xstar_runs" / "c5_ne1e8" / "convert_c5_triplet.sh").exists()
    mapping = (tmp_path / "xstar_test_run" / "xstar_c5_density_grid_references.csv").read_text(encoding="utf-8")
    assert "xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv" in mapping
