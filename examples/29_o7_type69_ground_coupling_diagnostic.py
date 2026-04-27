#!/usr/bin/env python3
"""Interpret the O VII type-69 ground--resonance coupling at high density.

Versions 0.2.73--0.2.75 narrowed the ``ne=1e12 cm^-3`` O VII triplet
mismatch to type-69 record 22490, the ground-to-resonance transition
``1 -> 7``.  This diagnostic compares several temporary collision-network
variants to determine whether the mismatch is driven by the whole record, by
its excitation direction, or by its de-excitation direction.

The script is diagnostic only.  It does not alter the ATDB or any packaged
reference products.  Each case refits the empirical source weights with the
same solver settings by calling ``examples/20_o7_solver_source_fit.py``.
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
from typing import List, Optional, Sequence, Tuple

BASELINE_LEVELS = "2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20"


def maybe_float(value) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
    except Exception:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def density_equal(a: float, b: float, rel: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)), 1.0)


def safe_name(text: str) -> str:
    out = str(text).strip().lower().replace("<=", "le").replace(">=", "ge")
    out = out.replace(".", "p").replace("+", "").replace("-", "m")
    return re.sub(r"[^a-z0-9]+", "_", out).strip("_") or "case"


def parse_float_list(text: str) -> List[float]:
    vals: List[float] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            vals.append(float(part))
    return vals


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
    raise SystemExit(f"Could not find density {density:g} in density-grid CSV")


def resolve_density_grid_csv(grid_dir: Path) -> Path:
    for name in ["o7_solver_source_fit_density_grid.csv", "o7_solver_source_fit_density_xstar_grid.csv"]:
        path = grid_dir / name
        if path.exists():
            return path
    raise SystemExit(f"Could not find density-grid CSV in {grid_dir}")


def xstar_reference_for_density(grid_dir: Path, density: float) -> Tuple[str, str, dict]:
    row = find_density_row(read_csv_rows(resolve_density_grid_csv(grid_dir)), density)
    xstar_csv = row.get("xstar_lines_csv") or ""
    if not xstar_csv:
        fit_dir = Path(row.get("fit_dir") or "")
        for cand in [fit_dir / "o7_solver_source_fit_summary.json", grid_dir / fit_dir / "o7_solver_source_fit_summary.json"]:
            if cand.exists():
                xstar_csv = ((read_json(cand).get("xstar_reference") or {}).get("path") or "")
                break
    if not xstar_csv:
        raise SystemExit(f"Density-grid row for ne={density:g} does not record xstar_lines_csv")
    xstar_path = Path(xstar_csv)
    if not xstar_path.exists():
        for cand in [grid_dir / xstar_path, grid_dir.parent / xstar_path]:
            if cand.exists():
                xstar_path = cand
                break
    if not xstar_path.exists():
        raise SystemExit(f"XSTAR CSV for ne={density:g} not found: {xstar_csv}")
    return str(xstar_path), str(row.get("xstar_value_column") or "emit_outward"), row


def normalized_components_from_summary(summary: dict) -> dict:
    comps = ((summary.get("combined_source_validation") or {}).get("triplet_components") or {})
    vals = {k: maybe_float(comps.get(k)) for k in ["forbidden", "intercombination", "resonance"]}
    total = sum(v for v in vals.values() if v is not None)
    if total <= 0.0:
        return {k: None for k in vals}
    return {k: (v / total if v is not None else None) for k, v in vals.items()}


def worst_component(summary: dict) -> Tuple[Optional[str], Optional[float]]:
    x = (summary.get("target_components_normalized") or {})
    y = normalized_components_from_summary(summary)
    worst_name = None
    worst_delta = None
    for name in ["forbidden", "intercombination", "resonance"]:
        xv = maybe_float(x.get(name)); yv = maybe_float(y.get(name))
        if xv is None or yv is None:
            continue
        d = abs(yv - xv)
        if worst_delta is None or d > worst_delta:
            worst_name = name; worst_delta = d
    return worst_name, worst_delta


def top_weight(summary: dict) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    path = Path(summary.get("compatible_weights_csv") or summary.get("weights_csv") or "")
    if not path.exists():
        return None, None, None
    rows = read_csv_rows(path)
    vals = []
    for row in rows:
        lev = row.get("level_index") or row.get("source_level")
        weight = maybe_float(row.get("weight") or row.get("source_weight"))
        try:
            lev_i = int(float(lev))
        except Exception:
            continue
        if weight is not None:
            vals.append((lev_i, weight))
    if not vals:
        return None, None, None
    vals.sort(key=lambda x: x[1], reverse=True)
    s2 = sum(w*w for _, w in vals)
    neff = (1.0 / s2) if s2 > 0 else None
    return vals[0][0], vals[0][1], neff


def build_cases(record: int, record_scales: Sequence[float], type69_scales: Sequence[float], direction_scales: Sequence[float]) -> List[dict]:
    cases: List[dict] = [{"case": "baseline", "family": "baseline", "record_scales": [], "data_type_scales": [], "direction_scales": [], "note": "unmodified network"}]
    for scale in record_scales:
        if float(scale) == 1.0:
            continue
        cases.append({"case": safe_name(f"record_{record}_x{scale:g}"), "family": "record", "record_scales": [f"{record}:{float(scale):.16g}"], "data_type_scales": [], "direction_scales": [], "scale": float(scale), "note": "symmetric scaling of excitation and de-excitation"})
    # Removal is useful even if 0 is not in the record scale list.
    if all(float(s) != 0.0 for s in record_scales):
        cases.append({"case": f"record_{record}_removed", "family": "record_removed", "record_scales": [f"{record}:0"], "data_type_scales": [], "direction_scales": [], "scale": 0.0, "note": "remove both directions for this record"})
    for scale in type69_scales:
        if float(scale) == 1.0:
            continue
        cases.append({"case": safe_name(f"type69_x{scale:g}"), "family": "type69", "record_scales": [], "data_type_scales": [f"69:{float(scale):.16g}"], "direction_scales": [], "scale": float(scale), "note": "scale all type-69 collision rows"})
    for scale in direction_scales:
        if float(scale) != 1.0:
            cases.append({"case": safe_name(f"record_{record}_excitation_x{scale:g}"), "family": "excitation_direction", "record_scales": [], "data_type_scales": [], "direction_scales": [f"{record}:excitation:{float(scale):.16g}"], "scale": float(scale), "note": "scale only lower->upper excitation for this record"})
            cases.append({"case": safe_name(f"record_{record}_deexcitation_x{scale:g}"), "family": "deexcitation_direction", "record_scales": [], "data_type_scales": [], "direction_scales": [f"{record}:deexcitation:{float(scale):.16g}"], "scale": float(scale), "note": "scale only upper->lower de-excitation for this record"})
    cases.append({"case": f"record_{record}_excitation_only", "family": "direction_isolation", "record_scales": [], "data_type_scales": [], "direction_scales": [f"{record}:deexcitation:0"], "scale": 0.0, "note": "keep excitation, remove de-excitation"})
    cases.append({"case": f"record_{record}_deexcitation_only", "family": "direction_isolation", "record_scales": [], "data_type_scales": [], "direction_scales": [f"{record}:excitation:0"], "scale": 0.0, "note": "keep de-excitation, remove excitation"})
    return cases


def run_fit_case(args, case: dict, xstar_csv: str, xstar_col: str, out_dir: Path) -> dict:
    fit_dir = out_dir / f"fit_{case['case']}"
    cmd = [
        sys.executable,
        "examples/20_o7_solver_source_fit.py",
        args.fitsfile,
        "--element", "O",
        "--ion-stage", "7",
        "--temperature", f"{float(args.temperature):.16g}",
        "--electron-density", f"{float(args.density):.16g}",
        "--source-levels", args.source_levels,
        "--source-rate", "1",
        "--combined-source-total-rate", f"{float(args.combined_source_total_rate):.16g}",
        "--wavelength-min", f"{float(args.wavelength_min):.16g}",
        "--wavelength-max", f"{float(args.wavelength_max):.16g}",
        "--xstar-lines-csv", xstar_csv,
        "--xstar-value-column", xstar_col,
        "--out-dir", str(fit_dir),
        "--linear-solver", args.linear_solver,
        "--rank-deficient-action", args.rank_deficient_action,
        "--negative-population-action", args.negative_population_action,
        "--negative-population-tol", f"{float(args.negative_population_tol):.16g}",
        "--null-rate-floor", f"{float(args.null_rate_floor):.16g}",
    ]
    if args.prune_null_rate_levels:
        cmd.append("--prune-null-rate-levels")
    else:
        cmd.append("--no-prune-null-rate-levels")
    if args.index_cache:
        cmd.append("--index-cache")
        if args.index_cache_path:
            cmd += ["--index-cache-path", args.index_cache_path]
        cmd += ["--index-cache-format", args.index_cache_format]
    for spec in case.get("data_type_scales") or []:
        cmd += ["--collision-data-type-scale", str(spec)]
    for spec in case.get("record_scales") or []:
        cmd += ["--collision-record-scale", str(spec)]
    for spec in case.get("direction_scales") or []:
        cmd += ["--collision-record-direction-scale", str(spec)]
    if args.print_commands:
        print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    summary_path = fit_dir / "o7_solver_source_fit_summary.json"
    summary = read_json(summary_path)
    pred = summary.get("combined_source_validation") or summary.get("fitted_prediction") or {}
    xstar = summary.get("xstar_reference", {})
    r_x = maybe_float(xstar.get("R_f_over_i"))
    g_x = maybe_float(xstar.get("G_f_plus_i_over_r"))
    r = maybe_float(pred.get("R_f_over_i"))
    g = maybe_float(pred.get("G_f_plus_i_over_r"))
    worst, worst_delta = worst_component(summary)
    top_lev, top_w, neff = top_weight(summary)
    row = {
        "case": case["case"],
        "family": case.get("family"),
        "record": int(args.record),
        "scale": case.get("scale"),
        "collision_data_type_scale": ";".join(case.get("data_type_scales") or []),
        "collision_record_scale": ";".join(case.get("record_scales") or []),
        "collision_record_direction_scale": ";".join(case.get("direction_scales") or []),
        "note": case.get("note"),
        "xstar_R_f_over_i": r_x,
        "xstar_G_f_plus_i_over_r": g_x,
        "combined_R_f_over_i": r,
        "combined_G_f_plus_i_over_r": g,
        "R_over_xstar": (r / r_x) if r is not None and r_x not in (None, 0.0) else None,
        "G_over_xstar": (g / g_x) if g is not None and g_x not in (None, 0.0) else None,
        "target_reachable": bool(abs((r / r_x) - 1.0) <= args.rg_tolerance and abs((g / g_x) - 1.0) <= args.rg_tolerance) if r is not None and g is not None and r_x not in (None, 0.0) and g_x not in (None, 0.0) else False,
        "fit_objective": summary.get("fit_objective"),
        "worst_component": worst,
        "worst_component_abs_delta": worst_delta,
        "top_source_level": top_lev,
        "top_source_weight": top_w,
        "source_weight_neff": neff,
        "matrix_rank": ((summary.get("combined_source_validation") or {}).get("solver_info") or {}).get("matrix_rank"),
        "matrix_size": ((summary.get("combined_source_validation") or {}).get("solver_info") or {}).get("matrix_size"),
        "condition_number": ((summary.get("combined_source_validation") or {}).get("solver_info") or {}).get("condition_number"),
        "linear_residual_l2": ((summary.get("combined_source_validation") or {}).get("solver_info") or {}).get("linear_residual_l2"),
        "linear_residual_linf": ((summary.get("combined_source_validation") or {}).get("solver_info") or {}).get("linear_residual_linf"),
        "fit_dir": str(fit_dir),
        "summary_json": str(summary_path),
    }
    return row


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Diagnose O VII type-69 record-22490 physical/directional high-density coupling")
    parser.add_argument("fitsfile")
    parser.add_argument("--density-grid-dir", default="o7_solver_source_fit_density_xstar_grid")
    parser.add_argument("--density", type=float, default=1.0e12)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--record", type=int, default=22490)
    parser.add_argument("--record-scales", default="0.1,0.2,0.5,2")
    parser.add_argument("--type69-scales", default="0.1,0.2,0.5,2")
    parser.add_argument("--direction-scales", default="0,0.1,0.2,0.5,2")
    parser.add_argument("--source-levels", default=BASELINE_LEVELS)
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--combined-source-total-rate", type=float, default=1.0)
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--rg-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--out-dir", default="o7_type69_ground_coupling_diagnostic")
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-commands", action="store_true")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xstar_csv, xstar_col, grid_row = xstar_reference_for_density(Path(args.density_grid_dir), float(args.density))
    cases = build_cases(int(args.record), parse_float_list(args.record_scales), parse_float_list(args.type69_scales), parse_float_list(args.direction_scales))
    rows: List[dict] = []
    for case in cases:
        rows.append(run_fit_case(args, case, xstar_csv, xstar_col, out_dir))

    scan_csv = out_dir / "o7_type69_ground_coupling_diagnostic.csv"
    summary_json = out_dir / "o7_type69_ground_coupling_diagnostic_summary.json"
    write_csv(scan_csv, rows)
    reachable = [r for r in rows if r.get("target_reachable")]
    best = min(rows, key=lambda r: abs(float(r.get("R_over_xstar") or 1e99) - 1.0) + abs(float(r.get("G_over_xstar") or 1e99) - 1.0)) if rows else None
    direction_rows = [r for r in rows if r.get("family") in {"excitation_direction", "deexcitation_direction", "direction_isolation"}]
    best_direction = min(direction_rows, key=lambda r: abs(float(r.get("R_over_xstar") or 1e99) - 1.0) + abs(float(r.get("G_over_xstar") or 1e99) - 1.0)) if direction_rows else None
    summary = {
        "fitsfile": args.fitsfile,
        "ion": "O VII",
        "electron_density_cm^-3": float(args.density),
        "temperature_K": float(args.temperature),
        "record": int(args.record),
        "xstar_lines_csv": xstar_csv,
        "xstar_value_column": xstar_col,
        "density_grid_row": grid_row,
        "n_cases": len(rows),
        "reachable_cases": [r["case"] for r in reachable],
        "best_case": best,
        "best_direction_case": best_direction,
        "scan_csv": str(scan_csv),
        "summary_json": str(summary_json),
        "interpretation": "Direction-specific cases intentionally break detailed balance. If de-excitation scaling/removal fixes R/G while excitation-only does not, the high-density mismatch is controlled by the reverse part of the type-69 ground-resonance pair.",
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    if args.print_summary:
        print("O VII type-69 ground-coupling diagnostic")
        print("-----------------------------------------")
        print(f"density: {float(args.density):g} cm^-3")
        print(f"record: {int(args.record)}")
        print(f"cases: {len(rows)}")
        print(f"wrote: {scan_csv}")
        print(f"wrote: {summary_json}")
        print("case                         family                 R/G combined        R/XSTAR G/XSTAR reachable worst")
        for r in rows:
            print(f"{r['case']:<28} {str(r.get('family')):<22} {r.get('combined_R_f_over_i')}/{r.get('combined_G_f_plus_i_over_r')}  {r.get('R_over_xstar')} {r.get('G_over_xstar')} {r.get('target_reachable')} {r.get('worst_component')}")
        if best:
            print(f"best case: {best.get('case')} R/XSTAR={best.get('R_over_xstar')} G/XSTAR={best.get('G_over_xstar')}")
        if best_direction:
            print(f"best direction case: {best_direction.get('case')} R/XSTAR={best_direction.get('R_over_xstar')} G/XSTAR={best_direction.get('G_over_xstar')}")
        if reachable:
            print("reachable cases: " + ", ".join(r["case"] for r in reachable))
        else:
            print("reachable cases: none")


if __name__ == "__main__":
    main()
