"""v0.6.48.7.35 post-Type-56 bound-free and matrix-residual decomposition.

This module is diagnostic only.  It replays source and native matrix terms in
separate source orders, attributes every non-exact dense cell to record-level
coefficient differences, and reconstructs the six ucalc answers for the
remaining Type-50/53/95/99 bound-free/line-coupled records.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.35"
SCHEMA = "xstar-tools-v0648735-post-type56-bound-free-matrix-residual-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TARGET_TYPES = (50, 53, 95, 99)
COEFFICIENTS = ("aj1", "aj2", "cj", "cj2")
ROLES = ("forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def as_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def as_float(row: dict[str, Any], key: str, default: float = math.nan) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "accept"}


def exact(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and a == b


def finite_delta(source: float, native: float) -> float:
    return native - source if math.isfinite(source) and math.isfinite(native) else math.nan


def role_rows(rows: list[dict[str, str]], dtype: int, record: int) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        if as_int(row, "data_type") == dtype and as_int(row, "record") == record:
            out[str(row.get("role", ""))] = row
    return out


def reconstruct_answers(roles: dict[str, dict[str, str]], side: str, xpx: float) -> dict[str, float]:
    fg = roles.get("forward_gain", {})
    rg = roles.get("reverse_gain", {})
    fd = roles.get("forward_diag_loss", {})
    rd = roles.get("reverse_diag_loss", {})
    prefix = f"{side}_"
    return {
        "ans1": as_float(fg, prefix + "aj1"),
        "ans2": as_float(rg, prefix + "aj1"),
        "ans3": -as_float(rd, prefix + "cj") / xpx,
        "ans4": as_float(fd, prefix + "cj") / xpx,
        "ans5": -as_float(rd, prefix + "cj2") / xpx,
        "ans6": as_float(fd, prefix + "cj2") / xpx,
    }




def direct_answer_matches_terms(name: str, value: float, roles: dict[str, dict[str, str]], side: str, xpx: float) -> bool:
    prefix = f"{side}_"
    if name == "ans1":
        return exact(value, as_float(roles.get("forward_gain", {}), prefix + "aj1"))
    if name == "ans2":
        return exact(value, as_float(roles.get("reverse_gain", {}), prefix + "aj1"))
    if name == "ans3":
        return exact(-value * xpx, as_float(roles.get("reverse_diag_loss", {}), prefix + "cj"))
    if name == "ans4":
        return exact(value * xpx, as_float(roles.get("forward_diag_loss", {}), prefix + "cj"))
    if name == "ans5":
        return exact(-value * xpx, as_float(roles.get("reverse_diag_loss", {}), prefix + "cj2"))
    if name == "ans6":
        return exact(value * xpx, as_float(roles.get("forward_diag_loss", {}), prefix + "cj2"))
    return False

def diagnostic_payload(row: dict[str, str], *, native: bool) -> str:
    generic = {
        "evaluation_ordinal", "source_position", "record", "element_index", "element_z",
        "data_type", "rate_type", "ion_index", "ion_stage", "lower_row", "upper_row",
        "matrix_enabled", "active_stage", "matrix_committed", "spectral",
        "ans1", "ans2", "ans3", "ans4", "ans5", "ans6", "density_scale",
    }
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if key in generic or value in ("", None, "nan", "0", "0.0"):
            continue
        if native and key.startswith("type53_delta_"):
            continue
        payload[key] = value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary_path = args.output / SUMMARY
    base = json.loads(summary_path.read_text())
    gates = dict(base.get("gates", {}))

    terms = read_csv(args.output / "call2_he_metadata_keyed_term_comparison.csv")
    matrix = read_csv(args.output / "call2_he_dense_matrix_comparison.csv")
    common_xpx = read_csv(args.output / "call2_he_common_xpx_scaling.csv")
    native_records = read_csv(args.native_replay / "diagnostics/evaluation_0022_records.csv")
    source_direct_path = args.source_capture / "v0472_call2_eval1_he_bound_free_records.csv"
    source_direct = read_csv(source_direct_path) if source_direct_path.is_file() and source_direct_path.stat().st_size else []

    xpx_values = {as_float(row, "density_scale") for row in common_xpx if math.isfinite(as_float(row, "density_scale"))}
    if len(xpx_values) != 1:
        raise RuntimeError(f"non-unique common xpx values: {sorted(xpx_values)}")
    xpx = next(iter(xpx_values))

    # Reconstruct both matrices in their independent insertion orders.  Plain
    # += is deliberate: this is the exact source/native floating-point order.
    source_replay: dict[tuple[int, int], float] = defaultdict(float)
    native_replay: dict[tuple[int, int], float] = defaultdict(float)
    for row in sorted(terms, key=lambda item: as_int(item, "source_source_order_index")):
        cell = (as_int(row, "compact_row"), as_int(row, "compact_column"))
        source_replay[cell] += as_float(row, "source_aj1")
    for row in sorted(terms, key=lambda item: as_int(item, "native_source_order_index")):
        cell = (as_int(row, "compact_row"), as_int(row, "compact_column"))
        native_replay[cell] += as_float(row, "native_aj1")

    matrix_by_cell = {
        (as_int(row, "compact_row"), as_int(row, "compact_column")): row for row in matrix
    }
    bad_cells = {
        cell: row for cell, row in matrix_by_cell.items() if not as_bool(row.get("dense_exact"))
    }
    mismatch_terms_by_cell: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    for row in terms:
        if not as_bool(row.get("aj1_exact")):
            mismatch_terms_by_cell[(as_int(row, "compact_row"), as_int(row, "compact_column"))].append(row)

    cell_summaries: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []
    all_cells_replayed = True
    all_bad_cells_attributed = True
    for cell, row in sorted(matrix_by_cell.items()):
        source_dense = as_float(row, "source_dense")
        native_dense = as_float(row, "native_dense")
        source_exact = exact(source_replay[cell], source_dense)
        native_exact = exact(native_replay[cell], native_dense)
        all_cells_replayed &= source_exact and native_exact
        if cell not in bad_cells:
            continue
        contributions = mismatch_terms_by_cell.get(cell, [])
        attribution_kind = "COEFFICIENT_DELTA"
        if contributions:
            ranked = sorted(
                contributions,
                key=lambda item: (-abs(finite_delta(as_float(item, "source_aj1"), as_float(item, "native_aj1"))), as_int(item, "source_source_order_index")),
            )
        else:
            # A small number of cells differ only because the source and native
            # streams insert identical coefficients in different orders.  List
            # every displaced term so the floating-point sequence is explicit.
            attribution_kind = "ACCUMULATION_ORDER_SEQUENCE"
            ranked = sorted(
                [item for item in terms if (as_int(item, "compact_row"), as_int(item, "compact_column")) == cell],
                key=lambda item: (as_int(item, "source_source_order_index"), as_int(item, "record")),
            )
        all_bad_cells_attributed &= bool(ranked)
        family_counts = Counter(as_int(item, "data_type") for item in ranked)
        record_counts = Counter(as_int(item, "record") for item in ranked)
        algebraic_delta = sum(finite_delta(as_float(item, "source_aj1"), as_float(item, "native_aj1")) for item in contributions)
        dominant = max(
            ranked,
            key=lambda item: (
                abs(finite_delta(as_float(item, "source_aj1"), as_float(item, "native_aj1"))) if contributions else abs(as_float(item, "source_aj1")),
                -as_int(item, "source_source_order_index"),
            ),
        )
        dense_delta = native_dense - source_dense
        for rank, item in enumerate(ranked, 1):
            delta = finite_delta(as_float(item, "source_aj1"), as_float(item, "native_aj1"))
            contribution_rows.append({
                "attribution_kind": attribution_kind,
                "compact_row": cell[0], "compact_column": cell[1],
                "source_dense": source_dense, "native_dense": native_dense, "dense_delta": dense_delta,
                "cell_contribution_rank": rank,
                "source_order_index": as_int(item, "source_source_order_index"),
                "native_order_index": as_int(item, "native_source_order_index"),
                "record": as_int(item, "record"), "data_type": as_int(item, "data_type"),
                "rate_type": as_int(item, "rate_type"), "role": item.get("role", ""),
                "source_aj1": as_float(item, "source_aj1"), "native_aj1": as_float(item, "native_aj1"),
                "signed_aj1_delta": delta, "absolute_aj1_delta": abs(delta),
                "absolute_delta_fraction": abs(delta) / abs(dense_delta) if dense_delta else math.nan,
            })
        cell_summaries.append({
            "compact_row": cell[0], "compact_column": cell[1],
            "source_dense": source_dense, "native_dense": native_dense, "dense_delta": dense_delta,
            "source_replayed_dense": source_replay[cell], "native_replayed_dense": native_replay[cell],
            "source_replay_exact": source_exact, "native_replay_exact": native_exact,
            "attribution_kind": attribution_kind,
            "mismatched_contribution_count": len(contributions),
            "attribution_term_count": len(ranked),
            "data_types": ";".join(str(value) for value in sorted(family_counts)),
            "records": ";".join(str(value) for value in sorted(record_counts)),
            "algebraic_sum_of_term_deltas": algebraic_delta,
            "accumulation_roundoff_residual": dense_delta - algebraic_delta,
            "dominant_data_type": as_int(dominant, "data_type"),
            "dominant_record": as_int(dominant, "record"),
            "dominant_role": dominant.get("role", ""),
            "dominant_source_order_index": as_int(dominant, "source_source_order_index"),
            "dominant_signed_delta": finite_delta(as_float(dominant, "source_aj1"), as_float(dominant, "native_aj1")),
        })

    write_csv(args.output / "call2_he_remaining_matrix_cell_decomposition.csv", contribution_rows)
    write_csv(args.output / "call2_he_remaining_matrix_cell_summary.csv", cell_summaries)

    # Record-level ans1..ans6 reconstruction for the four coupled families.
    source_direct_by_key = {(as_int(row, "data_type"), as_int(row, "record")): row for row in source_direct if as_int(row, "data_type") in TARGET_TYPES}
    native_direct_by_key = {
        (as_int(row, "data_type"), as_int(row, "record")): row
        for row in native_records
        if as_int(row, "element_z") == 2 and as_int(row, "data_type") in TARGET_TYPES and as_int(row, "matrix_committed") == 1
    }
    keys = sorted({(as_int(row, "data_type"), as_int(row, "record")) for row in terms if as_int(row, "data_type") in TARGET_TYPES})
    answer_rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []
    family_record_counts: Counter[int] = Counter()
    family_mismatch_records: Counter[int] = Counter()
    direct_source_exact = True
    direct_native_exact = True
    role_complete = True
    for dtype, record in keys:
        roles = role_rows(terms, dtype, record)
        role_complete &= all(role in roles for role in ROLES)
        source_answers = reconstruct_answers(roles, "source", xpx)
        native_answers = reconstruct_answers(roles, "native", xpx)
        direct_source = source_direct_by_key.get((dtype, record), {})
        direct_native = native_direct_by_key.get((dtype, record), {})
        row: dict[str, Any] = {
            "data_type": dtype, "record": record,
            "rate_type": as_int(next(iter(roles.values()), {}), "rate_type"),
            "source_order_index": min((as_int(value, "source_source_order_index", 10**9) for value in roles.values()), default=0),
            "compact_rows": ";".join(str(v) for v in sorted({as_int(value, "compact_row") for value in roles.values()})),
            "compact_columns": ";".join(str(v) for v in sorted({as_int(value, "compact_column") for value in roles.values()})),
            "role_count": len(roles), "roles_complete": all(role in roles for role in ROLES),
            "source_direct_capture_present": bool(direct_source),
            "native_direct_capture_present": bool(direct_native),
        }
        any_mismatch = False
        for name in (f"ans{index}" for index in range(1, 7)):
            source_value = source_answers[name]
            native_value = native_answers[name]
            row[f"source_{name}"] = source_value
            row[f"native_{name}"] = native_value
            row[f"{name}_exact"] = exact(source_value, native_value)
            row[f"{name}_signed_delta"] = finite_delta(source_value, native_value)
            row[f"{name}_abs_delta"] = abs(finite_delta(source_value, native_value))
            any_mismatch |= not row[f"{name}_exact"]
            if direct_source:
                row[f"source_direct_{name}"] = as_float(direct_source, name)
                row[f"source_direct_{name}_matches_terms"] = direct_answer_matches_terms(name, as_float(direct_source, name), roles, "source", xpx)
                direct_source_exact &= row[f"source_direct_{name}_matches_terms"]
            if direct_native:
                row[f"native_direct_{name}"] = as_float(direct_native, name)
                row[f"native_direct_{name}_matches_terms"] = direct_answer_matches_terms(name, as_float(direct_native, name), roles, "native", xpx)
                direct_native_exact &= row[f"native_direct_{name}_matches_terms"]
        row["record_answers_exact"] = not any_mismatch
        answer_rows.append(row)
        family_record_counts[dtype] += 1
        if any_mismatch:
            family_mismatch_records[dtype] += 1
        context_rows.append({
            "data_type": dtype, "record": record,
            "source_context_available": bool(direct_source),
            "native_context_available": bool(direct_native),
            "source_context_json": diagnostic_payload(direct_source, native=False) if direct_source else "{}",
            "native_context_json": diagnostic_payload(direct_native, native=True) if direct_native else "{}",
        })
    write_csv(args.output / "call2_he_bound_free_record_answer_comparison.csv", answer_rows)
    write_csv(args.output / "call2_he_bound_free_record_context.csv", context_rows)

    # Remaining-family summary and earliest/dominant causal records.
    residual_families: dict[int, dict[str, Any]] = defaultdict(lambda: {
        "terms": 0, "records": set(), "affected_dense_cells": set(),
        "aj1_mismatches": 0, "aj2_mismatches": 0, "cj_mismatches": 0, "cj2_mismatches": 0,
        "max_abs_delta": 0.0, "first": None, "record_l1": defaultdict(float),
    })
    first_remaining: tuple[Any, ...] | None = None
    first_bound_free: tuple[Any, ...] | None = None
    for row in terms:
        dtype = as_int(row, "data_type")
        record = as_int(row, "record")
        mismatched_fields = [name for name in COEFFICIENTS if not as_bool(row.get(f"{name}_exact"))]
        if not mismatched_fields:
            continue
        bucket = residual_families[dtype]
        bucket["terms"] += 1
        bucket["records"].add(record)
        if "aj1" in mismatched_fields:
            bucket["affected_dense_cells"].add((as_int(row, "compact_row"), as_int(row, "compact_column")))
        for name in mismatched_fields:
            delta = finite_delta(as_float(row, f"source_{name}"), as_float(row, f"native_{name}"))
            bucket[f"{name}_mismatches"] += 1
            bucket["max_abs_delta"] = max(bucket["max_abs_delta"], abs(delta))
            bucket["record_l1"][record] += abs(delta)
            candidate = (
                as_int(row, "source_source_order_index"), record, dtype,
                str(row.get("role", "")), name,
                as_float(row, f"source_{name}"), as_float(row, f"native_{name}"), delta,
            )
            if bucket["first"] is None or candidate < bucket["first"]:
                bucket["first"] = candidate
            if first_remaining is None or candidate < first_remaining:
                first_remaining = candidate
            if dtype in TARGET_TYPES and (first_bound_free is None or candidate < first_bound_free):
                first_bound_free = candidate

    family_rows: list[dict[str, Any]] = []
    for dtype, bucket in sorted(residual_families.items()):
        dominant_record, dominant_l1 = max(bucket["record_l1"].items(), key=lambda item: (item[1], -item[0]))
        first = bucket["first"]
        family_rows.append({
            "data_type": dtype, "target_bound_free_family": dtype in TARGET_TYPES,
            "mismatched_terms": bucket["terms"], "mismatched_records": len(bucket["records"]),
            "affected_dense_cells": len(bucket["affected_dense_cells"]),
            "aj1_mismatches": bucket["aj1_mismatches"], "aj2_mismatches": bucket["aj2_mismatches"],
            "cj_mismatches": bucket["cj_mismatches"], "cj2_mismatches": bucket["cj2_mismatches"],
            "max_abs_delta": bucket["max_abs_delta"],
            "first_source_order_index": first[0], "first_record": first[1], "first_role": first[3], "first_field": first[4],
            "dominant_record": dominant_record, "dominant_record_l1_delta": dominant_l1,
            "record_ids": ";".join(str(value) for value in sorted(bucket["records"])),
        })
    write_csv(args.output / "call2_he_remaining_family_residual_summary.csv", family_rows)

    target_family_localized: dict[int, bool] = {}
    for dtype in TARGET_TYPES:
        relevant = [row for row in answer_rows if row["data_type"] == dtype]
        target_family_localized[dtype] = bool(relevant) and all(row["roles_complete"] for row in relevant)

    direct_source_status = (
        "ACCEPT" if source_direct and direct_source_exact and set(source_direct_by_key) == set(keys)
        else "RUN_REQUIRED_RECONSTRUCTED_FROM_TERMS"
    )
    direct_native_status = "ACCEPT" if direct_native_exact and set(native_direct_by_key) == set(keys) else "REJECT"
    expected_bad_cells = int(base.get("matrix_cells", len(matrix))) - int(base.get("dense_matrix_exact_cells", 0))
    decomposition_complete = (
        len(matrix) == 6084 and len(bad_cells) == expected_bad_cells == 597
        and all_cells_replayed and all_bad_cells_attributed
        and len(cell_summaries) == 597 and role_complete
    )

    gates.update({
        "CALL2_HE_REMAINING_597_CELL_DECOMPOSITION": "ACCEPT" if decomposition_complete else "REJECT",
        "CALL2_HE_SOURCE_MATRIX_ORDER_REPLAY": "ACCEPT" if all_cells_replayed else "REJECT",
        "CALL2_HE_EVERY_REMAINING_CELL_ATTRIBUTED": "ACCEPT" if all_bad_cells_attributed and len(cell_summaries) == 597 else "REJECT",
        "CALL2_HE_BOUND_FREE_RECORD_ANSWER_RECONSTRUCTION": "ACCEPT" if role_complete and len(answer_rows) == 438 else "REJECT",
        "CALL2_HE_BOUND_FREE_DIRECT_SOURCE_RECORD_CAPTURE": direct_source_status,
        "CALL2_HE_BOUND_FREE_DIRECT_NATIVE_RECORD_CAPTURE": direct_native_status,
        "CALL2_HE_FIRST_CAUSAL_RECORD_IDENTIFIED": "ACCEPT" if first_remaining else "REJECT",
        "CALL2_HE_FIRST_BOUND_FREE_CAUSAL_RECORD_IDENTIFIED": "ACCEPT" if first_bound_free else "REJECT",
        "CALL2_HE_TYPE50_RESIDUAL_LOCALIZED": "ACCEPT" if target_family_localized[50] else "REJECT",
        "CALL2_HE_TYPE53_RESIDUAL_LOCALIZED": "ACCEPT" if target_family_localized[53] else "REJECT",
        "CALL2_HE_TYPE95_RESIDUAL_LOCALIZED": "ACCEPT" if target_family_localized[95] else "REJECT",
        "CALL2_HE_TYPE99_RESIDUAL_LOCALIZED": "ACCEPT" if target_family_localized[99] else "REJECT",
        "CALL2_HE_TYPE50_ROOT_CAUSE": "NOT_EVALUATED_DECOMPOSITION_ONLY",
        "CALL2_HE_TYPE53_ROOT_CAUSE": "NOT_EVALUATED_DECOMPOSITION_ONLY",
        "CALL2_HE_TYPE95_ROOT_CAUSE": "NOT_EVALUATED_DECOMPOSITION_ONLY",
        "CALL2_HE_TYPE99_ROOT_CAUSE": "NOT_EVALUATED_DECOMPOSITION_ONLY",
        "CALL2_HE_FIXED_STATE_PARITY": "BLOCKED_BY_597_MATRIX_CELLS",
        "THERMAL_PARITY": "BLOCKED",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    })

    inherited = all(gates.get(name) == "ACCEPT" for name in (
        "CALL2_HE_COMPACT_SEED_MAPPING", "CALL2_HE_TRANSFORMED_INITIAL_STATE",
        "CALL2_HE_RHS_CONSTRUCTION", "CALL2_HE_TERM_STREAM_COMPLETE",
        "CALL2_HE_TYPE56_RATE_MATRIX", "CALL2_HE_TYPE63_RATE_MATRIX", "CALL2_HE_TYPE71_RATE_MATRIX",
    ))
    targeted = all(gates.get(name) == "ACCEPT" for name in (
        "CALL2_HE_REMAINING_597_CELL_DECOMPOSITION", "CALL2_HE_SOURCE_MATRIX_ORDER_REPLAY",
        "CALL2_HE_EVERY_REMAINING_CELL_ATTRIBUTED", "CALL2_HE_BOUND_FREE_RECORD_ANSWER_RECONSTRUCTION",
        "CALL2_HE_BOUND_FREE_DIRECT_NATIVE_RECORD_CAPTURE", "CALL2_HE_FIRST_CAUSAL_RECORD_IDENTIFIED",
        "CALL2_HE_FIRST_BOUND_FREE_CAUSAL_RECORD_IDENTIFIED", "CALL2_HE_TYPE50_RESIDUAL_LOCALIZED",
        "CALL2_HE_TYPE53_RESIDUAL_LOCALIZED", "CALL2_HE_TYPE95_RESIDUAL_LOCALIZED",
        "CALL2_HE_TYPE99_RESIDUAL_LOCALIZED",
    ))

    dominant_cell = max(cell_summaries, key=lambda item: abs(float(item["dense_delta"])))
    report = dict(base)
    report.update({
        "schema": SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if inherited and targeted else "REJECT",
        "physics_changed": False,
        "physics_change_scope": "none; post-Type-56 bound-free coefficient and matrix-residual decomposition only",
        "qualification_only": True, "production_promotion_ready": False,
        "matrix_cells": len(matrix), "dense_matrix_exact_cells": len(matrix) - len(bad_cells),
        "remaining_incorrect_matrix_cells": len(bad_cells),
        "matrix_cell_decomposition_rows": len(contribution_rows),
        "bound_free_record_count": len(answer_rows),
        "bound_free_record_counts_by_type": {str(key): value for key, value in sorted(family_record_counts.items())},
        "bound_free_mismatched_record_counts_by_type": {str(key): value for key, value in sorted(family_mismatch_records.items())},
        "direct_source_bound_free_record_count": len(source_direct_by_key),
        "direct_native_bound_free_record_count": len(native_direct_by_key),
        "common_xpx": xpx,
        "first_remaining_coefficient_divergence": {
            "source_order_index": first_remaining[0], "record": first_remaining[1], "data_type": first_remaining[2],
            "role": first_remaining[3], "field": first_remaining[4],
            "source_value": first_remaining[5], "native_value": first_remaining[6], "signed_delta": first_remaining[7],
        } if first_remaining else None,
        "first_bound_free_coefficient_divergence": {
            "source_order_index": first_bound_free[0], "record": first_bound_free[1], "data_type": first_bound_free[2],
            "role": first_bound_free[3], "field": first_bound_free[4],
            "source_value": first_bound_free[5], "native_value": first_bound_free[6], "signed_delta": first_bound_free[7],
        } if first_bound_free else None,
        "dominant_matrix_residual": {
            "compact_row": dominant_cell["compact_row"], "compact_column": dominant_cell["compact_column"],
            "dense_delta": dominant_cell["dense_delta"], "data_type": dominant_cell["dominant_data_type"],
            "record": dominant_cell["dominant_record"], "role": dominant_cell["dominant_role"],
            "source_order_index": dominant_cell["dominant_source_order_index"],
        },
        "remaining_residual_data_types": [row["data_type"] for row in family_rows],
        "gates": gates,
    })
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
