#!/usr/bin/env python3
"""Audit O VII type-69 collision records and their rate interpretation.

Version 0.2.74 showed that the high-density O VII triplet mismatch at
``ne=1e12 cm^-3`` is controlled primarily by one type-69 transition record,
especially record 22490 (level 1 -> 7).  This script does not fit source
weights.  Instead, it audits the raw XSTAR ATDB records and the decoded
``xstar_atomic`` rates so the problematic transition can be inspected directly.

For each selected type-69 record, it reports:

* raw ``idat`` and ``rdat`` fields from ``atdb.fits``;
* decoded lower/upper levels, labels, energies, statistical weights;
* Kato--Nakazaki ``calt69`` effective collision strength Upsilon;
* excitation/de-excitation rate coefficients and density-scaled rates;
* detailed-balance consistency checks;
* temperature dependence over a configurable grid;
* optional comparison with the previous transition-sensitivity scan summary.

The audit is diagnostic only.  It does not modify the atomic database or apply
any physical correction.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from xstar_tools.xstar.constants import (
    COLLISION_RATE_COEFFICIENT_PER_SQRT_K,
    SOURCE_COLLISION_BOLTZMANN_EV_PER_K,
)

KB_EV_PER_K = SOURCE_COLLISION_BOLTZMANN_EV_PER_K
QCOEF = COLLISION_RATE_COEFFICIENT_PER_SQRT_K



def xstar_expo(x: float) -> float:
    """XSTAR expo.f90 limiter used by the local audit fallback."""
    return math.exp(min(max(float(x), -60.0), 60.0))


def expint_scaled_py(x: float) -> float:
    """Return XSTAR expint.f90 em1 = x*exp(x)*E1(x)."""
    x = float(x)
    if x > 1.0:
        b1 = 9.5733223454
        b2 = 25.6329561486
        b3 = 21.0996530827
        b4 = 3.9584969228
        c1 = 8.5733287401
        c2 = 18.0590169730
        c3 = 8.6347608925
        c4 = 0.2677737343
        return (x**4 + c1*x**3 + c2*x*x + c3*x + c4) / (x**4 + b1*x**3 + b2*x*x + b3*x + b4)
    a0 = -0.57721566
    a1 = 0.99999193
    a2 = -0.24991055
    a3 = 0.05519968
    a4 = -0.00976004
    a5 = 0.00107857
    if x > 0.0:
        e1 = a0 + a1*x + a2*x*x + a3*x**3 + a4*x**4 + a5*x**5 - math.log(x)
    elif x < 0.0:
        e1 = -a0 + a1*x + a2*x*x + a3*x**3 + a4*x**4 + a5*x**5 - math.log(-x)
    else:
        return float("inf")
    return e1 * x * xstar_expo(x)


def calt69_upsilon(reals: Sequence[float], temperature_k: float) -> Optional[float]:
    """Local calt69 audit evaluator matching xstar_atomic.collisions."""
    if temperature_k <= 0 or len(reals) < 6:
        return None
    try:
        eboltz = 1.160443e4
        dele = float(reals[0])
        if dele <= 0:
            return None
        y = dele / float(temperature_k) * eboltz
        if y < 1.0e-20:
            return None
        if y > 1.0e20:
            return 0.0
        y = min(max(y, 5.0e-2), 77.0)
        em1 = expint_scaled_py(y)
        a, b, c, d, e = [float(v) for v in reals[1:6]]
        m = len(reals)
        if m == 6:
            gamma = y * ((a / y + c) + d * 0.5 * (1.0 - y))
            gamma += em1 * (b - c * y + d * y * y * 0.5 + e / y)
        else:
            if len(reals) < 9:
                return None
            pcoef = float(reals[6])
            qcoef = float(reals[7])
            x1 = float(reals[8])
            if x1 <= 0.0 or y <= 0.0:
                return None
            em1x = expint_scaled_py(y * x1)
            gnr = a / y + c / x1 + d * 0.5 * (1.0 / (x1*x1) - y / x1) + e / y * math.log(x1)
            gnr += em1x / y / x1 * (b - c*y + d*y*y*0.5 + e/y)
            gnr = gnr * y * xstar_expo(y * (1.0 - x1))
            gamma = gnr + pcoef * xstar_expo(-qcoef * y)
        if not math.isfinite(gamma):
            return None
        return max(0.0, float(gamma))
    except Exception:
        return None


def q_rates_from_upsilon(upsilon: Optional[float], delta_e_ev: Optional[float], g_lower: Optional[float], g_upper: Optional[float], temperature_k: float) -> Tuple[Optional[float], Optional[float]]:
    if upsilon is None or delta_e_ev is None or g_lower in (None, 0, 0.0) or g_upper in (None, 0, 0.0) or temperature_k <= 0:
        return None, None
    kT = KB_EV_PER_K * temperature_k
    if kT <= 0:
        return None, None
    rootT = math.sqrt(temperature_k)
    u = max(0.0, float(upsilon))
    q_exc = QCOEF * u * math.exp(-float(delta_e_ev) / kT) / (float(g_lower) * rootT)
    q_deexc = QCOEF * u / (float(g_upper) * rootT)
    return q_exc, q_deexc


def physical_order(level_a: Optional[int], level_b: Optional[int], energies: Dict[int, float]) -> Tuple[Optional[int], Optional[int]]:
    if level_a is None or level_b is None:
        return level_a, level_b
    ea = energies.get(int(level_a))
    eb = energies.get(int(level_b))
    if ea is None or eb is None:
        return level_a, level_b
    return (int(level_a), int(level_b)) if ea <= eb else (int(level_b), int(level_a))


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


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


def parse_int_list(text: str) -> List[int]:
    out: List[int] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(int(float(part)))
    return out


def parse_float_list(text: str) -> List[float]:
    out: List[float] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(float(part))
    return out


def preview_json(values: Sequence, max_n: int = 32) -> str:
    vals = list(values or [])
    if len(vals) > max_n:
        vals = vals[:max_n] + [f"... {len(values)-max_n} more"]
    return json.dumps(vals, separators=(",", ":"))


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


def find_transition_scan_rows(path: Optional[str]) -> Dict[int, List[dict]]:
    """Read v0.2.74 transition-sensitivity rows keyed by record number.

    The transition scan may be supplied either as the CSV itself, as the output
    directory containing the CSV, or as a parent directory containing the output
    directory.  Older shell workflows commonly passed just
    ``o7_type69_transition_sensitivity``; this helper now searches
    recursively as a fallback so the annotation columns are not silently empty.
    """
    if not path:
        return {}
    p = Path(path)
    candidates: List[Path] = []
    if p.is_file():
        candidates.append(p)
    elif p.is_dir():
        candidates.append(p / "o7_type69_transition_sensitivity.csv")
        candidates.extend(sorted(p.rglob("o7_type69_transition_sensitivity.csv")))
    else:
        candidates.append(p)
    csv_path = next((c for c in candidates if c.exists() and c.is_file()), None)
    if csv_path is None:
        return {}
    out: Dict[int, List[dict]] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rec = maybe_int(row.get("record") or row.get("transition_record") or row.get("collision_record"))
            if rec is None:
                continue
            out.setdefault(rec, []).append(row)
    return out


def best_scan_effect(rows: List[dict]) -> dict:
    """Return compact information from the best sensitivity row for a record."""
    if not rows:
        return {}

    def score(row: dict) -> float:
        r = maybe_float(row.get("R_over_xstar"))
        g = maybe_float(row.get("G_over_xstar"))
        if r is None or g is None:
            return 1.0e99
        return abs(r - 1.0) + abs(g - 1.0)

    best = min(rows, key=score)
    reach = [r for r in rows if str(r.get("target_reachable")).lower() == "true"]
    return {
        "sensitivity_best_case": best.get("case"),
        "sensitivity_best_scale": best.get("scale"),
        "sensitivity_best_R_over_xstar": best.get("R_over_xstar"),
        "sensitivity_best_G_over_xstar": best.get("G_over_xstar"),
        "sensitivity_reachable_scales": ";".join(str(r.get("scale")) for r in reach),
        "sensitivity_n_reachable": len(reach),
    }


def load_type69_records(
    fitsfile: str,
    records: Sequence[int],
    temperatures: Sequence[float],
    density: float,
    index_cache: bool,
    cache_path: Optional[str],
    cache_format: str,
) -> Tuple[List[dict], List[dict], Dict[int, dict], Dict[int, str], Dict[int, float], Dict[int, float]]:
    """Return selected records, evaluated collision rows, and level metadata."""
    from xstar_atomic.hierarchy import ATDB, SYMBOL_TO_Z
    from xstar_atomic.lines import extract_levels, level_maps
    from xstar_atomic.collisions import extract_collisions

    z = SYMBOL_TO_Z["O"]
    with ATDB(fitsfile) as db:
        selected = db.select_records(
            z=z,
            ion_stage=7,
            use_cache=bool(index_cache),
            cache_path=cache_path,
            cache_format=cache_format,
        )
        level_rows = extract_levels(db, selected, z, 7)
        by_level, labels, energies, gs = level_maps(level_rows)
        _summary, _grid, eval_rows = extract_collisions(
            db,
            selected,
            z,
            7,
            [float(t) for t in temperatures],
            electron_density_cm3=float(density),
        )
        wanted = set(int(r) for r in records) if records else None
        raw_rows: List[dict] = []
        for r in selected:
            if r.rate_type != 3 or r.data_type != 69:
                continue
            if wanted is not None and int(r.recno) not in wanted:
                continue
            h = db.header(r.recno)
            ints = db.int_slice(h)
            reals = db.real_slice(h)
            ch = db.char_slice(h)
            lev_a = safe_int(ints[0]) if len(ints) > 0 else None
            lev_b = safe_int(ints[1]) if len(ints) > 1 else None
            lower, upper = physical_order(lev_a, lev_b, energies)
            raw_rows.append({
                "record": int(r.recno),
                "data_type": int(r.data_type),
                "rate_type": int(r.rate_type),
                "nreal": int(r.nreal),
                "nint": int(r.nint),
                "nchar": int(r.nchar),
                "raw_level_a_idat1": lev_a,
                "raw_level_b_idat2": lev_b,
                "lower_level": lower,
                "upper_level": upper,
                "lower_label": labels.get(int(lower), "") if lower is not None else "",
                "upper_label": labels.get(int(upper), "") if upper is not None else "",
                "lower_energy_eV": energies.get(int(lower)) if lower is not None else None,
                "upper_energy_eV": energies.get(int(upper)) if upper is not None else None,
                "delta_e_level_eV": (abs(energies.get(int(upper), 0.0) - energies.get(int(lower), 0.0)) if lower is not None and upper is not None and lower in energies and upper in energies else None),
                "delta_e_rdat0_eV": reals[0] if len(reals) > 0 else None,
                "lower_g": gs.get(int(lower)) if lower is not None else None,
                "upper_g": gs.get(int(upper)) if upper is not None else None,
                "chars": ch,
                "raw_idat_json": preview_json(ints, 80),
                "raw_rdat_json": preview_json(reals, 80),
            })
    raw_rows.sort(key=lambda r: int(r.get("record") or 0))
    return raw_rows, eval_rows, by_level, labels, energies, gs


def direct_record_temperature_rows(raw_rows: List[dict], temperatures: Sequence[float], density: float) -> List[dict]:
    """Compute direct calt69/q-rate audit rows from raw record metadata."""
    rows: List[dict] = []
    raw_by_rec = {int(r["record"]): r for r in raw_rows}
    for rec, raw in raw_by_rec.items():
        try:
            reals = json.loads(raw.get("raw_rdat_json") or "[]")
        except Exception:
            reals = []
        # Strip possible preview strings if present.
        reals = [float(x) for x in reals if isinstance(x, (int, float))]
        for T in temperatures:
            ups = calt69_upsilon(reals, float(T))
            delta = maybe_float(raw.get("delta_e_level_eV"))
            if delta is None:
                delta = maybe_float(raw.get("delta_e_rdat0_eV"))
            g_lo = maybe_float(raw.get("lower_g"))
            g_up = maybe_float(raw.get("upper_g"))
            q_exc, q_de = q_rates_from_upsilon(ups, delta, g_lo, g_up, float(T))
            ratio = (q_exc / q_de) if q_exc is not None and q_de not in (None, 0.0) else None
            expected = None
            if g_lo not in (None, 0.0) and g_up is not None and delta is not None and T > 0:
                expected = (g_up / g_lo) * math.exp(-delta / (KB_EV_PER_K * float(T)))
            rows.append({
                "record": rec,
                "temperature_K": float(T),
                "lower_level": raw.get("lower_level"),
                "upper_level": raw.get("upper_level"),
                "lower_label": raw.get("lower_label"),
                "upper_label": raw.get("upper_label"),
                "delta_e_level_eV": raw.get("delta_e_level_eV"),
                "delta_e_rdat0_eV": raw.get("delta_e_rdat0_eV"),
                "delta_e_difference_eV": ((maybe_float(raw.get("delta_e_rdat0_eV")) or 0.0) - (maybe_float(raw.get("delta_e_level_eV")) or 0.0)) if maybe_float(raw.get("delta_e_rdat0_eV")) is not None and maybe_float(raw.get("delta_e_level_eV")) is not None else None,
                "lower_g": g_lo,
                "upper_g": g_up,
                "upsilon_calt69": ups,
                "q_excitation_direct_cm3_s": q_exc,
                "q_deexcitation_direct_cm3_s": q_de,
                "C_excitation_direct_s^-1": (q_exc * float(density)) if q_exc is not None else None,
                "C_deexcitation_direct_s^-1": (q_de * float(density)) if q_de is not None else None,
                "detailed_balance_q_ratio": ratio,
                "detailed_balance_expected_ratio": expected,
                "detailed_balance_ratio_over_expected": (ratio / expected) if ratio is not None and expected not in (None, 0.0) else None,
            })
    return rows


def merge_eval_rows(raw_rows: List[dict], eval_rows: List[dict], temperatures: Sequence[float], density: float, scan_by_record: Dict[int, List[dict]]) -> List[dict]:
    """Build one audit summary row per selected record at the reference temperature."""
    T0 = float(temperatures[0]) if temperatures else 1.0e6
    by_eval: Dict[int, dict] = {}
    for row in eval_rows:
        if maybe_int(row.get("data_type")) != 69:
            continue
        rec = maybe_int(row.get("record"))
        T = maybe_float(row.get("temperature_K"))
        if rec is None or T is None:
            continue
        if abs(T - T0) <= 1e-6 * max(abs(T0), 1.0):
            by_eval[rec] = row
    direct_rows = direct_record_temperature_rows(raw_rows, [T0], density)
    by_direct = {int(r["record"]): r for r in direct_rows}
    audit: List[dict] = []
    for raw in raw_rows:
        rec = int(raw["record"])
        ev = by_eval.get(rec, {})
        dr = by_direct.get(rec, {})
        q_eval = maybe_float(ev.get("q_excitation_cm3_s"))
        qd_eval = maybe_float(ev.get("q_deexcitation_cm3_s"))
        q_dir = maybe_float(dr.get("q_excitation_direct_cm3_s"))
        qd_dir = maybe_float(dr.get("q_deexcitation_direct_cm3_s"))
        row = dict(raw)
        row.update({
            "audit_temperature_K": T0,
            "eval_method": ev.get("eval_method") or ev.get("collision_eval_method") or ev.get("method"),
            "upsilon_eval": ev.get("upsilon"),
            "upsilon_direct": dr.get("upsilon_calt69"),
            "upsilon_direct_over_eval": ((maybe_float(dr.get("upsilon_calt69")) / maybe_float(ev.get("upsilon"))) if maybe_float(dr.get("upsilon_calt69")) is not None and maybe_float(ev.get("upsilon")) not in (None, 0.0) else None),
            "q_excitation_eval_cm3_s": q_eval,
            "q_deexcitation_eval_cm3_s": qd_eval,
            "q_excitation_direct_cm3_s": q_dir,
            "q_deexcitation_direct_cm3_s": qd_dir,
            "q_excitation_direct_over_eval": (q_dir / q_eval) if q_dir is not None and q_eval not in (None, 0.0) else None,
            "q_deexcitation_direct_over_eval": (qd_dir / qd_eval) if qd_dir is not None and qd_eval not in (None, 0.0) else None,
            "C_excitation_eval_s^-1": (q_eval * float(density)) if q_eval is not None else None,
            "C_deexcitation_eval_s^-1": (qd_eval * float(density)) if qd_eval is not None else None,
            "C_total_eval_s^-1": ((q_eval or 0.0) + (qd_eval or 0.0)) * float(density),
            "detailed_balance_ratio_over_expected": dr.get("detailed_balance_ratio_over_expected"),
        })
        row.update(best_scan_effect(scan_by_record.get(rec, [])))
        audit.append(row)
    audit.sort(key=lambda r: float(r.get("C_total_eval_s^-1") or 0.0), reverse=True)
    return audit


def infer_primary_record(audit_rows: List[dict], preferred: int = 22490) -> Optional[dict]:
    for row in audit_rows:
        if maybe_int(row.get("record")) == preferred:
            return row
    reachable = [r for r in audit_rows if maybe_int(r.get("sensitivity_n_reachable")) and maybe_int(r.get("sensitivity_n_reachable")) > 0]
    if reachable:
        return reachable[0]
    return audit_rows[0] if audit_rows else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--records", default="22490,22491,22492,22493,22494,22495", help="Comma-separated type-69 record numbers to audit; use empty string for all O VII type-69 records")
    parser.add_argument("--temperature-grid", default="1e5,3e5,1e6,3e6,1e7")
    parser.add_argument("--audit-temperature", type=float, default=1.0e6, help="Temperature used for one-row summary; prepended to temperature grid if needed")
    parser.add_argument("--density", type=float, default=1.0e12)
    parser.add_argument("--transition-sensitivity", default="o7_type69_transition_sensitivity", help="Optional v0.2.74 transition-sensitivity directory or CSV")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--out-dir", default="o7_type69_record_audit")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    records = parse_int_list(args.records) if str(args.records).strip() else []
    temperatures = [float(args.audit_temperature)] + [t for t in parse_float_list(args.temperature_grid) if abs(t - float(args.audit_temperature)) > 1e-9 * max(abs(float(args.audit_temperature)), 1.0)]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows, eval_rows, _by_level, _labels, _energies, _gs = load_type69_records(
        args.fitsfile,
        records,
        temperatures,
        float(args.density),
        bool(args.index_cache),
        args.index_cache_path,
        args.index_cache_format,
    )
    if not raw_rows:
        raise SystemExit("No selected O VII type-69 records were found")

    scan_by_record = find_transition_scan_rows(args.transition_sensitivity)
    audit_rows = merge_eval_rows(raw_rows, eval_rows, temperatures, float(args.density), scan_by_record)
    temp_rows = direct_record_temperature_rows(raw_rows, temperatures, float(args.density))

    raw_csv = out_dir / "o7_type69_record_raw_audit.csv"
    audit_csv = out_dir / "o7_type69_record_audit.csv"
    temp_csv = out_dir / "o7_type69_record_temperature_grid.csv"
    summary_json = out_dir / "o7_type69_record_audit_summary.json"
    write_csv(raw_csv, raw_rows)
    write_csv(audit_csv, audit_rows)
    write_csv(temp_csv, temp_rows)

    primary = infer_primary_record(audit_rows, 22490)
    summary = {
        "fitsfile": args.fitsfile,
        "ion": "O VII",
        "electron_density_cm^-3": float(args.density),
        "audit_temperature_K": float(args.audit_temperature),
        "temperature_grid_K": temperatures,
        "records_requested": records or "all_type69",
        "records_found": [int(r["record"]) for r in raw_rows],
        "n_records": len(raw_rows),
        "primary_record": primary,
        "transition_sensitivity_input": str(args.transition_sensitivity),
        "transition_sensitivity_records_matched": sorted(int(k) for k in scan_by_record),
        "transition_sensitivity_rows_matched": sum(len(v) for v in scan_by_record.values()),
        "raw_audit_csv": str(raw_csv),
        "audit_csv": str(audit_csv),
        "temperature_grid_csv": str(temp_csv),
        "summary_json": str(summary_json),
        "interpretation": "If record 22490 appears as a reachable/best sensitivity case, the high-density resonance mismatch is driven by the ground-to-resonance type-69 channel rather than by missing empirical source levels.",
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    if args.print_summary:
        print("O VII type-69 record audit")
        print("---------------------------")
        print(f"density: {float(args.density):g} cm^-3")
        print(f"audit temperature: {float(args.audit_temperature):g} K")
        print(f"records found: {', '.join(str(r['record']) for r in raw_rows)}")
        print(f"wrote: {audit_csv}")
        print(f"wrote: {temp_csv}")
        print(f"wrote: {summary_json}")
        print("record levels label                          Upsilon        Cexc        Cdeexc      best sensitivity")
        for row in audit_rows:
            label = f"{row.get('lower_label','')} -> {row.get('upper_label','')}"[:30]
            print(
                f"{int(row['record']):<6} {row.get('lower_level')}->{row.get('upper_level'):<3} "
                f"{label:<30} {row.get('upsilon_eval')} {row.get('C_excitation_eval_s^-1')} {row.get('C_deexcitation_eval_s^-1')} "
                f"{row.get('sensitivity_best_case')}"
            )
        if primary:
            print(
                "primary record: "
                f"{primary.get('record')} levels={primary.get('lower_level')}->{primary.get('upper_level')} "
                f"best_case={primary.get('sensitivity_best_case')} "
                f"reachable_scales={primary.get('sensitivity_reachable_scales')}"
            )
        print("- This is an audit: direct calt69 rates should match evaluated xstar_atomic rates if decoding is internally consistent.")
        print("- If record 22490 remains the primary reachable sensitivity case, inspect its physical inclusion/direction rather than the empirical source basis.")


if __name__ == "__main__":
    main()
