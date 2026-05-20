from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    Comp2Context,
    compare_comp2_probe,
    comp2,
    comp2_continuum_result,
    cmpfnc,
    hunt3_one_based,
    load_comp2_probe_reference,
    load_compton_table,
    validate_v0438_all_element_regression,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
)


ENERGY = np.asarray([1.0e-2, 1.0, 10.0, 51.1, 100.0, 1000.0, 1.0e4, 4.0e4])
BREMSA = np.asarray([3.0, 2.5, 2.0, 1.75, 1.5, 1.0, 0.5, 0.1])
TEMPERATURE_K = 76655.18557758832
XPX = 1.0e8
XEE = 1.2046560563936872


def test_v0439_coheat_global_state_loads_exact_source_table():
    table = load_compton_table()
    assert table.loaded
    assert table.ncomp == 101
    assert table.ecomp.shape == (101,)
    assert table.sxcomp.shape == (101,)
    assert table.decomp.shape == (101, 101)
    assert table.ecomp[0] == pytest.approx(1.0e-7)
    assert table.ecomp[-1] == pytest.approx(100.0)
    assert table.sxcomp[0] == pytest.approx(1.0e-7)
    assert table.sxcomp[-1] == pytest.approx(100.0)
    assert table.decomp[0, 0] == pytest.approx(3.0e-7)
    assert table.decomp[-1, -1] == pytest.approx(1.908e-4)
    assert table.source_sha256 == "899c3289e47a11e875caf41a44bb42e9685d1ed2ca78fc585c920520585949f2"


def test_v0439_hunt3_one_based_boundary_semantics():
    grid = [1.0, 2.0, 4.0, 8.0]
    assert hunt3_one_based(grid, 0.5) == 1
    assert hunt3_one_based(grid, 1.0) == 1
    assert hunt3_one_based(grid, 2.0) == 2
    assert hunt3_one_based(grid, 3.0) == 2
    assert hunt3_one_based(grid, 8.0) == 4
    assert hunt3_one_based(grid, 9.0) == 4


def test_v0439_cmpfnc_low_energy_and_table_paths():
    table = load_compton_table()
    low = cmpfnc(1.0e-4, 1.0e-5, table)
    assert not low.used_table
    assert low.value == pytest.approx(-6.0e-5, rel=0.0, abs=1.0e-20)
    tab = cmpfnc(2.0e-4, 1.0e-5, table)
    assert tab.used_table
    assert tab.energy_index_one_based == 37
    assert tab.temperature_index_one_based == 23
    assert tab.value == pytest.approx(-1.6001308724832212e-4, rel=2.0e-15)


def test_v0439_comp2_matches_original_fortran_reference():
    table = load_compton_table()
    result = comp2(ENERGY, BREMSA, temperature_k=TEMPERATURE_K, table=table)
    # Frozen from compiling and running the supplied original comp2.f90,
    # cmpfnc.f90, hunt3.f90, constants.f90, and globaldata.f90.
    assert result.cmp1 == pytest.approx(2.1158425111949917e-22, rel=2.0e-15)
    assert result.cmp2 == pytest.approx(4.4917059510086977e-24, rel=2.0e-15)
    assert result.ekt_ev == pytest.approx(6.605430786152838, rel=2.0e-15)
    assert result.n_cmpfnc_table_evaluations == 4
    assert result.n_cmpfnc_low_energy_evaluations == 4


def test_v0439_comp2_context_derives_heatf_coefficients_without_accumulation():
    table = load_compton_table()
    result, diagnostics = comp2_continuum_result(
        Comp2Context(ENERGY, BREMSA, table),
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    assert diagnostics["comp2_translated"]
    assert diagnostics["cmpfnc_table_loaded"]
    assert diagnostics["heatf_rates_derived_for_parity_only"]
    assert not diagnostics["heatf_rates_accumulated_into_totals"]
    assert diagnostics["htcomp"] == pytest.approx(4.0837278881878755e-26, rel=2.0e-15)
    assert diagnostics["clcomp"] == pytest.approx(5.72645590648991e-27, rel=2.0e-15)
    assert result.cmpfnc_table_loaded


def test_v0439_same_call_probe_loader_and_parity(tmp_path: Path):
    table = load_compton_table()
    result = comp2(ENERGY, BREMSA, temperature_k=TEMPERATURE_K, table=table)
    htcomp = result.heating_rate(hydrogen_density_cm3=XPX, electron_fraction_xee=XEE)
    clcomp = result.cooling_rate(hydrogen_density_cm3=XPX, electron_fraction_xee=XEE)

    summary = tmp_path / "xstar_calc_hmc_all_comp2_summary_probe.csv"
    with summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "calc_hmc_all_call_id", "ncn2", "temperature_t4",
            "electron_fraction_xee", "hydrogen_density_cm3", "ekt_ev",
            "cmp1", "cmp2", "htcomp", "clcomp",
        ])
        writer.writerow([73, len(ENERGY), TEMPERATURE_K / 1.0e4, XEE, XPX,
                         result.ekt_ev, result.cmp1, result.cmp2, htcomp, clcomp])
    grid = tmp_path / "xstar_calc_hmc_all_comp2_grid_probe.csv"
    with grid.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["calc_hmc_all_call_id", "grid_index", "ncn2", "epi_eV", "bremsa"])
        for idx, (energy, flux) in enumerate(zip(ENERGY, BREMSA), start=1):
            writer.writerow([73, idx, len(ENERGY), energy, flux])

    reference = load_comp2_probe_reference(tmp_path, call_id=73)
    parity = compare_comp2_probe(reference, table=table, rtol=1.0e-13, atol=1.0e-40)
    assert parity.ready
    assert parity.cmp1_parity_ready
    assert parity.cmp2_parity_ready
    assert parity.compton_heating_parity_ready
    assert parity.compton_cooling_parity_ready


def test_v0439_frozen_h_he_o_regression_is_packaged_and_ready():
    gate = validate_v0438_all_element_regression()
    assert gate.ready, gate.failed_requirements
    assert gate.summary["call_id"] == 73
    assert gate.summary["all_element_pre_continuum_acceptance_ready"] is True
    assert gate.summary["n_outside_tolerance"] == 0
    assert gate.summary["n_blocking_outside_tolerance"] == 0


def test_v0439_probe_is_nine_hook_and_captures_comp2():
    snippets = calc_hmc_all_insertion_snippets()
    assert len(snippets) == 17
    assert "calc_hmc_all_comp2" in snippets
    assert "xap_hmc_comp2" in snippets["calc_hmc_all_comp2"]
    helper = calc_hmc_all_probe_helper()
    assert "subroutine xap_hmc_comp2" in helper
    assert "xstar_calc_hmc_all_comp2_summary_probe.csv" in helper
    assert "xstar_calc_hmc_all_comp2_grid_probe.csv" in helper
