from __future__ import annotations

import csv
from types import SimpleNamespace
from pathlib import Path

import numpy as np

from xstar_atomic.source_port import (
    CalcIonRatesResult,
    FixedStateContinuumResult,
    FixedStateElementRequest,
    IonStageLimitResult,
    IoneqmResult,
    IstrucResult,
    calc_hmc_all,
    compare_complete_fixed_state_calc_hmc_all,
    load_calc_hmc_all_final_state_reference,
    validate_v0442_heatf_regression,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
)


def _element_solver(master, derived, *, element_z, context, dispatcher=None):
    blocks = [
        SimpleNamespace(ion_stage=1, nlev=1),
        SimpleNamespace(ion_stage=2, nlev=1),
    ]
    rows = [
        SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}]),
        SimpleNamespace(compact_index=2, roles=[{"ion_stage": 2, "local_level": 1}]),
    ]
    basis = SimpleNamespace(blocks=blocks, rows=rows)
    assembly = SimpleNamespace(basis=basis, initial_populations=np.array([0.8, 0.2]), ion_summaries=[])
    solve = SimpleNamespace(
        heating=3.0,
        cooling=1.0,
        heating2=4.0,
        cooling2=2.0,
        ion_population_totals=np.array([0.75, 0.20]),
        recombination_totals=np.array([5.0, 6.0]),
        ionization_totals=np.array([7.0, 8.0]),
        ionization_components=np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]),
        recombination_components=np.array([[6.0, 5.0], [4.0, 3.0], [2.0, 1.0]]),
        populations=np.array([0.75, 0.20]),
        gamma=np.array([10.0, 11.0]),
        alpha=np.array([12.0, 13.0]),
        fgamma=np.ones((5, 2)),
        falpha=np.full((5, 2), 2.0),
        igammamax_record=np.array([101, 102]),
        ialphamax_record=np.array([201, 202]),
    )
    return SimpleNamespace(assembly=assembly, solve=solve, full_element_direct_solve_ready=True)


def _pre_matrix(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: CalcIonRatesResult(1, 11, element_z, 1, 1, 70.0, 50.0, ready=True),
        2: CalcIonRatesResult(2, 12, element_z, 2, 1, 80.0, 60.0, ready=True),
    }
    solved = IoneqmResult(
        fractions=np.array([0.4, 0.35, 0.25]),
        q_ratio=np.array([1.0, 1.0]),
        jmax=2,
        mmn=1,
        mmx=2,
    )
    preliminary = IstrucResult(
        ionization_rates=np.array([0.0, 70.0, 80.0]),
        recombination_rates=np.array([0.0, 50.0, 60.0]),
        fractions=np.array([0.0, 0.4, 0.35, 0.25]),
        ioneqm=solved,
    )
    return rates, preliminary, IonStageLimitResult(1, 2, critf, 1, 2, 2)


def _result():
    continuum = FixedStateContinuumResult(
        heating=0.5,
        cooling=0.25,
        heating2=0.5,
        cooling2=0.25,
        htcomp=0.3,
        clcomp=0.2,
        clbrems=0.05,
        htfreef=0.2,
        httot_after=0.8,
        cltot_after=0.35,
        httot2_after=0.9,
        cltot2_after=0.45,
        hmctot_after=2.0 * (0.8 - 0.35) / (1.0e-37 + 0.8 + 0.35),
        complete=True,
        diagnostics={
            "comp2_translated": True,
            "freef_translated": True,
            "bremem_translated": True,
            "heatf_translated": True,
            "cmp1": 1.25,
            "cmp2": 2.5,
        },
    )
    return calc_hmc_all(
        object(),
        SimpleNamespace(ion_element_z=np.array([0, 2])),
        elements=[FixedStateElementRequest(2, 1, 2, abundance=0.1)],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=0.14,
        continuum_kernel=lambda **kwargs: continuum,
        element_solver=_element_solver,
        pre_matrix_solver=_pre_matrix,
    )


def test_v0443_complete_fixed_state_final_probe_parity(tmp_path: Path):
    result = _result()
    target = tmp_path / "xstar_calc_hmc_all_final_state_probe.csv"
    fields = [
        "calc_hmc_all_call_id", "temperature_t4", "temperature_k",
        "electron_fraction_xee", "hydrogen_density_cm3", "electron_density_cm3",
        "enelec", "elcter", "htfreef", "cmp1", "cmp2", "htcomp", "clcomp",
        "clbrems", "httot", "cltot", "httot2", "cltot2", "hmctot",
    ]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "calc_hmc_all_call_id": 73,
            "temperature_t4": result.temperature_k / 1.0e4,
            "temperature_k": result.temperature_k,
            "electron_fraction_xee": result.electron_fraction_xee,
            "hydrogen_density_cm3": result.hydrogen_density_cm3,
            "electron_density_cm3": result.electron_density_cm3,
            "enelec": result.electron_contribution,
            "elcter": result.elcter,
            "htfreef": result.continuum.htfreef,
            "cmp1": result.continuum.diagnostics["cmp1"],
            "cmp2": result.continuum.diagnostics["cmp2"],
            "htcomp": result.continuum.htcomp,
            "clcomp": result.continuum.clcomp,
            "clbrems": result.continuum.clbrems,
            "httot": result.httot,
            "cltot": result.cltot,
            "httot2": result.httot2,
            "cltot2": result.cltot2,
            "hmctot": result.hmctot,
        })
    reference = load_calc_hmc_all_final_state_reference(tmp_path, call_id=73)
    parity = compare_complete_fixed_state_calc_hmc_all(result, reference)
    assert parity.ready
    assert parity.complete_fixed_state_ready
    assert parity.charge_identity_ready


def test_v0443_frozen_heatf_regression_is_packaged_and_ready():
    gate = validate_v0442_heatf_regression()
    assert gate.ready, gate.failed_requirements
    assert gate.summary["v0442_heatf_acceptance_ready"] is True


def test_v0443_probe_is_seventeen_hook_and_captures_final_state():
    snippets = calc_hmc_all_insertion_snippets()
    assert len(snippets) == 17
    assert "calc_hmc_all_final_state" in snippets
    helper = calc_hmc_all_probe_helper()
    assert "subroutine xap_hmc_final_state" in helper
    assert "xstar_calc_hmc_all_final_state_probe.csv" in helper
