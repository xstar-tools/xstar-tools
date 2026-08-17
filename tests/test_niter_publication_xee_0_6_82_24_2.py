from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_niter_publication_xee_source_ownership_gate():
    script = ROOT / "tools/qualification/check_niter_publication_xee_0_6_82_24_2.py"
    p = subprocess.run([sys.executable, str(script)], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "NITER_PUBLICATION_XEE_0682242_RESULT=ACCEPT" in p.stdout
