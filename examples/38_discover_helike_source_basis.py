#!/usr/bin/env python3
"""Discover ion-specific He-like source bases from solver response matrices.

This diagnostic reads output directories produced by
``examples/20_o7_solver_source_fit.py`` or the density-grid wrapper
``examples/22_o7_solver_source_fit_density_xstar_grid.py``.  For each
``fit_ne_*`` directory it scans the available source-level response matrix,
classifies each source level by its raw f/i/r response, and builds an
ion-specific discovered source basis from levels with nonzero, nonnegative
triplet response.

The diagnostic is intentionally conservative.  It does not assume that the
O VII source-level list is ion-general.  Instead it asks whether the levels
that have already been sampled for a given ion contain a clean positive triplet
response basis.  To scan more candidate levels, rerun example 20 or 22 with a
larger ``--source-levels`` list, then run this diagnostic again.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

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
    if not fields:
        fields = ["run_dir", "warning"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fit_dir_sort_key(path: Path):
    m = re.search(r"fit_ne_([^/]+)$", path.name)
    if not m:
        return (float("inf"), path.name)
    token = m.group(1)
    try:
        return (float(token.replace("e", "E")), path.name)
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


def normalize_positive(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = np.where(np.isfinite(arr) & (arr > 0.0), arr, 0.0)
    s = float(arr.sum())
    if s <= 0.0:
        return np.zeros_like(arr)
    return arr / s


def target_vector(summary: dict) -> Optional[np.ndarray]:
    target = summary.get("target_components_normalized") or {}
    vals = [_maybe_float(target.get(k)) for k in COMPONENTS]
    if any(v is None for v in vals):
        ref = summary.get("xstar_reference") or {}
        vals = [_maybe_float(ref.get(k)) for k in COMPONENTS]
    if any(v is None for v in vals):
        return None
    arr = np.asarray([float(v) for v in vals], dtype=float)
    s = float(arr.sum())
    if not math.isfinite(s) or s <= 0.0:
        return None
    return arr / s


def ratios_from_components(vec: Sequence[float]) -> dict:
    f, i, r = [float(x) for x in vec]
    return {
        "R_f_over_i": (f / i) if i > 0 else None,
        "G_f_plus_i_over_r": ((f + i) / r) if r > 0 else None,
    }


def response_rows_to_array(rows: List[dict]) -> Tuple[np.ndarray, List[int]]:
    vals = []
    levels = []
    for row in rows:
        try:
            levels.append(int(float(row.get("source_level", "nan"))))
        except Exception:
            levels.append(-1)
        vals.append([_maybe_float(row.get(c)) or 0.0 for c in RAW_COLS])
    return np.asarray(vals, dtype=float), levels


def weight_map(rows: List[dict]) -> Dict[int, float]:
    out: Dict[int, float] = {}
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


def fit_raw_response_simplex(raw_response: np.ndarray, target_norm: np.ndarray, max_iter: int = 30000, tol: float = 1e-13) -> Tuple[np.ndarray, dict]:
    Y = np.asarray(raw_response, dtype=float)
    n = int(Y.shape[0]) if Y.ndim == 2 else 0
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
        return np.full(n, 1.0 / n, dtype=float), {"status": "zero_raw_response_matrix", "objective": None}
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
    final_centered = w @ Z
    return w, {
        "status": status,
        "iterations": int(it + 1),
        "objective": float(np.dot(final_centered, final_centered)),
        "raw_response_scale": scale,
    }


def classify_response(raw: np.ndarray, min_sum: float, neg_tol: float) -> str:
    raw = np.asarray(raw, dtype=float)
    if not np.all(np.isfinite(raw)):
        return "nonfinite"
    abs_sum = float(np.sum(np.abs(raw)))
    signed_sum = float(np.sum(raw))
    any_negative = bool(np.any(raw < -abs(neg_tol)))
    any_positive = bool(np.any(raw > abs(min_sum)))
    if abs_sum <= abs(min_sum):
        return "zero"
    if any_negative and any_positive:
        return "mixed_negative"
    if any_negative:
        return "negative"
    if signed_sum > abs(min_sum):
        return "positive_nonzero"
    return "weak_or_zero"


def load_fit_dir(fit_dir: Path) -> Optional[dict]:
    response_path = find_file(fit_dir, "o7_solver_response_matrix.csv", "*_solver_response_matrix.csv")
    weights_path = find_file(fit_dir, "o7_solver_source_fit_weights.csv", "*_solver_source_fit_weights.csv")
    summary_path = find_file(fit_dir, "o7_solver_source_fit_summary.json", "*_solver_source_fit_summary.json")
    if response_path is None or summary_path is None:
        return None
    try:
        response_rows = read_csv(response_path)
        weights_rows = read_csv(weights_path) if weights_path and weights_path.exists() else []
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {"response_rows": response_rows, "weights_rows": weights_rows, "summary": summary}


def collect_fit_dir(tag: str, run_dir: Path, fit_dir: Path, min_sum: float, neg_tol: float, max_levels: Optional[int], max_iter: int) -> Tuple[List[dict], dict]:
    data = load_fit_dir(fit_dir)
    if data is None:
        return [], {"warning": f"{fit_dir}: missing response matrix or summary"}
    summary = data["summary"]
    target = target_vector(summary)
    if target is None:
        return [], {"warning": f"{fit_dir}: missing target components"}
    Y, levels = response_rows_to_array(data["response_rows"])
    wmap = weight_map(data["weights_rows"])
    density = _maybe_float(summary.get("electron_density_cm^-3"))
    element = summary.get("element")
    ion_stage = summary.get("ion_stage")
    target_ratios = ratios_from_components(target)
    rows: List[dict] = []
    useful_indices: List[int] = []
    for idx, (level, raw) in enumerate(zip(levels, Y)):
        raw_sum = float(np.sum(raw)) if np.all(np.isfinite(raw)) else None
        raw_abs_sum = float(np.sum(np.abs(raw))) if np.all(np.isfinite(raw)) else None
        cls = classify_response(raw, min_sum, neg_tol)
        if cls == "positive_nonzero":
            useful_indices.append(idx)
        norm = normalize_positive(raw)
        ratios = ratios_from_components(norm)
        rows.append({
            "tag": tag,
            "run_dir": str(run_dir),
            "fit_dir": str(fit_dir),
            "density_cm^-3": density,
            "element": element,
            "ion_stage": ion_stage,
            "source_level": level,
            "source_label": data["response_rows"][idx].get("source_label") or data["response_rows"][idx].get("level_label") or "",
            "response_class": cls,
            "raw_forbidden": float(raw[0]),
            "raw_intercombination": float(raw[1]),
            "raw_resonance": float(raw[2]),
            "raw_triplet_sum": raw_sum,
            "raw_triplet_abs_sum": raw_abs_sum,
            "response_forbidden_norm": float(norm[0]) if norm.size == 3 else None,
            "response_intercombination_norm": float(norm[1]) if norm.size == 3 else None,
            "response_resonance_norm": float(norm[2]) if norm.size == 3 else None,
            "response_R_f_over_i": ratios.get("R_f_over_i"),
            "response_G_f_plus_i_over_r": ratios.get("G_f_plus_i_over_r"),
            "original_fit_weight_norm": float(wmap.get(level, 0.0)),
        })
    useful_indices = sorted(useful_indices, key=lambda j: float(np.sum(Y[j])), reverse=True)
    if max_levels is not None and max_levels > 0:
        useful_indices = useful_indices[: int(max_levels)]
    Yd = Y[useful_indices, :] if useful_indices else np.empty((0, 3), dtype=float)
    wf, info = fit_raw_response_simplex(Yd, target, max_iter=max_iter)
    pred_raw = wf @ Yd if wf.size else np.zeros(3, dtype=float)
    pred = normalize_positive(pred_raw)
    pred_ratios = ratios_from_components(pred)
    l2 = float(np.linalg.norm(pred - target)) if pred.size == 3 else None
    l1 = float(np.sum(np.abs(pred - target))) if pred.size == 3 else None
    class_counts: Dict[str, int] = {}
    for r in rows:
        class_counts[str(r["response_class"])] = class_counts.get(str(r["response_class"]), 0) + 1
    discovered_levels = [levels[j] for j in useful_indices]
    original_weight_useful = sum(float(wmap.get(levels[j], 0.0)) for j in useful_indices)
    original_weight_zero = sum(float(wmap.get(levels[j], 0.0)) for j in range(len(levels)) if classify_response(Y[j], min_sum, neg_tol) == "zero")
    original_weight_negative = sum(float(wmap.get(levels[j], 0.0)) for j in range(len(levels)) if "negative" in classify_response(Y[j], min_sum, neg_tol))
    discovered_weight_map = {levels[j]: float(wf[k]) for k, j in enumerate(useful_indices)} if wf.size else {}
    for r in rows:
        lev = int(r["source_level"])
        r["discovered_basis_member"] = lev in discovered_weight_map
        r["discovered_fit_weight_norm"] = discovered_weight_map.get(lev, 0.0)
    density_summary = {
        "tag": tag,
        "run_dir": str(run_dir),
        "fit_dir": str(fit_dir),
        "density_cm^-3": density,
        "element": element,
        "ion_stage": ion_stage,
        "n_candidate_source_levels": len(levels),
        "n_positive_nonzero_source_levels": class_counts.get("positive_nonzero", 0),
        "n_zero_source_levels": class_counts.get("zero", 0),
        "n_negative_or_mixed_source_levels": class_counts.get("negative", 0) + class_counts.get("mixed_negative", 0),
        "n_discovered_source_levels": len(discovered_levels),
        "discovered_source_levels": ";".join(str(x) for x in discovered_levels),
        "discovered_fit_status": info.get("status"),
        "discovered_fit_objective": info.get("objective"),
        "discovered_component_l1_error": l1,
        "discovered_component_l2_error": l2,
        "pred_forbidden": float(pred[0]) if pred.size == 3 else None,
        "pred_intercombination": float(pred[1]) if pred.size == 3 else None,
        "pred_resonance": float(pred[2]) if pred.size == 3 else None,
        "target_forbidden": float(target[0]),
        "target_intercombination": float(target[1]),
        "target_resonance": float(target[2]),
        "pred_R_f_over_i": pred_ratios.get("R_f_over_i"),
        "pred_G_f_plus_i_over_r": pred_ratios.get("G_f_plus_i_over_r"),
        "target_R_f_over_i": target_ratios.get("R_f_over_i"),
        "target_G_f_plus_i_over_r": target_ratios.get("G_f_plus_i_over_r"),
        "original_fit_weight_on_discovered_basis": original_weight_useful,
        "original_fit_weight_on_zero_response": original_weight_zero,
        "original_fit_weight_on_negative_or_mixed_response": original_weight_negative,
        "candidate_source_level_command": ",".join(str(x) for x in discovered_levels) if discovered_levels else "",
    }
    return rows, density_summary


def collect_run(run_dir: Path, min_sum: float, neg_tol: float, max_levels: Optional[int], max_iter: int) -> Tuple[List[dict], List[dict], List[str]]:
    tag = infer_tag(run_dir)
    fit_dirs = sorted([p for p in run_dir.glob("fit_ne_*") if p.is_dir()], key=fit_dir_sort_key)
    if not fit_dirs:
        return [], [], [f"{run_dir}: no fit_ne_* directories found"]
    all_rows: List[dict] = []
    summaries: List[dict] = []
    warnings: List[str] = []
    for fit_dir in fit_dirs:
        rows, ss = collect_fit_dir(tag, run_dir, fit_dir, min_sum, neg_tol, max_levels, max_iter)
        all_rows.extend(rows)
        if "warning" in ss:
            warnings.append(str(ss["warning"]))
        else:
            summaries.append(ss)
    return all_rows, summaries, warnings


def summarize_runs(density_rows: List[dict]) -> List[dict]:
    groups: Dict[str, List[dict]] = {}
    for row in density_rows:
        groups.setdefault(str(row.get("tag")), []).append(row)
    out: List[dict] = []
    for tag, rows in sorted(groups.items()):
        l2s = [_maybe_float(r.get("discovered_component_l2_error")) for r in rows]
        l2s = [x for x in l2s if x is not None]
        ndisc = [_maybe_float(r.get("n_discovered_source_levels")) for r in rows]
        npos = [_maybe_float(r.get("n_positive_nonzero_source_levels")) for r in rows]
        zero_w = [_maybe_float(r.get("original_fit_weight_on_zero_response")) for r in rows]
        neg_w = [_maybe_float(r.get("original_fit_weight_on_negative_or_mixed_response")) for r in rows]
        basis_sets = [str(r.get("discovered_source_levels", "")) for r in rows]
        nonempty_basis = [b for b in basis_sets if b]
        common_basis = ""
        if nonempty_basis and all(b == nonempty_basis[0] for b in nonempty_basis):
            common_basis = nonempty_basis[0]
        status = "basis_found" if any((_maybe_float(r.get("n_discovered_source_levels")) or 0) > 0 for r in rows) else "no_positive_nonzero_basis"
        out.append({
            "tag": tag,
            "status": status,
            "n_densities": len(rows),
            "median_n_positive_nonzero_source_levels": float(np.median([x for x in npos if x is not None])) if any(x is not None for x in npos) else None,
            "median_n_discovered_source_levels": float(np.median([x for x in ndisc if x is not None])) if any(x is not None for x in ndisc) else None,
            "median_discovered_component_l2_error": float(np.median(l2s)) if l2s else None,
            "max_discovered_component_l2_error": float(np.max(l2s)) if l2s else None,
            "median_original_zero_response_weight": float(np.median([x for x in zero_w if x is not None])) if any(x is not None for x in zero_w) else None,
            "median_original_negative_or_mixed_response_weight": float(np.median([x for x in neg_w if x is not None])) if any(x is not None for x in neg_w) else None,
            "common_discovered_source_levels": common_basis,
        })
    return out


def write_markdown(path: Path, run_rows: List[dict], density_rows: List[dict], warnings: List[str]) -> None:
    lines = ["# He-like discovered source-basis summary", ""]
    lines.append("This diagnostic ranks source levels by raw f/i/r response and discovers an ion-specific positive, nonzero source basis from sampled response matrices.")
    lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    lines.append("## Run summary")
    lines.append("")
    lines.append("| run | status | densities | median positive levels | median discovered levels | median L2 error | median zero-weight | median negative/mixed-weight | common discovered levels |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in run_rows:
        lines.append(
            f"| {r.get('tag')} | {r.get('status')} | {r.get('n_densities')} | "
            f"{_fmt(r.get('median_n_positive_nonzero_source_levels'))} | {_fmt(r.get('median_n_discovered_source_levels'))} | "
            f"{_fmt(r.get('median_discovered_component_l2_error'))} | {_fmt(r.get('median_original_zero_response_weight'))} | "
            f"{_fmt(r.get('median_original_negative_or_mixed_response_weight'))} | {r.get('common_discovered_source_levels') or ''} |"
        )
    lines.append("")
    lines.append("## Density-level discovered basis")
    lines.append("")
    lines.append("| run | density | discovered levels | L2 error | target R | target G | predicted R | predicted G |")
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|")
    for r in density_rows:
        lines.append(
            f"| {r.get('tag')} | {_fmt(r.get('density_cm^-3'))} | {r.get('discovered_source_levels') or ''} | "
            f"{_fmt(r.get('discovered_component_l2_error'))} | {_fmt(r.get('target_R_f_over_i'))} | {_fmt(r.get('target_G_f_plus_i_over_r'))} | "
            f"{_fmt(r.get('pred_R_f_over_i'))} | {_fmt(r.get('pred_G_f_plus_i_over_r'))} |"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `basis_found` means at least one sampled source level has nonzero, nonnegative raw f/i/r response.")
    lines.append("- `no_positive_nonzero_basis` means the sampled source-level set cannot provide a clean positive triplet-response basis; rerun example 20/22 with a broader source-level candidate list.")
    lines.append("- The `candidate_source_level_command` column in the density CSV can be passed to `--source-levels` for follow-up tests when nonempty.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", help="Run directories containing fit_ne_* subdirectories.")
    parser.add_argument("--out-dir", default="helike_discovered_source_basis", help="Output directory.")
    parser.add_argument("--min-triplet-response-sum", type=float, default=1e-300, help="Minimum raw |f|+|i|+|r| for nonzero classification.")
    parser.add_argument("--negative-response-tol", type=float, default=0.0, help="Tolerance for negative raw f/i/r response classification.")
    parser.add_argument("--max-levels", type=int, default=0, help="Keep only the strongest N discovered levels per density; 0 keeps all.")
    parser.add_argument("--max-iter", type=int, default=30000, help="Maximum projected-gradient iterations for discovered-basis refit.")
    parser.add_argument("--print-summary", action="store_true", help="Print concise summary.")
    args = parser.parse_args()

    max_levels = int(args.max_levels) if int(args.max_levels) > 0 else None
    source_rows: List[dict] = []
    density_rows: List[dict] = []
    warnings: List[str] = []
    for item in args.run_dirs:
        rows, summaries, ww = collect_run(Path(item), args.min_triplet_response_sum, args.negative_response_tol, max_levels, args.max_iter)
        source_rows.extend(rows)
        density_rows.extend(summaries)
        warnings.extend(ww)
    run_rows = summarize_runs(density_rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "helike_discovered_source_basis_levels.csv", source_rows)
    write_csv(out_dir / "helike_discovered_source_basis_density_summary.csv", density_rows)
    write_csv(out_dir / "helike_discovered_source_basis_run_summary.csv", run_rows)
    with (out_dir / "helike_discovered_source_basis_summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"run_summary": run_rows, "density_summary": density_rows, "source_levels": source_rows, "warnings": warnings}, handle, indent=2)
    write_markdown(out_dir / "helike_discovered_source_basis_summary.md", run_rows, density_rows, warnings)

    if args.print_summary:
        print("He-like discovered source-basis summary")
        print("----------------------------------------")
        for r in run_rows:
            print(
                f"{r.get('tag')}: status={r.get('status')} densities={r.get('n_densities')} "
                f"pos_med={_fmt(r.get('median_n_positive_nonzero_source_levels'))} "
                f"disc_med={_fmt(r.get('median_n_discovered_source_levels'))} "
                f"l2_med={_fmt(r.get('median_discovered_component_l2_error'))} "
                f"levels={r.get('common_discovered_source_levels') or 'density-dependent'}"
            )
        for w in warnings:
            print(f"WARNING: {w}")
        print(f"wrote: {out_dir / 'helike_discovered_source_basis_summary.md'}")


if __name__ == "__main__":
    main()
