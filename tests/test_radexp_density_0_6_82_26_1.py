from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    path = ROOT / "tools/qualification/run_c5_radexp_density_host_smoke_0_6_82_26_1.py"
    spec = importlib.util.spec_from_file_location("radexp0261_runner", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_analytic_law_check_ignores_terminal_zero_row(monkeypatch):
    runner = _load_runner()
    rows = {
        "radius": [3.0, 6.0, 0.0],
        "delta_r": [0.0, 3.0, 0.0],
        "ion_parameter": [1.0, 1.0, 0.0],
        "x_e": [1.0, 1.0, 0.0],
        "n_p": [8.0, 2.0, 0.0],
        "temperature": [100.0, 100.0, 0.0],
    }
    monkeypatch.setattr(runner, "abundance", lambda _path: rows)
    result = runner.compare_radial_trajectory(Path("candidate"), Path("reference"),
                                               {"kind": "analytic", "radexp": -2.0})
    assert result["accept"] is True
    assert result["analytic_law_max_relative"] == 0.0


def test_native_publication_preserves_variable_density_state_and_xcol():
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert 'lcpres == 0 && radial_density_exponent_v0682261 != 0.0' in cpp
    assert '} else if (!variable_density_v0682261) {' in cpp
    assert 'if (variable_density_v0682261) {' in cpp
    assert 'Preserve it verbatim' in cpp
    assert '!constant_pressure_v068225 && !variable_density_v0682261' in cpp
    assert '(generic_all_element_publication_v0648123 || constant_pressure_v068225 ||\n             variable_density_v0682261)' in cpp


def test_live_step_uses_source_radius_and_retained_column_for_variable_density():
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'const double radius = source_initial_radius_cm + source_depth_cm;' in cpp
    assert '(params.pressure_mode == 1 || variable_density_v0682261)' in cpp
    assert 'source_initial_radius_cm_v068226,\n                    source_boundary_depth_cm.back()' in cpp
    if 'version = "0.6.82.26.1"' in pyproject:
        assert 'terminal_source_logxi_v068226);' in cpp
        assert 'terminal_posttransport_v0682261' in step
        assert 'if (!terminal_posttransport_v0682261 &&' in step
    else:
        # 0.6.82.26.2 corrected the .26.1 stale-terminal-xi assumption:
        # canonical pprint(9) recomputes zeta from the live radius/density.
        assert 'terminal_source_logxi_v068226' not in cpp
        assert 'terminal_posttransport_v0682261' not in step
        assert 'pprint.f90 option 9 recomputes zeta' in cpp
        assert 'pprint.f90 option 9 recomputes zeta from the live radius' in step


def test_density_dat_is_allowed_as_source_input_and_runner_separates_io():
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    runner = (ROOT / "tools/qualification/run_c5_radexp_density_host_smoke_0_6_82_26_1.py").read_text()
    assert 'allowed.insert("density.dat");' in cpp
    assert 'json_number_value(publication_json_v0682261, "radexp", 0.0) < -99.0' in cpp
    assert 'input_dir = root / "inputs" / name' in runner
    assert '"--input-dir", str(input_dir), "--output", str(out)' in runner
    assert '"--input-dir", str(input_dir), "--output-dir", str(out)' in runner
