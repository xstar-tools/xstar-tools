from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHECK=ROOT/'tools/qualification/check_msolvelucy_fixed_loop_0_6_82_9.py'
CPP=ROOT/'src/xstar_tools/xstar/cpp/element_engine.cpp'
def test_checker_accepts():
    p=subprocess.run([sys.executable,str(CHECK)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'MSOLVELUCY_FIXED_LOOP_06829_RESULT=ACCEPT' in p.stdout
def test_no_cpp_only_diff2_break():
    s=CPP.read_text()
    assert 'if (fixed_diff >= 1.0e3) break;' not in s
    assert 'Canonical msolvelucy.f90 uses diff2 >= 1.e3 only to stop' in s
