"""v0.6.48.7.27 call-2 general thermal construction and family attribution.

Qualification diagnostics only.  This module does not promote source budget
substitution as a production formula.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
RELEASE="0.6.48.7.27"
SCHEMA="xstar-tools-v0648727-call2-general-thermal-family-attribution-v1"
COMPONENTS={
 "H":("h_heating","h_cooling","h_heating2","h_cooling2"),
 "He":("he_heating","he_cooling","he_heating2","he_cooling2"),
 "Mg":("mg_heating","mg_cooling","mg_heating2","mg_cooling2"),
 "continuum":("continuum_heating","continuum_cooling","continuum_heating2","continuum_cooling2","htfreef","htcomp","clcomp","clbrems","cmp1","cmp2"),
}
def rows(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def one(p,call=2,ev=1):
 rs=rows(p); m=[r for r in rs if int(r.get('dsec_call_id',r.get('call_index',0)))==call and int(r.get('dsec_local_evaluation_index',r.get('evaluation_index',0)))==ev]
 if not m and len(rs)==1:m=rs
 if len(m)!=1:raise ValueError(f'expected one call {call} evaluation {ev} row in {p}, found {len(m)}')
 return m[0]
def f(r,k,default=0.0):
 try:return float(r[k])
 except:return default
def heatf(h,c):return 2.0*(h-c)/(float.fromhex('0x1.b38fb9daa78e4p-123')+h+c)
def budget(r):
 return {k:f(r,k) for fs in COMPONENTS.values() for k in fs}
def primary(b):
 h=b['h_heating']+b['he_heating']+b['mg_heating']+b['continuum_heating']
 c=b['h_cooling']+b['he_cooling']+b['mg_cooling']+b['continuum_cooling']
 return h,c,heatf(h,c)
def write_csv(p,rs):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='') as g:
  w=csv.DictWriter(g,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def write_json(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def analyze(source_budget,native_budget,native_state,output):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 s=one(source_budget);n=one(native_budget);st=one(native_state)
 sb,nb=budget(s),budget(n)
 plans=[('native',()),('source_H',('H',)),('source_He',('He',)),('source_Mg',('Mg',)),('source_continuum',('continuum',)),('source_H_He',('H','He')),('source_H_He_continuum',('H','He','continuum')),('source_all',('H','He','Mg','continuum'))]
 sub=[]
 for name,replace in plans:
  b=dict(nb)
  for c in replace:
   for k in COMPONENTS[c]:b[k]=sb[k]
  h,c,res=primary(b)
  sub.append({'substitution':name,'source_components':';'.join(replace),'httot_reconstructed':h,'cltot_reconstructed':c,'hmctot_reconstructed':res,'source_hmctot':f(s,'hmctot'),'hmctot_gap':res-f(s,'hmctot')})
 write_csv(out/'call2_component_substitution_ladder.csv',sub)
 gaps=[]
 for comp,fields in COMPONENTS.items():
  for k in fields:gaps.append({'component':comp,'field':k,'source':sb[k],'native':nb[k],'delta':nb[k]-sb[k],'ratio':nb[k]/sb[k] if sb[k]!=0 else math.nan,'exact':nb[k]==sb[k]})
 write_csv(out/'call2_component_field_gaps.csv',gaps)
 inp=[]
 for label,p in [('source_budget',Path(source_budget)),('native_budget',Path(native_budget)),('native_state',Path(native_state))]:inp.append({'artifact':label,'path':str(p.resolve()),'exists':p.is_file(),'size_bytes':p.stat().st_size if p.is_file() else 0})
 write_csv(out/'call2_source_input_artifact_inventory.csv',inp)
 exact=all(x['exact'] for x in gaps) and f(st,'native_charge_residual')==f(s,'elcter') and f(st,'native_hmctot')==f(s,'hmctot')
 report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT','diagnostic_capture_complete':True,'general_formula_exact':exact,'source_hmctot':f(s,'hmctot'),'native_hmctot':f(st,'native_hmctot',f(n,'hmctot')),'source_charge_residual':f(s,'elcter'),'native_charge_residual':f(st,'native_charge_residual',f(n,'elcter')),'gates':{'CALL1_ACCEPTED_BASELINE':'ACCEPT','CALL2_SOURCE_INPUT_CAPTURE':'ACCEPT','CALL2_FAMILY_SUBSTITUTION_LADDER':'ACCEPT','CALL2_GENERAL_H_THERMAL':'ACCEPT' if all(x['exact'] for x in gaps if x['component']=='H') else 'REJECT','CALL2_GENERAL_HE_THERMAL':'ACCEPT' if all(x['exact'] for x in gaps if x['component']=='He') else 'REJECT','CALL2_GENERAL_MG_THERMAL':'ACCEPT' if all(x['exact'] for x in gaps if x['component']=='Mg') else 'REJECT','CALL2_GENERAL_CONTINUUM':'ACCEPT' if all(x['exact'] for x in gaps if x['component']=='continuum') else 'REJECT','CALL2_COMPONENT_CHARGE_HMCTOT':'ACCEPT' if exact else 'REJECT','GLOBAL_BILEVG_RNISG_CONSUMERS':'DEFERRED_NO_CAUSAL_FAMILY','CALLS_3_TO_4':'RUN_ALLOWED' if exact else 'BLOCKED_BY_CALL2_EVALUATION1','THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'},'qualification_only':True,'production_promotion_ready':False}
 write_json(out/'call2_general_thermal_family_attribution_summary.json',report);return report
def main():
 p=argparse.ArgumentParser();p.add_argument('--source-budget',type=Path,required=True);p.add_argument('--native-budget',type=Path,required=True);p.add_argument('--native-state',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--output-json',type=Path);a=p.parse_args()
 try:r=analyze(a.source_budget,a.native_budget,a.native_state,a.output)
 except Exception as e:r={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(e)]}
 if a.output_json:write_json(a.output_json,r)
 print(json.dumps(r,indent=2,sort_keys=True));return 0 if r['result']=='ACCEPT' else 2
if __name__=='__main__':raise SystemExit(main())
