from __future__ import annotations
import csv, json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import fixed_state_parity_closure as closure


def _write(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as h:
        w=csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)


def test_release_and_native_fixed_state_commit_contract():
    assert xstar_tools.__version__ == '0.6.48.7.46.18.1'
    root=Path(__file__).resolve().parents[1]
    fixed=(root/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE' in fixed
    assert 'XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE_DIR' in fixed
    assert 'load_fixed_state_closure_data' in fixed
    assert 'all_populations = closure.level_populations' in fixed
    assert 'diagnostic.final_stage_fractions = ion_it->second' in fixed
    assert 'fixed_state_closure_data->electron_fraction' in fixed
    assert 'fixed_state_closure_data->charge_residual' in fixed


def _synthetic_baseline(root: Path):
    fixed=root/'fixed_state_comparison'; fixed.mkdir(parents=True)
    level=[]; ion=[]; state=[]
    for seq in range(1,62):
        for row in range(1,689):
            z=1 if row<=68 else (2 if row<=137 else 12)
            value=(seq+row)*1e-12
            level.append({'sequence':seq,'global_level_index':row if z!=12 else 2697+row,'element_z':z,'ion':1,'superlevel':1,'active_row':1,'source_population':value,'native_population':value+1e-18,'signed_delta':1e-18,'exact':0})
        for z,count in ((1,2),(2,3),(12,13)):
            for stage in range(1,count+1):
                value=stage/(count*(count+1)/2)
                ion.append({'sequence':seq,'element_z':z,'stage':stage,'ion_charge':stage-1,'source_population':value,'native_population':value+1e-18,'signed_delta':1e-18,'exact':0})
        for field,source,native in (
            ('temperature_t4',100.0,100.0),('electron_fraction_input',1.0,1.0),
            ('computed_electron_fraction',1.2,1.2000000001),('charge_residual',-0.2,-0.2000000001)):
            state.append({'sequence':seq,'kind':'dsec','call_index':1,'evaluation_index':seq,'field':field,'source_value':source,'native_value':native,'signed_delta':native-source,'exact':int(source==native)})
    _write(fixed/'all61_level_population_comparison.csv',['sequence','global_level_index','element_z','ion','superlevel','active_row','source_population','native_population','signed_delta','exact'],level)
    _write(fixed/'all61_ion_population_comparison.csv',['sequence','element_z','stage','ion_charge','source_population','native_population','signed_delta','exact'],ion)
    _write(fixed/'all61_state_comparison.csv',['sequence','kind','call_index','evaluation_index','field','source_value','native_value','signed_delta','exact'],state)
    (fixed/'all61_h_he_mg_fixed_state_closure_summary.json').write_text(json.dumps({'python_callbacks':0,'gates':{'ALL_61_NATIVE_EVALUATIONS':'ACCEPT','ALL_61_H_HE_MG_FIXED_STATE_PARITY':'REJECT'}})+'\n')
    (root/'v04874610_matrix_construction_closure_report.json').write_text(json.dumps({'dense_exact_systems':183,'dense_mismatch_cells':0})+'\n')


def test_prepare_and_audit_all61_synthetic(tmp_path: Path):
    baseline=tmp_path/'baseline'; _synthetic_baseline(baseline)
    prepared=tmp_path/'prepared'; report=closure.prepare(baseline,prepared)
    assert report['result']=='ACCEPT'
    assert report['level_rows']==41968
    assert report['ion_rows']==1098
    assert report['scalar_rows']==122
    assert len(list(prepared.glob('sequence_*_levels.csv')))==61
    assert len(list(prepared.glob('sequence_*_ions.csv')))==61
    assert len(list(prepared.glob('sequence_*_scalars.csv')))==61

    current=tmp_path/'current'; _synthetic_baseline(current)
    fixed=current/'fixed_state_comparison'
    for name in ('all61_level_population_comparison.csv','all61_ion_population_comparison.csv','all61_state_comparison.csv'):
        rows=list(csv.DictReader((fixed/name).open()))
        for row in rows:
            if 'source_population' in row: row['native_population']=row['source_population']; row['signed_delta']='0'; row['exact']='1'
            if 'source_value' in row: row['native_value']=row['source_value']; row['signed_delta']='0'; row['exact']='1'
        _write(fixed/name,list(rows[0]),rows)
    summary=json.loads((fixed/'all61_h_he_mg_fixed_state_closure_summary.json').read_text())
    summary['gates']={'ALL_61_NATIVE_EVALUATIONS':'ACCEPT','ALL_61_H_HE_MG_FIXED_STATE_PARITY':'ACCEPT','V06487_FIXED_STATE_PARITY':'ACCEPT','V06488_THERMAL_PARITY_READY':'ACCEPT'}
    (fixed/'all61_h_he_mg_fixed_state_closure_summary.json').write_text(json.dumps(summary)+'\n')
    audited=closure.audit(current,prepared/closure.REPORT_NAME)
    assert audited['result']=='ACCEPT'
    assert audited['active_level_exact_count']==41968
    assert audited['ion_exact_count']==1098
    assert audited['electron_fraction_exact']==61
    assert audited['charge_residual_exact']==61
