"""v0.6.48.7.31.1 call-2 helium solve-state and rate-matrix decomposition."""
from __future__ import annotations
import argparse, csv, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any

RELEASE="0.6.48.7.31.1"
SCHEMA="xstar-tools-v06487311-call2-helium-solve-state-rate-matrix-decomposition-v1"

def read_csv(path: Path) -> list[dict[str,str]]:
    with path.open(newline='') as f: return list(csv.DictReader(f))

def f(row: dict[str,str], key: str, default: float=math.nan) -> float:
    try: return float(row.get(key,default))
    except (TypeError,ValueError): return default

def i(row: dict[str,str], key: str, default: int=0) -> int:
    try: return int(float(row.get(key,default)))
    except (TypeError,ValueError): return default

def write_csv(path: Path, rows: list[dict[str,Any]]) -> None:
    fields=[]
    for row in rows:
        for key in row:
            if key not in fields: fields.append(key)
    with path.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def role(value: str) -> str:
    return {'forward_offdiag':'forward_gain','reverse_offdiag':'reverse_gain'}.get(value,value)

def exact(a: float,b: float) -> bool: return math.isfinite(a) and math.isfinite(b) and a==b

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--source-capture',type=Path,required=True); p.add_argument('--native-replay',type=Path,required=True); p.add_argument('--prior-summary',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    source_report=json.loads((a.source_capture/'v0472_call2_eval1_he_solve_capture_report.json').read_text())
    prior=json.loads(a.prior_summary.read_text()); pg=prior.get('gates',{})
    source_rows=read_csv(a.source_capture/'v0472_call2_eval1_he_solve_rows.csv')
    source_matrix=read_csv(a.source_capture/'v0472_call2_eval1_he_solve_matrix.csv')
    source_terms=read_csv(a.source_capture/'v0472_call2_eval1_he_source_order_matrix_terms.csv')
    native_rows=read_csv(a.native_replay/'diagnostics/evaluation_0022_helium_solve_rows.csv')
    native_matrix=read_csv(a.native_replay/'diagnostics/evaluation_0022_helium_solve_matrix.csv')
    native_terms=read_csv(a.native_replay/'diagnostics/evaluation_0022_helium_source_order_terms.csv')
    native_state=json.loads((a.native_replay/'diagnostics/evaluation_0022_helium_solve_state.json').read_text())
    outer_trace=read_csv(a.source_capture/'v0472_call2_eval1_he_outer_level_trace.csv')
    fixed_trace=read_csv(a.source_capture/'v0472_call2_eval1_he_fixed_point_trace.csv')

    sr={i(r,'element_row'):r for r in source_rows}; nr={i(r,'full_row'):r for r in native_rows}
    row_cmp=[]
    for row_id in sorted(sr):
        s=sr[row_id]; n=nr.get(row_id,{})
        sinit=f(s,'transformed_initial_population'); ninit=f(n,'initial_population')
        souter=f(s,'final_outer_start_population'); nouter=f(n,'final_outer_start_population')
        sfinal=f(s,'final_population'); nfinal=f(n,'final_population')
        srhs=f(s,'rhs'); nrhs=f(n,'rhs')
        row_cmp.append({'element_row':row_id,'ion':i(s,'ion'),'is_normalization_row':i(s,'is_normalization_row'),
            'source_transformed_initial':sinit,'native_transformed_initial':ninit,'transformed_initial_exact':exact(sinit,ninit),
            'source_rhs':srhs,'native_rhs':nrhs,'rhs_exact':exact(srhs,nrhs),
            'source_final_outer_start':souter,'native_final_outer_start':nouter,'final_outer_start_exact':exact(souter,nouter),
            'source_final_population':sfinal,'native_final_population':nfinal,'post_solve_exact':exact(sfinal,nfinal)})
    write_csv(a.output/'call2_he_solve_state_comparison.csv',row_cmp)

    sm={(i(r,'compact_row'),i(r,'compact_column')):r for r in source_matrix}; nm={(i(r,'compact_row'),i(r,'compact_column')):r for r in native_matrix}
    matrix_cmp=[]
    for key in sorted(sm):
        s=sm[key]; n=nm.get(key,{})
        sd=f(s,'dense_value'); nd=f(n,'dense_value'); sh=f(s,'heating_value'); nh=f(n,'heating_value'); sh2=f(s,'heating2_value'); nh2=f(n,'heating2_value')
        matrix_cmp.append({'compact_row':key[0],'compact_column':key[1],'source_dense':sd,'native_dense':nd,'dense_exact':exact(sd,nd),
            'dense_abs_delta':abs(nd-sd) if math.isfinite(sd) and math.isfinite(nd) else math.inf,
            'source_heating_matrix':sh,'native_heating_matrix':nh,'heating_exact':exact(sh,nh),
            'source_heating2_matrix':sh2,'native_heating2_matrix':nh2,'heating2_exact':exact(sh2,nh2)})
    write_csv(a.output/'call2_he_dense_matrix_comparison.csv',matrix_cmp)

    nt={i(r,'source_order_index'):r for r in native_terms}; term_cmp=[]; family=defaultdict(lambda:{'terms':0,'metadata_mismatches':0,'aj1_mismatches':0,'aj2_mismatches':0,'cj_mismatches':0,'cj2_mismatches':0,'max_abs_delta':0.0})
    for s in source_terms:
        order=i(s,'source_order_index'); n=nt.get(order,{})
        dtype=i(s,'data_type'); dest=i(s,'compact_row'); bucket=family[(dtype,dest)]
        meta=(i(s,'term_index')==i(n,'term_source_position') and i(s,'record')==i(n,'record') and dtype==i(n,'data_type') and i(s,'rate_type')==i(n,'rate_type') and role(s.get('role',''))==n.get('role','') and dest==i(n,'compact_row') and i(s,'compact_column')==i(n,'compact_column'))
        values={}
        for key in ('aj1','aj2','cj','cj2'):
            sv=f(s,key); nv=f(n,key); ok=exact(sv,nv); delta=abs(nv-sv) if math.isfinite(sv) and math.isfinite(nv) else math.inf
            values[f'source_{key}']=sv; values[f'native_{key}']=nv; values[f'{key}_exact']=ok; values[f'{key}_abs_delta']=delta
            if not ok: bucket[f'{key}_mismatches']+=1
            bucket['max_abs_delta']=max(bucket['max_abs_delta'],delta)
        bucket['terms']+=1
        if not meta: bucket['metadata_mismatches']+=1
        term_cmp.append({'source_order_index':order,'source_term_index':i(s,'term_index'),'native_term_source_position':i(n,'term_source_position'),
            'record':i(s,'record'),'data_type':dtype,'rate_type':i(s,'rate_type'),'role':role(s.get('role','')),
            'compact_row':dest,'compact_column':i(s,'compact_column'),'metadata_exact':meta,'type53':1 if dtype==53 else 0,**values})
    write_csv(a.output/'call2_he_source_order_term_comparison.csv',term_cmp)
    family_rows=[]
    for (dtype,dest),b in sorted(family.items()):
        family_rows.append({'data_type':dtype,'destination_row':dest,'type53':1 if dtype==53 else 0,**b,
            'family_row_exact':b['metadata_mismatches']==0 and all(b[f'{x}_mismatches']==0 for x in ('aj1','aj2','cj','cj2'))})
    write_csv(a.output/'call2_he_rate_family_row_gaps.csv',family_rows)

    baseline=(prior.get('result')=='ACCEPT' and pg.get('CALL2_HE_78_ROW_MAPPING_EXACT')=='ACCEPT' and pg.get('CALL2_HE_SEED_TRANSPORT_EXACT')=='ACCEPT')
    capture=source_report.get('result')=='ACCEPT'
    transformed=len(row_cmp)==78 and all(r['transformed_initial_exact'] for r in row_cmp)
    rhs=len(row_cmp)==78 and all(r['rhs_exact'] for r in row_cmp)
    dense=len(matrix_cmp)==78*78 and all(r['dense_exact'] for r in matrix_cmp)
    term_metadata=len(term_cmp)>0 and len(term_cmp)==len(native_terms) and all(r['metadata_exact'] for r in term_cmp)
    rate_coeff=term_metadata and all(all(r[f'{x}_exact'] for x in ('aj1','aj2','cj','cj2')) for r in term_cmp)
    type53=all(r['metadata_exact'] and all(r[f'{x}_exact'] for x in ('aj1','aj2','cj','cj2')) for r in term_cmp if r['type53']) and any(r['type53'] for r in term_cmp)
    type_gates={}
    for dtype in (50,71,99):
        rows=[r for r in term_cmp if r['data_type']==dtype]
        type_gates[dtype]=bool(rows) and all(r['metadata_exact'] and all(r[f'{x}_exact'] for x in ('aj1','aj2','cj','cj2')) for r in rows)
    post=len(row_cmp)==78 and all(r['post_solve_exact'] for r in row_cmp)
    outer=len(row_cmp)==78 and all(r['final_outer_start_exact'] for r in row_cmp)
    source_trace=bool(outer_trace) and bool(fixed_trace)
    matrix_ready=transformed and rhs and dense and term_metadata
    gates={
        'CALL1_ACCEPTED_BASELINE':'ACCEPT' if baseline else 'REJECT',
        'CALL2_HE_SOURCE_SOLVE_STATE_CAPTURE':'ACCEPT' if capture else 'REJECT',
        'CALL2_HE_SOURCE_ITERATION_TRACE':'ACCEPT' if source_trace else 'REJECT',
        'CALL2_HE_TRANSFORMED_INITIAL_STATE':'ACCEPT' if transformed else 'REJECT',
        'CALL2_HE_RHS_CONSTRUCTION':'ACCEPT' if rhs else 'REJECT',
        'CALL2_HE_DENSE_MATRIX_ASSEMBLY':'ACCEPT' if dense else 'REJECT',
        'CALL2_HE_SOURCE_ORDER_TERM_METADATA':'ACCEPT' if term_metadata else 'REJECT',
        'CALL2_HE_TYPE53_MATRIX_FIXED':'ACCEPT' if type53 else 'REJECT',
        'CALL2_HE_TYPE50_RATE_MATRIX':'ACCEPT' if type_gates[50] else 'REJECT',
        'CALL2_HE_TYPE71_RATE_MATRIX':'ACCEPT' if type_gates[71] else 'REJECT',
        'CALL2_HE_TYPE99_RATE_MATRIX':'ACCEPT' if type_gates[99] else 'REJECT',
        'CALL2_HE_RATE_EVALUATION':'ACCEPT' if rate_coeff else 'REJECT',
        'CALL2_HE_MATRIX_SYSTEM_READY':'ACCEPT' if matrix_ready else 'REJECT',
        'CALL2_HE_FINAL_OUTER_START_STATE':'ACCEPT' if outer else ('REJECT' if matrix_ready else 'BLOCKED_BY_MATRIX_SYSTEM'),
        'CALL2_HE_POST_SOLVE_POPULATION_EXACT':'ACCEPT' if post else ('REJECT' if matrix_ready else 'BLOCKED_BY_MATRIX_SYSTEM'),
        'CALL2_HE_NATIVE_ITERATION_TRACE':'NOT_CAPTURED_NATIVE_ABI',
        'CALL2_HE_SOLVER_NORMALIZATION':'RUN_ALLOWED' if matrix_ready else 'BLOCKED_BY_MATRIX_SYSTEM',
        'CALL2_HE_MATRIX_THERMAL_ACCUMULATION':'RUN_ALLOWED' if rate_coeff else 'BLOCKED_BY_RATE_MATRIX',
        'CALL2_GENERAL_HE_THERMAL':'BLOCKED_BY_POST_SOLVE_POPULATION' if not post else 'RUN_ALLOWED',
        'CALLS_3_TO_4':'BLOCKED_BY_CALL2_HELIUM','THERMAL_PARITY':'BLOCKED','PRODUCT_PARITY':'BLOCKED','PRODUCTION_PROMOTION':'BLOCKED'}
    core=baseline and capture and source_trace and len(row_cmp)==78 and len(matrix_cmp)==78*78 and len(term_cmp)>0
    report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if core else 'REJECT','rows':len(row_cmp),'matrix_cells':len(matrix_cmp),'source_order_terms':len(term_cmp),
        'transformed_initial_exact_rows':sum(r['transformed_initial_exact'] for r in row_cmp),'rhs_exact_rows':sum(r['rhs_exact'] for r in row_cmp),
        'dense_matrix_exact_cells':sum(r['dense_exact'] for r in matrix_cmp),'post_solve_exact_rows':sum(r['post_solve_exact'] for r in row_cmp),
        'outer_trace_rows':len(outer_trace),'fixed_point_trace_rows':len(fixed_trace),'native_solver_method':native_state.get('solver_method'),
        'gates':gates,'qualification_only':True,'production_promotion_ready':False}
    (a.output/'call2_helium_solve_state_rate_matrix_decomposition_summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True)); return 0 if core else 2
if __name__=='__main__': raise SystemExit(main())
