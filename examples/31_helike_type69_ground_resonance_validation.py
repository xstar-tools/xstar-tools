#!/usr/bin/env python3
"""Audit He-like type-69 ground-resonance candidates and track validation status.

The O VII high-density benchmark showed that suppressing the type-69
``ground -> resonance upper`` excitation channel fixes the density-grid R/G
mismatch at ``ne=1e12 cm^-3``.  This example generalizes the first part of that
workflow to other He-like ions by auditing the ATDB type-69 records that look
like ground-to-resonance candidates.

Important: this script does not claim that ``suppress-resonance`` is validated
for an ion unless density-specific XSTAR triplet references are supplied.  With
only ``atdb.fits`` it reports candidate records and marks each non-O VII ion as
``pending_xstar_density_grid``.  For O VII, the package ships compact converted
XSTAR density-grid references under ``xstar_test_run/o7_ne*/`` and the v0.2.81--
v0.2.84 comparison snapshots establish the validated behavior.

Outputs
-------

``helike_type69_ground_resonance_candidates.csv``
    One row per candidate type-69 ground-to-resonance transition.

``helike_type69_ground_resonance_validation_summary.csv``
    One row per ion with candidate counts and validation status.

``helike_type69_ground_resonance_validation_summary.json``
    Machine-readable summary for documentation and follow-up runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_IONS = "C V,N VI,O VII,Ne IX,Mg XI,Si XIII,S XV,Ar XVII,Ca XIX,Fe XXV"
HELIKE_ROMAN_BY_Z = {
    6: "V",
    7: "VI",
    8: "VII",
    10: "IX",
    12: "XI",
    14: "XIII",
    16: "XV",
    18: "XVII",
    20: "XIX",
    26: "XXV",
}
SYMBOL_NAME = {
    "C": "Carbon",
    "N": "Nitrogen",
    "O": "Oxygen",
    "Ne": "Neon",
    "Mg": "Magnesium",
    "Si": "Silicon",
    "S": "Sulfur",
    "Ar": "Argon",
    "Ca": "Calcium",
    "Fe": "Iron",
}


def roman_to_int(text: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    prev = 0
    for ch in reversed(str(text).upper()):
        value = values.get(ch)
        if value is None:
            raise ValueError(f"invalid Roman ion stage {text!r}")
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def parse_ion_spec(text: str) -> Tuple[str, int]:
    """Parse 'O VII', 'O:7', or 'O7' into (symbol, ion_stage)."""
    raw = str(text).strip()
    if not raw:
        raise ValueError("empty ion specification")
    if ":" in raw:
        sym, stage = [part.strip() for part in raw.split(":", 1)]
        return normalize_symbol(sym), int(float(stage))
    m = re.match(r"^([A-Z][a-z]?)[\s_\-]*([IVXLCDM]+|\d+)$", raw.strip(), flags=re.I)
    if not m:
        raise ValueError(f"invalid ion specification {text!r}; expected e.g. 'O VII' or 'O:7'")
    sym = normalize_symbol(m.group(1))
    stage_text = m.group(2)
    stage = int(float(stage_text)) if stage_text.isdigit() else roman_to_int(stage_text)
    return sym, stage


def normalize_symbol(text: str) -> str:
    t = str(text).strip()
    if not t:
        raise ValueError("empty element symbol")
    return t[0].upper() + t[1:].lower()


def parse_ion_list(text: str) -> List[Tuple[str, int]]:
    ions: List[Tuple[str, int]] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            ions.append(parse_ion_spec(part))
    return ions


def maybe_float(value) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def maybe_int(value) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def text_is_resonance_1p1(value: object) -> bool:
    text = str(value or "").replace(" ", "").lower()
    return ("1p" in text and "1p_1" in text) or "1s1.2p1.1p_1" in text or "1p1" in text


def density_from_dirname(path: Path) -> Optional[float]:
    name = path.name.lower()
    m = re.search(r"ne([0-9]+(?:e[+\-]?[0-9]+)?)", name)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def existing_density_reference_count(base: Path, prefix: str, filename: str = "xstar_triplet_lines.csv") -> int:
    """Count user-supplied density-specific XSTAR references for a generic ion.

    For O VII the historical filename is ``xstar_o7_triplet_lines.csv`` under
    ``xstar_test_run/o7_ne*/``; this helper handles that separately in
    validation_status_for_ion.
    """
    if not base.exists():
        return 0
    count = 0
    for sub in base.glob(f"{prefix}_ne*"):
        if (sub / filename).exists() or any(sub.glob("*triplet*lines*.csv")):
            count += 1
    return count


def validation_status_for_ion(symbol: str, stage: int, candidate_count: int, xstar_base: Path) -> Tuple[str, str, int]:
    """Return (status, note, n_density_references)."""
    ion_key = f"{symbol}{stage}"
    if symbol == "O" and stage == 7:
        n = 0
        for dirname in ["o7_ne1", "o7_ne1e4", "o7_ne1e8", "o7_ne1e10", "o7_ne1e12"]:
            if (xstar_base / dirname / "xstar_o7_triplet_lines.csv").exists():
                n += 1
        if n >= 5:
            return "validated_o7_density_grid", "O VII has packaged density-specific converted XSTAR references and validated include vs suppress-resonance comparison snapshots.", n
        return "pending_o7_references", "O VII candidate exists, but the packaged density-specific xstar_test_run/o7_ne*/ references are incomplete.", n
    prefix = f"{symbol.lower()}{stage}"
    n = existing_density_reference_count(xstar_base, prefix)
    if candidate_count <= 0:
        return "no_candidate_records", "No type-69 ground-resonance candidate was found in the decoded ATDB rows for this ion.", n
    if n >= 2:
        return "references_available_unvalidated", "Density-specific XSTAR references appear to exist; run an ion-specific density-grid comparison before marking this ion validated.", n
    return "pending_xstar_density_grid", "Candidate type-69 rows found, but no density-specific XSTAR triplet grid is packaged/supplied for this ion.", n


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not fields:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit_ion(fitsfile: str, symbol: str, stage: int, temperatures: Sequence[float], density: float, index_cache: bool, index_cache_path: Optional[str], index_cache_format: str) -> Tuple[List[dict], dict]:
    from xstar_atomic.hierarchy import ATDB, SYMBOL_TO_Z
    from xstar_atomic.lines import extract_levels, level_maps
    from xstar_atomic.collisions import extract_collisions
    from xstar_atomic.solver import is_type69_ground_resonance_excitation_row

    z = SYMBOL_TO_Z.get(symbol.upper())
    if z is None:
        raise ValueError(f"unknown element symbol {symbol!r}")
    ion_name = f"{symbol} {HELIKE_ROMAN_BY_Z.get(z, stage)}"
    rows: List[dict] = []
    n_type69 = 0
    with ATDB(fitsfile) as db:
        selected = db.select_records(z=z, ion_stage=stage, use_cache=bool(index_cache), cache_path=index_cache_path, cache_format=index_cache_format)
        level_rows = extract_levels(db, selected, z, stage)
        _by_level, labels, energies, _gs = level_maps(level_rows)
        _summary, _grid, eval_rows = extract_collisions(db, selected, z, stage, [float(t) for t in temperatures], electron_density_cm3=float(density))
    for row in eval_rows:
        if maybe_int(row.get("data_type")) != 69:
            continue
        n_type69 += 1
        lower = maybe_int(row.get("lower_level"))
        upper = maybe_int(row.get("upper_level"))
        is_ground = lower == 1
        is_res_label = text_is_resonance_1p1(row.get("upper_label"))
        is_candidate = bool(is_type69_ground_resonance_excitation_row(row))
        if not (is_candidate or (is_ground and is_res_label)):
            continue
        rows.append({
            "element": symbol,
            "z": z,
            "ion_stage": stage,
            "ion": ion_name,
            "record": row.get("record"),
            "data_type": row.get("data_type"),
            "lower_level": lower,
            "upper_level": upper,
            "lower_label": row.get("lower_label") or labels.get(lower, ""),
            "upper_label": row.get("upper_label") or labels.get(upper, ""),
            "lower_energy_eV": energies.get(lower) if lower is not None else None,
            "upper_energy_eV": energies.get(upper) if upper is not None else None,
            "wavelength_A": row.get("wavelength_A"),
            "temperature_K": row.get("temperature_K"),
            "density_cm^-3": float(density),
            "upsilon": row.get("upsilon"),
            "q_excitation_cm3_s": row.get("q_excitation_cm3_s"),
            "q_deexcitation_cm3_s": row.get("q_deexcitation_cm3_s"),
            "C_excitation_s^-1": (maybe_float(row.get("q_excitation_cm3_s")) or 0.0) * float(density),
            "C_deexcitation_s^-1": (maybe_float(row.get("q_deexcitation_cm3_s")) or 0.0) * float(density),
            "candidate_reason": "solver_suppress_resonance_match" if is_candidate else "label_ground_to_1P1",
        })
    summary = {
        "element": symbol,
        "z": z,
        "ion_stage": stage,
        "ion": ion_name,
        "n_type69_rows_evaluated": n_type69,
        "n_ground_resonance_candidates": len(rows),
        "candidate_records": ";".join(str(r.get("record")) for r in rows if r.get("record") not in (None, "")),
    }
    return rows, summary


def parse_float_list(text: str) -> List[float]:
    out = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(float(part))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--ions", default=DEFAULT_IONS, help="Comma-separated He-like ions, e.g. 'C V,N VI,O VII,Ne IX' or 'O:7,Ne:9'")
    parser.add_argument("--temperature-grid", default="1e6", help="Temperatures used when evaluating candidate collision rows")
    parser.add_argument("--density", type=float, default=1.0e12, help="Density used for C=n_e q diagnostic columns")
    parser.add_argument("--xstar-test-run-dir", default="xstar_test_run", help="Directory containing packaged or user-supplied density-specific XSTAR triplet CSVs")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--out-dir", default="helike_type69_ground_resonance_validation")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    ions = parse_ion_list(args.ions)
    temps = parse_float_list(args.temperature_grid)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xstar_base = Path(args.xstar_test_run_dir)

    candidate_rows: List[dict] = []
    summary_rows: List[dict] = []
    errors: List[dict] = []
    for symbol, stage in ions:
        try:
            rows, summary = audit_ion(args.fitsfile, symbol, stage, temps, float(args.density), bool(args.index_cache), args.index_cache_path, args.index_cache_format)
            status, note, n_refs = validation_status_for_ion(symbol, stage, len(rows), xstar_base)
            summary.update({
                "validation_status": status,
                "validation_note": note,
                "n_density_specific_xstar_references_found": n_refs,
            })
            candidate_rows.extend(rows)
            summary_rows.append(summary)
        except Exception as exc:
            errors.append({"element": symbol, "ion_stage": stage, "error": str(exc)})
            summary_rows.append({
                "element": symbol,
                "ion_stage": stage,
                "ion": f"{symbol} {stage}",
                "n_type69_rows_evaluated": 0,
                "n_ground_resonance_candidates": 0,
                "candidate_records": "",
                "validation_status": "audit_failed",
                "validation_note": str(exc),
                "n_density_specific_xstar_references_found": 0,
            })

    cand_csv = out_dir / "helike_type69_ground_resonance_candidates.csv"
    summ_csv = out_dir / "helike_type69_ground_resonance_validation_summary.csv"
    summ_json = out_dir / "helike_type69_ground_resonance_validation_summary.json"
    write_csv(cand_csv, candidate_rows)
    write_csv(summ_csv, summary_rows)
    payload = {
        "fitsfile": args.fitsfile,
        "ions_requested": [{"element": s, "ion_stage": st} for s, st in ions],
        "temperature_grid_K": temps,
        "density_cm^-3": float(args.density),
        "xstar_test_run_dir": str(xstar_base),
        "candidate_csv": str(cand_csv),
        "summary_csv": str(summ_csv),
        "errors": errors,
        "summary_rows": summary_rows,
        "interpretation": (
            "Only ions with density-specific XSTAR triplet grids can be marked validated. "
            "O VII is validated by the packaged density-grid benchmark; other He-like ions remain pending until converted XSTAR CSVs are supplied and compared."
        ),
    }
    summ_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    if args.print_summary:
        print("He-like type-69 ground-resonance validation audit")
        print("------------------------------------------------")
        print(f"ions: {', '.join(f'{s} {st}' for s, st in ions)}")
        print(f"wrote: {cand_csv}")
        print(f"wrote: {summ_csv}")
        print(f"wrote: {summ_json}")
        print("ion      candidates records        status")
        for row in summary_rows:
            print(f"{row.get('ion'):<8} {row.get('n_ground_resonance_candidates')!s:<10} {str(row.get('candidate_records') or '-'):<14} {row.get('validation_status')}")
        if errors:
            print("warnings/errors:")
            for err in errors:
                print(f"  {err.get('element')} {err.get('ion_stage')}: {err.get('error')}")
        print("Only O VII should be treated as validated unless additional density-specific XSTAR grids are supplied for other ions.")


if __name__ == "__main__":
    main()
