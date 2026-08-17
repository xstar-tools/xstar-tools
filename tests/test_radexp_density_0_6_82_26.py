from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from xstar_tools.xstar.parameter_contract import coerce_and_validate_parameter
from xstar_tools.xstar.radial_control import (
    TabulatedRadialDensityError,
    TabulatedRadialDensityState,
    TabulatedRadialRadiusError,
    advance_tabulated_radial_density,
    initialize_tabulated_radial_density,
)
from xstar_tools.xstar.state import XSTARPythonState

ROOT = Path(__file__).resolve().parents[1]


def test_radexp_public_envelope_keeps_stock_analytic_range_and_source_sentinel():
    for value in (-3.0, -2.0, -0.5, 0.0, 1.0, 3.0):
        assert coerce_and_validate_parameter("radexp", value) == float(value)
    for value in (-3.0001, -50.0, -99.0):
        with pytest.raises(ValueError):
            coerce_and_validate_parameter("radexp", value)
    for value in (-99.0001, -100.0, -101.0):
        assert coerce_and_validate_parameter("radexp", value) == float(value)


def test_analytic_density_law_uses_post_geometry_radius_and_source_baseline():
    n0 = 1.0e8
    r0 = 3.0e11
    r1 = 4.5e11
    for radexp in (0.0, -0.5, 1.0, -2.0):
        got = n0 * (r1 / r0) ** radexp
        expected = {
            0.0: 1.0e8,
            -0.5: 1.0e8 / np.sqrt(1.5),
            1.0: 1.5e8,
            -2.0: 1.0e8 / (1.5 * 1.5),
        }[radexp]
        assert np.isclose(got, expected, rtol=0.0, atol=1.0e-8 * max(1.0, abs(expected)))

    driver = (ROOT / "src/xstar_tools/xstar/driver.py").read_text()
    radial = (ROOT / "src/xstar_tools/xstar/radial_transfer.py").read_text()
    assert 'result.control["xpx0"] = float(result.plasma.xpx)' in driver
    assert 'result.control["r0"] = float(result.transfer.radius)' in driver
    assert '(result.transfer.radius / r0) ** radexp' in driver
    assert 'state.control["xpx0"] = float(state.plasma.xpx)' in radial
    assert 'state.control["r0"] = float(state.transfer.radius)' in radial


def _state(radius: float = 1.0e11, density: float = 1.0e8) -> XSTARPythonState:
    state = XSTARPythonState()
    state.transfer.radius = radius
    state.plasma.xpx = density
    return state


def test_density_dat_valid_sequential_reads_and_post_update_column_semantics(tmp_path: Path):
    path = tmp_path / "density.dat"
    path.write_text("1.0D11 1.0D8\n1.5D11 8.0D7\n2.0D11 6.0D7\n")
    table = TabulatedRadialDensityState.from_file(path)
    state = _state()
    first = initialize_tabulated_radial_density(state, table)
    assert first.row_one_based == 1
    assert state.transfer.radius == 1.0e11
    assert state.plasma.xpx == 1.0e8

    second = advance_tabulated_radial_density(state)
    assert second.row_one_based == 2
    assert state.transfer.step_size == 5.0e10
    assert state.transfer.radius == 1.5e11
    assert state.plasma.xpx == 8.0e7
    # Literal xstar.f90 order is xcol = xcol + xpx * delr after the file read.
    expected_column_increment = state.plasma.xpx * state.transfer.step_size
    assert expected_column_increment == 4.0e18


def test_density_dat_missing_file_is_hard_error(tmp_path: Path):
    with pytest.raises(TabulatedRadialDensityError, match="missing density file"):
        TabulatedRadialDensityState.from_file(tmp_path / "density.dat")


def test_density_dat_negative_radius_increment_matches_source_radius_error():
    table = TabulatedRadialDensityState.from_rows([(2.0e11, 1.0e8), (1.9e11, 9.0e7)])
    state = _state()
    initialize_tabulated_radial_density(state, table)
    with pytest.raises(TabulatedRadialRadiusError, match="radius error"):
        advance_tabulated_radial_density(state)


def test_density_dat_equal_radius_is_allowed_and_eof_retains_last_values():
    table = TabulatedRadialDensityState.from_rows([(1.0e11, 1.0e8), (1.0e11, 7.0e7)])
    state = _state()
    initialize_tabulated_radial_density(state, table)
    second = advance_tabulated_radial_density(state)
    assert second.iostat == 0
    assert state.transfer.step_size == 0.0
    eof = advance_tabulated_radial_density(state)
    assert eof.iostat == -1
    assert eof.retained_previous_values is True
    assert eof.radius_cm == 1.0e11
    assert eof.density_cm3 == 7.0e7
    assert state.transfer.step_size == 0.0
    assert state.control["density_iostat"] == -1


def test_public_runner_and_native_controller_bind_density_dat_source_branch():
    runner = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text()
    cli = (ROOT / "src/xstar_tools/source_port_physical_runner_cli.py").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    runtime = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text()
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.hpp").read_text()

    assert 'float(normalized.get("radexp")) < -99.0' in runner
    assert 'density_path = source_input_dir / "density.dat"' in runner
    assert 'TabulatedRadialDensityState.from_file(density_path)' in runner
    assert '"--input-dir"' in cli

    assert 'params.radial_density_exponent < -99.0' in standalone
    assert '/ "density.dat"' in standalone
    assert 'throw std::runtime_error("radius error")' in standalone
    assert 'density_iostat_v068226 == 0' in standalone
    assert 'post_geometry_density_cm3_v068226' in standalone
    assert 'xstar_tools' not in header or 'std::string input_dir = ".";' in header
    assert 'p.input_dir=json_string(p.raw_json,"input_dir",".")' in runtime


def test_native_analytic_update_and_live_density_are_source_ordered():
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert 'source_initial_density_cm3_v068226 *' in standalone
    assert 'std::pow(post_geometry_radius_cm_v068226 / source_initial_radius_cm_v068226,' in standalone
    assert 'state.hydrogen_density_cm3 = post_geometry_density_cm3_v068226;' in standalone
    assert (
        'advance_stpcut_depths(\n                    data, boundary, source_geometry_segment_v068226, post_geometry_density_cm3_v068226);' in standalone
        or 'advance_stpcut_depths(\n                    data, boundary, source_geometry_segment_v068226, post_geometry_density_cm3_v068226,\n                    data.radial_direction_v068227);' in standalone
    )
    assert 'source_lcdd == 1\n        ? trial.hydrogen_density_cm3' in standalone
    # Preserve canonical source cap only; no radexp-specific safety cap is introduced.
    assert 'radexp step cap' not in standalone.lower()
    assert 'radexp zone cap' not in standalone.lower()
