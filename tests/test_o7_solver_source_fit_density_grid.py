import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_example21():
    path = ROOT / "examples" / "21_o7_solver_source_fit_density_grid.py"
    spec = importlib.util.spec_from_file_location("o7_solver_source_fit_density_grid", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_example21_exists_and_documents_density_grid():
    path = ROOT / "examples" / "21_o7_solver_source_fit_density_grid.py"
    text = path.read_text(encoding="utf-8")
    assert "density-grid diagnostic" in text
    assert "fixed-weight baseline" in text
    assert "o7_solver_source_fit_density_grid.csv" in text
    assert "if __name__" in text


def test_example21_compare_weights_reports_changes():
    mod = _load_example21()
    out = mod.compare_weights({2: 0.5, 3: 0.5}, {2: 0.25, 3: 0.75})
    assert abs(out["weight_delta_l1"] - 0.5) < 1e-12
    assert out["weight_delta_l2"] > 0.0
    assert out["weight_delta_max_abs"] == 0.25
    assert out["top_weight_changes"][0]["source_level"] in {2, 3}


def test_example21_dry_run_reorders_reference_density_first(tmp_path):
    script = ROOT / "examples" / "21_o7_solver_source_fit_density_grid.py"
    cmd = [
        sys.executable,
        str(script),
        "dummy_atdb.fits",
        "--dry-run",
        "--electron-densities",
        "1e4",
        "1",
        "1e8",
        "--reference-density",
        "1",
        "--out-dir",
        str(tmp_path / "grid"),
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    assert "densities: 1, 10000, 1e+08" in result.stdout
    first_cmd = result.stdout.splitlines()[0]
    assert "--electron-density 1 " in first_cmd


def test_example21_flatten_row_adds_feasibility_flags_and_ratios():
    mod = _load_example21()

    class Args:
        xstar_target_label = "low-density XSTAR O VII reference reused at all densities"
        rg_tolerance = 5.0e-3
        reachable_rg_tolerance = 5.0e-2
        fit_objective_warn = 1.0e-4
        high_density_warning_threshold = 1.0e12

    xstar = {"R_f_over_i": 3.0, "G_f_plus_i_over_r": 10.0}
    fixed = {"R_f_over_i": 2.7, "G_f_plus_i_over_r": 8.0, "solver_diagnostics": {}}
    fit_summary = {
        "fitted_prediction": {
            "R_f_over_i": 3.0,
            "G_f_plus_i_over_r": 10.0,
            "fit_info": {"status": "converged", "objective": 1.0e-8},
        },
        "combined_source_validation": {
            "R_f_over_i": 3.003,
            "G_f_plus_i_over_r": 9.99,
            "solver_diagnostics": {},
        },
    }
    row = mod.flatten_row(1.0, xstar, 1.0, fixed, fit_summary, {}, Path("fit"), Path("fixed"), Args())
    assert row["fit_success_vs_xstar"] is True
    assert row["target_reachable"] is True
    assert abs(row["refitted_R_over_xstar"] - 1.001) < 1e-12
    assert abs(row["refitted_G_over_xstar"] - 0.999) < 1e-12
    assert abs(row["fixed_R_over_refitted"] - (2.7 / 3.003)) < 1e-12
    assert abs(row["fixed_G_over_refitted"] - (8.0 / 9.99)) < 1e-12
    assert row["xstar_target_is_reused_low_density_reference"] is True
    assert row["density_warning"] is None


def test_example21_flatten_row_warns_when_target_unreachable():
    mod = _load_example21()

    class Args:
        xstar_target_label = "low-density XSTAR O VII reference reused at all densities"
        rg_tolerance = 5.0e-3
        reachable_rg_tolerance = 5.0e-2
        fit_objective_warn = 1.0e-4
        high_density_warning_threshold = 1.0e12

    xstar = {"R_f_over_i": 3.0, "G_f_plus_i_over_r": 10.0}
    fixed = {"R_f_over_i": 0.1, "G_f_plus_i_over_r": 2.0, "solver_diagnostics": {}}
    fit_summary = {
        "fitted_prediction": {
            "R_f_over_i": 0.1,
            "G_f_plus_i_over_r": 0.7,
            "fit_info": {"status": "converged", "objective": 0.14},
        },
        "combined_source_validation": {
            "R_f_over_i": 0.1,
            "G_f_plus_i_over_r": 0.7,
            "solver_diagnostics": {},
        },
    }
    row = mod.flatten_row(1.0e12, xstar, 1.0, fixed, fit_summary, {}, Path("fit"), Path("fixed"), Args())
    assert row["fit_success_vs_xstar"] is False
    assert row["target_reachable"] is False
    assert "high-density type-68" in row["density_warning"]
    assert "fit objective" in row["density_warning"]
    assert "R/XSTAR" in row["density_warning"]
    assert "G/XSTAR" in row["density_warning"]
