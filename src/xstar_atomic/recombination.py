#!/usr/bin/env python3
"""Recombination, charge-exchange, and cascade-source tools.

This module inventories and evaluates recombination-like records from
XSTAR's packed ``atdb.fits`` database.  It separates electron
radiative/dielectronic recombination from charge exchange with neutral
hydrogen, and it can generate prototype level-source CSV files for the
level-population solver.

Implemented record classes
--------------------------

* Type 1: total radiative recombination, Aldrovandi and Pequignot.
* Type 2: charge exchange with neutral hydrogen, Kingdon and Ferland.
* Type 7, 8, and 22: total dielectronic recombination fits.
* Type 30: hydrogenic total radiative recombination.
* Type 37: Fe 3pq total dielectronic recombination.
* Type 38: Badnell total radiative recombination.
* Type 39: Badnell total dielectronic recombination.

The decoded RR/DR records are usually total ion recombination rates, not
true level-resolved cascade feeds.  Source CSV output is therefore a
prototype interface for solver experiments unless a record is explicitly
identified as level resolved.

Examples
--------

Inventory oxygen recombination-like records::

    python -m xstar_atomic.recombination atdb.fits --element O --temperatures 1e6 --summary

Generate an approximate O VII source distribution::

    python -m xstar_atomic.recombination atdb.fits \
        --element O --ion-stage 7 --temperatures 1e6 \
        --source-mode selected-statistical --source-levels 2,3,4,5,7 \
        --source-csv o7_sources.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .hierarchy import ATDB, SYMBOL_TO_Z, DATA_TYPES, RATE_TYPES, IndexedRecord, roman
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Could not import xstar_atomic_hierarchy.py. Put this script in the same "
        "directory as xstar_atomic_hierarchy.py. Original error: " + repr(exc)
    )

try:
    from .lines import extract_levels, extract_lines, level_maps
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Could not import xstar_atomic_extract_lines_v2.py. Put this script in the same "
        "directory as xstar_atomic_extract_lines_v2.py. Original error: " + repr(exc)
    )

ELECTRON_RECOMB_DATA_TYPES = {1, 7, 8, 22, 30, 37, 38, 39}
CHARGE_EXCHANGE_H0_DATA_TYPES = {2}
RECOMB_DATA_TYPES = ELECTRON_RECOMB_DATA_TYPES
RECOMB_LIKE_RATE_TYPES = {2, 6, 8}
K_B_EV_PER_1E4K = 0.861707  # k_B * 1e4 K in eV, as used in ucalc.f90

CASCADE_TARGET_PRESETS: Dict[str, str] = {
    # Recommended neutral Stage-6 O VII triplet target map. It gives equal
    # target weight to the forbidden, intercombination, and resonance upper
    # levels and preserves the good G=(f+i)/r behavior found in v0.2.35.
    "o7-triplet-equal": "2:1.0,3:1.0,4:1.0,5:1.0,7:1.0",
    # Experimental O VII triplet prototype presets. They downweight the
    # forbidden target while preserving the resonance target.  These are
    # intended for Stage-6 tuning scans that try to reduce R=f/i without
    # driving G=(f+i)/r away from the XSTAR reference.
    "o7-triplet-fdown090-rkeep": "2:0.90,3:1.0,4:1.0,5:1.0,7:1.0",
    "o7-triplet-fdown085-rkeep": "2:0.85,3:1.0,4:1.0,5:1.0,7:1.0",
    "o7-triplet-fdown075-rkeep": "2:0.75,3:1.0,4:1.0,5:1.0,7:1.0",
    "o7-triplet-fdown-rkeep": "2:0.5,3:1.0,4:1.0,5:1.0,7:1.0",
    # Stage-6 shift presets: preserve the resonance target and keep the total
    # triplet-target weight close to the equal-target baseline by moving weight
    # from the forbidden upper level (2) into the intercombination upper levels
    # (3, 4, 5).  These are preferred over simple fdown presets when the goal is
    # to reduce R=f/i without strongly changing G=(f+i)/r.
    "o7-triplet-f2i010-rkeep": "2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0",
    "o7-triplet-f2i015-rkeep": "2:0.85,3:1.05,4:1.05,5:1.05,7:1.0",
    "o7-triplet-f2i025-rkeep": "2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0",
    "o7-triplet-f2i050-rkeep": "2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0",
    # Backward-compatible name for the current preferred experimental preset:
    # it shifts source weight from forbidden to intercombination targets while
    # preserving the resonance target and the total triplet-target weight.
    "o7-triplet-xstar-tuned": "2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0",
}


def resolve_cascade_target_levels(levels_text: str = "", preset: str = "") -> str:
    """Return cascade-target level text after applying a named preset.

    Manual ``levels_text`` wins over ``preset``. This keeps
    ``--cascade-target-levels`` as the explicit experimental interface while
    exposing named presets for reproducible Stage-6 workflows.
    """
    if levels_text and levels_text.strip():
        return levels_text.strip()
    if not preset or preset.strip().lower() in {"", "none"}:
        return ""
    key = preset.strip().lower()
    if key not in CASCADE_TARGET_PRESETS:
        known = ", ".join(sorted(CASCADE_TARGET_PRESETS))
        raise ValueError(f"Unknown cascade target preset {preset!r}; known presets: {known}")
    return CASCADE_TARGET_PRESETS[key]


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


def row_match(r: IndexedRecord, z: Optional[int], ion_stage: Optional[int]) -> bool:
    if z is not None and r.element_z != z:
        return False
    if ion_stage is not None and r.ion_stage != ion_stage:
        return False
    return True


def safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def preview_list(vals: Sequence, max_items: int = 18) -> str:
    out = list(vals[:max_items])
    if len(vals) > max_items:
        out.append(f"... {len(vals)-max_items} more")
    return json.dumps(out)


def write_csv(path: str | Path, rows: List[dict], preferred_fields: Optional[List[str]] = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        fields = preferred_fields or []
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if fields:
                writer.writeheader()
        return
    fields: List[str] = []
    if preferred_fields:
        for f in preferred_fields:
            if f not in fields:
                fields.append(f)
    for row in rows:
        for k in row.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_level_list(text: Optional[str]) -> List[int]:
    if not text:
        return []
    vals: List[int] = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if part:
            vals.append(int(part))
    return vals


def parse_level_weight_map(text: str, default_weight: float = 1.0) -> Dict[int, float]:
    """Parse level weights like ``2,3,5`` or ``2:1.0,3:0.5``."""
    out: Dict[int, float] = {}
    if not text:
        return out
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            level_s, weight_s = part.split(":", 1)
            out[int(level_s.strip())] = float(weight_s.strip())
        else:
            out[int(part)] = float(default_weight)
    return out


def is_recombination_like(r: IndexedRecord) -> bool:
    if r.data_type in RECOMB_DATA_TYPES:
        return True
    if r.rate_type in RECOMB_LIKE_RATE_TYPES:
        return True
    # Some charge-exchange records behave recombination-like but are not electron recombination.
    if r.data_type in {2, 9} and r.rate_type in {2, 6, 8}:
        return True
    return False


def infer_destination_level(data_type: int, rate_type: int, ints: List[int], default_ground: int = 1) -> Optional[int]:
    """Infer recombined-ion destination level when XSTAR's indonly logic exposes it."""
    # Most total recombination records set idest1=1 in ucalc.
    if data_type in {1, 7, 8, 22, 30, 37, 38, 39}:
        return default_ground
    # Charge exchange He-like branch can contain a level in idat[0].
    if data_type == 9 and len(ints) > 1:
        return int(ints[0])
    # General fallback for level-specific rate_type=2 records: second-to-last integer is often level.
    if rate_type == 2 and len(ints) >= 2:
        lev = int(ints[-2])
        if lev > 0:
            return lev
    return None


