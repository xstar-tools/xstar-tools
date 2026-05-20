from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port.all_element_fixed_state import (
    AllElementFixedStateError,
    load_all_element_fixed_state_plan,
)
from xstar_atomic.source_port.msolvelucy_initial_state import (
    MSolveLucyInitialStateError,
    load_msolvelucy_initial_population_reference,
)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_zero_seed(root: Path, *, call_id: int = 11, element_z: int = 8) -> None:
    _write_csv(
        root / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv",
        [
            "calc_hmc_all_call_id",
            "element_index",
            "element_z",
            "compact_dimension",
            "compact_index",
            "population",
        ],
        [
            {
                "calc_hmc_all_call_id": call_id,
                "element_index": element_z,
                "element_z": element_z,
                "compact_dimension": 2,
                "compact_index": 1,
                "population": 0.0,
            },
            {
                "calc_hmc_all_call_id": call_id,
                "element_index": element_z,
                "element_z": element_z,
                "compact_dimension": 2,
                "compact_index": 2,
                "population": 0.0,
            },
        ],
    )


def _accepted_oxygen_summary(path: Path) -> Path:
    fields = {
        "pre_matrix_ready",
        "pre_continuum_state_ready",
        "element_array_ready",
        "global_ion_ready",
        "global_level_primary_ready",
        "global_level_active_ready",
        "global_level_derived_ready",
        "global_level_ready",
        "global_arrays_ready",
        "same_call_matrix_ready",
        "same_call_matrix_topology_ready",
        "same_call_matrix_active_closure_ready",
        "thermal_family_ready",
        "initial_solver_population_ready",
        "final_solver_snapshot_ready",
        "final_solver_same_iteration_ready",
        "final_solver_topology_ready",
        "final_solver_active_population_ready",
        "final_solver_outer_start_ready",
        "final_solver_source_xtot_ready",
        "type53_rate7_cj2_ready",
        "leveltemp_energy_ready",
        "type53_leveltemp_energy_ready",
        "oxygen_reassessment_ready",
        "oxygen_pre_continuum_acceptance_ready",
        "acceptance_gate_ready",
        "parity_ready",
    }
    payload: dict[str, object] = {
        "port_version": "v0.4.34",
        "call_id": 73,
        "n_rows": 1,
        "n_outside_tolerance": 0,
        "n_blocking_outside_tolerance": 0,
    }
    payload.update({name: True for name in fields})
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_zero_sum_seed_remains_rejected_by_default(tmp_path: Path) -> None:
    _write_zero_seed(tmp_path)
    with pytest.raises(MSolveLucyInitialStateError, match="non-positive sum"):
        load_msolvelucy_initial_population_reference(
            tmp_path, element_z=8, call_id=11
        )


def test_zero_sum_seed_is_accepted_only_when_explicitly_enabled(tmp_path: Path) -> None:
    _write_zero_seed(tmp_path)
    ref = load_msolvelucy_initial_population_reference(
        tmp_path,
        element_z=8,
        call_id=11,
        allow_zero_sum=True,
    )
    assert ref.population_sum == 0.0
    assert np.array_equal(ref.populations, np.zeros(2))


def test_call_correlated_plan_accepts_source_zero_compact_probes(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv",
        [
            "calc_hmc_all_call_id",
            "element_index",
            "element_z",
            "abundance",
            "mml",
            "mmu",
            "htt",
            "cll",
            "htt2",
            "cll2",
        ],
        [
            {
                "calc_hmc_all_call_id": 11,
                "element_index": 8,
                "element_z": 8,
                "abundance": 6.8e-4,
                "mml": 3,
                "mmu": 8,
                "htt": 0.0,
                "cll": 0.0,
                "htt2": 0.0,
                "cll2": 0.0,
            }
        ],
    )
    _write_zero_seed(tmp_path)
    summary = _accepted_oxygen_summary(tmp_path / "oxygen.json")

    with pytest.raises(AllElementFixedStateError, match="non-positive sum"):
        load_all_element_fixed_state_plan(
            tmp_path,
            oxygen_regression_dir=summary,
            call_id=11,
        )

    plan = load_all_element_fixed_state_plan(
        tmp_path,
        oxygen_regression_dir=summary,
        call_id=11,
        allow_zero_initial_population_sum=True,
    )
    assert plan.initial_population_elements == (8,)
    assert plan.initial_population_references[8].population_sum == 0.0
