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
They are not physical level-resolved recombination rates.  Because the current
solver keeps a normalized O VII population while adding external source terms,
the fitted weights are valid for the source amplitude used in this script.  The
fit is performed with the raw triplet response amplitudes, then the combined
triplet vector is normalized only when comparing to the XSTAR R/G target.  After
fitting, the script also runs one simultaneous combined-source validation solve
using the fitted weights and reports its R/G values and matrix diagnostics.
When passing the weights to ``examples/13_o7_recombination_cascade_workflow.py``,
use ``--solver-source-total-rate`` to match the source amplitude used here.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import shutil
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


def _fmt_float(value, precision: int = 6) -> str:
    value = _maybe_float(value)
    if value is None:
        return "NA"
    return f"{value:.{precision}g}"




def ion_output_prefix(element: str, ion_stage: int) -> str:
    return f"{str(element).strip().lower()}{int(ion_stage)}"


def write_ion_specific_alias(src: Path, prefix: str, legacy_stem: str) -> Path | None:
    """Write a non-O VII alias next to a legacy o7_* output file.

    The Stage-6 workflow historically used o7_* filenames.  Keep those names
    for backward compatibility with downstream examples, but for candidate
    non-O VII He-like ions also create clearer aliases such as
    c5_solver_source_fit_summary.json.
    """
    if prefix == "o7":
        return None
    if not src.exists():
        return None
    alias = src.with_name(src.name.replace(legacy_stem, prefix, 1))
    if alias == src:
        return None
    shutil.copy2(src, alias)
    return alias

def parse_level_list(text: str) -> List[int]:
    out: List[int] = []
    for part in str(text).replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


def _roman_to_int(text: str) -> Optional[int]:
    text = str(text).strip().upper()
    if not text:
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    prev = 0
    for ch in reversed(text):
        val = values.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total


def _expected_ion_aliases(element: str, ion_stage: int) -> set[str]:
    symbol = str(element).strip().lower()
    aliases = {f"{symbol}{int(ion_stage)}"}
    roman = {
        1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii",
        8: "viii", 9: "ix", 10: "x", 11: "xi", 12: "xii", 13: "xiii",
        14: "xiv", 15: "xv", 16: "xvi", 17: "xvii", 18: "xviii", 19: "xix",
        20: "xx", 21: "xxi", 22: "xxii", 23: "xxiii", 24: "xxiv", 25: "xxv",
    }.get(int(ion_stage))
    if roman:
        aliases.add(f"{symbol}{roman}")
    return aliases


def _normalize_ion_text(text: str) -> str:
    return str(text or "").strip().lower().replace(" ", "").replace("_", "")


def _classify_helike_triplet_row(row: dict, wavelength: Optional[float] = None,
                                  element: str = "O", ion_stage: int = 7) -> Optional[str]:
    """Classify He-like f/i/r components from XSTAR line labels.

    The converted XSTAR line CSVs for O VII, C V, Mg XI, and similar He-like
    ions carry lower/upper configuration labels.  Use those labels first so the
    reader is ion-generic; retain O VII wavelength matching only as a fallback
    for old O VII reference CSVs that did not include labels.
    """
    lower = str(row.get("lower_level", "") or row.get("lower", "")).replace(" ", "")
    upper = str(row.get("upper_level", "") or row.get("upper", "")).replace(" ", "")
    if "1s2.1S_0" in lower or "1s2" in lower:
        if "1s1.2s1.3S_1" in upper or "2s1.3S_1" in upper:
            return "f"
        if "1s1.2p1.1P_1" in upper or "2p1.1P_1" in upper:
            return "r"
        if "1s1.2p1.3P_" in upper or "2p1.3P_" in upper:
            return "i"
    # Backward-compatible O VII wavelength fallback.
    if str(element).strip().lower() == "o" and int(ion_stage) == 7 and wavelength is not None:
        if abs(wavelength - 22.1012) < 0.03:
            return "f"
        if abs(wavelength - 21.8070) < 0.04 or abs(wavelength - 21.8044) < 0.04:
            return "i"
        if abs(wavelength - 21.6020) < 0.03:
            return "r"
    return None


