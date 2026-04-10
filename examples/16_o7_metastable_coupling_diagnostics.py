#!/usr/bin/env python3
"""Inspect O VII metastable/intercombination coupling rates.

This Stage-6 diagnostic focuses on the O VII forbidden-line upper level
``1s2s 3S1`` (level 2 in the current XSTAR ATDB level indexing) and the
intercombination upper levels ``1s2p 3P_J`` (levels 3, 4, and 5).  The goal is
not to change the solver, but to expose whether the remaining O VII triplet
``R=f/i`` mismatch is caused by weak collisional transfer from level 2 into the
intercombination manifold, by source/cascade feeding, or by missing physics.

Example
-------

.. code-block:: bash

   PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
     ../xstar/data/atdb.fits \
     --temperature 1e6 \
     --electron-densities 1 1e4 1e8 1e10 1e12 \
     --out-dir o7_metastable_coupling \
     --print-summary

Outputs
-------

``o7_metastable_coupling_rates.csv``
    Per-density rates for level 2 -> levels 3, 4, and 5.

``o7_metastable_coupling_summary.json``
    JSON summary with level labels, radiative totals, and transition-rate
    diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from xstar_atomic.hierarchy import ATDB, SYMBOL_TO_Z
from xstar_atomic.lines import extract_levels, extract_lines, write_csv
from xstar_atomic.collisions import extract_collisions

DEFAULT_SOURCE_LEVEL = 2
DEFAULT_TARGET_LEVELS = [3, 4, 5]


def maybe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def maybe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


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


def representative_lines(lines: List[dict], upper: int, max_rows: int = 8) -> List[dict]:
    rows = []
    for row in lines:
        if maybe_int(row.get("upper_level")) != int(upper):
            continue
        rows.append({
            "record": row.get("record"),
            "lower_level": row.get("lower_level"),
            "upper_level": row.get("upper_level"),
            "lower_label": row.get("lower_label"),
            "upper_label": row.get("upper_label"),
            "wavelength_A": row.get("wavelength_A"),
            "A_s^-1": row.get("A_s^-1"),
            "data_type": row.get("data_type"),
            "rate_type": row.get("rate_type"),
        })
    rows.sort(key=lambda r: (-(maybe_float(r.get("A_s^-1")) or 0.0), maybe_float(r.get("wavelength_A")) or 1e99))
    return rows[:max_rows]


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
    """Summarize collisional rates between source and target levels.

    The collision evaluator returns ``q_excitation`` from lower-energy level to
    upper-energy level and ``q_deexcitation`` in the reverse direction.  For the
    O VII levels used here, level 2 is lower than levels 3, 4, and 5, so
    q_excitation is the desired 2 -> j transfer coefficient.
    """
    rows = collision_pair_rows(eval_rows, source_level, target_level)
    q_up = 0.0
    q_down = 0.0
    methods = []
    diagnostics = []
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
            # Reverse physical ordering; keep rates oriented as source -> target.
            q_up += q_de
            q_down += q_exc
        method = row.get("eval_method")
        if method and method not in methods:
            methods.append(str(method))
        diag = row.get("eval_diagnostic")
        if diag and diag not in diagnostics:
            diagnostics.append(str(diag))
        records.append(row.get("record"))
    return {
        "n_collision_records_pair": len(rows),
        "collision_records": ",".join(str(r) for r in records if r is not None),
        "q_2_to_j_cm3_s": q_up,
        "q_j_to_2_cm3_s": q_down,
        "C_2_to_j_s^-1": q_up * ne,
        "C_j_to_2_s^-1": q_down * ne,
        "collision_methods": ",".join(methods) if methods else "none",
        "collision_diagnostics": ",".join(diagnostics) if diagnostics else "",
    }


def parse_level_list(text: str) -> List[int]:
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Inspect O VII level-2 metastable/intercombination coupling rates")
    p.add_argument("fitsfile", nargs="?", default=None, help="Path to XSTAR atdb.fits; omitted path uses xstar_atomic datapath resolution")
    p.add_argument("--element", default="O")
    p.add_argument("--ion-stage", type=int, default=7)
    p.add_argument("--source-level", type=int, default=DEFAULT_SOURCE_LEVEL, help="Metastable source level, default O VII level 2")
    p.add_argument("--target-levels", default=",".join(str(v) for v in DEFAULT_TARGET_LEVELS), help="Comma-separated intercombination target levels")
    p.add_argument("--temperature", type=float, default=1.0e6)
    p.add_argument("--electron-densities", type=float, nargs="+", default=[1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12])
    p.add_argument("--out-dir", default="o7_metastable_coupling")
    p.add_argument("--index-cache", action="store_true", help="Use ATDB index cache")
    p.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    z = SYMBOL_TO_Z.get(str(args.element).strip().upper(), None)
    if z is None:
        raise SystemExit(f"Unknown element: {args.element}")
    source = int(args.source_level)
    targets = parse_level_list(args.target_levels)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    db = ATDB(args.fitsfile)
    # Select the full O VII ion record set. This remains fast with the array-backed NPZ cache.
    try:
        records = db.select_records(
            z=z,
            ion_stage=args.ion_stage,
            use_cache=bool(args.index_cache),
            cache_format=args.index_cache_format,
        )
    except TypeError:
        records, _elements, _ions = db.build_index(use_cache=bool(args.index_cache), cache_format=args.index_cache_format)

    levels = extract_levels(db, records, z, args.ion_stage)
    lines = extract_lines(db, records, z, args.ion_stage)
    level_by_index = {maybe_int(row.get("level_index")): row for row in levels if maybe_int(row.get("level_index")) is not None}

    A_source_total = sum_a_from_upper(lines, source)
    source_level_row = level_by_index.get(source, {})

    rows: List[dict] = []
    by_density: Dict[str, List[dict]] = {}
    for ne in args.electron_densities:
        _summary_rows, _grid_rows, eval_rows = extract_collisions(
            db,
            records,
            z,
            args.ion_stage,
            [args.temperature],
            electron_density_cm3=float(ne),
        )
        density_rows = []
        for target in targets:
            target_row = level_by_index.get(target, {})
            coll = summarize_collision_pair(eval_rows, source, target, float(ne))
            A_target_to_source = sum_a_from_upper(lines, target, lower=source)
            A_target_total = sum_a_from_upper(lines, target)
            q_up = maybe_float(coll.get("q_2_to_j_cm3_s")) or 0.0
            c_up = maybe_float(coll.get("C_2_to_j_s^-1")) or 0.0
            c_down = maybe_float(coll.get("C_j_to_2_s^-1")) or 0.0
            row = {
                "element": args.element,
                "ion_stage": args.ion_stage,
                "temperature_K": float(args.temperature),
                "electron_density_cm^-3": float(ne),
                "source_level": source,
                "source_label": source_level_row.get("level_label"),
                "source_energy_eV": source_level_row.get("energy_eV"),
                "target_level": target,
                "target_label": target_row.get("level_label"),
                "target_energy_eV": target_row.get("energy_eV"),
                "A_source_total_s^-1": A_source_total,
                "A_target_to_source_s^-1": A_target_to_source,
                "A_target_total_s^-1": A_target_total,
                **coll,
                "C_2_to_j_over_A_source_total": (c_up / A_source_total) if A_source_total > 0 else None,
                "C_2_to_j_over_A_target_total": (c_up / A_target_total) if A_target_total > 0 else None,
                "C_j_to_2_over_A_target_total": (c_down / A_target_total) if A_target_total > 0 else None,
                "density_C2j_equals_A_source_total_cm^-3": (A_source_total / q_up) if q_up > 0 and A_source_total > 0 else None,
                "density_C2j_equals_A_target_total_cm^-3": (A_target_total / q_up) if q_up > 0 and A_target_total > 0 else None,
            }
            rows.append(row)
            density_rows.append(row)
        by_density[str(ne)] = density_rows

    rate_csv = out_dir / "o7_metastable_coupling_rates.csv"
    write_csv(rate_csv, rows)

    line_summary = {
        "source_level": source,
        "source_label": source_level_row.get("level_label"),
        "source_total_radiative_A_s^-1": A_source_total,
        "source_representative_lines": representative_lines(lines, source),
        "targets": {
            str(t): {
                "target_label": level_by_index.get(t, {}).get("level_label"),
                "A_target_to_source_s^-1": sum_a_from_upper(lines, t, lower=source),
                "A_target_total_s^-1": sum_a_from_upper(lines, t),
                "representative_lines": representative_lines(lines, t),
            }
            for t in targets
        },
    }

    summary = {
        "fitsfile": str(args.fitsfile) if args.fitsfile else None,
        "element": args.element,
        "ion_stage": args.ion_stage,
        "temperature_K": float(args.temperature),
        "electron_densities_cm^-3": [float(v) for v in args.electron_densities],
        "source_level": source,
        "target_levels": targets,
        "index_cache_status": getattr(db, "index_cache_status", getattr(db, "_last_index_cache_status", None)),
        "n_levels": len(levels),
        "n_radiative_lines": len(lines),
        "outputs": {
            "rates_csv": str(rate_csv),
            "summary_json": str(out_dir / "o7_metastable_coupling_summary.json"),
        },
        "radiative_summary": line_summary,
        "rows": rows,
        "notes": [
            "Collision rates are oriented as level 2 -> target level j when level 2 is the lower-energy member of the pair.",
            "C_2_to_j_s^-1 = ne * q_2_to_j_cm3_s.",
            "Compare C_2_to_j_s^-1 with A_source_total_s^-1 to see when collisional transfer competes with forbidden-level radiative decay.",
            "This diagnostic inspects available ATDB rates; it does not by itself modify the cascade source model.",
        ],
    }
    summary_json = out_dir / "o7_metastable_coupling_summary.json"
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    if args.print_summary:
        print("O VII metastable/intercombination coupling diagnostics")
        print("------------------------------------------------------")
        print(f"Rates CSV: {rate_csv}")
        print(f"Summary JSON: {summary_json}")
        print(f"Source level {source}: {source_level_row.get('level_label')}  A_total={A_source_total:.6e} s^-1")
        for t in targets:
            targ = level_by_index.get(t, {})
            print(f"Target level {t}: {targ.get('level_label')}  A_target_total={sum_a_from_upper(lines, t):.6e} s^-1")
        print("\nSelected density diagnostics:")
        for row in rows:
            print(
                f"ne={row['electron_density_cm^-3']:.3e}  "
                f"2->{row['target_level']}  "
                f"C={row['C_2_to_j_s^-1']:.3e} s^-1  "
                f"C/A2={row['C_2_to_j_over_A_source_total']}  "
                f"methods={row['collision_methods']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
