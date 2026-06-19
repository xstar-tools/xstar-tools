from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import xstar_tools
ROOT=Path(__file__).resolve().parents[1]

def test_release_version():
    assert xstar_tools.__version__ == '0.6.48.7.46.17.2.1'

def test_cpp_uses_qualification_scoped_real_exponent_pow():
    s=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_FREEF_REAL_EXPONENT_POW' in s
    assert 'std::pow(epi[k], 3.0)' in s
    assert '(epi[k] * epi[k] * epi[k])' in s

def test_offline_production_replay_is_exact():
    r=json.loads((ROOT/'v048746172_offline_freef_pow_replay_report.json').read_text())
    assert r['chain_bit_exact']==48
    assert r['chain_max_ulp']==2
    assert r['pow_bit_exact']==61
    assert r['pow_max_ulp']==0
    assert r['predicted_native_computed_thermal_values_exact']==1029
    assert r['corrected_sequences']==[5,13,15,19,20,23,25,27,32,39,45,46,56]

def test_v46171_causal_baseline_gate(tmp_path:Path):
    source=tmp_path/'checker.json'; output=tmp_path/'out.json'
    source.write_text((Path('/mnt/data/v46171_review/result/v048746171_continuum_grid_binary64_semantics_hotfix/v048746171_checker_report.json').read_text()) if Path('/mnt/data/v46171_review/result/v048746171_continuum_grid_binary64_semantics_hotfix/v048746171_checker_report.json').exists() else json.dumps({
      'release':'0.6.48.7.46.17.1','result':'REJECT','scientific_result':'REJECT','native_computed_values_exact':1016,
      'gates':{
       'ALL_61_CONTINUUM_WORKSPACES_RECONSTRUCTED':'ACCEPT','CLBREMS_BIT_EXACT_61':'ACCEPT','CLCOMP_BIT_EXACT_61':'ACCEPT','CMP1_BIT_EXACT_61':'ACCEPT','CMP2_BIT_EXACT_61':'ACCEPT','CONTINUUM_BREMSAM_VALUES_EXACT_60939':'ACCEPT','CONTINUUM_BREMSMAP_INDICES_EXACT_60939':'ACCEPT','CONTINUUM_EPIM_BINARY64_VALUES_EXACT_60939':'ACCEPT','CONTINUUM_EPIM_CANONICAL_BINARY64_VALUES_EXACT_999':'ACCEPT','CONTINUUM_TOTAL_COMPONENTS_BIT_EXACT_244':'ACCEPT','CONTINUUM_WORKSPACE_CANONICAL_V0472_61':'ACCEPT','HTCOMP_BIT_EXACT_61':'ACCEPT','HTFREEF_BIT_EXACT_61':'REJECT','ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610':'REJECT','CONTINUUM_UNEXPLAINED_COMPONENT_DELTAS_ZERO':'REJECT','NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1029':'REJECT'},
      'continuum_component_summary':{'htfreef':{'bit_exact':48,'rows':61,'max_ulp_distance':2}}
    }))
    p=subprocess.run([sys.executable,'-m','xstar_tools.xstar.v46171_baseline_gate_v048746172',str(source),'--output-json',str(output)],cwd=ROOT,env={'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert json.loads(output.read_text())['result']=='ACCEPT'

def test_readiness_accepts(tmp_path:Path):
    out=tmp_path/'readiness.json'
    p=subprocess.run([sys.executable,str(ROOT/'check_v048746172_continuum_freef_pow_semantics_hotfix_readiness.py'),'--package-dir',str(ROOT),'--output-json',str(out)],cwd=ROOT,capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert json.loads(out.read_text())['result']=='ACCEPT'
