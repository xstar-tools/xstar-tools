from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    FreeFreeContext,
    compare_freef_probe,
    freef,
    freef_continuum_result,
    load_freef_probe_reference,
    validate_v0439_comp2_regression,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
)


ENERGY = np.asarray([1.0e-2, 1.0, 10.0, 51.1, 100.0, 1000.0, 1.0e4, 4.0e4])
BREMSA = np.asarray([3.0, 2.5, 2.0, 1.75, 1.5, 1.0, 0.5, 0.1])
OPACITY = np.arange(1, 9, dtype=float) * 1.0e-20
TEMPERATURE_K = 76655.18557758832
XPX = 1.0e8
XEE = 1.2046560563936872


def test_v0440_freef_matches_original_fortran_reference():
    result = freef(
        ENERGY,
        BREMSA,
        OPACITY,
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    # Frozen from compiling and running the supplied original freef.f90,
    # constants.f90, globaldata.f90, and PARAM.
    expected_opaff = np.asarray([
        2.9017443576089668e-18,
        2.6948119014121327e-22,
        1.4960854794476450e-24,
        1.4369331255330277e-26,
        1.9181778789904010e-27,
        1.9181783895890126e-30,
        1.9181783895890123e-33,
        2.9971537337328317e-35,
    ])
    assert result.htfreef_erg_cm3_s == pytest.approx(6.9094394931782541e-30, rel=2.0e-15)
    assert result.opacity_increment_cm_inv == pytest.approx(expected_opaff, rel=2.0e-15)
    assert result.opakc_after_cm_inv == pytest.approx(OPACITY + expected_opaff, rel=2.0e-15)
    assert np.all(result.gaunt_factor == 1.0)


def test_v0440_freef_context_preserves_in_place_semantics_without_heatf_accumulation():
    result, diagnostics = freef_continuum_result(
        FreeFreeContext(ENERGY, BREMSA, OPACITY),
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    assert diagnostics["freef_translated"]
    assert diagnostics["gaunt_factor_mode_unity"]
    assert diagnostics["free_free_opacity_added_in_place"]
    assert diagnostics["bremem_deferred"]
    assert diagnostics["heatf_accumulation_deferred"]
    assert result.opakc_after_cm_inv.shape == ENERGY.shape


def test_v0440_same_call_probe_loader_and_parity(tmp_path: Path):
    result = freef(
        ENERGY,
        BREMSA,
        OPACITY,
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    summary = tmp_path / "xstar_calc_hmc_all_freef_summary_probe.csv"
    with summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "calc_hmc_all_call_id", "ncn2", "temperature_t4",
            "electron_fraction_xee", "hydrogen_density_cm3", "ekt_ev",
            "t6", "electron_density_cm3", "enz2_cm3", "cc", "htfreef",
        ])
        writer.writerow([
            73, result.ncn2, result.temperature_t4, XEE, XPX, result.ekt_ev,
            result.t6, result.electron_density_cm3, result.enz2_cm3,
            result.cc, result.htfreef_erg_cm3_s,
        ])
    grid = tmp_path / "xstar_calc_hmc_all_freef_grid_probe.csv"
    with grid.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "calc_hmc_all_call_id", "grid_index", "ncn2", "epi_eV",
            "bremsa", "temp", "gam", "gau", "opakc_before", "opaff",
            "opakc_after", "cumulative_htfreef",
        ])
        for idx in range(result.ncn2):
            writer.writerow([
                73, idx + 1, result.ncn2, result.epi_eV[idx], result.bremsa[idx],
                result.dimensionless_energy[idx], result.gamma[idx], result.gaunt_factor[idx],
                result.opakc_before_cm_inv[idx], result.opacity_increment_cm_inv[idx],
                result.opakc_after_cm_inv[idx], result.cumulative_htfreef_erg_cm3_s[idx],
            ])
    reference = load_freef_probe_reference(tmp_path, call_id=73)
    parity = compare_freef_probe(reference, rtol=1.0e-13, atol=1.0e-40)
    assert parity.ready
    assert parity.free_free_opacity_increment_parity_ready
    assert parity.free_free_opacity_mutation_parity_ready
    assert parity.htfreef_parity_ready


def test_v0440_frozen_comp2_regression_is_packaged_and_ready():
    gate = validate_v0439_comp2_regression()
    assert gate.ready, gate.failed_requirements
    assert gate.summary["calc_hmc_all_call_id"] == 73
    assert gate.summary["v0439_comp2_acceptance_ready"] is True


def test_v0440_probe_is_eleven_hook_and_captures_freef_exact_bin_state():
    snippets = calc_hmc_all_insertion_snippets()
    assert len(snippets) == 11
    assert "calc_hmc_all_freef_pre" in snippets
    assert "freef_bin" in snippets
    assert "xap_hmc_freef_pre" in snippets["calc_hmc_all_freef_pre"]
    assert "xap_hmc_freef_bin" in snippets["freef_bin"]
    helper = calc_hmc_all_probe_helper()
    assert "subroutine xap_hmc_freef_pre" in helper
    assert "subroutine xap_hmc_freef_bin" in helper
    assert "xstar_calc_hmc_all_freef_summary_probe.csv" in helper
    assert "xstar_calc_hmc_all_freef_grid_probe.csv" in helper
