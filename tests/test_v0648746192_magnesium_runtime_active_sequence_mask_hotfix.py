from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import xstar_tools

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_cpp_sequence_mask_contract():
    assert xstar_tools.__version__ == "0.6.48.7.46.20"
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ACTIVE_RECORDS_CSV" in text
    assert "magnesium_escape.active_records.count(record.record) != 0" in text
    assert "expected_active = state.source_sequence <= 4 ? 2196u" in text
    assert "active magnesium Type-50 record is missing from source line-index map" in text


def test_audit_filters_to_applied_runtime_domain():
    text = (ROOT / "src/xstar_tools/xstar/magnesium_type50_cooling_v04874619.py").read_text()
    assert 'row.get("type50_magnesium_escape_state_applied") == "1"' in text
    assert "EXPECTED_ROWS = sum(EXPECTED_SEQUENCE_COUNTS.values())" in text


def test_actual_capture_has_exact_sequence_domain():
    path_text = os.environ.get("V04874619_ACTUAL_ESCAPE_CSV", "")
    if not path_text:
        return
    path = Path(path_text)
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts = Counter(int(row["sequence"]) for row in rows)
    expected = {**{i: 2196 for i in range(1, 5)}, **{i: 2201 for i in range(5, 7)}, **{i: 2420 for i in range(7, 62)}}
    assert counts == expected
    assert len(rows) == 146286
    assert len({int(row["record"]) for row in rows}) == 2420


def test_causal_gate_accepts_actual_failure(tmp_path: Path):
    manifest_text = os.environ.get("V048746191_ACTUAL_MANIFEST", "")
    log_text = os.environ.get("V048746191_ACTUAL_LOG", "")
    source_text = os.environ.get("V048746191_ACTUAL_SOURCE_REPORT", "")
    if not all((manifest_text, log_text, source_text)):
        return
    output = tmp_path / "report.json"
    completed = subprocess.run([
        sys.executable, "-m", "xstar_tools.xstar.v46191_sequence_mask_gate_v048746192",
        manifest_text, log_text, "--source-capture-report", source_text,
        "--output-json", str(output),
    ], cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["failure_classification"] == "MISSING_RUNTIME_ACTIVE_SEQUENCE_MASK"
    assert report["source_recapture_required"] is False


def test_runner_usage_and_active_record_transport():
    runner = ROOT / "run_v048746192_magnesium_runtime_active_sequence_mask_hotfix.sh"
    completed = subprocess.run([str(runner)], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 64
    assert "failed-v46.19.1-output" in completed.stderr
    text = runner.read_text()
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ACTIVE_RECORDS_CSV" in text
    assert "v46191_sequence_mask_gate_v048746192" in text
    assert "V048746192_SOURCE_CAPTURE_REUSE=ACCEPT" in text
