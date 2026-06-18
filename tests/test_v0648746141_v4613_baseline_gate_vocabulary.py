from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _base_gates() -> dict[str, str]:
    return {
        "ALL_61_THERMAL_EVALUATIONS": "ACCEPT",
        "ALL_61_THERMAL_POPULATION_STATE_EXACT": "ACCEPT",
        "THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149": "ACCEPT",
        "ALL_61_THERMAL_COMPACT_POPULATION_FINGERPRINTS_EXACT": "ACCEPT",
        "THERMAL_COMPONENT_CLOSURE_AUDIT": "ACCEPT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT",
        "V06488_THERMAL_PARITY": "ACCEPT",
    }


def _run(tmp_path: Path, gates: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict]:
    source = tmp_path / "checker.json"
    source.write_text(
        json.dumps(
            {
                "release": "0.6.48.7.46.13",
                "gates": gates,
            }
        )
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "xstar_tools.xstar.v4613_baseline_gate_vocabulary",
            str(source),
        ],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout.split("\nV04874614_BASELINE", 1)[0])
    return proc, payload


def test_concrete_production_v4613_vocabulary_accepts(tmp_path: Path) -> None:
    gates = _base_gates()
    gates.update(
        {
            "BASELINE_V461212_QUALIFICATION_PRESERVED": "ACCEPT",
            "FULL_LEVEL_FIXED_STATE_PRODUCT_UNCHANGED_41968": "ACCEPT",
            "ION_STAGE_PRODUCT_UNCHANGED_1098": "ACCEPT",
            "DENSE_EXACT_SYSTEMS_183_PRESERVED": "ACCEPT",
            "DENSE_MISMATCH_CELLS_ZERO_PRESERVED": "ACCEPT",
        }
    )
    proc, payload = _run(tmp_path, gates)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["result"] == "ACCEPT"
    assert payload["fixed_state_gate_mode"] == "concrete_v4613_gates"


def test_aggregate_alias_accepts(tmp_path: Path) -> None:
    gates = _base_gates()
    gates["V06487_FIXED_STATE_PARITY_PRESERVED"] = "ACCEPT"
    proc, payload = _run(tmp_path, gates)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["fixed_state_gate_mode"] == "aggregate_alias"


def test_incomplete_concrete_vocabulary_rejects(tmp_path: Path) -> None:
    gates = _base_gates()
    gates.update(
        {
            "BASELINE_V461212_QUALIFICATION_PRESERVED": "ACCEPT",
            "FULL_LEVEL_FIXED_STATE_PRODUCT_UNCHANGED_41968": "ACCEPT",
            "ION_STAGE_PRODUCT_UNCHANGED_1098": "ACCEPT",
            "DENSE_EXACT_SYSTEMS_183_PRESERVED": "ACCEPT",
        }
    )
    proc, payload = _run(tmp_path, gates)
    assert proc.returncode == 2
    assert payload["result"] == "REJECT"
    assert "fixed_state:DENSE_MISMATCH_CELLS_ZERO_PRESERVED" in payload["errors"]


def test_runner_uses_hotfix_validator() -> None:
    text = (ROOT / "run_v04874614_thermal_diagonal_domain_secondary_ledger_correction.sh").read_text()
    assert "v4613_baseline_gate_vocabulary" in text
    assert "20260725-v4613-baseline-gate-vocabulary-v2" in text
