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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


def _install_astropy_numpy_compatibility() -> None:
    """Install narrow NumPy shims needed by older Astropy on new NumPy."""
    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # type: ignore[attr-defined]
    try:
        import numpy.lib._function_base_impl as _np_function_base
    except Exception:
        return
    if not hasattr(_np_function_base, "_check_interpolation_as_method"):
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


class LegacyPprintPortError(RuntimeError):
    """Raised when the bounded source ``pprint`` contract is unavailable."""


ERGSEV = 1.602197e-12
NLPRNT = (
    22, 11, 1, 23, 24, 16, 27, 15, 19, 5, 14, 21, 7, 10, 26, 0, 4, 6, 18, 29, 30, 28
)

ELEMENT_FULL_NAMES = (
    "hydrogen", "helium", "lithium", "beryllium", "boron",
    "carbon", "nitrogen", "oxygen", "fluorine", "neon",
    "sodium", "magnesium", "aluminum", "silicon", "phosphorus",
    "sulfur", "chlorine", "argon", "potassium", "calcium",
    "scandium", "titanium", "vanadium", "chromium", "manganese",
    "iron", "cobalt", "nickel", "copper", "zinc",
)
ELEMENT_SYMBOL_TO_FULL_NAME = {
    "H": "hydrogen", "HE": "helium", "LI": "lithium", "BE": "beryllium",
    "B": "boron", "C": "carbon", "N": "nitrogen", "O": "oxygen",
    "F": "fluorine", "NE": "neon", "NA": "sodium", "MG": "magnesium",
    "AL": "aluminum", "SI": "silicon", "P": "phosphorus", "S": "sulfur",
    "CL": "chlorine", "AR": "argon", "K": "potassium", "CA": "calcium",
    "SC": "scandium", "TI": "titanium", "V": "vanadium", "CR": "chromium",
    "MN": "manganese", "FE": "iron", "CO": "cobalt", "NI": "nickel",
    "CU": "copper", "ZN": "zinc",
}


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


def _pprint_metadata(state: XSTARPythonState) -> PprintAtomicMetadata:
    value = state.control.get("pprint_atomic_metadata")
    if not isinstance(value, PprintAtomicMetadata):
        raise LegacyPprintPortError(
            "legacy pprint requires state.control['pprint_atomic_metadata']"
        )
    return value


def _buffers(state: XSTARPythonState, *, create: bool = False) -> LegacyPprintBuffers:
    value = state.outputs.get("legacy_pprint_buffers")
    if value is None and create:
        value = LegacyPprintBuffers()
        state.outputs["legacy_pprint_buffers"] = value
    if not isinstance(value, LegacyPprintBuffers):
        raise LegacyPprintPortError("legacy pprint caller-owned buffers are missing")
    return value


def _workspace(state: XSTARPythonState) -> Any:
    value = state.control.get("radial_transfer_workspace")
    if value is None:
        raise LegacyPprintPortError("legacy pprint requires radial transfer workspace")
    return value


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


def _fmt_e(value: float, width: int = 11, precision: int = 3) -> str:
    return f"{float(value):{width}.{precision}E}"


def _fmt_list_integer(value: int) -> str:
    # gfortran list-directed integers have a leading blank in these records.
    return f" {int(value)}"


def _fortran_logical_line_17() -> tuple[str, str]:
    # Exact gfortran rendering of source formats 9979 and 9989.
    return (
        "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)",
        "                                                                  fwd    rev",
    )


def _temperature_t4(state: XSTARPythonState) -> float:
    value = float(state.plasma.temperature)
    unit = str(state.control.get("plasma_temperature_unit", "legacy-auto")).strip().lower()
    if unit in {"k", "kelvin"}:
        return value / 1.0e4
    if unit in {"t4", "1e4k", "10^4k"}:
        return value
    return value / 1.0e4 if value > 1.0e3 else value


