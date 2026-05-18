from __future__ import annotations

import pytest

from xstar_atomic.source_port.element_equilibrium import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementIonBlock,
    _matrix_terms_for_result,
)
from xstar_atomic.source_port.ucalc import (
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcResult,
    UCalcStatus,
    default_source_faithful_ucalc,
)


def test_type63_nondipole_record_is_source_zero_not_blocked():
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0, principal_n=2, orbital_l=0),
            2: UCalcLevel(2, energy_ev=1.0, statistical_weight=6.0, principal_n=2, orbital_l=2),
        },
        nlev=2,
    )
    record = UCalcRecord(
        record=1,
        data_type=63,
        rate_type=5,
        continuation=0,
        reals=(),
        integers=(1, 2, 8, 1),
    )
    context = UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        levels=levels,
        nlev=2,
        extras={"element_z": 8, "ion_stage": 7},
    )
    result = default_source_faithful_ucalc().evaluate(record, context, strict=False)
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == 0.0
    assert result.ans2 == 0.0
    assert result.idest1 == 1
    assert result.idest2 == 2
    assert result.diagnostics["source_zero_behavior"] == "ucalc_label63_preserves_initialized_zero_rates"


def test_type63_nchanging_descending_record_preserves_ucalc_channel_direction():
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=1.0, principal_n=2, orbital_l=0),
            2: UCalcLevel(2, energy_ev=20.0, statistical_weight=3.0, principal_n=3, orbital_l=1),
        },
        nlev=2,
    )
    # Type 63 packed endpoints are idat[nidt-4], idat[nidt-3].  This record
    # deliberately stores the higher-energy level first, as do the nine O VII
    # records that failed the v0.4.16 full-matrix parity comparison.
    record = UCalcRecord(
        record=22361,
        data_type=63,
        rate_type=3,
        continuation=0,
        reals=(),
        integers=(2, 1, 7, 8),
    )
    context = UCalcContext(
        temperature_k=7.665518557758832e4,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        levels=levels,
        nlev=2,
        extras={"element_z": 8, "ion_stage": 7},
    )
    result = default_source_faithful_ucalc().evaluate(record, context, strict=False)

    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (2, 1)
    assert result.diagnostics["type63_matrix_channel_convention"] == "literal_ucalc_record_order"
    assert result.ans1 == pytest.approx(
        result.diagnostics["type63_ucalc_ans1_forward_cm3_s"]
        * context.electron_density_cm3
    )
    assert result.ans2 == pytest.approx(
        result.diagnostics["type63_ucalc_ans2_reverse_cm3_s"]
        * context.electron_density_cm3
    )


def test_msolvelucy_ipmat_clamp_aliases_excited_parent_endpoint_to_last_row():
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=8,
        blocks=[],
        rows=[ElementBasisRow(i) for i in range(1, 608)],
        n_rows=607,
        n_superlevels=1,
        n_ions=6,
        normalization_row=607,
    )
    block = ElementIonBlock(
        ion_index=35,
        ion_record=1,
        element_z=8,
        ion_stage=7,
        nlev=241,
        compact_start=335,
        compact_stop=575,
        first_level_record=1,
    )
    result = UCalcResult(
        record=21523,
        data_type=53,
        rate_type=7,
        status=UCalcStatus.EVALUATED,
        ans1=2.0,
        ans2=3.0,
        idest1=8,
        idest2=276,
    )
    terms = _matrix_terms_for_result(
        result=result,
        basis=basis,
        block=block,
        levels=UCalcLevelTable(),
        term_start=1,
        xpx=1.0e8,
    )
    assert [(t.row, t.column) for t in terms] == [
        (607, 342),
        (342, 607),
        (342, 342),
        (607, 607),
    ]
    assert terms[0].source_row_unclamped == 610
    assert terms[1].source_column_unclamped == 610
    assert sum(t.source_ipmat_clamped for t in terms) == 3


def test_type63_same_n_descending_record_preserves_ucalc_channel_direction():
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=10.0, statistical_weight=7.0, principal_n=5, orbital_l=3),
            2: UCalcLevel(2, energy_ev=20.0, statistical_weight=9.0, principal_n=5, orbital_l=4),
        },
        nlev=2,
    )
    # This exercises the same-n amcrs/velimp branch used by the nine O VII
    # records in the solve-call-219 matrix comparison.  The higher-energy,
    # higher-l endpoint is stored first in the packed type-63 record.
    record = UCalcRecord(
        record=22361,
        data_type=63,
        rate_type=3,
        continuation=0,
        reals=(),
        integers=(2, 1, 7, 8),
    )
    context = UCalcContext(
        temperature_k=7.665518557758832e4,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        levels=levels,
        nlev=2,
        extras={"element_z": 8, "ion_stage": 7},
    )
    result = default_source_faithful_ucalc().evaluate(record, context, strict=False)

    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (2, 1)
    assert result.diagnostics["type63_matrix_channel_convention"] == "literal_ucalc_record_order"
    assert result.ans1 == pytest.approx(
        result.diagnostics["type63_ucalc_ans1_forward_cm3_s"]
        * context.electron_density_cm3
    )
    assert result.ans2 == pytest.approx(
        result.diagnostics["type63_ucalc_ans2_reverse_cm3_s"]
        * context.electron_density_cm3
    )
    # lf < li: XSTAR uses ans1=cn and ans2=cn*g_initial/g_final.
    assert result.diagnostics["type63_ucalc_ans2_reverse_cm3_s"] == pytest.approx(
        result.diagnostics["type63_ucalc_ans1_forward_cm3_s"] * 9.0 / 7.0
    )
