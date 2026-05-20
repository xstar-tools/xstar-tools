from __future__ import annotations

import math

import pytest

from xstar_atomic.source_port.element_equilibrium import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementIonBlock,
    _matrix_terms_for_result,
)
from xstar_atomic.source_port.ucalc import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
)


def _record(record: int = 572) -> UCalcRecord:
    # calt77 layout: nden=2, ntem=2, nll/lower=1, upper=2, Z=1, ion=1.
    # The four table values are log10(cul); the final real is the record wav.
    return UCalcRecord(
        record=record,
        data_type=77,
        rate_type=23,
        continuation=0,
        reals=(7.0, 9.0, 4.0, 6.0, 0.0, 0.0, 0.0, 0.0, 1000.0),
        integers=(2, 2, 1, 2, 1, 1),
    )


def _context(delta_e_ev: float) -> UCalcContext:
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(index=1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(index=2, energy_ev=float(delta_e_ev), statistical_weight=2.0),
        },
        nlev=2,
    )
    return UCalcContext(
        temperature_k=76655.18557758832,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        nlev=2,
        levels=levels,
    )


def _basis() -> tuple[ElementCompactBasis, ElementIonBlock]:
    block = ElementIonBlock(
        ion_index=1,
        ion_record=1,
        element_z=1,
        ion_stage=1,
        nlev=2,
        compact_start=1,
        compact_stop=2,
        first_level_record=1,
        ion_counter=1,
    )
    basis = ElementCompactBasis(
        element_z=1,
        min_ion_stage=1,
        max_ion_stage=1,
        blocks=[block],
        rows=[ElementBasisRow(1, 1, 1), ElementBasisRow(2, 2, 1)],
        n_rows=2,
        n_superlevels=2,
        n_ions=1,
        normalization_row=2,
    )
    return basis, block


def test_type77_source_gate_returns_evaluated_zero_below_one_ev():
    result = SourceFaithfulUCalc().evaluate(_record(), _context(0.449095))
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 2)
    assert (result.ans1, result.ans2, result.ans3, result.ans4, result.ans5, result.ans6) == (0.0,) * 6
    assert result.diagnostics["type77_source_gate"] == "endpoint_energy_separation_below_1_eV_zero"
    assert result.diagnostics["type77_calt77_status"] == "not_called_source_abs_delta_e_lt_1_eV_gate"


def test_type77_source_gate_is_strictly_less_than_one_ev():
    result = SourceFaithfulUCalc().evaluate(_record(), _context(1.0))
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans2 == pytest.approx(1.0)
    assert result.ans1 > 0.0
    assert math.isfinite(result.ans1)
    assert result.diagnostics.get("type77_source_gate") is None


def test_type77_source_zero_preserves_four_matrix_roles():
    context = _context(0.5)
    result = SourceFaithfulUCalc().evaluate(_record(), context)
    basis, block = _basis()
    terms = _matrix_terms_for_result(
        result=result,
        basis=basis,
        block=block,
        levels=context.levels,
        term_start=1,
        xpx=context.hydrogen_density_cm3,
    )
    assert len(terms) == 4
    assert {term.role for term in terms} == {
        "forward_offdiag",
        "reverse_offdiag",
        "forward_diag_loss",
        "reverse_diag_loss",
    }
    assert all(term.aj1 == 0.0 and term.aj2 == 0.0 for term in terms)
    assert all(term.cj == 0.0 and term.cj2 == 0.0 for term in terms)


def test_type77_invalid_endpoint_is_source_rejected():
    bad = UCalcRecord(
        record=999,
        data_type=77,
        rate_type=23,
        continuation=0,
        reals=_record().reals,
        integers=(2, 2, 1, 3, 1, 1),
    )
    result = SourceFaithfulUCalc().evaluate(bad, _context(2.0), strict=False)
    assert result.status is UCalcStatus.SOURCE_REJECTED
    assert result.reason == "type77_endpoint_outside_active_level_range"
