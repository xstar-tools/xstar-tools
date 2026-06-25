from __future__ import annotations
import csv, json, subprocess
from pathlib import Path
from xstar_tools.xstar.magnesium_type49_leveltemp_closure_v048746222 import source_leveltemp_destination_energy
from xstar_tools.xstar.type49_leveltemp_case_contract_v048746222 import audit_case
ROOT=Path(__file__).resolve().parents[1]

def _candidates(*pairs):
    values=[0.0]*12; mask=0
    for stage,value in pairs: values[stage-1]=value; mask|=1<<(stage-1)
    return mask,tuple(values)

def test_type49_active_second_pass_owner():
    mask,values=_candidates((5,500.0),(11,1695.53125),(12,1884.255959375))
    value,owner,column=source_leveltemp_destination_energy(ion_stage=11,active_min_stage=5,active_max_stage=12,destination_column=35,candidate_mask=mask,candidate_energy_ev=values,incoming_energy_ev=104.0)
    assert (value,owner,column)==(1695.53125,11,35)

def test_type49_first_pass_last_active_owner_before_writer():
    mask,values=_candidates((11,1695.53125),(12,1884.255959375))
    value,owner,_=source_leveltemp_destination_energy(ion_stage=6,active_min_stage=5,active_max_stage=12,destination_column=35,candidate_mask=mask,candidate_energy_ev=values,incoming_energy_ev=104.0)
    assert value==1884.255959375 and owner==12

def test_type49_unowned_preserves_incoming():
    value,owner,column=source_leveltemp_destination_energy(ion_stage=6,active_min_stage=5,active_max_stage=12,destination_column=50,candidate_mask=0,candidate_energy_ev=(0.0,)*12,incoming_energy_ev=77.25)
    assert (value,owner,column)==(77.25,0,50)

def test_native_type49_correction_runs_after_active_selection():
    text=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    active=text.index('const ActiveElementView active =')
    invocation=text.index('apply_magnesium_type49_persistent_leveltemp_v048746222(',active)
    contributions=text.index('std::vector<xstar_element_contribution_v1> contributions',active)
    definition=text.index('void apply_magnesium_type49_persistent_leveltemp_v048746222(')
    end=text.index('PreliminaryIonBalance build_preliminary_ion_balance',definition)
    assert active<invocation<contributions
    assert 'shadow.sumh2' in text[definition:end]
    assert 'shadow.sumc2' in text[definition:end]

def test_lowerer_serializes_type49_candidate_layout():
    text=(ROOT/'src/xstar_tools/xstar/native_fixed_program.py').read_text()
    assert 'TYPE49_LEVELTEMP_LAYOUT_MAGIC_V048746222 = 222' in text
    assert 'dt in {49, 53}' in text
    assert 'range(1, 13)' in text

def test_type57_regression_uses_active_capture_domain():
    text=(ROOT/'src/xstar_tools/xstar/magnesium_type57_thermal_closure_v048746220.py').read_text()
    assert 'answer_capture_domain": "active_matrix_committed"' in text
    assert 'len(source_type57) == len(selected) * EXPECTED_TYPE57_PER_SEQUENCE' not in text
    assert 'set(source_type57) == native_keys' in text

def test_type49_case_contract_accepts_and_rejects_stale(tmp_path:Path):
    case=tmp_path/'case'; case.mkdir()
    (case/'elements.csv').write_text('element_index,element_z,normalization_row\n0,12,577\n')
    fields=['source_position','record','next_index','element_index','opcode','data_type','rate_type','ion_index','ion_stage','lower_row','upper_row','real_offset','real_count','int_offset','int_count','density_scale','line_energy_ev','atomic_mass_amu','matrix_enabled']
    reals=[]; ints=[]
    with (case/'records.csv').open('w',newline='') as h:
      w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
      for i in range(809):
        ro=len(reals); io=len(ints); context=[10.0,10.0,1.0,20.0,2.0,1.0,1.0,104.0,0.0,1.0,*([0.0]*10),1695.53125,0.0]
        reals.extend([1.0,2.0,3.0,4.0,*context]); ints.extend([1,999,35,1<<10,222])
        w.writerow({'source_position':i+1,'record':i+1,'next_index':i+1,'element_index':0,'opcode':49,'data_type':49,'rate_type':7,'ion_index':11,'ion_stage':11,'lower_row':1,'upper_row':35,'real_offset':ro,'real_count':26,'int_offset':io,'int_count':5,'density_scale':1.0,'line_energy_ev':10.0,'atomic_mass_amu':24.0,'matrix_enabled':1})
    (case/'reals.txt').write_text(''.join(f'{x:.17g}\n' for x in reals)); (case/'ints.txt').write_text(''.join(f'{x}\n' for x in ints))
    assert audit_case(case)['result']=='ACCEPT'
    lines=(case/'ints.txt').read_text().splitlines(); lines[4]='0'; (case/'ints.txt').write_text('\n'.join(lines)+'\n')
    assert audit_case(case)['result']=='REJECT'

def test_readiness_accepts(tmp_path:Path):
    out=tmp_path/'r.json'; cp=subprocess.run(['python',str(ROOT/'check_v048746222_magnesium_type49_leveltemp_closure_readiness.py'),'--package-dir',str(ROOT),'--output-json',str(out)],cwd=ROOT,capture_output=True,text=True)
    assert cp.returncode==0,cp.stdout+cp.stderr
    report=json.loads(out.read_text()); assert report['result']=='ACCEPT' and report['abi']==60487
