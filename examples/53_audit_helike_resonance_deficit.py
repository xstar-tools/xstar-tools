#!/usr/bin/env python3
"""
Audit common He-like resonance deficits after local-state validation.

This diagnostic reads the all-ion local-state case table produced by
``examples/51_run_helike_local_state_validation.py`` and the per-ion comparison
summaries written by ``examples/43_compare_xstar_detail_populations.py``.  It is
intended for the source-code-first stage after local XSTAR ``T`` and ``ne`` have
been matched.

The script does not fit scale factors.  It collects the residual triplet pattern,
the same-run XSTAR line depths, the current diagnostic radiation context, direct
collisional feed into the resonance upper level, and any explicit photoexcitation
terms into the resonance upper level.  The goal is to decide whether the next
source-code work should focus on local radiation/line-pumping normalization or on
row-level collisional rates.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return None if math.isnan(x) else x
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(text)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_summary(row: dict[str, str], solver_root: Path) -> tuple[Path | None, dict[str, Any]]:
    out_dir = row.get("recommended_solver_out_dir") or row.get("solver_out_dir") or ""
    candidates: list[Path] = []
    if out_dir:
        p = Path(out_dir)
        if p.is_absolute():
            candidates.append(p / "xstar_detail_population_comparison_summary.json")
        candidates.append(solver_root / p / "xstar_detail_population_comparison_summary.json")
    tag = (row.get("tag") or "").lower()
    if tag:
        candidates.extend(solver_root.glob(f"{tag}_xstar_like_element_solver_*/*comparison_summary.json"))
    for path in candidates:
        if path.exists():
            return path, _read_json(path)
    return None, {}


def _triplet(summary: dict[str, Any]) -> dict[str, float | None]:
    t = summary.get("triplet", {}) if isinstance(summary, dict) else {}
    solver_f = _to_float(t.get("f_fraction"))
    solver_i = _to_float(t.get("i_fraction"))
    solver_r = _to_float(t.get("r_fraction"))
    target_f = _to_float(t.get("target_f_fraction"))
    target_i = _to_float(t.get("target_i_fraction"))
    target_r = _to_float(t.get("target_r_fraction"))
    return {
        "solver_f": solver_f,
        "solver_i": solver_i,
        "solver_r": solver_r,
        "solver_R": _to_float(t.get("R")),
        "solver_G": _to_float(t.get("G")),
        "target_f": target_f,
        "target_i": target_i,
        "target_r": target_r,
        "target_R": _to_float(t.get("target_R")),
        "target_G": _to_float(t.get("target_G")),
        "delta_f": _to_float(t.get("delta_f_fraction")) if t.get("delta_f_fraction") is not None else (solver_f - target_f if solver_f is not None and target_f is not None else None),
        "delta_i": _to_float(t.get("delta_i_fraction")) if t.get("delta_i_fraction") is not None else (solver_i - target_i if solver_i is not None and target_i is not None else None),
        "delta_r": _to_float(t.get("delta_r_fraction")) if t.get("delta_r_fraction") is not None else (solver_r - target_r if solver_r is not None and target_r is not None else None),
        "l2": _to_float(t.get("l2_distance_to_target")),
    }


def _solver_dir_from_row(row: dict[str, str], solver_root: Path) -> Path | None:
    out_dir = row.get("recommended_solver_out_dir") or row.get("solver_out_dir") or ""
    if not out_dir:
        return None
    p = Path(out_dir)
    if p.is_absolute() and p.exists():
        return p
    q = solver_root / p
    return q if q.exists() else None


def _sum_resonance_collisional_feed(solver_dir: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "direct_resonance_collisional_feed_rows": 0,
        "direct_resonance_collisional_feed_sum_s^-1": None,
        "direct_resonance_collisional_feed_by_type": "",
        "direct_resonance_collisional_feed_status": "missing_audit",
    }
    if solver_dir is None:
        return out
    path = solver_dir / "xstar_like_element_solver_resonance_collisional_feed_audit.csv"
    rows = _read_csv(path)
    if not rows:
        return out
    total = 0.0
    by_type: dict[str, float] = {}
    n = 0
    for row in rows:
        if row.get("row_kind") != "resonance_collisional_feed_audit":
            continue
        rate = _to_float(row.get("matrix_rate_s^-1"))
        if rate is None:
            continue
        n += 1
        total += rate
        dt = row.get("data_type") or "unknown"
        by_type[dt] = by_type.get(dt, 0.0) + rate
    out.update({
        "direct_resonance_collisional_feed_rows": n,
        "direct_resonance_collisional_feed_sum_s^-1": total,
        "direct_resonance_collisional_feed_by_type": ";".join(f"{k}:{v:.6g}" for k, v in sorted(by_type.items())),
        "direct_resonance_collisional_feed_status": "available",
    })
    return out


def _radiation_context(solver_dir: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "radiation_field_mode": "",
        "radiation_bremsa_scale": None,
        "radiation_powerlaw_index": None,
        "radiation_total_bremsa_integral": None,
        "radiation_status": "missing_context",
    }
    if solver_dir is None:
        return out
    rows = _read_csv(solver_dir / "xstar_like_element_solver_radiation_context.csv")
    if rows:
        row = rows[0]
        out.update({
            "radiation_field_mode": row.get("radiation_field_mode", ""),
            "radiation_bremsa_scale": _to_float(row.get("radiation_bremsa_scale")),
            "radiation_powerlaw_index": _to_float(row.get("radiation_powerlaw_index")),
            "radiation_total_bremsa_integral": _to_float(row.get("total_bremsa_integral_over_eV_grid")),
            "radiation_status": row.get("warning") or row.get("assembly_status") or "available",
        })
    return out


def _photoexcitation_into_resonance(solver_dir: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "photoexcitation_into_resonance_rows": 0,
        "photoexcitation_into_resonance_sum_s^-1": 0.0,
        "photoexcitation_into_resonance_max_s^-1": 0.0,
        "photoexcitation_into_resonance_status": "missing_matrix_terms",
    }
    if solver_dir is None:
        return out
    path = solver_dir / "xstar_like_element_solver_full_global_matrix_terms.csv"
    if not path.exists():
        path = solver_dir / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv"
    rows = _read_csv(path)
    if not rows:
        return out
    n = 0
    total = 0.0
    mx = 0.0
    for row in rows:
        if "1s1.2p1.1P_1" not in (row.get("to_level_label", "") or ""):
            continue
        if row.get("matrix_term_kind") != "offdiag_gain":
            continue
        pe = _to_float(row.get("photoexcitation_rate_s^-1"))
        if pe is None or pe == 0.0:
            continue
        n += 1
        total += pe
        mx = max(mx, pe)
    out.update({
        "photoexcitation_into_resonance_rows": n,
        "photoexcitation_into_resonance_sum_s^-1": total,
        "photoexcitation_into_resonance_max_s^-1": mx,
        "photoexcitation_into_resonance_status": "explicit_terms_available" if n else "no_nonzero_photoexcitation_terms_into_resonance_upper",
    })
    return out


def _target_line_depths(row: dict[str, str], cases_base: Path) -> dict[str, Any]:
    csv_path = row.get("target_csv_path") or row.get("xstar_target_csv") or ""
    out: dict[str, Any] = {
        "target_csv_path": csv_path,
        "target_triplet_total_emit": _to_float(row.get("xstar_target_total_triplet_emit")),
        "target_max_depth_inward": _to_float(row.get("xstar_target_max_depth_inward")),
        "target_max_depth_outward": _to_float(row.get("xstar_target_max_depth_outward")),
        "target_resonance_depth_inward": None,
        "target_resonance_emit_outward": None,
    }
    if not csv_path:
        return out
    p = Path(csv_path)
    if not p.exists() and not p.is_absolute():
        p2 = cases_base / p
        if p2.exists():
            p = p2
    if not p.exists():
        out["target_resonance_depth_inward"] = out.get("target_max_depth_inward")
        return out
    for tr in _read_csv(p):
        text = (tr.get("upper_level", "") + " " + tr.get("lower_level", "")).lower()
        if "1p_1" in text or "2p1.1p_1" in text or "1s1.2p1.1p" in text:
            out["target_resonance_depth_inward"] = _to_float(tr.get("depth_inward"))
            out["target_resonance_emit_outward"] = _to_float(tr.get("emit_outward"))
            break
    return out


def audit(cases_csv: Path, solver_root: Path) -> list[dict[str, Any]]:
    rows = _read_csv(cases_csv)
    cases_base = cases_csv.parent
    out_rows: list[dict[str, Any]] = []
    for case in rows:
        summary_path, summary = _find_summary(case, solver_root)
        trip = _triplet(summary)
        sdir = _solver_dir_from_row(case, solver_root)
        target = _target_line_depths(case, cases_base)
        delta_r = trip.get("delta_r")
        target_r = trip.get("target_r")
        solver_r = trip.get("solver_r")
        missing_r_over_target = None
        if delta_r is not None and target_r not in (None, 0.0):
            missing_r_over_target = (-delta_r) / target_r
        row: dict[str, Any] = {
            "ion": case.get("ion", ""),
            "tag": case.get("tag", ""),
            "xstar_temperature_K": _to_float(case.get("xstar_temperature_K")),
            "xstar_electron_density_cm^-3": _to_float(case.get("xstar_electron_density_cm^-3")),
            "xstar_log_xi_local": _to_float(case.get("xstar_log_xi_local")),
            "solver_out_dir": str(sdir) if sdir else (case.get("recommended_solver_out_dir") or ""),
            "comparison_summary_path": str(summary_path) if summary_path else "",
            **trip,
            "resonance_fraction_deficit": -delta_r if delta_r is not None else None,
            "resonance_fraction_deficit_over_target_r": missing_r_over_target,
            "solver_r_over_target_r": (solver_r / target_r if solver_r is not None and target_r not in (None, 0.0) else None),
            **target,
            **_sum_resonance_collisional_feed(sdir),
            **_radiation_context(sdir),
            **_photoexcitation_into_resonance(sdir),
        }
        if row["photoexcitation_into_resonance_sum_s^-1"] == 0.0 and (row.get("delta_r") or 0) < 0:
            row["next_source_code_priority"] = "align_XSTAR_line_pumping_or_radiation_normalization_before_collision_scale_fitting"
        elif (row.get("delta_r") or 0) < 0:
            row["next_source_code_priority"] = "compare_nonzero_photoexcitation_and_direct_resonance_feed_against_XSTAR"
        else:
            row["next_source_code_priority"] = "no_resonance_deficit"
        out_rows.append(row)
    return out_rows


def _fmt(x: Any, prec: int = 6) -> str:
    if x is None or x == "":
        return ""
    if isinstance(x, float):
        if math.isnan(x):
            return ""
        return f"{x:.{prec}g}"
    return str(x)


def write_md(path: Path, rows: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# He-like resonance-deficit and radiation-feed audit\n")
    lines.append("This diagnostic summarizes the common local-state residual after matching XSTAR `T`/`ne`: solver resonance fractions below the same-run XSTAR target. It does not fit scale factors.\n")
    lines.append("| Ion | T (K) | ne | log xi | solver r | target r | deficit/target | solver f | target f | target depth(in) | collisional feed sum (s^-1) | photoexcitation into r (s^-1) | next priority |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        lines.append(
            f"| {r.get('ion','')} | {_fmt(r.get('xstar_temperature_K'))} | {_fmt(r.get('xstar_electron_density_cm^-3'))} | {_fmt(r.get('xstar_log_xi_local'))} | {_fmt(r.get('solver_r'))} | {_fmt(r.get('target_r'))} | {_fmt(r.get('resonance_fraction_deficit_over_target_r'))} | {_fmt(r.get('solver_f'))} | {_fmt(r.get('target_f'))} | {_fmt(r.get('target_resonance_depth_inward'))} | {_fmt(r.get('direct_resonance_collisional_feed_sum_s^-1'))} | {_fmt(r.get('photoexcitation_into_resonance_sum_s^-1'))} | {r.get('next_source_code_priority','')} |"
        )
    low_r = [r for r in rows if (r.get("delta_r") or 0) < 0]
    high_f = [r for r in rows if (r.get("delta_f") or 0) > 0]
    no_pe = [r for r in rows if (r.get("photoexcitation_into_resonance_sum_s^-1") or 0) == 0]
    lines.append("\n## Interpretation\n")
    lines.append(f"- Solver resonance fraction below target: `{len(low_r)}/{len(rows)}`")
    lines.append(f"- Solver forbidden fraction above target: `{len(high_f)}/{len(rows)}`")
    lines.append(f"- Cases with no explicit nonzero photoexcitation into `1s2p 1P1` in the assembled matrix audit: `{len(no_pe)}/{len(rows)}`")
    if low_r and high_f and len(low_r) == len(rows) and len(high_f) == len(rows):
        lines.append("- The common pattern is cross-ion, so the next source-code check should be shared radiation/line-pumping or direct ground-to-resonance feed, not per-ion fitted triplet scaling.")
    lines.append("\n## Recommended next checks\n")
    lines.append("1. Trace XSTAR `ucalc.f90` and `calc_emis_ion.f90` treatment of bound-bound absorption/photoexcitation into the He-like resonance upper level `1s2p 1P1`.")
    lines.append("2. Replace the current diagnostic `--radiation-bremsa-scale` continuum with the local XSTAR continuum/transfer context before interpreting type-56/type-63/type-68/type-69 rates.")
    lines.append("3. Keep collision-rate row audits, but defer empirical collisional scaling until the radiation/line-pumping channel is aligned.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases-csv", required=True, help="helike_local_state_cases.csv from example 51")
    p.add_argument("--solver-root", default=".", help="Root containing solver output directories")
    p.add_argument("--out-dir", default="helike_resonance_deficit_audit")
    p.add_argument("--print-summary", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    rows = audit(Path(args.cases_csv), Path(args.solver_root))
    out = Path(args.out_dir)
    _write_csv(out / "helike_resonance_deficit_audit.csv", rows)
    write_md(out / "helike_resonance_deficit_audit.md", rows)
    summary = {
        "n_cases": len(rows),
        "n_solver_f_high": sum(1 for r in rows if (r.get("delta_f") or 0) > 0),
        "n_solver_r_low": sum(1 for r in rows if (r.get("delta_r") or 0) < 0),
        "n_no_nonzero_photoexcitation_into_resonance": sum(1 for r in rows if (r.get("photoexcitation_into_resonance_sum_s^-1") or 0) == 0),
        "policy": "source-code audit only; no empirical triplet scale fitting",
    }
    (out / "helike_resonance_deficit_audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.print_summary:
        print("He-like resonance-deficit and radiation-feed audit")
        print("----------------------------------------------------")
        for k, v in summary.items():
            print(f"{k}={v}")
        print(f"wrote: {out/'helike_resonance_deficit_audit.csv'}")
        print(f"wrote: {out/'helike_resonance_deficit_audit.md'}")


if __name__ == "__main__":
    main()
