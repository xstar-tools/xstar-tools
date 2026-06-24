from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "src/xstar_tools/benchmarks/v0648746232_python_fits_schema"
ORACLE = ROOT / "src/xstar_tools/benchmarks/v064874622_product_oracles/python_physical_run/xout_step.raw.log"


def test_exact_prefix_asset() -> None:
    prefix = SCHEMA / "xout_step_prefix.log"
    assert prefix.is_file()
    assert len(prefix.read_text().splitlines()) == 91
    assert hashlib.sha256(prefix.read_bytes()).hexdigest() == "28d2ce41dde84abad5dbf559e7b7c0e58a33f7bf9dc0fc3a1d582d17e5c5b2d0"
    assert prefix.read_bytes() == b"".join(ORACLE.read_bytes().splitlines(keepends=True)[:91])


def test_source_writes_distinct_logs() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    writer = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    assert 'std::ofstream native_trace(std::filesystem::path(options.output_dir) / "native_dsec_trace.log")' in source
    assert 'copy_file(\n            step, output / "native_dsec_trace.log"' not in source
    assert 'output_dir / "xout_step.log"' in writer
    assert "write_python_step_log_prefix" in writer


def test_comparator_accepts_prefix_and_rejects_duplicate(tmp_path: Path) -> None:
    prefix = (SCHEMA / "xout_step_prefix.log").read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    (output / "xout_step.log").write_bytes(prefix)
    (output / "native_dsec_trace.log").write_text("native dsec trajectory\nsequence=1\n")
    report = tmp_path / "report.json"
    command = [
        sys.executable,
        str(ROOT / "compare_v048746232_xout_step.py"),
        "--output-dir", str(output),
        "--expected-log", str(ORACLE),
        "--output-json", str(report),
    ]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    data = json.loads(report.read_text())
    assert data["gates"]["XOUT_STEP_EXACT_PREFIX"] == "ACCEPT"
    assert data["gates"]["XOUT_STEP_DISTINCT_FROM_NATIVE_TRACE"] == "ACCEPT"
    assert data["gates"]["XOUT_STEP_PARITY"] == "IN_PROGRESS"
    assert data["first_difference"]["line"] == 92

    (output / "native_dsec_trace.log").write_bytes(prefix)
    duplicate = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert duplicate.returncode == 2
    data = json.loads(report.read_text())
    assert data["gates"]["XOUT_STEP_DISTINCT_FROM_NATIVE_TRACE"] == "REJECT"