def evaluate_alpha(data_type: int, reals: List[float], ints: List[int], temperature_K: float, include_charge_exchange: bool = False) -> Tuple[Optional[float], str]:
    """Return rate coefficient cm3/s and evaluation method for recombination / charge exchange types."""
    T4 = float(temperature_K) / 1.0e4
    if T4 <= 0.0:
        return None, "invalid_temperature"
    try:
        if data_type == 2:
            # Charge exchange with neutral H, Kingdon & Ferland.
            # ucalc type 2: rate = a * t**b * max(0, 1 + c*exp(d*t)) * 1e-9, t=T/1e4; zero for t>5.
            # This is a charge-exchange coefficient to be multiplied by n_H0, not n_e.
            if not include_charge_exchange:
                return None, "type2_charge_exchange_H0_not_evaluated_without_flag"
            if len(reals) < 4:
                return None, "type2_charge_exchange_H0_missing_coefficients"
            if T4 > 5.0:
                return 0.0, "type2_charge_exchange_H0_above_T4_range"
            aax, bbx, ccx, ddx = map(float, reals[:4])
            rate = aax * (T4 ** bbx) * max(0.0, 1.0 + ccx * math.exp(ddx * T4)) * 1.0e-9
            return max(rate, 0.0), "type2_charge_exchange_H0_kingdon_ferland"

        if data_type == 1:
            # RR A&P: arad / t**eta
            if len(reals) < 2:
                return None, "type1_missing_coefficients"
            A, eta = float(reals[0]), float(reals[1])
            return A / (T4 ** eta), "type1_rr_ap"

        if data_type == 7:
            # DR A&P
            if len(reals) < 4:
                return None, "type7_missing_coefficients"
            adi, bdi, t0, t1 = map(float, reals[:4])
            alpha = adi * 1.0e-6 * math.exp(-t0 / T4) * (1.0 + bdi * math.exp(-t1 / T4)) / (T4 * math.sqrt(T4))
            return max(alpha, 0.0), "type7_dr_ap"

        if data_type == 8:
            # Arnaud & Raymond: first four C, next four E(eV); alpha = 1e-6 T4^-3/2 sum C exp(-E/kT)
            if len(reals) < 8:
                return None, "type8_missing_coefficients"
            ekt = K_B_EV_PER_1E4K * T4
            s = 0.0
            for c, e in zip(reals[:4], reals[4:8]):
                s += float(c) * math.exp(-float(e) / ekt)
            return max(1.0e-6 * T4 ** (-1.5) * s, 0.0), "type8_dr_arnaud_raymond"

        if data_type == 22:
            # Storey DR; XSTAR skips above T4=6.
            if len(reals) < 5:
                return None, "type22_missing_coefficients"
            if T4 > 6.0:
                return 0.0, "type22_storey_outside_T4_range"
            a, b, c, d, e = map(float, reals[:5])
            alpha = 1.0e-12 * (a / T4 + b + T4 * (c + T4 * d)) * T4 ** (-1.5) * math.exp(-e / T4)
            return max(alpha, 0.0), "type22_dr_storey"

        if data_type == 30:
            # Hydrogenic RR; idat[0] = effective charge nmx in ucalc.
            if len(ints) < 1:
                return None, "type30_missing_effective_charge"
            zeff = float(ints[0])
            if zeff <= 0.0:
                return None, "type30_bad_effective_charge"
            beta = zeff * zeff / (6.34 * T4)
            yy = beta
            vth = 3.10782e7 * math.sqrt(T4)
            ypow = min(1.0, 0.06376 / (yy * yy)) if yy != 0 else 1.0
            fudge = 0.9 * (1.0 - ypow) + (1.0 / 1.5) * ypow
            phi1 = (1.735 + math.log(yy) + 1.0 / (6.0 * yy)) * fudge / 2.0
            phi2 = yy * (-1.202 * math.log(yy) - 0.298)
            phi = phi2 if yy < 0.2525 else phi1
            alpha = 2.0 * 2.105e-22 * vth * yy * phi
            return max(alpha, 0.0), "type30_rr_hydrogenic_gould_thakur"

        if data_type == 37:
            # Fe 3pq Badnell-like DR: nterm in idat[0], first n terms C, next n terms E(eV).
            if len(ints) < 1:
                return None, "type37_missing_nterm"
            nterm = int(ints[0])
            if len(reals) < 2 * nterm:
                return None, "type37_missing_coefficients"
            ekt = K_B_EV_PER_1E4K * T4
            s = 0.0
            for n in range(nterm):
                s += float(reals[n]) * math.exp(-float(reals[n + nterm]) / ekt)
            return max(1.0e-6 * T4 ** (-1.5) * s, 0.0), "type37_dr_badnell_fe3pq"

        if data_type == 38:
            # Badnell total RR.
            if len(reals) < 4:
                return None, "type38_missing_coefficients"
            a = float(reals[0])
            b = float(reals[1])
            t0 = float(reals[2]) / 1.0e4
            t1 = float(reals[3]) / 1.0e4
            if len(reals) > 4:
                c = float(reals[4])
                t2 = float(reals[5]) / 1.0e4 if len(reals) > 5 else 0.0
                b = b + c * math.exp(-t2 / T4) if T4 > 0 else b
            if t0 <= 0 or t1 <= 0:
                return None, "type38_bad_temperature_coefficients"
            term1 = (T4 / t0) ** 0.5
            term2 = (1.0 + (T4 / t0) ** 0.5) ** (1.0 - b)
            term3 = (1.0 + (T4 / t1) ** 0.5) ** (1.0 + b)
            alpha = a / (term1 * term2 * term3 + 1.0e-48)
            return max(alpha, 0.0), "type38_rr_badnell"

        if data_type == 39:
            # Badnell total DR: first half C, second half T_i(K) / 1e4 in ucalc.
            if len(reals) < 2:
                return None, "type39_missing_coefficients"
            nterm = len(reals) // 2
            if nterm <= 0:
                return None, "type39_bad_nterm"
            s = 0.0
            for n in range(nterm):
                dc = float(reals[n])
                dt4 = float(reals[n + nterm]) / 1.0e4
                s += dc * math.exp(-dt4 / T4)
            alpha = 1.0e-6 * T4 ** (-1.5) * s
            return max(alpha, 0.0), "type39_dr_badnell"

    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        return None, f"evaluation_error:{exc.__class__.__name__}"

    return None, "not_evaluated_inventory_only"



