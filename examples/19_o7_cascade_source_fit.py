#!/usr/bin/env python3
"""Fit prototype O VII cascade-source weights from a radiative yield matrix.

This Stage-6 diagnostic moves beyond hand-tuned cascade target weights.  It
builds a radiative cascade yield matrix

    Y(seed level -> forbidden, intercombination, resonance)

from the decoded O VII radiative branching network, then solves for nonnegative
source weights that best reproduce the O VII triplet ratios measured from an
XSTAR ``xout_lines1.fits`` conversion CSV.

The fitted source weights are diagnostic only.  The oxygen recombination records
currently decoded from ``atdb.fits`` are total O VIII -> O VII recombination
rates, not true level-resolved recombination rates.  This example asks what
level-resolved source distribution would be required by the current radiative
cascade network to reproduce XSTAR-like triplet ratios.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from xstar_atomic.hierarchy import ATDB
from xstar_atomic.lines import extract_levels, extract_lines, choose_z
from xstar_atomic.recombination import build_radiative_branching, cascade_probabilities_from_seed, parse_level_list, safe_float


def _maybe_float(value) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _classify_o7_wavelength(wavelength: float) -> Optional[str]:
    if abs(wavelength - 22.1012) < 0.03:
        return "f"
    if abs(wavelength - 21.8070) < 0.04 or abs(wavelength - 21.8044) < 0.04:
        return "i"
    if abs(wavelength - 21.6020) < 0.03:
        return "r"
    return None


def read_xstar_triplet_ratios(path: Path, value_column: str = "emit_outward") -> dict:
    """Read O VII f/i/r ratios from a converted XSTAR line CSV."""
    totals = {"f": 0.0, "i": 0.0, "r": 0.0}
    counts = {"f": 0, "i": 0, "r": 0}
    if not path.exists():
        return {"available": False, "path": str(path)}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ion_text = str(row.get("ion", "")).strip().lower().replace(" ", "").replace("_", "")
            if ion_text not in {"ovii", "o7"}:
                continue
            wav = _maybe_float(row.get("wavelength") or row.get("wavelength_A"))
            val = _maybe_float(row.get(value_column))
            if wav is None or val is None:
                continue
            kind = _classify_o7_wavelength(wav)
            if kind is None:
                continue
            totals[kind] += val
            counts[kind] += 1
    f, i, r = totals["f"], totals["i"], totals["r"]
    return {
        "available": True,
        "path": str(path),
        "value_column": value_column,
        "forbidden": f,
        "intercombination": i,
        "resonance": r,
        "R_f_over_i": (f / i) if i > 0 else None,
        "G_f_plus_i_over_r": ((f + i) / r) if r > 0 else None,
        "counts": counts,
        "note": "XSTAR model-output ratio; not directly normalized to local xstar-atomic emissivity coefficients.",
    }


def normalize_positive(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = np.where(np.isfinite(arr) & (arr > 0.0), arr, 0.0)
    s = float(arr.sum())
    if s <= 0.0:
        return np.full_like(arr, 1.0 / len(arr)) if len(arr) else arr
    return arr / s


def project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Project vector v onto the probability simplex {w>=0, sum(w)=1}."""
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
    sw = w.sum()
    return w / sw if sw > 0.0 else np.full_like(v, 1.0 / len(v))


