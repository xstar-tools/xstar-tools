#!/usr/bin/env python3
"""Prepare and optionally run He-like triplet validation at XSTAR local-zone states.

This source-code-first diagnostic connects XSTAR ``xout_abund1.fits`` local
zone conditions to the pure-Python He-like solver.  It is intended for the next
validation step after reading ``xout_abund1.fits``: run C V, O VII, Mg XI and
Ca XIX at the XSTAR-selected local temperature and electron density for a given
log xi, then compare the solver triplet fractions with the matching XSTAR
``xout_lines1`` triplet target CSV.

The script does not fit triplet scale factors.  It reads local gas conditions
from the ``ABUNDANCES`` table in ``xout_abund1.fits`` and writes reproducible
shell commands.  If ``--run-solver`` is supplied together with ``--atdb``, it
also executes those commands and the corresponding comparisons.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ION_INFO: dict[str, dict[str, Any]] = {
    "c5": {
        "ion": "C V",
        "element": "C",
        "he_like_stage": 5,
        "xstar_col": "c_v",
        "window_min": 40.0,
        "window_max": 42.0,
        "target_file": "xstar_c5_triplet_lines.csv",
    },
    "o7": {
        "ion": "O VII",
        "element": "O",
        "he_like_stage": 7,
        "xstar_col": "o_vii",
        "window_min": 21.4,
        "window_max": 22.2,
        "target_file": "xstar_o7_triplet_lines.csv",
    },
    "mg11": {
        "ion": "Mg XI",
        "element": "Mg",
        "he_like_stage": 11,
        "xstar_col": "mg_xi",
        "window_min": 9.05,
        "window_max": 9.40,
        "target_file": "xstar_mg11_triplet_lines.csv",
    },
    "ca19": {
        "ion": "Ca XIX",
        "element": "Ca",
        "he_like_stage": 19,
        "xstar_col": "ca_xix",
        "window_min": 3.14,
        "window_max": 3.23,
        "target_file": "xstar_ca19_triplet_lines.csv",
    },
}


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(str(v).strip())
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _find_col(row: dict[str, Any], desired: str) -> str | None:
    wanted = _normalize_col(desired)
    aliases = {wanted, wanted.replace("_", "")}
    for key in row:
        nk = _normalize_col(key)
        if nk in aliases or nk.replace("_", "") in aliases:
            return str(key)
    return None


def _xi_token_from_float(x: float | None) -> str | None:
    if x is None:
        return None
    return "xi" + f"{x:.12g}".replace(".", "p")


def _case_tag_from_path(path: Path) -> str | None:
    text = str(path).lower()
    # Prefer explicit directory tags.
    for tag in ION_INFO:
        if tag in text:
            return tag
    return None


def _logxi_from_path(path: Path) -> float | None:
    text = str(path).lower()
    m = re.search(r"xi([0-9]+(?:p[0-9]+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace("p", "."))
    except Exception:
        return None


def _format_num_for_dir(x: float | None) -> str:
    if x is None:
        return "unknown"
    return f"{x:.6g}".replace(".", "p").replace("+", "").replace("-", "m")


def _quote_cmd(parts: Sequence[str | Path | float | int]) -> str:
    return " ".join(shlex.quote(str(p)) for p in parts)


def _read_xout(path: Path) -> dict[str, list[dict[str, Any]]]:
    from xstar_atomic.xstar_outputs import read_xout_abundances

    return read_xout_abundances(path)


def _triplet_from_csv(path: Path, value_column: str = "emit_outward") -> dict[str, Any]:
    rows = _read_csv(path)
    vals = {"f": 0.0, "i": 0.0, "r": 0.0}
    total = 0.0
    max_depth_in = 0.0
    max_depth_out = 0.0
    for row in rows:
        upper = str(row.get("upper_level", "") or row.get("upper", "")).lower()
        lower = str(row.get("lower_level", "") or row.get("lower", "")).lower()
        text = upper + " " + lower
        comp = None
        if "2s1.3s" in text or "3s_1" in text:
            comp = "f"
        elif "2p1.3p" in text or "3p_" in text:
            comp = "i"
        elif "2p1.1p_1" in text or "1p_1" in text:
            comp = "r"
        val = _as_float(row.get(value_column)) or 0.0
        if comp:
            vals[comp] += val
            total += val
        max_depth_in = max(max_depth_in, _as_float(row.get("depth_inward")) or 0.0)
        max_depth_out = max(max_depth_out, _as_float(row.get("depth_outward")) or 0.0)
    frac = {k: (v / total if total > 0 else None) for k, v in vals.items()}
    return {
        "xstar_target_csv": str(path),
        "xstar_target_rows": len(rows),
        "xstar_target_total_triplet_emit": total,
        "xstar_target_f_fraction": frac["f"],
        "xstar_target_i_fraction": frac["i"],
        "xstar_target_r_fraction": frac["r"],
        "xstar_target_R": (frac["f"] / frac["i"] if frac["f"] is not None and frac["i"] not in (None, 0.0) else None),
        "xstar_target_G": ((frac["f"] + frac["i"]) / frac["r"] if frac["f"] is not None and frac["i"] is not None and frac["r"] not in (None, 0.0) else None),
        "xstar_target_max_depth_inward": max_depth_in,
        "xstar_target_max_depth_outward": max_depth_out,
    }


def _find_target_csv(roots: Iterable[Path], tag: str, logxi: float | None) -> Path | None:
    filename = str(ION_INFO[tag]["target_file"])
    xtok = _xi_token_from_float(logxi)
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if xtok:
            candidates.extend(root.glob(f"**/{tag}_{xtok}*/{filename}"))
            candidates.extend(root.glob(f"**/{tag}*{xtok}*/{filename}"))
        candidates.extend(root.glob(f"**/{filename}"))
    if not candidates:
        return None
    unique = sorted(set(candidates), key=lambda p: (len(str(p)), str(p)))
    if xtok:
        exact = [p for p in unique if xtok.lower() in str(p).lower()]
        if exact:
            return exact[0]
    # For C/O density-only targets there may not be a log-xi token.
    return unique[0]


def _find_xout_files(roots: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root.exists():
            found.extend(root.glob("**/xout_abund1.fits"))
    return sorted(set(found), key=lambda p: str(p))


def _candidate_zone_rows(xout_path: Path, tag: str) -> list[dict[str, Any]]:
    info = ION_INFO[tag]
    tables = _read_xout(xout_path)
    rows = tables.get("abundances", [])
    if not rows:
        return []
    col = _find_col(rows[0], str(info["xstar_col"]))
    if col is None:
        return []
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        ion_fraction = _as_float(row.get(col))
        logxi_raw = _as_float(row.get("ion_parameter"))
        t_1e4 = _as_float(row.get("temperature"))
        xe = _as_float(row.get("x_e"))
        np_ = _as_float(row.get("n_p"))
        ne = xe * np_ if xe is not None and np_ is not None else None
        out.append({
            "zone_index": idx,
            "xstar_abund_path": str(xout_path),
            "xstar_case_directory": xout_path.parent.name,
            "xstar_tag_from_path": _case_tag_from_path(xout_path),
            "xstar_log_xi_from_path": _logxi_from_path(xout_path),
            "xstar_ion_parameter_raw": logxi_raw,
            "xstar_log_xi_local": logxi_raw,
            "xstar_xi_erg_cm_s^-1": 10.0 ** logxi_raw if logxi_raw is not None else None,
            "xstar_radius_cm": _as_float(row.get("radius")),
            "xstar_delta_r_cm": _as_float(row.get("delta_r")),
            "xstar_x_e": xe,
            "xstar_n_p_cm^-3": np_,
            "xstar_electron_density_cm^-3": ne,
            "xstar_pressure": _as_float(row.get("pressure")),
            "xstar_temperature_K": 1.0e4 * t_1e4 if t_1e4 is not None else None,
            "xstar_frac_heat_error": _as_float(row.get("frac_heat_error")),
            "xstar_helike_column": col,
            "xstar_helike_fraction": ion_fraction,
        })
    return out


def _choose_zone(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    # Prefer the zone with the largest He-like fraction.  Keep zero-fraction
    # rows visible but mark them as not physically useful.
    return max(rows, key=lambda r: _as_float(r.get("xstar_helike_fraction")) or -1.0)


def _choose_one_zone_per_xout(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_path.setdefault(str(row.get("xstar_abund_path", "")), []).append(row)
    chosen = [_choose_zone(v) for _, v in sorted(by_path.items())]
    return [r for r in chosen if r is not None]


def _filter_logxi(rows: list[dict[str, Any]], wanted_logxi: float | None, tol: float = 1e-6) -> list[dict[str, Any]]:
    if wanted_logxi is None:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        lx = _as_float(row.get("xstar_log_xi_local"))
        if lx is not None and abs(lx - wanted_logxi) <= tol:
            out.append(row)
    return out


def _solver_out_dir(tag: str, zone: dict[str, Any] | None, version_label: str) -> str:
    logxi = _as_float(zone.get("xstar_log_xi_local")) if zone else None
    t = _as_float(zone.get("xstar_temperature_K")) if zone else None
    ne = _as_float(zone.get("xstar_electron_density_cm^-3")) if zone else None
    return f"{tag}_xstar_like_element_solver_{version_label}_logxi{_format_num_for_dir(logxi)}_T{_format_num_for_dir(t)}_ne{_format_num_for_dir(ne)}_local_state"


def _make_solver_command(atdb: str, tag: str, zone: dict[str, Any], out_dir: str, python_exe: str = "python") -> list[str]:
    info = ION_INFO[tag]
    t = _as_float(zone.get("xstar_temperature_K"))
    ne = _as_float(zone.get("xstar_electron_density_cm^-3"))
    if t is None or ne is None:
        raise ValueError("missing local T or ne")
    parts = [
        "PYTHONPATH=src", python_exe, "examples/42_xstar_like_element_solver_demo.py",
        atdb,
        "--element", str(info["element"]),
        "--he-like-stage", str(info["he_like_stage"]),
        "--temperature", f"{t:.12g}",
        "--electron-density", f"{ne:.12g}",
        "--wavelength-min", str(info["window_min"]),
        "--wavelength-max", str(info["window_max"]),
        "--max-level", "80",
        "--adjacent-coupling-mode", "recombination-source",
        "--adjacent-coupling-source-mode", "record-destination",
        "--index-cache",
        "--type57-energy-convention", "abs-rlev4",
        "--triplet-source-mode", "type74-direct-diagnostic",
        "--type99-proxy-scale", "0,1e-8,1e-6,1e-4,1e-2,1,1e2",
        "--radiation-field-mode", "xstar-powerlaw",
        "--radiation-bremsa-scale", "1e18",
        "--radiation-powerlaw-index", "1.0",
        "--radiation-n-energy-grid", "512",
        "--type53-flat-proxy-scale", "1",
        "--type53-phint53-scale", "1,1e5,1e10,1e15,1e18,1e20",
        "--inverse-recombination-mode", "xstar-ucalc",
        "--ion-fraction-closure", "xstar-calc-ion-rates",
        "--full-global-linear-solver", "xstar-lucy",
        "--full-global-topology", "xstar-continuum-alias-superlevels",
        "--type50-bound-bound-treatment", "xstar-line-escape",
        "--type50-escape-factor", "0.35",
        "--out-dir", out_dir,
        "--print-summary",
    ]
    return parts


def _make_compare_command(tag: str, out_dir: str, target_csv: Path | None, python_exe: str = "python") -> list[str] | None:
    if target_csv is None:
        return None
    info = ION_INFO[tag]
    return [
        "PYTHONPATH=src", python_exe, "examples/43_compare_xstar_detail_populations.py",
        "--solver-out-dir", out_dir,
        "--element", str(info["element"]),
        "--he-like-stage", str(info["he_like_stage"]),
        "--comparison-case", "full_global_xstar_tau0_calc_emis_ion",
        "--xstar-triplet-lines-csv", str(target_csv),
        "--xstar-value-column", "emit_outward",
        "--target-f", "nan", "--target-i", "nan", "--target-r", "nan",
        "--print-summary",
    ]


def _read_solver_after_run(out_dir: Path) -> dict[str, Any]:
    summary = _read_json(out_dir / "xstar_like_element_solver_summary.json")
    comp = _read_json(out_dir / "xstar_detail_population_comparison_summary.json")
    trip = comp.get("triplet") or summary.get("recommended_comparison", {}).get("triplet") or {}
    row: dict[str, Any] = {}
    for key in ("f_fraction", "i_fraction", "r_fraction", "R", "G", "l2_distance_to_target"):
        if key in trip:
            row[f"solver_after_run_{key}"] = trip.get(key)
    return row


def build(
    xstar_runs_root: Path,
    target_root: Path | None,
    ions: Sequence[str],
    atdb: str | None,
    out_dir: Path,
    version_label: str,
    run_solver: bool = False,
    python_exe: str = "python",
    selection_mode: str = "grid",
    logxi: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
    roots = [xstar_runs_root]
    if target_root is not None:
        roots.append(target_root)
    xout_files = _find_xout_files([xstar_runs_root])
    all_zone_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    solver_script_lines: list[str] = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    compare_script_lines: list[str] = ["#!/usr/bin/env bash", "set -euo pipefail", ""]

    def add_case(tag: str, zone: dict[str, Any] | None, case_rank: int = 0) -> None:
        info = ION_INFO[tag]
        row: dict[str, Any] = {
            "ion": info["ion"],
            "tag": tag,
            "element": info["element"],
            "he_like_stage": info["he_like_stage"],
            "has_xout_abund1": bool(zone),
            "selection_policy": selection_mode,
            "requested_log_xi": logxi,
            "case_rank": case_rank,
            "radiation_normalization_status": "not_yet_tied_to_XSTAR_xi_or_transfer; local T/ne/logxi are used first",
        }
        if zone is None:
            row.update({
                "status": "missing_xout_abund1_or_ion_column",
                "can_generate_solver_command": False,
                "recommended_action": f"provide a matching xout_abund1.fits for {info['ion']} before local-state validation",
            })
            case_rows.append(row)
            return
        row.update(zone)
        frac = _as_float(zone.get("xstar_helike_fraction"))
        if frac is None or frac <= 0.0:
            row["status"] = "xout_present_but_helike_fraction_zero_or_missing"
            row["can_generate_solver_command"] = False
            row["recommended_action"] = f"run/preserve an XSTAR target where {info['ion']} has nonzero abundance; current xout grid is not physically useful for this ion"
        else:
            row["status"] = "local_state_selected"
            row["can_generate_solver_command"] = bool(atdb)
            row["recommended_action"] = "rerun solver at XSTAR selected-zone T/ne, then compare to matching XSTAR triplet CSV"
        target_csv = _find_target_csv(roots, tag, _as_float(zone.get("xstar_log_xi_local")))
        row["target_csv_found"] = bool(target_csv)
        row["target_csv_path"] = str(target_csv) if target_csv else ""
        if target_csv:
            row.update(_triplet_from_csv(target_csv))
        out_name = _solver_out_dir(tag, zone, version_label)
        row["recommended_solver_out_dir"] = out_name
        if atdb and frac is not None and frac > 0.0:
            solver_cmd = _make_solver_command(atdb, tag, zone, out_name, python_exe=python_exe)
            cmp_cmd = _make_compare_command(tag, out_name, target_csv, python_exe=python_exe)
            row["solver_command"] = _quote_cmd(solver_cmd)
            row["compare_command"] = _quote_cmd(cmp_cmd) if cmp_cmd else ""
            solver_script_lines.append(" \\\n  ".join(solver_cmd))
            solver_script_lines.append("")
            if cmp_cmd:
                compare_script_lines.append(" \\\n  ".join(cmp_cmd))
                compare_script_lines.append("")
            if run_solver:
                env = os.environ.copy()
                env["PYTHONPATH"] = "src" + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
                subprocess.run([str(x) for x in solver_cmd[1:]], check=True, env=env)
                if cmp_cmd:
                    subprocess.run([str(x) for x in cmp_cmd[1:]], check=True, env=env)
                row.update(_read_solver_after_run(Path(out_name)))
        case_rows.append(row)

    for tag in ions:
        info = ION_INFO[tag]
        zone_candidates: list[dict[str, Any]] = []
        matching_tag_rows: list[dict[str, Any]] = []
        for xp in xout_files:
            rows = _candidate_zone_rows(xp, tag)
            if not rows:
                continue
            for row in rows:
                row["ion"] = info["ion"]
                row["tag"] = tag
                all_zone_rows.append(row)
            zone_candidates.extend(rows)
            if _case_tag_from_path(xp) == tag:
                matching_tag_rows.extend(rows)
        # Use the ion's own XSTAR target grid when available (Mg/Ca here).
        # For C/O in the supplied Mg/Ca xout tree, no matching-tag rows exist;
        # we keep one global zero-fraction diagnostic row instead of producing
        # misleading commands for every Mg/Ca grid file.
        source_rows = matching_tag_rows if matching_tag_rows else zone_candidates
        source_rows = _filter_logxi(source_rows, logxi)
        if not source_rows:
            add_case(tag, None)
            continue
        if selection_mode == "max":
            add_case(tag, _choose_zone(source_rows), case_rank=1)
        elif selection_mode == "grid":
            if matching_tag_rows:
                chosen_rows = _choose_one_zone_per_xout(source_rows)
            else:
                # No C/O-specific xout grid is present in the supplied Mg/Ca
                # tree; report a single global maximum/zero diagnostic row
                # instead of duplicating the Mg/Ca grid as if it were a C/O
                # validation target.
                chosen = _choose_zone(source_rows)
                chosen_rows = [chosen] if chosen is not None else []
            for idx, zone in enumerate(chosen_rows, start=1):
                add_case(tag, zone, case_rank=idx)
        else:
            raise ValueError(f"unknown selection_mode: {selection_mode}")

    summary = {
        "n_requested_ions": len(ions),
        "n_xout_abund1_files_scanned": len(xout_files),
        "n_cases": len(case_rows),
        "n_cases_with_local_state": sum(1 for r in case_rows if r.get("status") == "local_state_selected"),
        "n_cases_with_solver_command": sum(1 for r in case_rows if r.get("solver_command")),
        "selection_mode": selection_mode,
        "requested_log_xi": logxi,
        "run_solver": run_solver,
        "atdb": atdb or "",
        "xstar_runs_root": str(xstar_runs_root),
        "target_root": str(target_root) if target_root else "",
        "policy": "use XSTAR xout_abund1.fits local T/ne/logxi before judging He-like triplet f/i/r; no empirical triplet scale fitting",
    }
    return case_rows, all_zone_rows, solver_script_lines, compare_script_lines, summary


def write_markdown(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# He-like local-state validation plan\n")
    lines.append("This diagnostic examines whether C V, O VII, Mg XI, and Ca XIX can be rerun with the local XSTAR zone state from `xout_abund1.fits`. It does not fit triplet scale factors.\n")
    lines.append("## Summary\n")
    for key, val in summary.items():
        lines.append(f"- `{key}`: `{val}`")
    lines.append("\n## Cases\n")
    for r in rows:
        lines.append(f"### {r.get('ion')}\n")
        lines.append(f"- status: `{r.get('status')}`")
        lines.append(f"- selected xout: `{r.get('xstar_abund_path', '')}`")
        lines.append(f"- zone: `{r.get('zone_index', '')}`")
        lines.append(f"- local T: `{r.get('xstar_temperature_K', '')}` K")
        lines.append(f"- local ne: `{r.get('xstar_electron_density_cm^-3', '')}` cm^-3")
        lines.append(f"- local log xi: `{r.get('xstar_log_xi_local', '')}`")
        lines.append(f"- He-like fraction: `{r.get('xstar_helike_fraction', '')}`")
        lines.append(f"- target CSV found: `{r.get('target_csv_found', '')}`")
        if r.get("xstar_target_f_fraction") is not None:
            lines.append(f"- XSTAR target f/i/r: `{r.get('xstar_target_f_fraction')}` / `{r.get('xstar_target_i_fraction')}` / `{r.get('xstar_target_r_fraction')}`")
        lines.append(f"- recommended action: {r.get('recommended_action', '')}")
        if r.get("solver_command"):
            lines.append("\nSolver command:\n")
            lines.append("```bash")
            lines.append(str(r.get("solver_command")))
            lines.append("```")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--xstar-runs-root", default="xstar_runs", help="Root containing XSTAR run directories with xout_abund1.fits.")
    p.add_argument("--target-root", default=".", help="Root containing xstar_test_run triplet target CSVs.")
    p.add_argument("--ions", default="c5,o7,mg11,ca19", help="Comma-separated tags: c5,o7,mg11,ca19.")
    p.add_argument("--atdb", default="", help="Path to atdb.fits. If supplied, runnable solver commands are generated.")
    p.add_argument("--run-solver", action="store_true", help="Execute generated solver and comparison commands. Requires --atdb.")
    p.add_argument("--version-label", default="v03119", help="Label embedded in generated output directories.")
    p.add_argument("--selection-mode", choices=["grid", "max"], default="grid", help="grid: one max-fraction zone per xout file; max: one global max-fraction zone per ion.")
    p.add_argument("--log-xi", type=float, default=None, help="Optional log10(xi) filter, e.g. 3.0 for a single local-state comparison.")
    p.add_argument("--out-dir", default="helike_local_state_validation_v03119")
    p.add_argument("--python-exe", default="python")
    p.add_argument("--print-summary", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    ions = [t.strip().lower() for t in args.ions.split(",") if t.strip()]
    bad = [t for t in ions if t not in ION_INFO]
    if bad:
        raise SystemExit(f"unknown ion tag(s): {bad}; allowed: {sorted(ION_INFO)}")
    if args.run_solver and not args.atdb:
        raise SystemExit("--run-solver requires --atdb")
    out_dir = Path(args.out_dir)
    rows, zones, solver_script, compare_script, summary = build(
        Path(args.xstar_runs_root),
        Path(args.target_root) if args.target_root else None,
        ions,
        args.atdb or None,
        out_dir,
        args.version_label,
        run_solver=args.run_solver,
        python_exe=args.python_exe,
        selection_mode=args.selection_mode,
        logxi=args.log_xi,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "helike_local_state_cases.csv", rows)
    _write_csv(out_dir / "helike_local_state_zone_candidates.csv", zones)
    (out_dir / "helike_local_state_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(out_dir / "helike_local_state_validation_plan.md", rows, summary)
    run_script = out_dir / "run_helike_local_state_solvers.sh"
    cmp_script = out_dir / "compare_helike_local_state_solvers.sh"
    run_script.write_text("\n".join(solver_script) + "\n", encoding="utf-8")
    cmp_script.write_text("\n".join(compare_script) + "\n", encoding="utf-8")
    run_script.chmod(0o755)
    cmp_script.chmod(0o755)
    if args.print_summary:
        print("He-like local-state validation")
        print("--------------------------------")
        print("This prepares/runs C V, O VII, Mg XI, and Ca XIX at XSTAR xout_abund1.fits local T/ne/log xi; it does not fit triplet scale factors.")
        print(f"cases={summary['n_cases']} local_state={summary['n_cases_with_local_state']} solver_commands={summary['n_cases_with_solver_command']}")
        for r in rows:
            print(f"{r.get('ion')}: status={r.get('status')} T={r.get('xstar_temperature_K')} ne={r.get('xstar_electron_density_cm^-3')} logxi={r.get('xstar_log_xi_local')} frac={r.get('xstar_helike_fraction')}")
        print(f"wrote: {out_dir/'helike_local_state_cases.csv'}")
        print(f"wrote: {out_dir/'helike_local_state_validation_plan.md'}")


if __name__ == "__main__":
    main()