def source_kind_for_data_type(data_type: int) -> str:
    if data_type in ELECTRON_RECOMB_DATA_TYPES:
        return "electron_recombination"
    if data_type in CHARGE_EXCHANGE_H0_DATA_TYPES:
        return "charge_exchange_H0"
    return "recombination_like_inventory_only"


def level_resolved_status_for_data_type(data_type: int) -> str:
    if data_type in ELECTRON_RECOMB_DATA_TYPES:
        return "total_rate_assigned_to_ground"
    if data_type in CHARGE_EXCHANGE_H0_DATA_TYPES:
        return "charge_exchange_total_not_level_resolved"
    return "possibly_level_resolved_or_inventory_only"


def parent_ion_stage(z: Optional[int], ion_stage: Optional[int], data_type: int) -> Optional[int]:
    if ion_stage is None:
        return None
    # Recombination-like records in an ion block are interpreted as feeding this target ion
    # from the next higher ionization stage. For H-like target, the parent is bare nucleus Z+1.
    if data_type in ELECTRON_RECOMB_DATA_TYPES or data_type in CHARGE_EXCHANGE_H0_DATA_TYPES:
        return int(ion_stage) + 1
    return None


def parent_ion_label(symbol: str, z: Optional[int], ion_stage: Optional[int], data_type: int) -> str:
    ps = parent_ion_stage(z, ion_stage, data_type)
    if ps is None:
        return ""
    if z is not None and ps == int(z) + 1:
        return f"{symbol} {roman(ps)} (bare nucleus)"
    return f"{symbol} {roman(ps)}"

