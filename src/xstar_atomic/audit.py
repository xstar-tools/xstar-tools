"""Reusable source-code-first audit workflows for :mod:`xstar_atomic`.

Historically many of the deep XSTAR-comparison diagnostics lived only in the
``examples/`` directory.  This module begins moving stable, reusable audit logic
into the package while keeping example scripts as thin command-line wrappers.

The v0.3.128 public entry point is :func:`type50_line_pumping`, an audit-only
workflow for the He-like type-50 bound-bound photoexcitation / line-pumping path.
It does not inject new rates into the solver and does not fit empirical triplet
scale factors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .context import EscapeContext, LocalPlasmaState
from .rates_type50 import RateEvaluation, evaluate_type50_bound_bound, type50_formula_summary


@dataclass(frozen=True)
class Type50LinePumpingAudit:
    """Container returned by :func:`type50_line_pumping`."""

    rows: tuple[dict[str, Any], ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    out_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"rows": list(self.rows), "metadata": dict(self.metadata), "out_dir": self.out_dir}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([dict(row) for row in rows])


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_solver_dir(case: Mapping[str, str], solver_root: Path) -> Path | None:
    name = case.get("recommended_solver_out_dir") or case.get("solver_out_dir") or ""
    if name:
        p = Path(str(name))
        if p.is_absolute() and p.exists():
            return p
        q = solver_root / p
        if q.exists():
            return q
    tag = str(case.get("tag") or "").lower()
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


def _line_role(row: Mapping[str, str]) -> str:
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
        candidates.append(base_dir.parent / p)
    for q in candidates:
        try:
            if q.exists():
                return q
        except Exception:
            pass
    return None


def _find_resonance_target_row(case: Mapping[str, str], *, case_base_dir: Path | None = None) -> dict[str, str] | None:
    csv_path = str(case.get("target_csv_path") or case.get("xstar_target_csv") or "")
    p = _resolve_existing_path(csv_path, base_dir=case_base_dir)
    if p is None:
        return None
    rows = _read_csv(p)
    for row in rows:
        if _line_role(row) == "r":
            return row
    candidates = []
    for row in rows:
        depth = max(_to_float(row.get("depth_inward")) or 0.0, _to_float(row.get("depth_outward")) or 0.0)
        candidates.append((depth, row))
    if candidates:
        return sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]
    return None


def _matrix_terms(solver_dir: Path) -> list[dict[str, str]]:
    terms = _read_csv(solver_dir / "xstar_like_element_solver_full_global_matrix_terms.csv")
    if not terms:
        terms = _read_csv(solver_dir / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv")
    return terms


def _find_resonance_type50_terms(solver_dir: Path) -> list[dict[str, str]]:
    out = []
    for row in _matrix_terms(solver_dir):
        if str(row.get("matrix_term_kind") or "") != "offdiag_gain":
            continue
        if str(row.get("data_type") or row.get("resonance_collisional_feed_data_type") or "") not in {"50", "50.0"}:
            continue
        if _is_resonance_upper_label(row.get("from_level_label")) and _is_ground_label(row.get("to_level_label")):
            out.append(row)
        elif _is_resonance_upper_label(row.get("to_level_label")) or _is_resonance_upper_label(row.get("from_level_label")):
            out.append(row)
    return out


def _sum_photoexcitation_into_resonance(solver_dir: Path) -> float:
    total = 0.0
    for row in _matrix_terms(solver_dir):
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
        "xstar_type50_branch_lines": type50_formula_summary(),
    }


def _fmt(v: Any) -> str:
    x = _to_float(v)
    if x is None:
        return ""
    return f"{x:.6g}"


def _rate_preview_from_matrix_row(row: Mapping[str, str], case: Mapping[str, str]) -> RateEvaluation:
    """Build an audit-only type-50 evaluator preview from an existing matrix row.

    Current solver outputs usually lack the real XSTAR radiation terms, so the
    result is expected to be ``incomplete_context``.  The useful part is that the
    missing terms are now reported by the public ``RateEvaluation`` object.
    """
    state = LocalPlasmaState.from_mapping(case)
    escape = EscapeContext.from_mapping(row)
    return evaluate_type50_bound_bound(
        aij_s_inv=_to_float(row.get("raw_A_s^-1")),
        oscillator_strength=_to_float(row.get("oscillator_strength") or row.get("f_osc")),
        wavelength_A=_to_float(row.get("wavelength_A") or row.get("wavelength")),
        ptmp1=escape.ptmp1,
        ptmp2=escape.ptmp2,
        flinabs_ptmp1=escape.flinabs_ptmp1,
        cfrac=escape.cfrac,
        ion=str(case.get("ion") or "") or None,
        lower_level=row.get("to_level_label") or row.get("lower_level_label"),
        upper_level=row.get("from_level_label") or row.get("upper_level_label"),
        record_id=row.get("record_index") or row.get("record_id"),
        plasma_state=state,
        escape_context=escape,
        metadata={"audit_preview": True, "source": "existing_matrix_row"},
    )


def _audit_case(case: Mapping[str, str], solver_root: Path, xstar_source_info: Mapping[str, Any], *, case_base_dir: Path | None = None) -> dict[str, Any]:
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
    out.update(dict(xstar_source_info))
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
        best = None
        for row in terms:
            if _is_resonance_upper_label(row.get("from_level_label")) and _is_ground_label(row.get("to_level_label")):
                best = row
                break
        if best is None:
            best = terms[0]
        preview = _rate_preview_from_matrix_row(best, case)
        out["python_resonance_type50_treatment"] = best.get("type50_bound_bound_treatment")
        out["python_resonance_raw_A_s^-1"] = _to_float(best.get("raw_A_s^-1"))
        out["python_resonance_escaped_decay_rate_s^-1"] = _to_float(best.get("escaped_decay_rate_s^-1") or best.get("rate_s^-1"))
        out["python_resonance_photoexcitation_rate_s^-1"] = _to_float(best.get("photoexcitation_rate_s^-1")) or 0.0
        out["python_resonance_ptmp_sum_proxy"] = _to_float(best.get("ptmp_sum_proxy"))
        out["python_resonance_xstar_tau1_for_type50_escape"] = _to_float(best.get("xstar_tau1_for_type50_escape"))
        out["python_resonance_xstar_tau2_for_type50_escape"] = _to_float(best.get("xstar_tau2_for_type50_escape"))
        out["python_resonance_type50_context_status"] = best.get("ucalc_context_status")
        out["type50_rate_evaluator_status"] = preview.status
        out["type50_rate_evaluator_warnings"] = "; ".join(preview.warnings)
        out["type50_rate_evaluator_source_formula"] = preview.source_formula
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


def _write_markdown(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# He-like type-50 line-pumping source-code audit",
        "",
        "This audit identifies the XSTAR bound-bound photoexcitation term that is still absent from the Python population matrix. It does not fit or apply a scale factor.",
        "",
        "XSTAR `ucalc.f90` type 50 forms an escaped downward decay and an upward photoexcitation rate. After the branch-local ans1/ans2 swap, the upward matrix term is the photoexcitation rate.",
        "",
    ]
    if rows:
        lines.append("| Ion | solver r | target r | target/solver r | current photoexcitation | XSTAR resonance depth | evaluator status | type-50 treatment | next target |")
        lines.append("|---|---:|---:|---:|---:|---:|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r.get('ion','')} | {_fmt(r.get('solver_r'))} | {_fmt(r.get('target_r'))} | {_fmt(r.get('target_over_solver_r'))} | "
                f"{_fmt(r.get('population_matrix_photoexcitation_to_resonance_sum_s^-1'))} | {_fmt(r.get('xstar_resonance_depth_inward'))} | "
                f"{r.get('type50_rate_evaluator_status','')} | {r.get('python_resonance_type50_treatment','')} | {r.get('next_implementation_target','')} |"
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


def type50_line_pumping(
    cases_csv: str | Path,
    *,
    solver_root: str | Path = ".",
    xstar_source_root: str | Path | None = None,
    out_dir: str | Path | None = "helike_type50_line_pumping_audit_v03128",
    write_outputs: bool = True,
    print_summary: bool = False,
) -> Type50LinePumpingAudit:
    """Run the He-like type-50 line-pumping audit.

    Parameters mirror the former ``examples/55_audit_helike_type50_line_pumping``
    CLI script.  The function returns rows and summary metadata, and optionally
    writes the historical CSV/Markdown/JSON products.
    """
    cases_path = Path(cases_csv)
    cases = _read_csv(cases_path)
    source_info = _source_lines_available(Path(xstar_source_root)) if xstar_source_root else {}
    rows: list[dict[str, Any]] = []
    for case in cases:
        can_run = str(case.get("can_generate_solver_command") or "").lower() in {"true", "1", "yes"}
        if not can_run and case.get("status") != "local_state_selected":
            continue
        rows.append(_audit_case(case, Path(solver_root), source_info, case_base_dir=cases_path.parent))
    meta = {
        "n_cases": len(rows),
        "n_solver_r_low": sum(1 for r in rows if (_to_float(r.get("resonance_fraction_deficit")) or 0.0) > 0.0),
        "n_zero_photoexcitation_to_resonance": sum(1 for r in rows if (_to_float(r.get("population_matrix_photoexcitation_to_resonance_sum_s^-1")) or 0.0) == 0.0),
        "policy": "source-code audit only; no empirical triplet scale fitting",
        "api_entry_point": "xstar_atomic.audit.type50_line_pumping",
    }
    out_path = Path(out_dir) if out_dir is not None else None
    if write_outputs and out_path is not None:
        _write_csv(out_path / "helike_type50_line_pumping_audit.csv", rows)
        _write_markdown(out_path / "helike_type50_line_pumping_audit.md", rows)
        (out_path / "helike_type50_line_pumping_audit.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if print_summary:
        print("He-like type-50 line-pumping source-code audit")
        print("------------------------------------------------")
        for k, v in meta.items():
            print(f"{k}={v}")
        if out_path is not None:
            print(f"wrote: {out_path / 'helike_type50_line_pumping_audit.csv'}")
            print(f"wrote: {out_path / 'helike_type50_line_pumping_audit.md'}")
    return Type50LinePumpingAudit(rows=tuple(rows), metadata=meta, out_dir=str(out_path) if out_path is not None else None)


__all__ = ["Type50LinePumpingAudit", "type50_line_pumping"]
