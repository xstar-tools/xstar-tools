from __future__ import annotations
from pathlib import Path
import subprocess, sys

def test_standalone_terminal_writer_gate():
    root=Path(__file__).resolve().parents[1]
    p=subprocess.run([sys.executable,str(root/'tools/qualification/check_standalone_terminal_writer_0_6_82_18.py')],cwd=root,text=True,capture_output=True)
    assert p.returncode==0, p.stdout+p.stderr
    assert 'STANDALONE_TERMINAL_WRITER_068218_RESULT=ACCEPT' in p.stdout
    assert 'STANDALONE_TERMINAL_WRITER_068218_TERMINAL_OWNER=RADIAL_ZONES_BACK_ACCEPTED_EVALUATION' in p.stdout
