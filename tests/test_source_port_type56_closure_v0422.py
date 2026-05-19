from __future__ import annotations

import math

import pytest

from xstar_atomic.collisions import interp_type56_upsilon
from xstar_atomic.source_port import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
)


def _o8_like_levels() -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(2, energy_ev=653.5, statistical_weight=4.0),
        },
        nlev=2,
    )


def test_type56_hunt3_low_temperature_extrapolation_clips_to_source_zero():
    # Representative first two O VIII tabulated points documented by the
    # package.  solve-call 219 is below the tabulated grid.  XSTAR hunt3 uses
    # the first interval for linear extrapolation rather than flat-clamping.
    logt = [6.0, math.log10(3.0e6)]
    ups = [0.0308667, 0.720699]
    temperature = 76655.18557758832

    raw = ups[0] + (ups[1] - ups[0]) * (
        math.log10(temperature) - logt[0]
    ) / (logt[1] - logt[0])
    assert raw < 0.0
    assert interp_type56_upsilon(logt, ups, temperature) == 0.0


def test_type56_hunt3_interpolates_and_extrapolates_edge_intervals():
    logt = [6.0, 7.0, 8.0]
    ups = [1.0, 3.0, 7.0]
    assert interp_type56_upsilon(logt, ups, 10.0**6.5) == pytest.approx(2.0)
    assert interp_type56_upsilon(logt, ups, 10.0**8.5) == pytest.approx(9.0)


def test_type56_single_point_uses_second_record_real_as_literal_cijpp():
    assert interp_type56_upsilon([6.0], [0.25], 1.0e4) == pytest.approx(0.25)
    assert interp_type56_upsilon([6.0], [-0.25], 1.0e4) == 0.0


def test_source_port_type56_returns_four_exact_zero_matrix_channels_below_grid():
    temperature = 76655.18557758832
    context = UCalcContext(
        temperature_k=temperature,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        nlev=2,
        levels=_o8_like_levels(),
    )
    # First half is log10(T/K), second half is Upsilon, matching label 56.
    record = UCalcRecord(
        22862,
        56,
        3,
        0,
        (6.0, math.log10(3.0e6), 0.0308667, 0.720699),
        (1, 2),
    )
    result = SourceFaithfulUCalc().evaluate(record, context)

    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 2)
    assert result.ans1 == 0.0
    assert result.ans2 == 0.0
    assert result.ans5 == 0.0
    assert result.ans6 == 0.0
    assert result.diagnostics["upsilon"] == 0.0
    assert result.diagnostics["eval_method"] == "linear_logT_type56"
