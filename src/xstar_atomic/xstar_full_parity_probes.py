"""Readers and instrumentation helpers for full XSTAR local parity probes.

The products handled here are deliberately low-level.  They are intended to be
written by a local debug build of XSTAR at the exact Fortran call sites that
construct local rates and matrix rows:

* ``xstar_ucalc_record_probe.csv``: one row after every ``ucalc`` call in
  ``calc_hmc_ion.f90`` with ``ans1..ans6`` and destination indices.
* ``xstar_calc_hmc_ion_matrix_probe.csv``: one row for every ``ajisi/indbi``
  insertion made from those ``ucalc`` rates.

These probes are the bridge from audit-level rate comparisons to true
source-code-equivalent local matrix/population parity, including parent-ion and
superlevel closure.  This module does not change solver physics.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


_UCALC_REQUIRED = [
    "capture_index",
    "ml_data",
    "ltyp",
    "lrtyp",
    "jkk_ion",
    "idest1",
    "idest2",
    "idest3",
    "idest4",
    "ans1",
    "ans2",
    "ans3",
    "ans4",
    "ans5",
    "ans6",
]

_MATRIX_REQUIRED = [
    "capture_index",
    "ml_data",
    "ltyp",
    "lrtyp",
    "insertion_index",
    "insertion_kind",
    "indbi_1",
    "indbi_2",
    "ajisi_1",
    "ajisi_2",
]


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return int(round(f))
    except Exception:
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return f
    except Exception:
        return default


def _read_csv(path: str | Path | None) -> tuple[List[Dict[str, str]], str, str]:
    if path is None or not str(path).strip():
        return [], "csv_not_supplied", ""
    p = Path(path)
    if p.is_dir():
        candidates = sorted(p.rglob("*.csv"))
        preferred = []
        for pat in ["*ucalc*record*probe*.csv", "*calc_hmc_ion*matrix*probe*.csv", "*.csv"]:
            preferred = sorted(p.rglob(pat))
            if preferred:
                break
        if len(preferred) == 1:
            p = preferred[0]
        elif preferred:
            return [], "directory_multiple_csv_candidates", str(p)
    if not p.exists():
        return [], "csv_missing", str(p)
    try:
        with p.open("r", newline="", encoding="utf-8") as fh:
            rows = [dict(row) for row in csv.DictReader(fh)]
        return rows, "csv_loaded", str(p)
    except Exception as exc:  # pragma: no cover - defensive I/O detail
        return [], f"csv_read_error:{type(exc).__name__}", str(p)


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


def _missing_columns(rows: Sequence[Mapping[str, Any]], required: Sequence[str]) -> List[str]:
    if not rows:
        return list(required)
    have = set(rows[0].keys())
    return [c for c in required if c not in have]


def _schema_rows(kind: str) -> List[Dict[str, str]]:
    if kind == "ucalc":
        cols = [
            ("capture_index", "yes", "Sequential ucalc probe row id."),
            ("ml_data", "yes", "ATDB record pointer used by calc_hmc_ion."),
            ("ltyp", "yes", "XSTAR data type branch."),
            ("lrtyp", "yes", "XSTAR rate subtype."),
            ("jkk_ion", "yes", "Current XSTAR ion index."),
            ("idest1", "yes", "ucalc destination index 1."),
            ("idest2", "yes", "ucalc destination index 2, including parent/superlevel/continuum rows."),
            ("idest3", "yes", "ucalc auxiliary destination index 3."),
            ("idest4", "yes", "ucalc auxiliary destination index 4."),
            ("ans1", "yes", "ucalc returned forward/photo/excitation rate."),
            ("ans2", "yes", "ucalc returned reverse/recombination/de-excitation rate."),
            ("ans3", "yes", "ucalc returned heating/cooling channel."),
            ("ans4", "yes", "ucalc returned heating/cooling channel."),
            ("ans5", "yes", "ucalc returned auxiliary electron/photon channel."),
            ("ans6", "yes", "ucalc returned auxiliary electron/photon channel."),
            ("ptmp1", "recommended", "Incoming escape probability passed to ucalc."),
            ("ptmp2", "recommended", "Outgoing/covering escape probability passed to ucalc."),
            ("xpx", "recommended", "Ion-density scale used by XSTAR."),
            ("xnx", "recommended", "Electron density scalar used by XSTAR."),
            ("t_xstar_1e4K", "recommended", "XSTAR temperature variable t; Kelvin=t*1e4."),
            ("cfrac", "recommended", "Covering fraction."),
        ]
    elif kind == "matrix":
        cols = [
            ("capture_index", "yes", "Sequential matrix insertion probe row id."),
            ("ml_data", "yes", "ATDB record pointer associated with this matrix insertion."),
            ("ltyp", "yes", "XSTAR data type branch."),
            ("lrtyp", "yes", "XSTAR rate subtype."),
            ("insertion_index", "yes", "Fortran nindbi value."),
            ("insertion_kind", "yes", "forward_offdiag, reverse_offdiag, forward_diag_loss, reverse_diag_loss."),
            ("indbi_1", "yes", "Fortran indbi(1,nindbi) row index."),
            ("indbi_2", "yes", "Fortran indbi(2,nindbi) column index."),
            ("ajisi_1", "yes", "Fortran ajisi(1,nindbi) inserted coefficient."),
            ("ajisi_2", "yes", "Fortran ajisi(2,nindbi) inserted coefficient."),
            ("cjisi", "recommended", "Fortran cjisi(nindbi)."),
            ("cjisi2", "recommended", "Fortran cjisi2(nindbi)."),
            ("idest1", "recommended", "ucalc idest1 used to create llo/lup."),
            ("idest2", "recommended", "ucalc idest2 used to create llo/lup."),
            ("llo", "recommended", "Energy-ordered lower index after calc_hmc_ion switching."),
            ("lup", "recommended", "Energy-ordered upper index after calc_hmc_ion switching."),
            ("e1_eV", "recommended", "leveltemp energy for idest1."),
            ("e2_eV", "recommended", "leveltemp energy for idest2."),
        ]
    else:
        raise ValueError(f"unknown schema kind: {kind}")
    return [{"column": c, "required": r, "description": d} for c, r, d in cols]


def read_ucalc_record_probe_csv(path: str | Path | None) -> List[Dict[str, str]]:
    rows, status, _ = _read_csv(path)
    return rows if status == "csv_loaded" else []


def read_calc_hmc_ion_matrix_probe_csv(path: str | Path | None) -> List[Dict[str, str]]:
    rows, status, _ = _read_csv(path)
    return rows if status == "csv_loaded" else []


def summarize_full_parity_probe_csvs(
    *,
    ucalc_probe_csv: str | Path | None = None,
    matrix_probe_csv: str | Path | None = None,
) -> Dict[str, Any]:
    u_rows, u_status, u_path = _read_csv(ucalc_probe_csv)
    m_rows, m_status, m_path = _read_csv(matrix_probe_csv)
    u_missing = _missing_columns(u_rows, _UCALC_REQUIRED) if u_status == "csv_loaded" else _UCALC_REQUIRED
    m_missing = _missing_columns(m_rows, _MATRIX_REQUIRED) if m_status == "csv_loaded" else _MATRIX_REQUIRED
    u_keys = {(str(r.get("capture_index") or ""), str(r.get("ml_data") or "")) for r in u_rows}
    m_groups: Dict[Tuple[str, str], int] = {}
    for r in m_rows:
        key = (str(r.get("capture_index") or ""), str(r.get("ml_data") or ""))
        m_groups[key] = m_groups.get(key, 0) + 1
    m_keys = set(m_groups.keys())
    n_four = sum(1 for n in m_groups.values() if n == 4)
    n_not_four = sum(1 for n in m_groups.values() if n != 4)
    family_counts: Dict[str, int] = {}
    for r in u_rows:
        family = str(_as_int(r.get("ltyp"), None) or r.get("ltyp") or "unknown")
        family_counts[family] = family_counts.get(family, 0) + 1
    family_rows = [
        {"ltyp": k, "n_ucalc_rows": v}
        for k, v in sorted(family_counts.items(), key=lambda kv: (str(kv[0])))
    ]
    status = "probe_csvs_loaded"
    if u_status != "csv_loaded" and m_status != "csv_loaded":
        status = "probe_csvs_not_loaded"
    elif u_status != "csv_loaded" or m_status != "csv_loaded":
        status = "probe_csvs_partially_loaded"
    if (u_missing or m_missing) and status == "probe_csvs_loaded":
        status = "probe_csvs_loaded_with_schema_warnings"
    ready = (
        u_status == "csv_loaded"
        and m_status == "csv_loaded"
        and not u_missing
        and not m_missing
        and len(u_rows) > 0
        and len(m_rows) > 0
        and len(u_keys - m_keys) == 0
        and n_not_four == 0
    )
    return {
        "audit_version": "v0.3.179",
        "status": status,
        "ucalc_probe_status": u_status,
        "matrix_probe_status": m_status,
        "ucalc_probe_csv": u_path,
        "matrix_probe_csv": m_path,
        "n_ucalc_rows": len(u_rows),
        "n_matrix_rows": len(m_rows),
        "n_ucalc_record_keys": len(u_keys),
        "n_matrix_record_keys": len(m_keys),
        "n_ucalc_keys_without_matrix_rows": len(u_keys - m_keys),
        "n_matrix_keys_without_ucalc_rows": len(m_keys - u_keys),
        "n_matrix_record_keys_with_four_rows": n_four,
        "n_matrix_record_keys_not_four_rows": n_not_four,
        "ucalc_missing_required_columns": ";".join(u_missing),
        "matrix_missing_required_columns": ";".join(m_missing),
        "probe_ready_for_record_level_matrix_parity": ready,
        "family_rows": family_rows,
    }


def _fortran_helper_text() -> str:
    return r'''! xstar-atomic v0.3.179 full local parity probe helper.
! This helper is deliberately written as conservative free-form Fortran.
! HEASoft/XSTAR compiles .f90 files as free-form here; every continued
! line therefore has a trailing ampersand on the previous line.
! Short routine names avoid older compiler/name-length surprises.
!
! Public debug routines:
!   xap_ucalc  - write one ucalc ans1..ans6 record row
!   xap_mrow   - write one calc_hmc_ion matrix-insertion row

subroutine xap_ucalc(fname, ml_data, ltyp, lrtyp, jkk_ion, &
    idest1, idest2, idest3, idest4, ans1, ans2, ans3, ans4, &
    ans5, ans6, ptmp1, ptmp2, xpx, xnx, t, cfrac)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_data, ltyp, lrtyp, jkk_ion
  integer, intent(in) :: idest1, idest2, idest3, idest4
  real*8, intent(in) :: ans1, ans2, ans3, ans4, ans5, ans6
  real*8, intent(in) :: ptmp1, ptmp2, xpx, xnx, t, cfrac
  integer :: lun
  integer, save :: capture_index = 0
  logical, save :: wrote_header = .false.

  lun = 9376
  capture_index = capture_index + 1
  open(unit=lun, file=fname, status='unknown', position='append')
  if (.not. wrote_header) then
    write(lun,'(A,A,A,A)') &
      'capture_index,ml_data,ltyp,lrtyp,jkk_ion,', &
      'idest1,idest2,idest3,idest4,ans1,ans2,', &
      'ans3,ans4,ans5,ans6,ptmp1,ptmp2,xpx,', &
      'xnx,t_xstar_1e4K,cfrac'
    wrote_header = .true.
  endif
  write(lun,9001) capture_index, ml_data, ltyp, lrtyp, jkk_ion, &
      idest1, idest2, idest3, idest4, ans1, ans2, ans3, ans4, &
      ans5, ans6, ptmp1, ptmp2, xpx, xnx, t, cfrac
  close(lun)
  return
9001 format(i12,',',i12,',',i12,',',i12,',',i12,',', &
      i12,',',i12,',',i12,',',i12,',',1pe24.16,',', &
      1pe24.16,',',1pe24.16,',',1pe24.16,',', &
      1pe24.16,',',1pe24.16,',',1pe24.16,',', &
      1pe24.16,',',1pe24.16,',',1pe24.16,',', &
      1pe24.16,',',1pe24.16)
end subroutine xap_ucalc

subroutine xap_mrow(fname, ml_data, ltyp, lrtyp, nindbi, kind, &
    indbi1, indbi2, ajisi1, ajisi2, cjisi, cjisi2, idest1, &
    idest2, llo, lup, e1, e2)
  implicit none
  character(len=*), intent(in) :: fname, kind
  integer, intent(in) :: ml_data, ltyp, lrtyp, nindbi
  integer, intent(in) :: indbi1, indbi2, idest1, idest2, llo, lup
  real*8, intent(in) :: ajisi1, ajisi2, cjisi, cjisi2, e1, e2
  integer :: lun
  integer, save :: capture_index = 0
  logical, save :: wrote_header = .false.

  lun = 9377
  capture_index = capture_index + 1
  open(unit=lun, file=fname, status='unknown', position='append')
  if (.not. wrote_header) then
    write(lun,'(A,A,A)') &
      'capture_index,ml_data,ltyp,lrtyp,insertion_index,', &
      'insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2,', &
      'cjisi,cjisi2,idest1,idest2,llo,lup,e1_eV,e2_eV'
    wrote_header = .true.
  endif
  write(lun,9002) capture_index, ml_data, ltyp, lrtyp, nindbi, &
      kind, indbi1, indbi2, ajisi1, ajisi2, cjisi, cjisi2, &
      idest1, idest2, llo, lup, e1, e2
  close(lun)
  return
9002 format(i12,',',i12,',',i12,',',i12,',',i12,',', &
      A,',',i12,',',i12,',',1pe24.16,',',1pe24.16,',', &
      1pe24.16,',',1pe24.16,',',i12,',',i12,',', &
      i12,',',i12,',',1pe24.16,',',1pe24.16)
end subroutine xap_mrow

! Backward-compatible wrappers for v0.3.176/v0.3.177 insertion snippets.
! These symbols are needed when calc_hmc_ion.f90 still contains the long names.
subroutine xstar_atomic_probe_ucalc_record(fname, ml_data, ltyp, lrtyp, &
    jkk_ion, idest1, idest2, idest3, idest4, ans1, ans2, ans3, &
    ans4, ans5, ans6, ptmp1, ptmp2, xpx, xnx, t, cfrac)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: ml_data, ltyp, lrtyp, jkk_ion
  integer, intent(in) :: idest1, idest2, idest3, idest4
  real*8, intent(in) :: ans1, ans2, ans3, ans4, ans5, ans6
  real*8, intent(in) :: ptmp1, ptmp2, xpx, xnx, t, cfrac
  call xap_ucalc(fname, ml_data, ltyp, lrtyp, jkk_ion, idest1, &
      idest2, idest3, idest4, ans1, ans2, ans3, ans4, ans5, &
      ans6, ptmp1, ptmp2, xpx, xnx, t, cfrac)
  return
end subroutine xstar_atomic_probe_ucalc_record

subroutine xstar_atomic_probe_matrix_row(fname, ml_data, ltyp, lrtyp, &
    nindbi, kind, indbi1, indbi2, ajisi1, ajisi2, cjisi, cjisi2, &
    idest1, idest2, llo, lup, e1, e2)
  implicit none
  character(len=*), intent(in) :: fname, kind
  integer, intent(in) :: ml_data, ltyp, lrtyp, nindbi
  integer, intent(in) :: indbi1, indbi2, idest1, idest2, llo, lup
  real*8, intent(in) :: ajisi1, ajisi2, cjisi, cjisi2, e1, e2
  call xap_mrow(fname, ml_data, ltyp, lrtyp, nindbi, kind, indbi1, &
      indbi2, ajisi1, ajisi2, cjisi, cjisi2, idest1, idest2, &
      llo, lup, e1, e2)
  return
end subroutine xstar_atomic_probe_matrix_row
'''

def _after_ucalc_insertion_text() -> str:
    return """! xstar-atomic v0.3.179: insert after call ucalc(...).
