from __future__ import annotations
import csv,json,subprocess,sys
from pathlib import Path
import xstar_tools
from xstar_tools.xstar import hydrogen_type50_cooling_v04874618 as audit
from xstar_tools.xstar import v0472_all61_hydrogen_type50_escape_capture as capture
ROOT=Path(__file__).resolve().parents[1]
def write_csv(path,fields,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
def test_release_and_source_probe_contract():
 assert xstar_tools.__version__=='0.6.48.7.46.18'
 assert capture.EXPECTED_ROWS==8113
 assert 'line_tau_in.bin' in capture._PROBE
 assert 'v04874618_escape_rows' in capture._PROBE
 assert capture._pescl(0.0)==0.5

def test_cpp_line_escape_contract():
 s=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
 for token in ('XSTAR_QUALIFICATION_HYDROGEN_TYPE50_ESCAPE_STATE','XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_MAP_CSV','XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_IN_BIN','XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_OUT_BIN','pescl_v0472_binary64','type50_hydrogen_escape_state_applied'):
  assert token in s

def test_baseline_validator_accepts_post_continuum(tmp_path:Path):
 source=tmp_path/'checker.json'; out=tmp_path/'out.json'
 gates={name:'ACCEPT' for name in ('ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610','CONTINUUM_UNEXPLAINED_COMPONENT_DELTAS_ZERO','V06487_FIXED_STATE_PARITY_PRESERVED','DENSE_EXACT_SYSTEMS_183_PRESERVED','DENSE_MISMATCH_CELLS_ZERO_PRESERVED','NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1029','PRODUCTION_PROMOTION_BLOCKED')}
 source.write_text(json.dumps({'result':'ACCEPT','gates':gates,'native_computed_values_exact':1029,'native_computed_values_total':2440}))
 p=subprocess.run([sys.executable,'-m','xstar_tools.xstar.v461721_baseline_gate_v04874618',str(source),'--output-json',str(out)],cwd=ROOT,env={'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr
 assert json.loads(out.read_text())['result']=='ACCEPT'

def test_synthetic_hydrogen_type50_audit_accepts(tmp_path:Path):
 source=tmp_path/'source'; native=tmp_path/'native'; output=tmp_path/'out'
 sf=capture.ESCAPE_FIELDS
 srows=[]
 for seq in range(1,62):
  call=1 if seq<=12 else 2 if seq<=24 else 3 if seq<=43 else 4
  for record in range(1,134):
   srows.append({'sequence':seq,'kind':'dsec','call_index':call,'evaluation_index':seq,'record':record,'line_index':record,'tau_in':0.0,'tau_out':0.0,'ptmp1':0.5,'ptmp2':0.5,'ptmp_sum':1.0,'covering_fraction':0.0,'ans1':1.0,'ans2':2.0,'ans3':3.0,'ans4':4.0,'ans5':0.0,'ans6':0.0,'idest1':1,'idest2':2,'ucalc_status':'ok'})
 write_csv(source/capture.ESCAPE_NAME,sf,srows)
 nf=['element_z','data_type','record','source_position','type50_line_index_one_based','type50_line_tau_in','type50_line_tau_out','type50_ptmp1','type50_ptmp2','type50_hydrogen_escape_state_applied']+[f'type50_shadow_ans{i}' for i in range(1,7)]
 for seq in range(1,62):
  nrows=[]
  for record in range(1,134):
   row={'element_z':1,'data_type':50,'record':record,'source_position':record,'type50_line_index_one_based':record,'type50_line_tau_in':0.0,'type50_line_tau_out':0.0,'type50_ptmp1':0.5,'type50_ptmp2':0.5,'type50_hydrogen_escape_state_applied':1}
   for i,val in enumerate((1.0,2.0,3.0,4.0,0.0,0.0),1): row[f'type50_shadow_ans{i}']=val
   nrows.append(row)
  write_csv(native/'qualification_diagnostics'/f'evaluation_{seq:04d}_records.csv',nf,nrows)
 cf=['sequence','kind','call_index','evaluation_index','group','component','source_value','computed_native_value','committed_native_value','computed_signed_delta','committed_signed_delta','computed_exact','committed_exact','classification']
 crows=[]
 for seq in range(1,62):
  call=1 if seq<=12 else 2 if seq<=24 else 3 if seq<=43 else 4
  crows.append({'sequence':seq,'kind':'dsec','call_index':call,'evaluation_index':seq,'group':'H_HE_MG','component':'h_cooling','source_value':1,'computed_native_value':1,'committed_native_value':1,'computed_signed_delta':0,'committed_signed_delta':0,'computed_exact':1,'committed_exact':1,'classification':'exact'})
 for i in range(2379):
  exact=1 if i<1005 else 0
  crows.append({'sequence':1,'kind':'dsec','call_index':1,'evaluation_index':1,'group':'H_HE_MG','component':f'x{i}','source_value':1,'computed_native_value':1 if exact else 2,'committed_native_value':1,'computed_signed_delta':0 if exact else 1,'committed_signed_delta':0,'computed_exact':exact,'committed_exact':1,'classification':'x'})
 comp=tmp_path/'components.csv'; write_csv(comp,cf,crows)
 report=audit.audit(source,native,comp,output)
 assert report['result']=='ACCEPT',report
 assert report['native_computed_values_exact']==1066
 assert report['gates']['HYDROGEN_COOLING_CALLS34_EXACT_37']=='ACCEPT'

def test_readiness_accepts(tmp_path:Path):
 out=tmp_path/'readiness.json'
 p=subprocess.run([sys.executable,str(ROOT/'check_v04874618_hydrogen_type50_cooling_readiness.py'),'--package-dir',str(ROOT),'--output-json',str(out)],cwd=ROOT,capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr
 assert json.loads(out.read_text())['result']=='ACCEPT'
