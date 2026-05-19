from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    CalcIonRatesResult,
    FixedStateContinuumResult,
    IonStageLimitResult,
    IoneqmResult,
    IstrucResult,
    FixedStateElementRequest,
    XSTARCALC_FIXED_STATE_ORDER,
    XSTARPythonDriver,
    XSTARPythonState,
    XSTARSourceRoutine,
    calc_hmc_all,
    resolve_calc_hmc_all_density,
)


def test_source_driver_runs_fixed_state_xstarcalc_order():
    driver = XSTARPythonDriver()
    seen = []
    for routine in XSTARCALC_FIXED_STATE_ORDER:
        driver.register_source_routine(routine, lambda state, routine=routine: seen.append(routine))
    state = driver.run_xstarcalc(fixed_state=True)
    assert seen == list(XSTARCALC_FIXED_STATE_ORDER)
    assert state.provenance["completed_source_routines"] == [r.value for r in XSTARCALC_FIXED_STATE_ORDER]


def test_calc_hmc_all_density_preserves_literal_lcdd_branches():
    assert resolve_calc_hmc_all_density(
        temperature_k=1.0e6, hydrogen_density_cm3=9.0,
        electron_fraction_xee=2.0, pressure=1.38e-2, lcdd=0,
    ) == pytest.approx(1.0e8)
    assert resolve_calc_hmc_all_density(
        temperature_k=1.0e6, hydrogen_density_cm3=9.0,
        electron_fraction_xee=2.0, pressure=4.0e8, lcdd=2,
    ) == pytest.approx(2.0e8)


def _fake_element_solver(master, derived, *, element_z, context, dispatcher=None):
    blocks = [
        SimpleNamespace(ion_stage=1, nlev=1),
        SimpleNamespace(ion_stage=2, nlev=1),
    ]
    rows = [
        SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}]),
        SimpleNamespace(compact_index=2, roles=[{"ion_stage": 2, "local_level": 1}]),
    ]
    basis = SimpleNamespace(blocks=blocks, rows=rows)
    assembly = SimpleNamespace(basis=basis, initial_populations=np.array([0.8, 0.2]))
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
    return SimpleNamespace(
        assembly=assembly,
        solve=solve,
        full_element_direct_solve_ready=True,
    )



def _fake_pre_matrix_solver(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: CalcIonRatesResult(1, 11, element_z, 1, 1, 70.0, 50.0, ready=True),
        2: CalcIonRatesResult(2, 12, element_z, 2, 1, 80.0, 60.0, ready=True),
    }
    solved = IoneqmResult(
        fractions=np.array([0.4, 0.35, 0.25]),
        q_ratio=np.array([1.0, 1.0]),
        jmax=2, mmn=1, mmx=2,
    )
    preliminary = IstrucResult(
        ionization_rates=np.array([0.0, 70.0, 80.0]),
        recombination_rates=np.array([0.0, 50.0, 60.0]),
        fractions=np.array([0.0, 0.4, 0.35, 0.25]),
        ioneqm=solved,
    )
    limits = IonStageLimitResult(1, 2, critf, 1, 2, 2)
    return rates, preliminary, limits

def test_fixed_state_calc_hmc_all_accumulates_source_shaped_products():
    continuum = FixedStateContinuumResult(
        heating=0.5, cooling=0.25, heating2=0.5, cooling2=0.25,
        htcomp=0.3, clcomp=0.2, clbrems=0.05, htfreef=0.2,
        complete=True,
    )
    result = calc_hmc_all(
        object(), SimpleNamespace(ion_element_z=np.array([0, 2])),
        elements=[FixedStateElementRequest(2, 1, 2, abundance=0.1)],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=0.14,
        continuum_kernel=lambda **kwargs: continuum,
        element_solver=_fake_element_solver,
        pre_matrix_solver=_fake_pre_matrix_solver,
    )
    assert result.element_loop_ready is True
    assert result.charge_closure_scope_complete is True
    assert result.complete_fixed_state_ready is True
    assert result.htt[2] == pytest.approx(0.3)
    assert result.cll[2] == pytest.approx(0.1)
    assert result.httot == pytest.approx(0.8)
    assert result.cltot == pytest.approx(0.35)
    assert result.ion_fractions[(2, 3)] == pytest.approx(0.05)
    # 0.75*0 + 0.20*1 + 0.05*2, all multiplied by abundance 0.1.
    assert result.electron_contribution == pytest.approx(0.03)
    assert result.elcter == pytest.approx(0.11)
    assert result.xilevg[(2, 1, 1)] == pytest.approx(0.75)
    assert result.rrrt[(2, 1)] == pytest.approx(50.0)
    assert result.pirt[(2, 2)] == pytest.approx(80.0)
    assert result.atotg[(2, 1)] == pytest.approx(5.0)
    assert result.stotg[(2, 2)] == pytest.approx(8.0)


def test_fixed_state_calc_hmc_all_does_not_claim_complete_without_continuum_or_full_charge_scope():
    result = calc_hmc_all(
        object(), object(),
        elements=[FixedStateElementRequest(8, 3, 8, abundance=1.0)],
        temperature_k=76655.18557758832,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        element_solver=_fake_element_solver,
        pre_matrix_solver=_fake_pre_matrix_solver,
    )
    assert result.element_loop_ready is True
    assert result.charge_closure_scope_complete is False
    assert result.continuum.complete is False
    assert result.complete_fixed_state_ready is False
