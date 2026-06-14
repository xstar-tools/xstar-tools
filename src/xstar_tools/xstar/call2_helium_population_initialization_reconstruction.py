"""Call-2 helium population-initialization reconstruction for v0.6.48.7.29."""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

RELEASE='0.6.48.7.29'
SCHEMA='xstar-tools-v0648729-call2-helium-population-initialization-reconstruction-v1'

def rows(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))
def f(row,key,default=0.0):
    try:return float(row.get(key,default) or default)
    except (TypeError,ValueError):return float(default)
def i(row,key,default=0):
    try:return int(float(row.get(key,default) or default))
    except (TypeError,ValueError):return int(default)
def dump_csv(path,data,fields):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(data)
def dump_json(path,obj):Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def thermal_from_terms(terms,population_by_row):
    out={k:0.0 for k in ('primary_heating','primary_cooling','secondary_heating','secondary_cooling')}
    for r in terms:
        row=i(r,'destination_row'); abundance=f(r,'abundance'); pop=population_by_row.get(row,f(r,'population'))
        wp=abundance*pop; cj=f(r,'cj'); cj2=f(r,'cj2')
        out['primary_heating'] += max(0.0,-wp*cj)
        out['primary_cooling'] += max(0.0, wp*cj)
        out['secondary_heating'] += max(0.0,-wp*cj2)
        out['secondary_cooling'] += max(0.0, wp*cj2)
    return out

