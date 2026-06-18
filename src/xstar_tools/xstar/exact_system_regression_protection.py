#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
RELEASE='0.6.48.7.46.9.5'
KNOWN_ACCOUNTED={2,5,6,8,9,10,12,13,14,15,17,19,20}
ALLOWED_TYPES={53,56,63,77,99}
MAX_ACCOUNTED_DELTA=1.0e-6

def systems(path):
    with path.open(newline='') as h:
      return {(int(r['sequence']),int(r['element_z'])):r for r in csv.DictReader(h)}
def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--baseline-audit',type=Path,required=True); ap.add_argument('--audit-output',type=Path,required=True); ap.add_argument('--output-json',type=Path,required=True); a=ap.parse_args()
    errors=[]; base=systems(a.baseline_audit/'all61_matrix_contribution_systems.csv'); cur=systems(a.audit_output/'all61_matrix_contribution_systems.csv')
    protected=sorted(seq for (seq,z),r in base.items() if z==2 and r['dense_matrix_exact']=='1')
    exact=[]; regressed=[]
    cell_data={}
    with (a.audit_output/'all61_dense_matrix_causal_cells.csv').open(newline='') as h:
      for r in csv.DictReader(h):
        if int(r['element_z'])!=2: continue
        seq=int(r['sequence']); entry=cell_data.setdefault(seq,{'max_abs_delta':0.0,'data_types':set(),'cells':0})
        entry['cells']+=1; entry['max_abs_delta']=max(entry['max_abs_delta'],abs(float(r['delta'])))
        entry['data_types'].update(int(x) for x in r.get('causal_data_types','').split(';') if x)
    accounted=[]
    for seq in protected:
      r=cur.get((seq,2))
      if r and r['dense_matrix_exact']=='1': exact.append(seq); continue
      d=cell_data.get(seq,{'max_abs_delta':float('inf'),'data_types':set(),'cells':0})
      ok=seq in KNOWN_ACCOUNTED and d['cells']>0 and d['max_abs_delta']<=MAX_ACCOUNTED_DELTA and d['data_types'].issubset(ALLOWED_TYPES)
      item={'sequence':seq,'max_abs_delta':d['max_abs_delta'],'data_types':sorted(d['data_types']),'cells':d['cells'],'accounted':ok}
      regressed.append(item)
      if ok: accounted.append(seq)
      else: errors.append(f'unprotected formerly exact helium system: {item}')
    if len(protected)!=20: errors.append(f'baseline_exact_helium_systems={len(protected)} expected=20')
    if set(seq for seq in accounted)!=set(seq for seq in protected if seq not in exact):
      errors.append('not every formerly exact nonexact system is explicitly accounted')
    report={'schema':'xstar-tools-v064874693-exact-system-regression-protection-v1','release':RELEASE,'result':'ACCEPT' if not errors else 'REJECT','errors':errors,'baseline_exact_helium_systems':protected,'current_exact':exact,'explicitly_accounted':accounted,'regressions':regressed,'allowed_data_types':sorted(ALLOWED_TYPES),'maximum_accounted_delta':MAX_ACCOUNTED_DELTA,'gates':{'PREVIOUSLY_EXACT_DENSE_SYSTEMS_PROTECTED':'ACCEPT' if not errors else 'REJECT','PREVIOUSLY_EXACT_DENSE_SYSTEMS_TOTAL':len(protected),'PREVIOUSLY_EXACT_DENSE_SYSTEMS_EXACT':len(exact),'PREVIOUSLY_EXACT_DENSE_SYSTEMS_ACCOUNTED':len(accounted)}}
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if not errors else 2
if __name__=='__main__': raise SystemExit(main())
