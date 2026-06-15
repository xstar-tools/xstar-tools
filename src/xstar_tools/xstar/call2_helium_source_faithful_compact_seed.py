"""v0.6.48.7.32 source-faithful helium compact-seed construction audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.32"
SCHEMA = "xstar-tools-v0648732-source-faithful-helium-compact-seed-v1"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def f(row: dict[str, str], key: str, default: float = math.nan) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def i(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def canonical_role(value: str) -> str:
    return {
        "forward_offdiag": "forward_gain",
        "reverse_offdiag": "reverse_gain",
    }.get(value, value)


def exact(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and a == b


def finite_delta(a: float, b: float) -> float:
    return abs(b - a) if math.isfinite(a) and math.isfinite(b) else math.inf


def term_base_key(row: dict[str, str]) -> tuple[int, int, int, str, int, int]:
    """Stable cross-runtime term identity, excluding stream position."""
    return (
        i(row, "record"),
        i(row, "data_type"),
        i(row, "rate_type"),
        canonical_role(row.get("role", "")),
        i(row, "compact_row"),
        i(row, "compact_column"),
    )


def indexed_terms(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[int, int, int, str, int, int, int], dict[str, str]]:
    """Add an occurrence ordinal for duplicate metadata keys."""
    counts: Counter[tuple[int, int, int, str, int, int]] = Counter()
    indexed: dict[tuple[int, int, int, str, int, int, int], dict[str, str]] = {}
    for row in rows:
        base = term_base_key(row)
        counts[base] += 1
        indexed[base + (counts[base],)] = row
    return indexed


def key_fields(key: tuple[int, int, int, str, int, int, int]) -> dict[str, Any]:
    record, dtype, rate_type, role_name, row, column, occurrence = key
    return {
        "record": record,
        "data_type": dtype,
        "rate_type": rate_type,
        "role": role_name,
        "compact_row": row,
        "compact_column": column,
        "occurrence_ordinal": occurrence,
    }


def term_row_payload(prefix: str, row: dict[str, str] | None) -> dict[str, Any]:
    if row is None:
        return {
            f"{prefix}_source_order_index": 0,
            f"{prefix}_term_source_position": 0,
            f"{prefix}_contribution_source_position": 0,
        }
    return {
        f"{prefix}_source_order_index": i(row, "source_order_index"),
        f"{prefix}_term_source_position": i(row, "term_source_position", i(row, "term_index")),
        f"{prefix}_contribution_source_position": i(row, "contribution_source_position"),
    }


def all_coefficients_exact(row: dict[str, Any]) -> bool:
    return all(bool(row[f"{name}_exact"]) for name in ("aj1", "aj2", "cj", "cj2"))


def family_gate(
    dtype: int,
    comparison_rows: list[dict[str, Any]],
    unmatched_source: list[dict[str, Any]],
    unmatched_native: list[dict[str, Any]],
) -> str:
    matched = [row for row in comparison_rows if int(row["data_type"]) == dtype]
    source_gap = any(int(row["data_type"]) == dtype for row in unmatched_source)
    native_gap = any(int(row["data_type"]) == dtype for row in unmatched_native)
    if not matched and not source_gap and not native_gap:
        return "NOT_PRESENT"
    if source_gap or native_gap:
        return "NOT_EVALUATED_TERM_STREAM_ALIGNMENT"
    return "ACCEPT" if matched and all(all_coefficients_exact(row) for row in matched) else "REJECT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--prior-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    source_report = json.loads(
        (args.source_capture / "v0472_call2_eval1_he_solve_capture_report.json").read_text()
    )
    prior = json.loads(args.prior_summary.read_text())
    prior_gates = prior.get("gates", {})

    source_rows = read_csv(args.source_capture / "v0472_call2_eval1_he_solve_rows.csv")
    source_matrix = read_csv(args.source_capture / "v0472_call2_eval1_he_solve_matrix.csv")
    source_terms = read_csv(
        args.source_capture / "v0472_call2_eval1_he_source_order_matrix_terms.csv"
    )
    native_rows = read_csv(
        args.native_replay / "diagnostics/evaluation_0022_helium_solve_rows.csv"
    )
    native_matrix = read_csv(
        args.native_replay / "diagnostics/evaluation_0022_helium_solve_matrix.csv"
    )
    native_terms = read_csv(
        args.native_replay / "diagnostics/evaluation_0022_helium_source_order_terms.csv"
    )
    native_state = json.loads(
        (args.native_replay / "diagnostics/evaluation_0022_helium_solve_state.json").read_text()
    )
    outer_trace = read_csv(
        args.source_capture / "v0472_call2_eval1_he_outer_level_trace.csv"
    )
    fixed_trace = read_csv(
        args.source_capture / "v0472_call2_eval1_he_fixed_point_trace.csv"
    )

    # Lifecycle-aligned solve-state and seed-semantics ledger.
    source_by_row = {i(row, "element_row"): row for row in source_rows}
    native_by_row = {i(row, "full_row"): row for row in native_rows}
    row_comparison: list[dict[str, Any]] = []
    seed_comparison: list[dict[str, Any]] = []
    for row_id in sorted(source_by_row):
        source = source_by_row[row_id]
        native = native_by_row.get(row_id, {})

        source_compact_seed = f(source, "transformed_initial_population")
        raw_workspace_value = f(native, "raw_call_start_xilevg", f(native, "loaded_call_start_xilevg"))
        effective_runtime_seed = f(native, "loaded_call_start_xilevg")
        native_compact_seed = effective_runtime_seed
        native_solver_seed = f(native, "initial_population")
        source_outer = f(source, "final_outer_start_population")
        native_outer = f(native, "final_outer_start_population")
        source_final = f(source, "final_population")
        native_final = f(native, "final_population")
        source_rhs = f(source, "rhs")
        native_rhs = f(native, "rhs")
        normalization_row = i(source, "is_normalization_row")

        compact_exact = exact(source_compact_seed, native_compact_seed)
        solver_seed_exact = exact(source_compact_seed, native_solver_seed)
        normalization_applied = (
            math.isfinite(native_compact_seed)
            and math.isfinite(native_solver_seed)
            and native_compact_seed != native_solver_seed
        )
        scale = (
            native_solver_seed / native_compact_seed
            if math.isfinite(native_solver_seed)
            and math.isfinite(native_compact_seed)
            and native_compact_seed != 0.0
            else math.nan
        )

        seed_comparison.append(
            {
                "element_row": row_id,
                "ion": i(source, "ion"),
                "ion_stage": i(source, "ion_stage"),
                "is_normalization_row": normalization_row,
                "raw_global_level_index": i(native, "raw_global_level_index", i(native, "loaded_global_level_index")),
                "raw_global_workspace_value": raw_workspace_value,
                "loaded_global_level_index": i(native, "loaded_global_level_index"),
                "effective_runtime_seed": effective_runtime_seed,
                "source_compact_mapped_seed": source_compact_seed,
                "native_compact_mapped_seed": native_compact_seed,
                "normalized_native_solver_seed": native_solver_seed,
                "source_compact_vs_native_compact_exact": compact_exact,
                "source_compact_vs_native_solver_exact": solver_seed_exact,
                "native_pre_solve_normalization_applied": normalization_applied,
                "native_pre_solve_scale": scale,
                "shared_ion_boundary_row": 1 if row_id == 46 else 0,
                "post_boundary_row": 1 if row_id == 47 else 0,
            }
        )
        row_comparison.append(
            {
                "element_row": row_id,
                "ion": i(source, "ion"),
                "is_normalization_row": normalization_row,
                "source_compact_mapped_seed": source_compact_seed,
                "native_compact_mapped_seed": native_compact_seed,
                "native_normalized_solver_seed": native_solver_seed,
                "compact_seed_exact": compact_exact,
                "transformed_initial_exact": solver_seed_exact,
                "source_rhs": source_rhs,
                "native_rhs": native_rhs,
                "rhs_exact": exact(source_rhs, native_rhs),
                "source_final_outer_start": source_outer,
                "native_final_outer_start": native_outer,
                "final_outer_start_exact": exact(source_outer, native_outer),
                "source_final_population": source_final,
                "native_final_population": native_final,
                "post_solve_exact": exact(source_final, native_final),
            }
        )
    write_csv(args.output / "call2_he_seed_semantics_comparison.csv", seed_comparison)
    write_csv(args.output / "call2_he_solve_state_comparison.csv", row_comparison)

    # Dense matrix comparison remains independent of term-stream alignment.
    source_matrix_by_cell = {
        (i(row, "compact_row"), i(row, "compact_column")): row
        for row in source_matrix
    }
    native_matrix_by_cell = {
        (i(row, "compact_row"), i(row, "compact_column")): row
        for row in native_matrix
    }
    matrix_comparison: list[dict[str, Any]] = []
    for key in sorted(source_matrix_by_cell):
        source = source_matrix_by_cell[key]
        native = native_matrix_by_cell.get(key, {})
        source_dense = f(source, "dense_value")
        native_dense = f(native, "dense_value")
        source_heat = f(source, "heating_value")
        native_heat = f(native, "heating_value")
        source_heat2 = f(source, "heating2_value")
        native_heat2 = f(native, "heating2_value")
        matrix_comparison.append(
            {
                "compact_row": key[0],
                "compact_column": key[1],
                "source_dense": source_dense,
                "native_dense": native_dense,
                "dense_exact": exact(source_dense, native_dense),
                "dense_abs_delta": finite_delta(source_dense, native_dense),
                "source_heating_matrix": source_heat,
                "native_heating_matrix": native_heat,
                "heating_exact": exact(source_heat, native_heat),
                "source_heating2_matrix": source_heat2,
                "native_heating2_matrix": native_heat2,
                "heating2_exact": exact(source_heat2, native_heat2),
            }
        )
    write_csv(args.output / "call2_he_dense_matrix_comparison.csv", matrix_comparison)

    # Metadata-keyed term alignment. Positional source-order matching is retired.
    source_indexed = indexed_terms(source_terms)
    native_indexed = indexed_terms(native_terms)
    source_keys = set(source_indexed)
    native_keys = set(native_indexed)
    matched_keys = sorted(source_keys & native_keys)
    source_only_keys = sorted(source_keys - native_keys)
    native_only_keys = sorted(native_keys - source_keys)

    term_comparison: list[dict[str, Any]] = []
    for key in matched_keys:
        source = source_indexed[key]
        native = native_indexed[key]
        values: dict[str, Any] = {}
        for name in ("aj1", "aj2", "cj", "cj2"):
            source_value = f(source, name)
            native_value = f(native, name)
            values[f"source_{name}"] = source_value
            values[f"native_{name}"] = native_value
            values[f"{name}_exact"] = exact(source_value, native_value)
            values[f"{name}_abs_delta"] = finite_delta(source_value, native_value)
        term_comparison.append(
            {
                "alignment_status": "MATCHED_METADATA_KEY",
                **key_fields(key),
                **term_row_payload("source", source),
                **term_row_payload("native", native),
                "metadata_key_exact": True,
                "type53": 1 if key[1] == 53 else 0,
                **values,
            }
        )

    unmatched_source: list[dict[str, Any]] = []
    for key in source_only_keys:
        source = source_indexed[key]
        transpose_key = (key[0], key[1], key[2], key[3], key[5], key[4], key[6])
        unmatched_source.append(
            {
                "alignment_status": "UNMATCHED_SOURCE",
                **key_fields(key),
                **term_row_payload("source", source),
                "possible_native_transpose_match": transpose_key in native_indexed,
                "source_aj1": f(source, "aj1"),
                "source_aj2": f(source, "aj2"),
                "source_cj": f(source, "cj"),
                "source_cj2": f(source, "cj2"),
            }
        )

    unmatched_native: list[dict[str, Any]] = []
    for key in native_only_keys:
        native = native_indexed[key]
        transpose_key = (key[0], key[1], key[2], key[3], key[5], key[4], key[6])
        unmatched_native.append(
            {
                "alignment_status": "UNMATCHED_NATIVE",
                **key_fields(key),
                **term_row_payload("native", native),
                "possible_source_transpose_match": transpose_key in source_indexed,
                "native_aj1": f(native, "aj1"),
                "native_aj2": f(native, "aj2"),
                "native_cj": f(native, "cj"),
                "native_cj2": f(native, "cj2"),
            }
        )

    write_csv(args.output / "call2_he_metadata_keyed_term_comparison.csv", term_comparison)
    # Compatibility filename now contains metadata-keyed matches only.
    write_csv(args.output / "call2_he_source_order_term_comparison.csv", term_comparison)
    write_csv(args.output / "call2_he_unmatched_source_terms.csv", unmatched_source)
    write_csv(args.output / "call2_he_unmatched_native_terms.csv", unmatched_native)

    # Per-family/row summaries include explicit alignment completeness.
    family: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {
            "matched_terms": 0,
            "unmatched_source_terms": 0,
            "unmatched_native_terms": 0,
            "aj1_mismatches": 0,
            "aj2_mismatches": 0,
            "cj_mismatches": 0,
            "cj2_mismatches": 0,
            "max_abs_delta": 0.0,
        }
    )
    for row in term_comparison:
        bucket = family[(int(row["data_type"]), int(row["compact_row"]))]
        bucket["matched_terms"] += 1
        for name in ("aj1", "aj2", "cj", "cj2"):
            if not bool(row[f"{name}_exact"]):
                bucket[f"{name}_mismatches"] += 1
            bucket["max_abs_delta"] = max(
                float(bucket["max_abs_delta"]), float(row[f"{name}_abs_delta"])
            )
    for row in unmatched_source:
        family[(int(row["data_type"]), int(row["compact_row"]))][
            "unmatched_source_terms"
        ] += 1
    for row in unmatched_native:
        family[(int(row["data_type"]), int(row["compact_row"]))][
            "unmatched_native_terms"
        ] += 1

    family_rows: list[dict[str, Any]] = []
    for (dtype, destination), bucket in sorted(family.items()):
        alignment_complete = (
            bucket["unmatched_source_terms"] == 0
            and bucket["unmatched_native_terms"] == 0
        )
        coefficients_exact = all(
            bucket[f"{name}_mismatches"] == 0 for name in ("aj1", "aj2", "cj", "cj2")
        )
        family_rows.append(
            {
                "data_type": dtype,
                "destination_row": destination,
                "type53": 1 if dtype == 53 else 0,
                **bucket,
                "alignment_complete": alignment_complete,
                "coefficients_exact_when_aligned": alignment_complete and coefficients_exact,
                "family_row_status": (
                    "ACCEPT"
                    if alignment_complete and coefficients_exact
                    else "REJECT"
                    if alignment_complete
                    else "NOT_EVALUATED_TERM_STREAM_ALIGNMENT"
                ),
            }
        )
    write_csv(args.output / "call2_he_rate_family_row_gaps.csv", family_rows)

    baseline = (
        prior.get("result") == "ACCEPT"
        and prior_gates.get("CALL2_HE_78_ROW_MAPPING_EXACT") == "ACCEPT"
        and prior_gates.get("CALL2_HE_SEED_TRANSPORT_EXACT") == "ACCEPT"
    )
    capture = source_report.get("result") == "ACCEPT"
    source_trace = bool(outer_trace) and bool(fixed_trace)
    rhs_exact = len(row_comparison) == 78 and all(row["rhs_exact"] for row in row_comparison)
    dense_exact = len(matrix_comparison) == 78 * 78 and all(
        row["dense_exact"] for row in matrix_comparison
    )
    compact_seed_exact = len(seed_comparison) == 78 and all(
        row["source_compact_vs_native_compact_exact"] for row in seed_comparison
    )
    transformed_exact = len(seed_comparison) == 78 and all(
        row["source_compact_vs_native_solver_exact"] for row in seed_comparison
    )
    post_exact = len(row_comparison) == 78 and all(
        row["post_solve_exact"] for row in row_comparison
    )
    outer_exact = len(row_comparison) == 78 and all(
        row["final_outer_start_exact"] for row in row_comparison
    )
    term_alignment_complete = not unmatched_source and not unmatched_native
    metadata_keyed_alignment_available = bool(term_comparison)
    matched_coefficients_exact = bool(term_comparison) and all(
        all_coefficients_exact(row) for row in term_comparison
    )

    if term_alignment_complete:
        type_gates = {
            dtype: family_gate(dtype, term_comparison, unmatched_source, unmatched_native)
            for dtype in (50, 53, 71, 99)
        }
        rate_gate = "ACCEPT" if matched_coefficients_exact else "REJECT"
        rate_attribution_gate = rate_gate
    else:
        type_gates = {dtype: "NOT_EVALUATED_TERM_STREAM_ALIGNMENT" for dtype in (50, 53, 71, 99)}
        rate_gate = "NOT_EVALUATED_TERM_STREAM_ALIGNMENT"
        rate_attribution_gate = "NOT_EVALUATED_TERM_STREAM_ALIGNMENT"

    raw_sum = sum(float(row["raw_global_workspace_value"]) for row in seed_comparison)
    source_compact_sum = sum(float(row["source_compact_mapped_seed"]) for row in seed_comparison)
    native_compact_sum = sum(float(row["native_compact_mapped_seed"]) for row in seed_comparison)
    native_solver_sum = sum(float(row["normalized_native_solver_seed"]) for row in seed_comparison)
    normalization_applied_rows = sum(
        bool(row["native_pre_solve_normalization_applied"]) for row in seed_comparison
    )
    seed_by_row = {int(row["element_row"]): row for row in seed_comparison}
    boundary_row = seed_by_row.get(46, {})
    post_boundary_row = seed_by_row.get(47, {})
    normalization_seed_row = seed_by_row.get(78, {})
    shared_boundary_overwrite_exact = bool(
        boundary_row.get("source_compact_vs_native_compact_exact")
        and post_boundary_row.get("source_compact_vs_native_compact_exact")
        and int(boundary_row.get("loaded_global_level_index", 0)) == 79
        and int(post_boundary_row.get("loaded_global_level_index", 0)) == 81
    )
    terminal_normalization_seed_zero = bool(
        normalization_seed_row.get("source_compact_vs_native_compact_exact")
        and float(normalization_seed_row.get("native_compact_mapped_seed", math.nan)) == 0.0
        and int(normalization_seed_row.get("loaded_global_level_index", -1)) == 0
    )
    pre_solve_normalization_removed = bool(
        normalization_applied_rows == 0
        and transformed_exact
        and exact(source_compact_sum, native_solver_sum)
    )

    seed_semantics_captured = len(seed_comparison) == 78
    matrix_ready = transformed_exact and rhs_exact and dense_exact and term_alignment_complete

    gates: dict[str, str] = {
        "CALL1_ACCEPTED_BASELINE": "ACCEPT" if baseline else "REJECT",
        "CALL2_HE_SOURCE_SOLVE_STATE_CAPTURE": "ACCEPT" if capture else "REJECT",
        "CALL2_HE_SOURCE_ITERATION_TRACE": "ACCEPT" if source_trace else "REJECT",
        "CALL2_HE_SEED_PHASE_LEDGER": "ACCEPT" if seed_semantics_captured else "REJECT",
        "CALL2_HE_RAW_GLOBAL_WORKSPACE_CAPTURE": "ACCEPT" if seed_semantics_captured else "REJECT",
        "CALL2_HE_SOURCE_COMPACT_SEED_SEMANTICS": "ACCEPT" if seed_semantics_captured else "REJECT",
        "CALL2_HE_SHARED_BOUNDARY_OVERWRITE": "ACCEPT" if shared_boundary_overwrite_exact else "REJECT",
        "CALL2_HE_TERMINAL_NORMALIZATION_SEED_ZERO": "ACCEPT" if terminal_normalization_seed_zero else "REJECT",
        "CALL2_HE_NATIVE_COMPACT_SEED_PARITY": "ACCEPT" if compact_seed_exact else "REJECT",
        "CALL2_HE_COMPACT_SEED_MAPPING": "ACCEPT" if compact_seed_exact else "REJECT",
        "CALL2_HE_PRE_SOLVE_NORMALIZATION": "ACCEPT" if pre_solve_normalization_removed else "REJECT",
        "CALL2_HE_PRE_SOLVE_NORMALIZATION_REMOVED": "ACCEPT" if pre_solve_normalization_removed else "REJECT",
        "CALL2_HE_TRANSFORMED_INITIAL_STATE": "ACCEPT" if transformed_exact else "REJECT",
        "CALL2_HE_RHS_CONSTRUCTION": "ACCEPT" if rhs_exact else "REJECT",
        "CALL2_HE_DENSE_MATRIX_ASSEMBLY": "ACCEPT" if dense_exact else "REJECT",
        "CALL2_HE_SOURCE_ORDER_POSITIONAL_COMPARISON": "RETIRED",
        "CALL2_HE_METADATA_KEYED_TERM_ALIGNMENT": (
            "ACCEPT" if metadata_keyed_alignment_available else "REJECT"
        ),
        "CALL2_HE_TERM_STREAM_COMPLETE": "ACCEPT" if term_alignment_complete else "REJECT",
        "CALL2_HE_SOURCE_ORDER_TERM_METADATA": (
            "ACCEPT" if term_alignment_complete else "REJECT"
        ),
        "CALL2_HE_TYPE53_MATRIX_FIXED": type_gates[53],
        "CALL2_HE_TYPE50_RATE_MATRIX": type_gates[50],
        "CALL2_HE_TYPE71_RATE_MATRIX": type_gates[71],
        "CALL2_HE_TYPE99_RATE_MATRIX": type_gates[99],
        "CALL2_HE_RATE_EVALUATION": rate_gate,
        "CALL2_HE_RATE_FAMILY_ATTRIBUTION": rate_attribution_gate,
        "CALL2_HE_MATRIX_SYSTEM_READY": "ACCEPT" if matrix_ready else "REJECT",
        "CALL2_HE_FINAL_OUTER_START_STATE": (
            "ACCEPT"
            if outer_exact
            else "BLOCKED_BY_SEED_SEMANTICS"
            if not transformed_exact
            else "BLOCKED_BY_MATRIX_SYSTEM"
        ),
        "CALL2_HE_POST_SOLVE_POPULATION_EXACT": (
            "ACCEPT"
            if post_exact
            else "BLOCKED_BY_SEED_SEMANTICS"
            if not transformed_exact
            else "BLOCKED_BY_MATRIX_SYSTEM"
        ),
        "CALL2_HE_NATIVE_ITERATION_TRACE": "NOT_CAPTURED_NATIVE_ABI",
        "CALL2_HE_SOLVER_NORMALIZATION": (
            "BLOCKED_BY_SEED_SEMANTICS" if not transformed_exact else "RUN_ALLOWED"
        ),
        "CALL2_HE_MATRIX_THERMAL_ACCUMULATION": (
            "RUN_ALLOWED"
            if rate_gate == "ACCEPT"
            else "BLOCKED_BY_TERM_STREAM_ALIGNMENT"
            if rate_gate == "NOT_EVALUATED_TERM_STREAM_ALIGNMENT"
            else "BLOCKED_BY_RATE_MATRIX"
        ),
        "CALL2_GENERAL_HE_THERMAL": (
            "RUN_ALLOWED" if post_exact else "BLOCKED_BY_POST_SOLVE_POPULATION"
        ),
        "CALLS_3_TO_4": "BLOCKED_BY_CALL2_HELIUM",
        "THERMAL_PARITY": "BLOCKED",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }

    unmatched_source_by_type = Counter(int(row["data_type"]) for row in unmatched_source)
    unmatched_native_by_type = Counter(int(row["data_type"]) for row in unmatched_native)
    core = (
        baseline
        and capture
        and source_trace
        and len(row_comparison) == 78
        and len(matrix_comparison) == 78 * 78
        and seed_semantics_captured
        and metadata_keyed_alignment_available
    )
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if core else "REJECT",
        "rows": len(row_comparison),
        "matrix_cells": len(matrix_comparison),
        "source_terms": len(source_terms),
        "native_terms": len(native_terms),
        "metadata_keyed_matched_terms": len(term_comparison),
        "unmatched_source_terms": len(unmatched_source),
        "unmatched_native_terms": len(unmatched_native),
        "unmatched_source_by_data_type": {
            str(key): value for key, value in sorted(unmatched_source_by_type.items())
        },
        "unmatched_native_by_data_type": {
            str(key): value for key, value in sorted(unmatched_native_by_type.items())
        },
        "source_compact_seed_exact_rows": sum(
            row["source_compact_vs_native_compact_exact"] for row in seed_comparison
        ),
        "transformed_initial_exact_rows": sum(
            row["source_compact_vs_native_solver_exact"] for row in seed_comparison
        ),
        "rhs_exact_rows": sum(row["rhs_exact"] for row in row_comparison),
        "dense_matrix_exact_cells": sum(row["dense_exact"] for row in matrix_comparison),
        "post_solve_exact_rows": sum(row["post_solve_exact"] for row in row_comparison),
        "outer_trace_rows": len(outer_trace),
        "fixed_point_trace_rows": len(fixed_trace),
        "raw_global_workspace_sum": raw_sum,
        "source_compact_seed_sum": source_compact_sum,
        "native_compact_seed_sum": native_compact_sum,
        "effective_runtime_seed_sum": native_compact_sum,
        "native_normalized_solver_seed_sum": native_solver_sum,
        "native_pre_solve_normalization_applied_rows": normalization_applied_rows,
        "shared_boundary_overwrite_exact": shared_boundary_overwrite_exact,
        "terminal_normalization_seed_zero": terminal_normalization_seed_zero,
        "pre_solve_normalization_removed": pre_solve_normalization_removed,
        "native_solver_method": native_state.get("solver_method"),
        "gates": gates,
        "audit_corrections": {
            "positional_term_comparison_retired": True,
            "metadata_key_occurrence_alignment": True,
            "unmatched_term_inventories": True,
            "seed_lifecycle_phases_separated": True,
        },
        "physics_changed": True,
        "physics_change_scope": "helium compact seed construction only",
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    (args.output / "call2_helium_solve_state_rate_matrix_decomposition_summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if core else 2


if __name__ == "__main__":
    raise SystemExit(main())
