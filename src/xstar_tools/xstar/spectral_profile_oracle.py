"""Exact source-profile samples for spectral qualification.

The production native opacity path evaluates Gaussian/Voigt samples in C++.
Qualification can instead supply the complete source-ordered profile sample
stream computed with NumPy/Python arithmetic, while C++ still owns temporary
energy-grid traversal, trapezoid accumulation, rebinning, and array commit.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .radiation import nbinc


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
    if aa > 1.4 or u > 3.2:
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
    """Return center, negative, positive samples through ``radius``.

    The order matches ``xstar_opacity_apply_line_profile_v1``:
    ``center, -1, +1, -2, +2, ...``.  Radius 10000 covers the complete
    source temporary-grid scan because ``nbtpp`` is 20000.
    """
    radius = int(radius)
    if radius < 0:
        raise ValueError("radius must be non-negative")
    values = np.zeros(2 * radius + 1, dtype=np.float64)
    grid = np.asarray(epi, dtype=np.float64).reshape(-1)
    n = int(ncn2)
    e0 = float(line_energy_eV)
    if n < 3 or grid.size < n or e0 <= 0.0 or e0 <= float(grid[0]) or e0 >= float(grid[n - 1]):
        return values
    ml1 = max(2, min(n - 1, int(nbinc(e0, grid, n))))
    mass = max(float(atomic_mass_amu), 1.0e-30)
    vth = 12.9 * float(np.sqrt(float(temperature_1e4K) / mass))
    deleturb = e0 * (float(vturb_km_s) / 3.0e5)
    deleth = e0 * (vth / 3.0e5)
    dele = float(np.sqrt(deleth * deleth + deleturb * deleturb))
    if not math.isfinite(dele) or dele <= 0.0:
        return values
    aasmall = float(natural_width_eV) / (1.0e-24 + dele) / 12.56
    e00 = float(grid[ml1 - 1])
    deleepi = float(grid[ml1] - grid[ml1 - 1])
    ncut = max(1, min(int(deleepi / dele), 2000))
    deleused = deleepi / float(ncut)

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


__all__ = ["source_linopac_profile_samples"]
