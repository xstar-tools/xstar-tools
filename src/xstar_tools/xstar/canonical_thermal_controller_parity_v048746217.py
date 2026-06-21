"""All-sequence canonical Thermal and controller-state qualification for v21.7.

Numerical science values are accepted when their canonical normalized scientific
notation with ten digits after the decimal point is identical (``.10e``).  Raw
binary64 equality and ULP distance are retained as diagnostics.  Structural
identity, row keys, controller counters, and termination metadata remain exact.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np

from .continuum_freef_pow_hotfix_v048746172 import reconstruct

RELEASE = "0.6.48.7.46.21.7.1"
SCHEMA = "xstar-tools-v0648746217-canonical-thermal-controller-parity-v1"
DIFFERENCES = "v048746217_thermal_controller_differences.csv"
ACCEPTED_ROUNDOFF = "v048746217_thermal_controller_accepted_roundoff.csv"
REJECTIONS = "v048746217_thermal_controller_rejections.csv"
CATEGORY_SUMMARY = "v048746217_thermal_controller_category_summary.csv"
CONTROLLER_SUMMARY = "v048746217_controller_call_comparison.csv"

BUDGET_FIELDS: tuple[tuple[str, str], ...] = (
    ("h_heating", "h_heating"), ("h_cooling", "h_cooling"),
    ("h_heating2", "h_heating2"), ("h_cooling2", "h_cooling2"),
    ("he_heating", "he_heating"), ("he_cooling", "he_cooling"),
    ("he_heating2", "he_heating2"), ("he_cooling2", "he_cooling2"),
    ("he_type53_heating", "he_type53_heating"),
    ("he_type53_cooling", "he_type53_cooling"),
    ("he_type53_heating2", "he_type53_heating2"),
    ("he_type53_cooling2", "he_type53_cooling2"),
    ("he_non_type53_heating", "he_non_type53_heating"),
    ("he_non_type53_cooling", "he_non_type53_cooling"),
    ("he_non_type53_heating2", "he_non_type53_heating2"),
    ("he_non_type53_cooling2", "he_non_type53_cooling2"),
    ("mg_heating", "mg_heating"), ("mg_cooling", "mg_cooling"),
    ("mg_heating2", "mg_heating2"), ("mg_cooling2", "mg_cooling2"),
    ("element_heating", "element_heating"), ("element_cooling", "element_cooling"),
    ("element_heating2", "element_heating2"), ("element_cooling2", "element_cooling2"),
    ("continuum_heating", "continuum_heating"), ("continuum_cooling", "continuum_cooling"),
    ("continuum_heating2", "continuum_heating2"), ("continuum_cooling2", "continuum_cooling2"),
    ("cmp1", "cmp1"), ("cmp2", "cmp2"), ("htcomp", "htcomp"),
    ("clcomp", "clcomp"), ("htfreef", "htfreef"), ("clbrems", "clbrems"),
    ("httot", "total_heating"), ("cltot", "total_cooling"),
    ("httot2", "total_heating2"), ("cltot2", "total_cooling2"),
    ("hmctot", "hmctot"), ("elcter", "charge_residual"),
)

DIFF_FIELDS = [
    "category", "sequence", "identity", "field", "source_value", "native_value",
    "source_e10", "native_e10", "bit_exact", "e10_equal", "ulp_distance",
    "classification", "detail",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _ordered_int(value: float) -> int:
    integer = struct.unpack(">q", _bits(value))[0]
    return 0x8000000000000000 - integer if integer < 0 else integer


def _ulp(left: float, right: float) -> int:
    if not math.isfinite(left) or not math.isfinite(right):
        return 2**63 - 1
    return abs(_ordered_int(left) - _ordered_int(right))


def canonical_e10(value: Any) -> str:
    numeric = float(value)
    if not math.isfinite(numeric):
        return str(numeric).lower()
    return format(numeric, ".10e")


class Recorder:
    def __init__(self) -> None:
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.differences: list[dict[str, Any]] = []
        self.accepted_roundoff: list[dict[str, Any]] = []
        self.rejections: list[dict[str, Any]] = []

    def exact(self, category: str, sequence: int, identity: str, field: str, source: Any, native: Any, detail: str = "") -> bool:
        self.counts[category]["total"] += 1
        ok = str(source) == str(native)
        self.counts[category]["exact"] += int(ok)
        if not ok:
            self.counts[category]["rejected"] += 1
            row = {
                "category": category, "sequence": sequence, "identity": identity,
                "field": field, "source_value": source, "native_value": native,
                "source_e10": "", "native_e10": "", "bit_exact": 0,
                "e10_equal": 0, "ulp_distance": "", "classification": "STRUCTURAL_REJECT",
                "detail": detail,
            }
            self.differences.append(row); self.rejections.append(row)
        return ok

    def numeric(self, category: str, sequence: int, identity: str, field: str, source: Any, native: Any, detail: str = "") -> bool:
        self.counts[category]["total"] += 1
        try:
            left = float(source); right = float(native)
            finite = math.isfinite(left) and math.isfinite(right)
            bit_equal = finite and _bits(left) == _bits(right)
            left_e10 = canonical_e10(left); right_e10 = canonical_e10(right)
            acceptable = finite and left_e10 == right_e10
            distance = _ulp(left, right)
        except Exception:
            left_e10 = right_e10 = ""
            bit_equal = acceptable = False
            distance = 2**63 - 1
        if bit_equal:
            self.counts[category]["bit_exact"] += 1
            self.counts[category]["e10_acceptable"] += 1
            return True
        row = {
            "category": category, "sequence": sequence, "identity": identity,
            "field": field, "source_value": source, "native_value": native,
            "source_e10": left_e10, "native_e10": right_e10,
            "bit_exact": int(bit_equal), "e10_equal": int(acceptable),
            "ulp_distance": distance,
            "classification": "E10_ACCEPTED_ROUNDOFF" if acceptable else "NUMERIC_REJECT",
            "detail": detail,
        }
        self.differences.append(row)
        if acceptable:
            self.counts[category]["e10_acceptable"] += 1
            self.counts[category]["accepted_roundoff"] += 1
            self.accepted_roundoff.append(row)
        else:
            self.counts[category]["rejected"] += 1
            self.rejections.append(row)
        return acceptable

    def summary_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for category in sorted(self.counts):
            count = self.counts[category]
            total = count["total"]
            bit_exact = count["bit_exact"] + count["exact"]
            acceptable = count["e10_acceptable"] + count["exact"]
            rows.append({
                "category": category, "values_total": total,
                "values_bit_or_structural_exact": bit_exact,
                "values_e10_or_structural_acceptable": acceptable,
                "accepted_roundoff": count["accepted_roundoff"],
                "rejected": count["rejected"],
                "result": "ACCEPT" if total > 0 and count["rejected"] == 0 else "REJECT",
            })
        return rows


def _grouped_csv(path: Path, key_name: str) -> Iterator[tuple[int, list[dict[str, str]]]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for key, group in itertools.groupby(reader, key=lambda row: int(row[key_name])):
            yield key, list(group)


def _evaluation_root(native_evaluations: Path, sequence: int) -> Path:
    return native_evaluations / f"evaluation_{sequence:04d}"


def _compare_fixed_evaluations(source_capture: Path, native_evaluations: Path, recorder: Recorder, sequences: tuple[int, ...]) -> dict[str, Any]:
    source_inputs = {int(row["sequence"]): row for row in _read_csv(source_capture / "v0472_all61_input_states.csv")}
    source_budget = {int(row["sequence"]): row for row in _read_csv(source_capture / "v0472_all61_thermal_budget.csv")}
    source_compact_groups = dict(_grouped_csv(source_capture / "v0472_all61_element_solve_rows.csv", "sequence"))
    complete_sequences = 0
    python_callbacks = 0
    for sequence in sequences:
        root = _evaluation_root(native_evaluations, sequence)
        state_path = root / "native_evaluation.csv"
        budget_path = root / "native_thermal_budget.csv"
        summary_path = root / "native_evaluation_summary.json"
        compact_path = root / "native_thermal_compact_populations.csv"
        continuum_path = root / "native_continuum_workspace.csv"
        canonical_path = root / "native_canonical_thermal_terms.csv"
        diagonal_path = root / "native_thermal_diagonal_ledger.csv"
        diagnostic_path = root / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        required = (state_path, budget_path, summary_path, compact_path, continuum_path, canonical_path, diagonal_path, diagnostic_path)
        if not all(path.is_file() for path in required):
            for path in required:
                if not path.is_file(): recorder.exact("inventory", sequence, "evaluation", "required_file", path.name, "MISSING")
            continue
        state_rows = _read_csv(state_path); budget_rows = _read_csv(budget_path)
        if len(state_rows) != 1 or len(budget_rows) != 1:
            recorder.exact("inventory", sequence, "evaluation", "single_row_ledgers", "1,1", f"{len(state_rows)},{len(budget_rows)}")
            continue
        source_input = source_inputs[sequence]; source = source_budget[sequence]
        state = state_rows[0]; native = budget_rows[0]
        summary = json.loads(summary_path.read_text())
        python_callbacks += int(summary.get("python_callbacks", -1))
        identity = f"kind={source_input['kind']};call={source_input['dsec_call_id']};evaluation={source_input['evaluation_index']}"
        recorder.exact("structural_control", sequence, identity, "sequence", sequence, state.get("sequence"))
        recorder.exact("structural_control", sequence, identity, "call_index", source_input["dsec_call_id"], native.get("call_index"))
        recorder.exact("structural_control", sequence, identity, "evaluation_index", source_input["evaluation_index"], native.get("evaluation_index"))
        recorder.exact("structural_control", sequence, identity, "replay_workspace_applied", "1", state.get("replay_workspace_applied"))
        recorder.exact("structural_control", sequence, identity, "global_workspace_mode", "all", state.get("global_workspace_mode"))
        recorder.exact("structural_control", sequence, identity, "python_callbacks", 0, summary.get("python_callbacks"))
        recorder.exact("structural_control", sequence, identity, "elements_solved", 3, summary.get("elements_solved"))
        recorder.numeric("committed_temperature", sequence, identity, "temperature_t4", source_input["temperature_t4"], state["temperature_t4"])
        recorder.numeric("committed_temperature", sequence, identity, "temperature_k", source["temperature_k"], native["temperature_k"])
        for source_field, native_field in BUDGET_FIELDS:
            recorder.numeric("thermal_budget", sequence, identity, source_field, source[source_field], native[native_field])

        source_compact = {(int(row["element_z"]), int(row["compact_row"])): row for row in source_compact_groups.get(sequence, [])}
        native_compact_rows = _read_csv(compact_path)
        native_compact = {(int(row["element_z"]), int(row["compact_row"])): row for row in native_compact_rows}
        recorder.exact("compact_population_structure", sequence, identity, "compact_keys", sorted(source_compact), sorted(native_compact))
        for key in sorted(set(source_compact) & set(native_compact)):
            src = source_compact[key]; nat = native_compact[key]
            row_id = f"element_z={key[0]};compact_row={key[1]}"
            for field in ("ion", "ion_stage", "ion_charge", "superlevel", "is_normalization_row"):
                recorder.exact("compact_population_structure", sequence, row_id, field, src[field], nat[field])
            recorder.exact("compact_population_structure", sequence, row_id, "closure_applied", "0", nat.get("closure_applied"))
            recorder.numeric("compact_populations", sequence, row_id, "thermal_population", src["final_population"], nat["thermal_population"])

        # Continuum workspace is independently reconstructed from the captured source workspaces.
        call_id = int(source_input["dsec_call_id"])
        workspace = source_capture / "all61_input_workspaces" / f"evaluation_{sequence:04d}"
        full_epi = np.fromfile(workspace / f"call_{call_id}_radiation_energy.bin", dtype=np.float64)
        full_bremsa = np.fromfile(workspace / f"call_{call_id}_bremsa.bin", dtype=np.float64)
        epim, indices, bremsam = reconstruct(full_epi, full_bremsa)
        continuum = sorted(_read_csv(continuum_path), key=lambda row: int(row["reduced_bin_one_based"]))
        recorder.exact("continuum_workspace_structure", sequence, identity, "reduced_bin_count", 999, len(continuum))
        for index, row in enumerate(continuum[:999]):
            row_id = f"reduced_bin={index + 1}"
            recorder.exact("continuum_workspace_structure", sequence, row_id, "full_bin_one_based", int(indices[index]), row["full_bin_one_based"])
            recorder.numeric("continuum_workspace", sequence, row_id, "epim_ev", epim[index], row["epim_ev"])
            recorder.numeric("continuum_workspace", sequence, row_id, "bremsam", bremsam[index], row["bremsam"])

        # Canonical immutable term ownership must match the consumed diagonal ledger exactly in identity.
        diagonal_rows = _read_csv(diagonal_path)
        diagonal = {(int(row["element_z"]), int(row["source_order_index"])): row for row in diagonal_rows}
        canonical_rows = _read_csv(canonical_path)
        canonical = {(int(row["element_z"]), int(row["term_index"])): row for row in canonical_rows}
        recorder.exact("canonical_thermal_structure", sequence, identity, "canonical_diagonal_keys", sorted(canonical), sorted(diagonal))
        for key in sorted(set(canonical) & set(diagonal)):
            src = diagonal[key]; nat = canonical[key]
            row_id = f"element_z={key[0]};term_index={key[1]}"
            for canonical_field, diagonal_field in (
                ("source_position", "source_position"), ("record", "record"),
                ("data_type", "data_type"), ("rate_type", "rate_type"),
                ("compact_row", "compact_row"), ("role", "role"),
                ("is_normalization_row", "is_normalization_row"),
                ("source_domain_included", "source_domain_included"),
            ):
                recorder.exact("canonical_thermal_structure", sequence, row_id, canonical_field, src[diagonal_field], nat[canonical_field])
            recorder.exact("canonical_thermal_structure", sequence, row_id, "shared_ownership", "1", nat.get("shared_ownership"))
            recorder.exact("canonical_thermal_structure", sequence, row_id, "matrix_insertion_captured", "1", nat.get("matrix_insertion_captured"))
            recorder.exact("canonical_thermal_structure", sequence, row_id, "ledger_consumer_identity", nat.get("ledger_fingerprint"), nat.get("element_consumer_fingerprint"))
            recorder.exact("canonical_thermal_structure", sequence, row_id, "fixed_state_consumer_identity", nat.get("ledger_fingerprint"), nat.get("fixed_state_consumer_fingerprint"))
            for field in ("cj", "cj2", "native_cj", "source_cj"):
                recorder.numeric("canonical_thermal_terms", sequence, row_id, field, src[field], nat[field])
        complete_sequences += 1

    # Compare independent source answer channels without loading the 517k-row source table at once.
    answer_groups = _grouped_csv(source_capture / "v0472_all61_thermal_answer_channels.csv", "sequence")
    answer_sequences = 0
    selected = set(sequences)
    for sequence, source_rows in answer_groups:
        if sequence not in selected:
            continue
        root = _evaluation_root(native_evaluations, sequence)
        diagnostic_path = root / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        if not diagnostic_path.is_file():
            recorder.exact("canonical_answer_structure", sequence, "records", "diagnostic_file", diagnostic_path.name, "MISSING")
            continue
        native_rows = _read_csv(diagnostic_path)
        native = {(int(row["element_z"]), int(row["record"])): row for row in native_rows if int(row.get("element_z", "0")) in (1, 2, 12)}
        source = {(int(row["element_z"]), int(row["record"])): row for row in source_rows}
        recorder.exact("canonical_answer_structure", sequence, "records", "source_keys", sorted(source), sorted(set(source) & set(native)))
        for key in sorted(set(source) & set(native)):
            src = source[key]; nat = native[key]
            row_id = f"element_z={key[0]};record={key[1]}"
            for field in ("data_type", "rate_type", "ion_stage"):
                recorder.exact("canonical_answer_structure", sequence, row_id, field, src[field], nat[field])
            for field in ("ans3", "ans4", "ans5", "ans6"):
                recorder.numeric("canonical_answer_channels", sequence, row_id, field, src[field], nat[field])
        answer_sequences += 1
    return {
        "fixed_evaluation_sequences": complete_sequences,
        "answer_channel_sequences": answer_sequences,
        "python_callbacks": python_callbacks,
    }


def _compare_controller(source_capture: Path, native_controller: Path, recorder: Recorder) -> dict[str, Any]:
    trajectory_path = native_controller / "native_dsec_trajectory.csv"
    events_path = native_controller / "native_dsec_controller_events.csv"
    calls_path = native_controller / "native_dsec_call_summary.csv"
    summary_path = native_controller / "native_dsec_summary.json"
    required = (trajectory_path, events_path, calls_path, summary_path)
    if not all(path.is_file() for path in required):
        missing = [path.name for path in required if not path.is_file()]
        return {"result": "NOT_RUN", "missing": missing, "call_rows": 0, "event_rows": 0, "trajectory_rows": 0}

    source_inputs = _read_csv(source_capture / "v0472_all61_input_states.csv")
    source_budget = _read_csv(source_capture / "v0472_all61_thermal_budget.csv")
    source_by_identity = {
        (row["kind"], int(row["dsec_call_id"]), int(row["evaluation_index"])): row for row in source_inputs
    }
    budget_by_sequence = {int(row["sequence"]): row for row in source_budget}
    source_sequence_by_identity = {
        (row["kind"], int(row["dsec_call_id"]), int(row["evaluation_index"])): int(row["sequence"])
        for row in source_inputs
    }
    native_trajectory = _read_csv(trajectory_path)
    recorder.exact("controller_structure", 0, "trajectory", "row_count", 61, len(native_trajectory))
    for row in native_trajectory:
        identity_key = (row["kind"], int(row["call_index"]), int(row["evaluation_index"]))
        source = source_by_identity.get(identity_key)
        sequence = source_sequence_by_identity.get(identity_key, 0)
        identity = f"kind={identity_key[0]};call={identity_key[1]};evaluation={identity_key[2]}"
        if source is None:
            recorder.exact("controller_structure", sequence, identity, "source_identity_present", "present", "missing")
            continue
        source_budget_row = budget_by_sequence[sequence]
        recorder.numeric("controller_committed_state", sequence, identity, "temperature_t4", source["temperature_t4"], row["temperature_t4"])
        recorder.numeric("controller_committed_state", sequence, identity, "electron_fraction_input", source["electron_fraction_input"], row["electron_fraction_input"])
        source_computed_xee = float(source["electron_fraction_input"]) - float(source_budget_row["elcter"])
        recorder.numeric("controller_committed_state", sequence, identity, "computed_electron_fraction", source_computed_xee, row["computed_electron_fraction"])
        recorder.numeric("controller_committed_state", sequence, identity, "charge_residual", source_budget_row["elcter"], row["charge_residual"])
        recorder.numeric("controller_committed_state", sequence, identity, "hmctot", source_budget_row["hmctot"], row["hmctot"])

    source_trace = _read_csv(source_capture / "v0472_dsec_thermal_trace.csv")
    source_trace_by_key = {(int(row["dsec_call_id"]), int(row["dsec_local_evaluation_index"])): row for row in source_trace}
    native_events = _read_csv(events_path)
    after = {(int(row["call_index"]), int(row["evaluation_index"])): row for row in native_events if row.get("event_name") == "after_evaluation"}
    recorder.exact("controller_decisions", 0, "after_evaluation", "event_keys", sorted(source_trace_by_key), sorted(after))
    for key in sorted(set(source_trace_by_key) & set(after)):
        src = source_trace_by_key[key]; nat = after[key]
        sequence = int(src["global_evaluation_ordinal"])
        identity = f"call={key[0]};evaluation={key[1]};event=after_evaluation"
        recorder.exact("controller_decisions", sequence, identity, "event_name", "after_evaluation", nat["event_name"])
        for field in ("temperature_t4", "electron_fraction_xee", "hmctot", "elcter"):
            recorder.numeric("controller_decisions", sequence, identity, field, src[field], nat[field])

    source_counts = Counter(int(row["dsec_call_id"]) for row in source_trace)
    source_final = {(int(row["dsec_call_id"])): row for row in source_inputs if row["kind"] == "final"}
    native_calls = _read_csv(calls_path)
    call_rows: list[dict[str, Any]] = []
    recorder.exact("controller_termination", 0, "calls", "call_count", 4, len(native_calls))
    for row in native_calls:
        call = int(row["call_index"]); expected = source_counts[call]
        identity = f"call={call}"
        recorder.exact("controller_termination", 0, identity, "expected_evaluations", expected, row["expected_evaluations"])
        recorder.exact("controller_termination", 0, identity, "actual_evaluations", expected, row["actual_evaluations"])
        recorder.exact("controller_termination", 0, identity, "prefix_terminated", "1", row["prefix_terminated"])
        recorder.exact("controller_termination", 0, identity, "termination_reason", "maximum_evaluations", row["termination_reason"])
        final = source_final.get(call)
        if final is not None:
            recorder.numeric("controller_termination", 0, identity, "final_temperature_t4", final["temperature_t4"], row["final_temperature_t4"])
            recorder.numeric("controller_termination", 0, identity, "final_electron_fraction_xee", final["electron_fraction_input"], row["final_electron_fraction_xee"])
        call_rows.append({
            "call_index": call, "source_evaluations": expected,
            "native_expected_evaluations": row["expected_evaluations"],
            "native_actual_evaluations": row["actual_evaluations"],
            "charge_converged": row["charge_converged"],
            "thermal_converged": row["thermal_converged"],
            "prefix_terminated": row["prefix_terminated"], "lnerr": row["lnerr"],
            "termination_reason": row["termination_reason"],
        })
    summary = json.loads(summary_path.read_text())
    recorder.exact("controller_structure", 0, "summary", "python_callbacks", 0, summary.get("python_callbacks"))
    recorder.exact("controller_structure", 0, "summary", "total_evaluations", 61, summary.get("total_evaluations"))
    return {
        "result": "ACCEPT", "call_rows": len(native_calls), "event_rows": len(native_events),
        "after_evaluation_rows": len(after), "trajectory_rows": len(native_trajectory),
        "call_comparison": call_rows,
    }


def audit(source_capture: Path, native_evaluations: Path, native_controller: Path | None, output: Path, allow_controller_not_run: bool = False, sequences: tuple[int, ...] = tuple(range(1, 62))) -> dict[str, Any]:
    recorder = Recorder()
    fixed = _compare_fixed_evaluations(source_capture, native_evaluations, recorder, sequences)
    controller = _compare_controller(source_capture, native_controller, recorder) if native_controller else {
        "result": "NOT_RUN", "missing": ["native-controller-not-provided"], "call_rows": 0,
        "event_rows": 0, "trajectory_rows": 0,
    }
    category_rows = recorder.summary_rows()
    rejected = len(recorder.rejections)
    controller_required_ok = controller.get("result") == "ACCEPT" or allow_controller_not_run
    expected_sequences = len(sequences)
    inventory_ok = fixed["fixed_evaluation_sequences"] == expected_sequences and fixed["answer_channel_sequences"] == expected_sequences
    scientific_result = "ACCEPT" if inventory_ok and controller_required_ok and rejected == 0 else "REJECT"
    category_results = {row["category"]: row["result"] for row in category_rows}
    full_all61_scope = sequences == tuple(range(1, 62))
    gates = {
        "ALL_61_FIXED_EVALUATIONS_CLASSIFIED": (
            "ACCEPT" if full_all61_scope and fixed["fixed_evaluation_sequences"] == 61
            else ("REJECT" if full_all61_scope else "NOT_RUN_FOCUSED_SCOPE")
        ),
        "ALL_61_SOURCE_ANSWER_SEQUENCES_CLASSIFIED": (
            "ACCEPT" if full_all61_scope and fixed["answer_channel_sequences"] == 61
            else ("REJECT" if full_all61_scope else "NOT_RUN_FOCUSED_SCOPE")
        ),
        "COMMITTED_TEMPERATURES_IEEE_E10": category_results.get("committed_temperature", "REJECT"),
        "HEATING_COOLING_TOTALS_IEEE_E10": category_results.get("thermal_budget", "REJECT"),
        "CANONICAL_THERMAL_TERMS_IEEE_E10": "ACCEPT" if category_results.get("canonical_thermal_terms") == "ACCEPT" and category_results.get("canonical_answer_channels") == "ACCEPT" else "REJECT",
        "CANONICAL_THERMAL_STRUCTURE_EXACT": "ACCEPT" if category_results.get("canonical_thermal_structure") == "ACCEPT" and category_results.get("canonical_answer_structure") == "ACCEPT" else "REJECT",
        "COMPACT_POPULATIONS_IEEE_E10": category_results.get("compact_populations", "REJECT"),
        "COMPACT_POPULATION_STRUCTURE_EXACT": category_results.get("compact_population_structure", "REJECT"),
        "CONTINUUM_WORKSPACE_IEEE_E10": category_results.get("continuum_workspace", "REJECT"),
        "CONTINUUM_WORKSPACE_STRUCTURE_EXACT": category_results.get("continuum_workspace_structure", "REJECT"),
        "CONTROLLER_COMMITTED_STATE_IEEE_E10": category_results.get("controller_committed_state", "NOT_RUN"),
        "CONTROLLER_DECISIONS_EXACT_AND_IEEE_E10": "ACCEPT" if category_results.get("controller_decisions") == "ACCEPT" else ("NOT_RUN" if controller.get("result") == "NOT_RUN" else "REJECT"),
        "CONTROLLER_TERMINATION_STATE_EXACT": category_results.get("controller_termination", "NOT_RUN"),
        "STRUCTURAL_AND_CONTROL_FIELDS_EXACT": "ACCEPT" if all(category_results.get(name) == "ACCEPT" for name in (
            "structural_control", "compact_population_structure", "continuum_workspace_structure",
            "canonical_thermal_structure", "canonical_answer_structure",
        )) else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if fixed["python_callbacks"] == 0 else "REJECT",
        "REJECTED_SCIENTIFIC_DIFFERENCES_ZERO": "ACCEPT" if rejected == 0 else "REJECT",
    }
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / DIFFERENCES, DIFF_FIELDS, recorder.differences)
    _write_csv(output / ACCEPTED_ROUNDOFF, DIFF_FIELDS, recorder.accepted_roundoff)
    _write_csv(output / REJECTIONS, DIFF_FIELDS, recorder.rejections)
    _write_csv(output / CATEGORY_SUMMARY, list(category_rows[0]) if category_rows else ["category"], category_rows)
    call_rows = controller.get("call_comparison", [])
    _write_csv(output / CONTROLLER_SUMMARY, list(call_rows[0]) if call_rows else ["call_index"], call_rows)
    return {
        "schema": SCHEMA, "release": RELEASE, "result": scientific_result,
        "scientific_result": scientific_result,
        "comparison_semantics": "canonical normalized E-notation with 10 digits after decimal (.10e)",
        "structural_semantics": "exact identity and control metadata",
        "gates": gates, "category_summary": category_rows,
        "fixed_evaluation_summary": fixed, "controller_summary": {k: v for k, v in controller.items() if k != "call_comparison"},
        "numeric_or_structural_differences": len(recorder.differences),
        "accepted_roundoff_differences": len(recorder.accepted_roundoff),
        "rejected_differences": rejected,
        "first_difference": recorder.differences[0] if recorder.differences else None,
        "first_rejection": recorder.rejections[0] if recorder.rejections else None,
        "qualification_only": True,
        "product_level_parity": "NOT_RUN",
        "production_promotion_status": (
            "BLOCKED_PENDING_PRODUCT_PARITY"
            if scientific_result == "ACCEPT"
            else "BLOCKED_BY_THERMAL_OR_CONTROLLER_PARITY"
        ),
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-evaluations", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--allow-controller-not-run", action="store_true")
    parser.add_argument("--sequences", default="1-61", help="comma list and ranges; default 1-61")
    args = parser.parse_args(argv)
    def parse_sequences(spec: str) -> tuple[int, ...]:
        values: set[int] = set()
        for token in spec.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                first, last = token.split("-", 1)
                values.update(range(int(first), int(last) + 1))
            else:
                values.add(int(token))
        result = tuple(sorted(values))
        if not result or any(value < 1 or value > 61 for value in result):
            raise ValueError("sequences must be within 1..61")
        return result
    try:
        sequences = parse_sequences(args.sequences)
        report = audit(args.source_capture.resolve(), args.native_evaluations.resolve(), args.native_controller.resolve() if args.native_controller else None, args.output.resolve(), args.allow_controller_not_run, sequences)
    except Exception as exc:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT", "scientific_result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"], "qualification_only": True,
            "product_level_parity": "NOT_RUN", "production_promotion_status": "BLOCKED_PENDING_PRODUCT_PARITY",
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
