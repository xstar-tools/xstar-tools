"""v0.6.48.7.30 call-2 helium population-seed correction audit."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
RELEASE='0.6.48.7.30'
SCHEMA='xstar-tools-v0648730-call2-helium-population-seed-correction-v1'
def read_csv(p):
    with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def num(r,k,d=math.nan):
    try:return float(r.get(k,d))
    except:return d
def integer(r,k,d=0):
    try:return int(float(r.get(k,d)))
    except:return d
def write_csv(p,rows,fields):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-capture',type=Path,required=True);ap.add_argument('--native-replay',type=Path,required=True);ap.add_argument('--prior-summary',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    src=read_csv(a.source_capture/'v0472_call2_eval1_he_populations.csv')
    pops=read_csv(a.native_replay/'diagnostics/evaluation_0022_populations.csv')
    solve=read_csv(a.native_replay/'diagnostics/evaluation_0022_helium_solve_rows.csv')
    he=[r for r in pops if integer(r,'element_z')==2]
    sm={integer(r,'element_row'):r for r in src}; hm={integer(r,'element_row'):r for r in he}; sol={integer(r,'full_row'):r for r in solve}
    ledger=[]
    for row in sorted(sm):
        s=sm[row];n=hm.get(row,{});q=sol.get(row,{})
        source=num(s,'population_after_solve'); loaded=num(q,'initial_population',num(n,'initial_population')); final=num(q,'final_population',num(n,'final_population'))
        ledger.append({'element_row':row,'global_level_index':integer(n,'global_population_row'),'compact_row':integer(q,'compact_row'),'ion':integer(n,'ion'),'ion_charge':integer(n,'ion_charge'),'source_xilevg':source,'loaded_xilevg':loaded,'native_pre_solve_population':loaded,'native_post_solve_population':final,'seed_applied':int(math.isfinite(loaded) and loaded!=0.0),'pre_solve_exact':loaded==source,'post_solve_exact':final==source,'normalization_row':integer(q,'is_normalization_row')})
    write_csv(a.output/'call2_he_population_seed_transport_ledger.csv',ledger,list(ledger[0]))
    prior=json.loads(a.prior_summary.read_text());pg=prior.get('gates',{})
    baseline=prior.get('result')=='ACCEPT' and pg.get('CALL2_HE_78_ROW_MAPPING')=='ACCEPT'; mapped=len(ledger)==78 and len(solve)>0
    pre=mapped and all(r['pre_solve_exact'] for r in ledger); post=mapped and all(r['post_solve_exact'] for r in ledger)
    gates={'CALL1_ACCEPTED_BASELINE':'ACCEPT' if baseline else 'REJECT','CALL2_HE_SEED_TRANSPORT_LEDGER':'ACCEPT' if mapped else 'REJECT','CALL2_HE_GLOBAL_XILEVG_MAPPING':'ACCEPT' if mapped and all(r['global_level_index']>0 for r in ledger) else 'REJECT','CALL2_HE_PRE_SOLVE_POPULATION_EXACT':'ACCEPT' if pre else 'REJECT','CALL2_HE_POST_SOLVE_POPULATION_EXACT':'ACCEPT' if post else 'REJECT','CALL2_HE_GENUINE_NATIVE_INITIALIZATION_CORRECTION':'ACCEPT' if pre else 'REJECT','CALL2_HE_RATE_EVALUATION':'RUN_ALLOWED' if pre else 'BLOCKED_BY_POPULATION_INITIALIZATION','CALL2_HE_MATRIX_THERMAL_ACCUMULATION':'RUN_ALLOWED' if pre else 'BLOCKED_BY_POPULATION_INITIALIZATION','CALL2_GENERAL_HE_THERMAL':'RUN_ALLOWED' if pre else 'BLOCKED_BY_POPULATION_INITIALIZATION','CALLS_3_TO_4':'BLOCKED_BY_CALL2_HELIUM','THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'}
    core=baseline and mapped
    report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if core else 'REJECT','rows':len(ledger),'seed_rows_nonzero':sum(r['seed_applied'] for r in ledger),'pre_solve_exact_rows':sum(r['pre_solve_exact'] for r in ledger),'post_solve_exact_rows':sum(r['post_solve_exact'] for r in ledger),'gates':gates,'qualification_only':True,'production_promotion_ready':False}
    (a.output/'call2_helium_population_seed_correction_summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2,sort_keys=True));return 0 if core else 2
if __name__=='__main__':raise SystemExit(main())
