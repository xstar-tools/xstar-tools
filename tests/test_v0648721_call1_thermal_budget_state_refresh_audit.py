from __future__ import annotations
import csv, json
from pathlib import Path

from xstar_tools.xstar.thermal_budget_state_refresh_audit import readiness
from xstar_tools.xstar.v0472_thermal_budget_state_refresh_capture import (
    BUDGET_NAME, STATE_NAME, TRACE_NAME, REPORT_NAME, verify,
)


def _write(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def test_v0648721_readiness_package_root() -> None:
    root=Path(__file__).resolve().parents[1]
    result=readiness(root)
    assert result['result']=='ACCEPT'
    assert result['original_capture']=='RUN_REQUIRED'


def test_v0648721_capture_verifier_accepts_complete_fixture(tmp_path: Path) -> None:
    budget_fields=['global_evaluation_ordinal','dsec_call_id','dsec_local_evaluation_index']
    _write(tmp_path/BUDGET_NAME,budget_fields,[{'global_evaluation_ordinal':i,'dsec_call_id':1,'dsec_local_evaluation_index':i} for i in range(1,8)])
    state_fields=['dsec_call_id','radiation_energy_sha256','bremsa_sha256','continuum_tau_in_sha256','continuum_tau_out_sha256','opakc_before_sha256','brcems_before_sha256','global_xilevg_sha256']
    _write(tmp_path/STATE_NAME,state_fields,[{'dsec_call_id':i,'radiation_energy_sha256':'e','bremsa_sha256':f'b{i}','continuum_tau_in_sha256':f't{i}','continuum_tau_out_sha256':f'o{i}','opakc_before_sha256':f'p{i}','brcems_before_sha256':f'r{i}','global_xilevg_sha256':f'x{i}'} for i in range(1,5)])
    trace_fields=['global_evaluation_ordinal','dsec_call_id','dsec_local_evaluation_index']
    _write(tmp_path/TRACE_NAME,trace_fields,[{'global_evaluation_ordinal':i,'dsec_call_id':1 if i<=21 else 2,'dsec_local_evaluation_index':i} for i in range(1,58)])
    (tmp_path/REPORT_NAME).write_text(json.dumps({'actual_v0472_runtime_capture':True})+'\n')
    result=verify(tmp_path)
    assert result['result']=='ACCEPT'
    assert 'bremsa' in result['between_call_changed_workspaces']


def test_v0648721_probe_source_compiles() -> None:
    import xstar_tools.xstar.v0472_thermal_budget_state_refresh_capture as mod
    compile(mod._PROBE, 'v048721_probe_runtime.py', 'exec')
    compile(mod._DRIVER, 'driver.py', 'exec')


def test_v06487214_probe_uses_callbacks_without_snapshot_retention() -> None:
    import xstar_tools.xstar.v0472_thermal_budget_state_refresh_capture as mod
    assert 'self.capture_all_input_snapshots = False' in mod._PROBE
    assert 'self.capture_input_snapshot_indices = ()' in mod._PROBE
    assert 'def capture_pre' in mod._PROBE
    assert 'def capture_progress' in mod._PROBE
    assert 'self.pre_evaluation_callback = capture_pre' in mod._PROBE
    assert 'self.progress_callback = capture_progress' in mod._PROBE
    assert 'def streaming_calc_hmc_all' not in mod._PROBE
    assert 'dsec_mod.calc_hmc_all =' not in mod._PROBE


def test_v06487214_probe_preserves_production_result_history_policy() -> None:
    import xstar_tools.xstar.v0472_thermal_budget_state_refresh_capture as mod
    assert 'self.retain_fixed_state_results = False' not in mod._PROBE
    assert 'self.retain_fixed_state_results = True' not in mod._PROBE
    assert 'retain_fixed_state_results", True' in mod._PROBE
    assert 'v0487214_capture_bypass' in mod._PROBE
    assert 'active_result' not in mod._PROBE


def test_v06487214_probe_isolates_cyclic_gc_and_localizes_crashes() -> None:
    import xstar_tools.xstar.v0472_thermal_budget_state_refresh_capture as mod
    source = Path(mod.__file__).read_text()
    assert 'gc.disable()' in mod._PROBE
    assert 'cyclic_gc_disabled' in mod._PROBE
    assert 'PYTHONFAULTHANDLER' in source
    assert 'PYTHONUNBUFFERED' in source
    assert 'v0487214_capture_begin' in mod._PROBE
    assert 'v0487214_capture_end' in mod._PROBE


def test_v06487214_probe_bypasses_retained_evaluators(tmp_path: Path) -> None:
    import sys
    import types
    import xstar_tools.xstar as xstar_pkg
    import xstar_tools.xstar.v0472_thermal_budget_state_refresh_capture as capture_mod

    config = tmp_path / "probe_config.json"
    config.write_text(json.dumps({"output_dir": str(tmp_path / "out")}) + "\n")
    runtime_path = tmp_path / "v048721_probe_runtime.py"
    runtime_path.write_text(capture_mod._PROBE)

    sentinel = object()

    class FakeEvaluator:
        retain_fixed_state_results = True

        def __call__(self, state):
            assert self.retain_fixed_state_results is True
            return sentinel

    fake_dsec = types.ModuleType("xstar_tools.xstar.dsec")
    fake_dsec.CalcHMCAllDsecEvaluator = FakeEvaluator
    previous_module = sys.modules.get("xstar_tools.xstar.dsec")
    previous_attr = getattr(xstar_pkg, "dsec", None)
    sys.modules["xstar_tools.xstar.dsec"] = fake_dsec
    setattr(xstar_pkg, "dsec", fake_dsec)
    try:
        namespace = {"__file__": str(runtime_path), "__name__": "v048721_probe_runtime_test"}
        exec(compile(capture_mod._PROBE, str(runtime_path), "exec"), namespace)
        namespace["install"]()
        evaluator = FakeEvaluator()
        result = evaluator(object())
        assert result is sentinel
        assert namespace["_STATE"]["bypassed_retained_evaluators"] == 1
        assert namespace["_STATE"]["global_eval"] == 0
        assert namespace["_STATE"]["call_counter"] == 0
    finally:
        if previous_module is None:
            sys.modules.pop("xstar_tools.xstar.dsec", None)
        else:
            sys.modules["xstar_tools.xstar.dsec"] = previous_module
        if previous_attr is None:
            delattr(xstar_pkg, "dsec")
        else:
            setattr(xstar_pkg, "dsec", previous_attr)
