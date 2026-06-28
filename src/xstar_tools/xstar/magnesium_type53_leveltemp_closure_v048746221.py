from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from . import magnesium_type57_thermal_closure_v048746220 as v230

RELEASE = "0.6.48.7.46.21.11"
SCHEMA = "xstar-tools-v0648746221-magnesium-type53-persistent-leveltemp-closure-v1"


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


def _read_numeric_vector(path: Path, cast: type[float] | type[int]) -> list[float] | list[int]:
    values: list[float] | list[int] = []
    with path.open() as handle:
        for line in handle:
            text = line.strip()
            if text:
                values.append(cast(text))
    return values


def _case_type53_candidates(native_case: Path) -> dict[int, dict[str, Any]]:
    elements = read_csv(native_case / "elements.csv")
    mg = next((row for row in elements if int(row["element_z"]) == 12), None)
    if mg is None:
        raise ValueError("native case has no Magnesium element")
    element_index = int(mg["element_index"])
    reals = _read_numeric_vector(native_case / "reals.txt", float)
    ints = _read_numeric_vector(native_case / "ints.txt", int)
    result: dict[int, dict[str, Any]] = {}
    for row in read_csv(native_case / "records.csv"):
        if int(row["element_index"]) != element_index or int(row["data_type"]) != 53:
            continue
        record = int(row["record"])
        real_offset = int(row["real_offset"])
        real_count = int(row["real_count"])
        int_offset = int(row["int_offset"])
        int_count = int(row["int_count"])
        if int_count < 4 or int(ints[int_offset + 3]) != 221:
            raise ValueError(f"Mg Type-53 record {record} lacks v21.11 leveltemp layout magic")
        if real_count < 26 or (real_count - 22) % 2 != 0:
            raise ValueError(f"Mg Type-53 record {record} has malformed v21.11 real payload")
        destination_column = int(ints[int_offset + 1])
        candidate_mask = int(ints[int_offset + 2])
        if destination_column <= 0 or candidate_mask < 0 or candidate_mask > 0x0FFF:
            raise ValueError(f"Mg Type-53 record {record} has invalid leveltemp metadata")
        context_base = real_offset + real_count - 22
        incoming_energy = float(reals[context_base + 7])
        candidates = tuple(float(reals[context_base + 10 + stage]) for stage in range(12))
        for stage, value in enumerate(candidates, start=1):
            if candidate_mask & (1 << (stage - 1)) and not math.isfinite(value):
                raise ValueError(
                    f"Mg Type-53 record {record} has non-finite stage-{stage} candidate energy"
                )
        result[record] = {
            "destination_column": destination_column,
            "candidate_mask": candidate_mask,
            "candidate_energy_ev": candidates,
            "incoming_energy_ev": incoming_energy,
        }
    if not result:
        raise ValueError("native case has no Magnesium Type-53 v21.11 candidates")
    return result


def source_leveltemp_destination_energy(
    *, ion_stage: int, active_min_stage: int, active_max_stage: int,
    destination_column: int, candidate_mask: int,
    candidate_energy_ev: tuple[float, ...], incoming_energy_ev: float,
) -> tuple[float, int, int]:
    if not 1 <= ion_stage <= 12:
        raise ValueError(f"invalid current ion stage {ion_stage}")
    if destination_column <= 0 or len(candidate_energy_ev) != 12:
        raise ValueError("invalid Type-53 persistent leveltemp candidate layout")
    if candidate_mask < 0 or candidate_mask > 0x0FFF:
        raise ValueError("invalid Type-53 persistent leveltemp candidate mask")

    def present(stage: int) -> bool:
        return 1 <= stage <= 12 and bool(candidate_mask & (1 << (stage - 1)))

    owner = 0
    for stage in range(active_min_stage, min(ion_stage, active_max_stage) + 1):
        if present(stage):
            owner = stage
    if owner == 0:
        for stage in range(active_min_stage, active_max_stage + 1):
            if present(stage):
                owner = stage
    if owner == 0:
        return float(incoming_energy_ev), 0, destination_column
    value = float(candidate_energy_ev[owner - 1])
    if not math.isfinite(value):
        raise ValueError(f"non-finite Type-53 stage-{owner} candidate energy")
    return value, owner, destination_column

