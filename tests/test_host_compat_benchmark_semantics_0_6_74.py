from pathlib import Path
import json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def test_manifest_records_zone_cpp_acceptance_and_frozen_boundary():
    d=json.loads((ROOT/'qualification/host_compat_benchmark_semantics_0_6_74.json').read_text())
    assert d['productization_version']=='0.6.74'
    assert d['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert d['production_zone_abi']==6048110
    z=d['zone_cpp_0667_reanalysis']
    assert (z['old_strict_fits_accept'],z['new_semantic_fits_accept'],z['new_science_accept'])==(49,62,62)
    assert z['max_material_nl1_after_semantic_closure']<0.01

def test_host_compat_checker_accepts():
    p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_host_compat_benchmark_semantics_0_6_74.py')],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'HOST_COMPAT_0674_RESULT=ACCEPT' in p.stdout
