#!/usr/bin/env python3
"""Source-code-first Mg XI / Ca XIX validation audit.

This diagnostic intentionally does *not* fit empirical scale factors.  It reads
solver outputs and XSTAR triplet-line CSV targets, records whether the solver
state changes across the XSTAR log-xi grid, and maps the relevant solver paths
back to the XSTAR Fortran routines that should be ported/aligned before any
scale tuning is accepted as physics.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if math.isfinite(x) else None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", "--"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as h:
        return [dict(r) for r in csv.DictReader(h)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _component_from_line(row: dict[str, Any]) -> str | None:
    upper = str(row.get("upper_level") or row.get("upper") or "").lower()
    wave = _as_float(row.get("wavelength") or row.get("wavelength_A"))
    if "3s_1" in upper or "3s" in upper:
        return "f"
    if "3p" in upper:
        return "i"
    if "1p_1" in upper or "1p" in upper:
        return "r"
    # Fallback windows are intentionally broad and only used if labels are absent.
    if wave is None:
        return None
    return None


def _component_summary(vals: dict[str, float]) -> dict[str, Any]:
    total = sum(vals.values())
    if total <= 0:
        return {"f": None, "i": None, "r": None, "R": None, "G": None, "total": total}
    f = vals.get("f", 0.0) / total
    i = vals.get("i", 0.0) / total
    r = vals.get("r", 0.0) / total
    return {
        "f": f,
        "i": i,
        "r": r,
        "R": None if i <= 0 else f / i,
        "G": None if r <= 0 else (f + i) / r,
        "total": total,
    }


def _target_from_xstar_csv(path: Path, value_column: str = "emit_outward") -> dict[str, Any]:
    rows = _read_csv(path)
    vals = {"f": 0.0, "i": 0.0, "r": 0.0}
    max_depth = 0.0
    for r in rows:
        comp = _component_from_line(r)
        val = _as_float(r.get(value_column))
        if comp and val is not None:
            vals[comp] += max(0.0, val)
        for dcol in ("depth_inward", "depth_outward"):
            d = _as_float(r.get(dcol))
            if d is not None:
                max_depth = max(max_depth, d)
    s = _component_summary(vals)
    return {
        "target_f": s["f"], "target_i": s["i"], "target_r": s["r"],
        "target_R": s["R"], "target_G": s["G"],
        "target_total_triplet": s["total"],
        "target_n_lines": len(rows),
        "target_max_line_depth": max_depth,
    }


def _solver_summary(solver_dir: Path) -> dict[str, Any]:
    # Prefer comparison JSON because it is what users inspect after examples/43.
    p = solver_dir / "xstar_detail_population_comparison_summary.json"
    if p.exists():
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            trip = payload.get("triplet") if isinstance(payload.get("triplet"), dict) else payload
            return {
                "solver_f": _as_float(trip.get("f_fraction") or trip.get("triplet_f_fraction") or trip.get("f")),
                "solver_i": _as_float(trip.get("i_fraction") or trip.get("triplet_i_fraction") or trip.get("i")),
                "solver_r": _as_float(trip.get("r_fraction") or trip.get("triplet_r_fraction") or trip.get("r")),
                "solver_R": _as_float(trip.get("R_ratio") or trip.get("R") or trip.get("triplet_R")),
                "solver_G": _as_float(trip.get("G_ratio") or trip.get("G") or trip.get("triplet_G")),
                "solver_l2": _as_float(trip.get("l2_distance_to_target") or trip.get("L2")),
                "solver_source": "xstar_detail_population_comparison_summary.json:triplet",
            }
        except Exception:
            pass
    for fn in ("xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv", "xstar_like_element_solver_full_global_normalized_solve_comparison.csv"):
        rows = _read_csv(solver_dir / fn)
        for r in rows:
            case = str(r.get("comparison_case") or r.get("row_kind") or "")
            if "full_global_xstar_tau0_calc_emis_ion" in case or "triplet" in fn:
                f = _as_float(r.get("f_fraction") or r.get("f"))
                i = _as_float(r.get("i_fraction") or r.get("i"))
                rr = _as_float(r.get("r_fraction") or r.get("r"))
                if f is not None and i is not None and rr is not None:
                    return {
                        "solver_f": f,
                        "solver_i": i,
                        "solver_r": rr,
                        "solver_R": _as_float(r.get("R_ratio") or r.get("R")) or (f / i if i else None),
                        "solver_G": _as_float(r.get("G_ratio") or r.get("G")) or ((f + i) / rr if rr else None),
                        "solver_l2": _as_float(r.get("l2_distance_to_target") or r.get("L2")),
                        "solver_source": fn,
                    }
    return {"solver_f": None, "solver_i": None, "solver_r": None, "solver_R": None, "solver_G": None, "solver_l2": None, "solver_source": "not_found"}


def _l2(row: dict[str, Any]) -> float | None:
    vals = [
        (_as_float(row.get("solver_f")), _as_float(row.get("target_f"))),
        (_as_float(row.get("solver_i")), _as_float(row.get("target_i"))),
        (_as_float(row.get("solver_r")), _as_float(row.get("target_r"))),
    ]
    if any(a is None or b is None for a, b in vals):
        return None
    return math.sqrt(sum((a-b)**2 for a,b in vals))


def _find_target_csv(results_root: Path, tag: str) -> Path | None:
    pats = [
        f"xstar_test_run/{tag}/xstar_*_triplet_lines.csv",
        f"**/{tag}/xstar_*_triplet_lines.csv",
    ]
    for pat in pats:
        matches = sorted(results_root.glob(pat))
        if matches:
            return matches[0]
    return None


def _case_label_from_solver_dir(path: Path) -> tuple[str, str, str]:
    name = path.name.lower()
    ion = "Mg XI" if name.startswith("mg11") or "mg11" in name else ("Ca XIX" if name.startswith("ca19") or "ca19" in name else "unknown")
    m = re.search(r"xi([0-9]+(?:p[0-9]+)?)", name)
    xi = m.group(1).replace("p", ".") if m else "unknown"
    m2 = re.search(r"ne([0-9]+e[0-9]+)", name)
    ne = m2.group(1) if m2 else "unknown"
    tag_prefix = "mg11" if ion == "Mg XI" else ("ca19" if ion == "Ca XIX" else "unknown")
    tag = f"{tag_prefix}_xi{m.group(1) if m else 'unknown'}_ne{ne}"
    return ion, xi, tag


def _source_method_rows(xstar_source_root: Path | None) -> list[dict[str, Any]]:
    def exists(rel: str) -> bool:
        return bool(xstar_source_root and (xstar_source_root / rel).exists())
    rows = [
        {
            "method_family": "element_population_solver",
            "xstar_file": "xstarlib/src/calc_hmc_element.f90",
            "xstar_present": exists("xstarlib/src/calc_hmc_element.f90"),
            "current_status": "partially mirrored by full-global xstar-lucy topology; not yet a full XSTAR thermal/radiation/ionization-zone solve",
            "next_source_code_task": "port/align zone-specific population normalization and ion fraction closure before interpreting log-xi grids",
        },
        {
            "method_family": "level_rate_dispatch",
            "xstar_file": "xstarlib/src/ucalc.f90",
            "xstar_present": exists("xstarlib/src/ucalc.f90"),
            "current_status": "individual type-50/53/63/69/71/74/77/99 paths are diagnostic/partial; source-code audit should decide gaps",
            "next_source_code_task": "audit ans1/ans2 direction and density factors for each Mg/Ca resonance/intercombination path",
        },
        {
            "method_family": "type63_same_n_and_n_change_collisions",
            "xstar_file": "xstarlib/src/ucalc.f90 + erc.f90 + amcrs.f90 + velimp.f90 + anl1.f90",
            "xstar_present": exists("xstarlib/src/ucalc.f90"),
            "current_status": "Python evaluator mirrors formulas but C V shows resonance feed sensitivity; do not scale-fit Mg/Ca",
            "next_source_code_task": "row-by-row compare type-63 ans1/ans2, statistical weights, n/l branch selector, and same-n l-mixing cutoff against XSTAR detail rates",
        },
        {
            "method_family": "type69_helike_collisions",
            "xstar_file": "xstarlib/src/ucalc.f90 + calt69.f90",
            "xstar_present": exists("xstarlib/src/calt69.f90"),
            "current_status": "calt69 path exists; needs Mg/Ca row-by-row gamma/cij/cji audit rather than empirical multiplier",
            "next_source_code_task": "write gamma/cij/cji audit for Mg XI and Ca XIX resonance/intercombination upper levels",
        },
        {
            "method_family": "line_escape_and_emergent_output",
            "xstar_file": "xstarlib/src/calc_emis_ion.f90 + pescl.f90/pescv.f90",
            "xstar_present": exists("xstarlib/src/calc_emis_ion.f90"),
            "current_status": "O VII reference-depth postprocess is validation-only; population matrix still lacks full line-tau context for all lines",
            "next_source_code_task": "use XSTAR tau0/depth context for Mg/Ca emergent lines before comparing high-depth resonance components",
        },
        {
            "method_family": "radiation_normalization_log_xi",
            "xstar_file": "xstarlib/src/* radiation/continuum setup + ucalc bremsa arguments",
            "xstar_present": bool(xstar_source_root),
            "current_status": "solver outputs in v0.3.111 are xi-invariant; XSTAR target varies with log xi",
            "next_source_code_task": "derive bremsa/epi normalization from the XSTAR run context instead of using a fixed diagnostic bremsa scale",
        },
    ]
    return rows


def build_report(results_root: Path, xstar_source_root: Path | None, value_column: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    solver_dirs = sorted([p for p in results_root.glob("*xstar_like_element_solver*v03111*superlevels") if p.is_dir()])
    rows: list[dict[str, Any]] = []
    for sdir in solver_dirs:
        ion, xi, tag = _case_label_from_solver_dir(sdir)
        if ion == "unknown":
            continue
        target_csv = _find_target_csv(results_root, tag)
        solver = _solver_summary(sdir)
        target = _target_from_xstar_csv(target_csv, value_column=value_column) if target_csv else {}
        row = {
            "ion": ion,
            "log_xi": xi,
            "solver_dir": str(sdir.relative_to(results_root)),
            "xstar_triplet_csv": "" if target_csv is None else str(target_csv.relative_to(results_root)),
            **solver,
            **target,
        }
        row["l2_solver_to_xstar_csv"] = _l2(row)
        row["source_code_validation_status"] = "target_missing" if target_csv is None else "requires_source_code_alignment_not_scale_fit"
        rows.append(row)
    # Invariance summary by ion.
    inv: list[dict[str, Any]] = []
    for ion in sorted({r["ion"] for r in rows}):
        sub = [r for r in rows if r["ion"] == ion]
        def spread(key: str) -> float | None:
            vals = [_as_float(r.get(key)) for r in sub]
            vals = [v for v in vals if v is not None]
            return None if not vals else max(vals) - min(vals)
        inv.append({
            "ion": ion,
            "n_cases": len(sub),
            "solver_f_spread": spread("solver_f"),
            "solver_i_spread": spread("solver_i"),
            "solver_r_spread": spread("solver_r"),
            "target_f_spread": spread("target_f"),
            "target_i_spread": spread("target_i"),
            "target_r_spread": spread("target_r"),
            "diagnosis": "solver_state_xi_invariant_but_xstar_target_varies" if (spread("solver_f") or 0) < 1e-10 and (spread("target_f") or 0) > 1e-4 else "check_case_by_case",
        })
    payload = {
        "n_solver_cases": len(rows),
        "ions": sorted({r["ion"] for r in rows}),
        "source_code_policy": "do_not_choose_empirical_best_scale; port/audit XSTAR formulas first",
        "primary_diagnosis": "v0.3.111 Mg/Ca solver outputs are xi-invariant while XSTAR triplet targets vary with log xi; source-code work should prioritize XSTAR radiation/ionization normalization and row-level type63/type69 audits.",
    }
    return rows, _source_method_rows(xstar_source_root), {"summary": payload, "invariance": inv}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-root", default=".", help="Directory containing v0.3.111 Mg/Ca solver outputs and xstar_test_run targets")
    ap.add_argument("--xstar-source-root", default=None, help="Optional XSTAR source root containing xstarlib/src")
    ap.add_argument("--xstar-value-column", default="emit_outward")
    ap.add_argument("--out-dir", default="mg_ca_sourcecode_first_validation_v03112")
    ap.add_argument("--print-summary", action="store_true")
    ns = ap.parse_args()
    results_root = Path(ns.results_root)
    src_root = Path(ns.xstar_source_root) if ns.xstar_source_root else None
    out = Path(ns.out_dir)
    rows, method_rows, payload = build_report(results_root, src_root, ns.xstar_value_column)
    _write_csv(out / "mg_ca_sourcecode_first_comparison.csv", rows)
    _write_csv(out / "mg_ca_xstar_source_method_audit.csv", method_rows)
    _write_csv(out / "mg_ca_xi_invariance_audit.csv", payload["invariance"])
    _write_json(out / "mg_ca_sourcecode_first_summary.json", payload["summary"])
    md = ["# Mg XI / Ca XIX source-code-first validation", "", payload["summary"]["primary_diagnosis"], "", "## Policy", "", "Do not choose empirical best scale factors to reproduce f/i/r, R, and G. Use XSTAR source-code formulas and row-level audits first.", "", "## Invariance audit", ""]
    for r in payload["invariance"]:
        md.append(f"- {r['ion']}: {r['diagnosis']} (solver f spread={r.get('solver_f_spread')}, target f spread={r.get('target_f_spread')})")
    md.extend(["", "## Next source-code tasks", "", "1. Port/validate XSTAR log-xi radiation normalization (`epi`/`bremsa`) instead of fixed diagnostic `--radiation-bremsa-scale`.", "2. Add row-by-row `ucalc` type-63/type-69 audits for Mg XI/Ca XIX resonance and intercombination upper levels.", "3. Use XSTAR line-depth/tau context for emergent line comparison where resonance depth is non-negligible.", "4. Only after these audits should any scale-like discrepancy be interpreted physically.", ""])
    (out / "mg_ca_sourcecode_first_validation.md").write_text("\n".join(md), encoding="utf-8")
    if ns.print_summary:
        print("Mg/Ca source-code-first validation")
        print("----------------------------------")
        print(payload["summary"]["primary_diagnosis"])
        for r in payload["invariance"]:
            print(f"{r['ion']}: {r['diagnosis']}")
        print(f"wrote: {out/'mg_ca_sourcecode_first_comparison.csv'}")
        print(f"wrote: {out/'mg_ca_xstar_source_method_audit.csv'}")
        print(f"wrote: {out/'mg_ca_sourcecode_first_validation.md'}")


if __name__ == "__main__":
    main()
