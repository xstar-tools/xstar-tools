from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    BremsstrahlungContext,
    bremem,
    bremem_continuum_result,
    compare_bremem_probe,
    load_bremem_probe_reference,
    validate_v0440_freef_regression,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
)


ENERGY = np.asarray([1.0e-2, 1.0, 10.0, 51.1, 100.0, 1000.0, 1.0e4, 4.0e4])
BRCEMS_BEFORE = np.asarray([9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0])
OPACITY = np.arange(1, 9, dtype=float) * 1.0e-20
TEMPERATURE_K = 76655.18557758832
XPX = 1.0e8
XEE = 1.2046560563936872


def test_v0441_bremem_matches_original_fortran_reference():
    result = bremem(
        ENERGY,
        BRCEMS_BEFORE,
        OPACITY,
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    expected = np.asarray(
        [
            7.5614592210082242e2,
            6.5090109423376748e2,
            1.6664111346301229e2,
            3.3077715684204134e-1,
            2.0158291945039468e-4,
            1.3526002046985489e-63,
            0.0,
            0.0,
        ]
    )
    assert result.brcems_after == pytest.approx(expected, rel=2.0e-15, abs=0.0)
    assert result.brtmp == pytest.approx(expected, rel=2.0e-15, abs=0.0)
    assert np.array_equal(result.opakc_after_cm_inv, OPACITY)
    assert np.all(result.gaunt_factor == 1.0)
    assert np.all(result.bbee == 0.0)


def test_v0441_bremem_context_preserves_reset_and_no_opacity_branch():
    result, diagnostics = bremem_continuum_result(
        BremsstrahlungContext(ENERGY, BRCEMS_BEFORE, OPACITY),
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    assert diagnostics["bremem_translated"]
    assert diagnostics["bremem_gaunt_factor_mode_unity"]
    assert diagnostics["brcems_workspace_cleared_before_population"]
    assert diagnostics["bremem_opacity_branch_active"] is False
    assert diagnostics["continuum_opacity_preserved"]
    assert diagnostics["heatf_accumulation_deferred"]
    assert np.array_equal(result.brcems_after, result.brtmp)


def test_v0441_same_call_probe_loader_and_parity(tmp_path: Path):
    result = bremem(
        ENERGY,
        BRCEMS_BEFORE,
        OPACITY,
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    summary = tmp_path / "xstar_calc_hmc_all_bremem_summary_probe.csv"
    with summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "calc_hmc_all_call_id",
                "ncn2",
                "temperature_t4",
                "electron_fraction_xee",
                "hydrogen_density_cm3",
                "ekt_ev",
                "t6",
                "electron_density_cm3",
                "enz2_cm3",
                "cc",
                "ion_charge",
            ]
        )
        writer.writerow(
            [
                73,
                result.ncn2,
                result.temperature_t4,
                XEE,
                XPX,
                result.ekt_ev,
                result.t6,
                result.electron_density_cm3,
                result.enz2_cm3,
                result.cc,
                result.ion_charge,
            ]
        )
    grid = tmp_path / "xstar_calc_hmc_all_bremem_grid_probe.csv"
    with grid.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "calc_hmc_all_call_id",
                "grid_index",
                "ncn2",
                "epi_eV",
                "temp",
                "gam",
                "gau",
                "brcems_before",
                "brtmp",
                "brcems_after",
                "bbee",
                "opakc_before",
                "opakc_after",
            ]
        )
        for idx in range(result.ncn2):
            writer.writerow(
                [
                    73,
                    idx + 1,
                    result.ncn2,
                    result.epi_eV[idx],
                    result.dimensionless_energy[idx],
                    result.gamma[idx],
                    result.gaunt_factor[idx],
                    result.brcems_before[idx],
                    result.brtmp[idx],
                    result.brcems_after[idx],
                    result.bbee[idx],
                    result.opakc_before_cm_inv[idx],
                    result.opakc_after_cm_inv[idx],
                ]
            )
    reference = load_bremem_probe_reference(tmp_path, call_id=73)
    parity = compare_bremem_probe(reference, rtol=1.0e-13, atol=1.0e-40)
    assert parity.ready
    assert parity.bremsstrahlung_emissivity_parity_ready
    assert parity.brcems_reset_semantics_ready
    assert parity.continuum_opacity_preserved_parity_ready


def test_v0441_frozen_freef_regression_is_packaged_and_ready():
    gate = validate_v0440_freef_regression()
    assert gate.ready, gate.failed_requirements
    assert gate.summary["calc_hmc_all_call_id"] == 73
    assert gate.summary["v0440_freef_acceptance_ready"] is True


def test_v0441_probe_is_thirteen_hook_and_captures_bremem_state():
    snippets = calc_hmc_all_insertion_snippets()
    assert len(snippets) == 17
    assert "calc_hmc_all_bremem_pre" in snippets
    assert "bremem_bin" in snippets
    assert "xap_hmc_bremem_pre" in snippets["calc_hmc_all_bremem_pre"]
    assert "xap_hmc_bremem_bin" in snippets["bremem_bin"]
    helper = calc_hmc_all_probe_helper()
    assert "subroutine xap_hmc_bremem_pre" in helper
    assert "subroutine xap_hmc_bremem_bin" in helper
    assert "xstar_calc_hmc_all_bremem_summary_probe.csv" in helper
    assert "xstar_calc_hmc_all_bremem_grid_probe.csv" in helper
