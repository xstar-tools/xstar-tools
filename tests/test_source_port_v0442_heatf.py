from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    HeatFContext,
    compare_heatf_probe,
    heatf,
    heatf_continuum_result,
    load_heatf_probe_reference,
    validate_v0441_bremem_regression,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
)


ENERGY = np.asarray([1.0e-2, 1.0, 10.0, 51.1, 100.0, 1000.0, 1.0e4, 4.0e4])
BRCEMS = np.asarray(
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
TEMPERATURE_K = 76655.18557758832
XPX = 1.0e8
XEE = 1.2046560563936872
HTFREEF = 6.9094394931782541e-30
CMP1 = 4.6905625028450016e-5
CMP2 = 5.820068794170258e-6
HTTOT = 1.234567890123456e-7
CLTOT = 9.876543210987654e-8
HTTOT2 = 2.345678901234567e-7
CLTOT2 = 8.765432109876543e-8
RADIUS = 1.23456789e17
DELR = 2.34567891e14


def _run():
    return heatf(
        ENERGY,
        BRCEMS,
        temperature_k=TEMPERATURE_K,
        radius_cm=RADIUS,
        zone_thickness_cm=DELR,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
        htfreef_erg_cm3_s=HTFREEF,
        cmp1=CMP1,
        cmp2=CMP2,
        httot_before=HTTOT,
        cltot_before=CLTOT,
        httot2_before=HTTOT2,
        cltot2_before=CLTOT2,
    )


def test_v0442_heatf_matches_original_fortran_reference():
    result = _run()
    expected = [
        9.0531222445937379e-9,
        7.4199797774093763e-9,
        1.2520823926436448e-8,
        1.3250991125693935e-7,
        1.1870623581372237e-7,
        2.4362101236805045e-7,
        1.0759512480261126e-7,
        1.0989481053806870e-1,
    ]
    actual = [
        result.htcomp_erg_cm3_s,
        result.clcomp_erg_cm3_s,
        result.clbrems_erg_cm3_s,
        result.httot_after,
        result.cltot_after,
        result.httot2_after,
        result.cltot2_after,
        result.hmctot,
    ]
    assert actual == pytest.approx(expected, rel=2.0e-15, abs=0.0)


def test_v0442_heatf_context_reports_complete_source_accumulation():
    result, diagnostics = heatf_continuum_result(
        HeatFContext(
            ENERGY,
            BRCEMS,
            HTFREEF,
            CMP1,
            CMP2,
            HTTOT,
            CLTOT,
            HTTOT2,
            CLTOT2,
            radius_cm=RADIUS,
            zone_thickness_cm=DELR,
        ),
        temperature_k=TEMPERATURE_K,
        hydrogen_density_cm3=XPX,
        electron_fraction_xee=XEE,
    )
    assert diagnostics["heatf_translated"]
    assert diagnostics["heatf_source_order_accumulation"]
    assert diagnostics["heatf_primary_totals_complete"]
    assert diagnostics["heatf_secondary_totals_complete"]
    assert diagnostics["heatf_hmctot_complete"]
    assert result.cumulative_clbrems_erg_cm3_s[-1] == result.clbrems_erg_cm3_s


def test_v0442_same_call_probe_loader_and_parity(tmp_path: Path):
    result = _run()
    summary = tmp_path / "xstar_calc_hmc_all_heatf_summary_probe.csv"
    with summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "calc_hmc_all_call_id", "ncn2", "temperature_t4", "radius_cm",
                "zone_thickness_cm", "electron_fraction_xee", "hydrogen_density_cm3",
                "electron_density_cm3", "ekt_ev", "htfreef", "cmp1", "cmp2",
                "httot_before", "cltot_before", "httot2_before", "cltot2_before",
                "htcomp", "clcomp", "clbrems", "httot_after", "cltot_after",
                "httot2_after", "cltot2_after", "hmctot",
            ]
        )
        writer.writerow(
            [
                73, result.ncn2, result.temperature_t4, result.radius_cm,
                result.zone_thickness_cm, XEE, XPX, result.electron_density_cm3,
                result.ekt_ev, HTFREEF, CMP1, CMP2, HTTOT, CLTOT, HTTOT2, CLTOT2,
                result.htcomp_erg_cm3_s, result.clcomp_erg_cm3_s,
                result.clbrems_erg_cm3_s, result.httot_after, result.cltot_after,
                result.httot2_after, result.cltot2_after, result.hmctot,
            ]
        )
    grid = tmp_path / "xstar_calc_hmc_all_heatf_grid_probe.csv"
    with grid.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "calc_hmc_all_call_id", "grid_index", "ncn2", "epi_eV", "brcems",
                "previous_brcems", "current_brcems", "cumulative_clbrems",
            ]
        )
        for idx in range(result.ncn2):
            writer.writerow(
                [
                    73, idx + 1, result.ncn2, result.epi_eV[idx], result.brcems[idx],
                    result.previous_brcems[idx], result.brcems[idx],
                    result.cumulative_clbrems_erg_cm3_s[idx],
                ]
            )
    reference = load_heatf_probe_reference(tmp_path, call_id=73)
    parity = compare_heatf_probe(reference, rtol=1.0e-13, atol=1.0e-40)
    assert parity.ready
    assert parity.primary_heating_cooling_totals_parity_ready
    assert parity.secondary_heating_cooling_totals_parity_ready
    assert parity.hmctot_parity_ready


def test_v0442_frozen_bremem_regression_is_packaged_and_ready():
    gate = validate_v0441_bremem_regression()
    assert gate.ready, gate.failed_requirements
    assert gate.summary["calc_hmc_all_call_id"] == 73
    assert gate.summary["v0441_bremem_acceptance_ready"] is True


def test_v0442_probe_is_sixteen_hook_and_captures_heatf_state():
    snippets = calc_hmc_all_insertion_snippets()
    assert len(snippets) == 16
    for key in ("calc_hmc_all_heatf_pre", "heatf_bin", "calc_hmc_all_heatf_post"):
        assert key in snippets
    helper = calc_hmc_all_probe_helper()
    assert "subroutine xap_hmc_heatf_pre" in helper
    assert "subroutine xap_hmc_heatf_bin" in helper
    assert "subroutine xap_hmc_heatf_post" in helper
    assert "xstar_calc_hmc_all_heatf_summary_probe.csv" in helper
    assert "xstar_calc_hmc_all_heatf_grid_probe.csv" in helper
