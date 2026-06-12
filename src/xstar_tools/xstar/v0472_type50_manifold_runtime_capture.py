"""Capture a v0.6.47.2 evaluator oracle for the He II type-50 rows 46-54 manifold."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,subprocess,sys,tarfile,tempfile
from pathlib import Path
from typing import Any,Mapping
RELEASE='0.6.48.7.10'; SCHEMA='xstar-tools-v064879-v0472-type50-manifold-runtime-capture-v1'; ORACLE_SCHEMA='xstar-tools-v064879-type50-manifold-runtime-oracle-v1'
SOURCE_ARCHIVE_SHA256='85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060'
SOURCE_MODULE_RELATIVE=Path('src/xstar_tools/rates_type50.py'); SOURCE_MODULE_SHA256=''
ORACLE_NAME='type50_heii_rows46_54_runtime_oracle.csv'; TARGET_COUNT=79
FIELDS=['evaluation_ordinal','source_position','record','element_z','ion_stage','data_type','lower_row','upper_row','ans1','ans2','ans3','ans4','ans5','ans6','aij_s_inv','oscillator_strength','wavelength_a','line_energy_ev','ptmp1','ptmp2','ptmp_sum','cfrac','bremsa_nb1','radiation_bin_zero_based','temperature_k','hydrogen_density_cm3','payload_sha256','source_archive_sha256','source_module_sha256']
def sha256(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write_json(p:Path,x:Mapping[str,Any]):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(dict(x),indent=2,sort_keys=True)+'\n')
def safe_extract(a:Path,d:Path):
 d.mkdir(parents=True,exist_ok=True);root=d.resolve()
 with tarfile.open(a,'r:gz') as t:
  for m in t.getmembers():
   q=(root/m.name).resolve()
   if (root!=q and root not in q.parents) or m.issym() or m.islnk():raise ValueError(f'unsafe source member {m.name}')
  t.extractall(root,filter='fully_trusted')
def source_root(d:Path)->Path:
 roots=[p.parent for p in d.glob('*/pyproject.toml')]
 if len(roots)!=1:raise ValueError('expected one source root')
 return roots[0]
def state_path(a:Path,e:int)->Path:
 for p in (a/'diagnostics'/f'evaluation_{e:04d}_state.json',a/f'evaluation_{e:04d}_state.json'):
  if p.is_file():return p
 raise FileNotFoundError('state json')
_REPLAY=r'''
import csv,hashlib,json,math,pathlib,sys
import numpy as np
cfg=json.loads(pathlib.Path(sys.argv[1]).read_text());out=pathlib.Path(sys.argv[2])
from xstar_tools.rates_type50 import evaluate_type50_ucalc_record
root=pathlib.Path(cfg['lowered_program']); reals=[float(x) for x in (root/'reals.txt').read_text().splitlines()]
with (root/'records.csv').open() as f: recs=list(csv.DictReader(f))
with (root/'rows.csv').open() as f: rows={(int(r['element_index']),int(r['row'])):r for r in csv.DictReader(f)}
with pathlib.Path(cfg['radiation_csv']).open() as f: rr=list(csv.DictReader(f))
epi=np.asarray([float(r['energy']) for r in rr]); brem=np.asarray([float(r['incident']) for r in rr])
target=[r for r in recs if int(r['element_index'])==1 and int(r['ion_stage'])==2 and int(r['data_type'])==50 and (46<=int(r['lower_row'])<=54 or 46<=int(r['upper_row'])<=54)]
target.sort(key=lambda r:int(r['source_position']))
if len(target)!=79: raise RuntimeError(f'expected 79 records, got {len(target)}')
out.parent.mkdir(parents=True,exist_ok=True)
with out.open('w',newline='') as h:
 w=csv.DictWriter(h,fieldnames=cfg['fields']);w.writeheader()
 for rec in target:
  ro,rc=int(rec['real_offset']),int(rec['real_count']); payload=reals[ro:ro+rc]
  if len(payload)<2:raise RuntimeError('short type50 payload')
  lo=rows[(1,int(rec['lower_row']))];up=rows[(1,int(rec['upper_row']))]
  de=abs(float(up['energy_ev'])-float(lo['energy_ev'])); wave=12398.4016/de if de>0 else 0.0
  nb=max(0,min(int(np.searchsorted(epi,12398.54/wave,side='right')-1),len(epi)-1)) if wave>0 else 0
  ev=evaluate_type50_ucalc_record({'A_s_inv':payload[0],'oscillator_strength':payload[1],'wavelength_A':wave},ptmp1=1.0,ptmp2=0.0,cfrac=0.0,bremsa_nb1=float(brem[nb]),hydrogen_density_cm3=float(cfg['hydrogen_density_cm3']),endpoint_energy_eV=de)
  ans=[ev['ans1_photoexcitation_s^-1'],ev['ans2_escaped_decay_s^-1'],ev['ans3_cooling_signed_erg_s^-1'],ev['ans4_heating_signed_erg_s^-1'],0.0,0.0]
  if any(v is None or not math.isfinite(float(v)) for v in ans):raise RuntimeError(f'evaluator failed {rec["record"]}')
  dig=hashlib.sha256();[dig.update((float(v).hex()+'\n').encode()) for v in payload]
  row={'evaluation_ordinal':cfg['evaluation_ordinal'],'source_position':rec['source_position'],'record':rec['record'],'element_z':2,'ion_stage':2,'data_type':50,'lower_row':rec['lower_row'],'upper_row':rec['upper_row'],**{f'ans{i+1}':float(ans[i]) for i in range(6)},'aij_s_inv':payload[0],'oscillator_strength':payload[1],'wavelength_a':wave,'line_energy_ev':de,'ptmp1':1.0,'ptmp2':0.0,'ptmp_sum':1.0,'cfrac':0.0,'bremsa_nb1':float(brem[nb]),'radiation_bin_zero_based':nb,'temperature_k':cfg['temperature_k'],'hydrogen_density_cm3':cfg['hydrogen_density_cm3'],'payload_sha256':dig.hexdigest(),'source_archive_sha256':cfg['source_archive_sha256'],'source_module_sha256':cfg['source_module_sha256']}
  w.writerow(row)
pathlib.Path(sys.argv[3]).write_text(json.dumps({'schema':cfg['schema'],'release':cfg['release'],'result':'ACCEPT','capture_kind':'exact_v06472_fixed_state_type50_heii_rows46_54_evaluator_replay','records':len(target),'evaluation_ordinal':cfg['evaluation_ordinal'],'escape_probability_contract':'ptmp1=1, ptmp2=0, matching native ans2=A for all qualified records','radiation_sampling_contract':'v0.6.47.2 _nbinc lower-bin sampling at 12398.54/wavelength_A','full_dsec_runtime_capture':False,'production_promotion_ready':False},indent=2,sort_keys=True)+'\n')
'''
def capture(source:Path,program:Path,audit:Path,radiation:Path,out:Path,evaluation:int=61):
 if sha256(source)!=SOURCE_ARCHIVE_SHA256:raise ValueError('source hash mismatch')
 st=json.loads(state_path(audit,evaluation).read_text());out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);safe_extract(source,td/'src');root=source_root(td/'src'); mod=root/SOURCE_MODULE_RELATIVE; msh=sha256(mod)
  cfg={'schema':SCHEMA,'release':RELEASE,'fields':FIELDS,'evaluation_ordinal':evaluation,'lowered_program':str(program.resolve()),'radiation_csv':str(radiation.resolve()),'temperature_k':st['temperature_k'],'hydrogen_density_cm3':st['hydrogen_density_cm3'],'source_archive_sha256':SOURCE_ARCHIVE_SHA256,'source_module_sha256':msh}
  c=td/'cfg.json';c.write_text(json.dumps(cfg));env=dict(os.environ);env['PYTHONPATH']=str(root/'src')
  cp=subprocess.run([sys.executable,'-c',_REPLAY,str(c),str(out/ORACLE_NAME),str(out/'capture_report.json')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if cp.returncode:raise RuntimeError(cp.stdout)
 return json.loads((out/'capture_report.json').read_text())
def freeze(cap:Path,bundle:Path):
 bundle.mkdir(parents=True,exist_ok=True);(bundle/ORACLE_NAME).write_bytes((cap/ORACLE_NAME).read_bytes());r=json.loads((cap/'capture_report.json').read_text())
 prov={**r,'source_archive_sha256':SOURCE_ARCHIVE_SHA256,'oracle_sha256':sha256(bundle/ORACLE_NAME)};write_json(bundle/'capture_provenance.json',prov)
 files={n:{'sha256':sha256(bundle/n),'size_bytes':(bundle/n).stat().st_size} for n in (ORACLE_NAME,'capture_provenance.json')};write_json(bundle/'reference_manifest.json',{'schema':ORACLE_SCHEMA,'release':RELEASE,'result':'ACCEPT','immutable':True,'records':TARGET_COUNT,'files':files,'production_promotion_ready':False})
 return verify(bundle)
def verify(bundle:Path):
 errors=[];m=json.loads((bundle/'reference_manifest.json').read_text())
 for n,x in m['files'].items():
  if not (bundle/n).is_file() or sha256(bundle/n)!=x['sha256']:errors.append(n)
 rows=list(csv.DictReader((bundle/ORACLE_NAME).open()))
 if len(rows)!=TARGET_COUNT:errors.append(f'count={len(rows)}')
 return {'schema':ORACLE_SCHEMA,'release':RELEASE,'result':'ACCEPT' if not errors else 'REJECT','records':len(rows),'errors':errors,'files_verified':3 if not errors else 0,'oracle_sha256':sha256(bundle/ORACLE_NAME),'bundle_directory':str(bundle),'production_promotion_ready':False}
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True);c=s.add_parser('capture-and-freeze');[c.add_argument(x,type=Path) for x in ('source_archive','lowered_program','audit_output','radiation_csv','bundle_dir')];c.add_argument('--evaluation',type=int,default=61);c.add_argument('--output-json',type=Path);v=s.add_parser('verify');v.add_argument('bundle_dir',type=Path);v.add_argument('--output-json',type=Path);a=p.parse_args(argv)
 try:
  if a.cmd=='verify':r=verify(a.bundle_dir)
  else:
   with tempfile.TemporaryDirectory() as td:capture(a.source_archive,a.lowered_program,a.audit_output,a.radiation_csv,Path(td),a.evaluation);r=freeze(Path(td),a.bundle_dir)
  if a.output_json:write_json(a.output_json,r)
  print(json.dumps(r,indent=2,sort_keys=True));return 0 if r['result']=='ACCEPT' else 2
 except Exception as e:print(f'type50 manifold capture failed: {e}');return 2
if __name__=='__main__':raise SystemExit(main())
