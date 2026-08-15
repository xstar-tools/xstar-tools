# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: rread1.f90; ispec4.f90; starf.f90; ispec.f90; ispecg.f90; ispecgg.f90; xstar.f90
#   Role: Construct and renormalize the incident continuum for every public spectrum mode.
#   Relation: Literal source-order translation, including file-unit conversion, log interpolation, and repeated-pass ownership.
#   Concordance: SPECTRUM-001
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Source-faithful XSTAR incident-spectrum contract.

The public spectrum modes are translated from the canonical XSTAR 2.59g
routines ``ispec4`` (power law), ``starf`` (black body), ``ispec``
(bremsstrahlung), ``ispecg`` (file spectra), and ``ispecgg`` (final
1--1000 Ry renormalization).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Sequence

import numpy as np

from .radiation import nbinc

# constants.f90 REAL(8) parameter initialized by an unsuffixed literal: the
# source build rounds the literal through default REAL before promotion.
SOURCE_ERGSEV = float(np.float32(1.602176634e-12))
SOURCE_BREMS_KEV_PER_T7 = float(np.float32(0.861707))
# ispec.f90 evaluates 1000.*0.861707 in default REAL before multiplying by
# REAL(8) tp, so preserve that intermediate binary32 product as well.
SOURCE_BREMS_EV_PER_T7 = float(np.float32(np.float32(1000.0) * np.float32(0.861707)))
SOURCE_STARF_XKT = float(np.float32(1.16e-3))
SOURCE_STARF_TINY = float(np.float32(1.0e-37))
SOURCE_STARF_SMALL = float(np.float32(1.0e-3))
SOURCE_STARF_FACTOR = float(np.float32(3.1415e22))
SOURCE_STARF_TAIL_1E37 = float(np.float32(1.0e37))
SOURCE_BAND_LOW_DEFAULT_REAL = float(np.float32(13.6))
SOURCE_BAND_HIGH_DEFAULT_REAL = float(np.float32(1.36e4))
# exp10.f90 uses exp(2.30259*x), with the unsuffixed literal rounded
# through default REAL before promotion to REAL(8).
SOURCE_EXP10_LN10 = float(np.float32(2.30259))


class SpectrumContractError(ValueError):
    """Raised when a public incident-spectrum input violates the source contract."""


@dataclass(frozen=True)
class CanonicalSpectrumFile:
    energy_ev: np.ndarray
    energy_flux: np.ndarray
    spectun: int
    path: str


def canonical_spectrum_mode(value: str) -> str:
    mode = str(value).strip().lower()
    aliases = {
        "pow": "pow",
        "powerlaw": "pow",
        "power-law": "pow",
        "bbody": "bbody",
        "blackbody": "bbody",
        "black-body": "bbody",
        "brems": "brems",
        "bremss": "bremss",
        "bremsstrahlung": "bremss",
        "file": "file",
    }
    if mode not in aliases:
        raise SpectrumContractError(
            "spectrum must be one of pow, bbody, brems/bremss, or file"
        )
    return aliases[mode]


def _source_expo(value: float) -> float:
    return math.exp(min(max(float(value), -60.0), 60.0))


def _source_ispecgg_inplace(z: np.ndarray, epi: np.ndarray, luminosity_1e38: float) -> None:
    total = 0.0
    for i in range(1, epi.size):
        if SOURCE_BAND_LOW_DEFAULT_REAL <= float(epi[i]) <= SOURCE_BAND_HIGH_DEFAULT_REAL:
            total += (float(z[i]) + float(z[i - 1])) * (float(epi[i]) - float(epi[i - 1])) / 2.0
    if not (math.isfinite(total) and total > 0.0):
        raise SpectrumContractError("incident spectrum 1-1000 Ry normalization is nonpositive")
    scale = float(luminosity_1e38) / total / SOURCE_ERGSEV
    for i in range(z.size):
        z[i] = float(z[i]) * scale


