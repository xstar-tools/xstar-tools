from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from xstar_tools.xstar.v4615_baseline_gate import REQUIRED_GATES

ROOT = Path(__file__).resolve().parents[1]

def test_release_version() -> None:
    import xstar_tools
    assert xstar_tools.__version__ == "0.6.48.7.46.19.2"

def test_cpp_type50_energy_reduction_is_qualification_scoped() -> None:
    text=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_HE_NON_TYPE53_TYPE50_ENERGY_REDUCTION' in text
    assert 'contribution.ans3 = -contribution.ans2 * endpoint_energy_ev * kErgPerEv' in text
    assert 'contribution.ans4 = -contribution.ans1 * endpoint_energy_ev * kErgPerEv' in text
    assert 'requires replacement, matrix closure, and source-order Thermal reduction' in text

def test_runner_enables_type50_energy_reduction() -> None:
    text=(ROOT/'run_v04874616_helium_non_type53_cooling_family_attribution_reduction.sh').read_text()
    assert 'XSTAR_QUALIFICATION_HE_NON_TYPE53_TYPE50_ENERGY_REDUCTION=1' in text
    assert 'helium_non_type53_cooling_reduction' in text
    assert 'v04874616_helium_non_type53_cooling_report.json' in text

def test_v4615_baseline_gate_contract(tmp_path: Path) -> None:
    source=tmp_path/'checker.json'; output=tmp_path/'out.json'
    source.write_text(json.dumps({'release':'0.6.48.7.46.15','result':'ACCEPT','gates':{name:'ACCEPT' for name in REQUIRED_GATES}}))
    proc=subprocess.run([sys.executable,'-m','xstar_tools.xstar.v4615_baseline_gate',str(source),'--output-json',str(output)],cwd=ROOT,env={'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert json.loads(output.read_text())['result']=='ACCEPT'

def test_readiness_accepts(tmp_path: Path) -> None:
    output=tmp_path/'readiness.json'
    proc=subprocess.run([sys.executable,str(ROOT/'check_v04874616_helium_non_type53_cooling_family_attribution_reduction_readiness.py'),'--package-dir',str(ROOT),'--output-json',str(output)],cwd=ROOT,capture_output=True,text=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert json.loads(output.read_text())['result']=='ACCEPT'
