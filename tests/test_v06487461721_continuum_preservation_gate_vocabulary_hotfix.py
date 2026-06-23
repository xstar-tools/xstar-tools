from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import v46171_baseline_gate_v048746172


ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def baseline_checker_payload() -> dict:
    accepted = {
        name: "ACCEPT"
        for name in v46171_baseline_gate_v048746172.ACCEPTED_GATES
    }
    rejected = {
        name: "REJECT"
        for name in v46171_baseline_gate_v048746172.EXPECTED_REJECTED_GATES
    }
    return {
        "release": "0.6.48.7.46.17.1",
        "result": "REJECT",
        "scientific_result": "REJECT",
        "native_computed_values_exact": 1016,
        "gates": {**accepted, **rejected},
        "continuum_component_summary": {
            "htfreef": {"bit_exact": 48, "rows": 61, "max_ulp_distance": 2}
        },
    }


def test_package_version_and_corrected_alias_inventory() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21"
    assert "V06487_FIXED_STATE_PARITY_PRESERVED" in v46171_baseline_gate_v048746172.ACCEPTED_GATES
    assert "DENSE_EXACT_SYSTEMS_183_PRESERVED" in v46171_baseline_gate_v048746172.ACCEPTED_GATES
    assert "DENSE_MISMATCH_CELLS_ZERO_PRESERVED" in v46171_baseline_gate_v048746172.ACCEPTED_GATES


def test_corrected_baseline_validator_exports_preservation_aliases(tmp_path: Path) -> None:
    source = tmp_path / "v048746171_checker_report.json"
    output = tmp_path / "baseline.json"
    write(source, baseline_checker_payload())
    rc = v46171_baseline_gate_v048746172.main(
        [str(source), "--output-json", str(output)]
    )
    report = json.loads(output.read_text())
    assert rc == 0
    assert report["result"] == "ACCEPT"
    assert report["accepted_gates"]["V06487_FIXED_STATE_PARITY_PRESERVED"] == "ACCEPT"
    assert report["accepted_gates"]["DENSE_EXACT_SYSTEMS_183_PRESERVED"] == "ACCEPT"
    assert report["accepted_gates"]["DENSE_MISMATCH_CELLS_ZERO_PRESERVED"] == "ACCEPT"


def test_hotfix_checker_accepts_only_known_v46172_vocabulary_rejection(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "checker.json"
    exact_names = (
        "ALL_61_CONTINUUM_WORKSPACES_RECONSTRUCTED",
        "CONTINUUM_EPIM_CANONICAL_BINARY64_VALUES_EXACT_999",
        "CONTINUUM_EPIM_BINARY64_VALUES_EXACT_60939",
        "CONTINUUM_BREMSMAP_INDICES_EXACT_60939",
        "CONTINUUM_BREMSAM_VALUES_EXACT_60939",
        "CONTINUUM_WORKSPACE_CANONICAL_V0472_61",
        "CMP1_BIT_EXACT_61",
        "CMP2_BIT_EXACT_61",
        "HTCOMP_BIT_EXACT_61",
        "CLCOMP_BIT_EXACT_61",
        "HTFREEF_BIT_EXACT_61",
        "CLBREMS_BIT_EXACT_61",
        "CONTINUUM_TOTAL_COMPONENTS_BIT_EXACT_244",
        "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610",
        "CONTINUUM_UNEXPLAINED_COMPONENT_DELTAS_ZERO",
    )
    write(
        audit / "v048746172_thermal_state_consumption_report.json",
        {
            "gates": {"ALL_61_THERMAL_EVALUATIONS": "ACCEPT", "PYTHON_CALLBACKS_ZERO": "ACCEPT"},
            "thermal_component_values_exact": 2440,
            "thermal_component_values_total": 2440,
            "native_computed_values_exact": 1029,
            "native_computed_values_total": 2440,
            "native_evaluations": 61,
            "independent_native_thermal_parity": "NOT_ACCEPTED",
            "production_promotion_ready": False,
        },
    )
    write(
        audit / "v048746172_thermal_compact_population_closure_report.json",
        {
            "gates": {"THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149": "ACCEPT"},
            "fixed_state_product_modified": False,
            "production_promotion_ready": False,
        },
    )
    write(
        audit / "v048746172_thermal_diagonal_domain_report.json",
        {
            "gates": {"THERMAL_DIAGONAL_SOURCE_ORDER_STREAMS_EXACT_183": "ACCEPT"},
            "production_promotion_ready": False,
        },
    )
    write(
        audit / "v048746172_continuum_workspace_report.json",
        {
            "gates": {name: "ACCEPT" for name in exact_names},
            "component_summary": {},
            "production_promotion_ready": False,
        },
    )
    write(
        audit / "v048746172_native_replay_resume_manifest.json",
        {"result": "ACCEPT", "sequences_reusable": 61},
    )
    known = [
        "V06487_FIXED_STATE_PARITY_PRESERVED",
        "DENSE_EXACT_SYSTEMS_183_PRESERVED",
        "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
    ]
    write(
        audit / "v048746172_checker_report.json",
        {
            "release": "0.6.48.7.46.17.2",
            "result": "REJECT",
            "scientific_result": "REJECT",
            "native_computed_values_exact": 1029,
            "native_computed_values_total": 2440,
            "errors": known,
        },
    )
    write(
        baseline,
        {
            "result": "ACCEPT",
            "accepted_gates": {
                "V06487_FIXED_STATE_PARITY_PRESERVED": "ACCEPT",
                "DENSE_EXACT_SYSTEMS_183_PRESERVED": "ACCEPT",
                "DENSE_MISMATCH_CELLS_ZERO_PRESERVED": "ACCEPT",
            },
            "production_promotion_ready": False,
        },
    )
    command = [
        sys.executable,
        str(ROOT / "check_v0487461721_continuum_preservation_gate_vocabulary_hotfix.py"),
        "--audit-output",
        str(audit),
        "--baseline-v048746171-report",
        str(baseline),
        "--output-json",
        str(output),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    report = json.loads(output.read_text())
    assert completed.returncode == 0
    assert report["result"] == "ACCEPT"
    assert report["physics_changed"] is False
    assert report["native_replay_replayed"] is False
    assert report["gates"]["V046172_REJECTION_VOCABULARY_ONLY"] == "ACCEPT"
    assert report["gates"]["NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1029"] == "ACCEPT"
