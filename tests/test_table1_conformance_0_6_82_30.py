from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/'qualification/table1_conformance_0_6_82_30/table1_conformance_matrix_0_6_82_30.json'
SCOPE=ROOT/'qualification/table1_conformance_0_6_82_30/table1_conformance_scope_0_6_82_30.json'

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()

def test_version_and_frozen_identifiers():
    assert 'version = "0.6.82.30"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    d=json.loads(MATRIX.read_text())
    assert d['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert (d['c_api_abi'],d['production_zone_abi'],d['fixed_state_abi'])==(60487,6048110,60488)

def test_all_59_public_parameters_have_nondefault_probe_and_coverage():
    d=json.loads(MATRIX.read_text()); rows=d['parameter_matrix']
    assert len(rows)==59 and len({r['name'] for r in rows})==59
    assert sum(bool(r['table1_present']) for r in rows)==57
    assert {r['name'] for r in rows if not r['table1_present']}=={'naabund','lstep'}
    for r in rows:
        assert r['surface_probe_required'] is True
        assert r['semantic_group']
        try: equal=float(r['probe_value'])==float(r['stock_xstar_par_default'])
        except Exception: equal=str(r['probe_value'])==str(r['stock_xstar_par_default'])
        assert not equal, r['name']

def test_required_release_candidate_axes_are_frozen():
    a=json.loads(MATRIX.read_text())['required_axes']
    assert a['cfrac']==[0,0.4,1]
    assert a['emult']==[0.1,0.25,0.5,1.0]
    assert a['niter']==[0,-99,1,99]
    assert a['lcpres']==[0,1]
    assert a['npass']==[1,3,5]
    assert set(a['spectrum'])=={'pow','bbody','bremss','file'}
    assert a['spectun']==[0,1,2]
    assert a['ncn2']==[999,9999,19999]
    assert a['elements']==['C','O','Ca','Fe']

def test_science_tree_is_byte_identical_to_29_3_10():
    d=json.loads(SCOPE.read_text()); rows=d['numerical_science_files']
    assert len(rows)==137
    assert d['expected_changed_numerical_science_files']==[]
    for r in rows:
        assert sha(ROOT/r['path'])==r['sha256']==r['baseline_sha256']

def test_formal_29_closure_is_carried_into_30():
    d=json.loads((ROOT/'qualification/output_control_0_6_82_29_closure.json').read_text())
    assert d['closed'] is True and d['result']=='ACCEPT'
    assert d['closing_package']=='0.6.82.29.3.10'
    assert d['closing_archive_sha256']=='ed0af2a036fd760c0bc85e599e8afb8e274842c5f522e0b1188233e36f32b47f'
    text=(ROOT/'qualification/output_control_final_verbose_0_6_82_29_3_10/final_combined_check_0_6_82_29_3_10.txt').read_text()
    assert 'OUTPUT_CONTROL_068229310_RESULT=ACCEPT' in text

def test_static_checker_accepts_exact_candidate():
    p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_table1_conformance_0_6_82_30.py')],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0, p.stdout+p.stderr
    assert 'TABLE1_CONFORMANCE_068230_SOURCE_GATE=ACCEPT' in p.stdout

def test_all_30_abundance_parameters_have_full_science_cases():
    d=json.loads(MATRIX.read_text()); rows=d['parameter_matrix']; cases=d['representative_cases']
    abund=[r for r in rows if r['semantic_group']=='abundance_surface']
    assert len(abund)==30
    assert d['required_axes']['abundance_parameters']==[r['name'] for r in abund]
    for r in abund:
        c=cases['abund_'+r['name']]
        assert c['group']=='abundance_surface'
        assert c['parameter_under_test']==r['name']
        assert str(c['overrides'][r['name']])==str(r['probe_value'])


def test_master_host_runner_prepare_materializes_all_layers(tmp_path):
    runner=ROOT/'tools/qualification/run_table1_conformance_host_smoke_0_6_82_30.py'
    out=tmp_path/'prepared'
    p=subprocess.run([sys.executable,str(runner),'prepare','--package',str(ROOT),'--data-dir',str(tmp_path/'unused-data'),
                      '--output-root',str(out)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0, p.stdout+p.stderr
    assert 'TABLE1_CONFORMANCE_068230_RESULT=PREPARED' in p.stdout
    assert (out/'surface/qualification_manifest.json').is_file()
    assert (out/'representative/qualification_manifest.json').is_file()
    assert len(list((out/'representative/params').glob('*.par')))==len(json.loads(MATRIX.read_text())['representative_cases'])
    core=json.loads((out/'core/core_replay_summary.json').read_text())
    assert core['result']=='PREPARED'
    assert set(core['results'])=={'emult_cf0','emult_cf04','emult_cf1','niter','lcpres','radexp','npass','spectrum'}
