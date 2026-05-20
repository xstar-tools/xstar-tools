from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    CalcIonRatesResult,
    FixedStateElementRequest,
    IonStageLimitResult,
    IoneqmResult,
    IstrucResult,
    calc_hmc_all,
)


def _element_solver(master, derived, *, element_z, context, dispatcher=None):
    block = SimpleNamespace(ion_stage=1, nlev=2, ion_counter=1, ion_index=1)
    rows = [
        SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}]),
        SimpleNamespace(compact_index=2, roles=[{"ion_stage": 1, "local_level": 2}]),
    ]
    basis = SimpleNamespace(blocks=[block], rows=rows)
    assembly = SimpleNamespace(
        basis=basis,
        initial_populations=np.array([0.0, 0.4, 0.6]),
        lte_populations=np.array([0.0, 0.4, 0.6]),
    )
    solve = SimpleNamespace(
        heating=0.0,
        cooling=0.0,
        heating2=0.0,
        cooling2=0.0,
        # XSTAR msolvelucy ``xtot``: xo at the start of the final outer loop.
        ion_population_totals=np.array([0.4]),
        # XSTAR calc_hmc_element ``xii``: sum of returned final x, excluding continuum.
        ion_population_totals_final_vector=np.array([0.5]),
        recombination_totals=np.array([2.0]),
        ionization_totals=np.array([3.0]),
        ionization_components=np.zeros((3, 1)),
        recombination_components=np.zeros((3, 1)),
        populations=np.array([0.5, 0.5]),
        gamma=np.zeros(2),
        alpha=np.zeros(2),
        fgamma=np.zeros((5, 2)),
        falpha=np.zeros((5, 2)),
        igammamax_record=np.zeros(2, dtype=int),
        ialphamax_record=np.zeros(2, dtype=int),
    )
    return SimpleNamespace(
        assembly=assembly,
        solve=solve,
        full_element_direct_solve_ready=True,
    )


def _pre_matrix_solver(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: CalcIonRatesResult(1, 11, element_z, 1, 1, 3.0, 2.0, ready=True),
    }
    solved = IoneqmResult(
        fractions=np.array([0.5, 0.5]),
        q_ratio=np.array([1.0]),
        jmax=1,
        mmn=1,
        mmx=1,
    )
    preliminary = IstrucResult(
        ionization_rates=np.array([0.0, 3.0]),
        recombination_rates=np.array([0.0, 2.0]),
        fractions=np.array([0.0, 0.5, 0.5]),
        ioneqm=solved,
    )
    limits = IonStageLimitResult(1, 1, critf, 1, 1, 1)
    return rates, preliminary, limits


def test_calc_hmc_all_separates_final_xii_from_outer_start_xtot():
    result = calc_hmc_all(
        object(),
        SimpleNamespace(ion_element_z=np.array([0, 1])),
        elements=[FixedStateElementRequest(1, 1, 1, abundance=1.0)],
        temperature_k=76655.18557758832,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=0.5,
        element_solver=_element_solver,
        pre_matrix_solver=_pre_matrix_solver,
    )

    # calc_hmc_all.f90 stores calc_hmc_element's returned final-x total in xiin.
    assert result.ion_fractions[(1, 1)] == pytest.approx(0.5)
    # msolvelucy.f90 stores the final-outer-start xo total separately in xtotg.
    assert result.xtotg[(1, 1)] == pytest.approx(0.4)
    # The fully stripped residual and charge contribution are based on final xii.
    assert result.ion_fractions[(1, 2)] == pytest.approx(0.5)
    assert result.electron_contribution == pytest.approx(0.5)
    assert result.element_results[0].ion_fractions[1] == pytest.approx(0.5)
    assert result.element_results[0].fully_stripped_fraction == pytest.approx(0.5)


def test_legacy_synthetic_solve_without_final_vector_falls_back_to_source_total():
    equilibrium = _element_solver(None, None, element_z=1, context=None)
    del equilibrium.solve.ion_population_totals_final_vector

    def legacy_solver(*args, **kwargs):
        return equilibrium

    result = calc_hmc_all(
        object(),
        SimpleNamespace(ion_element_z=np.array([0, 1])),
        elements=[FixedStateElementRequest(1, 1, 1, abundance=1.0)],
        temperature_k=76655.18557758832,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=0.6,
        element_solver=legacy_solver,
        pre_matrix_solver=_pre_matrix_solver,
    )
    assert result.ion_fractions[(1, 1)] == pytest.approx(0.4)
    assert result.xtotg[(1, 1)] == pytest.approx(0.4)