def _source_ispec4_component(index: float, luminosity_1e38: float, epi: np.ndarray) -> np.ndarray:
    raw = np.empty(epi.size, dtype=float)
    for i, energy in enumerate(epi):
        raw[i] = float(energy) ** float(index) if float(energy) > 0.01 else float(np.float32(1.0e-24))
    nb1 = int(nbinc(13.6, epi, epi.size))
    nb2 = int(nbinc(1.36e4, epi, epi.size))
    total = 0.0
    for one in range(max(2, nb1), min(epi.size, nb2) + 1):
        i = one - 1
        total += (float(raw[i]) + float(raw[i - 1])) * (float(epi[i]) - float(epi[i - 1])) / 2.0
    if not (math.isfinite(total) and total > 0.0):
        raise SpectrumContractError("power-law 1-1000 Ry normalization is nonpositive")
    scale = float(luminosity_1e38) / total / SOURCE_ERGSEV
    for i in range(raw.size):
        raw[i] = float(raw[i]) * scale
    return raw


def _source_starf_component(temperature_t7: float, epi: np.ndarray) -> np.ndarray:
    # xstar.f90 calls starf(trad, xlum2=1, ...), then ispecgg(requested xlum).
    tp = float(temperature_t7)
    if not (math.isfinite(tp) and tp > 0.0):
        raise SpectrumContractError("bbody trad must be positive in units of 1e7 K")
    source_luminosity = 1.0
    xkt = SOURCE_STARF_XKT / (SOURCE_STARF_TINY + tp)
    raw = np.zeros(epi.size, dtype=float)
    total = 0.0
    for i, energy in enumerate(epi):
        e = float(energy)
        tempp = e * xkt
        if tempp < SOURCE_STARF_SMALL:
            value = e ** 3 / tempp
        elif tempp < 150.0:
            value = e ** 3 / (_source_expo(tempp) - 1.0)
        elif tempp > 150.0:
            value = source_luminosity / e / SOURCE_ERGSEV / SOURCE_STARF_TAIL_1E37
        else:
            # Literal starf.f90 leaves the pre-zeroed row at zero for the
            # exactly-150 boundary because the two source predicates are
            # strictly <150 and >150.
            value = 0.0
        raw[i] = SOURCE_STARF_FACTOR * value
        if i > 0 and SOURCE_BAND_LOW_DEFAULT_REAL <= e <= SOURCE_BAND_HIGH_DEFAULT_REAL:
            total += (float(raw[i]) + float(raw[i - 1])) * (e - float(epi[i - 1])) / 2.0
    if not (math.isfinite(total) and total > 0.0):
        raise SpectrumContractError("black-body 1-1000 Ry normalization is nonpositive")
    scale = source_luminosity / total / SOURCE_ERGSEV
    for i in range(raw.size):
        raw[i] = float(raw[i]) * scale
    return raw


def _source_ispec_brems_component(source_trad: float, luminosity_1e38: float, epi: np.ndarray) -> np.ndarray:
    tp = float(source_trad)
    if not (math.isfinite(tp) and tp > 0.0):
        raise SpectrumContractError("brems/bremss trad must be positive")
    # Literal ispec.f90: ekt=1000.*(0.861707)*tp.
    ekt = SOURCE_BREMS_EV_PER_T7 * tp
    raw = np.empty(epi.size, dtype=float)
    total = 0.0
    for i, energy in enumerate(epi):
        raw[i] = _source_expo(-float(energy) / ekt)
        if i > 0 and SOURCE_BAND_LOW_DEFAULT_REAL <= float(energy) <= SOURCE_BAND_HIGH_DEFAULT_REAL:
            total += (float(raw[i]) + float(raw[i - 1])) * (float(energy) - float(epi[i - 1])) / 2.0
    if not (math.isfinite(total) and total > 0.0):
        raise SpectrumContractError("bremsstrahlung 1-1000 Ry normalization is nonpositive")
    scale = float(luminosity_1e38) / total / SOURCE_ERGSEV
    for i in range(raw.size):
        raw[i] = float(raw[i]) * scale
    return raw


