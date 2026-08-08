from pathlib import Path
import subprocess, sys
ROOT = Path(__file__).resolve().parents[1]
def test_cpp_history_cleanup_gate():
    p=subprocess.run([sys.executable, str(ROOT/'tools/qualification/check_cpp_history_cleanup.py')], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode==0, p.stdout+p.stderr
    assert 'CPP_HISTORY_CLEANUP_RESULT=ACCEPT' in p.stdout
