from __future__ import annotations
import importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'tools/qualification/run_output_control_integrated_cpp_host_smoke_0_6_82_29_3_8.py'
SCOPE=ROOT/'qualification/output_control_integrated_cpp_0_6_82_29_3_8/output_control_integrated_cpp_scope_0_6_82_29_3_8.json'

def load_runner():
    spec=importlib.util.spec_from_file_location('oc38_test_runner',RUNNER); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_version_and_zero_production_delta():
    data=json.loads(SCOPE.read_text())
    assert data['milestone']=='0.6.82.29.3.8'
    assert data['baseline']=='0.6.82.29.3.7.1'
    assert len(data['production_hashes'])==137
    assert not [r for r in data['production_hashes'] if r['changed']]

def test_integrated_matrix_cases_are_exactly_baseline_plus_lprint_2_to_6():
    mod=load_runner()
    assert mod.CASES==('baseline','lprint_2','lprint_3','lprint_4','lprint_5','lprint_6')
    assert mod.MATRIX_CASES==('lprint_2','lprint_3','lprint_4','lprint_5','lprint_6')

def test_verbose_option_thresholds():
    mod=load_runner()
    assert mod.selected_options(2)==(14,21,7,10)
    assert mod.selected_options(3)==(14,21,7,10,4,6)
    assert mod.selected_options(4)==(14,21,7,10,4,6,18,29,30)
    assert mod.selected_options(5)==mod.selected_options(4)
    assert mod.selected_options(6)==mod.selected_options(4)

def test_canonical_row_inventory_contract():
    mod=load_runner()
    assert mod.EXPECTED_ROWS=={14:1140,21:238,7:250,10:15,4:998,6:999,18:1140,29:1954,30:4}

def test_science_invariance_is_exact_not_tolerance_based():
    text=RUNNER.read_text()
    assert 'ok = rel == 0.0' in text
    assert 'science-invariance cpp=' in text
    assert 'OUTPUT_CONTROL_06822938_CPP_RESULT' in text

def test_integrated_gate_reuses_all_host_closed_exact_parsers():
    text=RUNNER.read_text()
    for token in (
        'run_output_control_option4_host_smoke_0_6_82_29_3_3_8_4.py',
        'run_output_control_option6_host_smoke_0_6_82_29_3_2.py',
        'run_output_control_option10_host_smoke_0_6_82_29_3_4.py',
        'run_output_control_option18_host_smoke_0_6_82_29_3_5.py',
        'run_output_control_option29_host_smoke_0_6_82_29_3_6.py',
        'run_output_control_option30_host_smoke_0_6_82_29_3_7_1.py',
    ):
        assert token in text

def test_science_and_abi_freeze():
    data=json.loads(SCOPE.read_text())
    assert data['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert (data['c_api_abi'],data['production_zone_abi'],data['fixed_state_abi'])==(60487,6048110,60488)
