from __future__ import annotations

import json
from pathlib import Path

import pytest

from xstar_atomic.source_port import FixedStateElementRequest
from xstar_atomic.source_port_dsec_terminal_seed_cli import (
    _classify,
    _clean_passthrough,
    _write_products,
)


def _source_row(**updates):
    row = {
        "mode_id": "B_source_zero_terminal_seed",
        "label": "source",
        "terminal_continuum_seed_mode": "source-zero",
        "exit_code": 2,
        "transition_state_ready": True,
        "pre_matrix_ready": True,
        "same_call_matrix_active_closure_ready": True,
        "initial_solver_population_ready": True,
        "n_initial_solver_population_failures": 0,
        "initial_solver_population_failures_json": "[]",
        "final_solver_active_population_ready": True,
        "final_solver_outer_start_ready": True,
        "final_solver_source_xtot_ready": True,
        "thermal_family_ready": True,
        "element_array_ready": True,
        "cltot_pre_continuum_within_tolerance": False,
        "hmctot_within_tolerance": False,
        "cltot_pre_continuum_relative_difference": 0.01,
        "hmctot_relative_difference": 0.008,
        "primary_thermal_json": "{}",
    }
    row.update(updates)
    return row


def test_fixed_state_request_rejects_unknown_terminal_seed_mode() -> None:
    request = FixedStateElementRequest(
        element_z=8,
        min_ion_stage=5,
        max_ion_stage=8,
        terminal_continuum_seed_mode="unknown",
    )
    with pytest.raises(Exception, match="terminal_continuum_seed_mode"):
        request.validate()


def test_terminal_seed_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations", "7",
        "--global-writeback-mode", "legacy-selected",
        "--leveltemp-lifecycle", "carry",
        "--terminal-continuum-seed-mode", "legacy-global",
        "--transition-input-mode", "compare-only",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index", "4",
        "--print-summary",
        "--progress",
    ]
    assert _clean_passthrough(args) == ["--atdb", "atdb.fits", "--progress"]


def test_terminal_seed_classifier_identifies_primary_cause() -> None:
    row = _source_row(
        cltot_pre_continuum_within_tolerance=True,
        hmctot_within_tolerance=True,
    )
    assert _classify(row) == "terminal_continuum_seed_was_primary_cause"


def test_terminal_seed_classifier_advances_to_population_solution() -> None:
    row = _source_row(final_solver_active_population_ready=False)
    assert _classify(row) == (
        "terminal_seed_corrected_remaining_msolvelucy_population_solution"
    )


def test_terminal_seed_products_record_v0455_conclusion(tmp_path: Path) -> None:
    legacy = dict(_source_row())
    legacy.update(
        mode_id="A_legacy_global_terminal_seed",
        terminal_continuum_seed_mode="legacy-global",
        initial_solver_population_ready=False,
        n_initial_solver_population_failures=3,
    )
    source = _source_row(final_solver_active_population_ready=False)
    products = _write_products(tmp_path, [legacy, source])
    payload = json.loads(products["json"].read_text(encoding="utf-8"))
    assert payload["port_version"] == "v0.4.55"
    assert payload["source_zero_initial_solver_population_ready"] is True
    assert payload["diagnostic_conclusion"] == (
        "terminal_seed_corrected_remaining_msolvelucy_population_solution"
    )
