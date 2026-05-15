"""Diagnose whether remaining O VII triplet mismatch is rate- or closure-driven.

This post-processing audit consumes record-level replay family scans.  If exact
Fortran ``ucalc`` replay of the discrepant rate families barely changes the
population solution, the next source-code parity target is not another isolated
rate formula but the population/source closure around adjacent ions, superlevels,
and the linear-system right-hand side/normalization used by XSTAR.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


def _read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in fields:
                fields.append(str(k))
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _as_float(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        f = float(v)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def _resolve_family_scan(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        p = p / "xstar_record_level_ucalc_replay_family_scan.csv"
    if not p.exists():
        raise FileNotFoundError(f"family-scan CSV not found: {p}")
    return p


def diagnose_population_closure_from_family_scan(
    family_scan_csv: str | Path,
    *,
    ion: str = "O VII",
    population_delta_threshold: float = 1.0e-4,
) -> Dict[str, Any]:
    """Return a closure diagnosis from a family replay scan."""
    scan_path = _resolve_family_scan(family_scan_csv)
    rows_in = _read_csv_rows(scan_path)
    rows: List[Dict[str, Any]] = []
    max_abs_delta = 0.0
    max_abs_delta_family = ""
    for r in rows_in:
        df = _as_float(r.get("delta_triplet_population_f_fraction"), 0.0) or 0.0
        di = _as_float(r.get("delta_triplet_population_i_fraction"), 0.0) or 0.0
        dr = _as_float(r.get("delta_triplet_population_r_fraction"), 0.0) or 0.0
        fam = str(r.get("family_key") or r.get("family_selector") or "")
        fam_max = max(abs(df), abs(di), abs(dr))
        if fam_max > max_abs_delta:
            max_abs_delta = fam_max
            max_abs_delta_family = fam
        n_terms = int(_as_float(r.get("n_replayed_terms"), 0.0) or 0.0)
        median = _as_float(r.get("median_old_over_new"), None)
        if n_terms == 0:
            influence = "not_tested_or_no_matching_terms"
        elif fam_max >= population_delta_threshold:
            influence = "rate_family_moves_population"
        else:
            influence = "rate_family_does_not_move_population"
        rows.append({
            "family": fam,
            "n_replayed_terms": n_terms,
            "median_old_over_new": "" if median is None else median,
            "delta_f": df,
            "delta_i": di,
            "delta_r": dr,
            "max_abs_population_delta": fam_max,
            "population_influence_class": influence,
            "recommended_action": (
                "fix family selector or rerun scan" if n_terms == 0 else
                "native source-code rate port still needed, but not the dominant population-balance lever" if influence == "rate_family_does_not_move_population" else
                "prioritize this family as population-moving rate physics"
            ),
        })
    rate_replay_moves_population = max_abs_delta >= population_delta_threshold
    summary = {
        "audit_version": "v0.3.187",
        "ion": ion,
        "status": "population_closure_diagnosis_completed",
        "family_scan_csv": str(scan_path),
        "n_families": len(rows),
        "population_delta_threshold": population_delta_threshold,
        "max_abs_population_delta": max_abs_delta,
        "max_abs_population_delta_family": max_abs_delta_family,
        "rate_replay_moves_population": bool(rate_replay_moves_population),
        "dominant_next_target": "rate_family_port" if rate_replay_moves_population else "population_source_closure",
        "source_equivalent_population_closure_ready": False,
        "interpretation": (
            "At least one exact-ucalc family replay moved the triplet population above threshold; prioritize that native rate branch."
            if rate_replay_moves_population else
            "Exact-ucalc replay of discrepant matrix-rate families does not significantly move the triplet population. The next source-code-equivalent target is population/source closure: adjacent-ion parent coupling, superlevel source/sink closure, RHS/normalization, and pre/post-msolvelucy population parity."
        ),
    }
    plan = [
        {"priority": 1, "target": "levwkelement/calc_hmc_element RHS and normalization", "probe_product": "xstar_rhs_population_closure_probe.csv", "why": "Need XSTAR b/rhs vector and matrix normalization before msolvelucy, not only individual local rates."},
        {"priority": 2, "target": "pre/post msolvelucy population vector", "probe_product": "xstar_population_solution_probe.csv", "why": "Compare solved populations level-by-level before emissivity extraction."},
        {"priority": 3, "target": "type-70/type-74/type-99 parent and superlevel closure", "probe_product": "xstar_superlevel_parent_closure_probe.csv", "why": "Current type-99 term-wise replay is near unity, but source/sink population closure may differ."},
        {"priority": 4, "target": "native type-53/type-50/type-77 source-code ports", "probe_product": "native Python implementations", "why": "Still needed for source equivalence, but family replay shows they are not sufficient to fix the O VII population balance alone."},
    ]
    return {"summary": summary, "family_rows": rows, "implementation_plan_rows": plan}


def write_population_closure_diagnosis(audit: Mapping[str, Any], out_dir: str | Path, *, prefix: str = "xstar_population_closure_diagnosis") -> Dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    summary = dict(audit.get("summary", {}) or {})
    family_rows = list(audit.get("family_rows", []) or [])
    plan_rows = list(audit.get("implementation_plan_rows", []) or [])
    family_csv = out / f"{prefix}_family_influence.csv"
    plan_csv = out / f"{prefix}_implementation_plan.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    _write_csv(family_csv, family_rows)
    _write_csv(plan_csv, plan_rows)
    json_path.write_text(json.dumps({"summary": summary, "family_rows": family_rows, "implementation_plan_rows": plan_rows}, indent=2, default=str), encoding="utf-8")
    lines = [
        "# XSTAR population/source closure diagnosis",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"ion: `{summary.get('ion')}`",
        f"status: `{summary.get('status')}`",
        f"dominant_next_target: `{summary.get('dominant_next_target')}`",
        f"max_abs_population_delta: `{summary.get('max_abs_population_delta')}`",
        "",
        "## Interpretation",
        "",
        str(summary.get("interpretation") or ""),
        "",
        "## Family influence",
        "",
        "| family | n terms | median old/new | max | class |",
        "|---|---:|---:|---:|---|",
    ]
    for r in family_rows:
        lines.append(f"| {r.get('family')} | {r.get('n_replayed_terms')} | {r.get('median_old_over_new')} | {r.get('max_abs_population_delta')} | {r.get('population_influence_class')} |")
    lines.extend(["", "## Implementation plan", "", "| priority | target | probe product | why |", "|---:|---|---|---|"])
    for r in plan_rows:
        lines.append(f"| {r.get('priority')} | {r.get('target')} | {r.get('probe_product')} | {r.get('why')} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"family_influence_csv": str(family_csv), "implementation_plan_csv": str(plan_csv), "json": str(json_path), "markdown": str(md_path)}
