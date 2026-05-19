from __future__ import annotations

import numpy as np
import pytest

from xstar_atomic.rates_type53 import Type53LiveRadiationState
from xstar_atomic.source_port import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
)


def _context(*, indonly: bool = False) -> UCalcContext:
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0,
                          ionization_potential_ev=13.6),
            5: UCalcLevel(5, energy_ev=13.6, statistical_weight=1.0,
                          ionization_potential_ev=13.6,
                          continuum_energy_ev=13.6),
        },
        nlev=5,
    )
    epi = np.linspace(1.0, 300.0, 512)
    radiation = Type53LiveRadiationState.from_sequences(
        epi, np.full(epi.size, 1.0e10), np.zeros(epi.size)
    )
    return UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        nlev=5,
        levels=levels,
        radiation=radiation,
        indonly=indonly,
        extras={
            "element_z": 8,
            "ion_stage": 4,
            "parent_level_energy_ev_by_destination": {6: 4.0},
            "parent_level_stat_weight_by_destination": {6: 3.0},
        },
    )


def _record() -> UCalcRecord:
    # Tail semantics for label 49:
    # [-4] = parent-level offset, [-3] = idest4/link field,
    # [-2] = bound level, [-1] = current ion.
    return UCalcRecord(
        15961,
        49,
        7,
        0,
        (0.0, 1.0, 10.0, 0.5, 20.0, 0.25),
        (7, 2, 99, 1, 31),
    )


def test_type49_index_only_uses_fourth_from_end_parent_offset():
    result = SourceFaithfulUCalc().evaluate(_record(), _context(indonly=True))
    assert result.status is UCalcStatus.INDEX_ONLY
    assert (result.idest1, result.idest2) == (1, 6)


def test_type49_full_evaluator_keeps_idest4_separate_from_parent_offset():
    result = SourceFaithfulUCalc().evaluate(_record(), _context())
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 6)
    assert result.diagnostics["type49_parent_offset_packed_index"] == -4
    assert result.diagnostics["type49_idest4_packed_index"] == -3
    assert result.diagnostics["type49_parent_offset"] == 2
    assert result.diagnostics["destination_statistical_weight"] == pytest.approx(3.0)
    assert result.ans1 >= 0.0
    assert result.ans2 >= 0.0


def test_type49_zero_or_negative_parent_offset_maps_to_preceding_source_row():
    record = UCalcRecord(15962, 49, 7, 0, (0.0, 1.0, 10.0, 0.5), (7, -3, 99, 1, 31))
    result = SourceFaithfulUCalc().evaluate(record, _context(indonly=True))
    # Literal source expression: nlevp + max(0, offset) - 1.
    assert result.idest2 == 4
