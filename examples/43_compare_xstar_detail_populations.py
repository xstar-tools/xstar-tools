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
import sys
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


def _classify_triplet_line(row: dict[str, Any]) -> str | None:
    upper_label = str(row.get("upper_label") or row.get("upper_level_label") or row.get("upper_config") or row.get("upper_level") or "")
    lower_label = str(row.get("lower_label") or row.get("lower_level_label") or row.get("lower_config") or row.get("lower_level") or "")
    norm_upper = upper_label.replace(" ", "").lower()
    norm_lower = lower_label.replace(" ", "").lower()
    if "1s2" in norm_lower or not norm_lower:
        if "2s1.3s_1" in norm_upper or "1s1.2s1.3s_1" in norm_upper:
            return "f"
        if "2p1.1p_1" in norm_upper or "1s1.2p1.1p_1" in norm_upper:
            return "r"
        if "2p1.3p_" in norm_upper or "1s1.2p1.3p_" in norm_upper:
            return "i"
    wav = _as_float(row.get("wavelength_A") or row.get("wavelength"))
    upper = _as_int(row.get("upper_level"))
    if wav is not None:
        if abs(wav - 22.1012) < 0.02:
            return "f"
        if abs(wav - 21.8070) < 0.03 or abs(wav - 21.8044) < 0.03:
            return "i"
        if abs(wav - 21.6020) < 0.02:
            return "r"
    if upper == 2:
        return "f"
    if upper in (3, 4, 5):
        return "i"
    if upper == 7:
        return "r"
    return None


def _pescl(tau: float) -> float:
    tau = float(tau or 0.0)
    if tau < 1.0:
        if tau < 1.0e-5:
            val = 1.0
        else:
            aa = 2.0 * tau
            val = (1.0 - math.exp(-aa)) / aa
    else:
        bb = 0.5 * math.sqrt(max(0.0, math.log(tau))) / (1.0 + tau / 1.0e5)
        val = 1.0 / (tau * math.sqrt(math.pi) * (1.2 + bb))
    return 0.5 * val


def _ptmp_from_tau(tau1: float, tau2: float, cfrac: float = 0.0) -> tuple[float, float]:
    cfrac = max(0.0, min(1.0, float(cfrac or 0.0)))
    p1 = _pescl(tau1) * (1.0 - cfrac)
    p2 = _pescl(tau2) * (1.0 - cfrac) + 2.0 * _pescl(tau1 + tau2) * cfrac
    return p1, p2


def _component_summary(vals: dict[str, float]) -> dict[str, Any]:
    f = max(0.0, float(vals.get("f", 0.0) or 0.0))
    i = max(0.0, float(vals.get("i", 0.0) or 0.0))
    r = max(0.0, float(vals.get("r", 0.0) or 0.0))
    total = f + i + r
    return {
        "f_fraction": f / total if total > 0.0 else None,
        "i_fraction": i / total if total > 0.0 else None,
        "r_fraction": r / total if total > 0.0 else None,
        "R": f / i if i > 0.0 else None,
        "G": (f + i) / r if r > 0.0 else None,
        "f_emissivity": f,
        "i_emissivity": i,
        "r_emissivity": r,
        "total_emissivity": total,
    }


def _triplet_target_from_xstar_lines(rows: list[dict[str, Any]], value_column: str) -> dict[str, Any]:
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    for row in rows:
        comp = _classify_triplet_line(row)
        val = _as_float(row.get(value_column))
        if comp in sums and val is not None:
            sums[comp] += max(float(val), 0.0)
    summ = _component_summary(sums)
    return {
        "value_column": value_column,
        "target_f_fraction": summ["f_fraction"],
        "target_i_fraction": summ["i_fraction"],
        "target_r_fraction": summ["r_fraction"],
        "target_R": summ["R"],
        "target_G": summ["G"],
        "target_f_emissivity": sums["f"],
        "target_i_emissivity": sums["i"],
        "target_r_emissivity": sums["r"],
    }


def _match_reference_line(line: dict[str, Any], refs: list[dict[str, Any]], tol: float = 0.035) -> dict[str, Any] | None:
    comp = _classify_triplet_line(line)
    wav = _as_float(line.get("wavelength_A") or line.get("wavelength"))
    if comp is None or wav is None:
        return None
    best = None
    best_dw = float("inf")
    for ref in refs:
        if _classify_triplet_line(ref) != comp:
            continue
        rwav = _as_float(ref.get("wavelength_A") or ref.get("wavelength"))
        if rwav is None:
            continue
        dw = abs(float(wav) - float(rwav))
        if dw < best_dw:
            best = ref
            best_dw = dw
    if best is None or best_dw > tol:
        return None
    out = dict(best)
    out["match_delta_wavelength_A"] = best_dw
    return out


