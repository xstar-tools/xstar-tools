"""Validation and inventory helpers for xstar-atomic collision decoders.

This module provides lightweight utilities for checking the coverage and
behavior of collision-rate decoders against a local XSTAR ``atdb.fits`` file.
The routines are intended for regression tests and development diagnostics;
they do not replace independent validation against XSTAR spectral outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .hierarchy import ATDB, SYMBOL_TO_Z, Z_TO_SYMBOL, roman, IndexedRecord
from .collisions import extract_collisions, counts_by
from .lines import write_csv

DEFAULT_VALIDATION_TEMPERATURES = (1.0e6, 3.0e6, 1.0e7)


def choose_z(element: Optional[str | int]) -> Optional[int]:
    """Convert an element symbol or atomic number to ``Z``.

    Parameters
    ----------
    element:
        Element symbol such as ``"O"`` or atomic number such as ``8``.  If
        ``None``, no element filter is applied.
    """
    if element is None:
        return None
    if isinstance(element, int):
        return int(element)
    text = str(element).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    z = SYMBOL_TO_Z.get(text.upper())
    if z is None:
        raise ValueError(f"Unknown element: {element!r}")
    return z


def collision_inventory_from_records(
    records: Sequence[IndexedRecord],
    *,
    element: Optional[str | int] = None,
    data_types: Optional[Iterable[int]] = None,
) -> List[dict]:
    """Inventory collision records by element, ion stage, and data type.

    This routine only uses the already-built ATDB record index.  It does not
    decode the REALS arrays and is therefore much faster than full collision
    extraction.
    """
    z_filter = choose_z(element)
    dt_filter = {int(x) for x in data_types} if data_types is not None else None
    counts: Dict[Tuple[int, int, int, int], int] = defaultdict(int)

    for r in records:
        if r.rate_type != 3:
            continue
        if z_filter is not None and r.element_z != z_filter:
            continue
        if r.element_z is None or r.ion_stage is None:
            continue
        if dt_filter is not None and r.data_type not in dt_filter:
            continue
        key = (int(r.element_z), int(r.ion_stage), int(r.data_type), int(r.rate_type))
        counts[key] += 1

    rows: List[dict] = []
    for (z, stage, dt, rt), n in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
        symbol = Z_TO_SYMBOL.get(z, str(z))
        rows.append({
            "element_z": z,
            "element": symbol,
            "ion_stage": stage,
            "ion_roman": roman(stage),
            "ion": f"{symbol} {roman(stage)}",
            "data_type": dt,
            "rate_type": rt,
            "n_records": n,
        })
    return rows


def collision_inventory(
    fitsfile: str | Path,
    *,
    element: Optional[str | int] = None,
    data_types: Optional[Iterable[int]] = None,
) -> List[dict]:
    """Build a collision inventory directly from ``atdb.fits``."""
    db = ATDB(fitsfile, load_reals=False)
    try:
        records, _elements, _ions = db.build_index()
        return collision_inventory_from_records(records, element=element, data_types=data_types)
    finally:
        db.close()


def summarize_inventory(rows: Sequence[dict]) -> dict:
    """Return compact counts for inventory rows."""
    by_dt: Dict[str, int] = defaultdict(int)
    by_ion: Dict[str, int] = defaultdict(int)
    for row in rows:
        by_dt[str(row.get("data_type"))] += int(row.get("n_records", 0))
        by_ion[str(row.get("ion"))] += int(row.get("n_records", 0))
    return {
        "n_inventory_rows": len(rows),
        "n_records_total": sum(int(r.get("n_records", 0)) for r in rows),
        "counts_by_data_type": dict(sorted(by_dt.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else str(kv[0]))),
        "counts_by_ion": dict(sorted(by_ion.items())),
    }


def _candidate_ions_from_inventory(rows: Sequence[dict]) -> List[Tuple[str, int, int]]:
    """Return unique ``(element, ion_stage, data_type)`` targets."""
    out: List[Tuple[str, int, int]] = []
    seen = set()
    for row in rows:
        key = (row["element"], int(row["ion_stage"]), int(row["data_type"]))
        if key not in seen:
            out.append(key)
            seen.add(key)
    return out


def find_collision_validation_targets(
    fitsfile: str | Path,
    *,
    element: Optional[str | int] = None,
    data_types: Iterable[int] = (51, 98),
    temperatures: Sequence[float] = DEFAULT_VALIDATION_TEMPERATURES,
    max_targets: int = 20,
    electron_density_for_lmixing: float = 1.0,
) -> List[dict]:
    """Find ions with evaluable collision records for selected data types.

    The function inventories the requested data types, then decodes ions one by
    one until ``max_targets`` evaluable examples are found.  A target is reported
    when at least one evaluated row has a positive ``q_excitation_cm3_s`` or
    ``q_deexcitation_cm3_s``.
    """
    inv = collision_inventory(fitsfile, element=element, data_types=data_types)
    candidates = _candidate_ions_from_inventory(inv)
    targets: List[dict] = []

    db = ATDB(fitsfile, load_reals=True)
    try:
        records, _elements, _ions = db.build_index()
        for elem, stage, dt in candidates:
            if len(targets) >= max_targets:
                break
            summary_rows, _grid_rows, eval_rows = extract_collisions(
                db,
                records,
                choose_z(elem),
                int(stage),
                temperatures,
                electron_density_cm3=electron_density_for_lmixing,
            )
            dt_summary = [r for r in summary_rows if int(r.get("data_type", -1)) == int(dt)]
            dt_eval = [r for r in eval_rows if int(r.get("data_type", -1)) == int(dt)]
            good = [
                r for r in dt_eval
                if (r.get("q_excitation_cm3_s") is not None and float(r.get("q_excitation_cm3_s")) > 0.0)
                or (r.get("q_deexcitation_cm3_s") is not None and float(r.get("q_deexcitation_cm3_s")) > 0.0)
            ]
            if good:
                first = good[0]
                targets.append({
                    "element": elem,
                    "ion_stage": int(stage),
                    "ion_roman": roman(int(stage)),
                    "ion": f"{elem} {roman(int(stage))}",
                    "data_type": int(dt),
                    "n_records": len(dt_summary),
                    "n_evaluated_rows": len(dt_eval),
                    "n_positive_rate_rows": len(good),
                    "first_record": first.get("record"),
                    "first_lower_level": first.get("lower_level"),
                    "first_upper_level": first.get("upper_level"),
                    "first_wavelength_A": first.get("wavelength_A"),
                    "first_temperature_K": first.get("temperature_K"),
                    "first_eval_method": first.get("eval_method"),
                    "first_q_excitation_cm3_s": first.get("q_excitation_cm3_s"),
                    "first_q_deexcitation_cm3_s": first.get("q_deexcitation_cm3_s"),
                })
    finally:
        db.close()
    return targets


def type63_same_n_validation(
    fitsfile: str | Path,
    *,
    element: str | int = "O",
    ion_stage: int = 8,
    temperatures: Sequence[float] = (1.0e6,),
    electron_density_for_lmixing: float = 1.0,
) -> dict:
    """Validate basic behavior of the type-63 same-``n`` l-mixing branch.

    This is a regression diagnostic for the Python port of XSTAR's
    ``amcrs/velimp`` branch.  It verifies that same-``n`` adjacent-``l`` records
    evaluate to finite positive rates and reports count/min/max information.
    Independent numerical comparison to XSTAR spectral output should still be
    performed before using these rates for production science.
    """
    z = choose_z(element)
    db = ATDB(fitsfile, load_reals=True)
    try:
        records, _elements, _ions = db.build_index()
        summary_rows, _grid_rows, eval_rows = extract_collisions(
            db,
            records,
            z,
            int(ion_stage),
            temperatures,
            electron_density_cm3=electron_density_for_lmixing,
        )
    finally:
        db.close()

    same_n_summary = [
        r for r in summary_rows
        if int(r.get("data_type", -1)) == 63
        and r.get("n_lower") == r.get("n_upper")
        and r.get("l_lower") is not None
        and r.get("l_upper") is not None
        and abs(int(r.get("l_upper")) - int(r.get("l_lower"))) == 1
    ]
    same_n_eval = [
        r for r in eval_rows
        if r.get("eval_method") == "type63_same_n_lmixing_amcrs_velimp"
    ]
    q_exc = [float(r["q_excitation_cm3_s"]) for r in same_n_eval if r.get("q_excitation_cm3_s") is not None and math.isfinite(float(r["q_excitation_cm3_s"]))]
    q_de = [float(r["q_deexcitation_cm3_s"]) for r in same_n_eval if r.get("q_deexcitation_cm3_s") is not None and math.isfinite(float(r["q_deexcitation_cm3_s"]))]
    by_reason = counts_by(eval_rows, "eval_method")
    symbol = Z_TO_SYMBOL.get(z, str(z)) if z is not None else str(element)

    return {
        "fitsfile": str(fitsfile),
        "element": symbol,
        "z": z,
        "ion_stage": int(ion_stage),
        "ion": f"{symbol} {roman(int(ion_stage))}",
        "temperatures_K": list(temperatures),
        "electron_density_for_lmixing_cm^-3": electron_density_for_lmixing,
        "n_collision_records": len(summary_rows),
        "n_type63_same_n_adjacent_l_records": len(same_n_summary),
        "n_type63_same_n_evaluated_rows": len(same_n_eval),
        "q_excitation_min_cm3_s": min(q_exc) if q_exc else None,
        "q_excitation_max_cm3_s": max(q_exc) if q_exc else None,
        "q_deexcitation_min_cm3_s": min(q_de) if q_de else None,
        "q_deexcitation_max_cm3_s": max(q_de) if q_de else None,
        "eval_counts_by_method": by_reason,
        "validation_status": "pass" if same_n_eval and q_exc and q_de else "no_evaluated_same_n_rows",
        "note": "This is a Python-port regression diagnostic; compare against XSTAR outputs for final scientific validation.",
    }


def write_rows(path: str | Path, rows: Sequence[dict]) -> None:
    """Write a list of dictionaries to CSV."""
    write_csv(path, list(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Collision-decoder validation and inventory utilities for xstar-atomic")
    parser.add_argument("fitsfile")
    parser.add_argument("--element", help="Optional element filter, e.g. O or Fe")
    parser.add_argument("--data-types", nargs="*", type=int, default=[51, 98], help="Collision data types to inventory/target")
    parser.add_argument("--temperatures", nargs="*", type=float, default=[1.0e6, 3.0e6, 1.0e7])
    parser.add_argument("--electron-density", type=float, default=1.0, help="Electron density for type-63 l-mixing diagnostics")
    parser.add_argument("--inventory", action="store_true", help="Print collision inventory for selected data types")
    parser.add_argument("--inventory-csv")
    parser.add_argument("--find-targets", action="store_true", help="Find representative ions with evaluable selected data types")
    parser.add_argument("--targets-csv")
    parser.add_argument("--max-targets", type=int, default=20)
    parser.add_argument("--type63-same-n", action="store_true", help="Run type-63 same-n l-mixing validation diagnostic")
    parser.add_argument("--ion-stage", type=int, default=8, help="Ion stage for --type63-same-n")
    parser.add_argument("--summary-json")
    args = parser.parse_args()

    output = {}

    if args.inventory:
        rows = collision_inventory(args.fitsfile, element=args.element, data_types=args.data_types)
        output["inventory_summary"] = summarize_inventory(rows)
        output["inventory_rows"] = rows
        if args.inventory_csv:
            write_rows(args.inventory_csv, rows)

    if args.find_targets:
        targets = find_collision_validation_targets(
            args.fitsfile,
            element=args.element,
            data_types=args.data_types,
            temperatures=args.temperatures,
            max_targets=args.max_targets,
            electron_density_for_lmixing=args.electron_density,
        )
        output["targets"] = targets
        output["n_targets"] = len(targets)
        if args.targets_csv:
            write_rows(args.targets_csv, targets)

    if args.type63_same_n:
        output["type63_same_n_validation"] = type63_same_n_validation(
            args.fitsfile,
            element=args.element or "O",
            ion_stage=args.ion_stage,
            temperatures=args.temperatures,
            electron_density_for_lmixing=args.electron_density,
        )

    if not output:
        rows = collision_inventory(args.fitsfile, element=args.element, data_types=args.data_types)
        output["inventory_summary"] = summarize_inventory(rows)
        output["hint"] = "Use --inventory, --find-targets, or --type63-same-n for more detailed output."

    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
