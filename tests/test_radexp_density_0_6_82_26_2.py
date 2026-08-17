from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    path = ROOT / "tools/qualification/run_c5_radexp_density_host_smoke_0_6_82_26_2.py"
    spec = importlib.util.spec_from_file_location("radexp0262_runner", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_terminal_pprint9_recomputes_xi_and_has_no_optional_override():
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    assert "terminal_source_logxi_v068226" not in cpp
    assert "pprint.f90 option 9 recomputes zeta" in cpp
    assert "terminal_posttransport_v0682261" not in step
    assert "pprint.f90 option 9 recomputes zeta from the live radius" in step


def test_terminal_variable_density_abundance_row_uses_post_geometry_density():
    fits = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    assert "published_density_v0682262" in fits
    assert "(final_physical_row && variable_density_v0682262)" in fits
    assert "? geometry_zone.density_cm3 : zone.density_cm3" in fits
    assert "row.density_cm3 = published_density_v0682262;" in fits
    assert "xlum / (published_density_v0682262 * r19 * r19)" in fits


def test_density_table_public_lines_use_retained_heatt_elum_not_table_radius_widths():
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    table_gate = 'if (public_parameter_real(product, "radexp", 0.0) < -99.0) {'
    start = cpp.index(table_gate)
    end = cpp.index("// Literal heatt/trnfrn ownership for lines is", start)
    branch = cpp[start:end]
    assert "final_writer_evaluation" in branch
    assert "ws.elum" in branch
    assert "native_line_plane(ws.elum, stride, plane, line_index)" in branch
    # The table branch must return before the analytic geometry reconstruction.
    assert "return out;" in branch
    assert "next_depth - current_depth" not in branch


def test_radexp_host_comparator_still_ignores_terminal_zero_abundance_row(monkeypatch):
    runner = _runner()
    rows = {
        "radius": [3.0, 6.0, 0.0],
        "delta_r": [0.0, 3.0, 0.0],
        "ion_parameter": [1.0, 0.3979400087, 0.0],
        "x_e": [1.0, 1.0, 0.0],
        "n_p": [8.0, 16.0, 0.0],
        "temperature": [100.0, 100.0, 0.0],
    }
    monkeypatch.setattr(runner, "abundance", lambda _path: rows)
    result = runner.compare_radial_trajectory(
        Path("candidate"), Path("reference"), {"kind": "analytic", "radexp": 1.0}
    )
    assert result["accept"] is True
    assert result["analytic_law_max_relative"] == 0.0