def extract_recombination_records(db: ATDB, records: List[IndexedRecord], z: Optional[int], ion_stage: Optional[int]) -> List[dict]:
    # Level indices are local to each ion. Cache maps by ion stage to avoid mislabeling
    # all-ion inventories where many ions have level_index=1.
    level_cache: Dict[Tuple[Optional[int], Optional[int]], Tuple[dict, dict, dict, dict]] = {}

    def maps_for(zz: Optional[int], istage: Optional[int]):
        key = (zz, istage)
        if key not in level_cache:
            levs = extract_levels(db, records, zz, istage)
            level_cache[key] = level_maps(levs)
        return level_cache[key]

    rows: List[dict] = []
    for r in records:
        if not row_match(r, z, ion_stage):
            continue
        if not is_recombination_like(r):
            continue
        h = db.header(r.recno)
        rd = db.real_slice(h)
        it = db.int_slice(h)
        ch = db.char_slice(h)
        dest_level = infer_destination_level(r.data_type, r.rate_type, it)
        _by_level, labels, _energies, gs = maps_for(r.element_z, r.ion_stage)
        rows.append({
            "record": r.recno,
            "element_z": r.element_z,
            "element": r.element_symbol,
            "ion_stage": r.ion_stage,
            "ion_roman": roman(r.ion_stage),
            "ion": r.ion_label,
            "charge": r.charge_label,
            "data_type": r.data_type,
            "data_type_label": DATA_TYPES.get(r.data_type, r.data_type_label),
            "rate_type": r.rate_type,
            "rate_type_label": RATE_TYPES.get(r.rate_type, r.rate_type_label),
            "destination_level": dest_level,
            "destination_label": labels.get(dest_level, "") if dest_level is not None else "",
            "destination_g": gs.get(dest_level) if dest_level is not None else None,
            "source_kind": source_kind_for_data_type(r.data_type),
            "parent_ion_stage": parent_ion_stage(r.element_z, r.ion_stage, r.data_type),
            "parent_ion": parent_ion_label(r.element_symbol, r.element_z, r.ion_stage, r.data_type),
            "target_ion_stage": r.ion_stage,
            "target_ion": r.ion_label,
            "level_resolved_status": level_resolved_status_for_data_type(r.data_type),
            "nreal": r.nreal,
            "nint": r.nint,
            "nchar": r.nchar,
            "char_label": ch,
            "raw_reals": preview_list(rd),
            "raw_ints": preview_list(it),
        })
    rows.sort(key=lambda row: (row.get("data_type") or 0, row.get("rate_type") or 0, row.get("record") or 0))
    return rows


def evaluate_records(db: ATDB, recomb_rows: List[dict], temperatures: Sequence[float], include_charge_exchange: bool = False) -> List[dict]:
    rows: List[dict] = []
    for rec in recomb_rows:
        h = db.header(int(rec["record"]))
        rd = db.real_slice(h)
        it = db.int_slice(h)
        for T in temperatures:
            alpha, method = evaluate_alpha(int(rec["data_type"]), rd, it, float(T), include_charge_exchange=include_charge_exchange)
            out = dict(rec)
            out.update({
                "temperature_K": float(T),
                "alpha_cm3_s": alpha,
                "eval_method": method,
                "evaluated": alpha is not None,
            })
            rows.append(out)
    return rows


def allocation_levels(
    mode: str,
    selected_levels: List[int],
    level_rows: List[dict],
    rec: dict,
    branches_by_upper: Optional[Dict[int, List[dict]]] = None,
    cascade_target_weights: Optional[Dict[int, float]] = None,
    cascade_weight_floor: float = 0.0,
) -> List[Tuple[int, float, str]]:
    """Return (level_index, weight, allocation_note), weights normalized later.

    ``selected-cascade-yield`` is a Stage-6 prototype allocation mode.  It
    weights each selected seed level by the probability that a purely radiative
    cascade from that seed visits user-selected target levels, optionally
    multiplied by the seed statistical weight.  This is still approximate
    because the decoded oxygen records are total recombination rates, not true
    level-resolved recombination rates.
    """
    levels_by_idx = {int(r["level_index"]): r for r in level_rows if r.get("level_index") is not None}
    dest = rec.get("destination_level")
    if mode == "none":
        return []
    if mode == "ground":
        lev = int(dest or 1)
        return [(lev, 1.0, "allocated_total_recombination_to_ground")]
    if mode == "record-destination":
        if dest is None:
            return []
        return [(int(dest), 1.0, "allocated_to_record_destination_level")]
    if mode == "selected-equal":
        return [(int(x), 1.0, "equal_allocation_to_selected_levels") for x in selected_levels if int(x) in levels_by_idx]
    if mode == "selected-statistical":
        out = []
        for x in selected_levels:
            lev = levels_by_idx.get(int(x))
            if lev:
                g = safe_float(lev.get("statistical_weight_g")) or 1.0
                out.append((int(x), g, "statistical_weight_allocation_to_selected_levels"))
        return out
    if mode == "selected-cascade-yield":
        out = []
        target_weights = cascade_target_weights or {}
        branches = branches_by_upper or {}
        for x in selected_levels:
            lev = levels_by_idx.get(int(x))
            if not lev:
                continue
            g = safe_float(lev.get("statistical_weight_g")) or 1.0
            score = 0.0
            if target_weights and branches:
                visits, _paths = cascade_probabilities_from_seed(int(x), branches, max_depth=50, min_probability=0.0)
                for target_level, target_weight in target_weights.items():
                    score += float(visits.get(int(target_level), 0.0)) * float(target_weight)
            # Keep a configurable floor so levels with no path to the current
            # diagnostic targets can still receive a controlled small source.
            weight = g * max(float(cascade_weight_floor), score)
            if weight > 0.0:
                out.append((int(x), weight, "cascade_yield_weighted_allocation_to_selected_levels"))
        if out:
            return out
        # Robust fallback if target levels are absent or no radiative paths are found.
        for x in selected_levels:
            lev = levels_by_idx.get(int(x))
            if lev:
                g = safe_float(lev.get("statistical_weight_g")) or 1.0
                out.append((int(x), g, "cascade_yield_fallback_statistical_weight_allocation"))
        return out
    if mode == "all-statistical":
        out = []
        for lev in level_rows:
            idx = lev.get("level_index")
            if idx is None:
                continue
            g = safe_float(lev.get("statistical_weight_g")) or 1.0
            out.append((int(idx), g, "statistical_weight_allocation_to_all_levels"))
        return out
    raise ValueError(f"Unknown source mode: {mode}")


