from pathlib import Path
import csv

from xstar_atomic.xstar_record_level_parity import audit_record_level_matrix_parity


def _write(path: Path, rows):
    keys=[]
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def test_type99_records_fallback_and_blocker_diagnosis(tmp_path):
    bench=tmp_path/'bench'/'solver_products'/'o_vii'
    bench.mkdir(parents=True)
    matrix=bench/'xstar_like_element_solver_full_global_matrix_terms.csv'
    # No generic record value; parent/superlevel closure record lives in type99_records.
    _write(matrix, [
        {'record':'', 'type99_records':'21811', 'data_type':'99', 'rate_type':'',
         'full_global_component':'type99_calt99_recombination_source',
         'source_method':'', 'rate_source':'calt99.f90+phint53hunt.f90',
         'full_global_signed_rate_s^-1':'20.0'},
        {'record':'', 'type99_records':'21811', 'data_type':'99', 'rate_type':'',
         'full_global_component':'type99_calt99_recombination_source',
         'source_method':'', 'rate_source':'calt99.f90+phint53hunt.f90',
         'full_global_signed_rate_s^-1':'-20.0'},
    ])
    ucalc=tmp_path/'ucalc.csv'
    _write(ucalc, [{'capture_index':'1','ml_data':'21811','ltyp':'99','lrtyp':'0','jkk_ion':'7','idest1':'1','idest2':'2','idest3':'0','idest4':'0','ans1':'1.0','ans2':'1.0','ans3':'0','ans4':'0','ans5':'0','ans6':'0'}])
    m=tmp_path/'m.csv'
    _write(m, [
        {'capture_index':'1','matrix_capture_index':'1','ml_data':'21811','ltyp':'99','lrtyp':'0','insertion_index':'1','insertion_kind':'forward_offdiag','indbi_1':'1','indbi_2':'2','ajisi_1':'1.0','ajisi_2':'0'},
        {'capture_index':'1','matrix_capture_index':'2','ml_data':'21811','ltyp':'99','lrtyp':'0','insertion_index':'2','insertion_kind':'reverse_offdiag','indbi_1':'2','indbi_2':'1','ajisi_1':'1.0','ajisi_2':'0'},
        {'capture_index':'1','matrix_capture_index':'3','ml_data':'21811','ltyp':'99','lrtyp':'0','insertion_index':'3','insertion_kind':'forward_diag_loss','indbi_1':'1','indbi_2':'1','ajisi_1':'-1.0','ajisi_2':'0'},
        {'capture_index':'1','matrix_capture_index':'4','ml_data':'21811','ltyp':'99','lrtyp':'0','insertion_index':'4','insertion_kind':'reverse_diag_loss','indbi_1':'2','indbi_2':'2','ajisi_1':'-1.0','ajisi_2':'0'},
    ])
    audit=audit_record_level_matrix_parity(benchmark_dir=tmp_path/'bench', ion='O VII', ucalc_probe_csv=ucalc, matrix_probe_csv=m)
    assert audit['summary']['audit_version']=='v0.3.183'
    assert audit['summary']['n_python_records']==1
    row=audit['record_rows'][0]
    assert row['record']==21811
    assert row['blocker_hypothesis']=='type99_parent_superlevel_closure_not_source_equivalent'
    assert row['blocker_priority']=='blocking'
