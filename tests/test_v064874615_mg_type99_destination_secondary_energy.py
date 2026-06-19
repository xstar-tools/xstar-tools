from __future__ import annotations
import csv
from pathlib import Path

from xstar_tools.xstar.mg_type99_secondary_energy_correction import audit
from xstar_tools.xstar.v46141_baseline_gate_vocabulary import REQUIRED, validate

RECORDS = [39813,39855,40060,40359,40642,41154,41884,43327,45034,45614,45935,45936,46741]


def _write_records(root: Path, corrected: bool) -> None:
    diag=root/'qualification_diagnostics'; diag.mkdir(parents=True)
    fields=['source_position','record','element_z','data_type','type99_shadow_valid',
            'type99_shadow_ans1','type99_shadow_ans2','type99_shadow_ans3','type99_shadow_ans4','type99_shadow_ans5','type99_shadow_ans6',
            'type99_destination_energy_ev','type99_bound_energy_ev','type99_threshold_ev',
            'type99_energy_difference_ev','type99_destination_threshold_identity','type99_destination_identity_correction_applied',
            'type99_ans5_pre_energy_correction','type99_ans5_energy_correction_denominator','type99_ans5_energy_correction_factor']
    for seq in range(1,62):
        rows=[]
        for i,rec in enumerate(RECORDS):
            identity=rec!=39813
            neg=(rec==39855) or (rec==40060 and seq<=56) or (rec==41154 and seq<=49)
            pre=-(rec%1000+1)*1e-16
            old=pre
            if neg and not corrected: old=(rec%1000+1)*1e12
            rows.append({'source_position':10000+i,'record':rec,'element_z':12,'data_type':99,'type99_shadow_valid':1,
              'type99_shadow_ans1':1.0,'type99_shadow_ans2':2.0,'type99_shadow_ans3':3.0,'type99_shadow_ans4':4.0,
              'type99_shadow_ans5':pre if corrected else old,'type99_shadow_ans6':-5e-15,
              'type99_destination_energy_ev':20.0 if identity else 21.0,'type99_bound_energy_ev':10.0,'type99_threshold_ev':10.0,
              'type99_energy_difference_ev':10.0 if identity else 11.0,'type99_destination_threshold_identity':int(identity),
              'type99_destination_identity_correction_applied':int(identity and corrected),
              'type99_ans5_pre_energy_correction':pre,'type99_ans5_energy_correction_denominator':-1.0 if neg else 1.0,
              'type99_ans5_energy_correction_factor':1.0 if identity and corrected else (1e43 if neg else 1.0)})
        with (diag/f'evaluation_{seq:04d}_records.csv').open('w',newline='') as h:
            w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)


def test_audit_accepts_constrained_166_row_correction(tmp_path: Path) -> None:
    baseline=tmp_path/'baseline'; native=tmp_path/'native'; out=tmp_path/'out'
    _write_records(baseline/'native_all61',False); _write_records(native,True)
    report=audit(native,baseline,out)
    assert report['result']=='ACCEPT'
    assert report['changed_rows']==166
    assert report['changed_record_counts']=={'39855':61,'40060':56,'41154':49}


def test_v46141_baseline_gate_contract() -> None:
    report={'release':'0.6.48.7.46.14.1','result':'ACCEPT','gates':{name:'ACCEPT' for name in REQUIRED}}
    assert validate(report)['result']=='ACCEPT'
    report['gates']['CONTINUUM_SECONDARY_LEDGER_EXACT_61']='REJECT'
    assert validate(report)['result']=='REJECT'


def test_cpp_identity_guard_is_qualification_scoped() -> None:
    text=Path('src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_MG_TYPE99_SECONDARY_ENERGY_CORRECTION' in text
    assert 'destination_identity_correction_applied' in text
    assert 'const double ans5_energy_factor = destination_identity_correction_applied' in text


def test_runner_enables_new_correction() -> None:
    text=Path('run_v04874615_mg_type99_destination_secondary_energy_correction.sh').read_text()
    assert 'XSTAR_QUALIFICATION_MG_TYPE99_SECONDARY_ENERGY_CORRECTION=1' in text
    assert 'v04874615_mg_type99_secondary_energy_report.json' in text