def make_source_rows(
    eval_rows: List[dict],
    level_rows: List[dict],
    mode: str,
    selected_levels: List[int],
    electron_densities: Sequence[float],
    neutral_h_densities: Sequence[float],
    parent_population_scale: float,
    min_alpha: float,
    allow_charge_exchange_sources: bool = False,
    branches_by_upper: Optional[Dict[int, List[dict]]] = None,
    cascade_target_weights: Optional[Dict[int, float]] = None,
    cascade_weight_floor: float = 0.0,
) -> List[dict]:
    source_rows: List[dict] = []
    for rec in eval_rows:
        alpha = rec.get("alpha_cm3_s")
        if alpha is None:
            continue
        alpha = float(alpha)
        if alpha < min_alpha:
            continue
        alloc = allocation_levels(
            mode,
            selected_levels,
            level_rows,
            rec,
            branches_by_upper=branches_by_upper,
            cascade_target_weights=cascade_target_weights,
            cascade_weight_floor=cascade_weight_floor,
        )
        if not alloc:
            continue
        wsum = sum(max(0.0, float(w)) for _lev, w, _note in alloc)
        if wsum <= 0.0:
            continue
        source_kind = rec.get("source_kind")
        if source_kind == "charge_exchange_H0":
            if not allow_charge_exchange_sources:
                continue
            density_values = neutral_h_densities
            density_kind = "neutral_H_density_cm^-3"
        else:
            density_values = electron_densities
            density_kind = "electron_density_cm^-3"
        for dens in density_values:
            for lev, w, note in alloc:
                frac = max(0.0, float(w)) / wsum
                src = alpha * float(dens) * float(parent_population_scale) * frac
                source_rows.append({
                    "level_index": lev,
                    "source_s^-1": src,
                    "sink_s^-1": 0.0,
                    "temperature_K": rec.get("temperature_K"),
                    "electron_density_cm^-3": float(dens) if density_kind == "electron_density_cm^-3" else None,
                    "neutral_H_density_cm^-3": float(dens) if density_kind == "neutral_H_density_cm^-3" else None,
                    "density_kind": density_kind,
                    "source_type": rec.get("eval_method"),
                    "allocation_mode": mode,
                    "allocation_note": note,
                    "allocation_fraction": frac,
                    "alpha_cm3_s_total_record": alpha,
                    "parent_population_scale": parent_population_scale,
                    "record": rec.get("record"),
                    "data_type": rec.get("data_type"),
                    "rate_type": rec.get("rate_type"),
                    "ion": rec.get("ion"),
                    "charge": rec.get("charge"),
                    "parent_ion": rec.get("parent_ion"),
                    "parent_ion_stage": rec.get("parent_ion_stage"),
                    "target_ion": rec.get("target_ion"),
                    "target_ion_stage": rec.get("target_ion_stage"),
                    "source_kind": source_kind,
                    "comment": "prototype source term: multiply by physical parent-ion fraction in production",
                })
    source_rows.sort(key=lambda r: (float(r.get("temperature_K") or 0), float(r.get("electron_density_cm^-3") or r.get("neutral_H_density_cm^-3") or 0), int(r.get("level_index") or 0), int(r.get("record") or 0)))
    return source_rows




def build_radiative_branching(lines: List[dict]) -> Tuple[Dict[int, List[dict]], Dict[int, float]]:
    """Build radiative branching data keyed by upper level.

    Returns
    -------
    branches_by_upper:
        upper_level -> list of dicts with lower_level, A_s^-1, branching_ratio, record, wavelength_A
    total_A_by_upper:
        upper_level -> sum(A_s^-1) over decoded radiative decays.

    Only records with a positive A_s^-1 and a strict upper->lower energy ordering are used.
    """
    total_A: Dict[int, float] = defaultdict(float)
    tmp: Dict[int, List[dict]] = defaultdict(list)
    for line in lines:
        up = line.get("upper_level")
        lo = line.get("lower_level")
        A = safe_float(line.get("A_s^-1"))
        if up is None or lo is None or A is None or A <= 0.0:
            continue
        up = int(up); lo = int(lo)
        if up == lo:
            continue
        total_A[up] += A
        tmp[up].append({
            "upper_level": up,
            "lower_level": lo,
            "A_s^-1": A,
            "line_record": line.get("record"),
            "wavelength_A": line.get("wavelength_A"),
            "line_label": line.get("char_label", ""),
            "lower_label": line.get("lower_label", ""),
            "upper_label": line.get("upper_label", ""),
        })
    branches: Dict[int, List[dict]] = defaultdict(list)
    for up, arr in tmp.items():
        denom = total_A.get(up, 0.0)
        for item in arr:
            item = dict(item)
            item["branching_ratio"] = item["A_s^-1"] / denom if denom > 0.0 else 0.0
            branches[up].append(item)
    return dict(branches), dict(total_A)


