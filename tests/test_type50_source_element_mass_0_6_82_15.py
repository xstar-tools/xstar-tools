from pathlib import Path
import subprocess
import sys


def test_type50_source_element_mass_gate():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, str(root / "tools/qualification/check_type50_source_element_mass_0_6_82_15.py")],
        cwd=root, text=True, capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "TYPE50_SOURCE_ELEMENT_MASS_068215_RESULT=ACCEPT" in p.stdout
    assert "TYPE50_SOURCE_ELEMENT_MASS_068215_RLOGXI_MINUS3_MINUS2=PENDING_HOST" in p.stdout
