from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHECK=ROOT/'tools/qualification/check_type49_all_element_source_faithful_0_6_82_11.py'
def test_checker_accepts():
    p=subprocess.run([sys.executable,str(CHECK)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TYPE49_ALL_ELEMENT_SOURCE_FAITHFUL_068211_RESULT=ACCEPT' in p.stdout
