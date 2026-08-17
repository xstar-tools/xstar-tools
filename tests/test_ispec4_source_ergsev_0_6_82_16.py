from pathlib import Path
import subprocess
import sys


def test_ispec4_source_ergsev_gate():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, str(root / "tools/qualification/check_ispec4_source_ergsev_0_6_82_16.py")],
        cwd=root, text=True, capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ISPEC4_SOURCE_ERGSEV_068216_RESULT=ACCEPT" in p.stdout
    assert "ISPEC4_SOURCE_ERGSEV_068216_RLOGXI_MINUS3_MINUS2=PENDING_HOST" in p.stdout
