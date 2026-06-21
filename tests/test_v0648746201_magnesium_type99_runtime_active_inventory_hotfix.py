from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_v46201_corrected_inventory_contract():
    from xstar_tools.xstar import v0472_all61_magnesium_type99_primary_cooling_capture as capture
    assert capture.RELEASE == "0.6.48.7.46.21.5"
    assert capture.EXPECTED_UCALC_ROWS == 661
    assert capture.EXPECTED_UCALC_UNIQUE_RECORDS == 11
    assert capture.EXPECTED_UCALC_RECORD_COUNTS == capture.EXPECTED_ACTIVE_RECORD_COUNTS
    assert capture.EXPECTED_DIAGONAL_ROWS == 1322


def test_v46201_causal_classifier_actual_host_capture(tmp_path):
    from xstar_tools.xstar.v4620_runtime_inventory_gate_v048746201 import validate
    path = Path("/mnt/data/v4620_review/v04874620_magnesium_type99_primary_cooling/v04874620_source_capture_verification.json")
    if not path.exists():
        pytest.skip("actual v46.20 host report not mounted")
    report = validate(path)
    assert report["result"] == "ACCEPT"
    assert report["source_recapture_required"] is False
    assert report["physics_changed"] is False


def test_v46201_actual_capture_verifies():
    from xstar_tools.xstar import v0472_all61_magnesium_type99_primary_cooling_capture as capture
    path = Path("/mnt/data/v4620_review/v04874620_magnesium_type99_primary_cooling/v0472_all61_magnesium_type99_primary_cooling_capture")
    if not path.exists():
        pytest.skip("actual v46.20 capture not mounted")
    report = capture.verify(path)
    assert report["result"] == "ACCEPT"
    assert report["magnesium_type99_ucalc_rows"] == 661
    assert report["magnesium_type99_unique_ucalc_records"] == 11
    assert report["magnesium_type99_primary_thermal_rows"] == 1322


def test_v46201_readiness(tmp_path):
    out = tmp_path / "readiness.json"
    cp = subprocess.run([
        sys.executable,
        str(ROOT / "check_v048746201_magnesium_type99_runtime_active_inventory_hotfix_readiness.py"),
        "--package-dir", str(ROOT),
        "--output-json", str(out),
    ], cwd=ROOT)
    assert cp.returncode == 0
    assert json.loads(out.read_text())["result"] == "ACCEPT"


def test_v46201_runner_contract():
    runner = ROOT / "run_v048746201_magnesium_type99_runtime_active_inventory_hotfix.sh"
    text = runner.read_text()
    assert "V048746201_SOURCE_CAPTURE_REUSE=ACCEPT" in text
    assert "v4620_runtime_inventory_gate_v048746201" in text
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_REDUCTION=1" in text
    assert "SOURCE_ARCHIVE" not in text
    assert "ATDB=" not in text
    assert subprocess.run(["bash", "-n", str(runner)]).returncode == 0
    assert subprocess.run([str(runner)], cwd=ROOT).returncode == 64
