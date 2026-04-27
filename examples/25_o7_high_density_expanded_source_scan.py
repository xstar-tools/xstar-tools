#!/usr/bin/env python3
"""Scan expanded O VII source-level sets for the high-density mismatch.

This diagnostic follows ``examples/24_o7_high_density_mismatch_diagnostics.py``.
It asks whether the failure at high density, usually ``ne=1e12 cm^-3``, is
caused by using too small an empirical source-level basis.  For each source set
it runs ``examples/20_o7_solver_source_fit.py`` with the validated SVD/rank-aware
solver treatment, then compares the fitted and combined-source R/G values with
the density-specific XSTAR target.

The scan is diagnostic only.  The fitted weights are empirical source proxies,
not physical level-resolved recombination rates.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


BASELINE_LEVELS = [2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


def maybe_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def maybe_int(value) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def density_equal(a: float, b: float, rel: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)), 1.0)


def safe_name(text: str) -> str:
    out = str(text).strip().lower()
    out = out.replace("<=", "le").replace(">=", "ge")
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")
    return out or "set"


def safe_density_name(value: float) -> str:
    return f"{float(value):.6g}".replace("+", "").replace("-", "m").replace(".", "p")


def parse_level_list(text: str) -> List[int]:
    levels: List[int] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        levels.append(int(part))
    return sorted(dict.fromkeys(levels))


def read_csv_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_density_row(rows: Sequence[dict], density: float) -> dict:
    for row in rows:
        val = maybe_float(row.get("electron_density_cm^-3") or row.get("density") or row.get("ne"))
        if val is not None and density_equal(val, density):
            return dict(row)
    available = [row.get("electron_density_cm^-3") for row in rows]
    raise SystemExit(f"Could not find density {density:g}. Available densities: {available}")


def parse_principal_n(label: str) -> Optional[int]:
    """Best-effort principal-quantum-number parser for XSTAR level labels."""
    text = str(label or "")
    matches = re.findall(r"(?:^|[\.\s])([1-9][0-9]*)(?=[spdfghiklmSPDFGHIKLM])", text)
    vals = [int(m) for m in matches]
    return max(vals) if vals else None


def load_o7_level_rows(fitsfile: str, index_cache: bool = False, cache_format: str = "npz") -> List[dict]:
    from xstar_atomic.hierarchy import ATDB, SYMBOL_TO_Z
    from xstar_atomic.lines import extract_levels

    z = SYMBOL_TO_Z["O"]
    with ATDB(fitsfile) as db:
        records = db.select_records(z=z, ion_stage=7, use_cache=bool(index_cache), cache_format=cache_format)
        levels = extract_levels(db, records, z, 7)
    out = []
    for row in levels:
        idx = maybe_int(row.get("level_index"))
        if idx is None:
            continue
        label = row.get("level_label") or row.get("label") or row.get("configuration") or ""
        n = parse_principal_n(label)
        new = dict(row)
        new["level_index"] = idx
        new["parsed_n"] = n
        new["level_label"] = label
        out.append(new)
    return out


def build_auto_source_sets(level_rows: List[dict]) -> List[Tuple[str, List[int], str]]:
    sets: List[Tuple[str, List[int], str]] = [("baseline", BASELINE_LEVELS, "validated n<=4 source-level baseline")]
    levels_with_n = []
    for row in level_rows:
        idx = maybe_int(row.get("level_index"))
        n = maybe_int(row.get("parsed_n"))
        if idx is None or idx <= 1 or n is None:
            continue
        levels_with_n.append((idx, n))
    for nmax in [5, 6, 8]:
        vals = sorted({idx for idx, n in levels_with_n if n <= nmax})
        if vals:
            sets.append((f"n_le_{nmax}", vals, f"all parsed O VII levels with n <= {nmax}"))
    all_levels = sorted({maybe_int(row.get("level_index")) for row in level_rows if (maybe_int(row.get("level_index")) or 0) > 1})
    all_levels = [v for v in all_levels if v is not None]
    if all_levels:
        sets.append(("all_levels", all_levels, "all O VII levels except ground; broad connected-source proxy"))
    return sets


def read_weights(path: Path) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for row in read_csv_rows(path):
        level = maybe_int(row.get("source_level") or row.get("level_index"))
        weight = maybe_float(row.get("fit_weight_norm") or row.get("solver_fit_weight_norm") or row.get("weight"))
        if level is None or weight is None:
            continue
        out[level] = max(0.0, float(weight))
    s = sum(out.values())
    if s > 0.0:
        out = {k: v / s for k, v in out.items()}
    return out


def weight_stats(weights: Dict[int, float]) -> dict:
    positive = {k: v for k, v in weights.items() if v > 0.0}
    if not positive:
        return {"n_nonzero": 0, "effective_n": None, "top1_level": None, "top1_weight": None, "top5_weight_sum": None}
    vals = list(positive.values())
    eff_n = 1.0 / sum(v * v for v in vals)
    top = sorted(positive.items(), key=lambda item: item[1], reverse=True)
    return {
        "n_nonzero": len(positive),
        "effective_n": eff_n,
        "top1_level": int(top[0][0]),
        "top1_weight": float(top[0][1]),
        "top5_weight_sum": float(sum(v for _k, v in top[:5])),
        "top_weights": [{"source_level": int(k), "weight": float(v)} for k, v in top[:10]],
    }


def normalized_components(summary: dict) -> dict:
    comps = ((summary.get("combined_source_validation") or {}).get("triplet_components") or {})
    vals = {k: maybe_float(comps.get(k)) for k in ["forbidden", "intercombination", "resonance"]}
    total = sum(v for v in vals.values() if v is not None)
    if total <= 0.0:
        return {k: None for k in vals}
    return {k: (v / total if v is not None else None) for k, v in vals.items()}


def run_solver_fit(args, set_name: str, levels: List[int], xstar_csv: str, xstar_col: str, out_dir: Path) -> dict:
    fit_dir = out_dir / f"fit_{safe_name(set_name)}"
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("20_o7_solver_source_fit.py")),
        args.fitsfile,
        "--element", "O",
        "--ion-stage", "7",
        "--temperature", str(args.temperature),
        "--electron-density", str(args.density),
        "--source-levels", ",".join(str(v) for v in levels),
        "--source-rate", str(args.source_rate),
        "--combined-source-total-rate", str(args.combined_source_total_rate),
        "--wavelength-min", str(args.wavelength_min),
        "--wavelength-max", str(args.wavelength_max),
        "--xstar-lines-csv", xstar_csv,
        "--xstar-value-column", xstar_col,
        "--out-dir", str(fit_dir),
        "--linear-solver", args.linear_solver,
        "--rank-deficient-action", args.rank_deficient_action,
        "--negative-population-action", args.negative_population_action,
        "--negative-population-tol", str(args.negative_population_tol),
        "--null-rate-floor", str(args.null_rate_floor),
        "--index-cache-format", args.index_cache_format,
    ]
    if args.prune_null_rate_levels:
        cmd.append("--prune-null-rate-levels")
    if args.index_cache:
        cmd.append("--index-cache")
    if args.index_cache_path:
        cmd.extend(["--index-cache-path", args.index_cache_path])
    if args.print_commands:
        print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    summary_path = fit_dir / "o7_solver_source_fit_summary.json"
    if not summary_path.exists():
        raise SystemExit(f"Fit summary was not written: {summary_path}")
    return read_json(summary_path)


def summarize_set(set_name: str, note: str, levels: List[int], summary: dict, tolerance: float, fit_dir: Path) -> dict:
    xstar = summary.get("xstar_reference") or {}
    fitted = summary.get("fitted_prediction") or {}
    combined = summary.get("combined_source_validation") or {}
    solver_diag = combined.get("solver_diagnostics") or {}
    r_x = maybe_float(xstar.get("R_f_over_i"))
    g_x = maybe_float(xstar.get("G_f_plus_i_over_r"))
    r_c = maybe_float(combined.get("R_f_over_i"))
    g_c = maybe_float(combined.get("G_f_plus_i_over_r"))
    r_ratio = (r_c / r_x) if r_c is not None and r_x not in (None, 0.0) else None
    g_ratio = (g_c / g_x) if g_c is not None and g_x not in (None, 0.0) else None
    reachable = bool(r_ratio is not None and g_ratio is not None and abs(r_ratio - 1.0) <= tolerance and abs(g_ratio - 1.0) <= tolerance)
    comps_target = summary.get("target_components_normalized") or {}
    comps_comb = normalized_components(summary)
    mismatches = {}
    for key in ["forbidden", "intercombination", "resonance"]:
        x = maybe_float(comps_target.get(key))
        c = maybe_float(comps_comb.get(key))
        mismatches[key] = abs(c - x) if c is not None and x is not None else None
    worst = max((k for k, v in mismatches.items() if v is not None), key=lambda k: mismatches[k], default=None)
    weights = read_weights(fit_dir / "o7_source_fit_weights.csv")
    stats = weight_stats(weights)
    fit_info = fitted.get("fit_info") or {}
    return {
        "source_set": set_name,
        "source_set_note": note,
        "n_source_levels": len(levels),
        "source_levels": ",".join(str(v) for v in levels),
        "xstar_R_f_over_i": r_x,
        "xstar_G_f_plus_i_over_r": g_x,
        "combined_R_f_over_i": r_c,
        "combined_G_f_plus_i_over_r": g_c,
        "combined_R_over_xstar": r_ratio,
        "combined_G_over_xstar": g_ratio,
        "target_reachable": reachable,
        "fit_objective": maybe_float(fit_info.get("objective")),
        "fit_status": fit_info.get("status"),
        "worst_component": worst,
        "worst_component_abs_delta": mismatches.get(worst) if worst else None,
        "effective_n_source_weights": stats.get("effective_n"),
        "n_nonzero_source_weights": stats.get("n_nonzero"),
        "top1_source_level": stats.get("top1_level"),
        "top1_source_weight": stats.get("top1_weight"),
        "top5_source_weight_sum": stats.get("top5_weight_sum"),
        "matrix_rank": solver_diag.get("matrix_rank"),
        "matrix_size": solver_diag.get("matrix_size"),
        "condition_number": solver_diag.get("condition_number"),
        "linear_residual_l2": solver_diag.get("linear_residual_l2"),
        "linear_residual_linf": solver_diag.get("linear_residual_linf"),
        "n_negative_populations_raw": solver_diag.get("n_negative_populations_raw"),
        "fit_dir": str(fit_dir),
        "summary_json": str(fit_dir / "o7_solver_source_fit_summary.json"),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scan expanded O VII source-level sets for the high-density mismatch")
    p.add_argument("fitsfile", nargs="?", help="XSTAR atdb.fits path")
    p.add_argument("--density-grid-dir", default="o7_solver_source_fit_density_xstar_grid")
    p.add_argument("--density", type=float, default=1.0e12)
    p.add_argument("--temperature", type=float, default=1.0e6)
    p.add_argument("--source-set", action="append", default=[], help="Custom source set NAME:2,3,4,...; may be repeated")
    p.add_argument("--sets", default="baseline,n_le_5,n_le_6,n_le_8,all_levels", help="Comma-separated auto set names to scan")
    p.add_argument("--out-dir", default="o7_high_density_expanded_source_scan")
    p.add_argument("--wavelength-min", type=float, default=21.5)
    p.add_argument("--wavelength-max", type=float, default=22.2)
    p.add_argument("--source-rate", type=float, default=1.0)
    p.add_argument("--combined-source-total-rate", type=float, default=1.0)
    p.add_argument("--rg-tolerance", type=float, default=5e-3)
    p.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    p.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    p.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    p.add_argument("--negative-population-tol", type=float, default=1e-8)
    p.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    p.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    p.add_argument("--null-rate-floor", type=float, default=0.0)
    p.add_argument("--index-cache", action="store_true")
    p.add_argument("--index-cache-path")
    p.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    p.add_argument("--dry-run", action="store_true", help="Write the source-set plan and summary without running fits")
    p.add_argument("--print-summary", action="store_true")
    p.add_argument("--print-commands", action="store_true")
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    density_grid_csv = Path(args.density_grid_dir) / "o7_solver_source_fit_density_grid.csv"
    if not density_grid_csv.exists():
        raise SystemExit(f"Density-grid CSV not found: {density_grid_csv}")
    high_row = find_density_row(read_csv_rows(density_grid_csv), float(args.density))
    xstar_csv = high_row.get("xstar_lines_csv") or high_row.get("xstar_reference_csv")
    xstar_col = high_row.get("xstar_value_column") or "emit_outward"
    if not xstar_csv:
        raise SystemExit(f"Density row for ne={args.density:g} does not contain xstar_lines_csv")
    if not Path(xstar_csv).exists():
        raise SystemExit(f"XSTAR line CSV from density row does not exist: {xstar_csv}")

    auto_sets: Dict[str, Tuple[List[int], str]] = {"baseline": (BASELINE_LEVELS, "validated n<=4 source-level baseline")}
    if args.fitsfile:
        level_rows = load_o7_level_rows(args.fitsfile, bool(args.index_cache), args.index_cache_format)
        for name, levels, note in build_auto_source_sets(level_rows):
            auto_sets[name] = (levels, note)
    for item in args.source_set:
        if ":" not in item:
            raise SystemExit("--source-set must have form NAME:2,3,4")
        name, text = item.split(":", 1)
        auto_sets[safe_name(name)] = (parse_level_list(text), "custom user-supplied source set")

    wanted = [safe_name(x) for x in str(args.sets).split(",") if x.strip()]
    source_sets: List[Tuple[str, List[int], str]] = []
    for name in wanted:
        if name not in auto_sets:
            raise SystemExit(f"Requested source set {name!r} is not available. Available: {sorted(auto_sets)}")
        levels, note = auto_sets[name]
        source_sets.append((name, levels, note))

    source_set_rows = [{"source_set": n, "n_source_levels": len(v), "source_levels": ",".join(map(str, v)), "note": note} for n, v, note in source_sets]
    source_sets_csv = out_dir / "o7_high_density_expanded_source_sets.csv"
    write_csv(source_sets_csv, source_set_rows)

    rows: List[dict] = []
    if not args.dry_run:
        for name, levels, note in source_sets:
            summary = run_solver_fit(args, name, levels, str(xstar_csv), str(xstar_col), out_dir)
            fit_dir = out_dir / f"fit_{safe_name(name)}"
            rows.append(summarize_set(name, note, levels, summary, float(args.rg_tolerance), fit_dir))
    else:
        for name, levels, note in source_sets:
            rows.append({
                "source_set": name,
                "source_set_note": note,
                "n_source_levels": len(levels),
                "source_levels": ",".join(str(v) for v in levels),
                "target_reachable": None,
            })

    scan_csv = out_dir / "o7_high_density_expanded_source_scan.csv"
    write_csv(scan_csv, rows)
    best = None
    if rows and not args.dry_run:
        reachable = [r for r in rows if str(r.get("target_reachable")).lower() == "true"]
        candidates = reachable or rows
        best = min(candidates, key=lambda r: (abs((maybe_float(r.get("combined_R_over_xstar")) or 0.0) - 1.0) + abs((maybe_float(r.get("combined_G_over_xstar")) or 0.0) - 1.0)))

    summary = {
        "electron_density_cm^-3": float(args.density),
        "temperature_K": float(args.temperature),
        "xstar_lines_csv": str(xstar_csv),
        "xstar_value_column": str(xstar_col),
        "rg_tolerance": float(args.rg_tolerance),
        "dry_run": bool(args.dry_run),
        "source_sets_csv": str(source_sets_csv),
        "scan_csv": str(scan_csv),
        "n_source_sets": len(source_sets),
        "rows": rows,
        "best_source_set": best.get("source_set") if best else None,
        "any_target_reachable": any(str(r.get("target_reachable")).lower() == "true" for r in rows),
        "interpretation": [],
    }
    interp: List[str] = []
    if args.dry_run:
        interp.append("Dry run: source sets were planned but no solver fits were executed.")
    elif summary["any_target_reachable"]:
        interp.append("At least one expanded source-level set reaches the density-specific XSTAR R/G target within tolerance.")
    else:
        interp.append("No scanned source-level set reaches the density-specific XSTAR R/G target within tolerance; the mismatch likely requires additional physics or different source assumptions.")
    if best:
        interp.append(f"Best scanned source set: {best.get('source_set')} with R/XSTAR={best.get('combined_R_over_xstar')} and G/XSTAR={best.get('combined_G_over_xstar')}.")
    summary["interpretation"] = interp
    summary_json = out_dir / "o7_high_density_expanded_source_scan_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.print_summary:
        print("O VII high-density expanded source-level scan")
        print("------------------------------------------------")
        print(f"density: {args.density:g} cm^-3")
        print(f"source sets: {', '.join(n for n, _l, _note in source_sets)}")
        print(f"wrote: {scan_csv}")
        print(f"wrote: {summary_json}")
        if args.dry_run:
            for line in interp:
                print("- " + line)
        if not args.dry_run:
            print("set          nlev   R/G combined        R/XSTAR G/XSTAR reachable top1")
            for row in rows:
                print(f"{row.get('source_set')}  {row.get('n_source_levels')}  {row.get('combined_R_f_over_i')}/{row.get('combined_G_f_plus_i_over_r')}  {row.get('combined_R_over_xstar')} {row.get('combined_G_over_xstar')} {row.get('target_reachable')} {row.get('top1_source_level')}")
            for line in interp:
                print("- " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
