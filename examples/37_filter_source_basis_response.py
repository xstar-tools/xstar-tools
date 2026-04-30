#!/usr/bin/env python3
"""Compare He-like source-basis filters against fitted triplet targets.

This diagnostic works on output directories produced by
``examples/20_o7_solver_source_fit.py`` or by the density-grid wrapper
``examples/22_o7_solver_source_fit_density_xstar_grid.py``.  It refits the
raw f/i/r response matrix after applying simple source-level filters:

* all source levels;
* source levels with all-zero f/i/r response removed;
* source levels with any negative raw f/i/r response removed;
* source levels with only nonzero, nonnegative f/i/r response retained.

The output is intended to answer whether a non-O VII ion fails because the
source basis is contaminated by zero/negative-response levels, or because the
XSTAR target is outside the span of even the clean positive-response basis.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

RAW_COLS = ["raw_forbidden", "raw_intercombination", "raw_resonance"]
COMPONENTS = ["forbidden", "intercombination", "resonance"]


def _maybe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        val = float(value)
    except Exception:
        return None
    if not math.isfinite(val):
        return None
    return val


def _fmt(value, precision: int = 6) -> str:
    val = _maybe_float(value)
    if val is None:
        return "NA"
    return f"{val:.{precision}g}"


def read_csv(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def project_to_simplex(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if v.size == 0:
        return v
    u = np.sort(v)[::-1]
    cssv = np.cumsum(u)
    rho_candidates = u * np.arange(1, len(u) + 1) > (cssv - 1.0)
    if not np.any(rho_candidates):
        return np.full_like(v, 1.0 / len(v))
    rho = np.nonzero(rho_candidates)[0][-1]
    theta = (cssv[rho] - 1.0) / float(rho + 1)
    w = np.maximum(v - theta, 0.0)
    sw = float(w.sum())
    return w / sw if sw > 0.0 else np.full_like(v, 1.0 / len(v))


def normalize_positive(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = np.where(np.isfinite(arr) & (arr > 0.0), arr, 0.0)
    s = float(arr.sum())
    if s <= 0.0:
        return np.full_like(arr, 1.0 / len(arr)) if len(arr) else arr
    return arr / s


def fit_raw_response_simplex(raw_response: np.ndarray, target_norm: np.ndarray, max_iter: int = 50000, tol: float = 1e-13) -> Tuple[np.ndarray, dict]:
    Y = np.asarray(raw_response, dtype=float)
    n = int(Y.shape[0])
    if n == 0:
        return np.array([], dtype=float), {"status": "empty_response_matrix", "objective": None}
    target = np.asarray(target_norm, dtype=float)
    tsum = float(np.sum(target))
    if not math.isfinite(tsum) or tsum <= 0.0:
        return np.full(n, 1.0 / n, dtype=float), {"status": "invalid_target", "objective": None}
    target = target / tsum
    row_sums = np.sum(Y, axis=1)
    good = np.isfinite(row_sums) & (row_sums > 0.0)
    scale = float(np.nanmax(np.where(good, row_sums, 0.0))) if Y.size else 0.0
    if not np.isfinite(scale) or scale <= 0.0:
        final_raw = np.full(3, 0.0)
        final_norm = normalize_positive(final_raw)
        return np.full(n, 1.0 / n, dtype=float), {
            "status": "zero_raw_response_matrix",
            "objective": None,
            "raw_response_scale": scale,
            "combined_raw_triplet_sum": float(np.sum(final_raw)),
            "combined_normalized_forbidden": float(final_norm[0]),
            "combined_normalized_intercombination": float(final_norm[1]),
            "combined_normalized_resonance": float(final_norm[2]),
        }
    Ys = Y / scale
    Z = Ys - np.sum(Ys, axis=1)[:, None] * target[None, :]
    w = np.full(n, 1.0 / n, dtype=float)
    try:
        spectral = float(np.linalg.norm(Z, ord=2))
    except Exception:
        spectral = float(np.linalg.norm(Z))
    step = 1.0 / max(2.0 * spectral * spectral, 1e-30)
    prev = float("inf")
    status = "max_iter"
    it = 0
    for it in range(int(max_iter)):
        resid = w @ Z
        obj = float(np.dot(resid, resid))
        if abs(prev - obj) < tol * max(1.0, prev):
            status = "converged"
            break
        prev = obj
        grad = 2.0 * (Z @ resid)
        w = project_to_simplex(w - step * grad)
    final_raw = w @ Y
    final_norm = normalize_positive(final_raw)
    final_centered = w @ Z
    return w, {
        "status": status,
        "iterations": int(it + 1),
        "objective": float(np.dot(final_centered, final_centered)),
        "step": step,
        "raw_response_scale": scale,
        "combined_raw_triplet_sum": float(np.sum(final_raw)),
        "combined_normalized_forbidden": float(final_norm[0]),
        "combined_normalized_intercombination": float(final_norm[1]),
        "combined_normalized_resonance": float(final_norm[2]),
    }


def ratios_from_components(vec: Sequence[float]) -> dict:
    f, i, r = [float(x) for x in vec]
    return {
        "forbidden": f,
        "intercombination": i,
        "resonance": r,
        "R_f_over_i": (f / i) if i > 0 else None,
        "G_f_plus_i_over_r": ((f + i) / r) if r > 0 else None,
    }


def fit_dir_sort_key(path: Path):
    m = re.search(r"fit_ne_([^/]+)$", path.name)
    if not m:
        return (float("inf"), path.name)
    token = m.group(1)
    try:
        return (float(token.replace("e", "E")), path.name)
    except Exception:
        try:
            return (float(token), path.name)
        except Exception:
            return (float("inf"), path.name)


def infer_tag(run_dir: Path) -> str:
    name = run_dir.name
    for suffix in ["_solver_source_fit_density_xstar_grid", "_source_fit_density_xstar_grid", "_density_xstar_grid"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    name = name.replace("o7_solver", "o7")
    return name


def find_file(fit_dir: Path, *names: str) -> Optional[Path]:
    for name in names:
        p = fit_dir / name
        if p.exists():
            return p
    matches = []
    for pattern in names:
        matches.extend(fit_dir.glob(pattern))
    return matches[0] if matches else None


def load_fit_dir(fit_dir: Path) -> Optional[dict]:
    response_path = find_file(fit_dir, "o7_solver_response_matrix.csv", "*_solver_response_matrix.csv")
    summary_path = find_file(fit_dir, "o7_solver_source_fit_summary.json", "*_solver_source_fit_summary.json")
    weights_path = find_file(fit_dir, "o7_solver_source_fit_weights.csv", "*_solver_source_fit_weights.csv")
    if response_path is None or summary_path is None:
        return None
    try:
        response_rows = read_csv(response_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        weights_rows = read_csv(weights_path) if weights_path and weights_path.exists() else []
    except Exception:
        return None
    return {
        "response_path": response_path,
        "summary_path": summary_path,
        "weights_path": weights_path,
        "response_rows": response_rows,
        "weights_rows": weights_rows,
        "summary": summary,
    }


def target_vector(summary: dict) -> Optional[np.ndarray]:
    target = summary.get("target_components_normalized") or {}
    vals = [_maybe_float(target.get(k)) for k in COMPONENTS]
    if any(v is None for v in vals):
        # Fallback to raw XSTAR reference.
        ref = summary.get("xstar_reference") or {}
        vals = [_maybe_float(ref.get(k)) for k in COMPONENTS]
    if any(v is None for v in vals):
        return None
    arr = np.asarray([float(v) for v in vals], dtype=float)
    s = float(arr.sum())
    if not math.isfinite(s) or s <= 0.0:
        return None
    return arr / s


def response_array(rows: List[dict]) -> Tuple[np.ndarray, List[int]]:
    vals = []
    levels = []
    for row in rows:
        try:
            levels.append(int(float(row.get("source_level", "nan"))))
        except Exception:
            levels.append(-1)
        vals.append([_maybe_float(row.get(c)) or 0.0 for c in RAW_COLS])
    return np.asarray(vals, dtype=float), levels


def original_weight_map(rows: List[dict]) -> Dict[int, float]:
    out = {}
    for row in rows:
        try:
            lev = int(float(row.get("source_level", "nan")))
        except Exception:
            continue
        val = _maybe_float(row.get("fit_weight_norm"))
        if val is None:
            val = _maybe_float(row.get("solver_fit_weight_norm"))
        if val is not None:
            out[lev] = float(val)
    return out


def filter_masks(Y: np.ndarray, zero_tol: float, neg_tol: float) -> Dict[str, np.ndarray]:
    abs_sum = np.sum(np.abs(Y), axis=1)
    all_zero = abs_sum <= zero_tol
    any_negative = np.any(Y < -abs(neg_tol), axis=1)
    any_nonfinite = ~np.all(np.isfinite(Y), axis=1)
    return {
        "all": np.ones(Y.shape[0], dtype=bool) & ~any_nonfinite,
        "drop_zero_response": (~all_zero) & ~any_nonfinite,
        "drop_negative_response": (~any_negative) & ~any_nonfinite,
        "positive_nonzero_response": (~all_zero) & (~any_negative) & ~any_nonfinite,
    }


def collect_run(run_dir: Path, zero_tol: float, neg_tol: float, max_iter: int) -> Tuple[List[dict], List[str]]:
    rows: List[dict] = []
    warnings: List[str] = []
    fit_dirs = sorted([p for p in run_dir.glob("fit_ne_*") if p.is_dir()], key=fit_dir_sort_key)
    tag = infer_tag(run_dir)
    if not fit_dirs:
        warnings.append(f"{run_dir}: no fit_ne_* directories found")
        return rows, warnings
    for fit_dir in fit_dirs:
        data = load_fit_dir(fit_dir)
        if data is None:
            warnings.append(f"{fit_dir}: missing response matrix or summary JSON")
            continue
        summary = data["summary"]
        target = target_vector(summary)
        if target is None:
            warnings.append(f"{fit_dir}: missing target components")
            continue
        Y, levels = response_array(data["response_rows"])
        wmap = original_weight_map(data["weights_rows"])
        masks = filter_masks(Y, zero_tol, neg_tol)
        density = _maybe_float(summary.get("electron_density_cm^-3"))
        element = summary.get("element")
        ion_stage = summary.get("ion_stage")
        xref = summary.get("xstar_reference") or {}
        target_ratios = ratios_from_components(target)
        original_zero_weight_sum = 0.0
        original_negative_weight_sum = 0.0
        all_zero = np.sum(np.abs(Y), axis=1) <= zero_tol
        any_negative = np.any(Y < -abs(neg_tol), axis=1)
        for level, z, neg in zip(levels, all_zero, any_negative):
            ww = float(wmap.get(level, 0.0))
            if z:
                original_zero_weight_sum += ww
            if neg:
                original_negative_weight_sum += ww
        for filter_name, mask in masks.items():
            kept_idx = np.where(mask)[0]
            dropped_idx = np.where(~mask)[0]
            Yf = Y[kept_idx, :] if kept_idx.size else np.empty((0, 3), dtype=float)
            wf, info = fit_raw_response_simplex(Yf, target, max_iter=max_iter)
            raw = wf @ Yf if wf.size else np.zeros(3, dtype=float)
            pred = normalize_positive(raw)
            ratios = ratios_from_components(pred)
            component_l1 = float(np.sum(np.abs(pred - target))) if pred.size == 3 else None
            component_l2 = float(np.linalg.norm(pred - target)) if pred.size == 3 else None
            r = ratios.get("R_f_over_i")
            g = ratios.get("G_f_plus_i_over_r")
            xt_r = target_ratios.get("R_f_over_i")
            xt_g = target_ratios.get("G_f_plus_i_over_r")
            r_rel = abs(r - xt_r) / abs(xt_r) if r is not None and xt_r not in (None, 0.0) else None
            g_rel = abs(g - xt_g) / abs(xt_g) if g is not None and xt_g not in (None, 0.0) else None
            keep_levels = [levels[i] for i in kept_idx]
            dropped_levels = [levels[i] for i in dropped_idx]
            dropped_zero = int(np.sum(all_zero[dropped_idx])) if dropped_idx.size else 0
            dropped_negative = int(np.sum(any_negative[dropped_idx])) if dropped_idx.size else 0
            rows.append({
                "tag": tag,
                "run_dir": str(run_dir),
                "fit_dir": str(fit_dir),
                "density_cm^-3": density,
                "element": element,
                "ion_stage": ion_stage,
                "filter": filter_name,
                "n_source_levels_total": int(Y.shape[0]),
                "n_source_levels_kept": int(kept_idx.size),
                "n_source_levels_dropped": int(dropped_idx.size),
                "n_zero_response_levels_total": int(np.sum(all_zero)),
                "n_negative_response_levels_total": int(np.sum(any_negative)),
                "n_zero_response_levels_dropped": dropped_zero,
                "n_negative_response_levels_dropped": dropped_negative,
                "original_fit_weight_on_zero_response": original_zero_weight_sum,
                "original_fit_weight_on_negative_response": original_negative_weight_sum,
                "fit_status": info.get("status"),
                "fit_objective": info.get("objective"),
                "component_l1_error": component_l1,
                "component_l2_error": component_l2,
                "pred_forbidden": float(pred[0]) if pred.size == 3 else None,
                "pred_intercombination": float(pred[1]) if pred.size == 3 else None,
                "pred_resonance": float(pred[2]) if pred.size == 3 else None,
                "target_forbidden": float(target[0]),
                "target_intercombination": float(target[1]),
                "target_resonance": float(target[2]),
                "pred_R_f_over_i": r,
                "pred_G_f_plus_i_over_r": g,
                "target_R_f_over_i": xt_r,
                "target_G_f_plus_i_over_r": xt_g,
                "R_relative_error": r_rel,
                "G_relative_error": g_rel,
                "xstar_R_f_over_i": xref.get("R_f_over_i"),
                "xstar_G_f_plus_i_over_r": xref.get("G_f_plus_i_over_r"),
                "kept_source_levels": ";".join(str(x) for x in keep_levels),
                "dropped_source_levels": ";".join(str(x) for x in dropped_levels),
            })
    return rows, warnings


def summarize(rows: List[dict]) -> List[dict]:
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        groups.setdefault((str(row.get("tag")), str(row.get("filter"))), []).append(row)
    out = []
    for (tag, filt), rr in sorted(groups.items()):
        l2s = [_maybe_float(r.get("component_l2_error")) for r in rr]
        l2s = [x for x in l2s if x is not None]
        objs = [_maybe_float(r.get("fit_objective")) for r in rr]
        objs = [x for x in objs if x is not None]
        n_kept = [_maybe_float(r.get("n_source_levels_kept")) for r in rr]
        zero_w = [_maybe_float(r.get("original_fit_weight_on_zero_response")) for r in rr]
        neg_w = [_maybe_float(r.get("original_fit_weight_on_negative_response")) for r in rr]
        out.append({
            "tag": tag,
            "filter": filt,
            "n_densities": len(rr),
            "median_component_l2_error": float(np.median(l2s)) if l2s else None,
            "max_component_l2_error": float(np.max(l2s)) if l2s else None,
            "median_fit_objective": float(np.median(objs)) if objs else None,
            "median_n_source_levels_kept": float(np.median(n_kept)) if n_kept else None,
            "median_original_zero_response_weight": float(np.median([x for x in zero_w if x is not None])) if any(x is not None for x in zero_w) else None,
            "median_original_negative_response_weight": float(np.median([x for x in neg_w if x is not None])) if any(x is not None for x in neg_w) else None,
        })
    return out


def write_markdown(path: Path, summary_rows: List[dict], detail_rows: List[dict], warnings: List[str]) -> None:
    lines = ["# He-like source-basis filter comparison", ""]
    lines.append("This diagnostic refits the triplet target after dropping zero-response and/or negative-response source levels.")
    lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    lines.append("## Run/filter summary")
    lines.append("")
    lines.append("| run | filter | densities | median kept | median L2 error | median objective | median zero-weight | median negative-weight |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in summary_rows:
        lines.append(
            f"| {r.get('tag')} | {r.get('filter')} | {r.get('n_densities')} | "
            f"{_fmt(r.get('median_n_source_levels_kept'))} | {_fmt(r.get('median_component_l2_error'))} | "
            f"{_fmt(r.get('median_fit_objective'))} | {_fmt(r.get('median_original_zero_response_weight'))} | "
            f"{_fmt(r.get('median_original_negative_response_weight'))} |"
        )
    lines.append("")
    lines.append("## Interpretation guide")
    lines.append("")
    lines.append("- If `positive_nonzero_response` gives small errors, the failure is likely source-basis contamination.")
    lines.append("- If `positive_nonzero_response` still gives large errors or has too few levels, the XSTAR target is outside the current clean response basis or the source-level set is incomplete.")
    lines.append("- The `original zero/negative weight` columns report where the original fitted vector placed weight before filtering.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", help="Density-grid or single-run output directories containing fit_ne_* subdirectories.")
    parser.add_argument("--out-dir", default="helike_source_basis_filter_comparison", help="Output directory.")
    parser.add_argument("--zero-response-tol", type=float, default=1e-300, help="Absolute |f|+|i|+|r| threshold for all-zero response.")
    parser.add_argument("--negative-response-tol", type=float, default=0.0, help="Tolerance for classifying raw response as negative.")
    parser.add_argument("--max-iter", type=int, default=50000, help="Maximum projected-gradient iterations per refit.")
    parser.add_argument("--print-summary", action="store_true", help="Print concise summary.")
    args = parser.parse_args()

    all_rows: List[dict] = []
    warnings: List[str] = []
    for item in args.run_dirs:
        rows, ww = collect_run(Path(item), args.zero_response_tol, args.negative_response_tol, args.max_iter)
        all_rows.extend(rows)
        warnings.extend(ww)
    summary_rows = summarize(all_rows)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "helike_source_basis_filter_comparison.csv", all_rows)
    write_csv(out_dir / "helike_source_basis_filter_summary.csv", summary_rows)
    with (out_dir / "helike_source_basis_filter_comparison.json").open("w", encoding="utf-8") as handle:
        json.dump({"summary": summary_rows, "rows": all_rows, "warnings": warnings}, handle, indent=2)
    write_markdown(out_dir / "helike_source_basis_filter_summary.md", summary_rows, all_rows, warnings)

    if args.print_summary:
        print("He-like source-basis filter comparison")
        print("---------------------------------------")
        for r in summary_rows:
            print(
                f"{r.get('tag')} {r.get('filter')}: densities={r.get('n_densities')} "
                f"kept_med={_fmt(r.get('median_n_source_levels_kept'))} "
                f"l2_med={_fmt(r.get('median_component_l2_error'))} "
                f"obj_med={_fmt(r.get('median_fit_objective'))}"
            )
        for w in warnings:
            print(f"WARNING: {w}")
        print(f"wrote: {out_dir / 'helike_source_basis_filter_summary.md'}")


if __name__ == "__main__":
    main()
