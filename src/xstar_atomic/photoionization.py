#!/usr/bin/env python3
"""Photoionization and bound-free record extraction for XSTAR ``atdb.fits``.

This module decodes a conservative subset of photoionization-like
records from the packed XSTAR atomic database.  It currently focuses on
the formats used by XSTAR ``ucalc.f90`` for data types 49, 53, and 59.

Decoded formats
---------------

* Data type 53, rate type 7: OP photoionization cross sections.
* Data type 49, rate type 7: OP inner-shell photoionization cross sections.
* Data type 59: Verner-style photoionization coefficients.

For tabulated type-49 and type-53 records, the real array is interpreted
as pairs of energy offset in Rydberg and cross section in megabarns.
The cross section is converted to square centimeters using
``sigma_cm2 = sigma_raw * 1e-18``.

For type-59 records, the module exports the coefficient form and can
sample the Verner analytic formula.

Examples
--------

Run a summary for O VIII::

    python -m xstar_atomic.photoionization atdb.fits --element O --ion-stage 8 --summary

Export summary and grid tables::

    python -m xstar_atomic.photoionization atdb.fits \
        --element O --ion-stage 8 \
        --summary-csv o8_pi_summary.csv \
        --grid-csv o8_pi_grid.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from .hierarchy import ATDB, SYMBOL_TO_Z, IndexedRecord
except Exception as exc:
    raise SystemExit(
        "Could not import xstar_atomic_hierarchy.py. Put this script in the same "
        "directory as xstar_atomic_hierarchy.py. Original error: " + repr(exc)
    )

try:
    from .lines import extract_levels, level_maps, roman, write_csv, preview_list
except Exception as exc:
    raise SystemExit(
        "Could not import xstar_atomic_extract_lines_v2.py. Put this script in the same "
        "directory as this script. Original error: " + repr(exc)
    )

RYD_EV = 13.605692


def choose_z(element: Optional[str]) -> Optional[int]:
    if not element:
        return None
    text = element.strip()
    if text.isdigit():
        return int(text)
    z = SYMBOL_TO_Z.get(text.upper())
    if z is None:
        raise ValueError(f"Unknown element: {element}")
    return z


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def row_match(record: IndexedRecord, z: Optional[int], ion_stage: Optional[int]) -> bool:
    if z is not None and record.element_z != z:
        return False
    if ion_stage is not None and record.ion_stage != ion_stage:
        return False
    return True


def verner_sigma_cm2(energy_eV: float, coeffs: Dict[str, Optional[float]], l2: int = 0) -> Optional[float]:
    """Evaluate Verner-style PI cross section using the formula in ucalc.f90."""
    try:
        e0 = float(coeffs["E0_eV"])
        s0 = float(coeffs["sigma0_raw"])
        ya = float(coeffs["ya"])
        p = float(coeffs["p"])
        yw = float(coeffs["yw"])
        y0 = float(coeffs.get("y0") or 0.0)
        y1 = float(coeffs.get("y1") or 0.0)
        if e0 <= 0 or ya <= 0:
            return None
        x = energy_eV / e0 - y0
        if y1 != 0.0:
            y = math.sqrt(x*x + y1*y1)
        else:
            y = x
        if y <= 0:
            return None
        ywsq = yw*yw
        qq = 5.5 + l2 - p/2.0
        ff = ((x - 1.0)*(x - 1.0) + ywsq) * math.exp(-qq * math.log(max(1e-48, y))) * (1.0 + math.sqrt(y/ya))**(-p)
        return s0 * ff * 1.0e-18
    except Exception:
        return None


def decode_type49_53_summary(
    r: IndexedRecord,
    rd: List[float],
    it: List[int],
    labels: Dict[int, str],
    energies: Dict[int, float],
    nlev: int,
) -> Tuple[dict, List[dict]]:
    lower_level = safe_int(it[-2]) if len(it) >= 2 else None
    final_rel = safe_int(it[-3]) if len(it) >= 3 else None
    ion_pointer = safe_int(it[-1]) if len(it) >= 1 else None

    if r.data_type == 49 and final_rel is not None:
        final_continuum_index = nlev + max(0, final_rel) - 1
    elif final_rel is not None:
        final_continuum_index = nlev + final_rel - 1
    else:
        final_continuum_index = None

    lower_energy = energies.get(lower_level) if lower_level is not None else None
    # level table stores continuum/reference energy in the ionization_potential column;
    # recover it from the level rows where possible via energies handled externally later.
    # Here threshold is filled by caller using level_rows_by_index.

    grid_points = len(rd) // 2
    rel_ryd = [safe_float(rd[2*i]) for i in range(grid_points)]
    sigma_raw = [safe_float(rd[2*i+1]) for i in range(grid_points)]

    summary = {
        "record": r.recno,
        "element_z": r.element_z,
        "element": r.element_symbol,
        "ion_stage": r.ion_stage,
        "ion_roman": roman(r.ion_stage),
        "ion": r.ion_label,
        "charge": r.charge_label,
        "data_type": r.data_type,
        "rate_type": r.rate_type,
        "lower_level": lower_level,
        "lower_label": labels.get(lower_level, "") if lower_level is not None else "",
        "lower_energy_eV": lower_energy,
        "final_continuum_relative_index": final_rel,
        "final_continuum_index": final_continuum_index,
        "ion_pointer": ion_pointer,
        "n_grid_points": grid_points,
        "energy_offset_min_Ryd": min([x for x in rel_ryd if x is not None], default=None),
        "energy_offset_max_Ryd": max([x for x in rel_ryd if x is not None], default=None),
        "sigma_raw_min": min([x for x in sigma_raw if x is not None], default=None),
        "sigma_raw_max": max([x for x in sigma_raw if x is not None], default=None),
        "sigma_threshold_cm2": (sigma_raw[0] * 1.0e-18) if sigma_raw and sigma_raw[0] is not None else None,
        "nreal": r.nreal,
        "nint": r.nint,
        "nchar": r.nchar,
        "raw_ints": preview_list(it),
        "raw_reals_preview": preview_list(rd),
    }

    grid_rows = []
    for i in range(grid_points):
        eoff = rel_ryd[i]
        sig = sigma_raw[i]
        grid_rows.append({
            "record": r.recno,
            "element": r.element_symbol,
            "ion_stage": r.ion_stage,
            "ion_roman": roman(r.ion_stage),
            "data_type": r.data_type,
            "rate_type": r.rate_type,
            "lower_level": lower_level,
            "lower_label": labels.get(lower_level, "") if lower_level is not None else "",
            "point_index": i + 1,
            "energy_offset_Ryd": eoff,
            "energy_offset_eV": eoff * RYD_EV if eoff is not None else None,
            "sigma_raw_1e-18_cm2": sig,
            "sigma_cm2": sig * 1.0e-18 if sig is not None else None,
        })

    return summary, grid_rows


def decode_type59_summary(r: IndexedRecord, rd: List[float], it: List[int], labels: Dict[int, str], energies: Dict[int, float], nlev: int) -> Tuple[dict, List[dict]]:
    lower_level = safe_int(it[-2]) if len(it) >= 2 else None
    final_rel = safe_int(it[-3]) if len(it) >= 3 else None
    ion_pointer = safe_int(it[-1]) if len(it) >= 1 else None
    final_continuum_index = nlev + final_rel - 1 if final_rel is not None else None
    lower_energy = energies.get(lower_level) if lower_level is not None else None

    summary = {
        "record": r.recno,
        "element_z": r.element_z,
        "element": r.element_symbol,
        "ion_stage": r.ion_stage,
        "ion_roman": roman(r.ion_stage),
        "ion": r.ion_label,
        "charge": r.charge_label,
        "data_type": r.data_type,
        "rate_type": r.rate_type,
        "lower_level": lower_level,
        "lower_label": labels.get(lower_level, "") if lower_level is not None else "",
        "lower_energy_eV": lower_energy,
        "final_continuum_relative_index": final_rel,
        "final_continuum_index": final_continuum_index,
        "ion_pointer": ion_pointer,
        "nreal": r.nreal,
        "nint": r.nint,
        "nchar": r.nchar,
        "raw_ints": preview_list(it),
        "raw_reals_preview": preview_list(rd),
    }

    if len(rd) == 9:
        keys = ["threshold_eV", "emax_eV", "E0_eV", "sigma0_raw", "ya", "p", "yw", "y0", "y1"]
        for k, v in zip(keys, rd):
            summary[k] = safe_float(v)
        summary["sigma0_cm2_scale"] = (summary.get("sigma0_raw") or 0.0) * 1.0e-18
        l2 = 0
    elif len(rd) >= 6:
        # Alternate compact format visible in ucalc.f90. The threshold is not rd[0] in
        # the same way as the 9-real form; keep all raw values and identify coefficients.
        summary["threshold_or_reference_eV"] = safe_float(rd[0])
        summary["E0_eV"] = safe_float(rd[1])
        summary["sigma0_raw"] = safe_float(rd[2])
        summary["ya"] = safe_float(rd[3])
        summary["p"] = safe_float(rd[4])
        summary["yw"] = safe_float(rd[5])
        summary["y0"] = 0.0
        summary["y1"] = 0.0
        summary["sigma0_cm2_scale"] = (summary.get("sigma0_raw") or 0.0) * 1.0e-18
        l2 = safe_int(it[2]) if len(it) > 2 else 0
    else:
        l2 = 0

    grid_rows = []
    eth = summary.get("threshold_eV") or summary.get("threshold_or_reference_eV")
    emax = summary.get("emax_eV") or (eth * 10.0 if eth else None)
    if eth and emax and eth > 0 and emax > eth and summary.get("E0_eV"):
        # Small diagnostic grid, not a replacement for XSTAR's continuum mesh.
        for i in range(25):
            frac = i / 24.0
            e = eth * (emax / eth) ** frac
            grid_rows.append({
                "record": r.recno,
                "element": r.element_symbol,
                "ion_stage": r.ion_stage,
                "ion_roman": roman(r.ion_stage),
                "data_type": r.data_type,
                "rate_type": r.rate_type,
                "lower_level": lower_level,
                "lower_label": labels.get(lower_level, "") if lower_level is not None else "",
                "point_index": i + 1,
                "photon_energy_eV": e,
                "sigma_cm2": verner_sigma_cm2(e, summary, l2=l2),
            })
    return summary, grid_rows


def extract_photoionization(db: ATDB, records: List[IndexedRecord], z: Optional[int], ion_stage: Optional[int]) -> Tuple[List[dict], List[dict]]:
    levels = extract_levels(db, records, z, ion_stage)
    level_by_index, labels, energies, gs = level_maps(levels)
    nlev = max(level_by_index.keys(), default=0)

    summaries: List[dict] = []
    grids: List[dict] = []

    for r in records:
        if not row_match(r, z, ion_stage):
            continue
        if r.data_type not in (49, 53, 59, 85, 88, 99) and r.rate_type not in (1, 7, 42):
            continue
        h = db.header(r.recno)
        rd = list(db.real_slice(h))
        it = list(db.int_slice(h))
        ch = db.char_slice(h)

        if r.data_type in (49, 53):
            summary, grid_rows = decode_type49_53_summary(r, rd, it, labels, energies, nlev)
            lower = summary.get("lower_level")
            lev = level_by_index.get(lower) if lower is not None else None
            if lev:
                ip = lev.get("ionization_potential_eV")
                ee = lev.get("energy_eV")
                if ip is not None and ee is not None:
                    threshold = float(ip) - float(ee)
                    summary["threshold_eV_from_level"] = threshold
                    summary["threshold_keV_from_level"] = threshold / 1000.0
                    for grow in grid_rows:
                        eoff = grow.get("energy_offset_eV")
                        grow["threshold_eV_from_level"] = threshold
                        grow["photon_energy_eV_approx"] = threshold + max(0.0, eoff or 0.0)
                        grow["photon_energy_keV_approx"] = grow["photon_energy_eV_approx"] / 1000.0
            summary["char_label"] = ch
            summaries.append(summary)
            grids.extend(grid_rows)
        elif r.data_type == 59:
            summary, grid_rows = decode_type59_summary(r, rd, it, labels, energies, nlev)
            summary["char_label"] = ch
            summaries.append(summary)
            grids.extend(grid_rows)
        else:
            # Unknown/newer photoionization/Auger-related records: preserve metadata.
            lower = safe_int(it[-2]) if len(it) >= 2 else None
            summaries.append({
                "record": r.recno,
                "element_z": r.element_z,
                "element": r.element_symbol,
                "ion_stage": r.ion_stage,
                "ion_roman": roman(r.ion_stage),
                "ion": r.ion_label,
                "charge": r.charge_label,
                "data_type": r.data_type,
                "rate_type": r.rate_type,
                "lower_level_candidate": lower,
                "lower_label": labels.get(lower, "") if lower is not None else "",
                "nreal": r.nreal,
                "nint": r.nint,
                "nchar": r.nchar,
                "char_label": ch,
                "raw_ints": preview_list(it),
                "raw_reals_preview": preview_list(rd),
            })

    summaries.sort(key=lambda x: (x.get("threshold_eV_from_level") if x.get("threshold_eV_from_level") is not None else x.get("threshold_eV") if x.get("threshold_eV") is not None else 1e99, x.get("record") or 0))
    grids.sort(key=lambda x: (x.get("record") or 0, x.get("point_index") or 0))
    return summaries, grids


def filter_summaries(rows: List[dict], threshold_min: Optional[float], threshold_max: Optional[float], data_type: Optional[int], rate_type: Optional[int], lower_level: Optional[int]) -> List[dict]:
    out = []
    for row in rows:
        threshold = row.get("threshold_eV_from_level") or row.get("threshold_eV") or row.get("threshold_or_reference_eV")
        if threshold_min is not None and (threshold is None or threshold < threshold_min):
            continue
        if threshold_max is not None and (threshold is None or threshold > threshold_max):
            continue
        if data_type is not None and row.get("data_type") != data_type:
            continue
        if rate_type is not None and row.get("rate_type") != rate_type:
            continue
        if lower_level is not None and row.get("lower_level", row.get("lower_level_candidate")) != lower_level:
            continue
        out.append(row)
    return out


def slim(row: dict) -> dict:
    keys = [
        "record", "element", "ion_roman", "ion_stage", "data_type", "rate_type",
        "lower_level", "lower_level_candidate", "lower_label",
        "final_continuum_relative_index", "final_continuum_index",
        "threshold_eV_from_level", "threshold_keV_from_level", "threshold_eV",
        "n_grid_points", "sigma_threshold_cm2", "sigma_raw_min", "sigma_raw_max",
        "E0_eV", "sigma0_raw", "ya", "p", "yw", "y0", "y1", "char_label",
    ]
    return {k: row.get(k) for k in keys if k in row}


def main() -> None:
    ap = argparse.ArgumentParser(description="Decode/search XSTAR atdb.fits photoionization/bound-free records")
    ap.add_argument("fitsfile")
    ap.add_argument("--element", help="Element symbol or Z, e.g. O or 8")
    ap.add_argument("--ion-stage", type=int, help="Ion stage, e.g. 8 for O VIII")
    ap.add_argument("--summary", action="store_true", help="Print counts")
    ap.add_argument("--search", action="store_true", help="Print filtered PI summaries")
    ap.add_argument("--summary-csv", help="Write one-row-per-record summary CSV")
    ap.add_argument("--grid-csv", help="Write one-row-per-grid-point CSV")
    ap.add_argument("--threshold-min-ev", type=float)
    ap.add_argument("--threshold-max-ev", type=float)
    ap.add_argument("--data-type", type=int)
    ap.add_argument("--rate-type", type=int)
    ap.add_argument("--lower-level", type=int)
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    z = choose_z(args.element)
    with ATDB(args.fitsfile, load_reals=True) as db:
        records, elements, ions = db.build_index()
        summaries, grids = extract_photoionization(db, records, z, args.ion_stage)
        selected = filter_summaries(summaries, args.threshold_min_ev, args.threshold_max_ev, args.data_type, args.rate_type, args.lower_level)

    if args.summary_csv:
        write_csv(args.summary_csv, summaries)
        print(f"Wrote {args.summary_csv} ({len(summaries)} rows)")
    if args.grid_csv:
        write_csv(args.grid_csv, grids)
        print(f"Wrote {args.grid_csv} ({len(grids)} rows)")

    if args.summary or not any([args.summary_csv, args.grid_csv, args.search]):
        counts = {}
        for row in summaries:
            key = f"{row.get('data_type')},{row.get('rate_type')}"
            counts[key] = counts.get(key, 0) + 1
        print(json.dumps({
            "fitsfile": args.fitsfile,
            "element_filter": args.element,
            "z_filter": z,
            "ion_stage_filter": args.ion_stage,
            "n_photoionization_like_records": len(summaries),
            "n_grid_rows": len(grids),
            "counts_by_data_rate_type": counts,
        }, indent=2))

    if args.search:
        print(json.dumps({
            "query": {
                "element": args.element,
                "z": z,
                "ion_stage": args.ion_stage,
                "threshold_min_eV": args.threshold_min_ev,
                "threshold_max_eV": args.threshold_max_ev,
                "data_type": args.data_type,
                "rate_type": args.rate_type,
                "lower_level": args.lower_level,
            },
            "n_matches": len(selected),
            "matches": [slim(row) for row in selected[:args.limit]],
        }, indent=2))


if __name__ == "__main__":
    main()
