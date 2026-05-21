from __future__ import annotations

import json
from pathlib import Path

from xstar_atomic.source_port_dsec_source_zero_prefix_cli import (
    _branch_trajectory_ready,
    _classify,
    _clean_passthrough,
    _derived_bracket_drift_only,
    _write_products,
)


def _payload(**updates):
    payload = {
        "branch_trajectory_ready": True,
        "thermal_prefix_ready": True,
        "initial_solver_population_ready": True,
        "final_solver_active_population_ready": True,
        "thermal_family_ready": True,
        "element_array_ready": True,
        "transition_state_ready": True,
        "strict_trajectory_ready": False,
        "derived_bracket_drift_only": True,
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


def test_source_zero_prefix_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations=9",
        "--global-writeback-mode", "legacy-selected",
        "--leveltemp-lifecycle", "carry",
        "--terminal-continuum-seed-mode", "legacy-global",
        "--transition-input-mode", "replay-exact",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index", "3",
        "--xstar-transition-internal-probe-dir", "probe",
        "--xstar-transition-internal-call-id=7",
        "--print-summary",
        "--progress",
    ]
    assert _clean_passthrough(args) == ["--atdb", "atdb.fits", "--progress"]


def test_branch_trajectory_ignores_strict_runtime_workspace_drift() -> None:
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


def test_derived_bracket_drift_classifier() -> None:
    assert _derived_bracket_drift_only([
        {"quantity": "elctrh"},
        {"quantity": "hmcttl"},
    ]) is True
    assert _derived_bracket_drift_only([{"quantity": "temperature_t4"}]) is False
    assert _derived_bracket_drift_only([]) is False


def test_prefix_classifier_accepts_derived_bracket_roundoff() -> None:
    assert _classify(_payload()) == (
        "source_zero_four_evaluation_prefix_ready_with_derived_bracket_roundoff"
    )


def test_prefix_classifier_reports_non_strict_transition_arrays() -> None:
    assert _classify(_payload(transition_state_ready=False)) == (
        "source_zero_four_evaluation_prefix_ready_transition_arrays_not_strict"
    )


def test_prefix_products_record_v0456_acceptance(tmp_path: Path) -> None:
    products = _write_products(tmp_path, _payload())
    data = json.loads(products["json"].read_text(encoding="utf-8"))
    assert data["port_version"] == "v0.4.56"
    assert data["bounded_four_evaluation_acceptance_ready"] is True
    assert data["diagnostic_conclusion"] == (
        "source_zero_four_evaluation_prefix_ready_with_derived_bracket_roundoff"
    )
