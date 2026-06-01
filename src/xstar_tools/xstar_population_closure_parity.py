"""Population/source-closure parity audits for XSTAR element solves.

The record-level rate probes show whether individual ``ucalc`` branches and
``calc_hmc_ion`` matrix insertions agree with the Python matrix rows.  The
population-closure probe captures the next layer: the element-level population
vector immediately before and after XSTAR's ``msolvelucy`` solve in
``calc_hmc_element.f90``.  This module compares that XSTAR population basis to
preserved Python solver products.

The audit is diagnostic.  It does not change the solver.  Its main job is to
quantify whether the current Python local basis covers the same element
population rows as XSTAR's full ``ipmat2`` problem and, for rows that can be
mapped, how the solved populations compare.
"""
from __future__ import annotations

import csv
import json
import math
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
        return f if math.isfinite(f) else default
    except Exception:
        return default


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for key in row:
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


def _resolve_csv(path: str | Path, default_name: str) -> Path:
    p = Path(path)
    if p.is_dir():
        direct = p / default_name
        if direct.exists():
            return direct
        matches = sorted(p.rglob(default_name))
        if matches:
            return matches[0]
        # Be permissive for extracted tarballs with one top directory.
        stem = default_name.replace(".csv", "")
        matches = sorted(p.rglob(f"*{stem}*.csv"))
        if matches:
            return matches[0]
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p


_ELEMENT_Z = {
    "h": 1, "he": 2, "li": 3, "be": 4, "b": 5, "c": 6, "n": 7,
    "o": 8, "f": 9, "ne": 10, "na": 11, "mg": 12, "al": 13,
    "si": 14, "p": 15, "s": 16, "cl": 17, "ar": 18, "k": 19,
    "ca": 20, "fe": 26,
}


def element_z_from_ion(ion: str) -> int:
    tok = str(ion or "").strip().split()[0].lower()
    if tok not in _ELEMENT_Z:
        raise ValueError(f"cannot infer element Z from ion={ion!r}")
    return _ELEMENT_Z[tok]


def _ion_token(ion: str) -> str:
    return ion.strip().lower().replace(" ", "_").replace("+", "p")


def _find_solver_product_paths(benchmark_dir: str | Path, ion: str) -> Dict[str, Path]:
    root = Path(benchmark_dir)
    ion_tok = _ion_token(ion)
    prod = root / "solver_products" / ion_tok
    if not prod.exists():
        hits = sorted(root.rglob(f"solver_products/{ion_tok}"))
        if hits:
            prod = hits[0]
    # Fall back to any directory with the expected products.
    if not prod.exists():
        hits = sorted(root.rglob("xstar_like_element_solver_global_index.csv"))
        if hits:
            prod = hits[0].parent
    paths = {
        "product_dir": prod,
        "global_index_csv": prod / "xstar_like_element_solver_global_index.csv",
        "normalized_solve_csv": prod / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv",
        "populations_csv": prod / "xstar_like_element_solver_populations.csv",
        "topology_audit_csv": prod / "xstar_like_element_solver_xstar_matrix_topology_audit.csv",
    }
    if not paths["global_index_csv"].exists():
        raise FileNotFoundError(f"global index CSV not found for {ion} under {benchmark_dir}")
    return paths


def _group_population_probe_rows(rows: Sequence[Mapping[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], List[Dict[str, str]]]]:
    """Return capture summaries and raw rows keyed by (solve_call_id, stage)."""
    by_key: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    by_capture: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        cap = str(r.get("capture_index") or "").strip()
        sid = str(r.get("solve_call_id") or "").strip()
        stage = str(r.get("stage") or "").strip()
        by_capture.setdefault(cap, []).append(dict(r))
        by_key.setdefault((sid, stage), []).append(dict(r))
    captures: List[Dict[str, Any]] = []
    for cap, rs in sorted(by_capture.items(), key=lambda kv: (_as_int(kv[0], 0) or 0, kv[0])):
        if not rs:
            continue
        first = rs[0]
        ipmat2 = _as_int(first.get("ipmat2"), None)
        pop_sum = sum(_as_float(r.get("x_population"), 0.0) or 0.0 for r in rs)
        nonzero = sum(1 for r in rs if abs(_as_float(r.get("x_population"), 0.0) or 0.0) > 0.0)
        captures.append({
            "capture_index": cap,
            "solve_call_id": first.get("solve_call_id", ""),
            "stage": first.get("stage", ""),
            "ml_element": first.get("ml_element", ""),
            "element_z": _as_int(first.get("element_z"), None),
            "ipmat2": ipmat2,
            "nsp": _as_int(first.get("nsp"), None),
            "nionp": _as_int(first.get("nionp"), None),
            "nindbe": _as_int(first.get("nindbe"), None),
            "nit": _as_int(first.get("nit"), None),
            "nit2": _as_int(first.get("nit2"), None),
            "nit3": _as_int(first.get("nit3"), None),
            "n_rows": len(rs),
            "n_rows_matches_ipmat2": (ipmat2 == len(rs)) if ipmat2 is not None else False,
            "population_sum": pop_sum,
            "n_nonzero_population_rows": nonzero,
        })
    return captures, by_key


