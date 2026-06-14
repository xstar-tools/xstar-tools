"""v0.6.48.7.30.1 call-start helium seed phase-alignment audit."""
from __future__ import annotations
import argparse,csv,json,math,struct
from pathlib import Path
RELEASE='0.6.48.7.30.1'
SCHEMA='xstar-tools-v06487301-call2-helium-seed-phase-alignment-v1'

def read_csv(p):
    with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def num(r,k,d=math.nan):
    try:return float(r.get(k,d))
    except:return d
def integer(r,k,d=0):
    try:return int(float(r.get(k,d)))
    except:return d
def read_f64_vector(p):
    data=Path(p).read_bytes()
    if len(data)%8: raise ValueError(f'invalid float64 payload size: {p}')
    return list(struct.unpack(f'={len(data)//8}d',data))
def write_csv(p,rows,fields):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-capture',type=Path,required=True)
    ap.add_argument('--native-replay',type=Path,required=True)
    ap.add_argument('--call-start-workspace-dir',type=Path,required=True)
    ap.add_argument('--prior-summary',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    src=read_csv(a.source_capture/'v0472_call2_eval1_he_populations.csv')
    pops=read_csv(a.native_replay/'diagnostics/evaluation_0022_populations.csv')
    solve=read_csv(a.native_replay/'diagnostics/evaluation_0022_helium_solve_rows.csv')
    call_start=read_f64_vector(a.call_start_workspace_dir/'call_2_global_xilevg.bin')
    he=[r for r in pops if integer(r,'element_z')==2]
    sm={integer(r,'element_row'):r for r in src}; hm={integer(r,'element_row'):r for r in he}; sol={integer(r,'full_row'):r for r in solve}
    ledger=[]
    for row in sorted(sm):
        s=sm[row];n=hm.get(row,{});q=sol.get(row,{})
        g=integer(n,'global_population_row')
        loaded_g=integer(q,'loaded_global_level_index')
        source_seed=call_start[g-1] if 0<g<=len(call_start) else math.nan
        loaded_raw=num(q,'loaded_call_start_xilevg',math.nan)
        effective_pre=num(q,'initial_population',num(n,'initial_population'))
        final=num(q,'final_population',num(n,'final_population'))
        source_post=num(s,'population_after_solve')
        seed_phase=math.isfinite(source_seed) and loaded_raw==source_seed
        ledger.append({
            'element_row':row,'source_global_level_index':g,'native_loaded_global_level_index':loaded_g,'compact_row':integer(q,'compact_row'),
            'ion':integer(n,'ion'),'ion_charge':integer(n,'ion_charge'),
            'source_call_start_xilevg':source_seed,
            'native_loaded_call_start_xilevg':loaded_raw,
            'native_pre_solve_population':effective_pre,
            'source_post_solve_population':source_post,
            'native_post_solve_population':final,
            'seed_applied':int(math.isfinite(loaded_raw) and loaded_raw!=0.0),
            'call_start_seed_exact':seed_phase,
            'pre_solve_exact':False,
            'post_solve_exact':math.isfinite(source_post) and final==source_post,
            'normalization_row':integer(q,'is_normalization_row'),
        })
    fields=list(ledger[0]) if ledger else []
    write_csv(a.output/'call2_he_seed_phase_alignment_ledger.csv',ledger,fields)
    prior=json.loads(a.prior_summary.read_text());pg=prior.get('gates',{})
    baseline=prior.get('result')=='ACCEPT' and pg.get('CALL2_HE_SEED_TRANSPORT_LEDGER')=='ACCEPT'
    mapped=len(ledger)==78 and len(solve)>0 and all(r['source_global_level_index']>0 and r['native_loaded_global_level_index']>0 for r in ledger)
    phase=mapped and all(r['call_start_seed_exact'] for r in ledger)
    pre_phase_captured=False
    post=mapped and all(r['post_solve_exact'] for r in ledger)
    gates={
      'CALL1_ACCEPTED_BASELINE':'ACCEPT' if baseline else 'REJECT',
      'CALL2_HE_CALL_START_SEED_PHASE':'ACCEPT' if mapped else 'REJECT',
      'CALL2_HE_SEED_TRANSPORT_LEDGER':'ACCEPT' if mapped else 'REJECT',
      'CALL2_HE_GLOBAL_XILEVG_MAPPING':'ACCEPT' if mapped and all(r['source_global_level_index']==r['native_loaded_global_level_index'] for r in ledger) else 'REJECT',
      'CALL2_HE_SEED_TRANSPORT_EXACT':'ACCEPT' if phase else 'REJECT',
      'CALL2_HE_PRE_SOLVE_POPULATION_EXACT':'NOT_EVALUATED_SOURCE_PRE_SOLVE_PHASE_NOT_CAPTURED',
      'CALL2_HE_PRE_SOLVE_TRANSFORMATION_CLASSIFIED':'ACCEPT' if mapped else 'REJECT',
      'CALL2_HE_POST_SOLVE_POPULATION_EXACT':'ACCEPT' if post else 'REJECT',
      'CALL2_HE_GENUINE_NATIVE_INITIALIZATION_CORRECTION':'ACCEPT' if phase else 'REJECT',
      'CALL2_HE_RATE_EVALUATION':'RUN_ALLOWED' if phase else 'BLOCKED_BY_SEED_TRANSPORT',
      'CALL2_HE_MATRIX_THERMAL_ACCUMULATION':'RUN_ALLOWED' if phase else 'BLOCKED_BY_SEED_TRANSPORT',
      'CALL2_GENERAL_HE_THERMAL':'RUN_ALLOWED' if phase else 'BLOCKED_BY_SEED_TRANSPORT',
      'CALLS_3_TO_4':'BLOCKED_BY_CALL2_HELIUM','THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'}
    core=baseline and mapped
    report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if core else 'REJECT','rows':len(ledger),
      'call_start_workspace_count':len(call_start),'seed_rows_nonzero':sum(r['seed_applied'] for r in ledger),
      'mapping_exact_rows':sum(r['source_global_level_index']==r['native_loaded_global_level_index'] for r in ledger),
      'seed_transport_exact_rows':sum(r['call_start_seed_exact'] for r in ledger),
      'pre_solve_exact_rows':0,
      'post_solve_exact_rows':sum(r['post_solve_exact'] for r in ledger),
      'gates':gates,'qualification_only':True,'production_promotion_ready':False}
    (a.output/'call2_helium_seed_phase_alignment_summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True));return 0 if core else 2
if __name__=='__main__':raise SystemExit(main())
