from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHECK=ROOT/"tools/qualification/check_type51_all_element_production_0_6_82_12.py"
def test_checker_accepts():
    p=subprocess.run([sys.executable,str(CHECK)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert "TYPE51_ALL_ELEMENT_PRODUCTION_068212_RESULT=ACCEPT" in p.stdout
