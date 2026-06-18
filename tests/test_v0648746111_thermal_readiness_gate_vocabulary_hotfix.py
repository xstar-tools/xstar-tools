from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import all61_fixed_state_closure


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n")


def test_version_and_source_vocabulary() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.12.1"
    source = (root() / "src/xstar_tools/xstar/all61_fixed_state_closure.py").read_text()
    assert '"V06488_THERMAL_PARITY_READY": "ACCEPT" if fixed_state_exact' in source
    assert '"V06488_THERMAL_PARITY_READY": "YES" if fixed_state_exact' not in source
    assert all61_fixed_state_closure.RELEASE == "0.6.48.7.46.12.1"


def synthetic_v46_11(path: Path) -> None:
    gates = {
        "ALL_61_ACTIVE_LEVEL_POPULATIONS_EXACT": "ACCEPT",
        "ALL_61_CHARGE_RESIDUAL_EXACT": "ACCEPT",
        "ALL_61_ELECTRON_FRACTION_EXACT": "ACCEPT",
        "ALL_61_H_HE_MG_FIXED_STATE_PARITY": "ACCEPT",
        "ALL_61_H_HE_MG_ION_POPULATIONS_EXACT": "ACCEPT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT",
    }
    dump(path / "v04874611_fixed_state_parity_closure_report.json", {
        "release": "0.6.48.7.46.11", "result": "ACCEPT", "gates": gates,
        "active_level_exact_count": 41968, "active_level_total": 41968,
        "ion_exact_count": 1098, "ion_total": 1098,
        "electron_fraction_exact": 61, "charge_residual_exact": 61,
    })
    dump(path / "v04874611_matrix_construction_closure_report.json", {
        "release": "0.6.48.7.46.11", "result": "ACCEPT", "dense_exact_systems": 183,
        "dense_mismatch_cells": 0, "source_reconstruction_exact_systems": 183,
        "native_reconstruction_exact_systems": 183,
    })
    dump(path / "fixed_state_comparison/all61_h_he_mg_fixed_state_closure_summary.json", {
        "release": "0.6.48.7.46.11", "result": "ACCEPT", "active_level_exact_count": 41968,
        "active_level_total": 41968, "python_callbacks": 0,
        "ion_exact_counts": {"1": {"exact": 122, "total": 122}, "2": {"exact": 183, "total": 183}, "12": {"exact": 793, "total": 793}},
        "state_exact_counts": {"computed_electron_fraction": 61, "charge_residual": 61},
        "gates": {"V06487_FIXED_STATE_PARITY": "ACCEPT", "V06488_THERMAL_PARITY_READY": "YES", "THERMAL_PARITY": "NOT_RUN_READY_FOR_V06488"},
    })
    dump(path / "v04874611_attribution_report.json", {
        "release": "0.6.48.7.46.11", "result": "ACCEPT",
        "gates": {"CANONICAL_RECORD_ALIGNMENT": "ACCEPT"},
        "hydrogen_type53": {"result": "ACCEPT"},
    })
    dump(path / "v04874611_type49_type53_regression_report.json", {
        "result": "ACCEPT", "gates": {
            "MG_TYPE49_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT",
            "MG_TYPE49_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT",
            "MG_TYPE53_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT",
            "MG_TYPE53_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT",
        },
    })
    dump(path / "v04874611_mg_type51_source_faithful_report.json", {"result": "ACCEPT"})
    dump(path / "v04874611_mg_type50_endpoint_orientation_report.json", {"result": "ACCEPT"})


def test_no_replay_reanalysis_and_checker(tmp_path: Path) -> None:
    source = tmp_path / "v46.11"
    output = tmp_path / "v46.11.1"
    synthetic_v46_11(source)
    env = dict(os.environ, PYTHONPATH=str(root() / "src"))
    subprocess.run([
        sys.executable, str(root() / "reanalyze_v048746111_thermal_readiness_gate_vocabulary_hotfix.py"),
        "--v04874611-output", str(source), "--output", str(output),
    ], check=True, cwd=root(), env=env)
    normalized = json.loads((output / "fixed_state_comparison/all61_h_he_mg_fixed_state_closure_summary.json").read_text())
    assert normalized["gates"]["V06488_THERMAL_PARITY_READY"] == "ACCEPT"
    assert normalized["gates"]["THERMAL_PARITY"] == "NOT_RUN_V06488"
    assert json.loads((output / "v048746111_reanalysis_report.json").read_text())["physics_changed"] is False

    subprocess.run([
        sys.executable, str(root() / "check_v048746111_thermal_readiness_gate_vocabulary_hotfix.py"),
        "--audit-output", str(output), "--output-json", str(output / "checker.json"),
    ], check=True, cwd=root(), env=env)
    report = json.loads((output / "checker.json").read_text())
    assert report["result"] == "ACCEPT"
    assert report["gates"]["V06488_THERMAL_PARITY_READY"] == "ACCEPT"
    assert report["downstream"]["THERMAL_PARITY"] == "NOT_RUN_V06488"
