import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
REF = ROOT / "examples" / "reference_outputs" / "o7_solver_source_fit_summary_reference.json"


def _load_example20():
    path = ROOT / "examples" / "20_o7_solver_source_fit.py"
    spec = importlib.util.spec_from_file_location("o7_solver_source_fit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_example13():
    path = ROOT / "examples" / "13_o7_recombination_cascade_workflow.py"
    spec = importlib.util.spec_from_file_location("o7_recombination_cascade_workflow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_reference_solver_source_fit_matches_xstar_without_atdb():
    """Guard the validated O VII solver-source-fit reference ratios in CI.

    This uses a compact saved reference summary rather than the full 830 MB
    XSTAR atdb.fits file, so it can run in normal package tests.
    """
    data = json.loads(REF.read_text(encoding="utf-8"))
    x = data["xstar_reference"]
    fit = data["fitted_prediction"]
    combo = data["combined_source_validation"]

    assert abs(fit["R_f_over_i"] / x["R_f_over_i"] - 1.0) < 5e-6
    assert abs(fit["G_f_plus_i_over_r"] / x["G_f_plus_i_over_r"] - 1.0) < 5e-6
    assert abs(combo["R_f_over_i"] / x["R_f_over_i"] - 1.0) < 5e-6
    assert abs(combo["G_f_plus_i_over_r"] / x["G_f_plus_i_over_r"] - 1.0) < 5e-6


def test_reference_combined_validation_agrees_with_linear_response():
    data = json.loads(REF.read_text(encoding="utf-8"))
    fit = data["fitted_prediction"]
    combo = data["combined_source_validation"]
    assert abs(combo["R_f_over_i"] - fit["R_f_over_i"]) < 1e-6
    assert abs(combo["G_f_plus_i_over_r"] - fit["G_f_plus_i_over_r"]) < 1e-5
    assert combo["delta_R_vs_fitted_linear_response"] < 1e-6
    assert combo["delta_G_vs_fitted_linear_response"] < 1e-5


def test_reference_solver_matrix_treatment_is_validated_svd_path():
    data = json.loads(REF.read_text(encoding="utf-8"))
    treatment = data["solver_matrix_treatment"]
    diagnostics = data["combined_source_validation"]["solver_diagnostics"]
    pruning = diagnostics["null_rate_pruning_diagnostics"]

    assert treatment["linear_solver"] == "svd"
    assert treatment["rank_deficient_action"] == "svd"
    assert treatment["negative_population_action"] == "keep"
    assert treatment["prune_null_rate_levels"] is True
    assert diagnostics["matrix_rank"] < diagnostics["matrix_size"]
    assert diagnostics["solver"] == "numpy.linalg.svd_lstsq"
    assert diagnostics["linear_residual_l2"] < 0.01
    assert diagnostics["linear_residual_linf"] < 0.01
    assert pruning["n_levels_removed"] == 3
    assert pruning["removed_levels_preview"] == [44, 45, 241]


def test_example20_raw_response_fit_helper_reproduces_target():
    mod = _load_example20()
    target = np.array([0.6, 0.3, 0.1])
    raw_response = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    weights, info = mod.fit_raw_response_simplex(raw_response, target, max_iter=10000)
    assert info["status"] in {"converged", "max_iter"}
    assert np.all(weights >= 0.0)
    assert abs(float(weights.sum()) - 1.0) < 1e-12
    assert np.linalg.norm(weights - target) < 1e-5


def test_example13_warns_for_fitted_weights_without_source_total_rate():
    mod = _load_example13()
    args = SimpleNamespace(
        source_mode="selected-fit-weights",
        solver_source_total_rate=None,
        solver_source_csv_mode="auto",
    )
    msg = mod._selected_fit_source_amplitude_warning(args)
    assert msg is not None
    assert "--solver-source-total-rate 1.0" in msg


def test_example13_no_warning_when_source_total_rate_is_set():
    mod = _load_example13()
    args = SimpleNamespace(
        source_mode="selected-fit-weights",
        solver_source_total_rate=1.0,
        solver_source_csv_mode="auto",
    )
    assert mod._selected_fit_source_amplitude_warning(args) is None
