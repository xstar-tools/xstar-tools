"""Instrumentation helpers for XSTAR population/source closure probes.

The record-level ``ucalc`` and ``calc_hmc_ion`` probes verify local rate and
matrix-row insertion parity.  They do not expose how XSTAR closes the full
multi-ion element population problem: superlevel grouping, parent-ion coupling,
initial/right-hand-side population vector, normalization, and the final
``msolvelucy`` solution.  This module prepares and validates a lightweight
Fortran probe for those closure quantities.

The intended XSTAR capture site is ``calc_hmc_element.f90`` immediately before
and immediately after the call to ``msolvelucy``.  The probe writes one CSV row
per element-matrix population index for both stages, including ``x(mm)``,
``nsup(mm)``, and ``nion(mm)``.  It is diagnostic infrastructure only; it does
not change solver physics.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


_REQUIRED = [
    "capture_index",
    "stage",
    "ml_element",
    "element_z",
    "ipmat2",
    "nsp",
    "nionp",
    "nindbe",
    "nit",
    "nit2",
    "nit3",
    "level_index",
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


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(str(key))
        fields = fields or ["status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _read_csv(path: str | Path | None) -> Tuple[List[Dict[str, str]], str, str]:
    if path is None or not str(path).strip():
        return [], "csv_not_supplied", ""
    p = Path(path)
    if p.is_dir():
        candidate = p / "xstar_population_closure_probe.csv"
        if candidate.exists():
            p = candidate
        else:
            matches = sorted(p.rglob("*population*closure*probe*.csv"))
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


def population_closure_probe_schema_rows() -> List[Dict[str, str]]:
    cols = [
        ("capture_index", "yes", "Sequential row-dump call id for each population-stage dump."),
        ("solve_call_id", "recommended", "Shared before/after msolvelucy solve-call id. New in v0.3.189."),
        ("stage_capture_index", "recommended", "Independent stage-dump id. New in v0.3.189."),
        ("stage", "yes", "before_msolvelucy or after_msolvelucy."),
        ("ml_element", "yes", "XSTAR ATDB pointer for the current element record."),
        ("element_z", "yes", "Element nuclear charge/index from the element record."),
        ("ipmat2", "yes", "Element-population matrix dimension including final superlevel/continuum slot."),
        ("nsp", "yes", "Number of superlevels passed to msolvelucy."),
        ("nionp", "yes", "Number of ions represented in the current element problem."),
        ("nindbe", "yes", "Number of element-level sparse matrix entries passed to msolvelucy."),
        ("nit", "yes", "msolvelucy primary iteration count; zero for before stage."),
        ("nit2", "yes", "msolvelucy secondary iteration count; zero for before stage."),
        ("nit3", "yes", "msolvelucy tertiary iteration count; zero for before stage."),
        ("level_index", "yes", "1-based element-matrix population index."),
        ("x_population", "yes", "XSTAR x(level_index) before or after msolvelucy."),
        ("nsup", "yes", "Superlevel index for this element-matrix row."),
        ("nion", "yes", "Ion counter for this element-matrix row."),
        ("t_xstar_1e4K", "recommended", "XSTAR temperature variable t; Kelvin=t*1e4."),
        ("xee", "recommended", "Electron fraction relative to H."),
        ("xpx", "recommended", "Hydrogen density scalar."),
        ("cfrac", "recommended", "Covering fraction."),
    ]
    return [{"column": c, "required": r, "description": d} for c, r, d in cols]


def population_closure_fortran_helper() -> str:
    """Return a conservative free-form Fortran helper for HEASoft/XSTAR builds.

    v0.3.189 adds paired before/after wrappers.  The before wrapper increments a
    shared ``solve_call_id``; the after wrapper reuses it.  The legacy
    ``xap_pstate`` entry point remains available for older hand patches.
    """
    return """! xstar-atomic debug probe helper for population/source closure.
