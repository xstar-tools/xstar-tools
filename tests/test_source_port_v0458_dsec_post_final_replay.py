from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.source_port_dsec_physical_cli import build_parser as build_physical_parser
from xstar_atomic.source_port_dsec_post_final_replay_cli import (
    _classify,
    _clean_passthrough,
    _exact_final_source_semantic_summary,
    _natural_final_physics_ready,
    _source_control_flow_ready,
    _thermal_semantic_summary,
    _write_products,
)


def _accepted_payload(**updates):
    payload = {
        "python_dsec_converged": True,
        "evaluation_count_ready": True,
        "source_control_flow_ready": True,
        "thermal_component_trajectory_ready": True,
        "thermal_residual_sign_ready": True,
        "normalized_residual_roundoff_only": True,
        "evaluation2_internal_ready": True,
        "post_dsec_calc_hmc_all_executed": True,
        "natural_final_physics_ready": True,
        "natural_final_fixed_state_parity_ready": False,
        "exact_post_dsec_replay_executed": True,
        "exact_post_dsec_fixed_state_parity_ready": True,
        "exact_post_dsec_fixed_state_semantic_ready": True,
        "frozen_v0444_complete_fixed_state_regression": True,
        "strict_trajectory_ready": False,
        "python_evaluation_count": 33,
        "xstar_evaluation_count": 33,
        "python_final_temperature_t4": 7.6648,
        "xstar_final_temperature_t4": 7.6655,
        "python_final_electron_fraction_xee": 1.204656054,
        "xstar_final_electron_fraction_xee": 1.204656052,
        "normalized_residual_failures": [],
    }
    payload.update(updates)
    return payload


def test_physical_parser_accepts_compare_both_post_dsec_mode() -> None:
    parser = build_physical_parser()
    args = parser.parse_args(
        [
            "--atdb", "atdb.fits",
            "--xstar-dsec-trajectory", "trajectory.csv",
            "--oxygen-call73-regression-dir", "oxygen",
            "--out-dir", "out",
            "--post-dsec-input-mode", "compare-both",
        ]
    )
    assert args.post_dsec_input_mode == "compare-both"


def test_post_replay_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations", "4",
        "--global-writeback-mode", "legacy-selected",
        "--leveltemp-lifecycle", "carry",
        "--terminal-continuum-seed-mode", "legacy-global",
        "--transition-input-mode", "replay-exact",
        "--post-dsec-input-mode", "natural",
        "--compare-transition-internals",
        "--print-summary",
        "--progress",
    ]
    assert _clean_passthrough(args) == ["--atdb", "atdb.fits", "--progress"]


def test_source_control_flow_uses_events_integer_state_and_residual_signs() -> None:
    summary = {
        "event_sequence_ready": True,
        "integer_control_state_ready": True,
        "thermal_residual_sign_ready": True,
        "charge_residual_sign_ready": True,
        "thermal_residual_value_ready": False,
        "charge_residual_value_ready": False,
        "final_state_ready": False,
    }
    assert _source_control_flow_ready(summary) is True


def test_thermal_semantics_accept_same_sign_near_zero_hmctot(tmp_path: Path) -> None:
    path = tmp_path / "thermal.csv"
    fields = (
        "evaluation_index", "quantity", "python_value", "xstar_value",
        "absolute_difference", "relative_difference", "within_tolerance",
    )
    rows = [
        (24, "httot", 2.159574e-7, 2.159602e-7, 2.8e-12, 1.3e-5, True),
        (24, "cltot", 2.161144e-7, 2.161125e-7, 1.9e-12, 8.7e-6, True),
        (24, "hmctot", -7.270279e-4, -7.052245e-4, 2.18e-5, 3.09e-2, False),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)
    summary = _thermal_semantic_summary(path)
    assert summary["thermal_component_trajectory_ready"] is True
    assert summary["thermal_residual_sign_ready"] is True
    assert summary["normalized_residual_roundoff_only"] is True
    assert len(summary["normalized_residual_failures"]) == 1


