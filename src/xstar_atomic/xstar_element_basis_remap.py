"""Reconstruct and apply XSTAR element ``ipmat2`` basis mappings.

The element-basis probe records the exact compact population-row topology built
inside ``calc_hmc_element.f90``.  This module selects one element solve, reduces
its possibly duplicated row roles to the unique ``ipmat2`` basis, and maps the
preserved Python solver rows by physical ion/local-level identity rather than by
sequential global index.

The key source-code identity is

``Python (ion_stage, level_index)``
    -> ``XSTAR (nionp_current, local_level_index)``
    -> compact ``xstar_ipmat2_index``.

Parent-continuum rows are intentionally retained as aliases.  For example, a
He-like continuum row and the H-like ground row can map to the same compact
XSTAR population row because ``calc_hmc_element`` advances ``ipmat2`` by
``nlev-1`` between adjacent ions.

Diagnostic only: no solver physics or default matrix assembly is changed.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .xstar_population_closure_parity import (
    _find_solver_product_paths,
    _load_python_population_rows,
    element_z_from_ion,
)


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return int(round(f))
    except Exception:
        return default


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or (isinstance(value, str) and not str(value).strip()):
            return default
        f = float(value)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def _read_csv(path: str | Path) -> List[Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for key in row:
                if key not in ordered:
                    ordered.append(str(key))
        fields = ordered or ["status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _resolve_csv(path: str | Path, default_name: str) -> Path:
    p = Path(path)
    if p.is_dir():
        direct = p / default_name
        if direct.exists():
            return direct
        hits = sorted(p.rglob(default_name))
        if hits:
            return hits[0]
        stem = default_name.removesuffix(".csv")
        hits = sorted(p.rglob(f"*{stem}*.csv"))
        if hits:
            return hits[0]
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p


def _select_basis_solve(
    rows: Sequence[Mapping[str, str]],
    *,
    element_z: int,
    occurrence_rank: int | None,
    basis_solve_call_id: int | None,
) -> Tuple[int, int, List[Dict[str, str]], List[Dict[str, Any]]]:
    by_sid: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        sid = _as_int(r.get("basis_solve_call_id"), None)
        ez = _as_int(r.get("element_z"), None)
        if sid is not None and ez == int(element_z):
            by_sid[sid].append(dict(r))
    sids = sorted(by_sid)
    if not sids:
        raise ValueError(f"no element-basis solves for element_z={element_z}")
    scan: List[Dict[str, Any]] = []
    for rank, sid in enumerate(sids, start=1):
        rr = by_sid[sid]
        positive = {
            _as_int(r.get("xstar_ipmat2_index"), None)
            for r in rr
            if (_as_int(r.get("xstar_ipmat2_index"), None) or 0) > 0
        }
        scan.append({
            "element_occurrence_rank": rank,
            "basis_solve_call_id": sid,
            "n_probe_rows": len(rr),
            "n_unique_positive_ipmat2_rows": len(positive),
            "max_xstar_ipmat2_index": max(positive) if positive else "",
            "n_ion_roles": sum(r.get("row_kind") == "ion_population_row" for r in rr),
            "n_parent_link_roles": sum(r.get("row_kind") == "ion_parent_continuum_link" for r in rr),
            "n_final_roles": sum(r.get("row_kind") == "final_parent_continuum_slot" for r in rr),
        })
    if basis_solve_call_id is not None:
        sid = int(basis_solve_call_id)
        if sid not in by_sid:
            raise ValueError(f"basis_solve_call_id={sid} is not an element_z={element_z} solve")
        rank = sids.index(sid) + 1
    elif occurrence_rank in (None, -1):
        sid = sids[-1]
        rank = len(sids)
    else:
        if occurrence_rank <= 0 or occurrence_rank > len(sids):
            raise ValueError(f"occurrence_rank must be 1..{len(sids)} or -1/latest")
        rank = int(occurrence_rank)
        sid = sids[rank - 1]
    return sid, rank, by_sid[sid], scan


def _build_unique_basis_rows(selected: Sequence[Mapping[str, str]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_ip: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for r in selected:
        ip = _as_int(r.get("xstar_ipmat2_index"), None)
        if ip is not None and ip > 0:
            by_ip[ip].append(dict(r))

    basis_rows: List[Dict[str, Any]] = []
    alias_rows: List[Dict[str, Any]] = []
    for ip in sorted(by_ip):
        roles = by_ip[ip]
        pop_roles = [r for r in roles if r.get("row_kind") == "ion_population_row"]
        parent_roles = [r for r in roles if r.get("row_kind") == "ion_parent_continuum_link"]
        final_roles = [r for r in roles if r.get("row_kind") == "final_parent_continuum_slot"]
        primary = (pop_roles or final_roles or parent_roles or roles)[0]
        kinds = sorted({str(r.get("row_kind") or "") for r in roles})
        pop_values = [_as_float(r.get("x_population"), None) for r in roles]
        pop_values = [v for v in pop_values if v is not None]
        pop_spread = (max(pop_values) - min(pop_values)) if pop_values else 0.0
        if pop_roles and parent_roles:
            sharing = "parent_continuum_shared_with_next_ion_population"
        elif parent_roles and final_roles:
            sharing = "parent_continuum_shared_with_final_closure_slot"
        elif len(roles) > 1:
            sharing = "multiple_probe_roles_same_compact_row"
        else:
            sharing = "single_role"
        row = {
            "xstar_ipmat2_index": ip,
            "role_count": len(roles),
            "row_kinds": ";".join(kinds),
            "sharing_class": sharing,
            "x_population_before_solve": _as_float(primary.get("x_population"), 0.0) or 0.0,
            "role_population_spread": pop_spread,
            "xstar_nion": primary.get("nion", ""),
            "xstar_nsup": primary.get("nsup", ""),
            "primary_nionp_current": primary.get("nionp_current", ""),
            "primary_ml_ion": primary.get("ml_ion", ""),
            "primary_klion": primary.get("klion", ""),
            "primary_jkk_ion": primary.get("jkk_ion", ""),
            "primary_local_level_index": primary.get("local_level_index", ""),
            "primary_element_ipmat_index": primary.get("element_ipmat_index", ""),
            "population_role_nionp": pop_roles[0].get("nionp_current", "") if pop_roles else "",
            "population_role_local_level_index": pop_roles[0].get("local_level_index", "") if pop_roles else "",
            "parent_role_nionp": parent_roles[0].get("nionp_current", "") if parent_roles else "",
            "parent_role_local_level_index": parent_roles[0].get("local_level_index", "") if parent_roles else "",
            "final_slot": bool(final_roles),
        }
        basis_rows.append(row)
        if len(roles) > 1:
            for r in roles:
                alias_rows.append({
                    "xstar_ipmat2_index": ip,
                    "sharing_class": sharing,
                    "row_kind": r.get("row_kind", ""),
                    "nionp_current": r.get("nionp_current", ""),
                    "nsp_current": r.get("nsp_current", ""),
                    "ml_ion": r.get("ml_ion", ""),
                    "klion": r.get("klion", ""),
                    "jkk_ion": r.get("jkk_ion", ""),
                    "nlev": r.get("nlev", ""),
                    "local_level_index": r.get("local_level_index", ""),
                    "element_ipmat_index": r.get("element_ipmat_index", ""),
                    "x_population": r.get("x_population", ""),
                })
    return basis_rows, alias_rows


def _build_ion_blocks(selected: Sequence[Mapping[str, str]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[int, int], List[Dict[str, str]]] = defaultdict(list)
    for r in selected:
        if r.get("row_kind") not in {"ion_population_row", "ion_parent_continuum_link"}:
            continue
        nionp = _as_int(r.get("nionp_current"), None)
        ml_ion = _as_int(r.get("ml_ion"), None)
        if nionp is not None and ml_ion is not None:
            groups[(nionp, ml_ion)].append(dict(r))
    out: List[Dict[str, Any]] = []
    for (nionp, ml_ion), rr in sorted(groups.items()):
        pops = [r for r in rr if r.get("row_kind") == "ion_population_row"]
        parents = [r for r in rr if r.get("row_kind") == "ion_parent_continuum_link"]
        first = rr[0]
        ips = [_as_int(r.get("xstar_ipmat2_index"), None) for r in rr]
        ips = [x for x in ips if x is not None]
        local = [_as_int(r.get("local_level_index"), None) for r in rr]
        local = [x for x in local if x is not None and x > 0]
        nlev = _as_int(first.get("nlev"), None)
        out.append({
            "nionp_current": nionp,
            "ml_ion": ml_ion,
            "klion": first.get("klion", ""),
            "jkk_ion": first.get("jkk_ion", ""),
            "nlev": nlev if nlev is not None else "",
            "ion_start_ipmat2_offset": first.get("ion_start_ipmat2", ""),
            "ion_start_ipmat_offset": first.get("ion_start_ipmat", ""),
            "compact_first_population_row": min(_as_int(r.get("xstar_ipmat2_index"), 10**9) or 10**9 for r in pops) if pops else "",
            "compact_last_population_row": max(_as_int(r.get("xstar_ipmat2_index"), 0) or 0 for r in pops) if pops else "",
            "parent_continuum_ipmat2_index": _as_int(parents[0].get("xstar_ipmat2_index"), None) if parents else "",
            "n_population_roles": len(pops),
            "n_parent_link_roles": len(parents),
            "local_level_min": min(local) if local else "",
            "local_level_max": max(local) if local else "",
            "expected_population_roles_nlev_minus_1": (nlev - 1) if nlev is not None else "",
            "block_role_count_matches_nlev": bool(nlev is not None and len(pops) == nlev - 1 and len(parents) == 1),
            "compact_role_span": (max(ips) - min(ips) + 1) if ips else "",
        })
    return out


def _load_after_populations(population_probe_csv: str | Path | None, solve_call_id: int) -> Dict[int, Dict[str, Any]]:
    if not population_probe_csv:
        return {}
    path = _resolve_csv(population_probe_csv, "xstar_population_closure_probe.csv")
    rows = _read_csv(path)
    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        if _as_int(r.get("solve_call_id"), None) != solve_call_id:
            continue
        if str(r.get("stage") or "") != "after_msolvelucy":
            continue
        ip = _as_int(r.get("level_index"), None)
        if ip is None:
            continue
        out[ip] = {
            "xstar_after_population": _as_float(r.get("x_population"), 0.0) or 0.0,
            "xstar_after_nion": _as_int(r.get("nion"), None),
            "xstar_after_nsup": _as_int(r.get("nsup"), None),
        }
    return out


def audit_element_basis_remap(
    *,
    benchmark_dir: str | Path,
    ion: str,
    element_basis_probe_csv: str | Path,
    population_probe_csv: str | Path | None = None,
    occurrence_rank: int | None = None,
    basis_solve_call_id: int | None = None,
) -> Dict[str, Any]:
    """Build the exact XSTAR compact-basis remap for preserved Python rows."""
    ez = element_z_from_ion(ion)
    basis_path = _resolve_csv(element_basis_probe_csv, "xstar_element_basis_probe.csv")
    raw = _read_csv(basis_path)
    sid, rank, selected, scan = _select_basis_solve(
        raw,
        element_z=ez,
        occurrence_rank=occurrence_rank,
        basis_solve_call_id=basis_solve_call_id,
    )
    basis_rows, alias_roles = _build_unique_basis_rows(selected)
    ion_blocks = _build_ion_blocks(selected)
    after = _load_after_populations(population_probe_csv, sid)
    for r in basis_rows:
        a = after.get(int(r["xstar_ipmat2_index"]), {})
        r.update(a)

    # Physical identity map.  Parent links are included, so continuum rows and
    # the next ion ground can intentionally alias the same compact row.
    role_map: Dict[Tuple[int, int], List[Dict[str, str]]] = defaultdict(list)
    for r in selected:
        if r.get("row_kind") not in {"ion_population_row", "ion_parent_continuum_link"}:
            continue
        stage = _as_int(r.get("nionp_current"), None)
        level = _as_int(r.get("local_level_index"), None)
        if stage is not None and level is not None and stage > 0 and level > 0:
            role_map[(stage, level)].append(dict(r))

    paths = _find_solver_product_paths(benchmark_dir, ion)
    py_rows = _load_python_population_rows(paths)
    remap_rows: List[Dict[str, Any]] = []
    unmapped_python: List[Dict[str, Any]] = []
    mapped_ips: List[int] = []
    current_correct = 0
    current_wrong = 0
    for p in py_rows:
        stage = _as_int(p.get("ion_stage"), None)
        level = _as_int(p.get("level_index"), None)
        matches = role_map.get((stage or -1, level or -1), [])
        if not matches:
            row = {
                "global_index": p.get("global_index", p.get("global_index_int", "")),
                "ion_stage": stage if stage is not None else "",
                "level_index": level if level is not None else "",
                "level_kind": p.get("level_kind", ""),
                "level_label": p.get("level_label", ""),
                "mapping_status": "no_xstar_basis_role_for_ion_stage_level_index",
            }
            unmapped_python.append(row)
            remap_rows.append(row)
            continue
        # The identity key should resolve to one role.  Preserve ambiguity if a
        # malformed probe ever records more than one candidate.
        m = matches[0]
        ip = _as_int(m.get("xstar_ipmat2_index"), None)
        current_ip = _as_int(p.get("xstar_ipmat2_index_int"), None)
        if ip is not None:
            mapped_ips.append(ip)
        if current_ip == ip:
            current_correct += 1
        else:
            current_wrong += 1
        mapping_status = (
            "matched_parent_continuum_link"
            if m.get("row_kind") == "ion_parent_continuum_link"
            else "matched_ion_population_row"
        )
        a = after.get(ip or -1, {})
        remap_rows.append({
            "global_index": p.get("global_index", p.get("global_index_int", "")),
            "ion_stage": stage if stage is not None else "",
            "level_index": level if level is not None else "",
            "level_kind": p.get("level_kind", ""),
            "level_label": p.get("level_label", ""),
            "is_continuum": p.get("is_continuum", ""),
            "is_superlevel": p.get("is_superlevel", ""),
            "python_population_fraction": p.get("python_population_fraction", ""),
            "old_xstar_ipmat2_index": current_ip if current_ip is not None else "",
            "corrected_xstar_ipmat2_index": ip if ip is not None else "",
            "old_mapping_matches_corrected": current_ip == ip,
            "mapping_status": mapping_status,
            "matched_xstar_row_kind": m.get("row_kind", ""),
            "matched_nionp_current": m.get("nionp_current", ""),
            "matched_ml_ion": m.get("ml_ion", ""),
            "matched_klion": m.get("klion", ""),
            "matched_jkk_ion": m.get("jkk_ion", ""),
            "matched_nlev": m.get("nlev", ""),
            "matched_local_level_index": m.get("local_level_index", ""),
            "matched_element_ipmat_index": m.get("element_ipmat_index", ""),
            "xstar_after_population": a.get("xstar_after_population", ""),
            "xstar_after_nion": a.get("xstar_after_nion", ""),
            "xstar_after_nsup": a.get("xstar_after_nsup", ""),
        })

    by_mapped_ip: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in remap_rows:
        ip = _as_int(r.get("corrected_xstar_ipmat2_index"), None)
        if ip is not None:
            by_mapped_ip[ip].append(r)
    python_alias_groups: List[Dict[str, Any]] = []
    for ip, rr in sorted(by_mapped_ip.items()):
        if len(rr) <= 1:
            continue
        python_alias_groups.append({
            "corrected_xstar_ipmat2_index": ip,
            "n_python_rows": len(rr),
            "python_global_indices": ";".join(str(r.get("global_index", "")) for r in rr),
            "python_ion_stage_level": ";".join(f"{r.get('ion_stage')}:{r.get('level_index')}" for r in rr),
            "python_level_labels": ";".join(str(r.get("level_label", "")) for r in rr),
            "alias_class": "multiple_python_roles_share_one_xstar_compact_population_row",
        })

    represented = set(mapped_ips)
    unrepresented_basis = [r for r in basis_rows if int(r["xstar_ipmat2_index"]) not in represented]
    total_after = sum(float(v.get("xstar_after_population", 0.0) or 0.0) for v in after.values()) if after else None
    mapped_after = sum(float(after.get(ip, {}).get("xstar_after_population", 0.0) or 0.0) for ip in represented) if after else None
    unrepresented_after = (total_after - mapped_after) if total_after is not None and mapped_after is not None else None

    expected_rows = max((int(r["xstar_ipmat2_index"]) for r in basis_rows), default=0)
    exact_basis_ready = len(basis_rows) == expected_rows and all(int(r["xstar_ipmat2_index"]) == i for i, r in enumerate(basis_rows, 1))
    python_remap_ready = len(unmapped_python) == 0 and len(remap_rows) == len(py_rows)
    summary: Dict[str, Any] = {
        "audit_version": "v0.3.193",
        "status": "element_basis_remap_audit_completed",
        "ion": ion,
        "selected_element_z": ez,
        "selection": "basis-solve-call-id" if basis_solve_call_id is not None else ("latest" if occurrence_rank in (None, -1) else "occurrence-rank"),
        "occurrence_rank": rank,
        "selected_basis_solve_call_id": sid,
        "element_basis_probe_csv": str(basis_path),
        "population_probe_csv": str(population_probe_csv or ""),
        "n_selected_probe_role_rows": len(selected),
        "n_unique_xstar_basis_rows": len(basis_rows),
        "max_xstar_ipmat2_index": expected_rows,
        "n_ion_blocks": len(ion_blocks),
        "n_xstar_alias_role_rows": len(alias_roles),
        "n_xstar_compact_rows_with_multiple_roles": sum(int(r.get("role_count", 0)) > 1 for r in basis_rows),
        "n_python_population_rows": len(py_rows),
        "n_python_rows_mapped_by_ion_stage_level": len(py_rows) - len(unmapped_python),
        "n_python_rows_unmapped": len(unmapped_python),
        "n_unique_xstar_rows_represented_by_python": len(represented),
        "n_python_alias_groups": len(python_alias_groups),
        "n_old_python_ipmat2_indices_already_correct": current_correct,
        "n_old_python_ipmat2_indices_requiring_remap": current_wrong,
        "n_xstar_basis_rows_not_represented_by_python": len(unrepresented_basis),
        "xstar_after_population_total": total_after if total_after is not None else "",
        "xstar_after_population_on_corrected_python_mapped_rows": mapped_after if mapped_after is not None else "",
        "xstar_after_population_on_unrepresented_basis_rows": unrepresented_after if unrepresented_after is not None else "",
        "xstar_unrepresented_population_fraction_of_total": (unrepresented_after / total_after) if total_after not in (None, 0.0) and unrepresented_after is not None else "",
        "exact_xstar_basis_reconstruction_ready": exact_basis_ready,
        "python_to_xstar_basis_remap_ready": python_remap_ready,
        "source_equivalent_basis_mapping_ready": bool(exact_basis_ready and python_remap_ready),
        "dominant_next_target": "apply_corrected_ipmat2_remap_then_build_missing_full_element_rows" if python_remap_ready else "resolve_unmapped_python_level_identity",
    }
    return {
        "summary": summary,
        "basis_solve_scan": scan,
        "xstar_basis_rows": basis_rows,
        "xstar_ion_blocks": ion_blocks,
        "xstar_alias_roles": alias_roles,
        "python_remap_rows": remap_rows,
        "python_unmapped_rows": unmapped_python,
        "python_alias_groups": python_alias_groups,
        "xstar_unrepresented_rows": unrepresented_basis,
    }


def write_element_basis_remap_products(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "basis_solve_scan_csv": out / "xstar_element_basis_remap_audit_basis_solve_scan.csv",
        "xstar_basis_rows_csv": out / "xstar_element_basis_remap_audit_xstar_basis_rows.csv",
        "xstar_ion_blocks_csv": out / "xstar_element_basis_remap_audit_xstar_ion_blocks.csv",
        "xstar_alias_roles_csv": out / "xstar_element_basis_remap_audit_xstar_alias_roles.csv",
        "python_remap_csv": out / "xstar_element_basis_remap_audit_python_remap.csv",
        "python_unmapped_csv": out / "xstar_element_basis_remap_audit_python_unmapped.csv",
        "python_alias_groups_csv": out / "xstar_element_basis_remap_audit_python_alias_groups.csv",
        "xstar_unrepresented_rows_csv": out / "xstar_element_basis_remap_audit_xstar_unrepresented_rows.csv",
        "json": out / "xstar_element_basis_remap_audit.json",
        "markdown": out / "xstar_element_basis_remap_audit.md",
    }
    _write_csv(paths["basis_solve_scan_csv"], audit.get("basis_solve_scan", []) or [])
    _write_csv(paths["xstar_basis_rows_csv"], audit.get("xstar_basis_rows", []) or [])
    _write_csv(paths["xstar_ion_blocks_csv"], audit.get("xstar_ion_blocks", []) or [])
    _write_csv(paths["xstar_alias_roles_csv"], audit.get("xstar_alias_roles", []) or [])
    _write_csv(paths["python_remap_csv"], audit.get("python_remap_rows", []) or [])
    _write_csv(paths["python_unmapped_csv"], audit.get("python_unmapped_rows", []) or [])
    _write_csv(paths["python_alias_groups_csv"], audit.get("python_alias_groups", []) or [])
    _write_csv(paths["xstar_unrepresented_rows_csv"], audit.get("xstar_unrepresented_rows", []) or [])
    paths["json"].write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    s = dict(audit.get("summary", {}) or {})
    lines = [
        "# XSTAR element-basis remap audit",
        "",
        f"audit_version: `{s.get('audit_version')}`",
        f"status: `{s.get('status')}`",
        "",
        "This audit reconstructs the compact XSTAR element basis from the direct `calc_hmc_element` probe and maps Python rows by `(ion_stage, level_index)` to `(nionp_current, local_level_index)`.",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "ion", "selected_basis_solve_call_id", "occurrence_rank",
        "n_unique_xstar_basis_rows", "max_xstar_ipmat2_index", "n_ion_blocks",
        "n_python_population_rows", "n_python_rows_mapped_by_ion_stage_level",
        "n_python_rows_unmapped", "n_unique_xstar_rows_represented_by_python",
        "n_python_alias_groups", "n_old_python_ipmat2_indices_requiring_remap",
        "n_xstar_basis_rows_not_represented_by_python",
        "xstar_after_population_on_corrected_python_mapped_rows",
        "xstar_after_population_on_unrepresented_basis_rows",
        "xstar_unrepresented_population_fraction_of_total",
        "exact_xstar_basis_reconstruction_ready", "python_to_xstar_basis_remap_ready",
        "source_equivalent_basis_mapping_ready", "dominant_next_target",
    ]:
        lines.append(f"- {key}: `{s.get(key)}`")
    lines += [
        "",
        "## Interpretation",
        "",
        "Parent-continuum aliases are expected XSTAR topology, not duplicate populations.  Multiple Python rows may therefore map to one compact `ipmat2` row.",
        "",
        "Diagnostic only; no solver physics changed.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
