from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import magnesium_type50_cooling_v04874619 as audit
from xstar_tools.xstar import v0472_all61_magnesium_type50_escape_capture as capture

ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_release_and_magnesium_source_probe_contract():
    assert xstar_tools.__version__ == "0.6.48.7.46.19.2"
    assert capture.EXPECTED_UNIQUE_RECORDS == 2420
    assert capture.EXPECTED_ROWS == 146286
    assert capture.EXPECTED_SEQUENCE_COUNTS[1] == 2196
    assert capture.EXPECTED_SEQUENCE_COUNTS[5] == 2201
    assert capture.EXPECTED_SEQUENCE_COUNTS[7] == 2420
    assert "v04874619_pending_escape" in capture._PROBE
    assert "element_z\", 0) or 0) == 12" in capture._PROBE
    assert capture._pescl(0.0) == 0.5


def test_cpp_magnesium_type50_contract():
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    for token in (
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ESCAPE_STATE",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_MAP_CSV",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_IN_BIN",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_OUT_BIN",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_PRIMARY_COOLING_REDUCTION",
        "type50_magnesium_escape_state_applied",
        "magnesium Type-50 closure energy is invalid",
    ):
        assert token in text


def test_baseline_validator_accepts_v46181(tmp_path: Path):
    source = tmp_path / "checker.json"
    output = tmp_path / "out.json"
    names = (
        "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610_PRESERVED",
        "HYDROGEN_TYPE50_ANSWERS_EXACT_8113",
        "HYDROGEN_COOLING_ALL61_EXACT",
        "V06487_FIXED_STATE_PARITY_PRESERVED",
        "DENSE_EXACT_SYSTEMS_183_PRESERVED",
        "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066",
        "PRODUCTION_PROMOTION_BLOCKED",
    )
    source.write_text(json.dumps({
        "result": "ACCEPT", "scientific_result": "ACCEPT",
        "gates": {name: "ACCEPT" for name in names},
        "native_computed_values_exact": 1066,
        "native_computed_values_total": 2440,
    }))
    completed = subprocess.run([
        sys.executable, "-m", "xstar_tools.xstar.v46181_baseline_gate_v04874619",
        str(source), "--output-json", str(output),
    ], cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(output.read_text())["result"] == "ACCEPT"


def test_synthetic_magnesium_audit_accepts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(audit, "EXPECTED_EVALUATIONS", 2)
    monkeypatch.setattr(audit, "EXPECTED_UNIQUE_RECORDS", 3)
    monkeypatch.setattr(audit, "EXPECTED_SEQUENCE_COUNTS", {1: 3, 2: 3})
    monkeypatch.setattr(audit, "EXPECTED_ROWS", 6)
    monkeypatch.setattr(audit, "EXPECTED_COMMITTED_REVERSE_ROWS", 4)
    source = tmp_path / "source"
    native = tmp_path / "native"
    output = tmp_path / "output"
    source_rows = []
    for sequence in range(1, 3):
        for record in range(1, 4):
            source_rows.append({
                "sequence": sequence, "kind": "dsec", "call_index": sequence,
                "evaluation_index": sequence, "record": record, "line_index": record,
                "tau_in": 0.0, "tau_out": 0.0, "ptmp1": 0.0, "ptmp2": 1.0,
                "ptmp_sum": 1.0, "covering_fraction": 1.0,
                "ans1": 0.0, "ans2": 2.0, "ans3": -3.0, "ans4": 0.0,
                "ans5": 0.0, "ans6": 0.0, "idest1": 1, "idest2": 2,
                "ucalc_status": "evaluated",
            })
    _write_csv(source / capture.ESCAPE_NAME, capture.ESCAPE_FIELDS, source_rows)
    native_fields = [
        "element_z", "data_type", "record", "source_position", "density_scale",
        "type50_line_index_one_based", "type50_line_tau_in", "type50_line_tau_out",
        "type50_ptmp1", "type50_ptmp2", "type50_magnesium_escape_state_applied",
    ] + [f"type50_shadow_ans{i}" for i in range(1, 7)]
    for sequence in range(1, 3):
        rows = []
        for record in range(1, 4):
            row = {
                "element_z": 12, "data_type": 50, "record": record,
                "source_position": record, "density_scale": 10.0,
                "type50_line_index_one_based": record,
                "type50_line_tau_in": 0.0, "type50_line_tau_out": 0.0,
                "type50_ptmp1": 0.0, "type50_ptmp2": 1.0,
                "type50_magnesium_escape_state_applied": 1,
            }
            for index, value in enumerate((0.0, 2.0, -3.0, 0.0, 0.0, 0.0), 1):
                row[f"type50_shadow_ans{index}"] = value
            rows.append(row)
        _write_csv(native / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv", native_fields, rows)
    ledger_fields = [
        "element_z", "data_type", "role", "sequence", "record", "call_index",
        "source_position", "compact_row", "weighted_population", "cj",
        "cooling_contribution",
    ]
    ledger_rows = []
    for sequence, record in ((1, 1), (1, 2), (2, 1), (2, 2)):
        ledger_rows.append({
            "element_z": 12, "data_type": 50, "role": "reverse_diag_loss",
            "sequence": sequence, "record": record, "call_index": sequence,
            "source_position": record, "compact_row": 2,
            "weighted_population": 0.25, "cj": 30.0,
            "cooling_contribution": 7.5,
        })
    _write_csv(native / "native_all61_thermal_diagonal_ledger.csv", ledger_fields, ledger_rows)
    component_fields = ["component", "computed_exact"]
    component_rows = [
        {"component": "mg_cooling", "computed_exact": 1},
        {"component": "mg_cooling", "computed_exact": 1},
        {"component": "h_cooling", "computed_exact": 1},
        {"component": "h_cooling", "computed_exact": 1},
    ]
    component_rows.extend(
        {"component": f"other_{index}", "computed_exact": int(index < 1123)}
        for index in range(2436)
    )
    components = tmp_path / "components.csv"
    _write_csv(components, component_fields, component_rows)
    report = audit.audit(source, native, components, output)
    assert report["result"] == "ACCEPT", report
    assert report["native_computed_values_exact"] == 1127
    assert report["committed_reverse_cooling_exact"] == 4


def test_readiness_accepts(tmp_path: Path):
    output = tmp_path / "readiness.json"
    completed = subprocess.run([
        sys.executable, str(ROOT / "check_v048746191_magnesium_runtime_active_inventory_hotfix_readiness.py"),
        "--package-dir", str(ROOT), "--output-json", str(output),
    ], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(output.read_text())["result"] == "ACCEPT"
