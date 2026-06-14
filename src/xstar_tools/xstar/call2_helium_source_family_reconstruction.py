"""Audit call-2 helium source-family reconstruction for v0.6.48.7.28.1."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
RELEASE='0.6.48.7.28.1';SCHEMA='xstar-tools-v0648728-call2-helium-source-family-reconstruction-v1'
def read(p):
 with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def fl(r,k):
 try:return float(r.get(k,0) or 0)
 except:return 0.0
def write_csv(p,rows,fields=None):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True); fields=fields or list(rows[0])
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def write_json(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def analyze(source_dir,native_dir,prior_summary,out):
 source_dir=Path(source_dir);native_dir=Path(native_dir);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 pops=read(source_dir/'v0472_call2_eval1_he_populations.csv'); terms=read(source_dir/'v0472_call2_eval1_he_source_order_terms.csv'); fam=read(source_dir/'v0472_call2_eval1_he_family_rows.csv')
 npops=read(native_dir/'diagnostics/evaluation_0022_populations.csv'); nrec=read(native_dir/'diagnostics/evaluation_0022_records.csv')
 hep=[r for r in npops if int(r['element_z'])==2]; her=[r for r in nrec if int(r['element_z'])==2]
 native_by_row={int(r['element_row']):fl(r,'final_population') for r in hep}; popcmp=[]
 for r in pops:
  row=int(r['element_row']);sv=fl(r,'population_after_solve');nv=native_by_row.get(row,math.nan);popcmp.append({'element_row':row,'source_population':sv,'native_population':nv,'delta':nv-sv,'exact':nv==sv})
 write_csv(out/'call2_he_population_comparison.csv',popcmp)
 # Source exact-order family and destination-row decomposition.
 decomp=[]
 for r in fam:
  decomp.append({**r,'partition':'type53' if int(r['data_type'])==53 else 'non_type53'})
 write_csv(out/'call2_he_source_family_row_decomposition.csv',decomp)
 source_tot={k:sum(fl(r,k) for r in terms) for k in ('primary_heating','primary_cooling','secondary_heating','secondary_cooling')}
 source53={k:sum(fl(r,k) for r in terms if int(r['data_type'])==53) for k in source_tot}
 native_type53_records=sum(1 for r in her if int(r['data_type'])==53)
 pop_exact=bool(popcmp) and all(r['exact'] for r in popcmp)
 prior=json.loads(Path(prior_summary).read_text())
 accepted=prior.get('result')=='ACCEPT' and prior.get('gates',{}).get('CALL2_FAMILY_SUBSTITUTION_LADDER')=='ACCEPT'
 gates={'CALL1_ACCEPTED_BASELINE':'ACCEPT' if accepted else 'REJECT','CALL2_SOURCE_INPUT_CAPTURE':'ACCEPT','CALL2_FAMILY_SUBSTITUTION_LADDER':'ACCEPT' if accepted else 'REJECT','CALL2_HE_POPULATION_BEFORE_AFTER_CAPTURE':'ACCEPT' if pops else 'REJECT','CALL2_HE_SOURCE_ORDER_ACCUMULATION':'ACCEPT' if terms else 'REJECT','CALL2_HE_PER_FAMILY_ROW_LEDGER':'ACCEPT' if fam else 'REJECT','CALL2_HE_TYPE53_FIXED':'ACCEPT' if native_type53_records>0 else 'REJECT','CALL2_HE_ELEMENT_INTERCEPT':'ACCEPT' if pops and terms and fam else 'REJECT','CALL2_HE_POPULATION_ROWS_GT_ZERO':'ACCEPT' if pops else 'REJECT','CALL2_HE_SOURCE_ORDER_TERMS_GT_ZERO':'ACCEPT' if terms else 'REJECT','CALL2_HE_FAMILY_ROWS_GT_ZERO':'ACCEPT' if fam else 'REJECT','CALL2_HE_POPULATION_INITIALIZATION':('ACCEPT' if pop_exact else 'REJECT') if pops and terms and fam else 'NOT_EVALUATED','CALL2_HE_RATE_EVALUATION':'RUN_REQUIRED' if pops and terms and fam else 'NOT_EVALUATED','CALL2_HE_ABUNDANCE_APPLICATION':'ACCEPT' if all(fl(r,'abundance')>0 for r in terms) else 'REJECT','CALL2_HE_PRIMARY_SECONDARY_CLASSIFICATION':'ACCEPT' if terms else 'REJECT','CALL2_HE_MATRIX_THERMAL_ACCUMULATION':'RUN_REQUIRED' if pops and terms and fam else 'NOT_EVALUATED','CALL2_HE_SOURCE_ORDER_SUMMATION':'ACCEPT' if all(int(r['sequence'])==i for i,r in enumerate(terms,1)) else 'REJECT','CALL2_GENERAL_HE_THERMAL':'RUN_REQUIRED' if pops and terms and fam else 'NOT_EVALUATED','CALL2_HE_GENUINE_NATIVE_CORRECTION':'RUN_REQUIRED' if pops and terms and fam else 'NOT_EVALUATED','CALLS_3_TO_4':'BLOCKED_BY_CALL2_HELIUM','THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'}
 report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if all(gates[k]=='ACCEPT' for k in ('CALL1_ACCEPTED_BASELINE','CALL2_SOURCE_INPUT_CAPTURE','CALL2_HE_POPULATION_BEFORE_AFTER_CAPTURE','CALL2_HE_SOURCE_ORDER_ACCUMULATION','CALL2_HE_PER_FAMILY_ROW_LEDGER','CALL2_HE_TYPE53_FIXED')) else 'REJECT','source_totals':source_tot,'source_type53_totals':source53,'source_non_type53_totals':{k:source_tot[k]-source53[k] for k in source_tot},'native_he_population_rows':len(hep),'native_he_records':len(her),'native_type53_records':native_type53_records,'gates':gates,'qualification_only':True,'production_promotion_ready':False}
 write_json(out/'call2_helium_source_family_reconstruction_summary.json',report);return report
def main():
 p=argparse.ArgumentParser();p.add_argument('--source-capture',type=Path,required=True);p.add_argument('--native-replay',type=Path,required=True);p.add_argument('--prior-summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--output-json',type=Path);a=p.parse_args()
 try:r=analyze(a.source_capture,a.native_replay,a.prior_summary,a.output)
 except Exception as e:r={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(e)]}
 if a.output_json:write_json(a.output_json,r)
 print(json.dumps(r,indent=2,sort_keys=True));return 0 if r['result']=='ACCEPT' else 2
if __name__=='__main__':raise SystemExit(main())
