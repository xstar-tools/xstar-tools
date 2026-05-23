from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
)


def _type59_context() -> UCalcContext:
    energies = np.geomspace(10.0, 2.0e3, 257)
    radiation = SimpleNamespace(
        epim_eV=energies,
        bremsam=np.full(energies.size, 2.5e10, dtype=float),
        bremsint=np.full(energies.size, 1.0, dtype=float),
    )
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            26: UCalcLevel(26, energy_ev=64.5, statistical_weight=1.0),
        },
        nlev=26,
    )
    return UCalcContext(
        temperature_k=73198.407060,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2020726184,
        abund1=3.0e-4,
        nlev=26,
        levels=levels,
        radiation=radiation,
        lfast=2,
    )


def _compact_type59_record(*, rate_type: int = 1) -> UCalcRecord:
    # Compact nrdt=6 layout from ucalc.f90:
    #   threshold, e0, s0, ya, pp, yw
    reals = (20.0, 30.0, 2.0, 1.5, 2.5, 0.2)
    # Keep the source's independent integer roles visible:
    #   ints[2] = l2
    #   ints[-4] = idest2 parent/continuum offset
    #   ints[-3] = idest4
    #   ints[-2] = idest1
    #   ints[-1] = idest3
    integers = (0, 0, 2, 1, 3, 1, 4)
    return UCalcRecord(6077, 59, rate_type, 19, reals, integers)


def test_type59_compact_layout_uses_reals_1_through_5_and_fourth_from_end_offset():
    context = _type59_context()
    record = _compact_type59_record()
    result = SourceFaithfulUCalc().evaluate(record, context)

    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2, result.idest3, result.idest4) == (1, 26, 4, 3)

    diagnostics = result.diagnostics
    assert diagnostics["type59_threshold_ev"] == pytest.approx(20.0)
    assert diagnostics["type59_e0_ev"] == pytest.approx(30.0)
    assert diagnostics["type59_s0"] == pytest.approx(2.0)
    assert diagnostics["type59_ya"] == pytest.approx(1.5)
    assert diagnostics["type59_pp"] == pytest.approx(2.5)
    assert diagnostics["type59_yw"] == pytest.approx(0.2)
    assert diagnostics["type59_l2"] == 2
    assert diagnostics["type59_parent_offset_packed_index"] == -4
    assert diagnostics["type59_idest4_packed_index"] == -3
    assert diagnostics["type59_parent_offset"] == 1
    assert diagnostics["type59_parameter_layout"] == "six_real_verner_fit_threshold_then_coefficients"

    epi = context.radiation.epim_eV
    qq = 5.5 + 2.0 - 2.5 / 2.0
    expected = []
    for energy in epi:
        if energy < 20.0:
            expected.append(0.0)
            continue
        xx = energy / 30.0
        yy = xx
        yyqq = math.exp(-min(60.0, max(-60.0, qq * math.log(max(yy, 1.0e-48)))))
        expected.append(
            2.0
            * ((xx - 1.0) ** 2 + 0.2**2)
            * yyqq
            * (1.0 + math.sqrt(yy / 1.5)) ** (-2.5)
            * 1.0e-18
        )
    assert diagnostics["type59_sigma_max_cm2"] == pytest.approx(max(expected), rel=1.0e-13)


def test_type59_rate_type1_zeroes_inverse_fields_before_universal_swap():
    result = SourceFaithfulUCalc().evaluate(_compact_type59_record(rate_type=1), _type59_context())

    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 > 0.0
    assert result.ans2 == 0.0
    # Source zeroes pre-swap ans4/ans6; after the universal swap those are
    # post-swap ans3/ans5.  Forward photo-heating survives in ans4/ans6.
    assert result.ans3 == 0.0
    assert result.ans5 == 0.0
    assert result.ans4 < 0.0
    assert result.ans6 < 0.0
    assert result.diagnostics["type59_reverse_zero_pre_swap_fields"] == "ans2;ans4;ans6"
    assert result.diagnostics["type59_reverse_zero_post_swap_fields"] == "ans2;ans3;ans5"
    assert result.diagnostics["type59_reverse_zero_applied"] is True


def test_type59_index_only_uses_distinct_parent_offset_and_idest4():
    context = _type59_context()
    context.indonly = True
    result = SourceFaithfulUCalc().evaluate(_compact_type59_record(), context)
    assert result.status is UCalcStatus.INDEX_ONLY
    assert (result.idest1, result.idest2, result.idest3, result.idest4) == (1, 26, 4, 3)


def test_type59_source_endpoint_guard_returns_literal_evaluated_zero():
    record = UCalcRecord(
        5386,
        59,
        1,
        19,
        (20.0, 30.0, 2.0, 1.5, 2.5, 0.2),
        (0, 0, 2, 1, 8, 1, 4),
    )
    result = SourceFaithfulUCalc().evaluate(record, _type59_context())
    assert result.status is UCalcStatus.EVALUATED
    assert result.ready is True
    assert result.reason == "type59_source_zero_idest4_exceeds_idest3_plus_one"
    assert (result.idest1, result.idest2, result.idest3, result.idest4) == (0, 0, 4, 8)
    assert (result.ans1, result.ans2, result.ans3, result.ans4, result.ans5, result.ans6) == (0.0,) * 6
    assert result.diagnostics["type59_source_guard_triggered"] is True
    assert result.diagnostics["type59_source_guard_action"] == "normal_zero_return_via_label_9000"


def test_type59_source_endpoint_guard_precedes_indonly_endpoint_mapping():
    record = UCalcRecord(
        5386,
        59,
        1,
        19,
        (20.0, 30.0, 2.0, 1.5, 2.5, 0.2),
        (0, 0, 2, 1, 8, 1, 4),
    )
    context = _type59_context()
    context.indonly = True
    result = SourceFaithfulUCalc().evaluate(record, context)
    assert result.status is UCalcStatus.INDEX_ONLY
    assert result.ready is True
    assert (result.idest1, result.idest2, result.idest3, result.idest4) == (0, 0, 4, 8)
    assert result.reason == "type59_source_zero_idest4_exceeds_idest3_plus_one"
