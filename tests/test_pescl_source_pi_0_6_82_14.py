from pathlib import Path
import subprocess
import sys


def test_pescl_source_pi_gate():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, str(root / "tools/qualification/check_pescl_source_pi_0_6_82_14.py")],
        cwd=root, text=True, capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "PESCL_SOURCE_PI_068214_RESULT=ACCEPT" in p.stdout
    assert "PESCL_SOURCE_PI_068214_RLOGXI_MINUS3_MINUS2=PENDING_HOST" in p.stdout
