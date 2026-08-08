# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: ucalc.f90 label 50 / deleafnd.f90 / linopac.f90
#   Role: Derive live Type-50 line-profile inputs shared with the qualified C++ opacity path.
#   Relation: Source-derived provenance helper; no reference-product physics is injected.
#   Concordance: TYPE50-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   Appendix A Type 50 stores wavelength, weighted oscillator strength, Einstein A, and lower/upper level
#   IDs. The profile path must preserve that record identity independently of downstream rate-type handling.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Type-50 profile scalar provenance shared by the Python runtime.

v82 patch 5.20.17.3.5 aligns the live Python Type-50 profile inputs with the
already-qualified C++ path while preserving the literal XSTAR damping lookup:

* atomic mass comes from the fixed C++ parity table used by
  ``xstar_atdb_runtime.cpp``;
* natural width follows ``deleafnd.f90``: walk rate-type 41 for the parent ion,
  match the source upper local level against the second INTEGER, and use the
  third REAL times the historical 4.136e-15 eV s conversion;
* if no rate-type-41 match exists, fall back to the Type-50 A value times the
  same conversion.

No opacity, population, transport, or writer state is read from a reference
product here.  The helpers depend only on live ATDB topology and record data.
"""
from __future__ import annotations

import math
from typing import Any

# Exact table currently used by the accepted C++ ATDB lowerer.
CPP_ATOMIC_MASS_AMU: tuple[float, ...] = (
    0.0, 1.00794, 4.002602, 6.941, 9.012182, 10.811, 12.0107, 14.0067,
    15.9994, 18.9984032, 20.1797, 22.98976928, 24.3050, 26.9815386,
    28.0855, 30.973762, 32.065, 35.453, 39.948, 39.0983, 40.078,
    44.955912, 47.867, 50.9415, 51.9961, 54.938045, 55.845, 58.933195,
    58.6934, 63.546, 65.38,
)

SOURCE_TYPE50_DAMPING_EV_SECOND = 4.136e-15


def _ion_index_for_record(derived: Any, record: int, ion_index: int | None) -> int:
    if ion_index is not None and int(ion_index) > 0:
        return int(ion_index)
    try:
        ion_record = int(derived.npar[int(record)])
        if ion_record <= 0:
            return 0
        for idx in range(1, len(derived.ion_records)):
            if int(derived.ion_records[idx]) == ion_record:
                return idx
    except Exception:
        pass
    return 0


def cpp_parity_atomic_mass_amu(
    master: Any,
    derived: Any,
    record: int,
    *,
    ion_index: int | None = None,
) -> float:
    """Return the accepted C++ atomic mass, with ATDB-parent fallback."""
    idx = _ion_index_for_record(derived, int(record), ion_index)
    try:
        z = int(derived.ion_element_z[idx]) if idx > 0 else 0
    except Exception:
        z = 0
    if 0 < z < len(CPP_ATOMIC_MASS_AMU):
        value = float(CPP_ATOMIC_MASS_AMU[z])
        if math.isfinite(value) and value > 0.0:
            return value
    # Non-qualified elements retain the previous source-parent behavior.
    try:
        ion_record = int(derived.npar[int(record)])
        element_record = int(derived.npar[ion_record]) if ion_record > 0 else 0
        reals = master.record_reals(element_record) if element_record > 0 else ()
        if len(reals) > 1:
            value = float(reals[1])
            if math.isfinite(value) and value > 0.0:
                return value
    except Exception:
        pass
    return 1.0


def source_type50_natural_width_ev(
    master: Any,
    derived: Any,
    *,
    ion_index: int,
    upper_local: int,
    fallback_aij_s: float,
) -> tuple[float, int, bool]:
    """Translate ``deleafnd`` for a Type-50 line.

    Returns ``(width_eV, matched_record, matched_rate41)``.  ``matched_record``
    is zero on fallback.
    """
    ion = int(ion_index)
    upper = int(upper_local)
    fallback = float(fallback_aij_s)
    try:
        npfi = derived.npfi
        npar = derived.npar
        npnxt = derived.npnxt
        if ion > 0 and upper > 0 and npfi.shape[0] > 41 and ion < npfi.shape[1]:
            rec = int(npfi[41, ion])
            parent = int(npar[rec]) if 0 < rec < len(npar) else 0
            guard = 0
            while 0 < rec < len(npar) and int(npar[rec]) == parent:
                ints = master.record_integers(rec)
                reals = master.record_reals(rec)
                if len(ints) >= 2 and int(ints[1]) == upper and len(reals) >= 3:
                    rate = float(reals[2])
                    if math.isfinite(rate):
                        return rate * SOURCE_TYPE50_DAMPING_EV_SECOND, int(rec), True
                nxt = int(npnxt[rec]) if rec < len(npnxt) else 0
                if nxt == rec:
                    raise RuntimeError(f"Type-41 damping record self-cycle at {rec}")
                rec = nxt
                guard += 1
                if guard > len(npar):
                    raise RuntimeError("Type-41 damping record cycle")
    except Exception:
        # Preserve source fallback rather than turning a diagnostic lookup
        # problem into a missing line profile.
        pass
    return fallback * SOURCE_TYPE50_DAMPING_EV_SECOND, 0, False
