from __future__ import annotations

import numpy as np

import xstar_atomic as xa
from xstar_atomic.source_port import (
    GSmoothResult,
    XSTARPythonDriver,
    XSTARSourceRoutine,
    register_bounded_radial_source_routines,
    run_bounded_radial_shell_validation,
    run_direct_fortran_gsmooth_validation,
)
from xstar_atomic.source_port.gsmooth import (
    _direct_gsmooth_python_result,
    gsmooth2,
)


def test_v0466_gsmooth_direct_original_fortran_gate():
    summary = run_direct_fortran_gsmooth_validation()
    assert summary["gsmooth_direct_original_fortran_reference_ready"] is True
    assert summary["gsmooth_vtherm_direct_fortran_ready"] is True
    assert summary["gsmooth_brcems_direct_fortran_ready"] is True
    assert summary["gsmooth_rccemis1_direct_fortran_ready"] is True
    assert summary["gsmooth_rccemis2_direct_fortran_ready"] is True
    assert summary["gsmooth_opakc_direct_fortran_ready"] is True


def test_v0466_gsmooth_preserves_source_owned_unchanged_ranges():
    result = _direct_gsmooth_python_result()
    assert isinstance(result, GSmoothResult)
    assert np.array_equal(result.brcems_after[:2], result.brcems_before[:2])
    assert np.array_equal(result.rccemis_after[:, :2], result.rccemis_before[:, :2])
    assert np.array_equal(result.opakc_after[:2], result.opakc_before[:2])
    assert np.array_equal(result.brcems_after[12:14], result.brcems_before[12:14])
    assert np.array_equal(result.rccemis_after[:, 12:14], result.rccemis_before[:, 12:14])
    assert np.array_equal(result.opakc_after[12:14], result.opakc_before[12:14])
    assert np.array_equal(result.brcems_after[14:], result.brcems_before[14:])
    assert np.array_equal(result.rccemis_after[:, 14:], result.rccemis_before[:, 14:])
    assert np.array_equal(result.opakc_after[14:], result.opakc_before[14:])


def test_v0466_gsmooth2_uses_source_bin_three_as_first_mutated_bin():
    epi = np.asarray([100.0, 101.0, 102.0, 103.0, 2.1e4])
    y = np.asarray([10.0, 20.0, 100.0, 40.0, 50.0])
    result = gsmooth2(
        vtherm_cm_s=3.0e9,
        epi_eV=epi,
        ydat_before=y,
        ncn2=5,
    )
    assert np.array_equal(result.ydat_after[:2], y[:2])
    assert result.ydat_after[2] != y[2]
    assert result.ydat_after[4] == y[4]


def test_v0466_wrapper_calls_four_helpers_in_source_order():
    result = _direct_gsmooth_python_result()
    assert len(result.helper_results) == 4
    assert np.array_equal(result.helper_results[0].ydat_before, result.brcems_before)
    assert np.array_equal(result.helper_results[1].ydat_before, result.rccemis_before[0])
    assert np.array_equal(result.helper_results[2].ydat_before, result.rccemis_before[1])
    assert np.array_equal(result.helper_results[3].ydat_before, result.opakc_before)


def test_v0466_turbulent_radial_branch_places_gsmooth_before_heatt():
    summary = run_bounded_radial_shell_validation()
    assert summary["turbulent_gsmooth_executed_ready"] is True
    assert summary["turbulent_gsmooth_before_heatt_ready"] is True
    assert summary["turbulent_shared_array_ownership_ready"] is True
    order = summary["turbulent_source_order"]
    assert order.index("calc_emis_all") < order.index("gsmooth") < order.index("heatt")
    assert summary["bounded_radial_shell_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "detail_and_final_output_writers"


def test_v0466_registration_includes_gsmooth_and_unsavd():
    driver = XSTARPythonDriver()
    register_bounded_radial_source_routines(driver)
    implemented = driver.implemented_source_routines()
    assert XSTARSourceRoutine.GSSMOOTH in implemented
    assert XSTARSourceRoutine.UNSAVD in implemented


def test_v0466_version():
    assert xa.__version__ == "0.4.75"
