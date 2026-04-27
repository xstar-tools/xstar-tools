#!/usr/bin/env python3
"""Diagnose the high-density O VII source-fit mismatch.

This Stage-6 diagnostic reads the outputs of
``examples/22_o7_solver_source_fit_density_xstar_grid.py`` or
``examples/21_o7_solver_source_fit_density_grid.py`` and focuses on the density
where the empirical source-fit target becomes unreachable, by default
``ne=1e12 cm^-3``.  It compares the XSTAR target, fixed reference-density
weights, and refitted combined-source solution; summarizes which triplet
component drives the mismatch; reports source-weight collapse; and, when an
``atdb.fits`` path is supplied, evaluates the type-68/69 metastable-to-
intercombination collision rates for levels 2 -> 3,4,5.

The script is diagnostic only.  It does not change the solver or the fitted
weights, and the empirical weights remain non-physical level-source proxies.

Example
-------

.. code-block:: bash

   PYTHONPATH=src python examples/24_o7_high_density_mismatch_diagnostics.py \
     ../xstar/data/atdb.fits \
     --density-grid-dir o7_solver_source_fit_density_xstar_grid \
     --density 1e12 \
     --reference-density 1 \
     --out-dir o7_high_density_mismatch \
     --print-summary

Outputs
-------

``o7_high_density_component_mismatch.csv``
    Normalized triplet-component comparison for forbidden, intercombination,
    and resonance components.

``o7_high_density_source_weight_changes.csv``
    Source-level weights at the reference and high density, sorted by absolute
    change.

``o7_high_density_collision_rates.csv``
    Optional ATDB collision-rate diagnostics for level 2 -> 3,4,5 if a FITS
    path is supplied.

``o7_high_density_mismatch_summary.json``
    Combined JSON summary.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


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


def safe_density_name(value: float) -> str:
    return f"{float(value):.6g}".replace("+", "").replace("-", "m").replace(".", "p")


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



def resolve_grid_output_path(value: Optional[str], grid_dir: Path, fallback: Path) -> Path:
    """Resolve paths stored in density-grid CSVs across relocated output dirs.

    Example 21 writes paths relative to the working directory used when it ran.
    If a density-grid directory is moved or unpacked elsewhere, those recorded
    relative paths may no longer exist.  This helper first honors an existing
    absolute or current-working-directory path, then tries paths relative to the
    supplied density-grid directory and its parent.
    """
    if value:
        raw = Path(str(value))
        candidates = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.extend([
                raw,
                grid_dir / raw,
                grid_dir.parent / raw,
                grid_dir / raw.name,
            ])
        for cand in candidates:
            if cand.exists():
                return cand
    return fallback

def find_density_row(rows: Sequence[dict], density: float) -> dict:
    for row in rows:
        val = maybe_float(row.get("electron_density_cm^-3") or row.get("density") or row.get("ne"))
        if val is not None and density_equal(val, density):
            return dict(row)
    available = [row.get("electron_density_cm^-3") for row in rows]
    raise SystemExit(f"Could not find density {density:g} in density-grid CSV. Available densities: {available}")


def normalize_components(components: dict) -> dict:
    vals = {
        "forbidden": maybe_float(components.get("forbidden")),
        "intercombination": maybe_float(components.get("intercombination")),
        "resonance": maybe_float(components.get("resonance")),
    }
    total = sum(v for v in vals.values() if v is not None)
    if total <= 0.0:
        return {k: None for k in vals}
    return {k: (v / total if v is not None else None) for k, v in vals.items()}


def component_rows_from_fit_summary(summary: dict, density: float) -> List[dict]:
    xstar = summary.get("target_components_normalized") or {}
    fitted = summary.get("fitted_prediction") or {}
    fitted_components = fitted.get("components") or {}
    combined = summary.get("combined_source_validation") or {}
    combined_norm = normalize_components(combined.get("triplet_components") or {})
    fixed = None
    rows = []
    for name in ["forbidden", "intercombination", "resonance"]:
        x = maybe_float(xstar.get(name))
        f = maybe_float(fitted_components.get(name))
        c = maybe_float(combined_norm.get(name))
        rows.append({
            "electron_density_cm^-3": float(density),
            "component": name,
            "xstar_target_fraction": x,
            "fitted_linear_fraction": f,
            "combined_solver_fraction": c,
            "combined_minus_xstar": (c - x) if c is not None and x is not None else None,
            "combined_over_xstar": (c / x) if c is not None and x not in (None, 0.0) else None,
            "fitted_minus_xstar": (f - x) if f is not None and x is not None else None,
            "fitted_over_xstar": (f / x) if f is not None and x not in (None, 0.0) else None,
        })
    return rows


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


def weight_rows(reference: Dict[int, float], high: Dict[int, float]) -> List[dict]:
    levels = sorted(set(reference) | set(high))
    rows = []
    for level in levels:
        ref = float(reference.get(level, 0.0))
        cur = float(high.get(level, 0.0))
        rows.append({
            "source_level": int(level),
            "reference_weight": ref,
            "high_density_weight": cur,
            "delta_high_minus_reference": cur - ref,
            "abs_delta": abs(cur - ref),
            "ratio_high_over_reference": (cur / ref) if ref > 0.0 else None,
        })
    rows.sort(key=lambda r: r["abs_delta"], reverse=True)
    return rows


def weight_stats(weights: Dict[int, float]) -> dict:
    positive = {k: v for k, v in weights.items() if v > 0.0}
    if not positive:
        return {"n_nonzero": 0, "effective_n": None, "top1_level": None, "top1_weight": None, "top3_weight_sum": None, "entropy": None}
    vals = list(positive.values())
    entropy = -sum(v * math.log(v) for v in vals if v > 0.0)
    eff_n = 1.0 / sum(v * v for v in vals)
    top = sorted(positive.items(), key=lambda item: item[1], reverse=True)
    return {
        "n_nonzero": len(positive),
        "effective_n": eff_n,
        "top1_level": int(top[0][0]),
        "top1_weight": float(top[0][1]),
        "top3_weight_sum": float(sum(v for _k, v in top[:3])),
        "top5_weight_sum": float(sum(v for _k, v in top[:5])),
        "entropy": entropy,
        "top_weights": [{"source_level": int(k), "weight": float(v)} for k, v in top[:10]],
    }


def first_solve_diagnostics(summary: dict) -> dict:
    solves = summary.get("solves") or []
    first = dict(solves[0]) if solves else {}
    keep = [
        "solver", "solver_warning", "matrix_rank", "matrix_size", "condition_number",
        "linear_residual_l2", "linear_residual_linf", "negative_population_action",
        "n_negative_populations_raw", "n_significant_negative_populations_raw",
        "min_population_raw", "sum_negative_populations_raw_abs",
        "null_rate_pruning_diagnostics",
    ]
    return {k: first.get(k) for k in keep if k in first}


def sum_a_from_upper(lines: List[dict], upper: int, lower: Optional[int] = None) -> float:
    total = 0.0
    for row in lines:
        if maybe_int(row.get("upper_level")) != int(upper):
            continue
        if lower is not None and maybe_int(row.get("lower_level")) != int(lower):
            continue
        aval = maybe_float(row.get("A_s^-1"))
        if aval is not None:
            total += aval
    return total


def collision_pair_rows(eval_rows: List[dict], source_level: int, target_level: int) -> List[dict]:
    out = []
    pair = {int(source_level), int(target_level)}
    for row in eval_rows:
        lo = maybe_int(row.get("lower_level"))
        up = maybe_int(row.get("upper_level"))
        if lo is None or up is None:
            continue
        if {lo, up} == pair:
            out.append(row)
    return out


def summarize_collision_pair(eval_rows: List[dict], source_level: int, target_level: int, ne: float) -> dict:
    rows = collision_pair_rows(eval_rows, source_level, target_level)
    q_up = 0.0
    q_down = 0.0
    methods = []
    data_types = []
    records = []
    for row in rows:
        lo = maybe_int(row.get("lower_level"))
        up = maybe_int(row.get("upper_level"))
        q_exc = maybe_float(row.get("q_excitation_cm3_s")) or 0.0
        q_de = maybe_float(row.get("q_deexcitation_cm3_s")) or 0.0
        if lo == source_level and up == target_level:
            q_up += q_exc
            q_down += q_de
        elif lo == target_level and up == source_level:
            q_up += q_de
            q_down += q_exc
        method = row.get("eval_method")
        if method and method not in methods:
            methods.append(str(method))
        dt = row.get("data_type")
        if dt not in (None, "") and str(dt) not in data_types:
            data_types.append(str(dt))
        records.append(row.get("record"))
    return {
        "target_level": int(target_level),
        "n_collision_records_pair": len(rows),
        "collision_records": ";".join(str(r) for r in records if r is not None),
        "collision_data_types": ";".join(data_types),
        "collision_methods": ";".join(methods) if methods else "none",
        "q_2_to_j_cm3_s": q_up,
        "q_j_to_2_cm3_s": q_down,
        "C_2_to_j_s^-1": q_up * ne,
        "C_j_to_2_s^-1": q_down * ne,
    }


def compute_collision_diagnostics(fitsfile: str, density: float, temperature: float, out_dir: Path, index_cache: bool, index_cache_format: str) -> dict:
    from xstar_atomic.hierarchy import ATDB, SYMBOL_TO_Z
    from xstar_atomic.lines import extract_levels, extract_lines
    from xstar_atomic.collisions import extract_collisions

    z = SYMBOL_TO_Z["O"]
    with ATDB(fitsfile) as db:
        records = db.select_records(z=z, ion_stage=7, use_cache=bool(index_cache), cache_format=index_cache_format)
        levels = extract_levels(db, records, z, 7)
        lines = extract_lines(db, records, z, 7)
        summary_rows, _grid_rows, eval_rows = extract_collisions(db, records, z, 7, [float(temperature)], electron_density_cm3=float(density))

    source = 2
    targets = [3, 4, 5]
    level_by_index = {maybe_int(row.get("level_index")): row for row in levels if maybe_int(row.get("level_index")) is not None}
    A2 = sum_a_from_upper(lines, source)
    rows = []
    total_c_up = 0.0
    for target in targets:
        coll = summarize_collision_pair(eval_rows, source, target, float(density))
        c_up = maybe_float(coll.get("C_2_to_j_s^-1")) or 0.0
        total_c_up += c_up
        A_target = sum_a_from_upper(lines, target)
        row = {
            "electron_density_cm^-3": float(density),
            "temperature_K": float(temperature),
            "source_level": source,
            "source_label": level_by_index.get(source, {}).get("level_label"),
            "target_level": target,
            "target_label": level_by_index.get(target, {}).get("level_label"),
            "A_source_total_s^-1": A2,
            "A_target_total_s^-1": A_target,
            **coll,
            "C_2_to_j_over_A_source_total": (c_up / A2) if A2 > 0.0 else None,
            "C_2_to_j_over_A_target_total": (c_up / A_target) if A_target > 0.0 else None,
        }
        rows.append(row)
    for row in rows:
        row["C_2_to_3_4_5_total_s^-1"] = total_c_up
        row["C_2_to_3_4_5_total_over_A_source_total"] = (total_c_up / A2) if A2 > 0.0 else None
    csv_path = out_dir / "o7_high_density_collision_rates.csv"
    write_csv(csv_path, rows)
    return {
        "enabled": True,
        "collision_rates_csv": str(csv_path),
        "A_level2_total_s^-1": A2,
        "C_2_to_3_4_5_total_s^-1": total_c_up,
        "C_2_to_3_4_5_total_over_A_level2": (total_c_up / A2) if A2 > 0.0 else None,
        "rows": rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Diagnose the O VII high-density source-fit mismatch")
    p.add_argument("fitsfile", nargs="?", help="Optional XSTAR atdb.fits path; enables type-68/69 collision-rate diagnostics")
    p.add_argument("--density-grid-dir", default="o7_solver_source_fit_density_xstar_grid")
    p.add_argument("--density", type=float, default=1.0e12)
    p.add_argument("--reference-density", type=float, default=1.0)
    p.add_argument("--temperature", type=float, default=1.0e6)
    p.add_argument("--out-dir", default="o7_high_density_mismatch")
    p.add_argument("--index-cache", action="store_true")
    p.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    p.add_argument("--skip-collision-diagnostics", action="store_true")
    p.add_argument("--print-summary", action="store_true")
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    grid_dir = Path(args.density_grid_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    density_csv = grid_dir / "o7_solver_source_fit_density_grid.csv"
    density_summary_json = grid_dir / "o7_solver_source_fit_density_grid_summary.json"
    if not density_csv.exists():
        raise SystemExit(f"Density-grid CSV not found: {density_csv}")
    if not density_summary_json.exists():
        raise SystemExit(f"Density-grid summary JSON not found: {density_summary_json}")

    grid_rows = read_csv_rows(density_csv)
    high_row = find_density_row(grid_rows, float(args.density))
    ref_row = find_density_row(grid_rows, float(args.reference_density))
    grid_summary = read_json(density_summary_json)

    fit_dir = resolve_grid_output_path(
        high_row.get("fit_dir"),
        grid_dir,
        grid_dir / f"fit_ne_{safe_density_name(args.density)}",
    )
    ref_fit_dir = resolve_grid_output_path(
        ref_row.get("fit_dir"),
        grid_dir,
        grid_dir / f"fit_ne_{safe_density_name(args.reference_density)}",
    )
    fit_summary_path = fit_dir / "o7_solver_source_fit_summary.json"
    ref_summary_path = ref_fit_dir / "o7_solver_source_fit_summary.json"
    fit_summary = read_json(fit_summary_path)
    ref_summary = read_json(ref_summary_path) if ref_summary_path.exists() else {}

    component_rows = component_rows_from_fit_summary(fit_summary, float(args.density))
    component_csv = out_dir / "o7_high_density_component_mismatch.csv"
    write_csv(component_csv, component_rows)

    high_weights = read_weights(fit_dir / "o7_source_fit_weights.csv")
    ref_weights = read_weights(ref_fit_dir / "o7_source_fit_weights.csv")
    wrows = weight_rows(ref_weights, high_weights)
    weights_csv = out_dir / "o7_high_density_source_weight_changes.csv"
    write_csv(weights_csv, wrows)

    collision_diag = {"enabled": False, "reason": "no fitsfile supplied or skipped"}
    if args.fitsfile and not args.skip_collision_diagnostics:
        collision_diag = compute_collision_diagnostics(
            args.fitsfile,
            float(args.density),
            float(args.temperature),
            out_dir,
            bool(args.index_cache),
            args.index_cache_format,
        )

    xstar = fit_summary.get("xstar_reference") or {}
    fitted = fit_summary.get("fitted_prediction") or {}
    combined = fit_summary.get("combined_source_validation") or {}
    refitted_R_over_xstar = maybe_float(high_row.get("refitted_combined_R_over_xstar") or high_row.get("refitted_R_over_xstar"))
    refitted_G_over_xstar = maybe_float(high_row.get("refitted_combined_G_over_xstar") or high_row.get("refitted_G_over_xstar"))

    component_abs = [abs(maybe_float(r.get("combined_minus_xstar")) or 0.0) for r in component_rows]
    worst_component = None
    if component_rows:
        worst_component = component_rows[max(range(len(component_rows)), key=lambda i: component_abs[i])]["component"]

    summary = {
        "density_grid_dir": str(grid_dir),
        "density_grid_csv": str(density_csv),
        "density_grid_summary_json": str(density_summary_json),
        "electron_density_cm^-3": float(args.density),
        "reference_density_cm^-3": float(args.reference_density),
        "temperature_K": float(args.temperature),
        "xstar_target": {
            "R_f_over_i": maybe_float(xstar.get("R_f_over_i") or high_row.get("xstar_R_f_over_i")),
            "G_f_plus_i_over_r": maybe_float(xstar.get("G_f_plus_i_over_r") or high_row.get("xstar_G_f_plus_i_over_r")),
            "path": xstar.get("path") or high_row.get("xstar_lines_csv"),
            "target_label": xstar.get("target_label") or high_row.get("xstar_target_label"),
        },
        "fixed_reference_weights_prediction": {
            "R_f_over_i": maybe_float(high_row.get("fixed_ne1_R_f_over_i")),
            "G_f_plus_i_over_r": maybe_float(high_row.get("fixed_ne1_G_f_plus_i_over_r")),
            "R_over_xstar": maybe_float(high_row.get("fixed_ne1_R_over_xstar")),
            "G_over_xstar": maybe_float(high_row.get("fixed_ne1_G_over_xstar")),
        },
        "refitted_prediction": {
            "linear_R_f_over_i": maybe_float(fitted.get("R_f_over_i") or high_row.get("refitted_linear_R_f_over_i")),
            "linear_G_f_plus_i_over_r": maybe_float(fitted.get("G_f_plus_i_over_r") or high_row.get("refitted_linear_G_f_plus_i_over_r")),
            "combined_R_f_over_i": maybe_float(combined.get("R_f_over_i") or high_row.get("refitted_combined_R_f_over_i")),
            "combined_G_f_plus_i_over_r": maybe_float(combined.get("G_f_plus_i_over_r") or high_row.get("refitted_combined_G_f_plus_i_over_r")),
            "combined_R_over_xstar": refitted_R_over_xstar,
            "combined_G_over_xstar": refitted_G_over_xstar,
            "fit_objective": maybe_float((fitted.get("fit_info") or {}).get("objective") or high_row.get("fit_objective")),
            "fit_status": (fitted.get("fit_info") or {}).get("status") or high_row.get("fit_status"),
            "target_reachable": str(high_row.get("target_reachable")).lower() == "true",
            "fit_success_vs_xstar": str(high_row.get("fit_success_vs_xstar")).lower() == "true",
        },
        "component_mismatch": {
            "component_mismatch_csv": str(component_csv),
            "worst_component_by_normalized_fraction": worst_component,
            "rows": component_rows,
        },
        "source_weight_collapse": {
            "source_weight_changes_csv": str(weights_csv),
            "reference_density_stats": weight_stats(ref_weights),
            "high_density_stats": weight_stats(high_weights),
            "weight_delta_l1": maybe_float(high_row.get("weight_delta_l1_vs_ne1")),
            "weight_delta_l2": maybe_float(high_row.get("weight_delta_l2_vs_ne1")),
            "largest_changes": wrows[:10],
        },
        "solver_diagnostics": {
            "combined_validation": combined.get("solver_diagnostics") or {},
            "fit_summary_combined_warning": ((combined.get("solver_diagnostics") or {}).get("solver_warning")),
        },
        "collision_diagnostics": collision_diag,
        "interpretation": [],
        "outputs": {
            "summary_json": str(out_dir / "o7_high_density_mismatch_summary.json"),
            "component_mismatch_csv": str(component_csv),
            "source_weight_changes_csv": str(weights_csv),
            "collision_rates_csv": collision_diag.get("collision_rates_csv"),
        },
    }

    interp: List[str] = []
    if summary["refitted_prediction"]["target_reachable"]:
        interp.append("The selected high-density target is reachable with independently refitted empirical source weights.")
    else:
        interp.append("The selected high-density target is not reachable within the configured R/G tolerance using the current source-level set and solver network.")
    if worst_component:
        interp.append(f"The largest normalized triplet-component mismatch is in the {worst_component} component.")
    high_stats = summary["source_weight_collapse"]["high_density_stats"]
    if high_stats.get("top1_weight") is not None and high_stats["top1_weight"] > 0.5:
        interp.append(f"The fitted source distribution collapses strongly onto level {high_stats.get('top1_level')} (weight {high_stats.get('top1_weight'):.3g}).")
    if collision_diag.get("enabled") and (collision_diag.get("C_2_to_3_4_5_total_over_A_level2") or 0.0) > 1.0:
        interp.append("At this density, collisional transfer out of O VII level 2 exceeds the level-2 radiative decay rate, so type-68/69 coupling strongly suppresses the forbidden/intercombination ratio.")
    interp.append("Suggested next checks: expand the fitted source-level set beyond n<=4, inspect high-n cascade completion, and compare XSTAR level-source assumptions if available.")
    summary["interpretation"] = interp

    summary_json = out_dir / "o7_high_density_mismatch_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.print_summary:
        print("O VII high-density mismatch diagnostics")
        print("---------------------------------------")
        print(f"density: {float(args.density):.6g} cm^-3")
        print(f"XSTAR R/G: {summary['xstar_target']['R_f_over_i']:.6g} / {summary['xstar_target']['G_f_plus_i_over_r']:.6g}")
        print(
            "refitted combined R/G: "
            f"{summary['refitted_prediction']['combined_R_f_over_i']:.6g} / "
            f"{summary['refitted_prediction']['combined_G_f_plus_i_over_r']:.6g}"
        )
        print(f"target reachable: {summary['refitted_prediction']['target_reachable']}")
        print(f"worst component: {worst_component}")
        print(f"top high-density source level: {high_stats.get('top1_level')} weight={high_stats.get('top1_weight')}")
        if collision_diag.get("enabled"):
            print(
                "C(2->3,4,5)/A2 = "
                f"{collision_diag.get('C_2_to_3_4_5_total_over_A_level2'):.6g}"
            )
        print(f"wrote: {summary_json}")
        print(f"wrote: {component_csv}")
        print(f"wrote: {weights_csv}")
        if collision_diag.get("collision_rates_csv"):
            print(f"wrote: {collision_diag.get('collision_rates_csv')}")
        for item in interp:
            print("- " + item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
