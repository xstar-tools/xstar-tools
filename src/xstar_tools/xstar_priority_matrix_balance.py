"""Audit steady-state row balance for the priority compact XSTAR basis rows.

This module consumes the validated priority matrix-closure manifest and a
population-closure parity audit containing the captured XSTAR pre/post
``msolvelucy`` population vector.  It aggregates the probed Fortran
``ajisi(1, :)`` insertions into compact ``ipmat2`` matrix entries and evaluates

``residual_i = sum_j A_ij x_j``

for each activated priority row.  The result is a controlled consistency check
that the selected record manifest, endpoint mapping, occurrence selection, and
captured population vector describe the same XSTAR local solve.  It does not
alter the native Python matrix or enable the expanded-basis solver.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


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
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


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


def _resolve_json(path: str | Path, default_name: str) -> Path | None:
    try:
        return _resolve_product(path, default_name)
    except FileNotFoundError:
        return None


def _load_population_vector(
    population_closure_parity_audit: str | Path,
    *,
    population_stage: str,
) -> Tuple[Dict[int, float], Dict[str, Any], List[Dict[str, Any]]]:
    if population_stage not in {"before", "after"}:
        raise ValueError("population_stage must be 'before' or 'after'")
    overlap_path = _resolve_product(
        population_closure_parity_audit,
        "xstar_population_closure_parity_audit_overlap_rows.csv",
    )
    unmapped_path = _resolve_product(
        population_closure_parity_audit,
        "xstar_population_closure_parity_audit_unmapped_xstar_rows.csv",
    )
    column = f"xstar_{population_stage}_population"
    rows: List[Dict[str, Any]] = []
    vector: Dict[int, float] = {}
    for source, path in (("python_overlap", overlap_path), ("xstar_unmapped", unmapped_path)):
        for raw in _read_csv(path):
            ip = _as_int(raw.get("xstar_ipmat2_index"), None)
            if ip is None:
                continue
            value = _as_float(raw.get(column), 0.0)
            vector[ip] = value
            rows.append({
                "xstar_ipmat2_index": ip,
                "population_stage": population_stage,
                "population": value,
                "population_source": source,
                "xstar_nsup": raw.get("xstar_nsup", ""),
                "xstar_nion": raw.get("xstar_nion", ""),
            })
    meta: Dict[str, Any] = {
        "population_stage": population_stage,
        "n_population_rows": len(vector),
        "min_population_ipmat2": min(vector) if vector else None,
        "max_population_ipmat2": max(vector) if vector else None,
        "population_sum": sum(vector.values()),
        "overlap_csv": str(overlap_path),
        "unmapped_csv": str(unmapped_path),
    }
    json_path = _resolve_json(
        population_closure_parity_audit,
        "xstar_population_closure_parity_audit.json",
    )
    if json_path is not None:
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            summary = payload.get("summary", payload) if isinstance(payload, dict) else {}
            for key in ("selected_solve_call_id", "occurrence_rank", "selected_xstar_ipmat2", "ion"):
                if isinstance(summary, dict) and key in summary:
                    meta[key] = summary[key]
        except Exception:
            pass
    return vector, meta, rows


def build_priority_matrix_balance_audit(
    *,
    priority_matrix_closure_audit: str | Path,
    population_closure_parity_audit: str | Path,
    population_stage: str = "after",
    relative_residual_tolerance: float = 5.0e-3,
) -> Dict[str, Any]:
    """Evaluate selected compact-row residuals against an XSTAR population vector."""
    if relative_residual_tolerance <= 0.0:
        raise ValueError("relative_residual_tolerance must be positive")

    matrix_path = _resolve_product(
        priority_matrix_closure_audit,
        "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv",
    )
    selected_path = _resolve_product(
        priority_matrix_closure_audit,
        "xstar_priority_matrix_closure_audit_selected_row_summary.csv",
    )
    closure_json_path = _resolve_json(
        priority_matrix_closure_audit,
        "xstar_priority_matrix_closure_audit.json",
    )
    matrix_rows = _read_csv(matrix_path)
    selected_rows_raw = _read_csv(selected_path)
    selected_indices = sorted({
        ip for ip in (_as_int(row.get("xstar_ipmat2_index"), None) for row in selected_rows_raw)
        if ip is not None
    })
    selected_meta = {
        _as_int(row.get("xstar_ipmat2_index"), -1): dict(row)
        for row in selected_rows_raw
        if _as_int(row.get("xstar_ipmat2_index"), None) is not None
    }

    closure_summary: Dict[str, Any] = {}
    if closure_json_path is not None:
        payload = json.loads(closure_json_path.read_text(encoding="utf-8"))
        closure_summary = payload.get("summary", payload) if isinstance(payload, dict) else {}

    population, population_meta, population_rows = _load_population_vector(
        population_closure_parity_audit,
        population_stage=population_stage,
    )

    aggregated: Dict[Tuple[int, int], Dict[str, Any]] = {}
    contributions_by_row_family: Dict[Tuple[int, str], Dict[str, Any]] = defaultdict(lambda: {
        "n_terms": 0,
        "coefficient_sum_s^-1": 0.0,
        "population_weighted_net": 0.0,
        "population_weighted_abs_sum": 0.0,
    })
    term_rows: List[Dict[str, Any]] = []
    missing_population_cols: set[int] = set()

    for raw in matrix_rows:
        row_ip = _as_int(raw.get("compact_row_ipmat2"), None)
        col_ip = _as_int(raw.get("compact_col_ipmat2"), None)
        if row_ip is None or col_ip is None or row_ip not in selected_indices:
            continue
        coeff = _as_float(raw.get("ajisi_1"), 0.0)
        xcol = population.get(col_ip)
        if xcol is None:
            missing_population_cols.add(col_ip)
            xcol = 0.0
        contribution = coeff * xcol
        family = f"type{_as_int(raw.get('ltyp'), 0)}_rate{_as_int(raw.get('lrtyp'), 0)}"
        key = (row_ip, col_ip)
        if key not in aggregated:
            aggregated[key] = {
                "compact_row_ipmat2": row_ip,
                "compact_col_ipmat2": col_ip,
                "n_record_terms": 0,
                "coefficient_sum_s^-1": 0.0,
                "population_stage": population_stage,
                "column_population": xcol,
                "population_weighted_contribution": 0.0,
                "touches_selected_row": True,
            }
        entry = aggregated[key]
        entry["n_record_terms"] += 1
        entry["coefficient_sum_s^-1"] += coeff
        entry["population_weighted_contribution"] += contribution

        fam = contributions_by_row_family[(row_ip, family)]
        fam["n_terms"] += 1
        fam["coefficient_sum_s^-1"] += coeff
        fam["population_weighted_net"] += contribution
        fam["population_weighted_abs_sum"] += abs(contribution)

        term_rows.append({
            "capture_index": raw.get("capture_index", ""),
            "ml_data": raw.get("ml_data", ""),
            "ltyp": raw.get("ltyp", ""),
            "lrtyp": raw.get("lrtyp", ""),
            "family_key": family,
            "insertion_kind": raw.get("insertion_kind", ""),
            "compact_row_ipmat2": row_ip,
            "compact_col_ipmat2": col_ip,
            "ajisi_1_s^-1": coeff,
            "column_population": xcol,
            "population_weighted_contribution": contribution,
            "row_endpoint_selected": raw.get("row_endpoint_selected", ""),
            "col_endpoint_selected": raw.get("col_endpoint_selected", ""),
        })

    aggregated_rows = sorted(aggregated.values(), key=lambda row: (
        int(row["compact_row_ipmat2"]), int(row["compact_col_ipmat2"])
    ))

    row_balance_rows: List[Dict[str, Any]] = []
    family_rows: List[Dict[str, Any]] = []
    for row_ip in selected_indices:
        entries = [row for row in aggregated_rows if int(row["compact_row_ipmat2"]) == row_ip]
        net = sum(_as_float(row.get("population_weighted_contribution"), 0.0) for row in entries)
        abs_sum = sum(abs(_as_float(row.get("population_weighted_contribution"), 0.0)) for row in entries)
        positive = sum(max(_as_float(row.get("population_weighted_contribution"), 0.0), 0.0) for row in entries)
        negative = sum(min(_as_float(row.get("population_weighted_contribution"), 0.0), 0.0) for row in entries)
        relative = abs(net) / abs_sum if abs_sum > 0.0 else (0.0 if net == 0.0 else math.inf)
        if relative <= relative_residual_tolerance:
            status = "pass"
        elif relative <= 10.0 * relative_residual_tolerance:
            status = "near"
        else:
            status = "differs"
        diag = next((row for row in entries if int(row["compact_col_ipmat2"]) == row_ip), None)
        meta = selected_meta.get(row_ip, {})
        row_balance_rows.append({
            "xstar_ipmat2_index": row_ip,
            "activation_order": meta.get("activation_order", ""),
            "physical_roles": meta.get("physical_roles", ""),
            "xstar_population": population.get(row_ip, 0.0),
            "n_record_terms": sum(int(row.get("n_record_terms", 0)) for row in entries),
            "n_unique_matrix_columns": len(entries),
            "diagonal_coefficient_s^-1": _as_float(diag.get("coefficient_sum_s^-1"), 0.0) if diag else 0.0,
            "diagonal_population_weighted_contribution": _as_float(diag.get("population_weighted_contribution"), 0.0) if diag else 0.0,
            "positive_population_weighted_sum": positive,
            "negative_population_weighted_sum": negative,
            "net_population_weighted_residual": net,
            "abs_population_weighted_sum": abs_sum,
            "relative_row_residual": relative,
            "relative_residual_tolerance": relative_residual_tolerance,
            "row_balance_status": status,
        })

        row_fams = []
        for (ip, family), values in contributions_by_row_family.items():
            if ip != row_ip:
                continue
            fam_row = {
                "xstar_ipmat2_index": row_ip,
                "family_key": family,
                **values,
            }
            family_rows.append(fam_row)
            row_fams.append(fam_row)
        if row_fams:
            dominant = max(row_fams, key=lambda r: abs(float(r["population_weighted_net"])))
            row_balance_rows[-1]["dominant_net_family"] = dominant["family_key"]
            row_balance_rows[-1]["dominant_net_family_contribution"] = dominant["population_weighted_net"]

    family_rows.sort(key=lambda r: (int(r["xstar_ipmat2_index"]), -abs(float(r["population_weighted_net"]))))
    max_relative = max((float(row["relative_row_residual"]) for row in row_balance_rows), default=math.inf)
    n_pass = sum(row["row_balance_status"] == "pass" for row in row_balance_rows)
    manifest_ready = _as_bool(closure_summary.get("fortran_priority_subset_matrix_manifest_ready"))
    population_complete = (
        bool(population)
        and not missing_population_cols
        and max(population) >= max(selected_indices, default=0)
    )
    ready = bool(
        manifest_ready
        and population_complete
        and row_balance_rows
        and n_pass == len(row_balance_rows)
    )

    summary = {
        "audit_version": "v0.3.199",
        "status": "priority_matrix_row_balance_audit_completed",
        "ion": closure_summary.get("ion", population_meta.get("ion", "")),
        "selected_basis_solve_call_id": closure_summary.get(
            "selected_basis_solve_call_id", population_meta.get("selected_solve_call_id", "")
        ),
        "selection": closure_summary.get("selection", ""),
        "occurrence_rank": closure_summary.get("occurrence_rank", ""),
        "population_stage": population_stage,
        "n_population_rows": len(population),
        "population_sum": population_meta.get("population_sum"),
        "n_selected_compact_rows": len(selected_indices),
        "selected_xstar_ipmat2_indices": ";".join(str(v) for v in selected_indices),
        "n_record_level_matrix_terms": len(term_rows),
        "n_unique_compact_matrix_entries": len(aggregated_rows),
        "n_missing_population_columns": len(missing_population_cols),
        "missing_population_columns": ";".join(str(v) for v in sorted(missing_population_cols)),
        "relative_residual_tolerance": relative_residual_tolerance,
        "n_selected_rows_passing_balance": n_pass,
        "n_selected_rows_not_passing_balance": len(row_balance_rows) - n_pass,
        "max_abs_relative_row_residual": max_relative,
        "fortran_priority_subset_matrix_manifest_ready": manifest_ready,
        "population_vector_complete_for_manifest": population_complete,
        "fortran_priority_subset_row_balance_ready": ready,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": (
            "assemble_native_compact_matrix_rhs_normalization_and_compare_selected_row_residuals"
            if ready else
            "resolve_manifest_population_or_row_balance_mismatch_before_native_assembly"
        ),
        "priority_matrix_terms_csv": str(matrix_path),
        "selected_row_summary_csv": str(selected_path),
        **{f"population_{k}": v for k, v in population_meta.items() if k not in {"ion"}},
    }
    return {
        "summary": summary,
        "row_balance_rows": row_balance_rows,
        "family_contribution_rows": family_rows,
        "aggregated_matrix_rows": aggregated_rows,
        "record_term_rows": term_rows,
        "population_rows": population_rows,
    }


def write_priority_matrix_balance_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_priority_matrix_balance_audit"
    paths = {
        "row_balance_csv": out / f"{prefix}_row_balance.csv",
        "family_contributions_csv": out / f"{prefix}_family_contributions.csv",
        "aggregated_matrix_entries_csv": out / f"{prefix}_aggregated_matrix_entries.csv",
        "record_terms_csv": out / f"{prefix}_record_terms.csv",
        "population_vector_csv": out / f"{prefix}_population_vector.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["row_balance_csv"], audit.get("row_balance_rows", []))
    _write_csv(paths["family_contributions_csv"], audit.get("family_contribution_rows", []))
    _write_csv(paths["aggregated_matrix_entries_csv"], audit.get("aggregated_matrix_rows", []))
    _write_csv(paths["record_terms_csv"], audit.get("record_term_rows", []))
    _write_csv(paths["population_vector_csv"], audit.get("population_rows", []))
    paths["json"].write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")

    summary = audit.get("summary", {})
    lines = [
        "# XSTAR priority compact-matrix row-balance audit",
        "",
        f"- audit version: `{summary.get('audit_version')}`",
        f"- ion: `{summary.get('ion')}`",
        f"- selected compact rows: `{summary.get('selected_xstar_ipmat2_indices')}`",
        f"- population stage: `{summary.get('population_stage')}`",
        f"- unique compact matrix entries: `{summary.get('n_unique_compact_matrix_entries')}`",
        f"- maximum relative row residual: `{summary.get('max_abs_relative_row_residual')}`",
        f"- rows passing balance: `{summary.get('n_selected_rows_passing_balance')}/{summary.get('n_selected_compact_rows')}`",
        f"- Fortran priority subset row balance ready: `{summary.get('fortran_priority_subset_row_balance_ready')}`",
        f"- native priority subset matrix closure ready: `{summary.get('native_priority_subset_matrix_closure_ready')}`",
        "",
        "This diagnostic aggregates the probed Fortran `ajisi(1,:)` coefficients and evaluates `A x` on the captured XSTAR population vector. It does not alter the native Python solver.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
