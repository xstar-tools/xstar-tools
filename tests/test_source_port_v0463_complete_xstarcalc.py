from __future__ import annotations

import numpy as np

import xstar_atomic as xa
from xstar_atomic.source_port import (
    CalcEmisabWorkspace,
    XSTARPythonDriver,
    XSTARSourceRoutine,
    register_complete_local_xstarcalc_source_routines,
    run_complete_local_xstarcalc_validation,
)


def test_v0463_complete_local_xstarcalc_acceptance():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["complete_local_xstarcalc_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "radial_transfer_and_output"


def test_v0463_literal_source_order():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["source_order"] == [
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
    ]
    assert summary["literal_source_order_ready"] is True


def test_v0463_lpri_and_dsec_control_semantics():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["lpri_save_zero_restore_ready"] is True
    assert summary["bremsmap_before_dsec_ready"] is True
    assert summary["nlimdt_zero_dsec_skip_ready"] is True


def test_v0463_final_hmc_and_emissivity_order():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["final_calc_hmc_all_after_dsec_ready"] is True
    assert summary["calc_emisab_before_calc_emis_ready"] is True


def test_v0463_shared_workspace_and_continuum_capacity():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["shared_emissivity_workspace_ready"] is True
    assert summary["reduced_to_full_continuum_capacity_ready"] is True
    assert summary["caller_owned_array_continuity_ready"] is True


def test_v0463_calc_emisab_workspace_accepts_full_grid_capacity():
    workspace = CalcEmisabWorkspace.allocate(
        n_lines=1,
        n_continua=1,
        n_energy=5,
    )
    workspace.validate(n_lines=1, n_continua=1, n_energy=4)
    assert workspace.opakc.shape == (5,)
    assert workspace.rccemis.shape == (2, 5)


def test_v0463_precomputed_ranking_and_nry():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["precomputed_absorption_feature_ranking_ready"] is True
    assert summary["final_nry_assignment_ready"] is True
    assert summary["nry"] == summary["nry_expected"]


def test_v0463_final_state_flags():
    summary = run_complete_local_xstarcalc_validation()
    assert summary["fixed_state_ready"] is True
    assert summary["thermal_iteration_ready"] is True
    assert summary["emissivity_ready"] is True


def test_v0463_driver_registration():
    driver = XSTARPythonDriver()
    register_complete_local_xstarcalc_source_routines(driver)
    assert driver.implemented_source_routines() == [
        XSTARSourceRoutine.BREMSMAP,
        XSTARSourceRoutine.DSEC,
        XSTARSourceRoutine.CALC_HMC_ALL,
        XSTARSourceRoutine.CALC_EMISAB_ALL,
        XSTARSourceRoutine.CALC_EMIS_ALL,
    ]


def test_v0463_version():
    assert xa.__version__ == "0.4.76"
