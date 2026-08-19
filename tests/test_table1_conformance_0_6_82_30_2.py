from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/'qualification/table1_conformance_0_6_82_30_2/table1_conformance_matrix_0_6_82_30_2.json'
SCOPE=ROOT/'qualification/table1_conformance_0_6_82_30_2/table1_conformance_scope_0_6_82_30_2.json'
LEDGER=ROOT/'qualification/table1_parameter_contract_0_6_82_23.json'

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def same(a,b):
    try: return float(a)==float(b)
    except Exception: return str(a)==str(b)

def test_version_and_frozen_identifiers():
    assert 'version = "0.6.82.30.2"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30.2' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    d=json.loads(MATRIX.read_text())
    assert d['rejected_predecessor']['version']=='0.6.82.30.1'
    assert d['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert (d['c_api_abi'],d['production_zone_abi'],d['fixed_state_abi'])==(60487,6048110,60488)

def test_literal_table1_baseline_and_extensions():
    d=json.loads(MATRIX.read_text()); ledger=json.loads(LEDGER.read_text())
    literal={r['name']:r['table1_default'] for r in ledger['parameters'] if r['table1_present']}
    assert len(literal)==57 and d['table1_baseline_case']==literal
    assert literal['spectrum']=='pow' and literal['spectrum_file']=='spct.dat'
    assert literal['temperature']==400.0 and literal['density']==1e4 and literal['cfrac']==1.0
    assert literal['niter']==0 and literal['critf']==1e-7 and literal['ncn2']==9999
    assert literal['modelname']=='XSTAR Default' and literal['mode']=='ql'
    assert d['public_extension_defaults']=={'naabund':1.0,'lstep':0}
    assert len(d['baseline_case'])==59

def test_all_59_public_parameters_are_one_at_a_time_surface_probes():
    d=json.loads(MATRIX.read_text()); rows=d['parameter_matrix']
    assert len(rows)==59 and len({r['name'] for r in rows})==59
    assert sum(bool(r['table1_present']) for r in rows)==57
    assert {r['name'] for r in rows if not r['table1_present']}=={'naabund','lstep'}
    for r in rows:
        assert r['surface_probe_required'] is True
        assert not same(r['probe_value'],r['baseline_default']), r['name']
        if r['table1_present']:
            assert r['baseline_source']=='XSTAR Manual Table 1'
        else:
            assert 'extension' in r['baseline_source']

def test_representative_ordinary_cases_are_one_at_a_time():
    d=json.loads(MATRIX.read_text())
    for name,c in d['representative_cases'].items():
        if c['group']!='elements':
            assert len(c.get('overrides',{}))<=1, name
    assert d['representative_cases']['baseline']['overrides']=={}
    assert d['representative_cases']['cfrac_0p4']['overrides']=={'cfrac':'0.4'}
    assert d['representative_cases']['emult_0p25']['overrides']=={'emult':'0.25'}
    assert d['representative_cases']['ncn2_999']['overrides']=={'ncn2':'999'}

def test_required_release_candidate_axes_are_frozen():
    a=json.loads(MATRIX.read_text())['required_axes']
    assert a['cfrac']==[0,0.4,1]; assert a['emult']==[0.1,0.25,0.5,1.0]
    assert a['niter']==[0,-99,1,99]; assert a['lcpres']==[0,1]; assert a['npass']==[1,3,5]
    assert set(a['spectrum'])=={'pow','bbody','bremss','file'}; assert a['spectun']==[0,1,2]
    assert a['ncn2']==[999,9999,19999]; assert a['elements']==['C','O','Ca','Fe']

def test_source_xpi_exceptions_are_explicit():
    d=json.loads(MATRIX.read_text())
    assert {x['parameter'] for x in d['source_xpi_exceptions']}=={'spectun','radexp','lwrite'}
    lwrite=next(x for x in d['invalid_contract_probes'] if x['name']=='lwrite')
    assert lwrite['backend_expectations']=={'fortran':'reject-stock-xpi','cpp':'accept-source-branch','python':'accept-source-branch'}

def test_science_tree_is_byte_identical_to_29_3_10():
    d=json.loads(SCOPE.read_text()); rows=d['numerical_science_files']
    assert len(rows)==137 and d['expected_changed_numerical_science_files']==[]
    for r in rows: assert sha(ROOT/r['path'])==r['sha256']==r['baseline_sha256']

def test_formal_29_closure_is_carried_forward():
    d=json.loads((ROOT/'qualification/output_control_0_6_82_29_closure.json').read_text())
    assert d['closed'] is True and d['result']=='ACCEPT' and d['closing_package']=='0.6.82.29.3.10'
    text=(ROOT/'qualification/output_control_final_verbose_0_6_82_29_3_10/final_combined_check_0_6_82_29_3_10.txt').read_text()
    assert 'OUTPUT_CONTROL_068229310_RESULT=ACCEPT' in text

def test_static_checker_accepts_exact_candidate():
    p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_table1_conformance_0_6_82_30_2.py')],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TABLE1_CONFORMANCE_0682302_SOURCE_GATE=ACCEPT' in p.stdout

def test_all_30_abundance_parameters_have_oat_science_cases():
    d=json.loads(MATRIX.read_text()); rows=d['parameter_matrix']; cases=d['representative_cases']
    abund=[r for r in rows if r['name'].endswith('abund')]
    assert len(abund)==30
    for r in abund:
        c=cases['abund_'+r['name']]
        assert c['parameter_under_test']==r['name']
        assert c['overrides']=={r['name']:str(r['probe_value'])}

def test_master_prepare_materializes_all_layers(tmp_path):
    runner=ROOT/'tools/qualification/run_table1_conformance_host_smoke_0_6_82_30_2.py'; out=tmp_path/'prepared'
    p=subprocess.run([sys.executable,str(runner),'prepare','--package',str(ROOT),'--data-dir',str(tmp_path/'unused-data'),
                      '--output-root',str(out)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TABLE1_CONFORMANCE_0682302_RESULT=PREPARED' in p.stdout
    assert (out/'surface/qualification_manifest.json').is_file()
    sm=json.loads((out/'surface/qualification_manifest.json').read_text())
    assert sm['table1_baseline']['spectrum']=='pow' and sm['table1_baseline']['spectrum_file']=='spct.dat'
    assert (out/'representative/qualification_manifest.json').is_file()
    assert len(list((out/'representative/params').glob('*.par')))==len(json.loads(MATRIX.read_text())['representative_cases'])
    # The baseline .par itself must contain the literal Table-1 spectrum/default model.
    txt=(out/'representative/params/baseline.par').read_text()
    assert 'spectrum,s,a,"pow"' in txt or 'spectrum,s,a,pow' in txt
    assert 'spectrum_file,s,a,"spct.dat"' in txt or 'spectrum_file,s,a,spct.dat' in txt
    core=json.loads((out/'core/core_replay_summary.json').read_text())
    assert core['result']=='PREPARED'
    assert set(core['results'])=={'emult_cf0','emult_cf04','emult_cf1','niter','lcpres','radexp','npass','spectrum'}

def test_fortran_surface_uses_pget_not_pquery():
    text=(ROOT/'tools/qualification/run_table1_parameter_surface_host_smoke_0_6_82_30_2.py').read_text()
    assert 'shutil.which("pget")' in text
    assert 'subprocess.run([pget, "xstar", name]' in text
    assert 'shutil.which("pquery2")' not in text
    assert 'shutil.which("pquery")' not in text
    assert 'subprocess.run([pquery' not in text
    assert 'stock-xstar.par-envelope' in text

def test_fortran_surface_noninteractive_pget_and_file_fallback(tmp_path):
    import importlib.util, os
    runner=ROOT/'tools/qualification/run_table1_parameter_surface_host_smoke_0_6_82_30_2.py'
    spec=importlib.util.spec_from_file_location('surface0682302_test', runner)
    mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
    sysp=tmp_path/'syspfiles'; sysp.mkdir()
    (sysp/'xstar.par').write_text(
        'temperature,r,q,400,0,10000,temperature\n'
        'cfrac,r,h,1,0,1,cfrac\n', encoding='utf-8')
    bindir=tmp_path/'bin'; bindir.mkdir()
    pset=bindir/'pset'
    pset.write_text('''#!/usr/bin/env python3
import csv,os,sys
from pathlib import Path
local=Path(os.environ["PFILES"].split(";",1)[0]); par=local/"xstar.par"
name,value=sys.argv[2].split("=",1)
rows=list(csv.reader(par.open()))
for row in rows:
    if row and row[0].strip()==name: row[3]=value
with par.open("w",newline="") as f: csv.writer(f,lineterminator="\\n").writerows(rows)
''', encoding='utf-8'); pset.chmod(0o755)
    pget=bindir/'pget'
    pget.write_text('''#!/usr/bin/env python3
import csv,os,sys
from pathlib import Path
par=Path(os.environ["PFILES"].split(";",1)[0])/"xstar.par"; name=sys.argv[2]
for row in csv.reader(par.open()):
    if row and row[0].strip()==name:
        print(row[3]); raise SystemExit(0)
raise SystemExit(2)
''', encoding='utf-8'); pget.chmod(0o755)
    baseline={'temperature':400.0,'cfrac':1.0}
    observed,meta=mod.fortran_surface(pset=str(pset),pget=str(pget),sysp=sysp,baseline=baseline,name='temperature',value=250.0,kind='real')
    assert observed==250.0 and meta['readback_method']=='pget'
    assert float(meta['context_values']['cfrac'])==1.0
    observed2,meta2=mod.fortran_surface(pset=str(pset),pget=None,sysp=sysp,baseline=baseline,name='temperature',value=300.0,kind='real')
    assert observed2==300.0 and meta2['readback_method']=='private-xstar.par'