def audit(
    source_capture: Path,
    native_evaluations: Path,
    native_case: Path,
    controller: Path | None,
    canonical_report: Path | None,
    output_csv: Path,
    sequences: Iterable[int] = range(1, 62),
) -> dict[str, Any]:
    selected = tuple(int(value) for value in sequences)
    selected_set = set(selected)
    differences: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="v048746221_v230_") as tmp:
        baseline_csv = Path(tmp) / "v230_differences.csv"
        baseline = v230.audit(
            source_capture, native_evaluations, controller, canonical_report,
            baseline_csv, selected,
        )
        if baseline_csv.is_file():
            differences.extend(read_csv(baseline_csv))

    source_type53: dict[tuple[int, int], dict[str, str]] = {}
    source_counts: dict[int, int] = defaultdict(int)
    with (source_capture / "v0472_all61_thermal_answer_channels.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            sequence = int(row["sequence"])
            if sequence not in selected_set:
                continue
            if int(row["element_z"]) == 12 and int(row["data_type"]) == 53:
                key = (sequence, int(row["record"]))
                source_type53[key] = row
                source_counts[sequence] += 1

    type53_candidates = _case_type53_candidates(native_case)
    native_keys: set[tuple[int, int]] = set()
    native_counts: dict[int, int] = defaultdict(int)
    type_mismatches = 0
    ans34_rejections = 0
    ans56_rejections = 0
    owner_energy_mismatches = 0
    owner_stages: dict[int, int] = defaultdict(int)
    destination_columns: dict[int, int] = defaultdict(int)

    for sequence in selected:
        element_rows = read_csv(
            native_evaluations / f"evaluation_{sequence:04d}" /
            "qualification_diagnostics" / f"evaluation_{sequence:04d}_elements.csv"
        )
        mg_element = next((row for row in element_rows if int(row["element_z"]) == 12), None)
        if mg_element is None:
            raise ValueError(f"evaluation {sequence} has no Magnesium element diagnostics")
        active_min = int(mg_element["active_min_stage"])
        active_max = int(mg_element["active_max_stage"])
        record_rows = read_csv(
            native_evaluations / f"evaluation_{sequence:04d}" /
            "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        )
        for row in record_rows:
            record = int(row.get("record", "0"))
            key = (sequence, record)
            if key not in source_type53:
                continue
            native_keys.add(key)
            native_counts[sequence] += 1
            native_type = int(row.get("data_type", "0"))
            if native_type != 53:
                type_mismatches += 1
                differences.append({
                    "domain": "magnesium_type53", "sequence": sequence,
                    "identity": f"record={record}", "field": "data_type",
                    "source_value": 53, "native_value": native_type,
                    "source_e10": "", "native_e10": "", "bit_exact": 0,
                })
                continue
            source = source_type53[key]
            for field in ("ans3", "ans4"):
                if not compare_numeric(
                    differences, "magnesium_type53", sequence,
                    f"record={record}", field, source[field], row[field],
                ):
                    ans34_rejections += 1
            for field in ("ans5", "ans6"):
                if not compare_numeric(
                    differences, "magnesium_type53", sequence,
                    f"record={record}", field, source[field], row[field],
                ):
                    ans56_rejections += 1
            case_context = type53_candidates.get(record)
            if case_context is None:
                raise ValueError(f"native case has no Mg Type-53 context for record {record}")
            expected_energy, owner_stage, destination_column = source_leveltemp_destination_energy(
                ion_stage=int(row["ion_stage"]),
                active_min_stage=active_min,
                active_max_stage=active_max,
                destination_column=int(case_context["destination_column"]),
                candidate_mask=int(case_context["candidate_mask"]),
                candidate_energy_ev=case_context["candidate_energy_ev"],
                incoming_energy_ev=float(case_context["incoming_energy_ev"]),
            )
            owner_stages[owner_stage] += 1
            destination_columns[destination_column] += 1
            native_energy = float(row["type53_shadow_destination_energy_ev"])
            if not bit_exact(expected_energy, native_energy):
                owner_energy_mismatches += 1
                differences.append({
                    "domain": "magnesium_type53_leveltemp", "sequence": sequence,
                    "identity": f"record={record};owner_stage={owner_stage};column={destination_column}",
                    "field": "destination_energy_ev",
                    "source_value": expected_energy, "native_value": native_energy,
                    "source_e10": canonical_e10(expected_energy),
                    "native_e10": canonical_e10(native_energy),
                    "bit_exact": 0,
                })

    source_domain_exact = bool(source_type53) and all(source_counts[sequence] > 0 for sequence in selected)
    native_inventory_exact = (
        source_domain_exact and set(source_type53) == native_keys and type_mismatches == 0 and
        all(native_counts[sequence] == source_counts[sequence] for sequence in selected)
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

    v21_10_gates = baseline.get("required_gates", {})
    v21_10_required = (
        "V21_9_HYDROGEN_HELIUM_REGRESSION",
        "MAGNESIUM_TYPE57_SOURCE_DOMAIN_EXACT",
        "MAGNESIUM_TYPE57_NATIVE_INVENTORY_EXACT",
        "MAGNESIUM_TYPE57_ANS1_ANS2_NATIVE_FINITE",
        "MAGNESIUM_TYPE57_ANS5_ANS6_IEEE_E10",
        "MAGNESIUM_TYPE57_ACTIVE_SOURCE_THRESHOLDS_POSITIVE",
    )
    v21_10_ok = all(v21_10_gates.get(name) == "ACCEPT" for name in v21_10_required)
    required_gates = {
        "V21_10_TYPE57_AND_V21_9_REGRESSION": "ACCEPT" if v21_10_ok else "REJECT",
        "MAGNESIUM_TYPE53_SOURCE_DOMAIN_PRESENT": "ACCEPT" if source_domain_exact else "REJECT",
        "MAGNESIUM_TYPE53_NATIVE_INVENTORY_EXACT": "ACCEPT" if native_inventory_exact else "REJECT",
        "MAGNESIUM_TYPE53_ANS3_ANS4_IEEE_E10": "ACCEPT" if native_inventory_exact and ans34_rejections == 0 else "REJECT",
        "MAGNESIUM_TYPE53_ANS5_ANS6_IEEE_E10": "ACCEPT" if native_inventory_exact and ans56_rejections == 0 else "REJECT",
        "MAGNESIUM_TYPE53_LEVELTEMP_DESTINATION_ENERGY_BIT_EXACT": "ACCEPT" if native_inventory_exact and owner_energy_mismatches == 0 else "REJECT",
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
        "magnesium_type53": {
            "source_rows": len(source_type53),
            "native_rows": len(native_keys),
            "source_counts_by_sequence": dict(sorted(source_counts.items())),
            "native_counts_by_sequence": dict(sorted(native_counts.items())),
            "data_type_mismatches": type_mismatches,
            "ans3_ans4_rejections": ans34_rejections,
            "ans5_ans6_rejections": ans56_rejections,
            "leveltemp_destination_energy_mismatches": owner_energy_mismatches,
            "leveltemp_owner_stage_counts": dict(sorted(owner_stages.items())),
            "destination_column_counts": dict(sorted(destination_columns.items())),
        },
        "v21_10_regression": {
            "result": baseline.get("result", "REJECT"),
            "required_gates": baseline.get("required_gates", {}),
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
    parser.add_argument("--native-case", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path)
    parser.add_argument("--canonical-report", type=Path)
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
