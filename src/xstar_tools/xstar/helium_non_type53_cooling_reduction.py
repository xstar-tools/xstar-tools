"""Audit helium non-Type53 Type-50 cooling reduction for v0.6.48.7.46.19.1."""
from __future__ import annotations
import argparse, csv, json, math, struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.19.1"
SCHEMA = "xstar-tools-v064874616-helium-nontype53-cooling-reduction-v1"
ERG_PER_EV = 1.602176634e-12
EXPECTED_RECORD_COUNTS = {
    826: 37, 840: 37, 936: 37, 937: 37, 938: 18,
    1696: 37, 1697: 37, 1698: 18, 1699: 37,
    1704: 37, 1705: 37, 1706: 37, 1730: 37,
    1731: 37, 1784: 37, 1785: 37,
}
NUMERIC_FIELDS = (
    "abundance", "compact_population", "weighted_population", "cj", "cj2",
    "heating_contribution", "cooling_contribution", "heating2_contribution", "cooling2_contribution",
)

def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as h: return list(csv.DictReader(h))

def _bits(v: str | float) -> bytes: return struct.pack(">d", float(v))
def _exact(a: str | float, b: str | float) -> bool:
    try: x, y = float(a), float(b)
    except Exception: return False
    return math.isfinite(x) and math.isfinite(y) and _bits(x) == _bits(y)

def _identity(row: dict[str, str]) -> tuple[Any, ...]:
    return tuple(row.get(k, "") for k in (
        "sequence", "element_z", "source_order_index", "source_position", "record",
        "data_type", "rate_type", "ion_index", "ion_stage", "compact_row", "role",
    ))

def _load_diag(path: Path) -> dict[tuple[Any, ...], dict[str, str]]:
    out: dict[tuple[Any, ...], dict[str, str]] = {}
    for row in _rows(path):
        key = _identity(row)
        if key in out: raise ValueError(f"duplicate diagonal identity: {key}")
        out[key] = row
    return out

def _load_record_oracle(native_run: Path) -> dict[tuple[int, int, int], dict[str, str]]:
    out: dict[tuple[int, int, int], dict[str, str]] = {}
    diag = native_run / "qualification_diagnostics"
    for seq in range(1, 62):
        path = diag / f"evaluation_{seq:04d}_records.csv"
        for row in _rows(path):
            if row.get("element_z") != "2" or row.get("data_type") != "50" or row.get("matrix_committed") != "1":
                continue
            key = (seq, int(row["record"]), int(row["source_position"]))
            out[key] = row
    return out

def _load_closure(matrix_dir: Path) -> dict[tuple[int, int, int, int, int], dict[str, str]]:
    out: dict[tuple[int, int, int, int, int], dict[str, str]] = {}
    for seq in range(1, 62):
        path = matrix_dir / f"sequence_{seq:04d}_element_02_contributions.csv"
        for row in _rows(path):
            key = (seq, int(row["record"]), int(row["data_type"]), int(row["rate_type"]), int(row["ion_stage"]))
            out[key] = row
    return out

def _component_map(path: Path) -> dict[tuple[int, str], dict[str, str]]:
    return {(int(r["sequence"]), r["component"]): r for r in _rows(path)}

