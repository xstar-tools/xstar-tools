#!/usr/bin/env python3
"""
Summarize He-like local-state solver comparisons against same-run XSTAR targets.

This script is intentionally diagnostic-only.  It reads the case table produced by
``examples/51_run_helike_local_state_validation.py`` and the per-case comparison
summaries written by ``examples/43_compare_xstar_detail_populations.py``.  It then
builds one compact table for C V, O VII, Mg XI, and Ca XIX.

The purpose is to expose systematic residuals after matching the XSTAR local
``xout_abund1.fits`` temperature and density, not to fit empirical scale factors.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _find_case_summary(row: dict[str, str], solver_root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    out = row.get("recommended_solver_out_dir") or ""
    candidates: list[Path] = []
    if out:
        p = Path(out)
        if p.is_absolute():
            candidates.append(p / "xstar_detail_population_comparison_summary.json")
        candidates.append(solver_root / p / "xstar_detail_population_comparison_summary.json")
    # Fallback: search by ion/tag if the output directory was renamed.
    tag = (row.get("tag") or "").lower()
    if tag:
        candidates.extend(solver_root.glob(f"{tag}_xstar_like_element_solver_*/*comparison_summary.json"))
    for path in candidates:
        if path.exists():
            try:
                return path, json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return path, None
    return None, None


def _triplet_from_summary(summary: dict[str, Any] | None) -> dict[str, float | None]:
    t = (summary or {}).get("triplet", {}) if isinstance(summary, dict) else {}
    return {
        "solver_f": _to_float(t.get("f_fraction")),
        "solver_i": _to_float(t.get("i_fraction")),
        "solver_r": _to_float(t.get("r_fraction")),
        "solver_R": _to_float(t.get("R")),
        "solver_G": _to_float(t.get("G")),
        "target_f": _to_float(t.get("target_f_fraction")),
        "target_i": _to_float(t.get("target_i_fraction")),
        "target_r": _to_float(t.get("target_r_fraction")),
        "delta_f": _to_float(t.get("delta_f_fraction")),
        "delta_i": _to_float(t.get("delta_i_fraction")),
        "delta_r": _to_float(t.get("delta_r_fraction")),
        "l2": _to_float(t.get("l2_distance_to_target")),
    }


def _delta_sign(value: float | None) -> str:
    if value is None:
        return ""
    if value > 0:
        return "high"
    if value < 0:
        return "low"
    return "matched"


def summarize(cases_csv: Path, solver_root: Path) -> list[dict[str, Any]]:
    rows = _read_csv(cases_csv)
    out: list[dict[str, Any]] = []
    for row in rows:
        summary_path, summary = _find_case_summary(row, solver_root)
        vals = _triplet_from_summary(summary)
        out_row: dict[str, Any] = {
            "ion": row.get("ion", ""),
            "tag": row.get("tag", ""),
            "status": row.get("status", ""),
            "xstar_temperature_K": _to_float(row.get("xstar_temperature_K")),
            "xstar_electron_density_cm^-3": _to_float(row.get("xstar_electron_density_cm^-3")),
            "xstar_log_xi_local": _to_float(row.get("xstar_log_xi_local")),
            "xstar_helike_fraction": _to_float(row.get("xstar_helike_fraction")),
            "target_csv_source": row.get("target_csv_source", ""),
            "target_csv_path": row.get("target_csv_path", ""),
            "solver_out_dir": row.get("recommended_solver_out_dir", ""),
            "comparison_summary_path": str(summary_path) if summary_path else "",
            **vals,
        }
        out_row["residual_pattern"] = ",".join(
            f"{comp}_{_delta_sign(out_row.get('delta_' + comp))}" for comp in ("f", "i", "r") if out_row.get("delta_" + comp) is not None
        )
        out.append(out_row)
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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
    lines.append("# He-like local-state comparison summary\n")
    lines.append("This summary compares solver triplet fractions with the same-run XSTAR triplet targets after selecting local XSTAR `T`, `ne`, and `log xi` from `xout_abund1.fits`. It does not fit scale factors.\n")
    lines.append("| Ion | T (K) | ne (cm^-3) | log xi | solver f/i/r | XSTAR f/i/r | Δf/Δi/Δr | R | G | L2 | pattern |")
    lines.append("|---|---:|---:|---:|---|---|---|---:|---:|---:|---|")
    for r in rows:
        solver = f"{_fmt(r.get('solver_f'))}/{_fmt(r.get('solver_i'))}/{_fmt(r.get('solver_r'))}"
        target = f"{_fmt(r.get('target_f'))}/{_fmt(r.get('target_i'))}/{_fmt(r.get('target_r'))}"
        delta = f"{_fmt(r.get('delta_f'))}/{_fmt(r.get('delta_i'))}/{_fmt(r.get('delta_r'))}"
        lines.append(
            f"| {r.get('ion','')} | {_fmt(r.get('xstar_temperature_K'))} | {_fmt(r.get('xstar_electron_density_cm^-3'))} | {_fmt(r.get('xstar_log_xi_local'))} | {solver} | {target} | {delta} | {_fmt(r.get('solver_R'))} | {_fmt(r.get('solver_G'))} | {_fmt(r.get('l2'))} | {r.get('residual_pattern','')} |"
        )
    # Systematic diagnostics.
    rows_with = [r for r in rows if r.get("delta_f") is not None]
    high_f = sum(1 for r in rows_with if (r.get("delta_f") or 0) > 0)
    low_r = sum(1 for r in rows_with if (r.get("delta_r") or 0) < 0)
    lines.append("\n## Diagnostic interpretation\n")
    lines.append(f"- Cases with solver f above target: `{high_f}/{len(rows_with)}`")
    lines.append(f"- Cases with solver r below target: `{low_r}/{len(rows_with)}`")
    if rows_with and high_f == len(rows_with) and low_r == len(rows_with):
        lines.append("- Common residual: solver forbidden fraction is too high and resonance fraction is too low for every ion in this local-state comparison.")
        lines.append("- This points first to direct ground/resonance feeding and radiation/line-pumping normalization, rather than ion-specific empirical triplet scaling.")
    lines.append("\n## Next source-code checks\n")
    lines.append("1. Tie the local radiation field normalization to the selected XSTAR zone instead of the current diagnostic `xstar-powerlaw`/`radiation-bremsa-scale` proxy.")
    lines.append("2. Audit direct ground-to-`1s2p 1P1` feed terms and photoexcitation/line pumping against `ucalc.f90` and `calc_emis_ion.f90`.")
    lines.append("3. Compare row-level type-56/type-63/type-68/type-69 rates only after the radiation normalization is aligned.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases-csv", required=True, help="helike_local_state_cases.csv from example 51")
    p.add_argument("--solver-root", default=".", help="Root containing solver output directories")
    p.add_argument("--out-dir", default="helike_local_state_comparison_summary")
    p.add_argument("--print-summary", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    rows = summarize(Path(args.cases_csv), Path(args.solver_root))
    out = Path(args.out_dir)
    write_csv(out / "helike_local_state_comparison_summary.csv", rows)
    write_md(out / "helike_local_state_comparison_summary.md", rows)
    summary = {
        "n_cases": len(rows),
        "n_with_comparison": sum(1 for r in rows if r.get("l2") is not None),
        "n_solver_f_high": sum(1 for r in rows if (r.get("delta_f") or 0) > 0),
        "n_solver_r_low": sum(1 for r in rows if (r.get("delta_r") or 0) < 0),
    }
    (out / "helike_local_state_comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.print_summary:
        print("He-like local-state comparison summary")
        print("----------------------------------------")
        for k, v in summary.items():
            print(f"{k}={v}")
        print(f"wrote: {out/'helike_local_state_comparison_summary.csv'}")
        print(f"wrote: {out/'helike_local_state_comparison_summary.md'}")


if __name__ == "__main__":
    main()
