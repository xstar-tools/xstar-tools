from __future__ import annotations
import csv, gzip, json
from pathlib import Path

from xstar_tools.xstar.mg_type50_endpoint_orientation_attribution import analyze


def _write_records(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields=['record','lower_row','upper_row','data_type']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for record in (40066,40095,40108,40134,41209):
            w.writerow({'record':record,'lower_row':1,'upper_row':2,'data_type':50})


def _write_empty_causal(path: Path) -> None:
    fields=['sequence','element_z','data_type','classification','record']
    with gzip.open(path,'wt',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()


def test_accepted_corrected_type50_baseline_is_preserved(tmp_path: Path) -> None:
    baseline=tmp_path/'baseline'; current=tmp_path/'current'
    baseline.mkdir(); current.mkdir()
    _write_empty_causal(baseline/'all61_dense_matrix_causal_records.csv.gz')
    _write_empty_causal(current/'all61_dense_matrix_causal_records.csv.gz')
    _write_records(baseline/'native_case_all61'/'records.csv')
    _write_records(current/'native_case_all61'/'records.csv')
    report={
      'baseline_orientation_rows':1124,
      'baseline_record_evaluations':281,
      'baseline_target_records':[40066,40095,40108,40134,41209],
      'current_orientation_rows':0,
      'current_target_residual_rows':0,
      'gates':{
        'MG_TYPE50_ORIENTATION_CORRECTION':'ACCEPT',
        'MG_TYPE50_TARGET_ENDPOINTS_SWAPPED_EXACT':'ACCEPT',
        'MG_TYPE50_ONLY_TARGET_ENDPOINT_FIELDS_CHANGED':'ACCEPT',
      },
    }
    (baseline/'v04874696_mg_type50_endpoint_orientation_report.json').write_text(json.dumps(report))
    result=analyze(baseline,current)
    assert result['result']=='ACCEPT'
    assert result['baseline_mode']=='accepted_corrected_baseline'
    assert result['gates']['MG_TYPE50_ACCEPTED_BASELINE_PRESERVED']=='ACCEPT'


def test_zero_residual_contract_present() -> None:
    text=(Path(__file__).parents[1]/'src/xstar_tools/xstar/all61_dense_matrix_causal_attribution.py').read_text()
    assert 'zero_residual_closure' in text
    assert 'canonical_alignment_vacuous' in text