def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def audit(native_run: Path, baseline_v04874615: Path, matrix_dir: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    new_path = native_run / "native_all61_thermal_diagonal_ledger.csv"
    old_path = baseline_v04874615 / "native_all61" / "native_all61_thermal_diagonal_ledger.csv"
    comp_path = output / "v04874612_all61_thermal_component_comparison.csv"
    for p in (new_path, old_path, comp_path):
        if not p.is_file(): errors.append(f"missing:{p}")
    if errors:
        report = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors,
                  "qualification_only": True, "production_promotion_ready": False}
        _write_json(output / "v04874616_helium_non_type53_cooling_report.json", report)
        return report

    record_oracle = _load_record_oracle(native_run)
    closure = _load_closure(matrix_dir)
    changed_rows: list[dict[str, Any]] = []
    changed_records: Counter[int] = Counter()
    changed_sequences: set[int] = set()
    illegal_changes = 0; formula_exact = 0; cooling_exact = 0
    type50_old_by_seq: dict[int, float] = defaultdict(float)
    type50_new_by_seq: dict[int, float] = defaultdict(float)
    rows_compared = 0

    # Stream the million-row ledgers in lockstep.  Their canonical source order
    # is itself part of the v46.14/v46.15 contract, so a positional comparison
    # is both stricter and far less memory-intensive than materializing maps.
    with new_path.open(newline="") as nh, old_path.open(newline="") as oh:
        nr, br = csv.DictReader(nh), csv.DictReader(oh)
        for n, b in zip(nr, br):
            rows_compared += 1
            if _identity(n) != _identity(b):
                errors.append(f"diagonal_identity_order:{rows_compared}")
                break
            changed = [field for field in NUMERIC_FIELDS if not _exact(n[field], b[field])]
            seq = int(n["sequence"])
            if n["element_z"] == "2" and n["data_type"] == "50" and n["role"] == "reverse_diag_loss":
                type50_old_by_seq[seq] += float(b["cooling_contribution"])
                type50_new_by_seq[seq] += float(n["cooling_contribution"])
            if not changed: continue
            allowed = (n["element_z"] == "2" and n["data_type"] == "50" and
                       n["role"] == "reverse_diag_loss" and
                       set(changed).issubset({"cj", "cooling_contribution"}))
            if not allowed:
                illegal_changes += 1
                continue
            record = int(n["record"]); source_position = int(n["source_position"])
            rate_type = int(n["rate_type"]); ion_stage = int(n["ion_stage"])
            oracle = record_oracle.get((seq, record, source_position))
            corr = closure.get((seq, record, 50, rate_type, ion_stage))
            expected_cj = expected_cooling = float("nan")
            if oracle and corr and corr.get("replace_ans2") == "1":
                expected_cj = ((float(corr["source_ans2"]) * float(oracle["type50_endpoint_energy_ev"])) * ERG_PER_EV) * float(oracle["density_scale"])
                expected_cooling = float(n["weighted_population"]) * expected_cj
                formula_exact += _exact(n["cj"], expected_cj)
                cooling_exact += _exact(n["cooling_contribution"], expected_cooling)
            changed_records[record] += 1; changed_sequences.add(seq)
            changed_rows.append({
                "sequence": seq, "source_order_index": n["source_order_index"],
                "source_position": source_position, "record": record, "rate_type": rate_type,
                "ion_stage": ion_stage, "compact_row": n["compact_row"],
                "endpoint_energy_ev": oracle.get("type50_endpoint_energy_ev") if oracle else "",
                "density_scale": oracle.get("density_scale") if oracle else "",
                "closure_source_ans2": corr.get("source_ans2") if corr else "",
                "old_cj": b["cj"], "new_cj": n["cj"], "expected_cj": format(expected_cj, ".17g"),
                "old_cooling_contribution": b["cooling_contribution"],
                "new_cooling_contribution": n["cooling_contribution"],
                "expected_cooling_contribution": format(expected_cooling, ".17g"),
                "changed_fields": ";".join(changed),
            })
        if next(nr, None) is not None or next(br, None) is not None:
            errors.append("diagonal_row_count")

    components = _component_map(comp_path)
    family_rows: list[dict[str, Any]] = []
    source_scale = 0; family_delta_closed = 0
    max_abs = 0.0; max_rel = 0.0
    for seq in range(1, 62):
        row = components[(seq, "he_non_type53_cooling")]
        source = float(row["source_value"]); current = float(row["computed_native_value"])
        # Recover baseline family value using the exact Type-50 ledger delta.
        baseline = current + type50_old_by_seq[seq] - type50_new_by_seq[seq]
        residual = current - source
        abs_residual = abs(residual); rel = abs_residual / abs(source) if source else abs_residual
        max_abs = max(max_abs, abs_residual); max_rel = max(max_rel, rel)
        source_scale += abs_residual <= 5.0e-21
        family_delta_closed += abs((baseline - current) - (type50_old_by_seq[seq] - type50_new_by_seq[seq])) <= 5.0e-21
        family_rows.append({
            "sequence": seq, "source_he_non_type53_cooling": format(source, ".17g"),
            "baseline_he_non_type53_cooling": format(baseline, ".17g"),
            "corrected_he_non_type53_cooling": format(current, ".17g"),
            "corrected_signed_delta": format(residual, ".17g"),
            "baseline_type50_cooling": format(type50_old_by_seq[seq], ".17g"),
            "corrected_type50_cooling": format(type50_new_by_seq[seq], ".17g"),
            "type50_cooling_delta": format(type50_new_by_seq[seq] - type50_old_by_seq[seq], ".17g"),
        })

    changed_csv = output / "v04874616_he_type50_changed_rows.csv"
    fields = list(changed_rows[0]) if changed_rows else ["sequence", "record"]
    with changed_csv.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(changed_rows)
    family_csv = output / "v04874616_he_non_type53_family_summary.csv"
    with family_csv.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(family_rows[0])); w.writeheader(); w.writerows(family_rows)

    seq61 = family_rows[-1]
    expected_counts = {str(k): v for k, v in EXPECTED_RECORD_COUNTS.items()}
    actual_counts = {str(k): v for k, v in sorted(changed_records.items())}
    gates = {
        "HE_NON_TYPE53_COOLING_ATTRIBUTED_TO_TYPE50": "ACCEPT" if illegal_changes == 0 and len(changed_rows) == 554 else "REJECT",
        "HE_TYPE50_REVERSE_ENERGY_ROWS_CHANGED_554": "ACCEPT" if len(changed_rows) == 554 else "REJECT",
        "HE_TYPE50_CHANGED_SEQUENCES_37": "ACCEPT" if len(changed_sequences) == 37 else "REJECT",
        "HE_TYPE50_CHANGED_RECORDS_16": "ACCEPT" if actual_counts == expected_counts else "REJECT",
        "HE_TYPE50_ONLY_REVERSE_CJ_CHANGED": "ACCEPT" if illegal_changes == 0 else "REJECT",
        "HE_TYPE50_SOURCE_ENERGY_FORMULA_EXACT_554": "ACCEPT" if formula_exact == 554 else "REJECT",
        "HE_TYPE50_COOLING_CONTRIBUTION_EXACT_554": "ACCEPT" if cooling_exact == 554 else "REJECT",
        "HE_NON_TYPE53_COOLING_SOURCE_SCALE_61": "ACCEPT" if source_scale == 61 and max_abs <= 5.0e-21 else "REJECT",
        "HE_NON_TYPE53_FAMILY_DELTA_CLOSED_61": "ACCEPT" if family_delta_closed == 61 else "REJECT",
        "SEQUENCE61_HE_NON_TYPE53_COOLING_CLOSED": "ACCEPT" if abs(float(seq61["corrected_signed_delta"])) <= 5.0e-21 else "REJECT",
    }
    result = "ACCEPT" if not errors and all(v == "ACCEPT" for v in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA, "release": RELEASE, "result": result,
        "milestone_scope": "qualification-only source-faithful helium non-Type53 Type-50 cooling attribution and reduction",
        "changed_rows": len(changed_rows), "changed_sequences": len(changed_sequences),
        "changed_record_counts": actual_counts, "diagonal_rows_compared": rows_compared,
        "source_formula_exact": formula_exact, "cooling_contributions_exact": cooling_exact,
        "he_non_type53_source_scale_sequences": source_scale,
        "max_abs_he_non_type53_cooling_residual": max_abs,
        "max_relative_he_non_type53_cooling_residual": max_rel,
        "sequence61": seq61, "gates": gates,
        "errors": errors + [k for k, v in gates.items() if v != "ACCEPT"],
        "qualification_only": True, "production_promotion_ready": False,
        "independent_native_thermal_parity": "NOT_ACCEPTED",
    }
    _write_json(output / "v04874616_helium_non_type53_cooling_report.json", report)
    return report

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--native-run", type=Path, required=True)
    p.add_argument("--baseline-v04874615", type=Path, required=True)
    p.add_argument("--matrix-closure-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--output-json", type=Path)
    a = p.parse_args(argv)
    try: report = audit(a.native_run, a.baseline_v04874615, a.matrix_closure_dir, a.output)
    except Exception as exc:
        report = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if a.output_json: _write_json(a.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2

if __name__ == "__main__": raise SystemExit(main())
