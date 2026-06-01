"""Local matrix-parity audits for XSTAR detail-state reproduction.

The functions in this module do not tune He-like triplet ratios.  They inspect
preserved solver matrix products and rank the rate families that feed or drain
specific local levels, especially the He-like forbidden/intercombination/
resonance upper levels.  This is the next bridge between row-level type-50
parity and full source-code-equivalent local rate/matrix parity.
"""

from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


_RATE_FAMILY_SOURCE_PATHS = {
    "1": "ucalc.f90 type 1 radiative recombination / recombination source closure",
    "50": "calc_hmc_ion.f90 ptmp1/ptmp2 -> ucalc.f90 type 50 bound-bound radiative rate",
    "53": "ucalc.f90 type 53 photoionization / recombination through phint53-style continuum integrals",
    "56": "ucalc.f90 type 56 tabulated collision-strength excitation/de-excitation",
    "63": "ucalc.f90 type 63 Bautista hydrogenic collision evaluator",
    "67": "ucalc.f90/calt67-style collisional process evaluator",
    "68": "ucalc.f90/calt68-style collisional process evaluator",
    "69": "ucalc.f90/calt69-style collisional process evaluator",
    "71": "calt71.f90 superlevel cascade / spectroscopic redistribution",
    "74": "ucalc.f90 type 74 inverse recombination / photoionization closure",
    "77": "calt77.f90 superlevel collisional coupling",
    "99": "ucalc.f90 type 99 continuum-parent / superlevel source coupling",
}


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        val = float(value)
        if not math.isfinite(val):
            return default
        return val
    except Exception:
        return default


def _as_int(value: Any) -> Optional[int]:
    val = _as_float(value)
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except Exception:
        return None


