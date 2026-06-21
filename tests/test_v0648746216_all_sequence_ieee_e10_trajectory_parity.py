from __future__ import annotations
import csv, json, subprocess, sys
from pathlib import Path
from xstar_tools.xstar import iteration_resolved_trajectory_parity_v048746216 as parity

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ((1,1),(6,1),(1,2),(1,12))

def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as h:
        w=csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def _records(sequence,z,value=1.0):
    m={'sequence':sequence,'element_z':z,'n_rows':1,'n_superlevels':1,'normalization_row':1,'max_outer_iterations':200,'max_fixed_iterations':200,'lucy_tolerance':1e-2,'fixed_point_tolerance':1e-2,'outer_iterations':1,'total_fixed_point_iterations':1,'outer_trace_records':1,'fixed_trace_records':1,'trace_complete':1}
    o={'sequence':sequence,'element_z':z,'outer_iteration':1,'compact_row':1,'superlevel':1,'ion':5 if z==12 else 1,'outer_start_population':value,'row_fraction':value,'population_after_condensed':value,'population_after_fixed_point':value,'fixed_iterations_this_outer':1,'total_fixed_iterations_after_outer':1,'fixed_difference':0.0,'outer_difference':0.0,'fixed_termination_reason':'tolerance','outer_termination_reason':'tolerance'}
    s={'sequence':sequence,'element_z':z,'outer_iteration':1,'superlevel':1,'population_before_condensed_solve':value,'condensed_rhs':value,'first_lu_solution':value,'refinement_residual':0.0,'refinement_correction':0.0,'refined_superlevel_solution':value}
    x={'sequence':sequence,'element_z':z,'outer_iteration':1,'row_superlevel':1,'column_superlevel':1,'normalized_matrix_value':value}
    f={'sequence':sequence,'element_z':z,'outer_iteration':1,'fixed_iteration':1,'global_fixed_iteration':1,'compact_row':1,'superlevel':1,'ion':5 if z==12 else 1,'population_before':value,'riu':0.0,'rui':0.0,'ril':0.0,'rli':0.0,'population_after':value,'fixed_difference':0.0,'termination_reason':'tolerance'}
    return m,o,s,x,f

def _fixture(tmp_path:Path, delta:float):
    source=tmp_path/'source'; native=tmp_path/'native'; buckets={k:[] for k in parity.SOURCE_FILES}
    for seq,z in TARGETS:
        records=list(_records(seq,z))
        for k,row in zip(('manifest','outer','super','matrix','fixed'),records): buckets[k].append(row)
        n=[dict(r) for r in records]
        if z==12: n[1]['ion']=1; n[4]['ion']=1
        if (seq,z)==(6,1):
            n[3]['normalized_matrix_value']=1.0+delta
            n[1]['population_after_condensed']=1.0+delta
            n[4]['population_before']=1.0+delta
        d=native/f'evaluation_{seq:04d}'/'iteration_trace'; stem=f'sequence_{seq:04d}_element_{z:02d}'
        for k,row in zip(('manifest','outer','super','matrix','fixed'),n): _write(d/f'{stem}{parity.NATIVE_SUFFIXES[k]}',[row])
    for k,rows in buckets.items(): _write(source/parity.SOURCE_FILES[k],rows)
    return source,native

def test_default_inventory_is_all_183():
    assert len(parity.DEFAULT_TARGETS)==183
    assert len({s for s,_ in parity.DEFAULT_TARGETS})==61

def test_one_ulp_is_e10_acceptable(tmp_path:Path):
    source,native=_fixture(tmp_path,2.220446049250313e-16)
    out=tmp_path/'out'; result=parity.analyze(source,native,out,TARGETS)
    assert result['scientific_result']=='ACCEPT'
    assert result['systems_ieee_e10_acceptable']==4
    assert result['rejected_differences']==0
    assert result['numeric_values_accepted_roundoff']>=1
    assert (out/'v048746216_iteration_trajectory_accepted_roundoff.csv').is_file()

def test_visible_e10_difference_rejects(tmp_path:Path):
    source,native=_fixture(tmp_path,1e-6)
    result=parity.analyze(source,native,tmp_path/'out',TARGETS)
    assert result['scientific_result']=='REJECT'
    assert result['rejected_differences']>=1
    assert result['first_rejection_stage']=='condensed_matrix'

def test_readiness_accepts():
    p=subprocess.run([sys.executable,str(ROOT/'check_v048746216_all_sequence_ieee_e10_trajectory_parity_readiness.py'),'--package-dir',str(ROOT)],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert json.loads(p.stdout)['result']=='ACCEPT'
