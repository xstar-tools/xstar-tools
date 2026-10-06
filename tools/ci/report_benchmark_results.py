#!/usr/bin/env python3
"""Create Tier-3/performance reports grouped by physical regime and backend."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _density_exponent(name: str) -> int | None:
    match = re.search(r"_ne1(?:e(\d+))?(?:$|_)", name)
    if not match:
        return None
    return int(match.group(1) or 0)


def _density_regime(exp: int | None) -> str:
    if exp is None:
        return "unknown"
    if exp <= 4:
        return "low-ne<=1e4"
    if exp <= 8:
        return "mid-ne1e8"
    return "high-ne>=1e10"


def _xi_value(name: str) -> float | None:
    match = re.search(r"_xi(\d+)(?:p(\d+))?", name)
    if not match:
        return None
    whole = float(match.group(1))
    frac = match.group(2)
    return whole + (float("0." + frac) if frac else 0.0)


def _ionization_regime(xi: float | None) -> str:
    if xi is None:
        return "baseline"
    if xi < 2.0:
        return "low-xi"
    if xi < 3.0:
        return "mid-xi"
    return "high-xi"


def _element(name: str) -> str:
    leaf = name.split("/")[-1].lower()
    for prefix, symbol in (("ca", "Ca"), ("mg", "Mg"), ("o", "O"), ("c", "C")):
        if leaf.startswith(prefix):
            return symbol
    return "other"


def classify_case(case: str) -> dict[str, Any]:
    leaf = case.split("/")[-1]
    exp = _density_exponent(leaf)
    xi = _xi_value(leaf)
    return {
        "element": _element(case),
        "density_exponent": exp,
        "density_regime": _density_regime(exp),
        "ionization_log10_xi": xi,
        "ionization_regime": _ionization_regime(xi),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_report(run_manifest: Path, model_summary: Path | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs = _read_csv(run_manifest)
    science: dict[tuple[str, str], dict[str, str]] = {}
    if model_summary and model_summary.is_file():
        for row in _read_csv(model_summary):
            science[(row.get("mode", ""), row.get("case", ""))] = row
    detailed: list[dict[str, Any]] = []
    for row in runs:
        case = row["case"]
        mode = row["mode"]
        physical = classify_case(case)
        srow = science.get((mode, case), {})
        detailed.append({
            "case": case,
            "element": physical["element"],
            "density_regime": physical["density_regime"],
            "density_exponent": physical["density_exponent"],
            "ionization_regime": physical["ionization_regime"],
            "ionization_log10_xi": physical["ionization_log10_xi"],
            "backend": mode,
            "wall_seconds": float(row.get("wall_seconds") or 0.0),
            "run_accept": str(row.get("accept", "")).lower() in {"1", "true", "yes"},
            "science_accept": str(srow.get("science_gate", "")).lower() in {"1", "true", "yes"} if srow else None,
            "max_surface_nl1": float(srow.get("max_surface_nl1") or 0.0) if srow else None,
        })
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in detailed:
        key = (row["element"], row["density_regime"], row["ionization_regime"], row["backend"])
        groups[key].append(row)
    grouped: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        times = [float(r["wall_seconds"]) for r in rows]
        science_values = [r["science_accept"] for r in rows if r["science_accept"] is not None]
        nl1 = [float(r["max_surface_nl1"]) for r in rows if r["max_surface_nl1"] is not None]
        grouped.append({
            "element": key[0], "density_regime": key[1], "ionization_regime": key[2], "backend": key[3],
            "models": len(rows), "run_accept": sum(bool(r["run_accept"]) for r in rows),
            "science_accept": sum(bool(v) for v in science_values) if science_values else "",
            "mean_wall_seconds": mean(times) if times else 0.0,
            "median_wall_seconds": median(times) if times else 0.0,
            "min_wall_seconds": min(times) if times else 0.0,
            "max_wall_seconds": max(times) if times else 0.0,
            "max_surface_nl1": max(nl1) if nl1 else "",
        })
    return detailed, grouped


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-manifest", required=True)
    p.add_argument("--model-summary")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    detailed, grouped = build_report(Path(args.run_manifest), Path(args.model_summary) if args.model_summary else None)
    _write_csv(out / "benchmark_by_model.csv", detailed)
    _write_csv(out / "benchmark_by_regime.csv", grouped)
    summary = {
        "schema": "xstar-tools-ci-regime-report-v1",
        "model_rows": len(detailed),
        "group_rows": len(grouped),
        "dimensions": ["element", "density_regime", "ionization_regime", "backend"],
        "global_average_is_release_gate": False,
    }
    (out / "benchmark_report.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print("CI_BENCHMARK_REGIME_REPORT=ACCEPT")
    print(f"CI_BENCHMARK_MODEL_ROWS={len(detailed)}")
    print(f"CI_BENCHMARK_GROUP_ROWS={len(grouped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
