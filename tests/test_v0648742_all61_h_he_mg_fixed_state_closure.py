from __future__ import annotations
import csv,json
from pathlib import Path
from xstar_tools.xstar.all61_fixed_state_closure import compare


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def fixture(tmp_path: Path):
    source=tmp_path/'source'; native=tmp_path/'native'; diag=native/'qualification_diagnostics'; output=tmp_path/'out'; diag.mkdir(parents=True)
    states=[]; inputs=[]; levels=[]; ions=[]
    for seq in range(1,62):
        kind='final' if seq in (22,24,43,61) else 'dsec'; call=1 if seq<=22 else 2 if seq<=24 else 3 if seq<=43 else 4
        state={'sequence':seq,'kind':kind,'dsec_call_id':call,'evaluation_index':seq,'temperature_k':65000.0,'temperature_t4':6.5,'electron_fraction_input':1.2,'computed_electron_fraction':1.1,'charge_residual':0.1,'hmctot':0.2}
        states.append(state); inputs.append({**state,'covering_fraction':1.0,'turbulent_velocity_km_s':100.0,'workspace_directory':'x','radiation_bins':1,'continuum_tau_count':1,'global_level_count':1})
        levels.append({'sequence':seq,'kind':kind,'dsec_call_id':call,'evaluation_index':seq,'element_z':1,'stage':1,'local_level_ordinal':1,'global_level_index':1,'population':0.25,'bilevg':0.0,'rnisg':0.0})
        ion_diag=[]
        for z in (1,2,12):
            for stage in range(1,z+2):
                value=(stage)/(sum(range(1,z+2)))
                ions.append({'sequence':seq,'kind':kind,'dsec_call_id':call,'evaluation_index':seq,'element_z':z,'stage':stage,'ion_charge':stage-1,'population':value})
                ion_diag.append({'evaluation_ordinal':seq,'element_index':0,'element_z':z,'stage':stage,'ion_charge':stage-1,'preliminary_ionization':0,'preliminary_recombination':0,'preliminary_fraction':value,'final_fraction':value,'active_stage':1})
        write_csv(diag/f'evaluation_{seq:04d}_ion_balance.csv',list(ion_diag[0]),ion_diag)
        pop=[{'evaluation_ordinal':seq,'global_population_row':1,'element_index':0,'element_z':1,'element_row':1,'superlevel':1,'ion':1,'ion_charge':0,'energy_ev':0,'statistical_weight':2,'initial_population':0,'final_population':0.25,'active_row':1}]
        write_csv(diag/f'evaluation_{seq:04d}_populations.csv',list(pop[0]),pop)
    write_csv(source/'v0472_all61_fixed_state_rows.csv',list(states[0]),states)
    write_csv(source/'v0472_all61_input_states.csv',list(inputs[0]),inputs)
    write_csv(source/'v0472_all61_ion_populations.csv',list(ions[0]),ions)
    write_csv(source/'v0472_all61_level_populations.csv',list(levels[0]),levels)
    native_states=[{'sequence':r['sequence'],'kind':r['kind'],'call_index':r['dsec_call_id'],'evaluation_index':r['evaluation_index'],'temperature_t4':r['temperature_t4'],'electron_fraction_input':r['electron_fraction_input'],'computed_electron_fraction':r['computed_electron_fraction'],'charge_residual':r['charge_residual'],'hmctot':r['hmctot']} for r in states]
    write_csv(native/'native_dsec_trajectory.csv',list(native_states[0]),native_states)
    (native/'native_dsec_summary.json').write_text(json.dumps({'total_evaluations':61,'python_callbacks':0}))
    rows=tmp_path/'rows.csv'; write_csv(rows,['element_index','row','superlevel','ion','ion_charge','initial_population','energy_ev','statistical_weight','principal_n','orbital_l','global_level_index'],[{'element_index':0,'row':1,'superlevel':1,'ion':1,'ion_charge':0,'initial_population':1,'energy_ev':0,'statistical_weight':2,'principal_n':1,'orbital_l':0,'global_level_index':1}])
    return source,native,rows,output


def test_exact_all61_accepts(tmp_path):
    source,native,rows,output=fixture(tmp_path)
    result=compare(source,native,rows,output)
    assert result['result']=='ACCEPT'
    assert result['gates']['V06488_THERMAL_PARITY_READY']=='YES'


def test_electron_fraction_mismatch_rejects(tmp_path):
    source,native,rows,output=fixture(tmp_path)
    path=native/'native_dsec_trajectory.csv'; data=list(csv.DictReader(path.open())); data[0]['computed_electron_fraction']='1.1000000000000003'; write_csv(path,list(data[0]),data)
    result=compare(source,native,rows,output)
    assert result['result']=='REJECT'
    assert result['gates']['ALL_61_ELECTRON_FRACTION_EXACT']=='REJECT'
    assert result['gates']['THERMAL_PARITY']=='BLOCKED'
