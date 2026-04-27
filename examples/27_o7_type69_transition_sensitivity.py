#!/usr/bin/env python3
"""Scan individual O VII type-69 collision transitions at high density.

This diagnostic follows ``examples/26_o7_high_density_rate_sensitivity.py``.
The type-69 family scan showed that reducing all type-69 rates can make the
``ne=1e12 cm^-3`` O VII XSTAR triplet target reachable.  This script asks which
specific type-69 collision records or transition pairs are responsible.

The scan is diagnostic only.  It does not alter the packaged atomic data; it
passes temporary ``--collision-record-scale`` or ``--collision-pair-scale``
options to ``examples/20_o7_solver_source_fit.py`` and refits empirical source
weights for each scaled network.
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
from typing import Dict, List, Optional, Sequence, Tuple

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


def maybe_int(value) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def density_equal(a: float, b: float, rel: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)), 1.0)


def safe_name(text: str) -> str:
    out = str(text).strip().lower().replace("<=", "le").replace(">=", "ge")
    out = out.replace(".", "p").replace("+", "").replace("-", "m")
    return re.sub(r"[^a-z0-9]+", "_", out).strip("_") or "case"


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


def parse_float_list(text: str) -> List[float]:
    out: List[float] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(float(part))
    return out


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
    csv_path = resolve_density_grid_csv(grid_dir)
    row = find_density_row(read_csv_rows(csv_path), density)
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


def extract_type69_transitions(fitsfile: str, temperature: float, density: float, index_cache: bool, cache_format: str) -> List[dict]:
    from xstar_atomic.hierarchy import ATDB, SYMBOL_TO_Z
    from xstar_atomic.collisions import extract_collisions

    z = SYMBOL_TO_Z["O"]
    with ATDB(fitsfile) as db:
        records = db.select_records(z=z, ion_stage=7, use_cache=bool(index_cache), cache_format=cache_format)
        _summary, _grid, eval_rows = extract_collisions(db, records, z, 7, [float(temperature)], electron_density_cm3=float(density))
    out: List[dict] = []
    for row in eval_rows:
        if maybe_int(row.get("data_type")) != 69:
            continue
        rec = maybe_int(row.get("record"))
        lower = maybe_int(row.get("lower_level"))
        upper = maybe_int(row.get("upper_level"))
        if rec is None or lower is None or upper is None:
            continue
        q_exc = maybe_float(row.get("q_excitation_cm3_s")) or 0.0
        q_de = maybe_float(row.get("q_deexcitation_cm3_s")) or 0.0
        out.append({
            "record": rec,
            "lower_level": lower,
            "upper_level": upper,
            "lower_label": row.get("lower_label"),
            "upper_label": row.get("upper_label"),
            "q_excitation_cm3_s": q_exc,
            "q_deexcitation_cm3_s": q_de,
            "C_excitation_s^-1": q_exc * float(density),
            "C_deexcitation_s^-1": q_de * float(density),
            "rate_strength_s^-1": (q_exc + q_de) * float(density),
            "collision_eval_method": row.get("collision_eval_method") or row.get("method"),
        })
    # One row per record; if the decoder emitted multiple temperature rows, keep the strongest.
    by_record: Dict[int, dict] = {}
    for row in out:
        rec = int(row["record"])
        if rec not in by_record or float(row.get("rate_strength_s^-1") or 0.0) > float(by_record[rec].get("rate_strength_s^-1") or 0.0):
            by_record[rec] = row
    rows = list(by_record.values())
    rows.sort(key=lambda r: float(r.get("rate_strength_s^-1") or 0.0), reverse=True)
    return rows


def build_scan_cases(transitions: List[dict], scales: Sequence[float], mode: str, max_transitions: Optional[int]) -> List[dict]:
    chosen = transitions[: int(max_transitions)] if max_transitions and max_transitions > 0 else transitions
    cases: List[dict] = [{"case": "baseline", "mode": "baseline", "scale": 1.0, "record_scales": [], "pair_scales": [], "transition": {}}]
    seen = {"baseline"}
    if mode == "record":
        for tr in chosen:
            rec = int(tr["record"])
            for scale in scales:
                if float(scale) == 1.0:
                    continue
                name = safe_name(f"record_{rec}_x{scale:g}")
                if name in seen:
                    continue
                seen.add(name)
                cases.append({"case": name, "mode": "record", "scale": float(scale), "record_scales": [f"{rec}:{float(scale):.16g}"], "pair_scales": [], "transition": tr})
    elif mode == "pair":
        by_pair: Dict[Tuple[int, int], dict] = {}
        for tr in chosen:
            key = tuple(sorted((int(tr["lower_level"]), int(tr["upper_level"]))))
            cur = by_pair.get(key)
            if cur is None or float(tr.get("rate_strength_s^-1") or 0.0) > float(cur.get("rate_strength_s^-1") or 0.0):
                by_pair[key] = tr
        for key, tr in by_pair.items():
            for scale in scales:
                if float(scale) == 1.0:
                    continue
                name = safe_name(f"pair_{key[0]}_{key[1]}_x{scale:g}")
                if name in seen:
                    continue
                seen.add(name)
                cases.append({"case": name, "mode": "pair", "scale": float(scale), "record_scales": [], "pair_scales": [f"{key[0]}:{key[1]}:{float(scale):.16g}"], "transition": tr})
    else:
        raise SystemExit(f"Unknown scan mode {mode!r}; use record or pair")
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
        sys.executable, str(Path(__file__).with_name("20_o7_solver_source_fit.py")), args.fitsfile,
        "--element", "O", "--ion-stage", "7",
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
    for spec in case.get("record_scales") or []:
        cmd += ["--collision-record-scale", str(spec)]
    for spec in case.get("pair_scales") or []:
        cmd += ["--collision-pair-scale", str(spec)]
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
    tr = case.get("transition") or {}
    return {
        "case": case["case"],
        "scan_mode": case.get("mode"),
        "scale": case.get("scale"),
        "record": tr.get("record"),
        "lower_level": tr.get("lower_level"),
        "upper_level": tr.get("upper_level"),
        "lower_label": tr.get("lower_label"),
        "upper_label": tr.get("upper_label"),
        "rate_strength_s^-1": tr.get("rate_strength_s^-1"),
        "C_excitation_s^-1": tr.get("C_excitation_s^-1"),
        "C_deexcitation_s^-1": tr.get("C_deexcitation_s^-1"),
        "collision_record_scale": ";".join(case.get("record_scales") or []),
        "collision_pair_scale": ";".join(case.get("pair_scales") or []),
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
        "fit_dir": str(fit_dir),
        "summary_json": str(summary_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--density-grid-dir", default="o7_solver_source_fit_density_xstar_grid")
    parser.add_argument("--density", type=float, default=1.0e12)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--source-levels", default=BASELINE_LEVELS)
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--combined-source-total-rate", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--scan-mode", choices=["record", "pair"], default="record")
    parser.add_argument("--scales", default="0.1,0.2,0.5,2,5,10")
    parser.add_argument("--max-transitions", type=int, default=40, help="Scan only the strongest N type-69 records/pairs; use 0 for all")
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
    parser.add_argument("--out-dir", default="o7_type69_transition_sensitivity")
    parser.add_argument("--keep-unit-runs", action="store_true")
    parser.add_argument("--print-subprocess-summary", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xstar_csv, xstar_col, density_row = xstar_reference_for_density(Path(args.density_grid_dir), float(args.density))
    transitions = extract_type69_transitions(args.fitsfile, float(args.temperature), float(args.density), bool(args.index_cache), args.index_cache_format)
    if not transitions:
        raise SystemExit("No O VII type-69 collision transitions were found for this ATDB/temperature/density")
    transition_csv = out_dir / "o7_type69_transitions.csv"
    write_csv(transition_csv, transitions)
    cases = build_scan_cases(transitions, parse_float_list(args.scales), args.scan_mode, args.max_transitions)

    rows: List[dict] = []
    for case in cases:
        rows.append(run_case(args, case, xstar_csv, xstar_col, out_dir))

    def score(row: dict) -> float:
        r = maybe_float(row.get("R_over_xstar"))
        g = maybe_float(row.get("G_over_xstar"))
        if r is None or g is None:
            return 1.0e99
        return abs(r - 1.0) + abs(g - 1.0)

    best = min(rows, key=score) if rows else None
    reachable = [row for row in rows if row.get("target_reachable")]
    out_csv = out_dir / "o7_type69_transition_sensitivity.csv"
    out_summary = out_dir / "o7_type69_transition_sensitivity_summary.json"
    write_csv(out_csv, rows)
    summary = {
        "fitsfile": args.fitsfile,
        "temperature_K": float(args.temperature),
        "electron_density_cm^-3": float(args.density),
        "density_grid_dir": str(args.density_grid_dir),
        "xstar_lines_csv": xstar_csv,
        "xstar_value_column": xstar_col,
        "density_grid_row": density_row,
        "scan_mode": args.scan_mode,
        "scales": parse_float_list(args.scales),
        "max_transitions": int(args.max_transitions),
        "n_type69_transitions_found": len(transitions),
        "n_cases": len(rows),
        "n_reachable_cases": len(reachable),
        "best_case": best,
        "reachable_cases": [row.get("case") for row in reachable],
        "transition_inventory_csv": str(transition_csv),
        "scan_csv": str(out_csv),
        "summary_json": str(out_summary),
        "note": "Diagnostic only: transition-specific collision scaling is not a physical correction by itself.",
    }
    out_summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    if args.print_summary:
        print("O VII type-69 transition-sensitivity diagnostic")
        print("------------------------------------------------")
        print(f"density: {float(args.density):g} cm^-3")
        print(f"type-69 transitions found: {len(transitions)}")
        print(f"cases: {len(rows)}")
        print(f"wrote: {out_csv}")
        print(f"wrote: {out_summary}")
        print("case                  rec     levels   R/G combined        R/XSTAR G/XSTAR reachable worst")
        for row in rows[:80]:
            print(f"{row['case']:<22} {str(row.get('record')):<7} {str(row.get('lower_level'))}->{str(row.get('upper_level')):<5} {row.get('combined_R_f_over_i')}/{row.get('combined_G_f_plus_i_over_r')}  {row.get('R_over_xstar')} {row.get('G_over_xstar')} {row.get('target_reachable')} {row.get('worst_component')}")
        if best:
            print(f"best case: {best.get('case')} record={best.get('record')} levels={best.get('lower_level')}->{best.get('upper_level')} R/XSTAR={best.get('R_over_xstar')} G/XSTAR={best.get('G_over_xstar')}")
        if reachable:
            print("reachable cases: " + ", ".join(str(row.get("case")) for row in reachable[:20]))
        else:
            print("reachable cases: none")


if __name__ == "__main__":
    main()