def _build_pairs(captures: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    by_sid: Dict[str, Dict[str, Mapping[str, Any]]] = {}
    for c in captures:
        sid = str(c.get("solve_call_id") or "").strip()
        stage = str(c.get("stage") or "").strip()
        if sid:
            by_sid.setdefault(sid, {})[stage] = c
    pairs: List[Dict[str, Any]] = []
    for sid, d in sorted(by_sid.items(), key=lambda kv: (_as_int(kv[0], 0) or 0, kv[0])):
        b = d.get("before_msolvelucy")
        a = d.get("after_msolvelucy")
        if not b or not a:
            continue
        pairs.append({
            "solve_call_id": sid,
            "before_capture_index": b.get("capture_index", ""),
            "after_capture_index": a.get("capture_index", ""),
            "element_z": b.get("element_z"),
            "ml_element": b.get("ml_element", ""),
            "ipmat2": b.get("ipmat2"),
            "nsp": b.get("nsp"),
            "nionp": b.get("nionp"),
            "nindbe": b.get("nindbe"),
            "before_population_sum": b.get("population_sum"),
            "after_population_sum": a.get("population_sum"),
            "population_sum_delta": (_as_float(a.get("population_sum"), 0.0) or 0.0) - (_as_float(b.get("population_sum"), 0.0) or 0.0),
            "after_n_nonzero_population_rows": a.get("n_nonzero_population_rows"),
            "after_nit": a.get("nit"),
            "after_nit2": a.get("nit2"),
            "after_nit3": a.get("nit3"),
            "pair_ready": bool(b.get("n_rows_matches_ipmat2") and a.get("n_rows_matches_ipmat2") and b.get("ipmat2") == a.get("ipmat2")),
        })
    return pairs


def _select_pair(pairs: Sequence[Mapping[str, Any]], element_z: int, occurrence_rank: int | None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    elem_pairs = [dict(p) for p in pairs if _as_int(p.get("element_z"), None) == int(element_z)]
    for i, p in enumerate(elem_pairs, start=1):
        p["element_occurrence_rank"] = i
    if not elem_pairs:
        raise ValueError(f"no paired population captures for element_z={element_z}")
    if occurrence_rank is None or occurrence_rank == -1:
        return elem_pairs[-1], elem_pairs
    if occurrence_rank <= 0:
        raise ValueError("occurrence_rank is 1-based, or use -1/latest")
    if occurrence_rank > len(elem_pairs):
        raise ValueError(f"occurrence_rank={occurrence_rank} exceeds n_element_pairs={len(elem_pairs)}")
    return elem_pairs[occurrence_rank - 1], elem_pairs


def _rows_for_pair(by_key: Mapping[Tuple[str, str], List[Dict[str, str]]], pair: Mapping[str, Any], stage: str) -> List[Dict[str, str]]:
    sid = str(pair.get("solve_call_id") or "").strip()
    rows = list(by_key.get((sid, stage), []))
    rows.sort(key=lambda r: _as_int(r.get("level_index"), 0) or 0)
    return rows


def _load_python_population_rows(paths: Mapping[str, Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    norm = paths.get("normalized_solve_csv")
    if norm and norm.exists():
        for r in _read_csv_rows(norm):
            if str(r.get("row_kind") or "") != "population":
                continue
            out = dict(r)
            out["global_index_int"] = _as_int(r.get("global_index"), None)
            out["xstar_ipmat2_index_int"] = _as_int(r.get("xstar_ipmat2_index"), None)
            out["python_population_fraction"] = _as_float(r.get("population_fraction"), None)
            out["python_xstar_superlevel_population_p"] = _as_float(r.get("xstar_superlevel_population_p"), None)
            out["python_rr_fraction_within_superlevel"] = _as_float(r.get("xstar_rr_fraction_within_superlevel"), None)
            out["python_nsup"] = _as_int(r.get("xstar_nsup"), None)
            rows.append(out)
        if rows:
            return rows
    # Fallback: join global index and simple populations by ion_stage/level_index.
    g_rows = _read_csv_rows(paths["global_index_csv"])
    pop_rows: Dict[Tuple[int, int], Dict[str, str]] = {}
    pop_path = paths.get("populations_csv")
    if pop_path and pop_path.exists():
        for r in _read_csv_rows(pop_path):
            key = (_as_int(r.get("ion_stage"), -1) or -1, _as_int(r.get("level_index"), -1) or -1)
            pop_rows[key] = r
    for g in g_rows:
        key = (_as_int(g.get("ion_stage"), -1) or -1, _as_int(g.get("level_index"), -1) or -1)
        p = pop_rows.get(key, {})
        out = dict(g)
        out["global_index_int"] = _as_int(g.get("global_index"), None)
        out["xstar_ipmat2_index_int"] = (_as_int(g.get("global_index"), None) or 0) + 1 if _as_int(g.get("global_index"), None) is not None else None
        out["python_population_fraction"] = _as_float(p.get("population_fraction"), None)
        out["python_xstar_superlevel_population_p"] = None
        out["python_rr_fraction_within_superlevel"] = None
        out["python_nsup"] = None
        rows.append(out)
    return rows


def audit_population_closure_parity(
    *,
    benchmark_dir: str | Path,
    ion: str,
    population_probe_csv: str | Path,
    occurrence_rank: int | None = None,
    element_z: int | None = None,
    population_delta_threshold: float = 1e-4,
) -> Dict[str, Any]:
    """Compare a selected XSTAR population-closure pair to Python products."""
    ez = element_z if element_z is not None else element_z_from_ion(ion)
    probe_path = _resolve_csv(population_probe_csv, "xstar_population_closure_probe.csv")
    rows = _read_csv_rows(probe_path)
    captures, by_key = _group_population_probe_rows(rows)
    pairs = _build_pairs(captures)
    selected_pair, element_pairs = _select_pair(pairs, ez, occurrence_rank)
    before_rows = _rows_for_pair(by_key, selected_pair, "before_msolvelucy")
    after_rows = _rows_for_pair(by_key, selected_pair, "after_msolvelucy")
    paths = _find_solver_product_paths(benchmark_dir, ion)
    py_rows = _load_python_population_rows(paths)

    py_by_ip: Dict[int, Dict[str, Any]] = {}
    for r in py_rows:
        ip = _as_int(r.get("xstar_ipmat2_index_int"), None)
        if ip is not None and ip > 0:
            py_by_ip[ip] = dict(r)

    before_by_level = {_as_int(r.get("level_index"), -1): r for r in before_rows}
    overlap_rows: List[Dict[str, Any]] = []
    unmapped_rows: List[Dict[str, Any]] = []
    mapped_pop = 0.0
    unmapped_pop = 0.0
    max_abs_diff_population_fraction = 0.0
    max_abs_diff_superlevel_p = 0.0
    n_diff_population_fraction = 0
    n_diff_superlevel_p = 0
    for ar in after_rows:
        ip = _as_int(ar.get("level_index"), None)
        if ip is None:
            continue
        xr_after = _as_float(ar.get("x_population"), 0.0) or 0.0
        br = before_by_level.get(ip, {})
        xr_before = _as_float(br.get("x_population"), 0.0) or 0.0
        py = py_by_ip.get(ip)
        if py is None:
            unmapped_pop += xr_after
            unmapped_rows.append({
                "xstar_ipmat2_index": ip,
                "xstar_after_population": xr_after,
                "xstar_before_population": xr_before,
                "xstar_nsup": ar.get("nsup", ""),
                "xstar_nion": ar.get("nion", ""),
                "reason": "no_python_row_with_this_xstar_ipmat2_index",
            })
            continue
        mapped_pop += xr_after
        py_pop = _as_float(py.get("python_population_fraction"), None)
        py_p = _as_float(py.get("python_xstar_superlevel_population_p"), None)
        diff_pop = (py_pop - xr_after) if py_pop is not None else None
        diff_p = (py_p - xr_after) if py_p is not None else None
        if diff_pop is not None:
            max_abs_diff_population_fraction = max(max_abs_diff_population_fraction, abs(diff_pop))
            if abs(diff_pop) > population_delta_threshold:
                n_diff_population_fraction += 1
        if diff_p is not None:
            max_abs_diff_superlevel_p = max(max_abs_diff_superlevel_p, abs(diff_p))
            if abs(diff_p) > population_delta_threshold:
                n_diff_superlevel_p += 1
        overlap_rows.append({
            "xstar_ipmat2_index": ip,
            "global_index": py.get("global_index") or py.get("global_index_int"),
            "ion_stage": py.get("ion_stage", ""),
            "level_index": py.get("level_index", ""),
            "level_label": py.get("level_label", ""),
            "level_kind": py.get("level_kind", ""),
            "xstar_before_population": xr_before,
            "xstar_after_population": xr_after,
            "xstar_nsup": ar.get("nsup", ""),
            "xstar_nion": ar.get("nion", ""),
            "python_population_fraction": py_pop if py_pop is not None else "",
            "python_xstar_superlevel_population_p": py_p if py_p is not None else "",
            "python_rr_fraction_within_superlevel": py.get("python_rr_fraction_within_superlevel", ""),
            "python_nsup": py.get("python_nsup", ""),
            "python_minus_xstar_after_population_fraction": diff_pop if diff_pop is not None else "",
            "python_superlevel_p_minus_xstar_after": diff_p if diff_p is not None else "",
            "abs_python_minus_xstar_after_population_fraction": abs(diff_pop) if diff_pop is not None else "",
            "abs_python_superlevel_p_minus_xstar_after": abs(diff_p) if diff_p is not None else "",
        })

    xstar_sum_after = sum(_as_float(r.get("x_population"), 0.0) or 0.0 for r in after_rows)
    xstar_sum_before = sum(_as_float(r.get("x_population"), 0.0) or 0.0 for r in before_rows)
    n_xstar_nonzero = sum(1 for r in after_rows if abs(_as_float(r.get("x_population"), 0.0) or 0.0) > 0.0)
    n_unmapped_nonzero = sum(1 for r in unmapped_rows if abs(_as_float(r.get("xstar_after_population"), 0.0) or 0.0) > 0.0)
    basis_ready = (len(unmapped_rows) == 0 or abs(unmapped_pop) <= population_delta_threshold) and len(overlap_rows) > 0
    overlap_ready = (n_diff_population_fraction == 0 or max_abs_diff_population_fraction <= population_delta_threshold)
    superlevel_ready = (n_diff_superlevel_p == 0 or max_abs_diff_superlevel_p <= population_delta_threshold)
    source_equivalent_ready = bool(basis_ready and (overlap_ready or superlevel_ready))
    if not basis_ready:
        target = "full_element_population_basis_and_parent_superlevel_closure"
    elif not (overlap_ready or superlevel_ready):
        target = "population_vector_values_or_normalization_closure"
    else:
        target = "population_closure_near_parity"

    scan_rows: List[Dict[str, Any]] = []
    py_ip_set = set(py_by_ip)
    for ep in element_pairs:
        a_rows = _rows_for_pair(by_key, ep, "after_msolvelucy")
        total = sum(_as_float(r.get("x_population"), 0.0) or 0.0 for r in a_rows)
        mapped = 0.0
        unmapped = 0.0
        for r in a_rows:
            ip = _as_int(r.get("level_index"), None)
            val = _as_float(r.get("x_population"), 0.0) or 0.0
            if ip in py_ip_set:
                mapped += val
            else:
                unmapped += val
        scan_rows.append({
            **ep,
            "xstar_after_population_sum": total,
            "xstar_after_population_sum_on_python_mapped_rows": mapped,
            "xstar_after_population_sum_on_unmapped_rows": unmapped,
            "unmapped_population_fraction_of_total": (unmapped / total) if total else "",
        })

    summary: Dict[str, Any] = {
        "audit_version": "v0.3.190",
        "ion": ion,
        "status": "population_closure_parity_audit_completed",
        "population_probe_csv": str(probe_path),
        "benchmark_dir": str(benchmark_dir),
        "selected_element_z": ez,
        "selection": "latest" if occurrence_rank in (None, -1) else "occurrence-rank",
        "occurrence_rank": selected_pair.get("element_occurrence_rank", ""),
        "selected_solve_call_id": selected_pair.get("solve_call_id", ""),
        "selected_before_capture_index": selected_pair.get("before_capture_index", ""),
        "selected_after_capture_index": selected_pair.get("after_capture_index", ""),
        "selected_xstar_ipmat2": selected_pair.get("ipmat2", ""),
        "selected_xstar_nsp": selected_pair.get("nsp", ""),
        "selected_xstar_nionp": selected_pair.get("nionp", ""),
        "selected_xstar_nindbe": selected_pair.get("nindbe", ""),
        "n_population_probe_rows": len(rows),
        "n_population_pairs_total": len(pairs),
        "n_element_pairs": len(element_pairs),
        "n_xstar_population_rows_selected": len(after_rows),
        "n_xstar_nonzero_population_rows_selected": n_xstar_nonzero,
        "xstar_population_sum_before": xstar_sum_before,
        "xstar_population_sum_after": xstar_sum_after,
        "n_python_population_rows": len(py_rows),
        "n_python_rows_with_xstar_ipmat2_index": len(py_by_ip),
        "n_overlap_rows": len(overlap_rows),
        "n_xstar_rows_without_python_mapping": len(unmapped_rows),
        "n_xstar_unmapped_nonzero_rows": n_unmapped_nonzero,
        "xstar_population_sum_on_python_mapped_rows": mapped_pop,
        "xstar_population_sum_on_unmapped_rows": unmapped_pop,
        "xstar_unmapped_population_fraction_of_total": (unmapped_pop / xstar_sum_after) if xstar_sum_after else "",
        "max_abs_diff_python_population_fraction": max_abs_diff_population_fraction,
        "n_overlap_rows_diff_python_population_fraction_gt_threshold": n_diff_population_fraction,
        "max_abs_diff_python_superlevel_p": max_abs_diff_superlevel_p,
        "n_overlap_rows_diff_python_superlevel_p_gt_threshold": n_diff_superlevel_p,
        "population_delta_threshold": population_delta_threshold,
        "basis_closure_ready": basis_ready,
        "overlap_population_fraction_ready": overlap_ready,
        "overlap_superlevel_population_ready": superlevel_ready,
        "source_equivalent_population_closure_ready": source_equivalent_ready,
        "dominant_next_target": target,
    }
    return {
        "summary": summary,
        "capture_scan_rows": scan_rows,
        "overlap_rows": overlap_rows,
        "unmapped_xstar_rows": unmapped_rows,
    }


def write_population_closure_parity_audit(audit: Mapping[str, Any], out_dir: str | Path) -> Dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_population_closure_parity_audit"
    paths = {
        "capture_scan_csv": out / f"{prefix}_capture_scan.csv",
        "overlap_rows_csv": out / f"{prefix}_overlap_rows.csv",
        "unmapped_xstar_rows_csv": out / f"{prefix}_unmapped_xstar_rows.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["capture_scan_csv"], list(audit.get("capture_scan_rows", []) or []))
    _write_csv(paths["overlap_rows_csv"], list(audit.get("overlap_rows", []) or []))
    _write_csv(paths["unmapped_xstar_rows_csv"], list(audit.get("unmapped_xstar_rows", []) or []))
    summary = dict(audit.get("summary", {}) or {})
    paths["json"].write_text(json.dumps({
        "summary": summary,
        "capture_scan_rows": list(audit.get("capture_scan_rows", []) or []),
        "overlap_rows": list(audit.get("overlap_rows", []) or []),
        "unmapped_xstar_rows": list(audit.get("unmapped_xstar_rows", []) or []),
    }, indent=2, default=str), encoding="utf-8")
    lines = [
        "# XSTAR population/source closure parity audit",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"ion: `{summary.get('ion')}`",
        f"status: `{summary.get('status')}`",
        f"selected solve_call_id: `{summary.get('selected_solve_call_id')}`",
        f"occurrence_rank: `{summary.get('occurrence_rank')}`",
        "",
        "## Main conclusion",
        "",
        f"source_equivalent_population_closure_ready: `{summary.get('source_equivalent_population_closure_ready')}`",
        f"dominant_next_target: `{summary.get('dominant_next_target')}`",
        "",
        "## Basis coverage",
        "",
        f"- XSTAR selected ipmat2 rows: `{summary.get('n_xstar_population_rows_selected')}`",
        f"- Python rows with xstar_ipmat2 mapping: `{summary.get('n_python_rows_with_xstar_ipmat2_index')}`",
        f"- overlap rows: `{summary.get('n_overlap_rows')}`",
        f"- XSTAR rows without Python mapping: `{summary.get('n_xstar_rows_without_python_mapping')}`",
        f"- XSTAR population sum on unmapped rows: `{summary.get('xstar_population_sum_on_unmapped_rows')}`",
        "",
        "## Overlap comparison",
        "",
        f"- max |Python population_fraction - XSTAR after|: `{summary.get('max_abs_diff_python_population_fraction')}`",
        f"- max |Python superlevel P - XSTAR after|: `{summary.get('max_abs_diff_python_superlevel_p')}`",
        "",
        "This audit is diagnostic; it does not change solver physics.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
