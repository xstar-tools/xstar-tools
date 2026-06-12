"""Audit the complete original-DSEC He II row-46 source-order contract.

The audit consumes a v0.6.47.2 runtime bundle produced by
``v0472_dsec_row46_runtime_capture`` and compares it with the v0.6.48.7.13
qualification state (exact type-53, type-71, type-99 record 1695, and the live
DSEC type-50 manifold).  It reconstructs the original row-46 equation in
source order, verifies normalization behavior, substitutes the complete live
row-46 term set offline, and decomposes the remaining reference-population
residual by data type.  It never promotes a single record or family.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .helium_family_isolation import (
    RADIATION_SHA256,
    discover_reference,
    read_csv,
    run_command,
    sha256,
    write_csv,
    write_json,
)
from .helium_solve_response_decomposition import (
    _diagnostic_path,
    _effective_system,
    _matrix,
    _reference_populations,
    _residual_rows,
    _solve_rows,
    _verify_source_order_assembly,
)
from .type50_dsec_coupled_replacement_audit import _run as _run_type50_dsec_candidate
from .v0472_dsec_row46_runtime_capture import (
    NORMALIZATION_NAME,
    RECORDS_NAME,
    ROW46_MATRIX_NAME,
    SOLVE_ROWS_NAME,
    TARGET_EVALUATION,
    TARGET_FULL_ROW,
    TARGET_MATRIX_TERMS,
    TARGET_RECORDS,
    TARGET_TYPE_COUNTS,
    NATIVE_ONLY_ROW46_RECORDS,
    TERMS_NAME,
    verify as verify_capture,
)

csv.field_size_limit(sys.maxsize)

RELEASE = "0.6.48.7.14.2"
SCHEMA = "xstar-tools-v06487142-row46-dsec-residual-audit-v1"
ROLE_MAP = {
    "forward_gain": "forward_offdiag",
    "reverse_gain": "reverse_offdiag",
    "forward_diag_loss": "forward_diag_loss",
    "reverse_diag_loss": "reverse_diag_loss",
}


def _bits(value: str | float) -> bytes:
    return struct.pack(">d", float(value))


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _candidate_rows(run: Path, evaluation: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    records = read_csv(_diagnostic_path(run, evaluation, "records.csv"))
    terms = read_csv(_diagnostic_path(run, evaluation, "helium_source_order_terms.csv"))
    return records, terms


def _capture_inventory(capture: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    records = read_csv(capture / RECORDS_NAME)
    terms = read_csv(capture / TERMS_NAME)
    return records, terms


def _record_comparison(
    captured: list[dict[str, str]],
    candidate_records: list[dict[str, str]],
    output: Path,
) -> dict[str, Any]:
    actual = {
        (int(row["source_position"]), int(row["record"])): row
        for row in candidate_records
        if int(row.get("element_z", -1)) == 2
    }
    rows: list[dict[str, Any]] = []
    exact_by_type: dict[int, Counter[str]] = defaultdict(Counter)
    for oracle in captured:
        key = (int(oracle["source_position"]), int(oracle["record"]))
        candidate = actual.get(key)
        if candidate is None:
            raise ValueError(f"native candidate missing row-46 record {key}")
        data_type = int(oracle["data_type"])
        row: dict[str, Any] = {
            "source_position": key[0],
            "record": key[1],
            "data_type": data_type,
            "rate_type": int(oracle["rate_type"]),
            "lower_row": int(oracle["lower_row"]),
            "upper_row": int(oracle["upper_row"]),
            "escape_kind": oracle.get("escape_kind", ""),
            "escape_index": int(oracle.get("escape_index") or 0),
            "tau_in": float(oracle.get("tau_in") or 0.0),
            "tau_out": float(oracle.get("tau_out") or 0.0),
            "ptmp1": float(oracle["ptmp1"]),
            "ptmp2": float(oracle["ptmp2"]),
            "covering_fraction": float(oracle["covering_fraction"]),
            "initial_lower_population": float(oracle.get("initial_lower_population") or 0.0),
            "initial_upper_population": float(oracle.get("initial_upper_population") or 0.0),
            "final_lower_population": float(oracle.get("final_lower_population") or 0.0),
            "final_upper_population": float(oracle.get("final_upper_population") or 0.0),
        }
        all_exact = True
        for index in range(1, 7):
            field = f"ans{index}"
            exact = _bits(oracle[field]) == _bits(candidate[field])
            all_exact = all_exact and exact
            exact_by_type[data_type][field] += int(exact)
            row[f"dsec_{field}"] = float(oracle[field])
            row[f"native_{field}"] = float(candidate[field])
            row[f"{field}_ieee_exact"] = exact
        row["all_answers_ieee_exact"] = all_exact
        rows.append(row)
    write_csv(output / "row46_dsec_record_comparison.csv", rows, list(rows[0]))
    type_summary = {
        str(data_type): {
            "records": TARGET_TYPE_COUNTS[data_type],
            "exact_by_answer": {field: exact_by_type[data_type][field] for field in [f"ans{i}" for i in range(1, 7)]},
        }
        for data_type in sorted(TARGET_TYPE_COUNTS)
    }
    exact_records = sum(int(row["all_answers_ieee_exact"]) for row in rows)
    return {
        "records": len(rows),
        "answers": len(rows) * 6,
        "records_all_answers_ieee_exact": exact_records,
        "all_records_ieee_exact": exact_records == len(rows),
        "by_data_type": type_summary,
    }


def _term_key_from_candidate(row: dict[str, str]) -> tuple[int, int, str]:
    return (
        int(row["contribution_source_position"]),
        int(row["record"]),
        ROLE_MAP[str(row["role"])],
    )


def _term_comparison(
    captured: list[dict[str, str]],
    candidate_terms: list[dict[str, str]],
    output: Path,
) -> tuple[dict[str, Any], dict[tuple[int, int, str], dict[str, str]]]:
    actual = {_term_key_from_candidate(row): row for row in candidate_terms}
    rows: list[dict[str, Any]] = []
    exact_terms = 0
    absolute_order_exact = 0
    exact_by_type: Counter[int] = Counter()
    captured_by_key: dict[tuple[int, int, str], dict[str, str]] = {}
    captured_sequence: list[tuple[int, int, str]] = []
    for oracle in sorted(captured, key=lambda row: int(row["source_order_index"])):
        key = (int(oracle["source_position"]), int(oracle["record"]), str(oracle["role"]))
        captured_sequence.append(key)
        captured_by_key[key] = oracle
        candidate = actual.get(key)
        if candidate is None:
            raise ValueError(f"native candidate missing row-46 term {key}")
        data_type = int(oracle["data_type"])
        dsec_order = int(oracle["source_order_index"])
        native_order = int(candidate["source_order_index"])
        row: dict[str, Any] = {
            "source_position": key[0],
            "record": key[1],
            "data_type": data_type,
            "rate_type": int(oracle["rate_type"]),
            "role": key[2],
            "row": int(oracle["row"]),
            "column": int(oracle["column"]),
            "dsec_source_order_index": dsec_order,
            "native_source_order_index": native_order,
            "source_order_index_delta": native_order - dsec_order,
        }
        row["absolute_source_order_index_exact"] = dsec_order == native_order
        absolute_order_exact += int(row["absolute_source_order_index_exact"])
        all_exact = True
        for field in ("aj1", "aj2", "cj", "cj2"):
            exact = _bits(oracle[field]) == _bits(candidate[field])
            all_exact = all_exact and exact
            row[f"dsec_{field}"] = float(oracle[field])
            row[f"native_{field}"] = float(candidate[field])
            row[f"{field}_ieee_exact"] = exact
        row["term_ieee_exact"] = all_exact
        exact_terms += int(all_exact)
        exact_by_type[data_type] += int(all_exact)
        rows.append(row)
    write_csv(output / "row46_dsec_term_comparison.csv", rows, list(rows[0]))

    candidate_sequence = [
        _term_key_from_candidate(row)
        for row in sorted(candidate_terms, key=lambda row: int(row["source_order_index"]))
        if _term_key_from_candidate(row) in captured_by_key
    ]
    relative_order_exact = candidate_sequence == captured_sequence

    candidate_row46 = {
        _term_key_from_candidate(row): row
        for row in candidate_terms
        if int(row["full_row"]) == TARGET_FULL_ROW or int(row["full_column"]) == TARGET_FULL_ROW
    }
    captured_keys = set(captured_by_key)
    extras = set(candidate_row46) - captured_keys
    expected_native_only = {
        key for key in extras if (key[0], key[1]) in NATIVE_ONLY_ROW46_RECORDS
    }
    unexpected_extras = extras - expected_native_only
    native_only_rows = []
    for key in sorted(expected_native_only, key=lambda value: int(candidate_row46[value]["source_order_index"])):
        row = candidate_row46[key]
        native_only_rows.append({
            "source_position": key[0],
            "record": key[1],
            "data_type": int(row["data_type"]),
            "rate_type": int(row["rate_type"]),
            "role": key[2],
            "native_source_order_index": int(row["source_order_index"]),
            "full_row": int(row["full_row"]),
            "full_column": int(row["full_column"]),
            "aj1": float(row["aj1"]),
            "aj2": float(row["aj2"]),
            "cj": float(row["cj"]),
            "cj2": float(row["cj2"]),
            "original_dsec_action": "absent_remove_native_term",
        })
    if native_only_rows:
        write_csv(output / "row46_native_only_terms.csv", native_only_rows, list(native_only_rows[0]))

    return (
        {
            "terms": len(rows),
            "exact_terms": exact_terms,
            "all_terms_ieee_exact": exact_terms == len(rows),
            "absolute_source_order_indices_exact": absolute_order_exact,
            "absolute_source_order_fully_exact": absolute_order_exact == len(rows),
            "relative_source_order_exact": relative_order_exact,
            "source_order_index_delta_min": min((int(row["source_order_index_delta"]) for row in rows), default=0),
            "source_order_index_delta_max": max((int(row["source_order_index_delta"]) for row in rows), default=0),
            "native_only_terms": len(expected_native_only),
            "native_only_records": [
                {"source_position": source_position, "record": record}
                for source_position, record in sorted(NATIVE_ONLY_ROW46_RECORDS)
            ],
            "unexpected_native_row46_terms": len(unexpected_extras),
            "exact_terms_by_data_type": {str(k): exact_by_type[k] for k in sorted(TARGET_TYPE_COUNTS)},
        },
        captured_by_key,
    )


def _normalization_comparison(
    captured_normalization: list[dict[str, str]],
    candidate_dense: np.ndarray,
    candidate_rhs: np.ndarray,
    normalization_index: int,
    output: Path,
) -> dict[str, Any]:
    effective, effective_rhs = _effective_system(candidate_dense, normalization_index)
    rows: list[dict[str, Any]] = []
    pre_exact = post_exact = rhs_exact = 0
    for oracle in captured_normalization:
        column = int(oracle["compact_column"]) - 1
        row = {
            "compact_column": column + 1,
            "dsec_dense_before_normalization": float(oracle["dense_before_normalization"]),
            "native_dense_before_normalization": float(candidate_dense[normalization_index, column]),
            "dsec_normalized_after_commit": float(oracle["normalized_after_commit"]),
            "native_normalized_after_commit": float(effective[normalization_index, column]),
            "dsec_rhs": float(oracle["rhs"]),
            "native_rhs": float(effective_rhs[normalization_index]),
        }
        row["dense_before_ieee_exact"] = _bits(row["dsec_dense_before_normalization"]) == _bits(row["native_dense_before_normalization"])
        row["normalized_after_ieee_exact"] = _bits(row["dsec_normalized_after_commit"]) == _bits(row["native_normalized_after_commit"])
        row["rhs_ieee_exact"] = _bits(row["dsec_rhs"]) == _bits(row["native_rhs"])
        pre_exact += int(row["dense_before_ieee_exact"])
        post_exact += int(row["normalized_after_ieee_exact"])
        rhs_exact += int(row["rhs_ieee_exact"])
        rows.append(row)
    write_csv(output / "row46_dsec_normalization_comparison.csv", rows, list(rows[0]))
    return {
        "columns": len(rows),
        "dense_before_exact_columns": pre_exact,
        "normalized_after_exact_columns": post_exact,
        "rhs_exact_columns": rhs_exact,
        "source_normalization_contract_exact": post_exact == len(rows) and rhs_exact == len(rows),
        "pre_normalization_row_exact": pre_exact == len(rows),
    }


def _source_row_reconstruction(captured_terms: list[dict[str, str]], captured_row: list[dict[str, str]]) -> dict[str, Any]:
    n = len(captured_row)
    reconstructed = np.zeros(n, dtype=np.float64)
    for term in sorted(captured_terms, key=lambda row: int(row["source_order_index"])):
        if int(term["row"]) == TARGET_FULL_ROW:
            reconstructed[int(term["column"]) - 1] += float(term["aj1"])
    expected = np.asarray([float(row["dense_before_normalization"]) for row in captured_row], dtype=np.float64)
    exact = [
        _bits(reconstructed[index]) == _bits(expected[index])
        for index in range(n)
    ]
    return {
        "columns": n,
        "ieee_exact_columns": sum(exact),
        "all_ieee_exact": all(exact),
        "maximum_absolute_difference": float(np.max(np.abs(reconstructed - expected))) if n else 0.0,
        "l1_difference": float(np.sum(np.abs(reconstructed - expected))),
    }


def _substitute_terms(
    dense: np.ndarray,
    heat: np.ndarray,
    heat2: np.ndarray,
    candidate_terms: list[dict[str, str]],
    captured_by_key: dict[tuple[int, int, str], dict[str, str]],
    selected_types: set[int] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    out_dense = dense.copy()
    out_heat = heat.copy()
    out_heat2 = heat2.copy()
    replaced = 0
    removed_native_only = 0
    for candidate in candidate_terms:
        key = _term_key_from_candidate(candidate)
        candidate_type = int(candidate["data_type"])
        if selected_types is not None and candidate_type not in selected_types:
            continue
        row = int(candidate["compact_row"]) - 1
        column = int(candidate["compact_column"]) - 1
        oracle = captured_by_key.get(key)
        if oracle is not None:
            out_dense[row, column] += float(oracle["aj1"]) - float(candidate["aj1"])
            out_heat[row, column] += float(oracle["cj"]) - float(candidate["cj"])
            out_heat2[row, column] += float(oracle["cj2"]) - float(candidate["cj2"])
            replaced += 1
        elif (key[0], key[1]) in NATIVE_ONLY_ROW46_RECORDS:
            out_dense[row, column] -= float(candidate["aj1"])
            out_heat[row, column] -= float(candidate["cj"])
            out_heat2[row, column] -= float(candidate["cj2"])
            removed_native_only += 1
    return out_dense, out_heat, out_heat2, replaced, removed_native_only


def _residual_metrics(dense: np.ndarray, vector: np.ndarray, normalization_index: int) -> tuple[float, float, np.ndarray]:
    residual = dense @ vector
    residual = residual.astype(np.float64, copy=True)
    residual[normalization_index] = float(np.sum(vector) - 1.0)
    return float(np.sum(np.abs(residual))), float(np.max(np.abs(residual))), residual


def audit(
    package_dir: Path,
    lowered_program: Path,
    capture_bundle: Path,
    output_dir: Path,
    *,
    evaluation: int = TARGET_EVALUATION,
    radiation_csv: Path | None = None,
) -> dict[str, Any]:
    if evaluation != TARGET_EVALUATION:
        raise ValueError("row-46 DSEC residual audit is restricted to evaluation 61")
    root = package_dir.resolve()
    lowered = lowered_program.resolve()
    capture = capture_bundle.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    capture_verification = verify_capture(capture)
    if capture_verification["result"] != "ACCEPT":
        raise ValueError(f"row-46 capture rejected: {capture_verification['errors']}")
    captured_records, captured_terms = _capture_inventory(capture)
    captured_solve_rows = read_csv(capture / SOLVE_ROWS_NAME)
    captured_row46 = read_csv(capture / ROW46_MATRIX_NAME)
    captured_normalization = read_csv(capture / NORMALIZATION_NAME)

    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(root, "reference_radiation_v0472_full.csv")
    if sha256(radiation) != RADIATION_SHA256:
        raise ValueError("qualification radiation hash mismatch")
    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=environment)
    candidate = output / "candidate_exact_53_71_99_actual_dsec_type50"
    _run_type50_dsec_candidate(root, executable, lowered, trajectory, radiation, candidate, evaluation, True)

    candidate_records, candidate_terms = _candidate_rows(candidate, evaluation)
    record_comparison = _record_comparison(captured_records, candidate_records, output)
    term_comparison, captured_by_key = _term_comparison(captured_terms, candidate_terms, output)

    solve_rows = _solve_rows(candidate, evaluation)
    dense, heat, heat2, rhs = _matrix(candidate, evaluation)
    normalization_index = next(index for index, row in enumerate(solve_rows) if int(row["is_normalization_row"]) == 1)
    reference = _reference_populations(root, evaluation, solve_rows)
    normalization = _normalization_comparison(captured_normalization, dense, rhs, normalization_index, output)
    reconstruction = _source_row_reconstruction(captured_terms, captured_row46)

    candidate_l1, candidate_linf, candidate_residual = _residual_metrics(dense, reference, normalization_index)
    substituted_dense, substituted_heat, substituted_heat2, replaced, removed_native_only = _substitute_terms(
        dense, heat, heat2, candidate_terms, captured_by_key
    )
    complete_l1, complete_linf, complete_residual = _residual_metrics(substituted_dense, reference, normalization_index)

    residual_rows = _residual_rows(
        "original_dsec_row46_substitution",
        solve_rows,
        substituted_dense,
        reference,
        normalization_index,
        "v0472_reference",
    )
    write_csv(output / "row46_dsec_reference_residual_rows.csv", residual_rows, list(residual_rows[0]))

    scope_rows: list[dict[str, Any]] = []
    for data_type in sorted(TARGET_TYPE_COUNTS):
        scope_dense, _, _, scope_replaced, scope_removed_native_only = _substitute_terms(
            dense, heat, heat2, candidate_terms, captured_by_key, {data_type}
        )
        scope_l1, scope_linf, scope_residual = _residual_metrics(scope_dense, reference, normalization_index)
        scope_rows.append(
            {
                "data_type": data_type,
                "records": TARGET_TYPE_COUNTS[data_type],
                "terms_replaced": scope_replaced,
                "native_only_terms_removed": scope_removed_native_only,
                "candidate_reference_residual_l1": candidate_l1,
                "scope_reference_residual_l1": scope_l1,
                "absolute_l1_reduction": candidate_l1 - scope_l1,
                "fraction_l1_reduced": (candidate_l1 - scope_l1) / max(candidate_l1, 1.0e-300),
                "scope_reference_residual_linf": scope_linf,
                "row46_residual_before": float(candidate_residual[TARGET_FULL_ROW - 1]),
                "row46_residual_after": float(scope_residual[TARGET_FULL_ROW - 1]),
                "row46_absolute_reduction": abs(float(candidate_residual[TARGET_FULL_ROW - 1])) - abs(float(scope_residual[TARGET_FULL_ROW - 1])),
            }
        )
    scope_rows.sort(key=lambda row: row["absolute_l1_reduction"], reverse=True)
    write_csv(output / "row46_dsec_residual_scope_ranking.csv", scope_rows, list(scope_rows[0]))

    source_terms = [
        {
            **row,
            "source_order_index": int(row["source_order_index"]),
            "compact_row": int(row["compact_row"]),
            "compact_column": int(row["compact_column"]),
            "aj1": float(row["aj1"]),
        }
        for row in candidate_terms
    ]
    candidate_assembly = _verify_source_order_assembly(source_terms, dense)
    substituted_assembly_terms = []
    for row in source_terms:
        key = _term_key_from_candidate(row)
        if (key[0], key[1]) in NATIVE_ONLY_ROW46_RECORDS:
            continue
        oracle = captured_by_key.get(key)
        updated = dict(row)
        if oracle is not None:
            updated["aj1"] = float(oracle["aj1"])
        substituted_assembly_terms.append(updated)
    # The native-only self-loop is the final four-term record today, but
    # renumber explicitly so the reconstruction remains valid if ordering
    # changes in a later diagnostic build.
    for index, row in enumerate(substituted_assembly_terms, 1):
        row["source_order_index"] = index
    substituted_assembly = _verify_source_order_assembly(substituted_assembly_terms, substituted_dense)

    leading = scope_rows[0]
    complete_reduction = candidate_l1 - complete_l1
    complete_fraction = complete_reduction / max(candidate_l1, 1.0e-300)
    row46_before = float(candidate_residual[TARGET_FULL_ROW - 1])
    row46_after = float(complete_residual[TARGET_FULL_ROW - 1])
    source_row46_complete = reconstruction["all_ieee_exact"]
    normalization_captured = normalization["source_normalization_contract_exact"]
    residual_decomposition_complete = (
        math.isfinite(complete_l1)
        and math.isfinite(complete_linf)
        and replaced == TARGET_MATRIX_TERMS
        and removed_native_only == 4 * len(NATIVE_ONLY_ROW46_RECORDS)
    )
    audit_complete = (
        capture_verification["result"] == "ACCEPT"
        and len(captured_records) == TARGET_RECORDS
        and len(captured_terms) == TARGET_MATRIX_TERMS
        and term_comparison["unexpected_native_row46_terms"] == 0
        and source_row46_complete
        and normalization_captured
        and residual_decomposition_complete
    )

    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if audit_complete else "REJECT",
        "evaluation_ordinal": evaluation,
        "qualification_only": True,
        "capture_verification": capture_verification,
        "record_comparison": record_comparison,
        "term_comparison": term_comparison,
        "source_row46_reconstruction": reconstruction,
        "normalization_behavior": normalization,
        "source_order_assembly": {
            "native_candidate": candidate_assembly,
            "offline_original_dsec_row46": substituted_assembly,
        },
        "native_source_order_parity": term_comparison["relative_source_order_exact"],
        "native_absolute_source_order_parity": term_comparison["absolute_source_order_fully_exact"],
        "native_row46_record_inventory_parity": term_comparison["native_only_terms"] == 0,
        "residual_decomposition_complete": residual_decomposition_complete,
        "reference_population_residual": {
            "candidate_l1": candidate_l1,
            "candidate_linf": candidate_linf,
            "complete_row46_substitution_l1": complete_l1,
            "complete_row46_substitution_linf": complete_linf,
            "absolute_l1_reduction": complete_reduction,
            "fraction_l1_reduced": complete_fraction,
            "row46_before": row46_before,
            "row46_after": row46_after,
            "row46_absolute_reduction": abs(row46_before) - abs(row46_after),
            "terms_replaced": replaced,
            "native_only_terms_removed": removed_native_only,
        },
        "leading_row46_scope": leading,
        "data_type_scope_count": len(scope_rows),
        "captured_solve_rows": len(captured_solve_rows),
        "candidate_compact_rows": len(solve_rows),
        "single_record_correction_ready": False,
        "type76_correction_ready": False,
        "fixed_state_parity": False,
        "thermal_parity": False,
        "production_promotion_ready": False,
        "native_only_row46_contract": {
            "records": [
                {"source_position": source_position, "record": record}
                for source_position, record in sorted(NATIVE_ONLY_ROW46_RECORDS)
            ],
            "terms_removed": removed_native_only,
            "interpretation": "native compact self-loop absent from original v0.6.47.2 DSEC assembly",
        },
        "remaining_blockers": [
            "the runtime capture is restricted to evaluation 61",
            "native global and relative source-order parity differ from the original DSEC stream",
            "native type-95 record 1980 is a compact self-loop absent from the original DSEC assembly",
            "residual attribution does not by itself prove a source formula is wrong",
            "the complete arbitrary-state escape and population-dependent laws are not yet promoted",
            "fixed-state, thermal, controller, and product parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("lowered_program", type=Path)
    parser.add_argument("capture_bundle", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--evaluation", type=int, default=TARGET_EVALUATION)
    parser.add_argument("--radiation-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = audit(
            args.package_dir,
            args.lowered_program,
            args.capture_bundle,
            args.output_dir,
            evaluation=args.evaluation,
            radiation_csv=args.radiation_csv,
        )
    except Exception as exc:
        print(f"row-46 DSEC residual audit failed: {exc}")
        return 2
    if args.output_json:
        write_json(args.output_json, result)
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
