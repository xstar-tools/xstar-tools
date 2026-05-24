from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    CalcIonRatesResult,
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    ElementMatrixAssembly,
    FixedStateElementRequest,
    IonStageLimitResult,
    IoneqmResult,
    IstrucResult,
    MatrixTerm,
    calc_hmc_all,
    msolvelucy,
)
from xstar_atomic.source_port.linear_algebra import XSTARLinearAlgebraError
import xstar_atomic.source_port.element_equilibrium as ee


def _pre_matrix(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: CalcIonRatesResult(1, 1, element_z, 1, 1, 1.0, 1.0, ready=True),
    }
    solved = IoneqmResult(
        fractions=np.array([0.5, 0.5]),
        q_ratio=np.array([1.0]),
        jmax=1,
        mmn=1,
        mmx=1,
    )
    preliminary = IstrucResult(
        ionization_rates=np.array([0.0, 1.0]),
        recombination_rates=np.array([0.0, 1.0]),
        fractions=np.array([0.0, 0.5, 0.5]),
        ioneqm=solved,
    )
    return rates, preliminary, IonStageLimitResult(1, 1, critf, 1, 1, 1)


def _solver_capture(captured):
    def solver(master, derived, *, element_z, context, dispatcher=None):
        captured.append(context)
        basis = SimpleNamespace(
            blocks=[SimpleNamespace(ion_stage=1, nlev=1)],
            rows=[
                SimpleNamespace(
                    compact_index=1,
                    roles=[{"ion_stage": 1, "local_level": 1}],
                )
            ],
        )
        assembly = SimpleNamespace(
            basis=basis,
            initial_populations=np.array([0.0, 0.5]),
            lte_populations=np.array([0.0, 0.5]),
        )
        solve = SimpleNamespace(
            heating=0.0,
            cooling=0.0,
            heating2=0.0,
            cooling2=0.0,
            ion_population_totals=np.array([0.5]),
            ion_population_totals_final_vector=np.array([0.5]),
            recombination_totals=np.array([1.0]),
            ionization_totals=np.array([1.0]),
            ionization_components=np.zeros((3, 1)),
            recombination_components=np.zeros((3, 1)),
            populations=np.array([0.5]),
            gamma=np.zeros(1),
            alpha=np.zeros(1),
            fgamma=np.zeros((5, 1)),
            falpha=np.zeros((5, 1)),
            igammamax_record=np.zeros(1, dtype=int),
            ialphamax_record=np.zeros(1, dtype=int),
        )
        return SimpleNamespace(
            assembly=assembly,
            solve=solve,
            full_element_direct_solve_ready=True,
        )

    return solver


def test_calc_hmc_all_rebuilds_xh0_xh1_from_incoming_global_hydrogen_each_call():
    requests = [
        FixedStateElementRequest(
            1,
            1,
            1,
            abundance=0.9,
            neutral_h_density_cm3=999.0,
            ionized_h_density_cm3=999.0,
        ),
        FixedStateElementRequest(
            6,
            1,
            1,
            abundance=0.1,
            neutral_h_density_cm3=999.0,
            ionized_h_density_cm3=999.0,
        ),
    ]
    derived = SimpleNamespace(ion_element_z=np.array([0, 1, 6]))

    captured_first = []
    first = calc_hmc_all(
        object(),
        derived,
        elements=requests,
        temperature_k=1.0e6,
        hydrogen_density_cm3=100.0,
        electron_fraction_xee=1.0,
        initial_global_xilevg_by_index=np.array([0.25]),
        element_solver=_solver_capture(captured_first),
        pre_matrix_solver=_pre_matrix,
    )
    assert first.hydrogen_ground_fraction == pytest.approx(0.25)
    assert first.neutral_h_density_cm3 == pytest.approx(22.5)
    assert first.ionized_h_density_cm3 == pytest.approx(67.5)
    assert all(ctx.neutral_h_density_cm3 == pytest.approx(22.5) for ctx in captured_first)
    assert all(ctx.ionized_h_density_cm3 == pytest.approx(67.5) for ctx in captured_first)
    assert all(ctx.allow_lstsq_fallback is False for ctx in captured_first)
    assert all(ctx.allow_dense_matrix_rescue is False for ctx in captured_first)

    captured_second = []
    second = calc_hmc_all(
        object(),
        derived,
        elements=requests,
        temperature_k=1.0e6,
        hydrogen_density_cm3=100.0,
        electron_fraction_xee=1.0,
        initial_global_xilevg_by_index=np.array([0.40]),
        element_solver=_solver_capture(captured_second),
        pre_matrix_solver=_pre_matrix,
    )
    assert second.neutral_h_density_cm3 == pytest.approx(36.0)
    assert second.ionized_h_density_cm3 == pytest.approx(54.0)
    assert all(ctx.neutral_h_density_cm3 == pytest.approx(36.0) for ctx in captured_second)
    assert all(ctx.ionized_h_density_cm3 == pytest.approx(54.0) for ctx in captured_second)


