from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def test_python_hc1_stage_gate():
    p=subprocess.run([sys.executable, str(ROOT/'tools/qualification/check_python_hc1_stage_0_6_82_24_3.py')], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode == 0, p.stdout+p.stderr
    assert 'PYTHON_HC1_STAGE_0682243_RESULT=ACCEPT' in p.stdout