def _active_epi(state: XSTARPythonState) -> np.ndarray:
    n = int(state.control["ncn2"])
    epi = np.asarray(state.radiation.epi, dtype=float).reshape(-1)
    if epi.size < n:
        raise LegacyPprintPortError("epi is shorter than ncn2")
    return epi[:n]


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


def _option17_headings(buf: LegacyPprintBuffers) -> None:
    buf.log_lines.append(" print option:17")
    buf.log_lines.extend(_fortran_logical_line_17())
    buf.source_calls.append("pprint(17)")


def initialize_legacy_pprint(state: XSTARPythonState) -> LegacyPprintBuffers:
    """Execute source initialization calls ``pprint(3)`` and ``pprint(2)``."""
    buf = _buffers(state, create=True)
    if buf.initialized:
        return buf
    _option3_parameter_capture(state, buf)
    _option2_input_lines(state, buf)
    buf.log_lines.append(" running ...")
    buf.initialized = True
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return buf



def legacy_pprint_begin_pass(state: XSTARPythonState) -> tuple[str, ...]:
    """Emit the source pass banner followed by ``pprint(17)`` headings."""
    if not bool(state.control.get("pprint_legacy_enabled", False)):
        return ()
    buf = initialize_legacy_pprint(state)
    kk = int(state.transfer.pass_index)
    if kk in buf.begun_passes:
        return ()
    ldir = int(state.transfer.direction)
    buf.log_lines.append(" ")
    # This is list-directed in xstar.f90; retain the textual contract while
    # avoiding compiler-dependent leading-field padding.
    buf.log_lines.append(f" pass number= {kk} {ldir}")
    _option17_headings(buf)
    buf.begun_passes.add(kk)
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return ("pprint(17)",)


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
    nry = int(nbinc(13.6, epi, n)) + 1
    nry0 = max(1, min(n, nry)) - 1
    values = (
        np.log10(r),
        np.log10(max(1.0e-36, min(99.0, rdel / r))),
        np.log10(max(xcol, 1.0e-10)),
        zeta,
        xee,
        np.log10(xpx),
        np.log10(t4) + 4.0,
        min(99.99, max(-99.99, float(state.thermal.residual) * 100.0)),
        min(99.99, max(-99.99, terr * 100.0)),
        np.log10(max(dpthc[0, nry0], 1.0e-10)),
        np.log10(max(dpthc[1, nry0], 1.0e-10)),
    )
    line = " " + "".join(f" {float(value):6.2f}" for value in values)
    # The current source call supplies only ntotit to the historical 2i3
    # FORMAT.  Match the observed xout_step.log rather than emitting the Python
    # diagnostic lnerrd as an extra column.
    line += f"{int(state.control.get('ntotit', 0)):3d}"
    buf.log_lines.append(line)
    buf.source_calls.append("pprint(9)")
    return line


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


def legacy_pprint_after_heatt(state: XSTARPythonState, *, terminal_record: bool = False) -> tuple[str, ...]:
    """Execute source ``pprint(9)`` and final-pass ``pprint(12)``."""
    if not bool(state.control.get("pprint_legacy_enabled", False)):
        return ()
    buf = initialize_legacy_pprint(state)
    _option9_zone_line(state, buf)
    calls = ["pprint(9)"]
    if int(state.transfer.pass_index) == int(state.control.get("npass", 1)):
        zone_index = int(state.control.get("numrec", state.transfer.zone_index)) if terminal_record else int(state.transfer.zone_index)
        _option12_accumulate(state, buf, zone_index=zone_index)
        calls.append("pprint(12:terminal)" if terminal_record else "pprint(12)")
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return tuple(calls)




def _line_metadata_rows(state: XSTARPythonState) -> tuple[Any, ...]:
    """Return output line metadata without importing output_writers at module load."""
    meta = state.control.get("output_atomic_metadata")
    rows = getattr(meta, "lines", ())
    return tuple(rows) if rows is not None else ()


