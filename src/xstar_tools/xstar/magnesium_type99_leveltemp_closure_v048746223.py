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

from . import magnesium_type49_leveltemp_closure_v048746222 as v232
from .type99_leveltemp_case_contract_v048746223 import (
    CONTEXT_INT_COUNT,
    CONTEXT_REAL_COUNT,
    EXPECTED_MAGNESIUM_TYPE99_RECORDS,
    LAYOUT_MAGIC,
    audit_case,
)

RELEASE = "0.6.48.7.46.21.13"
SCHEMA = "xstar-tools-v0648746223-magnesium-type99-persistent-leveltemp-energy-weight-closure-v1"


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


def _read_vector(path: Path, cast: type[float] | type[int]) -> list[float] | list[int]:
    values: list[float] | list[int] = []
    with path.open() as handle:
        for line in handle:
            text = line.strip()
            if text:
                values.append(cast(text))
    return values


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


def _case_type99_context(native_case: Path) -> dict[int, dict[str, Any]]:
    case_report = audit_case(native_case)
    if case_report["result"] != "ACCEPT":
        raise ValueError("Mg Type-99 v21.13 case contract rejected: " + "; ".join(case_report["errors"][:5]))
    elements = read_csv(native_case / "elements.csv")
    mg = next(row for row in elements if int(row["element_z"]) == 12)
    element_index = int(mg["element_index"])
    reals = _read_vector(native_case / "reals.txt", float)
    ints = _read_vector(native_case / "ints.txt", int)
    result: dict[int, dict[str, Any]] = {}
    for row in read_csv(native_case / "records.csv"):
        if int(row["element_index"]) != element_index or int(row["data_type"]) != 99:
            continue
        record = int(row["record"])
        ro, rc = int(row["real_offset"]), int(row["real_count"])
        io, ic = int(row["int_offset"]), int(row["int_count"])
        nden, ntem, nxs = (int(ints[io + i]) for i in range(3))
        core = nden + ntem + nden * ntem + 2 * nxs
        if rc != core + CONTEXT_REAL_COUNT or ic < CONTEXT_INT_COUNT:
            raise ValueError(f"Mg Type-99 record {record} has malformed v21.13 context")
        ibase = io + ic - CONTEXT_INT_COUNT
        if int(ints[ibase + 7]) != LAYOUT_MAGIC:
            raise ValueError(f"Mg Type-99 record {record} lacks layout magic {LAYOUT_MAGIC}")
        base = ro + core
        result[record] = {
            "bound_column": int(ints[ibase + 0]),
            "parent_column": int(ints[ibase + 1]),
            "destination_column": int(ints[ibase + 2]),
            "bound_mask": int(ints[ibase + 3]),
            "parent_mask": int(ints[ibase + 4]),
            "destination_mask": int(ints[ibase + 5]),
            "excited_parent_mode": int(ints[ibase + 6]),
            "incoming_bound": (float(reals[base + 3]), float(reals[base + 4])),
            "incoming_parent": (float(reals[base + 5]), float(reals[base + 6])),
            "incoming_destination": (float(reals[base + 7]), float(reals[base + 8])),
            "excited_parent": (float(reals[base + 9]), float(reals[base + 10])),
            "bound_energy": tuple(float(reals[base + 11 + stage]) for stage in range(12)),
            "bound_weight": tuple(float(reals[base + 23 + stage]) for stage in range(12)),
            "parent_energy": tuple(float(reals[base + 35 + stage]) for stage in range(12)),
            "parent_weight": tuple(float(reals[base + 47 + stage]) for stage in range(12)),
            "destination_energy": tuple(float(reals[base + 59 + stage]) for stage in range(12)),
            "destination_weight": tuple(float(reals[base + 71 + stage]) for stage in range(12)),
        }
    if len(result) != EXPECTED_MAGNESIUM_TYPE99_RECORDS:
        raise ValueError(
            f"Mg Type-99 context inventory {len(result)} != {EXPECTED_MAGNESIUM_TYPE99_RECORDS}"
        )
    return result


