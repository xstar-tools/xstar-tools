from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.benchmarks import oxygen_call73_v0434_acceptance_path
from xstar_atomic.source_port import (
    AllElementFixedStateError,
    FixedStateElementRequest,
    build_all_element_fixed_state_requests,
    calc_hmc_all,
    load_all_element_fixed_state_plan,
    validate_oxygen_call73_regression,
    write_all_element_fixed_state_products,
)
from xstar_atomic.source_port.all_element_fixed_state import AllElementFixedStateRun
from xstar_atomic.source_port.element_equilibrium import EscapeProbabilityContext
from xstar_atomic.xstar_calc_hmc_all_probe import calc_hmc_all_probe_helper


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _accepted_summary(path: Path, *, call_id: int = 73, mutate: dict[str, object] | None = None) -> Path:
    required_true = {
        "pre_matrix_ready": True,
        "pre_continuum_state_ready": True,
        "element_array_ready": True,
        "global_ion_ready": True,
        "global_level_primary_ready": True,
        "global_level_active_ready": True,
        "global_level_derived_ready": True,
        "global_level_ready": True,
        "global_arrays_ready": True,
        "same_call_matrix_ready": True,
        "same_call_matrix_topology_ready": True,
        "same_call_matrix_active_closure_ready": True,
        "thermal_family_ready": True,
        "initial_solver_population_ready": True,
        "final_solver_snapshot_ready": True,
        "final_solver_same_iteration_ready": True,
        "final_solver_topology_ready": True,
        "final_solver_active_population_ready": True,
        "final_solver_outer_start_ready": True,
        "final_solver_source_xtot_ready": True,
        "type53_rate7_cj2_ready": True,
        "leveltemp_energy_ready": True,
        "type53_leveltemp_energy_ready": True,
        "oxygen_reassessment_ready": True,
        "oxygen_pre_continuum_acceptance_ready": True,
        "acceptance_gate_ready": True,
        "parity_ready": True,
    }
    payload: dict[str, object] = {
        "port_version": "v0.4.34",
        "call_id": call_id,
        "n_rows": 4369,
        "n_outside_tolerance": 0,
        "n_blocking_outside_tolerance": 0,
        **required_true,
    }
    if mutate:
        payload.update(mutate)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _probe_tree(root: Path, oxygen_summary: Path) -> Path:
    _write_csv(
        root / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv",
        [
            "calc_hmc_all_call_id", "element_index", "element_z", "abundance",
            "mml", "mmu", "htt", "cll", "htt2", "cll2",
        ],
        [
            {"calc_hmc_all_call_id": 73, "element_index": 1, "element_z": 1, "abundance": 1.0, "mml": 1, "mmu": 1, "htt": 1, "cll": 2, "htt2": 3, "cll2": 4},
            {"calc_hmc_all_call_id": 73, "element_index": 2, "element_z": 2, "abundance": 0.1, "mml": 1, "mmu": 2, "htt": 1, "cll": 2, "htt2": 3, "cll2": 4},
            {"calc_hmc_all_call_id": 73, "element_index": 8, "element_z": 8, "abundance": 6.8e-4, "mml": 3, "mmu": 8, "htt": 1, "cll": 2, "htt2": 3, "cll2": 4},
            {"calc_hmc_all_call_id": 73, "element_index": 6, "element_z": 6, "abundance": 0.0, "mml": 1, "mmu": 1, "htt": 0, "cll": 0, "htt2": 0, "cll2": 0},
        ],
    )
    _write_csv(
        root / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv",
        ["calc_hmc_all_call_id", "element_index", "element_z", "compact_dimension", "compact_index", "population"],
        [
            {"calc_hmc_all_call_id": 73, "element_index": 8, "element_z": 8, "compact_dimension": 2, "compact_index": 1, "population": 0.4},
            {"calc_hmc_all_call_id": 73, "element_index": 8, "element_z": 8, "compact_dimension": 2, "compact_index": 2, "population": 0.6},
        ],
    )
    # Existing v0.4.34 raw probes provide detailed products only for oxygen.
    for name in (
        "xstar_calc_hmc_element_pre_matrix_probe.csv",
        "xstar_calc_hmc_all_matrix_terms_probe.csv",
        "xstar_calc_hmc_all_msolvelucy_final_population_probe.csv",
        "xstar_calc_hmc_all_thermal_data_type_probe.csv",
        "xstar_calc_hmc_all_leveltemp_energy_probe.csv",
    ):
        _write_csv(
            root / name,
            ["calc_hmc_all_call_id", "element_z"],
            [{"calc_hmc_all_call_id": 73, "element_z": 8}],
        )
    return root


