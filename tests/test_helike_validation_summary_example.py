import csv
import json
import subprocess
import sys
from pathlib import Path


def test_helike_validation_summary_example(tmp_path):
    run_dir = tmp_path / "ca19_xi3_solver_source_fit_density_xstar_grid"
    run_dir.mkdir()
    csv_path = run_dir / "ca19_solver_source_fit_density_grid.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "electron_density_cm^-3",
                "xstar_R_f_over_i",
                "xstar_G_f_plus_i_over_r",
                "refitted_linear_R_f_over_i",
                "refitted_linear_G_f_plus_i_over_r",
                "refitted_combined_R_f_over_i",
                "refitted_combined_G_f_plus_i_over_r",
                "target_reachable",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "electron_density_cm^-3": "1",
            "xstar_R_f_over_i": "1.5",
            "xstar_G_f_plus_i_over_r": "2.3",
            "refitted_linear_R_f_over_i": "3.4",
            "refitted_linear_G_f_plus_i_over_r": "",
            "refitted_combined_R_f_over_i": "",
            "refitted_combined_G_f_plus_i_over_r": "",
            "target_reachable": "False",
        })
        writer.writerow({
            "electron_density_cm^-3": "1e12",
            "xstar_R_f_over_i": "1.4",
            "xstar_G_f_plus_i_over_r": "5.5",
            "refitted_linear_R_f_over_i": "1",
            "refitted_linear_G_f_plus_i_over_r": "2",
            "refitted_combined_R_f_over_i": "",
            "refitted_combined_G_f_plus_i_over_r": "",
            "target_reachable": "False",
        })
    (run_dir / "ca19_solver_source_fit_density_grid_summary.json").write_text(json.dumps({
        "element": "Ca",
        "ion_stage": 19,
        "temperature_K": 1.0e6,
        "warnings": ["mismatch"],
    }))

    audit_dir = tmp_path / "ca19_line_audit_xi3_ne1"
    audit_dir.mkdir()
    (audit_dir / "helike_xstar_line_audit_summary.json").write_text(json.dumps({
        "summary": {
            "expected_ion": "Ca XIX",
            "n_all_lines": 600,
            "n_expected_ion_rows_any_wavelength": 85,
            "n_expected_ion_rows_in_window": 5,
            "n_helike_like_rows_expected_ion": 5,
            "has_complete_triplet_target": True,
        }
    }))

    out_dir = tmp_path / "summary"
    cmd = [
        sys.executable,
        "examples/34_summarize_helike_validation_runs.py",
        str(run_dir),
        "--audit-dirs",
        str(audit_dir),
        "--out-dir",
        str(out_dir),
        "--print-summary",
    ]
    completed = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=True, text=True, capture_output=True)
    assert "ca19: status=not_validated reachable=0/2" in completed.stdout
    assert "audit Ca XIX: complete_triplet=True" in completed.stdout
    data = json.loads((out_dir / "helike_validation_summary.json").read_text())
    assert data["density_grid_runs"][0]["tag"] == "ca19"
    assert data["density_grid_runs"][0]["n_complete_xstar_targets"] == 2
    assert data["density_grid_runs"][0]["n_reachable"] == 0
    assert data["line_audits"][0]["has_complete_triplet_target"] is True
    assert (out_dir / "helike_validation_summary.md").exists()
