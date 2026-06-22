from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import tempfile
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from . import magnesium_type99_leveltemp_closure_v048746223 as v223

RELEASE = "0.6.48.7.46.21.13.1"
SCHEMA = "xstar-tools-v06487462231-type68-source-constants-and-residual-attribution-v1"
TARGET_FAMILIES = ((12, 68), (12, 73), (12, 95), (2, 53))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_e10(value: Any) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    return format(number, ".10e")


def bit_exact(left: Any, right: Any) -> bool:
    return struct.pack("!d", float(left)) == struct.pack("!d", float(right))


def compare_numeric(
    differences: list[dict[str, Any]], domain: str, sequence: int,
    identity: str, field: str, source: Any, native: Any,
) -> bool:
    source_e10 = canonical_e10(source)
    native_e10 = canonical_e10(native)
    equal = source_e10 == native_e10
    if not equal:
        differences.append({
            "domain": domain,
            "sequence": sequence,
            "identity": identity,
            "field": field,
            "source_value": source,
            "native_value": native,
            "source_e10": source_e10,
            "native_e10": native_e10,
            "bit_exact": int(bit_exact(source, native)),
        })
    return equal


def _case_record_types(native_case: Path) -> dict[tuple[int, int], int]:
    elements = {
        int(row["element_index"]): int(row["element_z"])
        for row in read_csv(native_case / "elements.csv")
    }
    result: dict[tuple[int, int], int] = {}
    for row in read_csv(native_case / "records.csv"):
        z = elements[int(row["element_index"])]
        result[(z, int(row["record"]))] = int(row["data_type"])
    return result


def _parse_answer_identity(identity: str) -> tuple[int, int] | None:
    values: dict[str, int] = {}
    for token in identity.split(";"):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in {"element_z", "record"}:
            try:
                values[key] = int(value)
            except ValueError:
                return None
    if "element_z" not in values or "record" not in values:
        return None
    return values["element_z"], values["record"]


def _residual_inventory(
    canonical_rejections: Path | None,
    native_case: Path,
) -> dict[str, Any]:
    if canonical_rejections is None or not canonical_rejections.is_file():
        return {"result": "NOT_RUN", "families": {}}
    record_types = _case_record_types(native_case)
    counts: Counter[tuple[int, int]] = Counter()
    fields: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    records: dict[tuple[int, int], set[int]] = defaultdict(set)
    sequences: dict[tuple[int, int], set[int]] = defaultdict(set)
    relative_errors: dict[tuple[int, int], list[float]] = defaultdict(list)
    native_source_ratios: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row in read_csv(canonical_rejections):
        if row.get("category") != "canonical_answer_channels":
            continue
        identity = _parse_answer_identity(row.get("identity", ""))
        if identity is None:
            continue
        z, record = identity
        key = (z, record_types.get((z, record), -1))
        if key not in TARGET_FAMILIES:
            continue
        counts[key] += 1
        fields[key][row.get("field", "")] += 1
        records[key].add(record)
        sequences[key].add(int(row["sequence"]))
        try:
            source_value = float(row["source_value"])
            native_value = float(row["native_value"])
            if source_value != 0.0:
                relative_errors[key].append((native_value - source_value) / source_value)
                native_source_ratios[key].append(native_value / source_value)
        except (KeyError, TypeError, ValueError):
            pass
    result: dict[str, Any] = {}
    labels = {(12, 68): "magnesium_type68", (12, 73): "magnesium_type73",
              (12, 95): "magnesium_type95", (2, 53): "helium_type53"}
    next_checks = {
        (12, 68): "legacy Boltzmann and collision-channel eV-to-erg constants",
        (12, 73): "literal Type-73 wavelength energy versus compact-row endpoint delta",
        (12, 95): "Type-95 ionization-rate and detailed-balance kernel operation order",
        (2, 53): "Helium Type-53 phint53 energy-channel accumulation and final rounding",
    }
    for key in TARGET_FAMILIES:
        seqs = sorted(sequences[key])
        rel = relative_errors[key]
        ratios = native_source_ratios[key]
        result[labels[key]] = {
            "rejected_values": counts[key],
            "fields": dict(sorted(fields[key].items())),
            "records": len(records[key]),
            "first_sequence": seqs[0] if seqs else None,
            "last_sequence": seqs[-1] if seqs else None,
            "relative_error_min": min(rel) if rel else None,
            "relative_error_median": statistics.median(rel) if rel else None,
            "relative_error_max": max(rel) if rel else None,
            "native_source_ratio_min": min(ratios) if ratios else None,
            "native_source_ratio_max": max(ratios) if ratios else None,
            "recommended_next_check": next_checks[key],
        }
    return {"result": "ACCEPT", "families": result}


