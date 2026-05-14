"""Replay/replacement utilities for XSTAR record-level local matrix parity.

This module uses the validated record-level XSTAR probes/audits to build a
controlled diagnostic matrix in which selected Python matrix rows are replaced
by XSTAR ``ucalc`` branch rates.  It is intended for local-state parity work:
first prove that the Python topology can replay the Fortran ``ans1/ans2`` rows,
then port the missing Fortran branches into native Python implementations.
"""

from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return int(round(f))
    except Exception:
        return default


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return f
    except Exception:
        return default


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in ordered:
                    ordered.append(str(key))
        fields = ordered or ["status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _ion_token(ion: str) -> str:
    return ion.strip().lower().replace(" ", "_").replace("+", "p")


def _find_solver_product_paths(benchmark_dir: str | Path, ion: str) -> Dict[str, Path]:
    root = Path(benchmark_dir)
    ion_tok = _ion_token(ion)
    prod = root / "solver_products" / ion_tok
    if not prod.exists():
        # Support extracted benchmark tarballs with one top-level directory.
        hits = list(root.rglob(f"solver_products/{ion_tok}"))
        if hits:
            prod = hits[0]
    paths = {
        "product_dir": prod,
        "matrix_terms_csv": prod / "xstar_like_element_solver_full_global_matrix_terms.csv",
        "global_index_csv": prod / "xstar_like_element_solver_global_index.csv",
        "line_rows_csv": prod / "xstar_like_element_solver_line_rows.csv",
        "calc_ion_rates_csv": prod / "xstar_like_element_solver_calc_ion_rates_istruc_audit.csv",
    }
    if not paths["matrix_terms_csv"].exists():
        raise FileNotFoundError(f"full-global matrix terms not found for {ion} under {benchmark_dir}")
    return paths


def _resolve_record_level_audit_records_csv(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        p = p / "xstar_record_level_matrix_parity_audit_records.csv"
    if not p.exists():
        raise FileNotFoundError(f"record-level parity records CSV not found: {p}")
    return p


def _record_key_from_matrix_row(row: Mapping[str, Any]) -> Optional[int]:
    rec = _as_int(row.get("record"), None)
    if rec is None or rec <= 0:
        rec = _as_int(row.get("type99_records"), None)
    if rec is None or rec <= 0:
        return None
    return int(rec)


def _row_text(row: Mapping[str, Any]) -> str:
    keys = [
        "matrix_term_kind", "matrix_role", "row_kind", "full_global_component",
        "full_global_provenance", "assembly_status", "source_method",
        "rate_source", "type77_rate_source", "type99_rate_source",
    ]
    return " ".join(str(row.get(k, "")) for k in keys).lower()


def _family_text(row: Mapping[str, Any], rec_row: Mapping[str, Any] | None = None) -> str:
    return (str((rec_row or {}).get("family_key") or "") + " " + _row_text(row)).lower()


def _record_status_selected(rec_row: Mapping[str, Any], *, mode: str, families: Sequence[str]) -> bool:
    mode = str(mode or "blockers").strip().lower().replace("_", "-")
    fam = str(rec_row.get("family_key") or "").lower()
    hyp = str(rec_row.get("blocker_hypothesis") or "").lower()
    status = str(rec_row.get("record_parity_status") or "").lower()
    if mode in {"all", "all-records"}:
        return True
    if mode in {"differs", "differing"}:
        return "differs" in status
    if mode in {"blockers", "blocking", "high"}:
        return ("blocking" in str(rec_row.get("blocker_priority") or "").lower()
                or "high" in str(rec_row.get("blocker_priority") or "").lower()
                or "type53" in hyp or "type77" in hyp or "type99" in hyp or "type50" in hyp)
    if mode in {"families", "family"}:
        toks = [f.lower() for f in families]
        return any(t in fam for t in toks)
    return False


def _infer_branch(row: Mapping[str, Any], rec_row: Mapping[str, Any]) -> str:
    """Infer whether a Python matrix row belongs to the Fortran ans1 or ans2 branch.

    This is a topology-preserving diagnostic mapping.  It keeps the Python row
    and column indices, but replaces the absolute rate with XSTAR ``ucalc``
    ``ans1`` or ``ans2`` depending on the branch encoded in the row metadata.
    """
    text = _family_text(row, rec_row)
    signed = _as_float(row.get("full_global_signed_rate_s^-1"), None)
    if signed is None:
        signed = _as_float(row.get("signed_rate_s^-1"), None)
    # Explicit labels first.
    if "ans1" in text:
        return "ans1"
    if "ans2" in text:
        return "ans2"
    # Photoionization-like forward branch.
    if any(tok in text for tok in [
        "photoionization", "phint53_photo", "bound_to_continuum",
        "destination_to_parent_continuum", "type99_destination_to_parent",
        "phint53hunt_photoionization", "photoionization_sink",
    ]):
        return "ans1"
    # Recombination/Milne-like reverse branch.
    if any(tok in text for tok in [
        "milne", "recombination", "parent_continuum_to_bound",
        "parent_continuum_to_type99", "phint53_ans2", "rec_xnx",
    ]):
        return "ans2"
    # Type-77 labels: XSTAR self-check maps forward branch to ans1 and reverse to ans2.
    if "type77" in text:
        if "clu" in text:
            return "ans1"
        if "cul" in text:
            return "ans2"
    # Type-50 line escape in cfrac=1 local runs often has ans1≈0 and only two
    # upper-to-lower decay rows; map two-row non-photoexcitation cases to ans2.
    if "data_type_50" in text or "type50" in text or "bound_bound" in text:
        ans1 = _as_float(rec_row.get("ans1"), 0.0) or 0.0
        ans2 = _as_float(rec_row.get("ans2"), 0.0) or 0.0
        if abs(ans1) <= 1e-30 and abs(ans2) > 0.0:
            return "ans2"
    # If still ambiguous, choose the branch whose rate is closer to the old row.
    old_abs = abs(signed) if signed is not None else None
    ans1 = abs(_as_float(rec_row.get("ans1"), 0.0) or 0.0)
    ans2 = abs(_as_float(rec_row.get("ans2"), 0.0) or 0.0)
    if old_abs is not None:
        if abs(old_abs - ans1) <= abs(old_abs - ans2):
            return "ans1"
        return "ans2"
    return "unknown"


def apply_record_level_ucalc_replay(
    matrix_terms: Sequence[Mapping[str, Any]],
    record_parity_rows: Sequence[Mapping[str, Any]],
    *,
    replacement_mode: str = "blockers",
    families: Sequence[str] = (),
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Replace selected matrix-row rates by XSTAR ``ucalc`` branch rates.

    The replacement preserves the Python matrix topology and sign.  It changes
    only the row rate magnitude, using ``ans1`` or ``ans2`` from a selected
    record-level parity audit.  This creates a diagnostic replay matrix for
    local parity and population-solve tests; it is not a native physics port.
    """
    rec_lookup: Dict[int, Dict[str, Any]] = {}
    for r in record_parity_rows:
        rec = _as_int(r.get("record"), None)
        if rec is None or rec <= 0:
            continue
        if _as_int(r.get("fortran_n_matrix_rows"), 0) != 4:
            continue
        if str(r.get("fortran_matrix_self_check_status") or "") != "pass":
            continue
        if not _record_status_selected(r, mode=replacement_mode, families=families):
            continue
        rec_lookup[int(rec)] = dict(r)

    out: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for row0 in matrix_terms:
        row = dict(row0)
        rec = _record_key_from_matrix_row(row)
        rec_row = rec_lookup.get(rec) if rec is not None else None
        if rec_row is None:
            row["record_level_ucalc_replay_status"] = "not_replayed"
            out.append(row)
            continue
        branch = _infer_branch(row, rec_row)
        if branch not in {"ans1", "ans2"}:
            row["record_level_ucalc_replay_status"] = "not_replayed_branch_unresolved"
            out.append(row)
            continue
        new_abs = _as_float(rec_row.get(branch), None)
        if new_abs is None or new_abs < 0.0:
            row["record_level_ucalc_replay_status"] = f"not_replayed_{branch}_invalid"
            out.append(row)
            continue
        old_signed = _as_float(row.get("full_global_signed_rate_s^-1"), None)
        if old_signed is None:
            old_signed = _as_float(row.get("signed_rate_s^-1"), None)
        sign = -1.0 if (old_signed is not None and old_signed < 0.0) else 1.0
        old_abs = _as_float(row.get("full_global_rate_s^-1"), None)
        if old_abs is None:
            old_abs = abs(old_signed) if old_signed is not None else _as_float(row.get("rate_s^-1"), 0.0)
        new_signed = sign * float(new_abs)
        for key in ["full_global_signed_rate_s^-1", "signed_rate_s^-1"]:
            if key in row:
                row[key] = new_signed
        for key in ["full_global_rate_s^-1", "rate_s^-1"]:
            if key in row:
                row[key] = float(new_abs)
        ratio = (float(old_abs) / max(float(new_abs), 1e-300)) if old_abs is not None else ""
        row.update({
            "record_level_ucalc_replay_status": f"replayed_from_fortran_{branch}_v03184",
            "record_level_ucalc_replay_branch": branch,
            "record_level_ucalc_replay_old_rate_s^-1": old_abs,
            "record_level_ucalc_replay_new_rate_s^-1": float(new_abs),
            "record_level_ucalc_replay_old_over_new": ratio,
            "record_level_ucalc_replay_selected_capture_index": rec_row.get("selected_capture_index"),
            "record_level_ucalc_replay_family_key": rec_row.get("family_key"),
            "record_level_ucalc_replay_blocker_hypothesis": rec_row.get("blocker_hypothesis"),
            "full_global_assembly_status": "assembled_full_global_topology_with_record_level_ucalc_replay_v03184",
        })
        changed.append({
            "row_kind": "record_level_ucalc_replay_matrix_term",
            "record": rec,
            "family_key": rec_row.get("family_key"),
            "blocker_hypothesis": rec_row.get("blocker_hypothesis"),
            "matrix_term_kind": row.get("matrix_term_kind"),
            "matrix_role": row.get("matrix_role"),
            "matrix_row_global_index": row.get("matrix_row_global_index"),
            "matrix_col_global_index": row.get("matrix_col_global_index"),
            "branch": branch,
            "old_rate_s^-1": old_abs,
            "old_signed_rate_s^-1": old_signed,
            "new_rate_s^-1": float(new_abs),
            "new_signed_rate_s^-1": new_signed,
            "old_over_new": ratio,
            "selected_capture_index": rec_row.get("selected_capture_index"),
            "replacement_status": row["record_level_ucalc_replay_status"],
        })
        out.append(row)
    return out, changed


def _median(values: Iterable[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else 0.5 * (vals[mid - 1] + vals[mid])


def _percentile(values: Iterable[float], pct: float) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return None
    vals.sort()
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * float(pct) / 100.0
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def _family_summary(changed_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for r in changed_rows:
        groups.setdefault(str(r.get("family_key") or "unknown"), []).append(r)
    out: List[Dict[str, Any]] = []
    for fam, rows in sorted(groups.items()):
        ratios = [_as_float(r.get("old_over_new"), None) for r in rows]
        ratios = [float(r) for r in ratios if r is not None and r > 0 and math.isfinite(r)]
        branches: Dict[str, int] = {}
        for r in rows:
            b = str(r.get("branch") or "")
            branches[b] = branches.get(b, 0) + 1
        out.append({
            "family_key": fam,
            "n_replayed_terms": len(rows),
            "median_old_over_new": _median(ratios),
            "p16_old_over_new": _percentile(ratios, 16.0),
            "p84_old_over_new": _percentile(ratios, 84.0),
            "min_old_over_new": min(ratios) if ratios else "",
            "max_old_over_new": max(ratios) if ratios else "",
            "branch_counts": json.dumps(branches, sort_keys=True),
        })
    return out


def _summary_row_for_solve(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        case = str(row.get("comparison_case") or row.get("row_kind") or "").lower()
        if "full_global" in case or "normalized" in case or str(row.get("row_kind") or "") == "full_global_normalized_solve_summary":
            return dict(row)
    return dict(rows[-1]) if rows else {}


def audit_record_level_ucalc_matrix_replay(
    *,
    benchmark_dir: str | Path,
    ion: str,
    record_level_audit_csv: str | Path,
    matrix_terms_csv: str | Path | None = None,
    global_index_csv: str | Path | None = None,
    line_rows_csv: str | Path | None = None,
    calc_ion_rates_csv: str | Path | None = None,
    replacement_mode: str = "blockers",
    families: Sequence[str] = (),
    run_solver: bool = False,
    linear_solver: str = "xstar-lucy",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    prune_null_rate_levels: bool = True,
    full_global_topology: str = "xstar-continuum-alias-superlevels",
    ion_fraction_closure: str = "xstar-calc-ion-rates",
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    paths = _find_solver_product_paths(benchmark_dir, ion)
    matrix_path = Path(matrix_terms_csv) if matrix_terms_csv else paths["matrix_terms_csv"]
    global_path = Path(global_index_csv) if global_index_csv else paths["global_index_csv"]
    lines_path = Path(line_rows_csv) if line_rows_csv else paths["line_rows_csv"]
    calc_path = Path(calc_ion_rates_csv) if calc_ion_rates_csv else paths["calc_ion_rates_csv"]
    rec_path = _resolve_record_level_audit_records_csv(record_level_audit_csv)
    matrix_rows = _read_csv_rows(matrix_path)
    record_rows = _read_csv_rows(rec_path)
    replay_terms, changed_rows = apply_record_level_ucalc_replay(
        matrix_rows, record_rows, replacement_mode=replacement_mode, families=families
    )
    family_rows = _family_summary(changed_rows)
    solve_comparison_rows: List[Dict[str, Any]] = []
    original_solve_rows: List[Dict[str, Any]] = []
    replay_solve_rows: List[Dict[str, Any]] = []
    solve_status = "not_run"
    if run_solver:
        from .xstar_element_solver import build_full_global_normalized_solve_comparison
        global_rows = _read_csv_rows(global_path)
        line_rows = _read_csv_rows(lines_path)
        calc_rows = _read_csv_rows(calc_path) if calc_path.exists() else []
        he_stage = None
        for gr in global_rows:
            label = str(gr.get("level_label") or gr.get("label") or "").lower()
            comp = str(gr.get("triplet_component") or "").lower()
            if comp in {"f", "i", "r"} or "1s1.2" in label:
                he_stage = _as_int(gr.get("ion_stage"), None)
                if he_stage is not None:
                    break
        if he_stage is None:
            raise ValueError("could not infer He-like stage from global index rows")
        original_solve_rows = build_full_global_normalized_solve_comparison(
            global_index_rows=global_rows,
            full_global_matrix_terms=matrix_rows,
            line_rows=line_rows,
            he_like_stage=int(he_stage),
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
            prune_null_rate_levels=prune_null_rate_levels,
            full_global_topology=full_global_topology,
            ion_fraction_closure=ion_fraction_closure,
            calc_ion_rates_istruc_audit_rows=calc_rows,
        )
        replay_solve_rows = build_full_global_normalized_solve_comparison(
            global_index_rows=global_rows,
            full_global_matrix_terms=replay_terms,
            line_rows=line_rows,
            he_like_stage=int(he_stage),
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
            prune_null_rate_levels=prune_null_rate_levels,
            full_global_topology=full_global_topology,
            ion_fraction_closure=ion_fraction_closure,
            calc_ion_rates_istruc_audit_rows=calc_rows,
        )
        orig = _summary_row_for_solve(original_solve_rows)
        repl = _summary_row_for_solve(replay_solve_rows)
        solve_status = "completed"
        for label, row in [("original_matrix", orig), ("record_level_ucalc_replay", repl)]:
            solve_comparison_rows.append({
                "row_kind": "record_level_ucalc_replay_solve_summary",
                "comparison_case": label,
                "f_fraction": row.get("f_fraction"),
                "i_fraction": row.get("i_fraction"),
                "r_fraction": row.get("r_fraction"),
                "R": row.get("R"),
                "G": row.get("G"),
                "l2_distance_to_target": row.get("l2_distance_to_target"),
                "solve_status": row.get("solve_status"),
                "solver": row.get("solver"),
                "n_negative_populations": row.get("n_negative_populations"),
                "sum_population": row.get("sum_population"),
            })
    ratios = [_as_float(r.get("old_over_new"), None) for r in changed_rows]
    ratios = [float(r) for r in ratios if r is not None and r > 0 and math.isfinite(r)]
    summary = {
        "audit_version": "v0.3.184",
        "ion": ion,
        "status": "record_level_ucalc_matrix_replay_audit_completed",
        "replacement_mode": replacement_mode,
        "families": ";".join(families),
        "matrix_terms_csv": str(matrix_path),
        "record_level_audit_csv": str(rec_path),
        "n_original_matrix_terms": len(matrix_rows),
        "n_replay_matrix_terms": len(replay_terms),
        "n_replayed_terms": len(changed_rows),
        "n_replayed_families": len(family_rows),
        "median_old_over_new": _median(ratios),
        "p16_old_over_new": _percentile(ratios, 16.0),
        "p84_old_over_new": _percentile(ratios, 84.0),
        "run_solver": bool(run_solver),
        "solve_status": solve_status,
        "solver": linear_solver,
        "total_seconds": time.perf_counter() - t0,
        "interpretation": "Controlled diagnostic replay: selected Python matrix row magnitudes are replaced by Fortran ucalc ans1/ans2 branch values from the validated record-level audit while preserving Python topology and signs. This is a parity/replay scaffold, not a native source-code port.",
    }
    return {
        "summary": summary,
        "replay_matrix_terms": replay_terms,
        "changed_rows": changed_rows,
        "family_rows": family_rows,
        "solve_comparison_rows": solve_comparison_rows,
        "original_solve_rows": original_solve_rows,
        "replay_solve_rows": replay_solve_rows,
    }


def write_record_level_ucalc_matrix_replay_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_record_level_ucalc_matrix_replay_audit",
) -> Dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    summary = dict(audit.get("summary", {}) or {})
    changed = list(audit.get("changed_rows", []) or [])
    family = list(audit.get("family_rows", []) or [])
    terms = list(audit.get("replay_matrix_terms", []) or [])
    solve_comp = list(audit.get("solve_comparison_rows", []) or [])
    replay_solve = list(audit.get("replay_solve_rows", []) or [])
    changed_csv = out / f"{prefix}_changed_terms.csv"
    family_csv = out / f"{prefix}_family_summary.csv"
    terms_csv = out / f"{prefix}_matrix_terms.csv"
    comp_csv = out / f"{prefix}_solve_comparison.csv"
    solve_csv = out / f"{prefix}_replay_normalized_solve_comparison.csv"
    _write_csv(changed_csv, changed)
    _write_csv(family_csv, family)
    _write_csv(terms_csv, terms)
    _write_csv(comp_csv, solve_comp)
    _write_csv(solve_csv, replay_solve)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "family_rows": family, "changed_rows": changed[:2000], "solve_comparison_rows": solve_comp}, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR record-level ucalc matrix replay audit",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"ion: `{summary.get('ion')}`",
        f"status: `{summary.get('status')}`",
        f"replacement_mode: `{summary.get('replacement_mode')}`",
        f"n_replayed_terms: `{summary.get('n_replayed_terms')}`",
        f"median_old_over_new: `{summary.get('median_old_over_new')}`",
        f"run_solver: `{summary.get('run_solver')}`",
        f"solve_status: `{summary.get('solve_status')}`",
        "",
        "## Family replay summary",
        "",
        "| family | n terms | median old/new | p16 | p84 | branches |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in family:
        lines.append(f"| {r.get('family_key')} | {r.get('n_replayed_terms')} | {r.get('median_old_over_new')} | {r.get('p16_old_over_new')} | {r.get('p84_old_over_new')} | {r.get('branch_counts')} |")
    if solve_comp:
        lines.extend(["", "## Solve comparison", "", "| case | f | i | r | R | G | status |", "|---|---:|---:|---:|---:|---:|---|"])
        for r in solve_comp:
            lines.append(f"| {r.get('comparison_case')} | {r.get('f_fraction')} | {r.get('i_fraction')} | {r.get('r_fraction')} | {r.get('R')} | {r.get('G')} | {r.get('solve_status')} |")
    lines.extend(["", "## Interpretation", "", str(summary.get("interpretation") or "")])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "changed_terms_csv": str(changed_csv),
        "family_summary_csv": str(family_csv),
        "replay_matrix_terms_csv": str(terms_csv),
        "solve_comparison_csv": str(comp_csv),
        "replay_normalized_solve_comparison_csv": str(solve_csv),
        "json": str(json_path),
        "markdown": str(md_path),
    }
