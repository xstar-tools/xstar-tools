#!/usr/bin/env python3
"""Summarize He-like density-grid validation outputs across ions.

This utility is intentionally light-weight: it reads the CSV/JSON products from
``examples/21``/``examples/22`` runs and optional ``examples/33`` line-audit
folders.  It does not rerun XSTAR or the atomic solver.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    try:
        x = float(text)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _fmt(value: Any, *, digits: int = 6) -> str:
    x = _as_float(value)
    if x is None:
        return "NA"
    return f"{x:.{digits}g}"


def _find_first(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        return json.load(handle)


def _infer_tag_from_dir(path: Path, summary: dict[str, Any]) -> str:
    element = str(summary.get("element") or "").lower()
    ion_stage = summary.get("ion_stage")
    if element and ion_stage is not None:
        return f"{element}{ion_stage}"
    name = path.name
    return name.replace("_solver_source_fit_density_xstar_grid", "")


def _ratio_range(rows: list[dict[str, str]], column: str) -> tuple[float | None, float | None]:
    vals = [_as_float(row.get(column)) for row in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None
    return min(vals), max(vals)


def _count_nonnull(rows: list[dict[str, str]], column: str) -> int:
    return sum(_as_float(row.get(column)) is not None for row in rows)


def summarize_run_dir(run_dir: Path) -> dict[str, Any]:
    csv_path = _find_first(
        [
            *run_dir.glob("*_solver_source_fit_density_grid.csv"),
            run_dir / "o7_solver_source_fit_density_grid.csv",
        ]
    )
    json_path = _find_first(
        [
            *run_dir.glob("*_solver_source_fit_density_grid_summary.json"),
            run_dir / "o7_solver_source_fit_density_grid_summary.json",
        ]
    )
    if csv_path is None:
        raise FileNotFoundError(f"No density-grid CSV found in {run_dir}")
    rows = _read_csv_rows(csv_path)
    summary = _read_json(json_path) if json_path is not None else {}
    tag = _infer_tag_from_dir(run_dir, summary)
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    xstar_r_min, xstar_r_max = _ratio_range(rows, "xstar_R_f_over_i")
    xstar_g_min, xstar_g_max = _ratio_range(rows, "xstar_G_f_plus_i_over_r")
    combo_r_min, combo_r_max = _ratio_range(rows, "refitted_combined_R_f_over_i")
    combo_g_min, combo_g_max = _ratio_range(rows, "refitted_combined_G_f_plus_i_over_r")
    linear_r_min, linear_r_max = _ratio_range(rows, "refitted_linear_R_f_over_i")
    linear_g_min, linear_g_max = _ratio_range(rows, "refitted_linear_G_f_plus_i_over_r")
    reachable = sum(_as_bool(row.get("target_reachable")) for row in rows)
    complete_xstar = sum(
        _as_float(row.get("xstar_R_f_over_i")) is not None
        and _as_float(row.get("xstar_G_f_plus_i_over_r")) is not None
        for row in rows
    )
    status = "validated" if rows and reachable == len(rows) else "not_validated"
    if complete_xstar == 0:
        status = "no_xstar_triplet_target"
    return {
        "tag": tag,
        "run_dir": str(run_dir),
        "density_csv": str(csv_path),
        "summary_json": str(json_path) if json_path else "",
        "element": summary.get("element", ""),
        "ion_stage": summary.get("ion_stage", ""),
        "temperature_K": summary.get("temperature_K", ""),
        "n_densities": len(rows),
        "n_complete_xstar_targets": complete_xstar,
        "n_reachable": reachable,
        "status": status,
        "xstar_R_min": xstar_r_min,
        "xstar_R_max": xstar_r_max,
        "xstar_G_min": xstar_g_min,
        "xstar_G_max": xstar_g_max,
        "combined_R_min": combo_r_min,
        "combined_R_max": combo_r_max,
        "combined_G_min": combo_g_min,
        "combined_G_max": combo_g_max,
        "linear_R_nonnull": _count_nonnull(rows, "refitted_linear_R_f_over_i"),
        "linear_G_nonnull": _count_nonnull(rows, "refitted_linear_G_f_plus_i_over_r"),
        "combined_R_nonnull": _count_nonnull(rows, "refitted_combined_R_f_over_i"),
        "combined_G_nonnull": _count_nonnull(rows, "refitted_combined_G_f_plus_i_over_r"),
        "n_warnings": len(warnings),
        "first_warning": warnings[0] if warnings else "",
    }


def summarize_audit_dir(audit_dir: Path) -> dict[str, Any]:
    summary_path = _find_first([audit_dir / "summary.json", *audit_dir.glob("*summary*.json")])
    if summary_path is None:
        raise FileNotFoundError(f"No line-audit summary JSON found in {audit_dir}")
    data = _read_json(summary_path)
    summary = data.get("summary", data)
    expected = str(summary.get("expected_ion", "")).replace(" ", "_").lower()
    return {
        "audit_dir": str(audit_dir),
        "summary_json": str(summary_path),
        "expected_ion": summary.get("expected_ion", ""),
        "tag": expected,
        "n_all_lines": summary.get("n_all_lines", ""),
        "n_expected_ion_rows_any_wavelength": summary.get("n_expected_ion_rows_any_wavelength", ""),
        "n_expected_ion_rows_in_window": summary.get("n_expected_ion_rows_in_window", ""),
        "n_helike_like_rows_expected_ion": summary.get("n_helike_like_rows_expected_ion", ""),
        "has_complete_triplet_target": bool(summary.get("has_complete_triplet_target")),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, run_rows: list[dict[str, Any]], audit_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# He-like validation summary", ""]
    if run_rows:
        lines += ["## Density-grid runs", "", "| tag | status | densities | reachable | XSTAR R range | XSTAR G range | combined R values | combined G values | warnings |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for row in run_rows:
            lines.append(
                "| {tag} | {status} | {nd} | {nr} | {rmin}..{rmax} | {gmin}..{gmax} | {cr} | {cg} | {nw} |".format(
                    tag=row["tag"],
                    status=row["status"],
                    nd=row["n_densities"],
                    nr=row["n_reachable"],
                    rmin=_fmt(row["xstar_R_min"]),
                    rmax=_fmt(row["xstar_R_max"]),
                    gmin=_fmt(row["xstar_G_min"]),
                    gmax=_fmt(row["xstar_G_max"]),
                    cr=row["combined_R_nonnull"],
                    cg=row["combined_G_nonnull"],
                    nw=row["n_warnings"],
                )
            )
        lines.append("")
    if audit_rows:
        lines += ["## XSTAR line audits", "", "| expected ion | complete triplet | rows in window | He-like n=2 rows | rows any wavelength |", "|---|---:|---:|---:|---:|"]
        for row in audit_rows:
            lines.append(
                f"| {row['expected_ion']} | {row['has_complete_triplet_target']} | {row['n_expected_ion_rows_in_window']} | {row['n_helike_like_rows_expected_ion']} | {row['n_expected_ion_rows_any_wavelength']} |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="*", type=Path, help="Density-grid output directories to summarize.")
    parser.add_argument("--audit-dirs", nargs="*", type=Path, default=[], help="Optional examples/33 line-audit directories.")
    parser.add_argument("--out-dir", type=Path, default=Path("helike_validation_summary"))
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    run_rows = [summarize_run_dir(path) for path in args.run_dirs]
    audit_rows = [summarize_audit_dir(path) for path in args.audit_dirs]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "helike_density_grid_validation_summary.csv", run_rows)
    write_csv(args.out_dir / "helike_xstar_line_audit_summary.csv", audit_rows)
    with (args.out_dir / "helike_validation_summary.json").open("w") as handle:
        json.dump({"density_grid_runs": run_rows, "line_audits": audit_rows}, handle, indent=2)
    write_markdown(args.out_dir / "helike_validation_summary.md", run_rows, audit_rows)

    if args.print_summary:
        print("He-like validation summary")
        print("--------------------------")
        for row in run_rows:
            print(
                f"{row['tag']}: status={row['status']} reachable={row['n_reachable']}/{row['n_densities']} "
                f"XSTAR_R={_fmt(row['xstar_R_min'])}..{_fmt(row['xstar_R_max'])} "
                f"XSTAR_G={_fmt(row['xstar_G_min'])}..{_fmt(row['xstar_G_max'])}"
            )
        for row in audit_rows:
            print(
                f"audit {row['expected_ion']}: complete_triplet={row['has_complete_triplet_target']} "
                f"rows_in_window={row['n_expected_ion_rows_in_window']}"
            )
        print(f"wrote: {args.out_dir / 'helike_validation_summary.md'}")


if __name__ == "__main__":
    main()
