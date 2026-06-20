"""Audit Mg Type-99 destination and secondary-energy correction for v0.6.48.7.46.20.1."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.20.1"
SCHEMA = "xstar-tools-v064874615-mg-type99-destination-secondary-energy-v1"
AFFECTED_RECORDS = {39855, 40060, 41154}


def _bits(v: str | float) -> bytes:
    return struct.pack(">d", float(v))


def _exact(a: str | float, b: str | float) -> bool:
    try:
        x, y = float(a), float(b)
    except Exception:
        return False
    return math.isfinite(x) and math.isfinite(y) and _bits(x) == _bits(y)


def _load_records(root: Path) -> dict[tuple[int, int, int, int], dict[str, str]]:
    out: dict[tuple[int, int, int, int], dict[str, str]] = {}
    diag = root / "qualification_diagnostics"
    for sequence in range(1, 62):
        path = diag / f"evaluation_{sequence:04d}_records.csv"
        if not path.is_file():
            raise FileNotFoundError(path)
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("data_type") != "99" or row.get("type99_shadow_valid") != "1":
                    continue
                key = (sequence, int(row["element_z"]), int(row["record"]), int(row["source_position"]))
                if key in out:
                    raise ValueError(f"duplicate Type-99 identity: {key}")
                out[key] = row
    return out


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def audit(native_run: Path, baseline_v048746141: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    new = _load_records(native_run)
    old = _load_records(baseline_v048746141 / "native_all61")
    errors: list[str] = []
    if set(new) != set(old):
        errors.append("type99_identity_inventory")

    mg_total = mg_identity = mg_nonidentity = 0
    identity_applied = identity_factor_one = identity_ans5_pre_exact = 0
    changed_rows = unchanged_rows = 0
    changed_only_ans5 = 0
    negative_identity = 0
    corrected_negative = 0
    max_abs_corrected_ans5 = 0.0
    changed_records: Counter[int] = Counter()
    rows_out: list[dict[str, Any]] = []

    for key in sorted(set(new) & set(old)):
        sequence, element_z, record, source_position = key
        n, b = new[key], old[key]
        if element_z != 12:
            continue
        mg_total += 1
        identity = n.get("type99_destination_threshold_identity") == "1"
        if identity:
            mg_identity += 1
            applied = n.get("type99_destination_identity_correction_applied") == "1"
            identity_applied += applied
            identity_factor_one += _exact(n.get("type99_ans5_energy_correction_factor", "nan"), 1.0)
            identity_ans5_pre_exact += _exact(n["type99_shadow_ans5"], n.get("type99_ans5_pre_energy_correction", "nan"))
            denominator = float(n.get("type99_ans5_energy_correction_denominator", "nan"))
            if denominator < 0.0:
                negative_identity += 1
                corrected_negative += applied and _exact(n.get("type99_ans5_energy_correction_factor", "nan"), 1.0)
                max_abs_corrected_ans5 = max(max_abs_corrected_ans5, abs(float(n["type99_shadow_ans5"])))
        else:
            mg_nonidentity += 1

        changed_fields = [
            field for field in ("type99_shadow_ans1", "type99_shadow_ans2", "type99_shadow_ans3",
                                "type99_shadow_ans4", "type99_shadow_ans5", "type99_shadow_ans6")
            if not _exact(n[field], b[field])
        ]
        if changed_fields:
            changed_rows += 1
            changed_records[record] += 1
            changed_only_ans5 += changed_fields == ["type99_shadow_ans5"]
            rows_out.append({
                "sequence": sequence,
                "source_position": source_position,
                "record": record,
                "destination_energy_ev": n["type99_destination_energy_ev"],
                "bound_energy_ev": n["type99_bound_energy_ev"],
                "threshold_ev": n["type99_threshold_ev"],
                "energy_difference_ev": n.get("type99_energy_difference_ev"),
                "signed_denominator": n.get("type99_ans5_energy_correction_denominator"),
                "old_ans5": b["type99_shadow_ans5"],
                "new_ans5": n["type99_shadow_ans5"],
                "pre_energy_correction_ans5": n.get("type99_ans5_pre_energy_correction"),
                "correction_factor": n.get("type99_ans5_energy_correction_factor"),
                "changed_fields": ";".join(changed_fields),
            })
        else:
            unchanged_rows += 1

    csv_path = output / "v04874615_mg_type99_corrected_rows.csv"
    fields = list(rows_out[0]) if rows_out else ["sequence", "record"]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows_out)

    target = next((row for (sequence, element_z, record, _), row in new.items()
                   if sequence == 23 and element_z == 12 and record == 41154), {})
    target_ok = bool(target) and _exact(target.get("type99_ans5_energy_correction_factor", "nan"), 1.0) \
        and target.get("type99_destination_identity_correction_applied") == "1" \
        and abs(float(target.get("type99_shadow_ans5", "inf"))) < 1.0e-10

    gates = {
        "MG_TYPE99_RECORDS_793": "ACCEPT" if mg_total == 793 else "REJECT",
        "MG_TYPE99_DESTINATION_IDENTITIES_732": "ACCEPT" if mg_identity == 732 else "REJECT",
        "MG_TYPE99_NONIDENTITY_RECORDS_61_PRESERVED": "ACCEPT" if mg_nonidentity == 61 else "REJECT",
        "DESTINATION_IDENTITY_CORRECTION_APPLIED_732": "ACCEPT" if identity_applied == 732 else "REJECT",
        "DESTINATION_IDENTITY_FACTORS_EXACT_ONE_732": "ACCEPT" if identity_factor_one == 732 else "REJECT",
        "DESTINATION_IDENTITY_ANS5_PRECORRECTION_EXACT_732": "ACCEPT" if identity_ans5_pre_exact == 732 else "REJECT",
        "NEGATIVE_SIGNED_DENOMINATORS_CORRECTED_166": "ACCEPT" if negative_identity == corrected_negative == 166 else "REJECT",
        "ONLY_THREE_MG_TYPE99_RECORDS_CHANGED": "ACCEPT" if set(changed_records) == AFFECTED_RECORDS else "REJECT",
        "ONLY_ANS5_CHANGED_IN_166_ROWS": "ACCEPT" if changed_rows == changed_only_ans5 == 166 else "REJECT",
        "UNCHANGED_MG_TYPE99_ROWS_627": "ACCEPT" if unchanged_rows == 627 else "REJECT",
        "CORRECTED_MG_TYPE99_ANS5_SOURCE_SCALE": "ACCEPT" if max_abs_corrected_ans5 < 1.0e-10 else "REJECT",
        "RECORD_41154_SEQUENCE23_CORRECTED": "ACCEPT" if target_ok else "REJECT",
    }
    result = "ACCEPT" if not errors and all(v == "ACCEPT" for v in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "milestone_scope": "qualification-only Mg Type-99 source-faithful destination and secondary-energy correction",
        "type99_records_total_all_elements": len(new),
        "mg_type99_records": mg_total,
        "mg_destination_identity_records": mg_identity,
        "mg_nonidentity_records": mg_nonidentity,
        "negative_signed_denominator_records": negative_identity,
        "changed_rows": changed_rows,
        "unchanged_rows": unchanged_rows,
        "changed_record_counts": {str(k): v for k, v in sorted(changed_records.items())},
        "max_abs_corrected_negative_denominator_ans5": max_abs_corrected_ans5,
        "record_41154_sequence23": {k: target.get(k) for k in (
            "type99_destination_energy_ev", "type99_bound_energy_ev", "type99_threshold_ev",
            "type99_energy_difference_ev", "type99_ans5_pre_energy_correction",
            "type99_ans5_energy_correction_denominator", "type99_ans5_energy_correction_factor",
            "type99_shadow_ans5", "type99_destination_identity_correction_applied")},
        "gates": gates,
        "errors": errors + [k for k, v in gates.items() if v != "ACCEPT"],
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    _write_json(output / "v04874615_mg_type99_secondary_energy_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--native-run", type=Path, required=True)
    p.add_argument("--baseline-v048746141", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--output-json", type=Path)
    a = p.parse_args(argv)
    try:
        report = audit(a.native_run, a.baseline_v048746141, a.output)
    except Exception as exc:
        report = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if a.output_json:
        _write_json(a.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
