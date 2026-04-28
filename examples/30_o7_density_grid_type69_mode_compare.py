#!/usr/bin/env python3
"""Compare O VII density-grid fits for type-69 ground-excitation modes.

This diagnostic runs the density-dependent O VII source-fit grid twice:

1. the original type-69 handling (``include``), and
2. the diagnostic/experimental ``suppress-resonance`` mode, which suppresses
   type-69 excitation from the ground level into the He-like resonance upper
   level while preserving de-excitation.

It then merges the two density-grid CSV files into one comparison table.  The
main benchmark is the high-density O VII case, where the ``include`` network is
known to miss the density-specific XSTAR R/G target while ``suppress-resonance``
recovers it.  The suppress-resonance mode remains diagnostic/experimental and is
not a general physical default.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def _safe_name(value: float) -> str:
    return (f"{float(value):.6g}".replace("+", "").replace("-", "m").replace(".", "p"))


def _density_key(value) -> str:
    return f"{float(value):.12g}"


def _maybe_float(value) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _maybe_bool(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _safe_ratio(value: Optional[float], reference: Optional[float]) -> Optional[float]:
    if value is None or reference is None or reference == 0.0:
        return None
    return float(value) / float(reference)


def _mismatch_norm(r_over: Optional[float], g_over: Optional[float]) -> Optional[float]:
    if r_over is None or g_over is None:
        return None
    return math.sqrt((float(r_over) - 1.0) ** 2 + (float(g_over) - 1.0) ** 2)


def _improvement_factor(include_norm: Optional[float], suppress_norm: Optional[float]) -> Optional[float]:
    if include_norm is None or suppress_norm is None:
        return None
    if suppress_norm == 0.0:
        return math.inf if include_norm > 0.0 else 1.0
    return float(include_norm) / float(suppress_norm)


def read_csv_rows(path: Path) -> List[dict]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
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


def read_density_grid_csv(path: Path) -> Dict[str, dict]:
    rows = read_csv_rows(path)
    out: Dict[str, dict] = {}
    for row in rows:
        density = _maybe_float(row.get("electron_density_cm^-3") or row.get("density") or row.get("ne"))
        if density is None:
            continue
        out[_density_key(density)] = row
    return out


def read_weights_csv(path: Path) -> Dict[int, float]:
    out: Dict[int, float] = {}
    if not Path(path).exists():
        return out
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lev_text = row.get("source_level") or row.get("level_index") or row.get("level")
            if not lev_text:
                continue
            weight = _maybe_float(row.get("fit_weight_norm") or row.get("solver_fit_weight_norm") or row.get("weight"))
            if weight is None:
                continue
            out[int(float(lev_text))] = float(weight)
    total = sum(max(0.0, v) for v in out.values())
    if total > 0.0:
        out = {k: max(0.0, v) / total for k, v in out.items()}
    return out


def top_weight(weights: Dict[int, float]) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    if not weights:
        return None, None, None
    level, weight = max(weights.items(), key=lambda item: item[1])
    denom = sum(v * v for v in weights.values())
    neff = 1.0 / denom if denom > 0.0 else None
    return int(level), float(weight), neff


def compare_weights(a: Dict[int, float], b: Dict[int, float]) -> dict:
    levels = sorted(set(a) | set(b))
    diffs = [float(b.get(level, 0.0) - a.get(level, 0.0)) for level in levels]
    absdiff = [abs(x) for x in diffs]
    top_changes = []
    for level, diff in sorted(zip(levels, diffs), key=lambda item: abs(item[1]), reverse=True)[:8]:
        top_changes.append({
            "source_level": int(level),
            "include_weight": float(a.get(level, 0.0)),
            "suppress_resonance_weight": float(b.get(level, 0.0)),
            "delta_suppress_minus_include": float(diff),
        })
    return {
        "l1": float(sum(absdiff)),
        "l2": float(math.sqrt(sum(x * x for x in diffs))),
        "max_abs": float(max(absdiff)) if absdiff else 0.0,
        "top_changes": top_changes,
    }


def mode_dir_name(mode: str) -> str:
    return "mode_" + str(mode).replace("-", "_")


def density_weights_path(mode_dir: Path, density: float) -> Path:
    return mode_dir / f"fit_ne_{_safe_name(density)}" / "o7_source_fit_weights.csv"


def run_mode(args, mode: str, mode_dir: Path) -> None:
    csv_path = mode_dir / "o7_solver_source_fit_density_grid.csv"
    summary_path = mode_dir / "o7_solver_source_fit_density_grid_summary.json"
    if args.reuse_existing and csv_path.exists() and summary_path.exists():
        print(f"Reusing existing {mode} density-grid outputs: {mode_dir}")
        return
    script = Path(__file__).resolve().with_name("22_o7_solver_source_fit_density_xstar_grid.py")
    cmd = [
        sys.executable,
        str(script),
        str(args.fitsfile),
        "--xstar-grid-summary-csv",
        str(args.xstar_grid_summary_csv),
        "--collision-type69-ground-excitation-mode",
        str(mode),
        "--linear-solver",
        args.linear_solver,
        "--rank-deficient-action",
        args.rank_deficient_action,
        "--negative-population-action",
        args.negative_population_action,
        "--negative-population-tol",
        f"{float(args.negative_population_tol):.16g}",
        "--combined-source-total-rate",
        f"{float(args.combined_source_total_rate):.16g}",
        "--out-dir",
        str(mode_dir),
    ]
    if args.prune_null_rate_levels:
        cmd += ["--prune-null-rate-levels"]
    else:
        cmd += ["--no-prune-null-rate-levels"]
    cmd += ["--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
    if args.index_cache:
        cmd += ["--index-cache"]
        if args.index_cache_path:
            cmd += ["--index-cache-path", str(args.index_cache_path)]
    if args.print_subprocess_summaries:
        cmd += ["--print-summary"]
    if args.dry_run:
        cmd += ["--dry-run"]
    print("$ " + " ".join(str(x) for x in cmd))
    if not args.dry_run:
        subprocess.run(cmd, check=True)


def build_comparison_rows(include_dir: Path, suppress_dir: Path) -> List[dict]:
    include_csv = include_dir / "o7_solver_source_fit_density_grid.csv"
    suppress_csv = suppress_dir / "o7_solver_source_fit_density_grid.csv"
    include_rows = read_density_grid_csv(include_csv)
    suppress_rows = read_density_grid_csv(suppress_csv)
    keys = sorted(set(include_rows) | set(suppress_rows), key=lambda x: float(x))
    rows: List[dict] = []
    for key in keys:
        inc = include_rows.get(key, {})
        sup = suppress_rows.get(key, {})
        density = float(key)
        xstar_R = _maybe_float((sup or inc).get("xstar_R_f_over_i"))
        xstar_G = _maybe_float((sup or inc).get("xstar_G_f_plus_i_over_r"))
        inc_R = _maybe_float(inc.get("refitted_combined_R_f_over_i"))
        inc_G = _maybe_float(inc.get("refitted_combined_G_f_plus_i_over_r"))
        sup_R = _maybe_float(sup.get("refitted_combined_R_f_over_i"))
        sup_G = _maybe_float(sup.get("refitted_combined_G_f_plus_i_over_r"))
        inc_R_over = _maybe_float(inc.get("refitted_R_over_xstar") or inc.get("refitted_combined_R_over_xstar")) or _safe_ratio(inc_R, xstar_R)
        inc_G_over = _maybe_float(inc.get("refitted_G_over_xstar") or inc.get("refitted_combined_G_over_xstar")) or _safe_ratio(inc_G, xstar_G)
        sup_R_over = _maybe_float(sup.get("refitted_R_over_xstar") or sup.get("refitted_combined_R_over_xstar")) or _safe_ratio(sup_R, xstar_R)
        sup_G_over = _maybe_float(sup.get("refitted_G_over_xstar") or sup.get("refitted_combined_G_over_xstar")) or _safe_ratio(sup_G, xstar_G)
        inc_norm = _mismatch_norm(inc_R_over, inc_G_over)
        sup_norm = _mismatch_norm(sup_R_over, sup_G_over)
        inc_weights = read_weights_csv(density_weights_path(include_dir, density))
        sup_weights = read_weights_csv(density_weights_path(suppress_dir, density))
        inc_top_level, inc_top_weight, inc_neff = top_weight(inc_weights)
        sup_top_level, sup_top_weight, sup_neff = top_weight(sup_weights)
        weight_cmp = compare_weights(inc_weights, sup_weights)
        row = {
            "electron_density_cm^-3": density,
            "xstar_R_f_over_i": xstar_R,
            "xstar_G_f_plus_i_over_r": xstar_G,
            "include_R_f_over_i": inc_R,
            "include_G_f_plus_i_over_r": inc_G,
            "include_R_over_xstar": inc_R_over,
            "include_G_over_xstar": inc_G_over,
            "include_target_reachable": _maybe_bool(inc.get("target_reachable")),
            "include_weight_l1_vs_ne1": _maybe_float(inc.get("weight_delta_l1_vs_ne1")),
            "include_top_source_level": inc_top_level,
            "include_top_source_weight": inc_top_weight,
            "include_source_neff": inc_neff,
            "suppress_resonance_R_f_over_i": sup_R,
            "suppress_resonance_G_f_plus_i_over_r": sup_G,
            "suppress_resonance_R_over_xstar": sup_R_over,
            "suppress_resonance_G_over_xstar": sup_G_over,
            "suppress_resonance_target_reachable": _maybe_bool(sup.get("target_reachable")),
            "suppress_resonance_weight_l1_vs_ne1": _maybe_float(sup.get("weight_delta_l1_vs_ne1")),
            "suppress_resonance_top_source_level": sup_top_level,
            "suppress_resonance_top_source_weight": sup_top_weight,
            "suppress_resonance_source_neff": sup_neff,
            "include_mismatch_norm": inc_norm,
            "suppress_resonance_mismatch_norm": sup_norm,
            "mismatch_improvement_factor": _improvement_factor(inc_norm, sup_norm),
            "source_weight_l1_change_suppress_minus_include": weight_cmp["l1"],
            "source_weight_l2_change_suppress_minus_include": weight_cmp["l2"],
            "source_weight_max_abs_change_suppress_minus_include": weight_cmp["max_abs"],
            "top_source_weight_changes_json": json.dumps(weight_cmp["top_changes"]),
            "include_fit_dir": str(include_dir / f"fit_ne_{_safe_name(density)}"),
            "suppress_resonance_fit_dir": str(suppress_dir / f"fit_ne_{_safe_name(density)}"),
        }
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--xstar-grid-summary-csv", required=True)
    parser.add_argument("--out-dir", default="o7_density_grid_type69_mode_compare")
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--combined-source-total-rate", type=float, default=1.0)
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse existing include/suppress-resonance mode outputs when present")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-subprocess-summaries", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    include_dir = out_dir / mode_dir_name("include")
    suppress_dir = out_dir / mode_dir_name("suppress-resonance")
    out_dir.mkdir(parents=True, exist_ok=True)

    run_mode(args, "include", include_dir)
    run_mode(args, "suppress-resonance", suppress_dir)

    comparison_csv = out_dir / "o7_density_grid_type69_mode_compare.csv"
    summary_json = out_dir / "o7_density_grid_type69_mode_compare_summary.json"
    if args.dry_run:
        print("dry-run: not merging mode outputs")
        return

    rows = build_comparison_rows(include_dir, suppress_dir)
    write_csv(comparison_csv, rows)
    high_density_rows = [row for row in rows if float(row["electron_density_cm^-3"]) >= 1.0e12]
    summary = {
        "fitsfile": str(args.fitsfile),
        "xstar_grid_summary_csv": str(args.xstar_grid_summary_csv),
        "include_dir": str(include_dir),
        "suppress_resonance_dir": str(suppress_dir),
        "comparison_csv": str(comparison_csv),
        "density_rows": rows,
        "high_density_rows": high_density_rows,
        "note": (
            "Diagnostic/experimental comparison: suppress-resonance suppresses type-69 ground-to-resonance excitation "
            "and is validated here for the O VII high-density benchmark only; it is not a general physical default."
        ),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("O VII density-grid type-69 mode comparison")
    print("-------------------------------------------")
    print(f"wrote: {comparison_csv}")
    print(f"wrote: {summary_json}")
    if args.print_summary:
        print("density      include R/G reachable      suppress-resonance R/G reachable      improvement")
        def _fmt(value):
            return "nan" if value is None else f"{float(value):.6g}"
        for row in rows:
            print(
                f"{float(row['electron_density_cm^-3']):.6g}  "
                f"{_fmt(row.get('include_R_f_over_i'))}/{_fmt(row.get('include_G_f_plus_i_over_r'))} {row.get('include_target_reachable')}      "
                f"{_fmt(row.get('suppress_resonance_R_f_over_i'))}/{_fmt(row.get('suppress_resonance_G_f_plus_i_over_r'))} {row.get('suppress_resonance_target_reachable')}      "
                f"{_fmt(row.get('mismatch_improvement_factor'))}"
            )


if __name__ == "__main__":
    main()
