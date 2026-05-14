"""Source-code-equivalent local matrix/population closure audits for XSTAR.

This module is intentionally an audit/probe-planning layer.  It does not tune
triplet ratios and it does not silently change solver physics.  It answers a
more basic question for a preserved Python matrix: which row families are already
close to XSTAR source-code parity, which ones are still proxy/scaffold rows, and
which Fortran call-site quantities must be captured to reach local
matrix/population parity including adjacent-parent ions and superlevels.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .xstar_matrix_parity import find_solver_product_paths


@dataclass(frozen=True)
class SourceSnippetSpec:
    key: str
    file: str
    pattern: str
    role: str
    interpretation: str
    context: int = 4


def _read_csv(path: str | Path | None) -> List[Dict[str, str]]:
    if path is None or not str(path).strip():
        return []
    p = Path(path)
    if p.is_dir():
        candidates = sorted(p.rglob("*.csv"))
        if len(candidates) == 1:
            p = candidates[0]
        else:
            # Prefer known records/summary names when a whole audit dir is supplied.
            for pat in [
                "*live_bremsam_phint53_audit_records.csv",
                "*matrix_replacement_audit_changed_terms.csv",
                "*full_global_matrix_terms.csv",
            ]:
                hits = sorted(p.rglob(pat))
                if hits:
                    p = hits[0]
                    break
    if not p.exists():
        return []
    with p.open("r", newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in ordered:
                    ordered.append(str(key))
        fields = ordered or ["status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _as_float(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or (isinstance(x, str) and not x.strip()):
            return default
        y = float(x)
        if not math.isfinite(y):
            return default
        return y
    except Exception:
        return default


def _as_int(x: Any, default: int | None = None) -> int | None:
    y = _as_float(x, None)
    if y is None:
        return default
    return int(round(y))


def _norm(text: Any) -> str:
    return str(text or "").strip().lower().replace(" ", "_").replace("-", "_")


def _infer_data_type(row: Mapping[str, Any]) -> str:
    dt = _as_int(row.get("data_type"), None)
    if dt is not None:
        return str(dt)
    method = str(row.get("source_method") or row.get("full_global_provenance") or row.get("provenance") or "")
    if "data_type_" in method:
        try:
            return str(int(method.split("data_type_", 1)[1].split("_", 1)[0]))
        except Exception:
            pass
    for key, value in [
        ("type99_rate_source", "99"),
        ("type71_rate_source", "71"),
        ("type77_rate_source", "77"),
        ("inverse_recombination_mode", "74"),
        ("source_code_phint53_milne_ans2_rrrt_s^-1", "53"),
        ("source_code_milne_f90_rate_alpha_ne_s^-1", "53"),
        ("type50_bound_bound_treatment", "50"),
        ("directional_q_cm3_s", "68"),
    ]:
        if str(row.get(key) or "").strip():
            return value
    return "unknown"


def _source_label(row: Mapping[str, Any]) -> str:
    bits: List[str] = []
    for key in [
        "source_method",
        "source_format",
        "rate_source",
        "type71_rate_source",
        "type77_rate_source",
        "type99_rate_source",
        "inverse_recombination_mode",
        "radiation_field_mode",
        "ucalc_context_status",
        "phint53_status",
    ]:
        val = str(row.get(key) or "").strip()
        if val and val.lower() != "nan" and val not in bits:
            bits.append(val)
    return ";".join(bits) if bits else "unspecified"


def _truthy(row: Mapping[str, Any], key: str) -> bool:
    val = str(row.get(key) or "").strip().lower()
    return val in {"1", "true", "yes", "y"}


def _row_is_triplet_touching(row: Mapping[str, Any]) -> bool:
    if str(row.get("triplet_component") or "").strip():
        return True
    for key in [
        "feeds_forbidden_upper",
        "feeds_intercombination_upper",
        "feeds_resonance_upper",
        "feeds_any_triplet_component",
    ]:
        if _truthy(row, key):
            return True
    text = " ".join(str(row.get(k) or "") for k in ["from_level_label", "to_level_label", "bound_level", "destination_level_label"])
    return any(tok in text for tok in ["3S_1", "3P_", "1P_1"])


def _row_has_proxy(row: Mapping[str, Any]) -> bool:
    """Return True for rate/source proxy rows, not merely topological scaffolds.

