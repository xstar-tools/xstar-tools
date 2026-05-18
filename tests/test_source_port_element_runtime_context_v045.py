from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from xstar_atomic.rates_type53 import Type53LiveRadiationState
from xstar_atomic.source_port import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
    load_escape_state_from_xstar_run,
)


def _levels() -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0, ionization_potential_ev=13.6, label="ground"),
            2: UCalcLevel(2, energy_ev=13.6, statistical_weight=1.0, ionization_potential_ev=13.6, continuum_energy_ev=13.6, label="continuum"),
        },
        nlev=2,
    )


def _radiation() -> Type53LiveRadiationState:
    epi = np.linspace(1.0, 200.0, 400)
    return Type53LiveRadiationState.from_sequences(epi, np.full(epi.size, 1.0e10), np.zeros(epi.size))


def _context() -> UCalcContext:
    return UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        covering_fraction=1.0,
        nlev=2,
        levels=_levels(),
        radiation=_radiation(),
        extras={"element_z": 8, "element_symbol": "O", "ion_stage": 7},
    )


def test_type50_decodes_source_a_slot_and_reconstructs_oscillator_strength():
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(1, 50, 4, 0, (1215.67, 0.0, 6.265e8), (2, 1, 1)),
        _context(),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == 0.0  # cfrac=1 source branch
    assert result.ans2 == pytest.approx(6.265e8)
    assert result.diagnostics["aij_s^-1"] == pytest.approx(6.265e8)
    assert result.diagnostics["oscillator_strength"] > 0.0


def test_collision_adapter_supplies_complete_element_ion_schema():
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(2, 56, 3, 0, (5.0, 7.0, 1.0, 1.0), (1, 2, 1)),
        _context(),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.diagnostics["element"] == "O"
    assert result.diagnostics["ion_stage"] == 7
    assert result.ans1 > 0.0 and result.ans2 > 0.0


def test_type53_decodes_packed_cross_section_without_predecoded_record():
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(3, 53, 7, 0, (0.0, 1.0, 10.0, 0.5), (1, 9, 1, 31)),
        _context(),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 2)
    assert result.ans1 >= 0.0 and result.ans2 > 0.0
    assert result.diagnostics["threshold_eV"] == pytest.approx(13.6)
    assert result.diagnostics["packed_parent_offset"] == 1
    assert result.diagnostics["packed_parent_offset_index"] == -4


def test_type53_index_only_uses_fourth_from_end_parent_offset():
    context = _context()
    context.indonly = True
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(3052, 53, 7, 0, (), (4, 2, 8, 1, 31)),
        context,
    )
    assert result.status is UCalcStatus.INDEX_ONLY
    assert (result.idest1, result.idest2) == (1, 3)


def test_type53_uses_fourth_from_end_parent_offset_for_excited_parent():
    context = _context()
    context.extras.update({
        "parent_level_energy_ev_by_destination": {3: 5.0},
        "parent_level_stat_weight_by_destination": {3: 3.0},
    })
    # Real type-53 tail semantics: [-4]=parent level offset, [-3]=linked
    # parent ion/element field, [-2]=bound level, [-1]=current ion.
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(3053, 53, 7, 0, (0.0, 1.0, 10.0, 0.5), (4, 2, 8, 1, 31)),
        context,
    )
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 3)
    assert result.diagnostics["packed_parent_offset"] == 2
    assert result.diagnostics["packed_parent_offset_index"] == -4
    assert result.diagnostics["source_idest2_expression"] == "nlevp + integers[-4] - 1"
    assert result.diagnostics["threshold_eV"] == pytest.approx(18.6)
    assert result.diagnostics["destination_statistical_weight"] == pytest.approx(3.0)


def test_type99_derives_threshold_and_uses_live_phint53hunt():
    # nden=1, ntem=2, nxs=2; then density, temperatures, recombination table,
    # and two cross-section pairs.
    reals = (8.0, 5.0, 7.0, 1.0e-12, 2.0e-12, 0.0, 1.0, 10.0, 0.5)
    # Real type-99 records retain the linked type-70 tail:
    # i8=parent level offset, i9=parent ion/element field,
    # i10=bound level, i11=current ion.
    integers = (1, 2, 2, 0, 0, 0, 0, 1, 8, 1, 31)
    context = _context()
    context.electron_fraction_xee = 1.2
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(4, 99, 7, 0, reals, integers),
        context,
    )
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 2)
    assert result.diagnostics["type99_parent_level_offset_packed_index"] == -4
    assert result.diagnostics["type99_parent_level_offset"] == 1
    assert result.diagnostics["type99_threshold_eV_derived"] == pytest.approx(13.6)
    assert result.diagnostics["status"] == "evaluated_phint53hunt_live_grid"
    # calt99 receives XSTAR den=xpx, not xpx*xee.
    assert result.diagnostics["type99_calt99_density_cm3_used"] == pytest.approx(1.0e8)
    assert result.diagnostics["type99_calt99_density_semantics"] == "hydrogen_density_xpx"
    assert result.diagnostics["type99_phint53hunt_density_semantics"] == "electron_density_xpx_times_xee"
    assert result.ans2 == pytest.approx(
        result.diagnostics["type99_calt99_rec_cm3_s"] * 1.2e8
    )


def _write_radial(path: Path, zones: list[tuple[np.ndarray, np.ndarray, np.ndarray]], index_name: str) -> None:
    hdus = [fits.PrimaryHDU()]
    for idx, tin, tout in zones:
        hdus.append(fits.BinTableHDU.from_columns([
            fits.Column(name=index_name, format="J", array=idx.astype(np.int32)),
            fits.Column(name="tau_in", format="D", array=tin.astype(float)),
            fits.Column(name="tau_out", format="D", array=tout.astype(float)),
        ], name="XSTAR_RADIAL"))
    fits.HDUList(hdus).writeto(path)


def test_sparse_escape_history_carries_forward_and_zero_fills_never_written(tmp_path: Path):
    run = tmp_path / "run"; run.mkdir()
    _write_radial(run / "xo01_detal2.fits", [
        (np.array([1]), np.array([1.0]), np.array([2.0])),
        (np.array([3]), np.array([0.3]), np.array([0.4])),
    ], "index")
    _write_radial(run / "xo01_detal3.fits", [
        (np.array([1]), np.array([5.0]), np.array([6.0])),
        (np.array([2]), np.array([0.5]), np.array([0.6])),
    ], "rrc index")
    derived = SimpleNamespace(nlsvn=4, ncsvn=3)
    reconstructed = load_escape_state_from_xstar_run(
        run, derived, zone="last", detail_policy="source_sparse_reconstruct",
    )
    assert reconstructed.context.line_taus(1) == pytest.approx((1.0, 2.0))
    assert reconstructed.context.line_taus(2) == pytest.approx((0.0, 0.0))
    assert reconstructed.context.line_taus(3) == pytest.approx((0.3, 0.4))
    assert reconstructed.n_line_indices_carried_forward == 1
    assert reconstructed.n_line_indices_zero_filled == 2
    assert reconstructed.n_line_indices_missing == 0
    assert reconstructed.source_writer_threshold_reconstruction is True
    assert reconstructed.exact_live_arrays is False

    strict = load_escape_state_from_xstar_run(
        run, derived, zone="last", detail_policy="strict_selected_zone",
    )
    assert strict.context.line_taus(1) == (None, None)
    assert strict.context.line_taus(2) == (None, None)
    assert strict.context.line_taus(3) == pytest.approx((0.3, 0.4))