def read_canonical_spectrum_file(path: str | Path, spectun: int) -> CanonicalSpectrumFile:
    """Read the canonical XSTAR text spectrum handled by ``rread1.f90``.

    First line is the number of ``energy flux`` pairs.  Energies are eV.
    ``spectun`` follows the executable logic: 0 energy flux, 1 photon flux
    (multiply by energy before normalization), 2 log10 energy flux.
    """
    unit = int(spectun)
    if unit not in (0, 1, 2):
        raise SpectrumContractError("spectun must be 0, 1, or 2")
    p = Path(path)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SpectrumContractError(f"cannot open spectrum_file {p}: {exc}") from exc
    if not lines:
        raise SpectrumContractError(f"empty spectrum_file: {p}")
    try:
        nenergy = int(lines[0].split()[0])
    except Exception as exc:
        raise SpectrumContractError("spectrum_file first line must be the number of energy/flux pairs") from exc
    if nenergy < 2:
        raise SpectrumContractError("spectrum_file requires at least two energy/flux pairs")
    rows: list[tuple[float, float]] = []
    for line in lines[1:]:
        text = line.strip()
        if not text:
            continue
        fields = text.split()
        if len(fields) < 2:
            raise SpectrumContractError("spectrum_file rows must contain energy and flux")
        try:
            energy, flux = float(fields[0]), float(fields[1])
        except ValueError as exc:
            raise SpectrumContractError("spectrum_file energy/flux values must be numeric") from exc
        rows.append((energy, flux))
        if len(rows) == nenergy:
            break
    if len(rows) != nenergy:
        raise SpectrumContractError(
            f"spectrum_file declared {nenergy} pairs but supplied {len(rows)}"
        )
    energy = np.asarray([row[0] for row in rows], dtype=float)
    flux = np.asarray([row[1] for row in rows], dtype=float)
    if np.any(~np.isfinite(energy)) or np.any(energy <= 0.0):
        raise SpectrumContractError("spectrum_file energies must be finite and positive")
    if np.any(~np.isfinite(flux)):
        raise SpectrumContractError("spectrum_file fluxes must be finite")
    # Canonical public text spectra are ordered in increasing energy.
    # ispecg.f90 calls hunt3(), which can search a descending table, but its
    # subsequent ep2/ep1 clamp is source-ordered for an ascending table.  Do
    # not silently reverse a noncanonical file because doing so would change
    # executable semantics.
    delta = np.diff(energy)
    if not np.all(delta > 0.0):
        raise SpectrumContractError("spectrum_file energies must be strictly increasing")
    if unit == 1:
        flux = flux * energy
    elif unit == 2:
        flux = np.power(10.0, flux)
    return CanonicalSpectrumFile(energy, flux, unit, str(p))