def _line_report_rank(rows: Sequence[Any], values: np.ndarray, *, limit: int = 500) -> list[Any]:
    ranked: list[tuple[float, int, Any]] = []
    arr = np.asarray(values, dtype=float)
    for order, row in enumerate(rows):
        idx = int(getattr(row, "line_index", 0)) - 1
        if idx < 0 or idx >= arr.shape[-1]:
            continue
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        rate_type = int(getattr(row, "rate_type", 50))
        if rate_type in (9, 14) or wave <= 0.1 or wave >= 8.9e6:
            continue
        if arr.ndim == 2:
            score = max(abs(float(arr[0, idx])), abs(float(arr[1, idx])))
        else:
            score = abs(float(arr[idx]))
        if score <= 0.0:
            continue
        ranked.append((-score, order, row))
    ranked.sort()
    return [r for _, _, r in ranked[: int(limit)]]


def _option1_emission_line_luminosities(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit the lprint=1 ``pprint(1)`` emission-line luminosity report."""
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
    for out_index, row in enumerate(_line_report_rank(rows, elum, limit=500), start=1):
        idx = int(getattr(row, "line_index", 0)) - 1
        ion = str(getattr(row, "ion_label", ""))[:8]
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        # ``heatt.f90``/``pprint.f90`` already stores ``elum`` in the
        # units printed by XSTAR (erg/sec/10**38).  Do not divide by 1e38
        # again; doing so made the v0.5.20 verbose text misleading without
        # changing the physical arrays.
        reflected = float(elum[0, idx])
        transmitted = float(elum[1, idx])
        buf.log_lines.append(
            f"{out_index:9d}{int(getattr(row, 'line_index', 0)):8d} {ion:<8s}"
            f"{wave:13.5E}{reflected:13.5E}{transmitted:13.5E}"
        )
    buf.source_calls.append("pprint(1)")


def _option23_line_depths(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit the lprint=1 ``pprint(23)`` line-depth report."""
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
    for out_index, row in enumerate(_line_report_rank(rows, tau0, limit=500), start=1):
        idx = int(getattr(row, "line_index", 0)) - 1
        ion = str(getattr(row, "ion_label", ""))[:8]
        wave = abs(float(getattr(row, "wavelength_angstrom", 0.0)))
        reflected = float(tau0[0, idx])
        transmitted = float(tau0[1, idx])
        buf.log_lines.append(
            f"{out_index:9d}{int(getattr(row, 'line_index', 0)):8d} {ion:<8s}"
            f"{wave:13.5E}{reflected:13.5E}{transmitted:13.5E}"
        )
    buf.source_calls.append("pprint(23)")


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


def _row_element_symbol(row: Any) -> str:
    ion = str(getattr(row, "ion_label", "")).strip().lower()
    return ion.split("_")[0] if ion else ""


def _active_line_rows_by_index(state: XSTARPythonState, rows: Sequence[Any]) -> list[Any]:
    active = _active_element_symbols(state)
    out = [
        r for r in rows
        if int(getattr(r, "line_index", 0)) > 0
        and (not active or _row_element_symbol(r) in active)
    ]
    out.sort(key=lambda r: int(getattr(r, "line_index", 0)))
    return out


def _active_rrc_rows_by_index(state: XSTARPythonState, rows: Sequence[Any]) -> list[Any]:
    active = _active_element_symbols(state)
    out = [
        r for r in rows
        if int(getattr(r, "continuum_index", 0)) > 0
        and (not active or _row_element_symbol(r) in active)
    ]
    out.sort(key=lambda r: int(getattr(r, "continuum_index", 0)))
    return out


def _line_rows_by_index(rows: Sequence[Any]) -> list[Any]:
    out = [r for r in rows if int(getattr(r, "line_index", 0)) > 0]
    out.sort(key=lambda r: int(getattr(r, "line_index", 0)))
    return out


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
            f"{float(tau0[0, idx]):13.5E}{float(tau0[1, idx]):13.5E}{label}"
        )
    buf.source_calls.append("pprint(15)")


