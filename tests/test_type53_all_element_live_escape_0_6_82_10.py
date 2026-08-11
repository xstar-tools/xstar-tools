from __future__ import annotations
import math, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHECK=ROOT/'tools/qualification/check_type53_all_element_live_escape_0_6_82_10.py'
def test_checker_accepts():
    p=subprocess.run([sys.executable,str(CHECK)],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TYPE53_ALL_ELEMENT_LIVE_ESCAPE_068210_RESULT=ACCEPT' in p.stdout
def test_source_cfrac_formula_endpoints_and_mixed_case():
    def pescv(tau): return max(math.exp(-tau),1e-12)/2.0
    def ptmp(ti,to,c):
        return pescv(ti)*(1-c), pescv(to)*(1-c)+2*pescv(ti+to)*c
    ti,to=0.3,0.7
    p1,p2=ptmp(ti,to,1.0)
    assert p1==0.0
    assert math.isclose(p2,math.exp(-(ti+to)),rel_tol=0,abs_tol=1e-15)
    p1,p2=ptmp(ti,to,0.0)
    assert math.isclose(p1,pescv(ti)) and math.isclose(p2,pescv(to))
    p1,p2=ptmp(ti,to,0.4)
    assert p1>0 and p2>0
