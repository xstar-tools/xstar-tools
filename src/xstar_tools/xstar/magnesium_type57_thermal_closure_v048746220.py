from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from . import hydrogen_type6062_thermal_closure_v048746219 as v219

RELEASE = "0.6.48.7.46.21.10"
SCHEMA = "xstar-tools-v0648746220-magnesium-type57-thermal-closure-v1"
EXPECTED_TYPE57_PER_SEQUENCE = 368


def canonical_e10(value: Any) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    return format(number, ".10e")


def bit_exact(left: Any, right: Any) -> bool:
    return struct.pack("!d", float(left)) == struct.pack("!d", float(right))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


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


def audit(
    source_capture: Path,
    native_evaluations: Path,
    controller: Path | None,
    canonical_report: Path | None,
    output_csv: Path,
    sequences: Iterable[int] = range(1, 62),
) -> dict[str, Any]:
    selected = tuple(int(value) for value in sequences)
    selected_set = set(selected)
    differences: list[dict[str, Any]] = []

    # Keep the v21.9 Hydrogen Type-60/62 and post-closure Helium domains as
    # mandatory regressions.  Its temporary CSV is folded into this report only
    # when a regression appears.
    with tempfile.TemporaryDirectory(prefix="v048746220_v219_") as tmp:
        baseline_csv = Path(tmp) / "v219_differences.csv"
        baseline = v219.audit(
            source_capture, native_evaluations, controller, baseline_csv, selected
        )
        if baseline_csv.is_file():
            differences.extend(read_csv(baseline_csv))

    source_type57: dict[tuple[int, int], dict[str, str]] = {}
    source_counts: dict[int, int] = defaultdict(int)
    with (source_capture / "v0472_all61_thermal_answer_channels.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            sequence = int(row["sequence"])
            if sequence not in selected_set:
                continue
            if int(row["element_z"]) == 12 and int(row["data_type"]) == 57:
                key = (sequence, int(row["record"]))
                source_type57[key] = row
                source_counts[sequence] += 1

    native_keys: set[tuple[int, int]] = set()
    native_counts: dict[int, int] = defaultdict(int)
    native_type_mismatches = 0
    rate_rejections = 0
    energy_rejections = 0
    nonpositive_active_threshold_rows = 0
    for sequence in selected:
        diagnostic_path = (
            native_evaluations / f"evaluation_{sequence:04d}" /
            "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        )
        for row in read_csv(diagnostic_path):
            key = (sequence, int(row.get("record", "0")))
            if key not in source_type57:
                continue
            native_keys.add(key)
            native_counts[sequence] += 1
            native_type = int(row.get("data_type", "0"))
            if native_type != 57:
                native_type_mismatches += 1
                differences.append({
                    "domain": "magnesium_type57", "sequence": sequence,
                    "identity": f"record={key[1]}", "field": "data_type",
                    "source_value": 57, "native_value": native_type,
                    "source_e10": "", "native_e10": "", "bit_exact": 0,
                })
            source = source_type57[key]
            source_active = any(abs(float(source[field])) > 0.0 for field in ("ans1", "ans2", "ans5", "ans6"))
            try:
                threshold_nonpositive = float(row.get("line_energy_ev", "0")) <= 0.0
            except ValueError:
                threshold_nonpositive = True
            if source_active and threshold_nonpositive:
                nonpositive_active_threshold_rows += 1
            for field in ("ans1", "ans2"):
                if not compare_numeric(
                    differences, "magnesium_type57", sequence,
                    f"record={key[1]}", field, source[field], row[field],
                ):
                    rate_rejections += 1
            for field in ("ans5", "ans6"):
                if not compare_numeric(
                    differences, "magnesium_type57", sequence,
                    f"record={key[1]}", field, source[field], row[field],
                ):
                    energy_rejections += 1

    source_domain_exact = (
        len(source_type57) == len(selected) * EXPECTED_TYPE57_PER_SEQUENCE
        and all(source_counts[sequence] == EXPECTED_TYPE57_PER_SEQUENCE for sequence in selected)
    )
    native_inventory_exact = (
        source_domain_exact
        and set(source_type57) == native_keys
        and native_type_mismatches == 0
        and all(native_counts[sequence] == EXPECTED_TYPE57_PER_SEQUENCE for sequence in selected)
    )

    source_budget = {
        int(row["sequence"]): row
        for row in read_csv(source_capture / "v0472_all61_thermal_budget.csv")
        if int(row["sequence"]) in selected_set
    }
    budget_counts = {
        "mg_heating2": {"compared": 0, "rejected": 0},
        "mg_cooling2": {"compared": 0, "rejected": 0},
    }
    budget_differences: list[dict[str, Any]] = []
    for sequence in selected:
        rows = read_csv(native_evaluations / f"evaluation_{sequence:04d}" / "native_thermal_budget.csv")
        if sequence not in source_budget or len(rows) != 1:
            continue
        for field in budget_counts:
            budget_counts[field]["compared"] += 1
            if not compare_numeric(
                budget_differences, "thermal_budget", sequence, "fixed_evaluation",
                field, source_budget[sequence][field], rows[0][field],
            ):
                budget_counts[field]["rejected"] += 1

    required_gates = {
        "V21_9_HYDROGEN_HELIUM_REGRESSION": "ACCEPT" if baseline.get("result") == "ACCEPT" else "REJECT",
        "MAGNESIUM_TYPE57_SOURCE_DOMAIN_EXACT": "ACCEPT" if source_domain_exact else "REJECT",
        "MAGNESIUM_TYPE57_NATIVE_INVENTORY_EXACT": "ACCEPT" if native_inventory_exact else "REJECT",
        "MAGNESIUM_TYPE57_ANS1_ANS2_IEEE_E10": "ACCEPT" if native_inventory_exact and rate_rejections == 0 else "REJECT",
        "MAGNESIUM_TYPE57_ANS5_ANS6_IEEE_E10": "ACCEPT" if native_inventory_exact and energy_rejections == 0 else "REJECT",
        "MAGNESIUM_TYPE57_ACTIVE_SOURCE_THRESHOLDS_POSITIVE": "ACCEPT" if native_inventory_exact and nonpositive_active_threshold_rows == 0 else "REJECT",
    }
    focused_result = "ACCEPT" if all(value == "ACCEPT" for value in required_gates.values()) else "REJECT"

    controller_summary: dict[str, Any] = {}
    if controller is not None and (controller / "native_dsec_summary.json").is_file():
        controller_summary = json.loads((controller / "native_dsec_summary.json").read_text())
    canonical: dict[str, Any] = {}
    if canonical_report is not None and canonical_report.is_file():
        canonical = json.loads(canonical_report.read_text())

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "domain", "sequence", "identity", "field", "source_value", "native_value",
        "source_e10", "native_e10", "bit_exact",
    )
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(differences)
        writer.writerows(budget_differences)

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": focused_result,
        "focused_scientific_result": focused_result,
        "required_gates": required_gates,
        "magnesium_type57": {
            "expected_records_per_sequence": EXPECTED_TYPE57_PER_SEQUENCE,
            "source_rows": len(source_type57),
            "native_rows": len(native_keys),
            "source_counts_by_sequence": dict(sorted(source_counts.items())),
            "native_counts_by_sequence": dict(sorted(native_counts.items())),
            "data_type_mismatches": native_type_mismatches,
            "ans1_ans2_rejections": rate_rejections,
            "ans5_ans6_rejections": energy_rejections,
            "nonpositive_active_serialized_threshold_rows": nonpositive_active_threshold_rows,
        },
        "v21_9_regression": {
            "result": baseline.get("result", "REJECT"),
            "gates": baseline.get("gates", {}),
        },
        "thermal_budget_progress": budget_counts,
        "focused_rejections": len(differences),
        "first_focused_rejection": differences[0] if differences else None,
        "canonical": {
            "result": canonical.get("result", "NOT_RUN"),
            "accepted_roundoff_differences": canonical.get("accepted_roundoff_differences"),
            "rejected_differences": canonical.get("rejected_differences"),
            "first_rejection": canonical.get("first_rejection"),
        },
        "controller": {
            "result": controller_summary.get("result", "NOT_RUN"),
            "source_trajectory_diverged": controller_summary.get("source_trajectory_diverged", False),
            "divergence_sequence": controller_summary.get("divergence_sequence"),
            "total_evaluations": controller_summary.get("total_evaluations", 0),
            "python_callbacks": controller_summary.get("python_callbacks"),
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
    parser.add_argument("--native-controller", type=Path)
    parser.add_argument("--canonical-report", type=Path)
    parser.add_argument("--sequences", default="1-61")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.source_capture.resolve(), args.native_evaluations.resolve(),
            args.native_controller.resolve() if args.native_controller else None,
            args.canonical_report.resolve() if args.canonical_report else None,
            args.output_csv.resolve(), parse_sequences(args.sequences),
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "focused_scientific_result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
