#!/usr/bin/env python3
"""Scan O VII high-density rate-network sensitivity.

This diagnostic follows ``examples/24_o7_high_density_mismatch_diagnostics.py``
and ``examples/25_o7_high_density_expanded_source_scan.py``.  After the
expanded source-level scan showed that adding more empirical source levels does
not reach the ``ne=1e12 cm^-3`` XSTAR O VII target, this script asks whether the
mismatch is sensitive to selected collision-rate blocks in the n=2 He-like
network.

The scan is explicitly diagnostic.  It does **not** change the packaged atomic
data.  It passes temporary scale factors to ``xstar_atomic.solver`` through
``examples/20_o7_solver_source_fit.py`` and then refits empirical source weights
for each scaled network.

Built-in rate families
----------------------

``metastable``
    Symmetric pair scaling for level 2 connected to levels 3, 4, and 5.  This
    preserves excitation/de-excitation ratios while changing the overall
    collisional coupling strength out of the forbidden upper level.

``type68`` / ``type69``
    Scale all evaluated collision rows decoded from XSTAR data type 68 or 69.

Outputs
-------

``o7_high_density_rate_sensitivity_scan.csv``
    One row per scale case with R/G, component mismatch, solver diagnostics, and
    reachability flags.

``o7_high_density_rate_sensitivity_summary.json``
    Combined JSON summary and best cases.
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


BASELINE_LEVELS = "2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20"


def discover_xstar_test_run_grid(base: Path = Path("xstar_test_run")) -> Dict[float, Path]:
    entries = {
        1.0: base / "o7_ne1" / "xstar_o7_triplet_lines.csv",
        1.0e4: base / "o7_ne1e4" / "xstar_o7_triplet_lines.csv",
        1.0e8: base / "o7_ne1e8" / "xstar_o7_triplet_lines.csv",
        1.0e10: base / "o7_ne1e10" / "xstar_o7_triplet_lines.csv",
        1.0e12: base / "o7_ne1e12" / "xstar_o7_triplet_lines.csv",
    }
    missing = [str(path) for path in entries.values() if not path.exists()]
    if missing:
        raise SystemExit("Missing packaged O VII density-grid XSTAR references: " + ", ".join(missing))
    return entries


def density_spec_from_mapping_csv(mapping_csv: Path, density: float) -> Tuple[str, str, dict]:
    rows = read_csv_rows(mapping_csv)
    row = find_density_row(rows, density)
    xstar_csv = row.get("xstar_lines_csv") or row.get("path") or row.get("csv") or ""
    if not xstar_csv:
        raise SystemExit(f"Mapping row for ne={density:g} does not contain xstar_lines_csv/path")
    xstar_path = Path(xstar_csv)
    if not xstar_path.exists():
        for cand in [mapping_csv.parent / xstar_path, Path.cwd() / xstar_path]:
            if cand.exists():
                xstar_path = cand
                break
    if not xstar_path.exists():
        raise SystemExit(f"XSTAR CSV for ne={density:g} not found: {xstar_csv}")
    return str(xstar_path), str(row.get("xstar_value_column") or "emit_outward"), row


def expected_o7_high_density_target(density: float) -> Optional[Tuple[float, float]]:
    if density_equal(float(density), 1.0e12, rel=1e-6):
        return 0.0830641, 4.51966
    return None


def validate_density_grid_target(row: dict, density: float, allow_unexpected: bool = False) -> None:
    expected = expected_o7_high_density_target(density)
    if expected is None or allow_unexpected:
        return
    rx = maybe_float(row.get("xstar_R_f_over_i"))
    gx = maybe_float(row.get("xstar_G_f_plus_i_over_r"))
    if rx is None or gx is None:
        return
    er, eg = expected
    if abs(rx / er - 1.0) > 5.0e-3 or abs(gx / eg - 1.0) > 5.0e-3:
        raise SystemExit(
            f"Density-grid directory appears stale or placeholder-based for ne={density:g}: "
            f"found XSTAR R/G={rx:.6g}/{gx:.6g}, expected about {er:.6g}/{eg:.6g}. "
            "Regenerate example 22 with --auto-xstar-test-run-grid or pass --allow-unexpected-xstar-target."
        )


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


def safe_name(text: str) -> str:
    out = str(text).strip().lower().replace("<=", "le").replace(">=", "ge")
    out = out.replace(".", "p").replace("+", "").replace("-", "m")
    return re.sub(r"[^a-z0-9]+", "_", out).strip("_") or "case"


def density_equal(a: float, b: float, rel: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)), 1.0)


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
    candidates = [
        grid_dir / "o7_solver_source_fit_density_grid.csv",
        grid_dir / "o7_solver_source_fit_density_xstar_grid.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise SystemExit(f"Could not find density-grid CSV in {grid_dir}")


def xstar_reference_for_density(grid_dir: Path, density: float, allow_unexpected: bool = False) -> Tuple[str, str, dict]:
    csv_path = resolve_density_grid_csv(grid_dir)
    row = find_density_row(read_csv_rows(csv_path), density)
    validate_density_grid_target(row, density, allow_unexpected=allow_unexpected)
    xstar_csv = row.get("xstar_lines_csv") or ""
    if not xstar_csv:
        # Fall back to the per-density fit summary if needed.
        fit_dir = Path(row.get("fit_dir") or "")
        candidates = []
        if fit_dir:
            candidates.extend([fit_dir / "o7_solver_source_fit_summary.json", grid_dir / fit_dir / "o7_solver_source_fit_summary.json"])
        for cand in candidates:
            if cand.exists():
                ref = (read_json(cand).get("xstar_reference") or {})
                xstar_csv = ref.get("path") or ""
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


def parse_float_list(text: str) -> List[float]:
    out: List[float] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out


def build_scan_cases(families: Sequence[str], scales: Sequence[float]) -> List[dict]:
    cases: List[dict] = [{"case": "baseline", "family": "baseline", "scale": 1.0, "data_type_scales": [], "pair_scales": []}]
    seen = {"baseline"}
    for family in families:
        fam = family.strip().lower()
        if not fam:
            continue
        for scale in scales:
            if abs(float(scale) - 1.0) < 1e-15:
                continue
            if fam in {"metastable", "metastable_2_345", "2_345"}:
                name = f"metastable_2_345_x{scale:g}"
                pair_scales = [f"2:3:{scale:g}", f"2:4:{scale:g}", f"2:5:{scale:g}"]
                data_type_scales: List[str] = []
            elif fam in {"type68", "68"}:
                name = f"type68_x{scale:g}"
                pair_scales = []
                data_type_scales = [f"68:{scale:g}"]
            elif fam in {"type69", "69"}:
                name = f"type69_x{scale:g}"
                pair_scales = []
                data_type_scales = [f"69:{scale:g}"]
            elif fam in {"global", "all"}:
                name = f"global_collision_x{scale:g}"
                pair_scales = []
                data_type_scales = []
            else:
                raise SystemExit(f"Unknown scan family: {family!r}")
            key = safe_name(name)
            if key in seen:
                continue
            seen.add(key)
            cases.append({"case": key, "family": fam, "scale": float(scale), "data_type_scales": data_type_scales, "pair_scales": pair_scales, "global_scale": float(scale) if fam in {"global", "all"} else 1.0})
    return cases


def normalized_components_from_summary(summary: dict) -> dict:
    comps = ((summary.get("combined_source_validation") or {}).get("triplet_components") or {})
    vals = {k: maybe_float(comps.get(k)) for k in ["forbidden", "intercombination", "resonance"]}
    total = sum(v for v in vals.values() if v is not None)
    if total <= 0.0:
        return {k: None for k in vals}
    return {k: (v / total if v is not None else None) for k, v in vals.items()}


def worst_component(summary: dict) -> Tuple[Optional[str], Optional[float]]:
    target = summary.get("target_components_normalized") or {}
    combined = normalized_components_from_summary(summary)
    worst_name = None
    worst_delta = None
    for name in ["forbidden", "intercombination", "resonance"]:
        x = maybe_float(target.get(name))
        y = maybe_float(combined.get(name))
        if x is None or y is None:
            continue
        delta = abs(y - x)
        if worst_delta is None or delta > worst_delta:
            worst_name = name
            worst_delta = delta
    return worst_name, worst_delta


def run_case(args, case: dict, xstar_csv: str, xstar_col: str, out_dir: Path) -> dict:
    fit_dir = out_dir / f"fit_{case['case']}"
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("20_o7_solver_source_fit.py")),
        args.fitsfile,
        "--element", "O",
        "--ion-stage", "7",
        "--temperature", f"{float(args.temperature):.16g}",
        "--electron-density", f"{float(args.density):.16g}",
        "--source-levels", args.source_levels,
        "--source-rate", f"{float(args.source_rate):.16g}",
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
    ]
    if args.prune_null_rate_levels:
        cmd += ["--prune-null-rate-levels", "--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
    if float(case.get("global_scale") or 1.0) != 1.0:
        cmd += ["--collision-rate-scale", f"{float(case['global_scale']):.16g}"]
    for spec in case.get("data_type_scales") or []:
        cmd += ["--collision-data-type-scale", str(spec)]
    for spec in case.get("pair_scales") or []:
        cmd += ["--collision-pair-scale", str(spec)]
    mode = getattr(args, "collision_type69_ground_excitation_mode", "include") or "include"
    if mode != "include":
        cmd += ["--collision-type69-ground-excitation-mode", str(mode)]
    if args.index_cache:
        if args.index_cache_path:
            cmd += ["--index-cache", "--index-cache-path", str(args.index_cache_path), "--index-cache-format", args.index_cache_format]
        else:
            cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]
    if args.keep_unit_runs:
        cmd += ["--keep-unit-runs"]
    if args.print_subprocess_summary:
        cmd += ["--print-summary"]
    subprocess.run(cmd, check=True)
    summary_path = fit_dir / "o7_solver_source_fit_summary.json"
    summary = read_json(summary_path)
    combined = summary.get("combined_source_validation") or {}
    fitted = summary.get("fitted_prediction") or {}
    fit_info = fitted.get("fit_info") or {}
    xstar = summary.get("xstar_reference") or {}
    diag = combined.get("solver_diagnostics") or {}
    worst_name, worst_delta = worst_component(summary)
    R = maybe_float(combined.get("R_f_over_i"))
    G = maybe_float(combined.get("G_f_plus_i_over_r"))
    Rx = maybe_float(xstar.get("R_f_over_i"))
    Gx = maybe_float(xstar.get("G_f_plus_i_over_r"))
    Rratio = (R / Rx) if R is not None and Rx not in (None, 0.0) else None
    Gratio = (G / Gx) if G is not None and Gx not in (None, 0.0) else None
    reachable = bool(Rratio is not None and Gratio is not None and abs(Rratio - 1.0) <= args.rg_tolerance and abs(Gratio - 1.0) <= args.rg_tolerance)
    return {
        "case": case["case"],
        "family": case.get("family"),
        "scale": case.get("scale"),
        "global_collision_scale": case.get("global_scale", 1.0),
        "collision_data_type_scale": ";".join(case.get("data_type_scales") or []),
        "collision_pair_scale": ";".join(case.get("pair_scales") or []),
        "electron_density_cm^-3": float(args.density),
        "xstar_R_f_over_i": Rx,
        "xstar_G_f_plus_i_over_r": Gx,
        "combined_R_f_over_i": R,
        "combined_G_f_plus_i_over_r": G,
        "R_over_xstar": Rratio,
        "G_over_xstar": Gratio,
        "target_reachable": reachable,
        "fit_objective": fit_info.get("objective"),
        "fit_status": fit_info.get("status"),
        "worst_component": worst_name,
        "worst_component_abs_delta": worst_delta,
        "matrix_rank": diag.get("matrix_rank"),
        "matrix_size": diag.get("matrix_size"),
        "condition_number": diag.get("condition_number"),
        "linear_residual_l2": diag.get("linear_residual_l2"),
        "linear_residual_linf": diag.get("linear_residual_linf"),
        "n_negative_populations_raw": diag.get("n_negative_populations_raw"),
        "fit_dir": str(fit_dir),
        "summary_json": str(summary_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--density-grid-dir", default=None, help="Generated output directory from example 22; optional when --auto-xstar-test-run-grid or --xstar-grid-summary-csv is supplied")
    parser.add_argument("--xstar-grid-summary-csv", help="Density-to-XSTAR-lines mapping CSV used directly for the selected target density")
    parser.add_argument("--auto-xstar-test-run-grid", action="store_true", help="Use packaged converted O VII density-specific XSTAR CSVs under xstar_test_run/o7_ne*/ instead of requiring a generated density-grid directory")
    parser.add_argument("--allow-unexpected-xstar-target", action="store_true", help="Allow a generated density-grid directory whose ne=1e12 target does not match the validated density-specific XSTAR reference; diagnostic only")
    parser.add_argument("--density", type=float, default=1.0e12)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--source-levels", default=BASELINE_LEVELS)
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--combined-source-total-rate", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--families", default="metastable,type68,type69", help="Comma-separated scan families: metastable,type68,type69,global")
    parser.add_argument("--scales", default="0.1,0.2,0.5,1,2,5,10")
    parser.add_argument("--rg-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--out-dir", default="o7_high_density_rate_sensitivity")
    parser.add_argument("--keep-unit-runs", action="store_true")
    parser.add_argument("--collision-type69-ground-excitation-mode", choices=["include", "suppress-resonance", "suppress-all"], default="include",
                        help="Diagnostic/experimental type-69 ground-excitation mode forwarded to example 20/solver for every case.")
    parser.add_argument("--print-subprocess-summary", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.auto_xstar_test_run_grid:
        grid = discover_xstar_test_run_grid()
        match = None
        for den, path in grid.items():
            if density_equal(den, float(args.density)):
                match = path
                break
        if match is None:
            raise SystemExit(f"No packaged xstar_test_run density reference for ne={float(args.density):g}")
        xstar_csv, xstar_col, density_row = str(match), "emit_outward", {"source": "auto-xstar-test-run-grid", "xstar_lines_csv": str(match)}
    elif args.xstar_grid_summary_csv:
        xstar_csv, xstar_col, density_row = density_spec_from_mapping_csv(Path(args.xstar_grid_summary_csv), float(args.density))
    else:
        grid_dir = Path(args.density_grid_dir or "o7_solver_source_fit_density_xstar_grid")
        xstar_csv, xstar_col, density_row = xstar_reference_for_density(grid_dir, float(args.density), allow_unexpected=args.allow_unexpected_xstar_target)
    families = [part.strip() for part in args.families.split(",") if part.strip()]
    scales = parse_float_list(args.scales)
    cases = build_scan_cases(families, scales)

    rows: List[dict] = []
    for case in cases:
        rows.append(run_case(args, case, xstar_csv, xstar_col, out_dir))

    best = min(rows, key=lambda r: abs(float(r.get("R_over_xstar") or 1e99) - 1.0) + abs(float(r.get("G_over_xstar") or 1e99) - 1.0)) if rows else None
    reachable = [row for row in rows if row.get("target_reachable")]
    out_csv = out_dir / "o7_high_density_rate_sensitivity_scan.csv"
    out_summary = out_dir / "o7_high_density_rate_sensitivity_summary.json"
    write_csv(out_csv, rows)
    summary = {
        "fitsfile": args.fitsfile,
        "temperature_K": float(args.temperature),
        "electron_density_cm^-3": float(args.density),
        "density_grid_dir": str(args.density_grid_dir) if args.density_grid_dir else None,
        "xstar_grid_summary_csv": str(args.xstar_grid_summary_csv) if args.xstar_grid_summary_csv else None,
        "auto_xstar_test_run_grid": bool(args.auto_xstar_test_run_grid),
        "xstar_lines_csv": xstar_csv,
        "xstar_value_column": xstar_col,
        "density_grid_row": density_row,
        "families": families,
        "scales": scales,
        "collision_type69_ground_excitation_mode": args.collision_type69_ground_excitation_mode,
        "n_cases": len(rows),
        "n_reachable": len(reachable),
        "best_case": best,
        "reachable_cases": reachable[:20],
        "scan_csv": str(out_csv),
        "note": "Diagnostic only: rate scales are temporary sensitivity factors, not physical atomic-data edits.",
    }
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("O VII high-density rate-sensitivity diagnostic")
    print("------------------------------------------------")
    print(f"density: {float(args.density):.6g} cm^-3")
    print(f"cases: {len(rows)}")
    print(f"wrote: {out_csv}")
    print(f"wrote: {out_summary}")
    if args.print_summary:
        print("case                  R/G combined        R/XSTAR G/XSTAR reachable worst")
        for row in rows:
            print(
                f"{row['case']:<21} "
                f"{float(row['combined_R_f_over_i']):.6g}/{float(row['combined_G_f_plus_i_over_r']):.6g}  "
                f"{float(row['R_over_xstar']):.6g} {float(row['G_over_xstar']):.6g} "
                f"{row['target_reachable']} {row.get('worst_component')}"
            )
        if best:
            print(f"best case: {best['case']} with R/XSTAR={best.get('R_over_xstar')} G/XSTAR={best.get('G_over_xstar')}")
        if reachable:
            print(f"reachable cases: {', '.join(row['case'] for row in reachable)}")
        else:
            print("No scanned rate-scale case reaches the density-specific XSTAR R/G target within tolerance.")


if __name__ == "__main__":
    main()