def _build_xstar_reference_depth_postprocess(
    solver_out_dir: Path,
    xstar_lines_csv: Path | None,
    value_column: str = "emit_outward",
    depth_scale: float = 1.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if xstar_lines_csv is None:
        return {}, []
    xstar_rows = _read_csv(xstar_lines_csv)
    line_path = solver_out_dir / "xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv"
    if not line_path.exists():
        return {}, []
    solver_lines = [r for r in _read_csv(line_path) if r.get("row_kind") == "calc_emis_ion_triplet_emergent_line"]
    depth_scale = max(0.0, float(depth_scale))
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    detail_rows: list[dict[str, Any]] = []
    for line in solver_lines:
        comp = _classify_triplet_line(line)
        if comp not in sums:
            continue
        raw = _as_float(line.get("raw_pop_A_E_erg_s^-1"))
        if raw is None:
            raw = _as_float(line.get("transparent_calc_emis_fline_total_erg_s^-1"))
        if raw is None:
            continue
        ref = _match_reference_line(line, xstar_rows)
        if ref is None:
            continue
        tau1 = depth_scale * max(0.0, float(_as_float(ref.get("depth_inward")) or 0.0))
        tau2 = depth_scale * max(0.0, float(_as_float(ref.get("depth_outward")) or 0.0))
        p1, p2 = _ptmp_from_tau(tau1, tau2, 0.0)
        # emit_outward corresponds to calc_emis fline(2): ans2=A*(ptmp1+ptmp2),
        # then fline(2)=(ans2*n_upper)*E*ptmp2.  Since raw=n_upper*A*E,
        # the validation-only reference-depth outward value is raw*(ptmp1+ptmp2)*ptmp2.
        corrected = max(float(raw), 0.0) * (p1 + p2) * p2
        sums[comp] += corrected
        detail_rows.append({
            "row_kind": "xstar_reference_depth_postprocess_line",
            "component": comp,
            "record": line.get("record", ""),
            "wavelength_A": line.get("wavelength_A", ""),
            "upper_level": line.get("upper_level", ""),
            "raw_pop_A_E_erg_s^-1": raw,
            "xstar_reference_value_column": value_column,
            "xstar_reference_value": ref.get(value_column, ""),
            "xstar_reference_depth_inward": ref.get("depth_inward", ""),
            "xstar_reference_depth_outward": ref.get("depth_outward", ""),
            "xstar_reference_depth_scale": depth_scale,
            "scaled_tau1": tau1,
            "scaled_tau2": tau2,
            "ptmp1": p1,
            "ptmp2": p2,
            "corrected_emit_outward_erg_s^-1": corrected,
            "attenuation_vs_raw": corrected / raw if raw else "",
            "match_delta_wavelength_A": ref.get("match_delta_wavelength_A", ""),
        })
    corrected_summary = _component_summary(sums)
    target_summary = _triplet_target_from_xstar_lines(xstar_rows, value_column)
    l2 = None
    if all(corrected_summary.get(k) is not None and target_summary.get("target_" + k) is not None for k in ("f_fraction", "i_fraction", "r_fraction")):
        l2 = math.sqrt(sum((float(corrected_summary[k]) - float(target_summary["target_" + k])) ** 2 for k in ("f_fraction", "i_fraction", "r_fraction")))
    summary = {
        "comparison_case": "full_global_xstar_reference_depth_emit_outward_calc_emis_ion",
        "xstar_lines_csv": str(xstar_lines_csv),
        "xstar_value_column": value_column,
        "xstar_reference_depth_scale": depth_scale,
        "f_fraction": corrected_summary["f_fraction"],
        "i_fraction": corrected_summary["i_fraction"],
        "r_fraction": corrected_summary["r_fraction"],
        "R": corrected_summary["R"],
        "G": corrected_summary["G"],
        "l2_distance_to_target": l2,
        **target_summary,
    }
    detail_rows.append({"row_kind": "xstar_reference_depth_postprocess_summary", **summary})
    return summary, detail_rows


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
        deltas: list[float] = []
        for comp in ("f", "i", "r"):
            val = out.get(f"{comp}_fraction")
            ref = target.get(comp)
            out[f"target_{comp}_fraction"] = ref
            delta = None if val is None or ref is None else val - ref
            out[f"delta_{comp}_fraction"] = delta
            if delta is not None:
                deltas.append(float(delta))
        if len(deltas) == 3:
            out["l2_distance_to_target"] = math.sqrt(sum(delta * delta for delta in deltas))
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
    p.add_argument("--xstar-triplet-lines-csv", help="Optional converted XSTAR triplet line CSV, e.g. xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv. When supplied, this script derives target f/i/r and a validation-only reference-depth emit_outward postprocess.")
    p.add_argument("--xstar-value-column", default="emit_outward", help="Column in --xstar-triplet-lines-csv used as the XSTAR target. Default emit_outward.")
    p.add_argument(
        "--xstar-reference-depth-scale",
        type=float,
        default=None,
        help="Scale applied to XSTAR depth_inward/depth_outward before the validation-only pescl postprocess. Default 1; when omitted in the O VII ne=1e8 reference-depth validation mode, a warning is printed because the validated scale was 0.37.",
    )
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
    explicit_cli_target = all(math.isfinite(x) for x in (args.target_f, args.target_i, args.target_r))
    if explicit_cli_target:
        target = {"f": args.target_f, "i": args.target_i, "r": args.target_r}
    xstar_reference_summary: dict[str, Any] = {}
    xstar_reference_rows: list[dict[str, Any]] = []
    xstar_target_summary: dict[str, Any] = {}
    if args.xstar_triplet_lines_csv:
        xstar_rows_for_target = _read_csv(Path(args.xstar_triplet_lines_csv))
        xstar_target_summary = _triplet_target_from_xstar_lines(xstar_rows_for_target, args.xstar_value_column)
        # When a real converted XSTAR triplet CSV is supplied, prefer its
        # target fractions over the historical built-in C V defaults.  This is
        # essential for Mg XI/Ca XIX validation, where the C V defaults are
        # physically meaningless.  Explicit --target-f/i/r values still work
        # when no XSTAR CSV is provided.
        if all(xstar_target_summary.get(f"target_{comp}_fraction") is not None for comp in ("f", "i", "r")):
            target = {
                "f": float(xstar_target_summary["target_f_fraction"]),
                "i": float(xstar_target_summary["target_i_fraction"]),
                "r": float(xstar_target_summary["target_r_fraction"]),
            }
    triplet_summary = _build_triplet_payload(_load_recommended_triplet_summary(solver_out_dir, args.comparison_case), target)
    reference_depth_scale = 1.0 if args.xstar_reference_depth_scale is None else args.xstar_reference_depth_scale
    if (
        args.xstar_triplet_lines_csv
        and args.comparison_case == "full_global_xstar_reference_depth_emit_outward_calc_emis_ion"
        and args.xstar_reference_depth_scale is None
    ):
        print(
            "Warning: Using default depth scale 1.0; O VII ne=1e8 validation used 0.37.",
            file=sys.stderr,
        )
    if args.xstar_triplet_lines_csv:
        xstar_reference_summary, xstar_reference_rows = _build_xstar_reference_depth_postprocess(
            solver_out_dir,
            Path(args.xstar_triplet_lines_csv),
            args.xstar_value_column,
            reference_depth_scale,
        )
        if args.comparison_case == xstar_reference_summary.get("comparison_case"):
            triplet_summary = {
                "comparison_case": xstar_reference_summary.get("comparison_case"),
                "f_fraction": xstar_reference_summary.get("f_fraction"),
                "i_fraction": xstar_reference_summary.get("i_fraction"),
                "r_fraction": xstar_reference_summary.get("r_fraction"),
                "R": xstar_reference_summary.get("R"),
                "G": xstar_reference_summary.get("G"),
                "l2_distance_to_target": xstar_reference_summary.get("l2_distance_to_target"),
                "target_f_fraction": xstar_reference_summary.get("target_f_fraction"),
                "target_i_fraction": xstar_reference_summary.get("target_i_fraction"),
                "target_r_fraction": xstar_reference_summary.get("target_r_fraction"),
                "delta_f_fraction": None if xstar_reference_summary.get("f_fraction") is None or xstar_reference_summary.get("target_f_fraction") is None else xstar_reference_summary.get("f_fraction") - xstar_reference_summary.get("target_f_fraction"),
                "delta_i_fraction": None if xstar_reference_summary.get("i_fraction") is None or xstar_reference_summary.get("target_i_fraction") is None else xstar_reference_summary.get("i_fraction") - xstar_reference_summary.get("target_i_fraction"),
                "delta_r_fraction": None if xstar_reference_summary.get("r_fraction") is None or xstar_reference_summary.get("target_r_fraction") is None else xstar_reference_summary.get("r_fraction") - xstar_reference_summary.get("target_r_fraction"),
            }

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
        "xstar_reference_triplet": xstar_reference_summary,
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
    if xstar_reference_rows:
        _write_csv(solver_out_dir / "xstar_reference_depth_triplet_postprocess.csv", xstar_reference_rows)
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
        if xstar_reference_rows:
            print(f"wrote: {solver_out_dir / 'xstar_reference_depth_triplet_postprocess.csv'}")


if __name__ == "__main__":
    main()
