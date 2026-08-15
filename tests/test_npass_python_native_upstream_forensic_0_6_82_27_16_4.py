from __future__ import annotations
import importlib.util, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'tools/qualification/run_c5_python_native_fixed_state_upstream_forensic_0_6_82_27_16_4.py'
PROBE=ROOT/'tools/qualification/upstream_fixed_state_native_probe_0_6_82_27_16_4.cpp'
MAN=ROOT/'qualification/npass_0_6_82_27_16_4/diagnostic_upstream_fixed_state_scope_0_6_82_27_16_4.json'
CHECK=ROOT/'tools/qualification/check_npass_python_native_upstream_forensic_0_6_82_27_16_4.py'
def load_runner():
    spec=importlib.util.spec_from_file_location('upstream164',RUNNER); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def test_068227164_package_science_version_split():
    sys.path.insert(0,str(ROOT/'src'))
    import xstar_tools
    from xstar_tools.execution import package_version
    assert package_version() in ('0.6.82.27.16.4.1','0.6.82.27.16.5','0.6.82.28')
    assert xstar_tools.__package_version__ in ('0.6.82.27.16.4.1','0.6.82.27.16.5','0.6.82.28')
    assert xstar_tools.__version__=='0.6.48.12.3.45.3.3.8'

def test_068227164_scope_gate_zero_production_numerical_changes():
    data=json.loads(MAN.read_text()); assert data['baseline']=='0.6.82.27.16.3'; assert data['protected_cpp_baseline']=='0.6.82.27.13'; assert data['production_numerical_changed']==[]
    p=subprocess.run([sys.executable,str(CHECK)],cwd=ROOT,text=True,capture_output=True); assert p.returncode==0,p.stdout+p.stderr
    assert 'NPASS_PYTHON_NATIVE_UPSTREAM_068227164_RESULT=ACCEPT' in p.stdout

def test_068227164_captures_exact_dsec_call_start_state_and_final_carried_state():
    text=RUNNER.read_text(); assert 'zone1_dsec_capture_all_inputs' in text; assert 'runtime_before_final' in text; assert '_raw_from_snapshot' in text; assert '_raw_final' in text

def test_068227164_native_probe_uses_production_atdb_lowerer_and_bundle_context():
    text=PROBE.read_text(); assert 'xstar_atdb_runtime::lower_atdb_in_memory' in text; assert 'xstar_fixed_state_context_create_from_bundle_v1' in text
    assert 'xstar_fixed_state_write_last_diagnostics_v1' in text; assert 'XSTAR_FIXED_RUNTIME_STATE_DSEC_HMC_ONLY' in text

def test_068227164_runner_compares_records_seed_matrix_rhs_and_final():
    text=RUNNER.read_text();
    for needle in ['eval1_python_vs_native_records.csv','final_python_vs_native_records.csv','python_vs_native_solve_summary.csv','record_max_rel','m1["seed"]','m1["matrix"]','m1["rhs"]','m1["final"]']:
        assert needle in text

def test_068227164_localization_order_is_upstream_before_post_dsec():
    text=RUNNER.read_text();
    for needle in ['EVAL1_RATE_OR_RECORD_EVALUATION','EVAL1_COMPACT_SEED_MAPPING','EVAL1_MATRIX_ASSEMBLY','EVAL1_SOLVER_PATH','POST_DSEC_STATE_OR_RATE_PATH','NO_PY_NATIVE_UPSTREAM_DIVERGENCE']:
        assert needle in text

def test_068227164_no_native_result_is_applied_back_to_python():
    text=RUNNER.read_text(); assert 'production_numerical_source_changes":0' in text
    assert 'state.local_zone.calc_hmc_all =' not in text
    assert 'global_xilevg_by_index =' not in text[text.find('def _run_native_probe'):]


def test_0682271641_native_probe_enables_solve_system_capture_without_science_replacement():
    text=RUNNER.read_text()
    assert 'env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"' in text
    assert 'env["XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM"] = "1"' in text
    assert 'XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED' not in text[text.find('def _run_native_probe'):text.find('def main')]
    assert 'XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE' not in text[text.find('def _run_native_probe'):text.find('def main')]