def _two_level_assembly(*, terms=None) -> ElementMatrixAssembly:
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=7,
        max_ion_stage=7,
        blocks=[],
        rows=[
            ElementBasisRow(1, superlevel=1, ion_counter=1),
            ElementBasisRow(2, superlevel=2, ion_counter=1),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=1,
        normalization_row=2,
    )
    if terms is None:
        up, down = 2.0, 8.0
        terms = [
            MatrixTerm(1, 10, 50, 4, 1, 7, "forward_offdiag", 2, 1, up, down, 0, 0, 1, 2, 1, 2, "evaluated"),
            MatrixTerm(2, 10, 50, 4, 1, 7, "reverse_offdiag", 1, 2, down, up, 0, 0, 1, 2, 1, 2, "evaluated"),
            MatrixTerm(3, 10, 50, 4, 1, 7, "forward_diag_loss", 1, 1, -up, -up, 0, 0, 1, 2, 1, 2, "evaluated"),
            MatrixTerm(4, 10, 50, 4, 1, 7, "reverse_diag_loss", 2, 2, -down, -down, 0, 0, 1, 2, 1, 2, "evaluated"),
        ]
    matrix = np.asarray([[-2.0, 8.0], [2.0, -8.0]], dtype=float)
    return ElementMatrixAssembly(
        basis=basis,
        initial_populations=np.asarray([0.0, 0.6, 0.4]),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=np.asarray([[-2.0, 8.0], [1.0, 1.0]], dtype=float),
        rhs=np.asarray([0.0, 1.0]),
        heating_matrix=np.zeros((2, 2)),
        heating_matrix2=np.zeros((2, 2)),
        ion_summaries=[],
        blocked_records=[],
        record_results=[],
        n_records_seen=len(terms),
        n_records_evaluated=len(terms),
        n_records_source_noop=0,
        n_records_skipped=0,
        n_records_blocked=0,
        n_unmapped_endpoints=0,
        strict_assembly_ready=True,
    )


def _context(**kwargs):
    return ElementEquilibriumContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        min_ion_stage=7,
        max_ion_stage=7,
        **kwargs,
    )


def test_strict_lucy_does_not_fall_back_to_lstsq(monkeypatch):
    def fail_leqt(*args, **kwargs):
        raise XSTARLinearAlgebraError("synthetic failure")

    monkeypatch.setattr(ee, "leqt2f", fail_leqt)
    with pytest.raises(XSTARLinearAlgebraError):
        msolvelucy(
            _two_level_assembly(),
            _context(allow_lstsq_fallback=False, allow_dense_matrix_rescue=False),
        )


def test_strict_lucy_does_not_use_dense_rescue(monkeypatch):
    calls = []

    def fake_solve(matrix, normalization_row, *, allow_lstsq):
        calls.append((np.asarray(matrix).shape, allow_lstsq))
        if len(calls) > 1:
            raise AssertionError("strict source mode attempted dense rescue")
        return np.array([0.5, 0.5]), "synthetic_condensed", 2

    monkeypatch.setattr(ee, "_solve_normalized", fake_solve)
    result = msolvelucy(
        _two_level_assembly(terms=[]),
        _context(allow_lstsq_fallback=False, allow_dense_matrix_rescue=False),
    )
    assert len(calls) == 1
    assert result.normalization == pytest.approx(0.0)
    assert not any("rescue used" in note for note in result.notes)


def test_ordered_source_difference_loops_stop_at_source_caps():
    fixed = ee._source_fixed_difference(
        np.array([100.0, 5.0]), np.array([1.0, 1.0]), epsilon=1.0e-6
    )
    assert fixed == pytest.approx((100.0 - 1.0) ** 2)

    previous = np.array([-1.001, 100.0])
    current = np.array([1.0, 1.0])
    with np.errstate(all="ignore"):
        first_ratio = (previous[0] - current[0]) / (previous[0] + current[0])
    outer = ee._source_outer_difference(previous, current, epsilon=1.0e-6)
    assert outer == pytest.approx(min(1.0e10, float(first_ratio)) ** 2)
