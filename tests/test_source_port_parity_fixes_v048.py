from __future__ import annotations

import numpy as np
import pytest

from xstar_atomic.source_port import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    ElementMatrixAssembly,
    MatrixTerm,
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcRecord,
    UCalcStatus,
    msolvelucy,
)


def _two_level_assembly(initial=(0.6, 0.15)) -> ElementMatrixAssembly:
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
    up, down = 2.0, 8.0
    terms = [
        MatrixTerm(1, 10, 50, 4, 1, 7, "forward_offdiag", 2, 1, up, down, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(2, 10, 50, 4, 1, 7, "reverse_offdiag", 1, 2, down, up, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(3, 10, 50, 4, 1, 7, "forward_diag_loss", 1, 1, -up, -up, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(4, 10, 50, 4, 1, 7, "reverse_diag_loss", 2, 2, -down, -down, 0, 0, 1, 2, 1, 2, "evaluated"),
    ]
    matrix = np.asarray([[-up, down], [up, -down]], dtype=float)
    return ElementMatrixAssembly(
        basis=basis,
        initial_populations=np.asarray([0.0, *initial], dtype=float),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=np.asarray([[-up, down], [1.0, 1.0]], dtype=float),
        rhs=np.asarray([0.0, 1.0]),
        heating_matrix=np.zeros((2, 2)),
        heating_matrix2=np.zeros((2, 2)),
        ion_summaries=[],
        blocked_records=[],
        record_results=[],
        n_records_seen=1,
        n_records_evaluated=1,
        n_records_source_noop=0,
        n_records_skipped=0,
        n_records_blocked=0,
        n_unmapped_endpoints=0,
        strict_assembly_ready=True,
    )


def test_type86_uses_exact_fortran_packed_integer_offsets():
    ucalc = SourceFaithfulUCalc()
    # For six packed integers, Fortran label 86 reads [-4] and [-5].
    record = UCalcRecord(
        record=21269,
        data_type=86,
        rate_type=41,
        continuation=0,
        reals=(0.0, 1.1888e14),
        integers=(11, 22, 33, 44, 55, 66),
    )
    result = ucalc.evaluate(record, UCalcContext(temperature_k=1.0e6, nlev=43))
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == pytest.approx(1.1888e14)
    assert result.idest1 == 33
    assert result.idest2 == 64  # 43 + 22 - 1

    index_only = ucalc.evaluate(
        record,
        UCalcContext(temperature_k=1.0e6, nlev=43, indonly=True),
    )
    assert index_only.status is UCalcStatus.INDEX_ONLY
    assert (index_only.idest1, index_only.idest2) == (33, 64)


def test_msolvelucy_preserves_supplied_seed_scale_at_outer_start():
    assembly = _two_level_assembly(initial=(0.6, 0.15))
    context = ElementEquilibriumContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        min_ion_stage=7,
        max_ion_stage=7,
        capture_lucy_trace=True,
    )
    result = msolvelucy(assembly, context)
    assert result.trace is not None
    first_outer = [row for row in result.trace.outer_level_rows if row["outer_iteration"] == 1]
    assert sum(row["population_outer_start"] for row in first_outer) == pytest.approx(0.75)
    assert result.normalization == pytest.approx(1.0)


def test_physical_ion_stage_is_distinct_from_compact_counter_and_alias_uses_next_ground():
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=4,
        blocks=[],
        rows=[
            ElementBasisRow(
                1,
                superlevel=1,
                ion_counter=1,
                roles=[{"ion_stage": 3, "role": "ground"}],
            ),
            ElementBasisRow(
                2,
                superlevel=2,
                ion_counter=2,
                roles=[
                    {"ion_stage": 3, "role": "parent_continuum_or_next_ground"},
                    {"ion_stage": 4, "role": "ground"},
                ],
            ),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=2,
        normalization_row=2,
    )
    assert basis.nion.tolist() == [0, 1, 2]
    assert basis.ion_stage.tolist() == [0, 3, 4]