! Diagnostic only.  Generated by xstar-atomic v0.3.189.
subroutine xap_pbefore(fname, ml_element, element_z, ipmat2, nsp, nionp, &
    nindbe, t, xee, xpx, cfrac, x, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_element, element_z, ipmat2, nsp, nionp
  integer, intent(in) :: nindbe
  real*8, intent(in) :: t, xee, xpx, cfrac
  real*8, intent(in) :: x(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: xap_pop_solve_call_id
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  data xap_pop_solve_call_id /0/
  xap_pop_solve_call_id = xap_pop_solve_call_id + 1
  call xap_pstate189(fname, 'before_msolvelucy', xap_pop_solve_call_id, &
      ml_element, element_z, ipmat2, nsp, nionp, nindbe, 0, 0, 0, &
      t, xee, xpx, cfrac, x, nsup, nion)
  return
end subroutine xap_pbefore

subroutine xap_pafter(fname, ml_element, element_z, ipmat2, nsp, nionp, &
    nindbe, nit, nit2, nit3, t, xee, xpx, cfrac, x, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_element, element_z, ipmat2, nsp, nionp
  integer, intent(in) :: nindbe, nit, nit2, nit3
  real*8, intent(in) :: t, xee, xpx, cfrac
  real*8, intent(in) :: x(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: xap_pop_solve_call_id
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (xap_pop_solve_call_id .le. 0) xap_pop_solve_call_id = 1
  call xap_pstate189(fname, 'after_msolvelucy', xap_pop_solve_call_id, &
      ml_element, element_z, ipmat2, nsp, nionp, nindbe, nit, nit2, nit3, &
      t, xee, xpx, cfrac, x, nsup, nion)
  return
end subroutine xap_pafter

subroutine xap_pstate(fname, stage, ml_element, element_z, ipmat2, nsp, &
    nionp, nindbe, nit, nit2, nit3, t, xee, xpx, cfrac, x, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  character(len=*), intent(in) :: stage
  integer, intent(in) :: ml_element, element_z, ipmat2, nsp, nionp
  integer, intent(in) :: nindbe, nit, nit2, nit3
  real*8, intent(in) :: t, xee, xpx, cfrac
  real*8, intent(in) :: x(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: xap_pop_solve_call_id
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (trim(stage) .eq. 'before_msolvelucy') then
    xap_pop_solve_call_id = xap_pop_solve_call_id + 1
  else if (xap_pop_solve_call_id .le. 0) then
    xap_pop_solve_call_id = 1
  endif
  call xap_pstate189(fname, stage, xap_pop_solve_call_id, ml_element, &
      element_z, ipmat2, nsp, nionp, nindbe, nit, nit2, nit3, &
      t, xee, xpx, cfrac, x, nsup, nion)
  return
end subroutine xap_pstate

subroutine xap_pstate189(fname, stage, solve_call_id, ml_element, element_z, &
    ipmat2, nsp, nionp, nindbe, nit, nit2, nit3, t, xee, xpx, cfrac, &
    x, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  character(len=*), intent(in) :: stage
  integer, intent(in) :: solve_call_id, ml_element, element_z, ipmat2, nsp, nionp
  integer, intent(in) :: nindbe, nit, nit2, nit3
  real*8, intent(in) :: t, xee, xpx, cfrac
  real*8, intent(in) :: x(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: lun, ios, mm
  logical :: exists
  integer, save :: stage_capture_index = 0
  stage_capture_index = stage_capture_index + 1
  lun = 934
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', &
      action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) then
    write(lun,'(A)') 'capture_index,solve_call_id,stage_capture_index,stage,'// &
      'ml_element,element_z,ipmat2,nsp,nionp,nindbe,nit,nit2,nit3,'// &
      'level_index,x_population,nsup,nion,t_xstar_1e4K,xee,xpx,cfrac'
  endif
  do mm = 1, ipmat2
    write(lun,9001) stage_capture_index, solve_call_id, stage_capture_index, &
      trim(stage), ml_element, element_z, ipmat2, nsp, nionp, nindbe, &
      nit, nit2, nit3, mm, x(mm), nsup(mm), nion(mm), t, xee, xpx, cfrac
  enddo
  close(lun)
  return
9001 format(i12,',',i12,',',i12,',',a,',',i12,',',i12,',',i12,',', &
      i12,',',i12,',',i12,',',i12,',',i12,',',i12,',',i12,',', &
      1pe24.16,',',i12,',',i12,',',1pe24.16,',',1pe24.16,',', &
      1pe24.16,',',1pe24.16)
end subroutine xap_pstate189
"""


def before_msolvelucy_insertion() -> str:
    return """! xstar-atomic population/source closure probe.
! Insert immediately before_msolvelucy: before the single call msolvelucy(...) in calc_hmc_element.f90.
! v0.3.189: this wrapper starts a shared solve_call_id for the following after call.
      call xap_pbefore('xstar_population_closure_probe.csv', &
     &     ml_element, jk, ipmat2, nsp, nionp, nindbe, &
     &     t, xee, xpx, cfrac, x, nsup, nion)
"""


def after_msolvelucy_insertion() -> str:
    return """! xstar-atomic population/source closure probe.
! Insert immediately after_msolvelucy: after the same single call msolvelucy(...) in calc_hmc_element.f90.
! v0.3.189: this wrapper reuses the solve_call_id created by xap_pbefore.
      call xap_pafter('xstar_population_closure_probe.csv', &
     &     ml_element, jk, ipmat2, nsp, nionp, nindbe, nit, nit2, nit3, &
     &     t, xee, xpx, cfrac, x, nsup, nion)
"""


def patch_notes() -> str:
    return """# XSTAR population/source closure probe insertion notes

Patch a debug copy of `xstarlib/src/calc_hmc_element.f90`.

1. Add `xstar_tools_population_closure_probe_helpers.f90` to
   `xstarlib/src/Makefile` in `HD_LIBRARY_SRC_f90`.

2. Remove any older probe calls before repatching.  In particular, delete any
   old calls to `xap_pstate(...)`, `xap_pbefore(...)`, or `xap_pafter(...)` from
   previous attempts.  Multiple probe insertions produce extra `after` captures.

3. Insert `calc_hmc_element_before_msolvelucy_insertion.f90` immediately before
   the existing `call msolvelucy(ajise,cjise,cjise2, ...)` block.

4. Insert `calc_hmc_element_after_msolvelucy_insertion.f90` immediately after
   the full `call msolvelucy(...)` block and before `chisq(...)` / map-back to
   `xileve`.

5. Rebuild XSTAR, remove old `xstar_population_closure_probe.csv`, and rerun
   the same O VII case.  Removing the old CSV is important because Fortran
   `save` counters restart in each executable run and appending can merge stale
   captures with new ones.

6. Validate with:

```bash
PYTHONPATH=src python examples/82_prepare_xstar_population_closure_probe.py \\
  --population-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv \\
  --out-dir xstar_population_closure_probe_o7_v03189_validated \\
  --print-summary
```

A ready probe has paired `before_msolvelucy` and `after_msolvelucy` captures
with matching `solve_call_id`, element metadata, and `ipmat2` row counts.
"""


def _capture_sort_key(row: Mapping[str, Any]) -> Tuple[int, str]:
    return (_as_int(row.get("capture_index"), 0) or 0, str(row.get("capture_index") or ""))


def _same_population_problem(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    keys = ["ml_element", "element_z", "ipmat2", "nsp", "nionp", "nindbe"]
    return all(str(a.get(k, "")).strip() == str(b.get(k, "")).strip() for k in keys)


def _pair_capture_rows(capture_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """Return before/after capture pairs.

    v0.3.189 CSVs include a shared solve_call_id and can be paired directly.
    Older v0.3.188 CSVs are paired by scanning forward from each valid before
    capture to the next valid after capture with matching element/problem
    metadata.  This lets the validator salvage a usable paired subset even when
    an old after-only insertion or stale appended CSV rows are present.
    """
    if any(str(r.get("solve_call_id") or "").strip() for r in capture_rows):
        by_solve: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for r in capture_rows:
            sid = str(r.get("solve_call_id") or "").strip()
            if not sid:
                continue
            stage = str(r.get("stage") or "")
            by_solve.setdefault(sid, {})[stage] = r
        pairs = []
        for sid, d in sorted(by_solve.items(), key=lambda kv: (_as_int(kv[0], 0) or 0, kv[0])):
            b = d.get("before_msolvelucy")
            a = d.get("after_msolvelucy")
            if b and a:
                pair = {"solve_call_id": sid, "before": b, "after": a}
                pairs.append(pair)
        return pairs, "solve_call_id"
    # Legacy fallback.
    pairs = []
    used_after: set[int] = set()
    ordered = sorted(enumerate(capture_rows), key=lambda ir: _capture_sort_key(ir[1]))
    for i, b in ordered:
        if b.get("stage") != "before_msolvelucy":
            continue
        if not b.get("n_rows_matches_ipmat2"):
            continue
        best_j = None
        best_a = None
        for j, a in ordered:
            if j <= i or j in used_after:
                continue
            if a.get("stage") != "after_msolvelucy":
                continue
            if not a.get("n_rows_matches_ipmat2"):
                continue
            if _same_population_problem(b, a):
                best_j = j
                best_a = a
                break
        if best_a is not None and best_j is not None:
            used_after.add(best_j)
            pairs.append({"solve_call_id": "", "before": b, "after": best_a})
    return pairs, "legacy_sequential_next_matching_after"


def summarize_population_closure_probe_csv(path: str | Path | None = None) -> Dict[str, Any]:
    rows, status, resolved = _read_csv(path)
    missing = [c for c in _REQUIRED if (not rows or c not in rows[0])]
    optional_present = {
        "solve_call_id": bool(rows and "solve_call_id" in rows[0]),
        "stage_capture_index": bool(rows and "stage_capture_index" in rows[0]),
    }
    by_capture: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        by_capture.setdefault(str(r.get("capture_index") or ""), []).append(r)
    stage_counts: Dict[str, int] = {}
    for r in rows:
        stage = str(r.get("stage") or "")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    capture_rows: List[Dict[str, Any]] = []
    before_caps: List[Dict[str, Any]] = []
    after_caps: List[Dict[str, Any]] = []
    for cap, cap_rows in sorted(by_capture.items(), key=lambda kv: (_as_int(kv[0], 0) or 0, kv[0])):
        if not cap_rows:
            continue
        first = cap_rows[0]
        ipmat2 = _as_int(first.get("ipmat2"), None)
        pop_sum = sum((_as_float(r.get("x_population"), 0.0) or 0.0) for r in cap_rows)
        nonzero = sum(1 for r in cap_rows if abs(_as_float(r.get("x_population"), 0.0) or 0.0) > 0.0)
        row = {
            "capture_index": cap,
            "solve_call_id": first.get("solve_call_id", ""),
            "stage_capture_index": first.get("stage_capture_index", ""),
            "stage": first.get("stage", ""),
            "ml_element": first.get("ml_element", ""),
            "element_z": first.get("element_z", ""),
            "n_rows": len(cap_rows),
            "ipmat2": ipmat2 if ipmat2 is not None else "",
            "n_rows_matches_ipmat2": (ipmat2 == len(cap_rows)) if ipmat2 is not None else False,
            "nsp": first.get("nsp", ""),
            "nionp": first.get("nionp", ""),
            "nindbe": first.get("nindbe", ""),
            "nit": first.get("nit", ""),
            "nit2": first.get("nit2", ""),
            "nit3": first.get("nit3", ""),
            "population_sum": pop_sum,
            "n_nonzero_population_rows": nonzero,
        }
        capture_rows.append(row)
        if row["stage"] == "before_msolvelucy":
            before_caps.append(row)
        elif row["stage"] == "after_msolvelucy":
            after_caps.append(row)
    n_bad_ipmat2 = sum(1 for r in capture_rows if not r.get("n_rows_matches_ipmat2"))
    pairs, pairing_mode = _pair_capture_rows(capture_rows)
    n_pairs = len(pairs)
    n_paired_bad_ipmat2 = 0
    n_pair_ipmat2_mismatch = 0
    n_pair_problem_mismatch = 0
    max_abs_population_sum_delta = 0.0
    paired_rows: List[Dict[str, Any]] = []
    for idx, pair in enumerate(pairs, start=1):
        b = pair["before"]
        a = pair["after"]
        bad = (not b.get("n_rows_matches_ipmat2")) or (not a.get("n_rows_matches_ipmat2"))
        if bad:
            n_paired_bad_ipmat2 += 1
        ip_mismatch = b.get("ipmat2") != a.get("ipmat2")
        if ip_mismatch:
            n_pair_ipmat2_mismatch += 1
        problem_mismatch = not _same_population_problem(b, a)
        if problem_mismatch:
            n_pair_problem_mismatch += 1
        delta = None
        try:
            delta = float(a.get("population_sum") or 0.0) - float(b.get("population_sum") or 0.0)
            max_abs_population_sum_delta = max(max_abs_population_sum_delta, abs(delta))
        except Exception:
            pass
        paired_rows.append({
            "pair_index": idx,
            "solve_call_id": pair.get("solve_call_id", ""),
            "before_capture_index": b.get("capture_index", ""),
            "after_capture_index": a.get("capture_index", ""),
            "ml_element": b.get("ml_element", ""),
            "element_z": b.get("element_z", ""),
            "ipmat2_before": b.get("ipmat2", ""),
            "ipmat2_after": a.get("ipmat2", ""),
            "n_rows_before": b.get("n_rows", ""),
            "n_rows_after": a.get("n_rows", ""),
            "population_sum_before": b.get("population_sum", ""),
            "population_sum_after": a.get("population_sum", ""),
            "population_sum_delta": delta if delta is not None else "",
            "pair_ipmat2_mismatch": ip_mismatch,
            "pair_problem_mismatch": problem_mismatch,
        })
    n_unpaired_before_captures = max(0, len(before_caps) - n_pairs)
    n_unpaired_after_captures = max(0, len(after_caps) - n_pairs)
    ready = (
        status == "csv_loaded"
        and not missing
        and len(rows) > 0
        and n_pairs > 0
        and n_paired_bad_ipmat2 == 0
        and n_pair_ipmat2_mismatch == 0
        and n_pair_problem_mismatch == 0
    )
    out_status = status
    if status == "csv_loaded" and missing:
        out_status = "csv_loaded_with_schema_warnings"
    elif ready and (n_bad_ipmat2 > 0 or n_unpaired_before_captures > 0 or n_unpaired_after_captures > 0):
        out_status = "csv_loaded_ready_with_unpaired_or_bad_extra_captures"
    elif ready:
        out_status = "csv_loaded_ready"
    elif status == "csv_loaded" and not ready:
        out_status = "csv_loaded_not_ready"
    return {
        "audit_version": "v0.3.189",
        "status": out_status,
        "population_probe_csv": resolved,
        "n_rows": len(rows),
        "n_captures": len(capture_rows),
        "n_before_captures": len(before_caps),
        "n_after_captures": len(after_caps),
        "n_before_after_pairs": n_pairs,
        "pairing_mode": pairing_mode,
        "n_bad_ipmat2_captures": n_bad_ipmat2,
        "n_paired_bad_ipmat2_captures": n_paired_bad_ipmat2,
        "n_pair_ipmat2_mismatch": n_pair_ipmat2_mismatch,
        "n_pair_problem_mismatch": n_pair_problem_mismatch,
        "n_unpaired_before_captures": n_unpaired_before_captures,
        "n_unpaired_after_captures": n_unpaired_after_captures,
        "max_abs_population_sum_delta": max_abs_population_sum_delta,
        "stage_counts": stage_counts,
        "optional_columns_present": optional_present,
        "missing_required_columns": missing,
        "probe_ready_for_population_closure_parity": ready,
        "correct_capture_site": "calc_hmc_element.f90 immediately before and after the single msolvelucy call",
        "correct_fortran_product": "xstar_population_closure_probe.csv",
        "capture_rows": capture_rows,
        "paired_capture_rows": paired_rows,
    }

def write_population_closure_probe_products(
    out_dir: str | Path,
    *,
    summary: Mapping[str, Any] | None = None,
    prefix: str = "xstar_population_closure_probe",
) -> Dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    paths = {
        "helper_fortran": out / "xstar_tools_population_closure_probe_helpers.f90",
        "before_msolvelucy_insertion": out / "calc_hmc_element_before_msolvelucy_insertion.f90",
        "after_msolvelucy_insertion": out / "calc_hmc_element_after_msolvelucy_insertion.f90",
        "patch_notes": out / "calc_hmc_element_population_closure_probe_notes.md",
        "schema_csv": out / f"{prefix}_schema.csv",
        "capture_summary_csv": out / f"{prefix}_capture_summary.csv",
        "paired_capture_summary_csv": out / f"{prefix}_paired_capture_summary.csv",
        "json": out / f"{prefix}.json",
        "markdown": out / f"{prefix}.md",
    }
    paths["helper_fortran"].write_text(population_closure_fortran_helper(), encoding="utf-8")
    paths["before_msolvelucy_insertion"].write_text(before_msolvelucy_insertion(), encoding="utf-8")
    paths["after_msolvelucy_insertion"].write_text(after_msolvelucy_insertion(), encoding="utf-8")
    paths["patch_notes"].write_text(patch_notes(), encoding="utf-8")
    _write_csv(paths["schema_csv"], population_closure_probe_schema_rows(), ["column", "required", "description"])
    summary = dict(summary or summarize_population_closure_probe_csv(None))
    _write_csv(paths["capture_summary_csv"], list(summary.get("capture_rows", []) or []))
    _write_csv(paths["paired_capture_summary_csv"], list(summary.get("paired_capture_rows", []) or []))
    json_ready = {k: v for k, v in summary.items() if k not in {"capture_rows", "paired_capture_rows"}}
    json_ready["capture_rows"] = list(summary.get("capture_rows", []) or [])
    json_ready["paired_capture_rows"] = list(summary.get("paired_capture_rows", []) or [])
    paths["json"].write_text(json.dumps(json_ready, indent=2, default=str), encoding="utf-8")
    lines = [
        "# XSTAR population/source closure probe",
        "",
        f"audit_version: `{summary.get('audit_version')}`",
        f"status: `{summary.get('status')}`",
        f"probe_ready_for_population_closure_parity: `{summary.get('probe_ready_for_population_closure_parity')}`",
        "",
        "## Capture site",
        "",
        "Insert the before/after snippets in `calc_hmc_element.f90` around the `call msolvelucy(...)` block.",
        "",
        "## Summary",
        "",
        f"- n_rows: `{summary.get('n_rows')}`",
        f"- n_captures: `{summary.get('n_captures')}`",
        f"- before/after pairs: `{summary.get('n_before_after_pairs')}`",
        f"- pairing mode: `{summary.get('pairing_mode')}`",
        f"- bad ipmat2 captures: `{summary.get('n_bad_ipmat2_captures')}`",
        f"- paired bad ipmat2 captures: `{summary.get('n_paired_bad_ipmat2_captures')}`",
        f"- max population-sum delta: `{summary.get('max_abs_population_sum_delta')}`",
        "",
        "## Next use",
        "",
        "After validation, compare the XSTAR before/after population vectors to the Python local solve input/output, with level mapping from the preserved solver products.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
