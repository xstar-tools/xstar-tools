# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: bremsmap.f90 / nbinc.f90 / huntf.f90
#   Role: Map the live high-resolution radiation field to the reduced grid with source search/range semantics.
#   Relation: Source-faithful numerical translation including one-based bin boundaries and caller-owned tails.
#   Concordance: ARCH-001; EMISAB-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Source-faithful translation of XSTAR ``bremsmap.f90``.

The source path is::

    xstarcalc.f90 -> bremsmap.f90 -> nbinc.f90 -> huntf.f90

The translation preserves two non-obvious source semantics:

* ``nbinc`` searches only ``ncn2-max(2,ncn2/50)`` high-resolution bins.
* ``bremsmap`` overwrites only ``bremsint(1:ncn2m)`` in descending order and
  uses the caller-owned ``bremsint(ncn2m+1)`` as its upper-tail boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .driver import XSTARPythonDriver, XSTARSourceRoutine
from .state import XSTARPythonState


XSTAR_BREMSMAP_ERG_PER_EV = float(np.float32(1.602197e-12))
XSTAR_BREMSMAP_EPIM_FLOOR = float(np.float32(1.0e-39))
XSTAR_HUNTF_ZERO_FLOOR = float(np.float32(1.0e-34))


class BremsMapPortError(RuntimeError):
    """Raised when the translated ``bremsmap`` source contract is violated."""


@dataclass(frozen=True)
class BremsMapContext:
    epi_eV: np.ndarray
    bremsa: np.ndarray
    epim_eV: np.ndarray
    bremsam_before: np.ndarray
    bremsint_before: np.ndarray
    ncn2: int
    ncn2m: int

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Validate BremsMapContext invariants before the value is consumed downstream.
    # Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
    # XSTAR-FUNCTION-COMMENT-END
    def validate(self) -> None:
        n = int(self.ncn2)
        nm = int(self.ncn2m)
        if n < 3:
            raise BremsMapPortError("bremsmap requires ncn2 >= 3")
        if nm < 1:
            raise BremsMapPortError("bremsmap requires ncn2m >= 1")
        epi = np.asarray(self.epi_eV, dtype=float).reshape(-1)
        brem = np.asarray(self.bremsa, dtype=float).reshape(-1)
        epim = np.asarray(self.epim_eV, dtype=float).reshape(-1)
        bam = np.asarray(self.bremsam_before, dtype=float).reshape(-1)
        bint = np.asarray(self.bremsint_before, dtype=float).reshape(-1)
        if epi.size < n or brem.size < n:
            raise BremsMapPortError("high-resolution arrays are shorter than ncn2")
        if epim.size < nm or bam.size < nm:
            raise BremsMapPortError("reduced-grid arrays are shorter than ncn2m")
        if bint.size < nm + 1:
            raise BremsMapPortError(
                "bremsint must include caller-owned row ncn2m+1 used as the tail boundary"
            )
        for name, arr in (("epi", epi[:n]), ("bremsa", brem[:n]), ("epim", epim[:nm]),
                          ("bremsam", bam), ("bremsint", bint)):
            if not np.all(np.isfinite(arr)):
                raise BremsMapPortError(f"{name} contains non-finite values")
        if np.any(epi[:n] <= 0.0) or np.any(np.diff(epi[:n]) <= 0.0):
            raise BremsMapPortError("epi must be positive and strictly increasing")
        if np.any(epim[:nm] <= XSTAR_BREMSMAP_EPIM_FLOOR):
            raise BremsMapPortError("epim error")


