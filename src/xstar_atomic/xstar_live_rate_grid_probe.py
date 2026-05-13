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
    return f"""! xstar-atomic v0.3.170 live rate-grid probe template
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


def read_live_rate_grid_probe_csv(path: str | Path) -> List[LiveRateGridState]:
    """Read a long-form live-rate-grid probe CSV into grouped states."""

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
    for (zone, pidx, ldir), group_rows in sorted(groups.items()):
        group_rows = sorted(group_rows, key=lambda r: _as_int(r.get("grid_index"), 0) or 0)
        epim: List[float] = []
        brem: List[float] = []
        bint: List[float] = []
        for row in group_rows:
            e = _as_float(row.get("epim_eV"))
            b = _as_float(row.get("bremsam"))
            bi = _as_float(row.get("bremsint"))
            if e is None or b is None or bi is None:
                continue
            epim.append(float(e)); brem.append(float(b)); bint.append(float(bi))
        ncn2m = _as_int(group_rows[0].get("ncn2m"), len(epim)) or len(epim)
        metadata: Dict[str, Any] = {}
        for key in LIVE_RATE_GRID_RECOMMENDED_COLUMNS:
            if key in group_rows[0] and group_rows[0].get(key) != "":
                val = _as_float(group_rows[0].get(key))
                metadata[key] = val if val is not None else group_rows[0].get(key)
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
        "audit_version": "v0.3.170",
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
]