def source_leveltemp_value(
    *, ion_stage: int, active_min_stage: int, active_max_stage: int,
    column: int, candidate_mask: int,
    candidate_energy_ev: tuple[float, ...],
    candidate_statistical_weight: tuple[float, ...],
    incoming_energy_ev: float, incoming_statistical_weight: float,
) -> tuple[float, float, int]:
    if not 1 <= ion_stage <= 12 or column <= 0:
        raise ValueError("invalid Type-99 stage/column")
    if candidate_mask < 0 or candidate_mask > 0x0FFF:
        raise ValueError("invalid Type-99 candidate mask")
    if len(candidate_energy_ev) != 12 or len(candidate_statistical_weight) != 12:
        raise ValueError("invalid Type-99 candidate arrays")

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
        return float(incoming_energy_ev), float(incoming_statistical_weight), 0
    energy = float(candidate_energy_ev[owner - 1])
    weight = float(candidate_statistical_weight[owner - 1])
    if not math.isfinite(energy) or not math.isfinite(weight) or weight <= 0.0:
        raise ValueError(f"invalid Type-99 stage-{owner} value")
    return energy, weight, owner


def resolve_type99_context(
    context: dict[str, Any], *, ion_stage: int,
    active_min_stage: int, active_max_stage: int,
) -> dict[str, Any]:
    bound = source_leveltemp_value(
        ion_stage=ion_stage, active_min_stage=active_min_stage,
        active_max_stage=active_max_stage, column=context["bound_column"],
        candidate_mask=context["bound_mask"], candidate_energy_ev=context["bound_energy"],
        candidate_statistical_weight=context["bound_weight"],
        incoming_energy_ev=context["incoming_bound"][0],
        incoming_statistical_weight=context["incoming_bound"][1],
    )
    parent = source_leveltemp_value(
        ion_stage=ion_stage, active_min_stage=active_min_stage,
        active_max_stage=active_max_stage, column=context["parent_column"],
        candidate_mask=context["parent_mask"], candidate_energy_ev=context["parent_energy"],
        candidate_statistical_weight=context["parent_weight"],
        incoming_energy_ev=context["incoming_parent"][0],
        incoming_statistical_weight=context["incoming_parent"][1],
    )
    destination = source_leveltemp_value(
        ion_stage=ion_stage, active_min_stage=active_min_stage,
        active_max_stage=active_max_stage, column=context["destination_column"],
        candidate_mask=context["destination_mask"],
        candidate_energy_ev=context["destination_energy"],
        candidate_statistical_weight=context["destination_weight"],
        incoming_energy_ev=context["incoming_destination"][0],
        incoming_statistical_weight=context["incoming_destination"][1],
    )
    parent_weight = (
        float(context["excited_parent"][1])
        if context["excited_parent_mode"] == 1 else parent[1]
    )
    threshold = (
        abs(bound[0] + float(context["excited_parent"][0]))
        if context["excited_parent_mode"] == 1 else abs(bound[0] - parent[0])
    )
    if bound[1] <= 0.0 or parent_weight <= 0.0 or destination[1] <= 0.0 or threshold <= 0.0:
        raise ValueError("resolved Type-99 energy/weight context is invalid")
    return {
        "bound_energy_ev": bound[0],
        "bound_weight": bound[1],
        "bound_owner_stage": bound[2],
        "parent_energy_ev": parent[0],
        "parent_weight": parent_weight,
        "parent_owner_stage": parent[2],
        "destination_energy_ev": destination[0],
        "destination_weight": destination[1],
        "destination_owner_stage": destination[2],
        "threshold_ev": threshold,
        "swrat": bound[1] / parent_weight,
    }


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

    with tempfile.TemporaryDirectory(prefix="v048746223_v232_") as tmp:
        baseline_csv = Path(tmp) / "v232_differences.csv"
        baseline = v232.audit(
            source_capture, native_evaluations, native_case, controller,
            canonical_report, baseline_csv, selected,
        )
        if baseline_csv.is_file():
            differences.extend(read_csv(baseline_csv))

    contexts = _case_type99_context(native_case)
    source_type99: dict[tuple[int, int], dict[str, str]] = {}
    source_counts: dict[int, int] = defaultdict(int)
    for row in read_csv(source_capture / "v0472_all61_thermal_answer_channels.csv"):
        sequence = int(row["sequence"])
        if sequence in selected_set and int(row["element_z"]) == 12 and int(row["data_type"]) == 99:
            key = (sequence, int(row["record"]))
            source_type99[key] = row
            source_counts[sequence] += 1

    native_keys: set[tuple[int, int]] = set()
    native_counts: dict[int, int] = defaultdict(int)
    # The historical source answer capture contains ans3 through ans6 only.
    # ans1/ans2 are recomputed natively by the shared kernel but are not a
    # focused comparison domain in this release.
    answer_rejections = {"ans3_ans4": 0, "ans5_ans6": 0}
    context_rejections = {"bound_energy": 0, "parent_energy": 0, "swrat": 0}
    owner_counts = {"bound": defaultdict(int), "parent": defaultdict(int), "destination": defaultdict(int)}
    context_applied_missing = 0

    for sequence in selected:
        eval_dir = native_evaluations / f"evaluation_{sequence:04d}"
        elements = read_csv(
            eval_dir / "qualification_diagnostics" / f"evaluation_{sequence:04d}_elements.csv"
        )
        mg = next((row for row in elements if int(row["element_z"]) == 12), None)
        if mg is None:
            raise ValueError(f"evaluation {sequence} has no Magnesium element")
        active_min = int(mg["active_min_stage"])
        active_max = int(mg["active_max_stage"])
        for row in read_csv(
            eval_dir / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        ):
            key = (sequence, int(row.get("record", "0")))
            if key not in source_type99:
                continue
            native_keys.add(key)
            native_counts[sequence] += 1
            record = key[1]
            source = source_type99[key]
            context = contexts.get(record)
            if context is None:
                raise ValueError(f"native case lacks Mg Type-99 record {record} context")
            resolved = resolve_type99_context(
                context, ion_stage=int(row["ion_stage"]),
                active_min_stage=active_min, active_max_stage=active_max,
            )
            for field in ("ans3", "ans4"):
                if not compare_numeric(differences, "magnesium_type99", sequence,
                                       f"record={record}", field, source[field], row[field]):
                    answer_rejections["ans3_ans4"] += 1
            for field in ("ans5", "ans6"):
                if not compare_numeric(differences, "magnesium_type99", sequence,
                                       f"record={record}", field, source[field], row[field]):
                    answer_rejections["ans5_ans6"] += 1
            for name, native_field in (
                ("bound_energy_ev", "type99_bound_energy_ev"),
                ("parent_energy_ev", "type99_parent_energy_ev"),
                ("swrat", "type99_swrat"),
            ):
                if not compare_numeric(
                    differences, "magnesium_type99_context", sequence,
                    f"record={record}", name, resolved[name], row[native_field],
                ):
                    key_name = "swrat" if name == "swrat" else name.replace("_ev", "")
                    context_rejections[key_name] += 1
            for label in owner_counts:
                owner_counts[label][int(resolved[f"{label}_owner_stage"])] += 1
            if int(row.get("type99_persistent_leveltemp_context_applied", "0")) != 1:
                context_applied_missing += 1

    source_domain_exact = bool(source_type99) and all(source_counts[seq] > 0 for seq in selected)
    native_inventory_exact = (
        source_domain_exact and set(source_type99) == native_keys and
        all(native_counts[seq] == source_counts[seq] for seq in selected)
    )

    source_budget = {
        int(row["sequence"]): row
        for row in read_csv(source_capture / "v0472_all61_thermal_budget.csv")
        if int(row["sequence"]) in selected_set
    }
    cooling_compared = 0
    cooling_rejections = 0
    budget_differences: list[dict[str, Any]] = []
    for sequence in selected:
        rows = read_csv(native_evaluations / f"evaluation_{sequence:04d}" / "native_thermal_budget.csv")
        if sequence not in source_budget or len(rows) != 1:
            continue
        cooling_compared += 1
        if not compare_numeric(
            budget_differences, "thermal_budget", sequence, "fixed_evaluation",
            "mg_cooling2", source_budget[sequence]["mg_cooling2"], rows[0]["mg_cooling2"],
        ):
            cooling_rejections += 1

    case_report = audit_case(native_case)
    v21_12_gates = baseline.get("required_gates", {})
    v21_12_required = (
        "V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION",
        "MAGNESIUM_TYPE49_SOURCE_DOMAIN_PRESENT",
        "MAGNESIUM_TYPE49_NATIVE_INVENTORY_EXACT",
        "MAGNESIUM_TYPE49_ANS3_ANS4_IEEE_E10",
        "MAGNESIUM_TYPE49_ANS5_ANS6_IEEE_E10",
        "MAGNESIUM_TYPE49_LEVELTEMP_DESTINATION_ENERGY_BIT_EXACT",
    )
    baseline_ok = all(v21_12_gates.get(name) == "ACCEPT" for name in v21_12_required)
    analyzer_completed = True
    required_gates = {
        "V21_12_TYPE49_REGRESSION": "ACCEPT" if baseline_ok else "REJECT",
        "FOCUSED_ANALYZER_COMPLETES_WITHOUT_RECURSION": "ACCEPT" if analyzer_completed else "REJECT",
        "MAGNESIUM_TYPE99_CONTEXT_LAYOUT_EXACT": "ACCEPT" if (
            case_report["result"] == "ACCEPT" and native_inventory_exact and context_applied_missing == 0
        ) else "REJECT",
        "MAGNESIUM_TYPE99_BOUND_ENERGY_IEEE_E10": "ACCEPT" if (
            native_inventory_exact and context_rejections["bound_energy"] == 0
        ) else "REJECT",
        "MAGNESIUM_TYPE99_PARENT_ENERGY_IEEE_E10": "ACCEPT" if (
            native_inventory_exact and context_rejections["parent_energy"] == 0
        ) else "REJECT",
        "MAGNESIUM_TYPE99_STATISTICAL_WEIGHT_RATIO_IEEE_E10": "ACCEPT" if (
            native_inventory_exact and context_rejections["swrat"] == 0
        ) else "REJECT",
        "MAGNESIUM_TYPE99_ANS3_ANS4_IEEE_E10": "ACCEPT" if (
            native_inventory_exact and answer_rejections["ans3_ans4"] == 0
        ) else "REJECT",
        "MAGNESIUM_TYPE99_ANS5_ANS6_IEEE_E10": "ACCEPT" if (
            native_inventory_exact and answer_rejections["ans5_ans6"] == 0
        ) else "REJECT",
        "MAGNESIUM_COOLING2_ALL_SELECTED_IEEE_E10": "ACCEPT" if (
            cooling_compared == len(selected) and cooling_rejections == 0
        ) else "REJECT",
    }
    focused_result = "ACCEPT" if all(value == "ACCEPT" for value in required_gates.values()) else "REJECT"

    fields = (
        "domain", "sequence", "identity", "field", "source_value", "native_value",
        "source_e10", "native_e10", "bit_exact",
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(differences)
        writer.writerows(budget_differences)

    controller_summary: dict[str, Any] = {}
    if controller is not None and (controller / "native_dsec_summary.json").is_file():
        controller_summary = json.loads((controller / "native_dsec_summary.json").read_text())
    canonical: dict[str, Any] = {}
    if canonical_report is not None and canonical_report.is_file():
        canonical = json.loads(canonical_report.read_text())

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": focused_result,
        "focused_scientific_result": focused_result,
        "required_gates": required_gates,
        "magnesium_type99": {
            "serialized_records": len(contexts),
            "source_rows": len(source_type99),
            "native_rows": len(native_keys),
            "source_counts_by_sequence": dict(sorted(source_counts.items())),
            "native_counts_by_sequence": dict(sorted(native_counts.items())),
            "ans1_ans2_comparison": "NOT_CAPTURED_IN_SOURCE_ANSWER_CHANNELS",
            "ans3_ans4_rejections": answer_rejections["ans3_ans4"],
            "ans5_ans6_rejections": answer_rejections["ans5_ans6"],
            "bound_energy_rejections": context_rejections["bound_energy"],
            "parent_energy_rejections": context_rejections["parent_energy"],
            "statistical_weight_ratio_rejections": context_rejections["swrat"],
            "context_applied_missing": context_applied_missing,
            "owner_stage_counts": {
                key: dict(sorted(value.items())) for key, value in owner_counts.items()
            },
        },
        "v21_12_regression": {
            "result": baseline.get("result", "REJECT"),
            "required_gates": baseline.get("required_gates", {}),
        },
        "case_contract": case_report,
        "thermal_budget_progress": {
            "mg_cooling2": {
                "compared": cooling_compared,
                "rejected": cooling_rejections,
            }
        },
        "focused_rejections": len(differences) + len(budget_differences),
        "first_focused_rejection": (differences + budget_differences)[0]
        if differences or budget_differences else None,
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