@dataclass(frozen=True)
class BremsMapResult:
    ncn2: int
    ncn2m: int
    epi_eV: np.ndarray
    bremsa: np.ndarray
    epim_eV: np.ndarray
    mapped_high_resolution_indices_one_based: np.ndarray
    bremsam_before: np.ndarray
    bremsam_after: np.ndarray
    bremsint_before: np.ndarray
    bremsint_after: np.ndarray
    source_file: str = "xstar/xstarlib/src/bremsmap.f90"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the huntf operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def huntf(xx: Sequence[float], x: float, *, n: Optional[int] = None) -> int:
    """Translate ``huntf.f90`` and return the one-based selected index."""
    arr = np.asarray(xx, dtype=float).reshape(-1)
    nn = arr.size if n is None else int(n)
    if nn < 2 or arr.size < nn:
        raise BremsMapPortError("huntf requires at least two grid values")
    xx1 = float(arr[0])
    xx2 = float(arr[1])
    xxn = float(arr[nn - 1])
    xf = float(x)
    xtmp = max(xf, xx2)
    jlo = 1
    if xf < XSTAR_HUNTF_ZERO_FLOOR or xx1 <= XSTAR_HUNTF_ZERO_FLOOR or xxn <= XSTAR_HUNTF_ZERO_FLOOR:
        return jlo
    jlo = int((nn - 1) * math.log(xtmp / xx1) / math.log(xxn / xx1)) + 1
    if jlo < nn:
        # Fortran jlo is one-based.
        tst = abs(math.log(xf / (XSTAR_HUNTF_ZERO_FLOOR + float(arr[jlo - 1]))))
        tst2 = abs(math.log(xf / (XSTAR_HUNTF_ZERO_FLOOR + float(arr[jlo]))))
        if tst2 < tst:
            jlo += 1
    return max(1, min(nn, jlo))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the nbinc operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def nbinc(e: float, epi_eV: Sequence[float], ncn2: int) -> int:
    """Translate ``nbinc.f90`` and return its one-based bin index."""
    n = int(ncn2)
    numcon2 = max(2, n // 50)
    numcon3 = n - numcon2
    if numcon3 < 2:
        raise BremsMapPortError("nbinc search extent is smaller than two bins")
    return huntf(epi_eV, float(e), n=numcon3)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Remap the incident/source continuum onto XSTAR's logarithmic working energy grid using the source hunt/bin interpolation conventions.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def bremsmap(
    bremsa: Sequence[float],
    bremsint_before: Sequence[float],
    epi_eV: Sequence[float],
    epim_eV: Sequence[float],
    *,
    ncn2: Optional[int] = None,
    ncn2m: Optional[int] = None,
    bremsam_before: Optional[Sequence[float]] = None,
) -> BremsMapResult:
    """Execute ``bremsmap.f90`` in literal source order."""
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    brem = np.asarray(bremsa, dtype=float).reshape(-1)
    epim = np.asarray(epim_eV, dtype=float).reshape(-1)
    bint_before = np.asarray(bremsint_before, dtype=float).reshape(-1)
    n = epi.size if ncn2 is None else int(ncn2)
    nm = epim.size if ncn2m is None else int(ncn2m)
    if bremsam_before is None:
        bam_before = np.zeros(max(nm, epim.size), dtype=float)
    else:
        bam_before = np.asarray(bremsam_before, dtype=float).reshape(-1)

    context = BremsMapContext(epi, brem, epim, bam_before, bint_before, n, nm)
    context.validate()

    bam_after = bam_before.copy()
    # Source loop 1: clear only the active reduced-grid rows.
    for mmm in range(1, nm + 1):
        bam_after[mmm - 1] = 0.0

    mapped = np.empty(nm, dtype=int)
    # Source loop 2: nearest logarithmic-grid mapping through nbinc/huntf.
    for mmm in range(1, nm + 1):
        mm = nbinc(float(epim[mmm - 1]), epi, n)
        mapped[mmm - 1] = mm
        bam_after[mmm - 1] = float(brem[mm - 1])

    bint_after = bint_before.copy()
    # Source loop 3: literal ncn2m descending bound and caller-owned tail.
    for mmm in range(1, nm + 1):
        jk = nm - mmm + 1
        sumtmp = (
            (float(brem[jk - 1]) + float(brem[jk]))
            * (float(epi[jk]) - float(epi[jk - 1]))
            / 2.0
        )
        bint_after[jk - 1] = bint_after[jk] + sumtmp * XSTAR_BREMSMAP_ERG_PER_EV

    return BremsMapResult(
        ncn2=n,
        ncn2m=nm,
        epi_eV=epi[:n].copy(),
        bremsa=brem[:n].copy(),
        epim_eV=epim[:nm].copy(),
        mapped_high_resolution_indices_one_based=mapped,
        bremsam_before=bam_before.copy(),
        bremsam_after=bam_after,
        bremsint_before=bint_before.copy(),
        bremsint_after=bint_after,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Apply bremsmap to state for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def apply_bremsmap_to_state(state: XSTARPythonState) -> BremsMapResult:
    """Apply ``bremsmap`` to caller-owned arrays in ``XSTARPythonState``."""
    rad = state.radiation
    missing = [name for name in ("epi", "bremsa", "epim", "bremsint") if getattr(rad, name) is None]
    if missing:
        raise BremsMapPortError(f"radiation state missing: {', '.join(missing)}")
    ncn2 = int(state.control.get("ncn2", len(np.asarray(rad.epi).reshape(-1))))
    ncn2m = int(state.control.get("ncn2m", len(np.asarray(rad.epim).reshape(-1))))
    before = rad.bremsam
    if before is None:
        before = np.zeros(max(ncn2m, len(np.asarray(rad.epim).reshape(-1))), dtype=float)
    result = bremsmap(
        rad.bremsa,
        rad.bremsint,
        rad.epi,
        rad.epim,
        ncn2=ncn2,
        ncn2m=ncn2m,
        bremsam_before=before,
    )
    rad.bremsam = result.bremsam_after.copy()
    rad.bremsint = result.bremsint_after.copy()
    rad.provenance["bremsmap"] = {
        "source_file": result.source_file,
        "ncn2": result.ncn2,
        "ncn2m": result.ncn2m,
        "mapped_indices_one_based": result.mapped_high_resolution_indices_one_based.tolist(),
        "tail_boundary_index_one_based": result.ncn2m + 1,
    }
    state.local_zone.source_arrays["bremsmap"] = result
    return result


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Register bremsmap source routine for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def register_bremsmap_source_routine(driver: XSTARPythonDriver) -> None:
    driver.register_source_routine(XSTARSourceRoutine.BREMSMAP, apply_bremsmap_to_state)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Provide the direct-source reference for fortran reference cases for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def direct_fortran_reference_cases() -> Mapping[str, Mapping[str, Any]]:
    """Frozen outputs from the unmodified XSTAR routines compiled with stub modules."""
    return {
        "case1": {
            "bremsam": [4.25, 9.375, 16.5, 36.75, 82.125],
            "bremsint": [
                1006.00000000117848,
                1006.00000000117416,
                1006.00000000115233,
                1006.00000000106945,
                1006.00000000079945,
                1006.0,
                1007.0,
            ],
        },
        "case2": {
            "bremsam": [0.003, 0.003, 0.009000000000000001, 42.0, 42.0],
            "bremsint": [
                10.4000000000002597,
                10.4000000000002526,
                10.4000000000002082,
                10.4,
                10.5,
            ],
        },
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute direct fortran reference validation for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def run_direct_fortran_reference_validation(*, rtol: float = 2.0e-15, atol: float = 0.0) -> Mapping[str, Any]:
    refs = direct_fortran_reference_cases()

    epi1 = np.asarray([2.0 ** i for i in range(12)], dtype=float)
    brem1 = np.asarray([(i * i) + 0.125 * i for i in range(1, 13)], dtype=float)
    bint1 = np.asarray([1001.0 + i for i in range(12)], dtype=float)
    bam1 = np.full(12, -777.0)
    epim1 = np.asarray([1.0, 3.0, 9.0, 31.0, 200.0])
    r1 = bremsmap(brem1, bint1, epi1, epim1, ncn2=12, ncn2m=5, bremsam_before=bam1)

    epi2 = np.asarray([10.0 ** (i / 2.0) for i in range(8)], dtype=float)
    brem2 = np.asarray([1.0e-3 * (2 * i - 1) for i in range(1, 9)], dtype=float)
    bint2 = np.asarray([10.0 + i / 10.0 for i in range(1, 9)], dtype=float)
    bam2 = np.full(8, 42.0)
    epim2 = np.asarray([1.0, 5.0, 100.0])
    r2 = bremsmap(brem2, bint2, epi2, epim2, ncn2=8, ncn2m=3, bremsam_before=bam2)

    c1_bam = bool(np.allclose(r1.bremsam_after[:5], refs["case1"]["bremsam"], rtol=rtol, atol=atol))
    c1_bint = bool(np.allclose(r1.bremsint_after[:7], refs["case1"]["bremsint"], rtol=rtol, atol=atol))
    c2_bam = bool(np.allclose(r2.bremsam_after[:5], refs["case2"]["bremsam"], rtol=rtol, atol=atol))
    c2_bint = bool(np.allclose(r2.bremsint_after[:5], refs["case2"]["bremsint"], rtol=rtol, atol=atol))
    return {
        "port_version": "v0.4.60",
        "bremsmap_translated": True,
        "nbinc_huntf_translated": True,
        "default_real_erg_per_ev": XSTAR_BREMSMAP_ERG_PER_EV,
        "case1_bremsam_ready": c1_bam,
        "case1_bremsint_ready": c1_bint,
        "case2_bremsam_ready": c2_bam,
        "case2_bremsint_ready": c2_bint,
        "reduced_grid_mapping_ready": bool(c1_bam and c2_bam),
        "caller_owned_bremsint_tail_ready": bool(c1_bint and c2_bint),
        "bremsmap_source_acceptance_ready": bool(c1_bam and c1_bint and c2_bam and c2_bint),
        "next_source_target": "calc_emisab_all",
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write bremsmap validation products for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.3 and 11.6.5, source spectrum and continuum energy grid.
# XSTAR-FUNCTION-COMMENT-END
def write_bremsmap_validation_products(summary: Mapping[str, Any], out_dir: str | Path) -> Mapping[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "xstar_bremsmap_source_validation_summary.json"
    md_path = out / "xstar_bremsmap_source_validation_summary.md"
    json_path.write_text(json.dumps(dict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "# XSTAR `bremsmap` source validation\n\n"
        + "\n".join(f"- {k}: `{v}`" for k, v in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}
