from pathlib import Path
import subprocess
import sys


def test_source_return_gate():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run([sys.executable, str(root/'tools/qualification/check_dsec_source_return_acceptance_0_6_82_21.py')], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'DSEC_SOURCE_RETURN_068221_RESULT=ACCEPT' in p.stdout


def test_python_source_accepted_is_separate_from_strict_convergence():
    root = Path(__file__).resolve().parents[1]
    src = (root/'src/xstar_tools/xstar/dsec.py').read_text()
    assert 'def converged(self) -> bool:' in src
    assert 'return bool(self.lnerr == 0 and self.charge_converged and thermal_ok)' in src
    assert 'def source_accepted(self) -> bool:' in src
    assert 'return bool(self.source_returned and not self.prefix_terminated)' in src


def test_python_source_accepted_allows_source_lnerr_diagnostics():
    root = Path(__file__).resolve().parents[1]
    src = (root/'src/xstar_tools/xstar/dsec.py').read_text()
    # Source acceptance deliberately does not inspect lnerr or the strict flags.
    start = src.index('def source_accepted(self) -> bool:')
    ret = next(line.strip() for line in src[start:].splitlines() if line.strip().startswith('return bool('))
    assert ret == 'return bool(self.source_returned and not self.prefix_terminated)'


def test_prefix_trace_is_not_complete_source_acceptance():
    root = Path(__file__).resolve().parents[1]
    src = (root/'src/xstar_tools/xstar/dsec.py').read_text()
    assert 'self.source_returned and not self.prefix_terminated' in src


def test_host_gate_is_locked_to_cfrac0_xim2(tmp_path):
    root = Path(__file__).resolve().parents[1]
    runner = root/'tools/qualification/run_c5_cfrac00_xim2_host_smoke_0_6_82_21.py'
    out = tmp_path/'prepared'
    p = subprocess.run([sys.executable, str(runner), 'prepare', '--package', str(root), '--output-root', str(out), '--replace'], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    manifest = (out/'qualification_manifest.json').read_text()
    assert '"cfrac": [\n    0.0\n  ]' in manifest
    assert '"rlogxi": [\n    -2.0\n  ]' in manifest
    assert 'C5_CFRAC00_XIM2_068221_PREPARED=' in p.stdout


def test_host_gate_rejects_other_case(tmp_path):
    root = Path(__file__).resolve().parents[1]
    runner = root/'tools/qualification/run_c5_cfrac00_xim2_host_smoke_0_6_82_21.py'
    p = subprocess.run([sys.executable, str(runner), 'prepare', '--package', str(root), '--output-root', str(tmp_path/'bad'), '--cfrac', '0.4', '--rlogxi', '-2'], cwd=root, capture_output=True, text=True)
    assert p.returncode == 2
    assert 'first host gate is locked to cfrac=0, rlogxi=-2' in p.stderr


def test_staged_gate_runs_xim2_then_wide_only():
    root = Path(__file__).resolve().parents[1]
    src = (root/'tools/qualification/run_c5_cfrac00_staged_0_6_82_21.py').read_text()
    assert '"first": ("-2",)' in src
    assert '"wide": ("-5", "-4", "-3", "-2", "-1", "0", "1", "2", "3", "4", "5")' in src
    assert 'for stage in ("first", "wide"):' in src
    assert 'Option-1 material-line comparison' in src