! Free-form Fortran continuation for calc_hmc_ion.f90.
      call xap_ucalc('xstar_ucalc_record_probe.csv', ml_data, ltyp, &
     &     lrtyp, jkk_ion, idest1, idest2, idest3, idest4, ans1, ans2, &
     &     ans3, ans4, ans5, ans6, ptmp1, ptmp2, xpx, xee, t, cfrac)
"""

def _matrix_insertion_notes_text() -> str:
    return """# xstar-atomic v0.3.179 calc_hmc_ion matrix insertion probes

These calls are free-form Fortran snippets for `calc_hmc_ion.f90`.  Insert them
after each of the four `nindbi` insertion blocks following a successful `ucalc`
call. The exact location matters because values must be captured after `ajisi`,
`cjisi`, `cjisi2`, `indbi`, and `ltpsv` are assigned.

After the first off-diagonal block (`indbi(1)=lup`, `indbi(2)=llo`):

```fortran
      call xap_mrow('xstar_calc_hmc_ion_matrix_probe.csv', ml_data, ltyp, &
     &     lrtyp, nindbi, 'forward_offdiag', indbi(1,nindbi), &
     &     indbi(2,nindbi), ajisi(1,nindbi), ajisi(2,nindbi), &
     &     cjisi(nindbi), cjisi2(nindbi), idest1, idest2, &
     &     llo, lup, e1, e2)
```

