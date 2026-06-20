from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import magnesium_type50_cooling_v04874619 as audit
from xstar_tools.xstar import v0472_all61_magnesium_type50_escape_capture as capture

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_active_inventory_contract():
    assert xstar_tools.__version__ == "0.6.48.7.46.20"
    assert capture.EXPECTED_UNIQUE_RECORDS == 2420
    assert capture.EXPECTED_ROWS == 146286
    assert capture.EXPECTED_SEQUENCE_COUNTS == audit.EXPECTED_SEQUENCE_COUNTS
    assert sorted(set(capture.EXPECTED_SEQUENCE_COUNTS.values())) == [2196, 2201, 2420]
    assert sum(capture.EXPECTED_SEQUENCE_COUNTS.values()) == 146286


def test_cpp_requires_runtime_active_map():
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "size() != 2420" in text
    assert "exactly 2420 runtime-active records" in text
    assert "exactly 2454 records" not in text


def test_v4619_causal_inventory_gate_accepts(tmp_path: Path):
    source = tmp_path / "old.json"
    output = tmp_path / "new.json"
    source.write_text(json.dumps({
        "result": "REJECT",
        "errors": [
            "escape_rows=146286 expected=149694",
            "records_per_evaluation=[2196, 2201, 2420]",
            "line_map_rows=2420 unique=2420",
        ],
        "evaluations": 61,
        "line_index_map_rows": 2420,
        "line_workspace_files": 122,
        "magnesium_type50_escape_rows": 146286,
        "thermal_capture_result": "ACCEPT",
        "qualification_only": True,
        "production_promotion_ready": False,
    }))
    completed = subprocess.run([
        sys.executable, "-m", "xstar_tools.xstar.v4619_runtime_inventory_gate_v048746191",
        str(source), "--output-json", str(output),
    ], cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["source_recapture_required"] is False


def test_hotfix_runner_contract():
    runner = ROOT / "run_v048746191_magnesium_runtime_active_inventory_hotfix.sh"
    completed = subprocess.run([str(runner)], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 64
    assert "failed-v46.19-output" in completed.stderr
    text = runner.read_text()
    assert "V048746191_SOURCE_CAPTURE_REUSE=ACCEPT" in text
    assert "v4619_runtime_inventory_gate_v048746191" in text
