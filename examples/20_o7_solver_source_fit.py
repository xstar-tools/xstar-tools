#!/usr/bin/env python3
"""Fit empirical O VII source weights against the full level-population solver.

This Stage-6 diagnostic is stricter than ``19_o7_cascade_source_fit.py``.  The
older source-fit example fits weights against a *radiative cascade yield matrix*
only.  This example instead builds a solver response matrix by injecting a unit
source into each selected O VII level, running ``xstar_atomic.solver``, reading
its O VII triplet R/G outputs, and fitting nonnegative source weights against
those full statistical-equilibrium responses.

The fitted weights remain empirical/diagnostic.  They are intended for testing
whether the current radiative+collisional solver network can reproduce the
XSTAR O VII triplet ratios when supplied with a fitted level-source distribution.
They are not physical level-resolved recombination rates.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np


def _maybe_float(value) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def parse_level_list(text: str) -> List[int]:
    out: List[int] = []
    for part in str(text).replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
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


def fit_nonnegative_simplex(Y: np.ndarray, target: np.ndarray, max_iter: int = 50000, tol: float = 1e-13) -> Tuple[np.ndarray, dict]:
    n = int(Y.shape[0])
    if n == 0:
        return np.array([], dtype=float), {"status": "empty_response_matrix"}
    w = np.full(n, 1.0 / n, dtype=float)
    try:
        spectral = float(np.linalg.norm(Y, ord=2))
    except Exception:
        spectral = float(np.linalg.norm(Y))
    step = 1.0 / max(2.0 * spectral * spectral, 1e-30)
    prev = float("inf")
    status = "max_iter"
    it = 0
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
        "iterations": int(it + 1),
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


def read_triplet_csv(path: Path) -> dict:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        return {"forbidden": 0.0, "intercombination": 0.0, "resonance": 0.0, "R_f_over_i": None, "G_f_plus_i_over_r": None}
    row = rows[0]
    return {
        "forbidden": float(row.get("forbidden_energy_per_ion_erg_s^-1") or 0.0),
        "intercombination": float(row.get("intercombination_energy_per_ion_erg_s^-1") or 0.0),
        "resonance": float(row.get("resonance_energy_per_ion_erg_s^-1") or 0.0),
        "R_f_over_i": _maybe_float(row.get("R_f_over_i")),
        "G_f_plus_i_over_r": _maybe_float(row.get("G_f_plus_i_over_r")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--element", default="O")
    parser.add_argument("--ion-stage", type=int, default=7)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-density", type=float, default=1.0)
    parser.add_argument("--source-levels", default="2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20")
    parser.add_argument("--source-rate", type=float, default=1.0, help="Unit source rate injected into each level while building the response matrix")
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto"], default="sparse")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--out-dir", default="o7_solver_source_fit")
    parser.add_argument("--keep-unit-runs", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    unit_dir = out_dir / "unit_source_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    unit_dir.mkdir(parents=True, exist_ok=True)

    source_levels = parse_level_list(args.source_levels)
    xstar = read_xstar_triplet_ratios(Path(args.xstar_lines_csv), args.xstar_value_column)
    if not xstar.get("available") or xstar.get("R_f_over_i") is None or xstar.get("G_f_plus_i_over_r") is None:
        raise SystemExit(f"Could not read XSTAR O VII triplet R/G reference from {args.xstar_lines_csv}")
    R_x = float(xstar["R_f_over_i"])
    G_x = float(xstar["G_f_plus_i_over_r"])
    target_raw = np.asarray([R_x, 1.0, (R_x + 1.0) / G_x], dtype=float)
    target = normalize_positive(target_raw)

    response_rows: List[dict] = []
    Y_rows: List[List[float]] = []
    valid_levels: List[int] = []
    for lev in source_levels:
        triplet_csv = unit_dir / f"level_{lev}_triplet.csv"
        lines_csv = unit_dir / f"level_{lev}_lines.csv"
        summary_json = unit_dir / f"level_{lev}_summary.json"
        cmd = [
            sys.executable, "-m", "xstar_atomic.solver", str(args.fitsfile),
            "--element", str(args.element), "--ion-stage", str(int(args.ion_stage)),
            "--temperatures", f"{float(args.temperature):.16g}",
            "--electron-densities", f"{float(args.electron_density):.16g}",
            "--wavelength-min", f"{float(args.wavelength_min):.16g}",
            "--wavelength-max", f"{float(args.wavelength_max):.16g}",
            "--source-level", str(int(lev)), f"{float(args.source_rate):.16g}",
            "--linear-solver", args.linear_solver,
            "--out-lines-csv", str(lines_csv),
            "--out-triplet-csv", str(triplet_csv),
            "--summary-json", str(summary_json),
        ]
        if args.index_cache:
            cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]
        subprocess.run(cmd, check=True)
        trip = read_triplet_csv(triplet_csv)
        raw = np.asarray([trip["forbidden"], trip["intercombination"], trip["resonance"]], dtype=float)
        response = normalize_positive(raw)
        valid_levels.append(int(lev))
        Y_rows.append([float(response[0]), float(response[1]), float(response[2])])
        response_rows.append({
            "source_level": int(lev),
            "unit_source_rate_s^-1": float(args.source_rate),
            "raw_forbidden": float(raw[0]),
            "raw_intercombination": float(raw[1]),
            "raw_resonance": float(raw[2]),
            "response_forbidden_norm": float(response[0]),
            "response_intercombination_norm": float(response[1]),
            "response_resonance_norm": float(response[2]),
            "response_R_f_over_i": trip.get("R_f_over_i"),
            "response_G_f_plus_i_over_r": trip.get("G_f_plus_i_over_r"),
            "triplet_csv": str(triplet_csv),
            "lines_csv": str(lines_csv),
            "summary_json": str(summary_json),
        })

    Y = np.asarray(Y_rows, dtype=float)
    fit_weights, fit_info = fit_nonnegative_simplex(Y, target)
    uniform_weights = np.full(len(valid_levels), 1.0 / len(valid_levels), dtype=float) if valid_levels else np.array([])
    fit_pred = fit_weights @ Y if len(fit_weights) else np.zeros(3)
    uniform_pred = uniform_weights @ Y if len(uniform_weights) else np.zeros(3)
    fit_ratios = ratios_from_components(fit_pred)
    uniform_ratios = ratios_from_components(uniform_pred)
    target_ratios = ratios_from_components(target)

    weight_rows: List[dict] = []
    for idx, lev in enumerate(valid_levels):
        row = {
            "source_level": int(lev),
            "fit_weight_norm": float(fit_weights[idx]),
            "solver_fit_weight_norm": float(fit_weights[idx]),
            "uniform_weight_norm": float(uniform_weights[idx]),
            "response_forbidden_norm": float(Y[idx, 0]),
            "response_intercombination_norm": float(Y[idx, 1]),
            "response_resonance_norm": float(Y[idx, 2]),
            "fit_contribution_forbidden": float(fit_weights[idx] * Y[idx, 0]),
            "fit_contribution_intercombination": float(fit_weights[idx] * Y[idx, 1]),
            "fit_contribution_resonance": float(fit_weights[idx] * Y[idx, 2]),
        }
        weight_rows.append(row)
    weight_rows.sort(key=lambda row: float(row.get("fit_weight_norm") or 0.0), reverse=True)

    out_response = out_dir / "o7_solver_response_matrix.csv"
    out_weights = out_dir / "o7_solver_source_fit_weights.csv"
    out_weights_compat = out_dir / "o7_source_fit_weights.csv"
    out_summary = out_dir / "o7_solver_source_fit_summary.json"
    write_csv(out_response, response_rows)
    write_csv(out_weights, weight_rows)
    write_csv(out_weights_compat, weight_rows)

    summary = {
        "fitsfile": args.fitsfile,
        "element": args.element,
        "ion_stage": args.ion_stage,
        "temperature_K": args.temperature,
        "electron_density_cm^-3": args.electron_density,
        "source_levels": valid_levels,
        "xstar_reference": xstar,
        "target_components_normalized": {
            "forbidden": float(target[0]),
            "intercombination": float(target[1]),
            "resonance": float(target[2]),
            **target_ratios,
        },
        "uniform_prediction": {
            "components": {
                "forbidden": float(uniform_pred[0]),
                "intercombination": float(uniform_pred[1]),
                "resonance": float(uniform_pred[2]),
            },
            **uniform_ratios,
            "R_over_xstar": (uniform_ratios.get("R_f_over_i") / R_x) if uniform_ratios.get("R_f_over_i") is not None else None,
            "G_over_xstar": (uniform_ratios.get("G_f_plus_i_over_r") / G_x) if uniform_ratios.get("G_f_plus_i_over_r") is not None else None,
        },
        "fitted_prediction": {
            "method": "projected-gradient nonnegative simplex fit to full solver unit-source response matrix",
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
            "solver_response_matrix_csv": str(out_response),
            "solver_source_fit_weights_csv": str(out_weights),
            "source_fit_weights_compatible_csv": str(out_weights_compat),
            "summary_json": str(out_summary),
        },
        "note": "Diagnostic only: these are empirical solver-response weights, not true level-resolved recombination rates.",
    }
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if not args.keep_unit_runs:
        # Keep the top-level response/weights/summary, but remove bulky per-level solver files.
        for p in unit_dir.glob("*"):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            unit_dir.rmdir()
        except OSError:
            pass

    print("O VII full-solver source-fit diagnostic")
    print("--------------------------------------")
    print(f"Wrote response matrix: {out_response}")
    print(f"Wrote solver-fit weights: {out_weights}")
    print(f"Wrote compatible weights: {out_weights_compat}")
    print(f"Wrote summary: {out_summary}")
    print(f"XSTAR R={R_x:.6g} G={G_x:.6g}")
    print(f"Uniform R={uniform_ratios.get('R_f_over_i'):.6g} G={uniform_ratios.get('G_f_plus_i_over_r'):.6g}")
    print(f"Fitted R={fit_ratios.get('R_f_over_i'):.6g} G={fit_ratios.get('G_f_plus_i_over_r'):.6g}")
    if args.print_summary:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
