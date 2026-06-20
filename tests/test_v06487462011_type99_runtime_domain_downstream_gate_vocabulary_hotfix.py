from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTUAL = Path("/mnt/data/v46201_review/out/v048746201_magnesium_type99_runtime_active_inventory_hotfix")


def test_v462011_causal_classifier_actual_host_result():
    from xstar_tools.xstar.v46201_downstream_gate_v0487462011 import validate
    if not ACTUAL.exists():
        pytest.skip("actual v46.20.1 output not mounted")
    report = validate(ACTUAL)
    assert report["result"] == "ACCEPT"
    assert report["failure_classification"] == "TYPE99_RUNTIME_DOMAIN_AND_DOWNSTREAM_GATE_VOCABULARY"
    assert report["source_recapture_required"] is False
    assert report["native_replay_required"] is False
    assert report["physics_changed"] is False


def test_v462011_actual_reanalysis_accepts(tmp_path):
    from xstar_tools.xstar.magnesium_type99_runtime_domain_v0487462011 import audit
    if not ACTUAL.exists():
        pytest.skip("actual v46.20.1 output not mounted")
    report = audit(ACTUAL, tmp_path)
    assert report["result"] == "ACCEPT"
    assert report["source_runtime_rows"] == 661
    assert report["native_only_rows"] == 132
    assert report["native_only_records"] == {39813: 61, 39855: 61, 40060: 6, 40359: 4}
    assert report["shared_answer_exact_by_field"]["ans2"] == 661
    assert report["shared_full_answer_rows_exact"] == 183
    assert report["shared_answer_values_exact"] == 1576
    assert report["type99_primary_cooling_rows_exact"] == 661
    assert report["type99_family_values_exact"] == 61
    assert report["mg_cooling_exact"] == 8
    assert report["native_computed_values_exact"] == 1080
    assert (tmp_path / "v0487462011_magnesium_type99_runtime_domain_classification.csv").is_file()


def test_v462011_readiness(tmp_path):
    output = tmp_path / "readiness.json"
    cp = subprocess.run([
        sys.executable,
        str(ROOT / "check_v0487462011_type99_runtime_domain_downstream_gate_vocabulary_hotfix_readiness.py"),
        "--package-dir", str(ROOT),
        "--output-json", str(output),
    ], cwd=ROOT)
    assert cp.returncode == 0
    assert json.loads(output.read_text())["result"] == "ACCEPT"


def test_v462011_runner_contract():
    runner = ROOT / "run_v0487462011_type99_runtime_domain_downstream_gate_vocabulary_hotfix.sh"
    text = runner.read_text()
    assert "V0487462011_SOURCE_CAPTURE_REUSE=ACCEPT" in text
    assert "V0487462011_NATIVE_REPLAY_REUSE=ACCEPT" in text
    assert "magnesium_type99_runtime_domain_v0487462011" in text
    assert "v46201_downstream_gate_v0487462011" in text
    assert "run-fixed-evaluation" not in text
    assert subprocess.run(["bash", "-n", str(runner)]).returncode == 0
    assert subprocess.run([str(runner)], cwd=ROOT).returncode == 64


def test_v462011_checker_vocabulary():
    text = (ROOT / "check_v0487462011_type99_runtime_domain_downstream_gate_vocabulary_hotfix.py").read_text()
    for token in (
        "TYPE99_SOURCE_RUNTIME_DOMAIN_EXACT_661",
        "TYPE99_NATIVE_ONLY_ROWS_CLASSIFIED_132",
        "TYPE99_PRIMARY_COOLING_ROWS_EXACT_661",
        "TYPE99_PRIMARY_COOLING_FAMILY_EXACT_61",
        "TYPE50_CORE_CLOSURE_PRESERVED",
        "MAGNESIUM_COOLING_EXACT_8_OF_61",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1080",
        "MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION_REQUIRED",
        "PRODUCTION_PROMOTION_BLOCKED",
    ):
        assert token in text
    assert "MAGNESIUM_COOLING_ALL61_EXACT" not in text
    assert "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127" not in text