After the second off-diagonal block (`indbi(1)=llo`, `indbi(2)=lup`):

```fortran
      call xap_mrow('xstar_calc_hmc_ion_matrix_probe.csv', ml_data, ltyp, &
     &     lrtyp, nindbi, 'reverse_offdiag', indbi(1,nindbi), &
     &     indbi(2,nindbi), ajisi(1,nindbi), ajisi(2,nindbi), &
     &     cjisi(nindbi), cjisi2(nindbi), idest1, idest2, &
     &     llo, lup, e1, e2)
```

After the third diagonal-loss block (`indbi(1)=llo`, `indbi(2)=llo`):

```fortran
      call xap_mrow('xstar_calc_hmc_ion_matrix_probe.csv', ml_data, ltyp, &
     &     lrtyp, nindbi, 'forward_diag_loss', indbi(1,nindbi), &
     &     indbi(2,nindbi), ajisi(1,nindbi), ajisi(2,nindbi), &
     &     cjisi(nindbi), cjisi2(nindbi), idest1, idest2, &
     &     llo, lup, e1, e2)
```

After the fourth diagonal-loss block (`indbi(1)=lup`, `indbi(2)=lup`):

```fortran
      call xap_mrow('xstar_calc_hmc_ion_matrix_probe.csv', ml_data, ltyp, &
     &     lrtyp, nindbi, 'reverse_diag_loss', indbi(1,nindbi), &
     &     indbi(2,nindbi), ajisi(1,nindbi), ajisi(2,nindbi), &
     &     cjisi(nindbi), cjisi2(nindbi), idest1, idest2, &
     &     llo, lup, e1, e2)
```

