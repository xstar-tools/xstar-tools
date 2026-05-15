#!/usr/bin/env python3
"""Scan controlled record-level ucalc matrix replay one family at a time.

This diagnostic separates topology/rate blockers by replaying one selected
record-level family at a time.  It is intended after a v0.3.183+ record-level
matrix-parity audit and before native source-code ports of the discrepant
families.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from xstar_atomic.xstar_record_level_replay import (
    audit_record_level_ucalc_matrix_replay,
    write_record_level_ucalc_matrix_replay_audit,
)


def _read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _resolve_family_summary(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        p = p / "xstar_record_level_matrix_parity_audit_family_summary.csv"
    if not p.exists():
        raise FileNotFoundError(f"record-level family summary CSV not found: {p}")
    return p


def _resolve_records(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        p = p / "xstar_record_level_matrix_parity_audit_records.csv"
    if not p.exists():
        raise FileNotFoundError(f"record-level records CSV not found: {p}")
    return p


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        return f
    except Exception:
        return default


def _selected_families(record_level_audit: str | Path, include: List[str], exclude: List[str]) -> List[str]:
    fam_csv = _resolve_family_summary(record_level_audit)
    rows = _read_csv_rows(fam_csv)
    families = []
    for row in rows:
        fam = str(row.get("family_key") or "").strip()
        if not fam:
            continue
        text = " ".join(str(v) for v in row.values()).lower()
        if include and not any(tok.lower() in fam.lower() or tok.lower() in text for tok in include):
            continue
        if exclude and any(tok.lower() in fam.lower() or tok.lower() in text for tok in exclude):
            continue
        families.append(fam)
    return families


def _solve_summary(audit: Dict[str, Any], case: str) -> Dict[str, Any]:
    for row in audit.get("solve_comparison_rows", []) or []:
        if str(row.get("comparison_case") or "") == case:
            return dict(row)
    return {}


def _scan(
    *,
    benchmark_dir: str,
    ion: str,
    record_level_audit_csv: str,
    families: List[str],
    run_solver: bool,
    linear_solver: str,
    rank_deficient_action: str,
    negative_population_action: str,
    prune_null_rate_levels: bool,
    full_global_topology: str,
    ion_fraction_closure: str,
    out_dir: str | Path,
    write_family_audits: bool,
) -> Dict[str, Any]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for idx, fam in enumerate(families, start=1):
        audit = audit_record_level_ucalc_matrix_replay(
            benchmark_dir=benchmark_dir,
            ion=ion,
            record_level_audit_csv=record_level_audit_csv,
            replacement_mode="families",
            families=[fam],
            run_solver=run_solver,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
            prune_null_rate_levels=prune_null_rate_levels,
            full_global_topology=full_global_topology,
            ion_fraction_closure=ion_fraction_closure,
        )
        if write_family_audits:
            safe = "".join(c if c.isalnum() else "_" for c in fam)[:120]
            write_record_level_ucalc_matrix_replay_audit(audit, out / f"family_{idx:02d}_{safe}")
        summary = dict(audit.get("summary", {}) or {})
        family_rows = list(audit.get("family_rows", []) or [])
        orig = _solve_summary(audit, "original_matrix")
        repl = _solve_summary(audit, "record_level_ucalc_replay")
        row: Dict[str, Any] = {
            "scan_index": idx,
            "family_selector": fam,
            "status": summary.get("status"),
            "n_replayed_terms": summary.get("n_replayed_terms"),
            "n_replayed_families": summary.get("n_replayed_families"),
            "median_old_over_new": summary.get("median_old_over_new"),
            "p16_old_over_new": summary.get("p16_old_over_new"),
            "p84_old_over_new": summary.get("p84_old_over_new"),
            "run_solver": summary.get("run_solver"),
            "solve_status": summary.get("solve_status"),
        }
        if family_rows:
            fr = family_rows[0]
            row.update({
                "family_key": fr.get("family_key"),
                "family_branch_counts": fr.get("branch_counts"),
                "family_min_old_over_new": fr.get("min_old_over_new"),
                "family_max_old_over_new": fr.get("max_old_over_new"),
            })
        for prefix, sr in [("original", orig), ("replay", repl)]:
            for key in [
                "triplet_population_f_fraction", "triplet_population_i_fraction",
                "triplet_population_r_fraction", "triplet_population_R", "triplet_population_G",
                "triplet_population_total", "sum_population", "n_negative_populations",
                "line_triplet_status",
            ]:
                row[f"{prefix}_{key}"] = sr.get(key, "")
        # Differences are useful for ranking family influence.
        for key in ["triplet_population_f_fraction", "triplet_population_i_fraction", "triplet_population_r_fraction"]:
            a = _as_float(orig.get(key), None)
            b = _as_float(repl.get(key), None)
            row[f"delta_{key}"] = "" if a is None or b is None else b - a
        rows.append(row)
    return {"summary_rows": rows}


def _write_outputs(result: Dict[str, Any], out_dir: str | Path, *, ion: str, families: List[str], run_solver: bool) -> Dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rows = result.get("summary_rows", []) or []
    fields: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    csv_path = out / "xstar_record_level_ucalc_replay_family_scan.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    summary = {
        "audit_version": "v0.3.186",
        "ion": ion,
        "status": "record_level_ucalc_replay_family_scan_completed",
        "n_families_scanned": len(rows),
        "run_solver": bool(run_solver),
        "families": families,
    }
    json_path = out / "xstar_record_level_ucalc_replay_family_scan.json"
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str), encoding="utf-8")
    md_path = out / "xstar_record_level_ucalc_replay_family_scan.md"
    lines = [
        "# XSTAR record-level ucalc replay family scan",
        "",
        f"audit_version: `{summary['audit_version']}`",
        f"ion: `{ion}`",
        f"n_families_scanned: `{len(rows)}`",
        f"run_solver: `{run_solver}`",
        "",
        "| family | n terms | median old/new | replay pop f | replay pop i | replay pop r |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('family_key') or row.get('family_selector')} | {row.get('n_replayed_terms')} | "
            f"{row.get('median_old_over_new')} | {row.get('replay_triplet_population_f_fraction')} | "
            f"{row.get('replay_triplet_population_i_fraction')} | {row.get('replay_triplet_population_r_fraction')} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"family_scan_csv": str(csv_path), "json": str(json_path), "markdown": str(md_path)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark-dir", required=True)
    p.add_argument("--ion", default="O VII")
    p.add_argument("--record-level-audit-csv", required=True, help="v0.3.183+ record-level parity audit directory or records CSV")
    p.add_argument("--include-family", action="append", default=[], help="Substring to include; may be repeated. Default scans all families in the record-level family summary.")
    p.add_argument("--exclude-family", action="append", default=[], help="Substring to exclude; may be repeated.")
    p.add_argument("--families", default="", help="Comma-separated explicit family selectors; overrides --include-family.")
    p.add_argument("--run-solver", action="store_true")
    p.add_argument("--linear-solver", default="xstar-lucy", choices=["solve", "dense", "lstsq", "svd", "xstar-lucy"])
    p.add_argument("--rank-deficient-action", default="svd")
    p.add_argument("--negative-population-action", default="keep")
    p.add_argument("--no-prune-null-rate-levels", action="store_true")
    p.add_argument("--full-global-topology", default="xstar-continuum-alias-superlevels")
    p.add_argument("--ion-fraction-closure", default="xstar-calc-ion-rates")
    p.add_argument("--write-family-audits", action="store_true")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    explicit = [s.strip() for s in args.families.split(",") if s.strip()]
    families = explicit or _selected_families(args.record_level_audit_csv, args.include_family, args.exclude_family)
    if not families:
        raise SystemExit("no families selected for replay scan")
    result = _scan(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        record_level_audit_csv=str(_resolve_records(args.record_level_audit_csv)),
        families=families,
        run_solver=args.run_solver,
        linear_solver=args.linear_solver,
        rank_deficient_action=args.rank_deficient_action,
        negative_population_action=args.negative_population_action,
        prune_null_rate_levels=not args.no_prune_null_rate_levels,
        full_global_topology=args.full_global_topology,
        ion_fraction_closure=args.ion_fraction_closure,
        out_dir=args.out_dir,
        write_family_audits=args.write_family_audits,
    )
    paths = _write_outputs(result, args.out_dir, ion=args.ion, families=families, run_solver=args.run_solver)
    if args.print_summary:
        print("XSTAR record-level ucalc replay family scan")
        print("------------------------------------------------")
        print("audit_version=v0.3.186")
        print(f"ion={args.ion}")
        print(f"n_families_scanned={len(result.get('summary_rows', []))}")
        print(f"run_solver={bool(args.run_solver)}")
        for row in result.get("summary_rows", []):
            print(
                "family={family} n_terms={n} median_old_over_new={med} "
                "replay_pop_f/i/r={f}/{i}/{r}".format(
                    family=row.get("family_key") or row.get("family_selector"),
                    n=row.get("n_replayed_terms"),
                    med=row.get("median_old_over_new"),
                    f=row.get("replay_triplet_population_f_fraction"),
                    i=row.get("replay_triplet_population_i_fraction"),
                    r=row.get("replay_triplet_population_r_fraction"),
                )
            )
        for k, v in paths.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
