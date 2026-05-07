#!/usr/bin/env python3
"""Compare xstar-atomic full-global populations with XSTAR detail populations.

This utility is intended for the Step-1 validation stage after the C V
full-global/emergent triplet path has been calibrated against XSTAR.  It reads
an output directory produced by ``examples/42_xstar_like_element_solver_demo.py``
and, optionally, an external XSTAR detail population table converted to CSV or
stored in a FITS binary table.

The comparison is deliberately conservative:

* without an external detail table, it writes a self-contained solver population
  summary and the recommended triplet comparison row;
* with an external detail table, it matches rows by ion stage and level index
  when those columns are available, and reports ratios/differences without
  changing any solver result;
* C V is the default validation target, but the same interface supports O VII
  by passing ``--element O --he-like-stage 7`` and an O VII solver output folder.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

RECOMMENDED_CASE = "full_global_xstar_tau0_calc_emis_ion"
DEFAULT_CV_TARGET = {"f": 0.807707, "i": 0.006633, "r": 0.185660}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "--"}:
        return None
    try:
        x = float(text)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _as_int(value: Any) -> int | None:
    x = _as_float(value)
    if x is None:
        return None
    return int(round(x))


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_fits_table(path: Path) -> list[dict[str, Any]]:
    from astropy.io import fits

    with fits.open(path) as hdul:
        for hdu in hdul[1:]:
            data = getattr(hdu, "data", None)
            names = getattr(data, "names", None)
            if data is None or not names:
                continue
            rows: list[dict[str, Any]] = []
            for rec in data:
                row: dict[str, Any] = {}
                for name in names:
                    value = rec[name]
                    if hasattr(value, "item"):
                        try:
                            value = value.item()
                        except Exception:
                            pass
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", errors="replace")
                    row[str(name)] = value
                rows.append(row)
            if rows:
                return rows
    return []


def _read_table(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".fits", ".fit", ".fts"}:
        return _read_fits_table(path)
    return _read_csv(path)


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _canonical_column_map(row: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key in row:
        canon = str(key).strip().lower().replace(" ", "_").replace("-", "_")
        mapping[canon] = key
    return mapping


def _get(row: dict[str, Any], cmap: dict[str, str], *names: str) -> Any:
    for name in names:
        key = cmap.get(name.lower())
        if key is not None:
            return row.get(key)
    return None


def _normalize_detail_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        cmap = _canonical_column_map(row)
        ion_stage = _as_int(_get(row, cmap, "ion_stage", "stage", "ionstage", "ion_stage_number", "ion"))
        level_index = _as_int(_get(row, cmap, "level_index", "level", "level_number", "nlev", "ilev", "level_id"))
        population = _as_float(_get(row, cmap, "population", "population_fraction", "xileve", "xilev", "pop", "level_population", "frac"))
        label = _get(row, cmap, "level_label", "label", "configuration", "config", "level_name", "name")
        out.append(
            {
                "xstar_ion_stage": ion_stage,
                "xstar_level_index": level_index,
                "xstar_level_label": "" if label is None else str(label),
                "xstar_detail_population": population,
                "xstar_detail_raw_json": json.dumps({str(k): str(v) for k, v in row.items()}, sort_keys=True),
            }
        )
    return out


def _load_solver_population_rows(solver_out_dir: Path, element: str, he_like_stage: int) -> list[dict[str, Any]]:
    full = solver_out_dir / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv"
    if not full.exists():
        raise FileNotFoundError(f"Missing solver full-global file: {full}")
    rows = _read_csv(full)
    pop_rows = [row for row in rows if str(row.get("row_kind", "")).strip() == "population"]
    if not pop_rows:
        raise RuntimeError(f"No population rows found in {full}")

    # Add global-index metadata, including configuration strings, when available.
    index_path = solver_out_dir / "xstar_like_element_solver_global_index.csv"
    index_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    if index_path.exists():
        for row in _read_csv(index_path):
            key = (_as_int(row.get("ion_stage")) or -1, _as_int(row.get("level_index")) or -1)
            index_by_key[key] = row

    out: list[dict[str, Any]] = []
    for row in pop_rows:
        ion_stage = _as_int(row.get("ion_stage"))
        level_index = _as_int(row.get("level_index"))
        if ion_stage is None or level_index is None:
            continue
        idx = index_by_key.get((ion_stage, level_index), {})
        solver_population = _as_float(row.get("xstar_xileve_emissivity_population"))
        if solver_population is None:
            solver_population = _as_float(row.get("population_fraction"))
        out.append(
            {
                "element": element,
                "he_like_stage": he_like_stage,
                "solver_ion_stage": ion_stage,
                "solver_level_index": level_index,
                "solver_global_index": row.get("global_index", ""),
                "solver_level_kind": row.get("level_kind", idx.get("level_kind", "")),
                "solver_triplet_component": row.get("triplet_component", idx.get("triplet_component", "")),
                "solver_is_triplet_upper": row.get("is_triplet_upper", idx.get("is_triplet_upper", "")),
                "solver_is_superlevel": row.get("is_superlevel", idx.get("is_superlevel", "")),
                "solver_is_continuum": row.get("is_continuum", idx.get("is_continuum", "")),
                "solver_level_label": row.get("level_label", idx.get("level_label", idx.get("configuration", ""))),
                "solver_configuration": idx.get("configuration", row.get("level_label", "")),
                "solver_population_fraction": _as_float(row.get("population_fraction")),
                "solver_xileve_emissivity_population": _as_float(row.get("xstar_xileve_emissivity_population")),
                "solver_bileve_departure_coefficient": _as_float(row.get("xstar_bileve_departure_coefficient")),
                "solver_rnise": _as_float(row.get("xstar_levwkelement_rnise")),
                "solver_nsup": row.get("xstar_nsup", ""),
                "solver_p_superlevel": _as_float(row.get("xstar_superlevel_population_p")),
                "solver_rr_within_superlevel": _as_float(row.get("xstar_rr_fraction_within_superlevel")),
            }
        )
    return out


def _load_recommended_triplet_summary(solver_out_dir: Path, comparison_case: str) -> dict[str, Any]:
    candidates = [
        solver_out_dir / "xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv",
        solver_out_dir / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        rows = _read_csv(path)
        for row in rows:
            if str(row.get("row_kind", "")).strip() == "summary" and str(row.get("comparison_case", "")).strip() == comparison_case:
                return row
    return {}


def _merge_with_xstar_detail(solver_rows: list[dict[str, Any]], detail_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detail_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for row in detail_rows:
        ion_stage = row.get("xstar_ion_stage")
        level_index = row.get("xstar_level_index")
        if ion_stage is None or level_index is None:
            continue
        detail_by_key[(int(ion_stage), int(level_index))] = row

    merged: list[dict[str, Any]] = []
    for srow in solver_rows:
        key = (int(srow["solver_ion_stage"]), int(srow["solver_level_index"]))
        drow = detail_by_key.get(key, {})
        solver_pop = _as_float(srow.get("solver_xileve_emissivity_population"))
        if solver_pop is None:
            solver_pop = _as_float(srow.get("solver_population_fraction"))
        xstar_pop = _as_float(drow.get("xstar_detail_population"))
        ratio = None
        delta = None
        abs_delta = None
        if solver_pop is not None and xstar_pop is not None:
            delta = solver_pop - xstar_pop
            abs_delta = abs(delta)
            if xstar_pop != 0.0:
                ratio = solver_pop / xstar_pop
        merged.append(
            {
                **srow,
                "xstar_detail_match_status": "matched_ion_stage_level_index" if drow else "no_xstar_detail_match",
                "xstar_detail_population": xstar_pop,
                "xstar_detail_level_label": drow.get("xstar_level_label", ""),
                "solver_minus_xstar_detail_population": delta,
                "abs_solver_minus_xstar_detail_population": abs_delta,
                "solver_over_xstar_detail_population": ratio,
            }
        )
    return merged


def _build_triplet_payload(summary: dict[str, Any], target: dict[str, float] | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "comparison_case": summary.get("comparison_case", ""),
        "f_fraction": _as_float(summary.get("f_fraction")),
        "i_fraction": _as_float(summary.get("i_fraction")),
        "r_fraction": _as_float(summary.get("r_fraction")),
        "R": _as_float(summary.get("R")),
        "G": _as_float(summary.get("G")),
        "l2_distance_to_target": _as_float(summary.get("l2_distance_to_target")),
    }
    if target:
        for comp in ("f", "i", "r"):
            val = out.get(f"{comp}_fraction")
            ref = target.get(comp)
            out[f"target_{comp}_fraction"] = ref
            out[f"delta_{comp}_fraction"] = None if val is None or ref is None else val - ref
    return out


def _write_markdown(path: Path, payload: dict[str, Any], comparison_rows: list[dict[str, Any]]) -> None:
    trip = payload.get("triplet", {})
    lines = [
        "# XSTAR detail population comparison",
        "",
        f"Solver output directory: `{payload.get('solver_out_dir', '')}`",
        f"Element / He-like stage: `{payload.get('element', '')}` / `{payload.get('he_like_stage', '')}`",
        f"Recommended triplet comparison case: `{payload.get('comparison_case', RECOMMENDED_CASE)}`",
        "",
        "## Triplet summary",
        "",
        "| quantity | value |",
        "|---|---:|",
    ]
    for key in ("f_fraction", "i_fraction", "r_fraction", "R", "G", "l2_distance_to_target", "target_f_fraction", "target_i_fraction", "target_r_fraction", "delta_f_fraction", "delta_i_fraction", "delta_r_fraction"):
        if key in trip:
            lines.append(f"| {key} | {trip.get(key)} |")
    lines += [
        "",
        "## Population comparison status",
        "",
        f"External XSTAR detail file: `{payload.get('xstar_detail_file') or 'not provided'}`",
        f"Rows written: `{len(comparison_rows)}`",
        f"Matched rows: `{payload.get('n_matched_rows', 0)}`",
        "",
        "The CSV output contains one row per solver population level, with XSTAR detail columns populated when an external detail table was supplied and matched by ion stage plus level index.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare xstar-atomic full-global populations with XSTAR detail populations.")
    p.add_argument("--solver-out-dir", required=True, help="Output directory from examples/42_xstar_like_element_solver_demo.py")
    p.add_argument("--xstar-detail", help="Optional XSTAR detail population CSV/FITS table")
    p.add_argument("--element", default="C")
    p.add_argument("--he-like-stage", type=int, default=5)
    p.add_argument("--comparison-case", default=RECOMMENDED_CASE)
    p.add_argument("--out-csv", default="xstar_detail_population_comparison.csv")
    p.add_argument("--out-json", default="xstar_detail_population_comparison_summary.json")
    p.add_argument("--out-md", default="xstar_detail_population_comparison.md")
    p.add_argument("--target-f", type=float, default=DEFAULT_CV_TARGET["f"], help="Target forbidden fraction; use NaN to omit")
    p.add_argument("--target-i", type=float, default=DEFAULT_CV_TARGET["i"], help="Target intercombination fraction; use NaN to omit")
    p.add_argument("--target-r", type=float, default=DEFAULT_CV_TARGET["r"], help="Target resonance fraction; use NaN to omit")
    p.add_argument("--print-summary", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    solver_out_dir = Path(args.solver_out_dir)
    if not solver_out_dir.exists():
        raise SystemExit(f"Solver output directory does not exist: {solver_out_dir}")

    solver_rows = _load_solver_population_rows(solver_out_dir, args.element, args.he_like_stage)
    detail_rows: list[dict[str, Any]] = []
    if args.xstar_detail:
        detail_rows = _normalize_detail_rows(_read_table(Path(args.xstar_detail)))
    comparison_rows = _merge_with_xstar_detail(solver_rows, detail_rows)

    target = None
    if all(math.isfinite(x) for x in (args.target_f, args.target_i, args.target_r)):
        target = {"f": args.target_f, "i": args.target_i, "r": args.target_r}
    triplet_summary = _build_triplet_payload(_load_recommended_triplet_summary(solver_out_dir, args.comparison_case), target)

    n_matched = sum(row.get("xstar_detail_match_status") == "matched_ion_stage_level_index" for row in comparison_rows)
    payload = {
        "solver_out_dir": str(solver_out_dir),
        "xstar_detail_file": args.xstar_detail or "",
        "element": args.element,
        "he_like_stage": args.he_like_stage,
        "comparison_case": args.comparison_case,
        "n_solver_population_rows": len(solver_rows),
        "n_xstar_detail_rows": len(detail_rows),
        "n_matched_rows": n_matched,
        "triplet": triplet_summary,
        "recommended_next_validation": "Run this same comparison for O VII with --element O --he-like-stage 7 after generating an O VII full-global solver output directory.",
    }

    out_csv = Path(args.out_csv)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not out_csv.is_absolute():
        out_csv = solver_out_dir / out_csv
    if not out_json.is_absolute():
        out_json = solver_out_dir / out_json
    if not out_md.is_absolute():
        out_md = solver_out_dir / out_md
    _write_csv(out_csv, comparison_rows)
    _write_json(out_json, payload)
    _write_markdown(out_md, payload, comparison_rows)

    if args.print_summary:
        print("XSTAR detail population comparison")
        print("---------------------------------")
        print(f"solver_out_dir={solver_out_dir}")
        print(f"comparison_case={args.comparison_case}")
        print(
            "triplet f/i/r="
            f"{triplet_summary.get('f_fraction')}/"
            f"{triplet_summary.get('i_fraction')}/"
            f"{triplet_summary.get('r_fraction')} "
            f"R={triplet_summary.get('R')} G={triplet_summary.get('G')} "
            f"L2={triplet_summary.get('l2_distance_to_target')}"
        )
        print(f"solver population rows={len(solver_rows)}")
        if args.xstar_detail:
            print(f"xstar detail rows={len(detail_rows)} matched={n_matched}")
        else:
            print("xstar detail rows=not provided; wrote solver-only population summary")
        print(f"wrote: {out_csv}")
        print(f"wrote: {out_json}")
        print(f"wrote: {out_md}")


if __name__ == "__main__":
    main()
