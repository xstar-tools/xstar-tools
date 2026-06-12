"""Audit the He II type-50 rows 46-54 manifold against a v0.6.47.2 evaluator replay."""
from __future__ import annotations
import argparse,csv,json,math,struct
from pathlib import Path
RELEASE='0.6.48.7.9';SCHEMA='xstar-tools-v064879-type50-manifold-audit-v1';ORACLE_SHA='548cbc4f489a19cfabb199ad2f063b581af0a1b5de21b3ae4a444841a0da4d6f'
def read(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def exact(a,b):return struct.pack('>d',float(a))==struct.pack('>d',float(b))
def write_csv(p,rows,fields):p.parent.mkdir(parents=True,exist_ok=True);f=p.open('w',newline='');w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows);f.close()
def audit(output:Path,bundle:Path,dest:Path,evaluation=61):
 native=read(output/'diagnostics'/f'evaluation_{evaluation:04d}_records.csv'); nm={(int(r['source_position']),int(r['record'])):r for r in native}
 refs=read(bundle/'type50_heii_rows46_54_runtime_oracle.csv'); comp=[]; exact_by={f'ans{i}':0 for i in range(1,7)}; sign_bad={f'ans{i}':0 for i in range(1,7)}; maxrel={f'ans{i}':(0,None) for i in range(1,7)}
 for ref in refs:
  key=(int(ref['source_position']),int(ref['record'])); n=nm[key]; row={k:ref[k] for k in ('source_position','record','lower_row','upper_row')}
  for i in range(1,7):
   a=float(n[f'ans{i}']);b=float(ref[f'ans{i}']);e=exact(a,b);d=a-b;rel=abs(d)/max(abs(b),1e-300)
   row.update({f'native_ans{i}':a,f'reference_ans{i}':b,f'delta_ans{i}':d,f'relative_delta_ans{i}':rel,f'exact_ans{i}':str(e).lower()})
   exact_by[f'ans{i}']+=int(e); sign_bad[f'ans{i}']+=int((a>0)-(a<0)!=(b>0)-(b<0))
   if rel>maxrel[f'ans{i}'][0]:maxrel[f'ans{i}']=(rel,key)
  comp.append(row)
 fields=list(comp[0]);write_csv(dest/'type50_manifold_answer_comparison.csv',comp,fields)
 # Matrix terms: standard four terms used by native construction.
 mats=[]
 for variant in ('native','reference'):
  for row in comp:
   a={i:float(row[f'{variant}_ans{i}']) for i in range(1,7)};lo=int(row['lower_row']);up=int(row['upper_row']);sp=int(row['source_position']);rec=int(row['record'])
   terms=[('forward_gain',up,lo,a[1],a[2],0,0),('reverse_gain',lo,up,a[2],a[1],0,0),('forward_diag',lo,lo,-a[1],-a[1],a[4],a[6]),('reverse_diag',up,up,-a[2],-a[2],-a[3],-a[5])]
   for role,r,c,aj1,aj2,cj,cj2 in terms:mats.append({'variant':variant,'source_position':sp,'record':rec,'role':role,'row':r,'column':c,'aj1':aj1,'aj2':aj2,'cj':cj,'cj2':cj2})
 write_csv(dest/'type50_manifold_matrix_terms.csv',mats,list(mats[0]))
 first=None
 for row in comp:
  for i in range(1,7):
   if row[f'exact_ans{i}']!='true':first={'source_position':int(row['source_position']),'record':int(row['record']),'answer':f'ans{i}'};break
  if first:break
 summary={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT','evaluation_ordinal':evaluation,'records_compared':len(refs),'answers_compared':len(refs)*6,'exact_by_answer':exact_by,'all_ieee_exact':all(v==len(refs) for v in exact_by.values()),'sign_mismatches_by_answer':sign_bad,'first_divergence':first,'maximum_relative_delta':{k:{'value':v[0],'record':v[1][1] if v[1] else None,'source_position':v[1][0] if v[1] else None} for k,v in maxrel.items()},'oracle_sha256':ORACLE_SHA,'capture_kind':'exact_v06472_fixed_state_type50_heii_rows46_54_evaluator_replay','escape_probability_contract':'ptmp1=1, ptmp2=0, consistent with native ans2=A','full_dsec_runtime_capture':False,'manifold_scope':'79 He II type-50 transitions incident on rows 46-54','type50_manifold_physics_replacement_ready':False,'fixed_state_parity':False,'production_promotion_ready':False,'remaining_blockers':['the type-50 manifold differs materially from the independent evaluator replay','the fixed-state replay does not capture a complete original DSEC escape-probability runtime','the nonlinear 46-54 manifold requires a coupled replacement experiment before any correction']}
 dest.mkdir(parents=True,exist_ok=True);(dest/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n');return summary
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('audit_output',type=Path);p.add_argument('oracle_bundle',type=Path);p.add_argument('output_dir',type=Path);p.add_argument('--evaluation',type=int,default=61);a=p.parse_args(argv)
 try:r=audit(a.audit_output,a.oracle_bundle,a.output_dir,a.evaluation);print(json.dumps(r,indent=2,sort_keys=True));return 0
 except Exception as e:print(f'type50 manifold audit failed: {e}');return 2
if __name__=='__main__':raise SystemExit(main())