def test_packaged_oxygen_call73_summary_is_mandatory_and_accepted():
    summary = (
        oxygen_call73_v0434_acceptance_path()
        / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    )
    gate = validate_oxygen_call73_regression(summary)
    assert gate.ready is True
    assert gate.call_id == 73
    assert gate.observed["n_outside_tolerance"] == 0


def test_oxygen_regression_rejects_wrong_call_or_failed_gate(tmp_path: Path):
    wrong = validate_oxygen_call73_regression(
        _accepted_summary(tmp_path / "wrong.json", call_id=72)
    )
    assert wrong.ready is False
    assert any("call_id" in item for item in wrong.failed_requirements)

    failed = validate_oxygen_call73_regression(
        _accepted_summary(
            tmp_path / "failed.json",
            mutate={"thermal_family_ready": False},
        )
    )
    assert failed.ready is False
    assert "thermal_family_ready is not true" in failed.failed_requirements


def test_all_element_plan_uses_positive_abundance_source_order_and_reports_coverage(tmp_path: Path):
    summary = _accepted_summary(tmp_path / "oxygen.json")
    _probe_tree(tmp_path, summary)
    plan = load_all_element_fixed_state_plan(
        tmp_path,
        oxygen_regression_dir=summary,
        call_id=73,
    )
    assert plan.abundant_element_z == (1, 2, 8)
    assert plan.initial_population_elements == (8,)
    assert plan.missing_initial_population_elements == (1, 2)
    assert plan.pre_matrix_elements == (8,)
    assert plan.full_detailed_probe_coverage is False
    assert plan.execution_scope_ready is True

    requests = build_all_element_fixed_state_requests(
        plan,
        radiation=None,
        escape=EscapeProbabilityContext(),
        covering_fraction=1.0,
        turbulent_velocity_km_s=0.0,
        lfast=2,
        critf=1.0e-6,
        initial_population_policy="use-available",
    )
    assert tuple(item.element_z for item in requests) == (1, 2, 8)
    assert requests[0].initial_populations is None
    assert requests[1].initial_populations is None
    np.testing.assert_allclose(requests[2].initial_populations, [0.4, 0.6])
    assert requests[2].initial_population_source == "xstar_same_call_xileve_replay"

    with pytest.raises(AllElementFixedStateError, match="missing for abundant elements"):
        build_all_element_fixed_state_requests(
            plan,
            radiation=None,
            escape=EscapeProbabilityContext(),
            covering_fraction=1.0,
            turbulent_velocity_km_s=0.0,
            lfast=2,
            critf=1.0e-6,
            initial_population_policy="require-all",
        )


def _pre_matrix(master, derived, *, element_z, context, critf, dispatcher=None):
    z = int(element_z)
    return (
        {1: SimpleNamespace(ready=True, pirti=1.0, rrrti=2.0, contributions=[], ion_index=z)},
        SimpleNamespace(n_rates=1, fractions=np.array([0.0, 1.0, 0.0])),
        SimpleNamespace(mml=1, mmu=1),
    )


