"""v0.6.48.7.30.3 He II boundary-row mapping completion audit."""
from __future__ import annotations
import argparse,csv,json,math,struct
from pathlib import Path
RELEASE='0.6.48.7.30.3'
SCHEMA='xstar-tools-v06487303-heii-boundary-row-mapping-completion-v1'
def read_csv(p):
    with Path(p).open(newline='') as f:return list(csv.DictReader(f))
def num(r,k,d=math.nan):
    try:return float(r.get(k,d))
    except:return d
def integer(r,k,d=0):
    try:return int(float(r.get(k,d)))
    except:return d
def read_f64_vector(p):
    b=Path(p).read_bytes()
    if len(b)%8: raise ValueError(f'invalid float64 payload size: {p}')
    return list(struct.unpack(f'={len(b)//8}d',b))
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
        source_g=integer(n,'global_population_row'); loaded_g=integer(q,'loaded_global_level_index')
        source_seed=call_start[source_g-1] if 0<source_g<=len(call_start) else math.nan
        loaded=num(q,'loaded_call_start_xilevg'); final=num(q,'final_population',num(n,'final_population'))
        source_post=num(s,'population_after_solve')
        ledger.append({'element_row':row,'ion':integer(n,'ion'),'compact_row':integer(q,'compact_row'),
          'source_global_level_index':source_g,'native_loaded_global_level_index':loaded_g,
          'source_call_start_xilevg':source_seed,'native_loaded_call_start_xilevg':loaded,
          'mapping_exact':source_g==loaded_g,'seed_transport_exact':math.isfinite(source_seed) and loaded==source_seed,
          'source_post_solve_population':source_post,'native_post_solve_population':final,
          'post_solve_exact':math.isfinite(source_post) and final==source_post,
          'normalization_row':integer(q,'is_normalization_row')})
    write_csv(a.output/'call2_he_boundary_row_mapping_ledger.csv',ledger,list(ledger[0]) if ledger else [])
    prior=json.loads(a.prior_summary.read_text()); pg=prior.get('gates',{})
    baseline=prior.get('result')=='ACCEPT' and pg.get('CALL2_HE_CALL_START_SEED_PHASE')=='ACCEPT'
    rows_ok=len(ledger)==78
    mapping=rows_ok and all(r['mapping_exact'] for r in ledger)
    seed=rows_ok and all(r['seed_transport_exact'] for r in ledger)
    he1=rows_ok and all(r['source_global_level_index']==33+r['element_row'] for r in ledger if r['element_row']<=45)
    he2=rows_ok and all(r['source_global_level_index']==33+r['element_row'] for r in ledger if r['element_row']>=46)
    normalization=rows_ok and ledger[-1]['source_global_level_index']==111 and ledger[-1]['native_loaded_global_level_index']==111
    post=rows_ok and all(r['post_solve_exact'] for r in ledger)
    gates={
      'CALL1_ACCEPTED_BASELINE':'ACCEPT' if baseline else 'REJECT',
      'CALL2_HE_78_ROW_MAPPING':'ACCEPT' if rows_ok else 'REJECT',
      'CALL2_HE_I_GLOBAL_LEVEL_MAPPING':'ACCEPT' if he1 else 'REJECT',
      'CALL2_HE_II_GLOBAL_LEVEL_MAPPING':'ACCEPT' if he2 else 'REJECT',
      'CALL2_HE_NORMALIZATION_ROW_GLOBAL_LEVEL_111':'ACCEPT' if normalization else 'REJECT',
      'CALL2_HE_GLOBAL_XILEVG_MAPPING':'ACCEPT' if mapping else 'REJECT',
      'CALL2_HE_SEED_TRANSPORT_EXACT':'ACCEPT' if seed else 'REJECT',
      'CALL2_HE_POST_SOLVE_POPULATION_EXACT':'ACCEPT' if post else 'REJECT',
      'CALL2_HE_GENUINE_NATIVE_INITIALIZATION_CORRECTION':'ACCEPT' if mapping and seed else 'REJECT',
      'CALL2_HE_RATE_EVALUATION':'RUN_ALLOWED' if mapping and seed else 'BLOCKED_BY_SEED_TRANSPORT',
      'CALL2_HE_MATRIX_THERMAL_ACCUMULATION':'RUN_ALLOWED' if mapping and seed else 'BLOCKED_BY_SEED_TRANSPORT',
      'CALL2_GENERAL_HE_THERMAL':'RUN_ALLOWED' if mapping and seed else 'BLOCKED_BY_SEED_TRANSPORT',
      'CALLS_3_TO_4':'BLOCKED_BY_CALL2_HELIUM','THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'}
    core=baseline and rows_ok and mapping and seed
    report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if core else 'REJECT','rows':len(ledger),
      'mapping_exact_rows':sum(r['mapping_exact'] for r in ledger),'seed_transport_exact_rows':sum(r['seed_transport_exact'] for r in ledger),
      'post_solve_exact_rows':sum(r['post_solve_exact'] for r in ledger),'gates':gates,
      'qualification_only':True,'production_promotion_ready':False}
    (a.output/'call2_helium_boundary_row_mapping_completion_summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True));return 0 if core else 2
if __name__=='__main__':raise SystemExit(main())
