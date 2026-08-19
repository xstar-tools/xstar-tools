import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/'qualification/final_qualification_models_0_6_82_30_6/final_qualification_models_0_6_82_30_6.json'
RUNNER=ROOT/'tools/qualification/run_final_qualification_models_host_smoke_0_6_82_30_6.py'

def test_exactly_eight_final_models_and_no_parameter_replay():
    m=json.loads(MATRIX.read_text())
    assert m['model_count']==8
    assert len(m['models'])==8
    assert m['fortran_cpp_execution_count']==16
    assert m['ncn2']['status']=='DEFERRED_FOCUSED_FOLLOWUP'
    assert m['ncn2']['value_in_this_gate']==9999
    text=RUNNER.read_text()
    for old in ('run_c5_emult_sweep','run_c5_niter_modes','run_c5_lcpres_pressure','run_c5_radexp_density','run_c5_npass_multipass','run_spectrum_contract'):
        assert old not in text

def test_required_science_breadth_is_present():
    m=json.loads(MATRIX.read_text())
    by={x['name']:x for x in m['models']}
    assert set(by)=={
      'c5_reference_ne1e8','c5_lowxi_cf04_ne1e12','o7_reference_ne1e10','ca19_reference_ne1e8',
      'fe_reference_ne1e8','multi_element_xi1_ne1e12','c5_low_density_ne1','c5_high_density_ne1e12'
    }
    assert by['c5_lowxi_cf04_ne1e12']['rlogxi']==-3.0
    assert by['c5_lowxi_cf04_ne1e12']['cfrac']==0.4
    assert by['c5_low_density_ne1']['density']==1.0
    assert by['c5_high_density_ne1e12']['density']==1e12
    assert {'O'} <= set(by['o7_reference_ne1e10']['elements'])
    assert {'Ca'} <= set(by['ca19_reference_ne1e8']['elements'])
    assert {'Fe'} <= set(by['fe_reference_ne1e8']['elements'])
    assert len(by['multi_element_xi1_ne1e12']['elements'])==15

def test_fortran_references_are_retained_for_later_python_phase():
    m=json.loads(MATRIX.read_text())
    assert m['reuse_for_python'] is True
    text=RUNNER.read_text()
    assert 'root / "fortran" / case_name' in text
    assert 'FINAL_QUALIFICATION_0682306_RESULT' in text
