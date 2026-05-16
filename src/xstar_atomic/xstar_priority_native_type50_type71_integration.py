"""Integrate validated native type-50 and type-71 terms after native type 51.

This controlled gate starts from the v0.3.205 selected-system term table, where
type 51 is already native and every other family remains probe-backed.  It
replaces all validated selected-row type-50 and type-71 terms, including both
selected-selected matrix entries and selected-to-external RHS contributions,
then recomputes row balance and the fixed-external conditional solve.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

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
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "pass"}


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
    payload = json.loads(_resolve_product(path, default_name).read_text(encoding="utf-8"))
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
    return (
        record,
        _as_int(row.get("capture_index"), None),
        str(row.get("insertion_kind") or "").strip(),
        row_ip,
        col_ip,
    )


def _structural_key(key: TermKey) -> StructuralTermKey:
    return key[0], key[2], key[3], key[4]


def _family(row: Mapping[str, Any]) -> str:
    family = str(row.get("family_key") or "").strip()
    if family:
        return family
    ltyp, lrtyp = _as_int(row.get("ltyp"), -1), _as_int(row.get("lrtyp"), -1)
    return f"type{ltyp}_rate{lrtyp}"


def _target_family(row: Mapping[str, Any]) -> str | None:
    family = _family(row)
    if family == "type50_rate4" or (_as_int(row.get("ltyp"), -1), _as_int(row.get("lrtyp"), -1)) == (50, 4):
        return "type50_rate4"
    if family == "type71_rate14" or (_as_int(row.get("ltyp"), -1), _as_int(row.get("lrtyp"), -1)) == (71, 14):
        return "type71_rate14"
    return None


def _solve(matrix: np.ndarray, rhs: np.ndarray, *, rank_rcond: float) -> Dict[str, Any]:
    n = matrix.shape[0]
    scales = np.max(np.abs(matrix), axis=1) if n else np.array([], dtype=float)
    scales[scales == 0.0] = 1.0
    scaled = matrix / scales[:, None] if n else matrix.copy()
    srhs = rhs / scales if n else rhs.copy()
    sv = np.linalg.svd(scaled, compute_uv=False) if n else np.array([], dtype=float)
    largest = float(sv[0]) if sv.size else 0.0
    threshold = rank_rcond * largest
    rank = int(np.count_nonzero(sv > threshold))
    cond = float(np.linalg.cond(scaled)) if n else math.inf
    if n and rank == n:
        solution = np.linalg.solve(scaled, srhs)
        method = "row_scaled_numpy_solve"
    elif n:
        solution, *_ = np.linalg.lstsq(scaled, srhs, rcond=rank_rcond)
        method = "row_scaled_numpy_lstsq"
    else:
        solution = np.array([], dtype=float)
        method = "empty_system"
    residual = matrix @ solution - rhs
    denom = np.maximum(np.abs(matrix @ solution) + np.abs(rhs), 1.0e-300)
    return {
        "scaled_matrix": scaled, "scaled_rhs": srhs, "row_scales": scales,
        "singular_values": sv, "rank": rank, "condition_number": cond,
        "solve_method": method, "solution": solution, "residual": residual,
        "relative_residual": np.abs(residual) / denom,
    }


def build_priority_native_type50_type71_integration_audit(
    *,
    priority_native_type51_integration_audit: str | Path,
    type50_type71_native_parity_audit: str | Path,
    relative_population_tolerance: float = 5.0e-3,
    replacement_population_delta_tolerance: float = 5.0e-5,
    relative_row_residual_tolerance: float = 5.0e-3,
    rank_rcond: float = 1.0e-12,
) -> Dict[str, Any]:
    """Replace validated type-50/type-71 selected-row terms and re-solve."""
    for name, value in (
        ("relative_population_tolerance", relative_population_tolerance),
        ("replacement_population_delta_tolerance", replacement_population_delta_tolerance),
        ("relative_row_residual_tolerance", relative_row_residual_tolerance),
        ("rank_rcond", rank_rcond),
    ):
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    parent_terms_path = _resolve_product(priority_native_type51_integration_audit, "xstar_priority_native_type51_integration_audit_term_replacements.csv")
    parent_rows_path = _resolve_product(priority_native_type51_integration_audit, "xstar_priority_native_type51_integration_audit_row_balance.csv")
    parent_solve_path = _resolve_product(priority_native_type51_integration_audit, "xstar_priority_native_type51_integration_audit_solve_comparison.csv")
    parity_terms_path = _resolve_product(type50_type71_native_parity_audit, "xstar_type50_type71_native_parity_audit_matrix_terms.csv")
    parent_terms = _read_csv(parent_terms_path)
    parent_rows = _read_csv(parent_rows_path)
    parent_solve_rows = _read_csv(parent_solve_path)
    parity_terms = _read_csv(parity_terms_path)
    parent_summary = _load_summary(priority_native_type51_integration_audit, "xstar_priority_native_type51_integration_audit.json")
    parity_summary = _load_summary(type50_type71_native_parity_audit, "xstar_type50_type71_native_parity_audit.json")

    selected = sorted({ip for r in parent_rows if (ip := _as_int(r.get("xstar_ipmat2_index"), None)) is not None})
    if not selected:
        raise ValueError("no selected rows found in parent type-51 integration audit")
    selected_set = set(selected)
    pos = {ip: i for i, ip in enumerate(selected)}
    n = len(selected)
    row_meta = {int(r["xstar_ipmat2_index"]): dict(r) for r in parent_rows if _as_int(r.get("xstar_ipmat2_index"), None) is not None}
    solve_meta = {int(r["xstar_ipmat2_index"]): dict(r) for r in parent_solve_rows if _as_int(r.get("xstar_ipmat2_index"), None) is not None}

    population: dict[int, float] = {}
    for r in parent_terms:
        col = _as_int(r.get("compact_col_ipmat2"), None)
        if col is not None:
            val = _as_float(r.get("column_population"), math.nan)
            if math.isfinite(val):
                population.setdefault(col, val)
    for ip in selected:
        population[ip] = _as_float(row_meta[ip].get("captured_population"), population.get(ip, 0.0))

    parity_exact: dict[TermKey, list[int]] = defaultdict(list)
    parity_struct: dict[StructuralTermKey, list[int]] = defaultdict(list)
    valid_indices: list[int] = []
    selected_scope: dict[str, set[int]] = {"type50_rate4": set(), "type71_rate14": set()}
    external_scope: dict[str, set[int]] = {"type50_rate4": set(), "type71_rate14": set()}
    for idx, row in enumerate(parity_terms):
        fam = _target_family(row)
        key = _term_key(row, record_field="record")
        if fam is None or key is None:
            continue
        parity_exact[key].append(idx)
        parity_struct[_structural_key(key)].append(idx)
        valid_indices.append(idx)
        (selected_scope if key[3] in selected_set else external_scope)[fam].add(idx)
    duplicate_exact = sum(max(0, len(v) - 1) for v in parity_exact.values())

    used: set[int] = set()
    unmatched: dict[str, list[str]] = {"type50_rate4": [], "type71_rate14": []}
    counts = defaultdict(int)
    touched: dict[str, set[int]] = {"type50_rate4": set(), "type71_rate14": set()}
    expected_touched: dict[str, set[int]] = {"type50_rate4": set(), "type71_rate14": set()}
    replacement_rows: list[dict[str, Any]] = []

    aggregate: dict[tuple[int, int], dict[str, Any]] = defaultdict(lambda: {
        "n_record_terms": 0, "n_native_type51_terms": 0,
        "n_native_type50_terms": 0, "n_native_type71_terms": 0,
        "n_probe_backed_terms": 0, "probe_coefficient_sum_s^-1": 0.0,
        "parent_native_type51_coefficient_sum_s^-1": 0.0,
        "hybrid_coefficient_sum_s^-1": 0.0,
    })
    family_acc: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "n_terms": 0, "n_native_terms": 0, "n_probe_backed_terms": 0,
        "probe_absolute_population_weighted_sum": 0.0,
        "parent_absolute_population_weighted_sum": 0.0,
        "hybrid_absolute_population_weighted_sum": 0.0,
        "probe_population_weighted_net": 0.0,
        "parent_population_weighted_net": 0.0,
        "hybrid_population_weighted_net": 0.0,
    })

    missing_population_columns: set[int] = set()
    for raw in parent_terms:
        row_ip = _as_int(raw.get("compact_row_ipmat2"), None)
        col_ip = _as_int(raw.get("compact_col_ipmat2"), None)
        if row_ip is None or col_ip is None or row_ip not in selected_set:
            continue
        probe = _as_float(raw.get("probe_coefficient_s^-1"), 0.0)
        parent_coeff = _as_float(raw.get("hybrid_coefficient_s^-1"), probe)
        hybrid = parent_coeff
        fam = _target_family(raw)
        match_method = "not_applicable"
        parity_row: Mapping[str, Any] | None = None
        provenance = str(raw.get("coefficient_provenance") or "fortran_probe")
        if fam is not None:
            counts[f"{fam}:balance"] += 1
            expected_touched[fam].add(row_ip)
            key = _term_key(raw, record_field="record") or _term_key(raw, record_field="ml_data")
            matched: int | None = None
            if key is not None:
                exact = [i for i in parity_exact.get(key, []) if i not in used]
                if len(exact) == 1:
                    matched, match_method = exact[0], "exact_capture_key"
                elif len(exact) > 1:
                    match_method = "ambiguous_exact_capture_key"
                else:
                    structural = [i for i in parity_struct.get(_structural_key(key), []) if i not in used]
                    if len(structural) == 1:
                        matched, match_method = structural[0], "unique_structural_key"
                    elif len(structural) > 1:
                        match_method = "ambiguous_structural_key"
                    else:
                        match_method = "no_native_match"
            else:
                match_method = "invalid_parent_term_key"
            if matched is not None:
                candidate = parity_terms[matched]
                value = _as_float(candidate.get("native_expected_ajisi_1_s^-1"), math.nan)
                valid = math.isfinite(value) and _as_bool(candidate.get("matrix_term_match")) and str(candidate.get("record_parity_status") or "") == "pass"
                if valid:
                    hybrid = value
                    used.add(matched)
                    parity_row = candidate
                    counts[f"{fam}:replaced"] += 1
                    touched[fam].add(row_ip)
                    provenance = "native_type50" if fam == "type50_rate4" else "native_type71"
                else:
                    match_method += ":parity_row_invalid"
            if parity_row is None:
                unmatched[fam].append(str(key))

        col_population = population.get(col_ip)
        if col_population is None:
            missing_population_columns.add(col_ip)
            col_population = 0.0
        partition = "selected_internal" if col_ip in selected_set else "fixed_external"
        probe_weight = probe * col_population
        parent_weight = parent_coeff * col_population
        hybrid_weight = hybrid * col_population
        family_key = _family(raw)
        acc = aggregate[(row_ip, col_ip)]
        acc["n_record_terms"] += 1
        acc["probe_coefficient_sum_s^-1"] += probe
        acc["parent_native_type51_coefficient_sum_s^-1"] += parent_coeff
        acc["hybrid_coefficient_sum_s^-1"] += hybrid
        if provenance == "native_type51":
            acc["n_native_type51_terms"] += 1
        elif provenance == "native_type50":
            acc["n_native_type50_terms"] += 1
        elif provenance == "native_type71":
            acc["n_native_type71_terms"] += 1
        else:
            acc["n_probe_backed_terms"] += 1
        facc = family_acc[(partition, family_key)]
        facc["n_terms"] += 1
        if provenance.startswith("native_type"):
            facc["n_native_terms"] += 1
        else:
            facc["n_probe_backed_terms"] += 1
        facc["probe_absolute_population_weighted_sum"] += abs(probe_weight)
        facc["parent_absolute_population_weighted_sum"] += abs(parent_weight)
        facc["hybrid_absolute_population_weighted_sum"] += abs(hybrid_weight)
        facc["probe_population_weighted_net"] += probe_weight
        facc["parent_population_weighted_net"] += parent_weight
        facc["hybrid_population_weighted_net"] += hybrid_weight
        replacement_rows.append({
            "capture_index": raw.get("capture_index", ""),
            "record": raw.get("record", raw.get("ml_data", "")),
            "ltyp": raw.get("ltyp", ""), "lrtyp": raw.get("lrtyp", ""),
            "family_key": family_key, "insertion_kind": raw.get("insertion_kind", ""),
            "compact_row_ipmat2": row_ip, "compact_col_ipmat2": col_ip,
            "partition": partition, "coefficient_provenance": provenance,
            "native_match_method": match_method,
            "probe_coefficient_s^-1": probe,
            "parent_native_type51_coefficient_s^-1": parent_coeff,
            "hybrid_coefficient_s^-1": hybrid,
            "hybrid_relative_change_vs_parent": _relative_difference(hybrid, parent_coeff),
            "column_population": col_population,
            "probe_population_weighted_contribution": probe_weight,
            "parent_population_weighted_contribution": parent_weight,
            "hybrid_population_weighted_contribution": hybrid_weight,
            "hybrid_minus_parent_population_weighted_contribution": hybrid_weight - parent_weight,
            "parity_matrix_term_match": parity_row.get("matrix_term_match", "") if parity_row else "",
            "parity_record_status": parity_row.get("record_parity_status", "") if parity_row else "",
            "parity_relative_difference": parity_row.get("relative_difference", "") if parity_row else "",
        })

    aggregate_rows: list[dict[str, Any]] = []
    probe_matrix = np.zeros((n, n), dtype=float)
    parent_matrix = np.zeros((n, n), dtype=float)
    hybrid_matrix = np.zeros((n, n), dtype=float)
    probe_rhs = np.zeros(n, dtype=float)
    parent_rhs = np.zeros(n, dtype=float)
    hybrid_rhs = np.zeros(n, dtype=float)
    for (row_ip, col_ip), acc in sorted(aggregate.items()):
        partition = "selected_internal" if col_ip in selected_set else "fixed_external"
        pop = population.get(col_ip, 0.0)
        out = {"compact_row_ipmat2": row_ip, "compact_col_ipmat2": col_ip, "partition": partition, "column_population": pop, **acc}
        out["probe_population_weighted_contribution"] = acc["probe_coefficient_sum_s^-1"] * pop
        out["parent_population_weighted_contribution"] = acc["parent_native_type51_coefficient_sum_s^-1"] * pop
        out["hybrid_population_weighted_contribution"] = acc["hybrid_coefficient_sum_s^-1"] * pop
        aggregate_rows.append(out)
        i = pos[row_ip]
        if col_ip in selected_set:
            j = pos[col_ip]
            probe_matrix[i, j] += acc["probe_coefficient_sum_s^-1"]
            parent_matrix[i, j] += acc["parent_native_type51_coefficient_sum_s^-1"]
            hybrid_matrix[i, j] += acc["hybrid_coefficient_sum_s^-1"]
        else:
            probe_rhs[i] -= acc["probe_coefficient_sum_s^-1"] * pop
            parent_rhs[i] -= acc["parent_native_type51_coefficient_sum_s^-1"] * pop
            hybrid_rhs[i] -= acc["hybrid_coefficient_sum_s^-1"] * pop

    probe_solve = _solve(probe_matrix, probe_rhs, rank_rcond=rank_rcond)
    parent_solve = _solve(parent_matrix, parent_rhs, rank_rcond=rank_rcond)
    hybrid_solve = _solve(hybrid_matrix, hybrid_rhs, rank_rcond=rank_rcond)
    captured = np.array([population.get(ip, 0.0) for ip in selected], dtype=float)

    row_abs_hybrid = defaultdict(float)
    row_residual = defaultdict(float)
    for r in replacement_rows:
        ip = int(r["compact_row_ipmat2"])
        val = float(r["hybrid_population_weighted_contribution"])
        row_abs_hybrid[ip] += abs(val)
        row_residual[ip] += val

    row_balance_rows: list[dict[str, Any]] = []
    solve_rows: list[dict[str, Any]] = []
    rhs_rows: list[dict[str, Any]] = []
    n_row_pass = n_pop_pass = n_delta_pass = 0
    max_row_rel = max_pop_rel = max_delta_rel = 0.0
    for i, ip in enumerate(selected):
        residual = row_residual[ip]
        rel_residual = abs(residual) / max(row_abs_hybrid[ip], 1.0e-300)
        row_ok = rel_residual <= relative_row_residual_tolerance
        n_row_pass += int(row_ok)
        max_row_rel = max(max_row_rel, rel_residual)
        solution = float(hybrid_solve["solution"][i])
        cap = float(captured[i])
        parent_solution = float(parent_solve["solution"][i])
        probe_solution = float(probe_solve["solution"][i])
        pop_rel = _relative_difference(solution, cap)
        delta_rel = _relative_difference(solution, parent_solution)
        pop_ok = pop_rel <= relative_population_tolerance
        delta_ok = delta_rel <= replacement_population_delta_tolerance
        n_pop_pass += int(pop_ok)
        n_delta_pass += int(delta_ok)
        max_pop_rel = max(max_pop_rel, pop_rel)
        max_delta_rel = max(max_delta_rel, delta_rel)
        roles = row_meta[ip].get("physical_roles", solve_meta.get(ip, {}).get("physical_roles", ""))
        row_balance_rows.append({
            "xstar_ipmat2_index": ip, "physical_roles": roles,
            "captured_population": cap, "hybrid_row_residual": residual,
            "hybrid_relative_row_residual": rel_residual,
            "relative_row_residual_tolerance": relative_row_residual_tolerance,
            "hybrid_row_balance_status": "pass" if row_ok else "differs",
            "row_touched_by_native_type50": ip in touched["type50_rate4"],
            "row_touched_by_native_type71": ip in touched["type71_rate14"],
        })
        solve_rows.append({
            "xstar_ipmat2_index": ip, "physical_roles": roles,
            "captured_xstar_population": cap,
            "all_probe_conditional_population": probe_solution,
            "parent_native_type51_conditional_population": parent_solution,
            "hybrid_native_type51_type50_type71_conditional_population": solution,
            "hybrid_vs_captured_relative_difference": pop_rel,
            "relative_population_tolerance": relative_population_tolerance,
            "hybrid_population_match_status": "pass" if pop_ok else "differs",
            "hybrid_vs_parent_relative_difference": delta_rel,
            "replacement_population_delta_tolerance": replacement_population_delta_tolerance,
            "replacement_population_delta_status": "pass" if delta_ok else "differs",
            "hybrid_linear_solve_residual": float(hybrid_solve["residual"][i]),
            "hybrid_linear_solve_relative_residual": float(hybrid_solve["relative_residual"][i]),
        })
        rhs_rows.append({
            "xstar_ipmat2_index": ip, "physical_roles": roles,
            "probe_external_rhs": float(probe_rhs[i]),
            "parent_native_type51_external_rhs": float(parent_rhs[i]),
            "hybrid_external_rhs": float(hybrid_rhs[i]),
            "hybrid_minus_parent_external_rhs": float(hybrid_rhs[i] - parent_rhs[i]),
            "external_rhs_relative_change_vs_parent": _relative_difference(float(hybrid_rhs[i]), float(parent_rhs[i])),
        })

    family_rows = []
    for (partition, family), acc in sorted(family_acc.items()):
        status = "probe_backed"
        if acc["n_native_terms"] == acc["n_terms"]:
            status = "native"
        elif acc["n_native_terms"]:
            status = "mixed"
        family_rows.append({"partition": partition, "family_key": family, "assembly_status": status, **acc})

    singular_rows = []
    for label, result in (("all_probe", probe_solve), ("parent_native_type51", parent_solve), ("hybrid_native_type51_type50_type71", hybrid_solve)):
        for i, value in enumerate(result["singular_values"], start=1):
            singular_rows.append({"system": label, "singular_value_index": i, "singular_value": float(value)})

    unused = sorted(set(valid_indices) - used)
    parity_scope_rows = []
    per_family_scope: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for idx in valid_indices:
        row = parity_terms[idx]
        fam = _target_family(row) or ""
        in_scope = idx in selected_scope[fam]
        is_used = idx in used
        if in_scope and is_used:
            status = "selected_row_scope_used"
        elif in_scope:
            status = "selected_row_scope_unused"
        elif is_used:
            status = "external_row_out_of_scope_but_used"
        else:
            status = "external_row_out_of_scope"
        per_family_scope[fam][status] += 1
        parity_scope_rows.append({
            "parity_term_index": idx, "family_key": fam,
            "record": row.get("record", ""), "capture_index": row.get("capture_index", ""),
            "insertion_kind": row.get("insertion_kind", ""),
            "compact_row_ipmat2": row.get("compact_row_ipmat2", ""),
            "compact_col_ipmat2": row.get("compact_col_ipmat2", ""),
            "selected_row_scope": in_scope, "used_by_selected_system": is_used,
            "scope_status": status, "matrix_term_match": row.get("matrix_term_match", ""),
            "record_parity_status": row.get("record_parity_status", ""),
            "relative_difference": row.get("relative_difference", ""),
        })

    family_gate_rows = []
    family_ready: dict[str, bool] = {}
    external_ready: dict[str, bool] = {}
    for fam in ("type50_rate4", "type71_rate14"):
        n_balance = counts[f"{fam}:balance"]
        n_replaced = counts[f"{fam}:replaced"]
        n_selected_parity = len(selected_scope[fam])
        n_external_parity = len(external_scope[fam])
        n_unused_selected = per_family_scope[fam]["selected_row_scope_unused"]
        n_used_external = per_family_scope[fam]["external_row_out_of_scope_but_used"]
        replacement_complete = (
            n_balance > 0 and n_replaced == n_balance == n_selected_parity
            and not unmatched[fam] and n_unused_selected == 0 and n_used_external == 0
            and duplicate_exact == 0 and touched[fam] == expected_touched[fam]
        )
        all_accounted = replacement_complete and n_replaced + n_external_parity == n_selected_parity + n_external_parity
        fixed_terms = [r for r in replacement_rows if r["family_key"] == fam and r["partition"] == "fixed_external"]
        fixed_native = [r for r in fixed_terms if r["coefficient_provenance"] == ("native_type50" if fam == "type50_rate4" else "native_type71")]
        ext_ready = bool(fixed_terms) and len(fixed_native) == len(fixed_terms)
        family_ready[fam] = replacement_complete and all_accounted
        external_ready[fam] = ext_ready
        family_gate_rows.append({
            "family_key": fam, "n_selected_row_balance_terms": n_balance,
            "n_terms_replaced_with_native": n_replaced,
            "n_parity_terms_in_selected_row_scope": n_selected_parity,
            "n_parity_terms_external_row_out_of_scope": n_external_parity,
            "n_unmatched_terms": len(unmatched[fam]),
            "n_unused_selected_row_parity_terms": n_unused_selected,
            "n_used_external_row_parity_terms": n_used_external,
            "n_expected_selected_rows_touched": len(expected_touched[fam]),
            "n_selected_rows_touched": len(touched[fam]),
            "all_selected_row_terms_replaced": replacement_complete,
            "all_parity_manifest_terms_accounted_for": all_accounted,
            "n_fixed_external_terms": len(fixed_terms),
            "n_fixed_external_terms_native": len(fixed_native),
            "external_rhs_ready": ext_ready,
        })

    parent_ready = _as_bool(parent_summary.get("native_type51_selected_system_integration_ready"))
    parity_ready = _as_bool(parity_summary.get("native_type50_type71_selected_system_parity_ready"))
    max_linear = float(np.max(np.abs(hybrid_solve["relative_residual"]))) if n else math.inf
    n_negative = int(np.count_nonzero(hybrid_solve["solution"] < 0.0))
    integration_ready = bool(
        parent_ready and parity_ready
        and family_ready["type50_rate4"] and family_ready["type71_rate14"]
        and external_ready["type50_rate4"] and external_ready["type71_rate14"]
        and not missing_population_columns
        and hybrid_solve["rank"] == n and n_negative == 0
        and n_row_pass == n and n_pop_pass == n and n_delta_pass == n
        and max_linear <= 1.0e-10
    )
    remaining_probe = sum(1 for r in replacement_rows if not str(r["coefficient_provenance"]).startswith("native_type"))

    summary = {
        "audit_version": "v0.3.207",
        "status": "priority_native_type50_type71_integration_completed",
        "ion": parent_summary.get("ion", parity_summary.get("ion", "")),
        "selected_basis_solve_call_id": parent_summary.get("selected_basis_solve_call_id", parity_summary.get("selected_basis_solve_call_id", "")),
        "selection": parent_summary.get("selection", parity_summary.get("selection", "")),
        "occurrence_rank": parent_summary.get("occurrence_rank", parity_summary.get("occurrence_rank", "")),
        "population_stage": parent_summary.get("population_stage", "after"),
        "n_population_rows_represented_by_term_columns": len(population),
        "n_selected_compact_rows": n,
        "selected_xstar_ipmat2_indices": ";".join(str(v) for v in selected),
        "n_parent_record_terms": len(replacement_rows),
        "n_type50_balance_terms": counts["type50_rate4:balance"],
        "n_type50_terms_replaced_with_native": counts["type50_rate4:replaced"],
        "n_type50_terms_unmatched": len(unmatched["type50_rate4"]),
        "n_type71_balance_terms": counts["type71_rate14:balance"],
        "n_type71_terms_replaced_with_native": counts["type71_rate14:replaced"],
        "n_type71_terms_unmatched": len(unmatched["type71_rate14"]),
        "n_non_type50_type71_terms": len(replacement_rows) - counts["type50_rate4:balance"] - counts["type71_rate14:balance"],
        "n_remaining_probe_backed_terms": remaining_probe,
        "n_duplicate_parity_exact_keys": duplicate_exact,
        "n_missing_population_columns": len(missing_population_columns),
        "missing_population_columns": ";".join(str(v) for v in sorted(missing_population_columns)),
        "probe_matrix_rank": probe_solve["rank"],
        "parent_native_type51_matrix_rank": parent_solve["rank"],
        "hybrid_matrix_rank": hybrid_solve["rank"],
        "matrix_dimension": n,
        "hybrid_scaled_matrix_condition_number": hybrid_solve["condition_number"],
        "hybrid_solve_method": hybrid_solve["solve_method"],
        "n_negative_hybrid_solution_rows": n_negative,
        "relative_row_residual_tolerance": relative_row_residual_tolerance,
        "n_hybrid_rows_passing_captured_balance": n_row_pass,
        "max_abs_hybrid_captured_relative_row_residual": max_row_rel,
        "relative_population_tolerance": relative_population_tolerance,
        "n_hybrid_rows_within_population_tolerance": n_pop_pass,
        "max_abs_hybrid_vs_captured_relative_population_difference": max_pop_rel,
        "replacement_population_delta_tolerance": replacement_population_delta_tolerance,
        "n_hybrid_rows_within_parent_delta_tolerance": n_delta_pass,
        "max_abs_hybrid_vs_parent_native_type51_relative_population_difference": max_delta_rel,
        "max_abs_hybrid_linear_solve_relative_residual": max_linear,
        "parent_native_type51_selected_system_integration_ready": parent_ready,
        "parent_native_type50_type71_parity_ready": parity_ready,
        "native_type50_selected_system_integration_ready": family_ready["type50_rate4"],
        "native_type71_selected_system_integration_ready": family_ready["type71_rate14"],
        "native_type50_external_rhs_ready": external_ready["type50_rate4"],
        "native_type71_external_rhs_ready": external_ready["type71_rate14"],
        "native_type50_type71_external_rhs_ready": external_ready["type50_rate4"] and external_ready["type71_rate14"],
        "native_type50_type71_selected_system_integration_ready": integration_ready,
        "hybrid_selected_system_contains_probe_backed_other_terms": remaining_probe > 0,
        "native_priority_subset_matrix_closure_ready": integration_ready and remaining_probe == 0,
        "production_expanded_compact_solver_changed": False,
        "dominant_next_target": "implement_exact_live_radiation_type53_then_remaining_minor_families" if integration_ready else "resolve_type50_type71_parity_replacement_or_solve_mismatch",
        "type53_scale44_status": "unresolved_no_empirical_factor_applied",
        "parent_type51_term_replacements_csv": str(parent_terms_path),
        "type50_type71_native_parity_matrix_terms_csv": str(parity_terms_path),
    }
    return {
        "summary": summary,
        "term_replacement_rows": replacement_rows,
        "aggregated_matrix_rows": aggregate_rows,
        "row_balance_rows": row_balance_rows,
        "solve_comparison_rows": solve_rows,
        "external_rhs_rows": rhs_rows,
        "family_status_rows": family_rows,
        "family_gate_rows": family_gate_rows,
        "singular_value_rows": singular_rows,
        "parity_scope_rows": parity_scope_rows,
        "unmatched_term_keys": unmatched,
        "unused_parity_term_indices": unused,
        "hybrid_scaled_selected_matrix": np.asarray(hybrid_solve["scaled_matrix"]).tolist(),
        "hybrid_scaled_rhs": np.asarray(hybrid_solve["scaled_rhs"]).tolist(),
    }


def write_priority_native_type50_type71_integration_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "term_replacements_csv": out / "xstar_priority_native_type50_type71_integration_audit_term_replacements.csv",
        "aggregated_matrix_entries_csv": out / "xstar_priority_native_type50_type71_integration_audit_aggregated_matrix_entries.csv",
        "row_balance_csv": out / "xstar_priority_native_type50_type71_integration_audit_row_balance.csv",
        "solve_comparison_csv": out / "xstar_priority_native_type50_type71_integration_audit_solve_comparison.csv",
        "external_rhs_csv": out / "xstar_priority_native_type50_type71_integration_audit_external_rhs.csv",
        "family_status_csv": out / "xstar_priority_native_type50_type71_integration_audit_family_status.csv",
        "family_gate_csv": out / "xstar_priority_native_type50_type71_integration_audit_family_gate.csv",
        "singular_values_csv": out / "xstar_priority_native_type50_type71_integration_audit_singular_values.csv",
        "parity_scope_csv": out / "xstar_priority_native_type50_type71_integration_audit_parity_scope.csv",
        "json": out / "xstar_priority_native_type50_type71_integration_audit.json",
        "markdown": out / "xstar_priority_native_type50_type71_integration_audit.md",
    }
    for key, data_key in (
        ("term_replacements_csv", "term_replacement_rows"),
        ("aggregated_matrix_entries_csv", "aggregated_matrix_rows"),
        ("row_balance_csv", "row_balance_rows"),
        ("solve_comparison_csv", "solve_comparison_rows"),
        ("external_rhs_csv", "external_rhs_rows"),
        ("family_status_csv", "family_status_rows"),
        ("family_gate_csv", "family_gate_rows"),
        ("singular_values_csv", "singular_value_rows"),
        ("parity_scope_csv", "parity_scope_rows"),
    ):
        _write_csv(paths[key], audit.get(data_key, []))
    paths["json"].write_text(json.dumps(dict(audit), indent=2, sort_keys=True), encoding="utf-8")
    s = dict(audit.get("summary", {}))
    lines = [
        "# XSTAR priority native type-50/type-71 integration audit", "",
        f"- Audit version: `{s.get('audit_version','')}`",
        f"- Ion: `{s.get('ion','')}`",
        f"- Native type-50 selected-system ready: `{s.get('native_type50_selected_system_integration_ready',False)}`",
        f"- Native type-71 selected-system ready: `{s.get('native_type71_selected_system_integration_ready',False)}`",
        f"- Native type-50/type-71 external RHS ready: `{s.get('native_type50_type71_external_rhs_ready',False)}`",
        f"- Combined selected-system integration ready: `{s.get('native_type50_type71_selected_system_integration_ready',False)}`",
        f"- Remaining probe-backed terms: `{s.get('n_remaining_probe_backed_terms',0)}`", "",
        "The production expanded compact-basis solver is unchanged. Type 53 remains blocked on exact live-radiation source equivalence; no empirical approximately-44 factor is applied.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths


__all__ = ["build_priority_native_type50_type71_integration_audit", "write_priority_native_type50_type71_integration_audit"]
