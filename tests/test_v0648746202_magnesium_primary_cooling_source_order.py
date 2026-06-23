from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_v46202_source_probe_contract():
    from xstar_tools.xstar import v0472_all61_magnesium_primary_cooling_source_order_capture as module

    assert module.RELEASE == "0.6.48.7.46.21"
    assert module.EXPECTED_EVALUATIONS == 61
    assert module.LEDGER_NAME.endswith("source_order_ledger.csv")
    assert "source_order_index" in module.LEDGER_FIELDS
    compile(module._PROBE, "<v46202-probe>", "exec")


def test_v46202_cpp_contract():
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert text.count("XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION") == 1
    assert text.count("XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_LEDGER_CSV") == 1
    assert "magnesium_primary_pending_cooling" in text
    assert "magnesium_primary_order_state.ordered_rows" in text
    assert "magnesium_primary_cooling_source_order_applied" in text
    assert "magnesium primary-cooling source-order ledger was not fully consumed" in text


def test_v46202_baseline_gate_accepts_synthetic(tmp_path):
    from xstar_tools.xstar.v462011_baseline_gate_v048746202 import validate

    checker = tmp_path / "checker.json"
    checker.write_text(json.dumps({
        "result": "ACCEPT",
        "scientific_result": "ACCEPT",
        "mg_cooling_exact": 8,
        "mg_cooling_total": 61,
        "native_computed_values_exact": 1080,
        "native_computed_values_total": 2440,
        "gates": {
            "TYPE99_PRIMARY_COOLING_FAMILY_EXACT_61": "ACCEPT",
            "TYPE50_CORE_CLOSURE_PRESERVED": "ACCEPT",
            "MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION_REQUIRED": "ACCEPT",
            "PRODUCTION_PROMOTION_BLOCKED": "ACCEPT",
        },
    }))
    report = validate(checker)
    assert report["result"] == "ACCEPT"
    assert report["baseline_release"] == "0.6.48.7.46.20.1.1"


def test_v46202_readiness(tmp_path):
    output = tmp_path / "readiness.json"
    completed = subprocess.run([
        sys.executable,
        str(ROOT / "check_v048746202_magnesium_primary_cooling_source_order_readiness.py"),
        "--package-dir", str(ROOT),
        "--output-json", str(output),
    ], cwd=ROOT)
    assert completed.returncode == 0
    assert json.loads(output.read_text())["result"] == "ACCEPT"


def test_v46202_synthetic_source_verifier(monkeypatch, tmp_path):
    from xstar_tools.xstar import v0472_all61_magnesium_primary_cooling_source_order_capture as module

    monkeypatch.setattr(module.base, "verify", lambda bundle: {"result": "ACCEPT", "errors": []})
    ledger = []
    family = []
    for sequence in range(1, 62):
        total = 0.0
        for offset, (record, role, cj) in enumerate(((100, "forward_diag_loss", 2.0), (101, "reverse_diag_loss", 3.0)), start=1):
            population = 0.25 * offset
            cooling = population * cj
            total += cooling
            ledger.append({
                "sequence": sequence,
                "kind": "dsec",
                "call_index": 1,
                "evaluation_index": sequence,
                "source_order_index": 1000 + offset,
                "record": record,
                "data_type": 50 if offset == 1 else 99,
                "rate_type": 7,
                "ion_index": 1,
                "ion_stage": 1,
                "role": role,
                "compact_row": offset,
                "compact_column": offset,
                "idest1": 1,
                "idest2": 2,
                "cj": cj,
                "abundance": 1.0,
                "compact_population": population,
                "weighted_population": population,
                "cooling_contribution": cooling,
            })
        family.append({
            "sequence": sequence,
            "kind": "dsec",
            "call_index": 1,
            "evaluation_index": sequence,
            "positive_primary_rows": 2,
            "source_order_reduced_mg_cooling": total,
            "source_mg_cooling": total,
            "reduction_exact": 1,
        })
    write_csv(tmp_path / module.LEDGER_NAME, module.LEDGER_FIELDS, ledger)
    write_csv(tmp_path / module.FAMILY_NAME, module.FAMILY_FIELDS, family)
    report = module.verify(tmp_path)
    assert report["result"] == "ACCEPT"
    assert report["magnesium_primary_cooling_rows"] == 122
    assert report["magnesium_primary_cooling_source_order_exact"] == 61


