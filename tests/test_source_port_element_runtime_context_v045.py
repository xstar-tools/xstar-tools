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
        UCalcRecord(3, 53, 7, 0, (0.0, 1.0, 10.0, 0.5), (1, 1, 1)),
        _context(),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (1, 2)
    assert result.ans1 >= 0.0 and result.ans2 > 0.0
    assert result.diagnostics["threshold_eV"] == pytest.approx(13.6)


def test_type99_derives_threshold_and_uses_live_phint53hunt():
    # nden=1, ntem=2, nxs=2; then density, temperatures, recombination table,
    # and two cross-section pairs.
    reals = (8.0, 5.0, 7.0, 1.0e-12, 2.0e-12, 0.0, 1.0, 10.0, 0.5)
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(4, 99, 7, 0, reals, (1, 2, 2, 1, 1, 1)),
        _context(),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.diagnostics["type99_threshold_eV_derived"] == pytest.approx(13.6)
    assert result.diagnostics["status"] == "evaluated_phint53hunt_live_grid"
    assert result.ans2 > 0.0


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
