"""Conditionally solve the activated priority compact XSTAR rows.

This diagnostic consumes the v0.3.199 priority matrix-balance products.  The
selected compact rows are treated as the unknown block ``S`` and every other
XSTAR compact population row is held fixed at the captured post-``msolvelucy``
value.  The selected equations are partitioned as

``A_SS x_S + A_SE x_E = 0``

and solved as

``A_SS x_S = -A_SE x_E``.

This is a controlled validation of compact-matrix assembly and external
source/sink closure.  It is not yet the native Python expanded-basis solver:
the matrix coefficients and fixed external populations still come from XSTAR
probe products.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import numpy as np


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


def _load_summary(root: str | Path) -> Dict[str, Any]:
    try:
        path = _resolve_product(root, "xstar_priority_matrix_balance_audit.json")
    except FileNotFoundError:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        summary = payload.get("summary", payload)
        if isinstance(summary, dict):
            return dict(summary)
    return {}


def build_priority_conditional_solve_audit(
    *,
    priority_matrix_balance_audit: str | Path,
    relative_population_tolerance: float = 5.0e-3,
    rank_rcond: float = 1.0e-12,
) -> Dict[str, Any]:
    """Solve the selected compact rows with all external XSTAR rows fixed."""
    if relative_population_tolerance <= 0.0:
        raise ValueError("relative_population_tolerance must be positive")
    if rank_rcond <= 0.0:
        raise ValueError("rank_rcond must be positive")

    agg_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_aggregated_matrix_entries.csv",
    )
    pop_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_population_vector.csv",
    )
    row_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_row_balance.csv",
    )
    term_path = _resolve_product(
        priority_matrix_balance_audit,
        "xstar_priority_matrix_balance_audit_record_terms.csv",
    )

    aggregated = _read_csv(agg_path)
    population_rows_raw = _read_csv(pop_path)
    selected_rows_raw = _read_csv(row_path)
    record_terms = _read_csv(term_path)
    parent_summary = _load_summary(priority_matrix_balance_audit)

    selected_indices = sorted({
        ip
        for ip in (_as_int(row.get("xstar_ipmat2_index"), None) for row in selected_rows_raw)
        if ip is not None
    })
    if not selected_indices:
        raise ValueError("no selected compact rows found in row-balance audit")
    position = {ip: i for i, ip in enumerate(selected_indices)}
    selected_meta = {
        _as_int(row.get("xstar_ipmat2_index"), -1): dict(row)
        for row in selected_rows_raw
        if _as_int(row.get("xstar_ipmat2_index"), None) is not None
    }
    population = {
        int(ip): _as_float(row.get("population"), 0.0)
        for row in population_rows_raw
        if (ip := _as_int(row.get("xstar_ipmat2_index"), None)) is not None
    }

    n = len(selected_indices)
    matrix = np.zeros((n, n), dtype=float)
    rhs = np.zeros(n, dtype=float)
    external_weighted = np.zeros(n, dtype=float)
    internal_captured = np.zeros(n, dtype=float)
    missing_population_columns: set[int] = set()
    n_internal_entries = 0
    n_external_entries = 0

    matrix_entry_rows: List[Dict[str, Any]] = []
    rhs_rows_by_ip: Dict[int, Dict[str, Any]] = {}

    for raw in aggregated:
        row_ip = _as_int(raw.get("compact_row_ipmat2"), None)
        col_ip = _as_int(raw.get("compact_col_ipmat2"), None)
        if row_ip not in position or col_ip is None:
            continue
        coeff = _as_float(raw.get("coefficient_sum_s^-1"), 0.0)
        i = position[int(row_ip)]
        xcol = population.get(int(col_ip))
        if xcol is None:
            missing_population_columns.add(int(col_ip))
            xcol = 0.0
        captured_contribution = coeff * xcol
        if int(col_ip) in position:
            j = position[int(col_ip)]
            matrix[i, j] += coeff
            internal_captured[i] += captured_contribution
            partition = "selected_internal"
            n_internal_entries += 1
        else:
            external_weighted[i] += captured_contribution
            rhs[i] -= captured_contribution
            partition = "fixed_external"
            n_external_entries += 1
        matrix_entry_rows.append({
            "compact_row_ipmat2": int(row_ip),
            "compact_col_ipmat2": int(col_ip),
            "partition": partition,
            "coefficient_sum_s^-1": coeff,
            "captured_column_population": xcol,
            "captured_population_weighted_contribution": captured_contribution,
            "n_record_terms": raw.get("n_record_terms", ""),
        })

    captured = np.array([population.get(ip, 0.0) for ip in selected_indices], dtype=float)
    row_scales = np.max(np.abs(matrix), axis=1)
    row_scales[row_scales == 0.0] = 1.0
    scaled_matrix = matrix / row_scales[:, None]
    scaled_rhs = rhs / row_scales

    singular_values = np.linalg.svd(scaled_matrix, compute_uv=False)
    largest_sv = float(singular_values[0]) if singular_values.size else 0.0
    rank_threshold = rank_rcond * largest_sv
    matrix_rank = int(np.count_nonzero(singular_values > rank_threshold))
    condition_number = float(np.linalg.cond(scaled_matrix)) if n else math.inf

    if matrix_rank == n:
        solved = np.linalg.solve(scaled_matrix, scaled_rhs)
        solve_method = "row_scaled_numpy_solve"
    else:
        solved, *_ = np.linalg.lstsq(scaled_matrix, scaled_rhs, rcond=rank_rcond)
        solve_method = "row_scaled_numpy_lstsq"

    linear_residual = matrix @ solved - rhs
    captured_residual = matrix @ captured - rhs
    residual_scale = np.maximum(np.abs(matrix @ solved) + np.abs(rhs), 1.0e-300)
    relative_linear_residual = np.abs(linear_residual) / residual_scale

    comparison_rows: List[Dict[str, Any]] = []
    n_within = 0
    max_rel_diff = 0.0
    for idx, ip in enumerate(selected_indices):
        cap = float(captured[idx])
        sol = float(solved[idx])
        diff = sol - cap
        denom = max(abs(cap), abs(sol), 1.0e-300)
        rel = abs(diff) / denom
        max_rel_diff = max(max_rel_diff, rel)
        status = "pass" if rel <= relative_population_tolerance else "differs"
        if status == "pass":
            n_within += 1
        meta = selected_meta.get(ip, {})
        comparison_rows.append({
            "xstar_ipmat2_index": ip,
            "activation_order": meta.get("activation_order", ""),
            "physical_roles": meta.get("physical_roles", ""),
            "captured_xstar_population": cap,
            "conditional_solved_population": sol,
            "population_difference": diff,
            "absolute_population_difference": abs(diff),
            "relative_population_difference": rel,
            "relative_population_tolerance": relative_population_tolerance,
            "population_match_status": status,
            "captured_row_residual": float(captured_residual[idx]),
            "conditional_solve_row_residual": float(linear_residual[idx]),
            "conditional_solve_relative_row_residual": float(relative_linear_residual[idx]),
            "external_population_weighted_sum": float(external_weighted[idx]),
            "conditional_rhs": float(rhs[idx]),
        })
        rhs_rows_by_ip[ip] = {
            "xstar_ipmat2_index": ip,
            "physical_roles": meta.get("physical_roles", ""),
            "captured_internal_population_weighted_sum": float(internal_captured[idx]),
            "captured_external_population_weighted_sum": float(external_weighted[idx]),
            "conditional_rhs": float(rhs[idx]),
            "captured_total_row_residual": float(captured_residual[idx]),
            "conditional_solved_total_row_residual": float(linear_residual[idx]),
        }

    # Decompose the fixed-external RHS by rate family from the record-level terms.
    family_acc: Dict[tuple[int, str], Dict[str, Any]] = defaultdict(lambda: {
        "n_record_terms": 0,
        "external_population_weighted_sum": 0.0,
        "conditional_rhs_contribution": 0.0,
        "absolute_rhs_contribution_sum": 0.0,
    })
    selected_set = set(selected_indices)
    for raw in record_terms:
        row_ip = _as_int(raw.get("compact_row_ipmat2"), None)
        col_ip = _as_int(raw.get("compact_col_ipmat2"), None)
        if row_ip not in selected_set or col_ip is None or col_ip in selected_set:
            continue
        family = str(raw.get("family_key", "unknown"))
        contribution = _as_float(raw.get("population_weighted_contribution"), 0.0)
        target = family_acc[(int(row_ip), family)]
        target["n_record_terms"] += 1
        target["external_population_weighted_sum"] += contribution
        target["conditional_rhs_contribution"] -= contribution
        target["absolute_rhs_contribution_sum"] += abs(contribution)
    family_rows = [
        {"xstar_ipmat2_index": ip, "family_key": family, **values}
        for (ip, family), values in family_acc.items()
    ]
    family_rows.sort(key=lambda row: (
        int(row["xstar_ipmat2_index"]),
        -abs(float(row["conditional_rhs_contribution"])),
    ))

    singular_value_rows = [
        {
            "singular_value_rank": idx + 1,
            "singular_value": float(value),
            "relative_to_largest": float(value / largest_sv) if largest_sv > 0.0 else 0.0,
            "rank_threshold": rank_threshold,
            "counted_in_rank": bool(value > rank_threshold),
        }
        for idx, value in enumerate(singular_values)
    ]

    captured_sum = float(np.sum(captured))
    solved_sum = float(np.sum(solved))
    sum_rel_diff = abs(solved_sum - captured_sum) / max(abs(captured_sum), abs(solved_sum), 1.0e-300)
    l1_relative = float(np.sum(np.abs(solved - captured)) / max(np.sum(np.abs(captured)), 1.0e-300))
    l2_relative = float(np.linalg.norm(solved - captured) / max(np.linalg.norm(captured), 1.0e-300))
    max_linear_residual = float(np.max(np.abs(relative_linear_residual))) if n else math.inf
    n_negative = int(np.count_nonzero(solved < 0.0))

    parent_ready = bool(parent_summary.get("fortran_priority_subset_row_balance_ready"))
    ready = bool(
        parent_ready
        and not missing_population_columns
        and matrix_rank == n
        and n_negative == 0
        and n_within == n
        and max_linear_residual <= 1.0e-10
    )

    summary = {
        "audit_version": "v0.3.201",
        "status": "priority_conditional_compact_solve_completed",
        "ion": parent_summary.get("ion", ""),
        "selected_basis_solve_call_id": parent_summary.get("selected_basis_solve_call_id", ""),
        "selection": parent_summary.get("selection", ""),
        "occurrence_rank": parent_summary.get("occurrence_rank", ""),
        "population_stage": parent_summary.get("population_stage", "after"),
        "n_population_rows": len(population),
        "n_selected_compact_rows": n,
        "selected_xstar_ipmat2_indices": ";".join(str(ip) for ip in selected_indices),
        "n_fixed_external_population_rows": max(len(population) - n, 0),
        "n_internal_aggregated_matrix_entries": n_internal_entries,
        "n_external_aggregated_matrix_entries": n_external_entries,
        "n_missing_population_columns": len(missing_population_columns),
        "matrix_rank": matrix_rank,
        "matrix_dimension": n,
        "scaled_matrix_condition_number": condition_number,
        "rank_rcond": rank_rcond,
        "solve_method": solve_method,
        "n_negative_solution_rows": n_negative,
        "captured_selected_population_sum": captured_sum,
        "conditional_solved_population_sum": solved_sum,
        "selected_population_sum_relative_difference": sum_rel_diff,
        "max_abs_population_difference": float(np.max(np.abs(solved - captured))) if n else math.inf,
        "max_abs_relative_population_difference": max_rel_diff,
        "l1_relative_population_difference": l1_relative,
        "l2_relative_population_difference": l2_relative,
        "relative_population_tolerance": relative_population_tolerance,
        "n_selected_rows_within_population_tolerance": n_within,
        "n_selected_rows_outside_population_tolerance": n - n_within,
        "max_abs_conditional_linear_solve_relative_residual": max_linear_residual,
        "fortran_priority_subset_row_balance_ready": parent_ready,
        "fortran_priority_subset_conditional_solve_ready": ready,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": (
            "replace_fortran_probed_coefficients_with_native_rate_assembly_then_expand_to_119_row_conditional_solve"
            if ready else
            "resolve_conditional_subset_rank_population_or_residual_mismatch"
        ),
        "aggregated_matrix_entries_csv": str(agg_path),
        "population_vector_csv": str(pop_path),
        "row_balance_csv": str(row_path),
        "record_terms_csv": str(term_path),
    }

    return {
        "summary": summary,
        "solve_comparison_rows": comparison_rows,
        "selected_matrix_entry_rows": matrix_entry_rows,
        "external_rhs_rows": [rhs_rows_by_ip[ip] for ip in selected_indices],
        "external_rhs_family_rows": family_rows,
        "singular_value_rows": singular_value_rows,
        "scaled_selected_matrix": scaled_matrix.tolist(),
        "scaled_rhs": scaled_rhs.tolist(),
    }


def write_priority_conditional_solve_audit(
    out_dir: str | Path,
    audit: Mapping[str, Any],
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_priority_conditional_solve_audit"
    paths = {
        "solve_comparison_csv": out / f"{prefix}_solve_comparison.csv",
        "selected_matrix_entries_csv": out / f"{prefix}_selected_matrix_entries.csv",
        "external_rhs_csv": out / f"{prefix}_external_rhs.csv",
        "external_rhs_family_csv": out / f"{prefix}_external_rhs_family_contributions.csv",
        "singular_values_csv": out / f"{prefix}_singular_values.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["solve_comparison_csv"], audit.get("solve_comparison_rows", []))
    _write_csv(paths["selected_matrix_entries_csv"], audit.get("selected_matrix_entry_rows", []))
    _write_csv(paths["external_rhs_csv"], audit.get("external_rhs_rows", []))
    _write_csv(paths["external_rhs_family_csv"], audit.get("external_rhs_family_rows", []))
    _write_csv(paths["singular_values_csv"], audit.get("singular_value_rows", []))
    paths["json"].write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")

    summary = audit.get("summary", {})
    lines = [
        "# XSTAR priority conditional compact solve audit",
        "",
        f"- audit version: `{summary.get('audit_version')}`",
        f"- ion: `{summary.get('ion')}`",
        f"- selected compact rows: `{summary.get('selected_xstar_ipmat2_indices')}`",
        f"- matrix rank: `{summary.get('matrix_rank')}/{summary.get('matrix_dimension')}`",
        f"- scaled condition number: `{summary.get('scaled_matrix_condition_number')}`",
        f"- maximum relative population difference: `{summary.get('max_abs_relative_population_difference')}`",
        f"- selected rows within tolerance: `{summary.get('n_selected_rows_within_population_tolerance')}/{summary.get('n_selected_compact_rows')}`",
        f"- conditional solve ready: `{summary.get('fortran_priority_subset_conditional_solve_ready')}`",
        f"- native compact closure ready: `{summary.get('native_priority_subset_matrix_closure_ready')}`",
        "",
        "The selected compact rows are solved conditionally while the remaining XSTAR population rows are held fixed. Matrix coefficients and external populations are still probe-derived; this is not yet the native Python expanded-basis solve.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
