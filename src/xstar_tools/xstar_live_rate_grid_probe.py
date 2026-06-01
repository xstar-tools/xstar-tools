"""Utilities for the XSTAR live rate-grid radiation-field probe.

The v0.3.169 provenance audit established that the type-53 ``phint53``
photoionization rates use the reduced live rate grid produced by
``xstarcalc.f90``/``bremsmap``:

``epim(:), bremsam(:), bremsint(:)``

rather than any continuum column written later to ``xo01_detal4.fits``.  This
module defines a small, explicit probe product that can be written by an
instrumented XSTAR build and read by the Python audit layer.  It does not alter
solver physics; it only standardizes the next live-state capture step.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple


LIVE_RATE_GRID_REQUIRED_COLUMNS = [
    "zone_index",
    "pass_index",
    "ldir",
    "grid_index",
    "ncn2m",
    "epim_eV",
    "bremsam",
    "bremsint",
]

LIVE_RATE_GRID_RECOMMENDED_COLUMNS = [
    "radius_cm",
    "r19",
    "fpr2",
    "temperature_K",
    "electron_density_cm^-3",
    "xpx",
    "cfrac",
    "source_file",
    "source_line",
]

LIVE_RATE_GRID_OPTIONAL_PROVENANCE_COLUMNS = [
    "epi_eV_highres",
    "bremsa_highres",
    "zremsz_highres",
    "dpthc_fwd_highres",
    "dpthc_bck_highres",
]


@dataclass(frozen=True)
class LiveRateGridState:
    """One captured live rate-grid state from instrumented XSTAR.

    Rows are grouped by ``zone_index``, ``pass_index``, and ``ldir``.  The core
    arrays are the exact reduced-grid arrays supplied to the level-population
    rate machinery in XSTAR.
    """

    zone_index: int
    pass_index: int
    ldir: int
    ncn2m: int
    epim_eV: Tuple[float, ...]
    bremsam: Tuple[float, ...]
    bremsint: Tuple[float, ...]
    metadata: Mapping[str, Any]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(str(key))
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        out = float(str(value).strip())
    except Exception:
        return default
    if not math.isfinite(out):
        return default
    return out


def live_rate_grid_probe_schema_rows() -> List[Dict[str, Any]]:
    """Return the recommended CSV schema for an XSTAR live-rate-grid dump."""

    rows: List[Dict[str, Any]] = []
    descriptions = {
        "zone_index": "1-based XSTAR zone/depth index; match this to xo01_detail/xo01_detal* products.",
        "pass_index": "Radial/pass counter or local debug pass id; use 1 if unavailable.",
        "ldir": "Transfer direction/state identifier; preserve XSTAR's local ldir value when available.",
        "grid_index": "1-based rate-grid bin index for epim/bremsam/bremsint.",
        "ncn2m": "Reduced rate-grid length used by calc_hmc_all/calc_hmc_ion.",
        "epim_eV": "Reduced rate-grid energy in eV after bremsmap.",
        "bremsam": "Live reduced-grid radiation field passed into calc_hmc_all -> calc_hmc_ion -> ucalc/phint53.",
        "bremsint": "Live reduced-grid upper-tail integral passed alongside bremsam.",
        "radius_cm": "Local radius r in cm, for checking fpr2=12.56*(r/1e19)^2.",
        "r19": "r/1e19 used in XSTAR geometric dilution formulas.",
        "fpr2": "12.56*r19*r19 geometric factor; useful provenance check.",
        "temperature_K": "Local electron/gas temperature at the same call-site timing.",
        "electron_density_cm^-3": "Local electron density at the same call-site timing.",
        "xpx": "Local XSTAR ion/abundance density scaling scalar when available.",
        "cfrac": "Covering fraction at the same call site.",
        "source_file": "Fortran source file containing the probe insertion point.",
        "source_line": "Approximate source line number or tag for the probe insertion point.",
        "epi_eV_highres": "Optional high-resolution trnfrc epi(:) value for provenance only.",
        "bremsa_highres": "Optional high-resolution trnfrc bremsa(:) value before bremsmap.",
        "zremsz_highres": "Optional high-resolution live zremsz(:) value before attenuation.",
        "dpthc_fwd_highres": "Optional high-resolution forward continuum depth dpthc(1,:).",
        "dpthc_bck_highres": "Optional high-resolution backward continuum depth dpthc(2,:).",
    }
    for name in LIVE_RATE_GRID_REQUIRED_COLUMNS:
        rows.append({"column": name, "required": "yes", "group": "core_rate_grid", "description": descriptions[name]})
    for name in LIVE_RATE_GRID_RECOMMENDED_COLUMNS:
        rows.append({"column": name, "required": "recommended", "group": "call_site_metadata", "description": descriptions[name]})
    for name in LIVE_RATE_GRID_OPTIONAL_PROVENANCE_COLUMNS:
        rows.append({"column": name, "required": "optional", "group": "high_resolution_provenance", "description": descriptions[name]})
    return rows


def live_rate_grid_probe_fortran_template() -> str:
    """Return a guarded Fortran probe template for the xstarcalc/bremsmap site.

    The template is intentionally conservative and text-based.  It is a guide
    for local XSTAR instrumentation, not an automatic patch against a specific
    XSTAR release.
    """

    cols = LIVE_RATE_GRID_REQUIRED_COLUMNS + LIVE_RATE_GRID_RECOMMENDED_COLUMNS
    header = ",".join(cols)
    return f"""! xstar-atomic v0.3.172 live rate-grid probe template
