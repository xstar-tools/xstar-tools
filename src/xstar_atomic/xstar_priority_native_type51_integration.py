"""Integrate validated native type-51 terms into the priority compact solve.

This controlled diagnostic consumes two existing audit products:

* the v0.3.199 priority matrix-balance audit, which contains every compact
  matrix term touching the selected rows plus the captured XSTAR population
  vector; and
* the v0.3.203 native type-51 parity audit, which contains source-aligned
  native coefficients for all selected type-51 matrix insertions.

Every matching type-51 term is replaced by its native coefficient.  All other
rate families remain explicitly probe-backed.  The resulting hybrid system is
used to recompute captured-population row balance and the six-row conditional
solve.  This is an integration gate for the native type-51 assembler; it does
not enable the production expanded compact-basis solver or claim complete
native matrix/RHS closure.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np


TermKey = Tuple[int, int | None, str, int, int]
StructuralTermKey = Tuple[int, str, int, int]


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass"}


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if str(key) not in fields:
                fields.append(str(key))
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _resolve_product(path: str | Path, default_name: str) -> Path:
    root = Path(path)
    if root.is_file() and root.name == default_name:
        return root
    if root.is_dir():
        direct = root / default_name
        if direct.exists():
            return direct
        hits = sorted(root.rglob(default_name))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"could not find {default_name} under {root}")


def _load_summary(path: str | Path, default_name: str) -> Dict[str, Any]:
    try:
        json_path = _resolve_product(path, default_name)
    except FileNotFoundError:
        return {}
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        summary = payload.get("summary", payload)
        if isinstance(summary, dict):
            return dict(summary)
    return {}


def _term_key(row: Mapping[str, Any], *, record_field: str) -> TermKey | None:
    record = _as_int(row.get(record_field), None)
    row_ip = _as_int(row.get("compact_row_ipmat2"), None)
    col_ip = _as_int(row.get("compact_col_ipmat2"), None)
    if record is None or row_ip is None or col_ip is None:
        return None
    capture = _as_int(row.get("capture_index"), None)
    kind = str(row.get("insertion_kind") or "").strip()
    return (record, capture, kind, row_ip, col_ip)


def _structural_key(key: TermKey) -> StructuralTermKey:
    record, _capture, kind, row_ip, col_ip = key
    return (record, kind, row_ip, col_ip)


def _is_type51(row: Mapping[str, Any]) -> bool:
    family = str(row.get("family_key") or "").strip()
    return family == "type51_rate3" or (
        _as_int(row.get("ltyp"), None) == 51
        and _as_int(row.get("lrtyp"), None) == 3
    )


def _solve_selected_system(
    matrix: np.ndarray,
    rhs: np.ndarray,
    *,
    rank_rcond: float,
) -> Dict[str, Any]:
    n = int(matrix.shape[0])
    row_scales = np.max(np.abs(matrix), axis=1) if n else np.array([], dtype=float)
    row_scales[row_scales == 0.0] = 1.0
    scaled_matrix = matrix / row_scales[:, None] if n else matrix.copy()
    scaled_rhs = rhs / row_scales if n else rhs.copy()
    singular_values = np.linalg.svd(scaled_matrix, compute_uv=False) if n else np.array([], dtype=float)
    largest_sv = float(singular_values[0]) if singular_values.size else 0.0
    rank_threshold = rank_rcond * largest_sv
    rank = int(np.count_nonzero(singular_values > rank_threshold))
    condition_number = float(np.linalg.cond(scaled_matrix)) if n else math.inf
    if n and rank == n:
        solved = np.linalg.solve(scaled_matrix, scaled_rhs)
        method = "row_scaled_numpy_solve"
    elif n:
        solved, *_ = np.linalg.lstsq(scaled_matrix, scaled_rhs, rcond=rank_rcond)
        method = "row_scaled_numpy_lstsq"
    else:
        solved = np.array([], dtype=float)
        method = "empty_system"
    residual = matrix @ solved - rhs
    residual_scale = np.maximum(np.abs(matrix @ solved) + np.abs(rhs), 1.0e-300)
    relative_residual = np.abs(residual) / residual_scale
    return {
        "matrix": matrix,
        "rhs": rhs,
        "scaled_matrix": scaled_matrix,
        "scaled_rhs": scaled_rhs,
        "row_scales": row_scales,
        "singular_values": singular_values,
        "largest_singular_value": largest_sv,
        "rank_threshold": rank_threshold,
        "rank": rank,
        "condition_number": condition_number,
        "solve_method": method,
        "solution": solved,
        "residual": residual,
        "relative_residual": relative_residual,
    }


def build_priority_native_type51_integration_audit(
    *,
    priority_matrix_balance_audit: str | Path,
    type51_native_parity_audit: str | Path,
    relative_population_tolerance: float = 5.0e-3,
    replacement_population_delta_tolerance: float = 5.0e-5,
    relative_row_residual_tolerance: float = 5.0e-3,
    rank_rcond: float = 1.0e-12,
) -> Dict[str, Any]:
    """Replace all selected-system type-51 probe terms and re-solve.

    The replacement source is the native coefficient stored in the v0.3.203
    parity product.  A term is matched first by record, capture index,
    insertion kind, compact row, and compact column.  A unique structural
    match that omits capture index is allowed for compatibility with older
    matrix-balance products.
    """
    for name, value in (
        ("relative_population_tolerance", relative_population_tolerance),
        ("replacement_population_delta_tolerance", replacement_population_delta_tolerance),
        ("relative_row_residual_tolerance", relative_row_residual_tolerance),
        ("rank_rcond", rank_rcond),
    ):
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    balance_term_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_record_terms.csv",
    )
    population_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_population_vector.csv",
    )
    selected_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_row_balance.csv",
    )
    parity_term_path = _resolve_product(
        type51_native_parity_audit,
        "xstar_type51_native_parity_audit_matrix_terms.csv",
    )

    balance_terms = _read_csv(balance_term_path)
    population_rows = _read_csv(population_path)
    selected_rows = _read_csv(selected_path)
    parity_terms = _read_csv(parity_term_path)
    balance_summary = _load_summary(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit.json",
    )
    parity_summary = _load_summary(
        type51_native_parity_audit,
        "xstar_type51_native_parity_audit.json",
    )

    selected_indices = sorted({
        ip
        for ip in (_as_int(row.get("xstar_ipmat2_index"), None) for row in selected_rows)
        if ip is not None
    })
    if not selected_indices:
        raise ValueError("no selected compact rows found in matrix-balance audit")
    selected_set = set(selected_indices)
    position = {ip: idx for idx, ip in enumerate(selected_indices)}
    selected_meta = {
        int(ip): dict(row)
        for row in selected_rows
        if (ip := _as_int(row.get("xstar_ipmat2_index"), None)) is not None
    }
    population = {
        int(ip): _as_float(row.get("population"), 0.0)
        for row in population_rows
        if (ip := _as_int(row.get("xstar_ipmat2_index"), None)) is not None
    }

    parity_by_exact: Dict[TermKey, List[int]] = defaultdict(list)
    parity_by_structural: Dict[StructuralTermKey, List[int]] = defaultdict(list)
    valid_parity_indices: List[int] = []
    for index, row in enumerate(parity_terms):
        key = _term_key(row, record_field="record")
        if key is None:
            continue
        parity_by_exact[key].append(index)
        parity_by_structural[_structural_key(key)].append(index)
        valid_parity_indices.append(index)
    n_duplicate_exact_keys = sum(max(len(indices) - 1, 0) for indices in parity_by_exact.values())

    used_parity_indices: set[int] = set()
    unmatched_type51_keys: List[str] = []
    replacement_rows: List[Dict[str, Any]] = []
    n_type51_terms = 0
    n_type51_replaced = 0
    rows_touched_by_native_type51: set[int] = set()

    aggregate: Dict[Tuple[int, int], Dict[str, Any]] = {}
    row_abs_probe: Dict[int, float] = defaultdict(float)
    row_abs_hybrid: Dict[int, float] = defaultdict(float)
    family_acc: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(lambda: {
        "n_terms": 0,
        "n_native_terms": 0,
        "n_probe_backed_terms": 0,
        "probe_absolute_population_weighted_sum": 0.0,
        "hybrid_absolute_population_weighted_sum": 0.0,
        "probe_population_weighted_net": 0.0,
        "hybrid_population_weighted_net": 0.0,
    })

    for raw in balance_terms:
        row_ip = _as_int(raw.get("compact_row_ipmat2"), None)
        col_ip = _as_int(raw.get("compact_col_ipmat2"), None)
        if row_ip is None or col_ip is None or row_ip not in selected_set:
            continue
        probe_coeff = _as_float(raw.get("ajisi_1_s^-1"), 0.0)
        hybrid_coeff = probe_coeff
        match_method = "not_applicable"
        parity_row: Mapping[str, Any] | None = None
        provenance = "fortran_probe_non_type51"
        type51 = _is_type51(raw)
        if type51:
            n_type51_terms += 1
            key = _term_key(raw, record_field="ml_data")
            matched_index: int | None = None
            if key is not None:
                exact_candidates = [idx for idx in parity_by_exact.get(key, []) if idx not in used_parity_indices]
                if len(exact_candidates) == 1:
                    matched_index = exact_candidates[0]
                    match_method = "exact_capture_key"
                elif len(exact_candidates) > 1:
                    match_method = "ambiguous_exact_capture_key"
                else:
                    structural_candidates = [
                        idx for idx in parity_by_structural.get(_structural_key(key), [])
                        if idx not in used_parity_indices
                    ]
                    if len(structural_candidates) == 1:
                        matched_index = structural_candidates[0]
                        match_method = "unique_structural_key"
                    elif len(structural_candidates) > 1:
                        match_method = "ambiguous_structural_key"
                    else:
                        match_method = "no_native_match"
            else:
                match_method = "invalid_balance_term_key"
            if matched_index is not None:
                candidate = parity_terms[matched_index]
                native_raw = candidate.get("native_expected_ajisi_1_s^-1")
                try:
                    native_value = float(native_raw)
                    native_value_valid = math.isfinite(native_value)
                except Exception:
                    native_value = probe_coeff
                    native_value_valid = False
                parity_term_valid = bool(
                    native_value_valid
                    and _as_bool(candidate.get("matrix_term_match"))
                    and _as_bool(candidate.get("record_parity_status"))
                )
                if parity_term_valid:
                    parity_row = candidate
                    used_parity_indices.add(matched_index)
                    hybrid_coeff = native_value
                    provenance = "native_type51_v03203"
                    n_type51_replaced += 1
                    rows_touched_by_native_type51.add(int(row_ip))
                else:
                    parity_row = candidate
                    match_method = f"{match_method}_invalid_parity_term"
                    matched_index = None
            if matched_index is None:
                if key is not None:
                    unmatched_type51_keys.append("|".join("" if v is None else str(v) for v in key))
                provenance = "fortran_probe_unmatched_type51"

        xcol = population.get(int(col_ip))
        if xcol is None:
            xcol = 0.0
        probe_contribution = probe_coeff * xcol
        hybrid_contribution = hybrid_coeff * xcol
        row_abs_probe[int(row_ip)] += abs(probe_contribution)
        row_abs_hybrid[int(row_ip)] += abs(hybrid_contribution)

        family = str(raw.get("family_key") or f"type{_as_int(raw.get('ltyp'), 0)}_rate{_as_int(raw.get('lrtyp'), 0)}")
        partition = "selected_internal" if int(col_ip) in selected_set else "fixed_external"
        fam = family_acc[(partition, family)]
        fam["n_terms"] += 1
        if provenance == "native_type51_v03203":
            fam["n_native_terms"] += 1
        else:
            fam["n_probe_backed_terms"] += 1
        fam["probe_absolute_population_weighted_sum"] += abs(probe_contribution)
        fam["hybrid_absolute_population_weighted_sum"] += abs(hybrid_contribution)
        fam["probe_population_weighted_net"] += probe_contribution
        fam["hybrid_population_weighted_net"] += hybrid_contribution

        aggregate_key = (int(row_ip), int(col_ip))
        if aggregate_key not in aggregate:
            aggregate[aggregate_key] = {
                "compact_row_ipmat2": int(row_ip),
                "compact_col_ipmat2": int(col_ip),
                "partition": partition,
                "column_population": xcol,
                "n_record_terms": 0,
                "n_native_type51_terms": 0,
                "n_probe_backed_terms": 0,
                "probe_coefficient_sum_s^-1": 0.0,
                "hybrid_coefficient_sum_s^-1": 0.0,
                "probe_population_weighted_contribution": 0.0,
                "hybrid_population_weighted_contribution": 0.0,
            }
        entry = aggregate[aggregate_key]
        entry["n_record_terms"] += 1
        if provenance == "native_type51_v03203":
            entry["n_native_type51_terms"] += 1
        else:
            entry["n_probe_backed_terms"] += 1
        entry["probe_coefficient_sum_s^-1"] += probe_coeff
        entry["hybrid_coefficient_sum_s^-1"] += hybrid_coeff
        entry["probe_population_weighted_contribution"] += probe_contribution
        entry["hybrid_population_weighted_contribution"] += hybrid_contribution

        replacement_rows.append({
            "capture_index": raw.get("capture_index", ""),
            "record": raw.get("ml_data", ""),
            "ltyp": raw.get("ltyp", ""),
            "lrtyp": raw.get("lrtyp", ""),
            "family_key": family,
            "insertion_kind": raw.get("insertion_kind", ""),
            "compact_row_ipmat2": int(row_ip),
            "compact_col_ipmat2": int(col_ip),
            "partition": partition,
            "coefficient_provenance": provenance,
            "native_match_method": match_method,
            "probe_coefficient_s^-1": probe_coeff,
            "hybrid_coefficient_s^-1": hybrid_coeff,
            "coefficient_relative_change": _relative_difference(hybrid_coeff, probe_coeff),
            "column_population": xcol,
            "probe_population_weighted_contribution": probe_contribution,
            "hybrid_population_weighted_contribution": hybrid_contribution,
            "population_weighted_contribution_change": hybrid_contribution - probe_contribution,
            "parity_matrix_term_match": parity_row.get("matrix_term_match", "") if parity_row else "",
            "parity_record_status": parity_row.get("record_parity_status", "") if parity_row else "",
            "parity_relative_difference": parity_row.get("relative_difference", "") if parity_row else "",
        })

    aggregate_rows = sorted(aggregate.values(), key=lambda row: (
        int(row["compact_row_ipmat2"]), int(row["compact_col_ipmat2"])
    ))

    n = len(selected_indices)
    probe_matrix = np.zeros((n, n), dtype=float)
    hybrid_matrix = np.zeros((n, n), dtype=float)
    probe_rhs = np.zeros(n, dtype=float)
    hybrid_rhs = np.zeros(n, dtype=float)
    missing_population_columns: set[int] = set()
    for entry in aggregate_rows:
        row_ip = int(entry["compact_row_ipmat2"])
        col_ip = int(entry["compact_col_ipmat2"])
        i = position[row_ip]
        if col_ip not in population:
            missing_population_columns.add(col_ip)
        xcol = population.get(col_ip, 0.0)
        probe_coeff = float(entry["probe_coefficient_sum_s^-1"])
        hybrid_coeff = float(entry["hybrid_coefficient_sum_s^-1"])
        if col_ip in position:
            j = position[col_ip]
            probe_matrix[i, j] += probe_coeff
            hybrid_matrix[i, j] += hybrid_coeff
        else:
            probe_rhs[i] -= probe_coeff * xcol
            hybrid_rhs[i] -= hybrid_coeff * xcol

    captured = np.array([population.get(ip, 0.0) for ip in selected_indices], dtype=float)
    probe_solve = _solve_selected_system(probe_matrix, probe_rhs, rank_rcond=rank_rcond)
    hybrid_solve = _solve_selected_system(hybrid_matrix, hybrid_rhs, rank_rcond=rank_rcond)
    probe_solution = np.asarray(probe_solve["solution"], dtype=float)
    hybrid_solution = np.asarray(hybrid_solve["solution"], dtype=float)

    captured_probe_residual = probe_matrix @ captured - probe_rhs
    captured_hybrid_residual = hybrid_matrix @ captured - hybrid_rhs
    row_balance_rows: List[Dict[str, Any]] = []
    solve_rows: List[Dict[str, Any]] = []
    rhs_rows: List[Dict[str, Any]] = []
    n_rows_hybrid_balance_pass = 0
    n_rows_population_pass = 0
    n_rows_replacement_delta_pass = 0
    max_hybrid_row_residual = 0.0
    max_hybrid_population_difference = 0.0
    max_replacement_population_delta = 0.0

    for idx, ip in enumerate(selected_indices):
        probe_rel_row = abs(float(captured_probe_residual[idx])) / max(row_abs_probe.get(ip, 0.0), 1.0e-300)
        hybrid_rel_row = abs(float(captured_hybrid_residual[idx])) / max(row_abs_hybrid.get(ip, 0.0), 1.0e-300)
        max_hybrid_row_residual = max(max_hybrid_row_residual, hybrid_rel_row)
        row_status = "pass" if hybrid_rel_row <= relative_row_residual_tolerance else "differs"
        if row_status == "pass":
            n_rows_hybrid_balance_pass += 1
        meta = selected_meta.get(ip, {})
        row_balance_rows.append({
            "xstar_ipmat2_index": ip,
            "physical_roles": meta.get("physical_roles", ""),
            "captured_population": float(captured[idx]),
            "probe_row_residual": float(captured_probe_residual[idx]),
            "probe_relative_row_residual": probe_rel_row,
            "hybrid_row_residual": float(captured_hybrid_residual[idx]),
            "hybrid_relative_row_residual": hybrid_rel_row,
            "relative_row_residual_tolerance": relative_row_residual_tolerance,
            "hybrid_row_balance_status": row_status,
            "row_touched_by_native_type51": ip in rows_touched_by_native_type51,
        })

        cap = float(captured[idx])
        probe_value = float(probe_solution[idx])
        hybrid_value = float(hybrid_solution[idx])
        hybrid_cap_rel = _relative_difference(hybrid_value, cap)
        hybrid_probe_rel = _relative_difference(hybrid_value, probe_value)
        max_hybrid_population_difference = max(max_hybrid_population_difference, hybrid_cap_rel)
        max_replacement_population_delta = max(max_replacement_population_delta, hybrid_probe_rel)
        pop_status = "pass" if hybrid_cap_rel <= relative_population_tolerance else "differs"
        delta_status = "pass" if hybrid_probe_rel <= replacement_population_delta_tolerance else "differs"
        if pop_status == "pass":
            n_rows_population_pass += 1
        if delta_status == "pass":
            n_rows_replacement_delta_pass += 1
        solve_rows.append({
            "xstar_ipmat2_index": ip,
            "physical_roles": meta.get("physical_roles", ""),
            "captured_xstar_population": cap,
            "all_probe_conditional_population": probe_value,
            "hybrid_native_type51_conditional_population": hybrid_value,
            "hybrid_minus_captured": hybrid_value - cap,
            "hybrid_vs_captured_relative_difference": hybrid_cap_rel,
            "relative_population_tolerance": relative_population_tolerance,
            "hybrid_population_match_status": pop_status,
            "hybrid_minus_all_probe": hybrid_value - probe_value,
            "hybrid_vs_all_probe_relative_difference": hybrid_probe_rel,
            "replacement_population_delta_tolerance": replacement_population_delta_tolerance,
            "replacement_population_delta_status": delta_status,
            "hybrid_linear_solve_residual": float(hybrid_solve["residual"][idx]),
            "hybrid_linear_solve_relative_residual": float(hybrid_solve["relative_residual"][idx]),
        })
        rhs_rows.append({
            "xstar_ipmat2_index": ip,
            "physical_roles": meta.get("physical_roles", ""),
            "probe_external_rhs": float(probe_rhs[idx]),
            "hybrid_external_rhs": float(hybrid_rhs[idx]),
            "hybrid_minus_probe_external_rhs": float(hybrid_rhs[idx] - probe_rhs[idx]),
            "external_rhs_relative_change": _relative_difference(float(hybrid_rhs[idx]), float(probe_rhs[idx])),
        })

    family_rows: List[Dict[str, Any]] = []
    for (partition, family), values in family_acc.items():
        status = "native_type51" if family == "type51_rate3" and values["n_probe_backed_terms"] == 0 else "probe_backed"
        family_rows.append({
            "partition": partition,
            "family_key": family,
            "assembly_status": status,
            **values,
        })
    family_rows.sort(key=lambda row: (
        str(row["partition"]),
        -float(row["hybrid_absolute_population_weighted_sum"]),
        str(row["family_key"]),
    ))

    singular_value_rows = []
    largest_sv = float(hybrid_solve["largest_singular_value"])
    for index, value in enumerate(np.asarray(hybrid_solve["singular_values"]), start=1):
        singular_value_rows.append({
            "singular_value_rank": index,
            "singular_value": float(value),
            "relative_to_largest": float(value / largest_sv) if largest_sv > 0.0 else 0.0,
            "rank_threshold": float(hybrid_solve["rank_threshold"]),
            "counted_in_rank": bool(value > hybrid_solve["rank_threshold"]),
        })

    unused_parity_indices = sorted(set(valid_parity_indices) - used_parity_indices)
    parity_ready = bool(
        _as_bool(parity_summary.get("native_type51_record_rate_parity_ready"))
        and _as_bool(parity_summary.get("native_type51_compact_matrix_parity_ready"))
        and _as_bool(parity_summary.get("native_type51_internal_block_assembly_ready"))
    )
    replacement_complete = bool(
        n_type51_terms > 0
        and n_type51_replaced == n_type51_terms
        and not unmatched_type51_keys
        and not unused_parity_indices
        and n_duplicate_exact_keys == 0
    )
    all_selected_rows_touched = rows_touched_by_native_type51 == selected_set
    max_hybrid_linear_residual = (
        float(np.max(np.abs(hybrid_solve["relative_residual"]))) if n else math.inf
    )
    n_negative = int(np.count_nonzero(hybrid_solution < 0.0))
    parent_ready = _as_bool(balance_summary.get("fortran_priority_subset_row_balance_ready"))
    integration_ready = bool(
        parent_ready
        and parity_ready
        and replacement_complete
        and all_selected_rows_touched
        and not missing_population_columns
        and hybrid_solve["rank"] == n
        and n_negative == 0
        and n_rows_hybrid_balance_pass == n
        and n_rows_population_pass == n
        and n_rows_replacement_delta_pass == n
        and max_hybrid_linear_residual <= 1.0e-10
    )

    summary = {
        "audit_version": "v0.3.204",
        "status": "priority_native_type51_integration_completed",
        "ion": balance_summary.get("ion", parity_summary.get("ion", "")),
        "selected_basis_solve_call_id": balance_summary.get(
            "selected_basis_solve_call_id", parity_summary.get("selected_basis_solve_call_id", "")
        ),
        "selection": balance_summary.get("selection", parity_summary.get("selection", "")),
        "occurrence_rank": balance_summary.get("occurrence_rank", parity_summary.get("occurrence_rank", "")),
        "population_stage": balance_summary.get("population_stage", "after"),
        "n_population_rows": len(population),
        "n_selected_compact_rows": n,
        "selected_xstar_ipmat2_indices": ";".join(str(ip) for ip in selected_indices),
        "n_balance_record_terms": len(replacement_rows),
        "n_type51_balance_terms": n_type51_terms,
        "n_type51_terms_replaced_with_native": n_type51_replaced,
        "n_type51_terms_unmatched": n_type51_terms - n_type51_replaced,
        "n_non_type51_probe_backed_terms": len(replacement_rows) - n_type51_terms,
        "n_type51_parity_terms": len(valid_parity_indices),
        "n_type51_parity_terms_used": len(used_parity_indices),
        "n_type51_parity_terms_unused": len(unused_parity_indices),
        "n_duplicate_type51_parity_exact_keys": n_duplicate_exact_keys,
        "n_selected_rows_touched_by_native_type51": len(rows_touched_by_native_type51),
        "n_selected_rows_not_touched_by_native_type51": len(selected_set - rows_touched_by_native_type51),
        "n_missing_population_columns": len(missing_population_columns),
        "missing_population_columns": ";".join(str(v) for v in sorted(missing_population_columns)),
        "probe_matrix_rank": int(probe_solve["rank"]),
        "hybrid_matrix_rank": int(hybrid_solve["rank"]),
        "matrix_dimension": n,
        "hybrid_scaled_matrix_condition_number": float(hybrid_solve["condition_number"]),
        "hybrid_solve_method": str(hybrid_solve["solve_method"]),
        "n_negative_hybrid_solution_rows": n_negative,
        "relative_row_residual_tolerance": relative_row_residual_tolerance,
        "n_hybrid_rows_passing_captured_balance": n_rows_hybrid_balance_pass,
        "n_hybrid_rows_not_passing_captured_balance": n - n_rows_hybrid_balance_pass,
        "max_abs_hybrid_captured_relative_row_residual": max_hybrid_row_residual,
        "relative_population_tolerance": relative_population_tolerance,
        "n_hybrid_rows_within_population_tolerance": n_rows_population_pass,
        "n_hybrid_rows_outside_population_tolerance": n - n_rows_population_pass,
        "max_abs_hybrid_vs_captured_relative_population_difference": max_hybrid_population_difference,
        "replacement_population_delta_tolerance": replacement_population_delta_tolerance,
        "n_hybrid_rows_within_replacement_delta_tolerance": n_rows_replacement_delta_pass,
        "n_hybrid_rows_outside_replacement_delta_tolerance": n - n_rows_replacement_delta_pass,
        "max_abs_hybrid_vs_all_probe_relative_population_difference": max_replacement_population_delta,
        "max_abs_hybrid_linear_solve_relative_residual": max_hybrid_linear_residual,
        "parent_fortran_priority_subset_row_balance_ready": parent_ready,
        "parent_native_type51_parity_ready": parity_ready,
        "native_type51_all_touching_terms_replaced": replacement_complete,
        "native_type51_all_selected_rows_touched": all_selected_rows_touched,
        "native_type51_selected_system_integration_ready": integration_ready,
        "hybrid_selected_system_contains_probe_backed_non_type51_terms": (
            len(replacement_rows) - n_type51_terms > 0
        ),
        "native_priority_subset_matrix_closure_ready": False,
        "production_expanded_compact_solver_changed": False,
        "dominant_next_target": (
            "integrate_native_type50_and_type71_external_rhs_then_exact_live_radiation_type53"
            if integration_ready else
            "resolve_type51_replacement_coverage_row_balance_or_conditional_solve_mismatch"
        ),
        "type53_scale44_status": "unresolved_no_empirical_factor_applied",
        "priority_matrix_balance_record_terms_csv": str(balance_term_path),
        "priority_matrix_balance_population_vector_csv": str(population_path),
        "type51_native_parity_matrix_terms_csv": str(parity_term_path),
    }

    return {
        "summary": summary,
        "term_replacement_rows": replacement_rows,
        "aggregated_matrix_rows": aggregate_rows,
        "row_balance_rows": row_balance_rows,
        "solve_comparison_rows": solve_rows,
        "external_rhs_rows": rhs_rows,
        "family_status_rows": family_rows,
        "singular_value_rows": singular_value_rows,
        "unmatched_type51_term_keys": unmatched_type51_keys,
        "unused_type51_parity_term_indices": unused_parity_indices,
        "hybrid_scaled_selected_matrix": np.asarray(hybrid_solve["scaled_matrix"]).tolist(),
        "hybrid_scaled_rhs": np.asarray(hybrid_solve["scaled_rhs"]).tolist(),
    }


def write_priority_native_type51_integration_audit(
    out_dir: str | Path,
    audit: Mapping[str, Any],
) -> Dict[str, Path]:
    """Write CSV, JSON, and Markdown products for the integration audit."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_priority_native_type51_integration_audit"
    paths = {
        "term_replacements_csv": out / f"{prefix}_term_replacements.csv",
        "aggregated_matrix_entries_csv": out / f"{prefix}_aggregated_matrix_entries.csv",
        "row_balance_csv": out / f"{prefix}_row_balance.csv",
        "solve_comparison_csv": out / f"{prefix}_solve_comparison.csv",
        "external_rhs_csv": out / f"{prefix}_external_rhs.csv",
        "family_status_csv": out / f"{prefix}_family_status.csv",
        "singular_values_csv": out / f"{prefix}_singular_values.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["term_replacements_csv"], audit.get("term_replacement_rows", []))
    _write_csv(paths["aggregated_matrix_entries_csv"], audit.get("aggregated_matrix_rows", []))
    _write_csv(paths["row_balance_csv"], audit.get("row_balance_rows", []))
    _write_csv(paths["solve_comparison_csv"], audit.get("solve_comparison_rows", []))
    _write_csv(paths["external_rhs_csv"], audit.get("external_rhs_rows", []))
    _write_csv(paths["family_status_csv"], audit.get("family_status_rows", []))
    _write_csv(paths["singular_values_csv"], audit.get("singular_value_rows", []))
    paths["json"].write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")

    summary = audit.get("summary", {})
    lines = [
        "# XSTAR priority native type-51 integration audit",
        "",
        f"- audit version: `{summary.get('audit_version')}`",
        f"- ion: `{summary.get('ion')}`",
        f"- selected compact rows: `{summary.get('selected_xstar_ipmat2_indices')}`",
        f"- native type-51 terms replaced: `{summary.get('n_type51_terms_replaced_with_native')}/{summary.get('n_type51_balance_terms')}`",
        f"- native type-51 parity terms used: `{summary.get('n_type51_parity_terms_used')}/{summary.get('n_type51_parity_terms')}`",
        f"- selected rows touched: `{summary.get('n_selected_rows_touched_by_native_type51')}/{summary.get('n_selected_compact_rows')}`",
        f"- hybrid matrix rank: `{summary.get('hybrid_matrix_rank')}/{summary.get('matrix_dimension')}`",
        f"- hybrid scaled condition number: `{summary.get('hybrid_scaled_matrix_condition_number')}`",
        f"- maximum hybrid/captured population difference: `{summary.get('max_abs_hybrid_vs_captured_relative_population_difference')}`",
        f"- maximum hybrid/all-probe population change: `{summary.get('max_abs_hybrid_vs_all_probe_relative_population_difference')}`",
        f"- native type-51 selected-system integration ready: `{summary.get('native_type51_selected_system_integration_ready')}`",
        f"- complete native compact closure ready: `{summary.get('native_priority_subset_matrix_closure_ready')}`",
        "",
        "All matching type-51 coefficients are native values from the v0.3.203 parity product. Non-type-51 families remain explicitly probe-backed. The production expanded compact-basis solver is unchanged.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
