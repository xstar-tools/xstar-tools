"""Diagnose XSTAR element-population basis mapping gaps.

The population-closure parity audit compares XSTAR's full element ``ipmat2``
population vector against the current Python local population basis.  When most
of the XSTAR population lives in rows without a Python mapping, the next issue
is not a rate formula; it is the mapping/topology between the Python basis and
XSTAR's element-level ``indb``/``ilev`` basis.

This module consumes a population-closure parity audit directory (or its CSVs)
and summarizes where the missing population lives in XSTAR's ``nion``/``nsup``
blocks, which Python rows are currently mapped to which XSTAR blocks, and what
implementation step should happen next.

Diagnostic only: no solver physics is changed.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


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


def _read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
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


def _resolve_audit_file(path: str | Path, filename: str) -> Path:
    p = Path(path)
    if p.is_dir():
        direct = p / filename
        if direct.exists():
            return direct
        hits = sorted(p.rglob(filename))
        if hits:
            return hits[0]
        stem = filename.replace(".csv", "")
        hits = sorted(p.rglob(f"*{stem}*.csv"))
        if hits:
            return hits[0]
        raise FileNotFoundError(f"{filename} not found under {p}")
    if p.name == filename or p.name.endswith(filename):
        return p
    raise FileNotFoundError(f"cannot resolve {filename} from {p}")


def _resolve_json(path: str | Path) -> Optional[Path]:
    p = Path(path)
    if p.is_dir():
        direct = p / "xstar_population_closure_parity_audit.json"
        if direct.exists():
            return direct
        hits = sorted(p.rglob("xstar_population_closure_parity_audit.json"))
        if hits:
            return hits[0]
    elif p.suffix.lower() == ".json" and p.exists():
        return p
    return None


def _classify_block(nion: Optional[int], nsup: Optional[int], population_sum: float, mapped: bool) -> str:
    if nion is None or nsup is None:
        return "unknown_block"
    if population_sum > 0.1:
        return "dominant_population_block"
    if population_sum > 1e-4:
        return "important_population_block"
    if mapped:
        return "current_python_mapped_block"
    if population_sum > 1e-10:
        return "minor_nonzero_block"
    return "trace_or_zero_block"


def diagnose_population_basis_mapping(
    *,
    population_closure_parity_audit: str | Path,
    population_fraction_threshold: float = 1e-4,
) -> Dict[str, Any]:
    """Summarize basis-mapping gaps from a population-closure parity audit.

    Parameters
    ----------
    population_closure_parity_audit:
        Directory containing ``xstar_population_closure_parity_audit_*.csv``
        products, or a path resolvable to those products.
    population_fraction_threshold:
        Population fraction above which a missing XSTAR block is treated as a
        high-priority basis closure gap.
    """
    root = Path(population_closure_parity_audit)
    overlap_csv = _resolve_audit_file(root, "xstar_population_closure_parity_audit_overlap_rows.csv")
    unmapped_csv = _resolve_audit_file(root, "xstar_population_closure_parity_audit_unmapped_xstar_rows.csv")
    scan_csv = _resolve_audit_file(root, "xstar_population_closure_parity_audit_capture_scan.csv")
    json_path = _resolve_json(root)

    summary_in: Dict[str, Any] = {}
    if json_path and json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as fh:
                summary_in = dict((json.load(fh) or {}).get("summary", {}) or {})
        except Exception:
            summary_in = {}

    overlap = _read_csv_rows(overlap_csv)
    unmapped = _read_csv_rows(unmapped_csv)
    scan = _read_csv_rows(scan_csv)

    # Block summary over both mapped and unmapped rows, keyed by XSTAR basis
    # metadata.  This intentionally does not equate Python ion_stage with XSTAR
    # nion; the audit has shown that such an equation is the likely mapping bug.
    blocks: Dict[Tuple[Optional[int], Optional[int]], Dict[str, Any]] = {}

    def ensure_block(nion: Optional[int], nsup: Optional[int]) -> Dict[str, Any]:
        key = (nion, nsup)
        if key not in blocks:
            blocks[key] = {
                "xstar_nion": nion if nion is not None else "",
                "xstar_nsup": nsup if nsup is not None else "",
                "n_xstar_rows": 0,
                "n_xstar_nonzero_rows": 0,
                "xstar_population_sum_after": 0.0,
                "xstar_population_sum_before": 0.0,
                "xstar_population_max_after": 0.0,
                "xstar_ipmat2_min": "",
                "xstar_ipmat2_max": "",
                "n_python_mapped_rows": 0,
                "python_population_sum": 0.0,
                "python_superlevel_p_sum": 0.0,
                "mapped_status": "unmapped_only",
            }
        return blocks[key]

    def update_index_range(b: Dict[str, Any], ip: Optional[int]) -> None:
        if ip is None:
            return
        if b["xstar_ipmat2_min"] == "" or ip < int(b["xstar_ipmat2_min"]):
            b["xstar_ipmat2_min"] = ip
        if b["xstar_ipmat2_max"] == "" or ip > int(b["xstar_ipmat2_max"]):
            b["xstar_ipmat2_max"] = ip

    for r in unmapped:
        ip = _as_int(r.get("xstar_ipmat2_index"), None)
        nion = _as_int(r.get("xstar_nion"), None)
        nsup = _as_int(r.get("xstar_nsup"), None)
        after = _as_float(r.get("xstar_after_population"), 0.0) or 0.0
        before = _as_float(r.get("xstar_before_population"), 0.0) or 0.0
        b = ensure_block(nion, nsup)
        b["n_xstar_rows"] += 1
        b["n_xstar_nonzero_rows"] += 1 if abs(after) > 0.0 else 0
        b["xstar_population_sum_after"] += after
        b["xstar_population_sum_before"] += before
        b["xstar_population_max_after"] = max(float(b["xstar_population_max_after"]), after)
        update_index_range(b, ip)

    for r in overlap:
        ip = _as_int(r.get("xstar_ipmat2_index"), None)
        nion = _as_int(r.get("xstar_nion"), None)
        nsup = _as_int(r.get("xstar_nsup"), None)
        after = _as_float(r.get("xstar_after_population"), 0.0) or 0.0
        before = _as_float(r.get("xstar_before_population"), 0.0) or 0.0
        py_pop = _as_float(r.get("python_population_fraction"), 0.0) or 0.0
        py_p = _as_float(r.get("python_xstar_superlevel_population_p"), 0.0) or 0.0
        b = ensure_block(nion, nsup)
        b["n_xstar_rows"] += 1
        b["n_xstar_nonzero_rows"] += 1 if abs(after) > 0.0 else 0
        b["xstar_population_sum_after"] += after
        b["xstar_population_sum_before"] += before
        b["xstar_population_max_after"] = max(float(b["xstar_population_max_after"]), after)
        b["n_python_mapped_rows"] += 1
        b["python_population_sum"] += py_pop
        b["python_superlevel_p_sum"] += py_p
        b["mapped_status"] = "mapped_and_xstar"
        update_index_range(b, ip)

    total_xstar_after = sum(float(b["xstar_population_sum_after"]) for b in blocks.values())
    total_python_mapped_xstar = sum(
        float(b["xstar_population_sum_after"]) for b in blocks.values() if int(b.get("n_python_mapped_rows") or 0) > 0
    )
    total_unmapped_xstar = sum(
        float(b["xstar_population_sum_after"]) for b in blocks.values() if int(b.get("n_python_mapped_rows") or 0) == 0
    )
    total_python_population = sum(float(b["python_population_sum"]) for b in blocks.values())

    block_rows: List[Dict[str, Any]] = []
    for b in blocks.values():
        pop = float(b["xstar_population_sum_after"])
        mapped = int(b["n_python_mapped_rows"] or 0) > 0
        frac_total = pop / total_xstar_after if total_xstar_after else 0.0
        b["xstar_population_fraction_of_total"] = frac_total
        b["xstar_population_sum_unmapped_part"] = 0.0 if mapped else pop
        b["xstar_population_fraction_unmapped_part"] = 0.0 if mapped or not total_xstar_after else pop / total_xstar_after
        b["block_classification"] = _classify_block(_as_int(b["xstar_nion"], None), _as_int(b["xstar_nsup"], None), pop, mapped)
        b["basis_gap_priority"] = (
            "high" if (not mapped and frac_total >= population_fraction_threshold) else
            "medium" if (not mapped and pop > 1e-10) else
            "mapped" if mapped else "low"
        )
        block_rows.append(b)
    block_rows.sort(key=lambda r: (float(r.get("xstar_population_sum_after") or 0.0)), reverse=True)

    dominant_unmapped = [r for r in block_rows if r.get("mapped_status") == "unmapped_only" and float(r.get("xstar_population_fraction_of_total") or 0.0) >= population_fraction_threshold]

    top_rows = []
    for r in sorted(unmapped, key=lambda x: _as_float(x.get("xstar_after_population"), 0.0) or 0.0, reverse=True):
        after = _as_float(r.get("xstar_after_population"), 0.0) or 0.0
        top_rows.append({
            "xstar_ipmat2_index": _as_int(r.get("xstar_ipmat2_index"), None),
            "xstar_nion": _as_int(r.get("xstar_nion"), None),
            "xstar_nsup": _as_int(r.get("xstar_nsup"), None),
            "xstar_after_population": after,
            "xstar_before_population": _as_float(r.get("xstar_before_population"), 0.0) or 0.0,
            "xstar_population_fraction_of_total": after / total_xstar_after if total_xstar_after else 0.0,
            "basis_gap_priority": "high" if (after / total_xstar_after if total_xstar_after else 0.0) >= population_fraction_threshold else "low",
            "reason": r.get("reason", ""),
        })

    py_block_rows = []
    for b in block_rows:
        if int(b.get("n_python_mapped_rows") or 0) <= 0:
            continue
        py_block_rows.append({
            "xstar_nion": b.get("xstar_nion"),
            "xstar_nsup": b.get("xstar_nsup"),
            "xstar_ipmat2_min": b.get("xstar_ipmat2_min"),
            "xstar_ipmat2_max": b.get("xstar_ipmat2_max"),
            "n_python_mapped_rows": b.get("n_python_mapped_rows"),
            "xstar_population_sum_after_on_these_rows": b.get("xstar_population_sum_after"),
            "python_population_sum_mapped_here": b.get("python_population_sum"),
            "python_superlevel_p_sum_mapped_here": b.get("python_superlevel_p_sum"),
            "mapping_warning": "python_population_mapped_to_low_xstar_population_block" if float(b.get("python_population_sum") or 0.0) > float(b.get("xstar_population_sum_after") or 0.0) + population_fraction_threshold else "",
        })

    implementation_plan = [
        {
            "priority": 1,
            "target": "replace_sequential_global_index_plus_one_ipmat2_mapping",
            "reason": "Python rows are mapped to XSTAR rows whose solved population is negligible while dominant XSTAR rows are unmapped.",
            "implementation": "Build ipmat2 mapping from XSTAR element basis metadata: indb/ilev/nlev/nlevp/nion/npnxt/topology, not from Python global_index+1.",
            "validation": "Mapped XSTAR population fraction should rise from current value to near unity for the selected element occurrence.",
        },
        {
            "priority": 2,
            "target": "construct_full_element_basis",
            "reason": "Selected O element solve has many more XSTAR ipmat2 rows than the current Python local O VII/O VIII basis.",
            "implementation": "Create Python basis rows for all selected element ipmat2 entries, including adjacent ion stages, continuum/parent rows, and superlevel rows.",
            "validation": "n_xstar_rows_without_python_mapping and xstar_population_sum_on_unmapped_rows should approach zero.",
        },
        {
            "priority": 3,
            "target": "populate_parent_superlevel_closure_terms",
            "reason": "Dominant unmapped blocks are concentrated in high-population XSTAR nion/nsup blocks, including parent/superlevel rows.",
            "implementation": "Port XSTAR parent/superlevel population closure around levwkelement/calc_hmc_element/type70/type74/type99 and normalization rows.",
            "validation": "Python post-solve population vector should match XSTAR post-msolvelucy on mapped rows with < threshold residuals.",
        },
    ]

    capture_scan_summary = []
    for r in scan:
        capture_scan_summary.append({
            "element_occurrence_rank": _as_int(r.get("element_occurrence_rank"), None),
            "solve_call_id": r.get("solve_call_id", ""),
            "ipmat2": _as_int(r.get("ipmat2"), None),
            "nsp": _as_int(r.get("nsp"), None),
            "nionp": _as_int(r.get("nionp"), None),
            "after_n_nonzero_population_rows": _as_int(r.get("after_n_nonzero_population_rows"), None),
            "xstar_after_population_sum_on_python_mapped_rows": _as_float(r.get("xstar_after_population_sum_on_python_mapped_rows"), None),
            "xstar_after_population_sum_on_unmapped_rows": _as_float(r.get("xstar_after_population_sum_on_unmapped_rows"), None),
            "unmapped_population_fraction_of_total": _as_float(r.get("unmapped_population_fraction_of_total"), None),
        })

    summary = {
        "audit_version": "v0.3.191",
        "status": "population_basis_mapping_diagnosis_completed",
        "source_population_closure_parity_audit": str(root),
        "ion": summary_in.get("ion", ""),
        "selected_solve_call_id": summary_in.get("selected_solve_call_id", ""),
        "occurrence_rank": summary_in.get("occurrence_rank", ""),
        "selected_xstar_ipmat2": summary_in.get("selected_xstar_ipmat2", ""),
        "selected_xstar_nsp": summary_in.get("selected_xstar_nsp", ""),
        "selected_xstar_nionp": summary_in.get("selected_xstar_nionp", ""),
        "n_xstar_population_rows_selected": summary_in.get("n_xstar_population_rows_selected", ""),
        "n_python_population_rows": summary_in.get("n_python_population_rows", ""),
        "n_python_rows_with_xstar_ipmat2_index": summary_in.get("n_python_rows_with_xstar_ipmat2_index", ""),
        "n_xstar_rows_without_python_mapping": summary_in.get("n_xstar_rows_without_python_mapping", len(unmapped)),
        "n_dominant_unmapped_blocks": len(dominant_unmapped),
        "xstar_population_sum_total_reconstructed": total_xstar_after,
        "xstar_population_sum_on_python_mapped_rows": total_python_mapped_xstar,
        "xstar_population_sum_on_unmapped_rows": total_unmapped_xstar,
        "xstar_unmapped_population_fraction_of_total": (total_unmapped_xstar / total_xstar_after) if total_xstar_after else "",
        "python_population_sum_mapped_to_xstar_rows": total_python_population,
        "max_unmapped_row_population": top_rows[0]["xstar_after_population"] if top_rows else 0.0,
        "max_unmapped_row_ipmat2": top_rows[0]["xstar_ipmat2_index"] if top_rows else "",
        "max_unmapped_row_nion": top_rows[0]["xstar_nion"] if top_rows else "",
        "max_unmapped_row_nsup": top_rows[0]["xstar_nsup"] if top_rows else "",
        "mapping_diagnosis": "python_ipmat2_mapping_is_not_source_equivalent_to_xstar_element_basis" if dominant_unmapped else "mapping_near_parity",
        "dominant_next_target": "xstar_element_basis_mapping_indb_ilev_parent_superlevel_closure" if dominant_unmapped else "population_values_on_mapped_basis",
        "population_fraction_threshold": population_fraction_threshold,
    }
    return {
        "summary": summary,
        "xstar_basis_block_summary": block_rows,
        "dominant_unmapped_xstar_rows": top_rows,
        "python_mapping_block_summary": py_block_rows,
        "capture_scan_summary": capture_scan_summary,
        "implementation_plan": implementation_plan,
    }


def write_population_basis_mapping_diagnosis(audit: Mapping[str, Any], out_dir: str | Path) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_population_basis_mapping_diagnosis"
    paths = {
        "basis_block_summary_csv": out / f"{prefix}_basis_block_summary.csv",
        "dominant_unmapped_rows_csv": out / f"{prefix}_dominant_unmapped_rows.csv",
        "python_mapping_block_summary_csv": out / f"{prefix}_python_mapping_block_summary.csv",
        "capture_scan_summary_csv": out / f"{prefix}_capture_scan_summary.csv",
        "implementation_plan_csv": out / f"{prefix}_implementation_plan.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["basis_block_summary_csv"], list(audit.get("xstar_basis_block_summary", []) or []))
    _write_csv(paths["dominant_unmapped_rows_csv"], list(audit.get("dominant_unmapped_xstar_rows", []) or []))
    _write_csv(paths["python_mapping_block_summary_csv"], list(audit.get("python_mapping_block_summary", []) or []))
    _write_csv(paths["capture_scan_summary_csv"], list(audit.get("capture_scan_summary", []) or []))
    _write_csv(paths["implementation_plan_csv"], list(audit.get("implementation_plan", []) or []))
    summary = dict(audit.get("summary", {}) or {})
    paths["json"].write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    top_blocks = list(audit.get("xstar_basis_block_summary", []) or [])[:8]
    top_rows = list(audit.get("dominant_unmapped_xstar_rows", []) or [])[:8]
    lines = [
        "# XSTAR population-basis mapping diagnosis",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"status: `{summary.get('status')}`",
        f"ion: `{summary.get('ion')}`",
        f"selected solve_call_id: `{summary.get('selected_solve_call_id')}`",
        f"occurrence_rank: `{summary.get('occurrence_rank')}`",
        "",
        "## Main conclusion",
        "",
        f"mapping_diagnosis: `{summary.get('mapping_diagnosis')}`",
        f"dominant_next_target: `{summary.get('dominant_next_target')}`",
        f"XSTAR population fraction on unmapped rows: `{summary.get('xstar_unmapped_population_fraction_of_total')}`",
        f"XSTAR population sum on Python-mapped rows: `{summary.get('xstar_population_sum_on_python_mapped_rows')}`",
        f"XSTAR population sum on unmapped rows: `{summary.get('xstar_population_sum_on_unmapped_rows')}`",
        "",
        "## Dominant XSTAR basis blocks",
        "",
    ]
    for b in top_blocks:
        lines.append(
            f"- nion=`{b.get('xstar_nion')}`, nsup=`{b.get('xstar_nsup')}`, "
            f"rows=`{b.get('xstar_ipmat2_min')}-{b.get('xstar_ipmat2_max')}`, "
            f"pop=`{b.get('xstar_population_sum_after')}`, mapped_rows=`{b.get('n_python_mapped_rows')}`, "
            f"priority=`{b.get('basis_gap_priority')}`"
        )
    lines += ["", "## Dominant unmapped rows", ""]
    for r in top_rows:
        lines.append(
            f"- ipmat2=`{r.get('xstar_ipmat2_index')}`, nion=`{r.get('xstar_nion')}`, nsup=`{r.get('xstar_nsup')}`, "
            f"population=`{r.get('xstar_after_population')}`"
        )
    lines += [
        "",
        "## Recommended implementation plan",
        "",
    ]
    for p in audit.get("implementation_plan", []) or []:
        lines.append(f"{p.get('priority')}. `{p.get('target')}` — {p.get('reason')}")
    lines += ["", "Diagnostic only; no solver physics changed."]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