! Insert immediately after the xstarcalc.f90 call to bremsmap(...) and before
! calc_hmc_all/calc_hmc_ion receive epim,ncn2m,bremsam,bremsint.
! Guard this block with your local debug flag and selected zone/ion conditions.
!
! Suggested CSV header:
! {header}
!
! Pseudocode only: adapt unit number, variable names, and debug guards to your
! local XSTAR tree.
!
! if (debug_live_rate_grid .and. selected_zone) then
!   open(unit=9876, file='xstar_live_rate_grid_probe.csv', status='unknown', position='append')
!   ! Write header once outside this block or guard with a first-write flag.
!   do jk = 1, ncn2m
!      write(9876,'(I0,",",I0,",",I0,",",I0,",",I0,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",ES24.16,",",A,",",I0)') &
!           nloopctl, 1, ldir, jk, ncn2m, epim(jk), bremsam(jk), bremsint(jk), &
!           r, r/1.e19, 12.56*(r/1.e19)*(r/1.e19), t, xee, xpx, cfrac, &
!           'xstarcalc.f90:after_bremsmap', 0
!   enddo
!   close(9876)
! endif
"""


def _split_probe_rows_into_blocks(rows: Sequence[Dict[str, str]]) -> List[List[Dict[str, str]]]:
    """Split rows from one nominal probe key into sequential capture blocks.

    The first v0.3.171 Fortran helper can use placeholder zone/pass metadata
    (for example ``zone_index=-1, pass_index=1, ldir=0``) for every call to
    ``bremsmap``.  In that common case, grouping only by
    ``(zone_index, pass_index, ldir)`` incorrectly concatenates multiple
    reduced grids into one non-monotonic state.  XSTAR writes rows in call-site
    order, and each capture block resets ``grid_index`` to 1, so use that reset
    as the primary block delimiter.  Also start a new block if a previous block
    has already reached its row-local ``ncn2m`` value.
    """

    blocks: List[List[Dict[str, str]]] = []
    current: List[Dict[str, str]] = []
    last_grid: int | None = None
    expected_n: int | None = None
    for row in rows:
        gidx = _as_int(row.get("grid_index"), None)
        ncn = _as_int(row.get("ncn2m"), None)
        start_new = False
        if current:
            if gidx is not None and last_grid is not None and gidx <= last_grid:
                start_new = True
            elif expected_n is not None and len(current) >= expected_n:
                start_new = True
        if start_new:
            blocks.append(current)
            current = []
            last_grid = None
            expected_n = None
        current.append(row)
        last_grid = gidx
        if expected_n is None and ncn is not None:
            expected_n = ncn
    if current:
        blocks.append(current)
    return blocks


def read_live_rate_grid_probe_csv(path: str | Path) -> List[LiveRateGridState]:
    """Read a long-form live-rate-grid probe CSV into grouped states.

    Rows are first partitioned by the nominal probe metadata
    ``(zone_index, pass_index, ldir)``.  Within each nominal group, sequential
    capture blocks are split whenever ``grid_index`` resets.  This supports the
    lightweight v0.3.171 probe helper, where the true radial-zone counter may
    not be in scope and all captures may therefore share ``zone_index=-1``.
    """

    rows = _read_csv_rows(path)
    groups: MutableMapping[Tuple[int, int, int], List[Dict[str, str]]] = {}
    for row in rows:
        zone = _as_int(row.get("zone_index"))
        pidx = _as_int(row.get("pass_index"), 1)
        ldir = _as_int(row.get("ldir"), 0)
        if zone is None or pidx is None or ldir is None:
            continue
        groups.setdefault((int(zone), int(pidx), int(ldir)), []).append(row)

    states: List[LiveRateGridState] = []
    capture_index = 0
    for (zone, pidx, ldir), group_rows in sorted(groups.items()):
        # Preserve file order inside each nominal group; do not sort before
        # splitting, because sorting would destroy the grid-index reset signal.
        for block_rows in _split_probe_rows_into_blocks(group_rows):
            capture_index += 1
            block_rows = sorted(block_rows, key=lambda r: _as_int(r.get("grid_index"), 0) or 0)
            epim: List[float] = []
            brem: List[float] = []
            bint: List[float] = []
            for row in block_rows:
                e = _as_float(row.get("epim_eV"))
                b = _as_float(row.get("bremsam"))
                bi = _as_float(row.get("bremsint"))
                if e is None or b is None or bi is None:
                    continue
                epim.append(float(e)); brem.append(float(b)); bint.append(float(bi))
            ncn2m = _as_int(block_rows[0].get("ncn2m"), len(epim)) or len(epim)
            metadata: Dict[str, Any] = {"capture_index": capture_index}
            for key in LIVE_RATE_GRID_RECOMMENDED_COLUMNS:
                if key in block_rows[0] and block_rows[0].get(key) != "":
                    val = _as_float(block_rows[0].get(key))
                    metadata[key] = val if val is not None else block_rows[0].get(key)
            states.append(LiveRateGridState(zone, pidx, ldir, int(ncn2m), tuple(epim), tuple(brem), tuple(bint), metadata))
    return states

def summarize_live_rate_grid_probe_csv(path: str | Path | None) -> Dict[str, Any]:
    """Summarize an optional live-rate-grid probe CSV for readiness checks."""

    if path is None:
        return {
            "probe_status": "probe_csv_not_supplied",
            "n_probe_states": 0,
            "n_probe_grid_points_total": 0,
            "probe_ready_for_type53_phint53_live_bremsam_audit": False,
        }
    p = Path(path)
    if not p.exists():
        return {
            "probe_status": "probe_csv_missing",
            "probe_csv": str(p),
            "n_probe_states": 0,
            "n_probe_grid_points_total": 0,
            "probe_ready_for_type53_phint53_live_bremsam_audit": False,
        }
    states = read_live_rate_grid_probe_csv(p)
    n_points = sum(len(s.epim_eV) for s in states)
    non_monotonic = 0
    non_positive_bremsam = 0
    ncn2m_mismatch = 0
    e_min: float | None = None
    e_max: float | None = None
    for st in states:
        if len(st.epim_eV) != st.ncn2m:
            ncn2m_mismatch += 1
        if any(st.epim_eV[i + 1] <= st.epim_eV[i] for i in range(len(st.epim_eV) - 1)):
            non_monotonic += 1
        if any(x < 0.0 for x in st.bremsam):
            non_positive_bremsam += 1
        if st.epim_eV:
            e_min = min(st.epim_eV[0], e_min) if e_min is not None else st.epim_eV[0]
            e_max = max(st.epim_eV[-1], e_max) if e_max is not None else st.epim_eV[-1]
    status = "probe_csv_loaded" if states else "probe_csv_empty_or_unreadable"
    if states and (non_monotonic or non_positive_bremsam or ncn2m_mismatch):
        status = "probe_csv_loaded_with_warnings"
    n_placeholder_zone_states = sum(1 for st in states if st.zone_index < 0)
    return {
        "probe_status": status,
        "probe_csv": str(p),
        "n_probe_states": len(states),
        "n_probe_grid_points_total": n_points,
        "probe_energy_min_eV": e_min,
        "probe_energy_max_eV": e_max,
        "n_probe_states_non_monotonic_energy": non_monotonic,
        "n_probe_states_with_negative_bremsam": non_positive_bremsam,
        "n_probe_states_ncn2m_mismatch": ncn2m_mismatch,
        "n_probe_states_placeholder_zone_index": n_placeholder_zone_states,
        "probe_block_split_method": "nominal_key_then_grid_index_reset_v03172",
        "probe_ready_for_type53_phint53_live_bremsam_audit": bool(states and not non_monotonic and not ncn2m_mismatch),
    }


def prepare_live_rate_grid_probe_products(
    out_dir: str | Path,
    *,
    probe_csv: str | Path | None = None,
    prefix: str = "xstar_live_rate_grid_probe",
) -> Dict[str, str]:
    """Write schema, Fortran probe template, readiness summary, and Markdown."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    schema_rows = live_rate_grid_probe_schema_rows()
    summary = {
        "audit_version": "v0.3.172",
        "purpose": "standardize the live epim/bremsam/bremsint capture needed for type-53 phint53 parity",
        "correct_capture_site": "xstarcalc.f90 immediately after bremsmap and before calc_hmc_all/calc_hmc_ion",
        "correct_live_rate_field": "epim(:), bremsam(:), bremsint(:)",
        "not_sufficient": "xo01_detal4 zrems(1:5) variants are output/detail products and do not contain live bremsam(:)",
        "performance_note": "Python remains the audit/orchestration layer; production RT/rate kernels should move to the planned C++ backend after parity is established.",
        **summarize_live_rate_grid_probe_csv(probe_csv),
    }

    schema_path = out / f"{prefix}_schema.csv"
    _write_csv(schema_path, schema_rows, ["column", "required", "group", "description"])
    fortran_path = out / f"{prefix}_fortran_template.f90"
    fortran_path.write_text(live_rate_grid_probe_fortran_template(), encoding="utf-8")
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "schema": schema_rows}, indent=2, default=str), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR live rate-grid probe preparation",
        "",
        f"audit_version: `{summary['audit_version']}`",
        f"purpose: {summary['purpose']}",
        "",
        "## Correct capture site",
        "",
        f"- `{summary['correct_capture_site']}`",
        f"- live field: `{summary['correct_live_rate_field']}`",
        f"- not sufficient: `{summary['not_sufficient']}`",
        "",
        "## Probe CSV readiness",
        "",
        f"probe_status: `{summary.get('probe_status')}`",
        f"probe_csv: `{summary.get('probe_csv', '')}`",
        f"n_probe_states: `{summary.get('n_probe_states')}`",
        f"n_probe_grid_points_total: `{summary.get('n_probe_grid_points_total')}`",
        f"probe_ready_for_type53_phint53_live_bremsam_audit: `{summary.get('probe_ready_for_type53_phint53_live_bremsam_audit')}`",
        "",
        "## Required columns",
        "",
    ]
    for row in schema_rows:
        if row.get("required") == "yes":
            lines.append(f"- `{row['column']}` — {row['description']}")
    lines.extend([
        "",
        "## Next audit after instrumentation",
        "",
        "After XSTAR writes this probe CSV, the next Python audit should recompute type-53 `phint53` photoionization `ans1` using `epim(:)` and `bremsam(:)` from this probe, then compare directly to the matrix photoionization rows.",
        "",
        "## Performance note",
        "",
        str(summary["performance_note"]),
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "schema_csv": str(schema_path),
        "fortran_template": str(fortran_path),
        "json": str(json_path),
        "markdown": str(md_path),
    }

# ---------------------------------------------------------------------------
# v0.3.172 local XSTAR instrumentation helper
# ---------------------------------------------------------------------------

def live_rate_grid_probe_fortran_helper() -> str:
    """Return a standalone Fortran helper for writing the live rate-grid CSV.

    This helper is intentionally external to XSTAR's physics routines.  A local
    XSTAR checkout can compile this small file and insert a single guarded call
    immediately after ``bremsmap`` in ``xstarcalc.f90``.  The helper writes the
    CSV header once and appends one row per rate-grid point.  It avoids very
    long Fortran source lines by using non-advancing writes.
    """

    return """! xstar-atomic v0.3.172 live rate-grid probe helper
! Compile this file into a local/debug XSTAR build only.  It writes the live
! rate-grid arrays epim(:), bremsam(:), and bremsint(:) immediately after
! xstarcalc.f90 calls bremsmap and before calc_hmc_all/calc_hmc_ion.
!
      subroutine xstar_tools_write_live_rate_grid_probe(filename,          &
     &     zone_index,pass_index,ldir,ncn2m,epim,bremsam,bremsint,          &
     &     radius_cm,temperature_k,electron_density,xpx,cfrac)
      implicit none
      character(len=*), intent(in) :: filename
      integer, intent(in) :: zone_index,pass_index,ldir,ncn2m
      real(8), intent(in) :: epim(*),bremsam(*),bremsint(*)
      real(8), intent(in) :: radius_cm,temperature_k,electron_density
      real(8), intent(in) :: xpx,cfrac
      integer :: jk
      logical :: file_exists
      real(8) :: r19,fpr2
!
      inquire(file=filename, exist=file_exists)
      open(unit=9876,file=filename,status='unknown',position='append',      &
     &     action='write')
      if (.not. file_exists) then
        write(9876,'(A)',advance='no') 'zone_index,pass_index,ldir,'
        write(9876,'(A)',advance='no') 'grid_index,ncn2m,epim_eV,'
        write(9876,'(A)',advance='no') 'bremsam,bremsint,radius_cm,'
        write(9876,'(A)',advance='no') 'r19,fpr2,temperature_K,'
        write(9876,'(A)',advance='no') 'electron_density_cm^-3,xpx,'
        write(9876,'(A)') 'cfrac,source_file,source_line'
      endif
      r19=radius_cm/1.d19
      fpr2=12.56d0*r19*r19
      do jk=1,ncn2m
        write(9876,'(I0,A)',advance='no') zone_index,','
        write(9876,'(I0,A)',advance='no') pass_index,','
        write(9876,'(I0,A)',advance='no') ldir,','
        write(9876,'(I0,A)',advance='no') jk,','
        write(9876,'(I0,A)',advance='no') ncn2m,','
        write(9876,'(ES24.16,A)',advance='no') epim(jk),','
        write(9876,'(ES24.16,A)',advance='no') bremsam(jk),','
        write(9876,'(ES24.16,A)',advance='no') bremsint(jk),','
        write(9876,'(ES24.16,A)',advance='no') radius_cm,','
        write(9876,'(ES24.16,A)',advance='no') r19,','
        write(9876,'(ES24.16,A)',advance='no') fpr2,','
        write(9876,'(ES24.16,A)',advance='no') temperature_k,','
        write(9876,'(ES24.16,A)',advance='no') electron_density,','
        write(9876,'(ES24.16,A)',advance='no') xpx,','
        write(9876,'(ES24.16,A)',advance='no') cfrac,','
        write(9876,'(A,A,I0)') 'xstarcalc.f90:after_bremsmap',',',0
      enddo
      close(9876)
      return
      end
"""


def live_rate_grid_probe_xstarcalc_insertion_block(
    *,
    filename: str = "xstar_live_rate_grid_probe.csv",
    zone_expression: str = "-1",
    pass_expression: str = "1",
    ldir_expression: str = "0",
    only_when_lpri2_negative: bool = False,
) -> str:
    """Return the call block to insert after ``call bremsmap``.

    ``xstarcalc.f90`` often does not have the radial zone counter in scope, so
    the default ``zone_expression`` is ``-1``.  Users who can pass or expose the
    XSTAR shell index should replace it with the real zone variable.  The rate
    comparison only needs the final captured state if the probe is used for a
    single run/zone, but an explicit zone id is better for multi-zone workflows.
    """

    call = (
        "      call xstar_tools_write_live_rate_grid_probe(                         &\n"
        f"     &     '{filename}',{zone_expression},{pass_expression},{ldir_expression},ncn2m,epim,bremsam,bremsint, &\n"
        "     &     r,t*1.d4,xee*xpx,xpx,cfrac)"
    )
    if only_when_lpri2_negative:
        return (
            "! xstar-atomic live-rate-grid probe: insert immediately after bremsmap.\n"
            "! This optional guard lets you activate the probe by setting lpri2<0 locally.\n"
            "      if (lpri2.lt.0) then\n" + call + "\n      endif\n"
        )
    return "! xstar-atomic live-rate-grid probe: insert immediately after bremsmap.\n" + call + "\n"


def locate_xstarcalc_bremsmap_site(xstar_source_root: str | Path) -> Dict[str, Any]:
    """Locate the first ``call bremsmap`` site in an XSTAR source tree."""

    root = Path(xstar_source_root)
    candidates = list(root.rglob("xstarcalc.f90"))
    if not candidates and root.name.lower() == "xstarcalc.f90":
        candidates = [root]
    if not candidates:
        return {"status": "xstarcalc_not_found", "xstar_source_root": str(root)}
    path = candidates[0]
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    idx = None
    for i, line in enumerate(lines):
        if "call bremsmap" in line.lower():
            idx = i
            break
    if idx is None:
        return {"status": "bremsmap_call_not_found", "xstarcalc_path": str(path)}
    lo = max(0, idx - 6)
    hi = min(len(lines), idx + 8)
    return {
        "status": "bremsmap_call_found",
        "xstarcalc_path": str(path),
        "bremsmap_line_number": idx + 1,
        "context": "\n".join(f"{j+1}: {lines[j]}" for j in range(lo, hi)),
    }


def prepare_live_rate_grid_probe_patch_products(
    out_dir: str | Path,
    *,
    xstar_source_root: str | Path | None = None,
    filename: str = "xstar_live_rate_grid_probe.csv",
    zone_expression: str = "-1",
    pass_expression: str = "1",
    ldir_expression: str = "0",
    guarded: bool = False,
    prefix: str = "xstar_live_rate_grid_probe_patch",
) -> Dict[str, str]:
    """Write helper/insertion files for local XSTAR instrumentation."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    helper = out / "xstar_tools_live_rate_grid_probe.f90"
    helper.write_text(live_rate_grid_probe_fortran_helper(), encoding="utf-8")
    insertion = out / "xstarcalc_after_bremsmap_insertion.f90"
    insertion.write_text(
        live_rate_grid_probe_xstarcalc_insertion_block(
            filename=filename,
            zone_expression=zone_expression,
            pass_expression=pass_expression,
            ldir_expression=ldir_expression,
            only_when_lpri2_negative=guarded,
        ),
        encoding="utf-8",
    )
    site = locate_xstarcalc_bremsmap_site(xstar_source_root) if xstar_source_root else {"status": "xstar_source_root_not_supplied"}
    summary = {
        "audit_version": "v0.3.172",
        "purpose": "prepare a compileable local XSTAR live-rate-grid probe helper and xstarcalc insertion block",
        "probe_output_csv": filename,
        "zone_expression": zone_expression,
        "pass_expression": pass_expression,
        "ldir_expression": ldir_expression,
        "guarded_by_lpri2_negative": guarded,
        "capture_site_status": site.get("status"),
        "xstarcalc_path": site.get("xstarcalc_path"),
        "bremsmap_line_number": site.get("bremsmap_line_number"),
        "next": "compile the helper into a local/debug XSTAR build, insert the call block immediately after bremsmap, rerun O VII, then validate the produced probe CSV with example 72",
    }
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps({"summary": summary, "site": site}, indent=2), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    md = [
        "# XSTAR live rate-grid probe patch preparation",
        "",
        f"audit_version: `{summary['audit_version']}`",
        f"capture_site_status: `{summary.get('capture_site_status')}`",
        f"xstarcalc_path: `{summary.get('xstarcalc_path') or ''}`",
        f"bremsmap_line_number: `{summary.get('bremsmap_line_number') or ''}`",
        "",
        "## Files written",
        "",
        f"- `{helper.name}`: standalone helper subroutine to add to the local/debug XSTAR build.",
        f"- `{insertion.name}`: call block to insert immediately after `call bremsmap(...)`.",
        "",
        "## Build notes",
        "",
        "1. Copy `xstar_tools_live_rate_grid_probe.f90` into the XSTAR source tree, for example `xstarlib/src/`.",
        "2. Add it to the local XSTAR build object list or compile it with the other library sources.",
        "3. Insert the call block from `xstarcalc_after_bremsmap_insertion.f90` immediately after `call bremsmap(...)` in `xstarcalc.f90`.",
        "4. Rerun the same O VII XSTAR case. It should create `xstar_live_rate_grid_probe.csv` in the run directory/current working directory.",
        "5. Validate with `examples/72_prepare_xstar_live_rate_grid_probe.py --probe-csv xstar_live_rate_grid_probe.csv`.",
        "",
        "## Important notes",
        "",
        "- This is a local instrumentation probe, not a production XSTAR patch.",
        "- The default `zone_expression=-1` is a placeholder because `xstarcalc.f90` may not have the radial shell index in scope. Replace it with the real zone variable if available.",
        "- The probe writes `temperature_K=t*1.d4` and `electron_density_cm^-3=xee*xpx`, matching XSTAR's documented units in `xstarcalc.f90`.",
        "",
        "## Located bremsmap context",
        "",
        "```fortran",
        str(site.get("context") or ""),
        "```",
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    return {"helper_fortran": str(helper), "insertion_block": str(insertion), "json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "LIVE_RATE_GRID_REQUIRED_COLUMNS",
    "LIVE_RATE_GRID_RECOMMENDED_COLUMNS",
    "LIVE_RATE_GRID_OPTIONAL_PROVENANCE_COLUMNS",
    "LiveRateGridState",
    "live_rate_grid_probe_schema_rows",
    "live_rate_grid_probe_fortran_template",
    "read_live_rate_grid_probe_csv",
    "summarize_live_rate_grid_probe_csv",
    "prepare_live_rate_grid_probe_products",
    "live_rate_grid_probe_fortran_helper",
    "live_rate_grid_probe_xstarcalc_insertion_block",
    "locate_xstarcalc_bremsmap_site",
    "prepare_live_rate_grid_probe_patch_products",
]