Most preserved full-global rows carry old provenance strings such as
``full_global_matrix_topology_scaffold`` even when the scalar rate itself came
from an XSTAR-aligned evaluator.  Do not count those topology labels as a rate
proxy; here we only flag fields that describe the rate/source construction.
    """
    hay = " ".join(str(row.get(k) or "") for k in [
        "source_method", "rate_source", "type99_rate_source", "source_proxy_basis",
        "ucalc_context_status", "phint53_status", "warning", "radiation_field_mode",
        "type50_line_escape_fallback_used",
    ]).lower()
    if str(row.get("source_proxy_basis") or "").strip():
        return True
    if str(row.get("type50_line_escape_fallback_used") or "").strip().lower() == "true":
        return True
    return any(tok in hay for tok in ["proxy", "placeholder", "fallback", "diagnostic", "flat", "legacy_preview"])


def _row_has_source_code_marker(row: Mapping[str, Any]) -> bool:
    hay = " ".join(str(row.get(k) or "") for k in [
        "source_method", "rate_source", "type71_rate_source", "type77_rate_source",
        "inverse_recombination_mode", "ucalc_context_status", "phint53_status",
        "eval_method", "type71_calt71_status", "type77_calt77_status",
        "source_code_phint53_milne_ans2_rrrt_s^-1", "source_code_milne_f90_rate_alpha_ne_s^-1",
    ]).lower()
    return any(tok in hay for tok in ["xstar", "ucalc", "calt", "source_code", "matrix_matches", "q_ne", "phint53"])


_FAMILY_REQUIREMENTS: Dict[str, Dict[str, str]] = {
    "50": {
        "family": "type-50 bound-bound radiative + line pumping",
        "fortran": "calc_hmc_ion.f90 escape ptmp1/ptmp2; ucalc.f90 type 50; pescl/flinabs",
        "closure": "mostly_source_code_verified_rate; still needs universal ucalc+matrix insertion probe for all rows",
        "probe": "ucalc ans1/ans2 and four calc_hmc_ion matrix insertions",
    },
    "53": {
        "family": "type-53 bound-free photoionization + Milne recombination",
        "fortran": "ucalc.f90 type 53; phint53.f90; nbinc/enxt; rnist/swrat; calc_hmc_ion insertion",
        "closure": "mixed: Milne branch partly source-code; photoionization rows may still be proxy-normalized",
        "probe": "ucalc ans1..ans6 for every type-53 record plus matrix insertions and parent continuum index",
    },
    "63": {
        "family": "type-63 Bautista hydrogenic collisions",
        "fortran": "ucalc.f90 type 63; anl1/erc/omega logic; calc_hmc_ion insertion",
        "closure": "kernel-audited but needs ucalc insertion parity across all records",
        "probe": "ucalc ans1/ans2, idest1/idest2, llo/lup, ajisi four rows",
    },
    "68": {
        "family": "type-68 collisional transitions",
        "fortran": "ucalc/calt68 path; calc_hmc_ion insertion",
        "closure": "source-code q*ne parity audited for O VII rows; still needs universal insertion probe",
        "probe": "ucalc ans1/ans2 and matrix insertions",
    },
    "69": {
        "family": "type-69 collisional transitions",
        "fortran": "ucalc.f90 type 69; calt69; calc_hmc_ion insertion",
        "closure": "partly implemented; needs source-code row-level probe",
        "probe": "calt69 gamma, ans1/ans2, matrix insertions",
    },
    "70": {
        "family": "type-70 old superlevel photoionization/recombination closure",
        "fortran": "ucalc.f90 type 70; calt70; phint53hunt; rec*xnx/ans2d scaling; ans3..ans6 swaps",
        "closure": "not source-code-complete unless calt70+phint53hunt scaling and parent coupling are implemented",
        "probe": "type-70 ans1..ans6, scale, rec, ans2d, idest parent continuum rows",
    },
    "71": {
        "family": "type-71 superlevel cascade redistribution",
        "fortran": "calt71.f90; ucalc/calc_hmc_ion insertion/topology",
        "closure": "local calt71 rate parity audited; population closure still needs superlevel parent matrix parity",
        "probe": "calt71 Aij, spectroscopic/superlevel indices, matrix insertion rows",
    },
    "74": {
        "family": "type-74 inverse recombination delta-function closure",
        "fortran": "ucalc.f90 type 74; calt74(temp,ncn2,epi,bremsa); ans1=rate; ans2=alpha*gglo/ggup",
        "closure": "diagnostic/partly implemented; needs true ucalc and parent continuum coupling parity",
        "probe": "calt74 rate/alpha, gglo/ggup, ans1/ans2, matrix insertion rows",
    },
    "77": {
        "family": "type-77 superlevel collisional coupling",
        "fortran": "calt77.f90; superlevel/spectroscopic topology; calc_hmc_ion insertion",
        "closure": "partly implemented; needs row-level source parity and msolvelucy superlevel closure",
        "probe": "calt77 clu/cul, indices, matrix insertion rows",
    },
    "99": {
        "family": "type-99 superlevel/parent continuum photoionization-recombination closure",
        "fortran": "ucalc.f90 type 99; calt99; phint53hunt; scale=rec*xnx/ans2d; ans5/ans6, ans3/ans4 swaps and heating corrections",
        "closure": "highest-priority missing closure; proxy/scaffold rows are not source-code-equivalent",
        "probe": "type-99 ans1..ans6, rec, ans2d, scale, swrat, parent continuum idest2, calc_hmc_ion rows",
    },
    "unknown": {
        "family": "unknown/source-vector/scaffold rows",
        "fortran": "must be mapped to calc_hmc_ion/ucalc or removed from source-code-equivalent solve",
        "closure": "not source-code-equivalent until mapped to an XSTAR record and insertion site",
        "probe": "record/idest/source provenance required",
    },
}


SOURCE_COMPLETENESS_SNIPPETS: List[SourceSnippetSpec] = [
    SourceSnippetSpec(
        "calc_hmc_ion_calls_ucalc", "calc_hmc_ion.f90",
        "call ucalc(ltyp,lrtyp,ml_data", "rate_kernel_call",
        "Every source-code-equivalent local matrix row must start from ucalc ans1..ans6 for a concrete ATDB record.", 8,
    ),
    SourceSnippetSpec(
        "calc_hmc_ion_saves_rates", "calc_hmc_ion.f90",
        "rates(1,ml_data)=ans1", "rate_array_capture",
        "XSTAR preserves ans1..ans6 in rates(:,ml_data) before constructing the level matrix.", 8,
    ),
    SourceSnippetSpec(
        "calc_hmc_ion_idrates", "calc_hmc_ion.f90",
        "idrates(3,ml_data)=idest1", "destination_capture",
        "idest1/idest2 and shifted global indices are part of the rate provenance.", 8,
    ),
    SourceSnippetSpec(
        "calc_hmc_ion_four_matrix_rows", "calc_hmc_ion.f90",
        "ajisi(1,nindbi)=ans1", "four_row_matrix_insertion",
        "Each ucalc record becomes paired off-diagonal and diagonal matrix contributions; parity must compare this insertion, not only the scalar rate.", 18,
    ),
    SourceSnippetSpec(
        "calc_hmc_ion_diagonal_loss", "calc_hmc_ion.f90",
        "ajisi(1,nindbi)=-ans1", "diagonal_loss_insertion",
        "The sign/topology convention is source-code-defined in calc_hmc_ion and must be reproduced exactly.", 10,
    ),
    SourceSnippetSpec(
        "type53_branch", "ucalc.f90", "53 continue", "type53_branch_start",
        "Type 53 builds idest1/idest2, threshold, cross-section arrays, swrat/rnist, then calls phint53.", 8,
    ),
    SourceSnippetSpec(
        "type53_rnist", "ucalc.f90", "rnist=rnissel", "type53_lte_inverse_factor",
        "rnist/swrat/LTE factors enter Milne/recombination and must be captured for exact parity.", 8,
    ),
    SourceSnippetSpec(
        "type53_phint53_call", "ucalc.f90", "call phint53(stmpp,etmpp", "type53_phint53_call",
        "The true branch target for type-53 ans1..ans6 parity is the ucalc phint53 call-site, not a standalone continuum approximation.", 8,
    ),
    SourceSnippetSpec(
        "type99_branch", "ucalc.f90", "99 continue", "type99_branch_start",
        "Type 99 is a superlevel/parent closure branch, not a generic source-vector proxy.", 8,
    ),
    SourceSnippetSpec(
        "type99_calt99", "ucalc.f90", "call calt99(temp,den,ettry", "type99_calt99_call",
        "calt99 constructs the superlevel cross section and recombination coefficient rec.", 8,
    ),
    SourceSnippetSpec(
        "type99_phint53hunt", "ucalc.f90", "call phint53hunt(stmpp,etmpp", "type99_phint53hunt_call",
        "type 99 uses phint53hunt and rescales ans1/ans3/ans5 by rec*xnx/ans2d.", 8,
    ),
    SourceSnippetSpec(
        "type99_scale", "ucalc.f90", "scale=rec*xnx/ans2d", "type99_recombination_scale",
        "This scaling is the key source-code closure missing from proxy superlevel source rows.", 8,
    ),
    SourceSnippetSpec(
        "type70_branch", "ucalc.f90", "70 continue", "type70_branch_start",
        "Old type-70 superlevel closure follows the same calt70/phint53hunt/rescale pattern.", 8,
    ),
    SourceSnippetSpec(
        "type74_branch", "ucalc.f90", "74 continue", "type74_branch_start",
        "Type 74 inverse recombination/delta-function closure must be included in parent-ion balance.", 8,
    ),
    SourceSnippetSpec(
        "type74_calt74", "ucalc.f90", "call calt74(temp,ncn2,epi,bremsa", "type74_calt74_call",
        "calt74 depends on the live radiation grid and returns both photo and inverse recombination pieces.", 8,
    ),
    SourceSnippetSpec(
        "calc_hmc_element_levwkelement", "calc_hmc_element.f90", "call levwkelement", "population_lte_initialization",
        "Parent/superlevel closure requires the same LTE/population initialization used by XSTAR before msolvelucy.", 8,
    ),
    SourceSnippetSpec(
        "calc_hmc_element_solver", "calc_hmc_element.f90", "call msolvelucy", "population_solver_call",
        "Full parity ultimately requires comparing the assembled ajise/indbe matrix and msolvelucy populations.", 8,
    ),
    SourceSnippetSpec(
        "levwkelement_normalizes", "levwkelement.f90", "rnise(mm)=rnise(mm)/(1.d-97+rnissum)", "population_normalization",
        "XSTAR normalizes LTE element-level populations before the linear solve; this is part of parent closure.", 8,
    ),
]


def _find_file(source_root: str | Path, name: str) -> Optional[Path]:
    root = Path(source_root)
    if not root.exists():
        return None
    direct = root / name
    if direct.exists():
        return direct
    for prefix in ["xstarlib/src", "xstar/xstarlib/src", "src"]:
        p = root / prefix / Path(name).name
        if p.exists():
            return p
    hits = sorted(root.rglob(Path(name).name))
    return hits[0] if hits else None


def _extract_snippet(path: Path, pattern: str, context: int) -> Dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    variants = [pattern.lower(), pattern.lower().replace(" ", "")]
    hit: int | None = None
    for i, line in enumerate(lines):
        low = line.lower()
        compact = low.replace(" ", "")
        if variants[0] in low or variants[1] in compact:
            hit = i
            break
    if hit is None:
        return {"matched": False, "line_start": "", "line_end": "", "matched_line": "", "snippet": ""}
    start = max(0, hit - context)
    end = min(len(lines), hit + context + 1)
    return {
        "matched": True,
        "line_start": start + 1,
        "line_end": end,
        "matched_line": f"{hit + 1}: {lines[hit]}",
        "snippet": "\n".join(f"{j + 1}: {lines[j]}" for j in range(start, end)),
    }


def audit_source_snippets(xstar_source_root: str | Path | None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if xstar_source_root is None:
        for spec in SOURCE_COMPLETENESS_SNIPPETS:
            rows.append({**spec.__dict__, "matched": False, "path": "", "snippet": "", "source_status": "source_root_not_supplied"})
        return rows
    for spec in SOURCE_COMPLETENESS_SNIPPETS:
        p = _find_file(xstar_source_root, spec.file)
        row: Dict[str, Any] = {**spec.__dict__, "path": str(p) if p else ""}
        if p is None:
            row.update({"matched": False, "source_status": "file_not_found", "snippet": ""})
        else:
            row.update(_extract_snippet(p, spec.pattern, spec.context))
            row["source_status"] = "matched" if row.get("matched") else "pattern_not_found"
        rows.append(row)
    return rows


def _classify_family(dt: str, rows: Sequence[Mapping[str, Any]]) -> Tuple[str, str, str]:
    req = _FAMILY_REQUIREMENTS.get(dt, _FAMILY_REQUIREMENTS.get("unknown", {}))
    n = len(rows)
    n_proxy = sum(1 for r in rows if _row_has_proxy(r))
    n_src = sum(1 for r in rows if _row_has_source_code_marker(r))
    if dt in {"99", "70"}:
        return "parent_superlevel_closure_incomplete", req.get("closure", ""), req.get("probe", "")
    if dt == "74":
        return "parent_inverse_recombination_closure_unverified", req.get("closure", ""), req.get("probe", "")
    if dt == "53" and n_proxy > 0:
        return "mixed_proxy_and_source_code_branches", req.get("closure", ""), req.get("probe", "")
    if n_proxy > 0 and n_src == 0:
        return "proxy_or_scaffold_not_source_code_equivalent", "rows contain proxy/scaffold/fallback provenance", req.get("probe", "")
    if n_src > 0 and n_proxy == 0:
        return "source_code_rate_kernel_present_insertion_universal_probe_needed", req.get("closure", ""), req.get("probe", "")
    return "unclassified_needs_ucalc_probe", req.get("closure", ""), req.get("probe", "")


def matrix_family_closure_summary(matrix_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for r in matrix_rows:
        dt = _infer_data_type(r)
        label = _source_label(r)
        groups.setdefault((dt, label), []).append(r)
    out: List[Dict[str, Any]] = []
    for (dt, label), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        req = _FAMILY_REQUIREMENTS.get(dt, _FAMILY_REQUIREMENTS["unknown"])
        closure_class, notes, probe = _classify_family(dt, rows)
        out.append({
            "data_type": dt,
            "source_label": label,
            "family": req.get("family", "unknown"),
            "n_matrix_terms": len(rows),
            "n_triplet_touching_terms": sum(1 for r in rows if _row_is_triplet_touching(r)),
            "n_proxy_or_scaffold_terms": sum(1 for r in rows if _row_has_proxy(r)),
            "n_source_code_marker_terms": sum(1 for r in rows if _row_has_source_code_marker(r)),
            "closure_class": closure_class,
            "source_fortran_requirements": req.get("fortran", ""),
            "required_next_probe": probe,
            "notes": notes,
            "example_records": ";".join(str(r.get("record") or "") for r in rows[:5] if str(r.get("record") or "").strip()),
        })
    return out


def required_fortran_subroutine_rows() -> List[Dict[str, Any]]:
    return [
        {"priority": 1, "component": "calc_hmc_ion", "subroutine_or_file": "calc_hmc_ion.f90", "required_for_parity": "ucalc ans1..ans6 call-site and four-row ajisi/indbi matrix insertion", "current_gap": "Python audits compare many scalar rates, but not a universal Fortran row-by-row insertion dump."},
        {"priority": 1, "component": "ucalc", "subroutine_or_file": "ucalc.f90", "required_for_parity": "per-record ltyp/lrtyp/idest1..4/ans1..6/ptmp1/ptmp2/rnist/swrat/branch diagnostics", "current_gap": "Some branches are audited individually; full local matrix parity requires all branches."},
        {"priority": 1, "component": "parent/superlevel closure", "subroutine_or_file": "ucalc.f90 type 99/type 70 + calt99/calt70 + phint53hunt", "required_for_parity": "rec*xnx/ans2d scaling, ans swaps, heating corrections, parent continuum destination mapping", "current_gap": "Proxy/scaffold type-99 source rows are not source-code-equivalent."},
        {"priority": 1, "component": "population solve", "subroutine_or_file": "calc_hmc_element.f90 + msolvelucy.f90", "required_for_parity": "assembled ajise/indbe matrix, superlevel boundaries, solved rniss/rnise populations", "current_gap": "Need direct population parity against xo01_detail/Fortran probe, not just f/i/r output."},
        {"priority": 2, "component": "LTE/initial populations", "subroutine_or_file": "levwkelement.f90 + levwk.f90", "required_for_parity": "rnise initialization and normalization including continuum/superlevel rows", "current_gap": "Python parent-continuum aliasing must be verified against XSTAR rnise/rniss."},
        {"priority": 2, "component": "ion fractions", "subroutine_or_file": "calc_ion_rates.f90 + istruc.f90", "required_for_parity": "xpx/xnx ion-stage closure feeding parent/child rates", "current_gap": "Already approximated via xstar-calc-ion-rates closure; still needs direct linked population closure audit."},
        {"priority": 2, "component": "radiation field", "subroutine_or_file": "trnfrc.f90 + bremsmap.f90 + xstarcalc.f90", "required_for_parity": "live epim/bremsam/bremsint already captured; use at exact ucalc timing", "current_gap": "v0.3.172+ captures rate-grid; now pair it with ucalc record-level probe."},
    ]


def ucalc_probe_schema_rows() -> List[Dict[str, Any]]:
    cols = [
        ("capture_index", "yes", "Sequential probe capture id."),
        ("ml_data", "yes", "ATDB record pointer passed to ucalc."),
        ("ltyp", "yes", "XSTAR data type / rate type branch number."),
        ("lrtyp", "yes", "XSTAR rate subtype used for escape/continuum handling."),
        ("jkk_ion", "yes", "Current XSTAR ion index."),
        ("record", "recommended", "Same as ml_data unless a remapped record id is used."),
        ("idest1", "yes", "ucalc lower/destination index 1."),
        ("idest2", "yes", "ucalc upper/destination index 2 including parent-continuum rows."),
        ("idest3", "yes", "ucalc auxiliary ion-stage destination."),
        ("idest4", "yes", "ucalc auxiliary ion-stage destination+1."),
        ("ans1", "yes", "Forward/photoionization/excitation rate returned by ucalc."),
        ("ans2", "yes", "Reverse/recombination/de-excitation rate returned by ucalc."),
        ("ans3", "yes", "Heating/cooling channel returned by ucalc."),
        ("ans4", "yes", "Heating/cooling channel returned by ucalc."),
        ("ans5", "yes", "Electron/pov auxiliary returned by ucalc."),
        ("ans6", "yes", "Electron/pov auxiliary returned by ucalc."),
        ("ptmp1", "recommended", "Incoming escape factor passed into ucalc."),
        ("ptmp2", "recommended", "Outgoing/covering escape factor passed into ucalc."),
        ("xpx", "recommended", "Ion density/abundance scaling used by ucalc."),
        ("xnx", "recommended", "Electron density scalar used by ucalc."),
        ("t_xstar_1e4K", "recommended", "XSTAR temperature variable t, where Kelvin=t*1e4."),
        ("swrat", "branch_specific", "Statistical-weight ratio used by type 53/70/99."),
        ("rnist", "branch_specific", "LTE/Milne population factor used by type 53."),
        ("rec", "branch_specific", "calt70/calt99 recombination coefficient."),
        ("ans2d", "branch_specific", "phint53hunt recombination before rec scaling."),
        ("scale", "branch_specific", "rec*xnx/ans2d scale for type 70/99."),
        ("source_file", "recommended", "Fortran file/probe label."),
    ]
    return [{"column": c, "required": r, "description": d} for c, r, d in cols]


def calc_hmc_ion_probe_schema_rows() -> List[Dict[str, Any]]:
    cols = [
        ("capture_index", "yes", "Sequential matrix insertion capture id."),
        ("ml_data", "yes", "ATDB record pointer used by ltpsv/idrates."),
        ("ltyp", "yes", "Rate family."),
        ("lrtyp", "yes", "Rate subtype."),
        ("insertion_index", "yes", "nindbi value after increment."),
        ("insertion_kind", "yes", "forward_offdiag, reverse_offdiag, forward_diag_loss, reverse_diag_loss."),
        ("indbi_1", "yes", "Row/level index stored in indbi(1,nindbi)."),
        ("indbi_2", "yes", "Column/level index stored in indbi(2,nindbi)."),
        ("ajisi_1", "yes", "ajisi(1,nindbi) inserted value."),
        ("ajisi_2", "yes", "ajisi(2,nindbi) inserted value."),
        ("cjisi", "recommended", "Cooling/heating vector term."),
        ("cjisi2", "recommended", "Secondary cooling/heating vector term."),
        ("idest1", "recommended", "ucalc idest1."),
        ("idest2", "recommended", "ucalc idest2."),
        ("llo", "recommended", "Energy-ordered lower index used by calc_hmc_ion."),
        ("lup", "recommended", "Energy-ordered upper index used by calc_hmc_ion."),
        ("e1_eV", "recommended", "leveltemp energy idest1."),
        ("e2_eV", "recommended", "leveltemp energy idest2."),
    ]
    return [{"column": c, "required": r, "description": d} for c, r, d in cols]


def population_probe_schema_rows() -> List[Dict[str, Any]]:
    cols = [
        ("capture_index", "yes", "Sequential population/matrix capture id."),
        ("level_index", "yes", "Local element/global level index."),
        ("level_label", "recommended", "Resolved level label if available."),
        ("rnise_before_solve", "yes", "Population/LTE seed before msolvelucy."),
        ("rnise_after_solve", "yes", "Solved population after msolvelucy."),
        ("superlevel_group", "recommended", "nsup/nspmx group if relevant."),
        ("ion_stage", "recommended", "Ion stage for parent/child closure."),
        ("continuum_or_parent_alias", "recommended", "Whether this row is a continuum/parent alias."),
    ]
    return [{"column": c, "required": r, "description": d} for c, r, d in cols]


def fortran_probe_template() -> str:
    return """! xstar-atomic v0.3.175 source-code-equivalent local parity probe notes