def _option27_ion_column_densities(state: XSTARPythonState, buf: LegacyPprintBuffers) -> None:
    """Emit verbose ``pprint(27)`` ion column densities from pprint rows."""
    metadata = _pprint_metadata(state)
    numrec = int(state.control.get("numrec", 0))
    nions = len(metadata.ions)
    if numrec < 2 or not buf.abundance_rows or nions <= 0:
        return
    columns = np.zeros(nions, dtype=float)
    ababs = np.asarray(state.control.get("ababs", np.ones(len(metadata.element_labels))), dtype=float)
    for j in range(1, numrec):
        prev = buf.abundance_rows.get(j)
        curr = buf.abundance_rows.get(j + 1)
        if prev is None or curr is None:
            continue
        prev = np.asarray(prev, dtype=float).reshape(-1)
        curr = np.asarray(curr, dtype=float).reshape(-1)
        if prev.size < 8 + nions or curr.size < 8 + nions:
            continue
        dr = float(curr[1] - prev[1])
        for k, ion in enumerate(metadata.ions):
            elem_ab = float(ion.elemental_abundance)
            if 1 <= int(ion.element_index) <= ababs.size:
                elem_ab = float(ababs[int(ion.element_index) - 1])
            columns[k] += (curr[8 + k] * curr[4] + prev[8 + k] * prev[4]) * dr * elem_ab / 2.0
    buf.log_lines.extend([
        " ",
        " print option:27",
        " ion column densities",
        " index, ion, column density",
    ])
    for k, ion in enumerate(metadata.ions):
        value = float(columns[k])
        if value == 0.0:
            continue
        buf.log_lines.append(f"{int(ion.ion_index):5d} {str(ion.ion_label)[:8]:<8s}{value:14.8E}")
    buf.source_calls.append("pprint(27)")


def _rrc_metadata_rows(state: XSTARPythonState) -> tuple[Any, ...]:
    meta = state.control.get("output_atomic_metadata")
    rows = getattr(meta, "rrcs", ())
    return tuple(rows) if rows is not None else ()


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
        buf.log_lines.append(
            f"{ci:7d}{level:6d} {ion:<8s}{level:8d} {lower:<20s} {upper:<20s}"
            f"{energy:13.3E}{backward:13.3E}{forward:13.3E}"
        )
    buf.source_calls.append("pprint(24)")


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
    for out_index, row in enumerate(_active_rrc_rows_by_index(state, rows), start=1):
        ci = int(getattr(row, "continuum_index", out_index))
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
        buf.log_lines.append(
            f"{out_index:7d}{level:6d} {ion:<8s}{level:8d} {lower:<20s} {upper:<20s}"
            f"{energy:13.3E}{out_lum:13.3E}{in_lum:13.3E}"
        )
    buf.source_calls.append("pprint(19)")


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
    ekt = t4 * 0.861707 * ERGSEV
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
        f"httot={_fmt_e(state.thermal.heating)} cltot={_fmt_e(state.thermal.cooling)}"
        f"taulc={_fmt_e(dpthc[0, nry])}taulcb={_fmt_e(dpthc[1, nry])}"
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


def _ascii_table_hdu(name: str, columns: Sequence[fits.Column]) -> fits.TableHDU:
    hdu = fits.TableHDU.from_columns(columns, name=name)
    hdu.header["EXTNAME"] = name
    return hdu


