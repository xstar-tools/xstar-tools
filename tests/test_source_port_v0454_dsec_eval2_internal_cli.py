from __future__ import annotations

import json
from pathlib import Path

from xstar_atomic.source_port_dsec_eval2_internal_cli import (
    _classify,
    _clean_passthrough,
    _top_failed_rows,
    _write_summary,
)


def _runner() -> dict[str, object]:
    return {"dsec_transition_state_ready": True}


def _internal() -> dict[str, object]:
    return {
        "pre_matrix_ready": True,
        "same_call_matrix_ready": True,
        "same_call_matrix_topology_ready": True,
        "same_call_matrix_coefficient_ready": True,
        "same_call_matrix_active_closure_ready": True,
        "initial_solver_population_ready": True,
        "final_solver_snapshot_ready": True,
        "final_solver_topology_ready": True,
        "final_solver_coefficient_ready": True,
        "final_solver_active_population_ready": True,
        "final_solver_outer_start_ready": True,
        "final_solver_source_xtot_ready": True,
        "thermal_family_ready": True,
        "element_array_ready": True,
        "pre_continuum_summary_ready": True,
    }


def _thermal(*, primary_ready: bool = False) -> dict[str, dict[str, object]]:
    return {
        "cltot_pre_continuum": {
            "python_value": 1.0,
            "xstar_value": 1.01,
            "absolute_difference": 0.01,
            "relative_difference": 0.01,
            "within_tolerance": primary_ready,
        },
        "hmctot": {
            "python_value": -0.5,
            "xstar_value": -0.51,
            "absolute_difference": 0.01,
            "relative_difference": 0.02,
            "within_tolerance": primary_ready,
        },
        "elcter": {
            "python_value": 0.0,
            "xstar_value": 0.0,
            "absolute_difference": 0.0,
            "relative_difference": 0.0,
            "within_tolerance": True,
        },
    }


def test_eval2_internal_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations", "8",
        "--transition-input-mode=replay-exact",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index", "4",
        "--xstar-transition-internal-probe-dir", "probe",
        "--xstar-transition-internal-call-id=22",
        "--global-writeback-mode", "legacy-selected",
        "--leveltemp-lifecycle", "carry",
        "--terminal-continuum-seed-mode", "legacy-global",
        "--print-summary",
        "--progress",
    ]
    assert _clean_passthrough(args) == ["--atdb", "atdb.fits", "--progress"]


def test_classification_prefers_active_matrix_failure() -> None:
    internal = _internal()
    internal["same_call_matrix_coefficient_ready"] = False
    internal["same_call_matrix_active_closure_ready"] = False
    internal["final_solver_active_population_ready"] = False
    assert _classify(_runner(), internal, _thermal()) == (
        "evaluation_2_active_matrix_or_rate_coefficients"
    )


def test_strict_inactive_coefficient_difference_does_not_preempt_solver() -> None:
    internal = _internal()
    internal["same_call_matrix_coefficient_ready"] = False
    internal["final_solver_active_population_ready"] = False
    assert _classify(_runner(), internal, _thermal()) == (
        "evaluation_2_msolvelucy_population_solution"
    )


def test_classification_identifies_solver_population_failure() -> None:
    internal = _internal()
    internal["final_solver_active_population_ready"] = False
    assert _classify(_runner(), internal, _thermal()) == (
        "evaluation_2_msolvelucy_population_solution"
    )


def test_classification_identifies_thermal_family_failure() -> None:
    internal = _internal()
    internal["thermal_family_ready"] = False
    assert _classify(_runner(), internal, _thermal()) == (
        "evaluation_2_thermal_coefficient_or_channel_accumulation"
    )


def test_summary_reports_post_element_scope_when_all_internal_gates_pass(
    tmp_path: Path,
) -> None:
    products = _write_summary(
        tmp_path,
        runner=_runner(),
        internal=_internal(),
        thermal=_thermal(primary_ready=False),
        matrix_family_rows=[],
        thermal_family_rows=[],
    )
    payload = json.loads(products["json"].read_text(encoding="utf-8"))
    assert payload["port_version"] == "v0.4.54"
    assert payload["diagnostic_conclusion"] == (
        "post_element_accumulation_or_probe_scope_mismatch"
    )


def test_top_failed_rows_accepts_family_count_failures() -> None:
    rows = [
        {"data_type": "53", "n_outside_tolerance": "4", "l1_abs_cj2_difference": "3"},
        {"data_type": "50", "n_outside_tolerance": "1", "l1_abs_cj2_difference": "2"},
        {"data_type": "71", "n_outside_tolerance": "0", "l1_abs_cj2_difference": "9"},
    ]
    failed = _top_failed_rows(rows)
    assert [row["data_type"] for row in failed] == ["53", "50"]