! Add this as guidance to a local debug XSTAR build.  The exact insertion is
! safer than reconstructing from final FITS products.
!
! 1) In calc_hmc_ion.f90, immediately after call ucalc(...), append one row to
!    xstar_ucalc_record_probe.csv with:
!      ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,
!      ans1,ans2,ans3,ans4,ans5,ans6,ptmp1,ptmp2,xpx,xnx,t,swrat,rnist
!
! 2) In calc_hmc_ion.f90, after each nindbi insertion block, append one row to
!    xstar_calc_hmc_ion_matrix_probe.csv with:
!      ml_data,ltyp,lrtyp,nindbi,insertion_kind,indbi(1,nindbi),
!      indbi(2,nindbi),ajisi(1,nindbi),ajisi(2,nindbi),cjisi(nindbi),cjisi2(nindbi)
!
! 3) In calc_hmc_element.f90, just before and after call msolvelucy(...), append
!    rnise/rniss level populations and superlevel boundaries to
!    xstar_population_probe.csv.
!
! These three probe products are the minimum needed to verify parent-ion and
! superlevel closure without guessing from xout/xo01 detail products.
"""


def implementation_plan_rows() -> List[Dict[str, Any]]:
    return [
        {"step": 1, "package_target": "v0.3.176", "action": "Add readers/validators for xstar_ucalc_record_probe.csv and xstar_calc_hmc_ion_matrix_probe.csv.", "success_criterion": "Every Python matrix term maps to a Fortran ml_data/ltyp/lrtyp/idest pair or is explicitly removed from source-equivalent mode."},
        {"step": 2, "package_target": "v0.3.177", "action": "Add record-level parity report: compare ucalc ans1..ans6 with Python rates for types 50,53,63,68,69,70,71,74,77,99.", "success_criterion": "Per-family max/median relative differences and branch-specific diagnostics are written."},
        {"step": 3, "package_target": "v0.3.178", "action": "Replace proxy type-99/type-70/type-74 rows with source-code calt/phint53hunt/calt74 branches using exact parent-continuum mapping.", "success_criterion": "No proxy/scaffold parent/superlevel source rows remain in source-equivalent mode."},
        {"step": 4, "package_target": "v0.3.179", "action": "Add calc_hmc_ion insertion parity: compare Python row topology/signs against Fortran ajisi/indbi rows.", "success_criterion": "Off-diagonal and diagonal rows agree record-by-record."},
        {"step": 5, "package_target": "v0.3.180", "action": "Add population parity: compare Python solved populations to XSTAR pre/post-msolvelucy probes and xo01_detail populations.", "success_criterion": "Local population vector, parent continuum rows, and superlevel rows agree within tolerance before checking emitted f/i/r."},
    ]


def audit_source_code_equivalent_local_closure(
    *,
    benchmark_dir: str | Path | None = None,
    ion: str = "O VII",
    xstar_source_root: str | Path | None = None,
    matrix_terms_csv: str | Path | None = None,
    comparisons_csv: str | Path | None = None,
) -> Dict[str, Any]:
    paths: Dict[str, Optional[Path]] = {}
    if benchmark_dir is not None and matrix_terms_csv is None:
        paths = find_solver_product_paths(benchmark_dir, ion=ion, comparisons_csv=comparisons_csv)
        matrix_terms_csv = paths.get("matrix_terms_csv")
    matrix_rows = _read_csv(matrix_terms_csv)
    family_rows = matrix_family_closure_summary(matrix_rows)
    snippets = audit_source_snippets(xstar_source_root)
    n_terms = len(matrix_rows)
    n_proxy = sum(int(r.get("n_proxy_or_scaffold_terms") or 0) for r in family_rows)
    n_parent = sum(int(r.get("n_matrix_terms") or 0) for r in family_rows if str(r.get("data_type")) in {"70", "74", "77", "99"})
    n_high_priority = sum(1 for r in family_rows if str(r.get("closure_class") or "").startswith(("parent_", "mixed_proxy")) or "proxy" in str(r.get("closure_class") or ""))
    n_snip = len(snippets)
    n_snip_matched = sum(1 for r in snippets if r.get("matched") is True)
    status = "source_code_equivalent_closure_audit_completed"
    if not matrix_rows:
        status = "matrix_terms_missing_or_empty"
    if xstar_source_root is not None and n_snip and n_snip_matched < n_snip:
        status += "_with_source_snippet_warnings"
    summary = {
        "audit_version": "v0.3.175",
        "ion": ion,
        "status": status,
        "benchmark_dir": str(benchmark_dir or ""),
        "matrix_terms_csv": str(matrix_terms_csv or ""),
        "xstar_source_root": str(xstar_source_root or ""),
        "n_matrix_terms": n_terms,
        "n_matrix_families": len(family_rows),
        "n_proxy_or_scaffold_terms": n_proxy,
        "n_parent_superlevel_or_inverse_terms": n_parent,
        "n_high_priority_closure_gap_families": n_high_priority,
        "n_source_snippets_matched": n_snip_matched,
        "n_source_snippets_total": n_snip,
        "source_equivalent_mode_ready": False,
        "blocking_gap_1": "universal ucalc ans1..ans6 probe is not yet available",
        "blocking_gap_2": "calc_hmc_ion ajisi/indbi insertion probe is not yet available",
        "blocking_gap_3": "type-99/type-70/type-74 parent/superlevel closure still contains proxy/scaffold logic",
        "recommended_next_step": "instrument XSTAR ucalc and calc_hmc_ion, then compare every Python matrix row against Fortran ans1..ans6 and ajisi/indbi rows before solving populations",
    }
    return {
        "summary": summary,
        "family_rows": family_rows,
        "required_fortran_subroutines": required_fortran_subroutine_rows(),
        "ucalc_probe_schema": ucalc_probe_schema_rows(),
        "calc_hmc_ion_probe_schema": calc_hmc_ion_probe_schema_rows(),
        "population_probe_schema": population_probe_schema_rows(),
        "implementation_plan": implementation_plan_rows(),
        "source_snippets": snippets,
        "fortran_probe_template": fortran_probe_template(),
    }


def write_source_code_equivalent_local_closure_audit(audit: Mapping[str, Any], out_dir: str | Path) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = "xstar_source_code_equivalent_local_closure_audit"
    paths = {
        "family_summary_csv": out / f"{prefix}_family_summary.csv",
        "required_fortran_subroutines_csv": out / f"{prefix}_required_fortran_subroutines.csv",
        "ucalc_probe_schema_csv": out / f"{prefix}_ucalc_probe_schema.csv",
        "calc_hmc_ion_probe_schema_csv": out / f"{prefix}_calc_hmc_ion_probe_schema.csv",
        "population_probe_schema_csv": out / f"{prefix}_population_probe_schema.csv",
        "implementation_plan_csv": out / f"{prefix}_implementation_plan.csv",
        "source_snippets_csv": out / f"{prefix}_source_snippets.csv",
        "fortran_probe_template": out / f"{prefix}_fortran_probe_template.f90",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    _write_csv(paths["family_summary_csv"], audit.get("family_rows", []))
    _write_csv(paths["required_fortran_subroutines_csv"], audit.get("required_fortran_subroutines", []))
    _write_csv(paths["ucalc_probe_schema_csv"], audit.get("ucalc_probe_schema", []))
    _write_csv(paths["calc_hmc_ion_probe_schema_csv"], audit.get("calc_hmc_ion_probe_schema", []))
    _write_csv(paths["population_probe_schema_csv"], audit.get("population_probe_schema", []))
    _write_csv(paths["implementation_plan_csv"], audit.get("implementation_plan", []))
    _write_csv(paths["source_snippets_csv"], audit.get("source_snippets", []))
    paths["fortran_probe_template"].write_text(str(audit.get("fortran_probe_template") or ""), encoding="utf-8")
    serializable = {k: v for k, v in audit.items() if k != "fortran_probe_template"}
    serializable["fortran_probe_template"] = str(audit.get("fortran_probe_template") or "")
    paths["json"].write_text(json.dumps(serializable, indent=2, sort_keys=True), encoding="utf-8")
    s = audit.get("summary", {})
    lines = [
        "# XSTAR source-code-equivalent local closure audit",
        "",
        f"- audit_version: `{s.get('audit_version')}`",
        f"- ion: `{s.get('ion')}`",
        f"- status: `{s.get('status')}`",
        f"- matrix terms: `{s.get('n_matrix_terms')}`",
        f"- matrix families: `{s.get('n_matrix_families')}`",
        f"- proxy/scaffold terms: `{s.get('n_proxy_or_scaffold_terms')}`",
        f"- parent/superlevel/inverse terms: `{s.get('n_parent_superlevel_or_inverse_terms')}`",
        f"- source snippets matched: `{s.get('n_source_snippets_matched')}/{s.get('n_source_snippets_total')}`",
        "",
        "## Blocking gaps before source-equivalent population parity",
        "",
        f"1. {s.get('blocking_gap_1')}",
        f"2. {s.get('blocking_gap_2')}",
        f"3. {s.get('blocking_gap_3')}",
        "",
        "## Required outputs",
        "",
        "The audit writes family summaries, required Fortran subroutines, ucalc/matrix/population probe schemas, source snippets, and an implementation plan.",
        "",
        "## Recommendation",
        "",
        str(s.get("recommended_next_step") or ""),
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
