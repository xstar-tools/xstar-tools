"""
xstar_atomic_extract_lines_v2.py

Physics-decoded level and radiative-line extractor for XSTAR's packed
atdb.fits atomic database.

This version is meant as the next validation layer after xstar_atomic_hierarchy.py:
  * decodes level records (rate_type=13, usually data_type=6/83);
  * decodes radiative line records (rate_type=4/9/14; especially data_type=50);
  * determines the physical lower/upper levels from the decoded level energies;
  * computes wavelength, energy, A-value, and an oscillator-strength estimate
    using the same type-50 relation visible in XSTAR's ucalc.f90;
  * supports wavelength/energy searches for known X-ray lines.

Place this file in the same directory as xstar_atomic_hierarchy.py.

Examples
--------
# O VIII Ly-alpha search
python xstar_atomic_extract_lines_v2.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1

# Export decoded O VIII levels and lines
python xstar_atomic_extract_lines_v2.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --levels-csv o8_levels_v2.csv --lines-csv o8_lines_v2.csv

# Query by energy range in keV
python xstar_atomic_extract_lines_v2.py ./xstar/data/atdb.fits \
  --element Fe --ion-stage 26 \
  --line-search --energy-min-kev 6.8 --energy-max-kev 7.2
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from .hierarchy import ATDB, SYMBOL_TO_Z, IndexedRecord
except Exception as exc:  # pragma: no cover - user environment check
    raise SystemExit(
        "Could not import xstar_atomic_hierarchy.py. Put this script in the same "
        "directory as xstar_atomic_hierarchy.py. Original error: " + repr(exc)
    )

HC_EV_A = 12398.4016
# From XSTAR ucalc.f90 type 50:
# flin=(1.d-16)*aij*ggup*elin*elin/((0.667274)*gglo)
XSTAR_FOSC_DENOM = 0.667274


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


def roman(n: Optional[int]) -> str:
    if n is None or n <= 0:
        return ""
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def write_csv(path: str | Path, rows: List[dict]) -> None:
    path = Path(path)
    if not rows:
        path.write_text("")
        return
    keys: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def preview_list(values: Iterable, max_n: int = 12) -> str:
    vals = list(values) if values is not None else []
    if len(vals) <= max_n:
        return json.dumps(vals)
    return json.dumps(vals[:max_n] + [f"... {len(vals)-max_n} more"])


def row_match(record: IndexedRecord, z: Optional[int], ion_stage: Optional[int]) -> bool:
    if z is not None and record.element_z != z:
        return False
    if ion_stage is not None and record.ion_stage != ion_stage:
        return False
    return True


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def extract_levels(db: ATDB, records: List[IndexedRecord], z: Optional[int], ion_stage: Optional[int]) -> List[dict]:
    rows: List[dict] = []
    for r in records:
        if not row_match(r, z, ion_stage):
            continue
        if r.rate_type != 13:
            continue
        h = db.header(r.recno)
        rd = db.real_slice(h)
        it = db.int_slice(h)
        ch = db.char_slice(h)

        level_index = safe_int(it[-2]) if len(it) >= 2 else r.level_index
        ion_pointer = safe_int(it[-1]) if len(it) >= 1 else None
        n_principal = safe_int(it[0]) if len(it) > 0 else None
        multiplicity = safe_int(it[1]) if len(it) > 1 else None
        orbital_l = safe_int(it[2]) if len(it) > 2 else None

        energy_ev = safe_float(rd[0]) if len(rd) > 0 else None
        g_stat = safe_float(rd[1]) if len(rd) > 1 else None
        effective_n = safe_float(rd[2]) if len(rd) > 2 else None
        ionization_potential_ev = safe_float(rd[3]) if len(rd) > 3 else None
        binding_from_continuum_ev = None
        if ionization_potential_ev is not None and energy_ev is not None:
            binding_from_continuum_ev = ionization_potential_ev - energy_ev

        rows.append({
            "record": r.recno,
            "element_z": r.element_z,
            "element": r.element_symbol,
            "ion_stage": r.ion_stage,
            "ion_roman": roman(r.ion_stage),
            "ion": r.ion_label,
            "charge": r.charge_label,
            "data_type": r.data_type,
            "rate_type": r.rate_type,
            "level_index": level_index,
            "level_label": ch,
            "energy_eV": energy_ev,
            "statistical_weight_g": g_stat,
            "effective_n": effective_n,
            "ionization_potential_eV": ionization_potential_ev,
            "binding_from_continuum_eV": binding_from_continuum_ev,
            "n_principal": n_principal,
            "multiplicity": multiplicity,
            "orbital_l": orbital_l,
            "ion_pointer": ion_pointer,
            "nreal": r.nreal,
            "nint": r.nint,
            "nchar": r.nchar,
            "raw_reals": preview_list(rd),
            "raw_ints": preview_list(it),
        })
    rows.sort(key=lambda row: (row.get("element_z") or 0, row.get("ion_stage") or 0, row.get("level_index") or 0, row.get("record") or 0))
    return rows


def level_maps(level_rows: List[dict]) -> Tuple[Dict[int, dict], Dict[int, str], Dict[int, float], Dict[int, float]]:
    by_index: Dict[int, dict] = {}
    labels: Dict[int, str] = {}
    energies: Dict[int, float] = {}
    gs: Dict[int, float] = {}
    for lev in level_rows:
        idx = lev.get("level_index")
        if idx is None:
            continue
        idx = int(idx)
        by_index[idx] = lev
        labels[idx] = lev.get("level_label", "") or ""
        if lev.get("energy_eV") is not None:
            energies[idx] = float(lev["energy_eV"])
        if lev.get("statistical_weight_g") is not None:
            gs[idx] = float(lev["statistical_weight_g"])
    return by_index, labels, energies, gs


def physical_order(level_a: Optional[int], level_b: Optional[int], energies: Dict[int, float]) -> Tuple[Optional[int], Optional[int]]:
    """Return (lower_energy_level, upper_energy_level), when known."""
    if level_a is None or level_b is None:
        return level_a, level_b
    ea = energies.get(int(level_a))
    eb = energies.get(int(level_b))
    if ea is None or eb is None:
        return level_a, level_b
    if ea <= eb:
        return int(level_a), int(level_b)
    return int(level_b), int(level_a)


def oscillator_strength_from_a(a_s: Optional[float], wavelength_a: Optional[float], g_upper: Optional[float], g_lower: Optional[float]) -> Optional[float]:
    if a_s is None or wavelength_a is None or g_upper in (None, 0.0) or g_lower in (None, 0.0):
        return None
    try:
        return 1.0e-16 * float(a_s) * float(g_upper) * float(wavelength_a) ** 2 / (XSTAR_FOSC_DENOM * float(g_lower))
    except Exception:
        return None


def extract_lines(db: ATDB, records: List[IndexedRecord], z: Optional[int], ion_stage: Optional[int]) -> List[dict]:
    levels = extract_levels(db, records, z, ion_stage)
    _, labels, energies, gs = level_maps(levels)

    rows: List[dict] = []
    for r in records:
        if not row_match(r, z, ion_stage):
            continue
        # rate_type=4 is bound-bound radiative; 9 is two-photon-like; 14 is superlevel radiative.
        if r.rate_type not in (4, 9, 14):
            continue

        h = db.header(r.recno)
        rd = db.real_slice(h)
        it = db.int_slice(h)
        ch = db.char_slice(h)

        idat_level_1 = safe_int(it[0]) if len(it) > 0 else None
        idat_level_2 = safe_int(it[1]) if len(it) > 1 else None
        lower, upper = physical_order(idat_level_1, idat_level_2, energies)

        wave = abs(float(rd[0])) if len(rd) > 0 and float(rd[0]) != 0.0 else None
        energy_ev_from_wavelength = HC_EV_A / wave if wave and wave > 0 else None
        energy_kev_from_wavelength = energy_ev_from_wavelength / 1000.0 if energy_ev_from_wavelength is not None else None

        lower_energy = energies.get(lower) if lower is not None else None
        upper_energy = energies.get(upper) if upper is not None else None
        delta_e_level_ev = None
        wavelength_from_levels_a = None
        if upper_energy is not None and lower_energy is not None:
            delta_e_level_ev = upper_energy - lower_energy
            if delta_e_level_ev > 0:
                wavelength_from_levels_a = HC_EV_A / delta_e_level_ev

        # For type 50 and type 91, ucalc uses rdat[2] as A_ij.
        # Keep raw r2 as well because some source datasets store another quantity there.
        a_s = safe_float(rd[2]) if len(rd) > 2 and r.data_type in (50, 89, 91) else None
        # For other radiative-like records, keep this conservative candidate only.
        a_candidate = safe_float(rd[2]) if len(rd) > 2 else None
        f_osc = oscillator_strength_from_a(
            a_s,
            wave,
            gs.get(upper) if upper is not None else None,
            gs.get(lower) if lower is not None else None,
        )

        rows.append({
            "record": r.recno,
            "element_z": r.element_z,
            "element": r.element_symbol,
            "ion_stage": r.ion_stage,
            "ion_roman": roman(r.ion_stage),
            "ion": r.ion_label,
            "charge": r.charge_label,
            "data_type": r.data_type,
            "rate_type": r.rate_type,
            "record_level_1": idat_level_1,
            "record_level_2": idat_level_2,
            "lower_level": lower,
            "upper_level": upper,
            "lower_label": labels.get(lower, "") if lower is not None else "",
            "upper_label": labels.get(upper, "") if upper is not None else "",
            "lower_energy_eV": lower_energy,
            "upper_energy_eV": upper_energy,
            "delta_e_level_eV": delta_e_level_ev,
            "wavelength_A": wave,
            "energy_eV": energy_ev_from_wavelength,
            "energy_keV": energy_kev_from_wavelength,
            "wavelength_from_level_energies_A": wavelength_from_levels_a,
            "wavelength_minus_level_wavelength_A": (wave - wavelength_from_levels_a) if wave is not None and wavelength_from_levels_a is not None else None,
            "A_s^-1": a_s,
            "A_candidate_r3": a_candidate,
            "f_osc_from_A": f_osc,
            "raw_r2": safe_float(rd[1]) if len(rd) > 1 else None,
            "char_label": ch,
            "nreal": r.nreal,
            "nint": r.nint,
            "nchar": r.nchar,
            "raw_reals": preview_list(rd),
            "raw_ints": preview_list(it),
        })

    rows.sort(key=lambda row: (
        row.get("wavelength_A") if row.get("wavelength_A") is not None else 1e99,
        row.get("record") or 0,
    ))
    return rows


def filter_lines(
    rows: List[dict],
    wavelength_min: Optional[float],
    wavelength_max: Optional[float],
    energy_min_kev: Optional[float],
    energy_max_kev: Optional[float],
    lower_level: Optional[int],
    upper_level: Optional[int],
    data_type: Optional[int],
    rate_type: Optional[int],
) -> List[dict]:
    out = []
    for row in rows:
        wave = row.get("wavelength_A")
        energy = row.get("energy_keV")
        if wavelength_min is not None and (wave is None or wave < wavelength_min):
            continue
        if wavelength_max is not None and (wave is None or wave > wavelength_max):
            continue
        if energy_min_kev is not None and (energy is None or energy < energy_min_kev):
            continue
        if energy_max_kev is not None and (energy is None or energy > energy_max_kev):
            continue
        if lower_level is not None and row.get("lower_level") != lower_level:
            continue
        if upper_level is not None and row.get("upper_level") != upper_level:
            continue
        if data_type is not None and row.get("data_type") != data_type:
            continue
        if rate_type is not None and row.get("rate_type") != rate_type:
            continue
        out.append(row)
    return out


def slim_line(row: dict) -> dict:
    keys = [
        "record", "element", "ion_roman", "ion_stage", "data_type", "rate_type",
        "lower_level", "upper_level", "lower_label", "upper_label",
        "wavelength_A", "energy_eV", "energy_keV", "A_s^-1", "f_osc_from_A", "char_label",
        "delta_e_level_eV", "wavelength_from_level_energies_A",
        "wavelength_minus_level_wavelength_A",
    ]
    return {k: row.get(k) for k in keys}


def main() -> None:
    ap = argparse.ArgumentParser(description="Decode/search XSTAR atdb.fits level and radiative-line records")
    ap.add_argument("fitsfile")
    ap.add_argument("--element", help="Element symbol or Z, e.g. O or 8")
    ap.add_argument("--ion-stage", type=int, help="Ion stage, e.g. 8 for O VIII")

    ap.add_argument("--levels-csv", help="Write decoded levels to CSV")
    ap.add_argument("--lines-csv", help="Write decoded radiative lines to CSV")
    ap.add_argument("--search-csv", help="Write searched/filtered line rows to CSV")

    ap.add_argument("--summary", action="store_true", help="Print level/line counts")
    ap.add_argument("--line-search", action="store_true", help="Print filtered line search results")
    ap.add_argument("--wavelength-min", type=float, help="Minimum wavelength in Angstrom")
    ap.add_argument("--wavelength-max", type=float, help="Maximum wavelength in Angstrom")
    ap.add_argument("--energy-min-kev", type=float, help="Minimum line energy in keV")
    ap.add_argument("--energy-max-kev", type=float, help="Maximum line energy in keV")
    ap.add_argument("--lower-level", type=int, help="Filter physical lower level index")
    ap.add_argument("--upper-level", type=int, help="Filter physical upper level index")
    ap.add_argument("--data-type", type=int, help="Filter line record data type")
    ap.add_argument("--rate-type", type=int, help="Filter line record rate type")
    ap.add_argument("--limit", type=int, default=25, help="Maximum printed search rows")

    args = ap.parse_args()
    z = choose_z(args.element)

    with ATDB(args.fitsfile, load_reals=True) as db:
        records, elements, ions = db.build_index()
        levels = extract_levels(db, records, z, args.ion_stage)
        lines = extract_lines(db, records, z, args.ion_stage)
        searched = filter_lines(
            lines,
            args.wavelength_min,
            args.wavelength_max,
            args.energy_min_kev,
            args.energy_max_kev,
            args.lower_level,
            args.upper_level,
            args.data_type,
            args.rate_type,
        )

        if args.levels_csv:
            write_csv(args.levels_csv, levels)
            print(f"Wrote {args.levels_csv} ({len(levels)} rows)")
        if args.lines_csv:
            write_csv(args.lines_csv, lines)
            print(f"Wrote {args.lines_csv} ({len(lines)} rows)")
        if args.search_csv:
            write_csv(args.search_csv, searched)
            print(f"Wrote {args.search_csv} ({len(searched)} rows)")

        if args.summary or not any([args.levels_csv, args.lines_csv, args.search_csv, args.line_search]):
            print(json.dumps({
                "fitsfile": args.fitsfile,
                "element_filter": args.element,
                "z_filter": z,
                "ion_stage_filter": args.ion_stage,
                "n_levels": len(levels),
                "n_radiative_line_like_records": len(lines),
                "wavelength_min_A": min([x["wavelength_A"] for x in lines if x.get("wavelength_A") is not None], default=None),
                "wavelength_max_A": max([x["wavelength_A"] for x in lines if x.get("wavelength_A") is not None], default=None),
            }, indent=2))

        if args.line_search:
            print(json.dumps({
                "query": {
                    "element": args.element,
                    "z": z,
                    "ion_stage": args.ion_stage,
                    "wavelength_min_A": args.wavelength_min,
                    "wavelength_max_A": args.wavelength_max,
                    "energy_min_keV": args.energy_min_kev,
                    "energy_max_keV": args.energy_max_kev,
                    "lower_level": args.lower_level,
                    "upper_level": args.upper_level,
                    "data_type": args.data_type,
                    "rate_type": args.rate_type,
                },
                "n_matches": len(searched),
                "matches": [slim_line(row) for row in searched[: args.limit]],
            }, indent=2))


if __name__ == "__main__":
    main()
