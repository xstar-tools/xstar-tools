"""Audit v46.18 source-faithful H Type-50 line-escape transport and cooling."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
from typing import Any
RELEASE='0.6.48.7.46.21.3.1'
SCHEMA='xstar-tools-v064874618-hydrogen-type50-cooling-audit-v1'
EXPECTED_EVALUATIONS=61; EXPECTED_RECORDS=133; EXPECTED_ROWS=8113
FIELDS=['sequence','call_index','record','source_position','line_index','native_line_index','tau_in','native_tau_in','tau_out','native_tau_out','ptmp1','native_ptmp1','ptmp2','native_ptmp2']+[f'ans{i}' for i in range(1,7)]+[f'native_ans{i}' for i in range(1,7)]+['line_index_exact','tau_in_exact','tau_out_exact','ptmp1_exact','ptmp2_exact','answers_exact']
def rows(path:Path):
 with path.open(newline='') as f: return list(csv.DictReader(f))
def exact(a:Any,b:Any)->bool:
 try: return float(a).hex()==float(b).hex()
 except Exception: return str(a)==str(b)
def write_json(path:Path,obj): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
def audit(source_capture:Path,native_run:Path,component_comparison:Path,output:Path)->dict:
 errors=[]; output.mkdir(parents=True,exist_ok=True)
 source_path=source_capture/'v0472_all61_hydrogen_type50_escape.csv'
 if not source_path.is_file(): return {'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[f'missing:{source_path}'],'gates':{},'qualification_only':True,'production_promotion_ready':False}
 source=rows(source_path); src={(int(r['sequence']),int(r['record'])):r for r in source}
 native={}
 for seq in range(1,62):
  path=native_run/'qualification_diagnostics'/f'evaluation_{seq:04d}_records.csv'
  if not path.is_file(): errors.append(f'missing_native_records:{seq}'); continue
  for r in rows(path):
   if int(r.get('element_z','0'))==1 and int(r.get('data_type','0'))==50:
    native[(seq,int(r['record']))]=r
 comparisons=[]; counts={k:0 for k in ('line','tau_in','tau_out','ptmp1','ptmp2','answers')}
 call_counts={i:{'rows':0,'exact':0} for i in range(1,5)}
 for key,s in sorted(src.items()):
  n=native.get(key)
  if n is None: errors.append(f'missing_native:{key[0]}:{key[1]}'); continue
  call=int(s['call_index']); call_counts[call]['rows']+=1
  vals={
   'line':int(s['line_index'])==int(n['type50_line_index_one_based']),
   'tau_in':exact(s['tau_in'],n['type50_line_tau_in']), 'tau_out':exact(s['tau_out'],n['type50_line_tau_out']),
   'ptmp1':exact(s['ptmp1'],n['type50_ptmp1']), 'ptmp2':exact(s['ptmp2'],n['type50_ptmp2']),
   'answers':all(exact(s[f'ans{i}'],n[f'type50_shadow_ans{i}']) for i in range(1,7)),
  }
  for k,v in vals.items(): counts[k]+=int(v)
  all_exact=all(vals.values()) and n.get('type50_hydrogen_escape_state_applied')=='1'
  call_counts[call]['exact']+=int(all_exact)
  row={'sequence':key[0],'call_index':call,'record':key[1],'source_position':n.get('source_position',''),'line_index':s['line_index'],'native_line_index':n['type50_line_index_one_based'],'tau_in':s['tau_in'],'native_tau_in':n['type50_line_tau_in'],'tau_out':s['tau_out'],'native_tau_out':n['type50_line_tau_out'],'ptmp1':s['ptmp1'],'native_ptmp1':n['type50_ptmp1'],'ptmp2':s['ptmp2'],'native_ptmp2':n['type50_ptmp2']}
  for i in range(1,7): row[f'ans{i}']=s[f'ans{i}']; row[f'native_ans{i}']=n[f'type50_shadow_ans{i}']
  row.update({'line_index_exact':int(vals['line']),'tau_in_exact':int(vals['tau_in']),'tau_out_exact':int(vals['tau_out']),'ptmp1_exact':int(vals['ptmp1']),'ptmp2_exact':int(vals['ptmp2']),'answers_exact':int(vals['answers'])})
  comparisons.append(row)
 with (output/'v04874618_hydrogen_type50_escape_comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore'); w.writeheader(); w.writerows(comparisons)
 components=rows(component_comparison)
 h=[r for r in components if r.get('component')=='h_cooling']
 h_exact=sum(int(r.get('computed_exact','0')) for r in h); h_call={i:[r for r in h if int(r['call_index'])==i] for i in range(1,5)}
 native_exact=sum(int(r.get('computed_exact','0')) for r in components)
 total=len(components)
 gates={
  'ALL_61_HYDROGEN_TYPE50_ESCAPE_STATES_CAPTURED':'ACCEPT' if len(src)==EXPECTED_ROWS else 'REJECT',
  'ALL_61_HYDROGEN_TYPE50_NATIVE_RECORDS_ATTRIBUTED':'ACCEPT' if len(native)==EXPECTED_ROWS else 'REJECT',
  'HYDROGEN_TYPE50_LINE_INDICES_EXACT_8113':'ACCEPT' if counts['line']==EXPECTED_ROWS else 'REJECT',
  'HYDROGEN_TYPE50_LINE_TAU_VALUES_EXACT_16226':'ACCEPT' if counts['tau_in']+counts['tau_out']==2*EXPECTED_ROWS else 'REJECT',
  'HYDROGEN_TYPE50_ESCAPE_FACTORS_EXACT_16226':'ACCEPT' if counts['ptmp1']+counts['ptmp2']==2*EXPECTED_ROWS else 'REJECT',
  'HYDROGEN_TYPE50_ANSWERS_EXACT_8113':'ACCEPT' if counts['answers']==EXPECTED_ROWS else 'REJECT',
  'HYDROGEN_COOLING_CALLS12_PRESERVED_24':'ACCEPT' if sum(int(r['computed_exact']) for i in (1,2) for r in h_call[i])==24 and sum(len(h_call[i]) for i in (1,2))==24 else 'REJECT',
  'HYDROGEN_COOLING_CALLS34_EXACT_37':'ACCEPT' if sum(int(r['computed_exact']) for i in (3,4) for r in h_call[i])==37 and sum(len(h_call[i]) for i in (3,4))==37 else 'REJECT',
  'HYDROGEN_COOLING_ALL61_EXACT':'ACCEPT' if h_exact==61 and len(h)==61 else 'REJECT',
  'NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066':'ACCEPT' if native_exact==1066 and total==2440 else 'REJECT',
  'HYDROGEN_TYPE50_UNEXPLAINED_DELTAS_ZERO':'ACCEPT' if len(comparisons)==EXPECTED_ROWS and all(r['line_index_exact']=='1' if isinstance(r['line_index_exact'],str) else r['line_index_exact']==1 for r in comparisons) and all(r['tau_in_exact']==1 and r['tau_out_exact']==1 and r['ptmp1_exact']==1 and r['ptmp2_exact']==1 and r['answers_exact']==1 for r in comparisons) else 'REJECT',
 }
 errors.extend(k for k,v in gates.items() if v!='ACCEPT')
 summary=[]
 for call,info in call_counts.items(): summary.append({'call_index':call,**info})
 with (output/'v04874618_hydrogen_type50_family_summary.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['call_index','rows','exact']); w.writeheader(); w.writerows(summary)
 report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if not errors else 'REJECT','errors':errors,'gates':gates,'source_rows':len(src),'native_rows':len(native),'comparison_rows':len(comparisons),'line_indices_exact':counts['line'],'tau_values_exact':counts['tau_in']+counts['tau_out'],'escape_factors_exact':counts['ptmp1']+counts['ptmp2'],'answers_exact_records':counts['answers'],'h_cooling_exact':h_exact,'h_cooling_total':len(h),'native_computed_values_exact':native_exact,'native_computed_values_total':total,'call_summary':summary,'qualification_only':True,'production_promotion_ready':False}
 return report
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--source-capture',type=Path,required=True); p.add_argument('--native-run',type=Path,required=True); p.add_argument('--component-comparison',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--output-json',type=Path,required=True); a=p.parse_args(argv)
 try:r=audit(a.source_capture.resolve(),a.native_run.resolve(),a.component_comparison.resolve(),a.output.resolve())
 except Exception as exc:r={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(exc)],'gates':{},'qualification_only':True,'production_promotion_ready':False}
 write_json(a.output_json,r); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r['result']=='ACCEPT' else 2
if __name__=='__main__': raise SystemExit(main())