def _synthetic_source_and_native(tmp_path: Path):
    source = tmp_path / "source"
    native = tmp_path / "native"
    output = tmp_path / "output"
    source.mkdir()
    (native / "evaluations").mkdir(parents=True)
    (source / "all61_magnesium_primary_cooling_source_order_capture_report.json").write_text(
        json.dumps({"result": "ACCEPT", "evaluations": 61})
    )

    source_rows = []
    source_family = []
    native_fields = [
        "element_z", "data_type", "rate_type", "record", "role", "compact_row",
        "cj", "cooling_contribution", "magnesium_primary_cooling_source_order_applied",
        "magnesium_primary_cooling_source_order_index",
    ]
    for sequence in range(1, 62):
        sequence_total = 0.0
        native_rows = []
        for offset, (record, dtype, role, cj, population) in enumerate((
            (100, 50, "forward_diag_loss", 2.0, 0.25),
            (101, 99, "reverse_diag_loss", 3.0, 0.5),
        ), start=1):
            cooling = population * cj
            order = 1000 + offset
            sequence_total += cooling
            source_rows.append({
                "sequence": sequence,
                "kind": "dsec",
                "call_index": 1,
                "evaluation_index": sequence,
                "source_order_index": order,
                "record": record,
                "data_type": dtype,
                "rate_type": 7,
                "ion_index": 1,
                "ion_stage": 1,
                "role": role,
                "compact_row": offset,
                "compact_column": offset,
                "idest1": 1,
                "idest2": 2,
                "cj": cj,
                "abundance": 1.0,
                "compact_population": population,
                "weighted_population": population,
                "cooling_contribution": cooling,
            })
            native_rows.append({
                "element_z": 12,
                "data_type": dtype,
                "rate_type": 7,
                "record": record,
                "role": role,
                "compact_row": offset,
                "cj": cj,
                "cooling_contribution": cooling,
                "magnesium_primary_cooling_source_order_applied": 1,
                "magnesium_primary_cooling_source_order_index": order,
            })
        source_family.append({
            "sequence": sequence,
            "kind": "dsec",
            "call_index": 1,
            "evaluation_index": sequence,
            "positive_primary_rows": 2,
            "source_order_reduced_mg_cooling": sequence_total,
            "source_mg_cooling": sequence_total,
            "reduction_exact": 1,
        })
        evaluation = native / "evaluations" / f"evaluation_{sequence:04d}"
        evaluation.mkdir()
        write_csv(evaluation / "native_thermal_diagonal_ledger.csv", native_fields, native_rows)

    from xstar_tools.xstar import v0472_all61_magnesium_primary_cooling_source_order_capture as capture
    write_csv(source / capture.LEDGER_NAME, capture.LEDGER_FIELDS, source_rows)
    write_csv(source / capture.FAMILY_NAME, capture.FAMILY_FIELDS, source_family)
    return source, native, output


def test_v46202_synthetic_audit_accepts(tmp_path):
    from xstar_tools.xstar.magnesium_primary_cooling_source_order_v048746202 import audit

    source, native, output = _synthetic_source_and_native(tmp_path)
    components = []
    exact_remaining = 1005
    for sequence in range(1, 62):
        for component in ["h_cooling", "mg_cooling"] + [f"component_{index}" for index in range(38)]:
            if component in {"h_cooling", "mg_cooling"}:
                exact = 1
            else:
                exact = int(exact_remaining > 0)
                if exact:
                    exact_remaining -= 1
            components.append({
                "sequence": sequence,
                "component": component,
                "computed_exact": exact,
                "computed_signed_delta": 0.0 if exact else 1.0,
            })
    component_path = tmp_path / "components.csv"
    write_csv(component_path, ["sequence", "component", "computed_exact", "computed_signed_delta"], components)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"result": "ACCEPT"}))

    report = audit(source, native, component_path, baseline, output)
    assert report["result"] == "ACCEPT"
    assert report["source_rows"] == 122
    assert report["source_order_exact_evaluations"] == 61
    assert report["mg_cooling_exact"] == 61
    assert report["native_computed_values_exact"] == 1127


def test_v46202_checker_accepts_synthetic(tmp_path):
    from check_v048746202_magnesium_primary_cooling_source_order import check

    audit_output = tmp_path / "audit"
    audit_output.mkdir()
    accepted_gates = {
        "MAGNESIUM_PRIMARY_COOLING_SOURCE_KEYS_EXACT": "ACCEPT",
        "MAGNESIUM_PRIMARY_COOLING_METADATA_EXACT": "ACCEPT",
        "MAGNESIUM_PRIMARY_COOLING_CONTRIBUTIONS_EXACT": "ACCEPT",
        "MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_INDICES_EXACT": "ACCEPT",
        "MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_ALL61_EXACT": "ACCEPT",
        "MAGNESIUM_COOLING_ALL61_EXACT": "ACCEPT",
        "HYDROGEN_COOLING_ALL61_PRESERVED": "ACCEPT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127": "ACCEPT",
    }
    (audit_output / "v048746202_magnesium_primary_cooling_source_order_report.json").write_text(json.dumps({
        "result": "ACCEPT",
        "scientific_result": "ACCEPT",
        "gates": accepted_gates,
        "source_rows": 122,
        "native_rows": 122,
        "mg_cooling_exact": 61,
        "mg_cooling_total": 61,
        "native_computed_values_exact": 1127,
        "native_computed_values_total": 2440,
        "production_promotion_ready": False,
    }))
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"result": "ACCEPT"}))
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"result": "ACCEPT", "evaluations": 61}))
    report = check(audit_output, baseline, source)
    assert report["result"] == "ACCEPT"
    assert report["mg_cooling_exact"] == 61
    assert report["native_computed_values_exact"] == 1127
