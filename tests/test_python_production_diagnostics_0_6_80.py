from __future__ import annotations

from dataclasses import dataclass
import ast
from pathlib import Path
import sys
import types
from typing import Any

from xstar_tools import execution

ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_RUNNER = ROOT / "src/xstar_tools/xstar/physical_runner.py"

DEBUG_KEYS = {
    "reference_trace_schema_version",
    "diagnostics_mode",
    "high_volume_diagnostics_enabled",
    "diagnostic_files_written",
    "element_solver_diagnostic_gating",
    "performance_profile_summary",
    "dsec_residual_trajectory_summary",
    "dsec_terminal_summary",
    "dsec_trace_capture_errors",
    "mg_matrix_ucalc_forensic_samples",
    "mg_type49_shadow_parity_summary",
    "mg_type53_shadow_parity_summary",
    "mg_matrix_assembly_dataflow_summary",
    "mg_rate_payload_dataflow_summary",
    "runtime_phase_wall_timing",
    "output_writer_timing_breakdown",
}


@dataclass
class _FakeRun:
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": True,
            "provenance": dict(self.provenance),
            "warnings": [],
            "products": {},
            "completed_passes": 1,
            "completed_zones": 1,
        }


def _fake_provenance() -> dict[str, Any]:
    return {
        "runner": "run_xstar_from_parameters",
        "source_faithful_calculation_path": True,
        "strict_ten_product_contract": True,
        "xstar_outputs_used_as_python_inputs": False,
        "active_subset_enabled": True,
        "backend_selection": {"global_backend": "python"},
        "solver_backend": {"requested": "python", "active": "python"},
        "rates_backend": {"requested": "python", "active": "python"},
        "matrix_backend": {"requested": "python", "active": "python"},
        "emissivity_backend": {"requested": "python", "active": "python"},
        "opacity_backend": {"requested": "python", "active": "python"},
        "thermal_backend": {"requested": "python", "active": "python"},
        "engine_backend": {"requested": "python", "active": "python"},
        "atdb_path": "/tmp/atdb.fits",
        "pointer_cache_status": "not_used",
        "metadata_cache_status": "not_used",
        "diagnostics_mode": "full",
        "high_volume_diagnostics_enabled": True,
        "diagnostic_files_written": True,
        "dsec_residual_trajectory_summary": [{"debug": 1}],
        "mg_matrix_ucalc_forensic_samples": [{"debug": 2}],
        "runtime_phase_wall_timing": {"debug": 3},
    }


def _install_fake_physical_runner(monkeypatch, captured: dict[str, Any]) -> None:
    module = types.ModuleType("xstar_tools.xstar.physical_runner")

    def fake_run(source, **kwargs):
        captured.update(kwargs)
        return _FakeRun(_fake_provenance())

    module.run_xstar_python_script = fake_run
    module.run_xstar_python_command = fake_run
    monkeypatch.setitem(sys.modules, "xstar_tools.xstar.physical_runner", module)


def test_public_provenance_filter_removes_debug_attribution():
    public = execution._public_python_provenance(_fake_provenance())
    assert public["runner"] == "run_xstar_from_parameters"
    assert public["strict_ten_product_contract"] is True
    assert public["backend_selection"]["global_backend"] == "python"
    assert not (DEBUG_KEYS & set(public))


def test_public_python_run_suppresses_files_and_debug_provenance(monkeypatch, tmp_path: Path):
    captured: dict[str, Any] = {}
    _install_fake_physical_runner(monkeypatch, captured)
    atdb = tmp_path / "atdb.fits"; atdb.write_bytes(b"atdb")
    coheat = tmp_path / "coheat.dat"; coheat.write_text("coheat\n", encoding="utf-8")
    script = tmp_path / "run_xstar.sh"; script.write_text("#!/bin/sh\n", encoding="utf-8")

    result = execution._run_xstar_legacy(
        mode="pure-python", run_script=script, atdb_path=atdb, coheat_path=coheat,
        output_dir=tmp_path / "out",
    )
    assert captured["write_diagnostic_files"] is False
    assert not (DEBUG_KEYS & set(result.summary["provenance"]))
    assert result.summary["provenance"]["execution"]["actual_mode"] == "pure-python"


def test_public_python_debug_opt_in_restores_full_provenance(monkeypatch, tmp_path: Path):
    captured: dict[str, Any] = {}
    _install_fake_physical_runner(monkeypatch, captured)
    atdb = tmp_path / "atdb.fits"; atdb.write_bytes(b"atdb")
    coheat = tmp_path / "coheat.dat"; coheat.write_text("coheat\n", encoding="utf-8")
    script = tmp_path / "run_xstar.sh"; script.write_text("#!/bin/sh\n", encoding="utf-8")

    result = execution._run_xstar_legacy(
        mode="zone-python", run_script=script, atdb_path=atdb, coheat_path=coheat,
        output_dir=tmp_path / "out", write_diagnostic_files=True,
        include_debug_provenance=True,
    )
    assert captured["write_diagnostic_files"] is True
    assert "dsec_residual_trajectory_summary" in result.summary["provenance"]
    assert result.summary["provenance"]["execution"]["actual_mode"] == "zone-python"


def test_internal_diagnostics_mode_stays_full_and_output_switch_is_separate():
    tree = ast.parse(PHYSICAL_RUNNER.read_text(encoding="utf-8"))
    target = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_xstar_from_parameters")
    defaults = target.args.defaults
    names = [a.arg for a in target.args.args] + [a.arg for a in target.args.kwonlyargs]
    kwdefaults = dict(zip([a.arg for a in target.args.kwonlyargs], target.args.kw_defaults))
    assert isinstance(kwdefaults["diagnostics_mode"], ast.Constant) and kwdefaults["diagnostics_mode"].value == "full"
    assert isinstance(kwdefaults["write_diagnostic_files"], ast.Constant) and kwdefaults["write_diagnostic_files"].value is True


def test_public_diagnostic_sidecar_capture_is_gated_only_by_output_switch():
    text = PHYSICAL_RUNNER.read_text(encoding="utf-8")
    assert 'emit_high_volume_diagnostics = bool(high_volume_diagnostics and write_diagnostic_files)' in text
    assert 'state.control["radial_spectrum_parity_diagnostic_enabled"] = emit_high_volume_diagnostics' in text
    assert 'state.control["continuum_phase_snapshot_enabled"] = emit_high_volume_diagnostics' in text
    assert 'state.control["ucalc_continuum_side_effect_diagnostics_enabled"] = emit_high_volume_diagnostics' in text
    assert 'diagnostics_mode: str = "full"' in text
