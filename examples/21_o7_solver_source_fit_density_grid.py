#!/usr/bin/env python3
"""Run an O VII solver-source-fit density-grid diagnostic.

This Stage-6 diagnostic extends ``20_o7_solver_source_fit.py`` from one density
(default ``ne=1 cm^-3``) to a density grid.  It answers two related questions:

1. If the fitted empirical source weights from the reference low-density solve
   are kept fixed, how do the O VII triplet ratios change with density?
2. If the source weights are refitted independently at each density, how much do
   the fitted weights change and how well does the simultaneous combined-source
   validation reproduce the XSTAR R/G target?

By default the same low-density XSTAR reference is reused at all densities.
This is intentional: the diagnostic tests whether the low-density target is
still reachable once the density-sensitive type-68 coupling changes the solver
response.  A future extension can accept density-dependent XSTAR reference
tables.

The fitted source weights remain empirical/diagnostic.  They are not physical
level-resolved recombination rates.  This script is intended to expose the
stability, density dependence, and numerical diagnostics of the fitted source
weights after type-68 metastable/intercombination coupling is included.
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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple




def ion_output_prefix(element: str, ion_stage: int) -> str:
    return f"{str(element).strip().lower()}{int(ion_stage)}"


def write_ion_specific_alias(src: Path, prefix: str, legacy_stem: str) -> Path | None:
    if prefix == "o7" or not src.exists():
        return None
    alias = src.with_name(src.name.replace(legacy_stem, prefix, 1))
    if alias == src:
        return None
    shutil.copy2(src, alias)
    return alias

def _safe_name(value: float) -> str:
    return (f"{float(value):.6g}".replace("+", "").replace("-", "m").replace(".", "p"))


def _maybe_float(value) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out




def _density_key(value: float) -> str:
    """Return a stable key for matching density-grid references."""
    return f"{float(value):.12g}"


def _parse_density_value(value: str) -> float:
    text = str(value).strip()
    if not text:
        raise ValueError("empty density value")
    return float(text)


def _split_density_path_spec(spec: str) -> Tuple[float, str]:
    """Parse DENSITY:PATH while allowing ':' characters inside the path."""
    text = str(spec).strip()
    if ":" not in text:
        raise ValueError(f"expected DENSITY:PATH specification, got {spec!r}")
    density_text, path_text = text.split(":", 1)
    density = _parse_density_value(density_text)
    path = path_text.strip()
    if not path:
        raise ValueError(f"missing XSTAR CSV path in specification {spec!r}")
    return density, path


def _find_density_column(row: dict) -> Optional[str]:
    for key in (
        "electron_density_cm^-3",
        "electron_density_cm-3",
        "electron_density",
        "density_cm^-3",
        "density_cm-3",
        "density",
        "ne_cm^-3",
        "ne_cm-3",
        "ne",
    ):
        if key in row and str(row.get(key, "")).strip():
            return key
    return None


def read_xstar_reference_grid_csv(path: Path) -> Dict[str, dict]:
    """Read a density-to-XSTAR-lines mapping CSV.

    Accepted density columns include ``electron_density_cm^-3``, ``density``,
    and ``ne``.  Accepted path columns include ``xstar_lines_csv``, ``path``,
    and ``xstar_csv``.  Optional columns are ``xstar_value_column`` and
    ``xstar_target_label``.
    """
    refs: Dict[str, dict] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dcol = _find_density_column(row)
            if dcol is None:
                raise ValueError(f"XSTAR grid CSV {path} is missing a density column")
            density = _parse_density_value(row[dcol])
            xpath = (
                row.get("xstar_lines_csv")
                or row.get("xstar_csv")
                or row.get("path")
                or row.get("filename")
                or row.get("file")
            )
            if not xpath or not str(xpath).strip():
                raise ValueError(f"XSTAR grid CSV {path} row for density {density:g} is missing xstar_lines_csv/path")
            refs[_density_key(density)] = {
                "electron_density_cm^-3": float(density),
                "xstar_lines_csv": str(xpath).strip(),
                "xstar_value_column": str(row.get("xstar_value_column") or row.get("value_column") or "").strip() or None,
                "xstar_target_label": str(row.get("xstar_target_label") or row.get("target_label") or "").strip() or None,
            }
    return refs


def build_xstar_reference_map(args) -> Dict[str, dict]:
    """Build a density-specific XSTAR reference map from CLI options."""
    refs: Dict[str, dict] = {}
    if getattr(args, "xstar_grid_summary_csv", None):
        refs.update(read_xstar_reference_grid_csv(Path(args.xstar_grid_summary_csv)))
    for spec in getattr(args, "xstar_lines_csv_by_density", []) or []:
        density, path = _split_density_path_spec(spec)
        refs[_density_key(density)] = {
            "electron_density_cm^-3": float(density),
            "xstar_lines_csv": path,
            "xstar_value_column": None,
            "xstar_target_label": None,
        }
    return refs


def select_xstar_reference(args, density: float, xstar_reference_map: Dict[str, dict]) -> dict:
    """Return the XSTAR reference configuration for one density."""
    key = _density_key(density)
    if xstar_reference_map:
        if key not in xstar_reference_map:
            available = ", ".join(sorted(xstar_reference_map))
            raise KeyError(
                f"no density-specific XSTAR reference for ne={float(density):.12g}; "
                f"available density keys: {available}"
            )
        ref = dict(xstar_reference_map[key])
        return {
            "xstar_lines_csv": ref["xstar_lines_csv"],
            "xstar_value_column": ref.get("xstar_value_column") or args.xstar_value_column,
            "xstar_target_label": ref.get("xstar_target_label")
                or f"density-specific XSTAR O VII reference at ne={float(density):.6g} cm^-3",
            "xstar_target_is_reused_low_density_reference": False,
            "xstar_reference_density_cm^-3": float(density),
        }
    return {
        "xstar_lines_csv": str(args.xstar_lines_csv),
        "xstar_value_column": args.xstar_value_column,
        "xstar_target_label": args.xstar_target_label,
        "xstar_target_is_reused_low_density_reference": True,
        "xstar_reference_density_cm^-3": float(args.reference_density),
    }


def _run(cmd: Sequence[str], dry_run: bool = False) -> None:
    print("$ " + " ".join(str(x) for x in cmd))
    if not dry_run:
        subprocess.run(list(cmd), check=True)


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


def read_weights_csv(path: Path) -> Dict[int, float]:
    out: Dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            level = int(row.get("source_level") or row.get("level_index"))
            weight = _maybe_float(row.get("fit_weight_norm") or row.get("solver_fit_weight_norm"))
            if weight is None:
                continue
            out[level] = float(weight)
    s = sum(v for v in out.values() if v > 0.0)
    if s > 0.0:
        out = {k: max(0.0, v) / s for k, v in out.items()}
    return out


def read_triplet_csv(path: Path) -> dict:
    if not path.exists():
        return {"forbidden": None, "intercombination": None, "resonance": None, "R_f_over_i": None, "G_f_plus_i_over_r": None}
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        return {"forbidden": None, "intercombination": None, "resonance": None, "R_f_over_i": None, "G_f_plus_i_over_r": None}
    row = rows[0]
    return {
        "forbidden": _maybe_float(row.get("forbidden_energy_per_ion_erg_s^-1")),
        "intercombination": _maybe_float(row.get("intercombination_energy_per_ion_erg_s^-1")),
        "resonance": _maybe_float(row.get("resonance_energy_per_ion_erg_s^-1")),
        "R_f_over_i": _maybe_float(row.get("R_f_over_i")),
        "G_f_plus_i_over_r": _maybe_float(row.get("G_f_plus_i_over_r")),
    }


def _first_solve_info(summary: dict) -> dict:
    solves = summary.get("solves") or []
    return dict(solves[0]) if solves else {}


def _solver_diagnostics_from_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    info = _first_solve_info(summary)
    keys = [
        "solver",
        "solver_warning",
        "matrix_rank",
        "matrix_size",
        "condition_number",
        "linear_residual_l2",
        "linear_residual_linf",
        "negative_population_action",
        "n_negative_populations_raw",
        "n_significant_negative_populations_raw",
        "min_population_raw",
        "sum_negative_populations_raw_abs",
        "null_rate_pruning_diagnostics",
    ]
    out = {key: info.get(key) for key in keys if key in info}
    ss = summary.get("source_sink_summaries") or []
    if ss:
        out["source_sum_s^-1"] = ss[0].get("source_sum_s^-1")
    return out


def write_source_csv(path: Path, weights: Dict[int, float], total_rate: float, temperature: float, density: float) -> None:
    rows = []
    for level in sorted(weights):
        w = float(weights[level])
        if w <= 0.0:
            continue
        rows.append({
            "temperature_K": float(temperature),
            "electron_density_cm^-3": float(density),
            "level_index": int(level),
            "source_s^-1": float(total_rate) * w,
            "fit_weight_norm": w,
        })
    write_csv(path, rows)


def compare_weights(reference: Dict[int, float], current: Dict[int, float]) -> dict:
    levels = sorted(set(reference) | set(current))
    diffs = [float(current.get(level, 0.0) - reference.get(level, 0.0)) for level in levels]
    absdiff = [abs(x) for x in diffs]
    l1 = float(sum(absdiff))
    l2 = float(math.sqrt(sum(x * x for x in diffs)))
    max_abs = float(max(absdiff)) if absdiff else 0.0
    top = []
    for level, diff in sorted(zip(levels, diffs), key=lambda item: abs(item[1]), reverse=True)[:8]:
        top.append({
            "source_level": int(level),
            "reference_weight": float(reference.get(level, 0.0)),
            "fitted_weight": float(current.get(level, 0.0)),
            "delta": float(diff),
        })
    return {"weight_delta_l1": l1, "weight_delta_l2": l2, "weight_delta_max_abs": max_abs, "top_weight_changes": top}


def add_solver_args(cmd: List[str], args) -> List[str]:
    cmd += [
        "--linear-solver", args.linear_solver,
        "--rank-deficient-action", args.rank_deficient_action,
        "--negative-population-action", args.negative_population_action,
        "--negative-population-tol", f"{float(args.negative_population_tol):.16g}",
    ]
    if args.residual_l2_max is not None:
        cmd += ["--residual-l2-max", f"{float(args.residual_l2_max):.16g}"]
    if args.residual_linf_max is not None:
        cmd += ["--residual-linf-max", f"{float(args.residual_linf_max):.16g}"]
    if args.reject_large_residual:
        cmd += ["--reject-large-residual"]
    if args.prune_null_rate_levels:
        cmd += ["--prune-null-rate-levels", "--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
    mode = getattr(args, "collision_type69_ground_excitation_mode", "include") or "include"
    if mode != "include":
        cmd += ["--collision-type69-ground-excitation-mode", str(mode)]
    return cmd


def add_cache_args(cmd: List[str], args) -> List[str]:
    if args.index_cache:
        if args.index_cache_path:
            cmd += ["--index-cache", "--index-cache-path", str(args.index_cache_path)]
        else:
            cmd += ["--index-cache"]
        cmd += ["--index-cache-format", args.index_cache_format]
    return cmd


def add_solver_cache_args(cmd: List[str], args) -> List[str]:
    if args.index_cache:
        if args.index_cache_path:
            cmd += ["--index-cache", str(args.index_cache_path), "--index-cache-format", args.index_cache_format]
        else:
            cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]
    return cmd


def run_fit_for_density(args, density: float, fit_dir: Path, xstar_ref: dict) -> dict:
    cmd = [
        sys.executable, "examples/20_o7_solver_source_fit.py", str(args.fitsfile),
        "--element", args.element,
        "--ion-stage", str(int(args.ion_stage)),
        "--temperature", f"{float(args.temperature):.16g}",
        "--electron-density", f"{float(density):.16g}",
        "--source-levels", args.source_levels,
        "--source-rate", f"{float(args.source_rate):.16g}",
        "--combined-source-total-rate", f"{float(args.combined_source_total_rate):.16g}",
        "--wavelength-min", f"{float(args.wavelength_min):.16g}",
        "--wavelength-max", f"{float(args.wavelength_max):.16g}",
        "--xstar-lines-csv", str(xstar_ref["xstar_lines_csv"]),
        "--xstar-value-column", str(xstar_ref["xstar_value_column"]),
        "--out-dir", str(fit_dir),
    ]
    if args.keep_unit_runs:
        cmd += ["--keep-unit-runs"]
    if args.print_subprocess_summaries:
        cmd += ["--print-summary"]
    cmd = add_solver_args(cmd, args)
    cmd = add_cache_args(cmd, args)
    _run(cmd, dry_run=args.dry_run)
    summary_path = fit_dir / "o7_solver_source_fit_summary.json"
    if args.dry_run:
        return {"summary_path": str(summary_path), "dry_run": True}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["_density_xstar_reference"] = dict(xstar_ref)
    if isinstance(summary.get("xstar_reference"), dict):
        summary["xstar_reference"].update({
            "target_label": xstar_ref.get("xstar_target_label"),
            "target_is_reused_low_density_reference": xstar_ref.get("xstar_target_is_reused_low_density_reference"),
            "reference_density_cm^-3": xstar_ref.get("xstar_reference_density_cm^-3"),
            "path": str(xstar_ref.get("xstar_lines_csv")),
        })
    return summary


def run_fixed_weight_validation(args, density: float, weights: Dict[int, float], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    source_csv = out_dir / "o7_fixed_ne1_sources.csv"
    lines_csv = out_dir / "o7_fixed_ne1_solver_lines.csv"
    triplet_csv = out_dir / "o7_fixed_ne1_solver_triplet.csv"
    summary_json = out_dir / "o7_fixed_ne1_solver_summary.json"
    write_source_csv(source_csv, weights, args.combined_source_total_rate, args.temperature, density)
    cmd = [
        sys.executable, "-m", "xstar_atomic.solver", str(args.fitsfile),
        "--element", args.element,
        "--ion-stage", str(int(args.ion_stage)),
        "--temperatures", f"{float(args.temperature):.16g}",
        "--electron-densities", f"{float(density):.16g}",
        "--wavelength-min", f"{float(args.wavelength_min):.16g}",
        "--wavelength-max", f"{float(args.wavelength_max):.16g}",
        "--source-csv", str(source_csv),
        "--out-lines-csv", str(lines_csv),
        "--out-triplet-csv", str(triplet_csv),
        "--summary-json", str(summary_json),
    ]
    cmd = add_solver_args(cmd, args)
    cmd = add_solver_cache_args(cmd, args)
    _run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"enabled": True, "dry_run": True, "source_csv": str(source_csv), "triplet_csv": str(triplet_csv), "summary_json": str(summary_json)}
    trip = read_triplet_csv(triplet_csv)
    return {
        "enabled": True,
        "source_total_rate_s^-1": float(args.combined_source_total_rate),
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
        "solver_diagnostics": _solver_diagnostics_from_summary(summary_json),
    }



def _safe_ratio(value: Optional[float], reference: Optional[float]) -> Optional[float]:
    if value is None or reference is None or reference == 0.0:
        return None
    return float(value) / float(reference)


def _within_fraction(value: Optional[float], reference: Optional[float], tolerance: float) -> bool:
    ratio = _safe_ratio(value, reference)
    if ratio is None:
        return False
    return abs(ratio - 1.0) <= float(tolerance)


def _fit_objective_from_summary(fit_summary: dict) -> Optional[float]:
    fitted = fit_summary.get("fitted_prediction") or {}
    fit_info = fitted.get("fit_info") or {}
    return _maybe_float(fit_info.get("objective"))


def _make_density_warning(
    density: float,
    fit_objective: Optional[float],
    fit_objective_warn: float,
    refitted_R_over_xstar: Optional[float],
    refitted_G_over_xstar: Optional[float],
    tolerance: float,
    high_density_warn: float,
) -> Optional[str]:
    messages: List[str] = []
    if fit_objective is not None and fit_objective > fit_objective_warn:
        messages.append(f"fit objective {fit_objective:.6g} exceeds warning threshold {fit_objective_warn:.6g}")
    if refitted_R_over_xstar is None or abs(refitted_R_over_xstar - 1.0) > tolerance:
        messages.append(f"refitted R/XSTAR mismatch exceeds tolerance {tolerance:.6g}")
    if refitted_G_over_xstar is None or abs(refitted_G_over_xstar - 1.0) > tolerance:
        messages.append(f"refitted G/XSTAR mismatch exceeds tolerance {tolerance:.6g}")
    if messages:
        prefix = f"density ne={float(density):.6g} cm^-3"
        if float(density) >= float(high_density_warn):
            prefix += " (high-density type-68 coupling regime)"
        return prefix + ": " + "; ".join(messages)
    return None


def flatten_row(
    density: float,
    xstar: dict,
    reference_density: float,
    fixed: dict,
    fit_summary: dict,
    weight_cmp: dict,
    fit_dir: Path,
    fixed_dir: Path,
    args,
) -> dict:
    fitted = fit_summary.get("fitted_prediction") or {}
    combined = fit_summary.get("combined_source_validation") or {}
    fit_info = fitted.get("fit_info") or {}
    diag_fixed = fixed.get("solver_diagnostics") or {}
    diag_combined = combined.get("solver_diagnostics") or {}
    R_x = xstar.get("R_f_over_i")
    G_x = xstar.get("G_f_plus_i_over_r")
    fixed_R = fixed.get("R_f_over_i")
    fixed_G = fixed.get("G_f_plus_i_over_r")
    refit_R = combined.get("R_f_over_i")
    refit_G = combined.get("G_f_plus_i_over_r")
    refit_R_over_xstar = _safe_ratio(refit_R, R_x)
    refit_G_over_xstar = _safe_ratio(refit_G, G_x)
    fit_objective = _fit_objective_from_summary(fit_summary)
    fit_success_vs_xstar = (
        _within_fraction(refit_R, R_x, args.rg_tolerance)
        and _within_fraction(refit_G, G_x, args.rg_tolerance)
        and (fit_objective is None or fit_objective <= args.fit_objective_warn)
    )
    target_reachable = (
        _within_fraction(refit_R, R_x, args.reachable_rg_tolerance)
        and _within_fraction(refit_G, G_x, args.reachable_rg_tolerance)
    )
    warning = _make_density_warning(
        density,
        fit_objective,
        args.fit_objective_warn,
        refit_R_over_xstar,
        refit_G_over_xstar,
        args.rg_tolerance,
        args.high_density_warning_threshold,
    )
    row = {
        "electron_density_cm^-3": float(density),
        "reference_weight_density_cm^-3": float(reference_density),
        "xstar_target_label": xstar.get("target_label") or args.xstar_target_label,
        "xstar_target_is_reused_low_density_reference": bool(xstar.get("target_is_reused_low_density_reference", True)),
        "xstar_reference_density_cm^-3": xstar.get("reference_density_cm^-3"),
        "xstar_lines_csv": xstar.get("path"),
        "xstar_R_f_over_i": R_x,
        "xstar_G_f_plus_i_over_r": G_x,
        "fixed_ne1_R_f_over_i": fixed_R,
        "fixed_ne1_G_f_plus_i_over_r": fixed_G,
        "fixed_ne1_R_over_xstar": _safe_ratio(fixed_R, R_x),
        "fixed_ne1_G_over_xstar": _safe_ratio(fixed_G, G_x),
        "refitted_linear_R_f_over_i": fitted.get("R_f_over_i"),
        "refitted_linear_G_f_plus_i_over_r": fitted.get("G_f_plus_i_over_r"),
        "refitted_combined_R_f_over_i": refit_R,
        "refitted_combined_G_f_plus_i_over_r": refit_G,
        "refitted_R_over_xstar": refit_R_over_xstar,
        "refitted_G_over_xstar": refit_G_over_xstar,
        "refitted_combined_R_over_xstar": refit_R_over_xstar,
        "refitted_combined_G_over_xstar": refit_G_over_xstar,
        "fixed_R_over_refitted": _safe_ratio(fixed_R, refit_R),
        "fixed_G_over_refitted": _safe_ratio(fixed_G, refit_G),
        "fit_success_vs_xstar": bool(fit_success_vs_xstar),
        "target_reachable": bool(target_reachable),
        "density_warning": warning,
        "delta_R_combined_minus_linear": combined.get("delta_R_vs_fitted_linear_response"),
        "delta_G_combined_minus_linear": combined.get("delta_G_vs_fitted_linear_response"),
        "fit_status": fit_info.get("status"),
        "fit_iterations": fit_info.get("iterations"),
        "fit_objective": fit_objective,
        "weight_delta_l1_vs_ne1": weight_cmp.get("weight_delta_l1"),
        "weight_delta_l2_vs_ne1": weight_cmp.get("weight_delta_l2"),
        "weight_delta_max_abs_vs_ne1": weight_cmp.get("weight_delta_max_abs"),
        "top_weight_changes_json": json.dumps(weight_cmp.get("top_weight_changes") or []),
        "fixed_solver": diag_fixed.get("solver"),
        "fixed_solver_warning": diag_fixed.get("solver_warning"),
        "fixed_matrix_rank": diag_fixed.get("matrix_rank"),
        "fixed_matrix_size": diag_fixed.get("matrix_size"),
        "fixed_condition_number": diag_fixed.get("condition_number"),
        "fixed_linear_residual_l2": diag_fixed.get("linear_residual_l2"),
        "fixed_linear_residual_linf": diag_fixed.get("linear_residual_linf"),
        "fixed_n_negative_populations_raw": diag_fixed.get("n_negative_populations_raw"),
        "refitted_solver": diag_combined.get("solver"),
        "refitted_solver_warning": diag_combined.get("solver_warning"),
        "refitted_matrix_rank": diag_combined.get("matrix_rank"),
        "refitted_matrix_size": diag_combined.get("matrix_size"),
        "refitted_condition_number": diag_combined.get("condition_number"),
        "refitted_linear_residual_l2": diag_combined.get("linear_residual_l2"),
        "refitted_linear_residual_linf": diag_combined.get("linear_residual_linf"),
        "refitted_n_negative_populations_raw": diag_combined.get("n_negative_populations_raw"),
        "fit_dir": str(fit_dir),
        "fixed_validation_dir": str(fixed_dir),
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--element", default="O")
    parser.add_argument("--ion-stage", type=int, default=7)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-densities", type=float, nargs="+", default=[1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12])
    parser.add_argument("--reference-density", type=float, default=1.0, help="Density whose fitted weights are reused as the fixed-weight baseline")
    parser.add_argument("--source-levels", default="2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20")
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--combined-source-total-rate", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--xstar-lines-csv-by-density", action="append", default=[], metavar="DENSITY:CSV", help="Density-specific XSTAR line CSV. May be repeated. Example: 1e10:xstar_o7_ne1e10_lines.csv")
    parser.add_argument("--xstar-grid-summary-csv", help="CSV mapping densities to XSTAR line CSVs. Columns: density/ne/electron_density_cm^-3 and xstar_lines_csv/path; optional xstar_value_column and xstar_target_label.")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument(
        "--xstar-target-label",
        default="low-density XSTAR O VII reference reused at all densities",
        help="Label written to outputs to clarify the XSTAR target used for every density.",
    )
    parser.add_argument("--rg-tolerance", type=float, default=5.0e-3, help="Fractional R/G tolerance for fit_success_vs_xstar")
    parser.add_argument("--reachable-rg-tolerance", type=float, default=5.0e-2, help="Fractional R/G tolerance for target_reachable")
    parser.add_argument("--fit-objective-warn", type=float, default=1.0e-4, help="Warn when the source-fit objective exceeds this value")
    parser.add_argument("--high-density-warning-threshold", type=float, default=1.0e12, help="Density threshold used to annotate high-density warnings")
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--residual-l2-max", type=float)
    parser.add_argument("--residual-linf-max", type=float)
    parser.add_argument("--reject-large-residual", action="store_true")
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--collision-type69-ground-excitation-mode", choices=["include", "suppress-resonance", "suppress-all"], default="include",
                        help="Diagnostic/experimental type-69 ground-excitation mode forwarded to example 20/solver.")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--out-dir", default="o7_solver_source_fit_density_grid")
    parser.add_argument("--keep-unit-runs", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-subprocess-summaries", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xstar_reference_map = build_xstar_reference_map(args)

    ref_density = float(args.reference_density)
    # Always run the reference density first so fixed-weight validation is defined
    # for every subsequent density, regardless of the user-provided order.
    remaining = []
    for value in args.electron_densities:
        fval = float(value)
        if abs(fval - ref_density) <= 0.0:
            continue
        if fval not in remaining:
            remaining.append(fval)
    densities = [ref_density] + remaining

    rows: List[dict] = []
    density_summaries: List[dict] = []
    reference_weights: Optional[Dict[int, float]] = None
    reference_fit_dir: Optional[Path] = None
    xstar_reference: dict = {}

    for density in densities:
        name = _safe_name(density)
        fit_dir = out_dir / f"fit_ne_{name}"
        fixed_dir = out_dir / f"fixed_ne1_validation_ne_{name}"
        xstar_ref_for_density = select_xstar_reference(args, density, xstar_reference_map)
        fit_summary = run_fit_for_density(args, density, fit_dir, xstar_ref_for_density)
        if args.dry_run:
            continue
        xstar_reference = fit_summary.get("xstar_reference") or {}
        weights_path = fit_dir / "o7_source_fit_weights.csv"
        current_weights = read_weights_csv(weights_path)
        if abs(density - float(args.reference_density)) <= 0.0:
            reference_weights = dict(current_weights)
            reference_fit_dir = fit_dir
        if reference_weights is None:
            raise RuntimeError("Reference weights were not initialized")
        fixed_validation = run_fixed_weight_validation(args, density, reference_weights, fixed_dir)
        weight_cmp = compare_weights(reference_weights, current_weights)
        row = flatten_row(density, xstar_reference, float(args.reference_density), fixed_validation, fit_summary, weight_cmp, fit_dir, fixed_dir, args)
        rows.append(row)
        density_summaries.append({
            "electron_density_cm^-3": float(density),
            "fit_summary_json": str(fit_dir / "o7_solver_source_fit_summary.json"),
            "weights_csv": str(weights_path),
            "fixed_validation": fixed_validation,
            "weight_comparison_vs_reference_density": weight_cmp,
            "fit_success_vs_xstar": row.get("fit_success_vs_xstar"),
            "target_reachable": row.get("target_reachable"),
            "density_warning": row.get("density_warning"),
            "xstar_reference": xstar_reference,
            "fit_summary": fit_summary,
        })

    output_prefix = ion_output_prefix(args.element, int(args.ion_stage))
    out_csv = out_dir / "o7_solver_source_fit_density_grid.csv"
    out_summary = out_dir / "o7_solver_source_fit_density_grid_summary.json"
    if not args.dry_run:
        write_csv(out_csv, rows)
        summary = {
            "fitsfile": str(args.fitsfile),
            "element": args.element,
            "ion_stage": int(args.ion_stage),
            "temperature_K": float(args.temperature),
            "electron_densities_cm^-3": densities,
            "reference_density_cm^-3": float(args.reference_density),
            "reference_fit_dir": str(reference_fit_dir) if reference_fit_dir is not None else None,
            "source_rate_s^-1": float(args.source_rate),
            "combined_source_total_rate_s^-1": float(args.combined_source_total_rate),
            "solver_matrix_treatment": {
                "linear_solver": args.linear_solver,
                "rank_deficient_action": args.rank_deficient_action,
                "negative_population_action": args.negative_population_action,
                "negative_population_tol": float(args.negative_population_tol),
                "prune_null_rate_levels": bool(args.prune_null_rate_levels),
                "null_rate_floor_s^-1": float(args.null_rate_floor),
            },
            "xstar_target_label": args.xstar_target_label if not xstar_reference_map else f"density-specific XSTAR {args.element} {int(args.ion_stage)} references",
            "xstar_target_is_reused_low_density_reference": not bool(xstar_reference_map),
            "xstar_reference_map": xstar_reference_map,
            "last_xstar_reference": xstar_reference,
            "fit_feasibility_tolerances": {
                "rg_tolerance_fraction": float(args.rg_tolerance),
                "reachable_rg_tolerance_fraction": float(args.reachable_rg_tolerance),
                "fit_objective_warn": float(args.fit_objective_warn),
            },
            "warnings": [row.get("density_warning") for row in rows if row.get("density_warning")],
            "density_rows_csv": str(out_csv),
            "density_summaries": density_summaries,
            "note": "Diagnostic only: density-dependent fitted source weights are empirical solver-response weights, not physical recombination rates.",
        }
        out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        alias_csv = write_ion_specific_alias(out_csv, output_prefix, "o7")
        alias_summary = write_ion_specific_alias(out_summary, output_prefix, "o7")
        summary["outputs"] = {
            "legacy_density_rows_csv": str(out_csv),
            "legacy_summary_json": str(out_summary),
            "ion_output_prefix": output_prefix,
            "ion_specific_density_rows_csv": str(alias_csv) if alias_csv else str(out_csv),
            "ion_specific_summary_json": str(alias_summary) if alias_summary else str(out_summary),
        }
        out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if alias_summary:
            alias_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"{args.element} {int(args.ion_stage)} solver-source-fit density-grid diagnostic")
    print("------------------------------------------------")
    print("densities:", ", ".join(f"{x:.6g}" for x in densities))
    print(f"reference density: {float(args.reference_density):.6g} cm^-3")
    if xstar_reference_map:
        print("XSTAR target mode: density-specific references")
    else:
        print("XSTAR target mode: reused low-density reference")
    print(f"wrote: {out_csv}")
    print(f"wrote: {out_summary}")
    if args.print_summary and rows:
        print("density      fixed R/G              refitted combined R/G      weight L1      reachable")
        def _fmt(value):
            return "nan" if value is None else f"{float(value):.6g}"
        for row in rows:
            print(
                f"{float(row['electron_density_cm^-3']):.6g}  "
                f"{_fmt(row.get('fixed_ne1_R_f_over_i'))}/{_fmt(row.get('fixed_ne1_G_f_plus_i_over_r'))}  "
                f"{_fmt(row.get('refitted_combined_R_f_over_i'))}/{_fmt(row.get('refitted_combined_G_f_plus_i_over_r'))}  "
                f"{_fmt(row.get('weight_delta_l1_vs_ne1'))}      "
                f"{row.get('target_reachable')}"
            )
        warnings = [row.get("density_warning") for row in rows if row.get("density_warning")]
        if warnings:
            print("warnings:")
            for message in warnings:
                print(f"  WARNING: {message}")


if __name__ == "__main__":
    main()
