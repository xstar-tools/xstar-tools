from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import (
    TabulatedRadialDensityState,
    TabulatedRadialRadiusError,
    advance_tabulated_radial_density,
    build_radial_pass_convergence_contract,
    default_port_ledger,
    initialize_tabulated_radial_density,
    run_bounded_radial_multipass,
    run_bounded_radial_shell_validation,
    run_direct_fortran_tabulated_density_validation,
)
from xstar_atomic.source_port.radial_transfer import _build_radial_validation_state


def test_v0468_tabulated_density_direct_source_fragment_gate():
    summary = run_direct_fortran_tabulated_density_validation()
    assert summary["tabulated_density_initial_direct_fortran_ready"] is True
    assert summary["tabulated_density_updates_direct_fortran_ready"] is True
    assert summary["tabulated_density_eof_retains_values_ready"] is True
    assert summary["tabulated_density_direct_original_fortran_reference_ready"] is True


def test_v0468_density_file_parser_and_eof_retention(tmp_path: Path):
    path = tmp_path / "density.dat"
    path.write_text("1.0D18 1.25D8\n1.4d18 2.5d8\n", encoding="utf-8")
    table = TabulatedRadialDensityState.from_file(path)
    state = _build_radial_validation_state(zone_index=1)
    initial = initialize_tabulated_radial_density(state, table)
    assert initial.row_one_based == 1
    second = advance_tabulated_radial_density(state)
    assert second.row_one_based == 2
    assert state.transfer.step_size == pytest.approx(4.0e17)
    eof = advance_tabulated_radial_density(state)
    assert eof.iostat == -1
    assert eof.retained_previous_values is True
    assert state.transfer.step_size == 0.0
    assert state.transfer.radius == second.radius_cm
    assert state.plasma.xpx == second.density_cm3


def test_v0468_descending_tabulated_radius_matches_source_stop():
    table = TabulatedRadialDensityState.from_rows(
        [(2.0e18, 1.0e8), (1.5e18, 2.0e8)]
    )
    state = _build_radial_validation_state(zone_index=1)
    initialize_tabulated_radial_density(state, table)
    with pytest.raises(TabulatedRadialRadiusError, match="radius error"):
        advance_tabulated_radial_density(state)


def test_v0468_integrated_tabulated_first_pass_uses_source_iostat_loop():
    state = _build_radial_validation_state(zone_index=1)
    state.control.update(
        {
            "radexp": -100.0,
            "xpxcol": 1.0e40,
            "xeemin": -1.0,
            "numrec": 20,
            "tabulated_density_state": TabulatedRadialDensityState.from_rows(
                [(1.0e18, 1.25e8), (1.4e18, 2.5e8), (2.1e18, 4.0e8)]
            ),
        }
    )
    result = run_bounded_radial_multipass(
        state, first_pass_shell_count=None, pass_count=1
    )
    radial_pass = result.pass_results[0]
    assert len(radial_pass.shell_results) == 3
    assert radial_pass.termination_reason == "density_iostat_nonzero"
    assert radial_pass.density_iostat == -1
    assert radial_pass.numrec == 4
    assert state.transfer.radius == pytest.approx(2.1e18)
    assert state.plasma.xpx == pytest.approx(4.0e8)
    assert state.transfer.radial_depth == pytest.approx(1.1e18)
    assert state.transfer.column == pytest.approx(3.8e26)
    reads = state.transfer.provenance["tabulated_density_reads"]
    assert [row["row_one_based"] for row in reads] == [2, 3, None]
    assert np.allclose([row["delr_cm"] for row in reads], [4e17, 7e17, 0.0])


def test_v0468_pass_convergence_is_fixed_count_not_adaptive():
    normal = build_radial_pass_convergence_contract(numrec=20, npass=4)
    assert normal.effective_passes == 4
    assert normal.directions == (-1, 1, -1, 1)
    assert normal.adaptive_convergence_used is False
    assert normal.convergence_kind == "fixed_requested_pass_count"
    forced = build_radial_pass_convergence_contract(numrec=0, npass=7)
    assert forced.effective_passes == 1
    assert forced.directions == (-1,)
    state = _build_radial_validation_state(zone_index=1)
    state.control["numrec"] = 0
    state.local_zone.source_arrays["xilevg"] = np.zeros(2)
    state.local_zone.source_arrays["rnisg"] = np.zeros(2)
    run = run_bounded_radial_multipass(
        state, first_pass_shell_count=1, pass_count=7
    )
    assert len(run.pass_results) == 1
    assert run.pass_results[0].direction == -1
    assert run.pass_results[0].shell_results == ()
    assert run.pass_results[0].termination_reason == "numrec_nonpositive"
    assert run.pass_results[0].numrec == 1


def test_v0468_acceptance_closes_radial_control_without_outputs():
    summary = run_bounded_radial_shell_validation()
    assert summary["tabulated_density_direct_original_fortran_reference_ready"] is True
    assert summary["tabulated_density_initial_source_read_ready"] is True
    assert summary["tabulated_density_post_shell_update_ready"] is True
    assert summary["tabulated_density_eof_loop_termination_ready"] is True
    assert summary["fixed_pass_count_convergence_contract_ready"] is True
    assert summary["numrec_nonpositive_forces_one_pass_ready"] is True
    assert summary["adaptive_pass_convergence_not_invented_ready"] is True
    assert summary["output_writers_excluded_ready"] is True
    assert summary["bounded_radial_shell_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "detail_and_final_output_writers"


def test_v0468_ledger_exports_and_version():
    assert xa.__version__ == "0.4.70"
    ledger = default_port_ledger()
    entry = next(
        item for item in ledger.entries
        if item.routine == "tabulated_density_and_pass_control"
    )
    assert entry.status.value == "validated"
    assert "pprint" in ledger.entries[-1].limitations.lower()