def read_xstar_triplet_ratios(path: Path, value_column: str = "emit_outward",
                              element: str = "O", ion_stage: int = 7) -> dict:
    totals = {"f": 0.0, "i": 0.0, "r": 0.0}
    counts = {"f": 0, "i": 0, "r": 0}
    if not path.exists():
        return {"available": False, "path": str(path)}
    aliases = _expected_ion_aliases(element, int(ion_stage))
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ion_text = _normalize_ion_text(row.get("ion", ""))
            if ion_text and ion_text not in aliases:
                # Some hand-written references omit ion labels; real converted
                # XSTAR CSVs include them and should match the requested ion.
                continue
            wav = _maybe_float(row.get("wavelength") or row.get("wavelength_A"))
            val = _maybe_float(row.get(value_column))
            if val is None:
                continue
            kind = _classify_helike_triplet_row(row, wav, element=element, ion_stage=int(ion_stage))
            if kind is None:
                continue
            totals[kind] += val
            counts[kind] += 1
    f, i, r = totals["f"], totals["i"], totals["r"]
    return {
        "available": True,
        "path": str(path),
        "element": element,
        "ion_stage": int(ion_stage),
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


def fit_raw_response_simplex(raw_response: np.ndarray, target_norm: np.ndarray, max_iter: int = 50000, tol: float = 1e-13) -> Tuple[np.ndarray, dict]:
    """Fit simplex weights using raw full-solver triplet amplitudes.

    The v0.2.54--v0.2.59 solver-source diagnostic fitted weights to per-level
    normalized response fractions.  That can reproduce R/G inside the diagnostic
    table but not necessarily when the same weights are injected simultaneously
    into the solver, because different source levels have different raw triplet
    yields per unit source.

    For a combined raw response p = sum_i w_i y_i, matching the XSTAR triplet
    fractions t requires p to be parallel to t, i.e.

        sum_i w_i (y_i - t sum_j y_ij) = 0.

    This is a linear least-squares problem on the nonnegative simplex after the
    rows are globally rescaled for numerical conditioning.
    """
    Y = np.asarray(raw_response, dtype=float)
    n = int(Y.shape[0])
    if n == 0:
        return np.array([], dtype=float), {"status": "empty_response_matrix"}
    target = np.asarray(target_norm, dtype=float)
    target = target / max(float(target.sum()), 1e-300)
    row_sums = np.sum(Y, axis=1)
    scale = float(np.nanmax(np.where(np.isfinite(row_sums) & (row_sums > 0.0), row_sums, 0.0)))
    if not np.isfinite(scale) or scale <= 0.0:
        return np.full(n, 1.0 / n, dtype=float), {"status": "zero_raw_response_matrix"}
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


def format_optional_float(value, precision: int = 6) -> str:
    """Format a diagnostic value that may be missing.

    Non-O VII exploratory He-like runs can legitimately have incomplete
    solver-side triplet diagnostics while the XSTAR target was read
    successfully.  Printing these values must not abort the density-grid
    workflow; the summary JSON/CSV keep the missing values as null/blank.
    """
    val = _maybe_float(value)
    if val is None:
        return "NA"
    return f"{val:.{int(precision)}g}"


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


def _first_solve_info(summary: dict) -> dict:
    solves = summary.get("solves") or []
    return dict(solves[0]) if solves else {}


def _extract_solver_diagnostics(summary: dict) -> dict:
    info = _first_solve_info(summary)
    keys = [
        "solver",
        "solver_warning",
        "matrix_rank",
        "matrix_size",
        "condition_number",
        "linear_residual_l2",
        "linear_residual_linf",
        "residual_l2_threshold",
        "residual_linf_threshold",
        "residual_rejected",
        "negative_population_action",
        "negative_population_tol",
        "n_negative_populations_raw",
        "n_significant_negative_populations_raw",
        "min_population_raw",
        "sum_negative_populations_raw_abs",
        "n_levels_in_this_solve",
        "null_rate_pruning_diagnostics",
    ]
    out = {key: info.get(key) for key in keys if key in info}
    ss = summary.get("source_sink_summaries") or []
    if ss:
        out["source_sink_summary"] = ss[0]
    return out


def write_combined_source_csv(path: Path, levels: Sequence[int], weights: Sequence[float], total_rate: float, temperature: float, electron_density: float) -> None:
    rows = []
    for lev, w in zip(levels, weights):
        rate = float(total_rate) * float(w)
        if rate <= 0.0:
            continue
        rows.append({
            "temperature_K": float(temperature),
            "electron_density_cm^-3": float(electron_density),
            "level_index": int(lev),
            "source_s^-1": rate,
            "fit_weight_norm": float(w),
        })
    write_csv(path, rows)




def append_collision_scale_args(cmd: List[str], args) -> None:
    """Append diagnostic collision-rate scaling options for solver subprocesses."""
    if getattr(args, "collision_rate_scale", 1.0) not in (None, 1.0):
        cmd += ["--collision-rate-scale", f"{float(args.collision_rate_scale):.16g}"]
    for spec in getattr(args, "collision_data_type_scale", []) or []:
        cmd += ["--collision-data-type-scale", str(spec)]
    for spec in getattr(args, "collision_pair_scale", []) or []:
        cmd += ["--collision-pair-scale", str(spec)]
    for spec in getattr(args, "collision_record_scale", []) or []:
        cmd += ["--collision-record-scale", str(spec)]
    for spec in getattr(args, "collision_record_direction_scale", []) or []:
        cmd += ["--collision-record-direction-scale", str(spec)]
    mode = getattr(args, "collision_type69_ground_excitation_mode", "include") or "include"
    if mode != "include":
        cmd += ["--collision-type69-ground-excitation-mode", str(mode)]

def run_combined_source_validation(args, levels: Sequence[int], weights: Sequence[float], out_dir: Path) -> dict:
    validation_dir = out_dir / "combined_source_validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    source_csv = validation_dir / "o7_combined_fitted_sources.csv"
    lines_csv = validation_dir / "o7_combined_solver_lines.csv"
    triplet_csv = validation_dir / "o7_combined_solver_triplet.csv"
    summary_json = validation_dir / "o7_combined_solver_summary.json"
    total_rate = float(args.combined_source_total_rate if args.combined_source_total_rate is not None else args.source_rate)
    write_combined_source_csv(source_csv, levels, weights, total_rate, args.temperature, args.electron_density)
    cmd = [
        sys.executable, "-m", "xstar_atomic.solver", str(args.fitsfile),
        "--element", str(args.element), "--ion-stage", str(int(args.ion_stage)),
        "--temperatures", f"{float(args.temperature):.16g}",
        "--electron-densities", f"{float(args.electron_density):.16g}",
        "--wavelength-min", f"{float(args.wavelength_min):.16g}",
        "--wavelength-max", f"{float(args.wavelength_max):.16g}",
        "--source-csv", str(source_csv),
        "--linear-solver", args.linear_solver,
        "--rank-deficient-action", args.rank_deficient_action,
        "--negative-population-action", args.negative_population_action,
        "--negative-population-tol", f"{float(args.negative_population_tol):.16g}",
        "--out-lines-csv", str(lines_csv),
        "--out-triplet-csv", str(triplet_csv),
        "--summary-json", str(summary_json),
    ]
    if args.residual_l2_max is not None:
        cmd += ["--residual-l2-max", f"{float(args.residual_l2_max):.16g}"]
    if args.residual_linf_max is not None:
        cmd += ["--residual-linf-max", f"{float(args.residual_linf_max):.16g}"]
    if args.reject_large_residual:
        cmd += ["--reject-large-residual"]
    if args.prune_null_rate_levels:
        cmd += ["--prune-null-rate-levels", "--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
    append_collision_scale_args(cmd, args)
    if args.index_cache:
        if args.index_cache_path:
            cmd += ["--index-cache", str(args.index_cache_path), "--index-cache-format", args.index_cache_format]
        else:
            cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]
    subprocess.run(cmd, check=True)
    trip = read_triplet_csv(triplet_csv)
    summary = json.loads(summary_json.read_text(encoding="utf-8")) if summary_json.exists() else {}
    return {
        "enabled": True,
        "source_total_rate_s^-1": total_rate,
        "source_csv": str(source_csv),
        "lines_csv": str(lines_csv),
        "triplet_csv": str(triplet_csv),
        "summary_json": str(summary_json),
        "triplet_components": {
            "forbidden": trip.get("forbidden"),
            "intercombination": trip.get("intercombination"),
            "resonance": trip.get("resonance"),
        },
        "R_f_over_i": trip.get("R_f_over_i"),
        "G_f_plus_i_over_r": trip.get("G_f_plus_i_over_r"),
        "solver_diagnostics": _extract_solver_diagnostics(summary),
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
    parser.add_argument("--skip-combined-validation", action="store_true",
                        help="Skip the simultaneous combined-source validation solve after fitting weights")
    parser.add_argument("--combined-source-total-rate", type=float,
                        help="Total source rate used for the combined validation solve; defaults to --source-rate")
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep",
                        help="Diagnostic default is keep so the fitted response remains a linear solver response rather than a clipped nonlinear response.")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--residual-l2-max", type=float)
    parser.add_argument("--residual-linf-max", type=float)
    parser.add_argument("--reject-large-residual", action="store_true")
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--collision-rate-scale", type=float, default=1.0,
                        help="Diagnostic scale factor passed to xstar_atomic.solver for all electron-impact collision rates.")
    parser.add_argument("--collision-data-type-scale", action="append", default=[], metavar="DATA_TYPE:SCALE",
                        help="Diagnostic scale passed to xstar_atomic.solver for one collision data type, e.g. 68:0.5. May be repeated.")
    parser.add_argument("--collision-pair-scale", action="append", default=[], metavar="LEVEL1:LEVEL2:SCALE",
                        help="Diagnostic symmetric pair-rate scale passed to xstar_atomic.solver, e.g. 2:4:0.5. May be repeated.")
    parser.add_argument("--collision-record-scale", action="append", default=[], metavar="RECORD:SCALE",
                        help="Diagnostic collision-record scale passed to xstar_atomic.solver, e.g. 12345:0.5. May be repeated.")
    parser.add_argument("--collision-record-direction-scale", action="append", default=[], metavar="RECORD:DIRECTION:SCALE",
                        help="Diagnostic direction-specific record scale passed to xstar_atomic.solver, e.g. 22490:deexcitation:0.0. May be repeated.")
    parser.add_argument("--collision-type69-ground-excitation-mode",
                        choices=["include", "suppress-resonance", "suppress-all"],
                        default="include",
                        help=("Diagnostic/experimental handling of type-69 excitation out of the ground level. "
                              "suppress-resonance suppresses ground -> He-like resonance-upper-level excitation "
                              "while preserving de-excitation; suppress-all suppresses all type-69 ground excitation."))
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path", help="Explicit hierarchy index-cache filename passed to xstar_atomic.solver. Use this to keep the cache away from atdb.fits.")
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
    xstar = read_xstar_triplet_ratios(Path(args.xstar_lines_csv), args.xstar_value_column, element=args.element, ion_stage=args.ion_stage)
    if not xstar.get("available") or xstar.get("R_f_over_i") is None or xstar.get("G_f_plus_i_over_r") is None:
        raise SystemExit(f"Could not read XSTAR He-like triplet R/G reference for {args.element} {args.ion_stage} from {args.xstar_lines_csv}")
    R_x = float(xstar["R_f_over_i"])
    G_x = float(xstar["G_f_plus_i_over_r"])
    target_raw = np.asarray([R_x, 1.0, (R_x + 1.0) / G_x], dtype=float)
    target = normalize_positive(target_raw)

    response_rows: List[dict] = []
    Y_rows: List[List[float]] = []
    raw_rows: List[List[float]] = []
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
            "--rank-deficient-action", args.rank_deficient_action,
            "--negative-population-action", args.negative_population_action,
            "--negative-population-tol", f"{float(args.negative_population_tol):.16g}",
            "--out-lines-csv", str(lines_csv),
            "--out-triplet-csv", str(triplet_csv),
            "--summary-json", str(summary_json),
        ]
        if args.residual_l2_max is not None:
            cmd += ["--residual-l2-max", f"{float(args.residual_l2_max):.16g}"]
        if args.residual_linf_max is not None:
            cmd += ["--residual-linf-max", f"{float(args.residual_linf_max):.16g}"]
        if args.reject_large_residual:
            cmd += ["--reject-large-residual"]
        if args.prune_null_rate_levels:
            cmd += ["--prune-null-rate-levels", "--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
        append_collision_scale_args(cmd, args)
        if args.index_cache:
            if args.index_cache_path:
                cmd += ["--index-cache", str(args.index_cache_path), "--index-cache-format", args.index_cache_format]
            else:
                cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]
        subprocess.run(cmd, check=True)
        trip = read_triplet_csv(triplet_csv)
        raw = np.asarray([trip["forbidden"], trip["intercombination"], trip["resonance"]], dtype=float)
        response = normalize_positive(raw)
        valid_levels.append(int(lev))
        Y_rows.append([float(response[0]), float(response[1]), float(response[2])])
        raw_rows.append([float(raw[0]), float(raw[1]), float(raw[2])])
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
    Y_raw = np.asarray(raw_rows, dtype=float)
    fit_weights, fit_info = fit_raw_response_simplex(Y_raw, target)
    uniform_weights = np.full(len(valid_levels), 1.0 / len(valid_levels), dtype=float) if valid_levels else np.array([])
    fit_pred_raw = fit_weights @ Y_raw if len(fit_weights) else np.zeros(3)
    uniform_pred_raw = uniform_weights @ Y_raw if len(uniform_weights) else np.zeros(3)
    fit_pred = normalize_positive(fit_pred_raw)
    uniform_pred = normalize_positive(uniform_pred_raw)
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
            "fit_source_rate_s^-1": float(args.source_rate),
            "response_forbidden_norm": float(Y[idx, 0]),
            "response_intercombination_norm": float(Y[idx, 1]),
            "response_resonance_norm": float(Y[idx, 2]),
            "raw_forbidden_per_unit_source": float(Y_raw[idx, 0]),
            "raw_intercombination_per_unit_source": float(Y_raw[idx, 1]),
            "raw_resonance_per_unit_source": float(Y_raw[idx, 2]),
            "fit_raw_contribution_forbidden": float(fit_weights[idx] * Y_raw[idx, 0]),
            "fit_raw_contribution_intercombination": float(fit_weights[idx] * Y_raw[idx, 1]),
            "fit_raw_contribution_resonance": float(fit_weights[idx] * Y_raw[idx, 2]),
            "fit_contribution_forbidden": float(fit_weights[idx] * Y[idx, 0]),
            "fit_contribution_intercombination": float(fit_weights[idx] * Y[idx, 1]),
            "fit_contribution_resonance": float(fit_weights[idx] * Y[idx, 2]),
        }
        weight_rows.append(row)
    weight_rows.sort(key=lambda row: float(row.get("fit_weight_norm") or 0.0), reverse=True)

    output_prefix = ion_output_prefix(args.element, int(args.ion_stage))
    out_response = out_dir / "o7_solver_response_matrix.csv"
    out_weights = out_dir / "o7_solver_source_fit_weights.csv"
    out_weights_compat = out_dir / "o7_source_fit_weights.csv"
    out_summary = out_dir / "o7_solver_source_fit_summary.json"
    combined_validation = {"enabled": False, "reason": "disabled_by_--skip-combined-validation"}
    if not args.skip_combined_validation:
        combined_validation = run_combined_source_validation(args, valid_levels, fit_weights, out_dir)
        combined_R = combined_validation.get("R_f_over_i")
        combined_G = combined_validation.get("G_f_plus_i_over_r")
        combined_validation["R_over_xstar"] = (combined_R / R_x) if combined_R is not None else None
        combined_validation["G_over_xstar"] = (combined_G / G_x) if combined_G is not None else None
        combined_validation["delta_R_vs_fitted_linear_response"] = (combined_R - fit_ratios.get("R_f_over_i")) if combined_R is not None and fit_ratios.get("R_f_over_i") is not None else None
        combined_validation["delta_G_vs_fitted_linear_response"] = (combined_G - fit_ratios.get("G_f_plus_i_over_r")) if combined_G is not None and fit_ratios.get("G_f_plus_i_over_r") is not None else None
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
        "source_rate_s^-1": float(args.source_rate),
        "solver_matrix_treatment": {
            "linear_solver": args.linear_solver,
            "rank_deficient_action": args.rank_deficient_action,
            "negative_population_action": args.negative_population_action,
            "negative_population_tol": float(args.negative_population_tol),
            "residual_l2_max": args.residual_l2_max,
            "residual_linf_max": args.residual_linf_max,
            "reject_large_residual": bool(args.reject_large_residual),
            "prune_null_rate_levels": bool(args.prune_null_rate_levels),
            "null_rate_floor_s^-1": float(args.null_rate_floor),
            "collision_rate_scale": float(args.collision_rate_scale),
            "collision_data_type_scale": list(args.collision_data_type_scale or []),
            "collision_pair_scale": list(args.collision_pair_scale or []),
            "collision_record_scale": list(args.collision_record_scale or []),
            "collision_record_direction_scale": list(args.collision_record_direction_scale or []),
            "collision_type69_ground_excitation_mode": args.collision_type69_ground_excitation_mode,
        },
        "source_rate_note": "The fitted weights are amplitude-dependent because the solver also has a normalized baseline population. When using these weights in examples/13, scale the solver source CSV so the first T/ne block has this same total source rate, e.g. --solver-source-total-rate equal to this value.",
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
            "raw_components": {
                "forbidden": float(uniform_pred_raw[0]),
                "intercombination": float(uniform_pred_raw[1]),
                "resonance": float(uniform_pred_raw[2]),
            },
            **uniform_ratios,
            "R_over_xstar": (uniform_ratios.get("R_f_over_i") / R_x) if uniform_ratios.get("R_f_over_i") is not None else None,
            "G_over_xstar": (uniform_ratios.get("G_f_plus_i_over_r") / G_x) if uniform_ratios.get("G_f_plus_i_over_r") is not None else None,
        },
        "fitted_prediction": {
            "method": "projected-gradient nonnegative simplex fit to raw full-solver unit-source response amplitudes; combined response normalized for R/G comparison",
            "fit_info": fit_info,
            "components": {
                "forbidden": float(fit_pred[0]),
                "intercombination": float(fit_pred[1]),
                "resonance": float(fit_pred[2]),
            },
            "raw_components": {
                "forbidden": float(fit_pred_raw[0]),
                "intercombination": float(fit_pred_raw[1]),
                "resonance": float(fit_pred_raw[2]),
            },
            **fit_ratios,
            "R_over_xstar": (fit_ratios.get("R_f_over_i") / R_x) if fit_ratios.get("R_f_over_i") is not None else None,
            "G_over_xstar": (fit_ratios.get("G_f_plus_i_over_r") / G_x) if fit_ratios.get("G_f_plus_i_over_r") is not None else None,
        },
        "combined_source_validation": combined_validation,
        "outputs": {
            "solver_response_matrix_csv": str(out_response),
            "solver_source_fit_weights_csv": str(out_weights),
            "source_fit_weights_compatible_csv": str(out_weights_compat),
            "summary_json": str(out_summary),
            "combined_validation_dir": str(out_dir / "combined_source_validation"),
        },
        "note": "Diagnostic only: these are empirical solver-response weights, not true level-resolved recombination rates.",
    }
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    alias_response = write_ion_specific_alias(out_response, output_prefix, "o7")
    alias_weights = write_ion_specific_alias(out_weights, output_prefix, "o7")
    alias_weights_compat = write_ion_specific_alias(out_weights_compat, output_prefix, "o7")
    alias_summary = write_ion_specific_alias(out_summary, output_prefix, "o7")
    summary["outputs"].update({
        "ion_output_prefix": output_prefix,
        "ion_specific_solver_response_matrix_csv": str(alias_response) if alias_response else str(out_response),
        "ion_specific_solver_source_fit_weights_csv": str(alias_weights) if alias_weights else str(out_weights),
        "ion_specific_source_fit_weights_compatible_csv": str(alias_weights_compat) if alias_weights_compat else str(out_weights_compat),
        "ion_specific_summary_json": str(alias_summary) if alias_summary else str(out_summary),
    })
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if alias_summary:
        alias_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

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

    print(f"{args.element} {args.ion_stage} full-solver source-fit diagnostic")
    print("--------------------------------------")
    print(f"Wrote response matrix: {out_response}")
    print(f"Wrote solver-fit weights: {out_weights}")
    print(f"Wrote compatible weights: {out_weights_compat}")
    print(f"Wrote summary: {out_summary}")
    if output_prefix != "o7":
        print(f"Wrote ion-specific summary alias: {out_dir / (output_prefix + '_solver_source_fit_summary.json')}")
    print(f"XSTAR R={R_x:.6g} G={G_x:.6g}")
    print(
        "Uniform "
        f"R={format_optional_float(uniform_ratios.get('R_f_over_i'))} "
        f"G={format_optional_float(uniform_ratios.get('G_f_plus_i_over_r'))}"
    )
    print(
        "Fitted linear-response "
        f"R={format_optional_float(fit_ratios.get('R_f_over_i'))} "
        f"G={format_optional_float(fit_ratios.get('G_f_plus_i_over_r'))}"
    )
    if combined_validation.get("enabled"):
        print(
            "Combined simultaneous-solver "
            f"R={format_optional_float(combined_validation.get('R_f_over_i'))} "
            f"G={format_optional_float(combined_validation.get('G_f_plus_i_over_r'))}"
        )
        diag = combined_validation.get("solver_diagnostics") or {}
        print(
            "Combined diagnostics: "
            f"rank={diag.get('matrix_rank')}/{diag.get('matrix_size')} "
            f"cond={diag.get('condition_number')} "
            f"resid_l2={diag.get('linear_residual_l2')} "
            f"resid_linf={diag.get('linear_residual_linf')} "
            f"nneg={diag.get('n_significant_negative_populations_raw')}"
        )
    if args.print_summary:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
