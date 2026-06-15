"""Capture v0.6.47.2 call-2/evaluation-1 helium solve state and matrix ledgers."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path
from typing import Any
from . import v0472_full_dsec_thermal_budget_capture as base
from . import v0472_thermal_budget_state_refresh_capture as low

RELEASE = "0.6.48.7.34"
SCHEMA = "xstar-tools-v0648734-v0472-call2-helium-solve-state-capture-v1"
REPORT = "v0472_call2_eval1_he_solve_capture_report.json"

_INJECT = r'''
_HE_SOLVE_ROWS=[]
_HE_SOLVE_MATRIX=[]
_HE_SOLVE_TERMS=[]
_HE_OUTER_TRACE=[]
_HE_SUPER_TRACE=[]
_HE_CONDENSED_TRACE=[]
_HE_FIXED_TRACE=[]
_HE_SOLVE_STATE={}
_HE_SOLVE_INTERCEPTS=[]
_HE_TYPE56_RECORDS=[]

def _v048731_capture_he_solve(call_id, local_eval, global_eval, state, result):
    if int(call_id)!=2 or int(local_eval)!=1: return
    items=tuple(getattr(result,'element_results',()) or ())
    _HE_SOLVE_INTERCEPTS.append({'call_id':int(call_id),'local_eval':int(local_eval),'global_eval':int(global_eval),'element_results':len(items)})
    for item in items:
        if int(item.request.element_z)!=2: continue
        eq=item.equilibrium; assembly=eq.assembly; solve=eq.solve
        if solve is None: return
        n=int(assembly.basis.n_rows)
        initial=np.asarray(assembly.initial_populations[1:n+1],dtype=float)
        final=np.asarray(solve.populations,dtype=float)
        outer=np.asarray(solve.final_outer_start_populations,dtype=float)
        rhs=np.asarray(assembly.rhs,dtype=float)
        rows=tuple(assembly.basis.rows)
        ion_stages=np.asarray(assembly.basis.ion_stage,dtype=np.int32)
        for i in range(n):
            meta=rows[i]
            stage=int(ion_stages[i+1])
            _HE_SOLVE_ROWS.append({
                'element_row':i+1,'ion':int(meta.ion_counter),'ion_charge':max(0,stage-1),
                'ion_stage':stage,'superlevel':int(meta.superlevel),'global_level_index':0,
                'is_normalization_row':1 if i+1==int(assembly.basis.normalization_row) else 0,
                'transformed_initial_population':float(initial[i]),
                'final_outer_start_population':float(outer[i]) if outer.size==n else float('nan'),
                'final_population':float(final[i]),'rhs':float(rhs[i]) if rhs.size==n else float('nan'),
                'row_residual':float(solve.row_residual[i]) if solve.row_residual.size==n else float('nan'),
                'row_scale':float(solve.row_scale[i]) if solve.row_scale.size==n else float('nan')})
        dense=np.asarray(assembly.dense_matrix,dtype=float); normalized=np.asarray(assembly.normalized_matrix,dtype=float)
        heat=np.asarray(assembly.heating_matrix,dtype=float); heat2=np.asarray(assembly.heating_matrix2,dtype=float)
        for i in range(n):
            for j in range(n):
                _HE_SOLVE_MATRIX.append({'compact_row':i+1,'compact_column':j+1,'dense_value':float(dense[i,j]),
                    'normalized_value':float(normalized[i,j]),'heating_value':float(heat[i,j]),'heating2_value':float(heat2[i,j])})
        for seq,term in enumerate(assembly.terms,start=1):
            _HE_SOLVE_TERMS.append({'source_order_index':seq,'term_index':int(term.term_index),'record':int(term.record),
                'data_type':int(term.data_type),'rate_type':int(term.rate_type),'ion_index':int(term.ion_index),
                'ion_stage':int(term.ion_stage),'role':str(term.role),'compact_row':int(term.row),'compact_column':int(term.column),
                'aj1':float(term.aj1),'aj2':float(term.aj2),'cj':float(term.cj),'cj2':float(term.cj2),
                'type53':1 if int(term.data_type)==53 else 0})
        for rr in tuple(getattr(assembly,'record_results',()) or ()):
            if int(rr.get('data_type',0) or 0)!=56: continue
            _HE_TYPE56_RECORDS.append({
                'record':int(rr.get('record',0) or 0),'data_type':56,'rate_type':int(rr.get('rate_type',0) or 0),
                'ion_index':int(rr.get('ion_index',0) or 0),'ion_stage':int(rr.get('ion_stage',0) or 0),
                'idest1':int(rr.get('idest1',0) or 0),'idest2':int(rr.get('idest2',0) or 0),
                'temperature_K':float(rr.get('diag_temperature_K',float('nan'))),
                'upsilon':float(rr.get('diag_upsilon',float('nan'))),
                'q_excitation_cm3_s':float(rr.get('diag_q_excitation_cm3_s',float('nan'))),
                'q_deexcitation_cm3_s':float(rr.get('diag_q_deexcitation_cm3_s',float('nan'))),
                'ans1':float(rr.get('ans1',float('nan'))),'ans2':float(rr.get('ans2',float('nan'))),
                'ans5':float(rr.get('ans5',float('nan'))),'ans6':float(rr.get('ans6',float('nan'))),
                'delta_e_eV':float(rr.get('diag_delta_e_eV',float('nan'))),
                'g_lower':float(rr.get('diag_g_lower',float('nan'))),'g_upper':float(rr.get('diag_g_upper',float('nan')))})
        trace=getattr(solve,'trace',None)
        if trace is not None:
            _HE_OUTER_TRACE.extend(dict(r) for r in trace.outer_level_rows)
            _HE_SUPER_TRACE.extend(dict(r) for r in trace.superlevel_rows)
            _HE_CONDENSED_TRACE.extend(dict(r) for r in trace.condensed_matrix_rows)
            _HE_FIXED_TRACE.extend(dict(r) for r in trace.fixed_point_rows)
        _HE_SOLVE_STATE.update({'global_evaluation_ordinal':int(global_eval),'compact_row_count':n,
            'normalization_compact_row':int(assembly.basis.normalization_row),'solver_method':str(solve.solver_method),
            'converged':bool(solve.converged),'outer_iterations':int(solve.outer_iterations),
            'fixed_point_iterations':int(solve.fixed_point_iterations),'normalization':float(solve.normalization),
            'normalization_error':float(solve.normalization_error),'source_order_term_count':len(_HE_SOLVE_TERMS)})
        return
'''

_PROBE = base._PROBE
_PROBE = _PROBE.replace('\ndef install():', _INJECT + '\ndef install():')
_PROBE = _PROBE.replace('def _capture_result(call_id, local_eval, global_eval, state, result):\n    _STATE["trace"].append({',
    'def _capture_result(call_id, local_eval, global_eval, state, result):\n    _v048731_capture_he_solve(call_id, local_eval, global_eval, state, result)\n    _STATE["trace"].append({')
_PROBE = _PROBE.replace(
'''        try:\n            out = original(self, state)\n        finally:\n            self.pre_evaluation_callback = previous_pre\n            self.progress_callback = previous_progress\n''',
'''        previous_factory = self.calc_kwargs_factory
        previous_trace = tuple(self.capture_lucy_trace_element_z)
        target_he_detail = int(call_id) == 2 and int(local_eval) == 1
        if target_he_detail:
            self.capture_lucy_trace_element_z = (2,)
            if previous_factory is not None:
                def retained_factory(current_state):
                    payload = dict(previous_factory(current_state))
                    payload["retain_element_results"] = True
                    payload["retain_diagnostic_arrays"] = True
                    return payload
                self.calc_kwargs_factory = retained_factory
            print(f"v048731_he_solve_capture_enable call={call_id} local={local_eval} global={global_eval}", flush=True)
        try:
            out = original(self, state)
        finally:
            self.calc_kwargs_factory = previous_factory
            self.capture_lucy_trace_element_z = previous_trace
            self.pre_evaluation_callback = previous_pre
            self.progress_callback = previous_progress
''')

_EXTRA = r'''
def _v048731_write_rows(name, rows):
    path=_OUT/name
    if not rows:
        path.write_text('')
        return
    fields=[]
    for row in rows:
        for key in row:
            if key not in fields: fields.append(key)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def _v048731_write_he_solve_outputs():
    _v048731_write_rows('v0472_call2_eval1_he_solve_rows.csv',_HE_SOLVE_ROWS)
    _v048731_write_rows('v0472_call2_eval1_he_solve_matrix.csv',_HE_SOLVE_MATRIX)
    _v048731_write_rows('v0472_call2_eval1_he_source_order_matrix_terms.csv',_HE_SOLVE_TERMS)
    _v048731_write_rows('v0472_call2_eval1_he_outer_level_trace.csv',_HE_OUTER_TRACE)
    _v048731_write_rows('v0472_call2_eval1_he_superlevel_trace.csv',_HE_SUPER_TRACE)
    _v048731_write_rows('v0472_call2_eval1_he_condensed_matrix_trace.csv',_HE_CONDENSED_TRACE)
    _v048731_write_rows('v0472_call2_eval1_he_fixed_point_trace.csv',_HE_FIXED_TRACE)
    _v048731_write_rows('v0472_call2_eval1_he_type56_records.csv',_HE_TYPE56_RECORDS)
    state_path=_OUT/'v0472_call2_eval1_he_solve_state.json'
    state_path.write_text(json.dumps(_HE_SOLVE_STATE,indent=2,sort_keys=True)+'\n')
    json.loads(state_path.read_text())

'''
_PROBE = _PROBE.replace('def finalize(run_summary=None):\n', _EXTRA + 'def finalize(run_summary=None):\n    _v048731_write_he_solve_outputs()\n', 1)
_DRIVER = base._DRIVER.replace('import v048726_full_probe_runtime as probe','import v048731_he_solve_probe_runtime as probe')

FILES = (
    'v0472_call2_eval1_he_solve_rows.csv','v0472_call2_eval1_he_solve_matrix.csv',
    'v0472_call2_eval1_he_source_order_matrix_terms.csv','v0472_call2_eval1_he_outer_level_trace.csv',
    'v0472_call2_eval1_he_superlevel_trace.csv','v0472_call2_eval1_he_condensed_matrix_trace.csv',
    'v0472_call2_eval1_he_fixed_point_trace.csv','v0472_call2_eval1_he_type56_records.csv','v0472_call2_eval1_he_solve_state.json')

def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def capture(source_archive: Path, atdb: Path, out: Path, params: Path, coheat: Path|None) -> dict[str, Any]:
    import csv
    out=out.resolve(); out.mkdir(parents=True,exist_ok=True)
    if low._sha256(source_archive)!=low.SOURCE_ARCHIVE_SHA256: raise ValueError('v0.6.47.2 source archive hash mismatch')
    with tempfile.TemporaryDirectory(prefix='v048731_') as raw:
        temp=Path(raw); low._safe_extract(source_archive,temp/'source'); root=low._source_root(temp/'source'); probe=temp/'probe'; probe.mkdir()
        (probe/'v048731_he_solve_probe_runtime.py').write_text(_PROBE)
        (probe/'probe_config.json').write_text(json.dumps({'output_dir':str(out)}))
        (probe/'driver.py').write_text(_DRIVER)
        env=dict(os.environ); env['PYTHONPATH']=os.pathsep.join([str(probe),str(root/'src')]); env.update({'PYTHONFAULTHANDLER':'1','PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        cmd=[sys.executable,str(probe/'driver.py'),'--parameters-json',str(params.resolve()),'--atdb-path',str(atdb.resolve()),'--output-dir',str(out/'physical_run')]
        if coheat: cmd += ['--coheat-path',str(coheat.resolve())]
        with (out/'v0472_call2_he_solve_capture.log').open('w') as log:
            rc=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
        if rc: raise RuntimeError(f'source helium solve capture failed rc={rc}')
    counts={}
    for name in FILES[:-1]:
        path=out/name
        if not path.is_file() or path.stat().st_size==0: counts[name]=0
        else:
            with path.open(newline='') as f: counts[name]=sum(1 for _ in csv.DictReader(f))
    state_ok=(out/FILES[-1]).is_file() and bool(json.loads((out/FILES[-1]).read_text()))
    log=(out/'v0472_call2_he_solve_capture.log').read_text(errors='replace')
    intercept='v048731_he_solve_capture_enable call=2 local=1' in log
    core=intercept and counts[FILES[0]]==78 and counts[FILES[1]]==78*78 and counts[FILES[2]]>0 and counts[FILES[3]]>0 and counts['v0472_call2_eval1_he_type56_records.csv']>0 and state_ok
    report={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if core else 'REJECT','counts':counts,
        'call2_he_solve_intercept':'ACCEPT' if intercept else 'REJECT','source_solve_rows':'ACCEPT' if counts[FILES[0]]==78 else 'REJECT',
        'source_matrix_rows':'ACCEPT' if counts[FILES[1]]==78*78 else 'REJECT','source_term_rows':'ACCEPT' if counts[FILES[2]]>0 else 'REJECT',
        'source_iteration_trace':'ACCEPT' if counts[FILES[3]]>0 else 'REJECT',
        'source_type56_records':'ACCEPT' if counts.get('v0472_call2_eval1_he_type56_records.csv',0)>0 else 'REJECT','qualification_only':True,'production_promotion_ready':False}
    _write_json(out/REPORT,report); return report

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('source_archive',type=Path); p.add_argument('atdb',type=Path); p.add_argument('output',type=Path); p.add_argument('parameters',type=Path); p.add_argument('--coheat-path',type=Path); p.add_argument('--output-json',type=Path); a=p.parse_args()
    try: report=capture(a.source_archive,a.atdb,a.output,a.parameters,a.coheat_path)
    except Exception as exc: report={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(exc)]}
    if a.output_json: _write_json(a.output_json,report)
    print(json.dumps(report,indent=2,sort_keys=True)); return 0 if report.get('result')=='ACCEPT' else 2
if __name__=='__main__': raise SystemExit(main())
