from pathlib import Path
import subprocess, sys

def test_lcpres_pressure_source_gate():
    root=Path(__file__).resolve().parents[1]
    p=subprocess.run([sys.executable,str(root/'tools/qualification/check_lcpres_pressure_0_6_82_25.py')],cwd=root,text=True,capture_output=True)
    assert p.returncode==0, p.stdout+p.stderr
    assert 'LCPRES_PRESSURE_068225_RESULT=ACCEPT' in p.stdout

def test_no_public_abi_bump_for_pressure_control():
    root=Path(__file__).resolve().parents[1]
    h=(root/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    p=(root/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    assert '60487' in h
    assert '6048110' in p
