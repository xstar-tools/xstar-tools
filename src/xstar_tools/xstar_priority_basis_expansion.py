"""Prepare a staged high-population expansion of an XSTAR compact element basis.

This module consumes the full-element scaffold written by
``examples/87_build_xstar_full_element_basis_scaffold.py`` and activates the
smallest population-ranked subset of missing compact ``ipmat2`` rows needed to
reach a requested solved-population coverage.  Shared parent-continuum rows
remain one compact unknown with multiple physical roles.

The result is an activation manifest and closure plan.  It does not yet create
native matrix terms for the activated rows or alter the default solver.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


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


def _parse_explicit_indices(values: Iterable[int] | None) -> List[int]:
    if values is None:
        return []
    result: List[int] = []
    seen = set()
    for value in values:
        index = int(value)
        if index <= 0:
            raise ValueError("explicit XSTAR ipmat2 indices must be positive")
        if index not in seen:
            result.append(index)
            seen.add(index)
    return result


def _select_missing_rows(
    missing: Sequence[Mapping[str, Any]],
    *,
    current_coverage: float,
    target_population_coverage: float,
    max_additional_rows: int | None,
    explicit_xstar_ipmat2_indices: Sequence[int],
) -> List[Mapping[str, Any]]:
    by_ip = {
        int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0): row
        for row in missing
    }
    if explicit_xstar_ipmat2_indices:
        absent = [index for index in explicit_xstar_ipmat2_indices if index not in by_ip]
        if absent:
            raise ValueError(f"explicit rows are not missing scaffold rows: {absent}")
        return [by_ip[index] for index in explicit_xstar_ipmat2_indices]

    ordered = sorted(
        missing,
        key=lambda row: (
            _as_int(row.get("missing_priority_rank"), 10**9) or 10**9,
            -_as_float(row.get("xstar_after_population")),
            _as_int(row.get("xstar_ipmat2_index"), 0) or 0,
        ),
    )
    selected: List[Mapping[str, Any]] = []
    coverage = current_coverage
    for row in ordered:
        if coverage >= target_population_coverage:
            break
        if max_additional_rows is not None and len(selected) >= max_additional_rows:
            break
        selected.append(row)
        coverage += max(0.0, _as_float(row.get("xstar_after_population")))
    return selected


def build_priority_basis_expansion(
    *,
    full_element_basis_scaffold: str | Path,
    target_population_coverage: float = 0.999999,
    max_additional_rows: int | None = None,
    explicit_xstar_ipmat2_indices: Sequence[int] | None = None,
) -> Dict[str, Any]:
    """Build a staged activation manifest for the highest-impact missing rows."""
    if not 0.0 < target_population_coverage <= 1.0:
        raise ValueError("target_population_coverage must be in (0, 1]")
    if max_additional_rows is not None and max_additional_rows < 0:
        raise ValueError("max_additional_rows must be non-negative")

    root = Path(full_element_basis_scaffold)
    scaffold_path = _resolve_product(root, "xstar_full_element_basis_scaffold.csv")
    priority_path = _resolve_product(root, "xstar_full_element_basis_scaffold_missing_priority.csv")
    block_path = _resolve_product(root, "xstar_full_element_basis_scaffold_ion_block_summary.csv")
    json_path = _resolve_product(root, "xstar_full_element_basis_scaffold.json")

    scaffold = _read_csv(scaffold_path)
    missing_priority = _read_csv(priority_path)
    ion_blocks = _read_csv(block_path)
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    prior_summary = dict(metadata.get("summary", {}))

    current_coverage = _as_float(prior_summary.get("current_population_coverage"))
    explicit = _parse_explicit_indices(explicit_xstar_ipmat2_indices)
    selected_source = _select_missing_rows(
        missing_priority,
        current_coverage=current_coverage,
        target_population_coverage=target_population_coverage,
        max_additional_rows=max_additional_rows,
        explicit_xstar_ipmat2_indices=explicit,
    )
    selected_ips = {
        int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0)
        for row in selected_source
    }
    selected_population = sum(
        max(0.0, _as_float(row.get("xstar_after_population")))
        for row in selected_source
    )
    achieved_coverage = min(1.0, current_coverage + selected_population)

    compact_rows: List[Dict[str, Any]] = []
    activation_rows: List[Dict[str, Any]] = []
    alias_rows: List[Dict[str, Any]] = []
    deferred_rows: List[Dict[str, Any]] = []
    block_accumulator: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
        "selected_rows": [],
        "selected_population": 0.0,
        "selected_shared_rows": 0,
        "selected_single_rows": 0,
    })

    selection_order = {
        int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0): index + 1
        for index, row in enumerate(selected_source)
    }

    for row in sorted(scaffold, key=lambda item: _as_int(item.get("xstar_ipmat2_index"), 0) or 0):
        ip = int(_as_int(row.get("xstar_ipmat2_index"), 0) or 0)
        was_existing = str(row.get("basis_row_status", "")) == "existing_python_row"
        activated = ip in selected_ips
        status = "existing_python_row" if was_existing else "activated_priority_row" if activated else "deferred_missing_row"
        active = was_existing or activated
        compact = dict(row)
        compact.update({
            "priority_expansion_status": status,
            "active_in_priority_basis": active,
            "activation_order": selection_order.get(ip, ""),
            "native_matrix_terms_ready": was_existing,
            "native_matrix_terms_required": activated,
        })
        compact_rows.append(compact)

        if activated:
            nionp = int(_as_int(row.get("primary_nionp_current"), -1) or -1)
            shared = "parent_continuum_shared" in str(row.get("sharing_class", ""))
            closure_action = (
                "preserve one compact unknown for parent-continuum and next-ion-ground roles; "
                "assemble all matrix terms touching both physical roles"
                if shared
                else "assemble all intra-ion and adjacent-ion matrix terms touching this compact row"
            )
            activation = {
                "activation_order": selection_order[ip],
                "xstar_ipmat2_index": ip,
                "proposed_python_global_index": row.get("proposed_primary_python_global_index", ""),
                "xstar_after_population": _as_float(row.get("xstar_after_population")),
                "cumulative_population_coverage": min(
                    1.0,
                    current_coverage + sum(
                        max(0.0, _as_float(source.get("xstar_after_population")))
                        for source in selected_source[: selection_order[ip]]
                    ),
                ),
                "primary_nionp_current": nionp,
                "primary_ml_ion": row.get("primary_ml_ion", ""),
                "primary_klion": row.get("primary_klion", ""),
                "primary_jkk_ion": row.get("primary_jkk_ion", ""),
                "primary_local_level_index": row.get("primary_local_level_index", ""),
                "row_kinds": row.get("row_kinds", ""),
                "sharing_class": row.get("sharing_class", ""),
                "population_role_nionp": row.get("population_role_nionp", ""),
                "population_role_local_level_index": row.get("population_role_local_level_index", ""),
                "parent_role_nionp": row.get("parent_role_nionp", ""),
                "parent_role_local_level_index": row.get("parent_role_local_level_index", ""),
                "closure_action": closure_action,
                "basis_row_instantiated": True,
                "native_matrix_terms_ready": False,
            }
            activation_rows.append(activation)
            accumulator = block_accumulator[nionp]
            accumulator["selected_rows"].append(ip)
            accumulator["selected_population"] += _as_float(row.get("xstar_after_population"))
            accumulator["selected_shared_rows"] += int(shared)
            accumulator["selected_single_rows"] += int(not shared)
        elif not was_existing:
            deferred_rows.append({
                "missing_priority_rank": row.get("missing_priority_rank", ""),
                "xstar_ipmat2_index": ip,
                "xstar_after_population": _as_float(row.get("xstar_after_population")),
                "primary_nionp_current": row.get("primary_nionp_current", ""),
                "primary_local_level_index": row.get("primary_local_level_index", ""),
                "row_kinds": row.get("row_kinds", ""),
                "sharing_class": row.get("sharing_class", ""),
                "proposed_python_global_index": row.get("proposed_primary_python_global_index", ""),
            })

        if int(_as_int(row.get("role_count"), 1) or 1) > 1 or "parent_continuum_shared" in str(row.get("sharing_class", "")):
            alias_rows.append({
                "xstar_ipmat2_index": ip,
                "priority_expansion_status": status,
                "active_in_priority_basis": active,
                "mapped_python_global_indices": row.get("mapped_python_global_indices", ""),
                "proposed_primary_python_global_index": row.get("proposed_primary_python_global_index", ""),
                "population_role_nionp": row.get("population_role_nionp", ""),
                "population_role_local_level_index": row.get("population_role_local_level_index", ""),
                "parent_role_nionp": row.get("parent_role_nionp", ""),
                "parent_role_local_level_index": row.get("parent_role_local_level_index", ""),
                "final_slot": row.get("final_slot", ""),
                "alias_policy": "single_compact_unknown_multiple_physical_roles",
            })

    block_lookup = {
        int(_as_int(row.get("nionp_current"), -1) or -1): row
        for row in ion_blocks
    }
    closure_rows: List[Dict[str, Any]] = []
    for nionp in sorted(block_accumulator):
        values = block_accumulator[nionp]
        block = block_lookup.get(nionp, {})
        closure_rows.append({
            "nionp_current": nionp,
            "ml_ion": block.get("ml_ion", ""),
            "klion": block.get("klion", ""),
            "jkk_ion": block.get("jkk_ion", ""),
            "selected_xstar_ipmat2_indices": ";".join(str(value) for value in values["selected_rows"]),
            "n_selected_rows": len(values["selected_rows"]),
            "n_selected_shared_parent_rows": values["selected_shared_rows"],
            "n_selected_single_role_rows": values["selected_single_rows"],
            "selected_population": values["selected_population"],
            "required_native_work": (
                "build local level metadata; assemble record-complete matrix rows; "
                "retain compact parent-continuum aliases; include RHS/normalization closure"
            ),
            "native_matrix_closure_ready": False,
        })

    existing_python_rows = int(_as_int(prior_summary.get("n_existing_python_population_rows"), 0) or 0)
    existing_unique = int(_as_int(prior_summary.get("n_unique_xstar_rows_represented_by_python"), 0) or 0)
    target_met = achieved_coverage + 1e-15 >= target_population_coverage
    summary = {
        "audit_version": "v0.3.195",
        "status": "priority_basis_expansion_completed",
        "ion": prior_summary.get("ion", ""),
        "selected_basis_solve_call_id": prior_summary.get("selected_basis_solve_call_id", ""),
        "target_population_coverage": target_population_coverage,
        "selection_mode": "explicit-ipmat2" if explicit else "population-ranked",
        "max_additional_rows": max_additional_rows if max_additional_rows is not None else "",
        "current_population_coverage": current_coverage,
        "n_selected_missing_rows": len(selected_source),
        "selected_xstar_ipmat2_indices": ";".join(str(_as_int(row.get("xstar_ipmat2_index"), 0) or 0) for row in selected_source),
        "selected_population": selected_population,
        "achieved_population_coverage": achieved_coverage,
        "target_population_coverage_met": target_met,
        "n_selected_shared_parent_rows": sum("parent_continuum_shared" in str(row.get("sharing_class", "")) for row in selected_source),
        "n_selected_single_role_rows": sum("parent_continuum_shared" not in str(row.get("sharing_class", "")) for row in selected_source),
        "n_selected_nionp_blocks": len(block_accumulator),
        "selected_nionp_blocks": ";".join(str(value) for value in sorted(block_accumulator)),
        "n_active_python_population_identities": existing_python_rows + len(selected_source),
        "n_active_unique_compact_basis_rows": existing_unique + len(selected_source),
        "n_deferred_missing_rows": len(deferred_rows),
        "n_full_xstar_basis_rows": len(scaffold),
        "priority_basis_expansion_ready": bool(selected_source) and target_met,
        "native_priority_subset_matrix_closure_ready": False,
        "native_full_element_solver_ready": False,
        "dominant_next_target": "assemble_native_matrix_terms_for_selected_rows_and_shared_parent_continuum_closure",
    }
    return {
        "summary": summary,
        "priority_activation_rows": activation_rows,
        "expanded_compact_basis_rows": compact_rows,
        "alias_rows": alias_rows,
        "closure_requirement_rows": closure_rows,
        "deferred_rows": deferred_rows,
        "source_files": {
            "scaffold_csv": str(scaffold_path),
            "missing_priority_csv": str(priority_path),
            "ion_block_summary_csv": str(block_path),
            "scaffold_json": str(json_path),
        },
    }


def write_priority_basis_expansion(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    """Write CSV, JSON, and Markdown products for a priority expansion audit."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_priority_basis_expansion"
    paths = {
        "priority_activation_csv": out / f"{prefix}_activation_manifest.csv",
        "expanded_compact_basis_csv": out / f"{prefix}_compact_basis.csv",
        "alias_map_csv": out / f"{prefix}_alias_map.csv",
        "closure_requirements_csv": out / f"{prefix}_closure_requirements.csv",
        "deferred_rows_csv": out / f"{prefix}_deferred_rows.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["priority_activation_csv"], audit.get("priority_activation_rows", []))
    _write_csv(paths["expanded_compact_basis_csv"], audit.get("expanded_compact_basis_rows", []))
    _write_csv(paths["alias_map_csv"], audit.get("alias_rows", []))
    _write_csv(paths["closure_requirements_csv"], audit.get("closure_requirement_rows", []))
    _write_csv(paths["deferred_rows_csv"], audit.get("deferred_rows", []))
    paths["json"].write_text(json.dumps(dict(audit), indent=2, sort_keys=True), encoding="utf-8")

    summary = dict(audit.get("summary", {}))
    activation = list(audit.get("priority_activation_rows", []))
    closure = list(audit.get("closure_requirement_rows", []))
    lines = [
        "# XSTAR priority basis expansion",
        "",
        "This product activates the smallest high-population subset of missing XSTAR compact-basis rows needed for the requested population coverage. It preserves shared parent-continuum aliases but does not yet assemble native matrix terms for the new rows.",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- **{key}**: `{value}`")
    lines.extend(["", "## Activated rows", "", "| order | ipmat2 | nionp | local level | population | sharing |", "|---:|---:|---:|---:|---:|---|"])
    for row in activation:
        lines.append(
            f"| {row.get('activation_order', '')} | {row.get('xstar_ipmat2_index', '')} | "
            f"{row.get('primary_nionp_current', '')} | {row.get('primary_local_level_index', '')} | "
            f"{_as_float(row.get('xstar_after_population')):.12g} | {row.get('sharing_class', '')} |"
        )
    lines.extend(["", "## Native closure work by ion block", ""])
    for row in closure:
        lines.append(
            f"- `nionp={row.get('nionp_current')}`: rows `{row.get('selected_xstar_ipmat2_indices')}`; "
            f"{row.get('required_native_work')}"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "The selected rows are now explicit Python basis identities. Source-equivalent solving still requires record-complete matrix assembly, shared parent-continuum alias handling, and XSTAR-compatible RHS/normalization closure for these rows.",
        "",
    ])
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}