def analyze(source_capture,native_replay,prior_summary,out):
    source_capture=Path(source_capture);native_replay=Path(native_replay);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    sp=rows(source_capture/'v0472_call2_eval1_he_populations.csv')
    st=rows(source_capture/'v0472_call2_eval1_he_source_order_terms.csv')
    np=rows(native_replay/'diagnostics/evaluation_0022_populations.csv')
    he=[r for r in np if i(r,'element_z')==2]
    source={i(r,'element_row'):r for r in sp}; native={i(r,'element_row'):r for r in he}
    comparison=[]
    for row in sorted(set(source)|set(native)):
        s=source.get(row,{});n=native.get(row,{})
        sv=f(s,'population_after_solve',math.nan); ni=f(n,'initial_population',math.nan); nf=f(n,'final_population',math.nan)
        ion=i(n,'ion',0); superlevel=i(n,'superlevel',row); active=i(n,'active_row',0)
        role='ground' if superlevel==1 else 'excited'
        if row not in native: cause='compact_row_omission'
        elif not math.isfinite(ni): cause='call_start_state_loading'
        elif ni==0.0 and sv!=0.0: cause='global_xilevg_mapping_or_zero_seed'
        elif nf!=sv: cause='post_load_solve_or_normalization'
        else: cause='exact'
        comparison.append({'element_row':row,'global_population_row':i(n,'global_population_row',0),'ion':ion,'ion_charge':i(n,'ion_charge',0),'superlevel':superlevel,'row_role':role,'active_row':active,'source_after_solve':sv,'native_initial':ni,'native_final':nf,'initial_delta':ni-sv if math.isfinite(ni) and math.isfinite(sv) else math.nan,'final_delta':nf-sv if math.isfinite(nf) and math.isfinite(sv) else math.nan,'initial_exact':ni==sv,'final_exact':nf==sv,'classification':cause})
    dump_csv(out/'call2_he_population_initialization_comparison.csv',comparison,list(comparison[0]))
    sums=defaultdict(lambda:{'source':0.0,'native_initial':0.0,'native_final':0.0,'rows':0})
    for r in comparison:
        key=(r['ion'],r['row_role']);g=sums[key];g['rows']+=1
        for src,dst in [('source_after_solve','source'),('native_initial','native_initial'),('native_final','native_final')]:
            v=r[src]
            if math.isfinite(v):g[dst]+=v
    sum_rows=[]
    for (ion,role),g in sorted(sums.items()):sum_rows.append({'ion':ion,'row_role':role,**g,'initial_delta':g['native_initial']-g['source'],'final_delta':g['native_final']-g['source']})
    dump_csv(out/'call2_he_population_sums_by_ion.csv',sum_rows,list(sum_rows[0]))
    source_pop={r['element_row']:r['source_after_solve'] for r in comparison if math.isfinite(r['source_after_solve'])}
    native_final={r['element_row']:r['native_final'] for r in comparison if math.isfinite(r['native_final'])}
    scenarios={}
    scenarios['native_final']=native_final
    scenarios['source_all']=source_pop
    for label,pred in {
        'source_ground_only':lambda r:r['row_role']=='ground',
        'source_excited_only':lambda r:r['row_role']=='excited',
        'source_he_i_only':lambda r:r['ion']==1,
        'source_he_ii_only':lambda r:r['ion']==2,
        'source_he_iii_only':lambda r:r['ion']==3,
    }.items():
        p=dict(native_final)
        for r in comparison:
            if pred(r) and math.isfinite(r['source_after_solve']):p[r['element_row']]=r['source_after_solve']
        scenarios[label]=p
    sub=[]
    source_tot=thermal_from_terms(st,source_pop)
    for name,pops in scenarios.items():
        totals=thermal_from_terms(st,pops)
        sub.append({'scenario':name,**totals,**{f'{k}_delta_from_source':totals[k]-source_tot[k] for k in source_tot}})
    dump_csv(out/'call2_he_population_substitution_ladder.csv',sub,list(sub[0]))
    prior=json.loads(Path(prior_summary).read_text()); pg=prior.get('gates',{})
    baseline=prior.get('result')=='ACCEPT' and pg.get('CALL2_HE_POPULATION_INITIALIZATION')=='REJECT'
    complete=len(sp)==78 and len(he)==78
    exact_initial=complete and all(r['initial_exact'] for r in comparison)
    exact_final=complete and all(r['final_exact'] for r in comparison)
    source_all_exact=all(x[f'{k}_delta_from_source']==0.0 for x in sub if x['scenario']=='source_all' for k in source_tot)
    gates={
      'CALL1_ACCEPTED_BASELINE':'ACCEPT' if baseline else 'REJECT',
      'CALL2_HE_RETAINED_SOURCE_CAPTURE':'ACCEPT' if len(sp)==78 and bool(st) else 'REJECT',
      'CALL2_HE_78_ROW_MAPPING':'ACCEPT' if complete else 'REJECT',
      'CALL2_HE_ION_STAGE_SUMS':'ACCEPT' if bool(sum_rows) else 'REJECT',
      'CALL2_HE_POPULATION_CLASSIFICATION':'ACCEPT' if complete else 'REJECT',
      'CALL2_HE_CONTROLLED_SUBSTITUTIONS':'ACCEPT' if source_all_exact else 'REJECT',
      'CALL2_HE_PRE_SOLVE_POPULATION_EXACT':'ACCEPT' if exact_initial else 'REJECT',
      'CALL2_HE_POST_SOLVE_POPULATION_EXACT':'ACCEPT' if exact_final else 'REJECT',
      'CALL2_HE_GENUINE_NATIVE_INITIALIZATION_CORRECTION':'RUN_REQUIRED',
      'CALL2_HE_RATE_EVALUATION':'BLOCKED_BY_POPULATION_INITIALIZATION',
      'CALL2_HE_MATRIX_THERMAL_ACCUMULATION':'BLOCKED_BY_POPULATION_INITIALIZATION',
      'CALL2_GENERAL_HE_THERMAL':'BLOCKED_BY_POPULATION_INITIALIZATION',
      'CALLS_3_TO_4':'BLOCKED_BY_CALL2_HELIUM',
      'THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'}
    core=all(gates[k]=='ACCEPT' for k in ('CALL1_ACCEPTED_BASELINE','CALL2_HE_RETAINED_SOURCE_CAPTURE','CALL2_HE_78_ROW_MAPPING','CALL2_HE_ION_STAGE_SUMS','CALL2_HE_POPULATION_CLASSIFICATION','CALL2_HE_CONTROLLED_SUBSTITUTIONS'))
    classes=defaultdict(int)
    for r in comparison:classes[r['classification']]+=1
    report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if core else 'REJECT','source_rows':len(sp),'native_rows':len(he),'population_class_counts':dict(classes),'source_thermal_totals':source_tot,'gates':gates,'qualification_only':True,'production_promotion_ready':False}
    dump_json(out/'call2_helium_population_initialization_reconstruction_summary.json',report)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-capture',type=Path,required=True);p.add_argument('--native-replay',type=Path,required=True);p.add_argument('--prior-summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--output-json',type=Path);a=p.parse_args()
    try:r=analyze(a.source_capture,a.native_replay,a.prior_summary,a.output)
    except Exception as e:r={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(e)]}
    if a.output_json:dump_json(a.output_json,r)
    print(json.dumps(r,indent=2,sort_keys=True));return 0 if r['result']=='ACCEPT' else 2
if __name__=='__main__':raise SystemExit(main())
