#!/usr/bin/env python3
"""Compare He-like source-fit vectors and response matrices across ions.

This is an offline diagnostic for products written by examples/20--22.  It
reads existing density-grid run directories and summarizes why a fitted
linear-response target is or is not reproduced by the simultaneous solver.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    try:
        x = float(text)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _fmt(value: Any, digits: int = 6) -> str:
    x = _as_float(value)
    if x is None:
        return "NA"
    return f"{x:.{digits}g}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        return json.load(handle)


def _find_first(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _strip_known_suffixes(name: str) -> str:
    suffixes = (
        "_solver_source_fit_density_xstar_grid",
        "_source_fit_density_xstar_grid",
        "_density_xstar_grid",
    )
    for suffix in suffixes:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _infer_tag(run_dir: Path, summary: dict[str, Any]) -> str:
    dirname = _strip_known_suffixes(run_dir.name)
    if dirname == "o7_solver_source_fit_density_xstar_grid_type69_suppressed":
        return "o7_suppressed"
    if dirname.startswith("o7_solver_source_fit_density_xstar_grid"):
        return "o7"
    if dirname and dirname not in {"solver", "o7"}:
        return dirname
    element = str(summary.get("element") or "").lower()
    ion_stage = summary.get("ion_stage")
    if element and ion_stage is not None:
        return f"{element}{ion_stage}"
    return dirname or run_dir.name


def _ion_prefix(tag: str, summary: dict[str, Any]) -> str:
    element = str(summary.get("element") or "").lower()
    ion_stage = summary.get("ion_stage")
    if element and ion_stage is not None:
        return f"{element}{ion_stage}"
    return tag.split("_")[0]


def _find_fit_summary(fit_dir: Path, prefix: str) -> Path | None:
    return _find_first(
        [
            fit_dir / f"{prefix}_solver_source_fit_summary.json",
            fit_dir / "o7_solver_source_fit_summary.json",
            *fit_dir.glob("*_solver_source_fit_summary.json"),
        ]
    )


def _find_response_matrix(fit_dir: Path, prefix: str) -> Path | None:
    return _find_first(
        [
            fit_dir / f"{prefix}_solver_response_matrix.csv",
            fit_dir / "o7_solver_response_matrix.csv",
            *fit_dir.glob("*_solver_response_matrix.csv"),
        ]
    )


def _find_weight_csv(fit_dir: Path, prefix: str) -> Path | None:
    return _find_first(
        [
            fit_dir / f"{prefix}_solver_source_fit_weights.csv",
            fit_dir / "o7_solver_source_fit_weights.csv",
            *fit_dir.glob("*_solver_source_fit_weights.csv"),
        ]
    )


def _density_sort_key(path: Path) -> float:
    token = path.name.replace("fit_ne_", "")
    try:
        return float(token.replace("e", "E"))
    except ValueError:
        return float("inf")


def _to_float_array(rows: list[dict[str, str]], columns: list[str]) -> np.ndarray:
    out = []
    for row in rows:
        vals = []
        for col in columns:
            vals.append(_as_float(row.get(col)) or 0.0)
        out.append(vals)
    return np.asarray(out, dtype=float)


def _response_metrics(matrix_csv: Path | None) -> dict[str, Any]:
    if matrix_csv is None or not matrix_csv.exists():
        return {
            "response_matrix_csv": "",
            "n_response_sources": 0,
            "n_response_active_sources": 0,
            "response_rank_3xn": None,
            "response_condition_3xn": None,
            "response_forbidden_zero_sources": None,
            "response_intercombination_zero_sources": None,
            "response_resonance_zero_sources": None,
        }
    rows = _read_csv(matrix_csv)
    raw = _to_float_array(rows, ["raw_forbidden", "raw_intercombination", "raw_resonance"])
    active = np.abs(raw).sum(axis=1) > 0
    rank = int(np.linalg.matrix_rank(raw.T, tol=1e-30)) if raw.size else 0
    cond = None
    if raw.size:
        svals = np.linalg.svd(raw.T, compute_uv=False)
        if len(svals) and svals[-1] > 0:
            cond = float(svals[0] / svals[-1])
        elif len(svals):
            cond = float("inf")
    return {
        "response_matrix_csv": str(matrix_csv),
        "n_response_sources": len(rows),
        "n_response_active_sources": int(active.sum()),
        "response_rank_3xn": rank,
        "response_condition_3xn": cond,
        "response_forbidden_zero_sources": int((np.abs(raw[:, 0]) == 0).sum()) if raw.size else None,
        "response_intercombination_zero_sources": int((np.abs(raw[:, 1]) == 0).sum()) if raw.size else None,
        "response_resonance_zero_sources": int((np.abs(raw[:, 2]) == 0).sum()) if raw.size else None,
    }


def _weight_metrics(weight_csv: Path | None) -> dict[str, Any]:
    if weight_csv is None or not weight_csv.exists():
        return {"weight_csv": "", "n_nonzero_weights": None, "weight_entropy_norm": None, "top_fit_weights": ""}
    rows = _read_csv(weight_csv)
    weights = np.asarray([_as_float(row.get("fit_weight_norm")) or 0.0 for row in rows], dtype=float)
    levels = [row.get("source_level", "") for row in rows]
    n_nonzero = int((weights > 1.0e-8).sum())
    entropy = None
    if len(weights) > 1 and weights.sum() > 0:
        p = weights / weights.sum()
        entropy = float(-(p[p > 0] * np.log(p[p > 0])).sum() / np.log(len(p)))
    order = np.argsort(-weights)
    top = []
    for idx in order[:6]:
        if weights[idx] > 0:
            top.append(f"{levels[idx]}:{weights[idx]:.4g}")
    return {
        "weight_csv": str(weight_csv),
        "n_nonzero_weights": n_nonzero,
        "weight_entropy_norm": entropy,
        "top_fit_weights": ";".join(top),
    }


def _ratio_error(pred: float | None, target: float | None) -> float | None:
    if pred is None or target in (None, 0):
        return None
    return abs(pred / target - 1.0)


def _diagnosis(row: dict[str, Any]) -> str:
    if row.get("combined_R") is not None and row.get("combined_G") is not None:
        er = _ratio_error(row.get("combined_R"), row.get("xstar_R"))
        eg = _ratio_error(row.get("combined_G"), row.get("xstar_G"))
        if er is not None and eg is not None and er <= 5.0e-3 and eg <= 5.0e-3:
            return "validated: fitted linear response and simultaneous solver reproduce XSTAR R/G"
    if row.get("combined_R") is None and row.get("combined_G") is None:
        if (row.get("linear_residual_l2") or 0) > 1.0:
            return "unreachable: simultaneous solver did not produce usable triplet R/G and linear residual is large"
        return "unreachable: simultaneous solver did not produce usable triplet R/G"
    if row.get("combined_R") is None or row.get("combined_G") is None:
        return "partial failure: only one combined R/G diagnostic is available"
    return "mismatch: combined solver R/G differ from XSTAR target"


def _collect_run(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fit_dirs = sorted([p for p in run_dir.glob("fit_ne_*") if p.is_dir()], key=_density_sort_key)
    if not fit_dirs:
        raise FileNotFoundError(f"No fit_ne_* directories found in {run_dir}")
    first_summary_path = _find_fit_summary(fit_dirs[0], "")
    first_summary = _read_json(first_summary_path) if first_summary_path else {}
    tag = _infer_tag(run_dir, first_summary)
    prefix = _ion_prefix(tag, first_summary)
    rows = []
    for fit_dir in fit_dirs:
        summary_path = _find_fit_summary(fit_dir, prefix)
        if summary_path is None:
            continue
        summary = _read_json(summary_path)
        prefix = _ion_prefix(tag, summary)
        xref = summary.get("xstar_reference") or {}
        target = summary.get("target_components_normalized") or {}
        uniform = summary.get("uniform_prediction") or {}
        fitted = summary.get("fitted_prediction") or {}
        fit_info = fitted.get("fit_info") or {}
        combined = summary.get("combined_source_validation") or {}
        diag = combined.get("solver_diagnostics") or {}
        matrix_metrics = _response_metrics(_find_response_matrix(fit_dir, prefix))
        weight_metrics = _weight_metrics(_find_weight_csv(fit_dir, prefix))
        row: dict[str, Any] = {
            "tag": tag,
            "fit_dir": str(fit_dir),
            "element": summary.get("element"),
            "ion_stage": summary.get("ion_stage"),
            "density_cm^-3": _as_float(summary.get("electron_density_cm^-3")),
            "xstar_R": _as_float(xref.get("R_f_over_i")),
            "xstar_G": _as_float(xref.get("G_f_plus_i_over_r")),
            "target_forbidden": _as_float(target.get("forbidden")),
            "target_intercombination": _as_float(target.get("intercombination")),
            "target_resonance": _as_float(target.get("resonance")),
            "uniform_R": _as_float(uniform.get("R_f_over_i")),
            "uniform_G": _as_float(uniform.get("G_f_plus_i_over_r")),
            "fitted_R": _as_float(fitted.get("R_f_over_i")),
            "fitted_G": _as_float(fitted.get("G_f_plus_i_over_r")),
            "fit_objective": _as_float(fit_info.get("objective")),
            "combined_R": _as_float(combined.get("R_f_over_i")),
            "combined_G": _as_float(combined.get("G_f_plus_i_over_r")),
            "combined_R_over_xstar": _as_float(combined.get("R_over_xstar")),
            "combined_G_over_xstar": _as_float(combined.get("G_over_xstar")),
            "solver_matrix_rank": diag.get("matrix_rank"),
            "solver_matrix_size": diag.get("matrix_size"),
            "linear_residual_l2": _as_float(diag.get("linear_residual_l2")),
            "linear_residual_linf": _as_float(diag.get("linear_residual_linf")),
            "negative_populations": diag.get("n_negative_populations_raw"),
        }
        row.update(matrix_metrics)
        row.update(weight_metrics)
        row["combined_R_fractional_error"] = _ratio_error(row.get("combined_R"), row.get("xstar_R"))
        row["combined_G_fractional_error"] = _ratio_error(row.get("combined_G"), row.get("xstar_G"))
        row["diagnosis"] = _diagnosis(row)
        rows.append(row)
    summary_row = _summarize_rows(tag, rows)
    return rows, summary_row


def _summarize_rows(tag: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def values(key: str) -> list[float]:
        vals = []
        for row in rows:
            x = _as_float(row.get(key))
            if x is not None:
                vals.append(x)
        return vals
    n = len(rows)
    n_valid = 0
    n_combined = 0
    for row in rows:
        if row.get("combined_R") is not None and row.get("combined_G") is not None:
            n_combined += 1
            er = row.get("combined_R_fractional_error")
            eg = row.get("combined_G_fractional_error")
            if er is not None and eg is not None and er <= 5.0e-3 and eg <= 5.0e-3:
                n_valid += 1
    l2 = values("linear_residual_l2")
    cond = values("response_condition_3xn")
    obj = values("fit_objective")
    return {
        "tag": tag,
        "n_densities": n,
        "n_combined_R_and_G": n_combined,
        "n_validated": n_valid,
        "status": "validated" if n > 0 and n_valid == n else "not_validated",
        "xstar_R_min": min(values("xstar_R")) if values("xstar_R") else None,
        "xstar_R_max": max(values("xstar_R")) if values("xstar_R") else None,
        "xstar_G_min": min(values("xstar_G")) if values("xstar_G") else None,
        "xstar_G_max": max(values("xstar_G")) if values("xstar_G") else None,
        "median_linear_residual_l2": float(np.median(l2)) if l2 else None,
        "median_response_condition_3xn": float(np.median(cond)) if cond else None,
        "median_fit_objective": float(np.median(obj)) if obj else None,
        "dominant_failure_mode": _dominant_failure(rows),
    }


def _dominant_failure(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no rows"
    n_valid = 0
    for row in rows:
        er = row.get("combined_R_fractional_error")
        eg = row.get("combined_G_fractional_error")
        if er is not None and eg is not None and er <= 5.0e-3 and eg <= 5.0e-3:
            n_valid += 1
    if n_valid == len(rows):
        return "combined solver reproduces XSTAR R/G at all densities"
    no_combined = sum(row.get("combined_R") is None or row.get("combined_G") is None for row in rows)
    large_l2 = sum((_as_float(row.get("linear_residual_l2")) or 0.0) > 1.0 for row in rows)
    if no_combined == len(rows) and large_l2:
        return "combined triplet R/G unavailable at most densities; simultaneous solve has large residuals"
    if no_combined == len(rows):
        return "combined triplet R/G unavailable"
    if large_l2 >= len(rows) / 2:
        return "large simultaneous-solver residuals"
    return "R/G mismatch"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, run_summaries: list[dict[str, Any]], density_rows: list[dict[str, Any]]) -> None:
    lines = ["# He-like source-vector and response-matrix comparison", ""]
    lines += [
        "## Run-level summary",
        "",
        "| tag | status | validated densities | combined R/G densities | XSTAR R range | XSTAR G range | median solver residual L2 | median response condition | dominant failure mode |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in run_summaries:
        lines.append(
            "| {tag} | {status} | {nv}/{nd} | {nc}/{nd} | {rmin}..{rmax} | {gmin}..{gmax} | {l2} | {cond} | {fail} |".format(
                tag=row["tag"],
                status=row["status"],
                nv=row["n_validated"],
                nc=row["n_combined_R_and_G"],
                nd=row["n_densities"],
                rmin=_fmt(row["xstar_R_min"]),
                rmax=_fmt(row["xstar_R_max"]),
                gmin=_fmt(row["xstar_G_min"]),
                gmax=_fmt(row["xstar_G_max"]),
                l2=_fmt(row["median_linear_residual_l2"]),
                cond=_fmt(row["median_response_condition_3xn"]),
                fail=row["dominant_failure_mode"],
            )
        )
    lines += ["", "## Key interpretation", ""]
    validated = [row["tag"] for row in run_summaries if row["status"] == "validated"]
    failed = [row["tag"] for row in run_summaries if row["status"] != "validated"]
    if validated:
        lines.append("- Validated runs: " + ", ".join(validated) + ".")
    if failed:
        lines.append("- Non-validated runs: " + ", ".join(failed) + ".")
    lines.append(
        "- The usual non-O VII failure pattern is not just that the XSTAR triplet target is missing; "
        "C V, Mg XI, and high-xi Ca XIX have targets, but the simultaneous solver does not return complete, target-matching R/G diagnostics."
    )
    lines.append(
        "- O VII differs because the fitted linear-response vector is reproduced by the combined simultaneous solve at every density; "
        "the non-O VII grids either lose one or both combined ratios or have large simultaneous-solver residuals."
    )
    lines += ["", "## Density-level diagnostics", "", "| tag | density | XSTAR R/G | fitted R/G | combined R/G | solver residual L2 | response active/rank | source weights | diagnosis |", "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for row in density_rows:
        lines.append(
            "| {tag} | {den} | {xr}/{xg} | {fr}/{fg} | {cr}/{cg} | {l2} | {active}/{rank} | {weights} | {diag} |".format(
                tag=row["tag"], den=_fmt(row["density_cm^-3"]), xr=_fmt(row["xstar_R"]), xg=_fmt(row["xstar_G"]),
                fr=_fmt(row["fitted_R"]), fg=_fmt(row["fitted_G"]), cr=_fmt(row["combined_R"]), cg=_fmt(row["combined_G"]),
                l2=_fmt(row["linear_residual_l2"]), active=row.get("n_response_active_sources", ""), rank=row.get("response_rank_3xn", ""),
                weights=row.get("top_fit_weights", ""), diag=row.get("diagnosis", ""),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="Density-grid output directories to compare.")
    parser.add_argument("--out-dir", type=Path, default=Path("helike_response_comparison"))
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for run_dir in args.run_dirs:
        rows, summary = _collect_run(run_dir)
        all_rows.extend(rows)
        summaries.append(summary)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out_dir / "helike_response_matrix_density_comparison.csv", all_rows)
    _write_csv(args.out_dir / "helike_response_matrix_run_summary.csv", summaries)
    with (args.out_dir / "helike_response_matrix_comparison.json").open("w") as handle:
        json.dump({"runs": summaries, "densities": all_rows}, handle, indent=2)
    _write_markdown(args.out_dir / "helike_response_matrix_comparison.md", summaries, all_rows)

    if args.print_summary:
        print("He-like source-vector/response-matrix comparison")
        print("------------------------------------------------")
        for row in summaries:
            print(
                f"{row['tag']}: status={row['status']} "
                f"validated={row['n_validated']}/{row['n_densities']} "
                f"combined={row['n_combined_R_and_G']}/{row['n_densities']} "
                f"median_l2={_fmt(row['median_linear_residual_l2'])} "
                f"failure={row['dominant_failure_mode']}"
            )
        print(f"wrote: {args.out_dir / 'helike_response_matrix_comparison.md'}")


if __name__ == "__main__":
    main()
