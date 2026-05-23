from __future__ import annotations

import numpy as np

import xstar_atomic as xa
from xstar_atomic.source_port import (
    SavedRadialStateStore,
    XSTARPythonDriver,
    XSTARSourceRoutine,
    capture_saved_shell_snapshot_from_state,
    register_bounded_radial_source_routines,
    run_bounded_radial_multipass,
    run_bounded_radial_shell_validation,
    run_direct_fortran_unsavd_validation,
)
from xstar_atomic.source_port.radial_transfer import _build_radial_validation_state


def test_v0467_unsavd_direct_original_fortran_gate():
    summary = run_direct_fortran_unsavd_validation()
    assert summary["unsavd_direct_original_fortran_reference_ready"] is True
    assert summary["unsavd_scalar_direct_fortran_ready"] is True
    assert summary["unsavd_direction_minus_optical_depth_ready"] is True
    assert summary["unsavd_direction_plus_optical_depth_ready"] is True
    assert summary["unsavd_zrems_local_temporary_semantics_ready"] is True


def test_v0467_saved_snapshot_uses_real4_persistence():
    state = _build_radial_validation_state(zone_index=1)
    state.transfer.pass_index = 1
    state.transfer.zone_index = 1
    state.transfer.radius = 1.2345678901234567e19
    state.plasma.temperature = 1234567.890123
    state.control["radial_transfer_workspace"].opakc[0] = 1.234567890123e-17
    state.local_zone.source_arrays["xilevg"] = np.asarray([0.1, 0.2])
    state.local_zone.source_arrays["rnisg"] = np.asarray([0.3, 0.4])
    snapshot = capture_saved_shell_snapshot_from_state(state)
    assert snapshot.radius == float(np.float32(1.2345678901234567e19))
    assert snapshot.temperature == float(np.float32(1234567.890123))
    assert snapshot.opakc[0] == float(np.float32(1.234567890123e-17))


def test_v0467_hdu_insertion_and_shift_order_matches_savd():
    state = _build_radial_validation_state(zone_index=1)
    result = run_bounded_radial_multipass(
        state, first_pass_shell_count=2, pass_count=3
    )
    first = result.saved_state.require_pass(1)
    assert first.populated_hdus() == (3, 4, 5)
    assert first.snapshot_at_hdu(3).zone_index == 1
    assert first.snapshot_at_hdu(4).terminal_record is True
    assert first.snapshot_at_hdu(5).zone_index == 2
    assert result.pass_results[1].saved_hdus == (3, 4, 5, 6)
    assert result.pass_results[1].terminal_saved_hdu == 5


def test_v0467_repeated_passes_restore_source_hdus_before_trnfrc():
    state = _build_radial_validation_state(zone_index=1)
    result = run_bounded_radial_multipass(
        state, first_pass_shell_count=2, pass_count=3
    )
    assert isinstance(result.saved_state, SavedRadialStateStore)
    assert tuple(p.direction for p in result.pass_results) == (-1, 1, -1)
    assert result.pass_results[1].restored_hdus == (5, 4, 3)
    assert result.pass_results[2].restored_hdus == (5, 4, 3)
    for radial_pass in result.pass_results[1:]:
        for shell in radial_pass.shell_results:
            assert shell.source_order[0] == "unsavd"
            assert shell.source_order.index("unsavd") < shell.source_order.index("trnfrc")


def test_v0467_direction_controls_dsec_on_repeated_passes():
    state = _build_radial_validation_state(zone_index=1)
    result = run_bounded_radial_multipass(
        state, first_pass_shell_count=2, pass_count=3
    )
    assert all("dsec" not in shell.source_order for shell in result.pass_results[1].shell_results)
    assert all("dsec" in shell.source_order for shell in result.pass_results[2].shell_results)


def test_v0467_validation_closes_unsavd_without_outputs():
    summary = run_bounded_radial_shell_validation()
    assert summary["caller_owned_saved_shell_state_ready"] is True
    assert summary["saved_state_real4_rounding_ready"] is True
    assert summary["saved_hdu_insertion_shift_order_ready"] is True
    assert summary["reverse_pass_unsavd_executed_ready"] is True
    assert summary["repeated_radial_pass_state_ready"] is True
    assert summary["output_writers_excluded_ready"] is True
    assert summary["bounded_radial_shell_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "detail_and_final_output_writers"


def test_v0467_registration_and_version():
    driver = XSTARPythonDriver()
    register_bounded_radial_source_routines(driver)
    assert XSTARSourceRoutine.UNSAVD in driver.implemented_source_routines()
    assert xa.__version__ == "0.4.73"
