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


__all__ = [
    "find_solver_product_paths",
    "audit_local_matrix_parity",
    "write_local_matrix_parity_audit",
    "audit_triplet_rate_terms",
    "write_triplet_rate_term_audit",
    "audit_type71_cascade_rates",
    "write_type71_cascade_rate_audit",
]
