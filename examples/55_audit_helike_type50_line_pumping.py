#!/usr/bin/env python3
"""
Audit the missing XSTAR type-50 bound-bound photoexcitation / line-pumping path.

This diagnostic follows the all-ion local-state validation after matching XSTAR
``xout_abund1.fits`` local ``T`` and ``ne``.  It does not fit or apply a scale
factor.  Instead, it records the source-code formula used by XSTAR's
``ucalc.f90`` type-50 branch and compares it with the current Python matrix,
which presently includes escaped downward type-50 decay but normally has zero
upward photoexcitation unless the old diagnostic proxy is explicitly enabled.

The key XSTAR source-code relation is, before the universal ans1/ans2 swap in
``ucalc.f90`` type 50::

    ans1 = A_ij * (ptmp1 + ptmp2)             ! escaped downward decay
    sigma = 0.02655 * f_line * lambda_cm / v_therm
    ans2 = sigma * bremsa(nb1) * v_therm / c * flinabs(ptmp1) * (1-cfrac)

After the swap near the end of the branch, ``ans1`` is the lower-to-upper
photoexcitation matrix rate and ``ans2`` is the upper-to-lower escaped decay
rate.  The present audit identifies which ingredients are already present and
which remain absent from the Python solver outputs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(text)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _to_int(value: Any) -> int | None:
    x = _to_float(value)
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_solver_dir(case: dict[str, str], solver_root: Path) -> Path | None:
    name = case.get("recommended_solver_out_dir") or case.get("solver_out_dir") or ""
    if name:
        p = Path(name)
        if p.is_absolute() and p.exists():
            return p
        q = solver_root / p
        if q.exists():
            return q
    tag = (case.get("tag") or "").lower()
    if tag:
        for p in sorted(solver_root.glob(f"{tag}_xstar_like_element_solver_*")):
            if (p / "xstar_like_element_solver_full_global_matrix_terms.csv").exists():
                return p
    return None


def _triplet_from_summary(solver_dir: Path) -> dict[str, Any]:
    summary = _read_json(solver_dir / "xstar_detail_population_comparison_summary.json")
    t = summary.get("triplet", {}) if isinstance(summary, dict) else {}
    out: dict[str, Any] = {}
    for src, dst in [
        ("f_fraction", "solver_f"), ("i_fraction", "solver_i"), ("r_fraction", "solver_r"),
        ("target_f_fraction", "target_f"), ("target_i_fraction", "target_i"), ("target_r_fraction", "target_r"),
        ("R", "solver_R"), ("G", "solver_G"), ("target_R", "target_R"), ("target_G", "target_G"),
        ("l2_distance_to_target", "l2"),
    ]:
        out[dst] = _to_float(t.get(src))
    if out.get("solver_r") is not None and out.get("target_r") is not None:
        out["delta_r"] = out["solver_r"] - out["target_r"]
    if out.get("solver_f") is not None and out.get("target_f") is not None:
        out["delta_f"] = out["solver_f"] - out["target_f"]
    if out.get("solver_i") is not None and out.get("target_i") is not None:
        out["delta_i"] = out["solver_i"] - out["target_i"]
    return out


def _compact_label(text: Any) -> str:
    return str(text or "").replace(" ", "")


def _is_resonance_upper_label(text: Any) -> bool:
    compact = _compact_label(text)
    return "1s1.2p1.1P_1" in compact or "1s2p1P" in compact or "2p1.1P_1" in compact


def _is_ground_label(text: Any) -> bool:
    compact = _compact_label(text)
    return "1s2.1S_0" in compact or "1s2_1S" in compact or compact.endswith("1S_0")


def _is_resonance_line_row(row: dict[str, str]) -> bool:
    text = " ".join(str(row.get(k) or "") for k in row)
    return _is_resonance_upper_label(text)


def _line_role(row: dict[str, str]) -> str:
    text = " ".join(str(row.get(k) or "") for k in row)
    if _is_resonance_upper_label(text):
        return "r"
    compact = _compact_label(text)
    if "1s1.2s1.3S_1" in compact or "1s2s3S" in compact:
        return "f"
    if "1s1.2p1.3P" in compact or "1s2p3P" in compact:
        return "i"
    return "unknown"


def _resolve_existing_path(text: str, *, base_dir: Path | None = None) -> Path | None:
    if not text:
        return None
    p = Path(text)
    candidates = [p]
    if base_dir is not None and not p.is_absolute():
        candidates.append(base_dir / p)
        # Many case tables store paths relative to the run directory parent.
        candidates.append(base_dir.parent / p)
    for q in candidates:
        try:
            if q.exists():
                return q
        except Exception:
            pass
    return None


def _find_resonance_target_row(case: dict[str, str], *, case_base_dir: Path | None = None) -> dict[str, str] | None:
    csv_path = case.get("target_csv_path") or case.get("xstar_target_csv") or ""
    p = _resolve_existing_path(csv_path, base_dir=case_base_dir)
    if p is None:
        return None
    rows = _read_csv(p)
    for row in rows:
        if _line_role(row) == "r":
            return row
    # Fallback: choose row with largest depth if labels are unavailable.
    candidates = []
    for row in rows:
        depth = max(_to_float(row.get("depth_inward")) or 0.0, _to_float(row.get("depth_outward")) or 0.0)
        candidates.append((depth, row))
    if candidates:
        return sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]
    return None


def _find_resonance_type50_terms(solver_dir: Path) -> list[dict[str, str]]:
    terms = _read_csv(solver_dir / "xstar_like_element_solver_full_global_matrix_terms.csv")
    if not terms:
        terms = _read_csv(solver_dir / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv")
    out = []
    for row in terms:
        if str(row.get("matrix_term_kind") or "") != "offdiag_gain":
            continue
        if str(row.get("data_type") or row.get("resonance_collisional_feed_data_type") or "") not in {"50", "50.0"}:
            continue
        if _is_resonance_upper_label(row.get("from_level_label")) and _is_ground_label(row.get("to_level_label")):
            # emitted line direction upper -> lower; photoexcitation would be reverse.
            out.append(row)
        elif _is_resonance_upper_label(row.get("to_level_label")) or _is_resonance_upper_label(row.get("from_level_label")):
            out.append(row)
    return out


def _sum_photoexcitation_into_resonance(solver_dir: Path) -> float:
    total = 0.0
    terms = _read_csv(solver_dir / "xstar_like_element_solver_full_global_matrix_terms.csv")
    if not terms:
        terms = _read_csv(solver_dir / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv")
    for row in terms:
        if str(row.get("matrix_term_kind") or "") != "offdiag_gain":
            continue
        if _is_resonance_upper_label(row.get("to_level_label")) or _is_resonance_upper_label(row.get("destination_level_label")):
            total += _to_float(row.get("photoexcitation_rate_s^-1")) or 0.0
    return total


def _source_lines_available(xstar_source_root: Path | None) -> dict[str, Any]:
    if not xstar_source_root:
        return {}
    ucalc = None
    for p in xstar_source_root.rglob("ucalc.f90"):
        ucalc = p
        break
    if not ucalc:
        return {"xstar_ucalc_found": False}
    return {
        "xstar_ucalc_found": True,
        "xstar_ucalc_path": str(ucalc),
        "xstar_type50_branch_lines": "ucalc.f90 around type 50: ans1=A*(ptmp1+ptmp2); sigma=0.02655*fline*lambda_cm/vtherm; ans2=sigma*bremsa(nb1)*vtherm/3e10*flinabs(ptmp1)*(1-cfrac); final swap maps ans1 to photoexcitation and ans2 to escaped decay",
    }


def _audit_case(case: dict[str, str], solver_root: Path, xstar_source_info: dict[str, Any], *, case_base_dir: Path | None = None) -> dict[str, Any]:
    solver_dir = _find_solver_dir(case, solver_root)
    out: dict[str, Any] = {
        "ion": case.get("ion"),
        "tag": case.get("tag"),
        "solver_out_dir": str(solver_dir) if solver_dir else "",
        "xstar_temperature_K": _to_float(case.get("xstar_temperature_K")),
        "xstar_electron_density_cm^-3": _to_float(case.get("xstar_electron_density_cm^-3")),
        "xstar_log_xi_local": _to_float(case.get("xstar_log_xi_local")),
        "xstar_helike_fraction": _to_float(case.get("xstar_helike_fraction")),
        "xstar_lines_fits_path": case.get("xstar_lines_fits_path"),
        "target_csv_path": case.get("target_csv_path") or case.get("xstar_target_csv"),
    }
    out.update(xstar_source_info)
    if solver_dir is None:
        out["status"] = "missing_solver_dir"
        return out
    out.update(_triplet_from_summary(solver_dir))
    line = _find_resonance_target_row(case, case_base_dir=case_base_dir)
    if line:
        out["xstar_resonance_wavelength_A"] = _to_float(line.get("wavelength") or line.get("wavelength_A"))
        out["xstar_resonance_emit_outward"] = _to_float(line.get("emit_outward"))
        out["xstar_resonance_depth_inward"] = _to_float(line.get("depth_inward"))
        out["xstar_resonance_depth_outward"] = _to_float(line.get("depth_outward"))
        out["xstar_resonance_line_label"] = line.get("upper") or line.get("upper_level") or line.get("transition") or line.get("line_label") or ""
    terms = _find_resonance_type50_terms(solver_dir)
    out["n_type50_terms_touching_resonance"] = len(terms)
    if terms:
        # Prefer the emitted resonance line upper->ground if present.
        best = None
        for row in terms:
            if _is_resonance_upper_label(row.get("from_level_label")) and _is_ground_label(row.get("to_level_label")):
                best = row
                break
        if best is None:
            best = terms[0]
        out["python_resonance_type50_treatment"] = best.get("type50_bound_bound_treatment")
        out["python_resonance_raw_A_s^-1"] = _to_float(best.get("raw_A_s^-1"))
        out["python_resonance_escaped_decay_rate_s^-1"] = _to_float(best.get("escaped_decay_rate_s^-1") or best.get("rate_s^-1"))
        out["python_resonance_photoexcitation_rate_s^-1"] = _to_float(best.get("photoexcitation_rate_s^-1")) or 0.0
        out["python_resonance_ptmp_sum_proxy"] = _to_float(best.get("ptmp_sum_proxy"))
        out["python_resonance_xstar_tau1_for_type50_escape"] = _to_float(best.get("xstar_tau1_for_type50_escape"))
        out["python_resonance_xstar_tau2_for_type50_escape"] = _to_float(best.get("xstar_tau2_for_type50_escape"))
        out["python_resonance_type50_context_status"] = best.get("ucalc_context_status")
    out["population_matrix_photoexcitation_to_resonance_sum_s^-1"] = _sum_photoexcitation_into_resonance(solver_dir)
    solver_r = _to_float(out.get("solver_r"))
    target_r = _to_float(out.get("target_r"))
    if solver_r is not None and target_r is not None and solver_r > 0:
        out["target_over_solver_r"] = target_r / solver_r
        out["resonance_fraction_deficit"] = target_r - solver_r
    out["xstar_type50_required_inputs"] = "epi energy grid; bremsa radiation field at line energy; flinabs(ptmp1); cfrac; vturb; ion mass A; tau/ptmp escape probabilities"
    out["current_missing_piece"] = "real XSTAR type-50 ans2 photoexcitation term is not assembled; current xstar-line-escape path sets photoexcitation_rate_s^-1=0"
    out["next_implementation_target"] = "port ucalc.f90 type-50 photoexcitation ans2 using same local radiation field normalization, then insert lower->upper matrix term before comparing collision-rate scales"
    out["policy"] = "source-code audit only; no empirical triplet scale fitting or solver modification"
    out["status"] = "ok"
    return out


def _write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# He-like type-50 line-pumping source-code audit",
        "",
        "This audit identifies the XSTAR bound-bound photoexcitation term that is still absent from the Python population matrix. It does not fit or apply a scale factor.",
        "",
        "XSTAR `ucalc.f90` type 50 forms an escaped downward decay and an upward photoexcitation rate. After the branch-local ans1/ans2 swap, the upward matrix term is the photoexcitation rate.",
        "",
    ]
    if rows:
        lines.append("| Ion | solver r | target r | target/solver r | current photoexcitation | XSTAR resonance depth | type-50 treatment | next target |")
        lines.append("|---|---:|---:|---:|---:|---:|---|---|")
        for r in rows:
            lines.append(
                f"| {r.get('ion','')} | {_fmt(r.get('solver_r'))} | {_fmt(r.get('target_r'))} | {_fmt(r.get('target_over_solver_r'))} | "
                f"{_fmt(r.get('population_matrix_photoexcitation_to_resonance_sum_s^-1'))} | {_fmt(r.get('xstar_resonance_depth_inward'))} | "
                f"{r.get('python_resonance_type50_treatment','')} | {r.get('next_implementation_target','')} |"
            )
    lines += [
        "",
        "## Source-code formula to port next",
        "",
        "```fortran",
        "ans1 = aij * (ptmp1 + ptmp2)",
        "sigma = 0.02655 * flin * elin * 1.d-8 / vtherm",
        "ans2 = sigma * bremsa(nb1) * vtherm / 3.e10 * flinabs(ptmp1)",
        "ans2 = ans2 * max(0., 1.d0-cfrac)",
        "! then XSTAR swaps ans1/ans2 so ans1 is lower->upper photoexcitation",
        "```",
        "",
        "The audit should remain diagnostic until the radiation-field normalization is ported from XSTAR rather than tuned to line ratios.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(v: Any) -> str:
    x = _to_float(v)
    if x is None:
        return ""
    return f"{x:.6g}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit missing He-like type-50 line-pumping/photoexcitation source-code path.")
    ap.add_argument("--cases-csv", required=True, help="helike_local_state_cases.csv from example 51")
    ap.add_argument("--solver-root", default=".", help="root containing solver output directories")
    ap.add_argument("--xstar-source-root", default="", help="optional XSTAR source tree for provenance")
    ap.add_argument("--out-dir", default="helike_type50_line_pumping_audit_v03127")
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args(argv)

    cases = _read_csv(Path(args.cases_csv))
    source_info = _source_lines_available(Path(args.xstar_source_root)) if args.xstar_source_root else {}
    rows: list[dict[str, Any]] = []
    for case in cases:
        if str(case.get("can_generate_solver_command") or "").lower() not in {"true", "1", "yes"} and case.get("status") != "local_state_selected":
            continue
        rows.append(_audit_case(case, Path(args.solver_root), source_info, case_base_dir=Path(args.cases_csv).parent))
    out_dir = Path(args.out_dir)
    _write_csv(out_dir / "helike_type50_line_pumping_audit.csv", rows)
    _write_markdown(out_dir / "helike_type50_line_pumping_audit.md", rows)
    meta = {
        "n_cases": len(rows),
        "n_solver_r_low": sum(1 for r in rows if (_to_float(r.get("resonance_fraction_deficit")) or 0.0) > 0.0),
        "n_zero_photoexcitation_to_resonance": sum(1 for r in rows if (_to_float(r.get("population_matrix_photoexcitation_to_resonance_sum_s^-1")) or 0.0) == 0.0),
        "policy": "source-code audit only; no empirical triplet scale fitting",
    }
    (out_dir / "helike_type50_line_pumping_audit.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if args.print_summary:
        print("He-like type-50 line-pumping source-code audit")
        print("------------------------------------------------")
        for k, v in meta.items():
            print(f"{k}={v}")
        print(f"wrote: {out_dir / 'helike_type50_line_pumping_audit.csv'}")
        print(f"wrote: {out_dir / 'helike_type50_line_pumping_audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
