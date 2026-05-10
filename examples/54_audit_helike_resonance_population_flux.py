#!/usr/bin/env python3
"""
Audit population-weighted feed/loss paths for the He-like resonance upper level.

This diagnostic follows the source-code-first validation path after local XSTAR
``T``/``ne`` matching.  It does not fit scale factors and does not change solver
physics.  Instead, it combines the full-global matrix terms with the solved
population fractions to estimate which currently assembled pathways actually
feed the He-like resonance upper level ``1s2p 1P1``.

The goal is to distinguish three possibilities before touching source-code
rates:

* the resonance upper level is under-fed by direct collisional/pumping paths;
* the resonance upper level is fed mostly by cascades that depend on upstream
  source/radiation normalization;
* the deficit is dominated by output/escape/radiative-transfer effects rather
  than population balance.
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
        return x if math.isfinite(x) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(text)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resonance_label(text: str) -> bool:
    compact = str(text or "").replace(" ", "")
    return (
        "1s1.2p1.1P_1" in compact
        or "1s2p1P" in compact
        or "2p1.1P_1" in compact
    )


def _find_solver_dir(row: dict[str, str], solver_root: Path) -> Path | None:
    out_dir = row.get("recommended_solver_out_dir") or row.get("solver_out_dir") or ""
    if out_dir:
        p = Path(out_dir)
        if p.is_absolute() and p.exists():
            return p
        q = solver_root / p
        if q.exists():
            return q
    tag = (row.get("tag") or "").lower()
    if tag:
        for p in sorted(solver_root.glob(f"{tag}_xstar_like_element_solver_*")):
            if (p / "xstar_like_element_solver_full_global_matrix_terms.csv").exists():
                return p
    return None


def _triplet_from_summary(path: Path) -> dict[str, float | None]:
    summary = _read_json(path)
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
        "delta_f": (solver_f - target_f) if solver_f is not None and target_f is not None else None,
        "delta_i": (solver_i - target_i) if solver_i is not None and target_i is not None else None,
        "delta_r": (solver_r - target_r) if solver_r is not None and target_r is not None else None,
        "l2": _to_float(t.get("l2_distance_to_target")),
    }


def _load_population_by_global(solver_dir: Path) -> tuple[dict[int, float], dict[int, dict[str, str]]]:
    gidx_rows = _read_csv(solver_dir / "xstar_like_element_solver_global_index.csv")
    gidx: dict[tuple[int, int], int] = {}
    meta: dict[int, dict[str, str]] = {}
    for row in gidx_rows:
        gi = _to_int(row.get("global_index"))
        st = _to_int(row.get("ion_stage"))
        lev = _to_int(row.get("level_index"))
        if gi is None:
            continue
        meta[gi] = row
        if st is not None and lev is not None:
            gidx[(st, lev)] = gi
    pop: dict[int, float] = {}
    for row in _read_csv(solver_dir / "xstar_like_element_solver_populations.csv"):
        st = _to_int(row.get("ion_stage"))
        lev = _to_int(row.get("level_index"))
        val = _to_float(row.get("population_fraction"))
        if st is None or lev is None or val is None:
            continue
        gi = gidx.get((st, lev))
        if gi is not None:
            pop[gi] = val
    return pop, meta


def _term_rate(row: dict[str, str]) -> float | None:
    for key in ("full_global_rate_s^-1", "rate_s^-1", "raw_rate_s^-1"):
        val = _to_float(row.get(key))
        if val is not None and val >= 0:
            return val
    val = _to_float(row.get("signed_rate_s^-1"))
    if val is not None:
        return abs(val)
    return None


def _family(row: dict[str, str]) -> str:
    kind = row.get("transition_kind") or row.get("matrix_role") or "unknown"
    dt = row.get("data_type") or row.get("resonance_collisional_feed_data_type") or ""
    src = row.get("source_method") or ""
    if dt:
        return f"{kind}|type{dt}"
    if src:
        return f"{kind}|{src.split(';')[0][:40]}"
    return str(kind)


def _classify_source(row: dict[str, str], src_meta: dict[str, str] | None) -> str:
    kind = str(row.get("transition_kind") or "")
    label = str(row.get("from_level_label") or (src_meta or {}).get("level_label") or "")
    if _to_float(row.get("photoexcitation_rate_s^-1")) not in (None, 0.0):
        return "explicit_photoexcitation"
    if "collisional" in kind or "collision" in kind:
        if "1s2.1S" in label.replace(" ", "") or "1s2_1S" in label.replace(" ", ""):
            return "direct_ground_to_resonance_collision"
        return "collisional_cascade_or_mixing_to_resonance"
    if kind == "radiative_decay":
        if "1s2.1S" in label.replace(" ", ""):
            return "direct_ground_to_resonance_radiative_photo_proxy"
        return "radiative_cascade_to_resonance"
    if "superlevel" in kind.lower() or "source" in kind.lower():
        return "superlevel_or_recombination_source_to_resonance"
    return kind or "unknown"


def _audit_one(row: dict[str, str], solver_root: Path, top_n: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    solver_dir = _find_solver_dir(row, solver_root)
    base: dict[str, Any] = {
        "ion": row.get("ion"),
        "tag": row.get("tag"),
        "solver_out_dir": str(solver_dir) if solver_dir else "",
        "xstar_temperature_K": _to_float(row.get("xstar_temperature_K")),
        "xstar_electron_density_cm^-3": _to_float(row.get("xstar_electron_density_cm^-3")),
        "xstar_log_xi_local": _to_float(row.get("xstar_log_xi_local")),
        "xstar_helike_fraction": _to_float(row.get("xstar_helike_fraction")),
    }
    if solver_dir is None:
        base.update({"status": "missing_solver_dir"})
        return base, []
    comp_path = solver_dir / "xstar_detail_population_comparison_summary.json"
    base.update(_triplet_from_summary(comp_path))
    solver_r = base.get("solver_r")
    target_r = base.get("target_r")
    if solver_r is not None and target_r is not None and solver_r > 0:
        base["target_over_solver_r"] = target_r / solver_r
        base["resonance_deficit_fraction"] = target_r - solver_r
    pop, meta = _load_population_by_global(solver_dir)
    matrix_path = solver_dir / "xstar_like_element_solver_full_global_matrix_terms.csv"
    if not matrix_path.exists():
        matrix_path = solver_dir / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv"
    rows = _read_csv(matrix_path)
    resonance_indices = set()
    for gi, m in meta.items():
        if _resonance_label(m.get("level_label", "")):
            resonance_indices.add(gi)
    if not resonance_indices:
        # Fallback from matrix labels.
        for tr in rows:
            rgi = _to_int(tr.get("matrix_row_global_index"))
            if rgi is not None and _resonance_label(tr.get("to_level_label", "")):
                resonance_indices.add(rgi)
    base["resonance_global_indices"] = ";".join(str(x) for x in sorted(resonance_indices))
    base["n_resonance_global_indices"] = len(resonance_indices)
    resonance_pop = sum(pop.get(gi, 0.0) for gi in resonance_indices)
    base["resonance_population_fraction_sum"] = resonance_pop

    detail: list[dict[str, Any]] = []
    feed_total = 0.0
    feed_total_signed = 0.0
    feed_by_class: dict[str, float] = {}
    feed_by_family: dict[str, float] = {}
    loss_total = 0.0
    loss_by_family: dict[str, float] = {}
    photo_feed = 0.0
    direct_ground_feed = 0.0
    for tr in rows:
        if tr.get("matrix_term_kind") != "offdiag_gain":
            continue
        row_gi = _to_int(tr.get("matrix_row_global_index"))
        col_gi = _to_int(tr.get("matrix_col_global_index"))
        rate = _term_rate(tr)
        if row_gi is None or col_gi is None or rate is None:
            continue
        source_pop = pop.get(col_gi, 0.0)
        weighted_signed = source_pop * rate
        weighted_positive = max(source_pop, 0.0) * rate
        src_meta = meta.get(col_gi, {})
        dst_meta = meta.get(row_gi, {})
        fam = _family(tr)
        cls = _classify_source(tr, src_meta)
        if row_gi in resonance_indices and col_gi not in resonance_indices:
            feed_total += weighted_positive
            feed_total_signed += weighted_signed
            feed_by_class[cls] = feed_by_class.get(cls, 0.0) + weighted_positive
            feed_by_family[fam] = feed_by_family.get(fam, 0.0) + weighted_positive
            pe = _to_float(tr.get("photoexcitation_rate_s^-1")) or 0.0
            if pe > 0:
                photo_feed += weighted_positive
            if cls.startswith("direct_ground"):
                direct_ground_feed += weighted_positive
            detail.append({
                "ion": row.get("ion"),
                "tag": row.get("tag"),
                "path_role": "feed_into_resonance_upper",
                "source_global_index": col_gi,
                "destination_global_index": row_gi,
                "source_level_label": tr.get("from_level_label") or src_meta.get("level_label"),
                "destination_level_label": tr.get("to_level_label") or dst_meta.get("level_label"),
                "transition_kind": tr.get("transition_kind"),
                "data_type": tr.get("data_type") or tr.get("resonance_collisional_feed_data_type"),
                "source_method": tr.get("source_method"),
                "rate_s^-1": rate,
                "source_population_fraction": source_pop,
                "population_weighted_flux_s^-1": weighted_positive,
                "population_weighted_flux_signed_s^-1": weighted_signed,
                "feed_class": cls,
                "feed_family": fam,
                "photoexcitation_rate_s^-1": _to_float(tr.get("photoexcitation_rate_s^-1")) or 0.0,
                "raw_A_s^-1": _to_float(tr.get("raw_A_s^-1")),
            })
        elif col_gi in resonance_indices and row_gi not in resonance_indices:
            rpop = pop.get(col_gi, 0.0)
            wloss = max(rpop, 0.0) * rate
            loss_total += wloss
            loss_by_family[fam] = loss_by_family.get(fam, 0.0) + wloss
    detail_sorted = sorted(detail, key=lambda r: abs(float(r.get("population_weighted_flux_s^-1") or 0.0)), reverse=True)
    for rank, d in enumerate(detail_sorted, start=1):
        d["rank_by_population_weighted_feed"] = rank
    base.update({
        "status": "ok",
        "population_weighted_feed_to_resonance_sum_s^-1": feed_total,
        "population_weighted_feed_to_resonance_signed_sum_s^-1": feed_total_signed,
        "population_weighted_loss_from_resonance_sum_s^-1": loss_total,
        "population_weighted_direct_ground_to_resonance_feed_s^-1": direct_ground_feed,
        "population_weighted_photoexcitation_to_resonance_s^-1": photo_feed,
        "feed_to_loss_ratio": (feed_total / loss_total) if loss_total > 0 else None,
        "feed_by_class": ";".join(f"{k}:{v:.6g}" for k, v in sorted(feed_by_class.items(), key=lambda kv: -abs(kv[1]))),
        "feed_by_family_top": ";".join(f"{k}:{v:.6g}" for k, v in sorted(feed_by_family.items(), key=lambda kv: -abs(kv[1]))[:8]),
        "loss_by_family_top": ";".join(f"{k}:{v:.6g}" for k, v in sorted(loss_by_family.items(), key=lambda kv: -abs(kv[1]))[:8]),
        "top_feed_source_label": detail_sorted[0].get("source_level_label") if detail_sorted else "",
        "top_feed_class": detail_sorted[0].get("feed_class") if detail_sorted else "",
        "top_feed_flux_s^-1": detail_sorted[0].get("population_weighted_flux_s^-1") if detail_sorted else None,
        "source_code_priority": "audit_XSTAR_bound_bound_photoexcitation_and_radiation_normalization" if photo_feed <= 0 else "compare_explicit_photoexcitation_against_XSTAR",
        "policy": "diagnostic_population_weighted_flux_only; no empirical scaling or solver modification",
    })
    if solver_r is not None and target_r is not None and solver_r > 0 and feed_total > 0:
        ratio = target_r / solver_r
        base["linearized_equivalent_feed_multiplier_for_target_r_not_applied"] = ratio
        base["linearized_equivalent_missing_feed_s^-1_not_applied"] = feed_total * max(0.0, ratio - 1.0)
    return base, detail_sorted[:top_n]


def _write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# He-like resonance population-flux audit",
        "",
        "This diagnostic combines solved populations with full-global matrix terms to identify the currently assembled population-weighted feed into the He-like resonance upper level `1s2p 1P1`. It does not fit or apply any scale factors.",
        "",
    ]
    if rows:
        lines.append("| Ion | solver r | target r | feed to r (s^-1) | loss from r (s^-1) | direct ground feed | photoexcitation feed | top feed class | next priority |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
        for r in rows:
            lines.append(
                f"| {r.get('ion','')} | {_fmt(r.get('solver_r'))} | {_fmt(r.get('target_r'))} | "
                f"{_fmt(r.get('population_weighted_feed_to_resonance_sum_s^-1'))} | "
                f"{_fmt(r.get('population_weighted_loss_from_resonance_sum_s^-1'))} | "
                f"{_fmt(r.get('population_weighted_direct_ground_to_resonance_feed_s^-1'))} | "
                f"{_fmt(r.get('population_weighted_photoexcitation_to_resonance_s^-1'))} | "
                f"{r.get('top_feed_class','')} | {r.get('source_code_priority','')} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "If `population_weighted_photoexcitation_to_resonance_s^-1` is zero while all ions have low resonance fractions, the next source-code target is XSTAR's bound-bound photoexcitation / line-pumping and local radiation normalization rather than empirical collisional scale fitting.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(v: Any) -> str:
    x = _to_float(v)
    if x is None:
        return ""
    return f"{x:.6g}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit population-weighted He-like resonance upper-level feed/loss paths.")
    ap.add_argument("--cases-csv", required=True, help="helike_local_state_cases.csv from example 51")
    ap.add_argument("--solver-root", default=".", help="root containing solver output directories")
    ap.add_argument("--out-dir", default="helike_resonance_population_flux_audit_v03126")
    ap.add_argument("--top-n", type=int, default=25, help="number of top per-ion feed rows to keep in detail output")
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args(argv)

    cases = _read_csv(Path(args.cases_csv))
    solver_root = Path(args.solver_root)
    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    for row in cases:
        if str(row.get("can_generate_solver_command", "")).lower() not in {"true", "1", "yes"} and row.get("status") != "local_state_selected":
            continue
        summary, details = _audit_one(row, solver_root, args.top_n)
        summary_rows.append(summary)
        detail_rows.extend(details)

    out_dir = Path(args.out_dir)
    _write_csv(out_dir / "helike_resonance_population_flux_summary.csv", summary_rows)
    _write_csv(out_dir / "helike_resonance_population_flux_detail.csv", detail_rows)
    _write_markdown(out_dir / "helike_resonance_population_flux_audit.md", summary_rows)
    meta = {
        "n_cases": len(summary_rows),
        "n_solver_r_low": sum(1 for r in summary_rows if (_to_float(r.get("delta_r")) or 0.0) < 0.0),
        "n_zero_photoexcitation_feed": sum(1 for r in summary_rows if (_to_float(r.get("population_weighted_photoexcitation_to_resonance_s^-1")) or 0.0) == 0.0),
        "policy": "population-weighted source-code audit only; no empirical triplet scale fitting",
    }
    (out_dir / "helike_resonance_population_flux_audit.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if args.print_summary:
        print("He-like resonance population-flux audit")
        print("-----------------------------------------")
        for k, v in meta.items():
            print(f"{k}={v}")
        print(f"wrote: {out_dir / 'helike_resonance_population_flux_summary.csv'}")
        print(f"wrote: {out_dir / 'helike_resonance_population_flux_detail.csv'}")
        print(f"wrote: {out_dir / 'helike_resonance_population_flux_audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