def _source_ispecg_component(file_spectrum: CanonicalSpectrumFile, luminosity_1e38: float, epi: np.ndarray) -> np.ndarray:
    src_e = np.asarray(file_spectrum.energy_ev, dtype=float)
    src_f = np.asarray(file_spectrum.energy_flux, dtype=float)
    out = np.zeros(epi.size, dtype=float)
    emin = float(src_e[0]); emax = float(src_e[-1])
    for i, energy in enumerate(epi):
        x = float(energy)
        if x < emin or x > emax:
            continue
        hi = int(np.searchsorted(src_e, x, side="right"))
        if hi <= 0:
            lo = 0; hi = 1
        elif hi >= src_e.size:
            lo = src_e.size - 2; hi = src_e.size - 1
        else:
            lo = hi - 1
        zr1 = math.log10(max(float(src_f[hi]), 1.0e-49))
        zr2 = math.log10(max(float(src_f[lo]), 1.0e-49))
        ep1 = math.log10(max(float(src_e[hi]), 1.0e-49))
        ep2 = math.log10(max(float(src_e[lo]), 1.0e-49))
        alx = min(max(math.log10(x), ep2), ep1)
        aly = (zr1 - zr2) * (alx - ep2) / (ep1 - ep2 + 1.0e-49) + zr2
        out[i] = math.exp(SOURCE_EXP10_LN10 * aly)
    total = 0.0
    previous = float(out[0])
    for i in range(1, epi.size):
        current = float(out[i])
        if SOURCE_BAND_LOW_DEFAULT_REAL <= float(epi[i]) <= SOURCE_BAND_HIGH_DEFAULT_REAL:
            total += (current + previous) * (float(epi[i]) - float(epi[i - 1])) / 2.0
        previous = current
    total *= SOURCE_ERGSEV
    if not (math.isfinite(total) and total > 0.0):
        raise SpectrumContractError("file spectrum 1-1000 Ry normalization is nonpositive")
    scale = float(luminosity_1e38) / total
    for i in range(out.size):
        out[i] = float(out[i]) * scale
    return out


def apply_source_spectrum_pass(
    existing: Sequence[float],
    *,
    mode: str,
    trad: float,
    luminosity_1e38: float,
    epi_eV: Sequence[float],
    file_spectrum: CanonicalSpectrumFile | None = None,
) -> np.ndarray:
    """Execute one literal ``xstar.f90`` source-spectrum pass.

    ``existing`` is caller-owned ``zremsz``.  Power-law, black-body, and file
    components are additive before ``ispecgg``; canonical ``brems`` assigns a
    fresh ``ispec`` spectrum before ``ispecgg``.  Public ``bremss`` accepts
    ``trad`` in keV and converts it to the source ``ispec`` temperature
    parameter so that ``kT_eV = 1000*trad`` exactly in the translated source arithmetic.  The canonical FORTRAN spelling
    ``brems`` remains available with literal source ``trad`` semantics.
    """
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    z = np.asarray(existing, dtype=float).reshape(-1).copy()
    if z.size != epi.size:
        raise SpectrumContractError("incident spectrum and energy grid differ in length")
    canonical = canonical_spectrum_mode(mode)
    if canonical == "pow":
        z += _source_ispec4_component(float(trad), float(luminosity_1e38), epi)
    elif canonical == "bbody":
        z += _source_starf_component(float(trad), epi)
    elif canonical in {"brems", "bremss"}:
        source_trad = float(trad)
        if canonical == "bremss":
            source_trad = 1000.0 * float(trad) / SOURCE_BREMS_EV_PER_T7
        z = _source_ispec_brems_component(source_trad, float(luminosity_1e38), epi)
    elif canonical == "file":
        if file_spectrum is None:
            raise SpectrumContractError("spectrum='file' requires a loaded spectrum_file")
        z += _source_ispecg_component(file_spectrum, float(luminosity_1e38), epi)
    else:  # pragma: no cover
        raise SpectrumContractError(f"unhandled spectrum mode {canonical}")
    _source_ispecgg_inplace(z, epi, float(luminosity_1e38))
    return z


def initial_source_spectrum(
    *,
    mode: str,
    trad: float,
    luminosity_1e38: float,
    epi_eV: Sequence[float],
    spectrum_file: str | Path = "spct.dat",
    spectun: int = 0,
) -> tuple[np.ndarray, CanonicalSpectrumFile | None]:
    canonical = canonical_spectrum_mode(mode)
    file_data = read_canonical_spectrum_file(spectrum_file, spectun) if canonical == "file" else None
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    z = apply_source_spectrum_pass(
        np.zeros(epi.size, dtype=float),
        mode=canonical,
        trad=float(trad),
        luminosity_1e38=float(luminosity_1e38),
        epi_eV=epi,
        file_spectrum=file_data,
    )
    return z, file_data
