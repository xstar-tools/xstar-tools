"""Diagnose native-rate assembly readiness for the priority compact subsystem.

This audit consumes the v0.3.201 priority conditional-solve products (and, when
available, the v0.3.199 record-term table).  It separates the selected compact
matrix into two physically distinct pieces:

``A_SS``
    couplings among the activated compact unknowns;

``b_S = -A_SE x_E``
    source/sink closure supplied by populations outside the activated subset.

The audit ranks ATDB/XSTAR rate families by their population-weighted influence
and attaches a conservative implementation status.  It is an implementation
plan, not a native-rate replacement and not a solver-physics change.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


_FAMILY_CATALOG: Dict[str, Dict[str, str]] = {
    "type50_rate4": {
        "physical_process": "bound-bound radiative decay, escape, and line pumping",
        "native_status": "partial",
        "native_status_detail": "type-50 evaluator exists; all-ion source-equivalent escape/cfrac and live-radiation pumping are not yet production-ready",
        "next_action": "port full ucalc type-50 branch for all active ion blocks and replace diagnostic escape-factor paths",
    },
    "type71_rate14": {
        "physical_process": "superlevel radiative cascade",
        "native_status": "source_equivalent_ready",
        "native_status_detail": "calt71 evaluator and matrix placement have passed record-level parity",
        "next_action": "integrate existing type-71 evaluator into the expanded compact-basis assembler",
    },
    "type53_rate7": {
        "physical_process": "photoionization and Milne inverse recombination",
        "native_status": "blocked",
        "native_status_detail": "native/proxy photoionization normalization differs from live XSTAR phint53 by approximately 44; exact live epim/bremsam path is required",
        "next_action": "implement source-equivalent live-radiation phint53 ans1/ans2 and remove proxy xstar-powerlaw normalization",
    },
    "type51_rate3": {
        "physical_process": "tabulated electron-impact excitation/de-excitation",
        "native_status": "evaluator_ready_integration_pending",
        "native_status_detail": "type-51 collision evaluator exists; compact lower-ion block assembly and selected-record parity remain to be wired",
        "next_action": "assemble type-51 rates on rows 79,80,241,242,244,293 and compare record-by-record with ucalc",
    },
    "type99_rate7": {
        "physical_process": "superlevel/parent photoionization-recombination closure",
        "native_status": "partial",
        "native_status_detail": "topology and diagnostic evaluators exist; calt99/phint53hunt population scaling and parent closure are incomplete",
        "next_action": "port calt99 plus phint53hunt scaling on shared parent-continuum aliases",
    },
    "type49_rate7": {
        "physical_process": "photoionization/recombination data branch",
        "native_status": "partial",
        "native_status_detail": "ATDB decoding exists; source-equivalent compact matrix assembly is not certified",
        "next_action": "audit type-49 ucalc branch and add compact endpoint assembly",
    },
    "type57_rate5": {
        "physical_process": "collisional ionization and inverse three-body recombination",
        "native_status": "diagnostic_only",
        "native_status_detail": "calt57 diagnostic evaluator exists but is not assembled into the production matrix",
        "next_action": "resolve energy convention and enable source-equivalent type-57 matrix terms",
    },
    "type86_rate41": {
        "physical_process": "continuum/superlevel closure branch",
        "native_status": "not_implemented",
        "native_status_detail": "no production native compact-matrix evaluator is certified",
        "next_action": "review ucalc branch and port only if population-weighted influence becomes material",
    },
    "type88_rate42": {
        "physical_process": "continuum/superlevel closure branch",
        "native_status": "not_implemented",
        "native_status_detail": "no production native compact-matrix evaluator is certified",
        "next_action": "review ucalc branch after dominant type-51/type-50/type-71 closure is native",
    },
    "type95_rate5": {
        "physical_process": "ionization/recombination auxiliary branch",
        "native_status": "not_implemented",
        "native_status_detail": "no production native compact-matrix evaluator is certified",
        "next_action": "defer until dominant-family replacement and residual audit",
    },
    "type2_rate5": {
        "physical_process": "auxiliary ionization/recombination metadata branch",
        "native_status": "zero_impact_here",
        "native_status_detail": "zero population-weighted contribution in this selected solve",
        "next_action": "defer for this subsystem",
    },
    "type9_rate5": {
        "physical_process": "auxiliary ionization/recombination metadata branch",
        "native_status": "negligible_here",
        "native_status_detail": "negligible population-weighted contribution in this selected solve",
        "next_action": "defer for this subsystem",
    },
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if str(key) not in fields:
                fields.append(str(key))
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _resolve_product(path: str | Path, default_name: str) -> Path:
    root = Path(path)
    if root.is_file() and root.name == default_name:
        return root
    if root.is_dir():
        direct = root / default_name
        if direct.exists():
            return direct
        hits = sorted(root.rglob(default_name))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"could not find {default_name} under {root}")


def _load_summary(root: str | Path, name: str) -> Dict[str, Any]:
    try:
        path = _resolve_product(root, name)
    except FileNotFoundError:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        summary = payload.get("summary", payload)
        if isinstance(summary, dict):
            return dict(summary)
    return {}


def _family_info(family_key: str) -> Dict[str, str]:
    return dict(_FAMILY_CATALOG.get(family_key, {
        "physical_process": "unclassified XSTAR rate family",
        "native_status": "not_classified",
        "native_status_detail": "family has not yet been assigned a native implementation status",
        "next_action": "review corresponding ucalc branch before native assembly",
    }))


def _rank_family_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = sorted(rows, key=lambda row: float(row["absolute_population_weighted_sum"]), reverse=True)
    total = sum(float(row["absolute_population_weighted_sum"]) for row in rows)
    cumulative = 0.0
    for rank, row in enumerate(rows, 1):
        value = float(row["absolute_population_weighted_sum"])
        fraction = value / total if total > 0.0 else 0.0
        cumulative += fraction
        row["influence_rank"] = rank
        row["influence_fraction"] = fraction
        row["cumulative_influence_fraction"] = cumulative
        row.update(_family_info(str(row["family_key"])))
    return rows


def build_priority_native_readiness_audit(
    *,
    priority_conditional_solve_audit: str | Path,
    priority_matrix_balance_audit: str | Path | None = None,
) -> Dict[str, Any]:
    """Build family-ranked native assembly readiness products."""
    cond_summary = _load_summary(
        priority_conditional_solve_audit,
        "xstar_priority_conditional_solve_audit.json",
    )
    solve_path = _resolve_product(
        priority_conditional_solve_audit,
        "xstar_priority_conditional_solve_audit_solve_comparison.csv",
    )
    external_path = _resolve_product(
        priority_conditional_solve_audit,
        "xstar_priority_conditional_solve_audit_external_rhs_family_contributions.csv",
    )
    solve_rows = _read_csv(solve_path)
    external_raw = _read_csv(external_path)

    internal_rows: List[Dict[str, Any]] = []
    record_terms_status = "not_supplied"
    if priority_matrix_balance_audit is not None:
        term_path = _resolve_product(
            priority_matrix_balance_audit,
            "xstar_priority_matrix_balance_audit_record_terms.csv",
        )
        term_rows = _read_csv(term_path)
        selected = {
            ip for ip in (_as_int(row.get("xstar_ipmat2_index"), None) for row in solve_rows)
            if ip is not None
        }
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in term_rows:
            col = _as_int(row.get("compact_col_ipmat2"), None)
            if col not in selected:
                continue
            family = str(row.get("family_key", "unknown"))
            out = grouped.setdefault(family, {
                "family_key": family,
                "n_record_terms": 0,
                "absolute_coefficient_sum_s^-1": 0.0,
                "signed_population_weighted_sum": 0.0,
                "absolute_population_weighted_sum": 0.0,
            })
            out["n_record_terms"] += 1
            out["absolute_coefficient_sum_s^-1"] += abs(_as_float(row.get("ajisi_1_s^-1"), 0.0))
            weighted = _as_float(row.get("population_weighted_contribution"), 0.0)
            out["signed_population_weighted_sum"] += weighted
            out["absolute_population_weighted_sum"] += abs(weighted)
        internal_rows = _rank_family_rows(list(grouped.values()))
        record_terms_status = "loaded"

    external_grouped: Dict[str, Dict[str, Any]] = {}
    for row in external_raw:
        family = str(row.get("family_key", "unknown"))
        out = external_grouped.setdefault(family, {
            "family_key": family,
            "n_record_terms": 0,
            "absolute_coefficient_sum_s^-1": "",
            "signed_population_weighted_sum": 0.0,
            "absolute_population_weighted_sum": 0.0,
        })
        out["n_record_terms"] += int(_as_int(row.get("n_record_terms"), 0) or 0)
        signed = _as_float(row.get("external_population_weighted_sum"), 0.0)
        out["signed_population_weighted_sum"] += signed
        out["absolute_population_weighted_sum"] += abs(signed)
    external_rows = _rank_family_rows(list(external_grouped.values()))

    row_dominance: List[Dict[str, Any]] = []
    by_row: Dict[int, List[Dict[str, str]]] = {}
    for row in external_raw:
        ip = _as_int(row.get("xstar_ipmat2_index"), None)
        if ip is not None:
            by_row.setdefault(ip, []).append(row)
    solve_meta = {_as_int(row.get("xstar_ipmat2_index"), -1): row for row in solve_rows}
    for ip in sorted(by_row):
        ranked = sorted(
            by_row[ip],
            key=lambda row: abs(_as_float(row.get("external_population_weighted_sum"), 0.0)),
            reverse=True,
        )
        total = sum(abs(_as_float(row.get("external_population_weighted_sum"), 0.0)) for row in ranked)
        first = ranked[0] if ranked else {}
        second = ranked[1] if len(ranked) > 1 else {}
        row_dominance.append({
            "xstar_ipmat2_index": ip,
            "physical_roles": solve_meta.get(ip, {}).get("physical_roles", ""),
            "captured_population": solve_meta.get(ip, {}).get("captured_xstar_population", ""),
            "external_rhs_absolute_sum": total,
            "dominant_family": first.get("family_key", ""),
            "dominant_family_fraction": (abs(_as_float(first.get("external_population_weighted_sum"), 0.0)) / total if total else 0.0),
            "second_family": second.get("family_key", ""),
            "second_family_fraction": (abs(_as_float(second.get("external_population_weighted_sum"), 0.0)) / total if total else 0.0),
            "dominant_native_status": _family_info(str(first.get("family_key", ""))).get("native_status", ""),
        })

    implementation_phases = [
        {
            "phase": 1,
            "scope": "selected internal compact block",
            "families": "type51_rate3",
            "reason": "dominates the internal population-weighted coupling",
            "acceptance_test": "record-level type-51 ans1/ans2 and compact matrix entries agree with XSTAR for all selected rows",
        },
        {
            "phase": 2,
            "scope": "external RHS closure",
            "families": "type50_rate4;type71_rate14",
            "reason": "together dominate the external source/sink closure",
            "acceptance_test": "native RHS reproduces probe-derived RHS row-by-row within 0.5 percent",
        },
        {
            "phase": 3,
            "scope": "photoionization closure",
            "families": "type53_rate7",
            "reason": "small influence in this six-row solve but required for source equivalence and broader states",
            "acceptance_test": "remove the approximately 44 scale using live epim/bremsam phint53; no empirical multiplier",
        },
        {
            "phase": 4,
            "scope": "parent/superlevel and residual families",
            "families": "type99_rate7;type49_rate7;type57_rate5;type86_rate41;type88_rate42;type95_rate5",
            "reason": "complete source-equivalent closure after dominant families pass",
            "acceptance_test": "native 6-row conditional solve remains within 0.5 percent and all record/matrix parity checks pass",
        },
        {
            "phase": 5,
            "scope": "active compact solve expansion",
            "families": "all native families",
            "reason": "replace fixed external populations by the 119-row active compact solve",
            "acceptance_test": "119-row populations and selected-row residuals agree with XSTAR before expanding to all 607 rows",
        },
    ]

    internal_total = sum(float(row["absolute_population_weighted_sum"]) for row in internal_rows)
    external_total = sum(float(row["absolute_population_weighted_sum"]) for row in external_rows)
    internal_top = internal_rows[0] if internal_rows else {}
    external_top = external_rows[0] if external_rows else {}
    external_top3 = sum(float(row.get("influence_fraction", 0.0)) for row in external_rows[:3])
    internal_top4 = sum(float(row.get("influence_fraction", 0.0)) for row in internal_rows[:4])

    summary = {
        "audit_version": "v0.3.202",
        "status": "priority_native_assembly_readiness_completed",
        "ion": cond_summary.get("ion", ""),
        "selected_basis_solve_call_id": cond_summary.get("selected_basis_solve_call_id", ""),
        "selected_xstar_ipmat2_indices": cond_summary.get("selected_xstar_ipmat2_indices", ""),
        "n_selected_compact_rows": cond_summary.get("n_selected_compact_rows", len(solve_rows)),
        "conditional_solve_ready": bool(cond_summary.get("fortran_priority_subset_conditional_solve_ready", False)),
        "record_terms_status": record_terms_status,
        "n_internal_rate_families": len(internal_rows),
        "n_external_rhs_rate_families": len(external_rows),
        "internal_absolute_population_weighted_total": internal_total,
        "external_rhs_absolute_population_weighted_total": external_total,
        "dominant_internal_family": internal_top.get("family_key", ""),
        "dominant_internal_family_fraction": internal_top.get("influence_fraction", 0.0),
        "dominant_external_rhs_family": external_top.get("family_key", ""),
        "dominant_external_rhs_family_fraction": external_top.get("influence_fraction", 0.0),
        "internal_top4_cumulative_fraction": internal_top4,
        "external_top3_cumulative_fraction": external_top3,
        "native_priority_subset_rate_assembly_ready": False,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": "native_type51_internal_block_then_type50_type71_external_rhs",
        "type53_scale44_status": "unresolved_exact_live_radiation_phint53_required_no_empirical_factor",
    }
    return {
        "summary": summary,
        "internal_family_rows": internal_rows,
        "external_family_rows": external_rows,
        "row_dominance_rows": row_dominance,
        "implementation_phases": implementation_phases,
    }


def write_priority_native_readiness_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    internal = out / "xstar_priority_native_readiness_audit_internal_families.csv"
    external = out / "xstar_priority_native_readiness_audit_external_rhs_families.csv"
    row_dom = out / "xstar_priority_native_readiness_audit_row_dominance.csv"
    phases = out / "xstar_priority_native_readiness_audit_implementation_phases.csv"
    json_path = out / "xstar_priority_native_readiness_audit.json"
    md_path = out / "xstar_priority_native_readiness_audit.md"
    _write_csv(internal, audit.get("internal_family_rows", []))
    _write_csv(external, audit.get("external_family_rows", []))
    _write_csv(row_dom, audit.get("row_dominance_rows", []))
    _write_csv(phases, audit.get("implementation_phases", []))
    json_path.write_text(json.dumps(dict(audit), indent=2, sort_keys=True), encoding="utf-8")
    summary = dict(audit.get("summary", {}))
    lines = [
        "# XSTAR priority native-assembly readiness audit",
        "",
        f"- Audit version: `{summary.get('audit_version', '')}`",
        f"- Ion: `{summary.get('ion', '')}`",
        f"- Selected compact rows: `{summary.get('selected_xstar_ipmat2_indices', '')}`",
        f"- Dominant internal family: `{summary.get('dominant_internal_family', '')}` ({float(summary.get('dominant_internal_family_fraction', 0.0)):.6%})",
        f"- Dominant external RHS family: `{summary.get('dominant_external_rhs_family', '')}` ({float(summary.get('dominant_external_rhs_family_fraction', 0.0)):.6%})",
        f"- External top-three cumulative influence: `{float(summary.get('external_top3_cumulative_fraction', 0.0)):.6%}`",
        "",
        "## Interpretation",
        "",
        "The probe-derived conditional solve is ready, but native assembly is not. "
        "The minimum implementation sequence is type 51 for the internal block, "
        "type 50 plus type 71 for the external RHS, then exact live-radiation type 53. "
        "The type-53 scale discrepancy must be removed by reproducing XSTAR `phint53`, not by an empirical factor.",
        "",
        "## Products",
        "",
        f"- `{internal.name}`",
        f"- `{external.name}`",
        f"- `{row_dom.name}`",
        f"- `{phases.name}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "internal_families_csv": str(internal),
        "external_rhs_families_csv": str(external),
        "row_dominance_csv": str(row_dom),
        "implementation_phases_csv": str(phases),
        "json": str(json_path),
        "markdown": str(md_path),
    }
