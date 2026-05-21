from __future__ import annotations

import json
from pathlib import Path

from xstar_atomic.source_port_dsec_source_zero_unrestricted_cli import (
    _branch_trajectory_ready,
    _classify,
    _clean_passthrough,
    _internal_evaluation2_ready,
    _write_products,
)


def _payload(**updates):
    payload = {
        "python_dsec_converged": True,
        "evaluation_count_ready": True,
        "branch_trajectory_ready": True,
        "thermal_trajectory_ready": True,
        "evaluation2_internal_ready": True,
        "post_dsec_calc_hmc_all_executed": True,
        "final_fixed_state_parity_ready": True,
        "frozen_v0444_complete_fixed_state_regression": True,
        "strict_trajectory_ready": False,
        "transition_state_ready": False,
        "python_evaluation_count": 33,
        "xstar_evaluation_count": 33,
        "runtime_failures": [],
        "thermal_evaluations": [
            {
                "evaluation_index": 1,
                "ready": True,
                "n_failed_quantities": 0,
                "failed_quantities": [],
                "max_relative_difference": 1.0e-6,
                "max_absolute_difference": 1.0e-12,
            }
        ],
    }
    payload.update(updates)
    return payload


def test_unrestricted_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations", "4",
        "--prepare-only",
        "--global-writeback-mode", "legacy-selected",
        "--leveltemp-lifecycle", "carry",
        "--terminal-continuum-seed-mode", "legacy-global",
        "--transition-input-mode", "replay-exact",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index=3",
        "--xstar-transition-internal-probe-dir", "probe",
        "--xstar-transition-internal-call-id", "7",
        "--print-summary",
        "--progress",
    ]
    assert _clean_passthrough(args) == ["--atdb", "atdb.fits", "--progress"]


def test_unrestricted_branch_gate_ignores_strict_runtime_workspace() -> None:
    summary = {
        "event_sequence_ready": True,
        "integer_control_state_ready": True,
        "runtime_state_ready": False,
        "thermal_residual_value_ready": True,
        "thermal_residual_sign_ready": True,
        "charge_residual_value_ready": True,
        "charge_residual_sign_ready": True,
        "final_state_ready": True,
    }
    assert _branch_trajectory_ready(summary) is True


def test_unrestricted_internal_gate_uses_active_source_layers() -> None:
    summary = {
        "pre_matrix_ready": True,
        "same_call_matrix_active_closure_ready": True,
        "same_call_matrix_coefficient_ready": False,
        "initial_solver_population_ready": True,
        "final_solver_active_population_ready": True,
        "final_solver_outer_start_ready": True,
        "final_solver_source_xtot_ready": True,
        "thermal_family_ready": True,
        "element_array_ready": True,
    }
    assert _internal_evaluation2_ready(summary) is True


def test_unrestricted_classifier_accepts_source_semantic_roundoff() -> None:
    assert _classify(_payload()) == (
        "source_zero_unrestricted_source_semantic_ready_with_strict_roundoff"
    )


def test_unrestricted_classifier_reports_final_state_failure() -> None:
    assert _classify(_payload(final_fixed_state_parity_ready=False)) == (
        "source_zero_unrestricted_final_fixed_state_mismatch"
    )


def test_unrestricted_products_record_v0457_acceptance(tmp_path: Path) -> None:
    products = _write_products(tmp_path, _payload())
    data = json.loads(products["json"].read_text(encoding="utf-8"))
    assert data["port_version"] == "v0.4.57"
    assert data["unrestricted_source_semantic_acceptance_ready"] is True
    assert data["ready_to_advance_to_bremsmap"] is True
    assert data["diagnostic_conclusion"] == (
        "source_zero_unrestricted_source_semantic_ready_with_strict_roundoff"
    )
