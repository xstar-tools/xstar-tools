from pathlib import Path
import json, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]

def test_release_version():
    sys.path.insert(0,str(ROOT/'src'))
    import xstar_tools
    assert xstar_tools.__version__=='0.6.48.7.46.19'

def test_native_source_order_contract_present():
    text=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_THERMAL_DIAGONAL_DOMAIN_SOURCE_FAITHFUL' in text
    assert 'forward_diag_loss' in text and 'reverse_diag_loss' in text
    assert 'source_order_index' in text
    assert 'last_computed_continuum_heating2 = ctx.last_computed_htcomp + ctx.last_computed_htfreef' in text
    assert 'last_computed_continuum_cooling2 = ctx.last_computed_clcomp + ctx.last_computed_clbrems' in text

def test_runner_resume_requires_diagonal_ledger():
    text=(ROOT/'run_v04874614_thermal_diagonal_domain_secondary_ledger_correction.sh').read_text()
    assert '--require-thermal-diagonal-ledger' in text
    assert 'XSTAR_QUALIFICATION_THERMAL_DIAGONAL_DOMAIN_SOURCE_FAITHFUL=1' in text
    assert 'thermal_diagonal_domain_audit' in text

def test_readiness_accepts(tmp_path):
    report=tmp_path/'readiness.json'
    proc=subprocess.run([
        sys.executable,str(ROOT/'check_v04874614_thermal_diagonal_domain_secondary_ledger_correction_readiness.py'),
        '--package-dir',str(ROOT),'--output-json',str(report)],cwd=ROOT,capture_output=True,text=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert json.loads(report.read_text())['result']=='ACCEPT'
