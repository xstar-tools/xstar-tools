#!/usr/bin/env python3
"""Scan broad He-like source-level blocks for positive triplet-response bases.

This v0.3.7 diagnostic automates the follow-up after
``examples/37_filter_source_basis_response.py`` and
``examples/38_discover_helike_source_basis.py``.  The previous diagnostics show
whether an already-sampled source-level list contains a clean positive nonzero
f/i/r response basis.  This script expands the search by running
``examples/20_o7_solver_source_fit.py`` over user-specified source-level blocks
(such as ``2:40`` or ``41:80``), then runs the discovery diagnostic on those
block outputs.

The goal is to determine whether non-O VII ions have useful source levels
outside the O VII-derived list.  The fitted weights remain empirical and the
scan is intended as a diagnostic, not as a physical recombination model.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple




def resolve_optional_fitsfile(path: Optional[str]) -> str:
    """Resolve optional atdb.fits path without rewriting datapath.

    If a path is supplied, return it unchanged; this avoids changing the
    persistent datapath during ordinary example runs.  If omitted, defer to the
    package data resolver, which uses XSTAR_ATDB_FITS, datapath, or data/.
    """
    if path is not None:
        return str(path)
    from xstar_atomic.data import resolve_atdb_path
    return str(resolve_atdb_path(None, prompt=False, remember_explicit=False))

def _maybe_float(value) -> Optional[float]:
    try:
        val = float(value)
    except Exception:
        return None
    if not math.isfinite(val):
        return None
    return val


def _fmt(value, precision: int = 6) -> str:
    val = _maybe_float(value)
    if val is None:
        return "NA"
    return f"{val:.{precision}g}"



def _discover_available_source_levels(args: argparse.Namespace) -> Tuple[Optional[set[int]], List[str]]:
    """Return available level indices for the requested ion, when ATDB can be read.

    This is intentionally best-effort.  The block scanner should still be able to
    write commands in dry-run mode or in environments where the ATDB file is not
    available.
    """
    warnings: List[str] = []
    fits_path = Path(str(args.fitsfile))
    if args.dry_run or not getattr(args, "skip_invalid_source_levels", True):
        return None, warnings
    if not fits_path.exists():
        warnings.append(f"source-level preflight skipped because ATDB file does not exist: {fits_path}")
        return None, warnings
    try:
        from xstar_atomic.hierarchy import ATDB
        from xstar_atomic.lines import extract_levels, choose_z
    except Exception as exc:  # pragma: no cover - import failures are environment-specific
        warnings.append(f"source-level preflight skipped because xstar_atomic imports failed: {exc}")
        return None, warnings
    try:
        z = choose_z(str(args.element))
        use_cache = bool(args.index_cache) or bool(args.index_cache_path)
        with ATDB(fits_path) as db:
            records, _elements, _ions = db.build_index(
                use_cache=use_cache,
                cache_path=args.index_cache_path,
                cache_format=args.index_cache_format,
            )
            levels = extract_levels(db, records, z, int(args.ion_stage))
        available = {int(row["level_index"]) for row in levels if row.get("level_index") not in (None, "")}
        if not available:
            warnings.append(f"source-level preflight found no levels for {args.element} {args.ion_stage}; using requested blocks unchanged")
            return None, warnings
        warnings.append(
            f"source-level preflight found {len(available)} available levels for {args.element} {args.ion_stage} "
            f"(min={min(available)}, max={max(available)})"
        )
        return available, warnings
    except Exception as exc:
        warnings.append(f"source-level preflight failed; using requested blocks unchanged: {exc}")
        return None, warnings


def _filter_levels_for_preflight(levels: Sequence[int], available: Optional[set[int]]) -> Tuple[List[int], List[int]]:
    if available is None:
        return [int(x) for x in levels], []
    kept = [int(x) for x in levels if int(x) in available]
    skipped = [int(x) for x in levels if int(x) not in available]
    return kept, skipped



def _normalize_ion_text(text: str) -> str:
    return str(text or "").strip().lower().replace(" ", "").replace("_", "")


def _expected_ion_aliases(element: str, ion_stage: int) -> set[str]:
    # Minimal aliases matching the converter output used by examples/20/33.
    roman_map = {
        1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii", 8: "viii", 9: "ix", 10: "x",
        11: "xi", 12: "xii", 13: "xiii", 14: "xiv", 15: "xv", 16: "xvi", 17: "xvii", 18: "xviii", 19: "xix", 20: "xx",
        21: "xxi", 22: "xxii", 23: "xxiii", 24: "xxiv", 25: "xxv", 26: "xxvi",
    }
    e = str(element or "").strip().lower()
    rn = roman_map.get(int(ion_stage), str(int(ion_stage)).lower())
    return {_normalize_ion_text(f"{e}_{rn}"), _normalize_ion_text(f"{e} {rn}"), _normalize_ion_text(f"{e}{rn}")}


def _classify_triplet_row(row: dict) -> Optional[str]:
    lower = str(row.get("lower_level", "") or row.get("lower", "")).replace(" ", "")
    upper = str(row.get("upper_level", "") or row.get("upper", "")).replace(" ", "")
    if "1s2.1S_0" in lower or "1s2" in lower:
        if "1s1.2s1.3S_1" in upper or "2s1.3S_1" in upper:
            return "f"
        if "1s1.2p1.1P_1" in upper or "2p1.1P_1" in upper:
            return "r"
        if "1s1.2p1.3P_" in upper or "2p1.3P_" in upper:
            return "i"
    return None


def _preflight_xstar_reference(args: argparse.Namespace) -> List[str]:
    """Best-effort validation of the converted XSTAR triplet reference CSV."""
    warnings: List[str] = []
    path = Path(str(args.xstar_lines_csv))
    if not path.exists():
        warnings.append(
            f"XSTAR triplet reference CSV does not exist: {path}. "
            "Run/copy the converter output for this ion/density before running the block scan."
        )
        return warnings
    aliases = _expected_ion_aliases(str(args.element), int(args.ion_stage))
    counts = {"f": 0, "i": 0, "r": 0}
    row_count = 0
    matching_ion_rows = 0
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row_count += 1
                ion = _normalize_ion_text(row.get("ion", ""))
                if ion and ion not in aliases:
                    continue
                matching_ion_rows += 1
                kind = _classify_triplet_row(row)
                if kind:
                    counts[kind] += 1
    except Exception as exc:
        warnings.append(f"XSTAR triplet reference CSV could not be read: {path}: {exc}")
        return warnings
    if row_count == 0:
        warnings.append(f"XSTAR triplet reference CSV is empty: {path}")
    elif matching_ion_rows == 0:
        warnings.append(f"XSTAR triplet reference CSV has {row_count} rows but none match {args.element} {args.ion_stage}: {path}")
    missing = [name for name, n in counts.items() if n <= 0]
    if missing:
        warnings.append(
            f"XSTAR triplet reference CSV is present but incomplete for {args.element} {args.ion_stage}: "
            f"counts={counts}; missing={','.join(missing)}; path={path}. "
            "examples/20 will reject this reference because it cannot compute both R=f/i and G=(f+i)/r."
        )
    else:
        warnings.append(f"XSTAR triplet reference preflight OK for {args.element} {args.ion_stage}: counts={counts}; path={path}")
    return warnings


def write_csv(path: Path, rows: List[dict], default_fields: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = default_fields or ["warning"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_block(text: str) -> Tuple[int, int]:
    raw = str(text).strip()
    if not raw:
        raise ValueError("empty source-level block")
    if ":" in raw:
        left, right = raw.split(":", 1)
    elif "-" in raw:
        left, right = raw.split("-", 1)
    else:
        left = right = raw
    start = int(left)
    stop = int(right)
    if start <= 0 or stop <= 0:
        raise ValueError(f"source levels must be positive: {text!r}")
    if stop < start:
        start, stop = stop, start
    return start, stop


def block_levels(block: Tuple[int, int]) -> List[int]:
    return list(range(int(block[0]), int(block[1]) + 1))


def block_tag(block: Tuple[int, int]) -> str:
    return f"levels_{int(block[0])}_{int(block[1])}"


def density_token(density: float) -> str:
    val = float(density)
    if val == 0:
        return "0"
    if abs(val - round(val)) < 1e-12 and abs(val) < 1e7:
        return str(int(round(val)))
    return f"{val:.0e}".replace("+", "")


def build_example20_command(args: argparse.Namespace, levels: Sequence[int], out_fit_dir: Path) -> List[str]:
    cmd = [
        sys.executable,
        "examples/20_o7_solver_source_fit.py",
        str(args.fitsfile),
        "--element", str(args.element),
        "--ion-stage", str(int(args.ion_stage)),
        "--temperature", str(float(args.temperature)),
        "--electron-density", str(float(args.electron_density)),
        "--source-levels", ",".join(str(int(x)) for x in levels),
        "--source-rate", str(float(args.source_rate)),
        "--combined-source-total-rate", str(float(args.combined_source_total_rate)),
        "--wavelength-min", str(float(args.wavelength_min)),
        "--wavelength-max", str(float(args.wavelength_max)),
        "--xstar-lines-csv", str(args.xstar_lines_csv),
        "--xstar-value-column", str(args.xstar_value_column),
        "--linear-solver", str(args.linear_solver),
        "--rank-deficient-action", str(args.rank_deficient_action),
        "--negative-population-action", str(args.negative_population_action),
        "--negative-population-tol", str(float(args.negative_population_tol)),
        "--null-rate-floor", str(float(args.null_rate_floor)),
        "--out-dir", str(out_fit_dir),
    ]
    if args.prune_null_rate_levels:
        cmd.append("--prune-null-rate-levels")
    else:
        cmd.append("--no-prune-null-rate-levels")
    if args.index_cache:
        cmd.append("--index-cache")
    if args.index_cache_path:
        cmd.extend(["--index-cache-path", str(args.index_cache_path)])
    cmd.extend(["--index-cache-format", str(args.index_cache_format)])
    if args.collision_type69_ground_excitation_mode:
        cmd.extend(["--collision-type69-ground-excitation-mode", str(args.collision_type69_ground_excitation_mode)])
    if args.skip_combined_validation:
        cmd.append("--skip-combined-validation")
    if args.print_child_summary:
        cmd.append("--print-summary")
    for item in args.collision_data_type_scale or []:
        cmd.extend(["--collision-data-type-scale", str(item)])
    for item in args.collision_pair_scale or []:
        cmd.extend(["--collision-pair-scale", str(item)])
    for item in args.collision_record_scale or []:
        cmd.extend(["--collision-record-scale", str(item)])
    for item in args.collision_record_direction_scale or []:
        cmd.extend(["--collision-record-direction-scale", str(item)])
    return cmd


def run_discovery(block_run_dirs: Sequence[Path], out_dir: Path, args: argparse.Namespace) -> Tuple[List[dict], List[dict], List[dict], List[str]]:
    discovery_out = out_dir / "discovery"
    cmd = [
        sys.executable,
        "examples/38_discover_helike_source_basis.py",
        *[str(p) for p in block_run_dirs],
        "--out-dir", str(discovery_out),
        "--min-triplet-response-sum", str(float(args.min_triplet_response_sum)),
        "--negative-response-tol", str(float(args.negative_response_tol)),
        "--max-iter", str(int(args.discovery_max_iter)),
    ]
    if int(args.discovery_max_levels) > 0:
        cmd.extend(["--max-levels", str(int(args.discovery_max_levels))])
    if args.print_child_summary:
        cmd.append("--print-summary")
    completed = subprocess.run(cmd, cwd=Path.cwd(), text=True, capture_output=True)
    warnings: List[str] = []
    if completed.returncode != 0:
        warnings.append(f"discovery command failed with return code {completed.returncode}: {' '.join(cmd)}")
        if completed.stderr:
            warnings.append(completed.stderr.strip())
        return [], [], [], warnings
    density_path = discovery_out / "helike_discovered_source_basis_density_summary.csv"
    run_path = discovery_out / "helike_discovered_source_basis_run_summary.csv"
    level_path = discovery_out / "helike_discovered_source_basis_levels.csv"
    density_rows = read_csv(density_path) if density_path.exists() else []
    run_rows = read_csv(run_path) if run_path.exists() else []
    level_rows = read_csv(level_path) if level_path.exists() else []
    return run_rows, density_rows, level_rows, warnings


def summarize_block_scan(scan_rows: List[dict], discovery_run_rows: List[dict], discovery_density_rows: List[dict]) -> List[dict]:
    by_tag = {str(row.get("block_tag")): dict(row) for row in scan_rows}
    out: List[dict] = []
    for row in discovery_run_rows:
        tag = str(row.get("tag"))
        base = by_tag.get(tag, {})
        merged = {
            "block_tag": tag,
            "source_level_start": base.get("source_level_start"),
            "source_level_stop": base.get("source_level_stop"),
            "n_source_levels_scanned": base.get("n_source_levels"),
            "fit_status": base.get("status"),
            "discovery_status": row.get("status"),
            "n_densities": row.get("n_densities"),
            "median_n_positive_nonzero_source_levels": row.get("median_n_positive_nonzero_source_levels"),
            "median_n_discovered_source_levels": row.get("median_n_discovered_source_levels"),
            "median_discovered_component_l2_error": row.get("median_discovered_component_l2_error"),
            "max_discovered_component_l2_error": row.get("max_discovered_component_l2_error"),
            "common_discovered_source_levels": row.get("common_discovered_source_levels"),
        }
        out.append(merged)
    # Include dry-run/skipped/failed blocks absent from discovery output.
    seen = {str(r.get("block_tag")) for r in out}
    for tag, base in by_tag.items():
        if tag in seen:
            continue
        out.append({
            "block_tag": tag,
            "source_level_start": base.get("source_level_start"),
            "source_level_stop": base.get("source_level_stop"),
            "n_source_levels_scanned": base.get("n_source_levels"),
            "fit_status": base.get("status"),
            "discovery_status": "not_run",
            "n_densities": 0,
            "median_n_positive_nonzero_source_levels": None,
            "median_n_discovered_source_levels": None,
            "median_discovered_component_l2_error": None,
            "max_discovered_component_l2_error": None,
            "common_discovered_source_levels": "",
        })
    return out


def write_markdown(path: Path, summary_rows: List[dict], scan_rows: List[dict], warnings: List[str]) -> None:
    lines = ["# He-like source-level block scan", ""]
    lines.append("This diagnostic scans broad source-level blocks by running example 20 for each block and then applying the source-basis discovery diagnostic from example 38. In v0.3.7 the scanner preflights the ATDB level table when possible, skips source levels that do not exist for the requested ion, and separately checks whether the XSTAR triplet reference CSV is present/readable before launching expensive block fits.")
    lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    lines.append("## Block summary")
    lines.append("")
    lines.append("| block | fit status | discovery status | levels scanned | positive levels | discovered levels | L2 error | discovered source levels |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for row in summary_rows:
        lines.append(
            f"| {row.get('block_tag')} | {row.get('fit_status')} | {row.get('discovery_status')} | "
            f"{row.get('n_source_levels_scanned') or 'NA'} | {_fmt(row.get('median_n_positive_nonzero_source_levels'))} | "
            f"{_fmt(row.get('median_n_discovered_source_levels'))} | {_fmt(row.get('median_discovered_component_l2_error'))} | "
            f"{row.get('common_discovered_source_levels') or ''} |"
        )
    lines.append("")
    lines.append("## Commands")
    lines.append("")
    lines.append("The `helike_source_level_block_scan.csv` file contains the exact example-20 command used for each block, the requested levels, any skipped invalid levels, and stdout/stderr log paths. If `--dry-run` was used, copy a command from that file to execute one block manually.")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile", nargs="?", default=None, help="Optional XSTAR ATDB FITS file passed to example 20. If omitted, use XSTAR_ATDB_FITS, datapath, or data/atdb.fits.")
    parser.add_argument("--element", required=True, help="Element symbol, e.g. C, O, Mg, Ca.")
    parser.add_argument("--ion-stage", type=int, required=True, help="Ion stage, e.g. 5 for C V.")
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-density", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, required=True)
    parser.add_argument("--wavelength-max", type=float, required=True)
    parser.add_argument("--xstar-lines-csv", required=True, help="Converted XSTAR triplet CSV for this ion/density.")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--level-blocks", nargs="+", required=True, help="Inclusive source-level blocks, e.g. 2:40 41:80.")
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--combined-source-total-rate", type=float, default=1.0)
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--collision-data-type-scale", action="append", default=[])
    parser.add_argument("--collision-pair-scale", action="append", default=[])
    parser.add_argument("--collision-record-scale", action="append", default=[])
    parser.add_argument("--collision-record-direction-scale", action="append", default=[])
    parser.add_argument("--collision-type69-ground-excitation-mode", choices=["include", "suppress-resonance", "suppress-all"], default=None)
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--skip-combined-validation", action="store_true")
    parser.add_argument("--min-triplet-response-sum", type=float, default=1e-300)
    parser.add_argument("--negative-response-tol", type=float, default=0.0)
    parser.add_argument("--discovery-max-levels", type=int, default=0)
    parser.add_argument("--discovery-max-iter", type=int, default=30000)
    parser.add_argument("--out-dir", default="helike_source_level_block_scan")
    parser.add_argument("--force", action="store_true", help="Re-run a block even if its response matrix already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Write commands and summary files but do not execute example 20 or discovery.")
    parser.add_argument("--skip-invalid-source-levels", action="store_true", default=True, help="Preflight ATDB level table and remove requested source levels that do not exist for this ion before running each block. Default: true.")
    parser.add_argument("--no-skip-invalid-source-levels", dest="skip_invalid_source_levels", action="store_false", help="Do not preflight/filter requested source levels.")
    parser.add_argument("--print-child-summary", action="store_true", help="Pass --print-summary to child examples.")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    args.fitsfile = resolve_optional_fitsfile(args.fitsfile)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    blocks = [parse_block(x) for x in args.level_blocks]
    scan_rows: List[dict] = []
    block_run_dirs: List[Path] = []
    warnings: List[str] = []
    dens_token = density_token(float(args.electron_density))
    available_levels, preflight_warnings = _discover_available_source_levels(args)
    warnings.extend(preflight_warnings)
    warnings.extend(_preflight_xstar_reference(args))

    for block in blocks:
        requested_levels = block_levels(block)
        levels, skipped_levels = _filter_levels_for_preflight(requested_levels, available_levels)
        tag = block_tag(block)
        run_dir = out_dir / tag
        fit_dir = run_dir / f"fit_ne_{dens_token}"
        block_run_dirs.append(run_dir)
        cmd = build_example20_command(args, levels, fit_dir) if levels else []
        row = {
            "block_tag": tag,
            "source_level_start": block[0],
            "source_level_stop": block[1],
            "n_source_levels": len(levels),
            "n_requested_source_levels": len(requested_levels),
            "n_skipped_invalid_source_levels": len(skipped_levels),
            "source_levels": ",".join(str(x) for x in levels),
            "requested_source_levels": ",".join(str(x) for x in requested_levels),
            "skipped_invalid_source_levels": ",".join(str(x) for x in skipped_levels),
            "fit_dir": str(fit_dir),
            "command": " ".join(cmd),
            "stdout_log": str(run_dir / "example20.stdout.log"),
            "stderr_log": str(run_dir / "example20.stderr.log"),
            "status": "pending",
            "returncode": None,
        }
        response_matrix = fit_dir / "o7_solver_response_matrix.csv"
        if not levels:
            row["status"] = "skipped_no_valid_source_levels"
            warnings.append(f"{tag}: no requested source levels are present for {args.element} {args.ion_stage}; skipped block")
        elif args.dry_run:
            row["status"] = "dry_run"
        elif response_matrix.exists() and not args.force:
            row["status"] = "existing"
            row["returncode"] = 0
        else:
            run_dir.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(cmd, cwd=Path.cwd(), text=True, capture_output=True)
            (run_dir / "example20.stdout.log").write_text(completed.stdout or "", encoding="utf-8")
            (run_dir / "example20.stderr.log").write_text(completed.stderr or "", encoding="utf-8")
            row["returncode"] = completed.returncode
            row["stdout_tail"] = "\n".join((completed.stdout or "").splitlines()[-20:])
            row["stderr_tail"] = "\n".join((completed.stderr or "").splitlines()[-20:])
            row["status"] = "ok" if completed.returncode == 0 and response_matrix.exists() else "failed"
            if row["status"] == "failed":
                warnings.append(f"{tag}: example 20 failed or did not write {response_matrix}; see {run_dir / 'example20.stderr.log'}")
        scan_rows.append(row)

    discovery_run_rows: List[dict] = []
    discovery_density_rows: List[dict] = []
    discovery_level_rows: List[dict] = []
    if not args.dry_run:
        runnable_dirs = [p for p in block_run_dirs if any(p.glob("fit_ne_*/o7_solver_response_matrix.csv"))]
        if runnable_dirs:
            discovery_run_rows, discovery_density_rows, discovery_level_rows, ww = run_discovery(runnable_dirs, out_dir, args)
            warnings.extend(ww)
        else:
            warnings.append("No block run directories contain fit_ne_*/o7_solver_response_matrix.csv; discovery was not run.")
    else:
        warnings.append("Dry-run mode: example 20 and discovery were not executed.")

    summary_rows = summarize_block_scan(scan_rows, discovery_run_rows, discovery_density_rows)
    write_csv(out_dir / "helike_source_level_block_scan.csv", scan_rows)
    write_csv(out_dir / "helike_source_level_block_scan_summary.csv", summary_rows)
    write_csv(out_dir / "helike_source_level_block_scan_density_summary.csv", discovery_density_rows, default_fields=["block_tag", "warning"])
    write_csv(out_dir / "helike_source_level_block_scan_levels.csv", discovery_level_rows, default_fields=["block_tag", "warning"])
    with (out_dir / "helike_source_level_block_scan_summary.json").open("w", encoding="utf-8") as handle:
        json.dump({
            "block_scan": scan_rows,
            "summary": summary_rows,
            "density_summary": discovery_density_rows,
            "source_levels": discovery_level_rows,
            "warnings": warnings,
        }, handle, indent=2)
    write_markdown(out_dir / "helike_source_level_block_scan_summary.md", summary_rows, scan_rows, warnings)

    if args.print_summary:
        print("He-like source-level block scan")
        print("--------------------------------")
        for row in summary_rows:
            print(
                f"{row.get('block_tag')}: fit={row.get('fit_status')} discovery={row.get('discovery_status')} "
                f"levels={row.get('n_source_levels_scanned')} pos_med={_fmt(row.get('median_n_positive_nonzero_source_levels'))} "
                f"disc_med={_fmt(row.get('median_n_discovered_source_levels'))} "
                f"l2_med={_fmt(row.get('median_discovered_component_l2_error'))} "
                f"basis={row.get('common_discovered_source_levels') or 'none'}"
            )
        for w in warnings:
            print(f"WARNING: {w}")
        print(f"wrote: {out_dir / 'helike_source_level_block_scan_summary.md'}")


if __name__ == "__main__":
    main()
