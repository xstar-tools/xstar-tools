from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/'qualification/table1_conformance_0_6_82_30_4/table1_conformance_matrix_0_6_82_30_4.json'
SCOPE=ROOT/'qualification/table1_conformance_0_6_82_30_4/table1_conformance_scope_0_6_82_30_4.json'
LEDGER=ROOT/'qualification/table1_parameter_contract_0_6_82_23.json'

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def same(a,b):
    try: return float(a)==float(b)
    except Exception: return str(a)==str(b)

def test_version_and_frozen_identifiers():
    assert 'version = "0.6.82.30.4"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30.4' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    d=json.loads(MATRIX.read_text())
    assert d['rejected_predecessor']['version']=='0.6.82.30.3'
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
    p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_table1_conformance_0_6_82_30_4.py')],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TABLE1_CONFORMANCE_0682304_SOURCE_GATE=ACCEPT' in p.stdout

def test_all_30_abundance_parameters_have_oat_science_cases():
    d=json.loads(MATRIX.read_text()); rows=d['parameter_matrix']; cases=d['representative_cases']
    abund=[r for r in rows if r['name'].endswith('abund')]
    assert len(abund)==30
    for r in abund:
        c=cases['abund_'+r['name']]
        assert c['parameter_under_test']==r['name']
        assert c['overrides']=={r['name']:str(r['probe_value'])}

