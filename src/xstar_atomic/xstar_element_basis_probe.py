"""Prepare and validate XSTAR element-population basis probes.

The population-closure parity audit showed that the current Python
``xstar_ipmat2_index`` mapping covers only a tiny fraction of XSTAR's solved
O-element population.  The missing information is the exact element-basis row
construction inside ``calc_hmc_element.f90``: how XSTAR maps ion-local level
indices and parent-continuum/shared rows onto the compact ``ipmat2`` basis passed
into ``msolvelucy``.

This module generates a lightweight Fortran probe for that row topology.  The
intended capture sites are in ``calc_hmc_element.f90`` during the second pass over
ions, where ``ipmat2``, ``ipmat``, ``klion``, ``jkk_ion``, ``nlev``, ``nsp``,
``nionp``, ``nsup(:)``, ``nion(:)``, and ``x(:)`` are all in scope.

Diagnostic only: no XSTAR or Python solver physics is changed.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


_REQUIRED_COLUMNS = [
    "basis_solve_call_id",
    "basis_capture_index",
    "row_kind",
    "ml_element",
    "element_z",
    "nionp_current",
    "nsp_current",
    "ml_ion",
    "klion",
    "jkk_ion",
    "nlev",
    "ion_start_ipmat2",
    "ion_start_ipmat",
    "local_level_index",
    "element_ipmat_index",
    "xstar_ipmat2_index",
    "x_population",
    "nsup",
    "nion",
]


def _as_int(v: Any, default: int | None = None) -> int | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        f = float(v)
        if not math.isfinite(f):
            return default
        return int(round(f))
    except Exception:
        return default


def _as_float(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        f = float(v)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def _read_csv(path: str | Path | None) -> Tuple[List[Dict[str, str]], str, str]:
    if path is None or not str(path).strip():
        return [], "csv_not_supplied", ""
    p = Path(path)
    if p.is_dir():
        candidate = p / "xstar_element_basis_probe.csv"
        if candidate.exists():
            p = candidate
        else:
            matches = sorted(p.rglob("*element*basis*probe*.csv"))
            if len(matches) == 1:
                p = matches[0]
            elif matches:
                return [], "directory_multiple_csv_candidates", str(p)
    if not p.exists():
        return [], "csv_missing", str(p)
    try:
        with p.open("r", newline="", encoding="utf-8") as fh:
            return [dict(row) for row in csv.DictReader(fh)], "csv_loaded", str(p)
    except Exception as exc:  # pragma: no cover
        return [], f"csv_read_error:{type(exc).__name__}", str(p)


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for k in row:
                if k not in ordered:
                    ordered.append(str(k))
        fields = ordered or ["status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def element_basis_probe_schema_rows() -> List[Dict[str, str]]:
    cols = [
        ("basis_solve_call_id", "yes", "Shared id for one calc_hmc_element element-basis construction."),
        ("basis_capture_index", "yes", "Sequential row-write id within the helper."),
        ("row_kind", "yes", "basis_begin, ion_population_row, ion_parent_continuum_link, or final_parent_continuum_slot."),
        ("ml_element", "yes", "ATDB pointer for the current element record."),
        ("element_z", "yes", "Element nuclear charge/index (jk in calc_hmc_element)."),
        ("nionp_current", "yes", "XSTAR element ion occurrence counter at this row."),
        ("nsp_current", "yes", "Current superlevel counter around this row."),
        ("ml_ion", "recommended", "ATDB pointer for the current ion record, blank for basis_begin/final row."),
        ("klion", "recommended", "Ion index relative to element from type-12 record."),
        ("jkk_ion", "recommended", "Global XSTAR ion index from type-12 record."),
        ("nlev", "recommended", "Number of ATDB levels for this ion."),
        ("ion_start_ipmat2", "recommended", "ipmat2 offset before this ion contributes rows."),
        ("ion_start_ipmat", "recommended", "full element xileve/rnise offset before this ion contributes rows."),
        ("local_level_index", "recommended", "ion-local level index mm; -1 for basis_begin/final rows."),
        ("element_ipmat_index", "recommended", "source xileve/rnise index mm+ipmat; -1 for basis_begin/final rows."),
        ("xstar_ipmat2_index", "yes", "compact element population row index passed to msolvelucy."),
        ("x_population", "recommended", "x(row) at the capture point."),
        ("nsup", "recommended", "XSTAR superlevel id for this compact row, if already assigned."),
        ("nion", "recommended", "XSTAR ion occurrence id for this compact row, if already assigned."),
        ("t_xstar_1e4K", "recommended", "XSTAR temperature variable t; Kelvin=t*1e4."),
        ("xee", "recommended", "Electron fraction relative to H."),
        ("xpx", "recommended", "Hydrogen density scalar."),
        ("cfrac", "recommended", "Covering fraction."),
    ]
    return [{"column": c, "required": r, "description": d} for c, r, d in cols]


def element_basis_fortran_helper() -> str:
    """Return conservative free-form Fortran helper source."""
    return """! xstar-atomic debug probe helper for element-basis mapping.
