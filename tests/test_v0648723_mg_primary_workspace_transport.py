from pathlib import Path
import json
import numpy as np
from xstar_tools.xstar.mg_primary_workspace_transport_audit import prepare, ARRAYS

ROOT=Path(__file__).resolve().parents[1]

def test_fixed_state_runtime_contract_and_mg_correction_present():
    header=(ROOT/'src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h').read_text()
    engine=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    standalone=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    for field in ('global_xilevg','global_bilevg','global_rnisg','mg_primary_heating_override'):
        assert field in header
    assert 'XSTAR_QUALIFICATION_MG_PRIMARY_THERMAL_CORRECTION' in engine
    assert 'canonical_reduction.tagged.total.abundance_weighted(element.abundance)' in engine
    assert 'element_heating *= element.abundance' not in engine
    assert '--call-start-workspace-dir' in standalone
    assert '--mg-primary-budget-csv' in standalone

def test_lowerer_serializes_global_level_index():
    text=(ROOT/'src/xstar_tools/xstar/native_fixed_program.py').read_text()
    assert 'global_level_index_by_key' in text
    assert '"global_level_index"' in text

def test_payload_prepare_writes_four_call_binary_contract(tmp_path):
    capture=tmp_path/'capture'/'original_payload_capture'/'call_start_payloads'
    capture.mkdir(parents=True)
    for call in range(1,5):
        np.savez(capture/f'call_{call}.npz', **{name:np.arange(call+1,dtype=np.float64) for name in ARRAYS})
    budget=tmp_path/'capture'/'original_payload_capture'/'v0472_call1_thermal_budget.csv'
    budget.write_text('dsec_call_id,dsec_local_evaluation_index,mg_heating,mg_cooling,mg_heating2,mg_cooling2\n1,1,1,2,3,4\n')
    result=prepare(tmp_path/'capture',tmp_path/'out')
    assert result['result']=='ACCEPT'
    assert result['payload_calls']==4
    for call in range(1,5):
        for name in ARRAYS:
            assert (tmp_path/'out'/'call_start_workspace_bin'/f'call_{call}_{name}.bin').is_file()