def cascade_probabilities_from_seed(
    seed_level: int,
    branches_by_upper: Dict[int, List[dict]],
    max_depth: int = 50,
    min_probability: float = 0.0,
) -> Tuple[Dict[int, float], List[dict]]:
    """Propagate a unit radiative cascade from one seed level.

    This follows only spontaneous radiative branching. It is a structural cascade
    approximation, not a full recombination cascade calculation. The returned
    probabilities are the accumulated probabilities that population visits a
    descendant level after one or more radiative decays. The seed itself is also
    recorded with probability 1 in the visit map.
    """
    visits: Dict[int, float] = defaultdict(float)
    rows: List[dict] = []
    stack: List[Tuple[int, float, int, str]] = [(int(seed_level), 1.0, 0, str(seed_level))]
    while stack:
        level, prob, depth, path = stack.pop()
        if prob < min_probability:
            continue
        visits[level] += prob
        if depth >= max_depth:
            rows.append({
                "seed_level": seed_level,
                "cascade_level": level,
                "cascade_probability": prob,
                "cascade_depth": depth,
                "cascade_path": path,
                "cascade_status": "max_depth_reached",
            })
            continue
        outs = branches_by_upper.get(level, [])
        if not outs:
            rows.append({
                "seed_level": seed_level,
                "cascade_level": level,
                "cascade_probability": prob,
                "cascade_depth": depth,
                "cascade_path": path,
                "cascade_status": "terminal_no_radiative_decay",
            })
            continue
        for br in outs:
            lo = int(br["lower_level"])
            p = prob * float(br.get("branching_ratio") or 0.0)
            if p < min_probability:
                continue
            rows.append({
                "seed_level": seed_level,
                "from_level": level,
                "to_level": lo,
                "cascade_level": lo,
                "cascade_probability": p,
                "branching_ratio": br.get("branching_ratio"),
                "A_s^-1": br.get("A_s^-1"),
                "line_record": br.get("line_record"),
                "wavelength_A": br.get("wavelength_A"),
                "cascade_depth": depth + 1,
                "cascade_path": path + f"->{lo}",
                "cascade_status": "radiative_branch",
            })
            if lo != level:
                stack.append((lo, p, depth + 1, path + f"->{lo}"))
    return dict(visits), rows


def make_cascade_rows(
    source_rows: List[dict],
    branches_by_upper: Dict[int, List[dict]],
    max_depth: int = 50,
    min_probability: float = 0.0,
) -> Tuple[List[dict], List[dict]]:
    """Convert initial source rows into cascade-redistributed source rows.

    The returned cascade_source_rows are intended as an approximation for sensitivity
    tests. They should not be combined with the original source rows in the same
    solver run unless the user explicitly wants double-counted cascade feeding.
    """
    out: List[dict] = []
    path_rows: List[dict] = []
    cache: Dict[int, Tuple[Dict[int, float], List[dict]]] = {}
    for row in source_rows:
        seed = int(row.get("level_index"))
        if seed not in cache:
            cache[seed] = cascade_probabilities_from_seed(seed, branches_by_upper, max_depth=max_depth, min_probability=min_probability)
        visits, paths = cache[seed]
        for pr in paths:
            ptmp = dict(pr)
            ptmp.update({
                "source_record": row.get("record"),
                "source_type": row.get("source_type"),
                "source_kind": row.get("source_kind"),
                "temperature_K": row.get("temperature_K"),
                "electron_density_cm^-3": row.get("electron_density_cm^-3"),
                "neutral_H_density_cm^-3": row.get("neutral_H_density_cm^-3"),
                "initial_source_s^-1": row.get("source_s^-1"),
            })
            path_rows.append(ptmp)
        for lev, prob in visits.items():
            if prob <= 0.0 or prob < min_probability:
                continue
            new = dict(row)
            new["level_index"] = int(lev)
            new["source_s^-1"] = float(row.get("source_s^-1") or 0.0) * prob
            new["allocation_mode"] = "cascade-redistributed"
            new["allocation_note"] = "radiative_branching_cascade_from_initial_source_level"
            new["cascade_seed_level"] = seed
            new["cascade_probability"] = prob
            new["comment"] = "approximate cascade-redistributed source term; not a true level-resolved recombination calculation"
            out.append(new)
    # Combine identical solver keys to keep source CSV compact.
    combined: Dict[Tuple, dict] = {}
    for r in out:
        key = (
            r.get("level_index"), r.get("temperature_K"), r.get("electron_density_cm^-3"),
            r.get("neutral_H_density_cm^-3"), r.get("density_kind"), r.get("source_kind"),
            r.get("source_type"), r.get("record"), r.get("cascade_seed_level"),
        )
        if key not in combined:
            combined[key] = dict(r)
        else:
            combined[key]["source_s^-1"] = float(combined[key].get("source_s^-1") or 0.0) + float(r.get("source_s^-1") or 0.0)
    compact = list(combined.values())
    compact.sort(key=lambda r: (float(r.get("temperature_K") or 0), int(r.get("cascade_seed_level") or 0), int(r.get("level_index") or 0)))
    return compact, path_rows


def classify_recombination_records(rows: List[dict]) -> List[dict]:
    """Add explicit total-vs-level-resolved classification fields."""
    out: List[dict] = []
    for r in rows:
        rec = dict(r)
        dt = int(rec.get("data_type") or -1)
        sk = rec.get("source_kind")
        if sk == "charge_exchange_H0":
            cls = "charge_exchange_total"
            action = "exclude_from_electron_recombination_sources_unless_requested"
        elif dt in ELECTRON_RECOMB_DATA_TYPES:
            cls = "electron_recombination_total_rate"
            action = "needs_level_distribution_or_cascade_model"
        else:
            cls = "unknown_recombination_like_inventory"
            action = "inspect_source_code_before_use"
        # Current decoded XSTAR Atomic records here are total rates, not true level-resolved cascades.
        rec["recombination_record_class"] = cls
        rec["recommended_source_action"] = action
        rec["is_true_level_resolved_recombination"] = False
        out.append(rec)
    return out

