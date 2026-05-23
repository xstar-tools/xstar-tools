from __future__ import annotations

import numpy as np

import xstar_atomic as xa
from xstar_atomic.source_port import (
    HeattResult,
    run_bounded_radial_shell_validation,
    run_direct_fortran_heatt_validation,
)
from xstar_atomic.source_port.heatt import _direct_heatt_python_result


def test_v0465_heatt_direct_original_fortran_gate():
    summary = run_direct_fortran_heatt_validation()
    assert summary["heatt_direct_original_fortran_reference_ready"] is True
    assert summary["heatt_continuum_direct_fortran_ready"] is True
    assert summary["heatt_line_direct_fortran_ready"] is True
    assert summary["heatt_rrc_direct_fortran_ready"] is True
    assert summary["heatt_leveltemp_direct_fortran_ready"] is True


def test_v0465_heatt_preserves_active_ranges_and_caller_tails():
    result = _direct_heatt_python_result()
    assert isinstance(result, HeattResult)
    assert np.array_equal(result.zrems_after[:, 4:], result.zrems_before[:, 4:])
    assert np.all(result.elum_after[:, 2:] == -900.0)
    assert np.all(result.elumab_after[:, 1:] == -600.0)


def test_v0465_heatt_preserves_stale_optp2_first_line_semantics():
    result = _direct_heatt_python_result()
    first = result.line_traces[0]
    second = result.line_traces[1]
    assert first.evaluated is True
    assert first.inherited_optp2 == 0.4
    assert first.inward_absorption_term > 0.0
    assert second.evaluated is False


def test_v0465_heatt_replays_leveltemp_partial_overwrite():
    result = _direct_heatt_python_result()
    assert result.leveltemp_workspace.energy(1) == 2.0
    assert result.leveltemp_workspace.require(1).ionization_potential_ev == 12.0
    assert result.leveltemp_workspace.energy(2) == 222.0
    assert result.leveltemp_workspace.require(2).ionization_potential_ev == 444.0


def test_v0465_uninitialized_compton_locals_are_not_invented():
    result = _direct_heatt_python_result()
    assert result.compton_coefficients_source_initialized is False


def test_v0465_radial_composition_uses_translated_heatt():
    summary = run_bounded_radial_shell_validation()
    assert summary["heatt_translated_in_radial_sequence_ready"] is True
    assert summary["bounded_radial_shell_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "detail_and_final_output_writers"


def test_v0465_version():
    assert xa.__version__ == "0.4.71"
