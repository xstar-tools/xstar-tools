from pathlib import Path
import subprocess, sys

def test_type50_cfrac_full_grid_gate():
    root=Path(__file__).resolve().parents[1]
    p=subprocess.run([sys.executable, str(root/'tools/qualification/check_type50_cfrac_full_grid_0_6_82_19.py')], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'TYPE50_CFRAC_FULL_GRID_068219_RESULT=ACCEPT' in p.stdout


def test_cfrac_runner_loads_019_base():
    import importlib.util
    root=Path(__file__).resolve().parents[1]
    path=root/'tools/qualification/run_c5_cfrac_wide_rlogxi_host_smoke_0_6_82_19.py'
    spec=importlib.util.spec_from_file_location('cfrac019', path)
    assert spec is not None and spec.loader is not None
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    base=mod.load_base(root)
    assert base.EXPECTED_CPP_VERSION == '0.6.82.19'