def fit_nonnegative_simplex(Y: np.ndarray, target: np.ndarray, max_iter: int = 20000, tol: float = 1e-13) -> Tuple[np.ndarray, dict]:
    """Fit nonnegative source weights on a simplex using projected gradient.

    Parameters
    ----------
    Y:
        Matrix with shape ``(n_source_levels, 3)`` for f/i/r yields.
    target:
        Normalized target vector with shape ``(3,)``.
    """
    n = int(Y.shape[0])
    if n == 0:
        return np.array([], dtype=float), {"status": "empty_yield_matrix"}
    w = np.full(n, 1.0 / n, dtype=float)
    # Lipschitz estimate for gradient of ||Y^T w - t||^2.
    try:
        spectral = float(np.linalg.norm(Y, ord=2))
    except Exception:
        spectral = float(np.linalg.norm(Y))
    step = 1.0 / max(2.0 * spectral * spectral, 1e-30)
    prev = float("inf")
    status = "max_iter"
    for it in range(int(max_iter)):
        pred = w @ Y
        resid = pred - target
        obj = float(np.dot(resid, resid))
        if abs(prev - obj) < tol * max(1.0, prev):
            status = "converged"
            break
        prev = obj
        grad = 2.0 * (Y @ resid)
        w = project_to_simplex(w - step * grad)
    return w, {
        "status": status,
        "iterations": it + 1 if n else 0,
        "objective": float(np.dot((w @ Y) - target, (w @ Y) - target)),
        "step": step,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--element", default="O")
    parser.add_argument("--ion-stage", type=int, default=7)
    parser.add_argument("--source-levels", default="2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20")
    parser.add_argument("--forbidden-level", type=int, default=2)
    parser.add_argument("--intercombination-levels", default="3,4,5")
    parser.add_argument("--resonance-level", type=int, default=7)
    parser.add_argument("--cascade-max-depth", type=int, default=50)
    parser.add_argument("--cascade-min-probability", type=float, default=0.0)
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--out-dir", default="o7_cascade_source_fit")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-format", default="npz", choices=["npz", "pickle"])
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_yield_csv = out_dir / "o7_cascade_yield_matrix.csv"
    out_weights_csv = out_dir / "o7_source_fit_weights.csv"
    out_summary_json = out_dir / "o7_source_fit_summary.json"

    z = choose_z(args.element)
    source_levels = parse_level_list(args.source_levels)
    i_levels = parse_level_list(args.intercombination_levels)
    f_level = int(args.forbidden_level)
    r_level = int(args.resonance_level)

    db = ATDB(args.fitsfile)
    records = db.select_records(
        z=z,
        ion_stage=args.ion_stage,
        data_type=[6, 50, 67, 68, 69],
        use_cache=args.index_cache,
        cache_format=args.index_cache_format,
    )
    level_rows = extract_levels(db, records, z, args.ion_stage)
    line_rows = extract_lines(db, records, z, args.ion_stage)
    labels = {int(row["level_index"]): row.get("level_label", "") for row in level_rows if row.get("level_index") is not None}
    gs = {int(row["level_index"]): (safe_float(row.get("statistical_weight_g")) or 1.0) for row in level_rows if row.get("level_index") is not None}

    branches, total_A = build_radiative_branching(line_rows)

    yield_rows: List[dict] = []
    Y_rows: List[List[float]] = []
    valid_sources: List[int] = []
    path_counts: Dict[int, int] = {}
    for lev in source_levels:
        visits, paths = cascade_probabilities_from_seed(
            int(lev), branches, max_depth=args.cascade_max_depth, min_probability=args.cascade_min_probability
        )
        y_f = float(visits.get(f_level, 0.0))
        y_i_components = {int(i): float(visits.get(int(i), 0.0)) for i in i_levels}
        y_i = float(sum(y_i_components.values()))
        y_r = float(visits.get(r_level, 0.0))
        row = {
            "source_level": int(lev),
            "source_label": labels.get(int(lev), ""),
            "statistical_weight_g": gs.get(int(lev), 1.0),
            "Y_forbidden": y_f,
            "Y_intercombination": y_i,
            "Y_resonance": y_r,
            "Y_triplet_sum": y_f + y_i,
            "Y_total_fir": y_f + y_i + y_r,
            "Y_R_f_over_i": (y_f / y_i) if y_i > 0.0 else None,
            "Y_G_f_plus_i_over_r": ((y_f + y_i) / y_r) if y_r > 0.0 else None,
            "cascade_path_rows": len(paths),
            "A_total_from_source_s^-1": total_A.get(int(lev), 0.0),
        }
        for i in i_levels:
            row[f"Y_i_level_{int(i)}"] = y_i_components[int(i)]
        yield_rows.append(row)
        valid_sources.append(int(lev))
        Y_rows.append([y_f, y_i, y_r])
        path_counts[int(lev)] = len(paths)

    Y = np.asarray(Y_rows, dtype=float)
    xstar = read_xstar_triplet_ratios(Path(args.xstar_lines_csv), args.xstar_value_column)
    if not xstar.get("available") or xstar.get("R_f_over_i") is None or xstar.get("G_f_plus_i_over_r") is None:
        raise SystemExit(f"Could not read XSTAR O VII triplet R/G reference from {args.xstar_lines_csv}")

    R_x = float(xstar["R_f_over_i"])
    G_x = float(xstar["G_f_plus_i_over_r"])
    target_raw = np.asarray([R_x, 1.0, (R_x + 1.0) / G_x], dtype=float)
    target = normalize_positive(target_raw)

    stat_weights = normalize_positive([gs.get(int(lev), 1.0) for lev in valid_sources])
    fit_weights, fit_info = fit_nonnegative_simplex(Y, target)

    stat_pred = stat_weights @ Y if len(stat_weights) else np.zeros(3)
    fit_pred = fit_weights @ Y if len(fit_weights) else np.zeros(3)
    stat_ratios = ratios_from_components(stat_pred)
    fit_ratios = ratios_from_components(fit_pred)
    target_ratios = ratios_from_components(target)

    weights_rows: List[dict] = []
    for idx, lev in enumerate(valid_sources):
        stat_w = float(stat_weights[idx]) if idx < len(stat_weights) else 0.0
        fit_w = float(fit_weights[idx]) if idx < len(fit_weights) else 0.0
        y_f, y_i, y_r = Y[idx]
        weights_rows.append({
            "source_level": int(lev),
            "source_label": labels.get(int(lev), ""),
            "statistical_weight_g": gs.get(int(lev), 1.0),
            "statistical_weight_norm": stat_w,
            "fit_weight_norm": fit_w,
            "fit_over_statistical": (fit_w / stat_w) if stat_w > 0 else None,
            "Y_forbidden": y_f,
            "Y_intercombination": y_i,
            "Y_resonance": y_r,
            "stat_contribution_forbidden": stat_w * y_f,
            "stat_contribution_intercombination": stat_w * y_i,
            "stat_contribution_resonance": stat_w * y_r,
            "fit_contribution_forbidden": fit_w * y_f,
            "fit_contribution_intercombination": fit_w * y_i,
            "fit_contribution_resonance": fit_w * y_r,
            "cascade_path_rows": path_counts.get(int(lev), 0),
        })

    # Sort the weight table by fitted importance while keeping all source levels.
    weights_rows.sort(key=lambda row: float(row.get("fit_weight_norm") or 0.0), reverse=True)

    write_csv(out_yield_csv, yield_rows)
    write_csv(out_weights_csv, weights_rows)

    summary = {
        "fitsfile": args.fitsfile,
        "element": args.element,
        "ion_stage": args.ion_stage,
        "source_levels": valid_sources,
        "triplet_component_levels": {
            "forbidden": f_level,
            "intercombination": i_levels,
            "resonance": r_level,
        },
        "xstar_reference": xstar,
        "target_components_normalized": {
            "forbidden": float(target[0]),
            "intercombination": float(target[1]),
            "resonance": float(target[2]),
            **target_ratios,
        },
        "statistical_prediction": {
            "weights": "normalized statistical weights over source_levels",
            "components": {
                "forbidden": float(stat_pred[0]),
                "intercombination": float(stat_pred[1]),
                "resonance": float(stat_pred[2]),
            },
            **stat_ratios,
            "R_over_xstar": (stat_ratios.get("R_f_over_i") / R_x) if stat_ratios.get("R_f_over_i") is not None else None,
            "G_over_xstar": (stat_ratios.get("G_f_plus_i_over_r") / G_x) if stat_ratios.get("G_f_plus_i_over_r") is not None else None,
        },
        "fitted_prediction": {
            "method": "projected-gradient nonnegative simplex fit",
            "fit_info": fit_info,
            "components": {
                "forbidden": float(fit_pred[0]),
                "intercombination": float(fit_pred[1]),
                "resonance": float(fit_pred[2]),
            },
            **fit_ratios,
            "R_over_xstar": (fit_ratios.get("R_f_over_i") / R_x) if fit_ratios.get("R_f_over_i") is not None else None,
            "G_over_xstar": (fit_ratios.get("G_f_plus_i_over_r") / G_x) if fit_ratios.get("G_f_plus_i_over_r") is not None else None,
        },
        "outputs": {
            "yield_matrix_csv": str(out_yield_csv),
            "source_fit_weights_csv": str(out_weights_csv),
            "summary_json": str(out_summary_json),
        },
        "note": "Diagnostic fit only: decoded O VIII -> O VII recombination records are total rates, not true level-resolved recombination feeds.",
    }
    out_summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("O VII cascade source-fit diagnostic")
    print("-----------------------------------")
    print(f"Wrote yield matrix: {out_yield_csv}")
    print(f"Wrote source weights: {out_weights_csv}")
    print(f"Wrote summary: {out_summary_json}")
    print(f"XSTAR R={R_x:.6g} G={G_x:.6g}")
    print(f"Statistical R={stat_ratios.get('R_f_over_i'):.6g} G={stat_ratios.get('G_f_plus_i_over_r'):.6g}")
    print(f"Fitted R={fit_ratios.get('R_f_over_i'):.6g} G={fit_ratios.get('G_f_plus_i_over_r'):.6g}")
    if args.print_summary:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