def _read_csv_rows(path: str | Path | None) -> List[Dict[str, Any]]:
    if path is None or not str(path).strip():
        return []
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Optional[Sequence[str]] = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in ordered:
                    ordered.append(key)
        fields = ordered or ["status"]
    with p.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _normalise_ion_key(text: Any) -> str:
    return str(text or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_path(root: Path, text: Any) -> Optional[Path]:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        return p
    # Example-56 comparison rows are often written relative to the command
    # working directory and include the benchmark directory name itself.  Try
    # both root/path and root.parent/path so archived outputs remain portable.
    for base in (root, root.parent):
        candidate = base / p
        if candidate.exists():
            return candidate
    return None


def find_solver_product_paths(
    benchmark_dir: str | Path,
    *,
    ion: str | None = None,
    comparisons_csv: str | Path | None = None,
) -> Dict[str, Optional[Path]]:
    """Locate preserved solver products for one ion from an example-56 run."""
    root = Path(benchmark_dir)
    out: Dict[str, Optional[Path]] = {
        "comparisons_csv": None,
        "matrix_terms_csv": None,
        "normalized_solve_csv": None,
        "solver_summary_json": None,
        "solver_product_dir": None,
    }
    candidates: List[Path] = []
    if comparisons_csv is not None:
        candidates.append(Path(comparisons_csv))
    candidates.extend([
        root / "xstar_local_reproduction_suite_comparisons.csv",
        root / "xstar_local_reproduction_comparison.csv",
    ])
    ion_norm = _normalise_ion_key(ion) if ion else ""
    for csv_path in candidates:
        if not csv_path.exists():
            continue
        out["comparisons_csv"] = csv_path
        for row in _read_csv_rows(csv_path):
            if ion_norm and _normalise_ion_key(row.get("ion")) != ion_norm:
                continue
            for key, col in [
                ("matrix_terms_csv", "solver_full_global_matrix_terms_csv"),
                ("normalized_solve_csv", "solver_full_global_normalized_solve_comparison_csv"),
                ("solver_summary_json", "solver_summary_json"),
            ]:
                p = _safe_path(root, row.get(col))
                if p is not None:
                    out[key] = p
            if out["matrix_terms_csv"] is not None:
                out["solver_product_dir"] = out["matrix_terms_csv"].parent
            return out
    matches = sorted(root.rglob("xstar_like_element_solver_full_global_matrix_terms.csv"))
    if ion_norm:
        slug = ion_norm.replace("_", "")
        matches = [p for p in matches if slug in str(p).lower().replace("_", "")] or matches
    if matches:
        m = matches[0]
        out["matrix_terms_csv"] = m
        out["solver_product_dir"] = m.parent
        n = m.parent / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv"
        s = m.parent / "xstar_like_element_solver_summary.json"
        out["normalized_solve_csv"] = n if n.exists() else None
        out["solver_summary_json"] = s if s.exists() else None
    return out


def _rate_family(row: Mapping[str, Any]) -> Tuple[str, str, str]:
    """Return ``(family_key, data_type, source_label)`` for a matrix term."""
    dt = _as_int(row.get("data_type"))
    if dt is None:
        method = str(row.get("source_method") or "")
        if "data_type_" in method:
            try:
                dt = int(method.split("data_type_", 1)[1].split("_", 1)[0])
            except Exception:
                dt = None
    if dt is None:
        # Source terms and older diagnostic rows often lack data_type but carry
        # a distinctive source/rate column.  Keep them grouped explicitly.
        for key, label in [
            ("type99_rate_source", "99"),
            ("type71_rate_source", "71"),
            ("type77_rate_source", "77"),
            ("inverse_recombination_mode", "74"),
            ("source_code_milne_f90_rate_alpha_ne_s^-1", "53"),
            ("source_rate_s^-1", "1"),
        ]:
            if str(row.get(key) or "").strip():
                dt = int(label)
                break
    data_type = str(dt) if dt is not None else "none"
    source_bits = []
    for key in [
        "source_method",
        "source_format",
        "rate_source",
        "type71_rate_source",
        "type77_rate_source",
        "type99_rate_source",
        "inverse_recombination_mode",
        "radiation_field_mode",
    ]:
        val = str(row.get(key) or "").strip()
        if val and val.lower() != "nan" and val not in source_bits:
            source_bits.append(val)
    source_label = ";".join(source_bits) if source_bits else "unspecified"
    key = f"dt{data_type}:{source_label}"
    return key, data_type, source_label


def _rate_value(row: Mapping[str, Any]) -> Optional[float]:
    for key in [
        "rate_s^-1",
        "full_global_rate_s^-1",
        "raw_rate_s^-1",
        "source_rate_s^-1",
        "escaped_decay_rate_s^-1",
        "q_excitation_cm3_s",
        "q_deexcitation_cm3_s",
    ]:
        val = _as_float(row.get(key))
        if val is not None:
            return val
    return None


def _signed_value(row: Mapping[str, Any]) -> Optional[float]:
    for key in ["full_global_signed_rate_s^-1", "signed_rate_s^-1", "matrix_signed_rate_s^-1"]:
        val = _as_float(row.get(key))
        if val is not None:
            return val
    return None


def _source_status_nonempty(row: Mapping[str, Any]) -> bool:
    for key in [
        "ucalc_context_status",
        "eval_method",
        "eval_diagnostic",
        "phint53_status",
        "phint53_milne_ans2_status",
        "type63_case",
        "type63_reason",
        "type71_calt71_status",
        "type77_calt77_status",
        "type99_phint53hunt_statuses",
        "assembly_status",
    ]:
        val = str(row.get(key) or "").strip()
        if val and val.lower() != "nan":
            return True
    return False


def _triplet_levels_from_solve_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if str(row.get("row_kind") or "").strip() != "population":
            continue
        comp = str(row.get("triplet_component") or "").strip().lower()
        is_upper = str(row.get("is_triplet_upper") or "").strip().lower() in {"true", "1", "yes"}
        if comp not in {"f", "i", "r"} and not is_upper:
            continue
        gi = _as_int(row.get("global_index"))
        if gi is None:
            continue
        out[gi] = {
            "global_index": gi,
            "component": comp if comp in {"f", "i", "r"} else "triplet",
            "ion_stage": _as_int(row.get("ion_stage")),
            "level_index": _as_int(row.get("level_index")),
            "level_label": row.get("level_label"),
            "population_fraction": _as_float(row.get("population_fraction")),
        }
    return out


def _comparison_case_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    summary_rows = [r for r in rows if str(r.get("row_kind") or "").strip() == "summary"]
    if not summary_rows:
        return out
    preferred = None
    for row in summary_rows:
        case = str(row.get("comparison_case") or "")
        if case == "full_global_xstar_tau0_calc_emis_ion":
            preferred = row
            break
    if preferred is None:
        non_baseline = [r for r in summary_rows if str(r.get("comparison_case") or "") != "per_ion_baseline"]
        preferred = non_baseline[-1] if non_baseline else summary_rows[-1]
    out["solver_comparison_case"] = preferred.get("comparison_case")
    for key in ["f_fraction", "i_fraction", "r_fraction", "R", "G", "l2_distance_to_target", "solve_status"]:
        out[f"solver_{key}"] = preferred.get(key)
    return out


def _load_type50_audit_status(type50_audit_csv: str | Path | None) -> Dict[str, Any]:
    rows = _read_csv_rows(type50_audit_csv)
    if not rows:
        return {"type50_audit_rows": 0, "type50_audit_all_matrix_match": None}
    classifications = [str(r.get("matrix_residual_classification") or "") for r in rows]
    n_match = sum(1 for c in classifications if c == "matrix_matches_ucalc_rate")
    return {
        "type50_audit_rows": len(rows),
        "type50_audit_matrix_matches": n_match,
        "type50_audit_all_matrix_match": bool(n_match == len(rows)),
        "type50_audit_classifications": ";".join(sorted(set(c for c in classifications if c))),
    }


def audit_local_matrix_parity(
    *,
    matrix_terms_csv: str | Path,
    normalized_solve_csv: str | Path | None = None,
    ion: str | None = None,
    type50_audit_csv: str | Path | None = None,
) -> Dict[str, Any]:
    """Summarize local rate-family and triplet matrix parity coverage.

    Parameters are paths to preserved products from
    ``examples/56_reproduce_xstar_local_outputs.py --write-solver-products``.
    The returned dictionary contains CSV-friendly ``family_rows`` and
    ``triplet_flow_rows`` plus an ``overall`` summary.  This is a ranking and
    coverage audit, not a replacement for individual Fortran-rate ports.
    """
    matrix_path = Path(matrix_terms_csv)
    matrix_rows = _read_csv_rows(matrix_path)
    solve_rows = _read_csv_rows(normalized_solve_csv)
    triplet = _triplet_levels_from_solve_rows(solve_rows)
    component_by_global = {int(k): str(v.get("component") or "") for k, v in triplet.items()}
    type50_status = _load_type50_audit_status(type50_audit_csv)

    families: Dict[str, Dict[str, Any]] = {}
    flows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in matrix_rows:
        fkey, data_type, source_label = _rate_family(row)
        fam = families.setdefault(fkey, {
            "ion": ion or "",
            "family_key": fkey,
            "data_type": data_type,
            "source_label": source_label,
            "source_code_path": _RATE_FAMILY_SOURCE_PATHS.get(data_type, "not_yet_mapped_to_specific_fortran_path"),
            "n_matrix_terms": 0,
            "n_unique_records": 0,
            "n_source_code_status_rows": 0,
            "n_gain_like_terms": 0,
            "n_loss_like_terms": 0,
            "n_terms_touching_triplet_levels": 0,
            "n_terms_touching_f": 0,
            "n_terms_touching_i": 0,
            "n_terms_touching_r": 0,
            "rate_abs_sum_s^-1": 0.0,
            "signed_abs_sum_s^-1": 0.0,
            "rate_min_s^-1": None,
            "rate_max_s^-1": None,
            "parity_status": "source_code_evaluator_or_matrix_terms_present_but_not_detail_verified",
            "next_audit_target": "compare evaluator rate, matrix placement, and diagonal partner against same-zone XSTAR detail/local state",
            "_records": set(),
        })
        fam["n_matrix_terms"] += 1
        rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
        if rec:
            fam["_records"].add(rec)
        if _source_status_nonempty(row):
            fam["n_source_code_status_rows"] += 1
        role = str(row.get("matrix_role") or row.get("matrix_term_kind") or row.get("row_kind") or "").lower()
        signed = _signed_value(row)
        if "gain" in role or (signed is not None and signed > 0):
            fam["n_gain_like_terms"] += 1
        if "loss" in role or (signed is not None and signed < 0):
            fam["n_loss_like_terms"] += 1
        rate = _rate_value(row)
        if rate is not None:
            fam["rate_abs_sum_s^-1"] += abs(float(rate))
            fam["rate_min_s^-1"] = float(rate) if fam["rate_min_s^-1"] is None else min(float(fam["rate_min_s^-1"]), float(rate))
            fam["rate_max_s^-1"] = float(rate) if fam["rate_max_s^-1"] is None else max(float(fam["rate_max_s^-1"]), float(rate))
        if signed is not None:
            fam["signed_abs_sum_s^-1"] += abs(float(signed))
        row_g = _as_int(row.get("matrix_row_global_index"))
        col_g = _as_int(row.get("matrix_col_global_index"))
        touched = sorted(set(g for g in [row_g, col_g] if g in component_by_global))
        if touched:
            fam["n_terms_touching_triplet_levels"] += 1
            comps = sorted(set(component_by_global[g] for g in touched))
            for comp in comps:
                key = f"n_terms_touching_{comp}"
                if key in fam:
                    fam[key] += 1
        if row_g in component_by_global:
            comp = component_by_global[row_g]
            flow_key = (comp, str(row_g), fkey)
            fl = flows.setdefault(flow_key, {
                "ion": ion or "",
                "triplet_component": comp,
                "triplet_global_index": row_g,
                "triplet_level_label": triplet[row_g].get("level_label"),
                "family_key": fkey,
                "data_type": data_type,
                "source_label": source_label,
                "source_code_path": _RATE_FAMILY_SOURCE_PATHS.get(data_type, "not_yet_mapped_to_specific_fortran_path"),
                "n_row_terms": 0,
                "row_gain_sum_s^-1": 0.0,
                "row_loss_sum_s^-1": 0.0,
                "row_signed_sum_s^-1": 0.0,
            })
            fl["n_row_terms"] += 1
            if signed is not None:
                fl["row_signed_sum_s^-1"] += float(signed)
                if signed >= 0.0:
                    fl["row_gain_sum_s^-1"] += float(signed)
                else:
                    fl["row_loss_sum_s^-1"] += abs(float(signed))

    family_rows: List[Dict[str, Any]] = []
    for fam in families.values():
        fam["n_unique_records"] = len(fam.pop("_records", set()))
        if fam["data_type"] == "50" and type50_status.get("type50_audit_all_matrix_match") is True:
            fam["parity_status"] = "detail_rate_and_matrix_parity_verified_for_audited_type50_lines"
            fam["next_audit_target"] = "expand type50 audit beyond selected triplet lines or move to non-type50 families"
        elif fam["data_type"] == "50" and type50_status.get("type50_audit_all_matrix_match") is False:
            fam["parity_status"] = "type50_detail_audit_has_remaining_mismatches"
        family_rows.append(fam)
    family_rows.sort(key=lambda r: (-(int(r.get("n_terms_touching_triplet_levels") or 0)), str(r.get("data_type")), str(r.get("family_key"))))

    triplet_flow_rows = list(flows.values())
    triplet_flow_rows.sort(key=lambda r: (str(r.get("triplet_component")), int(r.get("triplet_global_index") or -1), -float(r.get("row_gain_sum_s^-1") or 0.0) - float(r.get("row_loss_sum_s^-1") or 0.0)))

    overall: Dict[str, Any] = {
        "ion": ion or "",
        "matrix_terms_csv": str(matrix_path),
        "normalized_solve_csv": str(normalized_solve_csv or ""),
        "n_matrix_terms": len(matrix_rows),
        "n_rate_families": len(family_rows),
        "n_triplet_upper_levels": len(triplet),
        "triplet_levels": list(triplet.values()),
        "audit_scope": "rate-family ranking and triplet-row matrix-flow coverage; use per-family detail audits for final parity claims",
        "recommended_next_step": "port/check one non-type50 rate family at a time against XSTAR source code and same-zone detail/live state, then verify both off-diagonal and diagonal matrix placement",
    }
    overall.update(_comparison_case_summary(solve_rows))
    overall.update(type50_status)
    return {"overall": overall, "family_rows": family_rows, "triplet_flow_rows": triplet_flow_rows}


def write_local_matrix_parity_audit(result: Mapping[str, Any], out_dir: str | Path, *, prefix: str = "xstar_local_matrix_parity_audit") -> Dict[str, str]:
    """Write local matrix-parity audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    family_rows = list(result.get("family_rows") or [])
    flow_rows = list(result.get("triplet_flow_rows") or [])
    overall = dict(result.get("overall") or {})

    family_csv = out / f"{prefix}_family_summary.csv"
    flow_csv = out / f"{prefix}_triplet_flow_summary.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    _write_csv(family_csv, family_rows)
    _write_csv(flow_csv, flow_rows)
    json_path.write_text(json.dumps({"overall": overall, "family_rows": family_rows, "triplet_flow_rows": flow_rows}, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# XSTAR local matrix parity audit",
        "",
        f"Ion: `{overall.get('ion','')}`",
        "",
        f"Matrix terms: `{overall.get('n_matrix_terms')}`",
        f"Rate families: `{overall.get('n_rate_families')}`",
        f"Triplet upper levels: `{overall.get('n_triplet_upper_levels')}`",
        "",
        "This audit ranks the local matrix rate families that touch the He-like triplet upper levels. It is intended to guide source-code-equivalent parity work after the type-50 line-escape audit, not to tune f/i/r ratios empirically.",
        "",
    ]
    if overall.get("type50_audit_rows"):
        lines += [
            "## Type-50 detail audit handoff",
            "",
            f"Audited type-50 rows: `{overall.get('type50_audit_rows')}`",
            f"Rows matching matrix rate: `{overall.get('type50_audit_matrix_matches')}`",
            f"Classifications: `{overall.get('type50_audit_classifications')}`",
            "",
        ]
    if any(k in overall for k in ["solver_f_fraction", "solver_i_fraction", "solver_r_fraction"]):
        lines += [
            "## Solver summary",
            "",
            f"Solver f/i/r: `{overall.get('solver_f_fraction')}` / `{overall.get('solver_i_fraction')}` / `{overall.get('solver_r_fraction')}`",
            f"Solver R/G/L2: `{overall.get('solver_R')}` / `{overall.get('solver_G')}` / `{overall.get('solver_l2_distance_to_target')}`",
            "",
        ]
    lines += [
        "## Rate families touching triplet levels",
        "",
        "| data type | source label | n terms | n touching triplet | f | i | r | parity status | next audit target |",
        "|---:|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in family_rows:
        if int(row.get("n_terms_touching_triplet_levels") or 0) <= 0:
            continue
        lines.append(
            f"| {row.get('data_type')} | {row.get('source_label')} | {row.get('n_matrix_terms')} | "
            f"{row.get('n_terms_touching_triplet_levels')} | {row.get('n_terms_touching_f')} | {row.get('n_terms_touching_i')} | {row.get('n_terms_touching_r')} | "
            f"{row.get('parity_status')} | {row.get('next_audit_target')} |"
        )
    lines += [
        "",
        "## Triplet row flow summary",
        "",
        "| component | level | data type | source label | row gain sum | row loss sum | signed sum | n row terms |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    for row in flow_rows[:80]:
        lines.append(
            f"| {row.get('triplet_component')} | {row.get('triplet_level_label')} | {row.get('data_type')} | {row.get('source_label')} | "
            f"{row.get('row_gain_sum_s^-1')} | {row.get('row_loss_sum_s^-1')} | {row.get('row_signed_sum_s^-1')} | {row.get('n_row_terms')} |"
        )
    lines += [
        "",
        "## Recommended parity sequence",
        "",
        "1. Keep type-50 as the verified template: detail-state input -> source-code evaluator -> matrix gain/loss placement.",
        "2. Apply the same pattern to the largest non-type-50 families touching the triplet rows, starting with the families with the largest row gain/loss sums.",
        "3. Compare solved Python level populations directly to `xo01_detail.fits` once the dominant local matrix families have row-level parity.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"family_csv": str(family_csv), "triplet_flow_csv": str(flow_csv), "json": str(json_path), "markdown": str(md_path)}


def _label_for_global_index(index: Optional[int], triplet: Mapping[int, Mapping[str, Any]], row: Mapping[str, Any]) -> str:
    """Return a readable label for a global matrix index."""
    if index is None:
        return ""
    if index in triplet:
        label = triplet[index].get("level_label")
        comp = triplet[index].get("component")
        return f"{label} [{comp}]" if label else f"global {index} [{comp}]"
    for key, gi_key, label_key in [
        ("from", "from_global_index", "from_level_label"),
        ("to", "to_global_index", "to_level_label"),
        ("spectroscopic", "spectroscopic_global_index", "spectroscopic_level_label"),
        ("superlevel", "superlevel_global_index", "superlevel_level_label"),
        ("destination", "destination_global_index", "destination_level_label"),
        ("bound", "bound_global_index", "bound_level"),
        ("parent", "parent_continuum_global_index", "parent_continuum_level_label"),
    ]:
        gi = _as_int(row.get(gi_key))
        if gi == index:
            lab = str(row.get(label_key) or "").strip()
            if lab:
                return lab
    return f"global {index}"


def _make_term_lookup(rows: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, str, int, int], List[Mapping[str, Any]]]:
    """Index matrix rows for lightweight gain/loss partner checks."""
    out: Dict[Tuple[str, str, int, int], List[Mapping[str, Any]]] = {}
    for row in rows:
        fkey, _dt, _src = _rate_family(row)
        rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
        r = _as_int(row.get("matrix_row_global_index"))
        c = _as_int(row.get("matrix_col_global_index"))
        if r is None or c is None:
            continue
        out.setdefault((fkey, rec, r, c), []).append(row)
    return out


def _partner_status(row: Mapping[str, Any], lookup: Mapping[Tuple[str, str, int, int], Sequence[Mapping[str, Any]]]) -> Dict[str, Any]:
    """Classify whether a matrix term has the expected gain/loss partner.

    The check is intentionally conservative and matrix-local.  It does not
    prove source-code parity; it only catches obvious placement mistakes such
    as an off-diagonal term without its matching diagonal loss or vice versa.
    """
    fkey, _dt, _src = _rate_family(row)
    rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
    r = _as_int(row.get("matrix_row_global_index"))
    c = _as_int(row.get("matrix_col_global_index"))
    signed = _signed_value(row)
    rate = abs(float(signed)) if signed is not None else _rate_value(row)
    if r is None or c is None or signed is None:
        return {"partner_status": "not_checked_missing_matrix_indices_or_signed_rate", "partner_count": 0, "partner_residual_s^-1": ""}
    tol = max(1.0e-30, 1.0e-8 * abs(float(rate or 0.0)))
    if r != c and signed > 0.0:
        candidates = list(lookup.get((fkey, rec, c, c), []))
        residuals = []
        for cand in candidates:
            cs = _signed_value(cand)
            if cs is None:
                continue
            residuals.append(abs(float(cs) + float(signed)))
        if not residuals:
            return {"partner_status": "missing_diagonal_loss_partner", "partner_count": 0, "partner_residual_s^-1": ""}
        best = min(residuals)
        return {
            "partner_status": "matrix_gain_loss_partner_matches" if best <= tol else "matrix_gain_loss_partner_rate_mismatch",
            "partner_count": len(residuals),
            "partner_residual_s^-1": best,
        }
    if r == c and signed < 0.0:
        # The matching gain can go to any row with this diagonal level as the
        # source column for the same family/record.  Some source/superlevel
        # rows intentionally do not have a simple one-to-one partner.
        candidates: List[Mapping[str, Any]] = []
        for (kf, kr, rr, cc), vals in lookup.items():
            if kf == fkey and kr == rec and cc == r and rr != r:
                candidates.extend(vals)
        residuals = []
        for cand in candidates:
            cs = _signed_value(cand)
            if cs is None or cs <= 0.0:
                continue
            residuals.append(abs(float(cs) + float(signed)))
        if not residuals:
            return {"partner_status": "missing_offdiag_gain_partner_or_many_to_one_source", "partner_count": 0, "partner_residual_s^-1": ""}
        best = min(residuals)
        return {
            "partner_status": "matrix_gain_loss_partner_matches" if best <= tol else "matrix_gain_loss_partner_rate_mismatch",
            "partner_count": len(residuals),
            "partner_residual_s^-1": best,
        }
    return {"partner_status": "not_simple_gain_loss_pair", "partner_count": 0, "partner_residual_s^-1": ""}


def audit_triplet_rate_terms(
    *,
    matrix_terms_csv: str | Path,
    normalized_solve_csv: str | Path | None = None,
    ion: str | None = None,
    data_types: Sequence[str | int] | None = None,
    max_rows: int | None = 200,
) -> Dict[str, Any]:
    """Rank individual matrix terms in He-like triplet rows.

    This is the row-level companion to :func:`audit_local_matrix_parity`.  It
    lists the largest gain/loss terms for the actual triplet population rows,
    attaches Fortran source-path labels, and performs a conservative local
    check for matching off-diagonal/diagonal partners.  It is meant to select
    the next source-code-equivalent detail-rate audit targets.
    """
    matrix_path = Path(matrix_terms_csv)
    matrix_rows = _read_csv_rows(matrix_path)
    solve_rows = _read_csv_rows(normalized_solve_csv)
    triplet = _triplet_levels_from_solve_rows(solve_rows)
    type_filter = {str(x) for x in data_types} if data_types else None
    lookup = _make_term_lookup(matrix_rows)
    out_rows: List[Dict[str, Any]] = []
    for row in matrix_rows:
        row_g = _as_int(row.get("matrix_row_global_index"))
        if row_g not in triplet:
            continue
        fkey, data_type, source_label = _rate_family(row)
        if type_filter is not None and data_type not in type_filter:
            continue
        col_g = _as_int(row.get("matrix_col_global_index"))
        signed = _signed_value(row)
        rate = _rate_value(row)
        comp = str(triplet[row_g].get("component") or "")
        direction = "row_gain" if signed is not None and signed > 0 else "row_loss" if signed is not None and signed < 0 else "row_source_or_unknown"
        rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
        partner = _partner_status(row, lookup)
        out = {
            "ion": ion or "",
            "triplet_component": comp,
            "triplet_global_index": row_g,
            "triplet_level_label": triplet[row_g].get("level_label"),
            "matrix_col_global_index": col_g if col_g is not None else "",
            "matrix_col_label": _label_for_global_index(col_g, triplet, row),
            "direction": direction,
            "matrix_term_kind": row.get("matrix_term_kind") or row.get("matrix_term_kind") or "",
            "matrix_role": row.get("matrix_role") or "",
            "data_type": data_type,
            "source_label": source_label,
            "source_code_path": _RATE_FAMILY_SOURCE_PATHS.get(data_type, "not_yet_mapped_to_specific_fortran_path"),
            "record": rec,
            "signed_rate_s^-1": signed if signed is not None else "",
            "rate_s^-1": rate if rate is not None else "",
            "abs_signed_rate_s^-1": abs(float(signed)) if signed is not None else abs(float(rate)) if rate is not None else 0.0,
            "temperature_K": row.get("temperature_K") or "",
            "electron_density_cm^-3": row.get("electron_density_cm^-3") or "",
            "from_global_index": row.get("from_global_index") or row.get("spectroscopic_global_index") or row.get("bound_global_index") or "",
            "to_global_index": row.get("to_global_index") or row.get("destination_global_index") or row.get("superlevel_global_index") or "",
            "from_level_label": row.get("from_level_label") or row.get("spectroscopic_level_label") or row.get("bound_level") or "",
            "to_level_label": row.get("to_level_label") or row.get("destination_level_label") or row.get("superlevel_level_label") or "",
            "eval_status": row.get("ucalc_context_status") or row.get("eval_method") or row.get("type71_calt71_status") or row.get("type77_calt77_status") or row.get("phint53_status") or row.get("assembly_status") or "",
            "next_detail_audit_hint": "recompute this record from same-zone detail/live state and compare evaluator rate plus matrix partner placement",
        }
        out.update(partner)
        out_rows.append(out)
    out_rows.sort(key=lambda r: (-float(r.get("abs_signed_rate_s^-1") or 0.0), str(r.get("triplet_component")), int(r.get("triplet_global_index") or -1)))
    if max_rows is not None and max_rows > 0:
        selected_rows = out_rows[: int(max_rows)]
    else:
        selected_rows = out_rows
    family_counts: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in out_rows:
        key = (str(r.get("data_type")), str(r.get("source_label")))
        item = family_counts.setdefault(key, {
            "ion": ion or "",
            "data_type": key[0],
            "source_label": key[1],
            "source_code_path": r.get("source_code_path"),
            "n_triplet_row_terms": 0,
            "n_row_gain_terms": 0,
            "n_row_loss_terms": 0,
            "abs_signed_sum_s^-1": 0.0,
            "largest_abs_signed_rate_s^-1": 0.0,
            "n_partner_matches": 0,
            "n_partner_mismatches_or_missing": 0,
        })
        item["n_triplet_row_terms"] += 1
        if r.get("direction") == "row_gain":
            item["n_row_gain_terms"] += 1
        elif r.get("direction") == "row_loss":
            item["n_row_loss_terms"] += 1
        val = float(r.get("abs_signed_rate_s^-1") or 0.0)
        item["abs_signed_sum_s^-1"] += val
        item["largest_abs_signed_rate_s^-1"] = max(float(item["largest_abs_signed_rate_s^-1"]), val)
        ps = str(r.get("partner_status") or "")
        if ps == "matrix_gain_loss_partner_matches":
            item["n_partner_matches"] += 1
        elif ps and not ps.startswith("not_"):
            item["n_partner_mismatches_or_missing"] += 1
    family_rows = list(family_counts.values())
    family_rows.sort(key=lambda r: -float(r.get("abs_signed_sum_s^-1") or 0.0))
    overall = {
        "ion": ion or "",
        "matrix_terms_csv": str(matrix_path),
        "normalized_solve_csv": str(normalized_solve_csv or ""),
        "n_triplet_upper_levels": len(triplet),
        "n_triplet_row_terms_total": len(out_rows),
        "n_triplet_row_terms_written": len(selected_rows),
        "data_type_filter": ";".join(sorted(type_filter)) if type_filter else "",
        "audit_scope": "individual triplet-row matrix terms ranked by absolute signed contribution; local partner check is diagnostic only",
        "recommended_next_step": "select the largest unverified non-type50 row terms and build a same-zone detail-state rate evaluator audit for that data type",
        "triplet_levels": list(triplet.values()),
    }
    return {"overall": overall, "family_rows": family_rows, "term_rows": selected_rows}


def write_triplet_rate_term_audit(result: Mapping[str, Any], out_dir: str | Path, *, prefix: str = "xstar_triplet_rate_term_audit") -> Dict[str, str]:
    """Write row-level triplet matrix-term audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    family_rows = list(result.get("family_rows") or [])
    term_rows = list(result.get("term_rows") or [])
    overall = dict(result.get("overall") or {})
    family_csv = out / f"{prefix}_family_summary.csv"
    term_csv = out / f"{prefix}_ranked_terms.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    _write_csv(family_csv, family_rows)
    _write_csv(term_csv, term_rows)
    json_path.write_text(json.dumps({"overall": overall, "family_rows": family_rows, "term_rows": term_rows}, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# XSTAR triplet row rate-term audit",
        "",
        f"Ion: `{overall.get('ion','')}`",
        "",
        f"Triplet upper levels: `{overall.get('n_triplet_upper_levels')}`",
        f"Triplet row terms total: `{overall.get('n_triplet_row_terms_total')}`",
        f"Triplet row terms written: `{overall.get('n_triplet_row_terms_written')}`",
        "",
        "This audit ranks individual matrix terms in the He-like triplet population rows. It is a target selector for source-code-equivalent local rate and matrix parity work, not a triplet-ratio tuning step.",
        "",
        "## Family totals in triplet rows",
        "",
        "| data type | source label | n terms | gains | losses | abs signed sum | largest term | partner matches | partner issues |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in family_rows:
        lines.append(
            f"| {r.get('data_type')} | {r.get('source_label')} | {r.get('n_triplet_row_terms')} | {r.get('n_row_gain_terms')} | {r.get('n_row_loss_terms')} | "
            f"{r.get('abs_signed_sum_s^-1')} | {r.get('largest_abs_signed_rate_s^-1')} | {r.get('n_partner_matches')} | {r.get('n_partner_mismatches_or_missing')} |"
        )
    lines += [
        "",
        "## Largest individual triplet-row terms",
        "",
        "| component | level | direction | data type | source label | signed rate | partner status | record | role | column label |",
        "|---|---|---|---:|---|---:|---|---:|---|---|",
    ]
    for r in term_rows[:100]:
        lines.append(
            f"| {r.get('triplet_component')} | {r.get('triplet_level_label')} | {r.get('direction')} | {r.get('data_type')} | {r.get('source_label')} | "
            f"{r.get('signed_rate_s^-1')} | {r.get('partner_status')} | {r.get('record')} | {r.get('matrix_role')} | {r.get('matrix_col_label')} |"
        )
    lines += [
        "",
        "## Recommended parity sequence",
        "",
        "1. Use the top non-type-50 terms as concrete records for source-code re-evaluation from the same XSTAR detail/live state.",
        "2. For each selected data type, compare the Python evaluator rate, the off-diagonal gain term, and the diagonal loss partner.",
        "3. Only after dominant row-level terms pass should the solved populations be compared directly to `xo01_detail.fits`.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"family_csv": str(family_csv), "ranked_terms_csv": str(term_csv), "json": str(json_path), "markdown": str(md_path)}



def audit_type71_cascade_rates(
    *,
    matrix_terms_csv: str | Path,
    normalized_solve_csv: str | Path | None = None,
    ion: str | None = None,
    triplet_only: bool = False,
    max_rows: int | None = 500,
) -> Dict[str, Any]:
    """Audit source-code and matrix parity for type-71 superlevel cascades.

    XSTAR's ``ucalc.f90`` type-71 branch calls ``calt71.f90`` to interpolate
    the superlevel-to-spectroscopic radiative probability ``aij``.  The branch
    then uses that value as the escaped cascade rate (``ans2`` after the final
    assignment used by matrix assembly).  Preserved solver matrix terms already
    contain the interpolated ``type71_calt71_log10_aij`` value, so this audit
    checks the concrete handoff:

    ``calt71 log10(aij) -> evaluator rate -> off-diagonal gain and diagonal loss``.

    This is a parity audit only.  It does not change the solver and does not
    claim population parity against XSTAR by itself.
    """
    matrix_path = Path(matrix_terms_csv)
    matrix_rows = _read_csv_rows(matrix_path)
    solve_rows = _read_csv_rows(normalized_solve_csv)
    triplet = _triplet_levels_from_solve_rows(solve_rows)
    lookup = _make_term_lookup(matrix_rows)

    out_rows: List[Dict[str, Any]] = []
    record_pairs: Dict[str, Dict[str, Any]] = {}
    for row in matrix_rows:
        fkey, data_type, source_label = _rate_family(row)
        if data_type != "71":
            continue
        row_g = _as_int(row.get("matrix_row_global_index"))
        col_g = _as_int(row.get("matrix_col_global_index"))
        signed = _signed_value(row)
        matrix_rate = _rate_value(row)
        rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
        spectro_g = _as_int(row.get("spectroscopic_global_index"))
        super_g = _as_int(row.get("superlevel_global_index"))
        destination_triplet_component = str(row.get("destination_triplet_component") or "").strip().lower()
        row_triplet_component = str(triplet.get(row_g or -999, {}).get("component") or "")
        is_triplet_destination = bool(destination_triplet_component in {"f", "i", "r"} or spectro_g in triplet)
        is_triplet_row = bool(row_g in triplet)
        if triplet_only and not (is_triplet_destination or is_triplet_row):
            continue

        log_aij = _as_float(row.get("type71_calt71_log10_aij"))
        expected = 10.0 ** log_aij if log_aij is not None else None
        residual = ""
        rel = ""
        classification = "missing_calt71_log10_aij_or_matrix_rate"
        if expected is not None and matrix_rate is not None:
            residual_val = float(matrix_rate) - float(expected)
            rel_val = residual_val / max(abs(float(expected)), 1.0e-300)
            residual = residual_val
            rel = rel_val
            tol = max(1.0e-25, 1.0e-10 * abs(float(expected)))
            classification = "matrix_matches_calt71_aij" if abs(residual_val) <= tol else "matrix_rate_mismatch_vs_calt71_aij"

        direction = "row_gain" if signed is not None and signed > 0 else "row_loss" if signed is not None and signed < 0 else "row_source_or_unknown"
        partner = _partner_status(row, lookup)
        role = str(row.get("matrix_role") or "")
        pair = record_pairs.setdefault(rec, {
            "record": rec,
            "n_terms": 0,
            "n_gain_terms": 0,
            "n_loss_terms": 0,
            "n_matrix_matches_calt71_aij": 0,
            "n_partner_matches": 0,
            "abs_gain_sum_s^-1": 0.0,
            "abs_loss_sum_s^-1": 0.0,
            "largest_abs_rate_s^-1": 0.0,
            "spectroscopic_global_index": spectro_g if spectro_g is not None else "",
            "superlevel_global_index": super_g if super_g is not None else "",
            "spectroscopic_level_label": row.get("spectroscopic_level_label") or "",
            "superlevel_level_label": row.get("superlevel_level_label") or "",
            "destination_triplet_component": destination_triplet_component,
            "is_triplet_destination": is_triplet_destination,
        })
        pair["n_terms"] += 1
        if direction == "row_gain":
            pair["n_gain_terms"] += 1
            pair["abs_gain_sum_s^-1"] += abs(float(signed or matrix_rate or 0.0))
        elif direction == "row_loss":
            pair["n_loss_terms"] += 1
            pair["abs_loss_sum_s^-1"] += abs(float(signed or matrix_rate or 0.0))
        if classification == "matrix_matches_calt71_aij":
            pair["n_matrix_matches_calt71_aij"] += 1
        if partner.get("partner_status") == "matrix_gain_loss_partner_matches":
            pair["n_partner_matches"] += 1
        pair["largest_abs_rate_s^-1"] = max(float(pair["largest_abs_rate_s^-1"]), abs(float(signed if signed is not None else matrix_rate or 0.0)))

        out = {
            "ion": ion or "",
            "record": rec,
            "data_type": data_type,
            "source_label": source_label,
            "source_code_path": _RATE_FAMILY_SOURCE_PATHS.get(data_type, "not_yet_mapped_to_specific_fortran_path"),
            "fortran_ucalc_branch": "ucalc.f90 type 71: call calt71; ans2=aij*(ptmp1+ptmp2); ans1=0 after final assignment",
            "fortran_calt71_formula": "aij=10**interpolated_log10_rate over log10(ne),log10(T); constant records use rdat(3) directly/log10 converted when >30",
            "matrix_row_global_index": row_g if row_g is not None else "",
            "matrix_col_global_index": col_g if col_g is not None else "",
            "matrix_role": role,
            "direction": direction,
            "signed_rate_s^-1": signed if signed is not None else "",
            "matrix_rate_s^-1": matrix_rate if matrix_rate is not None else "",
            "calt71_log10_aij": log_aij if log_aij is not None else "",
            "calt71_aij_from_log10_s^-1": expected if expected is not None else "",
            "matrix_minus_calt71_aij_s^-1": residual,
            "relative_residual_vs_calt71_aij": rel,
            "rate_classification": classification,
            "partner_status": partner.get("partner_status"),
            "partner_count": partner.get("partner_count"),
            "partner_residual_s^-1": partner.get("partner_residual_s^-1"),
            "type71_calt71_status": row.get("type71_calt71_status") or "",
            "type71_calt71_wavelength_A": row.get("type71_calt71_wavelength_A") or "",
            "type71_calt71_nden": row.get("type71_calt71_nden") or "",
            "type71_calt71_ntem": row.get("type71_calt71_ntem") or "",
            "spectroscopic_global_index": spectro_g if spectro_g is not None else "",
            "superlevel_global_index": super_g if super_g is not None else "",
            "spectroscopic_level_label": row.get("spectroscopic_level_label") or "",
            "superlevel_level_label": row.get("superlevel_level_label") or "",
            "destination_triplet_component": destination_triplet_component,
            "is_triplet_destination": is_triplet_destination,
            "is_triplet_population_row": is_triplet_row,
            "feeds_forbidden_upper": row.get("feeds_forbidden_upper") or "",
            "feeds_intercombination_upper": row.get("feeds_intercombination_upper") or "",
            "feeds_resonance_upper": row.get("feeds_resonance_upper") or "",
            "notes": row.get("notes") or "",
        }
        out_rows.append(out)

    out_rows.sort(key=lambda r: (-abs(float(r.get("signed_rate_s^-1") or r.get("matrix_rate_s^-1") or 0.0)), str(r.get("record"))))
    if max_rows is not None and max_rows > 0:
        selected_rows = out_rows[: int(max_rows)]
    else:
        selected_rows = out_rows

    record_rows = list(record_pairs.values())
    for pair in record_rows:
        gain = float(pair.get("abs_gain_sum_s^-1") or 0.0)
        loss = float(pair.get("abs_loss_sum_s^-1") or 0.0)
        pair["gain_loss_abs_residual_s^-1"] = gain - loss
        pair["record_pair_classification"] = (
            "gain_loss_pair_matches"
            if int(pair.get("n_gain_terms") or 0) >= 1
            and int(pair.get("n_loss_terms") or 0) >= 1
            and abs(gain - loss) <= max(1.0e-25, 1.0e-10 * max(gain, loss, 1.0))
            else "gain_loss_pair_missing_or_mismatch"
        )
    record_rows.sort(key=lambda r: -float(r.get("largest_abs_rate_s^-1") or 0.0))

    n_match = sum(1 for r in out_rows if r.get("rate_classification") == "matrix_matches_calt71_aij")
    n_partner_match = sum(1 for r in out_rows if r.get("partner_status") == "matrix_gain_loss_partner_matches")
    n_pair_match = sum(1 for r in record_rows if r.get("record_pair_classification") == "gain_loss_pair_matches")
    overall = {
        "ion": ion or "",
        "matrix_terms_csv": str(matrix_path),
        "normalized_solve_csv": str(normalized_solve_csv or ""),
        "n_type71_matrix_terms": len(out_rows),
        "n_type71_matrix_terms_written": len(selected_rows),
        "n_type71_records": len(record_rows),
        "n_type71_matrix_matches_calt71_aij": n_match,
        "n_type71_partner_matches": n_partner_match,
        "n_type71_gain_loss_record_pairs_matching": n_pair_match,
        "n_type71_triplet_destination_terms": sum(1 for r in out_rows if r.get("is_triplet_destination")),
        "n_type71_triplet_population_row_terms": sum(1 for r in out_rows if r.get("is_triplet_population_row")),
        "triplet_only": bool(triplet_only),
        "audit_scope": "source-code-equivalent calt71 -> ucalc type-71 -> full-global matrix handoff; no solver physics changed",
        "source_code_reference": "calt71.f90 interpolates log10(aij); ucalc.f90 type 71 sets ans2 to the escaped superlevel cascade rate and ans1=0 for universal matrix assignment",
        "recommended_next_step": "if type-71 passes, move the same row-level parity pattern to type-68 and type-53 families that touch the triplet rows",
    }
    return {"overall": overall, "record_rows": record_rows, "term_rows": selected_rows}


def write_type71_cascade_rate_audit(result: Mapping[str, Any], out_dir: str | Path, *, prefix: str = "xstar_type71_cascade_rate_audit") -> Dict[str, str]:
    """Write type-71 superlevel cascade parity audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    record_rows = list(result.get("record_rows") or [])
    term_rows = list(result.get("term_rows") or [])
    overall = dict(result.get("overall") or {})
    record_csv = out / f"{prefix}_record_summary.csv"
    term_csv = out / f"{prefix}_terms.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    _write_csv(record_csv, record_rows)
    _write_csv(term_csv, term_rows)
    json_path.write_text(json.dumps({"overall": overall, "record_rows": record_rows, "term_rows": term_rows}, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# XSTAR type-71 superlevel cascade rate audit",
        "",
        f"Ion: `{overall.get('ion','')}`",
        "",
        f"Type-71 matrix terms: `{overall.get('n_type71_matrix_terms')}`",
        f"Type-71 records: `{overall.get('n_type71_records')}`",
        f"Terms matching `calt71` Aij: `{overall.get('n_type71_matrix_matches_calt71_aij')}`",
        f"Gain/loss record pairs matching: `{overall.get('n_type71_gain_loss_record_pairs_matching')}`",
        f"Triplet-destination terms: `{overall.get('n_type71_triplet_destination_terms')}`",
        f"Triplet population-row terms: `{overall.get('n_type71_triplet_population_row_terms')}`",
        "",
        "This audit checks the source-code handoff for XSTAR data type 71: `calt71.f90` interpolates the superlevel-to-spectroscopic radiative probability, then `ucalc.f90` type 71 supplies that rate to matrix assembly. It is a local parity audit, not an empirical triplet-ratio adjustment.",
        "",
        "## Record-level gain/loss summary",
        "",
        "| record | destination | superlevel | component | gain terms | loss terms | largest rate | gain-loss residual | classification |",
        "|---:|---|---|---|---:|---:|---:|---:|---|",
    ]
    for r in record_rows[:100]:
        lines.append(
            f"| {r.get('record')} | {r.get('spectroscopic_level_label')} | {r.get('superlevel_level_label')} | {r.get('destination_triplet_component')} | "
            f"{r.get('n_gain_terms')} | {r.get('n_loss_terms')} | {r.get('largest_abs_rate_s^-1')} | {r.get('gain_loss_abs_residual_s^-1')} | {r.get('record_pair_classification')} |"
        )
    lines += [
        "",
        "## Largest type-71 matrix terms",
        "",
        "| record | direction | role | destination | superlevel | matrix rate | calt71 Aij | residual | partner status |",
        "|---:|---|---|---|---|---:|---:|---:|---|",
    ]
    for r in term_rows[:120]:
        lines.append(
            f"| {r.get('record')} | {r.get('direction')} | {r.get('matrix_role')} | {r.get('spectroscopic_level_label')} | {r.get('superlevel_level_label')} | "
            f"{r.get('matrix_rate_s^-1')} | {r.get('calt71_aij_from_log10_s^-1')} | {r.get('matrix_minus_calt71_aij_s^-1')} | {r.get('partner_status')} |"
        )
    lines += [
        "",
        "## Recommended next parity sequence",
        "",
        "1. Treat type 71 as verified when all rows match `calt71` Aij and all record-level gain/loss pairs close.",
        "2. Apply the same source-code handoff audit to type 68 collision redistribution and type 53 photoionization/recombination terms.",
        "3. After dominant non-type-50 local terms pass, compare solved level populations directly against `xo01_detail.fits`.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"record_csv": str(record_csv), "terms_csv": str(term_csv), "json": str(json_path), "markdown": str(md_path)}


def audit_type68_collision_rates(
    *,
    matrix_terms_csv: str | Path,
    normalized_solve_csv: str | Path | None = None,
    ion: str | None = None,
    triplet_only: bool = False,
    max_rows: int | None = 500,
) -> Dict[str, Any]:
    """Audit local matrix parity for XSTAR data type 68 collision terms.

    Type 68 is the He-like Zhang-Sampson collision path in the current
    full-global solver products.  The preserved rows already contain the
    effective collision strength/collision-rate handoff used by the evaluator:

    ``q_excitation_cm3_s`` or ``q_deexcitation_cm3_s`` -> ``q * ne`` -> matrix gain/loss term.

    This audit checks that local handoff and the off-diagonal/diagonal partner
    placement for each record/direction.  It is intentionally a matrix/local
    parity audit; it does not change solver physics and does not claim that the
    type-68 evaluator itself is a complete independent re-port of ``calt68``.
    """
    matrix_path = Path(matrix_terms_csv)
    matrix_rows = _read_csv_rows(matrix_path)
    solve_rows = _read_csv_rows(normalized_solve_csv)
    triplet = _triplet_levels_from_solve_rows(solve_rows)
    lookup = _make_term_lookup(matrix_rows)

    out_rows: List[Dict[str, Any]] = []
    record_pairs: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in matrix_rows:
        _fkey, data_type, source_label = _rate_family(row)
        if data_type != "68":
            continue
        row_g = _as_int(row.get("matrix_row_global_index"))
        col_g = _as_int(row.get("matrix_col_global_index"))
        from_g = _as_int(row.get("from_global_index"))
        to_g = _as_int(row.get("to_global_index"))
        is_triplet_touch = any(g in triplet for g in [row_g, col_g, from_g, to_g] if g is not None)
        if triplet_only and not is_triplet_touch:
            continue

        signed = _signed_value(row)
        matrix_rate = _rate_value(row)
        ne = _as_float(row.get("electron_density_cm^-3"))
        transition_kind = str(row.get("transition_kind") or "").strip()
        q_exc = _as_float(row.get("q_excitation_cm3_s"))
        q_de = _as_float(row.get("q_deexcitation_cm3_s"))
        directional_q = _as_float(row.get("directional_q_cm3_s"))
        scale = _as_float(row.get("collision_rate_scale_applied"), 1.0) or 1.0
        if directional_q is None:
            if "deexc" in transition_kind.lower():
                directional_q = q_de
            else:
                directional_q = q_exc
        expected = None
        if directional_q is not None and ne is not None:
            expected = float(directional_q) * float(ne) * float(scale)
        residual = ""
        rel = ""
        classification = "missing_directional_q_or_ne_or_matrix_rate"
        if expected is not None and matrix_rate is not None:
            residual_val = float(matrix_rate) - float(expected)
            rel_val = residual_val / max(abs(float(expected)), 1.0e-300)
            residual = residual_val
            rel = rel_val
            tol = max(1.0e-25, 1.0e-10 * abs(float(expected)))
            classification = "matrix_matches_q_ne_rate" if abs(residual_val) <= tol else "matrix_rate_mismatch_vs_q_ne_rate"

        direction = "row_gain" if signed is not None and signed > 0 else "row_loss" if signed is not None and signed < 0 else "row_source_or_unknown"
        rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
        partner = _partner_status(row, lookup)
        row_triplet_component = str(triplet.get(row_g or -999, {}).get("component") or "")
        touched_components = sorted(set(str(triplet[g].get("component") or "") for g in [row_g, col_g, from_g, to_g] if g in triplet))
        pair_key = (rec, transition_kind or "unknown_transition")
        pair = record_pairs.setdefault(pair_key, {
            "record": rec,
            "transition_kind": transition_kind,
            "n_terms": 0,
            "n_gain_terms": 0,
            "n_loss_terms": 0,
            "n_matrix_matches_q_ne_rate": 0,
            "n_partner_matches": 0,
            "abs_gain_sum_s^-1": 0.0,
            "abs_loss_sum_s^-1": 0.0,
            "largest_abs_rate_s^-1": 0.0,
            "from_global_index": from_g if from_g is not None else "",
            "to_global_index": to_g if to_g is not None else "",
            "from_level_label": row.get("from_level_label") or "",
            "to_level_label": row.get("to_level_label") or "",
            "touched_triplet_components": ";".join(touched_components),
            "is_triplet_touching": bool(touched_components),
        })
        pair["n_terms"] += 1
        if direction == "row_gain":
            pair["n_gain_terms"] += 1
            pair["abs_gain_sum_s^-1"] += abs(float(signed if signed is not None else matrix_rate or 0.0))
        elif direction == "row_loss":
            pair["n_loss_terms"] += 1
            pair["abs_loss_sum_s^-1"] += abs(float(signed if signed is not None else matrix_rate or 0.0))
        if classification == "matrix_matches_q_ne_rate":
            pair["n_matrix_matches_q_ne_rate"] += 1
        if partner.get("partner_status") == "matrix_gain_loss_partner_matches":
            pair["n_partner_matches"] += 1
        pair["largest_abs_rate_s^-1"] = max(float(pair["largest_abs_rate_s^-1"]), abs(float(signed if signed is not None else matrix_rate or 0.0)))

        out = {
            "ion": ion or "",
            "record": rec,
            "data_type": data_type,
            "source_label": source_label,
            "source_code_path": _RATE_FAMILY_SOURCE_PATHS.get(data_type, "not_yet_mapped_to_specific_fortran_path"),
            "fortran_ucalc_branch": "ucalc/calt68-style He-like Zhang-Sampson collision evaluator; matrix rate uses directional q * ne",
            "matrix_row_global_index": row_g if row_g is not None else "",
            "matrix_col_global_index": col_g if col_g is not None else "",
            "direction": direction,
            "matrix_role": row.get("matrix_role") or "",
            "transition_kind": transition_kind,
            "from_global_index": from_g if from_g is not None else "",
            "to_global_index": to_g if to_g is not None else "",
            "from_level_label": row.get("from_level_label") or "",
            "to_level_label": row.get("to_level_label") or "",
            "row_triplet_component": row_triplet_component,
            "touched_triplet_components": ";".join(touched_components),
            "is_triplet_touching": bool(touched_components),
            "electron_density_cm^-3": ne if ne is not None else "",
            "temperature_K": row.get("temperature_K") or "",
            "effective_temperature_K": row.get("xstar_calt67_68_effective_temperature_K") or "",
            "temperature_floor_applied": row.get("xstar_calt67_68_temperature_floor_applied") or "",
            "upsilon": row.get("upsilon") or "",
            "q_excitation_cm3_s": q_exc if q_exc is not None else "",
            "q_deexcitation_cm3_s": q_de if q_de is not None else "",
            "directional_q_cm3_s": directional_q if directional_q is not None else "",
            "collision_rate_scale_applied": scale,
            "expected_rate_q_ne_s^-1": expected if expected is not None else "",
            "matrix_rate_s^-1": matrix_rate if matrix_rate is not None else "",
            "signed_rate_s^-1": signed if signed is not None else "",
            "matrix_minus_expected_s^-1": residual,
            "relative_residual": rel,
            "rate_classification": classification,
            "partner_status": partner.get("partner_status"),
            "partner_count": partner.get("partner_count"),
            "partner_residual_s^-1": partner.get("partner_residual_s^-1"),
            "eval_method": row.get("eval_method") or "",
            "eval_diagnostic": row.get("eval_diagnostic") or "",
            "next_detail_audit_hint": "independently re-port calt68/ucalc from ATDB record inputs, then compare q, q*ne rate, off-diagonal gain, and diagonal loss",
        }
        out_rows.append(out)

    for pair in record_pairs.values():
        pair["gain_loss_abs_residual_s^-1"] = abs(float(pair.get("abs_gain_sum_s^-1") or 0.0) - float(pair.get("abs_loss_sum_s^-1") or 0.0))
        tol = max(1.0e-25, 1.0e-10 * max(float(pair.get("abs_gain_sum_s^-1") or 0.0), float(pair.get("abs_loss_sum_s^-1") or 0.0), 1.0))
        pair["record_pair_classification"] = "gain_loss_pair_matches" if float(pair["gain_loss_abs_residual_s^-1"]) <= tol else "gain_loss_pair_mismatch"
    record_rows = list(record_pairs.values())
    record_rows.sort(key=lambda r: -float(r.get("largest_abs_rate_s^-1") or 0.0))
    out_rows.sort(key=lambda r: -abs(float(r.get("signed_rate_s^-1") or r.get("matrix_rate_s^-1") or 0.0)))
    selected_rows = out_rows if max_rows is None or max_rows <= 0 else out_rows[: int(max_rows)]
    overall = {
        "ion": ion or "",
        "matrix_terms_csv": str(matrix_path),
        "normalized_solve_csv": str(normalized_solve_csv or ""),
        "n_type68_matrix_terms": len(out_rows),
        "n_type68_records_or_directions": len(record_rows),
        "n_type68_matrix_matches_q_ne_rate": sum(1 for r in out_rows if r.get("rate_classification") == "matrix_matches_q_ne_rate"),
        "n_type68_partner_matches": sum(1 for r in out_rows if r.get("partner_status") == "matrix_gain_loss_partner_matches"),
        "n_type68_gain_loss_record_pairs_matching": sum(1 for r in record_rows if r.get("record_pair_classification") == "gain_loss_pair_matches"),
        "n_type68_triplet_touching_terms": sum(1 for r in out_rows if r.get("is_triplet_touching")),
        "n_type68_triplet_population_row_terms": sum(1 for r in out_rows if str(r.get("row_triplet_component") or "") in {"f", "i", "r"}),
        "triplet_only": bool(triplet_only),
        "audit_scope": "type-68 local evaluator handoff q*ne -> full-global matrix plus gain/loss partner placement; no solver physics changed",
        "source_code_reference": "type-68 He-like Zhang-Sampson collision path; preserved products expose upsilon, q_excitation/q_deexcitation, directional_q, ne, and matrix terms",
        "recommended_next_step": "if type 68 passes q*ne/matrix placement, port/check type 53 photoionization/recombination source-sink closure next",
    }
    return {"overall": overall, "record_rows": record_rows, "term_rows": selected_rows}


def write_type68_collision_rate_audit(result: Mapping[str, Any], out_dir: str | Path, *, prefix: str = "xstar_type68_collision_rate_audit") -> Dict[str, str]:
    """Write type-68 collision matrix parity audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    record_rows = list(result.get("record_rows") or [])
    term_rows = list(result.get("term_rows") or [])
    overall = dict(result.get("overall") or {})
    record_csv = out / f"{prefix}_record_summary.csv"
    term_csv = out / f"{prefix}_terms.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    _write_csv(record_csv, record_rows)
    _write_csv(term_csv, term_rows)
    json_path.write_text(json.dumps({"overall": overall, "record_rows": record_rows, "term_rows": term_rows}, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# XSTAR type-68 collision rate audit",
        "",
        f"Ion: `{overall.get('ion','')}`",
        "",
        f"Type-68 matrix terms: `{overall.get('n_type68_matrix_terms')}`",
        f"Type-68 record/direction groups: `{overall.get('n_type68_records_or_directions')}`",
        f"Terms matching `q * ne`: `{overall.get('n_type68_matrix_matches_q_ne_rate')}`",
        f"Partner matches: `{overall.get('n_type68_partner_matches')}`",
        f"Gain/loss record-direction pairs matching: `{overall.get('n_type68_gain_loss_record_pairs_matching')}`",
        f"Triplet-touching terms: `{overall.get('n_type68_triplet_touching_terms')}`",
        f"Triplet population-row terms: `{overall.get('n_type68_triplet_population_row_terms')}`",
        "",
        "This audit checks the local handoff for XSTAR data type 68 collision terms: the preserved type-68 evaluator provides a directional collisional rate coefficient, which is multiplied by the local electron density and inserted as paired gain/loss matrix terms. It is a parity audit, not an empirical triplet-ratio adjustment.",
        "",
        "## Record/direction gain-loss summary",
        "",
        "| record | transition | from | to | triplet components | gain terms | loss terms | largest rate | gain-loss residual | classification |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for r in record_rows[:120]:
        lines.append(
            f"| {r.get('record')} | {r.get('transition_kind')} | {r.get('from_level_label')} | {r.get('to_level_label')} | {r.get('touched_triplet_components')} | "
            f"{r.get('n_gain_terms')} | {r.get('n_loss_terms')} | {r.get('largest_abs_rate_s^-1')} | {r.get('gain_loss_abs_residual_s^-1')} | {r.get('record_pair_classification')} |"
        )
    lines += [
        "",
        "## Largest type-68 matrix terms",
        "",
        "| record | direction | transition | from | to | q | ne | matrix rate | expected q*ne | residual | partner status |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in term_rows[:120]:
        lines.append(
            f"| {r.get('record')} | {r.get('direction')} | {r.get('transition_kind')} | {r.get('from_level_label')} | {r.get('to_level_label')} | "
            f"{r.get('directional_q_cm3_s')} | {r.get('electron_density_cm^-3')} | {r.get('matrix_rate_s^-1')} | {r.get('expected_rate_q_ne_s^-1')} | {r.get('matrix_minus_expected_s^-1')} | {r.get('partner_status')} |"
        )
    lines += [
        "",
        "## Recommended next parity sequence",
        "",
        "1. Treat type 68 matrix placement as verified when all rows match `directional_q * ne` and all gain/loss partners close.",
        "2. Independently re-port the Fortran `calt68`/`ucalc` evaluator if the next mismatch points to the collision-strength calculation rather than matrix placement.",
        "3. Move to type 53 photoionization/recombination source-sink closure after type 68 matrix parity passes.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"record_csv": str(record_csv), "terms_csv": str(term_csv), "json": str(json_path), "markdown": str(md_path)}



def audit_type53_source_sink_rates(
    *,
    matrix_terms_csv: str | Path,
    normalized_solve_csv: str | Path | None = None,
    ion: str | None = None,
    triplet_only: bool = False,
    max_rows: int | None = 500,
) -> Dict[str, Any]:
    """Audit XSTAR type-53 photoionization/recombination matrix closure.

    Type 53 is the largest remaining triplet-touching source/sink family after
    the type-50 line escape and type-71/type-68 local handoff checks.  The
    preserved full-global matrix terms contain two distinct type-53 branches:

    * photoionization loss from a bound level plus gain into the continuum/
      parent row, produced by the phint53 photoionization kernel; and
    * inverse-recombination/Milne gain from the continuum/parent row into a
      bound level plus the corresponding continuum diagonal loss.

    This audit is deliberately matrix-local.  It verifies gain/loss placement
    and, for the Milne branch, checks that the matrix uses the preserved
    source-code ``phint53``/``ucalc`` ans2 value.  The photoionization branch
    currently has no separate same-zone ans1 column in the preserved matrix
    product, so it is classified as a source/sink closure check rather than an
    independent Fortran integral re-evaluation.
    """
    matrix_path = Path(matrix_terms_csv)
    matrix_rows = _read_csv_rows(matrix_path)
    solve_rows = _read_csv_rows(normalized_solve_csv)
    triplet = _triplet_levels_from_solve_rows(solve_rows)
    lookup = _make_term_lookup(matrix_rows)

    out_rows: List[Dict[str, Any]] = []
    record_pairs: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in matrix_rows:
        _fkey, data_type, source_label = _rate_family(row)
        if data_type != "53":
            continue
        row_g = _as_int(row.get("matrix_row_global_index"))
        col_g = _as_int(row.get("matrix_col_global_index"))
        bound_g = _as_int(row.get("bound_global_index"))
        continuum_g = _as_int(row.get("continuum_or_parent_global_index"))
        touched_components = sorted(set(str(triplet[g].get("component") or "") for g in [row_g, col_g, bound_g] if g in triplet))
        is_triplet_touch = bool(touched_components)
        row_triplet_component = str(triplet.get(row_g or -999, {}).get("component") or "")
        if triplet_only and not is_triplet_touch:
            continue

        kind = str(row.get("matrix_term_kind") or "")
        role = str(row.get("matrix_role") or "")
        if "milne" in kind.lower() or str(row.get("inverse_recombination_mode") or "").strip():
            branch = "inverse_recombination_milne"
        else:
            branch = "photoionization"

        signed = _signed_value(row)
        matrix_rate = _rate_value(row)
        rec = str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip()
        partner = _partner_status(row, lookup)
        direction = "row_gain" if signed is not None and signed > 0 else "row_loss" if signed is not None and signed < 0 else "row_source_or_unknown"

        phint53_ans2 = _as_float(row.get("source_code_phint53_milne_ans2_rrrt_s^-1"))
        milne_alpha_ne = _as_float(row.get("source_code_milne_f90_rate_alpha_ne_s^-1"))
        expected = None
        expected_source = ""
        classification = "photoionization_kernel_matrix_rate_no_independent_ans1_column"
        residual = ""
        rel = ""
        if branch == "inverse_recombination_milne":
            expected = phint53_ans2
            expected_source = "source_code_phint53_milne_ans2_rrrt_s^-1"
            classification = "missing_phint53_milne_ans2_or_matrix_rate"
            if expected is not None and matrix_rate is not None:
                residual_val = float(matrix_rate) - float(expected)
                rel_val = residual_val / max(abs(float(expected)), 1.0e-300)
                residual = residual_val
                rel = rel_val
                tol = max(1.0e-30, 1.0e-10 * abs(float(expected)))
                classification = "matrix_matches_phint53_milne_ans2" if abs(residual_val) <= tol else "matrix_rate_mismatch_vs_phint53_milne_ans2"

        pair_key = (rec, branch)
        pair = record_pairs.setdefault(pair_key, {
            "record": rec,
            "branch": branch,
            "n_terms": 0,
            "n_gain_terms": 0,
            "n_loss_terms": 0,
            "n_partner_matches": 0,
            "n_matrix_matches_expected_rate": 0,
            "abs_gain_sum_s^-1": 0.0,
            "abs_loss_sum_s^-1": 0.0,
            "largest_abs_rate_s^-1": 0.0,
            "bound_global_index": bound_g if bound_g is not None else "",
            "continuum_or_parent_global_index": continuum_g if continuum_g is not None else "",
            "bound_level": row.get("bound_level") or "",
            "target_ion_stage": row.get("target_ion_stage") or "",
            "parent_ion_stage": row.get("parent_ion_stage") or "",
            "touched_triplet_components": ";".join(touched_components),
            "is_triplet_touching": bool(touched_components),
        })
        pair["n_terms"] += 1
        if direction == "row_gain":
            pair["n_gain_terms"] += 1
            pair["abs_gain_sum_s^-1"] += abs(float(signed if signed is not None else matrix_rate or 0.0))
        elif direction == "row_loss":
            pair["n_loss_terms"] += 1
            pair["abs_loss_sum_s^-1"] += abs(float(signed if signed is not None else matrix_rate or 0.0))
        if partner.get("partner_status") == "matrix_gain_loss_partner_matches":
            pair["n_partner_matches"] += 1
        if classification in {"matrix_matches_phint53_milne_ans2", "photoionization_kernel_matrix_rate_no_independent_ans1_column"}:
            pair["n_matrix_matches_expected_rate"] += 1
        pair["largest_abs_rate_s^-1"] = max(float(pair["largest_abs_rate_s^-1"]), abs(float(signed if signed is not None else matrix_rate or 0.0)))

        out = {
            "ion": ion or "",
            "record": rec,
            "data_type": data_type,
            "branch": branch,
            "source_label": source_label,
            "source_code_path": _RATE_FAMILY_SOURCE_PATHS.get(data_type, "not_yet_mapped_to_specific_fortran_path"),
            "fortran_ucalc_branch": "ucalc.f90 type 53: phint53 photoionization ans1 and recombination/Milne ans2; matrix inserts paired bound<->continuum source/sink terms",
            "matrix_row_global_index": row_g if row_g is not None else "",
            "matrix_col_global_index": col_g if col_g is not None else "",
            "direction": direction,
            "matrix_term_kind": kind,
            "matrix_role": role,
            "signed_rate_s^-1": signed if signed is not None else "",
            "matrix_rate_s^-1": matrix_rate if matrix_rate is not None else "",
            "expected_rate_s^-1": expected if expected is not None else "",
            "expected_rate_source": expected_source,
            "matrix_minus_expected_s^-1": residual,
            "relative_residual": rel,
            "rate_classification": classification,
            "partner_status": partner.get("partner_status"),
            "partner_count": partner.get("partner_count"),
            "partner_residual_s^-1": partner.get("partner_residual_s^-1"),
            "bound_global_index": bound_g if bound_g is not None else "",
            "continuum_or_parent_global_index": continuum_g if continuum_g is not None else "",
            "bound_level": row.get("bound_level") or "",
            "record_ion_stage": row.get("record_ion_stage") or "",
            "target_ion_stage": row.get("target_ion_stage") or "",
            "parent_ion_stage": row.get("parent_ion_stage") or "",
            "triplet_component": row.get("triplet_component") or "",
            "row_triplet_component": row_triplet_component,
            "touched_triplet_components": ";".join(touched_components),
            "is_triplet_touching": bool(touched_components),
            "radiation_field_mode": row.get("radiation_field_mode") or "",
            "type53_phint53_scale": row.get("type53_phint53_scale") or "",
            "phint53_status": row.get("phint53_status") or "",
            "inverse_recombination_mode": row.get("inverse_recombination_mode") or "",
            "phint53_milne_ans2_status": row.get("phint53_milne_ans2_status") or "",
            "source_code_phint53_milne_ans2_rrrt_s^-1": phint53_ans2 if phint53_ans2 is not None else "",
            "source_code_milne_f90_rate_alpha_ne_s^-1": milne_alpha_ne if milne_alpha_ne is not None else "",
            "milne_alpha_ne_over_phint53_ans2": (milne_alpha_ne / phint53_ans2) if (milne_alpha_ne is not None and phint53_ans2 not in (None, 0.0)) else "",
            "warning": row.get("warning") or "",
            "next_detail_audit_hint": "replace placeholder radiation with reconstructed same-zone bremsa/epi and compare phint53 ans1/ans2 directly against XSTAR detail/live state",
        }
        out_rows.append(out)

    for pair in record_pairs.values():
        pair["gain_loss_abs_residual_s^-1"] = abs(float(pair.get("abs_gain_sum_s^-1") or 0.0) - float(pair.get("abs_loss_sum_s^-1") or 0.0))
        tol = max(1.0e-30, 1.0e-10 * max(float(pair.get("abs_gain_sum_s^-1") or 0.0), float(pair.get("abs_loss_sum_s^-1") or 0.0), 1.0))
        pair["record_pair_classification"] = "gain_loss_pair_matches" if float(pair["gain_loss_abs_residual_s^-1"]) <= tol else "gain_loss_pair_mismatch"
    record_rows = list(record_pairs.values())
    record_rows.sort(key=lambda r: -float(r.get("largest_abs_rate_s^-1") or 0.0))
    out_rows.sort(key=lambda r: -abs(float(r.get("signed_rate_s^-1") or r.get("matrix_rate_s^-1") or 0.0)))
    selected_rows = out_rows if max_rows is None or max_rows <= 0 else out_rows[: int(max_rows)]
    overall = {
        "ion": ion or "",
        "matrix_terms_csv": str(matrix_path),
        "normalized_solve_csv": str(normalized_solve_csv or ""),
        "n_type53_matrix_terms": len(out_rows),
        "n_type53_record_branches": len(record_rows),
        "n_type53_photoionization_terms": sum(1 for r in out_rows if r.get("branch") == "photoionization"),
        "n_type53_milne_terms": sum(1 for r in out_rows if r.get("branch") == "inverse_recombination_milne"),
        "n_type53_partner_matches": sum(1 for r in out_rows if r.get("partner_status") == "matrix_gain_loss_partner_matches"),
        "n_type53_gain_loss_record_pairs_matching": sum(1 for r in record_rows if r.get("record_pair_classification") == "gain_loss_pair_matches"),
        "n_type53_milne_matrix_matches_phint53_ans2": sum(1 for r in out_rows if r.get("rate_classification") == "matrix_matches_phint53_milne_ans2"),
        "n_type53_triplet_touching_terms": sum(1 for r in out_rows if r.get("is_triplet_touching")),
        "n_type53_triplet_population_row_terms": sum(1 for r in out_rows if str(r.get("row_triplet_component") or "") in {"f", "i", "r"}),
        "triplet_only": bool(triplet_only),
        "audit_scope": "type-53 photoionization and inverse-recombination/Milne source-sink matrix closure; no solver physics changed",
        "source_code_reference": "ucalc.f90 type 53 / phint53-style continuum integrals; current matrix products expose placeholder-radiation photoionization rates and source-code phint53 Milne ans2 values",
        "recommended_next_step": "replace placeholder type-53 radiation context with reconstructed same-zone detail bremsa/epi and compare phint53 ans1/ans2 against XSTAR local state; then audit type 63/69/77 and level populations",
    }
    return {"overall": overall, "record_rows": record_rows, "term_rows": selected_rows}


def write_type53_source_sink_rate_audit(result: Mapping[str, Any], out_dir: str | Path, *, prefix: str = "xstar_type53_source_sink_rate_audit") -> Dict[str, str]:
    """Write type-53 source/sink closure audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    record_rows = list(result.get("record_rows") or [])
    term_rows = list(result.get("term_rows") or [])
    overall = dict(result.get("overall") or {})
    record_csv = out / f"{prefix}_record_summary.csv"
    term_csv = out / f"{prefix}_terms.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    _write_csv(record_csv, record_rows)
    _write_csv(term_csv, term_rows)
    json_path.write_text(json.dumps({"overall": overall, "record_rows": record_rows, "term_rows": term_rows}, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# XSTAR type-53 source/sink rate audit",
        "",
        f"Ion: `{overall.get('ion','')}`",
        "",
        f"Type-53 matrix terms: `{overall.get('n_type53_matrix_terms')}`",
        f"Type-53 record branches: `{overall.get('n_type53_record_branches')}`",
        f"Photoionization terms: `{overall.get('n_type53_photoionization_terms')}`",
        f"Milne/inverse-recombination terms: `{overall.get('n_type53_milne_terms')}`",
        f"Partner matches: `{overall.get('n_type53_partner_matches')}`",
        f"Gain/loss record-branch pairs matching: `{overall.get('n_type53_gain_loss_record_pairs_matching')}`",
        f"Milne terms matching preserved `phint53` ans2: `{overall.get('n_type53_milne_matrix_matches_phint53_ans2')}`",
        f"Triplet-touching terms: `{overall.get('n_type53_triplet_touching_terms')}`",
        f"Triplet population-row terms: `{overall.get('n_type53_triplet_population_row_terms')}`",
        "",
        "This audit checks XSTAR data type 53 as a local source/sink closure problem. It verifies that photoionization and inverse-recombination/Milne rates appear as paired off-diagonal gain and diagonal loss terms. For the Milne branch, it also checks that the matrix rate equals the preserved source-code `phint53` ans2 value. It does not yet independently re-evaluate the photoionization integral from the same-zone live radiation field.",
        "",
        "## Record-branch gain-loss summary",
        "",
        "| record | branch | bound global | continuum/global parent | triplet components | gain terms | loss terms | largest rate | gain-loss residual | classification |",
        "|---:|---|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for r in record_rows[:160]:
        lines.append(
            f"| {r.get('record')} | {r.get('branch')} | {r.get('bound_global_index')} | {r.get('continuum_or_parent_global_index')} | {r.get('touched_triplet_components')} | "
            f"{r.get('n_gain_terms')} | {r.get('n_loss_terms')} | {r.get('largest_abs_rate_s^-1')} | {r.get('gain_loss_abs_residual_s^-1')} | {r.get('record_pair_classification')} |"
        )
    lines += [
        "",
        "## Largest type-53 matrix terms",
        "",
        "| record | branch | direction | bound global | continuum/global parent | matrix rate | expected rate | classification | partner status | radiation/source mode |",
        "|---:|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for r in term_rows[:160]:
        mode = r.get("radiation_field_mode") or r.get("inverse_recombination_mode") or ""
        lines.append(
            f"| {r.get('record')} | {r.get('branch')} | {r.get('direction')} | {r.get('bound_global_index')} | {r.get('continuum_or_parent_global_index')} | "
            f"{r.get('matrix_rate_s^-1')} | {r.get('expected_rate_s^-1')} | {r.get('rate_classification')} | {r.get('partner_status')} | {mode} |"
        )
    lines += [
        "",
        "## Recommended next parity sequence",
        "",
        "1. Treat current type-53 matrix insertion as locally closed if all gain/loss partners close and all Milne matrix rows match preserved `phint53` ans2.",
        "2. The remaining type-53 physics gap is not matrix placement; it is reconstructing XSTAR's same-zone `epi`, `bremsa`, `bremsint`, continuum depths, and parent populations closely enough to re-evaluate `phint53` ans1/ans2 without placeholder radiation.",
        "3. After this closure check, audit type 63/69/77 placement and then compare Python populations directly with `xo01_detail.fits`.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"record_csv": str(record_csv), "terms_csv": str(term_csv), "json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "find_solver_product_paths",
    "audit_local_matrix_parity",
    "write_local_matrix_parity_audit",
    "audit_triplet_rate_terms",
    "write_triplet_rate_term_audit",
    "audit_type71_cascade_rates",
    "write_type71_cascade_rate_audit",
    "audit_type68_collision_rates",
    "write_type68_collision_rate_audit",
    "audit_type53_source_sink_rates",
    "write_type53_source_sink_rate_audit",
    "audit_type53_detail_phint53_radiation",
    "write_type53_detail_phint53_radiation_audit",
    "audit_type53_detail_phint53_scale",
    "write_type53_detail_phint53_scale_audit",
    "audit_type53_detail_phint53_bremsa_variants",
    "write_type53_detail_phint53_bremsa_variants_audit",
]

# -----------------------------------------------------------------------------
# v0.3.162: detail-continuum phint53 photoionization audit


def _parse_number_list(value: Any) -> List[float]:
    """Parse a Python-list-like numeric field from preserved CSV products."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            val = _as_float(item)
            if val is not None:
                out.append(float(val))
        return out
    text = str(value).strip()
    if not text:
        return []
    try:
        import ast
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple)):
            return [float(x) for x in parsed if _as_float(x) is not None]
    except Exception:
        pass
    import re
    vals: List[float] = []
    for token in re.findall(r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?", text):
        val = _as_float(token.replace("D", "E").replace("d", "e"))
        if val is not None:
            vals.append(float(val))
    return vals


def _type53_cross_section_pairs_cm2(value: Any) -> Tuple[List[float], List[float]]:
    """Decode type-53 rdat pairs as energy-above-threshold [Ry], sigma [cm^2]."""
    vals = _parse_number_list(value)
    e_ry: List[float] = []
    sigma_cm2: List[float] = []
    for i in range(0, len(vals) - 1, 2):
        e = _as_float(vals[i])
        sig_mb = _as_float(vals[i + 1])
        if e is None or sig_mb is None:
            continue
        e_ry.append(float(e))
        sigma_cm2.append(max(float(sig_mb), 0.0) * 1.0e-18)
    return e_ry, sigma_cm2


def _interp_linear_zero_outside(x: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    xx = float(x)
    if xx < float(xs[0]) or xx > float(xs[-1]):
        return 0.0
    if xx == float(xs[-1]):
        return float(ys[-1])
    # Cross-section grids are short compared with XSTAR continuum grids.  A
    # direct scan keeps this helper dependency-free and transparent.
    for i in range(len(xs) - 1):
        x0 = float(xs[i]); x1 = float(xs[i + 1])
        if x0 <= xx <= x1:
            if x1 <= x0:
                return float(ys[i])
            y0 = float(ys[i]); y1 = float(ys[i + 1])
            return y0 + (y1 - y0) * (xx - x0) / (x1 - x0)
    return 0.0


def _evaluate_phint53_photoionization_ans1_detail_continuum(
    *,
    e_ry: Sequence[float],
    sigma_cm2: Sequence[float],
    threshold_eV: float,
    epi_eV: Sequence[float],
    bremsa: Sequence[float],
) -> Dict[str, Any]:
    """Evaluate the photoionization side of XSTAR ``phint53.f90`` on a detail grid.

    This ports the source-code integrand for ``pirt``:

    ``pirt += integral sigma(E) * bremsa(E) / E dE``

    using the reconstructed ``xo01_detal4`` output-state continuum.  XSTAR's
    Fortran maps the cross section onto continuum bins through an averaged
    ``sgbar`` array before doing a trapezoidal integral.  This audit uses the
    same source-code integrand on the same detail ``epi(:)``/``bremsa(:)`` grid,
    with explicit reporting that exact in-loop parity still requires the live
    transfer-array dump at the call site.
    """
    eth = _as_float(threshold_eV)
    if eth is None or eth <= 0.0:
        return {"detail_phint53_photo_status": "not_evaluated_missing_threshold_eV"}
    if not e_ry or not sigma_cm2 or len(e_ry) != len(sigma_cm2):
        return {"detail_phint53_photo_status": "not_evaluated_missing_cross_section_pairs"}
    n = min(len(epi_eV), len(bremsa))
    if n < 2:
        return {"detail_phint53_photo_status": "not_evaluated_missing_detail_continuum_grid"}
    pairs = sorted(
        (float(eth) + max(float(er), 0.0) * 13.605692, max(float(sig), 0.0))
        for er, sig in zip(e_ry, sigma_cm2)
        if math.isfinite(float(er)) and math.isfinite(float(sig))
    )
    if len(pairs) < 2:
        return {"detail_phint53_photo_status": "not_evaluated_too_few_cross_section_pairs"}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    emin = max(float(eth), xs[0], float(epi_eV[0]))
    emax = min(xs[-1], float(epi_eV[n - 1]))
    if emax <= emin:
        return {
            "detail_phint53_photo_status": "not_evaluated_cross_section_outside_detail_continuum_grid",
            "detail_phint53_threshold_eV": float(eth),
            "detail_phint53_cross_section_energy_min_eV": xs[0],
            "detail_phint53_cross_section_energy_max_eV": xs[-1],
            "detail_phint53_epi_min_eV": float(epi_eV[0]),
            "detail_phint53_epi_max_eV": float(epi_eV[n - 1]),
        }
    # Select native detail grid points spanning the cross-section interval and
    # force both integration boundaries into the grid.
    grid: List[float] = [emin]
    for ee in epi_eV[:n]:
        e = float(ee)
        if emin < e < emax:
            grid.append(e)
    grid.append(emax)
    grid = sorted(set(grid))
    if len(grid) < 2:
        return {"detail_phint53_photo_status": "not_evaluated_too_few_detail_bins_in_cross_section_range"}
    # Interpolate bremsa on the native detail grid.
    epi = [float(x) for x in epi_eV[:n]]
    brem = [float(x) for x in bremsa[:n]]
    def b_at(e: float) -> float:
        return _interp_linear_zero_outside(e, epi, brem)
    total = 0.0
    sigma_weighted = 0.0
    used = 0
    prev_e = grid[0]
    prev_sig = _interp_linear_zero_outside(prev_e, xs, ys)
    prev_b = b_at(prev_e)
    prev_y = prev_sig * prev_b / max(prev_e, 1.0e-300)
    for e in grid[1:]:
        sig = _interp_linear_zero_outside(e, xs, ys)
        b = b_at(e)
        y = sig * b / max(e, 1.0e-300)
        de = e - prev_e
        if de > 0.0:
            total += 0.5 * (prev_y + y) * de
            sigma_weighted += 0.5 * (prev_sig + sig) * de
            used += 1
        prev_e, prev_sig, prev_y = e, sig, y
    return {
        "detail_phint53_photo_status": "evaluated_detail_continuum_photoionization_ans1_integrand",
        "detail_phint53_photo_ans1_s^-1": max(float(total), 0.0),
        "detail_phint53_threshold_eV": float(eth),
        "detail_phint53_cross_section_pairs": len(xs),
        "detail_phint53_cross_section_energy_min_eV": xs[0],
        "detail_phint53_cross_section_energy_max_eV": xs[-1],
        "detail_phint53_epi_min_eV": float(epi[0]),
        "detail_phint53_epi_max_eV": float(epi[-1]),
        "detail_phint53_integral_energy_min_eV": float(emin),
        "detail_phint53_integral_energy_max_eV": float(emax),
        "detail_phint53_n_detail_grid_points": len(grid),
        "detail_phint53_n_intervals_used": used,
        "detail_phint53_sigma_integral_cm2_eV": max(float(sigma_weighted), 0.0),
        "detail_phint53_source_file": "xstarlib/src/phint53.f90",
        "detail_phint53_detail_source": "xo01_detal4.fits reconstructed bremsa output-state continuum",
        "detail_phint53_warning": "Uses phint53 pirt integrand on reconstructed detail-output bremsa; exact call-site parity still requires XSTAR live bremsa(:), epi(:), opacities, and escape context at ucalc type 53.",
    }


def _evaluate_phint53_photoionization_ans1_detail_continuum_variants_fast(
    *,
    e_ry: Sequence[float],
    sigma_cm2: Sequence[float],
    threshold_eV: float,
    epi_eV: Sequence[float],
    bremsa_variants: Mapping[str, Sequence[float]],
) -> Dict[str, Dict[str, Any]]:
    """Vectorized v0.3.165 helper for one type-53 record and many continua.

    The v0.3.164 bremsa-variant audit evaluated each record/variant pair with
    repeated Python interpolation loops.  This helper keeps the same trapezoidal
    ``sigma(E) * bremsa(E) / E`` diagnostic integrand, but precomputes the
    cross-section values on the integration grid once per record and evaluates
    every requested bremsa variant with NumPy vector operations.

    It is still a Python audit prototype, not the production XSTAR backend.  The
    production target for these hot loops is a C++ kernel once the physics parity
    path is fixed.
    """
    names = [str(name) for name in bremsa_variants.keys()]
    if not names:
        return {}
    eth = _as_float(threshold_eV)
    if eth is None or eth <= 0.0:
        return {name: {"detail_phint53_photo_status": "not_evaluated_missing_threshold_eV"} for name in names}
    if not e_ry or not sigma_cm2 or len(e_ry) != len(sigma_cm2):
        return {name: {"detail_phint53_photo_status": "not_evaluated_missing_cross_section_pairs"} for name in names}
    n_epi = len(epi_eV)
    if n_epi < 2:
        return {name: {"detail_phint53_photo_status": "not_evaluated_missing_detail_continuum_grid"} for name in names}
    try:
        import numpy as np  # type: ignore
    except Exception:
        # Safe fallback keeps the public function usable in minimal
        # environments, though the normal package depends on NumPy elsewhere.
        return {
            name: _evaluate_phint53_photoionization_ans1_detail_continuum(
                e_ry=e_ry,
                sigma_cm2=sigma_cm2,
                threshold_eV=float(eth),
                epi_eV=epi_eV,
                bremsa=bremsa_variants[name],
            )
            for name in names
        }

    pairs = sorted(
        (float(eth) + max(float(er), 0.0) * 13.605692, max(float(sig), 0.0))
        for er, sig in zip(e_ry, sigma_cm2)
        if math.isfinite(float(er)) and math.isfinite(float(sig))
    )
    if len(pairs) < 2:
        return {name: {"detail_phint53_photo_status": "not_evaluated_too_few_cross_section_pairs"} for name in names}
    epi = np.asarray([float(x) for x in epi_eV], dtype=float)
    finite_epi = np.isfinite(epi)
    if epi.size < 2 or not bool(np.all(finite_epi)):
        return {name: {"detail_phint53_photo_status": "not_evaluated_invalid_detail_continuum_grid"} for name in names}
    # The FITS detail grid is already sorted in normal XSTAR output.  Sorting is
    # cheap compared with the old nested loops and makes in-memory tests safer.
    if bool(np.any(np.diff(epi) < 0.0)):
        order = np.argsort(epi)
        epi = epi[order]
    else:
        order = None
    xs = np.asarray([p[0] for p in pairs], dtype=float)
    ys = np.asarray([p[1] for p in pairs], dtype=float)
    emin = max(float(eth), float(xs[0]), float(epi[0]))
    emax = min(float(xs[-1]), float(epi[-1]))
    common_outside = {
        "detail_phint53_threshold_eV": float(eth),
        "detail_phint53_cross_section_energy_min_eV": float(xs[0]),
        "detail_phint53_cross_section_energy_max_eV": float(xs[-1]),
        "detail_phint53_epi_min_eV": float(epi[0]),
        "detail_phint53_epi_max_eV": float(epi[-1]),
    }
    if emax <= emin:
        return {
            name: {
                "detail_phint53_photo_status": "not_evaluated_cross_section_outside_detail_continuum_grid",
                **common_outside,
            }
            for name in names
        }
    inside = epi[(epi > emin) & (epi < emax)]
    grid = np.unique(np.concatenate(([emin], inside, [emax]))).astype(float)
    if grid.size < 2:
        return {name: {"detail_phint53_photo_status": "not_evaluated_too_few_detail_bins_in_cross_section_range"} for name in names}
    sigma_grid = np.interp(grid, xs, ys, left=0.0, right=0.0)
    kernel = sigma_grid / np.maximum(grid, 1.0e-300)
    # sigma integral is independent of bremsa and useful for source-code audits.
    # NumPy 2.x keeps ``trapezoid`` but some builds no longer expose ``trapz``.
    # Do not use ``getattr(np, "trapezoid", np.trapz)`` here: Python evaluates
    # the default argument eagerly, so it still crashes when ``np.trapz`` is
    # absent even if ``np.trapezoid`` exists.  Keep a tiny local fallback for
    # unusual NumPy builds or minimal test environments.
    if hasattr(np, "trapezoid"):
        trapz = np.trapezoid
    else:
        def trapz(y, x):  # type: ignore[no-redef]
            yy = np.asarray(y, dtype=float)
            xx = np.asarray(x, dtype=float)
            if yy.size < 2 or xx.size < 2:
                return 0.0
            return np.sum(0.5 * (yy[1:] + yy[:-1]) * (xx[1:] - xx[:-1]))

    sigma_weighted = float(trapz(sigma_grid, grid)) if grid.size >= 2 else 0.0
    results: Dict[str, Dict[str, Any]] = {}
    for name in names:
        braw = np.asarray([float(x) for x in bremsa_variants[name]], dtype=float)
        n = min(int(braw.size), int(epi.size))
        if n < 2:
            results[name] = {"detail_phint53_photo_status": "not_evaluated_missing_detail_continuum_grid"}
            continue
        b = braw[:n]
        epi_use = epi[:n]
        if order is not None and len(order) == len(braw):
            b = braw[order]
            epi_use = epi
        if not bool(np.all(np.isfinite(b))):
            b = np.where(np.isfinite(b), b, 0.0)
        b_grid = np.interp(grid, epi_use, b, left=0.0, right=0.0)
        total = float(trapz(kernel * b_grid, grid)) if grid.size >= 2 else 0.0
        results[name] = {
            "detail_phint53_photo_status": "evaluated_detail_continuum_photoionization_ans1_integrand_vectorized_v03165",
            "detail_phint53_photo_ans1_s^-1": max(float(total), 0.0),
            "detail_phint53_threshold_eV": float(eth),
            "detail_phint53_cross_section_pairs": int(xs.size),
            "detail_phint53_cross_section_energy_min_eV": float(xs[0]),
            "detail_phint53_cross_section_energy_max_eV": float(xs[-1]),
            "detail_phint53_epi_min_eV": float(epi[0]),
            "detail_phint53_epi_max_eV": float(epi[-1]),
            "detail_phint53_integral_energy_min_eV": float(emin),
            "detail_phint53_integral_energy_max_eV": float(emax),
            "detail_phint53_n_detail_grid_points": int(grid.size),
            "detail_phint53_n_intervals_used": int(max(grid.size - 1, 0)),
            "detail_phint53_sigma_integral_cm2_eV": max(float(sigma_weighted), 0.0),
            "detail_phint53_source_file": "xstarlib/src/phint53.f90",
            "detail_phint53_detail_source": "xo01_detal4.fits reconstructed bremsa output-state continuum",
            "detail_phint53_vectorized_audit": "v0.3.166 precomputed sigma(E) and evaluated all requested bremsa variants by vectorized dot/trapezoid operations",
            "detail_phint53_warning": "Uses phint53 pirt integrand on reconstructed detail-output bremsa; exact call-site parity still requires XSTAR live bremsa(:), epi(:), opacities, and escape context at ucalc type 53.",
        }
    return results


def _level_by_global_index(global_rows: Sequence[Mapping[str, Any]]) -> Dict[int, Mapping[str, Any]]:
    out: Dict[int, Mapping[str, Any]] = {}
    for row in global_rows:
        gi = _as_int(row.get("global_index"))
        if gi is not None:
            out[int(gi)] = row
    return out


def _first_existing_path(candidates: Sequence[Path]) -> Optional[Path]:
    for path in candidates:
        if path.exists():
            return path
    return None


def _infer_run_dir_from_benchmark(benchmark_dir: Path, ion: str | None) -> Optional[Path]:
    ion_norm = _normalise_ion_key(ion) if ion else ""
    for name in ["xstar_local_reproduction_suite_local_states.csv", "xstar_local_reproduction_suite_comparisons.csv"]:
        p = benchmark_dir / name
        if not p.exists():
            continue
        for row in _read_csv_rows(p):
            if ion_norm and _normalise_ion_key(row.get("ion")) != ion_norm:
                continue
            raw = str(row.get("run_dir") or "").strip()
            if not raw:
                continue
            rp = Path(raw)
            for base in [Path.cwd(), benchmark_dir, benchmark_dir.parent]:
                cand = rp if rp.is_absolute() else base / rp
                if cand.exists():
                    return cand
            return rp
    return None


def audit_type53_detail_phint53_radiation(
    *,
    benchmark_dir: str | Path | None = None,
    ion: str = "O VII",
    run_dir: str | Path | None = None,
    matrix_terms_csv: str | Path | None = None,
    adjacent_coupling_csv: str | Path | None = None,
    global_index_csv: str | Path | None = None,
    comparisons_csv: str | Path | None = None,
    zone_index: int | str = "last",
    triplet_only: bool = False,
    max_records: int | None = None,
) -> Dict[str, Any]:
    """Audit type-53 photoionization rates against reconstructed detail continuum.

    The v0.3.161 audit verified type-53 source/sink closure in the matrix.  This
    audit is the next narrower test: it recomputes the photoionization ``ans1``
    side of ``phint53.f90`` from the same-run ``xo01_detal4.fits`` continuum
    reconstruction and compares it with the matrix photoionization kernel rate.
    """
    t_start = time.perf_counter()
    root = Path(benchmark_dir) if benchmark_dir is not None else Path(".")
    paths = find_solver_product_paths(root, ion=ion, comparisons_csv=comparisons_csv) if benchmark_dir is not None else {}
    matrix_path = Path(matrix_terms_csv) if matrix_terms_csv is not None else paths.get("matrix_terms_csv")
    if matrix_path is None or not matrix_path.exists():
        raise ValueError("provide --matrix-terms-csv or --benchmark-dir with preserved solver products")
    product_dir = matrix_path.parent
    adjacent_path = Path(adjacent_coupling_csv) if adjacent_coupling_csv is not None else _first_existing_path([
        product_dir / "xstar_like_element_solver_adjacent_coupling_terms.csv",
    ])
    global_path = Path(global_index_csv) if global_index_csv is not None else _first_existing_path([
        product_dir / "xstar_like_element_solver_global_index.csv",
    ])
    if adjacent_path is None or not adjacent_path.exists():
        raise ValueError("adjacent coupling CSV not found; provide --adjacent-coupling-csv")
    if global_path is None or not global_path.exists():
        raise ValueError("global index CSV not found; provide --global-index-csv")

    matrix_rows = _read_csv_rows(matrix_path)
    adjacent_rows = _read_csv_rows(adjacent_path)
    global_rows = _read_csv_rows(global_path)
    level_by_g = _level_by_global_index(global_rows)
    adjacent_by_record = {str(r.get("record") or "").strip(): r for r in adjacent_rows if str(r.get("data_type") or "").strip() == "53"}

    # Optional same-run detail continuum.
    inferred_run_dir = Path(run_dir) if run_dir is not None else (_infer_run_dir_from_benchmark(root, ion) if benchmark_dir is not None else None)
    detail_status = "not_loaded"
    detail_source = ""
    epi: List[float] = []
    bremsa: List[float] = []
    detail_zone_index: Any = zone_index
    if inferred_run_dir is not None:
        try:
            from .xstar_detail import read_xstar_detail_run_state
            state = read_xstar_detail_run_state(inferred_run_dir, include_level_populations=False, include_line_transfer=False, include_continuum=True)
            if state.zones:
                if isinstance(zone_index, str) and str(zone_index).lower() == "last":
                    zone = state.zones[-1]
                else:
                    zi = int(zone_index)
                    zone = state.zones[zi - 1]
                if zone.continuum is not None and zone.continuum.epi and zone.continuum.bremsa:
                    epi = list(zone.continuum.epi)
                    bremsa = list(zone.continuum.bremsa)
                    detail_status = "loaded_detail_continuum"
                    detail_source = str(inferred_run_dir)
                    detail_zone_index = zone.zone_index
                else:
                    detail_status = "detail_state_loaded_but_continuum_missing"
                    detail_source = str(inferred_run_dir)
            else:
                detail_status = "detail_state_has_no_zones"
                detail_source = str(inferred_run_dir)
        except Exception as exc:
            detail_status = f"detail_continuum_load_failed:{type(exc).__name__}:{exc}"
            detail_source = str(inferred_run_dir)
    else:
        detail_status = "run_dir_not_supplied_or_inferable"

    candidates: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    for row in matrix_rows:
        if str(row.get("data_type") or "").strip() != "53":
            continue
        component = str(row.get("full_global_component") or "")
        role = str(row.get("matrix_role") or "")
        kind = str(row.get("matrix_term_kind") or "")
        if "photoionization" not in component and "photoionization" not in role and "phint53" not in kind:
            continue
        if "milne" in component.lower() or "xstar_ucalc" in str(row.get("global_type53_xstar_ucalc_term_id") or ""):
            continue
        if triplet_only:
            comp = str(row.get("triplet_component") or "").strip().lower()
            bg = _as_int(row.get("bound_global_index"))
            lev = level_by_g.get(int(bg)) if bg is not None else None
            is_trip = comp in {"f", "i", "r"} or str(lev.get("is_triplet_upper") if lev else "").lower() in {"true", "1", "yes"}
            if not is_trip:
                continue
        record = str(row.get("record") or "").strip()
        bg = _as_int(row.get("bound_global_index")) or -1
        cg = _as_int(row.get("continuum_or_parent_global_index")) or -1
        key = (record, int(bg), int(cg))
        # Keep one positive-rate representative per record/branch.  The gain
        # and loss partner rows were already checked by v0.3.161.
        rate = _as_float(row.get("full_global_rate_s^-1") or row.get("rate_s^-1"), 0.0) or 0.0
        prev = candidates.get(key)
        if prev is None or rate > float(prev.get("matrix_photoionization_rate_s^-1") or 0.0):
            candidates[key] = dict(row, matrix_photoionization_rate_s__1=rate)

    rows: List[Dict[str, Any]] = []
    for idx, ((record, bg, cg), mrow) in enumerate(candidates.items(), start=1):
        if max_records is not None and idx > int(max_records):
            break
        adj = adjacent_by_record.get(record, {})
        lev = level_by_g.get(int(bg), {}) if bg is not None else {}
        cont = level_by_g.get(int(cg), {}) if cg is not None else {}
        e_ry, sigma_cm2 = _type53_cross_section_pairs_cm2(adj.get("type53_raw_reals_full") or adj.get("raw_reals_preview"))
        threshold = _as_float(lev.get("binding_from_continuum_eV"))
        if threshold is None or threshold <= 0.0:
            ip = _as_float(lev.get("ionization_potential_eV"))
            ee = _as_float(lev.get("energy_eV"), 0.0) or 0.0
            threshold = (ip - ee) if ip is not None else None
        matrix_rate = _as_float(mrow.get("full_global_rate_s^-1") or mrow.get("rate_s^-1"), 0.0) or 0.0
        eval_result: Dict[str, Any]
        if detail_status != "loaded_detail_continuum":
            eval_result = {"detail_phint53_photo_status": detail_status}
        else:
            eval_result = _evaluate_phint53_photoionization_ans1_detail_continuum(
                e_ry=e_ry,
                sigma_cm2=sigma_cm2,
                threshold_eV=float(threshold or 0.0),
                epi_eV=epi,
                bremsa=bremsa,
            )
        detail_rate = _as_float(eval_result.get("detail_phint53_photo_ans1_s^-1"))
        if detail_rate is None:
            cls = "detail_phint53_not_evaluated"
            diff = None
            rel = None
            ratio = None
        else:
            diff = float(matrix_rate) - float(detail_rate)
            rel = abs(diff) / max(abs(float(detail_rate)), 1.0e-300)
            ratio = float(matrix_rate) / max(float(detail_rate), 1.0e-300)
            cls = "matrix_matches_detail_phint53_ans1" if rel <= 1.0e-6 else "matrix_differs_from_detail_phint53_ans1"
        rows.append({
            "row_kind": "type53_detail_phint53_photo_audit",
            "audit_version": "v0.3.162",
            "ion": ion,
            "record": record,
            "bound_global_index": bg,
            "bound_level": mrow.get("bound_level") or adj.get("idest1_guess"),
            "bound_level_label": lev.get("level_label"),
            "triplet_component": mrow.get("triplet_component") or lev.get("triplet_component"),
            "continuum_or_parent_global_index": cg,
            "continuum_level_label": cont.get("level_label"),
            "matrix_photoionization_rate_s^-1": matrix_rate,
            "detail_phint53_photo_ans1_s^-1": detail_rate,
            "matrix_minus_detail_phint53_ans1_s^-1": diff,
            "matrix_over_detail_phint53_ans1": ratio,
            "relative_error_vs_detail_phint53_ans1": rel,
            "classification": cls,
            "detail_continuum_status": detail_status,
            "detail_continuum_source": detail_source,
            "detail_zone_index": detail_zone_index,
            "n_detail_epi": len(epi),
            "n_type53_cross_section_pairs": len(e_ry),
            "threshold_eV_source": "global_index.binding_from_continuum_eV",
            **eval_result,
        })

    evaluated = [r for r in rows if r.get("classification") != "detail_phint53_not_evaluated"]
    matching = [r for r in evaluated if r.get("classification") == "matrix_matches_detail_phint53_ans1"]
    differing = [r for r in evaluated if r.get("classification") == "matrix_differs_from_detail_phint53_ans1"]
    top = sorted(rows, key=lambda r: abs(_as_float(r.get("matrix_minus_detail_phint53_ans1_s^-1"), 0.0) or 0.0), reverse=True)[:12]
    summary = {
        "audit_version": "v0.3.162",
        "ion": ion,
        "matrix_terms_csv": str(matrix_path),
        "adjacent_coupling_csv": str(adjacent_path),
        "global_index_csv": str(global_path),
        "run_dir": str(inferred_run_dir) if inferred_run_dir is not None else "",
        "detail_continuum_status": detail_status,
        "detail_zone_index": detail_zone_index,
        "triplet_only": bool(triplet_only),
        "n_type53_photoionization_records": len(rows),
        "n_detail_phint53_evaluated": len(evaluated),
        "n_detail_phint53_matches": len(matching),
        "n_detail_phint53_differs": len(differing),
        "n_detail_epi": len(epi),
        "top_records_by_abs_matrix_minus_detail": top,
        "status": "detail_phint53_photoionization_audit_completed",
        "warning": "Detail bremsa is reconstructed from xo01_detal4 output-state rows; use this audit to expose radiation-field differences before claiming exact phint53 call-site parity.",
    }
    return {"summary": summary, "rows": rows}


def write_type53_detail_phint53_radiation_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_type53_detail_phint53_radiation_audit",
) -> Dict[str, str]:
    """Write v0.3.162 detail-continuum phint53 audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(audit.get("rows", []) or [])
    summary = dict(audit.get("summary", {}) or {})
    csv_path = out / f"{prefix}_records.csv"
    _write_csv(csv_path, rows)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR type-53 detail-continuum phint53 radiation audit",
        "",
        f"ion: `{summary.get('ion')}`",
        f"detail_continuum_status: `{summary.get('detail_continuum_status')}`",
        f"triplet_only: `{summary.get('triplet_only')}`",
        f"n_type53_photoionization_records: `{summary.get('n_type53_photoionization_records')}`",
        f"n_detail_phint53_evaluated: `{summary.get('n_detail_phint53_evaluated')}`",
        f"n_detail_phint53_matches: `{summary.get('n_detail_phint53_matches')}`",
        f"n_detail_phint53_differs: `{summary.get('n_detail_phint53_differs')}`",
        "",
        "This audit recomputes the photoionization `ans1` side of `phint53.f90` from the reconstructed `xo01_detal4.fits` continuum and compares it with the preserved type-53 matrix photoionization rate.",
        "",
        "## Largest records by |matrix - detail phint53 ans1|",
        "",
    ]
    top = summary.get("top_records_by_abs_matrix_minus_detail") or []
    if top:
        lines.append("| record | bound | comp | matrix | detail ans1 | ratio | class |")
        lines.append("|---:|---|---|---:|---:|---:|---|")
        for row in top:
            lines.append(
                f"| {row.get('record')} | {row.get('bound_level_label')} | {row.get('triplet_component')} | "
                f"{row.get('matrix_photoionization_rate_s^-1')} | {row.get('detail_phint53_photo_ans1_s^-1')} | "
                f"{row.get('matrix_over_detail_phint53_ans1')} | {row.get('classification')} |"
            )
    else:
        lines.append("No evaluated records were available.")
    lines.extend(["", f"records_csv: `{csv_path.name}`", f"json: `{json_path.name}`"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"records_csv": str(csv_path), "json": str(json_path), "markdown": str(md_path)}

# -----------------------------------------------------------------------------
# v0.3.163: detail-continuum phint53 radiation scale/shape audit


def _median_float(values: Sequence[float]) -> Optional[float]:
    vals = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return 0.5 * (vals[mid - 1] + vals[mid])


def _percentile_float(values: Sequence[float], pct: float) -> Optional[float]:
    vals = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    x = max(0.0, min(100.0, float(pct))) / 100.0 * (len(vals) - 1)
    lo = int(math.floor(x))
    hi = int(math.ceil(x))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - x) + vals[hi] * (x - lo)


def _scale_factor_summary(records: Sequence[Mapping[str, Any]], *, scale: float) -> Dict[str, Any]:
    residuals: List[float] = []
    log_residuals: List[float] = []
    within_01 = 0
    within_05 = 0
    within_10 = 0
    within_25 = 0
    within_2x = 0
    n = 0
    for r in records:
        matrix = _as_float(r.get("matrix_photoionization_rate_s^-1"))
        detail = _as_float(r.get("detail_phint53_photo_ans1_s^-1"))
        if matrix is None or detail is None or matrix <= 0.0 or detail <= 0.0 or scale <= 0.0:
            continue
        scaled = scale * detail
        frac = (matrix - scaled) / max(abs(matrix), 1.0e-300)
        residuals.append(frac)
        ratio = matrix / scaled if scaled > 0.0 else math.nan
        if ratio > 0.0 and math.isfinite(ratio):
            log_residuals.append(math.log10(ratio))
        afrac = abs(frac)
        n += 1
        within_01 += int(afrac <= 0.01)
        within_05 += int(afrac <= 0.05)
        within_10 += int(afrac <= 0.10)
        within_25 += int(afrac <= 0.25)
        within_2x += int(0.5 <= matrix / scaled <= 2.0)
    return {
        "scale": scale,
        "n_scaled_records": n,
        "n_within_1pct_after_scaling": within_01,
        "n_within_5pct_after_scaling": within_05,
        "n_within_10pct_after_scaling": within_10,
        "n_within_25pct_after_scaling": within_25,
        "n_within_factor2_after_scaling": within_2x,
        "median_fractional_residual_after_scaling": _median_float(residuals),
        "p16_fractional_residual_after_scaling": _percentile_float(residuals, 16.0),
        "p84_fractional_residual_after_scaling": _percentile_float(residuals, 84.0),
        "median_abs_fractional_residual_after_scaling": _median_float([abs(v) for v in residuals]),
        "median_log10_matrix_over_scaled_detail": _median_float(log_residuals),
        "p16_log10_matrix_over_scaled_detail": _percentile_float(log_residuals, 16.0),
        "p84_log10_matrix_over_scaled_detail": _percentile_float(log_residuals, 84.0),
    }


def audit_type53_detail_phint53_scale(
    *,
    records_csv: str | Path | None = None,
    phint53_audit: Mapping[str, Any] | None = None,
    ion: str | None = None,
    scale_choice: str = "median_ratio",
) -> Dict[str, Any]:
    """Diagnose whether v0.3.162 type-53 residuals are scale-like.

    This audit consumes the record CSV or in-memory product written by
    :func:`audit_type53_detail_phint53_radiation`.  It does not change solver
    physics.  It measures the matrix/detail ``phint53`` ratio distribution,
    derives robust and least-squares multiplicative scale factors, and reports
    how many records would match after applying one global scale to the detail
    continuum result.  A narrow residual distribution means the mismatch is
    likely dominated by radiation-field normalization; broad or component-
    dependent residuals indicate a reconstruction/shape/cross-section problem.
    """
    if phint53_audit is not None:
        rows = [dict(r) for r in (phint53_audit.get("rows", []) or [])]
        input_source = "in_memory_phint53_audit"
        if ion is None:
            ion = str((phint53_audit.get("summary", {}) or {}).get("ion") or "")
    else:
        if records_csv is None:
            raise ValueError("provide --records-csv or phint53_audit")
        rows = _read_csv_rows(records_csv)
        input_source = str(records_csv)
    evaluated: List[Dict[str, Any]] = []
    ratios: List[float] = []
    matrices: List[float] = []
    details: List[float] = []
    for row in rows:
        matrix = _as_float(row.get("matrix_photoionization_rate_s^-1"))
        detail = _as_float(row.get("detail_phint53_photo_ans1_s^-1"))
        if matrix is None or detail is None or matrix <= 0.0 or detail <= 0.0:
            continue
        ratio = matrix / detail
        if not math.isfinite(ratio) or ratio <= 0.0:
            continue
        rr = dict(row)
        rr["matrix_over_detail_phint53_ans1"] = ratio
        evaluated.append(rr)
        ratios.append(ratio)
        matrices.append(matrix)
        details.append(detail)
    median_ratio = _median_float(ratios)
    mean_ratio = sum(ratios) / len(ratios) if ratios else None
    p16 = _percentile_float(ratios, 16.0)
    p84 = _percentile_float(ratios, 84.0)
    p05 = _percentile_float(ratios, 5.0)
    p95 = _percentile_float(ratios, 95.0)
    ls_num = sum(m * d for m, d in zip(matrices, details))
    ls_den = sum(d * d for d in details)
    least_squares_scale = (ls_num / ls_den) if ls_den > 0.0 else None
    log_ratios = [math.log10(r) for r in ratios if r > 0.0]
    geom_scale = 10.0 ** (_median_float(log_ratios) or 0.0) if log_ratios else None
    if scale_choice == "least_squares" and least_squares_scale is not None:
        chosen = least_squares_scale
    elif scale_choice == "geometric_median" and geom_scale is not None:
        chosen = geom_scale
    else:
        chosen = median_ratio or least_squares_scale or geom_scale or 1.0

    scaled_rows: List[Dict[str, Any]] = []
    for row in evaluated:
        matrix = _as_float(row.get("matrix_photoionization_rate_s^-1"))
        detail = _as_float(row.get("detail_phint53_photo_ans1_s^-1"))
        ratio = _as_float(row.get("matrix_over_detail_phint53_ans1"))
        if matrix is None or detail is None or ratio is None:
            continue
        scaled = chosen * detail
        frac = (matrix - scaled) / max(abs(matrix), 1.0e-300)
        after_ratio = matrix / scaled if scaled > 0.0 else None
        cls = "scaled_detail_within_10pct" if abs(frac) <= 0.10 else "scaled_detail_still_differs"
        scaled_rows.append({
            **row,
            "audit_version": "v0.3.163",
            "scale_choice": scale_choice,
            "chosen_detail_rate_scale": chosen,
            "scaled_detail_phint53_photo_ans1_s^-1": scaled,
            "matrix_minus_scaled_detail_phint53_ans1_s^-1": matrix - scaled,
            "matrix_over_scaled_detail_phint53_ans1": after_ratio,
            "scaled_relative_error_vs_matrix": frac,
            "scaled_classification": cls,
        })

    group_rows: List[Dict[str, Any]] = []
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in evaluated:
        key = (str(row.get("triplet_component") or "non_triplet"), str(row.get("threshold_eV_source") or ""))
        groups.setdefault(key, []).append(row)
    for (component, threshold_source), grows in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        gratios = [_as_float(r.get("matrix_over_detail_phint53_ans1")) for r in grows]
        gratios = [float(v) for v in gratios if v is not None and v > 0.0]
        group_rows.append({
            "audit_version": "v0.3.163",
            "ion": ion or (grows[0].get("ion") if grows else ""),
            "triplet_component": component,
            "threshold_eV_source": threshold_source,
            "n_records": len(grows),
            "median_matrix_over_detail": _median_float(gratios),
            "mean_matrix_over_detail": (sum(gratios) / len(gratios)) if gratios else None,
            "p16_matrix_over_detail": _percentile_float(gratios, 16.0),
            "p84_matrix_over_detail": _percentile_float(gratios, 84.0),
            "min_matrix_over_detail": min(gratios) if gratios else None,
            "max_matrix_over_detail": max(gratios) if gratios else None,
        })

    scaled_summary = _scale_factor_summary(evaluated, scale=float(chosen)) if evaluated else {}
    sorted_rows = sorted(scaled_rows, key=lambda r: abs(_as_float(r.get("scaled_relative_error_vs_matrix"), 0.0) or 0.0), reverse=True)
    summary = {
        "audit_version": "v0.3.163",
        "ion": ion or (evaluated[0].get("ion") if evaluated else ""),
        "input_records_csv": input_source,
        "scale_choice": scale_choice,
        "n_input_rows": len(rows),
        "n_evaluated_rows": len(evaluated),
        "median_matrix_over_detail": median_ratio,
        "geometric_median_matrix_over_detail": geom_scale,
        "mean_matrix_over_detail": mean_ratio,
        "least_squares_detail_rate_scale": least_squares_scale,
        "p05_matrix_over_detail": p05,
        "p16_matrix_over_detail": p16,
        "p84_matrix_over_detail": p84,
        "p95_matrix_over_detail": p95,
        "chosen_detail_rate_scale": chosen,
        **scaled_summary,
        "n_group_rows": len(group_rows),
        "top_scaled_residual_records": sorted_rows[:12],
        "status": "type53_detail_phint53_scale_audit_completed",
        "interpretation": "If one global scale brings most rows within tolerance, the v0.3.162 mismatch is dominated by detail/live radiation normalization. Outliers identify records needing phint53 grid, threshold, or live-state treatment checks.",
    }
    return {"summary": summary, "rows": scaled_rows, "groups": group_rows}


def write_type53_detail_phint53_scale_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_type53_detail_phint53_scale_audit",
) -> Dict[str, str]:
    """Write v0.3.163 detail-continuum phint53 scale/shape audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = dict(audit.get("summary", {}) or {})
    rows = list(audit.get("rows", []) or [])
    groups = list(audit.get("groups", []) or [])
    scaled_csv = out / f"{prefix}_scaled_records.csv"
    group_csv = out / f"{prefix}_group_summary.csv"
    _write_csv(scaled_csv, rows)
    _write_csv(group_csv, groups)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "rows": rows, "groups": groups}, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR type-53 detail phint53 scale/shape audit",
        "",
        f"ion: `{summary.get('ion')}`",
        f"n_evaluated_rows: `{summary.get('n_evaluated_rows')}`",
        f"median_matrix_over_detail: `{summary.get('median_matrix_over_detail')}`",
        f"least_squares_detail_rate_scale: `{summary.get('least_squares_detail_rate_scale')}`",
        f"chosen_detail_rate_scale: `{summary.get('chosen_detail_rate_scale')}`",
        f"n_within_10pct_after_scaling: `{summary.get('n_within_10pct_after_scaling')}`",
        f"n_within_factor2_after_scaling: `{summary.get('n_within_factor2_after_scaling')}`",
        f"median_abs_fractional_residual_after_scaling: `{summary.get('median_abs_fractional_residual_after_scaling')}`",
        "",
        "This audit applies one multiplicative scale to the reconstructed-detail `phint53` ans1 rates and reports whether the v0.3.162 matrix/detail discrepancy is mostly a radiation-field normalization difference or a record-dependent shape/reconstruction difference.",
        "",
        "## Group summary",
        "",
        "| component | n | median ratio | p16 | p84 | min | max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in groups:
        lines.append(
            f"| {g.get('triplet_component')} | {g.get('n_records')} | {g.get('median_matrix_over_detail')} | "
            f"{g.get('p16_matrix_over_detail')} | {g.get('p84_matrix_over_detail')} | "
            f"{g.get('min_matrix_over_detail')} | {g.get('max_matrix_over_detail')} |"
        )
    lines.extend(["", "## Largest residuals after chosen scale", ""])
    top = summary.get("top_scaled_residual_records") or []
    if top:
        lines.append("| record | bound | comp | matrix | detail | scaled detail | matrix/scaled detail | scaled class |")
        lines.append("|---:|---|---|---:|---:|---:|---:|---|")
        for row in top:
            lines.append(
                f"| {row.get('record')} | {row.get('bound_level_label')} | {row.get('triplet_component')} | "
                f"{row.get('matrix_photoionization_rate_s^-1')} | {row.get('detail_phint53_photo_ans1_s^-1')} | "
                f"{row.get('scaled_detail_phint53_photo_ans1_s^-1')} | {row.get('matrix_over_scaled_detail_phint53_ans1')} | "
                f"{row.get('scaled_classification')} |"
            )
    else:
        lines.append("No scaled rows were available.")
    lines.extend(["", f"scaled_records_csv: `{scaled_csv.name}`", f"group_summary_csv: `{group_csv.name}`", f"json: `{json_path.name}`"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"scaled_records_csv": str(scaled_csv), "group_summary_csv": str(group_csv), "json": str(json_path), "markdown": str(md_path)}


# -----------------------------------------------------------------------------
# v0.3.164/v0.3.165: detail-continuum bremsa reconstruction variant audit


def _zrems_value(row: Mapping[str, Any], idx: int) -> float:
    """Return one ``zrems(idx)`` value from a normalized detail-continuum row."""
    return float(_as_float(row.get(f"zrems({idx})"), 0.0) or 0.0)


def _continuum_bremsa_variants_from_detail_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    radius_cm: Optional[float],
) -> Dict[str, List[float]]:
    """Build candidate ``bremsa(:)`` arrays from ``xo01_detal4`` columns.

    XSTAR's live outward transfer path in ``trnfrc.f90`` uses
    ``zremsz(:) * exp(-dpthc(1,:)) / (12.56 * r19**2)``.  The detail file
    written by ``fstepr4.f90`` stores ``zrems(1:5,:)`` rather than ``zremsz``.
    These variants test whether any available detail column/combination can
    reproduce the matrix type-53 photoionization rates without a free scale.
    If all variants still need a large common scale, the missing quantity is
    probably live incident ``zremsz`` or a normalization that is not present in
    ``xo01_detal4.fits``.
    """
    r = float(radius_cm or 0.0)
    fpr2 = 12.56 * (r / 1.0e19) ** 2 if r > 0.0 else None
    if fpr2 is None or fpr2 <= 0.0:
        fpr2 = 1.0
    variants: Dict[str, List[float]] = {
        "sum_zrems_exp_fwd_over_fpr2": [],
        "sum_zrems_no_att_over_fpr2": [],
        "sum_zrems_exp_bck_over_fpr2": [],
        "zrems1_over_fpr2_trnfrc_inward_form": [],
        "zrems1_exp_fwd_over_fpr2": [],
        "zrems2_exp_fwd_over_fpr2": [],
        "zrems3_exp_fwd_over_fpr2": [],
        "zrems4_exp_fwd_over_fpr2": [],
        "zrems5_exp_fwd_over_fpr2": [],
        "sum_zrems_exp_fwd_no_geometric_divide": [],
    }
    for row in rows:
        zvals = [_zrems_value(row, i) for i in range(1, 6)]
        zsum = sum(zvals)
        fwd = max(float(_as_float(row.get("fwd_dpth"), 0.0) or 0.0), 0.0)
        bck = max(float(_as_float(row.get("bck_dpth"), 0.0) or 0.0), 0.0)
        efwd = math.exp(-fwd)
        ebck = math.exp(-bck)
        variants["sum_zrems_exp_fwd_over_fpr2"].append(zsum * efwd / fpr2)
        variants["sum_zrems_no_att_over_fpr2"].append(zsum / fpr2)
        variants["sum_zrems_exp_bck_over_fpr2"].append(zsum * ebck / fpr2)
        variants["zrems1_over_fpr2_trnfrc_inward_form"].append(zvals[0] / fpr2)
        for i in range(1, 6):
            variants[f"zrems{i}_exp_fwd_over_fpr2"].append(zvals[i - 1] * efwd / fpr2)
        variants["sum_zrems_exp_fwd_no_geometric_divide"].append(zsum * efwd)
    return variants


def _type53_photoionization_candidates(
    matrix_rows: Sequence[Mapping[str, Any]],
    level_by_g: Mapping[int, Mapping[str, Any]],
    *,
    triplet_only: bool = False,
) -> Dict[Tuple[str, int, int], Dict[str, Any]]:
    """Return one representative matrix photoionization row per type-53 branch."""
    candidates: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    for row in matrix_rows:
        if str(row.get("data_type") or "").strip() != "53":
            continue
        component = str(row.get("full_global_component") or "")
        role = str(row.get("matrix_role") or "")
        kind = str(row.get("matrix_term_kind") or "")
        if "photoionization" not in component and "photoionization" not in role and "phint53" not in kind:
            continue
        if "milne" in component.lower() or "xstar_ucalc" in str(row.get("global_type53_xstar_ucalc_term_id") or ""):
            continue
        if triplet_only:
            comp = str(row.get("triplet_component") or "").strip().lower()
            bg0 = _as_int(row.get("bound_global_index"))
            lev0 = level_by_g.get(int(bg0)) if bg0 is not None else None
            is_trip = comp in {"f", "i", "r"} or str(lev0.get("is_triplet_upper") if lev0 else "").lower() in {"true", "1", "yes"}
            if not is_trip:
                continue
        record = str(row.get("record") or "").strip()
        bg = _as_int(row.get("bound_global_index")) or -1
        cg = _as_int(row.get("continuum_or_parent_global_index")) or -1
        key = (record, int(bg), int(cg))
        rate = _as_float(row.get("full_global_rate_s^-1") or row.get("rate_s^-1"), 0.0) or 0.0
        prev = candidates.get(key)
        if prev is None or rate > float(prev.get("matrix_photoionization_rate_s^-1") or 0.0):
            rr = dict(row)
            rr["matrix_photoionization_rate_s^-1"] = rate
            candidates[key] = rr
    return candidates


def _summarize_variant_ratios(rows: Sequence[Mapping[str, Any]], *, variant: str) -> Dict[str, Any]:
    ratios: List[float] = []
    matrices: List[float] = []
    details: List[float] = []
    for row in rows:
        matrix = _as_float(row.get("matrix_photoionization_rate_s^-1"))
        detail = _as_float(row.get("variant_detail_phint53_photo_ans1_s^-1"))
        if matrix is None or detail is None or matrix <= 0.0 or detail <= 0.0:
            continue
        ratio = matrix / detail
        if math.isfinite(ratio) and ratio > 0.0:
            ratios.append(ratio)
            matrices.append(matrix)
            details.append(detail)
    ls_num = sum(m * d for m, d in zip(matrices, details))
    ls_den = sum(d * d for d in details)
    ls = (ls_num / ls_den) if ls_den > 0.0 else None
    median = _median_float(ratios)
    scale = median or ls or 1.0
    no_scale_within10 = 0
    scaled_within10 = 0
    scaled_within5 = 0
    scaled_within2x = 0
    absfrac: List[float] = []
    abslog: List[float] = []
    for row in rows:
        matrix = _as_float(row.get("matrix_photoionization_rate_s^-1"))
        detail = _as_float(row.get("variant_detail_phint53_photo_ans1_s^-1"))
        if matrix is None or detail is None or matrix <= 0.0 or detail <= 0.0:
            continue
        no_frac = abs((matrix - detail) / max(abs(matrix), 1.0e-300))
        no_scale_within10 += int(no_frac <= 0.10)
        scaled = scale * detail
        frac = abs((matrix - scaled) / max(abs(matrix), 1.0e-300))
        absfrac.append(frac)
        scaled_within5 += int(frac <= 0.05)
        scaled_within10 += int(frac <= 0.10)
        if scaled > 0.0:
            ratio = matrix / scaled
            scaled_within2x += int(0.5 <= ratio <= 2.0)
            if ratio > 0.0 and math.isfinite(ratio):
                abslog.append(abs(math.log10(ratio)))
    return {
        "audit_version": "v0.3.164",
        "bremsa_variant": variant,
        "n_evaluated_rows": len(ratios),
        "median_matrix_over_variant_detail": median,
        "least_squares_variant_scale": ls,
        "p16_matrix_over_variant_detail": _percentile_float(ratios, 16.0),
        "p84_matrix_over_variant_detail": _percentile_float(ratios, 84.0),
        "min_matrix_over_variant_detail": min(ratios) if ratios else None,
        "max_matrix_over_variant_detail": max(ratios) if ratios else None,
        "n_within_10pct_without_free_scale": no_scale_within10,
        "chosen_variant_scale": scale,
        "n_within_5pct_after_variant_scale": scaled_within5,
        "n_within_10pct_after_variant_scale": scaled_within10,
        "n_within_factor2_after_variant_scale": scaled_within2x,
        "median_abs_fractional_residual_after_variant_scale": _median_float(absfrac),
        "median_abs_log10_residual_after_variant_scale": _median_float(abslog),
    }


def audit_type53_detail_phint53_bremsa_variants(
    *,
    benchmark_dir: str | Path | None = None,
    ion: str = "O VII",
    run_dir: str | Path | None = None,
    matrix_terms_csv: str | Path | None = None,
    adjacent_coupling_csv: str | Path | None = None,
    global_index_csv: str | Path | None = None,
    comparisons_csv: str | Path | None = None,
    zone_index: int | str = "last",
    triplet_only: bool = False,
    max_records: int | None = None,
    variant_names: Sequence[str] | None = None,
    fast: bool = False,
    profile: bool = False,
    # In-memory hooks used by tests and notebooks.
    matrix_rows: Sequence[Mapping[str, Any]] | None = None,
    adjacent_rows: Sequence[Mapping[str, Any]] | None = None,
    global_rows: Sequence[Mapping[str, Any]] | None = None,
    continuum_variants: Mapping[str, Tuple[Sequence[float], Sequence[float]]] | None = None,
) -> Dict[str, Any]:
    """Compare type-53 phint53 rates from several ``xo01_detal4`` bremsa variants.

    v0.3.163 showed that the default reconstructed detail continuum has the
    right type-53 shape but a large normalization offset.  This audit checks
    whether the offset can be removed by another detail-file column choice
    (different ``zrems`` component, attenuation side, or geometric divisor), or
    whether all available detail variants still require a large free scale.  The
    latter outcome points to the XSTAR source-code fact that ``trnfrc.f90`` uses
    live incident ``zremsz(:)`` for the outward ``bremsa(:)``, while
    ``fstepr4.f90`` writes only ``zrems(1:5,:)`` to ``xo01_detal4.fits``.
    """
    t_start = time.perf_counter()
    root = Path(benchmark_dir) if benchmark_dir is not None else Path(".")
    paths = find_solver_product_paths(root, ion=ion, comparisons_csv=comparisons_csv) if benchmark_dir is not None else {}
    matrix_path = Path(matrix_terms_csv) if matrix_terms_csv is not None else paths.get("matrix_terms_csv")
    product_dir = matrix_path.parent if matrix_path is not None else Path(".")
    adjacent_path = Path(adjacent_coupling_csv) if adjacent_coupling_csv is not None else _first_existing_path([
        product_dir / "xstar_like_element_solver_adjacent_coupling_terms.csv",
    ])
    global_path = Path(global_index_csv) if global_index_csv is not None else _first_existing_path([
        product_dir / "xstar_like_element_solver_global_index.csv",
    ])
    if matrix_rows is None:
        if matrix_path is None or not matrix_path.exists():
            raise ValueError("provide --matrix-terms-csv or --benchmark-dir with preserved solver products")
        matrix_rows = _read_csv_rows(matrix_path)
    if adjacent_rows is None:
        if adjacent_path is None or not adjacent_path.exists():
            raise ValueError("adjacent coupling CSV not found; provide --adjacent-coupling-csv")
        adjacent_rows = _read_csv_rows(adjacent_path)
    if global_rows is None:
        if global_path is None or not global_path.exists():
            raise ValueError("global index CSV not found; provide --global-index-csv")
        global_rows = _read_csv_rows(global_path)

    level_by_g = _level_by_global_index(global_rows)
    adjacent_by_record = {str(r.get("record") or "").strip(): r for r in adjacent_rows if str(r.get("data_type") or "").strip() == "53"}
    detail_status = "not_loaded"
    detail_source = ""
    detail_zone_index: Any = zone_index
    variant_map: Dict[str, Tuple[List[float], List[float]]] = {}
    radius_cm: Optional[float] = None
    if continuum_variants is not None:
        for name, pair in continuum_variants.items():
            epi_v, brem_v = pair
            variant_map[str(name)] = ([float(x) for x in epi_v], [float(x) for x in brem_v])
        detail_status = "loaded_in_memory_continuum_variants"
        detail_source = "in_memory"
    else:
        inferred_run_dir = Path(run_dir) if run_dir is not None else (_infer_run_dir_from_benchmark(root, ion) if benchmark_dir is not None else None)
        if inferred_run_dir is not None:
            try:
                from .xstar_detail import read_xstar_detail_run_state
                state = read_xstar_detail_run_state(inferred_run_dir, include_level_populations=False, include_line_transfer=False, include_continuum=True)
                if state.zones:
                    if isinstance(zone_index, str) and str(zone_index).lower() == "last":
                        zone = state.zones[-1]
                    else:
                        zone = state.zones[int(zone_index) - 1]
                    detail_zone_index = zone.zone_index
                    radius_cm = zone.radius_cm
                    crecs = list(getattr(zone.continuum, "continuum_records", []) or [])
                    epi = list(zone.continuum.epi or [])
                    if crecs and epi:
                        for name, brem in _continuum_bremsa_variants_from_detail_rows(crecs, radius_cm=zone.radius_cm).items():
                            variant_map[name] = (epi, brem)
                        # Preserve the exact default reconstruction as a named
                        # variant in case the detail reader changes later.
                        if zone.continuum.bremsa:
                            variant_map["default_reader_bremsa"] = (epi, list(zone.continuum.bremsa))
                        detail_status = "loaded_detail_continuum_variants"
                        detail_source = str(inferred_run_dir)
                    else:
                        detail_status = "detail_state_loaded_but_continuum_rows_missing"
                        detail_source = str(inferred_run_dir)
                else:
                    detail_status = "detail_state_has_no_zones"
                    detail_source = str(inferred_run_dir)
            except Exception as exc:
                detail_status = f"detail_continuum_variant_load_failed:{type(exc).__name__}:{exc}"
                detail_source = str(inferred_run_dir)
        else:
            detail_status = "run_dir_not_supplied_or_inferable"

    # v0.3.165 performance cleanup: choose variants before the expensive
    # integration loop and evaluate all selected variants together for each
    # record.  ``fast`` intentionally exercises only the physically useful
    # candidate continua that diagnosed the v0.3.164 normalization gap.
    fast_default_variants = [
        "default_reader_bremsa",
        "sum_zrems_no_att_over_fpr2",
        "zrems1_over_fpr2_trnfrc_inward_form",
        "sum_zrems_exp_fwd_no_geometric_divide",
    ]
    requested_variants = [str(v).strip() for v in (variant_names or []) if str(v).strip()]
    if fast and not requested_variants:
        requested_variants = fast_default_variants
    requested_missing: List[str] = []
    if requested_variants:
        filtered: Dict[str, Tuple[List[float], List[float]]] = {}
        for name in requested_variants:
            if name in variant_map:
                filtered[name] = variant_map[name]
            else:
                requested_missing.append(name)
        variant_map = filtered

    candidates = _type53_photoionization_candidates(matrix_rows, level_by_g, triplet_only=triplet_only)
    candidate_items = list(candidates.items())
    if max_records is not None:
        candidate_items = candidate_items[: int(max_records)]

    variant_rows_by_name: Dict[str, List[Dict[str, Any]]] = {name: [] for name in variant_map}
    variant_summaries: List[Dict[str, Any]] = []
    integration_t0 = time.perf_counter()
    n_vectorized_record_batches = 0
    n_evaluated_variant_record_pairs = 0
    if variant_map:
        # In normal detail files all variants share the same epi(:).  In-memory
        # tests may pass separate grids, so group by grid to keep correctness.
        variant_groups: Dict[Tuple[float, ...], Dict[str, Tuple[List[float], List[float]]]] = {}
        for vname, pair in variant_map.items():
            epi_v, _ = pair
            key = tuple(float(x) for x in epi_v)
            variant_groups.setdefault(key, {})[vname] = pair
        for (record, bg, cg), mrow in candidate_items:
            adj = adjacent_by_record.get(record, {})
            lev = level_by_g.get(int(bg), {}) if bg is not None else {}
            cont = level_by_g.get(int(cg), {}) if cg is not None else {}
            e_ry, sigma_cm2 = _type53_cross_section_pairs_cm2(adj.get("type53_raw_reals_full") or adj.get("raw_reals_preview"))
            threshold = _as_float(lev.get("binding_from_continuum_eV"))
            if threshold is None or threshold <= 0.0:
                ip = _as_float(lev.get("ionization_potential_eV"))
                ee = _as_float(lev.get("energy_eV"), 0.0) or 0.0
                threshold = (ip - ee) if ip is not None else None
            matrix_rate = _as_float(mrow.get("matrix_photoionization_rate_s^-1") or mrow.get("full_global_rate_s^-1") or mrow.get("rate_s^-1"), 0.0) or 0.0
            for epi_key, grouped in variant_groups.items():
                epi_values = list(epi_key)
                brem_by_variant = {name: pair[1] for name, pair in grouped.items()}
                evals = _evaluate_phint53_photoionization_ans1_detail_continuum_variants_fast(
                    e_ry=e_ry,
                    sigma_cm2=sigma_cm2,
                    threshold_eV=float(threshold or 0.0),
                    epi_eV=epi_values,
                    bremsa_variants=brem_by_variant,
                )
                n_vectorized_record_batches += 1
                for variant_name, eval_result in evals.items():
                    detail_rate = _as_float(eval_result.get("detail_phint53_photo_ans1_s^-1"))
                    ratio = (float(matrix_rate) / detail_rate) if detail_rate is not None and detail_rate > 0.0 else None
                    row = {
                        "row_kind": "type53_detail_phint53_bremsa_variant_audit",
                        "audit_version": "v0.3.166",
                        "ion": ion,
                        "bremsa_variant": variant_name,
                        "record": record,
                        "bound_global_index": bg,
                        "bound_level_label": lev.get("level_label"),
                        "triplet_component": mrow.get("triplet_component") or lev.get("triplet_component"),
                        "continuum_or_parent_global_index": cg,
                        "continuum_level_label": cont.get("level_label"),
                        "matrix_photoionization_rate_s^-1": matrix_rate,
                        "variant_detail_phint53_photo_ans1_s^-1": detail_rate,
                        "matrix_over_variant_detail_phint53_ans1": ratio,
                        "variant_detail_phint53_status": eval_result.get("detail_phint53_photo_status"),
                        "detail_phint53_threshold_eV": eval_result.get("detail_phint53_threshold_eV"),
                        "detail_phint53_n_intervals_used": eval_result.get("detail_phint53_n_intervals_used"),
                    }
                    variant_rows_by_name.setdefault(variant_name, []).append(row)
                    n_evaluated_variant_record_pairs += 1
    integration_seconds = time.perf_counter() - integration_t0

    variant_rows: List[Dict[str, Any]] = []
    for variant_name in variant_map:
        rows = variant_rows_by_name.get(variant_name, [])
        summary = _summarize_variant_ratios(rows, variant=variant_name)
        summary.update({
            "audit_version": "v0.3.166",
            "ion": ion,
            "triplet_only": bool(triplet_only),
            "detail_continuum_status": detail_status,
            "detail_continuum_source": detail_source,
            "detail_zone_index": detail_zone_index,
            "radius_cm": radius_cm,
            "source_code_live_outward_bremsa": "trnfrc.f90: bremsa(j)=zremsz(j)*exp(-dpthc(1,j))/(12.56*r19*r19)",
            "detail_output_continuum_columns": "fstepr4.f90 writes zrems(1:5), opacity, emis out/in, fwd/bck dpth; it does not write zremsz",
            "integration_engine": "vectorized_numpy_record_precompute_v03166",
        })
        variant_summaries.append(summary)
        variant_rows.extend(rows)

    def _score(srow: Mapping[str, Any]) -> Tuple[float, float, float]:
        med = _as_float(srow.get("median_matrix_over_variant_detail"), 1.0e300) or 1.0e300
        no = -float(_as_float(srow.get("n_within_10pct_without_free_scale"), 0.0) or 0.0)
        shape = float(_as_float(srow.get("median_abs_fractional_residual_after_variant_scale"), 1.0e300) or 1.0e300)
        return (abs(math.log10(med)) if med > 0.0 else 1.0e300, no, shape)
    variant_summaries = sorted(variant_summaries, key=_score)
    best = variant_summaries[0] if variant_summaries else {}
    median_best = _as_float(best.get("median_matrix_over_variant_detail"))
    if median_best is not None and 0.8 <= median_best <= 1.25:
        interpretation = "One available xo01_detal4 bremsa variant approximately matches the matrix without a free scale; inspect that variant as a candidate live-bremsa reconstruction."
        status = "bremsa_variant_candidate_found"
    elif median_best is not None:
        interpretation = "No available xo01_detal4 zrems-column variant removes the type-53 normalization gap without a free scale. This supports the source-code diagnosis that exact outward phint53 parity needs live zremsz/bremsa from trnfrc, not only fstepr4 detail zrems columns."
        status = "available_detail_variants_do_not_remove_normalization_gap"
    else:
        interpretation = "No detail bremsa variant could be evaluated."
        status = "no_bremsa_variant_evaluated"
    total_seconds = time.perf_counter() - t_start
    summary = {
        "audit_version": "v0.3.166",
        "ion": ion,
        "triplet_only": bool(triplet_only),
        "detail_continuum_status": detail_status,
        "detail_continuum_source": detail_source,
        "detail_zone_index": detail_zone_index,
        "n_type53_photoionization_records": len(candidate_items),
        "n_bremsa_variants": len(variant_summaries),
        "requested_bremsa_variants": requested_variants,
        "requested_bremsa_variants_missing": requested_missing,
        "fast_mode": bool(fast),
        "profile_requested": bool(profile),
        "integration_engine": "vectorized_numpy_record_precompute_v03166",
        "n_vectorized_record_batches": n_vectorized_record_batches,
        "n_evaluated_variant_record_pairs": n_evaluated_variant_record_pairs,
        "integration_seconds": integration_seconds,
        "total_seconds": total_seconds,
        "best_bremsa_variant_without_free_scale": best.get("bremsa_variant"),
        "best_variant_median_matrix_over_detail": best.get("median_matrix_over_variant_detail"),
        "best_variant_n_within_10pct_without_free_scale": best.get("n_within_10pct_without_free_scale"),
        "best_variant_n_within_10pct_after_variant_scale": best.get("n_within_10pct_after_variant_scale"),
        "status": status,
        "interpretation": interpretation,
        "source_code_live_outward_bremsa": "trnfrc.f90: bremsa(j)=zremsz(j)*exp(-dpthc(1,j))/(12.56*r19*r19)",
        "detail_output_continuum_columns": "fstepr4.f90 writes zrems(1:5), opacity, emis out/in, fwd/bck dpth; it does not write zremsz",
        "top_bremsa_variants": variant_summaries[:12],
        "performance_note": "v0.3.166 keeps the v0.3.165 vectorized audit and fixes NumPy trapezoid compatibility; it vectorizes the Python audit by precomputing sigma(E) once per record and evaluating requested bremsa variants together. It remains a diagnostic prototype; production RT-coupled kernels should move to the planned C++ backend.",
    }
    return {"summary": summary, "variant_summaries": variant_summaries, "rows": variant_rows}


def write_type53_detail_phint53_bremsa_variants_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_type53_detail_phint53_bremsa_variants_audit",
    write_records_csv: bool = True,
) -> Dict[str, str]:
    """Write v0.3.166 type-53 bremsa-variant audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = dict(audit.get("summary", {}) or {})
    variants = list(audit.get("variant_summaries", []) or [])
    rows = list(audit.get("rows", []) or [])
    variant_csv = out / f"{prefix}_variant_summary.csv"
    row_csv = out / f"{prefix}_records.csv"
    _write_csv(variant_csv, variants)
    if write_records_csv:
        _write_csv(row_csv, rows)
    json_path = out / f"{prefix}.json"
    json_payload = {"summary": summary, "variant_summaries": variants, "rows": rows if write_records_csv else []}
    if not write_records_csv:
        json_payload["rows_omitted"] = True
        json_payload["n_rows_omitted"] = len(rows)
    json_path.write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR type-53 detail phint53 bremsa-variant audit",
        "",
        f"ion: `{summary.get('ion')}`",
        f"triplet_only: `{summary.get('triplet_only')}`",
        f"detail_continuum_status: `{summary.get('detail_continuum_status')}`",
        f"n_type53_photoionization_records: `{summary.get('n_type53_photoionization_records')}`",
        f"n_bremsa_variants: `{summary.get('n_bremsa_variants')}`",
        f"fast_mode: `{summary.get('fast_mode')}`",
        f"integration_engine: `{summary.get('integration_engine')}`",
        f"integration_seconds: `{summary.get('integration_seconds')}`",
        f"total_seconds: `{summary.get('total_seconds')}`",
        f"best_bremsa_variant_without_free_scale: `{summary.get('best_bremsa_variant_without_free_scale')}`",
        f"best_variant_median_matrix_over_detail: `{summary.get('best_variant_median_matrix_over_detail')}`",
        f"status: `{summary.get('status')}`",
        "",
        "## Source-code context",
        "",
        f"- live outward bremsa: `{summary.get('source_code_live_outward_bremsa')}`",
        f"- detail columns: `{summary.get('detail_output_continuum_columns')}`",
        "",
        str(summary.get("interpretation") or ""),
        "",
        "## Performance note",
        "",
        str(summary.get("performance_note") or ""),
        "",
        "## Variant summary",
        "",
        "| variant | n | median matrix/detail | p16 | p84 | within 10% no scale | within 10% after scale | median abs frac residual after scale |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants:
        lines.append(
            f"| {row.get('bremsa_variant')} | {row.get('n_evaluated_rows')} | {row.get('median_matrix_over_variant_detail')} | "
            f"{row.get('p16_matrix_over_variant_detail')} | {row.get('p84_matrix_over_variant_detail')} | "
            f"{row.get('n_within_10pct_without_free_scale')} | {row.get('n_within_10pct_after_variant_scale')} | "
            f"{row.get('median_abs_fractional_residual_after_variant_scale')} |"
        )
    if write_records_csv:
        lines.extend(["", f"variant_summary_csv: `{variant_csv.name}`", f"records_csv: `{row_csv.name}`", f"json: `{json_path.name}`"])
    else:
        lines.extend(["", f"variant_summary_csv: `{variant_csv.name}`", "records_csv: `omitted_by_request`", f"json: `{json_path.name}`"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_paths = {"variant_summary_csv": str(variant_csv), "json": str(json_path), "markdown": str(md_path)}
    if write_records_csv:
        out_paths["records_csv"] = str(row_csv)
    return out_paths

# -----------------------------------------------------------------------------
# v0.3.173: type-53 phint53 audit against live XSTAR rate-grid bremsam(:)


def _select_live_rate_grid_state(states: Sequence[Any], selector: str | int = "last") -> Tuple[Optional[Any], str]:
    """Select one live-rate-grid state from a probe CSV reader result."""
    if not states:
        return None, "no_probe_states_available"
    text = str(selector).strip().lower()
    if text in {"last", "final", "-1"}:
        return states[-1], "last"
    if text in {"first", "0"}:
        return states[0], "first"
    try:
        idx = int(text)
    except Exception:
        return states[-1], "last_fallback_invalid_selector"
    # Human-facing selectors are 1-based unless explicitly 0 was requested.
    if idx <= 0:
        pos = 0
    else:
        pos = idx - 1
    if pos < 0 or pos >= len(states):
        return states[-1], "last_fallback_selector_out_of_range"
    return states[pos], f"index_{idx}"


def audit_type53_live_bremsam_phint53(
    *,
    benchmark_dir: str | Path | None = None,
    ion: str = "O VII",
    probe_csv: str | Path | None = None,
    probe_state: str | int = "last",
    matrix_terms_csv: str | Path | None = None,
    adjacent_coupling_csv: str | Path | None = None,
    global_index_csv: str | Path | None = None,
    comparisons_csv: str | Path | None = None,
    triplet_only: bool = False,
    max_records: int | None = None,
) -> Dict[str, Any]:
    """Compare type-53 photoionization matrix rows with live XSTAR bremsam(:).

    This is the first audit that uses the instrumented XSTAR rate grid captured
    immediately after ``xstarcalc.f90`` calls ``bremsmap``.  It therefore
    evaluates the photoionization ``ans1`` integrand on ``epim(:)`` and
    ``bremsam(:)``, rather than on ``xo01_detal4`` output continuum variants.

    The audit still compares against the preserved Python solver matrix terms;
    it does not tune the matrix.  It answers whether the current type-53 matrix
    photoionization rates are consistent with the live XSTAR rate-grid radiation
    field at the ``calc_hmc_all/calc_hmc_ion`` call site.
    """
    t_start = time.perf_counter()
    root = Path(benchmark_dir) if benchmark_dir is not None else Path(".")
    paths = find_solver_product_paths(root, ion=ion, comparisons_csv=comparisons_csv) if benchmark_dir is not None else {}
    matrix_path = Path(matrix_terms_csv) if matrix_terms_csv is not None else paths.get("matrix_terms_csv")
    if matrix_path is None or not matrix_path.exists():
        raise ValueError("provide --matrix-terms-csv or --benchmark-dir with preserved solver products")
    product_dir = matrix_path.parent
    adjacent_path = Path(adjacent_coupling_csv) if adjacent_coupling_csv is not None else _first_existing_path([
        product_dir / "xstar_like_element_solver_adjacent_coupling_terms.csv",
    ])
    global_path = Path(global_index_csv) if global_index_csv is not None else _first_existing_path([
        product_dir / "xstar_like_element_solver_global_index.csv",
    ])
    if adjacent_path is None or not adjacent_path.exists():
        raise ValueError("adjacent coupling CSV not found; provide --adjacent-coupling-csv")
    if global_path is None or not global_path.exists():
        raise ValueError("global index CSV not found; provide --global-index-csv")
    if probe_csv is None:
        raise ValueError("provide --probe-csv from the instrumented XSTAR live-rate-grid probe")
    probe_path = Path(probe_csv)
    if not probe_path.exists():
        raise ValueError(f"probe CSV not found: {probe_path}")

    from .xstar_live_rate_grid_probe import read_live_rate_grid_probe_csv, summarize_live_rate_grid_probe_csv

    probe_summary = summarize_live_rate_grid_probe_csv(probe_path)
    states = read_live_rate_grid_probe_csv(probe_path)
    state, state_status = _select_live_rate_grid_state(states, probe_state)
    if state is None:
        epim: Sequence[float] = []
        bremsam: Sequence[float] = []
        bremsint: Sequence[float] = []
    else:
        epim = list(state.epim_eV)
        bremsam = list(state.bremsam)
        bremsint = list(state.bremsint)

    matrix_rows = _read_csv_rows(matrix_path)
    adjacent_rows = _read_csv_rows(adjacent_path)
    global_rows = _read_csv_rows(global_path)
    level_by_g = _level_by_global_index(global_rows)
    adjacent_by_record = {str(r.get("record") or "").strip(): r for r in adjacent_rows if str(r.get("data_type") or "").strip() == "53"}

    candidates: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    for row in matrix_rows:
        if str(row.get("data_type") or "").strip() != "53":
            continue
        component = str(row.get("full_global_component") or "")
        role = str(row.get("matrix_role") or "")
        kind = str(row.get("matrix_term_kind") or "")
        if "photoionization" not in component and "photoionization" not in role and "phint53" not in kind:
            continue
        if "milne" in component.lower() or "xstar_ucalc" in str(row.get("global_type53_xstar_ucalc_term_id") or ""):
            continue
        if triplet_only:
            comp = str(row.get("triplet_component") or "").strip().lower()
            bg0 = _as_int(row.get("bound_global_index"))
            lev0 = level_by_g.get(int(bg0)) if bg0 is not None else None
            is_trip = comp in {"f", "i", "r"} or str(lev0.get("is_triplet_upper") if lev0 else "").lower() in {"true", "1", "yes"}
            if not is_trip:
                continue
        record = str(row.get("record") or "").strip()
        bg = _as_int(row.get("bound_global_index")) or -1
        cg = _as_int(row.get("continuum_or_parent_global_index")) or -1
        key = (record, int(bg), int(cg))
        rate = _as_float(row.get("full_global_rate_s^-1") or row.get("rate_s^-1"), 0.0) or 0.0
        prev = candidates.get(key)
        if prev is None or rate > float(prev.get("matrix_photoionization_rate_s^-1") or 0.0):
            m = dict(row)
            m["matrix_photoionization_rate_s^-1"] = rate
            candidates[key] = m

    probe_loaded = bool(state is not None and len(epim) >= 2 and len(bremsam) >= 2)
    live_status = "loaded_live_rate_grid_bremsam" if probe_loaded else "live_rate_grid_probe_not_loaded_or_empty"
    rows: List[Dict[str, Any]] = []
    for idx, ((record, bg, cg), mrow) in enumerate(candidates.items(), start=1):
        if max_records is not None and idx > int(max_records):
            break
        adj = adjacent_by_record.get(record, {})
        lev = level_by_g.get(int(bg), {}) if bg is not None else {}
        cont = level_by_g.get(int(cg), {}) if cg is not None else {}
        e_ry, sigma_cm2 = _type53_cross_section_pairs_cm2(adj.get("type53_raw_reals_full") or adj.get("raw_reals_preview"))
        threshold = _as_float(lev.get("binding_from_continuum_eV"))
        if threshold is None or threshold <= 0.0:
            ip = _as_float(lev.get("ionization_potential_eV"))
            ee = _as_float(lev.get("energy_eV"), 0.0) or 0.0
            threshold = (ip - ee) if ip is not None else None
        matrix_rate = _as_float(mrow.get("matrix_photoionization_rate_s^-1") or mrow.get("full_global_rate_s^-1") or mrow.get("rate_s^-1"), 0.0) or 0.0
        if not probe_loaded:
            eval_result: Dict[str, Any] = {"live_phint53_photo_status": live_status}
        else:
            eval_result0 = _evaluate_phint53_photoionization_ans1_detail_continuum_variants_fast(
                e_ry=e_ry,
                sigma_cm2=sigma_cm2,
                threshold_eV=float(threshold or 0.0),
                epi_eV=epim,
                bremsa_variants={"live_bremsam": bremsam},
            ).get("live_bremsam", {})
            # Rename detail-oriented keys to live-rate-grid names while keeping
            # the numeric values identical and easy to compare to older audits.
            eval_result = {}
            for k, v in eval_result0.items():
                nk = str(k).replace("detail_phint53", "live_phint53").replace("detail_continuum", "live_rate_grid")
                eval_result[nk] = v
            if "live_phint53_photo_status" in eval_result:
                eval_result["live_phint53_photo_status"] = "evaluated_live_bremsam_photoionization_ans1_integrand_v03173"
            if "live_phint53_photo_ans1_s^-1" not in eval_result and "detail_phint53_photo_ans1_s^-1" in eval_result0:
                eval_result["live_phint53_photo_ans1_s^-1"] = eval_result0.get("detail_phint53_photo_ans1_s^-1")
            eval_result["live_phint53_source_file"] = "xstarlib/src/phint53.f90"
            eval_result["live_phint53_detail_source"] = "instrumented xstarcalc.f90 after bremsmap: epim(:), bremsam(:), bremsint(:)"
            eval_result["live_phint53_warning"] = "Uses live XSTAR rate-grid epim/bremsam captured after bremsmap; remaining differences indicate matrix radiation-kernel/source mismatch rather than xo01_detal4 column selection."
        live_rate = _as_float(eval_result.get("live_phint53_photo_ans1_s^-1"))
        if live_rate is None:
            cls = "live_phint53_not_evaluated"
            diff = None
            rel = None
            ratio = None
        else:
            diff = float(matrix_rate) - float(live_rate)
            rel = abs(diff) / max(abs(float(live_rate)), 1.0e-300)
            ratio = float(matrix_rate) / max(float(live_rate), 1.0e-300)
            cls = "matrix_matches_live_bremsam_phint53_ans1" if rel <= 1.0e-6 else "matrix_differs_from_live_bremsam_phint53_ans1"
        rows.append({
            "row_kind": "type53_live_bremsam_phint53_photo_audit",
            "audit_version": "v0.3.173",
            "ion": ion,
            "record": record,
            "bound_global_index": bg,
            "bound_level": mrow.get("bound_level") or adj.get("idest1_guess"),
            "bound_level_label": lev.get("level_label"),
            "triplet_component": mrow.get("triplet_component") or lev.get("triplet_component"),
            "continuum_or_parent_global_index": cg,
            "continuum_level_label": cont.get("level_label"),
            "matrix_photoionization_rate_s^-1": matrix_rate,
            "live_phint53_photo_ans1_s^-1": live_rate,
            "matrix_minus_live_phint53_ans1_s^-1": diff,
            "matrix_over_live_phint53_ans1": ratio,
            "relative_error_vs_live_phint53_ans1": rel,
            "classification": cls,
            "probe_csv": str(probe_path),
            "probe_state_selector": str(probe_state),
            "probe_state_selection_status": state_status,
            "probe_capture_index": state.metadata.get("capture_index") if state is not None else None,
            "probe_zone_index": state.zone_index if state is not None else None,
            "probe_pass_index": state.pass_index if state is not None else None,
            "probe_ldir": state.ldir if state is not None else None,
            "n_live_epim": len(epim),
            "n_live_bremsam": len(bremsam),
            "n_live_bremsint": len(bremsint),
            "n_type53_cross_section_pairs": len(e_ry),
            "threshold_eV_source": "global_index.binding_from_continuum_eV",
            **eval_result,
        })

    evaluated = [r for r in rows if r.get("classification") != "live_phint53_not_evaluated"]
    matching = [r for r in evaluated if r.get("classification") == "matrix_matches_live_bremsam_phint53_ans1"]
    differing = [r for r in evaluated if r.get("classification") == "matrix_differs_from_live_bremsam_phint53_ans1"]
    ratios = [float(r["matrix_over_live_phint53_ans1"]) for r in evaluated if _as_float(r.get("matrix_over_live_phint53_ans1")) is not None and float(r.get("matrix_over_live_phint53_ans1")) > 0.0]
    top = sorted(rows, key=lambda r: abs(_as_float(r.get("matrix_minus_live_phint53_ans1_s^-1"), 0.0) or 0.0), reverse=True)[:12]
    status = "live_bremsam_phint53_photoionization_audit_completed"
    if evaluated and len(matching) == len(evaluated):
        status = "live_bremsam_phint53_matches_matrix_for_all_evaluated_rows"
    elif evaluated:
        status = "live_bremsam_phint53_differs_from_matrix_for_some_rows"
    summary = {
        "audit_version": "v0.3.173",
        "ion": ion,
        "matrix_terms_csv": str(matrix_path),
        "adjacent_coupling_csv": str(adjacent_path),
        "global_index_csv": str(global_path),
        "probe_csv": str(probe_path),
        "probe_status": probe_summary.get("probe_status"),
        "n_probe_states": probe_summary.get("n_probe_states"),
        "n_probe_grid_points_total": probe_summary.get("n_probe_grid_points_total"),
        "probe_state_selector": str(probe_state),
        "probe_state_selection_status": state_status,
        "probe_capture_index": state.metadata.get("capture_index") if state is not None else None,
        "probe_zone_index": state.zone_index if state is not None else None,
        "probe_pass_index": state.pass_index if state is not None else None,
        "probe_ldir": state.ldir if state is not None else None,
        "triplet_only": bool(triplet_only),
        "n_type53_photoionization_records": len(rows),
        "n_live_phint53_evaluated": len(evaluated),
        "n_live_phint53_matches": len(matching),
        "n_live_phint53_differs": len(differing),
        "median_matrix_over_live_phint53_ans1": _median_float(ratios),
        "p16_matrix_over_live_phint53_ans1": _percentile_float(ratios, 16.0),
        "p84_matrix_over_live_phint53_ans1": _percentile_float(ratios, 84.0),
        "n_live_epim": len(epim),
        "live_epim_min_eV": min(epim) if epim else None,
        "live_epim_max_eV": max(epim) if epim else None,
        "top_records_by_abs_matrix_minus_live": top,
        "status": status,
        "total_seconds": time.perf_counter() - t_start,
        "source_path_note": "Uses instrumented XSTAR rate-grid epim(:), bremsam(:), bremsint(:) captured immediately after bremsmap and before calc_hmc_all/calc_hmc_ion.",
        "performance_note": "The Python audit precomputes/interpolates each type-53 record for transparency. Production RT-coupled phint53/rate kernels should move to the planned C++ backend after parity is established.",
    }
    return {"summary": summary, "rows": rows}


def write_type53_live_bremsam_phint53_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_type53_live_bremsam_phint53_audit",
) -> Dict[str, str]:
    """Write v0.3.173 live-bremsam phint53 audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(audit.get("rows", []) or [])
    summary = dict(audit.get("summary", {}) or {})
    csv_path = out / f"{prefix}_records.csv"
    _write_csv(csv_path, rows)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR type-53 live-bremsam phint53 audit",
        "",
        f"ion: `{summary.get('ion')}`",
        f"probe_status: `{summary.get('probe_status')}`",
        f"probe_state_selection_status: `{summary.get('probe_state_selection_status')}`",
        f"probe_capture_index: `{summary.get('probe_capture_index')}`",
        f"triplet_only: `{summary.get('triplet_only')}`",
        f"n_type53_photoionization_records: `{summary.get('n_type53_photoionization_records')}`",
        f"n_live_phint53_evaluated: `{summary.get('n_live_phint53_evaluated')}`",
        f"n_live_phint53_matches: `{summary.get('n_live_phint53_matches')}`",
        f"n_live_phint53_differs: `{summary.get('n_live_phint53_differs')}`",
        f"median_matrix_over_live_phint53_ans1: `{summary.get('median_matrix_over_live_phint53_ans1')}`",
        f"status: `{summary.get('status')}`",
        "",
        "This audit recomputes the photoionization `ans1` side of `phint53.f90` using the live XSTAR rate-grid `epim(:)` and `bremsam(:)` captured immediately after `bremsmap` and compares it with the preserved type-53 matrix photoionization rows.",
        "",
        "## Largest records by |matrix - live phint53 ans1|",
        "",
    ]
    top = summary.get("top_records_by_abs_matrix_minus_live") or []
    if top:
        lines.append("| record | bound | comp | matrix | live ans1 | ratio | class |")
        lines.append("|---:|---|---|---:|---:|---:|---|")
        for row in top:
            lines.append(
                f"| {row.get('record')} | {row.get('bound_level_label')} | {row.get('triplet_component')} | "
                f"{row.get('matrix_photoionization_rate_s^-1')} | {row.get('live_phint53_photo_ans1_s^-1')} | "
                f"{row.get('matrix_over_live_phint53_ans1')} | {row.get('classification')} |"
            )
    else:
        lines.append("No evaluated records were available.")
    lines.extend(["", f"records_csv: `{csv_path.name}`", f"json: `{json_path.name}`"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"records_csv": str(csv_path), "json": str(json_path), "markdown": str(md_path)}


# -----------------------------------------------------------------------------
# v0.3.174: controlled type-53 live-bremsam matrix replacement solve audit


def _is_type53_photoionization_matrix_term(row: Mapping[str, Any]) -> bool:
    """Return True for the full-global type-53 photoionization gain/loss terms."""
    if str(row.get("data_type") or "").strip() != "53":
        return False
    comp = str(row.get("full_global_component") or "").lower()
    role = str(row.get("matrix_role") or "").lower()
    kind = str(row.get("matrix_term_kind") or "").lower()
    if "milne" in comp or "milne" in role or "milne" in kind:
        return False
    text = " ".join([comp, role, kind])
    return "photoionization" in text and ("phint53" in text or "type53" in text)


def _infer_he_like_stage_from_global_index(global_rows: Sequence[Mapping[str, Any]]) -> Optional[int]:
    stages: List[int] = []
    for row in global_rows:
        comp = str(row.get("triplet_component") or "").strip().lower()
        if comp in {"f", "i", "r"} or str(row.get("is_triplet_upper") or "").strip().lower() in {"true", "1", "yes"}:
            st = _as_int(row.get("ion_stage"))
            if st is not None:
                stages.append(int(st))
    if not stages:
        return None
    counts: Dict[int, int] = {}
    for st in stages:
        counts[st] = counts.get(st, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _summary_row_for_solve(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    for row in rows:
        if row.get("row_kind") == "summary" and row.get("comparison_case") == "full_global_normalized_proxy_topology_solve":
            return dict(row)
    for row in rows:
        if row.get("row_kind") == "summary":
            return dict(row)
    return {}


def _live_phint53_replacement_lookup(live_audit_rows: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, int, int], Dict[str, Any]]:
    out: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    for row in live_audit_rows:
        rec = str(row.get("record") or "").strip()
        bg = _as_int(row.get("bound_global_index"))
        cg = _as_int(row.get("continuum_or_parent_global_index"))
        live = _as_float(row.get("live_phint53_photo_ans1_s^-1"))
        if not rec or bg is None or cg is None or live is None or live < 0.0:
            continue
        out[(rec, int(bg), int(cg))] = dict(row)
    return out


def apply_live_bremsam_type53_photoionization_replacement(
    full_global_matrix_terms: Sequence[Mapping[str, Any]],
    live_audit_rows: Sequence[Mapping[str, Any]],
    *,
    replacement_mode: str = "replace-all",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return matrix terms with type-53 photoionization rates replaced by live phint53.

    This is a controlled diagnostic transformation: it leaves all non-type-53
    rows unchanged and replaces only matrix rows whose record/bound/continuum
    key appears in a v0.3.173 live-bremsam audit.  The sign and matrix topology
    of each row are preserved; only the absolute rate is replaced.
    """
    mode = str(replacement_mode or "replace-all").strip().lower().replace("_", "-")
    if mode not in {"replace-all", "off", "none"}:
        mode = "replace-all"
    lookup = _live_phint53_replacement_lookup(live_audit_rows)
    out: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for row0 in full_global_matrix_terms:
        row = dict(row0)
        if mode in {"off", "none"} or not _is_type53_photoionization_matrix_term(row):
            out.append(row)
            continue
        rec = str(row.get("record") or "").strip()
        bg = _as_int(row.get("bound_global_index"))
        cg = _as_int(row.get("continuum_or_parent_global_index"))
        key = (rec, int(bg) if bg is not None else -1, int(cg) if cg is not None else -1)
        live_row = lookup.get(key)
        live = _as_float(live_row.get("live_phint53_photo_ans1_s^-1") if live_row else None)
        if live is None:
            row["type53_live_bremsam_replacement_status"] = "not_replaced_no_matching_live_phint53_row"
            out.append(row)
            continue
        old_signed = _as_float(row.get("full_global_signed_rate_s^-1"))
        if old_signed is None:
            old_signed = _as_float(row.get("signed_rate_s^-1"))
        sign = -1.0 if (old_signed is not None and old_signed < 0.0) else 1.0
        old_rate = _as_float(row.get("full_global_rate_s^-1"))
        if old_rate is None:
            old_rate = abs(float(old_signed)) if old_signed is not None else _as_float(row.get("rate_s^-1"), 0.0)
        new_signed = sign * float(live)
        ratio = None
        if live > 0.0 and old_rate is not None:
            ratio = float(old_rate) / max(float(live), 1.0e-300)
        for k in ["full_global_signed_rate_s^-1", "signed_rate_s^-1"]:
            if k in row:
                row[k] = new_signed
        for k in ["full_global_rate_s^-1", "rate_s^-1"]:
            if k in row:
                row[k] = float(live)
        row.update({
            "type53_live_bremsam_replacement_status": "replaced_with_live_bremsam_phint53_ans1_v03174",
            "type53_original_matrix_rate_s^-1": old_rate,
            "type53_original_matrix_signed_rate_s^-1": old_signed,
            "type53_live_bremsam_phint53_ans1_s^-1": float(live),
            "type53_original_over_live_bremsam": ratio,
            "type53_replacement_probe_capture_index": live_row.get("probe_capture_index") if live_row else "",
            "type53_replacement_source_record_classification": live_row.get("classification") if live_row else "",
            "full_global_component": "type53_live_bremsam_phint53_photoionization_replacement",
            "full_global_assembly_status": "assembled_full_global_topology_with_live_bremsam_type53_replacement",
        })
        changed.append({
            "row_kind": "type53_live_bremsam_replacement_term",
            "record": rec,
            "bound_global_index": bg,
            "continuum_or_parent_global_index": cg,
            "full_global_term_id": row.get("full_global_term_id"),
            "matrix_term_kind": row.get("matrix_term_kind"),
            "matrix_row_global_index": row.get("matrix_row_global_index"),
            "matrix_col_global_index": row.get("matrix_col_global_index"),
            "old_rate_s^-1": old_rate,
            "old_signed_rate_s^-1": old_signed,
            "new_rate_s^-1": float(live),
            "new_signed_rate_s^-1": new_signed,
            "old_over_new": ratio,
            "triplet_component": row.get("triplet_component") or (live_row.get("triplet_component") if live_row else ""),
            "replacement_status": row["type53_live_bremsam_replacement_status"],
        })
        out.append(row)
    return out, changed


def audit_type53_live_bremsam_matrix_replacement(
    *,
    benchmark_dir: str | Path | None = None,
    ion: str = "O VII",
    live_phint53_audit_csv: str | Path | None = None,
    matrix_terms_csv: str | Path | None = None,
    global_index_csv: str | Path | None = None,
    line_rows_csv: str | Path | None = None,
    calc_ion_rates_csv: str | Path | None = None,
    comparisons_csv: str | Path | None = None,
    normalized_solve_csv: str | Path | None = None,
    linear_solver: str = "xstar-lucy",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    prune_null_rate_levels: bool = True,
    full_global_topology: str = "xstar-continuum-alias-superlevels",
    ion_fraction_closure: str = "xstar-calc-ion-rates",
) -> Dict[str, Any]:
    """Controlled solve audit with type-53 photoionization rates replaced by live phint53.

    This diagnostic does not change the default solver.  It reads a preserved
    full-global matrix from example 56 and a v0.3.173 live-bremsam phint53 audit,
    replaces only the type-53 photoionization gain/loss rates with the live
    phint53 ans1 values, and re-solves the matrix for comparison.
    """
    t_start = time.perf_counter()
    root = Path(benchmark_dir) if benchmark_dir is not None else Path(".")
    paths = find_solver_product_paths(root, ion=ion, comparisons_csv=comparisons_csv) if benchmark_dir is not None else {}
    matrix_path = Path(matrix_terms_csv) if matrix_terms_csv is not None else paths.get("matrix_terms_csv")
    normalized_path = Path(normalized_solve_csv) if normalized_solve_csv is not None else paths.get("normalized_solve_csv")
    if matrix_path is None or not Path(matrix_path).exists():
        raise ValueError("provide --matrix-terms-csv or --benchmark-dir with preserved solver products")
    product_dir = Path(matrix_path).parent
    global_path = Path(global_index_csv) if global_index_csv is not None else product_dir / "xstar_like_element_solver_global_index.csv"
    lines_path = Path(line_rows_csv) if line_rows_csv is not None else product_dir / "xstar_like_element_solver_line_rows.csv"
    calc_path = Path(calc_ion_rates_csv) if calc_ion_rates_csv is not None else product_dir / "xstar_like_element_solver_calc_ion_rates_istruc_audit.csv"
    if live_phint53_audit_csv is None:
        raise ValueError("provide --live-phint53-audit-csv from example 74")
    live_path = Path(live_phint53_audit_csv)
    if live_path.is_dir():
        live_path = live_path / "xstar_type53_live_bremsam_phint53_audit_records.csv"
    if not live_path.exists():
        raise ValueError(f"live phint53 audit CSV not found: {live_path}")
    if not global_path.exists():
        raise ValueError(f"global index CSV not found: {global_path}")
    if not lines_path.exists():
        raise ValueError(f"line rows CSV not found: {lines_path}")

    matrix_rows = _read_csv_rows(matrix_path)
    global_rows = _read_csv_rows(global_path)
    line_rows = _read_csv_rows(lines_path)
    calc_rows = _read_csv_rows(calc_path) if calc_path.exists() else []
    live_rows = _read_csv_rows(live_path)
    he_stage = _infer_he_like_stage_from_global_index(global_rows)
    if he_stage is None:
        raise ValueError("could not infer He-like ion stage from global index triplet rows")

    replaced_terms, replacement_rows = apply_live_bremsam_type53_photoionization_replacement(matrix_rows, live_rows)

    from .xstar_element_solver import build_full_global_normalized_solve_comparison

    original_solve_rows = build_full_global_normalized_solve_comparison(
        global_index_rows=global_rows,
        full_global_matrix_terms=matrix_rows,
        line_rows=line_rows,
        he_like_stage=int(he_stage),
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        prune_null_rate_levels=prune_null_rate_levels,
        full_global_topology=full_global_topology,
        ion_fraction_closure=ion_fraction_closure,
        calc_ion_rates_istruc_audit_rows=calc_rows,
    )
    replacement_solve_rows = build_full_global_normalized_solve_comparison(
        global_index_rows=global_rows,
        full_global_matrix_terms=replaced_terms,
        line_rows=line_rows,
        he_like_stage=int(he_stage),
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        prune_null_rate_levels=prune_null_rate_levels,
        full_global_topology=full_global_topology,
        ion_fraction_closure=ion_fraction_closure,
        calc_ion_rates_istruc_audit_rows=calc_rows,
    )
    orig = _summary_row_for_solve(original_solve_rows)
    repl = _summary_row_for_solve(replacement_solve_rows)

    def _flt(row: Mapping[str, Any], key: str) -> Optional[float]:
        return _as_float(row.get(key))
    comparison_rows = []
    for label, row in [("original_matrix", orig), ("live_bremsam_type53_replacement", repl)]:
        comparison_rows.append({
            "row_kind": "type53_live_bremsam_matrix_replacement_solve_summary",
            "comparison_case": label,
            "f_fraction": row.get("f_fraction"),
            "i_fraction": row.get("i_fraction"),
            "r_fraction": row.get("r_fraction"),
            "R": row.get("R"),
            "G": row.get("G"),
            "l2_distance_to_target": row.get("l2_distance_to_target"),
            "solve_status": row.get("solve_status"),
            "solver": row.get("solver"),
            "n_negative_populations": row.get("n_negative_populations"),
            "sum_population": row.get("sum_population"),
        })
    delta = {
        "row_kind": "type53_live_bremsam_matrix_replacement_delta",
        "comparison_case": "replacement_minus_original",
        "delta_f": (_flt(repl, "f_fraction") or 0.0) - (_flt(orig, "f_fraction") or 0.0),
        "delta_i": (_flt(repl, "i_fraction") or 0.0) - (_flt(orig, "i_fraction") or 0.0),
        "delta_r": (_flt(repl, "r_fraction") or 0.0) - (_flt(orig, "r_fraction") or 0.0),
        "delta_l2": (_flt(repl, "l2_distance_to_target") or 0.0) - (_flt(orig, "l2_distance_to_target") or 0.0),
    }
    comparison_rows.append(delta)
    ratios = [_as_float(r.get("old_over_new")) for r in replacement_rows]
    ratios = [float(x) for x in ratios if x is not None and x > 0.0]
    summary = {
        "audit_version": "v0.3.174",
        "ion": ion,
        "status": "type53_live_bremsam_replacement_solve_audit_completed",
        "matrix_terms_csv": str(matrix_path),
        "global_index_csv": str(global_path),
        "line_rows_csv": str(lines_path),
        "calc_ion_rates_csv": str(calc_path) if calc_path.exists() else None,
        "live_phint53_audit_csv": str(live_path),
        "he_like_stage": int(he_stage),
        "n_original_matrix_terms": len(matrix_rows),
        "n_replacement_matrix_terms": len(replaced_terms),
        "n_type53_photoionization_terms_replaced": len(replacement_rows),
        "median_original_over_live_replacement_rate": _median_float(ratios),
        "p16_original_over_live_replacement_rate": _percentile_float(ratios, 16.0),
        "p84_original_over_live_replacement_rate": _percentile_float(ratios, 84.0),
        "original_f_fraction": orig.get("f_fraction"),
        "original_i_fraction": orig.get("i_fraction"),
        "original_r_fraction": orig.get("r_fraction"),
        "replacement_f_fraction": repl.get("f_fraction"),
        "replacement_i_fraction": repl.get("i_fraction"),
        "replacement_r_fraction": repl.get("r_fraction"),
        "delta_f_replacement_minus_original": delta["delta_f"],
        "delta_i_replacement_minus_original": delta["delta_i"],
        "delta_r_replacement_minus_original": delta["delta_r"],
        "original_l2_distance_to_target": orig.get("l2_distance_to_target"),
        "replacement_l2_distance_to_target": repl.get("l2_distance_to_target"),
        "delta_l2_replacement_minus_original": delta["delta_l2"],
        "solver": linear_solver,
        "full_global_topology": full_global_topology,
        "ion_fraction_closure": ion_fraction_closure,
        "total_seconds": time.perf_counter() - t_start,
        "interpretation": "Controlled diagnostic only: only type-53 photoionization matrix rates are replaced by live-bremsam phint53 ans1 values; all other matrix/source terms remain as in the preserved solver products.",
    }
    return {
        "summary": summary,
        "replacement_terms": replaced_terms,
        "replacement_rows": replacement_rows,
        "solve_comparison_rows": comparison_rows,
        "original_solve_rows": original_solve_rows,
        "replacement_solve_rows": replacement_solve_rows,
    }


def write_type53_live_bremsam_matrix_replacement_audit(
    audit: Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_type53_live_bremsam_matrix_replacement_audit",
) -> Dict[str, str]:
    """Write v0.3.174 controlled replacement solve audit products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = dict(audit.get("summary", {}) or {})
    replacement_rows = list(audit.get("replacement_rows", []) or [])
    replacement_terms = list(audit.get("replacement_terms", []) or [])
    solve_comparison_rows = list(audit.get("solve_comparison_rows", []) or [])
    replacement_solve_rows = list(audit.get("replacement_solve_rows", []) or [])
    terms_csv = out / f"{prefix}_matrix_terms.csv"
    changed_csv = out / f"{prefix}_changed_terms.csv"
    comp_csv = out / f"{prefix}_solve_comparison.csv"
    repl_solve_csv = out / f"{prefix}_replacement_normalized_solve_comparison.csv"
    _write_csv(terms_csv, replacement_terms)
    _write_csv(changed_csv, replacement_rows)
    _write_csv(comp_csv, solve_comparison_rows)
    _write_csv(repl_solve_csv, replacement_solve_rows)
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({
        "summary": summary,
        "replacement_rows": replacement_rows,
        "solve_comparison_rows": solve_comparison_rows,
    }, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR type-53 live-bremsam matrix replacement audit",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"ion: `{summary.get('ion')}`",
        f"status: `{summary.get('status')}`",
        f"n_type53_photoionization_terms_replaced: `{summary.get('n_type53_photoionization_terms_replaced')}`",
        f"median_original_over_live_replacement_rate: `{summary.get('median_original_over_live_replacement_rate')}`",
        "",
        "## Solve comparison",
        "",
        "| case | f | i | r | R | G | L2 | status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in solve_comparison_rows:
        if row.get("row_kind") != "type53_live_bremsam_matrix_replacement_solve_summary":
            continue
        lines.append(
            f"| {row.get('comparison_case')} | {row.get('f_fraction')} | {row.get('i_fraction')} | {row.get('r_fraction')} | "
            f"{row.get('R')} | {row.get('G')} | {row.get('l2_distance_to_target')} | {row.get('solve_status')} |"
        )
    lines.extend([
        "",
        "## Delta",
        "",
        f"delta_f: `{summary.get('delta_f_replacement_minus_original')}`",
        f"delta_i: `{summary.get('delta_i_replacement_minus_original')}`",
        f"delta_r: `{summary.get('delta_r_replacement_minus_original')}`",
        f"delta_l2: `{summary.get('delta_l2_replacement_minus_original')}`",
        "",
        str(summary.get("interpretation") or ""),
        "",
        f"changed_terms_csv: `{changed_csv.name}`",
        f"matrix_terms_csv: `{terms_csv.name}`",
        f"solve_comparison_csv: `{comp_csv.name}`",
        f"replacement_normalized_solve_comparison_csv: `{repl_solve_csv.name}`",
        f"json: `{json_path.name}`",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "matrix_terms_csv": str(terms_csv),
        "changed_terms_csv": str(changed_csv),
        "solve_comparison_csv": str(comp_csv),
        "replacement_normalized_solve_comparison_csv": str(repl_solve_csv),
        "json": str(json_path),
        "markdown": str(md_path),
    }
