#!/usr/bin/env python3
"""Diagnose He-like triplet balance terms in full-global solver outputs.

This helper compares one or more directories produced by
``examples/42_xstar_like_element_solver_demo.py``.  It is intended for the
post-v0.3.100 C V/O VII validation stage, where the O VII resonance-line output
can be matched with an XSTAR reference-depth postprocess but C V still shows an
intercombination/resonance residual.

The script does not change populations and does not tune rates.  It collects
existing audit products into compact, comparable tables:

* type-50 1s2p 3P_J -> 1s2s 3S1 radiative drain and density-scaled collisional
  coupling;
* triplet component population/incoming/loss balances;
* intercombination incoming-feed categories;
* type-71 cascade feed into f/i/r upper levels;
* type-99 superlevel source rates and their type-71 branch proxies;
* optional XSTAR triplet-line CSV presence/target fractions.

Example
-------

.. code-block:: bash

   PYTHONPATH=src python examples/44_diagnose_helike_triplet_balance.py \
     --case "C V:c5_xstar_like_element_solver_v03100_xstar_msolvelucy_superlevels" \
     --case "O VII:o7_xstar_like_element_solver_v03100_superlevels" \
     --xstar-triplet-lines-csv "O VII:xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv" \
     --out-dir triplet_balance_diagnostic \
     --print-summary
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REFERENCE_DEPTH_CASE = "full_global_xstar_reference_depth_emit_outward_calc_emis_ion"


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "--"}:
        return None
    try:
        x = float(text)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _sum(values: Iterable[Any]) -> float:
    total = 0.0
    for value in values:
        x = _as_float(value)
        if x is not None:
            total += x
    return total


def _ratio(num: Any, den: Any) -> Optional[float]:
    n = _as_float(num)
    d = _as_float(den)
    if n is None or d in (None, 0.0):
        return None
    return n / d


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["status"]
        rows = [{"status": "no_rows"}]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _path(solver_dir: Path, name: str) -> Path:
    path = solver_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Missing {name} in {solver_dir}")
    return path


def _read_solver_csv(
    label: str,
    solver_dir: Path,
    name: str,
    warnings: List[str],
) -> List[Dict[str, Any]]:
    """Read an optional solver audit CSV.

    Older output directories, partially copied validation directories, or quick
    reruns may not contain every diagnostic audit written by the newest solver.
    This triplet-balance aggregator should still collate the available pieces
    instead of aborting on the first missing optional file.
    """
    path = solver_dir / name
    if not path.exists():
        warnings.append(f"{label}: missing optional audit {name} in {solver_dir}; skipped that diagnostic block.")
        return []
    return _read_csv(path)


def _missing_row(label: str, name: str) -> Dict[str, Any]:
    return {
        "case_label": label,
        "status": "missing_optional_audit",
        "missing_file": name,
    }


def _parse_case(text: str) -> Tuple[str, Path]:
    if ":" not in text:
        path = Path(text)
        return path.name, path
    label, path = text.split(":", 1)
    return label.strip(), Path(path.strip())


def _parse_label_path(text: str) -> Tuple[str, Path]:
    if ":" not in text:
        raise argparse.ArgumentTypeError("expected LABEL:PATH")
    label, path = text.split(":", 1)
    return label.strip(), Path(path.strip())


def _component_balance(label: str, solver_dir: Path, warnings: List[str]) -> List[Dict[str, Any]]:
    name = "xstar_like_element_solver_triplet_component_balance_audit.csv"
    rows = _read_solver_csv(label, solver_dir, name, warnings)
    if not rows:
        row = _missing_row(label, name)
        row["component"] = "missing_audit"
        return [row]
    out: List[Dict[str, Any]] = []
    by_comp: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        comp = str(row.get("component", "")).strip()
        if comp in {"f", "i", "r"}:
            by_comp[comp] = row
            out.append(
                {
                    "case_label": label,
                    "component": comp,
                    "population_sum": _as_float(row.get("population_sum")),
                    "incoming_rate_sum_s^-1": _as_float(row.get("incoming_rate_sum_s^-1")),
                    "diagonal_loss_rate_sum_s^-1": _as_float(row.get("diagonal_loss_rate_sum_s^-1")),
                    "outgoing_offdiag_rate_sum_s^-1": _as_float(row.get("outgoing_offdiag_rate_sum_s^-1")),
                    "type71_cascade_in_rate_sum_s^-1": _as_float(row.get("type71_cascade_in_rate_sum_s^-1")),
                    "type53_milne_in_rate_sum_s^-1": _as_float(row.get("type53_milne_in_rate_sum_s^-1")),
                    "type74_inverse_in_rate_sum_s^-1": _as_float(row.get("type74_inverse_in_rate_sum_s^-1")),
                    "collisional_in_rate_sum_s^-1": _as_float(row.get("collisional_in_rate_sum_s^-1")),
                    "collisional_out_rate_sum_s^-1": _as_float(row.get("collisional_out_rate_sum_s^-1")),
                    "radiative_out_rate_sum_s^-1": _as_float(row.get("radiative_out_rate_sum_s^-1")),
                    "type53_photoionization_loss_rate_sum_s^-1": _as_float(row.get("type53_photoionization_loss_rate_sum_s^-1")),
                    "population_weighted_radiative_out_proxy_s^-1": _as_float(row.get("population_weighted_radiative_out_proxy_s^-1")),
                    "n_incoming_terms": _as_float(row.get("n_incoming_terms")),
                    "n_diagonal_loss_terms": _as_float(row.get("n_diagonal_loss_terms")),
                }
            )
    if {"f", "i", "r"}.issubset(by_comp):
        f = by_comp["f"]
        i = by_comp["i"]
        r = by_comp["r"]
        out.append(
            {
                "case_label": label,
                "component": "derived_ratios",
                "incoming_i_over_f": _ratio(i.get("incoming_rate_sum_s^-1"), f.get("incoming_rate_sum_s^-1")),
                "incoming_i_over_r": _ratio(i.get("incoming_rate_sum_s^-1"), r.get("incoming_rate_sum_s^-1")),
                "type71_i_over_f": _ratio(i.get("type71_cascade_in_rate_sum_s^-1"), f.get("type71_cascade_in_rate_sum_s^-1")),
                "type71_i_over_r": _ratio(i.get("type71_cascade_in_rate_sum_s^-1"), r.get("type71_cascade_in_rate_sum_s^-1")),
                "population_i_over_f": _ratio(i.get("population_sum"), f.get("population_sum")),
                "population_i_over_r": _ratio(i.get("population_sum"), r.get("population_sum")),
                "diagnostic_note": "Ratios compare component-level balance terms; raw rates are matrix coefficients, not normalized emissivity contributions.",
            }
        )
    return out


def _type50_summary(label: str, solver_dir: Path, warnings: List[str]) -> List[Dict[str, Any]]:
    name = "xstar_like_element_solver_triplet_coupling_record_audit.csv"
    rows = _read_solver_csv(label, solver_dir, name, warnings)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("audit_kind", "")) == "triplet_3S_3P_coupling_audit_summary":
            out.append(
                {
                    "case_label": label,
                    "row_kind": "triplet_3S_3P_coupling_audit_summary",
                    "radiative_i_to_f_gain_rate_sum_s^-1": _as_float(row.get("radiative_i_to_f_gain_rate_sum_s^-1")),
                    "collisional_f_to_i_gain_rate_sum_s^-1": _as_float(row.get("collisional_f_to_i_gain_rate_sum_s^-1")),
                    "collisional_i_to_f_gain_rate_sum_s^-1": _as_float(row.get("collisional_i_to_f_gain_rate_sum_s^-1")),
                    "radiative_i_to_f_over_collisional_f_to_i_rate_ratio": _as_float(row.get("radiative_i_to_f_over_collisional_f_to_i_rate_ratio")),
                    "diagnostic_conclusion": row.get("diagnostic_conclusion", ""),
                }
            )
    name = "xstar_like_element_solver_type50_ucalc_rate_audit.csv"
    rows = _read_solver_csv(label, solver_dir, name, warnings)
    for row in rows:
        if str(row.get("row_kind", "")) == "type50_ucalc_rate_audit_summary":
            out.append(
                {
                    "case_label": label,
                    "row_kind": "type50_ucalc_rate_audit_summary",
                    "n_type50_rows": _as_float(row.get("n_type50_rows")),
                    "n_helike_3p_to_3s_uv_drain_rows": _as_float(row.get("n_helike_3p_to_3s_uv_drain_rows")),
                    "sum_raw_A_helike_3p_to_3s_s^-1": _as_float(row.get("sum_raw_A_helike_3p_to_3s_s^-1")),
                    "sum_escaped_decay_helike_3p_to_3s_s^-1": _as_float(row.get("sum_escaped_decay_helike_3p_to_3s_s^-1")),
                    "sum_photoexcitation_3s_to_3p_proxy_s^-1": _as_float(row.get("sum_photoexcitation_3s_to_3p_proxy_s^-1")),
                    "treatment": row.get("treatment", ""),
                    "diagnostic_note": row.get("diagnostic_note", ""),
                }
            )
    return out


def _intercombination_feed_categories(label: str, solver_dir: Path, warnings: List[str]) -> List[Dict[str, Any]]:
    name = "xstar_like_element_solver_intercombination_feed_audit.csv"
    rows = _read_solver_csv(label, solver_dir, name, warnings)
    if not rows:
        return [_missing_row(label, name)]
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("route_role", "")),
            str(row.get("transition_kind", "")),
            str(row.get("data_type", "")),
        )
        item = grouped.setdefault(
            key,
            {
                "case_label": label,
                "route_role": key[0],
                "transition_kind": key[1],
                "data_type": key[2],
                "count": 0,
                "rate_sum_s^-1": 0.0,
                "population_weighted_rate_proxy_sum_s^-1": 0.0,
            },
        )
        item["count"] += 1
        item["rate_sum_s^-1"] += _as_float(row.get("rate_s^-1")) or 0.0
        item["population_weighted_rate_proxy_sum_s^-1"] += _as_float(row.get("population_weighted_rate_proxy_s^-1")) or 0.0
    return sorted(grouped.values(), key=lambda r: abs(float(r.get("rate_sum_s^-1") or 0.0)), reverse=True)


def _type71_summary(label: str, solver_dir: Path, warnings: List[str]) -> List[Dict[str, Any]]:
    name = "xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv"
    rows = _read_solver_csv(label, solver_dir, name, warnings)
    if not rows:
        row = _missing_row(label, name)
        row["destination_triplet_component"] = "missing_audit"
        return [row]
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        comp = str(row.get("destination_triplet_component", "")).strip()
        if comp not in {"f", "i", "r", ""}:
            comp = "other"
        if not comp:
            comp = "non_triplet"
        item = grouped.setdefault(comp, {"case_label": label, "destination_triplet_component": comp, "count": 0, "rate_sum_s^-1": 0.0})
        item["count"] += 1
        item["rate_sum_s^-1"] += _as_float(row.get("rate_s^-1")) or 0.0
    out = [grouped[k] for k in sorted(grouped)]
    by = {r["destination_triplet_component"]: r for r in out}
    if all(k in by for k in ("f", "i", "r")):
        out.append(
            {
                "case_label": label,
                "destination_triplet_component": "derived_ratios",
                "type71_i_over_f": _ratio(by["i"].get("rate_sum_s^-1"), by["f"].get("rate_sum_s^-1")),
                "type71_i_over_r": _ratio(by["i"].get("rate_sum_s^-1"), by["r"].get("rate_sum_s^-1")),
                "type71_r_over_f": _ratio(by["r"].get("rate_sum_s^-1"), by["f"].get("rate_sum_s^-1")),
            }
        )
    return out


def _type99_summary(label: str, solver_dir: Path, warnings: List[str]) -> List[Dict[str, Any]]:
    name = "xstar_like_element_solver_global_superlevel_source_matrix_terms.csv"
    rows = _read_solver_csv(label, solver_dir, name, warnings)
    if not rows:
        return [_missing_row(label, name)]
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("superlevel_level", "")),
            str(row.get("superlevel_level_label", "")),
            str(row.get("type99_parent_mapping_source", "")),
        )
        item = grouped.setdefault(
            key,
            {
                "case_label": label,
                "superlevel_level": key[0],
                "superlevel_level_label": key[1],
                "type99_parent_mapping_source": key[2],
                "type99_parent_maps_to_target_continuum_alias": row.get("type99_parent_maps_to_target_continuum_alias", ""),
                "count": 0,
                "rate_sum_s^-1": 0.0,
                "rate_max_s^-1": 0.0,
                "type71_B_f_first": _as_float(row.get("type71_B_f")),
                "type71_B_i_first": _as_float(row.get("type71_B_i")),
                "type71_B_r_first": _as_float(row.get("type71_B_r")),
                "type99_records": str(row.get("type99_records", "")),
            },
        )
        rate = _as_float(row.get("rate_s^-1")) or 0.0
        item["count"] += 1
        item["rate_sum_s^-1"] += rate
        item["rate_max_s^-1"] = max(float(item["rate_max_s^-1"]), rate)
    return sorted(grouped.values(), key=lambda r: abs(float(r.get("rate_sum_s^-1") or 0.0)), reverse=True)


def _triplet_summary(label: str, solver_dir: Path, xstar_csv: Optional[Path], value_column: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"case_label": label}
    comparison = solver_dir / "xstar_detail_population_comparison_summary.json"
    if comparison.exists():
        try:
            payload = json.loads(comparison.read_text(encoding="utf-8"))
            trip = payload.get("triplet", {})
            for key in ("f_fraction", "i_fraction", "r_fraction", "R", "G", "l2_distance_to_target", "target_f_fraction", "target_i_fraction", "target_r_fraction"):
                out[f"solver_{key}"] = trip.get(key)
        except Exception as exc:
            out["comparison_summary_read_error"] = str(exc)
    if xstar_csv is not None:
        out["xstar_triplet_lines_csv"] = str(xstar_csv)
        if xstar_csv.exists():
            rows = _read_csv(xstar_csv)
            by = {"f": 0.0, "i": 0.0, "r": 0.0}
            for row in rows:
                comp = _component_from_xstar_row(row)
                if comp in by:
                    by[comp] += _as_float(row.get(value_column)) or 0.0
            total = sum(by.values())
            out["xstar_value_column"] = value_column
            out["xstar_f_value"] = by["f"]
            out["xstar_i_value"] = by["i"]
            out["xstar_r_value"] = by["r"]
            out["xstar_f_fraction"] = by["f"] / total if total else None
            out["xstar_i_fraction"] = by["i"] / total if total else None
            out["xstar_r_fraction"] = by["r"] / total if total else None
            out["xstar_R"] = _ratio(by["f"], by["i"])
            out["xstar_G"] = _ratio(by["f"] + by["i"], by["r"])
            out["xstar_csv_status"] = "present"
        else:
            out["xstar_csv_status"] = "missing"
    else:
        out["xstar_csv_status"] = "not_supplied"
    return out


def _component_from_xstar_row(row: Dict[str, Any]) -> str:
    for key in ("component", "helike_component", "triplet_component"):
        value = str(row.get(key, "")).strip().lower()
        if value in {"f", "forbidden"}:
            return "f"
        if value in {"i", "intercombination"}:
            return "i"
        if value in {"r", "resonance"}:
            return "r"
    upper = str(row.get("upper_level", "") or row.get("upper_label", "")).replace(" ", "").lower()
    if "1s1.2s1.3s_1" in upper or "1s1.2s1.3s1" in upper:
        return "f"
    if "1s1.2p1.1p_1" in upper or "1s1.2p1.1p1" in upper:
        return "r"
    if "1s1.2p1.3p_" in upper or "1s1.2p1.3p" in upper:
        return "i"
    return "other"


def _write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines: List[str] = [
        "# He-like triplet balance diagnostic",
        "",
        "This diagnostic collates existing solver audits. It does not modify the population matrix or tune rates.",
        "",
        "## Key conclusions",
        "",
    ]
    conclusions = payload.get("conclusions", [])
    if conclusions:
        for item in conclusions:
            lines.append(f"- {item}")
    else:
        lines.append("- No automatic conclusions were generated.")
    lines += ["", "## Triplet summary", "", "| case | solver f/i/r | solver R | solver G | XSTAR f/i/r | XSTAR R | XSTAR G |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload.get("triplet_summary", []):
        sf = row.get("solver_f_fraction")
        si = row.get("solver_i_fraction")
        sr = row.get("solver_r_fraction")
        xf = row.get("xstar_f_fraction")
        xi = row.get("xstar_i_fraction")
        xr = row.get("xstar_r_fraction")
        lines.append(
            f"| {row.get('case_label')} | {sf}/{si}/{sr} | {row.get('solver_R')} | {row.get('solver_G')} | {xf}/{xi}/{xr} | {row.get('xstar_R')} | {row.get('xstar_G')} |"
        )
    lines += ["", "## Warnings", ""]
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None.")
    lines += ["", "## Type-50 / 3P-3S coupling summary", "", "| case | row | radiative i->f | collisional f->i | ratio | escaped 3P->3S sum |", "|---|---|---:|---:|---:|---:|"]
    for row in payload.get("type50_summary", []):
        lines.append(
            f"| {row.get('case_label')} | {row.get('row_kind')} | {row.get('radiative_i_to_f_gain_rate_sum_s^-1','')} | {row.get('collisional_f_to_i_gain_rate_sum_s^-1','')} | {row.get('radiative_i_to_f_over_collisional_f_to_i_rate_ratio','')} | {row.get('sum_escaped_decay_helike_3p_to_3s_s^-1','')} |"
        )
    lines += ["", "## Type-71 triplet cascade summary", "", "See `helike_type71_triplet_cascade_summary.csv` for f/i/r cascade sums and ratios.", "", "## Type-99 superlevel source summary", "", "See `helike_type99_superlevel_source_summary.csv` for superlevel source rates and type-71 branch proxies.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _automatic_conclusions(payload: Dict[str, Any]) -> List[str]:
    conclusions: List[str] = []
    trip = {r.get("case_label"): r for r in payload.get("triplet_summary", [])}
    if "C V" in trip:
        cv = trip["C V"]
        si = _as_float(cv.get("solver_i_fraction"))
        ti = _as_float(cv.get("solver_target_i_fraction"))
        sr = _as_float(cv.get("solver_r_fraction"))
        tr = _as_float(cv.get("solver_target_r_fraction"))
        if si is not None and ti is not None and si > ti:
            conclusions.append(f"C V intercombination fraction is high relative to the built-in target ({si:.6g} vs {ti:.6g}).")
        if sr is not None and tr is not None and sr < tr:
            conclusions.append(f"C V resonance fraction is low relative to the built-in target ({sr:.6g} vs {tr:.6g}).")
    type50 = {r.get("case_label"): r for r in payload.get("type50_summary", []) if r.get("row_kind") == "triplet_3S_3P_coupling_audit_summary"}
    if "C V" in type50:
        ratio = _as_float(type50["C V"].get("radiative_i_to_f_over_collisional_f_to_i_rate_ratio"))
        if ratio is not None and ratio > 1.0e4:
            conclusions.append(f"C V 3P_J->3S1 radiative drain is much larger than density-scaled 3S1->3P_J collisional coupling (ratio {ratio:.3g}); this drain suppresses, not overpopulates, i.")
    type71 = [r for r in payload.get("type71_summary", []) if r.get("destination_triplet_component") == "derived_ratios"]
    for row in type71:
        if row.get("case_label") == "C V":
            i_over_r = _as_float(row.get("type71_i_over_r"))
            if i_over_r is not None and i_over_r > 1.0:
                conclusions.append(f"C V type-71 cascade feed favors i over r in the assembled triplet cascade rate sum (i/r={i_over_r:.3g}).")
    if trip.get("C V", {}).get("xstar_csv_status") != "present":
        conclusions.append("No real C V XSTAR triplet-line CSV was supplied; generate xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv before applying an O VII-style line-output correction to C V.")
    return conclusions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[], help="Case as LABEL:SOLVER_OUT_DIR. Example: 'C V:c5_xstar_like_element_solver_v03100_xstar_msolvelucy_superlevels'.")
    parser.add_argument("--xstar-triplet-lines-csv", action="append", type=_parse_label_path, default=[], help="Optional XSTAR triplet-line CSV as LABEL:CSV. Example: 'O VII:xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv'.")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--out-dir", default="helike_triplet_balance_diagnostic")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    cases = [_parse_case(item) for item in args.case]
    if not cases:
        raise SystemExit("Provide at least one --case LABEL:SOLVER_OUT_DIR")
    xstar_by_label = {label: path for label, path in args.xstar_triplet_lines_csv}
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "cases": [{"label": label, "solver_out_dir": str(path)} for label, path in cases],
        "xstar_value_column": args.xstar_value_column,
        "triplet_summary": [],
        "component_balance": [],
        "type50_summary": [],
        "intercombination_feed_categories": [],
        "type71_summary": [],
        "type99_summary": [],
        "warnings": [],
    }
    for label, solver_dir in cases:
        payload["triplet_summary"].append(_triplet_summary(label, solver_dir, xstar_by_label.get(label), args.xstar_value_column))
        payload["component_balance"].extend(_component_balance(label, solver_dir, payload["warnings"]))
        payload["type50_summary"].extend(_type50_summary(label, solver_dir, payload["warnings"]))
        payload["intercombination_feed_categories"].extend(_intercombination_feed_categories(label, solver_dir, payload["warnings"]))
        payload["type71_summary"].extend(_type71_summary(label, solver_dir, payload["warnings"]))
        payload["type99_summary"].extend(_type99_summary(label, solver_dir, payload["warnings"]))
    payload["conclusions"] = _automatic_conclusions(payload)

    _write_csv(out_dir / "helike_triplet_summary.csv", payload["triplet_summary"])
    _write_csv(out_dir / "helike_component_balance.csv", payload["component_balance"])
    _write_csv(out_dir / "helike_type50_triplet_coupling_summary.csv", payload["type50_summary"])
    _write_csv(out_dir / "helike_intercombination_feed_categories.csv", payload["intercombination_feed_categories"])
    _write_csv(out_dir / "helike_type71_triplet_cascade_summary.csv", payload["type71_summary"])
    _write_csv(out_dir / "helike_type99_superlevel_source_summary.csv", payload["type99_summary"])
    _write_json(out_dir / "helike_triplet_balance_diagnostic_summary.json", payload)
    _write_markdown(out_dir / "helike_triplet_balance_diagnostic.md", payload)

    if args.print_summary:
        print("He-like triplet balance diagnostic")
        print("--------------------------------")
        for row in payload["triplet_summary"]:
            print(
                f"{row.get('case_label')}: solver f/i/r="
                f"{row.get('solver_f_fraction')}/{row.get('solver_i_fraction')}/{row.get('solver_r_fraction')} "
                f"R={row.get('solver_R')} G={row.get('solver_G')} xstar_csv={row.get('xstar_csv_status')}"
            )
        print("conclusions:")
        for item in payload["conclusions"]:
            print(f"- {item}")
        if payload.get("warnings"):
            print("warnings:")
            for item in payload["warnings"]:
                print(f"- {item}")
        print(f"wrote: {out_dir / 'helike_triplet_balance_diagnostic.md'}")


if __name__ == "__main__":
    main()