Remove old CSVs before each run:

```bash
rm -f xstar_ucalc_record_probe.csv xstar_calc_hmc_ion_matrix_probe.csv
```
"""

def prepare_full_parity_probe_products(
    *,
    out_dir: str | Path,
    ucalc_probe_csv: str | Path | None = None,
    matrix_probe_csv: str | Path | None = None,
    xstar_source_root: str | Path | None = None,
) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = summarize_full_parity_probe_csvs(
        ucalc_probe_csv=ucalc_probe_csv,
        matrix_probe_csv=matrix_probe_csv,
    )
    summary["xstar_source_root"] = str(xstar_source_root or "")
    summary["correct_capture_site"] = "calc_hmc_ion.f90 immediately after ucalc and after each ajisi/indbi insertion"
    summary["correct_fortran_products"] = "xstar_ucalc_record_probe.csv and xstar_calc_hmc_ion_matrix_probe.csv"
    paths = {
        "ucalc_schema_csv": out / "xstar_ucalc_record_probe_schema.csv",
        "matrix_schema_csv": out / "xstar_calc_hmc_ion_matrix_probe_schema.csv",
        "helper_fortran": out / "xstar_atomic_full_parity_probe_helpers.f90",
        "after_ucalc_insertion": out / "calc_hmc_ion_after_ucalc_insertion.f90",
        "matrix_insertion_notes": out / "calc_hmc_ion_matrix_insertion_probe_notes.md",
        "family_summary_csv": out / "xstar_full_parity_probe_family_summary.csv",
        "json": out / "xstar_full_parity_probe.json",
        "markdown": out / "xstar_full_parity_probe.md",
    }
    _write_csv(paths["ucalc_schema_csv"], _schema_rows("ucalc"))
    _write_csv(paths["matrix_schema_csv"], _schema_rows("matrix"))
    _write_csv(paths["family_summary_csv"], summary.get("family_rows", []))
    paths["helper_fortran"].write_text(_fortran_helper_text(), encoding="utf-8")
    paths["after_ucalc_insertion"].write_text(_after_ucalc_insertion_text(), encoding="utf-8")
    paths["matrix_insertion_notes"].write_text(_matrix_insertion_notes_text(), encoding="utf-8")
    public_summary = {k: v for k, v in summary.items() if k != "family_rows"}
    payload = {"summary": public_summary, "family_rows": summary.get("family_rows", []), "paths": {k: str(v) for k, v in paths.items()}}
    paths["json"].write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# XSTAR full local parity probe preparation",
        "",
        f"- audit_version: `{summary.get('audit_version')}`",
        f"- status: `{summary.get('status')}`",
        f"- ucalc rows: `{summary.get('n_ucalc_rows')}`",
        f"- matrix rows: `{summary.get('n_matrix_rows')}`",
        f"- ready for record-level matrix parity: `{summary.get('probe_ready_for_record_level_matrix_parity')}`",
        "",
        "## Capture site",
        "",
        str(summary.get("correct_capture_site")),
        "",
        "## Required products",
        "",
        "- `xstar_ucalc_record_probe.csv`",
        "- `xstar_calc_hmc_ion_matrix_probe.csv`",
        "",
        "The helper and insertion templates in this directory are debug instrumentation scaffolds; keep them out of production XSTAR builds.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"summary": public_summary, "paths": {k: str(v) for k, v in paths.items()}}
