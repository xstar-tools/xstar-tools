"""Capture source v0.6.47.2 call-2/evaluation-1 helium populations and thermal families.

The probe is observational. It records exact source-order diagonal thermal
accumulation without changing the source calculation.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path
from typing import Any
from . import v0472_full_dsec_thermal_budget_capture as base
from . import v0472_thermal_budget_state_refresh_capture as low

RELEASE='0.6.48.7.28.1'
SCHEMA='xstar-tools-v06487281-v0472-call2-helium-source-family-capture-v1'
POP='v0472_call2_eval1_he_populations.csv'
TERMS='v0472_call2_eval1_he_source_order_terms.csv'
FAMILIES='v0472_call2_eval1_he_family_rows.csv'
REPORT='v0472_call2_eval1_he_capture_report.json'

_INJECT=r'''
_HE_POP=[]
_HE_TERMS=[]
_HE_INTERCEPTS=[]
_HE_CAPTURE_ERRORS=[]

def _v048728_he_capture(call_id, local_eval, global_eval, state, result):
    if int(call_id)!=2 or int(local_eval)!=1: return
    element_results=tuple(getattr(result,'element_results',()) or ())
    _HE_INTERCEPTS.append({'call_id':int(call_id),'local_eval':int(local_eval),'global_eval':int(global_eval),'element_results':len(element_results)})
    if not element_results:
        _HE_CAPTURE_ERRORS.append('target result has no retained element_results')
        return
    for item in element_results:
        if int(item.request.element_z)!=2: continue
        abundance=float(item.request.abundance)
        pops=np.asarray(item.equilibrium.solve.populations,dtype=float)
        initial=np.asarray(getattr(item.equilibrium.solve,'initial_populations',np.zeros_like(pops)),dtype=float)
        if initial.size!=pops.size: initial=np.zeros_like(pops)
        for i,(before,after) in enumerate(zip(initial,pops),start=1):
            _HE_POP.append({'global_evaluation_ordinal':global_eval,'dsec_call_id':call_id,'dsec_local_evaluation_index':local_eval,'element_z':2,'element_row':i,'abundance':abundance,'population_before_solve':float(before),'population_after_solve':float(after),'abundance_weighted_population':abundance*float(after)})
        seq=0
        for term in item.equilibrium.assembly.terms:
            if int(term.row)!=int(term.column): continue
            row=int(term.row)
            if row<1 or row>pops.size: continue
            seq+=1; wp=abundance*float(pops[row-1]); cj=float(term.cj); cj2=float(term.cj2)
            h=max(0.0,-wp*cj); c=max(0.0,wp*cj); h2=max(0.0,-wp*cj2); c2=max(0.0,wp*cj2)
            _HE_TERMS.append({'sequence':seq,'global_evaluation_ordinal':global_eval,'dsec_call_id':call_id,'dsec_local_evaluation_index':local_eval,'element_z':2,'data_type':int(term.data_type),'rate_type':int(getattr(term,'rate_type',0) or 0),'source_position':int(getattr(term,'source_position',0) or 0),'record':int(getattr(term,'record',0) or 0),'destination_row':row,'abundance':abundance,'population':float(pops[row-1]),'weighted_population':wp,'cj':cj,'cj2':cj2,'primary_heating':h,'primary_cooling':c,'secondary_heating':h2,'secondary_cooling':c2,'type53':1 if int(term.data_type)==53 else 0})
        return
'''

_PROBE=base._PROBE
# Inject storage/functions before install and capture before the standard budget row.
_PROBE=_PROBE.replace('\ndef install():', _INJECT+'\ndef install():')
_PROBE=_PROBE.replace('def _capture_result(call_id, local_eval, global_eval, state, result):\n    _STATE["trace"].append({', 'def _capture_result(call_id, local_eval, global_eval, state, result):\n    _v048728_he_capture(call_id, local_eval, global_eval, state, result)\n    _STATE["trace"].append({')
_PROBE=_PROBE.replace(
    '        try:\n            out = original(self, state)\n        finally:\n            self.pre_evaluation_callback = previous_pre\n            self.progress_callback = previous_progress\n',
    '''        previous_factory = self.calc_kwargs_factory
        target_he_detail = int(call_id) == 2 and int(local_eval) == 1
        if target_he_detail and previous_factory is not None:
            def retained_factory(current_state):
                payload = dict(previous_factory(current_state))
                payload["retain_element_results"] = True
                payload["retain_diagnostic_arrays"] = True
                return payload
            self.calc_kwargs_factory = retained_factory
            print(f"v0487281_he_retention_enable call={call_id} local={local_eval} global={global_eval}", flush=True)
        try:
            out = original(self, state)
        finally:
            self.calc_kwargs_factory = previous_factory
            self.pre_evaluation_callback = previous_pre
            self.progress_callback = previous_progress
''')
# Add exact-order outputs during finalize.
needle='def finalize(run_summary=None):\n'
extra=r'''def _v048728_write_he_outputs():
    pop_fields=['global_evaluation_ordinal','dsec_call_id','dsec_local_evaluation_index','element_z','element_row','abundance','population_before_solve','population_after_solve','abundance_weighted_population']
    term_fields=['sequence','global_evaluation_ordinal','dsec_call_id','dsec_local_evaluation_index','element_z','data_type','rate_type','source_position','record','destination_row','abundance','population','weighted_population','cj','cj2','primary_heating','primary_cooling','secondary_heating','secondary_cooling','type53']
    with (_OUT/'v0472_call2_eval1_he_populations.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=pop_fields);w.writeheader();w.writerows(_HE_POP)
    with (_OUT/'v0472_call2_eval1_he_source_order_terms.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=term_fields);w.writeheader();w.writerows(_HE_TERMS)
    grouped={}
    for r in _HE_TERMS:
        key=(r['data_type'],r['destination_row']); g=grouped.setdefault(key,{'data_type':key[0],'destination_row':key[1],'terms':0,'primary_heating':0.0,'primary_cooling':0.0,'secondary_heating':0.0,'secondary_cooling':0.0,'type53':1 if key[0]==53 else 0})
        g['terms']+=1
        for k in ('primary_heating','primary_cooling','secondary_heating','secondary_cooling'): g[k]+=float(r[k])
    fields=['data_type','destination_row','terms','primary_heating','primary_cooling','secondary_heating','secondary_cooling','type53']
    with (_OUT/'v0472_call2_eval1_he_family_rows.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(grouped.values())

'''
_PROBE=_PROBE.replace(needle, extra+needle)
_PROBE=_PROBE.replace('def finalize(run_summary=None):\n    for name, fields, rows in [', 'def finalize(run_summary=None):\n    _v048728_write_he_outputs()\n    for name, fields, rows in [')
_DRIVER=base._DRIVER.replace('import v048726_full_probe_runtime as probe','import v048728_he_probe_runtime as probe')

def _write_json(path:Path,obj:Any): path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def capture(source_archive:Path,atdb:Path,out:Path,params:Path,coheat:Path|None)->dict[str,Any]:
    out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    if low._sha256(source_archive)!=low.SOURCE_ARCHIVE_SHA256: raise ValueError('v0.6.47.2 source archive hash mismatch')
    with tempfile.TemporaryDirectory(prefix='v048728_') as t:
        t=Path(t); low._safe_extract(source_archive,t/'source'); root=low._source_root(t/'source'); p=t/'probe';p.mkdir()
        (p/'v048728_he_probe_runtime.py').write_text(_PROBE);(p/'probe_config.json').write_text(json.dumps({'output_dir':str(out)}));(p/'driver.py').write_text(_DRIVER)
        env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join([str(p),str(root/'src')]);env.update({'PYTHONFAULTHANDLER':'1','PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        cmd=[sys.executable,str(p/'driver.py'),'--parameters-json',str(params.resolve()),'--atdb-path',str(atdb.resolve()),'--output-dir',str(out/'physical_run')]
        if coheat: cmd += ['--coheat-path',str(coheat.resolve())]
        with (out/'v0472_call2_he_capture.log').open('w') as f: rc=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
        if rc: raise RuntimeError(f'source helium capture failed rc={rc}')
    import csv
    counts={}
    for name in (POP,TERMS,FAMILIES):
        path=out/name
        with path.open(newline='') as f: counts[name]=sum(1 for _ in csv.DictReader(f))
    ok=counts[POP]>0 and counts[TERMS]>0 and counts[FAMILIES]>0
    log_text=(out/'v0472_call2_he_capture.log').read_text(errors='replace') if (out/'v0472_call2_he_capture.log').is_file() else ''
    intercept_seen='v0487281_he_retention_enable call=2 local=1' in log_text
    r={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if ok and intercept_seen else 'REJECT','counts':counts,'actual_v0472_runtime_capture':True,
       'call2_he_element_intercept':'ACCEPT' if intercept_seen else 'REJECT',
       'call2_he_population_rows_gt_zero':'ACCEPT' if counts[POP]>0 else 'REJECT',
       'call2_he_source_order_terms_gt_zero':'ACCEPT' if counts[TERMS]>0 else 'REJECT',
       'call2_he_family_rows_gt_zero':'ACCEPT' if counts[FAMILIES]>0 else 'REJECT',
       'qualification_only':True,'production_promotion_ready':False}
    _write_json(out/REPORT,r);return r

def main():
    p=argparse.ArgumentParser();p.add_argument('source_archive',type=Path);p.add_argument('atdb',type=Path);p.add_argument('output',type=Path);p.add_argument('parameters',type=Path);p.add_argument('--coheat-path',type=Path);p.add_argument('--output-json',type=Path);a=p.parse_args()
    try:r=capture(a.source_archive,a.atdb,a.output,a.parameters,a.coheat_path)
    except Exception as e:r={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(e)]}
    if a.output_json:_write_json(a.output_json,r)
    print(json.dumps(r,indent=2,sort_keys=True));return 0 if r['result']=='ACCEPT' else 2
if __name__=='__main__':raise SystemExit(main())
