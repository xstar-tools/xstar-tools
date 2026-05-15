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
        ("capture_index", "yes", "Sequential call id for each population-stage dump."),
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
    """Return a conservative free-form Fortran helper for HEASoft/XSTAR builds."""
    return """! xstar-atomic debug probe helper for population/source closure.
! Diagnostic only.  Generated by xstar-atomic v0.3.188.
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
  integer :: lun, ios, mm
  logical :: exists
  integer, save :: capture_index = 0
  capture_index = capture_index + 1
  lun = 934
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', &
      action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) then
    write(lun,'(A)') 'capture_index,stage,ml_element,element_z,ipmat2,'// &
      'nsp,nionp,nindbe,nit,nit2,nit3,level_index,x_population,'// &
      'nsup,nion,t_xstar_1e4K,xee,xpx,cfrac'
  endif
  do mm = 1, ipmat2
    write(lun,9001) capture_index, trim(stage), ml_element, element_z, &
      ipmat2, nsp, nionp, nindbe, nit, nit2, nit3, mm, x(mm), &
      nsup(mm), nion(mm), t, xee, xpx, cfrac
  enddo
  close(lun)
  return
9001 format(i12,',',a,',',i12,',',i12,',',i12,',',i12,',',i12,',', &
      i12,',',i12,',',i12,',',i12,',',i12,',',1pe24.16,',', &
      i12,',',i12,',',1pe24.16,',',1pe24.16,',',1pe24.16,',',1pe24.16)
end subroutine xap_pstate
"""


def before_msolvelucy_insertion() -> str:
    return """! xstar-atomic population/source closure probe.
! Insert immediately before call msolvelucy(...) in calc_hmc_element.f90.
      call xap_pstate('xstar_population_closure_probe.csv', &
     &     'before_msolvelucy', ml_element, jk, ipmat2, nsp, nionp, &
     &     nindbe, 0, 0, 0, t, xee, xpx, cfrac, x, nsup, nion)
"""


def after_msolvelucy_insertion() -> str:
    return """! xstar-atomic population/source closure probe.
! Insert immediately after call msolvelucy(...) in calc_hmc_element.f90.
      call xap_pstate('xstar_population_closure_probe.csv', &
     &     'after_msolvelucy', ml_element, jk, ipmat2, nsp, nionp, &
     &     nindbe, nit, nit2, nit3, t, xee, xpx, cfrac, x, nsup, nion)
"""


def patch_notes() -> str:
    return """# XSTAR population/source closure probe insertion notes

Patch a debug copy of `xstarlib/src/calc_hmc_element.f90`.

1. Add `xstar_atomic_population_closure_probe_helpers.f90` to
   `xstarlib/src/Makefile` in `HD_LIBRARY_SRC_f90`.

2. Insert `calc_hmc_element_before_msolvelucy_insertion.f90` immediately before
   the existing `call msolvelucy(ajise,cjise,cjise2, ...)` block.

3. Insert `calc_hmc_element_after_msolvelucy_insertion.f90` immediately after
   the full `call msolvelucy(...)` block and before `chisq(...)` / map-back to
   `xileve`.

4. Rebuild XSTAR, remove old `xstar_population_closure_probe.csv`, and rerun
   the same O VII case.

5. Validate with:

```bash
PYTHONPATH=src python examples/82_prepare_xstar_population_closure_probe.py \\
  --population-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv \\
  --out-dir xstar_population_closure_probe_o7_v03188_validated \\
  --print-summary
```

A ready probe has paired `before_msolvelucy` and `after_msolvelucy` captures
with matching `ipmat2` row counts.
"""


def summarize_population_closure_probe_csv(path: str | Path | None = None) -> Dict[str, Any]:
    rows, status, resolved = _read_csv(path)
    missing = [c for c in _REQUIRED if (not rows or c not in rows[0])]
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
    # Pairing is sequential: before and after are written around the same call.
    n_pairs = min(len(before_caps), len(after_caps))
    n_pair_ipmat2_mismatch = 0
    max_abs_population_sum_delta = 0.0
    for b, a in zip(before_caps, after_caps):
        if b.get("ipmat2") != a.get("ipmat2"):
            n_pair_ipmat2_mismatch += 1
        try:
            delta = abs(float(a.get("population_sum") or 0.0) - float(b.get("population_sum") or 0.0))
            max_abs_population_sum_delta = max(max_abs_population_sum_delta, delta)
        except Exception:
            pass
    ready = (
        status == "csv_loaded"
        and not missing
        and len(rows) > 0
        and len(before_caps) > 0
        and len(after_caps) > 0
        and n_pairs > 0
        and n_bad_ipmat2 == 0
        and n_pair_ipmat2_mismatch == 0
    )
    out_status = status
    if status == "csv_loaded" and missing:
        out_status = "csv_loaded_with_schema_warnings"
    elif status == "csv_loaded" and not ready:
        out_status = "csv_loaded_not_ready"
    elif ready:
        out_status = "csv_loaded_ready"
    return {
        "audit_version": "v0.3.188",
        "status": out_status,
        "population_probe_csv": resolved,
        "n_rows": len(rows),
        "n_captures": len(capture_rows),
        "n_before_captures": len(before_caps),
        "n_after_captures": len(after_caps),
        "n_before_after_pairs": n_pairs,
        "n_bad_ipmat2_captures": n_bad_ipmat2,
        "n_pair_ipmat2_mismatch": n_pair_ipmat2_mismatch,
        "max_abs_population_sum_delta": max_abs_population_sum_delta,
        "stage_counts": stage_counts,
        "missing_required_columns": missing,
        "probe_ready_for_population_closure_parity": ready,
        "correct_capture_site": "calc_hmc_element.f90 immediately before and after msolvelucy",
        "correct_fortran_product": "xstar_population_closure_probe.csv",
        "capture_rows": capture_rows,
    }


def write_population_closure_probe_products(
    out_dir: str | Path,
    *,
    summary: Mapping[str, Any] | None = None,
    prefix: str = "xstar_population_closure_probe",
) -> Dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    paths = {
        "helper_fortran": out / "xstar_atomic_population_closure_probe_helpers.f90",
        "before_msolvelucy_insertion": out / "calc_hmc_element_before_msolvelucy_insertion.f90",
        "after_msolvelucy_insertion": out / "calc_hmc_element_after_msolvelucy_insertion.f90",
        "patch_notes": out / "calc_hmc_element_population_closure_probe_notes.md",
        "schema_csv": out / f"{prefix}_schema.csv",
        "capture_summary_csv": out / f"{prefix}_capture_summary.csv",
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
    json_ready = {k: v for k, v in summary.items() if k != "capture_rows"}
    json_ready["capture_rows"] = list(summary.get("capture_rows", []) or [])
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
        f"- bad ipmat2 captures: `{summary.get('n_bad_ipmat2_captures')}`",
        f"- max population-sum delta: `{summary.get('max_abs_population_sum_delta')}`",
        "",
        "## Next use",
        "",
        "After validation, compare the XSTAR before/after population vectors to the Python local solve input/output, with level mapping from the preserved solver products.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
