from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_source_port_cli_cleanup_gate_accepts():
    p = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_legacy_source_port_cli_cleanup.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "LEGACY_SOURCE_PORT_CLI_CLEANUP_RESULT=ACCEPT" in p.stdout


def test_only_public_source_port_runner_cli_remains_active():
    names = sorted(p.name for p in (ROOT / "src/xstar_tools").glob("source_port_*_cli.py"))
    assert names == ["source_port_physical_runner_cli.py"]


def test_eval2_internal_cli_is_historical_only():
    assert not (ROOT / "src/xstar_tools/source_port_dsec_eval2_internal_cli.py").exists()
    historical = ROOT / "historical/python/source_port_cli_campaign/source_port_dsec_eval2_internal_cli.py"
    if (ROOT / "historical").exists():
        assert historical.is_file()
