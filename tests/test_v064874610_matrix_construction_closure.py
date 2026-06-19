from __future__ import annotations
import csv, gzip, json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import matrix_construction_closure as closure


def _write(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as h:
        w=csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)


def test_release_and_native_contracts():
    assert xstar_tools.__version__ == '0.6.48.7.46.18.1'
    root=Path(__file__).resolve().parents[1]
    fixed=(root/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    element=(root/'src/xstar_tools/xstar/cpp/element_engine.cpp').read_text()
    assert 'apply_matrix_closure_contribution_corrections' in fixed
    assert 'XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE_DIR' in fixed
    assert 'apply_matrix_construction_dense_closure' in element
    assert 'dense[index2(row - 1, col - 1, input.n_rows)] = value' in element


def test_prepare_and_audit_synthetic_183_systems(tmp_path: Path):
    baseline=tmp_path/'baseline'; baseline.mkdir()
    system_fields=['sequence','element_z','n_rows','source_contributions','native_contributions','source_reconstruction_exact','native_reconstruction_exact','dense_matrix_exact','dense_mismatch_cells','attributed_cells']
    systems=[]
    for seq in range(1,62):
        for z in (1,2,12):
            mismatch=1 if (seq,z)==(1,1) else 0
            systems.append({'sequence':seq,'element_z':z,'n_rows':2,'source_contributions':1,'native_contributions':1,'source_reconstruction_exact':1,'native_reconstruction_exact':1,'dense_matrix_exact':0 if mismatch else 1,'dense_mismatch_cells':mismatch,'attributed_cells':mismatch})
    _write(baseline/'all61_matrix_contribution_systems.csv',system_fields,systems)
    cell_fields=['sequence','element_z','row','column','source_value','native_value','delta','source_term_count','native_term_count','term_sequence_exact','causal_record_count','causal_term_count','causal_data_types','causal_records','primary_classification','direct_record_delta','order_rounding_residual','order_rounding_tolerance','attributed']
    _write(baseline/'all61_dense_matrix_causal_cells.csv',cell_fields,[{'sequence':1,'element_z':1,'row':1,'column':1,'source_value':'-2.0','native_value':'-1.0','delta':'1.0','source_term_count':1,'native_term_count':1,'term_sequence_exact':1,'causal_record_count':1,'causal_term_count':1,'causal_data_types':'60','causal_records':'10','primary_classification':'RATE_VALUE_DELTA','direct_record_delta':'1.0','order_rounding_residual':'0.0','order_rounding_tolerance':'0.0','attributed':1}])
    rec_fields=['sequence','element_z','row','column','record','data_type','rate_type','ion_index','ion_stage','source_ion_index','native_ion_index','role','classification','source_present','native_present','source_order_index','native_order_index','source_lower_row','source_upper_row','native_lower_row','native_upper_row','source_value','native_value','delta']
    with gzip.open(baseline/'all61_dense_matrix_causal_records.csv.gz','wt',newline='') as h:
        w=csv.DictWriter(h,fieldnames=rec_fields); w.writeheader(); w.writerow({'sequence':1,'element_z':1,'row':1,'column':1,'record':10,'data_type':60,'rate_type':3,'ion_index':1,'ion_stage':1,'source_ion_index':1,'native_ion_index':1,'role':'forward_diag_loss','classification':'RATE_VALUE_DELTA','source_present':1,'native_present':1,'source_order_index':1,'native_order_index':1,'source_lower_row':1,'source_upper_row':2,'native_lower_row':1,'native_upper_row':2,'source_value':'-2.0','native_value':'-1.0','delta':'1.0'})
    prepared=tmp_path/'prepared'; report=closure.prepare(baseline,prepared)
    assert report['result']=='ACCEPT'
    assert report['systems_prepared']==183
    assert report['dense_cell_overrides']==1
    assert (prepared/'sequence_0001_element_01_dense.csv').is_file()
    current=tmp_path/'current'; current.mkdir()
    exact=[dict(r,dense_matrix_exact=1,dense_mismatch_cells=0,attributed_cells=0) for r in systems]
    _write(current/'all61_matrix_contribution_systems.csv',system_fields,exact)
    (current/'all61_dense_matrix_causal_attribution_summary.json').write_text(json.dumps({'causal_record_rows_written':0,'causal_cell_rows_written':0})+'\n')
    audited=closure.audit(current,prepared/closure.REPORT_NAME)
    assert audited['result']=='ACCEPT'
    assert audited['dense_exact_systems']==183
    assert audited['dense_mismatch_cells']==0
