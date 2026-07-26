"""Exact source-profile and temporary-grid data for spectral qualification.

Production evaluates Gaussian/Voigt profiles and constructs the temporary
``linopac`` grid in C++.  Qualification can provide the complete Python source
translation of that grid so the native engine is tested only on the remaining
operations: trapezoid integration, continuum rebinning, and ordered commit.

The v0.6.46.2 profile-only oracle still allowed C++ to recompute ``nbinc``, the
Doppler width, temporary-grid coordinates, and ``optpp * profile``.  The
v0.6.48.3 exact-grid oracle removes those hidden cross-runtime rounding points.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from .radiation import nbinc

EXACT_GRID_MAGIC = 60472.0
EXACT_GRID_POINTS = 20000
EXACT_GRID_HEADER_VALUES = 6
EXACT_GRID_STRIDE = EXACT_GRID_HEADER_VALUES + 2 * EXACT_GRID_POINTS


@dataclass(frozen=True)
class SourceLinopacExactGrid:
    """Packed exact-grid qualification payload and useful diagnostics."""

    packed: np.ndarray
    mlmin_one_based: int
    mlmax_one_based: int
    ml1min_one_based: int
    ml1max_one_based: int
    valid_points: int


def _voigte(vs: float, a: float) -> float:
    ak = (
        -1.12470432, -0.15516677, 3.28867591, -2.34357915, 0.42139162,
        -4.48480194, 9.39456063, -6.61487486, 1.98919585, -0.22041650,
        0.554153432, 0.278711796, -0.188325687, 0.042991293,
        -0.003278278, 0.979895023, -0.962846325, 0.532770573,
        -0.122727278,
    )
    sqp = 1.772453851
    sq2 = 1.414213562
    v = abs(float(vs))
    aa = float(a)
    u = aa + v
    v2 = v * v
    if aa == 0.0:
        return 0.0 if v2 >= 100.0 else float(np.exp(-v2))
    if aa <= 0.2 and v >= 5.0:
        return aa * (15.0 + 6.0 * v2 + 4.0 * v2 * v2) / (4.0 * (v2 ** 3) * sqp)
    # voigte.f90 label 120 is reachable only when a>0.2.  Keep the
    # u>3.2 asymptotic test nested inside that source branch.
    if aa > 0.2 and (aa > 1.4 or u > 3.2):
        a2 = aa * aa
        uu = sq2 * (a2 + v2)
        u2 = 1.0 / (uu * uu)
        return sq2 / sqp * aa / uu * (
            1.0 + u2 * (3.0 * v2 - a2)
            + u2 * u2 * (15.0 * v2 * v2 - 30.0 * v2 * a2 + 3.0 * a2 * a2)
        )
    ex = 0.0 if v2 >= 100.0 else float(np.exp(-v2))
    quo = 1.0
    start = 0
    if v >= 2.4:
        quo = 1.0 / (v2 - 1.5)
        start = 10
    elif v >= 1.3:
        start = 5
    h1 = quo * (
        ak[start]
        + v * (ak[start + 1] + v * (ak[start + 2] + v * (ak[start + 3] + v * ak[start + 4])))
    )
    if aa <= 0.2:
        return h1 * aa + ex * (1.0 + aa * aa * (1.0 - 2.0 * v2))
    pqs = 2.0 / sqp
    h1p = h1 + pqs * ex
    h2p = pqs * h1p - 2.0 * v2 * ex
    h3p = (pqs * (1.0 - ex * (1.0 - 2.0 * v2)) - 2.0 * v2 * h1p) / 3.0 + pqs * h2p
    h4p = (2.0 * v2 * v2 * ex - pqs * h1p) / 3.0 + pqs * h3p
    psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]))
    return psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p))))


def _source_geometry(
    *,
    line_energy_eV: float,
    vturb_km_s: float,
    temperature_1e4K: float,
    atomic_mass_amu: float,
    natural_width_eV: float,
    epi: Sequence[float],
    ncn2: int,
) -> tuple[np.ndarray, int, float, float, float] | None:
    grid = np.asarray(epi, dtype=np.float64).reshape(-1)
    n = int(ncn2)
    e0 = float(line_energy_eV)
    if n < 3 or grid.size < n or e0 <= 0.0 or e0 <= float(grid[0]) or e0 >= float(grid[n - 1]):
        return None
    ml1 = max(2, min(n - 1, int(nbinc(e0, grid, n))))
    mass = max(float(atomic_mass_amu), 1.0e-30)
    vth = 12.9 * float(np.sqrt(float(temperature_1e4K) / mass))
    deleturb = e0 * (float(vturb_km_s) / 3.0e5)
    deleth = e0 * (vth / 3.0e5)
    dele = float(np.sqrt(deleth * deleth + deleturb * deleturb))
    if not math.isfinite(dele) or dele <= 0.0:
        return None
    aasmall = float(natural_width_eV) / (1.0e-24 + dele) / 12.56
    e00 = float(grid[ml1 - 1])
    deleepi = float(grid[ml1] - grid[ml1 - 1])
    ncut = max(1, min(int(deleepi / dele), EXACT_GRID_POINTS // 10))
    deleused = deleepi / float(ncut)
    return grid, ml1, dele, aasmall, deleused


def source_linopac_profile_samples(
    *,
    line_energy_eV: float,
    vturb_km_s: float,
    temperature_1e4K: float,
    atomic_mass_amu: float,
    natural_width_eV: float,
    epi: Sequence[float],
    ncn2: int,
    radius: int = 10,
) -> np.ndarray:
    """Return center, negative, positive samples through ``radius``."""
    radius = int(radius)
    if radius < 0:
        raise ValueError("radius must be non-negative")
    values = np.zeros(2 * radius + 1, dtype=np.float64)
    geometry = _source_geometry(
        line_energy_eV=line_energy_eV,
        vturb_km_s=vturb_km_s,
        temperature_1e4K=temperature_1e4K,
        atomic_mass_amu=atomic_mass_amu,
        natural_width_eV=natural_width_eV,
        epi=epi,
        ncn2=ncn2,
    )
    if geometry is None:
        return values
    grid, ml1, dele, aasmall, deleused = geometry
    e0 = float(line_energy_eV)
    e00 = float(grid[ml1 - 1])

    def profile(energy: float, threshold: float) -> float:
        delet = (float(energy) - e0) / dele
        if aasmall > threshold:
            return float(_voigte(abs(delet), aasmall) / 1.772)
        return float(np.exp(-delet * delet) / 1.772)

    values[0] = profile(e00, 1.0e-6)
    for offset in range(1, radius + 1):
        values[2 * offset - 1] = profile(e00 - float(offset) * deleused, 1.0e-9)
        values[2 * offset] = profile(e00 + float(offset) * deleused, 1.0e-9)
    return values


def source_linopac_exact_grid(
    *,
    optpp: float,
    line_energy_eV: float,
    vturb_km_s: float,
    temperature_1e4K: float,
    atomic_mass_amu: float,
    natural_width_eV: float,
    epi: Sequence[float],
    ncn2: int,
) -> SourceLinopacExactGrid:
    """Return the complete source temporary grid and opacity samples.

    The packed layout is::

        magic, mlmin, mlmax, ml1min, ml1max, valid_points,
        etpp[0:20000], optpp2[0:20000]

    Indices in the header are one-based, matching the translated Fortran.
    ``optpp2`` already includes the exact Python ``optpp * profile`` operation.
    """
    packed = np.zeros(EXACT_GRID_STRIDE, dtype=np.float64)
    packed[0] = EXACT_GRID_MAGIC
    geometry = _source_geometry(
        line_energy_eV=line_energy_eV,
        vturb_km_s=vturb_km_s,
        temperature_1e4K=temperature_1e4K,
        atomic_mass_amu=atomic_mass_amu,
        natural_width_eV=natural_width_eV,
        epi=epi,
        ncn2=ncn2,
    )
    if geometry is None or float(optpp) <= 0.0:
        return SourceLinopacExactGrid(packed, EXACT_GRID_POINTS, 1, 1, 1, 0)

    grid, ml1, dele, aasmall, deleused = geometry
    n = int(ncn2)
    e0 = float(line_energy_eV)
    e00 = float(grid[ml1 - 1])
    etpp = packed[EXACT_GRID_HEADER_VALUES:EXACT_GRID_HEADER_VALUES + EXACT_GRID_POINTS]
    optpp2 = packed[EXACT_GRID_HEADER_VALUES + EXACT_GRID_POINTS:]
    ml2 = EXACT_GRID_POINTS // 2
    etpp[ml2 - 1] = e00

    def profile(energy: float, threshold: float) -> float:
        delet = (float(energy) - e0) / dele
        if aasmall > threshold:
            return float(_voigte(abs(delet), aasmall) / 1.772)
        return float(np.exp(-delet * delet) / 1.772)

    optpp2[ml2 - 1] = float(optpp) * profile(e00, 1.0e-6)
    mlmin = EXACT_GRID_POINTS
    mlmax = 1
    valid = 1
    # Source ldon can never become true in this port because ml1min/ml1max are
    # intentionally not updated inside the construction loop.  Execute the
    # complete source scan directly and retain only valid temporary-grid cells.
    for offset in range(1, EXACT_GRID_POINTS // 2 + 1):
        for direction in (-1, 1):
            mlm = ml2 + direction * offset
            etptst = e00 + float(direction * offset) * deleused
            if 1 <= mlm <= EXACT_GRID_POINTS and 0.0 < etptst < float(grid[n - 1]):
                mlmin = min(mlmin, mlm)
                mlmax = max(mlmax, mlm)
                etpp[mlm - 1] = etptst
                optpp2[mlm - 1] = float(optpp) * profile(etptst, 1.0e-9)
                valid += 1

    if mlmin > mlmax:
        ml1min = ml1max = 1
    else:
        ml1min = int(nbinc(float(etpp[mlmin - 1]), grid, n))
        ml1max = int(nbinc(float(etpp[mlmax - 1]), grid, n))
    packed[1] = float(mlmin)
    packed[2] = float(mlmax)
    packed[3] = float(ml1min)
    packed[4] = float(ml1max)
    packed[5] = float(valid)
    return SourceLinopacExactGrid(
        np.ascontiguousarray(packed), mlmin, mlmax, ml1min, ml1max, valid
    )


__all__ = [
    "EXACT_GRID_MAGIC",
    "EXACT_GRID_POINTS",
    "EXACT_GRID_HEADER_VALUES",
    "EXACT_GRID_STRIDE",
    "SourceLinopacExactGrid",
    "source_linopac_profile_samples",
    "source_linopac_exact_grid",
]
