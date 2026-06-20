"""Audit v46.19 source-faithful Mg Type-50 escape transport and primary cooling."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.20"
SCHEMA = "xstar-tools-v0648746191-magnesium-type50-primary-cooling-audit-v1"
EXPECTED_EVALUATIONS = 61
EXPECTED_UNIQUE_RECORDS = 2420
EXPECTED_SEQUENCE_COUNTS = {
    **{sequence: 2196 for sequence in range(1, 5)},
    **{sequence: 2201 for sequence in range(5, 7)},
    **{sequence: 2420 for sequence in range(7, EXPECTED_EVALUATIONS + 1)},
}
EXPECTED_ROWS = sum(EXPECTED_SEQUENCE_COUNTS.values())
EXPECTED_COMMITTED_REVERSE_ROWS = 146286


def _rows(path: Path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _exact(a: Any, b: Any) -> bool:
    try:
        return float(a).hex() == float(b).hex()
    except Exception:
        return str(a) == str(b)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def audit(source_capture: Path, native_run: Path, component_comparison: Path,
          output: Path) -> dict[str, Any]:
    errors: list[str] = []
    output.mkdir(parents=True, exist_ok=True)
    source_path = source_capture / "v0472_all61_magnesium_type50_escape.csv"
    if not source_path.is_file():
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"missing:{source_path}"], "gates": {},
            "qualification_only": True, "production_promotion_ready": False,
        }

    source_rows = _rows(source_path)
    source = {(int(row["sequence"]), int(row["record"])): row for row in source_rows}
    source_counts: dict[int, int] = {}
    for sequence, _record in source:
        source_counts[sequence] = source_counts.get(sequence, 0) + 1
    source_unique_records = {record for _sequence, record in source}
    if len(source_rows) != len(source):
        errors.append(f"duplicate_source_keys={len(source_rows) - len(source)}")
    if source_counts != EXPECTED_SEQUENCE_COUNTS:
        errors.append(f"source_records_by_sequence={source_counts}")
    if len(source_unique_records) != EXPECTED_UNIQUE_RECORDS:
        errors.append(
            f"source_unique_records={len(source_unique_records)} expected={EXPECTED_UNIQUE_RECORDS}"
        )
    native: dict[tuple[int, int], dict[str, str]] = {}
    density_scale: dict[tuple[int, int], float] = {}
    for sequence in range(1, EXPECTED_EVALUATIONS + 1):
        path = native_run / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        if not path.is_file():
            errors.append(f"missing_native_records:{sequence}")
            continue
        for row in _rows(path):
            if (int(row.get("element_z", "0")) == 12 and
                    int(row.get("data_type", "0")) == 50 and
                    row.get("type50_magnesium_escape_state_applied") == "1"):
                key = (sequence, int(row["record"]))
                native[key] = row
                density_scale[key] = float(row["density_scale"])
    if set(native) != set(source):
        missing = set(source) - set(native)
        extra = set(native) - set(source)
        errors.append(f"native_source_domain_mismatch=missing:{len(missing)},extra:{len(extra)}")

    fields = [
        "sequence", "call_index", "record", "source_position", "line_index",
        "native_line_index", "tau_in", "native_tau_in", "tau_out", "native_tau_out",
        "ptmp1", "native_ptmp1", "ptmp2", "native_ptmp2",
    ] + [f"ans{i}" for i in range(1, 7)] + [f"native_ans{i}" for i in range(1, 7)] + [
        "line_index_exact", "tau_in_exact", "tau_out_exact", "ptmp1_exact",
        "ptmp2_exact", "answers_exact",
    ]
    comparisons: list[dict[str, Any]] = []
    counts = {name: 0 for name in ("line", "tau_in", "tau_out", "ptmp1", "ptmp2", "answers")}
    call_summary = {call: {"rows": 0, "exact": 0} for call in range(1, 5)}
    for key, source_row in sorted(source.items()):
        native_row = native.get(key)
        if native_row is None:
            errors.append(f"missing_native:{key[0]}:{key[1]}")
            continue
        call = int(source_row["call_index"])
        call_summary[call]["rows"] += 1
        values = {
            "line": int(source_row["line_index"]) == int(native_row["type50_line_index_one_based"]),
            "tau_in": _exact(source_row["tau_in"], native_row["type50_line_tau_in"]),
            "tau_out": _exact(source_row["tau_out"], native_row["type50_line_tau_out"]),
            "ptmp1": _exact(source_row["ptmp1"], native_row["type50_ptmp1"]),
            "ptmp2": _exact(source_row["ptmp2"], native_row["type50_ptmp2"]),
            "answers": all(_exact(source_row[f"ans{i}"], native_row[f"type50_shadow_ans{i}"]) for i in range(1, 7)),
        }
        for name, value in values.items():
            counts[name] += int(value)
        all_exact = all(values.values()) and native_row.get("type50_magnesium_escape_state_applied") == "1"
        call_summary[call]["exact"] += int(all_exact)
        row: dict[str, Any] = {
            "sequence": key[0], "call_index": call, "record": key[1],
            "source_position": native_row.get("source_position", ""),
            "line_index": source_row["line_index"],
            "native_line_index": native_row["type50_line_index_one_based"],
            "tau_in": source_row["tau_in"], "native_tau_in": native_row["type50_line_tau_in"],
            "tau_out": source_row["tau_out"], "native_tau_out": native_row["type50_line_tau_out"],
            "ptmp1": source_row["ptmp1"], "native_ptmp1": native_row["type50_ptmp1"],
            "ptmp2": source_row["ptmp2"], "native_ptmp2": native_row["type50_ptmp2"],
        }
        for i in range(1, 7):
            row[f"ans{i}"] = source_row[f"ans{i}"]
            row[f"native_ans{i}"] = native_row[f"type50_shadow_ans{i}"]
        row.update({
            "line_index_exact": int(values["line"]), "tau_in_exact": int(values["tau_in"]),
            "tau_out_exact": int(values["tau_out"]), "ptmp1_exact": int(values["ptmp1"]),
            "ptmp2_exact": int(values["ptmp2"]), "answers_exact": int(values["answers"]),
        })
        comparisons.append(row)

    comparison_path = output / "v04874619_magnesium_type50_escape_comparison.csv"
    with comparison_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(comparisons)

    ledger_path = native_run / "native_all61_thermal_diagonal_ledger.csv"
    committed_rows = 0
    committed_cj_exact = 0
    committed_cooling_exact = 0
    diagonal_comparison: list[dict[str, Any]] = []
    if not ledger_path.is_file():
        errors.append(f"missing:{ledger_path}")
    else:
        for row in _rows(ledger_path):
            if not (int(row.get("element_z", "0")) == 12 and
                    int(row.get("data_type", "0")) == 50 and
                    row.get("role") == "reverse_diag_loss"):
                continue
            key = (int(row["sequence"]), int(row["record"]))
            source_row = source.get(key)
            if source_row is None:
                errors.append(f"missing_source_for_diagonal:{key[0]}:{key[1]}")
                continue
            committed_rows += 1
            expected_cj = -float(source_row["ans3"]) * density_scale[key]
            expected_cooling = float(row["weighted_population"]) * expected_cj
            cj_exact = _exact(expected_cj, row["cj"])
            cooling_exact = _exact(expected_cooling, row["cooling_contribution"])
            committed_cj_exact += int(cj_exact)
            committed_cooling_exact += int(cooling_exact)
            diagonal_comparison.append({
                "sequence": key[0], "call_index": row["call_index"],
                "source_position": row["source_position"], "record": key[1],
                "compact_row": row["compact_row"], "weighted_population": row["weighted_population"],
                "source_ans3": source_row["ans3"], "density_scale": density_scale[key],
                "expected_cj": expected_cj, "native_cj": row["cj"],
                "expected_cooling_contribution": expected_cooling,
                "native_cooling_contribution": row["cooling_contribution"],
                "cj_exact": int(cj_exact), "cooling_contribution_exact": int(cooling_exact),
            })
    diagonal_fields = [
        "sequence", "call_index", "source_position", "record", "compact_row",
        "weighted_population", "source_ans3", "density_scale", "expected_cj",
        "native_cj", "expected_cooling_contribution", "native_cooling_contribution",
        "cj_exact", "cooling_contribution_exact",
    ]
    with (output / "v04874619_magnesium_type50_reverse_cooling_comparison.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=diagonal_fields)
        writer.writeheader(); writer.writerows(diagonal_comparison)

    components = _rows(component_comparison)
    mg = [row for row in components if row.get("component") == "mg_cooling"]
    hydrogen = [row for row in components if row.get("component") == "h_cooling"]
    mg_exact = sum(int(row.get("computed_exact", "0")) for row in mg)
    h_exact = sum(int(row.get("computed_exact", "0")) for row in hydrogen)
    native_exact = sum(int(row.get("computed_exact", "0")) for row in components)
    total = len(components)

    all_record_exact = (
        len(comparisons) == EXPECTED_ROWS and
        all(row["line_index_exact"] == 1 and row["tau_in_exact"] == 1 and
            row["tau_out_exact"] == 1 and row["ptmp1_exact"] == 1 and
            row["ptmp2_exact"] == 1 and row["answers_exact"] == 1
            for row in comparisons)
    )
    gates = {
        "ALL_61_MAGNESIUM_TYPE50_ESCAPE_STATES_CAPTURED": "ACCEPT" if len(source) == EXPECTED_ROWS and source_counts == EXPECTED_SEQUENCE_COUNTS and len(source_unique_records) == EXPECTED_UNIQUE_RECORDS else "REJECT",
        "ALL_61_MAGNESIUM_TYPE50_NATIVE_RECORDS_ATTRIBUTED": "ACCEPT" if set(native) == set(source) and len(native) == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_LINE_INDICES_EXACT_146286": "ACCEPT" if counts["line"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_LINE_TAU_VALUES_EXACT_292572": "ACCEPT" if counts["tau_in"] + counts["tau_out"] == 2 * EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ESCAPE_FACTORS_EXACT_292572": "ACCEPT" if counts["ptmp1"] + counts["ptmp2"] == 2 * EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANSWERS_EXACT_146286": "ACCEPT" if counts["answers"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286": "ACCEPT" if committed_rows == EXPECTED_COMMITTED_REVERSE_ROWS and committed_cj_exact == EXPECTED_COMMITTED_REVERSE_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286": "ACCEPT" if committed_rows == EXPECTED_COMMITTED_REVERSE_ROWS and committed_cooling_exact == EXPECTED_COMMITTED_REVERSE_ROWS else "REJECT",
        "MAGNESIUM_COOLING_ALL61_EXACT": "ACCEPT" if len(mg) == EXPECTED_EVALUATIONS and mg_exact == EXPECTED_EVALUATIONS else "REJECT",
        "HYDROGEN_COOLING_ALL61_PRESERVED": "ACCEPT" if len(hydrogen) == EXPECTED_EVALUATIONS and h_exact == EXPECTED_EVALUATIONS else "REJECT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127": "ACCEPT" if native_exact == 1127 and total == 2440 else "REJECT",
        "MAGNESIUM_TYPE50_UNEXPLAINED_DELTAS_ZERO": "ACCEPT" if all_record_exact and committed_rows == committed_cj_exact == committed_cooling_exact == EXPECTED_COMMITTED_REVERSE_ROWS else "REJECT",
    }
    errors.extend(name for name, value in gates.items() if value != "ACCEPT")

    summary_rows = [{"call_index": call, **info} for call, info in sorted(call_summary.items())]
    with (output / "v04874619_magnesium_type50_family_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["call_index", "rows", "exact"])
        writer.writeheader(); writer.writerows(summary_rows)

    return {
        "schema": SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "gates": gates, "source_rows": len(source), "native_rows": len(native),
        "source_unique_records": len(source_unique_records),
        "source_records_by_sequence": {str(key): value for key, value in sorted(source_counts.items())},
        "comparison_rows": len(comparisons), "line_indices_exact": counts["line"],
        "tau_values_exact": counts["tau_in"] + counts["tau_out"],
        "escape_factors_exact": counts["ptmp1"] + counts["ptmp2"],
        "answers_exact_records": counts["answers"],
        "committed_reverse_rows": committed_rows,
        "committed_reverse_cj_exact": committed_cj_exact,
        "committed_reverse_cooling_exact": committed_cooling_exact,
        "mg_cooling_exact": mg_exact, "mg_cooling_total": len(mg),
        "hydrogen_cooling_exact": h_exact, "hydrogen_cooling_total": len(hydrogen),
        "native_computed_values_exact": native_exact,
        "native_computed_values_total": total,
        "call_summary": summary_rows,
        "qualification_only": True, "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--component-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.source_capture.resolve(), args.native_run.resolve(),
                       args.component_comparison.resolve(), args.output.resolve())
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT",
                  "errors": [str(exc)], "gates": {}, "qualification_only": True,
                  "production_promotion_ready": False}
    _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