def test_natural_final_physics_ignores_runtime_root_and_strict_continuum() -> None:
    summary = {
        "fixed_state_calc_hmc_all_translated": True,
        "pre_matrix_ready": True,
        "element_loop_ready": True,
        "charge_scope_complete": True,
        "continuum_sequence_complete": True,
        "runtime_state_parity_ready": False,
        "continuum_component_parity_ready": False,
        "primary_heating_cooling_totals_parity_ready": True,
        "secondary_heating_cooling_totals_parity_ready": True,
        "electron_contribution_parity_ready": True,
        "charge_residual_parity_ready": True,
        "charge_identity_ready": True,
        "hmctot_parity_ready": True,
        "complete_fixed_state_ready": True,
    }
    assert _natural_final_physics_ready(summary) is True


def test_post_replay_classifier_accepts_root_roundoff() -> None:
    assert _classify(_accepted_payload()) == (
        "source_zero_post_replay_ready_with_converged_root_roundoff"
    )


def test_post_replay_classifier_accepts_strict_residual_roundoff() -> None:
    assert _classify(
        _accepted_payload(exact_post_dsec_fixed_state_parity_ready=False)
    ) == "source_zero_post_replay_ready_with_source_converged_residual_roundoff"


def test_post_replay_classifier_reports_exact_semantic_failure() -> None:
    assert _classify(
        _accepted_payload(exact_post_dsec_fixed_state_semantic_ready=False)
    ) == "source_zero_post_replay_fixed_state_semantic_mismatch"


def test_exact_final_source_semantics_accept_source_converged_hmctot() -> None:
    py_h = 2.1780313628738658e-7
    py_c = 2.1779005273384123e-7
    xs_h = 2.1780603350353703e-7
    xs_c = 2.177880437491999e-7
    py_r = 2.0 * (py_h - py_c) / (1.0e-37 + py_h + py_c)
    xs_r = 2.0 * (xs_h - xs_c) / (1.0e-37 + xs_h + xs_c)
    rows = []
    for quantity, py, xs, ready in (
        ("temperature_t4", 7.6655, 7.6655, True),
        ("electron_fraction_xee", 1.204656, 1.204656, True),
        ("httot", py_h, xs_h, True),
        ("cltot", py_c, xs_c, True),
        ("httot2", 6.2541e-8, 6.2543e-8, True),
        ("cltot2", 6.21735e-8, 6.21736e-8, True),
        ("elcter", -4.1405e-5, -4.14068e-5, True),
        ("hmctot", py_r, xs_r, False),
    ):
        rows.append({
            "quantity": quantity,
            "python_value": str(py),
            "xstar_value": str(xs),
            "within_tolerance": str(ready),
        })
    summary = {
        "fixed_state_calc_hmc_all_translated": True,
        "pre_matrix_ready": True,
        "element_loop_ready": True,
        "charge_scope_complete": True,
        "continuum_sequence_complete": True,
        "runtime_state_parity_ready": True,
        "continuum_component_parity_ready": True,
        "primary_heating_cooling_totals_parity_ready": True,
        "secondary_heating_cooling_totals_parity_ready": True,
        "electron_contribution_parity_ready": True,
        "charge_residual_parity_ready": True,
        "charge_identity_ready": True,
        "hmctot_parity_ready": False,
        "complete_fixed_state_ready": True,
    }
    result = _exact_final_source_semantic_summary(summary, rows)
    assert result["exact_post_dsec_fixed_state_semantic_ready"] is True
    assert result["exact_post_dsec_hmctot_residual_only_failure"] is True
    assert result["exact_post_dsec_hmctot_source_expression_ready"] is True
    assert result["exact_post_dsec_hmctot_convergence_decision_ready"] is True
    assert result["exact_post_dsec_python_hmctot_converged"] is True
    assert result["exact_post_dsec_xstar_hmctot_converged"] is True


def test_post_replay_products_record_v0459_acceptance(tmp_path: Path) -> None:
    products = _write_products(tmp_path, _accepted_payload())
    data = json.loads(products["json"].read_text(encoding="utf-8"))
    assert data["port_version"] == "v0.4.59"
    assert data["unrestricted_source_semantic_acceptance_ready"] is True
    assert data["ready_to_advance_to_bremsmap"] is True