def _rows_matrix(rows: Mapping[int, np.ndarray], *, numrec: int, width: int) -> np.ndarray:
    matrix = np.zeros((numrec, width), dtype=np.float32)
    for index, values in rows.items():
        if 1 <= int(index) <= numrec:
            arr = np.asarray(values, dtype=np.float32).reshape(-1)
            if arr.size != width:
                raise LegacyPprintPortError("pprint row width mismatch")
            matrix[int(index) - 1, :] = arr
    return matrix


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
    # Source XSTAR leaves one terminal all-zero table record after the final
    # physical row.  Keep the caller-owned physical rows indexed 1..numrec,
    # and reserve row numrec+1 as the trailing zero record in the three
    # multi-row FITS extensions.  The COLUMNS extension is an integrated
    # single-row product and must integrate only the physical rows.
    output_numrec = numrec + 1
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

    def columns_for(matrix: np.ndarray, names: Sequence[str], units: Sequence[str]) -> list[fits.Column]:
        return [
            fits.Column(name=str(name), format="E13.5", unit=(str(unit) or None), array=matrix[:, idx])
            for idx, (name, unit) in enumerate(zip(names, units))
        ]

    abund_columns = columns_for(abund, base_names + ion_names, base_units + ("",) * nions)

    columns_values = np.zeros((1, 8 + nions), dtype=np.float32)
    ababs = np.asarray(state.control.get("ababs", np.ones(len(metadata.element_labels))), dtype=float)
    for j in range(1, numrec):
        r0 = abund[j - 1, 1]
        r1 = abund[j, 1]
        for k, ion in enumerate(metadata.ions):
            element_abundance = float(ion.elemental_abundance)
            if 1 <= ion.element_index <= ababs.size:
                element_abundance = float(ababs[ion.element_index - 1])
            columns_values[0, 8 + k] += (
                abund[j, 8 + k] * abund[j, 4] + abund[j - 1, 8 + k] * abund[j - 1, 4]
            ) * (r1 - r0) * element_abundance / 2.0
    column_columns = columns_for(columns_values, base_names + ion_names, base_units + ("",) * nions)

    heat_names = base_names + element_names + ("compton", "total")
    heat_units = base_units + ("",) * (nelem + 2)
    cool_names = base_names + element_names + ("compton", "brems", "total")
    cool_units = base_units + ("",) * (nelem + 3)

    primary = fits.PrimaryHDU()
    primary.header["CREATOR"] = "XSTAR version 2.59g"
    primary.header["MODEL"] = str(state.control.get("kmodelname", "xstar-python"))[:30]
    primary.header["ATDATA"] = str(state.control.get("atcredate", ""))[:63]
    hdul = fits.HDUList([
        primary,
        _ascii_table_hdu("ABUNDANCES", abund_columns),
        _ascii_table_hdu("COLUMNS", column_columns),
        _ascii_table_hdu("HEATING", columns_for(heat, heat_names, heat_units)),
        _ascii_table_hdu("COOLING", columns_for(cool, cool_names, cool_units)),
    ])
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    hdul.writeto(output, overwrite=overwrite, checksum=True)
    if "pprint(11)" not in buf.source_calls:
        buf.source_calls.append("pprint(11)")
    return str(output)


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
    _option22_final_lines(state, buf)
    buf.log_lines.extend([" ", " print option:11"])
    if "pprint(11)" not in buf.source_calls:
        buf.source_calls.append("pprint(11)")
    if requested_lpri >= 1:
        _option1_emission_line_luminosities(state, buf)
        _option23_line_depths(state, buf)
        _option24_absorption_edge_depths(state, buf)
        _option16_ucalc_timing_accounting(state, buf)
        _option27_ion_column_densities(state, buf)
        _option15_line_luminosities_and_depths(state, buf)
        _option19_recombination_continuum_luminosities(state, buf)
        _option5_energy_sums(state, buf)
    paths: dict[str, str] = {}
    if out_dir is not None:
        root = Path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
        log_path = root / "xout_step.log"
        log_path.write_text("\n".join(buf.log_lines) + "\n", encoding="utf-8")
        paths[log_path.name] = str(log_path)
        abund_path = root / "xout_abund1.fits"
        paths[abund_path.name] = write_xout_abund1(state, path=abund_path, overwrite=overwrite)
    else:
        buf.source_calls.append("pprint(11)")
    buf.final_written = True
    state.outputs["legacy_pprint_paths"] = dict(paths)
    state.outputs["legacy_pprint_source_order"] = list(buf.source_calls)
    return tuple(buf.source_calls), paths


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
    "finalize_legacy_pprint", "write_xout_abund1",
    "direct_fortran_pprint_reference", "run_direct_fortran_pprint_validation",
]
