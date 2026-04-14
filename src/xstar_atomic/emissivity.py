"""
xstar_atomic_make_emissivity_table_v1.py

Build an emissivity-ready joined table from XSTAR's packed atdb.fits.

This script joins the validated XSTAR Atomic readers/decoders:

  * xstar_atomic_hierarchy.py
  * xstar_atomic_extract_lines_v2.py
  * xstar_atomic_extract_collisions_v2b.py

It produces one row per radiative line, per matched collisional-excitation
record, per requested temperature.  The output is intended for plasma-emissivity
post-processing, e.g. a low-density coronal approximation where a collisional
excitation into an upper level is followed by radiative decay.

Main output quantities
----------------------
  line_photon_emissivity_coeff_cm3_s = q_excitation_cm3_s * branching_ratio
  line_energy_emissivity_coeff_erg_cm3_s = line_photon_coeff * h nu

These are coefficients per electron per ion in cm^3 s^-1 and erg cm^3 s^-1.
To get volume emissivity, multiply by n_e * n_ion.

Important caveats
-----------------
  * This is a direct-excitation + radiative-branching table.  It does not yet
    include cascades from higher levels, recombination cascades, optical-depth
    effects, or density-dependent level populations.
  * Branching ratios are computed from decoded radiative A-values within the
    same ion: A_ul / sum_l A_ul.  Missing radiative records mean incomplete
    branching information.
  * Type-63 collisions use the current v2b evaluator.  Same-n l-mixing and
    Delta-l != 1 branches remain diagnostic-only unless implemented there.

Examples
--------
# O VIII Ly-alpha emissivity-ready rows
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o8_lya_emissivity.csv

# O VII direct-excitation lines from ground covered by type-63
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element O --ion-stage 7 --lower-level 1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o7_emissivity.csv

# Also save component tables for debugging
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element Ne --ion-stage 10 --temperatures 1e6 1e7 \
  --out-csv nex_emissivity.csv \
  --lines-csv nex_lines.csv \
  --collisions-csv nex_collisions.csv \
  --collision-eval-csv nex_collision_eval.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Make imports work when this script is run from a directory containing the
# companion scripts, or when the companion scripts live next to this file.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from .hierarchy import ATDB  # type: ignore
from .lines import (  # type: ignore
    choose_z,
    extract_levels,
    extract_lines,
    level_maps,
)
from .collisions import extract_collisions  # type: ignore


HC_EV_A = 12398.419843320026
EV_TO_ERG = 1.602176634e-12


def write_csv(path: str | Path, rows: List[dict]) -> None:
    path = Path(path)
    if not rows:
        path.write_text("")
        return
    keys: List[str] = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                keys.append(k)
                seen.add(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def maybe_float(x) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def maybe_int(x) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None


def line_energy_erg(line: dict) -> Optional[float]:
    e_ev = maybe_float(line.get("energy_eV"))
    if e_ev is None:
        wave = maybe_float(line.get("wavelength_A")) or maybe_float(line.get("wavelength_from_level_energies_A"))
        if wave and wave > 0:
            e_ev = HC_EV_A / wave
    return e_ev * EV_TO_ERG if e_ev is not None else None


def is_usable_radiative_line(row: dict, include_two_photon: bool = False, include_superlevel: bool = False) -> bool:
    """Conservative line filter for emissivity joins."""
    rt = maybe_int(row.get("rate_type"))
    dt = maybe_int(row.get("data_type"))
    if rt == 4:
        pass
    elif include_two_photon and rt == 9:
        pass
    elif include_superlevel and rt == 14:
        pass
    else:
        return False
    if maybe_int(row.get("lower_level")) is None or maybe_int(row.get("upper_level")) is None:
        return False
    if maybe_float(row.get("A_s^-1")) is None:
        # For now only lines with true decoded A-values are used for branching.
        return False
    if maybe_float(row.get("wavelength_A")) is None and maybe_float(row.get("wavelength_from_level_energies_A")) is None:
        return False
    return True


def filter_lines_for_query(rows: List[dict], args) -> List[dict]:
    out: List[dict] = []
    for row in rows:
        if not is_usable_radiative_line(row, args.include_two_photon, args.include_superlevel_radiative):
            continue
        ll = maybe_int(row.get("lower_level"))
        ul = maybe_int(row.get("upper_level"))
        if args.lower_level is not None and ll != args.lower_level:
            continue
        if args.upper_level is not None and ul != args.upper_level:
            continue
        wave = maybe_float(row.get("wavelength_A")) or maybe_float(row.get("wavelength_from_level_energies_A"))
        if args.wavelength_min is not None and (wave is None or wave < args.wavelength_min):
            continue
        if args.wavelength_max is not None and (wave is None or wave > args.wavelength_max):
            continue
        ekev = maybe_float(row.get("energy_keV"))
        if ekev is None:
            eev = maybe_float(row.get("energy_eV"))
            ekev = eev / 1000.0 if eev is not None else None
        if args.energy_min_kev is not None and (ekev is None or ekev < args.energy_min_kev):
            continue
        if args.energy_max_kev is not None and (ekev is None or ekev > args.energy_max_kev):
            continue
        out.append(row)
    return out


def filter_collision_rows(rows: List[dict], args) -> List[dict]:
    out: List[dict] = []
    for row in rows:
        if args.collision_data_type is not None and maybe_int(row.get("data_type")) != args.collision_data_type:
            continue
        if args.lower_level is not None and maybe_int(row.get("lower_level")) != args.lower_level:
            continue
        if args.upper_level is not None and maybe_int(row.get("upper_level")) != args.upper_level:
            continue
        out.append(row)
    return out


def compute_branching(lines: List[dict]) -> Tuple[Dict[Tuple[int, int, int], float], Dict[int, float], Dict[int, int]]:
    """
    Return:
      branch_by_line_key[(record, lower, upper)] = A_ul / sum_l A_ul
      total_A_by_upper[upper] = sum_l A_ul
      n_decay_by_upper[upper] = number of decoded radiative decays from upper
    """
    total_A_by_upper: Dict[int, float] = {}
    n_decay_by_upper: Dict[int, int] = {}
    for row in lines:
        upper = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if upper is None or A is None or A <= 0:
            continue
        total_A_by_upper[upper] = total_A_by_upper.get(upper, 0.0) + A
        n_decay_by_upper[upper] = n_decay_by_upper.get(upper, 0) + 1

    branch_by_key: Dict[Tuple[int, int, int], float] = {}
    for row in lines:
        rec = maybe_int(row.get("record"))
        lower = maybe_int(row.get("lower_level"))
        upper = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if rec is None or lower is None or upper is None or A is None or A <= 0:
            continue
        denom = total_A_by_upper.get(upper, 0.0)
        branch_by_key[(rec, lower, upper)] = A / denom if denom > 0 else None
    return branch_by_key, total_A_by_upper, n_decay_by_upper


def build_collision_lookup(eval_rows: List[dict]) -> Dict[Tuple[int, int, float], List[dict]]:
    lookup: Dict[Tuple[int, int, float], List[dict]] = {}
    for row in eval_rows:
        lower = maybe_int(row.get("lower_level"))
        upper = maybe_int(row.get("upper_level"))
        T = maybe_float(row.get("temperature_K"))
        if lower is None or upper is None or T is None:
            continue
        lookup.setdefault((lower, upper, T), []).append(row)
    return lookup


def build_emissivity_rows(
    line_rows: List[dict],
    collision_eval_rows: List[dict],
    temperatures: Sequence[float],
    include_unmatched_lines: bool = False,
) -> List[dict]:
    branch_by_key, total_A_by_upper, n_decay_by_upper = compute_branching(line_rows)
    coll_lookup = build_collision_lookup(collision_eval_rows)

    out: List[dict] = []
    for line in line_rows:
        line_record = maybe_int(line.get("record"))
        lower = maybe_int(line.get("lower_level"))
        upper = maybe_int(line.get("upper_level"))
        if line_record is None or lower is None or upper is None:
            continue
        A_line = maybe_float(line.get("A_s^-1"))
        total_A = total_A_by_upper.get(upper)
        branching = branch_by_key.get((line_record, lower, upper))
        e_erg = line_energy_erg(line)
        wave = maybe_float(line.get("wavelength_A")) or maybe_float(line.get("wavelength_from_level_energies_A"))
        energy_ev = maybe_float(line.get("energy_eV"))
        if energy_ev is None and e_erg is not None:
            energy_ev = e_erg / EV_TO_ERG
        energy_kev = energy_ev / 1000.0 if energy_ev is not None else None

        any_match_for_line = False
        for T in temperatures:
            matches = coll_lookup.get((lower, upper, float(T)), [])
            usable_matches = matches
            if not usable_matches and include_unmatched_lines:
                usable_matches = [None]
            for coll in usable_matches:
                any_match_for_line = True
                if coll is None:
                    q_exc = None
                    q_de = None
                    photon_coeff = None
                    energy_coeff = None
                    coll_record = None
                    coll_data_type = None
                    coll_source_format = "no_matched_collision"
                    coll_method = "no_matched_collision"
                    coll_diag = "no collision evaluation row matched line lower/upper/T"
                else:
                    q_exc = maybe_float(coll.get("q_excitation_cm3_s"))
                    q_de = maybe_float(coll.get("q_deexcitation_cm3_s"))
                    photon_coeff = q_exc * branching if q_exc is not None and branching is not None else None
                    energy_coeff = photon_coeff * e_erg if photon_coeff is not None and e_erg is not None else None
                    coll_record = coll.get("record")
                    coll_data_type = coll.get("data_type")
                    coll_source_format = coll.get("source_format")
                    coll_method = coll.get("eval_method")
                    coll_diag = coll.get("eval_diagnostic")

                out.append({
                    "element": line.get("element"),
                    "element_z": line.get("element_z"),
                    "ion": line.get("ion"),
                    "ion_stage": line.get("ion_stage"),
                    "ion_roman": line.get("ion_roman"),
                    "charge": line.get("charge"),
                    "line_record": line_record,
                    "line_data_type": line.get("data_type"),
                    "line_rate_type": line.get("rate_type"),
                    "collision_record": coll_record,
                    "collision_data_type": coll_data_type,
                    "collision_source_format": coll_source_format,
                    "collision_eval_method": coll_method,
                    "collision_eval_diagnostic": coll_diag,
                    "lower_level": lower,
                    "upper_level": upper,
                    "lower_label": line.get("lower_label"),
                    "upper_label": line.get("upper_label"),
                    "wavelength_A": wave,
                    "energy_eV": energy_ev,
                    "energy_keV": energy_kev,
                    "photon_energy_erg": e_erg,
                    "delta_e_level_eV": line.get("delta_e_level_eV"),
                    "A_line_s^-1": A_line,
                    "A_total_from_upper_s^-1": total_A,
                    "n_radiative_decays_from_upper": n_decay_by_upper.get(upper, 0),
                    "branching_ratio": branching,
                    "f_osc_from_A": line.get("f_osc_from_A"),
                    "temperature_K": float(T),
                    "q_excitation_cm3_s": q_exc,
                    "q_deexcitation_cm3_s": q_de,
                    "line_photon_emissivity_coeff_cm3_s": photon_coeff,
                    "line_energy_emissivity_coeff_erg_cm3_s": energy_coeff,
                    "line_char_label": line.get("char_label"),
                    "collision_lower_label": coll.get("lower_label") if coll else "",
                    "collision_upper_label": coll.get("upper_label") if coll else "",
                    "collision_n_lower": coll.get("n_lower") if coll else None,
                    "collision_l_lower": coll.get("l_lower") if coll else None,
                    "collision_n_upper": coll.get("n_upper") if coll else None,
                    "collision_l_upper": coll.get("l_upper") if coll else None,
                })
        # If there were no temperature matches and include_unmatched_lines was false,
        # skip silently; the summary will count unmatched lines separately.
    out.sort(key=lambda r: (
        r.get("wavelength_A") if r.get("wavelength_A") is not None else 1e99,
        r.get("temperature_K") if r.get("temperature_K") is not None else 1e99,
        r.get("line_record") or 0,
        r.get("collision_record") or 0,
    ))
    return out


def summarize(line_rows: List[dict], collision_summary: List[dict], collision_eval: List[dict], emissivity_rows: List[dict]) -> dict:
    def counts(rows: List[dict], key: str) -> Dict[str, int]:
        d: Dict[str, int] = {}
        for r in rows:
            k = str(r.get(key))
            d[k] = d.get(k, 0) + 1
        return dict(sorted(d.items()))

    line_keys = {(maybe_int(r.get("lower_level")), maybe_int(r.get("upper_level"))) for r in line_rows}
    coll_keys = {(maybe_int(r.get("lower_level")), maybe_int(r.get("upper_level"))) for r in collision_summary}
    line_keys.discard((None, None))
    coll_keys.discard((None, None))
    matched_pairs = line_keys & coll_keys

    return {
        "n_radiative_lines_selected": len(line_rows),
        "n_collision_records_selected": len(collision_summary),
        "n_collision_eval_rows": len(collision_eval),
        "n_emissivity_rows": len(emissivity_rows),
        "n_unique_line_level_pairs": len(line_keys),
        "n_unique_collision_level_pairs": len(coll_keys),
        "n_level_pairs_with_both_line_and_collision": len(matched_pairs),
        "line_counts_by_data_type": counts(line_rows, "data_type"),
        "collision_counts_by_data_type": counts(collision_summary, "data_type"),
        "collision_eval_counts_by_method": counts(collision_eval, "eval_method"),
        "emissivity_counts_by_collision_method": counts(emissivity_rows, "collision_eval_method"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Make emissivity-ready line+collision tables from XSTAR atdb.fits")
    p.add_argument("fitsfile")
    p.add_argument("--element", required=True, help="Element symbol or Z, e.g. O or 8")
    p.add_argument("--ion-stage", type=int, required=True, help="Ion stage, e.g. 8 for O VIII")
    p.add_argument("--temperatures", type=float, nargs="+", default=[1e6, 3e6, 1e7], help="Temperatures in K")
    p.add_argument("--electron-density-for-lmixing", type=float, default=1.0, help="Electron density cm^-3 used only for type-63 same-n l-mixing cutoff")

    p.add_argument("--lower-level", type=int)
    p.add_argument("--upper-level", type=int)
    p.add_argument("--wavelength-min", type=float)
    p.add_argument("--wavelength-max", type=float)
    p.add_argument("--energy-min-kev", type=float)
    p.add_argument("--energy-max-kev", type=float)
    p.add_argument("--collision-data-type", type=int, help="Optional collision data_type filter, e.g. 56 or 63")

    p.add_argument("--include-two-photon", action="store_true", help="Include rate_type=9 radiative records when A-values are decoded")
    p.add_argument("--include-superlevel-radiative", action="store_true", help="Include rate_type=14 records when A-values are decoded")
    p.add_argument("--include-unmatched-lines", action="store_true", help="Emit line/T rows even if no collision matched")

    p.add_argument("--out-csv", default="emissivity_table.csv")
    p.add_argument("--summary-json")
    p.add_argument("--levels-csv")
    p.add_argument("--lines-csv")
    p.add_argument("--collisions-csv")
    p.add_argument("--collision-grid-csv")
    p.add_argument("--collision-eval-csv")
    p.add_argument("--print-summary", action="store_true")

    args = p.parse_args()

    z = choose_z(args.element)
    if z is None:
        raise SystemExit(f"Could not parse element: {args.element}")

    db = ATDB(Path(args.fitsfile))
    records, elements, ions = db.build_index()

    level_rows = extract_levels(db, records, z, args.ion_stage)
    all_line_rows = extract_lines(db, records, z, args.ion_stage)
    line_rows = filter_lines_for_query(all_line_rows, args)

    collision_summary, collision_grid, collision_eval = extract_collisions(
        db, records, z, args.ion_stage, args.temperatures,
        electron_density_cm3=args.electron_density_for_lmixing,
    )
    collision_summary = filter_collision_rows(collision_summary, args)
    # Filter eval rows consistently with selected collision records.
    selected_collision_records = {maybe_int(r.get("record")) for r in collision_summary}
    selected_collision_records.discard(None)
    collision_eval = [r for r in collision_eval if maybe_int(r.get("record")) in selected_collision_records]
    collision_grid = [r for r in collision_grid if maybe_int(r.get("record")) in selected_collision_records]

    emissivity_rows = build_emissivity_rows(
        line_rows,
        collision_eval,
        args.temperatures,
        include_unmatched_lines=args.include_unmatched_lines,
    )

    write_csv(args.out_csv, emissivity_rows)
    if args.levels_csv:
        write_csv(args.levels_csv, level_rows)
    if args.lines_csv:
        write_csv(args.lines_csv, line_rows)
    if args.collisions_csv:
        write_csv(args.collisions_csv, collision_summary)
    if args.collision_grid_csv:
        write_csv(args.collision_grid_csv, collision_grid)
    if args.collision_eval_csv:
        write_csv(args.collision_eval_csv, collision_eval)

    info = summarize(line_rows, collision_summary, collision_eval, emissivity_rows)
    info.update({
        "fitsfile": args.fitsfile,
        "element": args.element,
        "z": z,
        "ion_stage": args.ion_stage,
        "temperatures_K": [float(t) for t in args.temperatures],
        "out_csv": str(args.out_csv),
    })
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(info, indent=2), encoding="utf-8")
    if args.print_summary or not args.summary_json:
        print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
