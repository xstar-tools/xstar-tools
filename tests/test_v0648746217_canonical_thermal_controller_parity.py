from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import canonical_thermal_controller_parity_v048746217 as parity

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_e10_preserves_v216_semantics() -> None:
    assert parity.canonical_e10(2.1624460966087834e-15) == "2.1624460966e-15"
    assert parity.canonical_e10(2.1624460966087830e-15) == "2.1624460966e-15"


def test_numeric_roundoff_is_accepted_but_recorded() -> None:
    recorder = parity.Recorder()
    assert recorder.numeric(
        "committed_temperature", 2, "evaluation=2", "temperature",
        2.8591353411150710e-09, 2.8591353411150713e-09,
    )
    assert len(recorder.accepted_roundoff) == 1
    assert len(recorder.rejections) == 0
    assert recorder.accepted_roundoff[0]["classification"] == "E10_ACCEPTED_ROUNDOFF"


def test_visible_e10_difference_is_rejected() -> None:
    recorder = parity.Recorder()
    assert not recorder.numeric(
        "thermal_budget", 1, "kind=dsec;call=1;evaluation=1", "h_cooling2",
        6.034766640150065e-09, 6.0347716572508278e-09,
    )
    assert len(recorder.rejections) == 1
    assert recorder.rejections[0]["classification"] == "NUMERIC_REJECT"
    assert recorder.rejections[0]["source_e10"] != recorder.rejections[0]["native_e10"]


def test_structural_fields_remain_exact() -> None:
    recorder = parity.Recorder()
    assert recorder.exact("controller_structure", 1, "call=1", "evaluation", 1, 1)
    assert not recorder.exact("controller_termination", 1, "call=1", "reason", "tolerance", "maximum_evaluations")
    assert len(recorder.rejections) == 1
    assert recorder.rejections[0]["classification"] == "STRUCTURAL_REJECT"


def test_gate_reporting_cleanup_and_readiness() -> None:
    checker = (ROOT / "check_v048746217_canonical_thermal_controller_parity.py").read_text()
    assert "PRODUCT_LEVEL_PARITY" in checker
    assert "PRODUCTION_PROMOTION_STATUS" in checker
    assert "PRODUCTION_PROMOTION_BLOCKED=ACCEPT" not in checker
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v048746217_canonical_thermal_controller_parity_readiness.py"),
            "--package-dir", str(ROOT),
            "--output-json", str(ROOT / "v048746217_test_readiness_report.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout)["result"] == "ACCEPT"


def test_checker_accepts_zero_rejection_contract(tmp_path: Path) -> None:
    checker_module = __import__(
        "check_v048746217_canonical_thermal_controller_parity",
        fromlist=["check"],
    )
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    audit = {
        "gates": {name: "ACCEPT" for name in checker_module.REQUIRED_GATES},
        "scientific_result": "ACCEPT",
        "accepted_roundoff_differences": 3,
        "rejected_differences": 0,
        "first_rejection": None,
    }
    baseline = {
        "result": "ACCEPT", "scientific_result": "ACCEPT",
        "systems_classified": 183, "systems_ieee_e10_acceptable": 183,
        "rejected_differences": 0,
    }
    source = {"result": "ACCEPT", "evaluations": 61}
    (audit_dir / "v048746217_thermal_controller_report.json").write_text(json.dumps(audit))
    baseline_path = tmp_path / "baseline.json"
    source_path = tmp_path / "source.json"
    baseline_path.write_text(json.dumps(baseline))
    source_path.write_text(json.dumps(source))
    result = checker_module.check(audit_dir, baseline_path, source_path)
    assert result["result"] == "ACCEPT"
    assert result["product_level_parity"] == "NOT_RUN"
    assert result["production_promotion_status"] == "BLOCKED_PENDING_PRODUCT_PARITY"