def build_summary(records: List[dict], eval_rows: List[dict], source_rows: List[dict], args, z: Optional[int]) -> dict:
    return {
        "fitsfile": args.fitsfile,
        "element": args.element,
        "z": z,
        "ion_stage": args.ion_stage,
        "temperatures_K": args.temperatures,
        "electron_densities_cm^-3": args.electron_densities,
        "neutral_H_densities_cm^-3": args.neutral_h_densities,
        "include_charge_exchange": args.include_charge_exchange,
        "allow_charge_exchange_sources": args.allow_charge_exchange_sources,
        "n_recombination_like_records": len(records),
        "n_eval_rows": len(eval_rows),
        "n_evaluated_rows": sum(1 for r in eval_rows if r.get("alpha_cm3_s") is not None),
        "n_source_rows": len(source_rows),
        "counts_by_data_type": dict(Counter(str(r.get("data_type")) for r in records)),
        "counts_by_rate_type": dict(Counter(str(r.get("rate_type")) for r in records)),
        "counts_by_source_kind": dict(Counter(str(r.get("source_kind")) for r in records)),
        "counts_by_parent_ion": dict(Counter(str(r.get("parent_ion")) for r in records)),
        "eval_counts_by_method": dict(Counter(str(r.get("eval_method")) for r in eval_rows)),
        "eval_counts_by_source_kind": dict(Counter(str(r.get("source_kind")) for r in eval_rows if r.get("alpha_cm3_s") is not None)),
        "source_counts_by_mode": dict(Counter(str(r.get("allocation_mode")) for r in source_rows)),
        "source_sum_s^-1_by_T_ne": {
            f"T={k[0]:g},ne={k[1]:g}": v
            for k, v in _sum_sources_by_T_ne(source_rows).items()
        },
        "source_mode": args.source_mode,
        "source_levels": parse_level_list(args.source_levels),
        "parent_population_scale": args.parent_population_scale,
        "notes": [
            "This is a third-pass recombination / charge-exchange / cascade-source extractor.",
            "Electron RR/DR and charge exchange are separated by source_kind.",
            "Total recombination records are not true level-resolved cascade feeds unless source_mode says so.",
            "Charge-exchange type 2 rates require neutral-H density and are not electron recombination.",
            "Use source CSV outputs as prototype inputs to the level-population solver, not final physical recombination cascades.",
        ],
    }


