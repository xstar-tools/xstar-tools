#!/usr/bin/env python3
"""Fit absolute He-like triplet response across a density grid.

This wrapper runs ``examples/40_audit_signed_triplet_response.py`` once per
requested electron density with ``--fit-mode absolute-response`` and collects
the target/predicted f/i/r, R, G, component errors, and top source levels.

The fit uses source-injected absolute triplet emissivities rather than
baseline-subtracted signed deltas, so it avoids negative response columns that
can appear when a source level reduces the baseline triplet emissivity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


COMPONENTS = ["forbidden", "intercombination", "resonance"]


def _maybe_float(value) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _fmt(value, precision: int = 6) -> str:
    val = _maybe_float(value)
    if val is None:
        return "NA"
    return f"{val:.{precision}g}"


def density_tag(value: float) -> str:
    """Return compact density tag used by existing XSTAR test-run folders."""
    val = float(value)
    if val == 0.0:
        return "0"
    # Existing test-run folders use tags such as ne1, ne1e4, ne1e8.
    # Prefer exact power-of-ten notation when possible.
    if val > 0.0:
        log10 = math.log10(val)
        rounded = round(log10)
        if abs(log10 - rounded) < 1.0e-10:
            return f"1e{int(rounded)}" if int(rounded) != 0 else "1"
    text = f"{val:.12g}"
    if "e" in text or "E" in text:
        mant, exp = text.lower().split("e", 1)
        mant = mant.rstrip("0").rstrip(".")
        exp_i = int(exp)
        return f"{mant}e{exp_i}" if mant != "1" else f"1e{exp_i}"
    if val.is_integer():
        return str(int(val))
    return text.replace(".", "p")


def parse_float_list(text: str) -> List[float]:
    out: List[float] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(float(part))
    return out


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["warning"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_template(template: str, density: float, index: int, element: str, ion_stage: int) -> str:
    tag = density_tag(float(density))
    return str(template).format(
        ne=float(density),
        density=float(density),
        electron_density=float(density),
        ne_tag=tag,
        density_tag=tag,
        index=int(index),
        element=str(element).lower(),
        Element=str(element),
        ion_stage=int(ion_stage),
    )


def command_for_density(args, density: float, index: int, xstar_csv: str, out_dir: Path) -> List[str]:
    script = Path(__file__).resolve().with_name("40_audit_signed_triplet_response.py")
    cmd = [
        sys.executable, str(script),
    ]
    if args.fitsfile:
        cmd.append(str(args.fitsfile))
    cmd += [
        "--element", str(args.element),
        "--ion-stage", str(int(args.ion_stage)),
        "--temperature", f"{float(args.temperature):.16g}",
        "--electron-density", f"{float(density):.16g}",
        "--wavelength-min", f"{float(args.wavelength_min):.16g}",
        "--wavelength-max", f"{float(args.wavelength_max):.16g}",
        "--source-levels", str(args.source_levels),
        "--source-rate", f"{float(args.source_rate):.16g}",
        "--xstar-lines-csv", str(xstar_csv),
        "--xstar-value-column", str(args.xstar_value_column),
        "--fit-mode", "absolute-response",
        "--absolute-fit-min-triplet-sum", f"{float(args.absolute_fit_min_triplet_sum):.16g}",
        "--absolute-fit-component-weights", str(args.absolute_fit_component_weights),
        "--absolute-fit-weight-floor", f"{float(args.absolute_fit_weight_floor):.16g}",
        "--absolute-fit-constraint-mode", str(args.absolute_fit_constraint_mode),
        "--absolute-fit-target-i-factor", f"{float(args.absolute_fit_target_i_factor):.16g}",
        "--absolute-fit-target-i-floor", f"{float(args.absolute_fit_target_i_floor):.16g}",
        "--absolute-fit-low-target-i-threshold", f"{float(args.absolute_fit_low_target_i_threshold):.16g}",
        "--absolute-fit-pure-i-threshold", f"{float(args.absolute_fit_pure_i_threshold):.16g}",
        "--absolute-fit-max-intercombination-fraction", f"{float(args.absolute_fit_max_intercombination_fraction):.16g}",
        "--absolute-fit-max-forbidden-fraction", f"{float(args.absolute_fit_max_forbidden_fraction):.16g}",
        "--absolute-fit-max-resonance-fraction", f"{float(args.absolute_fit_max_resonance_fraction):.16g}",
        "--absolute-fit-min-forbidden-fraction", f"{float(args.absolute_fit_min_forbidden_fraction):.16g}",
        "--absolute-fit-min-resonance-fraction", f"{float(args.absolute_fit_min_resonance_fraction):.16g}",
        "--fit-max-iter", str(int(args.fit_max_iter)),
        "--linear-solver", str(args.linear_solver),
        "--rank-deficient-action", str(args.rank_deficient_action),
        "--negative-population-action", str(args.negative_population_action),
        "--negative-population-tol", f"{float(args.negative_population_tol):.16g}",
        "--zero-tol", f"{float(args.zero_tol):.16g}",
        "--out-dir", str(out_dir),
    ]
    if args.absolute_fit_reject_pure_i:
        cmd.append("--absolute-fit-reject-pure-i")
    if args.residual_l2_max is not None:
        cmd += ["--residual-l2-max", f"{float(args.residual_l2_max):.16g}"]
    if args.residual_linf_max is not None:
        cmd += ["--residual-linf-max", f"{float(args.residual_linf_max):.16g}"]
    if args.reject_large_residual:
        cmd.append("--reject-large-residual")
    if args.prune_null_rate_levels:
        cmd += ["--prune-null-rate-levels", "--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
    else:
        cmd.append("--no-prune-null-rate-levels")
    if args.collision_rate_scale not in (None, 1.0):
        cmd += ["--collision-rate-scale", f"{float(args.collision_rate_scale):.16g}"]
    for name in ["collision_data_type_scale", "collision_pair_scale", "collision_record_scale", "collision_record_direction_scale"]:
        flag = "--" + name.replace("_", "-")
        for spec in getattr(args, name) or []:
            cmd += [flag, str(spec)]
    if args.collision_type69_ground_excitation_mode != "include":
        cmd += ["--collision-type69-ground-excitation-mode", str(args.collision_type69_ground_excitation_mode)]
    if args.index_cache:
        if args.index_cache_path_template:
            cache_path = render_template(args.index_cache_path_template, density, index, args.element, int(args.ion_stage))
            cmd += ["--index-cache", "--index-cache-path", cache_path, "--index-cache-format", args.index_cache_format]
        elif args.index_cache_path:
            cmd += ["--index-cache", "--index-cache-path", str(args.index_cache_path), "--index-cache-format", args.index_cache_format]
        else:
            cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.child_print_summary:
        cmd.append("--print-summary")
    return cmd


def run_command(cmd: List[str], stdout_path: Path, stderr_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(" ".join(cmd) + "\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    with stdout_path.open("a", encoding="utf-8") as out, stderr_path.open("a", encoding="utf-8") as err:
        proc = subprocess.run(cmd, stdout=out, stderr=err, text=True)
    return int(proc.returncode)


def summarize_density(density: float, tag: str, run_dir: Path, rc: int, xstar_csv: str) -> dict:
    row = {
        "electron_density_cm^-3": float(density),
        "density_tag": tag,
        "run_status": "ok" if rc == 0 else "failed",
        "returncode": int(rc),
        "run_dir": str(run_dir),
        "xstar_lines_csv": str(xstar_csv),
    }
    summary_path = run_dir / "helike_signed_triplet_response_summary.json"
    if not summary_path.exists():
        row["fit_status"] = "missing_summary"
        return row
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        row["fit_status"] = f"invalid_summary:{exc}"
        return row
    fit = summary.get("absolute_response_fit") or {}
    row.update({
        "fit_status": fit.get("status"),
        "n_candidate_source_levels": fit.get("n_candidate_source_levels"),
        "component_l1_error": fit.get("component_l1_error"),
        "component_l2_error": fit.get("component_l2_error"),
        "component_weights": ";".join(str(x) for x in (fit.get("component_weights") or [])),
        "component_weights_mode": fit.get("component_weights_mode"),
        "constraint_rejection_counts": json.dumps(fit.get("constraint_rejection_counts") or {}, sort_keys=True),
        "constraint_mode": fit.get("constraint_mode"),
        "effective_constraints": json.dumps(fit.get("effective_constraints") or {}, sort_keys=True),
        "target_forbidden": fit.get("target_forbidden"),
        "target_intercombination": fit.get("target_intercombination"),
        "target_resonance": fit.get("target_resonance"),
        "pred_forbidden": fit.get("pred_forbidden"),
        "pred_intercombination": fit.get("pred_intercombination"),
        "pred_resonance": fit.get("pred_resonance"),
        "target_R_f_over_i": fit.get("target_R_f_over_i"),
        "target_G_f_plus_i_over_r": fit.get("target_G_f_plus_i_over_r"),
        "pred_R_f_over_i": fit.get("pred_R_f_over_i"),
        "pred_G_f_plus_i_over_r": fit.get("pred_G_f_plus_i_over_r"),
        "top_source_levels": ";".join(str(x) for x in (fit.get("top_source_levels") or [])),
        "baseline_forbidden": (summary.get("baseline_triplet") or {}).get("forbidden"),
        "baseline_intercombination": (summary.get("baseline_triplet") or {}).get("intercombination"),
        "baseline_resonance": (summary.get("baseline_triplet") or {}).get("resonance"),
        "n_negative_due_to_baseline_subtraction": summary.get("n_negative_due_to_baseline_subtraction"),
    })
    return row


def collect_weight_rows(density: float, tag: str, run_dir: Path) -> List[dict]:
    path = run_dir / "helike_absolute_response_fit_weights.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row = dict(row)
            row["electron_density_cm^-3"] = float(density)
            row["density_tag"] = tag
            rows.append(row)
    return rows


def write_markdown(path: Path, rows: List[dict], args) -> None:
    lines = []
    lines.append("# Absolute-response He-like triplet density-grid fit")
    lines.append("")
    lines.append(f"Element/ion: `{args.element} {args.ion_stage}`")
    lines.append(f"T = `{float(args.temperature):g}` K")
    lines.append(f"Source levels: `{args.source_levels}`")
    lines.append(f"Constraint mode: `{args.absolute_fit_constraint_mode}`")
    lines.append("")
    lines.append("| ne | status | candidates | L2 | target f/i/r | predicted f/i/r | target R/G | predicted R/G | top levels |")
    lines.append("|---:|---|---:|---:|---|---|---|---|---|")
    for row in rows:
        target = f"{_fmt(row.get('target_forbidden'))}/{_fmt(row.get('target_intercombination'))}/{_fmt(row.get('target_resonance'))}"
        pred = f"{_fmt(row.get('pred_forbidden'))}/{_fmt(row.get('pred_intercombination'))}/{_fmt(row.get('pred_resonance'))}"
        trg = f"{_fmt(row.get('target_R_f_over_i'))}/{_fmt(row.get('target_G_f_plus_i_over_r'))}"
        prg = f"{_fmt(row.get('pred_R_f_over_i'))}/{_fmt(row.get('pred_G_f_plus_i_over_r'))}"
        lines.append(
            f"| {_fmt(row.get('electron_density_cm^-3'))} | {row.get('fit_status')} | {row.get('n_candidate_source_levels') or 'NA'} | {_fmt(row.get('component_l2_error'))} | {target} | {pred} | {trg} | {prg} | `{row.get('top_source_levels') or ''}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile", nargs="?", default=None, help="Optional XSTAR atdb.fits path. Explicit paths are passed through and do not rewrite datapath.")
    parser.add_argument("--element", default="C")
    parser.add_argument("--ion-stage", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-densities", default="1,1e4,1e8,1e10,1e12")
    parser.add_argument("--source-levels", default="2:80")
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, default=40.0)
    parser.add_argument("--wavelength-max", type=float, default=42.0)
    parser.add_argument("--xstar-lines-csv-template", required=True, help="Template for each density, e.g. xstar_test_run/c5_ne{ne_tag}/xstar_c5_triplet_lines.csv")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--absolute-fit-min-triplet-sum", type=float, default=0.0)
    parser.add_argument("--absolute-fit-component-weights", default="uniform", help="Component weights for child absolute-response fits: uniform, auto, or comma-separated f,i,r weights.")
    parser.add_argument("--absolute-fit-weight-floor", type=float, default=1.0e-3)
    parser.add_argument("--absolute-fit-constraint-mode", choices=["fixed", "target-aware"], default="fixed", help="Column-constraint mode passed to child absolute-response fits.")
    parser.add_argument("--absolute-fit-target-i-factor", type=float, default=3.0)
    parser.add_argument("--absolute-fit-target-i-floor", type=float, default=0.05)
    parser.add_argument("--absolute-fit-low-target-i-threshold", type=float, default=0.05)
    parser.add_argument("--absolute-fit-reject-pure-i", action="store_true", help="Reject nearly pure intercombination columns in child fits.")
    parser.add_argument("--absolute-fit-pure-i-threshold", type=float, default=0.95)
    parser.add_argument("--absolute-fit-max-intercombination-fraction", type=float, default=1.0)
    parser.add_argument("--absolute-fit-max-forbidden-fraction", type=float, default=1.0)
    parser.add_argument("--absolute-fit-max-resonance-fraction", type=float, default=1.0)
    parser.add_argument("--absolute-fit-min-forbidden-fraction", type=float, default=0.0)
    parser.add_argument("--absolute-fit-min-resonance-fraction", type=float, default=0.0)
    parser.add_argument("--fit-max-iter", type=int, default=50000)
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--residual-l2-max", type=float)
    parser.add_argument("--residual-linf-max", type=float)
    parser.add_argument("--reject-large-residual", action="store_true")
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--collision-rate-scale", type=float, default=1.0)
    parser.add_argument("--collision-data-type-scale", action="append", default=[])
    parser.add_argument("--collision-pair-scale", action="append", default=[])
    parser.add_argument("--collision-record-scale", action="append", default=[])
    parser.add_argument("--collision-record-direction-scale", action="append", default=[])
    parser.add_argument("--collision-type69-ground-excitation-mode", choices=["include", "suppress-resonance", "suppress-all"], default="include")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-path-template", help="Optional per-density cache template, e.g. .xstar_atomic_cache/atdb_c5_{ne_tag}.npz")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--zero-tol", type=float, default=0.0)
    parser.add_argument("--out-dir", default="helike_absolute_response_density_grid")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--child-print-summary", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    runs_dir = out_dir / "density_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    densities = parse_float_list(args.electron_densities)
    command_rows: List[dict] = []
    summary_rows: List[dict] = []
    all_weight_rows: List[dict] = []

    for idx, ne in enumerate(densities):
        tag = density_tag(float(ne))
        xstar_csv = render_template(args.xstar_lines_csv_template, float(ne), idx, args.element, int(args.ion_stage))
        run_dir = runs_dir / f"ne_{tag}"
        cmd = command_for_density(args, float(ne), idx, xstar_csv, run_dir)
        stdout_path = run_dir / "example40.stdout.log"
        stderr_path = run_dir / "example40.stderr.log"
        rc = run_command(cmd, stdout_path, stderr_path)
        command_rows.append({
            "electron_density_cm^-3": float(ne),
            "density_tag": tag,
            "returncode": rc,
            "xstar_lines_csv": xstar_csv,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "command": " ".join(cmd),
        })
        row = summarize_density(float(ne), tag, run_dir, rc, xstar_csv)
        summary_rows.append(row)
        all_weight_rows.extend(collect_weight_rows(float(ne), tag, run_dir))

    write_csv(out_dir / "helike_absolute_response_density_grid_summary.csv", summary_rows)
    write_csv(out_dir / "helike_absolute_response_density_grid_commands.csv", command_rows)
    write_csv(out_dir / "helike_absolute_response_density_grid_weights.csv", all_weight_rows)
    aggregate = {
        "element": args.element,
        "ion_stage": int(args.ion_stage),
        "temperature_K": float(args.temperature),
        "electron_densities_cm^-3": densities,
        "source_levels": args.source_levels,
        "fitsfile": str(args.fitsfile) if args.fitsfile else None,
        "xstar_lines_csv_template": args.xstar_lines_csv_template,
        "absolute_fit_component_weights": args.absolute_fit_component_weights,
        "absolute_fit_reject_pure_i": bool(args.absolute_fit_reject_pure_i),
        "absolute_fit_pure_i_threshold": float(args.absolute_fit_pure_i_threshold),
        "absolute_fit_max_intercombination_fraction": float(args.absolute_fit_max_intercombination_fraction),
        "n_density_points": len(densities),
        "n_successful_runs": sum(1 for r in summary_rows if r.get("run_status") == "ok"),
        "rows": summary_rows,
    }
    (out_dir / "helike_absolute_response_density_grid_summary.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    write_markdown(out_dir / "helike_absolute_response_density_grid_summary.md", summary_rows, args)

    if args.print_summary:
        print("Absolute-response He-like triplet density-grid fit")
        print("---------------------------------------------------")
        for row in summary_rows:
            print(
                f"ne={_fmt(row.get('electron_density_cm^-3'))} status={row.get('fit_status')} "
                f"candidates={row.get('n_candidate_source_levels') or 'NA'} l2={_fmt(row.get('component_l2_error'))} "
                f"target={_fmt(row.get('target_forbidden'))}/{_fmt(row.get('target_intercombination'))}/{_fmt(row.get('target_resonance'))} "
                f"pred={_fmt(row.get('pred_forbidden'))}/{_fmt(row.get('pred_intercombination'))}/{_fmt(row.get('pred_resonance'))} "
                f"top=[{row.get('top_source_levels') or ''}]"
            )
        print(f"wrote: {out_dir / 'helike_absolute_response_density_grid_summary.md'}")


if __name__ == "__main__":
    main()
