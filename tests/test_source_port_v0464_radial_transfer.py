from __future__ import annotations

import numpy as np
import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import (
    XSTARPythonDriver,
    XSTARSourceRoutine,
    RadialTransferWorkspace,
    register_bounded_radial_source_routines,
    run_bounded_radial_shell_validation,
    run_direct_fortran_radial_validation,
    step,
    stpcut,
    trnfrc,
    trnfrn,
)


def test_v0464_direct_original_fortran_kernel_gate():
    summary = run_direct_fortran_radial_validation()
    assert summary["direct_original_fortran_reference_ready"] is True
    assert summary["step_direct_fortran_ready"] is True
    assert summary["trnfrc_out_bremsa_ready"] is True
    assert summary["trnfrc_in_bremsint_ready"] is True
    assert summary["stpcut_tau0_ready"] is True
    assert summary["trnfrn_rrc_active_range_ready"] is True


def test_v0464_bounded_radial_acceptance():
    summary = run_bounded_radial_shell_validation()
    assert summary["bounded_radial_shell_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "detail_and_final_output_writers"


def test_v0464_zone1_skips_step_and_preserves_order():
    summary = run_bounded_radial_shell_validation()
    assert summary["zone1_step_skip_ready"] is True
    assert summary["zone1_source_order"] == [
        "trnfrc",
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
        "heatt",
        "stpcut",
        "trnfrn",
    ]


def test_v0464_later_first_pass_executes_step():
    summary = run_bounded_radial_shell_validation()
    assert summary["later_first_pass_step_ready"] is True
    assert summary["later_zone_source_order"] == [
        "step",
        "trnfrc",
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
        "heatt",
        "stpcut",
        "trnfrn",
    ]


def test_v0464_repeated_pass_and_turbulent_branch():
    summary = run_bounded_radial_shell_validation()
    assert summary["reverse_pass_unsavd_executed_ready"] is True
    assert summary["reverse_pass_restore_hdu_order_ready"] is True
    assert summary["turbulent_gsmooth_executed_ready"] is True
    assert summary["turbulent_gsmooth_before_heatt_ready"] is True
    assert summary["turbulent_shared_array_ownership_ready"] is True
    assert summary["turbulent_source_order"] == [
        "trnfrc",
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
        "gsmooth",
        "heatt",
        "stpcut",
        "trnfrn",
    ]


def test_v0464_heatt_handler_and_no_outputs():
    summary = run_bounded_radial_shell_validation()
    assert summary["heatt_translated_in_radial_sequence_ready"] is True
    assert summary["output_writers_excluded_ready"] is True
    assert summary["shared_radial_array_ownership_ready"] is True


def test_v0464_step_preserves_overwritten_tst_semantics():
    epi = np.asarray([0.5, 1.0, 10.0, 100.0])
    opakc = np.asarray([1e-20, 1e-19, 2e-14, 5e-15])
    zrems = np.zeros((5, 4))
    zrems[0] = 1e-3
    result = step(
        1.0,
        0.5,
        epi,
        opakc,
        np.zeros((2, 4)),
        np.zeros((2, 1)),
        zrems,
        np.zeros((2, 4)),
        ncn2=4,
        radius_cm=2e19,
        column_limit_cm2=5e22,
        column_cm2=1e22,
        hydrogen_density_cm3=1e8,
        taumax=10.0,
        numrec0=10,
    )
    assert result.delr_cm == pytest.approx(2.5e13)
    assert result.selected_bin_one_based == 3


def test_v0464_trnfrc_preserves_caller_tails():
    epi = np.asarray([1.0, 10.0, 100.0, 1000.0, 10000.0, 20000.0])
    before = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 777.0])
    integral = np.asarray([11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 999.0])
    result = trnfrc(
        direction=1,
        radius_cm=1e19,
        column_limit_cm2=1e21,
        hydrogen_density_cm3=1e8,
        epi_eV=epi,
        zremsz=np.ones(6),
        dpthc=np.zeros((2, 6)),
        opakc=np.zeros(6),
        zrems=np.zeros((5, 6)),
        bremsa_before=before,
        bremsint_before=integral,
        ncn2=6,
    )
    assert result.bremsa_after[6] == 777.0
    assert result.bremsint_after[6] == 999.0
    assert result.bremsa_after[5] == 0.0
    assert result.bremsint_after[5] == 0.0


def test_v0464_stpcut_mutates_only_selected_direction_and_active_ranges():
    result = stpcut(
        direction=-1,
        epi_eV=np.arange(1.0, 6.0),
        opakc=np.ones(5),
        opakcont=2.0 * np.ones(5),
        oplin=np.asarray([3.0, 4.0, 99.0]),
        opakab=np.asarray([5.0, 88.0]),
        delr_cm=2.0,
        dpthc_before=np.zeros((2, 6)),
        dpthcont_before=np.zeros((2, 6)),
        tau0_before=np.zeros((2, 3)),
        tauc_before=np.zeros((2, 2)),
        ncn2=5,
        n_lines=2,
        n_continua=1,
    )
    assert np.all(result.dpthc_after[0, :5] == 2.0)
    assert np.all(result.dpthc_after[1, :] == 0.0)
    assert result.dpthc_after[0, 5] == 0.0
    assert np.array_equal(result.tau0_after[0], [6.0, 8.0, 0.0])
    assert np.array_equal(result.tauc_after[0], [10.0, 0.0])


def test_v0464_trnfrn_active_range_copy_only():
    z = np.arange(40.0).reshape(5, 8)
    l = np.arange(16.0).reshape(2, 8)
    r = np.arange(12.0).reshape(2, 6)
    result = trnfrn(
        zrems=z,
        zremso_before=np.full((5, 8), -1.0),
        elumab=r,
        elumabo_before=np.full((2, 6), -3.0),
        elum=l,
        elumo_before=np.full((2, 8), -2.0),
        ncn2=6,
        n_lines=4,
        n_continua=3,
    )
    assert np.array_equal(result.zremso_after[:, :6], z[:, :6])
    assert np.all(result.zremso_after[:, 6:] == -1.0)
    assert np.array_equal(result.elumo_after[:, :4], l[:, :4])
    assert np.all(result.elumo_after[:, 4:] == -2.0)
    assert np.array_equal(result.elumabo_after[:, :3], r[:, :3])
    assert np.all(result.elumabo_after[:, 3:] == -3.0)


def test_v0464_registration_includes_gsmooth_and_unsavd():
    driver = XSTARPythonDriver()
    register_bounded_radial_source_routines(driver)
    implemented = driver.implemented_source_routines()
    assert XSTARSourceRoutine.STEP in implemented
    assert XSTARSourceRoutine.TRNFRC in implemented
    assert XSTARSourceRoutine.HEATT in implemented
    assert XSTARSourceRoutine.STPCUT in implemented
    assert XSTARSourceRoutine.TRNFRN in implemented
    assert XSTARSourceRoutine.GSSMOOTH in implemented
    assert XSTARSourceRoutine.UNSAVD in implemented


def test_v0464_version():
    assert xa.__version__ == "0.4.68"