def _sum_sources_by_T_ne(rows: List[dict]) -> Dict[Tuple[float, float], float]:
    out: Dict[Tuple[float, float], float] = defaultdict(float)
    for r in rows:
        key = (float(r.get("temperature_K") or 0.0), float(r.get("electron_density_cm^-3") or r.get("neutral_H_density_cm^-3") or 0.0))
        out[key] += float(r.get("source_s^-1") or 0.0)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Extract and evaluate recombination-like records from XSTAR atdb.fits.")
    p.add_argument("fitsfile")
    p.add_argument("--element", required=True, help="Element symbol or Z, e.g. O or 8")
    p.add_argument("--ion-stage", type=int, default=None, help="Optional ion stage, e.g. 7 for O VII. If omitted, inventory all ions of the element.")
    p.add_argument("--temperatures", nargs="+", type=float, default=[1.0e6], help="Temperatures in K")
    p.add_argument("--electron-densities", nargs="+", type=float, default=[1.0], help="Electron densities in cm^-3 for electron recombination source CSV")
    p.add_argument("--neutral-h-densities", nargs="+", type=float, default=[1.0], help="Neutral hydrogen densities in cm^-3 for charge-exchange source CSV")
    p.add_argument("--include-charge-exchange", action="store_true", help="Evaluate type-2 charge-exchange H0 records; otherwise inventory them only")
    p.add_argument("--allow-charge-exchange-sources", action="store_true", help="Allow charge-exchange records to create source CSV rows using neutral-H density")
    p.add_argument("--parent-population-scale", type=float, default=1.0, help="Multiplier for parent ion population/fraction in source_s^-1")
    p.add_argument("--min-alpha", type=float, default=0.0, help="Minimum alpha_cm3_s to include in source CSV")
    p.add_argument("--source-mode", choices=["none", "ground", "record-destination", "selected-equal", "selected-statistical", "selected-cascade-yield", "all-statistical"], default="none")
    p.add_argument("--source-levels", default="", help="Comma-separated levels for selected-* source modes")
    p.add_argument("--cascade-target-levels", default="", help="Comma-separated target levels, or level:weight pairs, used by selected-cascade-yield source allocation")
    p.add_argument("--cascade-target-preset", default="", choices=["", "none"] + sorted(CASCADE_TARGET_PRESETS), help="Named cascade target weighting preset; manual --cascade-target-levels overrides this")
    p.add_argument("--cascade-weight-floor", type=float, default=0.0, help="Minimum cascade-yield score used by selected-cascade-yield allocation")
    p.add_argument("--records-csv")
    p.add_argument("--eval-csv")
    p.add_argument("--source-csv")
    p.add_argument("--cascade-source-csv", help="Optional solver-source CSV after approximate radiative cascade redistribution from initial source rows")
    p.add_argument("--cascade-path-csv", help="Optional detailed cascade path/probability CSV")
    p.add_argument("--cascade-mode", choices=["none", "radiative-branching"], default="none", help="Create approximate cascade-redistributed source rows from initial source rows")
    p.add_argument("--cascade-max-depth", type=int, default=50)
    p.add_argument("--cascade-min-probability", type=float, default=0.0)
    p.add_argument("--summary-json")
    p.add_argument("--summary", action="store_true", help="Print JSON summary")
    p.add_argument("--print-records", action="store_true", help="Print record rows as JSON")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    z = choose_z(args.element)
    selected_levels = parse_level_list(args.source_levels)

    if args.ion_stage is None and args.source_mode != "none":
        p.error("--ion-stage is required when --source-mode is not none, because solver source CSV level indices are ion-local")

    with ATDB(args.fitsfile, load_reals=True) as db:
        records, _elements, _ions = db.build_index()
        level_rows = extract_levels(db, records, z, args.ion_stage)
        recomb_records = classify_recombination_records(extract_recombination_records(db, records, z, args.ion_stage))
        if args.limit is not None:
            print_records = recomb_records[:args.limit]
        else:
            print_records = recomb_records
        eval_rows = evaluate_records(db, recomb_records, args.temperatures, include_charge_exchange=args.include_charge_exchange)
        line_rows_for_cascade: List[dict] = []
        branches_by_upper_for_source: Optional[Dict[int, List[dict]]] = None
        cascade_target_levels_text = resolve_cascade_target_levels(args.cascade_target_levels, args.cascade_target_preset)
        cascade_target_weights = parse_level_weight_map(cascade_target_levels_text)
        if args.source_mode == "selected-cascade-yield" or args.cascade_mode == "radiative-branching":
            line_rows_for_cascade = extract_lines(db, records, z, args.ion_stage)
        if args.source_mode == "selected-cascade-yield":
            branches_by_upper_for_source, _total_A_for_source = build_radiative_branching(line_rows_for_cascade)
        source_rows = make_source_rows(
            eval_rows,
            level_rows,
            args.source_mode,
            selected_levels,
            args.electron_densities,
            args.neutral_h_densities,
            args.parent_population_scale,
            args.min_alpha,
            allow_charge_exchange_sources=args.allow_charge_exchange_sources,
            branches_by_upper=branches_by_upper_for_source,
            cascade_target_weights=cascade_target_weights,
            cascade_weight_floor=args.cascade_weight_floor,
        )
        cascade_source_rows: List[dict] = []
        cascade_path_rows: List[dict] = []
        if args.cascade_mode == "radiative-branching" and source_rows:
            branches_by_upper, _total_A_by_upper = build_radiative_branching(line_rows_for_cascade)
            cascade_source_rows, cascade_path_rows = make_cascade_rows(
                source_rows,
                branches_by_upper,
                max_depth=args.cascade_max_depth,
                min_probability=args.cascade_min_probability,
            )

    record_fields = [
        "record", "element", "ion", "charge", "parent_ion", "parent_ion_stage", "target_ion", "target_ion_stage",
        "data_type", "data_type_label", "rate_type", "rate_type_label",
        "destination_level", "destination_label", "source_kind", "level_resolved_status", "nreal", "nint", "nchar",
        "char_label", "raw_reals", "raw_ints", "recombination_record_class", "recommended_source_action", "is_true_level_resolved_recombination",
    ]
    eval_fields = record_fields + ["temperature_K", "alpha_cm3_s", "eval_method", "evaluated"]
    source_fields = [
        "level_index", "source_s^-1", "sink_s^-1", "temperature_K", "electron_density_cm^-3", "neutral_H_density_cm^-3", "density_kind",
        "source_type", "allocation_mode", "allocation_note", "allocation_fraction",
        "alpha_cm3_s_total_record", "parent_population_scale", "record", "data_type", "rate_type", "ion", "charge",
        "parent_ion", "parent_ion_stage", "target_ion", "target_ion_stage", "source_kind", "comment",
    ]

    if args.records_csv:
        write_csv(args.records_csv, recomb_records, record_fields)
    if args.eval_csv:
        write_csv(args.eval_csv, eval_rows, eval_fields)
    if args.source_csv:
        write_csv(args.source_csv, source_rows, source_fields)
    if args.cascade_source_csv:
        write_csv(args.cascade_source_csv, cascade_source_rows, source_fields + ["cascade_seed_level", "cascade_probability"])
    if args.cascade_path_csv:
        write_csv(args.cascade_path_csv, cascade_path_rows)

    summary = build_summary(recomb_records, eval_rows, source_rows, args, z)
    summary.update({
        "cascade_mode": args.cascade_mode,
        "n_cascade_source_rows": len(cascade_source_rows),
        "n_cascade_path_rows": len(cascade_path_rows),
        "cascade_max_depth": args.cascade_max_depth,
        "cascade_min_probability": args.cascade_min_probability,
        "counts_by_recombination_record_class": dict(Counter(str(r.get("recombination_record_class")) for r in recomb_records)),
        "n_true_level_resolved_recombination_records_found": sum(1 for r in recomb_records if r.get("is_true_level_resolved_recombination")),
        "cascade_warning": "radiative-branching cascade redistribution is an approximation; do not combine original and cascade sources unless intentionally testing double-counting",
    })
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.summary or args.print_records or not (args.records_csv or args.eval_csv or args.source_csv or args.summary_json):
        print(json.dumps(summary, indent=2))
    if args.print_records:
        print(json.dumps({"records": print_records}, indent=2))


if __name__ == "__main__":
    main()