def test_master_prepare_materializes_all_layers(tmp_path):
    runner=ROOT/'tools/qualification/run_table1_conformance_host_smoke_0_6_82_30_4.py'; out=tmp_path/'prepared'
    p=subprocess.run([sys.executable,str(runner),'prepare','--package',str(ROOT),'--data-dir',str(tmp_path/'unused-data'),
                      '--output-root',str(out)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TABLE1_CONFORMANCE_0682304_RESULT=PREPARED' in p.stdout
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

def test_fortran_surface_uses_benchmark_style_direct_xstar_and_runtime_step_snapshot():
    text=(ROOT/'tools/qualification/run_table1_parameter_surface_host_smoke_0_6_82_30_4.py').read_text()
    prefix=text.split('def native_surface',1)[0]
    assert 'subprocess.Popen(argv' in prefix
    assert 'xout_step.log' in prefix and 'input parameters:' in prefix
    assert 'terminated_after_runtime_snapshot' in text
    assert 'shutil.which("pset")' not in prefix
    assert 'shutil.which("pget")' not in prefix
    assert 'shutil.which("pquery")' not in prefix
    assert 'write_private_par' not in prefix
    assert 'private_pfiles_case' not in prefix


def test_fortran_runtime_policies_are_source_faithful():
    d=json.loads(MATRIX.read_text()); rows={r['name']:r for r in d['parameter_matrix']}
    assert rows['pressure']['fortran_surface_runtime_policy']=='conditionally-inactive-at-table1-lcpres0'
    assert rows['spectrum_file']['fortran_surface_runtime_policy']=='conditionally-inactive-at-table1-spectrum-pow'
    assert rows['spectun']['fortran_surface_runtime_policy']=='conditionally-inactive-at-table1-spectrum-pow'
    assert rows['mode']['fortran_surface_runtime_policy']=='xpi-interface-only-not-consumed-by-rread1'
    for n,r in rows.items():
        if n not in {'pressure','spectrum_file','spectun','mode'}:
            assert r['fortran_surface_runtime_policy']=='runtime-equals-supplied'


def test_parse_fortran_runtime_snapshot_covers_target_surface():
    import importlib.util
    runner=ROOT/'tools/qualification/run_table1_parameter_surface_host_smoke_0_6_82_30_4.py'
    spec=importlib.util.spec_from_file_location('surface0682304_parse_test', runner)
    mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
    abund='\n'.join(f'{name:8s}  5.000E-01  1.000E-04  8.000E+00' for name in mod.ELEMENT_TO_ABUND)
    block='''input parameters:
 covering fraction=      4.000E-01
 temperature (/10**4K)= 1.000E+02
 constant pressure switch (1=yes, 0=no)=           0
 pressure (dyne/cm**2)= 3.000E-02
 density (cm**-3)=      1.000E+04
 spectrum type=pow
 spectrum file=
 spectrum units? (0=energy, 1=photons)           0
 radiation temperature or alpha= -1.000E+00
 luminosity (/10**38 erg/s)= 1.000E-06
 column density (cm**-2)= 1.000E+17
 log(ionization parameter)= 5.000E+00
 abundance table: xdef
 abundances:
 element,   rel.to cosmic,     rel. to H,     H=12
'''+abund+'''
 model name=XSTAR Default
 number of steps=           3
 number of iterations=           0
 write switch (1=yes, 0=no)=           0
 print switch (1=yes, 0=no)=           0
 step size choice switch=           0
 loop control (0=standalone)=           0
 number of passes=           1
 emult=  5.0000000000000000E-01
 taumax=  5.0000000000000000
 xeemin=  1.0000000000000001E-01
 critf=  9.9999999999999995E-08
 vturbi=  1.0000000000000000
 ncn2=        9999
 radexp=  0.0000000000000000
'''
    d=mod.parse_fortran_runtime_snapshot(block)
    assert d['cfrac']==0.4 and d['temperature']==100.0 and d['spectrum']=='pow'
    assert d['spectrum_file']=='' and d['spectun']==0 and d['ncn2']==9999
    assert d['radexp']==0.0 and d['habund']==0.5 and d['znabund']==0.5


def test_fortran_surface_launches_full_oat_command_and_stops_after_snapshot(tmp_path):
    import importlib.util
    runner=ROOT/'tools/qualification/run_table1_parameter_surface_host_smoke_0_6_82_30_4.py'
    spec=importlib.util.spec_from_file_location('surface0682304_fake_test', runner)
    mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
    fake=tmp_path/'xstar'
    fake.write_text(r'''#!/usr/bin/env python3
import sys,time
from pathlib import Path
vals=dict(x.split('=',1) for x in sys.argv[1:] if '=' in x)
text=f"""input parameters:
 covering fraction=      {float(vals['cfrac']):.3E}
 temperature (/10**4K)= {float(vals['temperature']):.3E}
 constant pressure switch (1=yes, 0=no)= {int(float(vals['lcpres']))}
 pressure (dyne/cm**2)= {float(vals['pressure']):.3E}
 density (cm**-3)=      {float(vals['density']):.3E}
 spectrum type={vals['spectrum']}
 spectrum file=
 spectrum units? (0=energy, 1=photons) 0
 radiation temperature or alpha= {float(vals['trad']):.3E}
 luminosity (/10**38 erg/s)= {float(vals['rlrad38']):.3E}
 column density (cm**-2)= {float(vals['column']):.3E}
 log(ionization parameter)= {float(vals['rlogxi']):.3E}
 abundance table: {vals['abundtbl']}
 abundances:
 element,   rel.to cosmic,     rel. to H,     H=12
 hydrogen  {float(vals['habund']):.3E} 1.0E+00 1.2E+01
 model name={vals['modelname']}
 number of steps= {int(float(vals['nsteps']))}
 number of iterations= {int(float(vals['niter']))}
 write switch (1=yes, 0=no)= {int(float(vals['lwrite']))}
 print switch (1=yes, 0=no)= {int(float(vals['lprint']))}
 step size choice switch= {int(float(vals['lstep']))}
 loop control (0=standalone)= {int(float(vals['loopcontrol']))}
 number of passes= {int(float(vals['npass']))}
 emult= {float(vals['emult']):.16E}
 taumax= {float(vals['taumax']):.16E}
 xeemin= {float(vals['xeemin']):.16E}
 critf= {float(vals['critf']):.16E}
 vturbi= {float(vals['vturbi']):.16E}
 ncn2= {int(float(vals['ncn2']))}
 radexp= {float(vals['radexp']):.16E}
"""
Path('xout_step.log').write_text(text)
time.sleep(30)
''',encoding='utf-8'); fake.chmod(0o755)
    baseline={
      'cfrac':1.0,'temperature':400.0,'lcpres':0,'pressure':0.03,'density':1e4,'spectrum':'pow','spectrum_file':'spct.dat','spectun':0,
      'trad':-1.0,'rlrad38':1e-6,'column':1e17,'rlogxi':5.0,'abundtbl':'xdef','habund':1.0,'modelname':'XSTAR Default','nsteps':3,
      'niter':0,'lwrite':0,'lprint':0,'lstep':0,'emult':0.5,'taumax':5.0,'xeemin':0.1,'critf':1e-7,'vturbi':1.0,'radexp':0.0,
      'ncn2':9999,'loopcontrol':0,'npass':1,'mode':'ql'}
    observed,meta=mod.fortran_surface(binary=fake,root=tmp_path/'out',baseline=baseline,name='temperature',value=100.0,kind='real',timeout=5)
    assert observed==100.0
    assert meta['benchmark_style_direct_invocation'] is True
    assert meta['terminated_after_runtime_snapshot'] is True
    assert meta['command_values']['cfrac']==1.0 and meta['command_values']['temperature']==100.0
    cmd=json.loads(Path(meta['command_json']).read_text())
    assert 'temperature=100.0' in cmd['argv'] and 'cfrac=1.0' in cmd['argv']
    assert cmd['changed']==['temperature']


def test_conditional_fortran_target_expectations():
    import importlib.util
    runner=ROOT/'tools/qualification/run_table1_parameter_surface_host_smoke_0_6_82_30_4.py'
    spec=importlib.util.spec_from_file_location('surface0682304_policy_test', runner)
    mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
    b={'lcpres':0,'pressure':0.03,'spectrum':'pow','spectrum_file':'spct.dat','spectun':0,'mode':'ql'}
    assert mod.fortran_target_expectation('pressure',0.04,{**b,'pressure':0.04},b)[0]==0.03
    assert mod.fortran_target_expectation('spectrum_file','spect.dat',{**b,'spectrum_file':'spect.dat'},b)[0]==''
    assert mod.fortran_target_expectation('spectun',1,{**b,'spectun':1},b)[0]==0
    assert mod.fortran_target_expectation('mode','h',{**b,'mode':'h'},b)[0] is None
    assert mod.fortran_target_expectation('cfrac',0.4,{**b,'cfrac':0.4},b)[0]==0.4