def audit(
    source_capture: Path,
    native_evaluations: Path,
    native_case: Path,
    controller: Path | None,
    canonical_report: Path | None,
    canonical_rejections: Path | None,
    output_csv: Path,
    sequences: Iterable[int] = range(1, 62),
) -> dict[str, Any]:
    selected = tuple(int(value) for value in sequences)
    selected_set = set(selected)
    differences: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="v0487462231_v223_") as tmp:
        baseline_csv = Path(tmp) / "v223_differences.csv"
        baseline = v223.audit(
            source_capture, native_evaluations, native_case, controller,
            canonical_report, baseline_csv, selected,
        )

    source_type68: dict[tuple[int, int], dict[str, str]] = {}
    source_counts: Counter[int] = Counter()
    for row in read_csv(source_capture / "v0472_all61_thermal_answer_channels.csv"):
        sequence = int(row["sequence"])
        if sequence in selected_set and int(row["element_z"]) == 12 and int(row["data_type"]) == 68:
            key = (sequence, int(row["record"]))
            source_type68[key] = row
            source_counts[sequence] += 1

    native_keys: set[tuple[int, int]] = set()
    native_counts: Counter[int] = Counter()
    answer_rejections = 0
    for sequence in selected:
        path = (
            native_evaluations / f"evaluation_{sequence:04d}" / "qualification_diagnostics" /
            f"evaluation_{sequence:04d}_records.csv"
        )
        for row in read_csv(path):
            if int(row.get("element_z", "0")) != 12 or int(row.get("data_type", "0")) != 68:
                continue
            key = (sequence, int(row["record"]))
            if key not in source_type68:
                continue
            native_keys.add(key)
            native_counts[sequence] += 1
            source = source_type68[key]
            for field in ("ans5", "ans6"):
                if not compare_numeric(
                    differences, "magnesium_type68", sequence,
                    f"record={key[1]}", field, source[field], row[field],
                ):
                    answer_rejections += 1

    source_domain_exact = (
        bool(source_type68)
        and all(source_counts[sequence] > 0 for sequence in selected)
        and len(set(source_counts.values())) == 1
    )
    native_inventory_exact = (
        source_domain_exact
        and set(source_type68) == native_keys
        and all(native_counts[sequence] == source_counts[sequence] for sequence in selected)
    )

    source_budget = {
        int(row["sequence"]): row
        for row in read_csv(source_capture / "v0472_all61_thermal_budget.csv")
        if int(row["sequence"]) in selected_set
    }
    cooling_compared = 0
    cooling_rejections = 0
    for sequence in selected:
        rows = read_csv(native_evaluations / f"evaluation_{sequence:04d}" / "native_thermal_budget.csv")
        if sequence not in source_budget or len(rows) != 1:
            continue
        cooling_compared += 1
        if not compare_numeric(
            differences, "thermal_budget", sequence, "fixed_evaluation", "mg_cooling2",
            source_budget[sequence]["mg_cooling2"], rows[0]["mg_cooling2"],
        ):
            cooling_rejections += 1

    v223_gates = baseline.get("required_gates", {})
    v223_required = (
        "V21_12_TYPE49_REGRESSION",
        "FOCUSED_ANALYZER_COMPLETES_WITHOUT_RECURSION",
        "MAGNESIUM_TYPE99_CONTEXT_LAYOUT_EXACT",
        "MAGNESIUM_TYPE99_BOUND_ENERGY_IEEE_E10",
        "MAGNESIUM_TYPE99_PARENT_ENERGY_IEEE_E10",
        "MAGNESIUM_TYPE99_STATISTICAL_WEIGHT_RATIO_IEEE_E10",
        "MAGNESIUM_TYPE99_ANS3_ANS4_IEEE_E10",
        "MAGNESIUM_TYPE99_ANS5_ANS6_IEEE_E10",
    )
    v223_ok = all(v223_gates.get(name) == "ACCEPT" for name in v223_required)
    v21_12_ok = v223_gates.get("V21_12_TYPE49_REGRESSION") == "ACCEPT"
    v21_11_ok = (
        baseline.get("v21_12_regression", {}).get("required_gates", {})
        .get("V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION") == "ACCEPT"
    )

    required_gates = {
        "V21_13_TYPE99_AND_PRIOR_REGRESSION": "ACCEPT" if v223_ok else "REJECT",
        "V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION": "ACCEPT" if v21_11_ok else "REJECT",
        "V21_12_TYPE49_REGRESSION": "ACCEPT" if v21_12_ok else "REJECT",
        "MAGNESIUM_TYPE68_SOURCE_DOMAIN_EXACT": "ACCEPT" if source_domain_exact else "REJECT",
        "MAGNESIUM_TYPE68_NATIVE_INVENTORY_EXACT": "ACCEPT" if native_inventory_exact else "REJECT",
        "MAGNESIUM_TYPE68_ANS5_ANS6_IEEE_E10": "ACCEPT" if native_inventory_exact and answer_rejections == 0 else "REJECT",
        "MAGNESIUM_COOLING2_ALL_SELECTED_IEEE_E10": "ACCEPT" if (
            cooling_compared == len(selected) and cooling_rejections == 0
        ) else "REJECT",
    }
    focused_result = "ACCEPT" if all(value == "ACCEPT" for value in required_gates.values()) else "REJECT"

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields_out = (
        "domain", "sequence", "identity", "field", "source_value", "native_value",
        "source_e10", "native_e10", "bit_exact",
    )
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields_out)
        writer.writeheader()
        writer.writerows(differences)

    canonical: dict[str, Any] = {}
    if canonical_report is not None and canonical_report.is_file():
        canonical = json.loads(canonical_report.read_text())
    residuals = _residual_inventory(canonical_rejections, native_case)
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": focused_result,
        "focused_scientific_result": focused_result,
        "required_gates": required_gates,
        "magnesium_type68": {
            "source_rows": len(source_type68),
            "native_rows": len(native_keys),
            "records_per_sequence": sorted(set(source_counts.values())),
            "ans5_ans6_rejections": answer_rejections,
            "source_constants": {
                "boltzmann_ev_per_t4": 0.861707,
                "collision_rate_coefficient_per_sqrt_t4": 8.626e-8,
                "collision_erg_per_ev": 1.602197e-12,
            },
        },
        "thermal_budget_progress": {
            "mg_cooling2": {"compared": cooling_compared, "rejected": cooling_rejections},
        },
        "residual_family_attribution": residuals,
        "v21_13_regression": {
            "result": baseline.get("result", "REJECT"),
            "required_gates": v223_gates,
        },
        "focused_rejections": len(differences),
        "first_focused_rejection": differences[0] if differences else None,
        "canonical": {
            "result": canonical.get("result", "NOT_RUN"),
            "accepted_roundoff_differences": canonical.get("accepted_roundoff_differences"),
            "rejected_differences": canonical.get("rejected_differences"),
            "first_rejection": canonical.get("first_rejection"),
        },
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def parse_sequences(text: str) -> tuple[int, ...]:
    values: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            first, last = token.split("-", 1)
            values.update(range(int(first), int(last) + 1))
        else:
            values.add(int(token))
    return tuple(sorted(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-evaluations", type=Path, required=True)
    parser.add_argument("--native-case", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path)
    parser.add_argument("--canonical-report", type=Path)
    parser.add_argument("--canonical-rejections", type=Path)
    parser.add_argument("--sequences", default="1-61")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.source_capture.resolve(), args.native_evaluations.resolve(),
            args.native_case.resolve(),
            args.native_controller.resolve() if args.native_controller else None,
            args.canonical_report.resolve() if args.canonical_report else None,
            args.canonical_rejections.resolve() if args.canonical_rejections else None,
            args.output_csv.resolve(), parse_sequences(args.sequences),
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [str(exc)], "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