def _element_solver(master, derived, *, element_z, context, dispatcher=None):
    z = int(element_z)
    row = SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}])
    block = SimpleNamespace(
        ion_index=z,
        ion_stage=1,
        nlev=1,
        ion_counter=1,
        compact_index=lambda level: 1,
        second_pass_pirt=0.0,
        second_pass_rrrt=0.0,
    )
    assembly = SimpleNamespace(
        basis=SimpleNamespace(rows=[row], blocks=[block]),
        initial_populations=np.array([0.0, 1.0]),
        lte_populations=np.array([0.0, 1.0]),
        ion_summaries=[block],
        record_results=[],
    )
    solve = SimpleNamespace(
        heating=0.0,
        cooling=0.0,
        heating2=0.0,
        cooling2=0.0,
        ion_population_totals=np.array([1.0]),
        ionization_totals=np.array([0.0]),
        recombination_totals=np.array([0.0]),
        ionization_components=np.zeros((5, 1)),
        recombination_components=np.zeros((5, 1)),
        populations=np.array([1.0]),
        gamma=np.zeros(1),
        alpha=np.zeros(1),
        fgamma=np.zeros((5, 1)),
        falpha=np.zeros((5, 1)),
        igammamax_record=np.zeros(1, dtype=int),
        ialphamax_record=np.zeros(1, dtype=int),
    )
    return SimpleNamespace(assembly=assembly, solve=solve, full_element_direct_solve_ready=True)


def test_explicit_positive_abundance_scope_closes_charge_coverage():
    # Three ATDB elements exist. All three are requested, so the explicit
    # positive-abundance source scope is complete.
    derived = SimpleNamespace(
        n_ions=3,
        ion_records=np.array([0, 101, 102, 108]),
        ion_element_z=np.array([0, 1, 2, 8]),
        ion_stage=np.array([0, 1, 1, 1]),
        nlevs=np.array([0, 1, 1, 1]),
        npilev=np.array([[0, 0, 0, 0], [0, 11, 21, 81]]),
        element_records=np.array([0]),
    )
    requests = [
        FixedStateElementRequest(z, 1, 1, abundance=1.0)
        for z in (1, 2, 8)
    ]
    result = calc_hmc_all(
        object(),
        derived,
        elements=requests,
        required_element_z=(1, 2, 8),
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        element_solver=_element_solver,
        pre_matrix_solver=_pre_matrix,
    )
    assert result.charge_closure_scope_complete is True
    assert result.diagnostics["charge_scope_reference"] == "explicit_positive_abundance_element_scope"
    assert result.diagnostics["missing_required_element_z"] == []


def test_probe_helper_supports_zero_as_all_element_capture():
    helper = calc_hmc_all_probe_helper()
    assert "XSTAR_ATOMIC_HMC_TARGET_ELEMENT" in helper
    assert helper.count("xap_hmc_target_element .gt. 0") >= 5
    assert "xstar-atomic v0.4.41" in helper


def test_all_element_scope_products_record_missing_detailed_probes(tmp_path: Path):
    summary = _accepted_summary(tmp_path / "oxygen.json")
    _probe_tree(tmp_path, summary)
    plan = load_all_element_fixed_state_plan(
        tmp_path,
        oxygen_regression_dir=summary,
        call_id=73,
    )
    fake_result = SimpleNamespace(
        element_results=[],
        element_loop_ready=True,
        pre_matrix_ready=True,
        charge_closure_scope_complete=True,
        continuum=SimpleNamespace(complete=False),
        complete_fixed_state_ready=False,
    )
    run = AllElementFixedStateRun(
        plan=plan,
        result=fake_result,
        initial_population_policy="use-available",
    )
    paths = write_all_element_fixed_state_products(run, tmp_path / "out")
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["all_element_execution_ready"] is True
    assert payload["all_element_detailed_parity_probe_ready"] is False
    assert payload["missing_initial_population_elements"] == [1, 2]
    assert payload["next_required_probe_mode"] == "XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0"
