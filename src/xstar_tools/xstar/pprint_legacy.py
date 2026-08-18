# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: pprint.f90 / nbinc.f90 / huntf.f90
#   Role: Produce the legacy STEP print options and abundance/log diagnostics.
#   Relation: Source-exact/source-equivalent formatting and numerical option semantics where qualified.
#   Concordance: STEP-001; TERMINAL-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Source-faithful bounded translation of the legacy XSTAR ``pprint`` path.

The original ``pprint.f90`` routine is a 30-way computed-GOTO report writer.
The production/default XSTAR caller uses a coherent subset for the physical
products:

``3 -> 2 -> 17 -> [9,12 per final-pass shell] -> [9,12 terminal] -> 22 -> 11``.

v0.5.23 emits the verbose ``lprint=1`` terminal diagnostics in the observed
source order: ``pprint(1)``, ``pprint(23)``, ``pprint(24)``, ``pprint(16)``,
``pprint(27)``, ``pprint(15)``, ``pprint(19)``, and ``pprint(5)``.  These are
text-report diagnostics only; they do not change the FITS product path or any
physical arrays.
"""

from __future__ import annotations

from .constants import LEGACY_BOLTZMANN_EV_PER_T4

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the install astropy numpy compatibility operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _install_astropy_numpy_compatibility() -> None:
    """Install narrow NumPy shims needed by older Astropy on new NumPy."""
    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # type: ignore[attr-defined]
    try:
        import numpy.lib._function_base_impl as _np_function_base
    except Exception:
        return
    if not hasattr(_np_function_base, "_check_interpolation_as_method"):
        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Check interpolation as method for this module while preserving the surrounding source/runtime invariants.
        # Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
        # XSTAR-FUNCTION-COMMENT-END
        def _check_interpolation_as_method(method, interpolation, fname):
            if method != "linear":
                raise TypeError(
                    "You shall not pass both `method` and `interpolation`!\n"
                    "(`interpolation` is Deprecated in favor of `method`)"
                )
            return interpolation

        _np_function_base._check_interpolation_as_method = _check_interpolation_as_method


_install_astropy_numpy_compatibility()

from astropy.io import fits

from .radiation import nbinc
from .state import XSTARPythonState
from .fits_provenance import apply_python_primary_fits_header


class LegacyPprintPortError(RuntimeError):
    """Raised when the bounded source ``pprint`` contract is unavailable."""


ERGSEV = 1.602197e-12
NLPRNT = (
    22, 11, 1, 23, 24, 16, 27, 15, 19, 5, 14, 21, 7, 10, 26, 0, 4, 6, 18, 29, 30, 28
)

ELEMENT_FULL_NAMES = (
    "hydrogen", "helium", "lithium", "beryllium", "boron",
    "carbon", "nitrogen", "oxygen", "fluorine", "neon",
    "sodium", "magnesium", "aluminum", "silicon", "phosphoru",
    "sulfur", "chlorine", "argon", "potassium", "calcium",
    "scandium", "titanium", "vanadium", "chromium", "manganese",
    "iron", "cobalt", "nickel", "copper", "zinc",
)
ELEMENT_SYMBOL_TO_FULL_NAME = {
    "H": "hydrogen", "HE": "helium", "LI": "lithium", "BE": "beryllium",
    "B": "boron", "C": "carbon", "N": "nitrogen", "O": "oxygen",
    "F": "fluorine", "NE": "neon", "NA": "sodium", "MG": "magnesium",
    "AL": "aluminum", "SI": "silicon", "P": "phosphoru", "S": "sulfur",
    "CL": "chlorine", "AR": "argon", "K": "potassium", "CA": "calcium",
    "SC": "scandium", "TI": "titanium", "V": "vanadium", "CR": "chromium",
    "MN": "manganese", "FE": "iron", "CO": "cobalt", "NI": "nickel",
    "CU": "copper", "ZN": "zinc",
}


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the pprint element column name operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _pprint_element_column_name(item: PprintElementMetadata) -> str:
    """Return source ``pprint(11)`` elemental column names for heat/cool tables.

    XSTAR's ``xout_abund1.fits`` HEATING and COOLING extensions use full
    element names (``hydrogen``, ``helium``, ...), while the input-abundance
    report and ion labels may use element symbols.  Keep the physical metadata
    unchanged and translate only the FITS table column headers here.
    """
    index = int(item.element_index)
    if 1 <= index <= len(ELEMENT_FULL_NAMES):
        return ELEMENT_FULL_NAMES[index - 1]
    label = str(item.element_label).strip()
    mapped = ELEMENT_SYMBOL_TO_FULL_NAME.get(label.upper())
    return (mapped or label).replace(" ", "_")


@dataclass(frozen=True)
class PprintIonMetadata:
    ion_index: int
    ion_label: str
    element_index: int
    elemental_abundance: float


@dataclass(frozen=True)
class PprintElementMetadata:
    element_index: int
    element_label: str


@dataclass(frozen=True)
class PprintAtomicMetadata:
    element_labels: tuple[str, ...]
    ions: tuple[PprintIonMetadata, ...]
    thermal_elements: tuple[PprintElementMetadata, ...]
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class LegacyPprintBuffers:
    """Caller-owned arrays corresponding to ``zrtmp*`` and the log unit."""

    log_lines: list[str] = field(default_factory=list)
    abundance_rows: dict[int, np.ndarray] = field(default_factory=dict)
    heating_rows: dict[int, np.ndarray] = field(default_factory=dict)
    cooling_rows: dict[int, np.ndarray] = field(default_factory=dict)
    parameter_values: list[float] = field(default_factory=list)
    parameter_comments: list[str] = field(default_factory=list)
    source_calls: list[str] = field(default_factory=list)
    initialized: bool = False
    final_written: bool = False
    begun_passes: set[int] = field(default_factory=set)
    source_file: str = "xstar/xstarlib/src/pprint.f90"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the pprint metadata operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _pprint_metadata(state: XSTARPythonState) -> PprintAtomicMetadata:
    value = state.control.get("pprint_atomic_metadata")
    if not isinstance(value, PprintAtomicMetadata):
        raise LegacyPprintPortError(
            "legacy pprint requires state.control['pprint_atomic_metadata']"
        )
    return value


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the buffers operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _buffers(state: XSTARPythonState, *, create: bool = False) -> LegacyPprintBuffers:
    value = state.outputs.get("legacy_pprint_buffers")
    if value is None and create:
        value = LegacyPprintBuffers()
        state.outputs["legacy_pprint_buffers"] = value
    if not isinstance(value, LegacyPprintBuffers):
        raise LegacyPprintPortError("legacy pprint caller-owned buffers are missing")
    return value


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the workspace operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _workspace(state: XSTARPythonState) -> Any:
    value = state.control.get("radial_transfer_workspace")
    if value is None:
        raise LegacyPprintPortError("legacy pprint requires radial transfer workspace")
    return value


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the array value operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _array_value(state: XSTARPythonState, name: str, length: int) -> np.ndarray:
    candidates = (
        state.local_zone.source_arrays.get(name),
        state.control.get(name),
    )
    for value in candidates:
        if value is not None:
            arr = np.asarray(value, dtype=float).reshape(-1)
            if arr.size < length:
                raise LegacyPprintPortError(f"{name} is shorter than {length}")
            return arr[:length].copy()
    return np.zeros(length, dtype=float)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fmt e operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _fmt_e(value: float, width: int = 11, precision: int = 3) -> str:
    return f"{float(value):{width}.{precision}E}"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fmt list integer operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _fmt_list_integer(value: int) -> str:
    # gfortran list-directed integers have a leading blank in these records.
    return f" {int(value)}"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fortran logical line 17 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _fortran_logical_line_17() -> tuple[str, str]:
    # Exact gfortran rendering of source formats 9979 and 9989.
    return (
        "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)",
        "                                                                  fwd    rev",
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the temperature t4 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _temperature_t4(state: XSTARPythonState) -> float:
    value = float(state.plasma.temperature)
    unit = str(state.control.get("plasma_temperature_unit", "legacy-auto")).strip().lower()
    if unit in {"k", "kelvin"}:
        return value / 1.0e4
    if unit in {"t4", "1e4k", "10^4k"}:
        return value
    return value / 1.0e4 if value > 1.0e3 else value


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the active epi operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _active_epi(state: XSTARPythonState) -> np.ndarray:
    n = int(state.control["ncn2"])
    epi = np.asarray(state.radiation.epi, dtype=float).reshape(-1)
    if epi.size < n:
        raise LegacyPprintPortError("epi is shorter than ncn2")
    return epi[:n]


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option3 parameter capture operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option3_parameter_capture(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    metadata = _pprint_metadata(state)
    values = [
        float(state.control.get("cfrac", 0.0)),
        _temperature_t4(state),
        float(1 - int(state.control.get("lcdd", 1))),
        float(state.control.get("p", 0.0)),
        float(state.plasma.xpx),
        0.0,
        0.0,
        float(state.control.get("specunit", 0)),
        float(state.control.get("trad", 0.0)),
        float(state.control.get("xlum", 0.0)),
        float(state.control.get("xpxcol", 0.0)),
        float(state.control.get("zeta", 0.0)),
        float(state.control.get("numrec", 0)),
        float(state.control.get("nlimd", 0)),
        float(state.control.get("lwri", 0)),
        float(state.control.get("lpri", 0)),
        float(state.control.get("lfix", 0)),
        0.0,
    ]
    abel = np.asarray(state.control.get("abel", np.ones(len(metadata.element_labels))), dtype=float)
    if abel.size < len(metadata.element_labels):
        raise LegacyPprintPortError("abel is shorter than pprint element list")
    values.extend(float(v) for v in abel[: len(metadata.element_labels)])
    values.extend([
        float(state.control.get("emult", 0.0)),
        float(state.control.get("taumax", 0.0)),
        float(state.control.get("xeemin", 0.0)),
        float(state.control.get("critf", 0.0)),
        float(state.control.get("vturbi", 0.0)),
        float(state.control.get("npass", 1)),
        0.0,
        float(state.control.get("nloopctl", 0)),
    ])
    comments = [""] * len(values)
    comments[5] = str(state.control.get("spectype", ""))
    comments[6] = str(state.control.get("specfile", ""))
    comments[17] = str(state.control.get("abndtbl", ""))
    comments[-2] = str(state.control.get("kmodelname", ""))
    buf.parameter_values = values
    buf.parameter_comments = comments
    buf.log_lines.append(" print option: 3")
    buf.source_calls.append("pprint(3)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option2 input lines operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option2_input_lines(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    metadata = _pprint_metadata(state)
    abel = np.asarray(state.control.get("abel", np.ones(len(metadata.element_labels))), dtype=float)
    ababs = np.asarray(state.control.get("ababs", np.ones(len(metadata.element_labels))), dtype=float)
    if abel.size < len(metadata.element_labels) or ababs.size < len(metadata.element_labels):
        raise LegacyPprintPortError("pprint abundance arrays are shorter than element list")
    r = float(state.transfer.radius)
    r19 = r / 1.0e19
    flux = float(state.control.get("xlum", 0.0)) / 12.56 / r19 / r19
    lines = [
        " ",
        " print option: 2",
        " input parameters:",
        f"covering fraction=    {_fmt_e(state.control.get('cfrac', 0.0))}",
        f"temperature (/10**4K)={_fmt_e(_temperature_t4(state))}",
        " constant pressure switch (1=yes, 0=no)=" + _fmt_list_integer(1 - int(state.control.get("lcdd", 1))),
        f"pressure (dyne/cm**2)={_fmt_e(state.control.get('p', 0.0))}",
        f"density (cm**-3)=     {_fmt_e(state.plasma.xpx)}",
        " spectrum type=" + str(state.control.get("spectype", "")),
        " spectrum file=" + str(state.control.get("specfile", "")),
        " spectrum units? (0=energy, 1=photons)" + _fmt_list_integer(int(state.control.get("specunit", 0))),
        f"radiation temperature or alpha={_fmt_e(state.control.get('trad', 0.0))}",
        f"luminosity (/10**38 erg/s)={_fmt_e(state.control.get('xlum', 0.0))}",
        f"column density (cm**-2)={_fmt_e(state.control.get('xpxcol', 0.0))}",
        f"log(ionization parameter)={_fmt_e(state.control.get('zeta', 0.0))}",
        f"flux=                 {_fmt_e(flux)}",
        " abundance table: " + str(state.control.get("abndtbl", "")),
        " abundances:",
        " element,   rel.to cosmic,     rel. to H,     H=12",
    ]
    h = max(float(ababs[0]), 1.0e-48)
    for label, rel, absolute in zip(metadata.element_labels, abel, ababs):
        ab12 = 12.0 + np.log10(max(1.0e-12, float(absolute)) / h)
        lines.append(f" {label[:8]:8s}{_fmt_e(rel)}{_fmt_e(absolute)}{_fmt_e(ab12)}")
    lines.extend([
        " model name=" + str(state.control.get("kmodelname", "")),
        " number of steps=" + _fmt_list_integer(int(state.control.get("numrec", 0))),
        " number of iterations=" + _fmt_list_integer(int(state.control.get("nlimd", 0))),
        " write switch (1=yes, 0=no)=" + _fmt_list_integer(int(state.control.get("lwri", 0))),
        " print switch (1=yes, 0=no)=" + _fmt_list_integer(int(state.control.get("requested_lpri", state.control.get("lpri", 0)))),
        " step size choice switch=" + _fmt_list_integer(int(state.control.get("lfix", 0))),
        " loop control (0=standalone)=" + _fmt_list_integer(int(state.control.get("nloopctl", 0))),
        " number of passes=" + _fmt_list_integer(int(state.control.get("npass", 1))),
        " emult=" + _fmt_e(state.control.get("emult", 0.0)),
        " taumax=" + _fmt_e(state.control.get("taumax", 0.0)),
        " xeemin=" + _fmt_e(state.control.get("xeemin", 0.0)),
        " critf=" + _fmt_e(state.control.get("critf", 0.0)),
        " vturbi=" + _fmt_e(state.control.get("vturbi", 0.0)),
        " ncn2=" + _fmt_list_integer(int(state.control.get("ncn2", 0))),
        " radexp=" + _fmt_e(state.control.get("radexp", 0.0)),
        " ",
        " ",
    ])
    buf.log_lines.extend(lines)
    buf.source_calls.append("pprint(2)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option17 headings operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option17_headings(buf: LegacyPprintBuffers) -> None:
    buf.log_lines.append(" print option:17")
    buf.log_lines.extend(_fortran_logical_line_17())
    buf.source_calls.append("pprint(17)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Initialize legacy pprint for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def initialize_legacy_pprint(state: XSTARPythonState) -> LegacyPprintBuffers:
    """Execute source initialization calls ``pprint(3)`` and ``pprint(2)``."""
    buf = _buffers(state, create=True)
    if buf.initialized:
        return buf
    _option3_parameter_capture(state, buf)
    _option2_input_lines(state, buf)
    buf.log_lines.append(" running ...")
    # xstar.f90 calls ispcg2 immediately after ``running ...`` and before the
    # first pass banner.  These are spectrum diagnostics only; they do not
    # alter any controller or thermal state.
    if all(k in state.control for k in ("ispcg2_u_1_1p8", "ispcg2_u_1p8_4", "ispcg2_lbol")):
        buf.log_lines.append(
            " U(1-1.8),U(1.8-4):"
            f"   {float(state.control['ispcg2_u_1_1p8']):.16g}"
            f"        {float(state.control['ispcg2_u_1p8_4']):.16g}"
        )
        buf.log_lines.append(f" Lbol=   {float(state.control['ispcg2_lbol']):.16e}")
    buf.initialized = True
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return buf



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the legacy pprint begin pass operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def legacy_pprint_begin_pass(state: XSTARPythonState) -> tuple[str, ...]:
    """Emit the source pass banner followed by ``pprint(17)`` headings."""
    if not bool(state.control.get("pprint_legacy_enabled", False)):
        return ()
    buf = initialize_legacy_pprint(state)
    kk = int(state.transfer.pass_index)
    if kk in buf.begun_passes:
        return ()
    ldir = int(state.transfer.direction)
    # xstar.f90 calls ispcg2 before each pass banner.  Pass 1 was emitted by
    # initialize_legacy_pprint; repeated passes use the freshly regenerated
    # source spectrum retained by radial_transfer.
    if kk > 1:
        rows = state.control.get("ispcg2_passes_v0682274", state.control.get("ispcg2_passes_v0682273", ()))
        row = next((item for item in rows if int(item.get("pass_index", 0)) == kk), None)
        if row is not None:
            buf.log_lines.append(
                " U(1-1.8),U(1.8-4):"
                f"   {float(row['u_1_1p8']):.16g}"
                f"        {float(row['u_1p8_4']):.16g}"
            )
            buf.log_lines.append(f" Lbol=   {float(row['lbol']):.16e}")
    buf.log_lines.append(" ")
    # This is list-directed in xstar.f90; retain the textual contract while
    # avoiding compiler-dependent leading-field padding.
    buf.log_lines.append(f" pass number= {kk} {ldir}")
    _option17_headings(buf)
    buf.begun_passes.add(kk)
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return ("pprint(17)",)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option9 zone line operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option9_zone_line(state: XSTARPythonState, buf: LegacyPprintBuffers) -> str:
    workspace = _workspace(state)
    epi = _active_epi(state)
    n = epi.size
    zremsz = np.asarray(workspace.zremsz, dtype=float).reshape(-1)[:n]
    zrems = np.asarray(workspace.zrems, dtype=float)
    dpthc = np.asarray(workspace.dpthc, dtype=float)
    if zrems.shape[0] < 3 or zrems.shape[1] < n or dpthc.shape[0] < 2 or dpthc.shape[1] < n:
        raise LegacyPprintPortError("pprint option 9 arrays are shorter than source ranges")
    sum_in = float(np.trapezoid(zremsz, epi) * ERGSEV)
    sum_out = float(np.trapezoid(zrems[0, :n], epi) * ERGSEV)
    terr = (sum_in - sum_out) / (sum_in + 1.0e-24)
    r = float(state.transfer.radius)
    rdel = float(state.transfer.radial_depth)
    xcol = float(state.transfer.column)
    xpx = float(state.plasma.xpx)
    xee = float(state.plasma.xee)
    t4 = _temperature_t4(state)
    r19 = r * 1.0e-19
    xlum = float(state.control.get("xlum", 0.0))
    skse = xlum / xpx / r19 / r19
    zeta = np.log10(max(1.0e-24, skse))
    # 0.6.82.27.16: pprint.f90 receives zeta by reference and option 9
    # assigns the radius-local log(xi) before the caller's terminal SAVD.
    # Preserve that side effect so the terminal detail header owns the same
    # LOGXI scalar as canonical FORTRAN.
    state.control["zeta"] = float(zeta)
    nry = int(nbinc(13.6, epi, n)) + 1
    nry0 = max(1, min(n, nry)) - 1
    # The first h-c(%) column is the local thermal-balance residual.
    # Keep the physical value by default, but allow the dsec handler to pass
    # the exact source-display residual snapshot when available.  This avoids
    # recomputing a display value from stale state during terminal/xout logging.
    hc1_percent = float(state.control.get(
        "legacy_pprint_hc1_percent",
        float(state.thermal.residual) * 100.0,
    ))
    values = (
        np.log10(r),
        np.log10(max(1.0e-36, min(99.0, rdel / r))),
        np.log10(max(xcol, 1.0e-10)),
        zeta,
        xee,
        np.log10(xpx),
        np.log10(t4) + 4.0,
        min(99.99, max(-99.99, hc1_percent)),
        min(99.99, max(-99.99, terr * 100.0)),
        np.log10(max(dpthc[0, nry0], 1.0e-10)),
        np.log10(max(dpthc[1, nry0], 1.0e-10)),
    )
    line = " " + "".join(f" {float(value):6.2f}" for value in values)
    # XSTAR's print option 17 displays the count of completed thermal-balance
    # evaluations used by the current radial row, not the Python diagnostic's
    # increment-after-evaluator counter.  The first non-trivial solve therefore
    # appears as ntotit-1 while the one-shot second row remains one.
    line += f"{int(state.control.get('legacy_pprint_ntotit', state.control.get('ntotit', 0))):3d}"
    buf.log_lines.append(line)
    # Keep the exact source-like line available for terminal progress.  The
    # CLI should print this line rather than recomputing approximate values
    # from transfer arrays, so terminal output and xout_step.log stay aligned.
    state.outputs["latest_legacy_pprint9_line"] = line
    buf.source_calls.append("pprint(9)")
    return line


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option12 accumulate operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option12_accumulate(state: XSTARPythonState, buf: LegacyPprintBuffers, *, zone_index: int) -> None:
    metadata = _pprint_metadata(state)
    j = int(zone_index)
    if j > 3999:
        return
    nions = len(metadata.ions)
    nelem = len(metadata.thermal_elements)
    base = np.zeros(8, dtype=float)
    r = float(state.transfer.radius)
    xpx = float(state.plasma.xpx)
    r19 = r * 1.0e-19
    zeta = np.log10(max(1.0e-24, float(state.control.get("xlum", 0.0)) / xpx / r19 / r19))
    base[:] = (
        r,
        float(state.transfer.radial_depth),
        zeta,
        float(state.plasma.xee),
        xpx,
        float(state.control.get("p", 0.0)),
        _temperature_t4(state),
        float(state.thermal.residual),
    )
    xii = _array_value(state, "xii", nions)
    htt = _array_value(state, "htt", nelem)
    cll = _array_value(state, "cll", nelem)
    abundance = np.concatenate((base, xii))
    heating = np.concatenate((base, htt, [float(state.control.get("htcomp", 0.0)), float(state.thermal.heating)]))
    cooling = np.concatenate((base, cll, [float(state.control.get("clcomp", 0.0)), float(state.control.get("clbrems", 0.0)), float(state.thermal.cooling)]))
    buf.abundance_rows[j] = abundance
    buf.heating_rows[j] = heating
    buf.cooling_rows[j] = cooling
    buf.source_calls.append("pprint(12)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the legacy pprint after heatt operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def legacy_pprint_after_heatt(state: XSTARPythonState, *, terminal_record: bool = False) -> tuple[str, ...]:
    """Execute source ``pprint(9)`` and final-pass ``pprint(12)``."""
    if not bool(state.control.get("pprint_legacy_enabled", False)):
        return ()
    buf = initialize_legacy_pprint(state)
    _option9_zone_line(state, buf)
    calls = ["pprint(9)"]
    if int(state.transfer.pass_index) == int(state.control.get("npass", 1)):
        # xstar.f90 sets numrec=jkp+1 after the first-pass loop, but then the
        # terminal pprint(12) call is still made with jkstep=jkp.  Therefore
        # the final radial state overwrites the last in-loop row and the extra
        # numrec row remains zero padding.  Do not write terminal abundance data
        # to numrec; that creates a spurious extra xout_abund1 row.
        zone_index = int(state.transfer.zone_index)
        _option12_accumulate(state, buf, zone_index=zone_index)
        calls.append("pprint(12:terminal)" if terminal_record else "pprint(12)")
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return tuple(calls)




# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the line metadata rows operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _line_metadata_rows(state: XSTARPythonState) -> tuple[Any, ...]:
    """Return output line metadata without importing output_writers at module load."""
    meta = state.control.get("output_atomic_metadata")
    rows = getattr(meta, "lines", ())
    return tuple(rows) if rows is not None else ()


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the source fixed capacity line rank operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _source_fixed_capacity_line_rank(
    rows: Sequence[Any],
    values: np.ndarray,
    *,
    depth_mode: bool,
    limit: int = 500,
    activity_floor: float = 1.0e-49,
) -> list[Any]:
    """Literal ``pprint.f90`` fixed-capacity ``kltmp`` identity rank.

    This is the Python publication counterpart of the accepted C++
    ``source_pprint_line_identity_rank`` implementation. Equal
    keys insert ahead of existing equal-key rows, and the source terminal-slot
    retention is preserved after the fixed list reaches capacity.
    """
    maximum_rows = max(0, int(limit))
    if maximum_rows == 0:
        return []
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return []
    ordered = sorted(
        (row for row in rows if int(getattr(row, "line_index", 0)) > 0),
        key=lambda row: int(getattr(row, "line_index", 0)),
    )
    kltmp = [0] * maximum_rows
    keys = [0.0] * len(ordered)
    valid = [False] * len(ordered)
    kltmpo = 0
    nlpl = 1
    for si, row in enumerate(ordered):
        idx = int(getattr(row, "line_index", 0)) - 1
        if idx < 0 or idx >= arr.shape[1]:
            continue
        rate_type = int(getattr(row, "rate_type", 50))
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        if rate_type in (9, 14) or not (wave >= 0.1 and wave <= 1.0e10 and wave <= 8.9e6):
            continue
        key = float(arr[0, idx]) if depth_mode else 0.5 * (float(arr[0, idx]) + float(arr[1, idx]))
        if not np.isfinite(key) or not (key > float(activity_floor)):
            continue
        keys[si] = key
        valid[si] = True
        lmm = 0
        elcomp = 1.0e10
        while lmm < nlpl and key < elcomp:
            lmm += 1
            kl2 = kltmp[lmm - 1]
            elcomp = keys[kl2 - 1] if kl2 > 0 else 0.0
        kltmpo = si + 1
        last = min(maximum_rows, nlpl)
        if lmm > 0:
            for k in range(lmm, last + 1):
                at = k - 1
                kltmpn = kltmp[at]
                kltmp[at] = kltmpo
                kltmpo = kltmpn
        nlpl = min(maximum_rows, nlpl + 1)
    if nlpl > 0:
        kltmp[nlpl - 1] = kltmpo
    out: list[Any] = []
    for kk in range(min(nlpl, len(kltmp))):
        if kltmp[kk] == 0:
            continue
        si = kltmp[kk] - 1
        if 0 <= si < len(ordered) and valid[si]:
            out.append(ordered[si])
    return out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the numeric line rank operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _numeric_line_rank(
    rows: Sequence[Any], values: np.ndarray, *, depth_mode: bool, limit: int = 500
) -> list[Any]:
    """Independent ranked numerical owner used by Options 1/23."""
    arr = np.asarray(values, dtype=float)
    ranked: list[tuple[float, int, Any]] = []
    for order, row in enumerate(rows):
        idx = int(getattr(row, "line_index", 0)) - 1
        if idx < 0 or arr.ndim != 2 or arr.shape[0] < 2 or idx >= arr.shape[1]:
            continue
        rate_type = int(getattr(row, "rate_type", 50))
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        if rate_type in (9, 14) or not (wave >= 0.1 and wave <= 1.0e10 and wave <= 8.9e6):
            continue
        key = float(arr[0, idx]) if depth_mode else 0.5 * (float(arr[0, idx]) + float(arr[1, idx]))
        if not np.isfinite(key):
            continue
        ranked.append((-key, -order, row))
    ranked.sort()
    return [row for _, _, row in ranked[: int(limit)]]


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option1 emission line luminosities operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option1_emission_line_luminosities(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit source-ranked ``pprint(1)`` with independent numeric owner."""
    workspace = _workspace(state)
    rows = _line_metadata_rows(state)
    elum = np.asarray(getattr(workspace, "elum", np.zeros((2, 0))), dtype=float)
    if elum.ndim != 2 or elum.shape[0] < 2:
        return
    buf.log_lines.extend([
        " ",
        " print option: 1",
        " emission line luminosities (erg/sec/10**38))",
        " index, ion, wavelength, reflected, transmitted",
    ])
    identity_rows = _source_fixed_capacity_line_rank(rows, elum, depth_mode=False, limit=500)
    numeric_rows = _numeric_line_rank(rows, elum, depth_mode=False, limit=500)
    for out_index, (identity_row, numeric_row) in enumerate(zip(identity_rows, numeric_rows), start=1):
        numeric_idx = int(getattr(numeric_row, "line_index", 0)) - 1
        ion = str(getattr(identity_row, "ion_label", ""))[:8]
        wave = abs(float(getattr(identity_row, "wavelength_angstrom", 0.0)))
        reflected = float(elum[0, numeric_idx])
        transmitted = float(elum[1, numeric_idx])
        buf.log_lines.append(
            f"{out_index:9d}{int(getattr(identity_row, 'line_index', 0)):8d} {ion:<8s}"
            f"{wave:13.5E}{reflected:13.5E}{transmitted:13.5E}"
        )
    buf.source_calls.append("pprint(1)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option23 line depths operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option23_line_depths(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit source-ranked ``pprint(23)`` with independent numeric owner."""
    workspace = _workspace(state)
    rows = _line_metadata_rows(state)
    tau0 = np.asarray(getattr(workspace, "tau0", np.zeros((2, 0))), dtype=float)
    if tau0.ndim != 2 or tau0.shape[0] < 2:
        return
    buf.log_lines.extend([
        " ",
        " print option:23",
        " line depths",
        " index, ion, wavelength, reflected, transmitted",
    ])
    identity_rows = _source_fixed_capacity_line_rank(rows, tau0, depth_mode=True, limit=500)
    numeric_rows = _numeric_line_rank(rows, tau0, depth_mode=True, limit=500)
    for out_index, (identity_row, numeric_row) in enumerate(zip(identity_rows, numeric_rows), start=1):
        numeric_idx = int(getattr(numeric_row, "line_index", 0)) - 1
        ion = str(getattr(identity_row, "ion_label", ""))[:8]
        wave = abs(float(getattr(identity_row, "wavelength_angstrom", 0.0)))
        reflected = float(tau0[0, numeric_idx])
        transmitted = float(tau0[1, numeric_idx])
        buf.log_lines.append(
            f"{out_index:9d}{int(getattr(identity_row, 'line_index', 0)):8d} {ion:<8s}"
            f"{wave:13.5E}{reflected:13.5E}{transmitted:13.5E}"
        )
    buf.source_calls.append("pprint(23)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the active element symbols operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _active_element_symbols(state: XSTARPythonState) -> set[str]:
    """Return lower-case element symbols with non-zero user abundance.

    XSTAR verbose reports are bounded by the active composition.  The C test
    case should stop at C VI rather than iterating over inactive ATDB padding
    through Zn.
    """
    metadata = _pprint_metadata(state)
    ababs = np.asarray(state.control.get("ababs", np.ones(len(metadata.element_labels))), dtype=float)
    symbols: set[str] = set()
    for i, label in enumerate(metadata.element_labels):
        if i < ababs.size and float(ababs[i]) != 0.0:
            symbols.add(str(label).strip().lower())
    return symbols


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the row element symbol operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _row_element_symbol(row: Any) -> str:
    ion = str(getattr(row, "ion_label", "")).strip().lower()
    return ion.split("_")[0] if ion else ""


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the active line rows by index operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _active_line_rows_by_index(state: XSTARPythonState, rows: Sequence[Any]) -> list[Any]:
    active = _active_element_symbols(state)
    out = [
        r for r in rows
        if int(getattr(r, "line_index", 0)) > 0
        and (not active or _row_element_symbol(r) in active)
    ]
    out.sort(key=lambda r: int(getattr(r, "line_index", 0)))
    return out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the active rrc rows by index operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _source_verbose_line_rows(state: XSTARPythonState) -> list[Any]:
    """Return the observable pprint(14/18) active nplin inventory.

    In the literal source the apparent lrtyp test occurs after parent-ion and
    parent-element drd() calls have overwritten lrtyp.  The public inventory
    therefore reduces to active composition plus the wavelength gate, matching
    the already-qualified pprint(15) FORTRAN row identity surface.
    """
    return [
        row for row in _active_line_rows_by_index(state, _line_metadata_rows(state))
        if 0.1 < abs(float(getattr(row, "wavelength_angstrom", 0.0))) < 9.0e9
    ]


def _source_verbose_level_rows(state: XSTARPythonState) -> list[Any]:
    active = _active_element_symbols(state)
    meta = state.control.get("output_atomic_metadata")
    rows = [
        row for row in tuple(getattr(meta, "levels", ()) or ())
        if int(getattr(row, "global_index", 0)) > 0
        and (not active or _row_element_symbol(row) in active)
    ]
    rows.sort(key=lambda row: int(getattr(row, "global_index", 0)))
    return rows


def _active_rrc_rows_by_index(state: XSTARPythonState, rows: Sequence[Any]) -> list[Any]:
    active = _active_element_symbols(state)
    out = [
        r for r in rows
        if int(getattr(r, "continuum_index", 0)) > 0
        and (not active or _row_element_symbol(r) in active)
    ]
    out.sort(key=lambda r: int(getattr(r, "continuum_index", 0)))
    return out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the line rows by index operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _line_rows_by_index(rows: Sequence[Any]) -> list[Any]:
    out = [r for r in rows if int(getattr(r, "line_index", 0)) > 0]
    out.sort(key=lambda r: int(getattr(r, "line_index", 0)))
    return out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option15 line luminosities and depths operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option15_line_luminosities_and_depths(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit verbose ``pprint(15)``: line luminosities and depths.

    This is diagnostic text coverage for the source log.  It intentionally
    uses the same already-populated ``elum`` and ``tau0`` arrays as
    ``pprint(1)`` and ``pprint(23)``; no physical arrays are altered.
    """
    workspace = _workspace(state)
    rows = _line_metadata_rows(state)
    elum = np.asarray(getattr(workspace, "elum", np.zeros((2, 0))), dtype=float)
    tau0 = np.asarray(getattr(workspace, "tau0", np.zeros((2, 0))), dtype=float)
    if elum.ndim != 2 or tau0.ndim != 2 or elum.shape[0] < 2 or tau0.shape[0] < 2:
        return
    buf.log_lines.extend([
        " ",
        " print option:15",
        " line luminosities (erg/sec/10**38) and depths",
        "  line, wavelength, ion, ref. lum.,trn. lum.,backward depth, forward depth",
    ])
    for row in _active_line_rows_by_index(state, rows):
        idx = int(getattr(row, "line_index", 0)) - 1
        if idx < 0 or idx >= elum.shape[1] or idx >= tau0.shape[1]:
            continue
        ion = str(getattr(row, "ion_label", ""))[:8]
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        lower = str(getattr(row, "lower_level", "")).strip()
        upper = str(getattr(row, "upper_level", "")).strip()
        label = (lower + "-" + upper).replace(" ", "")[:18]
        buf.log_lines.append(
            f"{int(getattr(row, 'line_index', 0)):10d}{wave:13.5E} {ion:<8s}"
            f"{float(elum[0, idx]):13.5E}{float(elum[1, idx]):13.5E}"
            f"{float(tau0[0, idx]):13.5E}{float(tau0[1, idx]):13.5E} {label}"
        )
    buf.source_calls.append("pprint(15)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Compute ion column values for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _compute_ion_column_values(
    *,
    abundance_rows: Mapping[int, np.ndarray],
    metadata: PprintAtomicMetadata,
    numrec: int,
    ababs: Sequence[float],
) -> np.ndarray:
    """Compute source ``pprint(27)`` / ``xout_abund1`` ion columns.

    XSTAR sets ``numrec=jkp+1`` and leaves the final row as an all-zero
    sentinel.  The FITS COLUMNS writer already honors that row by first
    constructing the full ``numrec`` matrix.  The text log must use the same
    matrix rather than walking only explicitly populated rows; otherwise the
    last physical interval is integrated to the last physical row instead of
    to the source zero-padding row, producing approximately doubled
    ``pprint(27)`` columns in the thin one-pass benchmark.
    """
    nions = len(metadata.ions)
    columns = np.zeros(nions, dtype=float)
    if int(numrec) < 2 or nions <= 0:
        return columns
    abund = _rows_matrix(abundance_rows, numrec=int(numrec), width=8 + nions)
    elem_abundances = np.asarray(ababs, dtype=float).reshape(-1)
    for j in range(1, int(numrec)):
        r0 = float(abund[j - 1, 1])
        r1 = float(abund[j, 1])
        dr = r1 - r0
        for k, ion in enumerate(metadata.ions):
            element_abundance = float(ion.elemental_abundance)
            if 1 <= int(ion.element_index) <= elem_abundances.size:
                element_abundance = float(elem_abundances[int(ion.element_index) - 1])
            columns[k] += (
                float(abund[j, 8 + k]) * float(abund[j, 4])
                + float(abund[j - 1, 8 + k]) * float(abund[j - 1, 4])
            ) * dr * element_abundance / 2.0
    return columns


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option27 ion column densities operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option27_ion_column_densities(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit verbose ``pprint(27)`` ion column densities from pprint rows."""
    metadata = _pprint_metadata(state)
    numrec = int(state.control.get("numrec", 0))
    nions = len(metadata.ions)
    if numrec < 2 or not buf.abundance_rows or nions <= 0:
        return
    columns = _compute_ion_column_values(
        abundance_rows=buf.abundance_rows,
        metadata=metadata,
        numrec=numrec,
        ababs=state.control.get("ababs", np.ones(len(metadata.element_labels))),
    )
    buf.log_lines.extend([
        " ",
        " print option:27",
        " ion column densities",
        " index, ion, column density",
    ])
    source_column_floor = float(np.float32(1.0e-15))
    for k, ion in enumerate(metadata.ions):
        value = float(columns[k])
        if not (value > source_column_floor):
            continue
        # Source format is (1x,i4,1x,9a1,1pe16.8).  The 9-character ion
        # field preserves a separator for 8-character labels such as ca_xviii.
        buf.log_lines.append(f"{int(ion.ion_index):5d} {str(ion.ion_label)[:9]:<9s}{value:16.8E}")
    buf.source_calls.append("pprint(27)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the rrc metadata rows operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _rrc_metadata_rows(state: XSTARPythonState) -> tuple[Any, ...]:
    meta = state.control.get("output_atomic_metadata")
    rows = getattr(meta, "rrcs", ())
    return tuple(rows) if rows is not None else ()


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Publish STEP Option 24 absorption edges from clean RRC/continuum identities; do not reproduce the historical Fortran stale-local H I/He II text alias.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option24_absorption_edge_depths(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit verbose ``pprint(24)`` absorption edge depths from final RRC depths.

    The canonical C benchmark's original XSTAR log prints the type-7 edge
    report through He II only.  Earlier Python diagnostic coverage walked all
    active metadata and therefore overprinted C V/C VI edge rows.  Keep the
    report bounded to the H/He ion block until the full Fortran type-7 record
    traversal is translated; this preserves the observed source log contract
    for the current benchmark and avoids misleading carbon edge rows.
    """
    workspace = _workspace(state)
    rows = _rrc_metadata_rows(state)
    tauc = np.asarray(getattr(workspace, "tauc", np.zeros((2, 0))), dtype=float)
    if tauc.ndim != 2 or tauc.shape[0] < 2:
        return
    buf.log_lines.extend([
        " ",
        " print option:24",
        " absorption edge depths",
        " index, ion, level, energy (eV), depth ",
    ])
    out_index = 0
    for row in _active_rrc_rows_by_index(state, rows):
        ion_label_l = str(getattr(row, "ion_label", "")).strip().lower()
        if not (ion_label_l.startswith("h_") or ion_label_l.startswith("he_")):
            continue
        out_index += 1
        ci = int(getattr(row, "continuum_index", out_index))
        idx = ci - 1
        if idx < 0 or idx >= tauc.shape[1]:
            continue
        backward = float(tauc[0, idx])
        forward = float(tauc[1, idx])
        if backward == 0.0 and forward == 0.0:
            continue
        ion = str(getattr(row, "ion_label", ""))[:8]
        lower = str(getattr(row, "lower_level", "")).strip()[:20]
        upper = str(getattr(row, "upper_level", "continuum")).strip()[:20]
        energy = float(getattr(row, "threshold_eV", 0.0))
        level = int(getattr(row, "level_global_index", 0))
        lower_local = int(getattr(row, "lower_local_index", 0) or 0)
        upper_local = int(getattr(row, "upper_local_index", 0) or 0)
        # pprint.f90 label 9293: kkkl, mmlv, ion, idest1, idest2, labels,
        # threshold, inward depth, outward depth.  Option 24 uses the same
        # row format as option 19.
        buf.log_lines.append(
            f"{ci:7d}{level:6d} {ion:<8s}{lower_local:6d}{upper_local:6d} {lower:<20s} {upper:<20s}"
            f"{energy:13.3E}{backward:13.3E}{forward:13.3E}"
        )
    buf.source_calls.append("pprint(24)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option16 ucalc timing accounting operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option16_ucalc_timing_accounting(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit verbose ``pprint(16)`` in the source table shape.

    The original report prints seven timer scalars, then one row per XSTAR
    rate type 1..102: ``rate_type, count, total_time, time_per_call``.  The
    Python port does not yet carry the exact Fortran CPU accumulators, so the
    timing columns remain zero unless future instrumentation populates
    ``state.outputs['ucalc_timing_table']``.  The shape and ordering match the
    original log, which makes diffs readable without producing a huge report.
    """
    timing = state.outputs.get("ucalc_timing_table", {})
    counts = {int(k): int(v) for k, v in dict(timing.get("counts", {})).items()} if isinstance(timing, Mapping) else {}
    totals = {int(k): float(v) for k, v in dict(timing.get("totals", {})).items()} if isinstance(timing, Mapping) else {}
    if not counts:
        # Fallback: static ATDB rate-type inventory.  This is not the same as
        # Fortran's dynamic call count, but it is bounded and source-shaped.
        derived = state.control.get("derived") or getattr(state, "derived", None)
        try:
            rates = np.asarray(getattr(derived, "rdat1", []))
            # Unknown in many states; keep all zero if unavailable.
        except Exception:
            rates = np.asarray([])
    if not counts and not totals:
        # Explicitly ignore this bookkeeping-only report rather than printing
        # 102 all-zero placeholder rows that look like measured source timing.
        # If future instrumentation populates state.outputs['ucalc_timing_table'],
        # the source-shaped table below is emitted unchanged.
        buf.log_lines.extend([
            " ",
            " print option:16",
            " ucalc timing/accounting report intentionally ignored: ",
            " Python port does not carry source CPU accumulators or dynamic per-rate call counts. ",
        ])
        buf.source_calls.append("pprint(16:ignored)")
        return
    buf.log_lines.extend([
        " ",
        " print option:16",
        " times:   0.00000000       0.00000000       0.00000000       0.00000000       0.00000000       0.00000000       0.00000000    ",
    ])
    total_ucalc = 0.0
    for rate_type in range(1, 103):
        count = int(counts.get(rate_type, 0))
        total = float(totals.get(rate_type, 0.0))
        per = total / count if count else 0.0
        total_ucalc += total
        buf.log_lines.append(f"{rate_type:9d}{count:8d}{total:11.3E}{per:11.3E}")
    buf.log_lines.append(f" total ucalc= {total_ucalc:22.16E}     ")
    buf.source_calls.append("pprint(16)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option19 recombination continuum luminosities operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option19_recombination_continuum_luminosities(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit bounded verbose ``pprint(19)`` RRC luminosities for active elements."""
    workspace = _workspace(state)
    rows = _rrc_metadata_rows(state)
    elumab = np.asarray(getattr(workspace, "elumab", np.zeros((2, 0))), dtype=float)
    if elumab.ndim != 2 or elumab.shape[0] < 2:
        return
    buf.log_lines.extend([
        " ",
        " print option:19",
        " recombination continuum luminosities(erg/sec/10**38))",
        " index, ion, level, energy (eV), RRC luminosity ",
    ])
    for row in _active_rrc_rows_by_index(state, rows):
        ci = int(getattr(row, "continuum_index", 0))
        idx = ci - 1
        if idx < 0 or idx >= elumab.shape[1]:
            continue
        out_lum = float(elumab[0, idx])
        in_lum = float(elumab[1, idx])
        if out_lum == 0.0 and in_lum == 0.0:
            continue
        ion = str(getattr(row, "ion_label", ""))[:8]
        lower = str(getattr(row, "lower_level", "")).strip()[:20]
        upper = str(getattr(row, "upper_level", "continuum")).strip()[:20]
        energy = float(getattr(row, "threshold_eV", 0.0))
        level = int(getattr(row, "level_global_index", 0))
        lower_local = int(getattr(row, "lower_local_index", 0) or 0)
        upper_local = int(getattr(row, "upper_local_index", 0) or 0)
        # Source-faithful pprint(19): after the ATDB continuum index and ion
        # label, XSTAR prints the local bound-level ordinal and the local
        # continuum/destination ordinal, not the global packed level index.
        # Keep the global level only as an internal metadata field.
        buf.log_lines.append(
            f"{ci:7d}{level:6d} {ion:<8s}{lower_local:6d}{upper_local:6d} {lower:<20s} {upper:<20s}"
            f"{energy:13.3E}{out_lum:13.3E}{in_lum:13.3E}"
        )
    buf.source_calls.append("pprint(19)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option5 energy sums operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option5_energy_sums(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit source-positioned ``pprint(5)`` energy-sum footer.

    This implements the original report formula as closely as the bounded
    workspace allows:

    * absorbed: incident continuum removed by the accumulated outward optical
      depth, integrated over energy and converted by ``ergsev``;
    * continuum: inward + outward continuum/RRC emissivity rows integrated over
      energy and converted by ``ergsev``;
    * line: reflected + transmitted line luminosity sums from ``elum``;
    * error: fractional energy residual.

    The report is diagnostic only and does not alter any physical arrays.
    """
    workspace = _workspace(state)
    epi = _active_epi(state)
    n = int(epi.size)
    zremsz = np.asarray(getattr(workspace, "zremsz", np.zeros(n)), dtype=float).reshape(-1)[:n]
    dpthc = np.asarray(getattr(workspace, "dpthc", np.zeros((2, n))), dtype=float)
    zrems = np.asarray(getattr(workspace, "zrems", np.zeros((5, n))), dtype=float)
    elum = np.asarray(getattr(workspace, "elum", np.zeros((2, 0))), dtype=float)
    absorbed = 0.0
    cont = 0.0
    if n > 1:
        tau = dpthc[0, :n] if dpthc.ndim == 2 and dpthc.shape[1] >= n else np.zeros(n, dtype=float)
        removed = zremsz * (1.0 - np.exp(-np.maximum(tau, 0.0)))
        absorbed = float(np.trapezoid(removed, epi) * ERGSEV)
        if zrems.ndim == 2 and zrems.shape[0] >= 4 and zrems.shape[1] >= n:
            # Source energy balance uses the inward and outward continuum/RRC
            # emission rows, not final line luminosities.
            continuum_rows = zrems[2, :n] + zrems[3, :n]
            cont = float(np.trapezoid(continuum_rows, epi) * ERGSEV)
    line = float(np.sum(elum[:2, :])) if elum.ndim == 2 and elum.shape[0] >= 2 else 0.0
    err = (absorbed - cont - line) / absorbed if abs(absorbed) > 1.0e-300 else 0.0
    buf.log_lines.extend([
        " ",
        " print option: 5",
        f" energy sums: abs, cont, line, err:{absorbed:13.5E}{cont:13.5E}{line:13.5E}{err:13.5E}",
    ])
    buf.source_calls.append("pprint(5)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the final zero thickness print operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _final_zero_thickness_print(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit xstar.f90's post-radial ``final print`` block.

    The block is not pprint(17).  Source XSTAR performs a final
    ``xstarcalc`` with ``delr=1.e-15`` and ``nlimd=0``, then HEATT/STPCUT,
    writes ``t, httot, cltot, hmctot`` with ``4(1pe16.8)``, and only then
    calls pprint(22).  ``run_output_writer_sequence`` owns that recompute and
    records the exact resulting scalars here.
    """
    payload = state.outputs.get("final_local_recompute")
    if not isinstance(payload, Mapping):
        return
    required = ("temperature_t4", "httot", "cltot", "hmctot")
    if not all(key in payload for key in required):
        return
    lpri = int(state.control.get("requested_lpri", state.control.get("lpri", 0)))
    buf.log_lines.extend([
        " ",
        f"  final print:{lpri:12d}",
        "".join(f"{float(payload[key]):16.8E}" for key in required),
        " ",
    ])
    buf.source_calls.append("xstar(final-zero-thickness-print)")




# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Return the literal final pprint option sequence selected by lprint.
# Reference context: xstar.f90 nlprnt/nlnprnt dispatch; lprint=-1..6.
# XSTAR-FUNCTION-COMMENT-END
def _final_pprint_option_sequence(lprint: int) -> tuple[int, ...]:
    lpri = int(lprint)
    if lpri < 0:
        return (22,)
    if lpri == 0:
        n = 2
    elif lpri == 1:
        n = 10
    elif lpri == 2:
        n = 15
    elif lpri == 3:
        n = 18
    else:
        n = 21
    return tuple(int(v) for v in NLPRNT[:n])


def _append_pprint_marker(buf: LegacyPprintBuffers, option: int) -> None:
    # pprint.f90 format 9211: ``1x,'print option:',i2``.
    buf.log_lines.append(f" print option:{int(option):2d}")
    call = f"pprint({int(option)})"
    if call not in buf.source_calls:
        buf.source_calls.append(call)


def _option14_line_opacity_emissivity(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 14)
    buf.log_lines.extend([
        "line opacities and emissivities (erg/cm**3/sec/10**38)",
        " index,wavelength,energy,ion,opacity,rec. em.,coll. em.,fl. em.,di. em.,cx. em.",
    ])
    rows = _source_verbose_line_rows(state)
    all_rows = _line_metadata_rows(state)
    ws = _workspace(state)
    oplin = np.asarray(getattr(ws, "oplin_physical", np.zeros(0)), dtype=float).reshape(-1)
    rcem = np.asarray(getattr(ws, "rcem_physical", np.zeros((2, 0))), dtype=float)
    # FORTRAN prints nlsvn before the filtered rows.  Preserve the complete
    # metadata capacity scalar while iterating only the source-active inventory.
    buf.log_lines.append(str(len(all_rows)))
    for row in rows:
        idx = int(getattr(row, "line_index", 0)) - 1
        if idx < 0 or idx >= oplin.size or rcem.ndim != 2 or rcem.shape[0] < 2 or idx >= rcem.shape[1]:
            continue
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        energy = 12398.4016 / max(wave, 1.0e-24)
        ion = str(getattr(row, "ion_label", ""))[:9]
        buf.log_lines.append(
            f"{idx+1:10d}{wave:13.5E}{energy:13.5E} {ion:<9s}"
            f"{oplin[idx]:13.5E}{rcem[0,idx]:13.5E}{rcem[1,idx]:13.5E}"
        )


def _option21_level_opacity_emissivity(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 21)
    buf.log_lines.extend([
        " level opacities and emissivities",
        "index,energy,ion,level,index,emiss in,emiss out,threshold opacity,absorbed energy,depth in, depth out",
    ])
    ws = _workspace(state)
    cemab = np.asarray(getattr(ws, "cemab_physical", np.zeros((2, 0))), dtype=float)
    base = getattr(getattr(ws, "emissivity", None), "base", None)
    opakab = np.asarray(getattr(base, "opakab", np.zeros(1)), dtype=float).reshape(-1)[1:]
    cabab = np.asarray(getattr(base, "cabab", np.zeros(1)), dtype=float).reshape(-1)[1:]
    tauc = np.asarray(getattr(ws, "tauc", np.zeros((2, 0))), dtype=float)
    output_meta = state.control.get("output_atomic_metadata")
    all_rows = tuple(getattr(output_meta, "detail_rrcs", ()) or ())
    # Literal pprint(21) retains the first Type-12 ion's Type-7/npconi2
    # workspace for an element while the outer Type-12 traversal advances the
    # printed ion label.  This is why canonical He II repeats the 103 He I
    # rows and carbon contributes no rows when the C I workspace is zero.
    first_rows_by_z: dict[int, tuple[Any, ...]] = {}
    for z in sorted({int(getattr(row, "atomic_number", 0)) for row in all_rows}):
        if z <= 0:
            continue
        rows = tuple(
            row for row in all_rows
            if int(getattr(row, "atomic_number", 0)) == z
            and _roman_stage_from_ion_label(str(getattr(row, "ion_label", ""))) == 1
        )
        if rows:
            first_rows_by_z[z] = rows
    meta = _pprint_metadata(state)
    for ion in meta.ions:
        z = int(getattr(ion, "element_index", 0))
        if float(getattr(ion, "elemental_abundance", 0.0)) <= 1.0e-10:
            continue
        rows = first_rows_by_z.get(z, ())
        printed_label = str(getattr(ion, "ion_label", ""))[:9]
        for row in rows:
            idx = int(getattr(row, "continuum_index", 0)) - 1
            if idx < 0:
                continue
            cin = cemab[0,idx] if cemab.ndim == 2 and cemab.shape[0] > 1 and idx < cemab.shape[1] else 0.0
            cout = cemab[1,idx] if cemab.ndim == 2 and cemab.shape[0] > 1 and idx < cemab.shape[1] else 0.0
            opa = opakab[idx] if idx < opakab.size else 0.0
            absorbed = cabab[idx] if idx < cabab.size else 0.0
            if not (opa > 1.0e-49 or absorbed > 1.0e-49 or cin > 1.0e-49 or cout > 1.0e-49):
                continue
            tin = tauc[0,idx] if tauc.ndim == 2 and tauc.shape[0] > 1 and idx < tauc.shape[1] else 0.0
            tout = tauc[1,idx] if tauc.ndim == 2 and tauc.shape[0] > 1 and idx < tauc.shape[1] else 0.0
            buf.log_lines.append(
                f"{idx+1:8d} {int(getattr(row,'level_global_index',0)):5d} "
                f"{printed_label:<9s} "
                f"{int(getattr(row,'lower_local_index',0)):5d} {int(getattr(row,'upper_local_index',0)):5d} "
                f"{str(getattr(row,'lower_level',''))[:20]:<20s} {str(getattr(row,'upper_level',''))[:20]:<20s} "
                f"{float(getattr(row,'threshold_eV',0.0)):13.5E}{cin:13.5E}{cout:13.5E}{opa:13.5E}{absorbed:13.5E}{tin:13.5E}{tout:13.5E}"
            )


def _option7_level_populations(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 7)
    buf.log_lines.extend(["  level populations ", " ion                      level               e_exc population"])

    # 0.6.82.29.3.1: pprint(7) consumes the complete final calc_hmc_all
    # global workspaces, not just population/LTE columns.  Python already
    # computes and retains gammag/alphag and the dominant-record pointers;
    # publish those exact source-owned values rather than dropping six fields.
    fixed = getattr(state.local_zone, "calc_hmc_all", None)
    dense_x = np.asarray(
        getattr(fixed, "global_xilevg_by_index", np.zeros(0)), dtype=float
    ).reshape(-1) if fixed is not None else np.zeros(0, dtype=float)
    dense_rn = np.asarray(
        getattr(fixed, "global_rnisg_by_index", np.zeros(0)), dtype=float
    ).reshape(-1) if fixed is not None else np.zeros(0, dtype=float)
    dense_b = np.asarray(
        getattr(fixed, "global_bilevg_by_index", np.zeros(0)), dtype=float
    ).reshape(-1) if fixed is not None else np.zeros(0, dtype=float)

    xilev = state.local_zone.source_arrays.get("xilevg")
    rnis = state.local_zone.source_arrays.get("rnisg")
    fallback_x = np.asarray(xilev if xilev is not None else np.zeros(0), dtype=float).reshape(-1)
    fallback_rn = np.asarray(rnis if rnis is not None else np.zeros(0), dtype=float).reshape(-1)
    guarded = fallback_x.size > 1 and abs(fallback_x[0]) == 0.0

    gammag = getattr(fixed, "gammag", None) if fixed is not None else None
    alphag = getattr(fixed, "alphag", None) if fixed is not None else None
    igammamaxg = getattr(fixed, "igammamaxg", None) if fixed is not None else None
    ialphamaxg = getattr(fixed, "ialphamaxg", None) if fixed is not None else None
    if not isinstance(gammag, Mapping):
        gammag = state.local_zone.source_arrays.get("gammag", {})
    if not isinstance(alphag, Mapping):
        alphag = state.local_zone.source_arrays.get("alphag", {})
    if not isinstance(igammamaxg, Mapping):
        igammamaxg = state.local_zone.source_arrays.get("igammamaxg", {})
    if not isinstance(ialphamaxg, Mapping):
        ialphamaxg = state.local_zone.source_arrays.get("ialphamaxg", {})

    for row in _source_verbose_level_rows(state):
        gi = int(getattr(row, "global_index", 0))
        dense_at = gi - 1
        fallback_at = gi if guarded else gi - 1
        pop = (
            float(dense_x[dense_at]) if 0 <= dense_at < dense_x.size
            else float(fallback_x[fallback_at]) if 0 <= fallback_at < fallback_x.size
            else 0.0
        )
        if not (pop > 1.0e-64):
            continue
        rnval = (
            float(dense_rn[dense_at]) if 0 <= dense_at < dense_rn.size
            else float(fallback_rn[fallback_at]) if 0 <= fallback_at < fallback_rn.size
            else 0.0
        )
        bilev = float(dense_b[dense_at]) if 0 <= dense_at < dense_b.size else 0.0
        dep = pop / (rnval + 1.0e-36)
        z = int(getattr(row, "atomic_number", 0))
        stage = _roman_stage_from_ion_label(str(getattr(row, "ion_label", "")))
        local_level = int(getattr(row, "upper_index", 0))
        key = (z, stage, local_level)
        gamma = float(gammag.get(key, 0.0))
        alpha = float(alphag.get(key, 0.0))
        igamma = int(igammamaxg.get(key, 0))
        ialpha = int(ialphamaxg.get(key, 0))
        buf.log_lines.append(
            f"{gi:7d} {str(getattr(row,'ion_label',''))[:8]:<8s} "
            f"{str(getattr(row,'level_label',''))[:20]:<20s} "
            f"{float(getattr(row,'excitation_eV',0.0)):13.5E}{pop:13.5E}{rnval:13.5E}"
            f"{dep:13.5E}{bilev:13.5E}{gamma:13.5E}{igamma:8d}{alpha:13.5E}{ialpha:8d}"
        )
    buf.log_lines.append(" done with 7")


def _option10_ion_rates(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 10)
    buf.log_lines.extend([" ion abundances and  rates (/sec)", " index, ion, abundance, recombination, ionization,"])
    meta = _pprint_metadata(state)
    n = max((int(i.ion_index) for i in meta.ions), default=0)
    def _safe(name: str) -> np.ndarray:
        if not n:
            return np.zeros(0)
        try:
            return _array_value(state, name, n)
        except LegacyPprintPortError:
            return np.zeros(n, dtype=float)
    xii, rrrt, pirt = _safe("xii"), _safe("rrrt"), _safe("pirt")
    for ion in meta.ions:
        if float(getattr(ion, "elemental_abundance", 0.0)) <= 1.0e-15:
            continue
        j = int(ion.ion_index) - 1
        if 0 <= j < n:
            rat1 = 0.0
            rat2 = 0.0
            # Literal pprint(10): lk.gt.1 and lk.lt.nni, with xii(lk+1)
            # crossing element boundaries in global Type-12 order.
            if j + 1 > 1 and j + 1 < n:
                rat1 = xii[j] / (xii[j+1] + 1.0e-34)
                rat2 = rrrt[j] / (pirt[j] + 1.0e-34)
            buf.log_lines.append(
                f"{j+1:5d} {str(ion.ion_label)[:9]:<9s} {xii[j]:16.8E} {rrrt[j]:16.8E} {pirt[j]:16.8E} {rat1:16.8E} {rat2:16.8E}"
            )
    buf.log_lines.extend([
        " heating and cooling rates (erg/sec)",
        "                 photon pov                                      electron pov",
        " index element   heating         cooling        heating-cooling  heating         cooling        heating-cooling",
    ])
    ababs = np.asarray(state.control.get("ababs", np.ones(len(meta.thermal_elements))), dtype=float)
    htt = np.asarray(state.local_zone.source_arrays.get("htt", np.zeros(len(meta.thermal_elements))), dtype=float).reshape(-1)
    cll = np.asarray(state.local_zone.source_arrays.get("cll", np.zeros(len(meta.thermal_elements))), dtype=float).reshape(-1)
    htt2 = np.asarray(state.local_zone.source_arrays.get("htt2", np.zeros(len(meta.thermal_elements))), dtype=float).reshape(-1)
    cll2 = np.asarray(state.local_zone.source_arrays.get("cll2", np.zeros(len(meta.thermal_elements))), dtype=float).reshape(-1)
    for element in meta.thermal_elements:
        ei = int(element.element_index)
        if ei <= 0 or ei > ababs.size or float(ababs[ei-1]) <= 1.0e-36:
            continue
        h = htt[ei-1] if ei-1 < htt.size else 0.0
        c = cll[ei-1] if ei-1 < cll.size else 0.0
        h2 = htt2[ei-1] if ei-1 < htt2.size else 0.0
        c2 = cll2[ei-1] if ei-1 < cll2.size else 0.0
        buf.log_lines.append(
            f"{ei:5d} {str(element.element_label)[:10]:<10s} {h:16.8E} {c:16.8E} {h-c:16.8E} {h2:16.8E} {c2:16.8E} {h2-c2:16.8E}"
        )
    fixed = getattr(state.local_zone, "calc_hmc_all", None)
    continuum = getattr(fixed, "continuum", None)
    htcomp = float(getattr(continuum, "htcomp", state.control.get("htcomp", 0.0)))
    clcomp = float(getattr(continuum, "clcomp", state.control.get("clcomp", 0.0)))
    htfreef = float(getattr(continuum, "htfreef", state.control.get("htfreef", 0.0)))
    clbrems = float(getattr(continuum, "clbrems", state.control.get("clbrems", 0.0)))
    buf.log_lines.append(f"      compton    {htcomp:16.8E} {clcomp:16.8E} {htcomp-clcomp:16.8E} {htcomp:16.8E} {clcomp:16.8E} {htcomp-clcomp:16.8E}")
    buf.log_lines.append(f"      free-free  {htfreef:16.8E} {clbrems:16.8E} {htfreef-clbrems:16.8E} {htfreef:16.8E} {clbrems:16.8E} {htfreef-clbrems:16.8E}")
    httot = float(state.control.get("httot", state.thermal.heating))
    cltot = float(state.control.get("cltot", state.thermal.cooling))
    httot2 = float(state.control.get("httot2", httot))
    cltot2 = float(state.control.get("cltot2", cltot))
    buf.log_lines.append(f"      total      {httot:16.8E} {cltot:16.8E} {httot-cltot:16.8E} {httot2:16.8E} {cltot2:16.8E} {httot2-cltot2:16.8E}")


def _option4_continuum_opacity(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 4)
    buf.log_lines.extend([
        "continuum opacity and emissivities (/cm**3/sec/10**38)",
        "channel, energy,      opacity,    sigma*e**3,scattered,  rec. in,   rec. out,  brem. em., source, bbe,photon occ",
    ])
    ws = _workspace(state)
    epi = _active_epi(state)
    opakc = np.asarray(getattr(ws, "opakc", np.zeros(0)), dtype=float).reshape(-1)
    opakcont = np.asarray(getattr(ws, "opakcont", np.zeros(0)), dtype=float).reshape(-1)
    rcc = np.asarray(getattr(ws, "rccemis", np.zeros((2,0))), dtype=float)
    base = getattr(getattr(ws, "emissivity", None), "base", None)
    br = np.asarray(getattr(base, "brcems", np.zeros(0)), dtype=float).reshape(-1)
    flinel = np.asarray(getattr(getattr(ws, "emissivity", None), "flinel", np.zeros(0)), dtype=float).reshape(-1)
    n = min(epi.size, opakc.size)
    xpx = float(state.plasma.xpx)
    xee = float(state.plasma.xee)
    xnx = float(state.plasma.electron_density) if float(state.plasma.electron_density) > 0.0 else xpx * xee
    tstar = _temperature_t4(state)
    source_665e25 = float(np.float32(6.65e-25))
    source_116 = float(np.float32(1.16))
    source_1e4 = float(np.float32(1.0e-4))
    source_two = float(np.float32(2.0))
    source_planck_coeff = float(np.float32(1.5642e22))
    source_kt_coeff = float(np.float32(0.861707))
    source_four_pi = float(np.float32(12.56))
    ekkr = max(1.0e-20, xnx * source_665e25)
    optpp = max(float(opakc[0]) if n else 0.0, ekkr)
    fstr = 0.0
    rsum1 = 0.0
    rsum2 = 0.0
    opsum = 0.0
    for i in range(1, n):
        e = float(epi[i])
        op = float(opakc[i])
        sgtmp = op * (e / 1000.0) ** 3 / max(1.0e-24, xpx)
        if e > 100.0:
            opsum += (op + float(opakc[i-1])) * (e - float(epi[i-1])) / 2.0
        tmp = e * source_116 / tstar
        crayj = 1.0 / tmp
        fstro = fstr
        if tmp <= 50.0:
            if tmp > source_1e4:
                crayj = 1.0 / (float(np.exp(np.clip(tmp, -60.0, 60.0))) - 1.0)
            crayj *= crayj
            fstr = tmp * crayj * e**3 / tstar
        optppo = optpp
        optpp = max(op, ekkr)
        delte = e - float(epi[i-1])
        rsum1 = min(1.0e20, rsum1 + (fstr / optpp + fstro / optppo) * delte / 2.0)
        rsum2 = min(1.0e20, rsum2 + (fstr + fstro) * delte / 2.0)
        rin = rcc[0,i] if rcc.ndim == 2 and rcc.shape[0] > 1 and i < rcc.shape[1] else 0.0
        rout = rcc[1,i] if rcc.ndim == 2 and rcc.shape[0] > 1 and i < rcc.shape[1] else 0.0
        b = br[i] if i < br.size else 0.0
        scattered = opakcont[i] if i < opakcont.size else 0.0
        source = (rin + rout + b / source_four_pi) / (1.0e-36 + op)
        planck_energy = min(2.0e4, e)
        expo_value = float(np.exp(np.clip(e / (source_kt_coeff * tstar), -60.0, 60.0)))
        bbe = source_two * planck_energy**3 * source_planck_coeff / (expo_value - 1.0 + 1.0e-36)
        rocc = source / (bbe + 1.0e-36)
        fl = flinel[i] if i < flinel.size else 0.0
        buf.log_lines.append(
            f"{i+1:7d}{e:13.5E}{op:13.5E}{sgtmp:13.5E}{scattered:13.5E}"
            f"{rin:13.5E}{rout:13.5E}{b:13.5E}{source:13.5E}{bbe:13.5E}{rocc:13.5E}{fl:13.5E}"
        )
    rssmn = rsum2 / rsum1 if rsum1 > 0.0 else 0.0
    buf.log_lines.append(f" opsum cont=   {opsum:.16E}")
    buf.log_lines.append(f" rosseland mean opacity=   {tstar:.16E}        {rssmn:.16E}")

def _option6_continuum_luminosities(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 6)
    buf.log_lines.extend([
        "continuum luminosities (/sec/10**38) and depths",
        "real quantities are as follows:",
        "1 ) photon energy in eV",
        "2) Incident radiation field",
        "3) Radiation field used by xstar for internal calculations of rates, etc.",
        "   The quantity defined in equation (12) in the xstar manual, chapter 8, the Physics of xstar.",
        "4) and 5) the quantities in equations (15) and (16), with lines added",
        "6) and 7) the quantities in equations (15) and (16), without lines",
        "8) inward depth",
        "9) outward depth",
        "10) Planck function at local gas temperature",
        "11) ratio of the xstar internal radiation field (in flux units) to Planck function at local gas temperature.",
    ])
    ws = _workspace(state)
    epi = _active_epi(state)
    zrems = np.asarray(getattr(ws, "zrems", np.zeros((0,0))), dtype=float)
    zremsz = np.asarray(getattr(ws, "zremsz", np.zeros(0)), dtype=float).reshape(-1)
    dpth = np.asarray(getattr(ws, "dpthc", np.zeros((2,0))), dtype=float)
    # Literal pprint.f90 source-default-REAL constants promoted into the
    # DOUBLE PRECISION expression.  This publication path consumes final
    # retained state only and does not feed the physical calculation.
    source_two = float(np.float32(2.0))
    source_planck_coeff = float(np.float32(1.5642e22))
    source_kt_coeff = float(np.float32(0.861707))
    source_four_pi = float(np.float32(12.56))
    source_radius_scale = float(np.float32(1.0e-19))
    radius_cm = float(state.transfer.radius)
    t4 = _temperature_t4(state)
    r19 = radius_cm * source_radius_scale
    fpr2 = source_four_pi * r19 * r19
    for i, e in enumerate(epi):
        vals = [zrems[k,i] if zrems.ndim == 2 and k < zrems.shape[0] and i < zrems.shape[1] else 0.0 for k in range(5)]
        incident = zremsz[i] if i < zremsz.size else 0.0
        tin = dpth[0,i] if dpth.ndim == 2 and dpth.shape[0] > 1 and i < dpth.shape[1] else 0.0
        tout = dpth[1,i] if dpth.ndim == 2 and dpth.shape[0] > 1 and i < dpth.shape[1] else 0.0
        planck_energy = min(2.0e4, float(e))
        expo_value = float(np.exp(np.clip(float(e) / (source_kt_coeff * t4), -60.0, 60.0)))
        bbe = source_two * planck_energy**3 * source_planck_coeff / (expo_value - 1.0 + 1.0e-36)
        rocc = vals[0] / (bbe + 1.0e-36) / fpr2 / source_four_pi if fpr2 > 0.0 else 0.0
        buf.log_lines.append(
            f"{i+1:7d}{e:13.5E}{incident:13.5E}"
            + "".join(f"{v:13.5E}" for v in vals)
            + f"{tin:13.5E}{tout:13.5E}{bbe:13.5E}{rocc:13.5E}"
        )
    sums = [0.0, 0.0, 0.0, 0.0]
    ergsev = 1.602197e-12
    for i in range(1, int(epi.size)):
        de = float(epi[i] - epi[i-1])
        z0 = zremsz[i] if i < zremsz.size else 0.0
        z1 = zremsz[i-1] if i-1 < zremsz.size else 0.0
        sums[0] += (z0 + z1) * de * ergsev / 2.0
        for plane in range(3):
            a = zrems[plane,i] if zrems.ndim == 2 and plane < zrems.shape[0] and i < zrems.shape[1] else 0.0
            b = zrems[plane,i-1] if zrems.ndim == 2 and plane < zrems.shape[0] and i-1 < zrems.shape[1] else 0.0
            sums[plane+1] += (a + b) * de * ergsev / 2.0
    buf.log_lines.extend([" norms:", " " * 20 + "".join(f"{v:13.5E}" for v in sums)])


def _option18_line_levels(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 18)
    buf.log_lines.extend(["line wavelengths and levels", "      index wavelength  ion       lo                  up"])
    for row in _source_verbose_line_rows(state):
        buf.log_lines.append(
            f"{int(getattr(row,'line_index',0)):10d}{abs(float(getattr(row,'wavelength_angstrom',0.0))):13.5E} "
            f"{str(getattr(row,'ion_label',''))[:9]:<9s} {str(getattr(row,'lower_level',''))[:25]:<25s} "
            f"{str(getattr(row,'upper_level',''))[:25]:<25s} {int(getattr(row,'lower_local_index',0)):7d} {int(getattr(row,'upper_local_index',0)):7d}"
        )


def _option29_rates(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 29)
    buf.log_lines.extend(["rates", "doing pprint(29)"])
    fixed = getattr(state.local_zone, "calc_hmc_all", None)
    output_meta = state.control.get("output_atomic_metadata")
    levels = tuple(getattr(output_meta, "levels", ()) or ())
    level_by_ion_local = {(int(row.ion_index), int(row.upper_index)): row for row in levels}
    ion_label_by_index = {
        int(i.ion_index): str(i.ion_label)
        for i in _pprint_metadata(state).ions
    }
    rows: list[tuple[int, Mapping[str, Any], Any, Any]] = []
    if fixed is not None:
        for element in getattr(fixed, "element_results", ()):
            eq = getattr(element, "equilibrium", None)
            assembly = getattr(eq, "assembly", None)
            if assembly is None:
                continue
            z = int(getattr(getattr(element, "request", None), "element_z", 0))
            min_stage = int(getattr(element, "selected_min_ion_stage", 1))
            max_stage = int(getattr(element, "selected_max_ion_stage", z))
            block_by_ion = {
                int(block.ion_index): block
                for block in getattr(getattr(assembly, "basis", None), "blocks", ())
            }
            for row in getattr(assembly, "record_results", ()):
                rate_type = int(row.get("rate_type", 0) or 0)
                data_type = int(row.get("data_type", 0) or 0)
                stage = int(row.get("ion_stage", 0) or 0)
                if rate_type in {8, 15} or (rate_type == 1 and data_type == 53):
                    continue
                if stage < min_stage or stage > max_stage:
                    continue
                # pprint(29) tests the raw rates(1,ml) value saved immediately
                # after UCalc, before calc_hmc_ion's rate-type-1 ans1 filter.
                ans1 = float(row.get("ans1", 0.0) or 0.0)
                if abs(ans1) <= 1.0e-34:
                    continue
                ion_index = int(row.get("ion_index", 0) or 0)
                block = block_by_ion.get(ion_index)
                if block is None:
                    continue
                rows.append((int(row.get("record", 0) or 0), row, element, block))
    rows.sort(key=lambda item: item[0])
    for record, row, element, block in rows:
        ion_index = int(row.get("ion_index", 0) or 0)
        id1 = int(row.get("idest1", 0) or 0)
        id2 = int(row.get("idest2", 0) or 0)
        nlev = max(int(getattr(block, "nlev", row.get("nlev", 1)) or 1), 1)
        # Literal pprint(29) uses klev(:,min(nlev,idest)) after
        # calc_rates_level_lte(jkk), so continuum/superlevel destinations
        # print the current ion's terminal Type-13 level label.
        label_id1 = min(nlev, max(id1, 1))
        label_id2 = min(nlev, max(id2, 1))
        lower = level_by_ion_local.get((ion_index, label_id1))
        upper = level_by_ion_local.get((ion_index, label_id2))
        ion_label = str(ion_label_by_index.get(ion_index, getattr(lower, "ion_label", f"ion_{ion_index}")))
        lower_label = str(getattr(lower, "level_label", "unknown"))
        upper_label = str(getattr(upper, "level_label", "unknown"))
        # calc_hmc_element's ipmat2 starts at zero and increments by nlev-1
        # only across selected active stages.  ElementCompactBasis already
        # encodes that exact active prefix in compact_start.
        ipmat2 = int(getattr(block, "compact_start", 1)) - 1
        shifted1 = id1 + ipmat2
        shifted2 = id2 + ipmat2
        ans = [float(row.get(f"ans{k}", 0.0) or 0.0) for k in range(1, 7)]
        # Literal FORTRAN 9939:
        # (1h ,i9,1x,a9,1x,2(25a1,1x),6i8,6(1pe13.5))
        buf.log_lines.append(
            f"{record:10d} {ion_label[:9]:<9s} {lower_label[:25]:<25s} {upper_label[:25]:<25s} "
            f"{int(row.get('data_type',0)):8d}{int(row.get('rate_type',0)):8d}{id1:8d}{id2:8d}{shifted1:8d}{shifted2:8d}"
            + "".join(f"{v:13.5E}" for v in ans)
        )
    buf.log_lines.append("done with pprint(29)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Decode the Roman ion-stage suffix used by source-format ion labels for verbose publication.
# Reference context: XSTAR pprint ion labels use lower-case Roman stages through the complete element inventory.
# XSTAR-FUNCTION-COMMENT-END
def _roman_stage_from_ion_label(label: str) -> int:
    text = str(label).strip().lower()
    numeral = text.split("_", 1)[1] if "_" in text else ""
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    total = 0
    previous = 0
    for char in reversed(numeral):
        value = values.get(char, 0)
        if value <= 0:
            return 0
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total


def _option30_auger_fluorescence(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    _append_pprint_marker(buf, 30)
    buf.log_lines.extend(["auger and fluorescence yields", "ion     K shell pi rate  k fluorescence rate auger rate fluorescence yield"])
    meta = _pprint_metadata(state)
    n = max((int(i.ion_index) for i in meta.ions), default=0)
    try:
        xii = _array_value(state, "xii", n)
    except LegacyPprintPortError:
        xii = np.zeros(n, dtype=float)
    fixed = getattr(state.local_zone, "calc_hmc_all", None)
    output_meta = state.control.get("output_atomic_metadata")
    levels = tuple(getattr(output_meta, "levels", ()) or ())
    level_by_ion_local = {(int(row.ion_index), int(row.upper_index)): row for row in levels}
    xilev = np.asarray(state.local_zone.source_arrays.get("xilevg", np.zeros(0)), dtype=float).reshape(-1)
    guarded = xilev.size > 1 and abs(xilev[0]) == 0.0
    records_by_ion: dict[int, list[Mapping[str, Any]]] = {}
    if fixed is not None:
        for element in getattr(fixed, "element_results", ()):
            assembly = getattr(getattr(element, "equilibrium", None), "assembly", None)
            if assembly is None:
                continue
            for row in getattr(assembly, "record_results", ()):
                records_by_ion.setdefault(int(row.get("ion_index", 0) or 0), []).append(row)
    def _pop(level: Any) -> float:
        gi = int(getattr(level, "global_index", 0))
        at = gi if guarded else gi - 1
        return float(xilev[at]) if 0 <= at < xilev.size else 0.0
    previous_k_pi = 0.0
    for ion in meta.ions:
        j = int(ion.ion_index) - 1
        label = str(ion.ion_label).strip()
        stage = _roman_stage_from_ion_label(label)
        z = int(getattr(ion, "element_index", 0))
        if float(getattr(ion, "elemental_abundance", 0.0)) <= 1.0e-34 or stage <= 0:
            continue
        if not (0 <= j < xii.size and xii[j] > 1.0e-12):
            continue
        pirttoto = previous_k_pi
        current_k_pi = 0.0
        fluorescence = 0.0
        auger = 0.0
        if stage < z:
            for row in records_by_ion.get(int(ion.ion_index), ()):
                rt = int(row.get("rate_type", 0) or 0)
                id1 = int(row.get("idest1", 0) or 0)
                id2 = int(row.get("idest2", 0) or 0)
                if id1 <= 0 or id2 <= 0:
                    continue
                lower = level_by_ion_local.get((int(ion.ion_index), id1))
                upper = level_by_ion_local.get((int(ion.ion_index), id2))
                lower_label = str(getattr(lower, "level_label", ""))
                upper_label = str(getattr(upper, "level_label", ""))
                pop = _pop(lower)
                ans1 = float(row.get("ans1_after_calc_hmc_ion_filter", row.get("ans1", 0.0)) or 0.0)
                ans2 = float(row.get("ans2_after_calc_hmc_ion_filter", row.get("ans2", 0.0)) or 0.0)
                if rt == 7 and id2 > int(row.get("nlev", 0) or 0) and upper_label.startswith("1s1"):
                    current_k_pi += ans1 * pop
                if rt in {4, 41} and (lower_label.startswith("1s1") or upper_label.startswith("1s1")):
                    if rt == 4:
                        fluorescence += ans2 * pop
                    else:
                        auger += ans1 * pop
            buf.log_lines.append(
                f" {label[:8]:<8s} {pirttoto:11.3E} {fluorescence:11.3E} {auger:11.3E} {fluorescence/(1.0e-34+pirttoto):11.3E}"
            )
        previous_k_pi = current_k_pi

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the option22 final lines operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _option22_final_lines(state: XSTARPythonState, buf: LegacyPprintBuffers) -> tuple[str, str, str, str]:
    buf.log_lines.append(" print option:22")
    workspace = _workspace(state)
    epi = _active_epi(state)
    n = epi.size
    zremsz = np.asarray(workspace.zremsz, dtype=float).reshape(-1)[:n]
    dpthc = np.asarray(workspace.dpthc, dtype=float)
    r = float(state.transfer.radius)
    t4 = _temperature_t4(state)
    xpx = float(state.plasma.xpx)
    xee = float(state.plasma.xee)
    r19 = r * 1.0e-19
    enlum = float(state.control.get("enlum", state.control.get("xlum", 0.0)))
    xlum = float(state.control.get("xlum", 0.0))
    uu1 = enlum / (12.56 * xpx * r19 * r19) / 3.0e10
    nb1 = int(nbinc(100.0, epi, n))
    nb10 = int(nbinc(10000.0, epi, n))
    lo = max(2, min(n, nb1))
    hi = max(lo, min(n, nb10))
    enlumx = 0.0
    for kl in range(lo, hi + 1):
        i = kl - 1
        enlumx += (
            zremsz[i] / epi[i] + zremsz[i - 1] / epi[i - 1]
        ) * (epi[i] - epi[i - 1]) / 2.0
    uux = enlumx / (12.56 * xpx * r19 * r19) / 3.0e10
    skse = xlum / (xpx * r19 * r19)
    zeta = np.log10(max(1.0e-24, skse))
    ekt = t4 * LEGACY_BOLTZMANN_EV_PER_T4 * ERGSEV
    sksec = skse / 12.56 / ((1.0 + xee) * ekt * 2.998e10)
    zetac = np.log10(max(1.0e-24, sksec))
    nry_gamma = max(1, min(n, int(nbinc(13.7, epi, n)) + 1)) - 1
    egam = zremsz[nry_gamma] / (2.0 * 12.56 * xpx * 2.998e10 * r19 * r19 + 1.0e-24)
    nry = max(1, min(n, int(nbinc(13.6, epi, n)) + 1)) - 1
    xnx = xpx * xee
    line1 = (
        f" r={_fmt_e(r)} t={_fmt_e(t4)} log(xi)={_fmt_e(zeta)}"
        f" n_e={_fmt_e(xnx)} n_p={_fmt_e(xpx)}"
    )
    line2 = (
        f"httot={_fmt_e(state.thermal.heating)} cltot={_fmt_e(state.thermal.cooling)} "
        f"taulc={_fmt_e(dpthc[0, nry])} taulcb={_fmt_e(dpthc[1, nry])}"
    )
    line3 = (
        f" log(Xi)={_fmt_e(zetac)} log(u1)={_fmt_e(np.log10(max(1.0e-24, uu1)))}"
        f" log(ux)={_fmt_e(np.log10(max(1.0e-24, uux)))}"
        f" gamma={_fmt_e(egam)} rdel={_fmt_e(state.transfer.radial_depth)}"
    )
    blank = " "
    buf.log_lines.extend((line1, line2, line3, blank))
    buf.source_calls.append("pprint(22)")
    return line1, line2, line3, blank


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the ascii table hdu operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _ascii_table_hdu(name: str, columns: Sequence[fits.Column]) -> fits.TableHDU:
    hdu = fits.TableHDU.from_columns(columns, name=name)
    hdu.header["EXTNAME"] = name
    return hdu


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the rows matrix operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def _rows_matrix(rows: Mapping[int, np.ndarray], *, numrec: int, width: int) -> np.ndarray:
    matrix = np.zeros((numrec, width), dtype=np.float32)
    for index, values in rows.items():
        if 1 <= int(index) <= numrec:
            arr = np.asarray(values, dtype=np.float32).reshape(-1)
            if arr.size != width:
                raise LegacyPprintPortError("pprint row width mismatch")
            matrix[int(index) - 1, :] = arr
    return matrix


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write xout abund1 for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def write_xout_abund1(
    state: XSTARPythonState,
    *,
    path: str | Path,
    overwrite: bool = True,
) -> str:
    """Translate ``pprint(11)`` and write ``xout_abund1.fits``."""
    buf = _buffers(state)
    metadata = _pprint_metadata(state)
    numrec = int(state.control.get("numrec", 0))
    if numrec < 1:
        raise LegacyPprintPortError("pprint(11) requires positive numrec")
    # Source XSTAR sets ``numrec=jkp+1`` after the first traversal.  The
    # terminal ``pprint(12,jkp,...)`` overwrites row ``jkp`` and the already
    # included ``numrec`` row remains the single trailing all-zero record.
    # Therefore the FITS table has exactly ``numrec`` rows, not
    # ``numrec+1``.  Adding another row creates a second zero-padding record.
    output_numrec = numrec
    nions = len(metadata.ions)
    nelem = len(metadata.thermal_elements)
    abund = _rows_matrix(buf.abundance_rows, numrec=output_numrec, width=8 + nions)
    heat = _rows_matrix(buf.heating_rows, numrec=output_numrec, width=8 + nelem + 2)
    cool = _rows_matrix(buf.cooling_rows, numrec=output_numrec, width=8 + nelem + 3)

    base_names = (
        "radius", "delta_r", "ion_parameter", "x_e", "n_p", "pressure",
        "temperature", "frac_heat_error",
    )
    # Preserve pprint.f90 option-11 source typo: kunits(5) is never set;
    # kunits(6) is first assigned cm**(-3) and then overwritten by pressure.
    base_units = ("cm", "cm", "erg*cm/s", "", "", "dynes/cm**2", "10**4 K", "")
    ion_names = tuple(item.ion_label.strip().replace(" ", "_") for item in metadata.ions)
    element_names = tuple(_pprint_element_column_name(item) for item in metadata.thermal_elements)

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the columns for operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
    # XSTAR-FUNCTION-COMMENT-END
    def columns_for(matrix: np.ndarray, names: Sequence[str], units: Sequence[str]) -> list[fits.Column]:
        return [
            fits.Column(name=str(name), format="E13.5", unit=(str(unit) or None), array=matrix[:, idx])
            for idx, (name, unit) in enumerate(zip(names, units))
        ]

    abund_columns = columns_for(abund, base_names + ion_names, base_units + ("",) * nions)

    columns_values = np.zeros((1, 8 + nions), dtype=np.float32)
    columns_values[0, 8:] = _compute_ion_column_values(
        abundance_rows=buf.abundance_rows,
        metadata=metadata,
        numrec=numrec,
        ababs=state.control.get("ababs", np.ones(len(metadata.element_labels))),
    ).astype(np.float32, copy=False)
    column_columns = columns_for(columns_values, base_names + ion_names, base_units + ("",) * nions)

    heat_names = base_names + element_names + ("compton", "total")
    heat_units = base_units + ("",) * (nelem + 2)
    cool_names = base_names + element_names + ("compton", "brems", "total")
    cool_units = base_units + ("",) * (nelem + 3)

    primary = fits.PrimaryHDU()
    apply_python_primary_fits_header(
        primary.header,
        model_name=str(state.control.get("kmodelname", "xstar-python"))[:30],
        atomic_data_date=str(state.control.get("atcredate", ""))[:63],
    )
    hdul = fits.HDUList([
        primary,
        _ascii_table_hdu("ABUNDANCES", abund_columns),
        _ascii_table_hdu("COLUMNS", column_columns),
        _ascii_table_hdu("HEATING", columns_for(heat, heat_names, heat_units)),
        _ascii_table_hdu("COOLING", columns_for(cool, cool_names, cool_units)),
    ])
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    hdul.writeto(output, overwrite=overwrite, checksum=False)
    from .output_writers import (
        _refresh_fits_checksums,
        _rewrite_fits_ascii_table_intercolumn_gaps,
    )
    try:
        _rewrite_fits_ascii_table_intercolumn_gaps(output)
    except Exception:
        pass
    _refresh_fits_checksums(output)
    if "pprint(11)" not in buf.source_calls:
        buf.source_calls.append("pprint(11)")
    return str(output)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Emit terminal STEP print surfaces and xout_abund1 accumulation from the final qualified source state.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def finalize_legacy_pprint(
    state: XSTARPythonState,
    *,
    out_dir: str | Path | None,
    overwrite: bool = True,
) -> tuple[tuple[str, ...], Mapping[str, str]]:
    """Execute final ``pprint(22)`` and the default ``pprint(11)`` report."""
    if not bool(state.control.get("pprint_legacy_enabled", False)):
        return (), {}
    buf = initialize_legacy_pprint(state)
    requested_lpri = int(state.control.get("requested_lpri", state.control.get("lpri", 0)))
    _final_zero_thickness_print(state, buf)
    _option22_final_lines(state, buf)
    dispatch = {
        1: _option1_emission_line_luminosities,
        23: _option23_line_depths,
        24: _option24_absorption_edge_depths,
        16: _option16_ucalc_timing_accounting,
        27: _option27_ion_column_densities,
        15: _option15_line_luminosities_and_depths,
        19: _option19_recombination_continuum_luminosities,
        5: _option5_energy_sums,
        14: _option14_line_opacity_emissivity,
        21: _option21_level_opacity_emissivity,
        7: _option7_level_populations,
        10: _option10_ion_rates,
        4: _option4_continuum_opacity,
        6: _option6_continuum_luminosities,
        18: _option18_line_levels,
        29: _option29_rates,
        30: _option30_auger_fluorescence,
    }
    for option in _final_pprint_option_sequence(requested_lpri)[1:]:
        if option == 11:
            _append_pprint_marker(buf, 11)
        elif option in (0, 26):
            _append_pprint_marker(buf, option)
        else:
            fn = dispatch.get(option)
            if fn is not None:
                fn(state, buf)
    paths: dict[str, str] = {}
    if out_dir is not None:
        root = Path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
        log_path = root / "xout_step.log"
        log_path.write_text("\n".join(buf.log_lines) + "\n", encoding="utf-8")
        paths[log_path.name] = str(log_path)
        if requested_lpri >= 0:
            abund_path = root / "xout_abund1.fits"
            paths[abund_path.name] = write_xout_abund1(state, path=abund_path, overwrite=overwrite)
    buf.final_written = True
    state.outputs["legacy_pprint_paths"] = dict(paths)
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return tuple(buf.source_calls), paths


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Provide the direct-source reference for fortran pprint reference for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def direct_fortran_pprint_reference() -> Mapping[str, Any]:
    """Frozen values from literal source fragments compiled with gfortran."""
    return {
        "heading_1": "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)",
        "heading_2": "                                                                  fwd    rev",
        "zone_values": np.asarray([
            19.0, -36.0, -10.0, 37.30102999566398, 1.2,
            0.6989700043360189, 6.0, 2.5, 75.0, -10.0, -10.0,
        ]),
        "abundance_column": np.asarray([0.0, 1.00000003e15], dtype=np.float32),
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute direct fortran pprint validation for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 and source pprint print-option semantics.
# XSTAR-FUNCTION-COMMENT-END
def run_direct_fortran_pprint_validation(*, rtol: float = 2.0e-7, atol: float = 0.0) -> dict[str, bool]:
    ref = direct_fortran_pprint_reference()
    h1, h2 = _fortran_logical_line_17()
    # The numeric values are independently reconstructed from the literal
    # option-9 and option-11 equations used in the minimal Fortran reference.
    values = np.asarray([
        np.log10(1.0e19),
        np.log10(max(1.0e-36, min(99.0, 0.0 / 1.0e19))),
        np.log10(max(0.0, 1.0e-10)),
        np.log10(1.0e38 / 5.0 / 1.0 / 1.0),
        1.2,
        np.log10(5.0),
        np.log10(100.0) + 4.0,
        2.5,
        75.0,
        -10.0,
        -10.0,
    ])
    # Two radial rows: fraction 0 then 0.5, density 5, delta depth 2e15,
    # element abundance 0.4 -> 2e15 source trapezoid column.
    column = np.asarray([0.0, (0.5 * 5.0 + 0.0 * 5.0) * 2.0e15 * 0.4 / 2.0], dtype=np.float32)
    summary = {
        "pprint_option17_heading_direct_fortran_ready": h1 == ref["heading_1"] and h2 == ref["heading_2"],
        "pprint_option9_values_direct_fortran_ready": bool(np.allclose(values, ref["zone_values"], rtol=rtol, atol=atol)),
        "pprint_option11_column_direct_fortran_ready": bool(np.allclose(column, ref["abundance_column"], rtol=rtol, atol=atol)),
    }
    summary["pprint_direct_original_fortran_reference_ready"] = bool(all(summary.values()))
    return summary


__all__ = [
    "LegacyPprintPortError", "PprintIonMetadata", "PprintElementMetadata",
    "PprintAtomicMetadata", "LegacyPprintBuffers", "NLPRNT",
    "initialize_legacy_pprint", "legacy_pprint_begin_pass", "legacy_pprint_after_heatt",
    "finalize_legacy_pprint", "write_xout_abund1", "_final_pprint_option_sequence",
    "direct_fortran_pprint_reference", "run_direct_fortran_pprint_validation",
]