! Diagnostic only.  Generated by xstar-atomic v0.3.192.
subroutine xap_basis_begin(fname, ml_element, element_z, t, xee, xpx, cfrac)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_element, element_z
  real*8, intent(in) :: t, xee, xpx, cfrac
  integer :: xap_basis_solve_call_id
  common /xap_basis_probe_state/ xap_basis_solve_call_id
  save /xap_basis_probe_state/
  data xap_basis_solve_call_id /0/
  xap_basis_solve_call_id = xap_basis_solve_call_id + 1
  call xap_basis_write(fname, xap_basis_solve_call_id, 'basis_begin', &
      ml_element, element_z, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, &
      -1, 0.d0, -1, -1, t, xee, xpx, cfrac)
  return
end subroutine xap_basis_begin

subroutine xap_basis_ion(fname, ml_element, element_z, nionp_current, &
    nsp_current, ml_ion, klion, jkk_ion, nlev, ion_start_ipmat2, &
    ion_start_ipmat, t, xee, xpx, cfrac, x, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_element, element_z, nionp_current, nsp_current
  integer, intent(in) :: ml_ion, klion, jkk_ion, nlev
  integer, intent(in) :: ion_start_ipmat2, ion_start_ipmat
  real*8, intent(in) :: t, xee, xpx, cfrac
  real*8, intent(in) :: x(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: mm, row, eidx
  integer :: xap_basis_solve_call_id
  common /xap_basis_probe_state/ xap_basis_solve_call_id
  save /xap_basis_probe_state/
  if (xap_basis_solve_call_id .le. 0) xap_basis_solve_call_id = 1
  do mm = 1, max(0, nlev - 1)
    row = ion_start_ipmat2 + mm
    eidx = ion_start_ipmat + mm
    call xap_basis_write(fname, xap_basis_solve_call_id, 'ion_population_row', &
        ml_element, element_z, nionp_current, nsp_current, ml_ion, klion, &
        jkk_ion, nlev, ion_start_ipmat2, ion_start_ipmat, mm, eidx, row, &
        x(row), nsup(row), nion(row), t, xee, xpx, cfrac)
  enddo
  if (nlev .ge. 1) then
    mm = nlev
    row = ion_start_ipmat2 + mm
    eidx = ion_start_ipmat + mm
    call xap_basis_write(fname, xap_basis_solve_call_id, 'ion_parent_continuum_link', &
        ml_element, element_z, nionp_current, nsp_current, ml_ion, klion, &
        jkk_ion, nlev, ion_start_ipmat2, ion_start_ipmat, mm, eidx, row, &
        x(row), -1, -1, t, xee, xpx, cfrac)
  endif
  return
end subroutine xap_basis_ion

subroutine xap_basis_final(fname, ml_element, element_z, ipmat2_final, nsp, &
    nionp, t, xee, xpx, cfrac, x, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_element, element_z, ipmat2_final, nsp, nionp
  real*8, intent(in) :: t, xee, xpx, cfrac
  real*8, intent(in) :: x(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: xap_basis_solve_call_id
  common /xap_basis_probe_state/ xap_basis_solve_call_id
  save /xap_basis_probe_state/
  if (xap_basis_solve_call_id .le. 0) xap_basis_solve_call_id = 1
  call xap_basis_write(fname, xap_basis_solve_call_id, 'final_parent_continuum_slot', &
      ml_element, element_z, nionp, nsp, -1, -1, -1, -1, -1, -1, -1, -1, &
      ipmat2_final, x(ipmat2_final), nsup(ipmat2_final), nion(ipmat2_final), &
      t, xee, xpx, cfrac)
  return
end subroutine xap_basis_final

subroutine xap_basis_write(fname, solve_id, row_kind, ml_element, element_z, &
    nionp_current, nsp_current, ml_ion, klion, jkk_ion, nlev, &
    ion_start_ipmat2, ion_start_ipmat, local_level_index, element_ipmat_index, &
    xstar_ipmat2_index, x_population, nsup_value, nion_value, &
    t, xee, xpx, cfrac)
  implicit none
  character(len=*), intent(in) :: fname
  character(len=*), intent(in) :: row_kind
  integer, intent(in) :: solve_id, ml_element, element_z, nionp_current, nsp_current
  integer, intent(in) :: ml_ion, klion, jkk_ion, nlev, ion_start_ipmat2
  integer, intent(in) :: ion_start_ipmat, local_level_index, element_ipmat_index
  integer, intent(in) :: xstar_ipmat2_index, nsup_value, nion_value
  real*8, intent(in) :: x_population, t, xee, xpx, cfrac
  integer :: lun, ios
  logical :: exists
  integer, save :: capture_index = 0
  capture_index = capture_index + 1
  lun = 936
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', &
      action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) then
    write(lun,'(A)') 'basis_solve_call_id,basis_capture_index,row_kind,'// &
      'ml_element,element_z,nionp_current,nsp_current,ml_ion,klion,'// &
      'jkk_ion,nlev,ion_start_ipmat2,ion_start_ipmat,local_level_index,'// &
      'element_ipmat_index,xstar_ipmat2_index,x_population,nsup,nion,'// &
      't_xstar_1e4K,xee,xpx,cfrac'
  endif
  write(lun,9001) solve_id, capture_index, trim(row_kind), ml_element, &
      element_z, nionp_current, nsp_current, ml_ion, klion, jkk_ion, nlev, &
      ion_start_ipmat2, ion_start_ipmat, local_level_index, element_ipmat_index, &
      xstar_ipmat2_index, x_population, nsup_value, nion_value, &
      t, xee, xpx, cfrac
  close(lun)
  return
9001 format(i12,',',i12,',',a,',',i12,',',i12,',',i12,',',i12,',', &
      i12,',',i12,',',i12,',',i12,',',i12,',',i12,',',i12,',', &
      i12,',',i12,',',1pe24.16,',',i12,',',i12,',', &
      1pe24.16,',',1pe24.16,',',1pe24.16,',',1pe24.16)
end subroutine xap_basis_write
"""


def basis_begin_insertion() -> str:
    return """! xstar-atomic element-basis mapping probe.
! Insert after calc_hmc_element initializes the second-pass element basis:
!   ipmat=0; nindbi=0; ipmat2=0; ml_ion=derivedpointers%npfirst(...)
      call xap_basis_begin('xstar_element_basis_probe.csv', &
     &     ml_element, jk, t, xee, xpx, cfrac)
"""


def basis_ion_rows_insertion() -> str:
    return """! xstar-atomic element-basis mapping probe.
! Insert after the do mm=1,nlev block that assigns x(mm+ipmat2), and before:
!   ipmat2=ipmat2+nlev-1
! It records the compact XSTAR ipmat2 rows contributed by this ion and the
! parent-continuum link row that is shared with the next ion/final slot.
      call xap_basis_ion('xstar_element_basis_probe.csv', &
     &     ml_element, jk, nionp, nsp, ml_ion, klion, jkk_ion, nlev, &
     &     ipmat2, ipmat, t, xee, xpx, cfrac, x, nsup, nion)
"""


def basis_final_row_insertion() -> str:
    return """! xstar-atomic element-basis mapping probe.
! Insert immediately after calc_hmc_element executes:
!   ipmat2=ipmat2+1
! for the final superlevel/parent-continuum slot, and before msolvelucy.
      call xap_basis_final('xstar_element_basis_probe.csv', &
     &     ml_element, jk, ipmat2, nsp, nionp, t, xee, xpx, cfrac, &
     &     x, nsup, nion)
"""


def summarize_element_basis_probe_csv(path: str | Path | None) -> Dict[str, Any]:
    rows, status, resolved = _read_csv(path)
    missing: List[str] = []
    if rows:
        missing = [c for c in _REQUIRED_COLUMNS if c not in rows[0]]
    good_rows = [r for r in rows if not missing]
    solves = defaultdict(list)
    for r in good_rows:
        sid = _as_int(r.get("basis_solve_call_id"), None)
        if sid is not None:
            solves[sid].append(r)

    solve_summary: List[Dict[str, Any]] = []
    total_duplicate_solver_rows = 0
    total_unique_population_rows = 0
    total_parent_links = 0
    ready_solves = 0
    for sid, rr in sorted(solves.items()):
        kinds = Counter(r.get("row_kind", "") for r in rr)
        population_rows = [r for r in rr if r.get("row_kind") in {"ion_population_row", "final_parent_continuum_slot"}]
        parent_links = [r for r in rr if r.get("row_kind") == "ion_parent_continuum_link"]
        unique_indices = { _as_int(r.get("xstar_ipmat2_index"), None) for r in population_rows }
        unique_indices.discard(None)
        role_indices = [ _as_int(r.get("xstar_ipmat2_index"), None) for r in rr if _as_int(r.get("xstar_ipmat2_index"), None) and _as_int(r.get("xstar_ipmat2_index"), None) > 0]
        dup_count = len(role_indices) - len(set(role_indices))
        max_row = max(unique_indices) if unique_indices else 0
        nion_values = [_as_int(r.get("nion"), None) for r in population_rows]
        nsup_values = [_as_int(r.get("nsup"), None) for r in population_rows]
        nion_values = [x for x in nion_values if x is not None and x >= 0]
        nsup_values = [x for x in nsup_values if x is not None and x >= 0]
        solve_ready = bool(kinds.get("basis_begin") and kinds.get("ion_population_row") and kinds.get("final_parent_continuum_slot"))
        ready_solves += 1 if solve_ready else 0
        total_duplicate_solver_rows += dup_count
        total_unique_population_rows += len(unique_indices)
        total_parent_links += len(parent_links)
        solve_summary.append({
            "basis_solve_call_id": sid,
            "n_rows": len(rr),
            "n_basis_begin_rows": kinds.get("basis_begin", 0),
            "n_ion_population_rows": kinds.get("ion_population_row", 0),
            "n_parent_continuum_link_rows": kinds.get("ion_parent_continuum_link", 0),
            "n_final_parent_continuum_slot_rows": kinds.get("final_parent_continuum_slot", 0),
            "n_unique_solver_population_rows": len(unique_indices),
            "max_xstar_ipmat2_index": max_row,
            "n_duplicate_row_roles_including_parent_links": dup_count,
            "nion_min": min(nion_values) if nion_values else "",
            "nion_max": max(nion_values) if nion_values else "",
            "nsup_min": min(nsup_values) if nsup_values else "",
            "nsup_max": max(nsup_values) if nsup_values else "",
            "basis_probe_solve_ready": solve_ready,
        })

    kind_counts = Counter(r.get("row_kind", "") for r in good_rows)
    summary = {
        "audit_version": "v0.3.192",
        "status": "csv_loaded_ready" if (status == "csv_loaded" and ready_solves > 0 and not missing) else status if status != "csv_loaded" else "csv_loaded_not_ready",
        "element_basis_probe_csv": resolved,
        "n_rows": len(rows),
        "n_basis_solve_calls": len(solves),
        "n_ready_basis_solve_calls": ready_solves,
        "n_basis_begin_rows": kind_counts.get("basis_begin", 0),
        "n_ion_population_rows": kind_counts.get("ion_population_row", 0),
        "n_parent_continuum_link_rows": kind_counts.get("ion_parent_continuum_link", 0),
        "n_final_parent_continuum_slot_rows": kind_counts.get("final_parent_continuum_slot", 0),
        "n_unique_solver_population_rows_total_over_solves": total_unique_population_rows,
        "n_parent_link_rows_total": total_parent_links,
        "n_duplicate_row_roles_total": total_duplicate_solver_rows,
        "missing_required_columns": missing,
        "probe_ready_for_element_basis_mapping": bool(ready_solves > 0 and not missing),
        "correct_capture_site": "calc_hmc_element.f90 second-pass basis construction: begin before ion loop, ion rows after x(mm+ipmat2) mapping and before ipmat2 increment, final row after final ipmat2 increment",
        "correct_fortran_product": "xstar_element_basis_probe.csv",
    }
    return {"summary": summary, "solve_summary": solve_summary}


def write_element_basis_probe_products(out_dir: str | Path, summary: Mapping[str, Any] | None = None) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if summary is None:
        summary = summarize_element_basis_probe_csv(None)
    paths = {
        "helper_fortran": out / "xstar_atomic_element_basis_probe_helpers.f90",
        "basis_begin_insertion": out / "calc_hmc_element_basis_begin_insertion.f90",
        "basis_ion_rows_insertion": out / "calc_hmc_element_basis_ion_rows_insertion.f90",
        "basis_final_row_insertion": out / "calc_hmc_element_basis_final_row_insertion.f90",
        "patch_notes": out / "calc_hmc_element_element_basis_probe_notes.md",
        "schema_csv": out / "xstar_element_basis_probe_schema.csv",
        "basis_solve_summary_csv": out / "xstar_element_basis_probe_solve_summary.csv",
        "json": out / "xstar_element_basis_probe.json",
        "markdown": out / "xstar_element_basis_probe.md",
    }
    paths["helper_fortran"].write_text(element_basis_fortran_helper(), encoding="utf-8")
    paths["basis_begin_insertion"].write_text(basis_begin_insertion(), encoding="utf-8")
    paths["basis_ion_rows_insertion"].write_text(basis_ion_rows_insertion(), encoding="utf-8")
    paths["basis_final_row_insertion"].write_text(basis_final_row_insertion(), encoding="utf-8")
    _write_csv(paths["schema_csv"], element_basis_probe_schema_rows())
    _write_csv(paths["basis_solve_summary_csv"], list(summary.get("solve_summary", []) or []))
    paths["json"].write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    s = dict(summary.get("summary", {}) or {})
    notes = [
        "# XSTAR element-basis mapping probe",
        "",
        f"audit_version: `{s.get('audit_version', 'v0.3.192')}`",
        f"status: `{s.get('status')}`",
        f"probe_ready_for_element_basis_mapping: `{s.get('probe_ready_for_element_basis_mapping')}`",
        "",
        "## Purpose",
        "",
        "Capture XSTAR's compact element `ipmat2` basis directly from `calc_hmc_element.f90`, including ion-local level links, parent-continuum/shared rows, and the final element closure row.",
        "",
        "## Patch sites",
        "",
        "1. Copy `xstar_atomic_element_basis_probe_helpers.f90` into `xstarlib/src/` and add it to the XSTAR library build.",
        "2. Insert `calc_hmc_element_basis_begin_insertion.f90` after `ipmat=0; nindbi=0; ipmat2=0` at the start of the second-pass basis construction.",
        "3. Insert `calc_hmc_element_basis_ion_rows_insertion.f90` after the `do mm=1,nlev` block that assigns `x(mm+ipmat2)`, and before `ipmat2=ipmat2+nlev-1`.",
        "4. Insert `calc_hmc_element_basis_final_row_insertion.f90` immediately after the final `ipmat2=ipmat2+1`, before `msolvelucy`.",
        "5. Remove stale `xstar_element_basis_probe.csv` before rerunning XSTAR.",
        "",
        "## Current summary",
        "",
    ]
    for key in [
        "element_basis_probe_csv", "n_rows", "n_basis_solve_calls", "n_ready_basis_solve_calls",
        "n_ion_population_rows", "n_parent_continuum_link_rows", "n_final_parent_continuum_slot_rows",
        "probe_ready_for_element_basis_mapping",
    ]:
        notes.append(f"- {key}: `{s.get(key)}`")
    notes.append("")
    notes.append("Diagnostic only; no solver physics changed.")
    paths["markdown"].write_text("\n".join(notes) + "\n", encoding="utf-8")
    paths["patch_notes"].write_text("\n".join(notes) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
