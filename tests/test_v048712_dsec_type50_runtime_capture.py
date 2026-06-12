from __future__ import annotations
import csv, json
from pathlib import Path
from xstar_tools.xstar import v0472_dsec_type50_runtime_capture as cap


def test_embedded_probe_scripts_compile() -> None:
    compile(cap._PROBE_RUNTIME, 'probe_runtime', 'exec')
    compile(cap._DRIVER, 'capture_driver', 'exec')


def test_target_inventory_from_lowered_program(tmp_path: Path) -> None:
    fields=['element_index','ion_stage','data_type','lower_row','upper_row','record','source_position']
    with (tmp_path/'records.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for i in range(79):
            w.writerow({'element_index':1,'ion_stage':2,'data_type':50,'lower_row':46+(i%9),'upper_row':55+(i%20),'record':1696+i,'source_position':6316+4*i})
    rows=cap._load_target_inventory(tmp_path)
    assert len(rows)==79
    assert rows[0]['source_position']==6316


def test_verify_accepts_complete_actual_capture(tmp_path: Path) -> None:
    rec_fields=[
        'global_evaluation_ordinal','dsec_call_id','dsec_local_evaluation_index','source_position','record','element_z','ion_stage','data_type','lower_row','upper_row','line_index','tau_in','tau_out','allow_missing_as_zero','ptmp1','ptmp2','ptmp_sum','flinabs_ptmp1','covering_fraction','temperature_k','hydrogen_density_cm3','electron_fraction_xee','ans1','ans2','ans3','ans4','ans5','ans6','idest1','idest2','ucalc_status','matrix_term_count','matrix_committed'
    ]
    term_fields=['global_evaluation_ordinal','dsec_call_id','source_position','record','term_index','role','row','column','aj1','aj2','cj','cj2','idest1','idest2','lower_endpoint','upper_endpoint','source_row_unclamped','source_column_unclamped','source_ipmat_clamped']
    with (tmp_path/cap.RECORDS_NAME).open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=rec_fields);w.writeheader()
        for i in range(79):
            row={k:0 for k in rec_fields};row.update({'global_evaluation_ordinal':61,'record':1696+i,'source_position':6316+4*i,'tau_in':0.0,'tau_out':0.0,'ptmp1':0.5,'ptmp2':0.5,'ptmp_sum':1.0,'flinabs_ptmp1':1.0,'covering_fraction':1.0,'temperature_k':1e6,'hydrogen_density_cm3':1e8,'electron_fraction_xee':1.2,'matrix_term_count':4,'matrix_committed':True})
            w.writerow(row)
    with (tmp_path/cap.TERMS_NAME).open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=term_fields);w.writeheader()
        for i in range(79):
            for j in range(4):
                row={k:0 for k in term_fields};row.update({'global_evaluation_ordinal':61,'record':1696+i,'source_position':6316+4*i,'term_index':4*i+j+1,'role':str(j)})
                w.writerow(row)
    with (tmp_path/cap.TRACE_NAME).open('w',newline='') as h:
        fields=['global_evaluation_ordinal','dsec_call_id','dsec_local_evaluation_index','temperature_k','hydrogen_density_cm3','electron_fraction_xee']
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for i in range(61): w.writerow({'global_evaluation_ordinal':i+1,'dsec_call_id':1,'dsec_local_evaluation_index':i+1,'temperature_k':1e6,'hydrogen_density_cm3':1e8,'electron_fraction_xee':1.2})
    (tmp_path/cap.REPORT_NAME).write_text(json.dumps({'actual_dsec_runtime_capture':True,'capture_kind':'actual_v06472_dsec_type50_escape_probability_runtime_capture','dsec_evaluations_observed':61})+'\n')
    result=cap.verify(tmp_path)
    assert result['result']=='ACCEPT'
    assert result['records']==79
    assert result['matrix_terms']==316
