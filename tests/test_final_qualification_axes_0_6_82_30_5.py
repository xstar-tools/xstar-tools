import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'tools/qualification/run_final_qualification_axes_host_smoke_0_6_82_30_5.py'
MATRIX=ROOT/'qualification/final_qualification_axes_0_6_82_30_5/final_qualification_axes_0_6_82_30_5.json'

def test_final_axis_matrix_is_complete():
    m=json.loads(MATRIX.read_text())
    a=m['axes']
    assert a['cfrac']==[0.0,0.4,1.0]
    assert a['emult']==[0.1,0.25,0.5,1.0]
    assert a['niter']==[0,-99,1,99]
    assert a['lcpres']==[0,1]
    assert a['npass']==[1,3,5]
    assert a['ncn2']==[999,9999,19999]
    assert set(a['elements'])=={'H+He+C','H+He+O','H+He+Ca','H+He+Fe'}
    assert {'pow','bbody','bremss','file:spectun=0','file:spectun=1','file:spectun=2'}==set(a['spectrum'])

def test_release_gate_has_no_parameter_surface_dependency():
    text=RUNNER.read_text()
    assert 'run_table1_parameter_surface' not in text
    assert 'pset' not in text and 'pget' not in text and 'pquery' not in text
    assert 'FINAL_QUALIFICATION_0682305_RESULT' in text

def test_fortran_outputs_are_reusable_for_python_phase():
    m=json.loads(MATRIX.read_text())
    assert m['reuse_for_python'] is True
    text=RUNNER.read_text()
    assert 'FORTRAN -> C++ now; retain FORTRAN outputs for later Python -> FORTRAN' in text
