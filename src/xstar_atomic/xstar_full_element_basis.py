"""Build a source-aligned full-element population-basis scaffold.

This module consumes the products from ``examples/86_audit_xstar_element_basis_remap.py``
and turns the reconstructed compact XSTAR ``ipmat2`` topology into an explicit Python
basis scaffold.  Existing Python rows retain their identities; unrepresented XSTAR
rows receive deterministic placeholder indices and implementation priorities based on
the solved XSTAR population carried by each compact row.

The scaffold is intentionally diagnostic/preparatory.  It does not yet assemble native
rates for missing lower-ion rows or change the default element solver.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        return int(round(f)) if math.isfinite(f) else default
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _resolve_product(path: str | Path, default_name: str) -> Path:
    p = Path(path)
    if p.is_file():
        if p.name == default_name:
            return p
        if p.suffix.lower() == ".json" and default_name.endswith(".json"):
            return p
    if p.is_dir():
        direct = p / default_name
        if direct.exists():
            return direct
        hits = sorted(p.rglob(default_name))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"could not find {default_name} under {p}")


def _coverage_tiers(current: float, missing_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    thresholds = [0.999, 0.9999, 0.99999, 0.999999, 0.9999999, 1.0 - 1e-12]
    ordered = sorted(missing_rows, key=lambda r: (-_as_float(r.get("xstar_after_population")), _as_int(r.get("xstar_ipmat2_index"), 0) or 0))
    rows: List[Dict[str, Any]] = []
    for target in thresholds:
        cumulative = current
        selected: List[Mapping[str, Any]] = []
        for row in ordered:
            if cumulative >= target:
                break
            pop = max(0.0, _as_float(row.get("xstar_after_population")))
            if pop <= 0.0:
                continue
            cumulative += pop
            selected.append(row)
        rows.append({
            "target_total_population_coverage": target,
            "current_total_population_coverage": current,
            "n_additional_rows_required": len(selected),
            "additional_population_added": sum(_as_float(r.get("xstar_after_population")) for r in selected),
            "achieved_total_population_coverage": min(cumulative, 1.0),
            "required_xstar_ipmat2_indices": ";".join(str(_as_int(r.get("xstar_ipmat2_index"), 0)) for r in selected),
            "required_nionp_blocks": ";".join(sorted({str(_as_int(r.get("primary_nionp_current"), -1)) for r in selected})),
        })
    return rows


def build_full_element_basis_scaffold(
    *,
    element_basis_remap_audit: str | Path,
    priority_population_threshold: float = 1.0e-12,
) -> Dict[str, Any]:
    """Build a 1:1 compact-basis scaffold from an element-basis remap audit."""
    root = Path(element_basis_remap_audit)
    basis_path = _resolve_product(root, "xstar_element_basis_remap_audit_xstar_basis_rows.csv")
    remap_path = _resolve_product(root, "xstar_element_basis_remap_audit_python_remap.csv")
    ion_blocks_path = _resolve_product(root, "xstar_element_basis_remap_audit_xstar_ion_blocks.csv")
    alias_path = _resolve_product(root, "xstar_element_basis_remap_audit_xstar_alias_roles.csv")
    json_path = _resolve_product(root, "xstar_element_basis_remap_audit.json")

    basis = _read_csv(basis_path)
    remap = _read_csv(remap_path)
    ion_blocks = _read_csv(ion_blocks_path)
    aliases = _read_csv(alias_path)
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    prior_summary = dict(meta.get("summary", {}))

    mapped_by_ip: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    max_global = -1
    for row in remap:
        ip = _as_int(row.get("corrected_xstar_ipmat2_index"), None)
        gi = _as_int(row.get("global_index"), None)
        if gi is not None:
            max_global = max(max_global, gi)
        if ip is not None:
            mapped_by_ip[ip].append(row)

    missing_basis = [r for r in basis if (_as_int(r.get("xstar_ipmat2_index"), -1) or -1) not in mapped_by_ip]
    missing_sorted = sorted(missing_basis, key=lambda r: (-_as_float(r.get("xstar_after_population")), _as_int(r.get("xstar_ipmat2_index"), 0) or 0))
    missing_rank = {int(_as_int(r.get("xstar_ipmat2_index"), 0) or 0): i + 1 for i, r in enumerate(missing_sorted)}
    placeholder_index: Dict[int, int] = {}
    next_index = max_global + 1
    for row in sorted(missing_basis, key=lambda r: _as_int(r.get("xstar_ipmat2_index"), 0) or 0):
        ip = int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0)
        placeholder_index[ip] = next_index
        next_index += 1

    scaffold: List[Dict[str, Any]] = []
    missing_priority: List[Dict[str, Any]] = []
    current_mapped_population = sum(_as_float(r.get("xstar_after_population")) for r in basis if (_as_int(r.get("xstar_ipmat2_index"), -1) or -1) in mapped_by_ip)
    running_total = current_mapped_population
    for row in missing_sorted:
        running_total += max(0.0, _as_float(row.get("xstar_after_population")))
        ip = int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0)
        missing_priority.append({
            "missing_priority_rank": missing_rank[ip],
            "xstar_ipmat2_index": ip,
            "xstar_after_population": _as_float(row.get("xstar_after_population")),
            "cumulative_total_population_coverage_if_added": min(running_total, 1.0),
            "primary_nionp_current": row.get("primary_nionp_current", ""),
            "primary_local_level_index": row.get("primary_local_level_index", ""),
            "row_kinds": row.get("row_kinds", ""),
            "sharing_class": row.get("sharing_class", ""),
            "proposed_python_global_index": placeholder_index[ip],
            "priority_class": (
                "required_high_population_closure"
                if _as_float(row.get("xstar_after_population")) >= 1.0e-4
                else "required_nonzero_closure"
                if _as_float(row.get("xstar_after_population")) > priority_population_threshold
                else "low_population_or_zero_scaffold"
            ),
        })

    for row in sorted(basis, key=lambda r: _as_int(r.get("xstar_ipmat2_index"), 0) or 0):
        ip = int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0)
        mapped = mapped_by_ip.get(ip, [])
        represented = bool(mapped)
        gis = [_as_int(r.get("global_index"), None) for r in mapped]
        gis = [x for x in gis if x is not None]
        scaffold.append({
            "xstar_ipmat2_index": ip,
            "basis_row_status": "existing_python_row" if represented else "missing_python_placeholder",
            "proposed_primary_python_global_index": min(gis) if gis else placeholder_index[ip],
            "mapped_python_row_count": len(mapped),
            "mapped_python_global_indices": ";".join(str(x) for x in sorted(gis)),
            "mapped_python_ion_stages": ";".join(str(x) for x in sorted({_as_int(r.get("ion_stage"), -1) for r in mapped})),
            "mapped_python_level_indices": ";".join(str(x) for x in sorted({_as_int(r.get("level_index"), -1) for r in mapped})),
            "mapped_python_level_labels": ";".join(str(r.get("level_label", "")) for r in mapped),
            "requires_new_python_row": not represented,
            "missing_priority_rank": "" if represented else missing_rank[ip],
            "xstar_after_population": _as_float(row.get("xstar_after_population")),
            "row_kinds": row.get("row_kinds", ""),
            "sharing_class": row.get("sharing_class", ""),
            "role_count": row.get("role_count", ""),
            "primary_nionp_current": row.get("primary_nionp_current", ""),
            "primary_ml_ion": row.get("primary_ml_ion", ""),
            "primary_klion": row.get("primary_klion", ""),
            "primary_jkk_ion": row.get("primary_jkk_ion", ""),
            "primary_local_level_index": row.get("primary_local_level_index", ""),
            "population_role_nionp": row.get("population_role_nionp", ""),
            "population_role_local_level_index": row.get("population_role_local_level_index", ""),
            "parent_role_nionp": row.get("parent_role_nionp", ""),
            "parent_role_local_level_index": row.get("parent_role_local_level_index", ""),
            "final_slot": row.get("final_slot", ""),
        })

    # Summarize compact blocks by nionp using the exact block metadata.
    block_summary: List[Dict[str, Any]] = []
    basis_by_ip = {int(_as_int(r.get("xstar_ipmat2_index"), 0) or 0): r for r in basis}
    for block in ion_blocks:
        nionp = _as_int(block.get("nionp_current"), -1) or -1
        start = _as_int(block.get("compact_first_population_row"), 0) or 0
        end = _as_int(block.get("parent_continuum_ipmat2_index"), 0) or 0
        exclusive_ips = list(range(start, end)) if start > 0 and end >= start else []
        parent_ip = end if end > 0 else None
        inclusive_ips = exclusive_ips + ([parent_ip] if parent_ip is not None else [])
        exclusive_pop = sum(_as_float(basis_by_ip.get(ip, {}).get("xstar_after_population")) for ip in exclusive_ips)
        parent_pop = _as_float(basis_by_ip.get(parent_ip, {}).get("xstar_after_population")) if parent_ip is not None else 0.0
        represented_exclusive = [ip for ip in exclusive_ips if ip in mapped_by_ip]
        exclusive_mapped_pop = sum(_as_float(basis_by_ip.get(ip, {}).get("xstar_after_population")) for ip in represented_exclusive)
        parent_represented = bool(parent_ip in mapped_by_ip) if parent_ip is not None else False
        block_summary.append({
            "nionp_current": nionp,
            "ml_ion": block.get("ml_ion", ""),
            "klion": block.get("klion", ""),
            "jkk_ion": block.get("jkk_ion", ""),
            "nlev": block.get("nlev", ""),
            "compact_first_exclusive_row": start,
            "compact_last_exclusive_row": end - 1 if end >= start else "",
            "shared_parent_continuum_row": parent_ip if parent_ip is not None else "",
            "n_exclusive_compact_rows": len(exclusive_ips),
            "n_exclusive_rows_represented_by_python": len(represented_exclusive),
            "n_exclusive_rows_missing_from_python": len(exclusive_ips) - len(represented_exclusive),
            "shared_parent_row_represented_by_python": parent_represented,
            "xstar_population_in_exclusive_rows": exclusive_pop,
            "xstar_population_on_python_exclusive_rows": exclusive_mapped_pop,
            "xstar_population_missing_from_exclusive_rows": max(0.0, exclusive_pop - exclusive_mapped_pop),
            "exclusive_block_population_coverage": (exclusive_mapped_pop / exclusive_pop) if exclusive_pop > 0 else 1.0,
            "xstar_population_in_shared_parent_row": parent_pop,
            "note": "shared parent row is also the next ion ground row (or final closure slot) and is not added to exclusive block totals",
        })

    tiers = _coverage_tiers(current_mapped_population, missing_basis)
    missing_pop = sum(_as_float(r.get("xstar_after_population")) for r in missing_basis)
    nonzero_missing = sum(_as_float(r.get("xstar_after_population")) > priority_population_threshold for r in missing_basis)
    high_missing = sum(_as_float(r.get("xstar_after_population")) >= 1.0e-4 for r in missing_basis)
    summary = {
        "audit_version": "v0.3.194",
        "status": "full_element_basis_scaffold_completed",
        "ion": prior_summary.get("ion", ""),
        "selected_basis_solve_call_id": prior_summary.get("selected_basis_solve_call_id", ""),
        "n_full_xstar_basis_rows": len(basis),
        "n_existing_python_population_rows": len(remap),
        "n_unique_xstar_rows_represented_by_python": len(mapped_by_ip),
        "n_missing_python_basis_rows": len(missing_basis),
        "n_missing_rows_above_population_threshold": nonzero_missing,
        "n_high_population_missing_rows": high_missing,
        "current_population_coverage": current_mapped_population,
        "missing_population_fraction": missing_pop,
        "max_missing_row_ipmat2": _as_int(missing_sorted[0].get("xstar_ipmat2_index"), None) if missing_sorted else None,
        "max_missing_row_population": _as_float(missing_sorted[0].get("xstar_after_population")) if missing_sorted else 0.0,
        "n_shared_alias_rows": len({(_as_int(r.get("xstar_ipmat2_index"), -1) or -1) for r in aliases}),
        "proposed_total_python_rows_after_expansion": len(remap) + len(missing_basis),
        "proposed_unique_compact_basis_rows": len(basis),
        "full_element_basis_scaffold_ready": len(basis) > 0 and len(scaffold) == len(basis),
        "native_full_element_solver_ready": False,
        "dominant_next_target": "instantiate_missing_basis_rows_and_assemble_adjacent_ion_parent_superlevel_closure",
    }
    return {
        "summary": summary,
        "full_basis_scaffold_rows": scaffold,
        "missing_priority_rows": missing_priority,
        "ion_block_summary_rows": block_summary,
        "coverage_tier_rows": tiers,
        "source_files": {
            "xstar_basis_rows_csv": str(basis_path),
            "python_remap_csv": str(remap_path),
            "xstar_ion_blocks_csv": str(ion_blocks_path),
            "xstar_alias_roles_csv": str(alias_path),
        },
    }


def write_full_element_basis_scaffold(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_full_element_basis_scaffold"
    paths = {
        "full_basis_scaffold_csv": out / f"{prefix}.csv",
        "missing_priority_csv": out / f"{prefix}_missing_priority.csv",
        "ion_block_summary_csv": out / f"{prefix}_ion_block_summary.csv",
        "coverage_tiers_csv": out / f"{prefix}_coverage_tiers.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["full_basis_scaffold_csv"], audit.get("full_basis_scaffold_rows", []))
    _write_csv(paths["missing_priority_csv"], audit.get("missing_priority_rows", []))
    _write_csv(paths["ion_block_summary_csv"], audit.get("ion_block_summary_rows", []))
    _write_csv(paths["coverage_tiers_csv"], audit.get("coverage_tier_rows", []))
    paths["json"].write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")

    s = audit.get("summary", {})
    lines = [
        "# XSTAR full-element basis scaffold",
        "",
        f"- Audit version: `{s.get('audit_version')}`",
        f"- Ion benchmark: `{s.get('ion')}`",
        f"- Full compact XSTAR basis rows: `{s.get('n_full_xstar_basis_rows')}`",
        f"- Existing Python population rows: `{s.get('n_existing_python_population_rows')}`",
        f"- Unique XSTAR rows already represented: `{s.get('n_unique_xstar_rows_represented_by_python')}`",
        f"- Missing Python basis rows: `{s.get('n_missing_python_basis_rows')}`",
        f"- Current solved-population coverage: `{s.get('current_population_coverage')}`",
        f"- Missing solved-population fraction: `{s.get('missing_population_fraction')}`",
        "",
        "## Interpretation",
        "",
        "The corrected physical remap is ready.  The scaffold now supplies one explicit Python-side row assignment for every compact XSTAR `ipmat2` row, while retaining shared parent-continuum aliases.  Missing rows are placeholders only; native rates and closure terms still need to be assembled before the default solver can use the expanded basis.",
        "",
        f"Next target: `{s.get('dominant_next_target')}`.",
        "",
        "## Products",
        "",
        f"- `{paths['full_basis_scaffold_csv'].name}`",
        f"- `{paths['missing_priority_csv'].name}`",
        f"- `{paths['ion_block_summary_csv'].name}`",
        f"- `{paths['coverage_tiers_csv'].name}`",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
