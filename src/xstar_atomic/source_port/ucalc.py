"""Source-faithful Python execution layer for ``xstarlib/src/ucalc.f90``.

The module owns the complete packed-record -> branch -> result contract used by
later matrix assembly.  All XSTAR data-type labels 1..102 are registered.  A
branch is never silently ignored: source-defined metadata/no-op labels return a
successful zero result and every physical label has a native Python execution
path.  Record-specific prerequisites such as level quantum numbers or a live
radiation grid are reported as structured ``blocked_missing_context`` results
rather than replaced by proxies.

The first implementation milestone deliberately keeps the original one-based
record semantics and names ``ans1``..``ans6`` / ``idest1``..``idest4``.  This
makes direct comparison with the Fortran probe products possible while the
remaining leaf routines are translated source-file by source-file.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np

from .atomic_database import XSTARMasterData

ERG_PER_EV = 1.602197e-12
XSTAR_KT_EV_PER_1E4K = 0.861707

# Current XSTAR ``constants.f90`` values used by the continuum-integration
# routines.  Keep these separate from historical formulas that literally use
# the older rounded coefficients above.
XSTAR_SOURCE_ERG_PER_EV = 1.602176634e-12
XSTAR_SOURCE_BOLTZMANN_ERG_K = 1.380649e-16
XSTAR_SOURCE_KT_EV_PER_1E4K = (
    XSTAR_SOURCE_BOLTZMANN_ERG_K * 1.0e4 / XSTAR_SOURCE_ERG_PER_EV
)


def _expo(value: float) -> float:
    return math.exp(min(max(float(value), -60.0), 60.0))


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _ee1expo(x: float) -> float:
    """Source translation of ``ee1expo.f90`` (E1(x)*exp(x))."""
    x = float(x)
    if x <= 0.0:
        return float("inf")
    if x >= 1.0:
        return (1.0 / x) * (0.250621 + x * (2.334733 + x)) / (1.68153 + x * (3.330657 + x))
    return (-math.log(x) - 0.57721566 + x * (0.99999193 + x * (-0.24991055 + x * (0.05519968 + x * (-0.00976004 + x * 0.0010707857))))) * _expo(x)


def _ff2(x: float) -> float:
    """Source translation of ``ff2.f90`` used by type 16."""
    q = (1.0, 2.1958e2, 2.0984e4, 1.1517e6, 4.0349e7, 9.4900e8, 1.5345e10, 1.7182e11, 1.3249e12, 6.9071e12, 2.3531e13, 4.9432e13, 5.7760e13, 3.0225e13, 3.3641e12)
    ppv = (1.0, 2.1658e2, 2.0336e4, 1.0911e6, 3.7114e7, 8.3963e8, 1.2889e10, 1.3449e11, 9.4002e11, 4.2571e12, 1.1743e13, 1.7549e13, 1.0806e13, 4.9776e11, 0.0)
    if x <= 0.0:
        return 0.0
    xprod = 1.0; pp = 0.0; qq = 0.0
    for pv, qv in zip(ppv, q):
        ptst = 1.0 / xprod
        if ptst < 1.0e20 and xprod < 1.0e24 / x:
            pp += pv / xprod; qq += qv / xprod; xprod *= x
    return pp / (1.0e-20 + qq) / x / x


def _linear_hunt(grid: Sequence[float], x: float) -> int:
    """Return a clamped zero-based lower bracket compatible with hunt3 use."""
    if len(grid) < 2:
        return 0
    if x <= grid[0]:
        return 0
    if x >= grid[-1]:
        return len(grid) - 2
    return max(0, min(int(np.searchsorted(np.asarray(grid), x, side="right") - 1), len(grid) - 2))


def _radiation_arrays(state: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if state is None:
        raise ValueError("live radiation state is required")
    epi = np.asarray(getattr(state, "epim_eV", getattr(state, "epi_eV", ())), dtype=float).reshape(-1)
    brem = np.asarray(getattr(state, "bremsam", getattr(state, "bremsa", ())), dtype=float).reshape(-1)
    bint = np.asarray(getattr(state, "bremsint", np.zeros_like(epi)), dtype=float).reshape(-1)
    n = int(epi.size)
    # bremsmap.f90 owns a caller tail at bremsint(ncn2m+1), and the translated
    # state may retain additional inactive capacity in bremsam/bremsint.  ucalc
    # consumes only rows 1:ncn2m, so require capacity rather than exact length
    # and return the active reduced-grid views.
    if (
        n < 3
        or brem.size < n
        or bint.size < n
        or np.any(np.diff(epi) <= 0)
        or not np.all(np.isfinite(epi))
        or not np.all(np.isfinite(brem[:n]))
        or not np.all(np.isfinite(bint[:n]))
    ):
        raise ValueError("invalid live radiation arrays")
    return epi, brem[:n], bint[:n]


def _nbinc(energy: float, epi: Sequence[float]) -> int:
    arr = np.asarray(epi, dtype=float)
    return max(0, min(int(np.searchsorted(arr, float(energy), side="right") - 1), len(arr) - 1))


def _xstar_nbinc_fortran_value(energy: float, epi: Sequence[float]) -> int:
    """Return the literal one-based integer value from ``nbinc.f90``.

    ``nbinc`` does not return a conventional lower bracket.  It calls
    ``huntf`` on the source's truncated logarithmic continuum range and then
    selects the nearer of the estimated grid point and its successor.  The
    numeric one-based result is retained because ``phint53hunt.f90`` uses it
    both directly and as ``nb1=nbinc(...)+1``.
    """
    arr = np.asarray(epi, dtype=float)
    n = int(arr.size)
    if n < 3:
        return 1
    numcon2 = max(2, n // 50)
    numcon3 = n - numcon2
    work = arr[:numcon3]
    x = float(energy)
    jlo = 1
    if x < 1.0e-34 or work[0] <= 1.0e-34 or work[-1] <= 1.0e-34:
        return jlo
    xtmp = max(x, float(work[1]))
    denom = math.log(float(work[-1]) / float(work[0]))
    if denom == 0.0:
        return jlo
    jlo = int((numcon3 - 1) * math.log(xtmp / float(work[0])) / denom) + 1
    if jlo < numcon3:
        tst = abs(math.log(x / (1.0e-34 + float(work[jlo - 1]))))
        tst2 = abs(math.log(x / (1.0e-34 + float(work[jlo]))))
        if tst2 < tst:
            jlo += 1
    return max(1, min(numcon3, jlo))


def _xstar_phint53hunt_pass_indices(nb1: int, nphint: int, nskip: int) -> list[int]:
    """Return literal one-based ``kl`` values from a phint53hunt pass.

    The Fortran loop does not force the final ``nphint`` endpoint into a pass;
    it stops after the last naturally reached ``kl=kl+nskp`` value.
    """
    kl = max(1, int(nb1) - 1)
    stop = int(nphint)
    step = max(1, int(nskip))
    out: list[int] = []
    while kl <= stop:
        out.append(kl)
        kl += step
    return out


def _xstar_enxt_step(
    *,
    threshold_ev: float,
    nb1_fortran: int,
    epi: Sequence[float],
    t_1e4: float,
    lfast: int,
    jk_fortran: int,
) -> tuple[int, int, int]:
    """Translate one call to ``enxt.f90`` using one-based indices."""
    arr = np.asarray(epi, dtype=float)
    n = int(arr.size)
    numcon2 = max(2, n // 50)
    numcon3 = n - numcon2
    bktm = XSTAR_SOURCE_KT_EV_PER_1E4K * float(t_1e4)
    if int(lfast) <= 2:
        nphint = n - numcon2
        nskip = 1
        nskip2 = 1
    elif int(lfast) == 3:
        nphint = _xstar_nbinc_fortran_value(
            max(3.0 * threshold_ev, threshold_ev + 3.0 * bktm), arr
        )
        nphint = max(nphint, int(nb1_fortran) + 1)
        nskip = max(1, int((nphint - int(nb1_fortran)) / 16))
        nskip2 = nskip
    else:
        nphint = _xstar_nbinc_fortran_value(1.0e4, arr)
        nskip = 1
        nskip2 = 1
    nskip1 = nskip
    epii = float(arr[max(1, min(n, int(jk_fortran))) - 1])
    exptst = (epii - float(threshold_ev)) / max(bktm, 1.0e-48)
    if exptst < 3.0:
        lrcalc = 1
        nskip = nskip1
    else:
        lrcalc = 0
        nskip = nskip2
    nphint = max(nphint, int(nb1_fortran) + nskip)
    nphint = min(nphint, numcon3)
    return int(nskip), int(nphint), int(lrcalc)


def _phintfo_exact(*, sigma_cm2: Sequence[float], threshold_ev: float, context: "UCalcContext", swrat: float) -> dict[str, float]:
    """Literal one-based translation of ``phintfo.f90`` scalar outputs."""
    epi, bremsa, _ = _radiation_arrays(context.radiation)
    sig = np.asarray(sigma_cm2, dtype=float)
    if sig.size != epi.size:
        raise ValueError("cross section must be mapped to the live radiation grid")
    n = int(epi.size)
    nb1 = _xstar_nbinc_fortran_value(threshold_ev, epi)
    numcon2 = max(2, n // 50)
    nphint = max(n - numcon2, nb1 + 1)
    nphint = min(nphint, n - numcon2)
    bktm = XSTAR_SOURCE_KT_EV_PER_1E4K * context.t
    rnist = 5.216e-21 * float(swrat) / max(context.t * context.tsq, 1.0e-48)
    sumr = sumh = sumh2 = sumi = sumc = sumc2 = 0.0
    tempr = tempi = tempro = tempio = 0.0
    atmp2 = atmp22 = 0.0
    ener = float(epi[nb1 - 1])
    opakab = 0.0
    kl = int(nb1)
    tst = 1.0e10
    eps = 1.0e-2
    n_steps = 0
    last_lrcalc = 0
    last_nskip = 1
    while kl <= nphint and (int(context.lfast) <= 2 or tst > eps):
        enero = ener
        ener = float(epi[kl - 1])
        epii = ener
        sgtmp = max(float(sig[kl - 1]), 0.0)
        bremtmp = float(bremsa[kl - 1]) / 25.3
        tempro = tempr
        tempr = 25.3 * sgtmp * bremtmp / max(epii, 1.0e-48)
        deld = ener - enero
        tst = (tempr + tempro) * deld / 2.0
        sumr += tst
        sumh += (tempr * ener + tempro * enero) * deld * XSTAR_SOURCE_ERG_PER_EV / 2.0
        sumh2 += (
            tempr * (ener - threshold_ev)
            + tempro * (enero - threshold_ev)
        ) * deld * XSTAR_SOURCE_ERG_PER_EV / 2.0
        exptst = max(1.0e-36, (epii - threshold_ev) / max(bktm, 1.0e-48))
        exptmp = _expo(-exptst)
        bbnurj = min(epii, 2.0e4) ** 3 * 1.571e22
        tempi1 = rnist * bbnurj * exptmp * sgtmp / max(epii, 1.0e-48)
        tempi2 = rnist * bremtmp * exptmp * sgtmp / max(epii, 1.0e-48)
        tempi = tempi1 + tempi2
        atmp2o = atmp2
        atmp2 = tempi1 * epii
        atmp22o = atmp22
        atmp22 = tempi1 * (epii - threshold_ev)
        sumi += (tempi + tempio) * deld / 2.0
        sumc += (atmp2 + atmp2o) * deld * XSTAR_SOURCE_ERG_PER_EV / 2.0
        sumc2 += (atmp22 + atmp22o) * deld * XSTAR_SOURCE_ERG_PER_EV / 2.0
        optmp = context.abund1 * sgtmp * context.hydrogen_density_cm3
        if kl <= nb1 + 1:
            opakab = optmp
        tempio = tempi
        n_steps += 1
        last_nskip, nphint, last_lrcalc = _xstar_enxt_step(
            threshold_ev=threshold_ev, nb1_fortran=nb1, epi=epi,
            t_1e4=context.t, lfast=context.lfast, jk_fortran=kl,
        )
        kl += last_nskip
    ne = context.electron_density_cm3
    return {
        "ans1": sumr, "ans2": ne * sumi, "ans3": sumh, "ans4": ne * sumc,
        "ans5": sumh2, "ans6": ne * sumc2, "opakab": opakab,
        "nb1": nb1, "nphint": nphint,
        "n_integration_steps": n_steps,
        "last_nskip": last_nskip, "last_lrcalc": last_lrcalc,
        "grid_index_semantics": "one_based_nbinc_huntf_nearest",
        "source_bktm_eV": bktm,
        "source_erg_per_eV": XSTAR_SOURCE_ERG_PER_EV,
        "source_boltzmann_erg_K": XSTAR_SOURCE_BOLTZMANN_ERG_K,
    }


def _find53_cross_section(energy_ryd: np.ndarray, sigma_cm2: np.ndarray, efnd_ryd: float) -> float:
    """Translate ``find53.f90`` interpolation/extrapolation."""
    if energy_ryd.size < 2 or efnd_ryd < 0.0 or efnd_ryd > float(energy_ryd[-1]):
        return 0.0
    j = int(np.searchsorted(energy_ryd, efnd_ryd, side="right") - 1)
    j = max(0, min(j, energy_ryd.size - 2))
    e0, e1 = float(energy_ryd[j]), float(energy_ryd[j + 1])
    s0, s1 = max(float(sigma_cm2[j]), 0.0), max(float(sigma_cm2[j + 1]), 0.0)
    if j + 1 == energy_ryd.size - 1 and e0 > 0.0 and e1 > 0.0 and efnd_ryd > 0.0:
        slope = math.log(max(s1, 1.0e-26) / max(s0, 1.0e-26)) / math.log(max(e1, 1.0e-26) / max(e0, 1.0e-26))
        return max(0.0, s0 * (efnd_ryd / e0) ** slope)
    if e1 == e0:
        return max(s0, 0.0)
    f = (efnd_ryd - e0) / (e1 - e0)
    return max(0.0, s0 + f * (s1 - s0))


def _phint53hunt_exact(
    *, energy_above_threshold_ryd: Sequence[float], cross_section_cm2: Sequence[float],
    threshold_ev: float, context: "UCalcContext", swrat: float, crit: float = 0.01,
) -> dict[str, float | int | str]:
    """Translate ``phint53hunt.f90`` for the type-99 live-grid branch.

    Continuum-bin indices are retained in their literal one-based Fortran form
    until an array access is made.  In particular, source ``nb1`` is
    ``nbinc(eth)+1`` whereas source ``nphint`` is ``nbinc(emaxx)``.
    """
    egrid = np.asarray(energy_above_threshold_ryd, dtype=float)
    sigma = np.asarray(cross_section_cm2, dtype=float)
    if egrid.size < 2 or egrid.size != sigma.size:
        return {"status": "not_evaluated_bad_cross_section_grid"}
    epi, bremsa, _ = _radiation_arrays(context.radiation)
    n = int(epi.size)
    numcon2 = max(2, n // 50)
    numcon3 = n - numcon2

    # phint53hunt.f90: nb1=nbinc(ethi,epi,ncn2)+1
    nbinc_threshold = _xstar_nbinc_fortran_value(threshold_ev, epi)
    nb1 = nbinc_threshold + 1
    if nb1 >= numcon3:
        return {
            "status": "not_evaluated_threshold_above_guard_tail",
            "nbinc_threshold_fortran": nbinc_threshold,
            "nb1_fortran": nb1,
        }

    emax = threshold_ev + float(egrid[-1]) * 13.605692
    nphint = _xstar_nbinc_fortran_value(emax, epi)
    ndelt = max(nphint - nb1, 1)
    itmp = int(math.log(float(ndelt)) / 0.69315 + 0.5)
    while True:
        ndelt = 2 ** itmp
        nphint = nb1 + ndelt
        etst = 0.0
        if nphint <= numcon3:
            etst = (float(epi[nphint - 1]) - threshold_ev) / 13.605692
        if nphint > numcon3 or etst > float(egrid[-1]):
            itmp -= 1
            if itmp > 1:
                continue
        break

    t = context.t
    bktm = XSTAR_SOURCE_KT_EV_PER_1E4K * t
    rnist = 5.216e-21 * float(swrat) / max(t * math.sqrt(max(t, 0.0)), 1.0e-48)
    luse = np.zeros(n, dtype=np.int8)
    ansar1 = np.zeros(n, dtype=float)
    ansar2 = np.zeros(n, dtype=float)
    nskip = ndelt
    npass = 0
    sumr = sumh = sumi = sumc = sumh2 = sumc2 = 0.0
    tst1 = tst2 = tst3 = tst4 = float("inf")
    last_pass_indices: list[int] = []
    cached_atmp22_stale_reuses = 0

    while (
        (tst3 > crit or tst1 > crit or tst2 > crit or tst4 > crit or sumi <= 1.0e-24)
        and nskip > 1
    ):
        npass += 1
        nskip = max(1, nskip // 2)
        sumro, sumho, sumio, sumco = sumr, sumh, sumi, sumc
        sumr = sumh = sumi = sumc = sumh2 = sumc2 = 0.0
        tempr = tempi = atmp2 = atmp22 = 0.0
        ener = float(epi[nb1 - 1])
        pass_indices = _xstar_phint53hunt_pass_indices(nb1, nphint, nskip)
        last_pass_indices = pass_indices
        for kl in pass_indices:
            k = kl - 1
            enero = ener
            epii = float(epi[k])
            ener = epii
            bremtmp = float(bremsa[k]) / 25.3
            tempio, atmp2o, atmp22o = tempi, atmp2, atmp22
            sgtmp = 0.0
            if ener >= threshold_ev:
                if luse[k] == 0:
                    efnd = (ener - threshold_ev) / 13.605692
                    sgtmp = _find53_cross_section(egrid, sigma, efnd)
                    exptmp = _expo(-(epii - threshold_ev) / max(bktm, 1.0e-48))
                    bbnurj = min(2.0e4, epii) ** 3
                    tempi1 = rnist * bbnurj * sgtmp * exptmp * 1.571e22 / max(epii, 1.0e-48)
                    tempi2 = rnist * bremtmp * sgtmp * exptmp / max(epii, 1.0e-48)
                    tempi = tempi1 + tempi2
                    atmp2 = tempi * epii
                    atmp22 = tempi * (epii - threshold_ev)
                    ansar1[k] = sgtmp
                    ansar2[k] = atmp2
                else:
                    sgtmp = float(ansar1[k])
                    atmp2 = float(ansar2[k])
                    tempi = atmp2 / max(epii, 1.0e-48)
                    # Literal ``phint53hunt.f90`` behavior: the cached
                    # ``luse(kl)`` branch restores ``sgtmp``/``atmp2`` and
                    # recomputes ``tempi`` but does not assign ``atmp22``.
                    # The value therefore remains stale from the preceding
                    # loop point in the current integration pass.
                    cached_atmp22_stale_reuses += 1
            tempro = tempr
            tempr = 25.3 * sgtmp * bremtmp / max(epii, 1.0e-48)
            deld = ener - enero
            sumr += (tempr + tempro) * deld / 2.0
            sumh += (tempr * ener + tempro * enero) * deld / 2.0
            sumh2 += (tempr * (ener - threshold_ev) + tempro * (enero - threshold_ev)) * deld / 2.0
            sumi += (tempi + tempio) * deld / 2.0
            sumc += (atmp2 + atmp2o) * deld / 2.0
            sumc2 += (atmp22 + atmp22o) * deld / 2.0
            luse[k] = 1
        tst3 = abs((sumio - sumi) / (sumio + sumi + 1.0e-24))
        tst1 = abs((sumro - sumr) / (sumro + sumr + 1.0e-24))
        tst2 = abs((sumho - sumh) / (sumho + sumh + 1.0e-24))
        tst4 = abs((sumco - sumc) / (sumco + sumc + 1.0e-24))

    ne = context.electron_density_cm3
    return {
        "status": "evaluated_phint53hunt_live_grid",
        "pirt": sumr,
        "rrrt": ne * sumi,
        "piht": sumh * XSTAR_SOURCE_ERG_PER_EV,
        "rrcl": ne * sumc * XSTAR_SOURCE_ERG_PER_EV,
        "piht2": sumh2 * XSTAR_SOURCE_ERG_PER_EV,
        "rrcl2": ne * sumc2 * XSTAR_SOURCE_ERG_PER_EV,
        "npass": npass,
        "nbinc_threshold_fortran": nbinc_threshold,
        "nb1_fortran": nb1,
        "nphint_fortran": nphint,
        "ndelt_fortran": ndelt,
        "nskip_last_fortran": nskip,
        "last_pass_first_kl_fortran": last_pass_indices[0] if last_pass_indices else None,
        "last_pass_last_kl_fortran": last_pass_indices[-1] if last_pass_indices else None,
        "last_pass_includes_nphint": bool(last_pass_indices and last_pass_indices[-1] == nphint),
        "type99_phint53hunt_grid_policy": "literal_nbinc_plus_one_and_natural_kl_stride",
        "type99_phint53hunt_cached_atmp22_policy": "preserve_stale_previous_loop_value",
        "n_cached_atmp22_stale_reuses": cached_atmp22_stale_reuses,
        "source_bktm_eV": bktm,
        "source_erg_per_eV": XSTAR_SOURCE_ERG_PER_EV,
        "source_boltzmann_erg_K": XSTAR_SOURCE_BOLTZMANN_ERG_K,
    }


def _photo_result_swapped(dispatch: "SourceFaithfulUCalc", r: "UCalcRecord", c: "UCalcContext", s: "UCalcBranchSpec", *, sigma: Sequence[float], threshold: float, swrat: float, id1: int, id2: int, zero_reverse: bool = False) -> "UCalcResult":
    ph=_phintfo_exact(sigma_cm2=sigma,threshold_ev=threshold,context=c,swrat=swrat)
    a1,a2=ph["ans1"],ph["ans2"]; a3,a4=-ph["ans4"],-ph["ans3"]; a5,a6=-ph["ans6"],-ph["ans5"]
    # ``ucalc.f90`` zeroes the pre-swap inverse/recombination fields
    # ``ans2``, ``ans4``, and ``ans6`` for the type-59 ground/special branch,
    # then performs the universal heating/cooling swaps at label 9000.  In the
    # post-swap Python contract those same source fields are ``ans2``,
    # ``ans3``, and ``ans5``.  Zeroing ``ans4``/``ans6`` here would erase the
    # forward photo-heating terms and retain the inverse terms, the exact
    # opposite of the original source.
    if zero_reverse: a2=a3=a5=0.0
    return dispatch._ctx_result(r,s,ans1=a1,ans2=a2,ans3=a3,ans4=a4,ans5=a5,ans6=a6,idest1=id1,idest2=id2,opakab=ph["opakab"],diagnostics=ph,context_fields_used=("temperature_k","xpx","xee","radiation","levels","abund1"))


@dataclass(frozen=True)
class UCalcLevel:
    """One ion-local XSTAR level using the source ``rlev`` conventions."""

    index: int
    energy_ev: float = 0.0
    statistical_weight: float = 0.0
    ionization_potential_ev: float = 0.0
    continuum_energy_ev: float = 0.0
    principal_n: int | None = None
    orbital_l: int | None = None
    label: str = ""


@dataclass
class UCalcLevelTable:
    """One-based ion-local level table consumed by ``ucalc`` branches."""

    levels: Dict[int, UCalcLevel] = field(default_factory=dict)
    nlev: int = 0

    def get(self, index: int) -> UCalcLevel | None:
        return self.levels.get(int(index))

    def require(self, index: int) -> UCalcLevel:
        level = self.get(index)
        if level is None:
            raise KeyError(f"missing XSTAR ion-local level {index}")
        return level

    def energy(self, index: int, default: float = 0.0) -> float:
        level = self.get(index)
        return float(level.energy_ev) if level is not None else float(default)

    def weight(self, index: int, default: float = 0.0) -> float:
        level = self.get(index)
        return float(level.statistical_weight) if level is not None else float(default)


@dataclass(frozen=True)
class UCalcRecord:
    """Decoded packed ATDB record passed to one ``ucalc`` source branch."""

    record: int
    data_type: int
    rate_type: int
    continuation: int
    reals: Tuple[float, ...]
    integers: Tuple[int, ...]
    chars: bytes = b""
    parent_record: int = 0
    next_record: int = 0

    @classmethod
    def from_master(
        cls,
        master: XSTARMasterData,
        record: int,
        *,
        parent_record: int = 0,
        next_record: int = 0,
    ) -> "UCalcRecord":
        header = master.header(int(record))
        return cls(
            record=int(record),
            data_type=int(header.data_type),
            rate_type=int(header.rate_type),
            continuation=int(header.continuation),
            reals=tuple(float(x) for x in master.record_reals(record)),
            integers=tuple(int(x) for x in master.record_integers(record)),
            chars=bytes(master.record_chars(record)),
            parent_record=int(parent_record),
            next_record=int(next_record),
        )

    @property
    def ion_index(self) -> int:
        return int(self.integers[-1]) if self.integers else 0


@dataclass
class UCalcContext:
    """Runtime arguments corresponding to the non-record inputs of ``ucalc``.

    Temperature is stored in Kelvin at the Python boundary.  ``t`` and ``tsq``
    properties reproduce XSTAR's internal temperature in units of 1e4 K.
    ``extras`` is reserved for source-specific state that has not yet graduated
    to a typed field; each use is reported in result provenance.
    """

    temperature_k: float
    hydrogen_density_cm3: float = 0.0  # xpx
    electron_fraction_xee: float = 0.0
    neutral_h_density_cm3: float = 0.0  # xh0
    ionized_h_density_cm3: float = 0.0  # xh1
    turbulent_velocity_km_s: float = 0.0
    covering_fraction: float = 1.0
    ptmp1: float = 1.0
    ptmp2: float = 0.0
    abund1: float = 0.0
    abund2: float = 0.0
    jkion: int = 0
    nlev: int = 0
    lfast: int = 2
    indonly: bool = False
    levels: UCalcLevelTable = field(default_factory=UCalcLevelTable)
    radiation: Any = None
    derived_pointers: Any = None
    master: XSTARMasterData | None = None
    extras: MutableMapping[str, Any] = field(default_factory=dict)

    @property
    def t(self) -> float:
        return float(self.temperature_k) / 1.0e4

    @property
    def tsq(self) -> float:
        return math.sqrt(max(self.t, 0.0))

    @property
    def electron_density_cm3(self) -> float:
        return float(self.hydrogen_density_cm3) * float(self.electron_fraction_xee)

    @property
    def nlevp(self) -> int:
        return int(self.nlev or self.levels.nlev)


class UCalcStatus(str, Enum):
    EVALUATED = "evaluated"
    INDEX_ONLY = "index_only"
    SOURCE_NOOP = "source_noop_or_metadata"
    CONTEXT_BLOCKED = "blocked_missing_context"
    UNTRANSLATED = "blocked_untranslated_leaf"
    INVALID_RECORD = "invalid_record"
    SOURCE_REJECTED = "source_branch_rejected_record"


@dataclass(frozen=True)
class UCalcProvenance:
    source_file: str = "xstarlib/src/ucalc.f90"
    source_label: int = 0
    source_routines: Tuple[str, ...] = ()
    branch_name: str = ""
    implementation: str = ""
    validation_status: str = ""
    context_fields_used: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class UCalcResult:
    """Complete return contract of the translated ``ucalc`` subsystem."""

    record: int
    data_type: int
    rate_type: int
    status: UCalcStatus
    ans1: float = 0.0
    ans2: float = 0.0
    ans3: float = 0.0
    ans4: float = 0.0
    ans5: float = 0.0
    ans6: float = 0.0
    idest1: int = 0
    idest2: int = 0
    idest3: int = 0
    idest4: int = 0
    opakab: float = 0.0
    reason: str = ""
    provenance: UCalcProvenance = field(default_factory=UCalcProvenance)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status in {UCalcStatus.EVALUATED, UCalcStatus.INDEX_ONLY, UCalcStatus.SOURCE_NOOP}

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "record": self.record,
            "data_type": self.data_type,
            "rate_type": self.rate_type,
            "status": self.status.value,
            "ready": self.ready,
            "ans1": self.ans1,
            "ans2": self.ans2,
            "ans3": self.ans3,
            "ans4": self.ans4,
            "ans5": self.ans5,
            "ans6": self.ans6,
            "idest1": self.idest1,
            "idest2": self.idest2,
            "idest3": self.idest3,
            "idest4": self.idest4,
            "opakab": self.opakab,
            "reason": self.reason,
            "source_file": self.provenance.source_file,
            "source_label": self.provenance.source_label,
            "source_routines": ";".join(self.provenance.source_routines),
            "branch_name": self.provenance.branch_name,
            "implementation": self.provenance.implementation,
            "validation_status": self.provenance.validation_status,
            "context_fields_used": ";".join(self.provenance.context_fields_used),
            "notes": ";".join(self.provenance.notes),
        }
        out.update({f"diag_{k}": v for k, v in self.diagnostics.items()})
        return out


class UCalcExecutionError(RuntimeError):
    pass


class UCalcUntranslatedBranch(UCalcExecutionError):
    def __init__(self, result: UCalcResult):
        self.result = result
        super().__init__(
            f"XSTAR ucalc data type {result.data_type} is registered but its physical leaf routine "
            f"is not translated: {result.reason}"
        )


@dataclass(frozen=True)
class UCalcBranchSpec:
    data_type: int
    name: str
    source_routines: Tuple[str, ...] = ("ucalc",)
    category: str = "physical"
    implementation: str = "untranslated"
    validation_status: str = "not_validated"
    notes: Tuple[str, ...] = ()


# Labels that are metadata, reserved, or explicit ``go to 9000`` branches in
# the supplied ucalc.f90.  Returning zeros for these is source behavior, not a
# fallback approximation.
_SOURCE_NOOP_TYPES = {
    13, 14, 24, 29, 40, 41, 42, 43, 44, 45, 46, 47, 48, 52, 58, 61,
    78, 80, 83, 84, 87, 90, 91, 93, 94, 100,
}

_DATA_TYPE_NAMES: Dict[int, str] = {
    1: "radiative_recombination_aldrovandi_pequignot",
    2: "charge_exchange_h0_kingdon_ferland",
    3: "autoionization_hamilton_sarazin_chevalier",
    4: "legacy_bound_bound_radiative",
    5: "two_photon_collisional",
    6: "level_metadata",
    7: "dielectronic_recombination_aldrovandi_pequignot",
    8: "dielectronic_recombination_arnaud_raymond",
    9: "charge_exchange_he_h0",
    10: "charge_transfer_ionization_hplus",
    11: "two_photon_radiative",
    12: "hydrogenic_photoionization_alias_type36",
    13: "element_metadata",
    14: "ion_metadata",
    15: "bkh_photoionization",
    16: "arnaud_raymond_collisional_ionization",
    17: "hydrogenic_collisional_excitation_cota",
    18: "hydrogenic_radiative_recombination_cota",
    19: "hullac_photoionization",
    20: "charge_exchange_hplus_kingdon_ferland",
    21: "hydrogen_charge_exchange_dalgarno_butler",
    22: "dielectronic_recombination_storey",
    23: "clark_excited_photoionization",
    24: "clark_photoionization_continuation",
    25: "raymond_smith_collisional_ionization",
    26: "hydrogenic_collisional_ionization_cota",
    27: "hydrogenic_photoionization",
    28: "legacy_bound_bound_collision",
    29: "reserved_scaled_hydrogenic_ci",
    30: "hydrogenic_radiative_recombination_gould_thakur",
    31: "line_data_without_levels",
    32: "collisional_ionization_cota",
    33: "hullac_bound_bound_collision",
    34: "legacy_bound_bound_radiative_mendoza",
    35: "tabulated_bkh_photoionization",
    36: "hydrogenic_photoionization_no_l",
    37: "badnell_fe_3pq_dielectronic_recombination",
    38: "badnell_total_radiative_recombination",
    39: "badnell_total_dielectronic_recombination",
    49: "op_inner_shell_photoionization",
    50: "op_bound_bound_radiative",
    51: "op_chianti_burgess_tully_collision",
    53: "op_photoionization",
    54: "bautista_hlike_collision_hlike_ion",
    55: "bautista_hydrogenic_photoionization",
    56: "bautista_tabulated_collision_strength",
    57: "effective_charge_collisional_ionization",
    59: "verner_photoionization",
    60: "calloway_hlike_collision",
    62: "calloway_hlike_collision_alias",
    63: "bautista_hlike_collision_general_ion",
    64: "bautista_hydrogenic_photoionization_alias",
    65: "effective_charge_collisional_ionization_alias",
    66: "fine_structure_helike_collision",
    67: "keenan_helike_collision",
    68: "zhang_sampson_helike_collision",
    69: "kato_nakazaki_helike_collision",
    70: "superlevel_photoionization_old",
    71: "superlevel_to_spectroscopic_transition",
    72: "satellite_autoionization",
    73: "satellite_helike_collision",
    74: "dielectronic_delta_photoionization",
    75: "fe_xxiv_satellite_autoionization",
    76: "two_photon_decay",
    77: "superlevel_collision_from_type71",
    78: "auger_level_metadata",
    79: "fluorescence_line",
    80: "fe_ni_ground_collisional_ionization_metadata",
    81: "bhatia_fe_xix_collision",
    82: "fe_uta_radiative",
    83: "fe_uta_level_metadata",
    84: "iron_k_photoionization_binned",
    85: "iron_k_photoionization_summed",
    86: "iron_k_auger",
    88: "iron_inner_shell_resonance_excitation",
    89: "saf_bound_bound_radiative",
    91: "aped_line_wavelength_metadata",
    92: "aped_collision_strength",
    93: "op_photoionization_powerlaw_1",
    94: "op_photoionization_powerlaw_2",
    95: "bryans_collisional_ionization",
    96: "safranova_fe_xxiv_satellite",
    97: "palmeri_inner_shell_collisional_ionization",
    98: "chianti2016_burgess_tully_collision",
    99: "new_superlevel_photoionization",
    101: "spex_tabulated_collision",
    102: "spex_analytic_collision",
}

_SOURCE_CALLS: Dict[int, Tuple[str, ...]] = {
    15: ("bkhsgo", "drd", "phintfo"), 19: ("enxt", "phintfo"),
    23: ("drd", "enxt", "phintfo"), 27: ("enxt", "phintfo"),
    28: ("hunt3",), 31: ("drd", "linopac"), 34: ("linopac",),
    35: ("enxt", "hunt3", "phintfo"), 36: ("drd", "enxt", "phintfo"),
    49: ("dprinto", "drd", "phextrap", "phint53"),
    50: ("deleafnd", "drd", "enxt", "linopac"), 53: ("dprinto", "drd", "milne", "phextrap", "phint53"),
    54: ("anl1",), 55: ("drd", "enxt", "phintfo"), 56: ("hunt3",),
    57: ("calt57",), 59: ("drd", "enxt", "phintfo"),
    60: ("calt6062",), 62: ("calt6062",),
    63: ("amcrs", "anl1", "erc"), 64: ("enxt", "hphotx", "milne", "phintfo"),
    65: ("szirco",), 66: ("calt66",), 67: ("calt67",), 68: ("calt68",), 69: ("calt69",),
    70: ("calt70", "drd", "phint53hunt"), 71: ("calt71", "drd"), 72: ("calt72",),
    73: ("calt73",), 74: ("calt74",), 75: ("calt72",), 77: ("calt77",),
    82: ("drd", "linopac"), 84: ("phextrap", "phint5384"), 85: ("pexs", "phintfo"),
    88: ("dprinto", "drd", "phextrap", "phint53"), 89: ("deleafnd", "drd", "linopac"),
    92: ("calc_maxwell_rates", "calt66", "drd", "eint", "expint"),
    93: ("dprinto", "drd", "phint53pl"), 94: ("dprinto", "drd", "phint53pl"),
    95: ("eint",), 97: ("drd",), 99: ("calt99", "drd", "phint53hunt"), 101: ("hunt3",),
}


def complete_ucalc_branch_catalog() -> Dict[int, UCalcBranchSpec]:
    """Return a complete registry for every computed-GOTO label 1..102."""
    catalog: Dict[int, UCalcBranchSpec] = {}
    for dt in range(1, 103):
        category = "source_noop" if dt in _SOURCE_NOOP_TYPES else "physical"
        implementation = "source_noop" if category == "source_noop" else "untranslated"
        catalog[dt] = UCalcBranchSpec(
            data_type=dt,
            name=_DATA_TYPE_NAMES.get(dt, f"reserved_or_undocumented_type_{dt}"),
            source_routines=("ucalc",) + _SOURCE_CALLS.get(dt, ()),
            category=category,
            implementation=implementation,
            validation_status="source_control_flow_catalogued",
        )
    # Native source translations already present in the package.
    for dt, status in {
        1: "translated_formula", 2: "translated_formula", 3: "translated_formula", 4: "translated_formula",
        5: "translated_formula", 6: "translated_index_metadata", 7: "translated_formula",
        8: "translated_formula", 9: "translated_formula", 10: "translated_formula",
        11: "translated_formula", 12: "translated_alias_to_type36", 15: "translated_formula", 16: "translated_formula", 17: "translated_formula", 18: "translated_formula",
        19: "translated_formula", 20: "translated_formula", 21: "translated_formula", 22: "translated_formula", 23: "translated_formula",
        25: "translated_formula", 27: "translated_formula",
        26: "source_noop_by_code", 28: "translated_formula", 30: "translated_formula", 31: "translated_formula", 32: "source_noop_by_code",
        33: "translated_formula", 34: "translated_formula", 35: "translated_formula", 36: "translated_formula",
        37: "translated_formula", 38: "translated_formula",
        39: "translated_formula", 49: "translated_formula", 50: "validated_selected_system", 51: "validated_selected_system",
        54: "translated_formula", 55: "translated_formula", 59: "translated_formula",
        60: "translated_formula", 62: "translated_formula", 64: "translated_formula",
        65: "translated_formula", 66: "translated_formula",
        53: "translated_pending_real_context_parity", 56: "translated_formula",
        57: "translated_formula", 63: "translated_formula", 67: "translated_formula",
        68: "translated_formula", 69: "translated_formula", 70: "translated_formula", 71: "validated_selected_system",
        73: "translated_formula",
        72: "translated_formula", 74: "translated_formula", 75: "translated_formula", 76: "translated_formula",
        79: "translated_formula", 81: "translated_formula", 82: "translated_formula", 85: "translated_formula", 86: "translated_formula", 88: "translated_formula", 89: "translated_formula", 92: "translated_formula",
        77: "translated_formula", 95: "translated_formula", 96: "translated_formula", 97: "translated_formula",
        101: "translated_formula", 102: "translated_formula",
        98: "translated_formula", 99: "translated_formula",
    }.items():
        old = catalog[dt]
        catalog[dt] = replace(old, implementation="native_python", validation_status=status)
    return catalog


BranchEvaluator = Callable[[UCalcRecord, UCalcContext, UCalcBranchSpec], UCalcResult]


class SourceFaithfulUCalc:
    """Complete ``ucalc`` branch dispatcher with explicit execution coverage."""

    def __init__(self) -> None:
        self.catalog = complete_ucalc_branch_catalog()
        self._evaluators: Dict[int, BranchEvaluator] = {}
        self._register_builtin_evaluators()

    @property
    def registered_data_types(self) -> Tuple[int, ...]:
        return tuple(sorted(self.catalog))

    @property
    def native_data_types(self) -> Tuple[int, ...]:
        return tuple(sorted(dt for dt, spec in self.catalog.items() if spec.implementation == "native_python"))

    @property
    def source_noop_data_types(self) -> Tuple[int, ...]:
        return tuple(sorted(_SOURCE_NOOP_TYPES))

    @property
    def untranslated_data_types(self) -> Tuple[int, ...]:
        return tuple(sorted(dt for dt, spec in self.catalog.items() if spec.implementation == "untranslated"))

    def register(self, data_type: int, evaluator: BranchEvaluator, *, validation_status: str = "translated") -> None:
        dt = int(data_type)
        if dt not in self.catalog:
            raise KeyError(f"ucalc data type {dt} is outside the source computed-GOTO range 1..102")
        self._evaluators[dt] = evaluator
        self.catalog[dt] = replace(self.catalog[dt], implementation="native_python", validation_status=validation_status)

    def decode_record(self, master: XSTARMasterData, record: int, *, parent_record: int = 0, next_record: int = 0) -> UCalcRecord:
        return UCalcRecord.from_master(master, record, parent_record=parent_record, next_record=next_record)

    def evaluate_record_number(
        self,
        master: XSTARMasterData,
        record: int,
        context: UCalcContext,
        *,
        parent_record: int = 0,
        next_record: int = 0,
        strict: bool = True,
    ) -> UCalcResult:
        decoded = self.decode_record(master, record, parent_record=parent_record, next_record=next_record)
        if context.master is None:
            context.master = master
        return self.evaluate(decoded, context, strict=strict)

    def evaluate(self, record: UCalcRecord, context: UCalcContext, *, strict: bool = True) -> UCalcResult:
        spec = self.catalog.get(int(record.data_type))
        if spec is None:
            result = self._base_result(record, None, UCalcStatus.INVALID_RECORD, reason="data_type_outside_1_102")
            if strict:
                raise UCalcExecutionError(result.reason)
            return result

        # Several source labels jump directly to label 9000 before the
        # ``indonly`` endpoint block.  Preserve that ordering so metadata and
        # disabled source branches never acquire synthetic destinations.
        if spec.category == "source_noop":
            return self._base_result(record, spec, UCalcStatus.SOURCE_NOOP)

        if context.indonly:
            return self._index_only(record, context, spec)

        evaluator = self._evaluators.get(record.data_type)
        if evaluator is not None:
            try:
                return evaluator(record, context, spec)
            except Exception as exc:
                result = self._base_result(
                    record, spec, UCalcStatus.SOURCE_REJECTED,
                    reason=f"{exc.__class__.__name__}:{exc}",
                    diagnostics={"exception_type": exc.__class__.__name__},
                )
                if strict:
                    raise UCalcExecutionError(
                        f"ucalc type {record.data_type} record {record.record} failed: {exc}"
                    ) from exc
                return result

        result = self._base_result(
            record,
            spec,
            UCalcStatus.UNTRANSLATED,
            reason="called source leaf routines not yet translated: " + ",".join(spec.source_routines[1:] or ("inline_ucalc_branch",)),
        )
        if strict:
            raise UCalcUntranslatedBranch(result)
        return result

    def coverage(self, data_types: Iterable[int] | None = None) -> Dict[str, Any]:
        values = sorted(set(int(x) for x in (data_types if data_types is not None else self.catalog)))
        native = [x for x in values if x in self.native_data_types]
        noop = [x for x in values if x in self.source_noop_data_types]
        blocked = [x for x in values if x not in native and x not in noop]
        all_registered = set(values).issubset(self.catalog)
        return {
            "n_registered": len(values),
            "n_native": len(native),
            "n_source_noop": len(noop),
            "n_untranslated": len(blocked),
            "n_blocked": len(blocked),  # compatibility alias
            "native_data_types": native,
            "source_noop_data_types": noop,
            "untranslated_data_types": blocked,
            "blocked_data_types": blocked,  # compatibility alias
            "all_branches_registered": all_registered,
            "complete_source_branch_translation_ready": all_registered and len(blocked) == 0,
            # This means every physical branch has an implementation.  A
            # particular record may still need levels, density, or radiation.
            "complete_physical_execution_ready": len(blocked) == 0,
        }

    def _base_result(
        self,
        record: UCalcRecord,
        spec: UCalcBranchSpec | None,
        status: UCalcStatus,
        *,
        reason: str = "",
        diagnostics: Mapping[str, Any] | None = None,
        **values: Any,
    ) -> UCalcResult:
        ion = record.ion_index
        provenance = UCalcProvenance(
            source_label=record.data_type,
            source_routines=spec.source_routines if spec else (),
            branch_name=spec.name if spec else "invalid",
            implementation=spec.implementation if spec else "invalid",
            validation_status=spec.validation_status if spec else "invalid",
            notes=spec.notes if spec else (),
        )
        defaults = dict(
            record=record.record,
            data_type=record.data_type,
            rate_type=record.rate_type,
            status=status,
            idest3=ion,
            idest4=ion + 1 if ion else 0,
            reason=reason,
            provenance=provenance,
            diagnostics=dict(diagnostics or {}),
        )
        defaults.update(values)
        return UCalcResult(**defaults)

    def _index_only(self, record: UCalcRecord, context: UCalcContext, spec: UCalcBranchSpec) -> UCalcResult:
        i = record.integers
        nlev = context.nlevp
        dt = record.data_type
        id1 = id2 = 0
        # Source endpoint rules for translated/commonly active branches.
        if dt in {1, 3, 7, 8, 21, 22, 30, 37, 38, 39}:
            id1, id2 = 1, 0
        elif dt == 2:
            id1, id2 = 1, nlev
        elif dt in {4, 31, 34, 50, 51, 56, 66, 67, 68, 69, 81, 82, 89, 92, 98, 101} and len(i) >= 2:
            id1, id2 = i[0], i[1]
        elif dt == 5 and len(i) >= 2:
            id1, id2 = i[1], i[0]
        elif dt == 6:
            id1, id2 = (i[-2] if len(i) >= 2 else 0), 0
        elif dt in {9}:
            id1, id2 = (i[0], nlev + i[1] - 1) if len(i) > 1 else (1, nlev)
        elif dt == 10:
            id1, id2 = (i[0] if i else 0), nlev
        elif dt == 11 and len(i) >= 2:
            id1, id2 = i[1], i[0]
        elif dt == 53:
            # Label 53 uses the fourth packed integer from the end for the
            # parent-level offset; [-3] is the linked parent-ion/element field.
            id1 = i[-2] if len(i) >= 2 else 0
            parent_offset = i[-4] if len(i) >= 4 else 1
            id2 = nlev + parent_offset - 1
        elif dt == 49:
            # ucalc.f90 label 49 uses idat(np1i-1+nidt-3), i.e. the
            # fourth packed integer from the end.  The adjacent [-3] field
            # is idest4 and is overwritten later from the linked line record.
            id1 = i[-2] if len(i) >= 2 else (i[0] if i else 0)
            parent_offset = i[-4] if len(i) >= 4 else 1
            id2 = nlev + max(0, parent_offset) - 1
        elif dt == 59:
            # Source label 59 evaluates its idest4/idest3 guard before the
            # generic ``indonly`` return.  A guarded record therefore keeps
            # idest1/idest2 at their source-entry zero values instead of
            # acquiring synthetic compact endpoints.
            id3 = i[-1] if len(i) >= 1 else 0
            id4 = i[-3] if len(i) >= 3 else 0
            if id4 > id3 + 1:
                return self._base_result(
                    record, spec, UCalcStatus.INDEX_ONLY,
                    idest3=id3, idest4=id4,
                    reason="type59_source_zero_idest4_exceeds_idest3_plus_one",
                    diagnostics={
                        "type59_idest3": id3,
                        "type59_idest4": id4,
                        "type59_source_guard": "idest4_le_idest3_plus_one",
                        "type59_source_guard_triggered": True,
                        "type59_source_guard_action": "normal_zero_return_via_label_9000",
                    },
                )
            # Source label 59 has four distinct trailing endpoint fields:
            #
            #   idest2 offset = idat(np1i-1+nidt-3)  -> integers[-4]
            #   idest4        = idat(np1i+nidt-3)    -> integers[-3]
            #   idest1        = idat(np1i+nidt-2)    -> integers[-2]
            #   idest3        = idat(np1i+nidt-1)    -> integers[-1]
            #
            # The previous implementation incorrectly reused ``[-3]`` for
            # both the continuum offset and idest4.
            id1 = i[-2] if len(i) >= 2 else (i[0] if i else 0)
            parent_offset = i[-4] if len(i) >= 4 else 1
            id2 = max(nlev + parent_offset - 1, 1)
            id3 = i[-1] if len(i) >= 1 else 0
            id4 = i[-3] if len(i) >= 3 else 0
        elif dt in {12, 15, 19, 23, 27, 35, 36, 55, 64, 70, 85, 88, 99}:
            id1 = i[-2] if len(i) >= 2 else (i[0] if i else 0)
            parent_offset = i[-3] if len(i) >= 3 else 1
            id2 = max(nlev + parent_offset - 1, nlev)
        elif dt in {16, 25, 26, 32, 57, 65, 95, 97}:
            if record.rate_type == 5:
                id1 = i[0] if i else 1
                id2 = nlev + (i[1] - 1 if len(i) >= 3 else 0)
            else:
                id1 = id2 = 1
        elif dt in {17, 18, 28, 33, 54, 60, 62, 63, 73, 77, 102} and len(i) >= 2:
            id1, id2 = i[-4], i[-3] if len(i) >= 4 else (i[0], i[1])
        elif dt == 20 and len(i) >= 2:
            id1, id2 = i[0], nlev + i[1] - 1
        elif dt == 71 and len(i) >= 4:
            id1, id2 = i[-4], i[-3]
        elif dt in {72, 75, 96}:
            id1 = max(i[-3] if len(i) >= 3 else 1, 1)
            id2 = max((i[-2] if len(i) >= 2 else 1) + nlev - 1, 1)
        elif dt == 74:
            id1 = i[-2] if len(i) >= 2 else 0
            id2 = nlev + (i[-3] if len(i) >= 3 else 1) - 1
        elif dt == 76 and len(i) >= 2:
            id1, id2 = i[0], i[1]
        elif dt == 79 and len(i) >= 2:
            id1, id2 = i[0], i[1]
        elif dt == 86:
            id1 = max(i[-4] if len(i) >= 4 else 1, 1)
            id2 = max((i[-5] if len(i) >= 5 else 1) + nlev - 1, 1)
        values = {"idest1": id1, "idest2": id2}
        if dt == 59:
            values.update(idest3=id3, idest4=id4)
        return self._base_result(record, spec, UCalcStatus.INDEX_ONLY, **values)

    def _register_builtin_evaluators(self) -> None:
        for dt in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 49, 55, 59, 64, 70, 72, 74, 75, 76, 77, 79, 81, 82, 85, 86, 88, 89, 92, 95, 96, 97):
            self._evaluators[dt] = getattr(self, f"_eval_type{dt}")
        self._evaluators.update({
            50: self._eval_type50,
            51: self._eval_type51,
            53: self._eval_type53,
            54: self._eval_type54,
            56: self._eval_collision_generic,
            57: self._eval_type57,
            60: self._eval_type60,
            62: self._eval_type60,
            63: self._eval_collision_generic,
            65: self._eval_type65,
            66: self._eval_type66,
            67: self._eval_collision_generic,
            68: self._eval_collision_generic,
            69: self._eval_collision_generic,
            71: self._eval_type71,
            73: self._eval_type73,
            98: self._eval_collision_generic,
            101: self._eval_type101,
            102: self._eval_type102,
            99: self._eval_type99,
        })

    def _ctx_result(self, record: UCalcRecord, spec: UCalcBranchSpec, **values: Any) -> UCalcResult:
        diagnostics = values.pop("diagnostics", {})
        used = tuple(values.pop("context_fields_used", ()))
        result = self._base_result(record, spec, UCalcStatus.EVALUATED, diagnostics=diagnostics, **values)
        return replace(result, provenance=replace(result.provenance, context_fields_used=used))

    def _context_blocked(self, record: UCalcRecord, spec: UCalcBranchSpec, reason: str, *, diagnostics: Mapping[str, Any] | None = None) -> UCalcResult:
        return self._base_result(record, spec, UCalcStatus.CONTEXT_BLOCKED, reason=reason, diagnostics=diagnostics or {})

    def _parent_record_number(self, record: UCalcRecord, context: UCalcContext) -> int:
        if record.parent_record > 0:
            return int(record.parent_record)
        derived=context.derived_pointers
        if derived is not None and hasattr(derived,"npar"):
            try:
                return int(derived.npar[record.record])
            except Exception:
                try: return int(derived.npar[record.record-1])
                except Exception: pass
        return 0

    def _parent_record(self, record: UCalcRecord, context: UCalcContext) -> UCalcRecord | None:
        rec=self._parent_record_number(record,context)
        master=context.master
        if rec>0 and master is not None:
            try: return self.decode_record(master,rec)
            except Exception: return None
        return None

    def _atomic_mass(self, record: UCalcRecord, context: UCalcContext) -> float | None:
        value=_finite(context.extras.get("atomic_mass"))
        if value is not None and value>0: return value
        master=context.master; derived=context.derived_pointers
        if master is None or derived is None: return None
        rec=record.record
        try:
            # rate -> ion -> element in the source parent hierarchy
            ion=int(derived.npar[rec]); elem=int(derived.npar[ion]) if ion>0 else 0
            vals=master.record_reals(elem) if elem>0 else ()
            if len(vals)>1 and float(vals[1])>0: return float(vals[1])
        except Exception:
            pass
        return None

    def _linked_line_wavelength(self, record: UCalcRecord, context: UCalcContext, fallback: float) -> float:
        master=context.master; derived=context.derived_pointers
        if master is None or derived is None: return abs(float(fallback))
        try:
            line_index=int(derived.nplini[record.record]); line_record=int(derived.nplin[line_index])
            vals=master.record_reals(line_record)
            if len(vals): return abs(float(vals[0]))
        except Exception:
            pass
        return abs(float(fallback))

    def _level_threshold(self, context: UCalcContext, index: int) -> float:
        level=context.levels.require(index)
        if level.ionization_potential_ev>0:
            return max(level.ionization_potential_ev-level.energy_ev,0.0)
        if level.continuum_energy_ev>0:
            return max(level.continuum_energy_ev-level.energy_ev,0.0)
        continuum=context.levels.get(context.nlevp)
        return max((continuum.energy_ev if continuum else 0.0)-level.energy_ev,0.0)

    def _parent_destination_context(self, context: UCalcContext, idest2: int) -> tuple[float,float]:
        if idest2<=context.nlevp:
            return context.levels.energy(idest2),context.levels.weight(idest2)
        emap=context.extras.get("parent_level_energy_ev_by_destination",{})
        gmap=context.extras.get("parent_level_stat_weight_by_destination",{})
        energy=_finite(emap.get(idest2) if isinstance(emap,Mapping) else None, context.levels.energy(context.nlevp)) or 0.0
        weight=_finite(gmap.get(idest2) if isinstance(gmap,Mapping) else None, context.levels.weight(context.nlevp)) or 0.0
        return energy,weight

    def _leveltemp_destination_energy(
        self, context: UCalcContext, idest2: int, fallback: float
    ) -> float:
        """Return the mutable source ``leveltemp%rlev(1,idest2)`` value.

        For endpoints above the current ion's ``nlev``, XSTAR does not read
        the physical parent-level map in the final electron-energy correction.
        It reads the persistent ``leveltemp`` workspace, whose higher columns
        may retain values from a previously processed ion.
        """

        level = context.levels.get(idest2)
        return float(level.energy_ev) if level is not None else float(fallback)

    def _live_type53_state(self, context: UCalcContext) -> Any:
        from xstar_atomic.rates_type53 import Type53LiveRadiationState
        epi,brem,bint=_radiation_arrays(context.radiation)
        if isinstance(context.radiation,Type53LiveRadiationState): return context.radiation
        return Type53LiveRadiationState.from_sequences(epi,brem,bint,metadata=getattr(context.radiation,"metadata",{}))

    def _type53_from_pairs(self, record: UCalcRecord, context: UCalcContext, spec: UCalcBranchSpec, *, energy_ryd: Sequence[float], sigma_cm2: Sequence[float], threshold_ev: float, idest1: int, idest2: int, zero_reverse: bool = False, zero_all_heating: bool = False) -> UCalcResult:
        from xstar_atomic.rates_type53 import evaluate_type53_ucalc_record
        physical_dest_energy,dest_weight=self._parent_destination_context(context,idest2)
        continuum=context.levels.require(context.nlevp); bound=context.levels.require(idest1)
        leveltemp_dest_energy=self._leveltemp_destination_energy(
            context, idest2, physical_dest_energy
        )
        decoded={
            "energy_above_threshold_ryd":list(float(x) for x in energy_ryd),
            "cross_section_cm2":list(float(x) for x in sigma_cm2),
            "threshold_eV":float(threshold_ev),
            "bound_statistical_weight":bound.statistical_weight,
            "continuum_statistical_weight":continuum.statistical_weight,
            "destination_statistical_weight":dest_weight or continuum.statistical_weight,
            "continuum_energy_eV":continuum.energy_ev,
            "bound_energy_eV":bound.energy_ev,
            "destination_energy_eV":leveltemp_dest_energy,
            "physical_parent_destination_energy_eV":physical_dest_energy,
            "leveltemp_destination_energy_eV":leveltemp_dest_energy,
            "leveltemp_workspace_semantics":"persistent_higher_columns",
        }
        ev=evaluate_type53_ucalc_record(decoded,self._live_type53_state(context),temperature_k=context.temperature_k,xpx_cm3=context.hydrogen_density_cm3,electron_fraction_xee=context.electron_fraction_xee,ptmp1=context.ptmp1,ptmp2=context.ptmp2,lfast=context.lfast,abund1=context.abund1,abund2=context.abund2)
        ev = {
            **dict(ev),
            "physical_parent_destination_energy_eV": physical_dest_energy,
            "leveltemp_destination_energy_eV": leveltemp_dest_energy,
            "leveltemp_workspace_semantics": "persistent_higher_columns",
        }
        if ev.get("status")!="evaluated":
            return self._context_blocked(record,spec,str(ev.get("status")),diagnostics=ev)
        ans=[float(ev[f"ans{k}_{name}"]) for k,name in ((1,"photoionization_s^-1"),(2,"milne_recombination_s^-1"),(3,"cooling_signed_erg_s^-1"),(4,"heating_signed_erg_s^-1"),(5,"electron_pov_cooling_signed_erg_s^-1"),(6,"electron_pov_heating_signed_erg_s^-1"))]
        if zero_reverse: ans[1]=ans[2]=ans[4]=0.0
        if zero_all_heating: ans[2]=ans[3]=ans[4]=ans[5]=0.0
        return self._ctx_result(record,spec,ans1=ans[0],ans2=ans[1],ans3=ans[2],ans4=ans[3],ans5=ans[4],ans6=ans[5],idest1=idest1,idest2=idest2,opakab=float(ev.get("opakab_cm^-1",0.0)),diagnostics=ev,context_fields_used=("temperature_k","xpx","xee","radiation","levels","ptmp1","ptmp2"))

    # --- direct source translations for compact analytic branches ---
    def _eval_type1(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        arad, eta = r.reals[:2]
        ans1 = arad / c.t**eta * c.electron_density_cm3
        return self._ctx_result(r, s, ans1=ans1, idest1=1, context_fields_used=("temperature_k", "xpx", "xee"))

    def _eval_type2(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        id1, id2 = 1, c.nlevp
        if c.t > 5.0:
            return self._ctx_result(r, s, idest1=id1, idest2=id2, context_fields_used=("temperature_k",))
        a, b, cc, d = r.reals[:4]
        rate = a * _expo(math.log(c.t) * b) * max(0.0, 1.0 + cc * _expo(d * c.t)) * 1.0e-9
        ans1, ans2 = rate * c.neutral_h_density_cm3, 0.0
        if r.rate_type == 5:
            ans1, ans2 = 0.0, ans1
        return self._ctx_result(r, s, ans1=ans1, ans2=ans2, idest1=id1, idest2=id2,
                                context_fields_used=("temperature_k", "neutral_h_density_cm3"))

    def _eval_type3(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        cai, eai = r.reals[:2]
        ans1 = cai * _expo(-eai / (XSTAR_KT_EV_PER_1E4K * c.t)) / c.tsq * c.electron_density_cm3
        return self._ctx_result(r, s, ans1=ans1, idest1=1, idest2=1,
                                context_fields_used=("temperature_k", "xpx", "xee"))

    def _eval_type5(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        i = r.integers
        if len(i) < 2:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type5_requires_two_level_indices")
        id1, id2 = i[1], i[0]
        up, lo = c.levels.require(id1), c.levels.require(id2)
        eex = abs(lo.energy_ev - up.energy_ev)
        coef, power = r.reals[4], r.reals[5]
        base = 8.629e-8 * coef * c.t**power
        ans2 = base / up.statistical_weight
        ans1 = base * _expo(-eex / (XSTAR_KT_EV_PER_1E4K * c.t)) / lo.statistical_weight
        return self._ctx_result(r, s, ans1=ans1, ans2=ans2, idest1=id1, idest2=id2,
                                context_fields_used=("temperature_k", "levels"))

    def _eval_type6(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        id1 = r.integers[-2] if len(r.integers) >= 2 else 0
        return self._ctx_result(r, s, idest1=id1)

    def _eval_type7(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        adi, bdi, t0, t1 = r.reals[:4]
        rate = adi * 1.0e-6 * _expo(-t0 / c.t) * (1.0 + bdi * _expo(-t1 / c.t)) / (c.t * math.sqrt(c.t))
        return self._ctx_result(r, s, ans1=rate * c.electron_density_cm3, idest1=1,
                                context_fields_used=("temperature_k", "xpx", "xee"))

    def _eval_type8(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        dc, de = r.reals[:4], r.reals[4:8]
        rate = sum(dc[n] * _expo(-de[n] / (XSTAR_KT_EV_PER_1E4K * c.t)) for n in range(4))
        rate *= 1.0e-6 * c.t**-1.5
        return self._ctx_result(r, s, ans1=rate * c.electron_density_cm3, idest1=1,
                                context_fields_used=("temperature_k", "xpx", "xee"))

    def _eval_type9(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        a, b, cc, d = r.reals[:4]
        rate = a * min(c.t, 1000.0)**b * (1.0 + cc * _expo(d * c.t)) * 1.0e-9
        ans2 = rate * c.neutral_h_density_cm3 * 0.1
        if len(r.integers) > 1:
            id1, id2, ans2 = r.integers[0], c.nlevp + r.integers[1] - 1, ans2 / 6.0
        else:
            id1, id2 = 1, c.nlevp
        return self._ctx_result(r, s, ans2=ans2, idest1=id1, idest2=id2,
                                context_fields_used=("temperature_k", "neutral_h_density_cm3"))

    def _eval_type10(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        a, b, cc, d = r.reals[:4]
        eex = r.reals[6] if len(r.reals) >= 7 else 0.0
        rate = a * c.t**b * (1.0 + cc * _expo(d * c.t)) * _expo(-eex / c.t) * 1.0e-9
        return self._ctx_result(r, s, ans1=rate * c.ionized_h_density_cm3,
                                idest1=r.integers[0] if r.integers else 0, idest2=c.nlevp,
                                context_fields_used=("temperature_k", "ionized_h_density_cm3"))

    def _eval_type11(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        i = r.integers
        id2, id1 = i[0], i[1]
        dele = abs(c.levels.energy(id2) - c.levels.energy(id1))
        ggl, ggu = r.reals[2], r.reals[3]
        ans1 = 6.669e15 * r.reals[1] * ggl / (ggu * r.reals[0]**2)
        return self._ctx_result(r, s, ans1=ans1, ans4=ans1 * dele * ERG_PER_EV,
                                idest1=id1, idest2=id2, context_fields_used=("levels",))

    def _eval_type21(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        beta, al1, al2 = r.reals[:3]
        alpha = al1 if c.t < 1.0 else al2
        ans1 = beta * c.t**alpha * c.ionized_h_density_cm3
        return self._ctx_result(r, s, ans1=ans1, idest1=1,
                                context_fields_used=("temperature_k", "ionized_h_density_cm3"))

    def _eval_type22(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if c.t > 6.0:
            return self._ctx_result(r, s, idest1=1, context_fields_used=("temperature_k",))
        a, b, cc, d, e = r.reals[:5]
        rate = 1.0e-12 * (a / c.t + b + c.t * (cc + c.t*d)) * c.t**-1.5 * _expo(-e / c.t)
        ans1 = max(rate, 0.0) * c.electron_density_cm3
        return self._ctx_result(r, s, ans1=ans1, idest1=1,
                                context_fields_used=("temperature_k", "xpx", "xee"))

    def _eval_type30(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        nmx = r.integers[0]
        t6 = c.t / 100.0
        beta = float(nmx*nmx) / (6.34*t6)
        yy = beta
        vth = 3.10782e7 * math.sqrt(c.t)
        ypow = min(1.0, 0.06376 / yy / yy)
        fudge = 0.9*(1.0-ypow) + (1.0/1.5)*ypow
        phi1 = (1.735 + math.log(yy) + 1.0/(6.0*yy))*fudge/2.0
        phi2 = yy*(-1.202*math.log(yy)-0.298)
        phi = phi2 if yy < 0.2525 else phi1
        rate = 2.0*2.105e-22*vth*yy*phi
        return self._ctx_result(r, s, ans1=rate*c.electron_density_cm3, idest1=1,
                                context_fields_used=("temperature_k", "xpx", "xee"))

    def _eval_type4(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers) < 2 or len(r.reals) < 5:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type4_short_record")
        id1, id2 = r.integers[0], r.integers[1]
        if c.levels.energy(id1) < c.levels.energy(id2): id1, id2 = id2, id1
        elin, flin, mass = abs(r.reals[0]), r.reals[1], r.reals[4]
        gu, gl = c.levels.weight(id1), c.levels.weight(id2)
        if min(elin, gu, gl) <= 0.0:
            return self._base_result(r, s, UCalcStatus.SOURCE_REJECTED, reason="type4_bad_wavelength_or_weight")
        aij = 6.67e7 * gl * flin / gu / (elin * 1.0e-4) ** 2
        if flin <= 1.01e-12 or elin >= 1.0e9: aij = 1.0e5
        ans1 = aij * (c.ptmp1 + c.ptmp2)
        vtherm = math.sqrt((c.turbulent_velocity_km_s * 1.0e5) ** 2 + (1.29e6 / math.sqrt(max(mass / c.t, 1e-48))) ** 2)
        opakab = 0.02655 * flin * elin * 1.0e-8 / vtherm
        if elin > 0.99e9: opakab = 0.0
        ener = 12398.4016 / elin
        return self._ctx_result(r, s, ans1=ans1, ans4=ans1 * ener * ERG_PER_EV,
            idest1=id1, idest2=id2, opakab=opakab,
            context_fields_used=("temperature_k","turbulent_velocity_km_s","ptmp1","ptmp2","levels"))

    def _eval_type16(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        ekt = XSTAR_KT_EV_PER_1E4K * c.t
        if ekt <= 0.0 or len(r.reals) % 5:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type16_bad_temperature_or_layout")
        csum = csum2 = 0.0
        for k in range(0, len(r.reals), 5):
            eth, a, b, cc, d = r.reals[k:k+5]; xx = eth / ekt
            if xx <= 0.0: continue
            em1 = _ee1expo(xx); f1 = em1 / xx; f2 = _ff2(xx)
            fi = max(a*(1.0-xx*f1) + b*(1.0+xx-xx*(2.0+xx)*f1) + cc*f1 + d*xx*f2, 0.0)
            csum += fi * _expo(-xx) / xx; csum2 += fi / xx
        ne = c.electron_density_cm3
        ans1 = csum * 6.69e-7 / ekt**1.5 * ne
        gu = c.levels.weight(c.nlevp); gl = c.levels.weight(1)
        rinf = 2.08e-22 * gl / max(gu,1e-48) / max(c.t*c.tsq,1e-48)
        ans2 = csum2 * 6.69e-7 / ekt**1.5 * ne * rinf * ne
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,idest1=1,idest2=c.nlevp if r.rate_type==5 else 1,
            context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type17(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<2: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type17_short_record")
        a,b=r.integers[0],r.integers[1]
        lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a)
        de=c.levels.energy(up)-c.levels.energy(lo); gu=c.levels.weight(up); gl=c.levels.weight(lo)
        ans2=8.629e-8*r.reals[0]*c.t**r.reals[1]/max(gu,1e-48)
        ans1=ans2*gu/max(gl,1e-48) if XSTAR_KT_EV_PER_1E4K*c.t>de/20.0 else 0.0
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,idest1=lo,idest2=up,context_fields_used=("temperature_k","levels"))

    def _eval_type18(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<4 or not r.integers: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type18_short_record")
        a,b,cc,ttz=r.reals[:4]; algt=min(max(math.log10(c.t/max(ttz,1e-48))+4.0,3.5),7.5)
        ans1=10.0**(a+b*(algt-cc)**2)/c.t/1.0e4*c.electron_density_cm3
        return self._ctx_result(r,s,ans1=ans1,idest1=r.integers[0],context_fields_used=("temperature_k","xpx","xee"))

    def _eval_type20(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type20_short_record")
        a,b,cc,d,e=r.reals[:5]; rate=a*c.t**b*(1.0+cc*_expo(d*c.t))*_expo(-e/c.t)*1e-9
        return self._ctx_result(r,s,ans1=rate*c.ionized_h_density_cm3,idest1=1,idest2=c.nlevp,
            context_fields_used=("temperature_k","ionized_h_density_cm3"))

    def _eval_type25(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type25_short_record")
        e,a,b,cc,d=r.reals[:5]; chir=c.temperature_k/(11590.0*e)
        id1=(r.integers[-2] if r.rate_type==5 and len(r.integers)>=2 else 1); id2=c.nlevp if r.rate_type==5 else 1
        if chir<=0.0115: return self._ctx_result(r,s,idest1=id1,idest2=id2,context_fields_used=("temperature_k",))
        chi=max(chir,0.1); ch2=chi*chi; ch3=ch2*chi
        alpha=(.001193+.9764*chi+.6604*ch2+.02590*ch3)/(1.0+1.488*chi+.2972*ch2+.004925*ch3)
        beta=(-.0005725+.01345*chi+.8691*ch2+.03404*ch3)/(1.0+2.197*chi+.2457*ch2+.002503*ch3)
        ch=1.0/chi; fchi=.3*ch*(a+b*(1.0+ch)+(cc-(a+b*(2.0+ch))*ch)*alpha+d*beta*ch)
        cion=2.2e-6*math.sqrt(chir)*fchi/(e*math.sqrt(e)); ne=c.electron_density_cm3
        raw=cion*ne; gu=c.levels.weight(c.nlevp); gl=c.levels.weight(id1)
        rinf=2.08e-22*gl/max(gu,1e-48)/max(c.t*c.tsq,1e-48)
        ans2=raw*rinf*ne; ans1=raw*_expo(-1.0/chir)
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*e*ERG_PER_EV,ans6=ans1*e*ERG_PER_EV,
            idest1=id1,idest2=id2,context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type26(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        return self._ctx_result(r,s)

    def _eval_type28(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type28_short_record")
        a,b=r.integers[:2]; lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a)
        nind=4
        if len(r.reals)>=12:
            j=_linear_hunt(r.reals[-4:],c.t); nind=len(r.reals)-8+j-1
        cijpp=r.reals[max(0,min(nind,len(r.reals)-1))]; elin=abs(r.reals[0]); gu=c.levels.weight(up); gl=c.levels.weight(lo)
        if elin<=1e-24: return self._ctx_result(r,s,idest1=lo,idest2=up)
        ex=_expo(-(12398.4016/elin)/(XSTAR_KT_EV_PER_1E4K*c.t)); cji=8.626e-8*cijpp/c.tsq/max(gu,1e-48)
        cij=cji*gu*ex/c.tsq/max(gl,1e-48); ne=c.electron_density_cm3
        return self._ctx_result(r,s,ans1=cij*ne,ans2=cji*ne,idest1=lo,idest2=up,
            context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type32(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        return self._ctx_result(r,s,idest1=r.integers[0] if r.integers else 0)

    def _eval_type33(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<4: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type33_short_record")
        lo,up=r.integers[0],r.integers[1]; elin=abs(r.reals[0]); gu=c.levels.weight(up); gl=c.levels.weight(lo)
        if elin<=1e-24: return self._ctx_result(r,s,idest1=lo,idest2=up)
        om=r.reals[3]; de=12398.4016/elin; ex=_expo(-de/(XSTAR_KT_EV_PER_1E4K*c.t)); ne=c.electron_density_cm3
        cij=8.626e-8*om*ex/c.tsq/max(gl,1e-48); cji=8.626e-8*om/c.tsq/max(gu,1e-48)
        return self._ctx_result(r,s,ans1=cij*ne,ans2=cji*ne,ans5=cji*ne*de*ERG_PER_EV,ans6=cij*ne*de*ERG_PER_EV,
            idest1=lo,idest2=up,context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type34(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type34_short_record")
        a,b=r.integers[:2]; up,lo=(a,b) if c.levels.energy(a)>=c.levels.energy(b) else (b,a)
        elin=abs(r.reals[0]); aij=r.reals[1]; mass=r.reals[4]; gu=c.levels.weight(up); gl=c.levels.weight(lo)
        if min(elin,gu,gl)<=0: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason="type34_bad_wavelength_or_weight")
        flin=aij*(elin*1e-8)**2*gu/(.667274*gl); ans1=aij*(c.ptmp1+c.ptmp2)
        vtherm=math.sqrt((c.turbulent_velocity_km_s*1e5)**2+(1.29e6/math.sqrt(max(mass/c.t,1e-48)))**2)
        opakab=.02655*flin*elin*1e-8/vtherm; ener=12398.4016/elin
        if elin>.99e9: opakab=0.0
        return self._ctx_result(r,s,ans1=ans1,ans4=ans1*ener*ERG_PER_EV,idest1=up,idest2=lo,opakab=opakab,
            context_fields_used=("temperature_k","turbulent_velocity_km_s","ptmp1","ptmp2","levels"))

    def _eval_type37(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        n=r.integers[0] if r.integers else min(4,len(r.reals)//2); ekt=XSTAR_KT_EV_PER_1E4K*c.t
        rate=sum(r.reals[k]*_expo(-r.reals[k+4]/ekt) for k in range(min(n,4,len(r.reals)-4)))*1e-6*c.t**-1.5
        return self._ctx_result(r,s,ans1=rate*c.electron_density_cm3,idest1=1,context_fields_used=("temperature_k","xpx","xee"))

    def _eval_type38(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<4: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type38_short_record")
        a,b,t0,t1=r.reals[:4]; t0/=1e4; t1/=1e4
        if len(r.reals)>4: b=b+r.reals[4]*_expo(-(r.reals[5]/1e4)/c.t)
        rate=a/(1e-48+(c.t/t0)**.5*(1+(c.t/t0)**.5)**(1-b)*(1+(c.t/t1)**.5)**(1+b))
        return self._ctx_result(r,s,ans1=rate*c.electron_density_cm3,idest1=1,context_fields_used=("temperature_k","xpx","xee"))

    def _eval_type39(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        n=len(r.reals)//2; rate=sum(r.reals[k]*_expo(-(r.reals[k+n]/1e4)/c.t) for k in range(n))*1e-6*c.t**-1.5
        return self._ctx_result(r,s,ans1=rate*c.electron_density_cm3,idest1=1,context_fields_used=("temperature_k","xpx","xee"))

    def _mapped_grid(self, c: UCalcContext) -> np.ndarray:
        return _radiation_arrays(c.radiation)[0]

    def _eval_type19(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<5 or not r.integers: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type19_short_record")
        epi=self._mapped_grid(c); eth=r.reals[4]; sig=np.zeros_like(epi)
        for k,e in enumerate(epi):
            if e>=eth:
                z=math.log(e/max(eth,1e-48)); alp=r.reals[0]+z*(r.reals[1]+z*(z*r.reals[2]+z*r.reals[3]))
                sig[k]=1e-18*_expo(alp)*13.606/max(eth,1e-48)
        id1=r.integers[0]; id2=c.nlevp; sw=c.levels.weight(id1)/max(c.levels.weight(id2),1e-48)
        return _photo_result_swapped(self,r,c,s,sigma=sig,threshold=eth,swrat=sw,id1=id1,id2=id2)

    def _eval_type27(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if not r.reals: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type27_short_record")
        epi=self._mapped_grid(c); eth=abs(c.levels.energy(c.nlevp)-c.levels.energy(1)); z=max(r.reals[0],1e-48); sig=np.zeros_like(epi)
        for k,e in enumerate(epi):
            if e>=eth:
                zap=e/eth-1.0; y=e/eth; yy=max(math.sqrt(max(zap,0.0)),1e-4)
                sig[k]=6.3e-18/z**2*y**-4*_expo(4.0-4.0*math.atan(yy)/yy)/(1.0-_expo(-6.2832/yy))
        id2=0 if r.rate_type==1 else c.nlevp; sw=c.levels.weight(1)
        return _photo_result_swapped(self,r,c,s,sigma=sig,threshold=eth,swrat=sw,id1=1,id2=id2)

    def _eval_type35(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<5 or len(r.integers)<3: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type35_short_record")
        eth=r.reals[0]; pairs=(len(r.reals)-1)//2; xs=np.asarray(r.reals[2:2+2*pairs:2],float); ys=np.asarray(r.reals[1:1+2*pairs:2],float)
        epi=self._mapped_grid(c); ef=(epi-eth)/13.605692; sig=np.where(epi>=eth,np.interp(ef,xs,ys,left=ys[0],right=ys[-1]),0.0)
        id1=r.integers[5] if len(r.integers)>5 else r.integers[-2]; id2=(r.integers[4] if len(r.integers)>4 else c.nlevp)-(r.integers[6] if len(r.integers)>6 else 0)
        sw=c.levels.weight(1)/max(c.levels.weight(c.nlevp),1e-48)
        return _photo_result_swapped(self,r,c,s,sigma=sig,threshold=eth,swrat=sw,id1=id1,id2=id2)

    def _hydrogenic_sigma_grid(self,c: UCalcContext,eth: float,sgth: float) -> np.ndarray:
        epi=self._mapped_grid(c); return np.where(epi>=eth,sgth*(epi/eth)**-3,0.0)

    def _eval_type36(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        id1=r.integers[-2] if len(r.integers)>=2 else 1; eth=c.levels.energy(c.nlevp)-c.levels.energy(id1)
        nq=min(10,r.integers[0] if r.integers else 1); z=float(c.extras.get("element_z",1)-c.extras.get("ion_stage",1)+1)
        sig=self._hydrogenic_sigma_grid(c,eth,6.3e-18*nq*nq/max(z*z,1e-48)); sw=c.levels.weight(id1)/max(c.levels.weight(c.nlevp),1e-48)
        return _photo_result_swapped(self,r,c,s,sigma=sig,threshold=eth,swrat=sw,id1=id1,id2=c.nlevp)

    def _eval_type55(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        id1=r.integers[-2] if len(r.integers)>=2 else 1; eth=c.levels.energy(c.nlevp)-c.levels.energy(id1)
        z=float(c.extras.get("element_z",1)-c.extras.get("ion_stage",1)); sig=self._hydrogenic_sigma_grid(c,eth,6.3e-18/max(z*z,1e-48))
        sw=c.levels.weight(id1)/max(c.levels.weight(c.nlevp),1e-48)
        return _photo_result_swapped(self,r,c,s,sigma=sig,threshold=eth,swrat=sw,id1=id1,id2=c.nlevp)

    def _eval_type59(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate the Verner bound-free branch at source label 59.

        v0.4.82 corrects three literal source-order/indexing errors exposed by
        C IV record 6077:

        * the compact six-real form starts its Verner coefficients at
          ``rdat(np1r+1)``, so Python must decode ``reals[1:6]`` rather than
          ``reals[:5]``;
        * the parent/continuum offset is the fourth integer from the end,
          while the third from the end is the separate ``idest4`` field;
        * source zeroing occurs before the universal ans3/ans4 and ans5/ans6
          swap, so the post-swap zero fields are ans2/ans3/ans5.
        """
        if len(r.reals)<6 or len(r.integers)<4:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type59_short_record")

        id3=int(r.integers[-1])
        id4=int(r.integers[-3])
        if id4 > id3 + 1:
            # Literal ucalc.f90 label-59 source guard:
            #
            #   if (idest4.gt.idest3+1) go to 9000
            #
            # Label 9000 is the normal return path.  ans1..ans6 and
            # idest1/idest2 were initialized to zero at routine entry, while
            # idest3/idest4 retain the values decoded immediately before the
            # guard.  This is an evaluated zero-rate record, not a blocked or
            # invalid record.  Treating it as SOURCE_REJECTED makes strict
            # calc_ion_rates abort on legitimate ATDB rows such as record
            # 5386.
            return self._base_result(
                r, s, UCalcStatus.EVALUATED,
                reason="type59_source_zero_idest4_exceeds_idest3_plus_one",
                idest3=id3, idest4=id4,
                diagnostics={
                    "type59_idest3": id3,
                    "type59_idest4": id4,
                    "type59_source_guard": "idest4_le_idest3_plus_one",
                    "type59_source_guard_triggered": True,
                    "type59_source_guard_action": "normal_zero_return_via_label_9000",
                },
            )

        eth=float(r.reals[0]); epi=self._mapped_grid(c); sig=np.zeros_like(epi)
        if len(r.reals)==9:
            _,emax,e0,s0,ya,pp,yw,y0,y1=(float(v) for v in r.reals); l2=0
            parameter_layout="nine_real_verner_fit"
        else:
            # Literal source assignments for nrdt /= 9.
            e0,s0,ya,pp,yw=(float(v) for v in r.reals[1:6])
            emax=math.nan; y0=y1=0.0
            l2=int(r.integers[2]) if len(r.integers)>2 else 0
            parameter_layout="six_real_verner_fit_threshold_then_coefficients"
        if e0 <= 0.0 or ya <= 0.0:
            return self._base_result(
                r, s, UCalcStatus.SOURCE_REJECTED,
                reason="type59_nonpositive_e0_or_ya",
                idest3=id3, idest4=id4,
                diagnostics={
                    "type59_threshold_ev": eth,
                    "type59_e0_ev": e0,
                    "type59_ya": ya,
                    "type59_parameter_layout": parameter_layout,
                },
            )
        id1=int(r.integers[-2])
        off=int(r.integers[-4])
        id2=max(c.nlevp+off-1,1)

        # Source label 59 uses the current record threshold for both sigma and
        # phintfo, but an excited parent destination changes ggup and therefore
        # the Milne statistical-weight ratio.
        gglo=c.levels.weight(1)
        ggup=c.levels.weight(c.nlevp)
        parent_excitation_ev=0.0
        if id2>c.nlevp:
            parent_excitation_ev,parent_weight=self._parent_destination_context(c,id2)
            ggup=parent_weight
        if ggup<=1.0e-24:
            return self._base_result(
                r,s,UCalcStatus.SOURCE_REJECTED,reason="type59_nonpositive_parent_stat_weight",
                idest1=id1,idest2=id2,idest3=id3,idest4=id4,
            )
        sw=gglo/ggup

        qq=5.5+l2-pp/2.0
        nb1=_xstar_nbinc_fortran_value(eth,epi)
        nphint=max(len(epi)-max(2,len(epi)//50),nb1+1)
        ll=nb1
        while ll<=nphint:
            energy=float(epi[ll-1])
            xx=energy/e0-y0
            yy=math.sqrt(xx*xx+y1*y1) if len(r.reals)==9 else xx
            yyqq=math.exp(-min(60.0,max(-60.0,qq*math.log(max(1.0e-48,yy)))))
            term1=(xx-1.0)*(xx-1.0)+yw*yw
            term3=(1.0+math.sqrt(max(yy/ya,0.0)))**(-pp)
            sig[ll-1]=s0*term1*yyqq*term3*1.0e-18
            nskip,nphint,_=_xstar_enxt_step(
                threshold_ev=eth,nb1_fortran=nb1,epi=epi,t_1e4=c.t,
                lfast=1,jk_fortran=ll,
            )
            ll+=nskip

        # ucalc.f90 owns ``lfastl=1`` for type 59 regardless of the caller.
        source_context=replace(c,lfast=1)
        zero=(r.rate_type==1 or id1>1)
        out=_photo_result_swapped(
            self,r,source_context,s,sigma=sig,threshold=eth,swrat=sw,
            id1=id1,id2=id2,zero_reverse=zero,
        )
        return replace(
            out,
            idest3=id3,
            idest4=id4,
            diagnostics={
                **dict(out.diagnostics),
                "type59_threshold_ev": eth,
                "type59_emax_ev": emax,
                "type59_e0_ev": e0,
                "type59_s0": s0,
                "type59_ya": ya,
                "type59_pp": pp,
                "type59_yw": yw,
                "type59_y0": y0,
                "type59_y1": y1,
                "type59_l2": l2,
                "type59_qq": qq,
                "type59_parameter_layout": parameter_layout,
                "type59_parent_offset_packed_index": -4,
                "type59_idest4_packed_index": -3,
                "type59_parent_offset": off,
                "type59_idest1": id1,
                "type59_idest2": id2,
                "type59_idest3": id3,
                "type59_idest4": id4,
                "type59_source_guard": "idest4_le_idest3_plus_one",
                "type59_reverse_zero_pre_swap_fields": "ans2;ans4;ans6",
                "type59_reverse_zero_post_swap_fields": "ans2;ans3;ans5",
                "type59_reverse_zero_applied": bool(zero),
                "type59_sigma_max_cm2": float(np.max(sig)) if sig.size else 0.0,
                "type59_nb1_fortran": nb1,
                "type59_nphint_fortran": nphint,
                "type59_sigma_grid_policy": "literal_nbinc_enxt_one_based",
                "type59_source_lfast": 1,
                "type59_requested_lfast": int(c.lfast),
                "type59_gglo": gglo,
                "type59_ggup": ggup,
                "type59_swrat": sw,
                "type59_excited_parent_destination": bool(id2>c.nlevp),
                "type59_parent_excitation_ev": parent_excitation_ev,
            },
        )

    def _eval_type12(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Source label 12 is an unconditional jump to the type-36 branch."""
        return self._eval_type36(r,c,s)

    def _eval_type15(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate source label 15 with literal shell-loop overwrite order.

        ``ucalc.f90`` first reads the parent-record threshold into ``ett`` but
        then overwrites ``ett`` and ``ddd`` for every BKH shell.  The final
        shell values are passed to both ``bkhsgo`` and ``phintfo``.  Preserve
        both the parent and shell values in diagnostics, but use only the final
        shell values in production calculations.
        """
        from .ucalc_leaves import bkhsgo
        if len(r.integers)<5 or len(r.reals)<14:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type15_short_record")
        parent=self._parent_record(r,c)
        parent_threshold=_finite(c.extras.get("type15_threshold_ev"))
        if parent_threshold is None and parent is not None and parent.reals:
            parent_threshold=float(parent.reals[0])
        if parent_threshold is None or parent_threshold<=0:
            return self._context_blocked(r,s,"type15_requires_parent_threshold_record")

        na=max(1,int(r.integers[-5]))
        shell_thresholds=[]
        shell_d_values=[]
        b=[]
        coeff=[]
        effective_threshold=None
        effective_d=None
        for k in range(na):
            off=15*k
            if off+14>len(r.reals):
                break
            # Literal source assignments inside ``do lk=1,na``:
            #   ett=rdat(np1r-1+1+lz)
            #   ddd=rdat(np1r-1+2+lz)
            effective_threshold=float(r.reals[off])
            effective_d=float(r.reals[off+1])
            shell_thresholds.append(effective_threshold)
            shell_d_values.append(effective_d)
            b.append(float(r.reals[off+2]))
            coeff.append(tuple(float(x) for x in r.reals[off+3:off+14]))
        if not b or effective_threshold is None or effective_d is None:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type15_missing_bkh_shell_coefficients")

        epi=self._mapped_grid(c)
        sigma=bkhsgo(epi,effective_threshold,effective_d,b,coeff)
        id1=int(r.integers[-2])
        id2=int(r.integers[-3])-int(r.integers[-1])
        sw=c.levels.weight(1)/max(c.levels.weight(c.nlevp),1e-48)
        out=_photo_result_swapped(
            self,r,c,s,sigma=sigma,threshold=effective_threshold,
            swrat=sw,id1=id1,id2=id2,
        )
        return replace(
            out,
            diagnostics={
                **dict(out.diagnostics),
                "type15_parent_record": int(r.parent_record),
                "type15_parent_threshold_ev": float(parent_threshold),
                "type15_shell_thresholds_ev": tuple(shell_thresholds),
                "type15_shell_d_values": tuple(shell_d_values),
                "type15_effective_threshold_ev": float(effective_threshold),
                "type15_effective_d": float(effective_d),
                "type15_bkhsgo_threshold_ev": float(effective_threshold),
                "type15_phintfo_threshold_ev": float(effective_threshold),
                "bkh_n_shells": len(b),
                "bkh_d": float(effective_d),
                "threshold_source": "final_type15_shell_record",
            },
        )

    def _eval_type23(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if not r.integers:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type23_missing_level_index")
        id1=int(r.integers[-2] if len(r.integers)>=2 else r.integers[0]); id2=c.nlevp
        threshold=max(c.levels.energy(id1),0.0)
        z=_finite(c.extras.get("element_z"))
        if z is None or z<=0: return self._context_blocked(r,s,"type23_requires_element_z")
        n=max(float(r.integers[0]),1.0); sigma0=6.3e-18*n/(z*z)
        sigma=self._hydrogenic_sigma_grid(c,threshold,sigma0)
        sw=c.levels.weight(id1)/max(c.levels.weight(c.nlevp),1e-48)
        return _photo_result_swapped(self,r,c,s,sigma=sigma,threshold=threshold,swrat=sw,id1=id1,id2=id2)

    def _eval_type31(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<2:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type31_short_record")
        lower,upper=int(r.integers[1]),int(r.integers[0]); wavelength=abs(float(r.reals[0])); f=float(r.reals[1])
        if wavelength<=0: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason="type31_zero_wavelength")
        mass=self._atomic_mass(r,c)
        if mass is None: return self._context_blocked(r,s,"type31_requires_parent_element_atomic_mass")
        gup=c.levels.weight(upper); glo=c.levels.weight(lower)
        aij=.02655*f*8*math.pi/(wavelength*1e-8)**2*glo/max(gup,1e-24)
        decay=aij*(c.ptmp1+c.ptmp2)
        vtherm=math.sqrt((c.turbulent_velocity_km_s*1e5)**2+(1.29e6/math.sqrt(max(mass/c.t,1e-48)))**2)
        sigma=.02655*f*wavelength*1e-8/max(vtherm,1e-48)
        epi,brem,_=_radiation_arrays(c.radiation); energy=12398.4016/wavelength; nb=_nbinc(energy,epi)
        pumping=sigma*brem[nb]*vtherm/3e10
        if wavelength>.99e9: pumping=sigma=0.0
        decay += pumping*gup/max(glo,1e-48)
        # lfasto is hard-wired to 4 in the source, so ans2 is zeroed.
        return self._ctx_result(r,s,ans1=decay,ans2=0.0,ans3=pumping*energy*ERG_PER_EV,ans4=decay*energy*ERG_PER_EV,idest1=lower,idest2=upper,opakab=sigma,
            diagnostics={"aij_s^-1":aij,"pumping_pre_lfast_zero_s^-1":pumping,"radiation_bin":nb},context_fields_used=("temperature_k","turbulent_velocity_km_s","radiation","levels","ptmp1","ptmp2","atomic_mass"))

    def _eval_type49(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import phextrap
        if len(r.integers)<3 or len(r.reals)<4:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type49_short_record")
        # Fortran: idest2=nlevp+max(0,idat(np1i-1+nidt-3))-1.
        # In the zero-based packed tuple this is integers[-4], not [-3].
        # integers[-3] is the separate idest4 field.
        id1=int(r.integers[-2]); off=max(0,int(r.integers[-4])); id2=c.nlevp+off-1
        threshold=self._level_threshold(c,id1)
        e=np.asarray(r.reals[0::2],float); xs=np.maximum(np.asarray(r.reals[1::2],float)*1e-18,0.0); n=min(e.size,xs.size)
        if n<2: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type49_missing_cross_section_pairs")
        e,xs=phextrap(e[:n],xs[:n],threshold,len(self._mapped_grid(c)))
        out=self._type53_from_pairs(r,c,s,energy_ryd=e,sigma_cm2=xs,threshold_ev=threshold,idest1=id1,idest2=id2)
        return replace(out, diagnostics={**dict(out.diagnostics),
            "type49_parent_offset_packed_index": -4,
            "type49_idest4_packed_index": -3,
            "type49_parent_offset": off,
            "type49_source_expression": "nlevp+max(0,idat(np1i-1+nidt-3))-1",
        })

    def _eval_type64(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import hphotx,milne
        if len(r.integers)<3:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type64_short_record")
        id1=int(r.integers[-2]); id2=c.nlevp; threshold=abs(c.levels.energy(c.nlevp)-c.levels.energy(id1))
        if threshold<=1e-5: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason="type64_nonpositive_threshold")
        nq=max(int(r.integers[0]),1); l=max(int(r.integers[1]),0); charge=max(int(r.integers[2]),1)
        epi=self._mapped_grid(c); e_ryd=np.maximum((epi-threshold)/13.605692,0.0); sig_mb=np.asarray([hphotx(x,charge,nq)[min(l,nq-1)] for x in e_ryd]); sigma=sig_mb*1e-18
        sw=c.levels.weight(id1)
        out=_photo_result_swapped(self,r,c,s,sigma=sigma,threshold=threshold,swrat=sw,id1=id1,id2=id2)
        alpha=milne(c.temperature_k,e_ryd,sig_mb,threshold/13.6)*sw
        return replace(out,ans2=alpha,diagnostics={**dict(out.diagnostics),"milne_override_ans2_s^-1":alpha,"principal_n":nq,"orbital_l":l,"ion_charge":charge})

    def _eval_type70(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import calt70
        from xstar_atomic.rates_type53 import evaluate_phint53_exact
        if len(r.integers)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type70_short_record")
        id1=min(int(r.integers[-2]),max(c.nlevp-1,1)); id2=max(c.nlevp+int(r.integers[-3])-1,c.nlevp)
        threshold=abs(c.levels.energy(id1)-c.levels.energy(c.nlevp)); dest_energy,dest_g=self._parent_destination_context(c,id2)
        if id2>c.nlevp: threshold=abs(c.levels.energy(id1)+dest_energy)
        gbound=c.levels.weight(id1); gdest=dest_g or c.levels.weight(c.nlevp)
        if gbound<=0 or gdest<=0: return self._context_blocked(r,s,"type70_requires_bound_and_parent_statistical_weights")
        density=c.hydrogen_density_cm3
        if c.jkion==1: density=min(density,1e8)
        ion_charge=int(c.extras.get("ion_charge",r.integers[0] if r.integers else 1))
        try: rec,e_ryd,xs_mb,diag=calt70(r.reals,r.integers,c.temperature_k,density,threshold/13.6)
        except Exception as exc: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=f"calt70:{exc}")
        ne=c.electron_density_cm3; sw=gbound/gdest; rnist=5.216e-21*sw/max(c.t*c.tsq,1e-48)*ne
        ph=evaluate_phint53_exact(energy_above_threshold_ryd=e_ryd,cross_section_cm2=xs_mb*1e-18,threshold_eV=threshold,live_radiation=self._live_type53_state(c),temperature_1e4K=c.t,rnist=rnist,ptmp1=1.0,ptmp2=0.0,lfast=3,abund1=0.0,abund2=0.0,xpx_cm3=c.hydrogen_density_cm3)
        ans2d=ph.rrrt_s_inv
        if ans2d<=1e-48: return self._ctx_result(r,s,idest1=id1,idest2=id2,diagnostics={**diag,"phint_status":ph.diagnostics.get("status")})
        scale=rec*ne/ans2d
        return self._ctx_result(r,s,ans1=ph.pirt_s_inv*scale,ans2=rec*ne,ans3=-ph.rrcl_erg_s_inv,ans4=-ph.piht_erg_s_inv*scale,ans5=-ph.rrcl2_erg_s_inv,ans6=-ph.piht2_erg_s_inv*scale,idest1=id1,idest2=id2,
            diagnostics={**diag,"phint53hunt_equivalent_scale":scale,"ion_charge":ion_charge,"source_lfast":3},context_fields_used=("temperature_k","xpx","xee","radiation","levels"))

    def _eval_type81(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or not r.reals: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type81_short_record")
        a,b=int(r.integers[0]),int(r.integers[1]); lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a); de=abs(c.levels.energy(up)-c.levels.energy(lo)); om=max(float(r.reals[0]),0.0)
        gu=c.levels.weight(up); gl=c.levels.weight(lo); ex=_expo(-de/(XSTAR_KT_EV_PER_1E4K*c.t)); ne=c.electron_density_cm3
        qd=8.626e-8*om/c.tsq/max(gu,1e-48); qe=qd*gu*ex/max(gl,1e-48)
        return self._ctx_result(r,s,ans1=qe*ne,ans2=qd*ne,ans5=qd*ne*de*ERG_PER_EV,ans6=qe*ne*de*ERG_PER_EV,idest1=lo,idest2=up,diagnostics={"upsilon":om},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type82(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<4: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type82_short_record")
        a,b=int(r.integers[0]),int(r.integers[1]); up,lo=(a,b) if c.levels.energy(a)>=c.levels.energy(b) else (b,a)
        wavelength=abs(float(r.reals[0])); flin=float(r.reals[2]); aij=float(r.reals[3]); mass=self._atomic_mass(r,c)
        if mass is None: return self._context_blocked(r,s,"type82_requires_parent_element_atomic_mass")
        vtherm=math.sqrt((c.turbulent_velocity_km_s*1e5)**2+(1.29e6/math.sqrt(max(mass/c.t,1e-48)))**2); sigma=.02655*flin*wavelength*1e-8/max(vtherm,1e-48)
        rwave=self._linked_line_wavelength(r,c,wavelength); epi,brem,_=_radiation_arrays(c.radiation); energy=12398.4016/max(rwave,1e-48); nb=_nbinc(energy,epi); pump=sigma*brem[nb]*vtherm/3e10; decay=aij*(c.ptmp1+c.ptmp2)
        return self._ctx_result(r,s,ans1=pump,ans2=decay,ans3=pump*energy*ERG_PER_EV,idest1=up,idest2=lo,opakab=sigma,diagnostics={"aij_s^-1":aij,"radiation_bin":nb,"linked_wavelength_A":rwave},context_fields_used=("temperature_k","turbulent_velocity_km_s","radiation","levels","ptmp1","ptmp2","atomic_mass"))

    def _eval_type85(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import pexs
        if len(r.integers)<3 or len(r.reals)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type85_short_record")
        id1=int(r.integers[-2]); id2=1; id3=int(r.integers[-1]); epi=self._mapped_grid(c); nmin=int(r.integers[0]); zc=float(id3-114); eion=float(r.reals[1]); far=float(r.reals[2]); gam=float(r.reals[3]); scal=float(r.reals[4])
        sig_mb=pexs(nmin,zc,eion,far,gam,scal,epi/13.605692); ph=_phintfo_exact(sigma_cm2=sig_mb*1e-18,threshold_ev=eion*13.605692*.8,context=c,swrat=1.0)
        return self._ctx_result(r,s,ans1=ph["ans1"],ans2=0.0,ans3=0.0,ans4=-ph["ans3"],ans5=0.0,ans6=-ph["ans5"],idest1=id1,idest2=id2,opakab=0.0,diagnostics={**ph,"pexs_nmin":nmin,"pexs_zc":zc,"source_swrat_uninitialized_assumed_one":True},context_fields_used=("temperature_k","xpx","xee","radiation"))

    def _eval_type88(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import phextrap
        if len(r.integers)<2 or len(r.reals)<4: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type88_short_record")
        id1=int(r.integers[-2]); id2=c.nlevp; threshold=self._level_threshold(c,id1); e=np.asarray(r.reals[0::2],float); xs=np.maximum(np.asarray(r.reals[1::2],float)*1e-18,0.0); n=min(e.size,xs.size)
        e,xs=phextrap(e[:n],xs[:n],threshold,len(self._mapped_grid(c)))
        return self._type53_from_pairs(r,c,s,energy_ryd=e,sigma_cm2=xs,threshold_ev=threshold,idest1=id1,idest2=id2,zero_reverse=True,zero_all_heating=True)

    def _eval_type89(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<3: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type89_short_record")
        a,b=int(r.integers[0]),int(r.integers[1]); up,lo=(a,b) if c.levels.energy(a)>=c.levels.energy(b) else (b,a); aij=float(r.reals[2]); wavelength=abs(float(r.reals[0])); mass=self._atomic_mass(r,c)
        if mass is None: return self._context_blocked(r,s,"type89_requires_parent_element_atomic_mass")
        gu=c.levels.weight(up); gl=c.levels.weight(lo); flin=1e-16*aij*gu*wavelength*wavelength/(.667274*max(gl,1e-48)); vtherm=math.sqrt((c.turbulent_velocity_km_s*1e5)**2+(1.29e6/math.sqrt(max(mass/c.t,1e-48)))**2); sigma=.02655*flin*wavelength*1e-8/max(vtherm,1e-48)
        if wavelength>.99e9: sigma=0.0
        energy=12398.4016/max(wavelength,1e-48); decay=aij*(c.ptmp1+c.ptmp2)
        return self._ctx_result(r,s,ans1=decay,ans2=0.0,ans3=0.0,ans4=decay*energy*ERG_PER_EV,ans5=0.0,ans6=0.0,idest1=up,idest2=lo,opakab=sigma,diagnostics={"aij_s^-1":aij,"oscillator_strength":flin,"resonant_excitation_forced_zero_by_source":True},context_fields_used=("temperature_k","turbulent_velocity_km_s","levels","ptmp1","ptmp2","atomic_mass"))

    def _eval_type92(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import calc_maxwell_rates
        if len(r.integers)<3 or len(r.reals)<42: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type92_short_record")
        lo,up=int(r.integers[0]),int(r.integers[1]); coll_type=int(r.integers[2]); tmin,tmax=float(r.reals[0]),float(r.reals[1]); tarr=r.reals[2:22]; om=r.reals[22:42]; z=int(c.extras.get("element_z",0))
        if z<=0: return self._context_blocked(r,s,"type92_requires_element_z")
        de=abs(c.levels.energy(up)-c.levels.energy(lo)); exc,dex,ups,diag=calc_maxwell_rates(coll_type,tmin,tmax,tarr,om,de/1000.0,c.temperature_k,z,c.levels.weight(lo),c.levels.weight(up)); ne=c.electron_density_cm3
        return self._ctx_result(r,s,ans1=exc*ne,ans2=dex*ne,ans5=dex*ne*de*ERG_PER_EV,ans6=exc*ne*de*ERG_PER_EV,idest1=lo,idest2=up,diagnostics={**diag,"upsilon":ups,"collision_type":coll_type},context_fields_used=("temperature_k","xpx","xee","levels","element_z"))

    def _eval_type97(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals)<4: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type97_short_record")
        if r.rate_type==5:
            id1=int(r.integers[0]) if r.integers else 1; id2=c.nlevp-1+(int(r.integers[1]) if len(r.integers)>=3 else 1)
        else: id1=id2=1
        threshold=self._level_threshold(c,id1); dest_energy,dest_g=self._parent_destination_context(c,id2)
        if id2>c.nlevp: threshold += dest_energy
        ns=len(r.reals)//2; tg=np.asarray(r.reals[:ns],float); vals=np.asarray(r.reals[ns:2*ns],float); ekt=XSTAR_KT_EV_PER_1E4K*c.t
        if ns<2: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type97_missing_spline")
        ups=float(np.interp(ekt,tg,vals,left=vals[0],right=vals[-1])); gl=c.levels.weight(id1); gu=dest_g or c.levels.weight(c.nlevp)
        cji=8.626e-8*ups/c.tsq/max(gu,1e-48); ex=_expo(-threshold/max(ekt,1e-48)); cij=cji*gu*ex/max(gl,1e-48); ne=c.electron_density_cm3; ans1=cij*ne; rinf=2.08e-22*gl/max(gu,1e-48)/max(c.t*c.tsq,1e-48); ans2=ans1*rinf*ne/max(ex,1e-300)
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*threshold*ERG_PER_EV,ans6=ans1*threshold*ERG_PER_EV,idest1=id1,idest2=id2,diagnostics={"upsilon":ups,"threshold_eV":threshold},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type50(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate the complete type-50 ``ucalc`` record decode and rate.

        XSTAR stores wavelength at ``rdat(1)`` and A at ``rdat(3)``.  The
        oscillator strength is reconstructed from A and the endpoint
        statistical weights exactly as in label 50 of ``ucalc.f90``.
        """
        from xstar_atomic.rates_type50 import evaluate_type50_ucalc_record
        decoded = dict(c.extras.get("decoded_type50", {}))
        i = r.integers
        id1, id2 = (int(i[0]), int(i[1])) if len(i) >= 2 else (0, 0)
        if not decoded:
            wavelength = abs(float(r.reals[0])) if r.reals else None
            aij = float(r.reals[2]) if len(r.reals) > 2 else None
            flin = None
            source_upper_id = id1
            source_lower_id = id2
            source_upper_weight = None
            source_lower_weight = None
            source_swapped_endpoints = False
            if wavelength and aij is not None and id1 > 0 and id2 > 0:
                # Source-faithful label-50 endpoint handling.  ucalc.f90 first
                # reads idest1/idest2, then compares level energies and swaps
                # the endpoint ids when idest1 is lower in energy:
                #
                #   eeup=rlev(1,idest1); eelo=rlev(1,idest2)
                #   if (eeup.lt.eelo) swap(idest1,idest2)
                #   ggup=rlev(2,idest1); gglo=rlev(2,idest2)
                #   flin=1e-16*aij*ggup*elin**2/(0.667274*gglo)
                #
                # Earlier Python used the raw record order for ggup/gglo.  For
                # the H-like/He-like resonance doublets this inverted the
                # statistical-weight factor before linopac, making the lower-J
                # component too strong and the upper-J component too weak.
                try:
                    e1 = c.levels.energy(id1)
                    e2 = c.levels.energy(id2)
                    if e1 < e2:
                        source_upper_id, source_lower_id = id2, id1
                        source_swapped_endpoints = True
                except Exception:
                    source_upper_id, source_lower_id = id1, id2
                    source_swapped_endpoints = False
                ggup = c.levels.weight(source_upper_id)
                gglo = c.levels.weight(source_lower_id)
                source_upper_weight = ggup
                source_lower_weight = gglo
                if ggup > 0.0 and gglo > 0.0:
                    flin = 1.0e-16 * aij * ggup * wavelength * wavelength / (0.667274 * gglo)
            decoded = {
                "A_s^-1": aij,
                "f_osc_from_A": flin,
                "wavelength_A": wavelength,
                "source_upper_id_after_energy_swap": source_upper_id,
                "source_lower_id_after_energy_swap": source_lower_id,
                "source_upper_statistical_weight": source_upper_weight,
                "source_lower_statistical_weight": source_lower_weight,
                "source_swapped_endpoints_for_type50_flin": source_swapped_endpoints,
            }
        bremsa = c.extras.get("bremsa_nb1")
        # Source label 50 samples bremsa at the line energy.  This context is
        # unnecessary for cfrac=1, but derive it directly when pumping is live.
        if bremsa is None and c.radiation is not None and c.covering_fraction < 1.0:
            try:
                epi, brem, _ = _radiation_arrays(c.radiation)
                wavelength = float(decoded.get("wavelength_A") or 0.0)
                if wavelength > 0.0:
                    bremsa = float(brem[_nbinc(12398.54 / wavelength, epi)])
            except Exception:
                bremsa = None
        endpoint_energy_ev = None
        if id1 > 0 and id2 > 0:
            upper_energy = c.levels.energy(id1)
            lower_energy = c.levels.energy(id2)
            endpoint_energy_ev = abs(float(upper_energy) - float(lower_energy))
        ev = evaluate_type50_ucalc_record(
            decoded, ptmp1=c.ptmp1, ptmp2=c.ptmp2,
            cfrac=c.covering_fraction, bremsa_nb1=bremsa,
            hydrogen_density_cm3=c.hydrogen_density_cm3,
            endpoint_energy_eV=endpoint_energy_ev,
            source_erg_per_eV=XSTAR_SOURCE_ERG_PER_EV,
        )
        if (
            ev.get("status") != "evaluated"
            or ev.get("energy_channel_status") != "evaluated"
            or ev.get("ans3_cooling_signed_erg_s^-1") is None
            or ev.get("ans4_heating_signed_erg_s^-1") is None
        ):
            reason = str(ev.get("reason") or ev.get("energy_channel_status") or "missing_type50_energy_context")
            return self._base_result(r, s, UCalcStatus.CONTEXT_BLOCKED, reason=reason, diagnostics=ev)
        # Source label 50 also returns the line-center opacity through the
        # caller-owned ``opakb1`` argument and, when the lower-level population
        # is nonzero, immediately sends ``opakb1 = sigma * abund1`` through
        # ``linopac`` into the continuum-grid ``opakc`` array.  Earlier Python
        # releases reproduced the population/thermal channels but left
        # ``opakab`` at zero for type 50, so the v0.5.05 line handoff had no
        # opacity to bin for the dominant bound-bound records.
        opakab = 0.0
        try:
            wavelength = float(decoded.get("wavelength_A") or 0.0)
            flin = float(decoded.get("f_osc_from_A") or 0.0)
            mass = self._atomic_mass(r, c)
            if wavelength > 0.0 and flin > 0.0 and mass is not None and mass > 0.0 and wavelength <= 0.99e9:
                vtherm = math.sqrt((c.turbulent_velocity_km_s * 1.0e5) ** 2 + (1.29e6 / math.sqrt(max(float(mass) / c.t, 1.0e-48))) ** 2)
                if vtherm > 0.0:
                    opakab = 0.02655 * flin * wavelength * 1.0e-8 / vtherm
        except Exception:
            opakab = 0.0
        diag = dict(ev)
        diag["type50_line_center_opakab_cm2"] = opakab
        return self._ctx_result(
            r, s, ans1=float(ev["ans1_photoexcitation_s^-1"]),
            ans2=float(ev["ans2_escaped_decay_s^-1"]),
            ans3=float(ev["ans3_cooling_signed_erg_s^-1"]),
            ans4=float(ev["ans4_heating_signed_erg_s^-1"]),
            idest1=id1, idest2=id2, opakab=opakab, diagnostics=diag,
            context_fields_used=("ptmp1", "ptmp2", "cfrac", "radiation", "xpx", "levels", "turbulent_velocity_km_s", "atomic_mass"),
        )

    def _collision_row(self, r: UCalcRecord, c: UCalcContext) -> tuple[dict, list[dict]]:
        # Build the stable row schema used by the already validated collision kernels.
        i, rd = r.integers, r.reals
        levels = c.levels
        dt = r.data_type
        if dt == 51:
            a, b = i[2], i[1]
        elif dt == 63 and len(i) >= 4:
            a, b = i[-4], i[-3]
        else:
            a, b = (i[0], i[1]) if len(i) >= 2 else (0, 0)
        ea, eb = levels.energy(a), levels.energy(b)
        lower, upper = (a, b) if ea <= eb else (b, a)
        delta = abs(levels.energy(upper)-levels.energy(lower))
        from xstar_atomic.hierarchy import Z_TO_SYMBOL, roman
        element_z = int(c.extras.get("element_z", 0) or 0)
        ion_stage = int(c.extras.get("ion_stage", 0) or 0)
        element = str(c.extras.get("element_symbol") or Z_TO_SYMBOL.get(element_z, str(element_z) if element_z else ""))
        formats = {
            51: "BT_CHIANTI_pre2016_type51", 56: "tabulated_upsilon_type56",
            63: "bautista_nl_algorithm_type63", 67: "helike_keenan_mccann_kingston_type67",
            68: "helike_zhang_sampson_type68", 69: "helike_kato_nakazaki_type69",
            98: "BT_CHIANTI2016_type98",
        }
        row: Dict[str, Any] = {
            "record": r.record, "element": element, "ion_stage": ion_stage,
            "ion_roman": roman(ion_stage) if ion_stage > 0 else "",
            "data_type": dt, "rate_type": r.rate_type,
            "source_format": formats.get(dt, f"data_type_{dt}"),
            "lower_level": lower, "upper_level": upper,
            "lower_label": (levels.get(lower).label if levels.get(lower) else ""),
            "upper_label": (levels.get(upper).label if levels.get(upper) else ""),
            "g_lower": levels.weight(lower), "g_upper": levels.weight(upper),
            "delta_e_level_eV": delta,
            "wavelength_from_levels_A": 12398.4016/delta if delta > 0 else None,
            "helike_fit_reals": __import__("json").dumps(list(rd)),
            "helike_fit_ints": __import__("json").dumps(list(i)),
        }
        grid: list[dict] = []
        if dt == 51:
            row.update({"bt_transition_type": i[0], "eij_rdat_Ryd": rd[0], "bt_scaling_c": rd[1]})
            xs = [0.0, .25, .5, .75, 1.0] if len(rd)==7 else [0.125*k for k in range(max(0,len(rd)-2))]
            for k,(x,y) in enumerate(zip(xs,rd[2:]),1): grid.append({"grid_index":k,"grid_kind":"BT_scaled","bt_x":x,"bt_y":y})
        elif dt == 56:
            n=len(rd)//2
            for k,(x,y) in enumerate(zip(rd[:n],rd[n:2*n]),1): grid.append({"grid_index":k,"grid_kind":"logT_Upsilon","log10_T_K":x,"upsilon":y})
        elif dt == 98:
            n=(len(rd)-3)//2
            row.update({"bt_transition_type": i[-2], "eij_rdat_Ryd": rd[0], "bt_scaling_c": rd[2]})
            for k,(x,y) in enumerate(zip(rd[3:3+n],rd[3+n:3+2*n]),1): grid.append({"grid_index":k,"grid_kind":"BT_scaled","bt_x":x,"bt_y":y})
        if dt == 63:
            row.update({
                "type63_iq": i[-2] if len(i)>=2 else None,
                "type63_initial_level": a, "type63_final_level": b,
                "type63_initial_n": levels.get(a).principal_n if levels.get(a) else None,
                "type63_initial_l": levels.get(a).orbital_l if levels.get(a) else None,
                "type63_final_n": levels.get(b).principal_n if levels.get(b) else None,
                "type63_final_l": levels.get(b).orbital_l if levels.get(b) else None,
                "type63_initial_energy_eV": levels.energy(a), "type63_final_energy_eV": levels.energy(b),
                "type63_initial_g": levels.weight(a), "type63_final_g": levels.weight(b),
                "n_lower": levels.get(lower).principal_n if levels.get(lower) else None,
                "l_lower": levels.get(lower).orbital_l if levels.get(lower) else None,
                "n_upper": levels.get(upper).principal_n if levels.get(upper) else None,
                "l_upper": levels.get(upper).orbital_l if levels.get(upper) else None,
            })
        return row, grid

    def _eval_type51(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.rates_type51 import evaluate_type51_ucalc_record
        row, grid = self._collision_row(r,c)
        ev=evaluate_type51_ucalc_record(row,c.temperature_k,c.electron_density_cm3,grid)
        if ev.get("status") != "evaluated":
            return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=str(ev.get("reason")),diagnostics=ev)
        return self._ctx_result(r,s,ans1=float(ev["ans1_excitation_s^-1"]),ans2=float(ev["ans2_deexcitation_s^-1"]),
                                ans5=float(ev["ans5_deexcitation_energy_erg_s^-1"]),ans6=float(ev["ans6_excitation_energy_erg_s^-1"]),
                                idest1=int(row["lower_level"]),idest2=int(row["upper_level"]),diagnostics=ev,
                                context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_collision_generic(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.collisions import evaluate_collision_row
        row, grid = self._collision_row(r,c)
        ev=evaluate_collision_row(row,c.temperature_k,grid,electron_density_cm3=c.electron_density_cm3)
        reason = str(
            ev.get("eval_diagnostic")
            or ev.get("type63_reason")
            or ev.get("diagnostic")
            or "collision_evaluation_failed"
        )
        # ucalc.f90 label 63 is exceptional among the collision branches:
        # its idest1/idest2 and ans1/ans2 remain in the literal packed-record
        # direction.  Do not remap descending ATDB endpoints to the generic
        # energy-ordered excitation/de-excitation convention before inserting
        # the population-matrix terms.  That remapping inverted nine active
        # O VII records in the solve-call-219 parity case.
        if r.data_type == 63 and ev.get("type63_ucalc_ans1_forward_cm3_s") is not None:
            qforward = _finite(ev.get("type63_ucalc_ans1_forward_cm3_s"))
            qreverse = _finite(ev.get("type63_ucalc_ans2_reverse_cm3_s"))
            if qforward is None or qreverse is None:
                return self._base_result(
                    r, s, UCalcStatus.SOURCE_REJECTED,
                    reason=reason, diagnostics=ev,
                )
            ans1=qforward*c.electron_density_cm3
            ans2=qreverse*c.electron_density_cm3
            idest1=int(row["type63_initial_level"])
            idest2=int(row["type63_final_level"])
            ev = dict(ev)
            ev["type63_matrix_channel_convention"] = "literal_ucalc_record_order"
        else:
            qexc=_finite(ev.get("q_excitation_cm3_s")); qde=_finite(ev.get("q_deexcitation_cm3_s"))
            if qexc is None or qde is None:
                # ucalc.f90 label 63 leaves initialized ans1/ans2 at zero when
                # Delta-l is not one or the literal record-order angular selector
                # aa1 vanishes. These are evaluated source-zero records, not
                # rejected runtime context.
                source_zero_type63 = {
                    "delta_l_not_equal_1",
                    "same_n_delta_l_not_equal_1",
                    "nonpositive_xstar_record_order_aa1",
                }
                if r.data_type == 63 and reason in source_zero_type63:
                    qexc = 0.0
                    qde = 0.0
                    ev = dict(ev)
                    ev["source_zero_behavior"] = "ucalc_label63_preserves_initialized_zero_rates"
                    ev["source_zero_reason"] = reason
                else:
                    return self._base_result(
                        r, s, UCalcStatus.SOURCE_REJECTED,
                        reason=reason, diagnostics=ev,
                    )
            ans1=qexc*c.electron_density_cm3
            ans2=qde*c.electron_density_cm3
            idest1=int(row["lower_level"])
            idest2=int(row["upper_level"])
        de=float(row.get("delta_e_level_eV") or 0.0)
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*de*ERG_PER_EV,ans6=ans1*de*ERG_PER_EV,
                                idest1=idest1,idest2=idest2,diagnostics=ev,
                                context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type53(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.rates_type53 import evaluate_type53_ucalc_record
        decoded = c.extras.get("decoded_type53_by_record", {}).get(r.record) or c.extras.get("decoded_type53")
        i = r.integers
        # ucalc.f90 label 53:
        #   idest1 = idat(np1i+nidt-2)             -> packed integer [-2]
        #   idest2 = nlevp+idat(np1i-1+nidt-3)-1 -> packed integer [-4]
        # The third integer from the end is a linked parent-ion/element field,
        # not the parent-level offset.  Using [-3] collapses almost every
        # excited-parent destination onto an unrelated row and also feeds the
        # wrong threshold/statistical weight into phint53.
        if len(i) < 4:
            return self._base_result(
                r, s, UCalcStatus.INVALID_RECORD,
                reason="type53_requires_four_packed_tail_integers",
            )
        id1 = int(i[-2])
        off = int(i[-4])
        id2 = c.nlevp + off - 1

        # ucalc.f90 label 53 applies the bound-level threshold gate *before*
        # correcting the threshold for an excited parent destination:
        #
        #   eth = rlev(4,idest1) - rlev(1,idest1)
        #   ett = eth
        #   if (ett.le.0.) go to 9000
        #   ...
        #   if (idest2.gt.nlevp) ett=ett+rdat(parent_level)
        #
        # Do not clamp the base threshold to zero and then add the parent
        # excitation.  High/autoionizing bound levels must retain the source
        # zero-rate result even when the later parent correction would make
        # the final threshold positive.  calc_hmc_ion still inserts the four
        # zero matrix terms, so return an evaluated zero result with endpoints
        # rather than SOURCE_NOOP.
        try:
            bound_for_gate = c.levels.require(id1)
        except (KeyError, ValueError, IndexError) as exc:
            return self._context_blocked(r, s, f"type53_bound_level:{exc}")
        base_threshold = (
            float(bound_for_gate.ionization_potential_ev)
            - float(bound_for_gate.energy_ev)
        )
        if base_threshold <= 0.0:
            return self._ctx_result(
                r, s,
                ans1=0.0, ans2=0.0, ans3=0.0, ans4=0.0, ans5=0.0, ans6=0.0,
                idest1=id1, idest2=id2,
                diagnostics={
                    "packed_parent_offset": off,
                    "packed_parent_offset_index": -4,
                    "packed_bound_level_index": -2,
                    "source_idest2_expression": "nlevp + integers[-4] - 1",
                    "source_type53_base_threshold_eV": base_threshold,
                    "source_type53_zero_gate": "ett_le_zero_before_excited_parent_correction",
                    "source_type53_parent_correction_applied": False,
                    "source_type53_zero_matrix_terms_expected": 4,
                },
                context_fields_used=("levels",),
            )

        if decoded is None and c.radiation is not None and id1 > 0:
            try:
                bound = bound_for_gate
                continuum = c.levels.require(c.nlevp)
                parent_excitation, destination_g = self._parent_destination_context(c, id2)
                # For excited parents the map stores excitation above the
                # parent ground; the physical destination energy includes the
                # current-ion continuum energy.
                physical_destination_energy = continuum.energy_ev + (parent_excitation if id2 > c.nlevp else 0.0)
                leveltemp_destination_energy = self._leveltemp_destination_energy(
                    c, id2, physical_destination_energy
                )
                threshold = base_threshold + (parent_excitation if id2 > c.nlevp else 0.0)
                n_pairs = len(r.reals) // 2
                decoded = {
                    "record": r.record,
                    "energy_above_threshold_ryd": [float(r.reals[2*k]) for k in range(n_pairs)],
                    "cross_section_cm2": [max(0.0, float(r.reals[2*k+1])) * 1.0e-18 for k in range(n_pairs)],
                    "threshold_eV": threshold,
                    "bound_statistical_weight": bound.statistical_weight,
                    "continuum_statistical_weight": continuum.statistical_weight,
                    "destination_statistical_weight": destination_g or continuum.statistical_weight,
                    "continuum_energy_eV": continuum.energy_ev,
                    "bound_energy_eV": bound.energy_ev,
                    "destination_energy_eV": leveltemp_destination_energy,
                    "physical_parent_destination_energy_eV": physical_destination_energy,
                    "leveltemp_destination_energy_eV": leveltemp_destination_energy,
                    "leveltemp_workspace_semantics": "persistent_higher_columns",
                    "packed_parent_offset": off,
                    "packed_parent_offset_index": -4,
                    "packed_bound_level_index": -2,
                    "source_idest2_expression": "nlevp + integers[-4] - 1",
                    "decode_source": "packed_type53_record_plus_element_level_context",
                }
            except (KeyError, ValueError, IndexError) as exc:
                return self._context_blocked(r, s, f"type53_decode:{exc}")
        if decoded is None or c.radiation is None:
            return self._context_blocked(r, s, "type53 requires packed cross-section/level context and live epim/bremsam/bremsint")
        decoded = dict(decoded)
        physical_destination_energy = float(
            decoded.get("physical_parent_destination_energy_eV",
                        decoded.get("destination_energy_eV", c.levels.energy(c.nlevp)))
        )
        leveltemp_destination_energy = self._leveltemp_destination_energy(
            c, id2, physical_destination_energy
        )
        decoded["destination_energy_eV"] = leveltemp_destination_energy
        decoded["physical_parent_destination_energy_eV"] = physical_destination_energy
        decoded["leveltemp_destination_energy_eV"] = leveltemp_destination_energy
        decoded["leveltemp_workspace_semantics"] = "persistent_higher_columns"
        ev = evaluate_type53_ucalc_record(
            decoded, self._live_type53_state(c), temperature_k=c.temperature_k,
            xpx_cm3=c.hydrogen_density_cm3, electron_fraction_xee=c.electron_fraction_xee,
            ptmp1=c.ptmp1, ptmp2=c.ptmp2, lfast=c.lfast, abund1=c.abund1, abund2=c.abund2,
        )
        if ev.get("status") != "evaluated":
            return self._base_result(r, s, UCalcStatus.SOURCE_REJECTED, reason=str(ev.get("status")), diagnostics=ev)
        ev = {
            **dict(ev),
            "packed_parent_offset": off,
            "packed_parent_offset_index": -4,
            "packed_bound_level_index": -2,
            "source_idest2_expression": "nlevp + integers[-4] - 1",
        }
        return self._ctx_result(
            r, s, ans1=float(ev["ans1_photoionization_s^-1"]), ans2=float(ev["ans2_milne_recombination_s^-1"]),
            ans3=float(ev["ans3_cooling_signed_erg_s^-1"]), ans4=float(ev["ans4_heating_signed_erg_s^-1"]),
            ans5=float(ev["ans5_electron_pov_cooling_signed_erg_s^-1"]), ans6=float(ev["ans6_electron_pov_heating_signed_erg_s^-1"]),
            idest1=id1, idest2=id2, opakab=float(ev.get("opakab_cm^-1") or 0.0), diagnostics=ev,
            context_fields_used=("temperature_k", "xpx", "xee", "ptmp1", "ptmp2", "radiation", "levels"),
        )

    def _eval_type54(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.collisions import anl1_py
        if len(r.integers)<4: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type54_short_record")
        a,b=r.integers[-4],r.integers[-3]; lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a)
        lu=c.levels.get(up); ll=c.levels.get(lo)
        if lu is None or ll is None or lu.principal_n is None or ll.principal_n is None or lu.orbital_l is None or ll.orbital_l is None:
            return self._base_result(r,s,UCalcStatus.CONTEXT_BLOCKED,reason="type54_requires_level_n_l")
        ni,nf,li,lf=lu.principal_n,ll.principal_n,lu.orbital_l,ll.orbital_l
        if ni==nf: return self._ctx_result(r,s,idest1=lo,idest2=up)
        if ni<nf: ni,nf=nf,ni
        iq=r.integers[-2]; alm,alp=anl1_py(ni,nf,lf,iq); rate=alm if li<lf else alp
        de=abs(c.levels.energy(up)-c.levels.energy(lo))
        delt=de/max(XSTAR_SOURCE_KT_EV_PER_1E4K*c.t,1.0e-300)
        return self._ctx_result(
            r,s,ans2=rate,ans3=-rate*delt*XSTAR_SOURCE_ERG_PER_EV,
            idest1=lo,idest2=up,
            diagnostics={
                "alm":alm,"alp":alp,"ni":ni,"nf":nf,"li":li,"lf":lf,
                "delta_energy_eV":de,"delt_dimensionless":delt,
                "source_ekt_eV":XSTAR_SOURCE_KT_EV_PER_1E4K*c.t,
            },
            context_fields_used=("temperature_k","levels"),
        )

    def _eval_type60(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate the shared XSTAR labels 60 and 62.

        Both branches enter label 60 in ``ucalc.f90`` and call
        ``calt6062.f90``.  Data type 60 is a pure polynomial in the reduced
        temperature.  Data type 62 adds the Callaway logarithmic/exponential
        tail carried by the final three real coefficients.  Earlier package
        versions incorrectly classified data type 62 as a source no-op; that
        omitted four H I records (488--491) and therefore sixteen matrix
        terms in the accepted call-73 all-element benchmark.
        """

        minimum_reals = 3 if int(r.data_type) == 60 else 6
        if len(r.integers) < 2 or len(r.reals) < minimum_reals:
            return self._base_result(
                r,
                s,
                UCalcStatus.INVALID_RECORD,
                reason=f"type{r.data_type}_short_record",
                diagnostics={
                    "n_integers": len(r.integers),
                    "n_reals": len(r.reals),
                    "minimum_reals": minimum_reals,
                },
            )

        packed_endpoint_1 = int(r.integers[0])
        packed_endpoint_2 = int(r.integers[1])
        endpoint_1 = c.levels.get(packed_endpoint_1)
        endpoint_2 = c.levels.get(packed_endpoint_2)
        if (
            packed_endpoint_1 <= 0
            or packed_endpoint_2 <= 0
            or packed_endpoint_1 > c.nlevp
            or packed_endpoint_2 > c.nlevp
            or endpoint_1 is None
            or endpoint_2 is None
        ):
            return self._base_result(
                r,
                s,
                UCalcStatus.SOURCE_REJECTED,
                reason="type6062_endpoint_outside_level_table",
                diagnostics={
                    "packed_endpoint_1": packed_endpoint_1,
                    "packed_endpoint_2": packed_endpoint_2,
                    "nlev": c.nlevp,
                },
            )

        lo, up = (
            (packed_endpoint_1, packed_endpoint_2)
            if float(endpoint_1.energy_ev) <= float(endpoint_2.energy_ev)
            else (packed_endpoint_2, packed_endpoint_1)
        )
        lower = c.levels.require(lo)
        upper = c.levels.require(up)
        de = abs(float(upper.energy_ev) - float(lower.energy_ev))
        if de <= 1.0e-24:
            return self._base_result(
                r,
                s,
                UCalcStatus.SOURCE_REJECTED,
                reason="type6062_zero_transition_energy",
                diagnostics={
                    "packed_endpoint_1": packed_endpoint_1,
                    "packed_endpoint_2": packed_endpoint_2,
                    "idest1": lo,
                    "idest2": up,
                    "delta_energy_eV": de,
                },
            )

        # ucalc.f90 label 60 raises the temperature only when required by the
        # source's 0.02*DeltaE floor, then calt6062 converts it to the reduced
        # Callaway temperature t1.  calt6062 sets tmax=1 unconditionally.
        source_temperature_floor_k = (
            0.02 * de * 1.0e4 / XSTAR_KT_EV_PER_1E4K
        )
        effective_temperature_k = max(
            float(c.temperature_k), source_temperature_floor_k
        )
        if effective_temperature_k > 1.0e9:
            t1 = 6.33652e3
        else:
            t1 = effective_temperature_k * 6.33652e-6
        tt = min(t1, 1.0)

        if int(r.data_type) == 60:
            polynomial_coefficients = tuple(float(value) for value in r.reals[2:])
            logarithmic_amplitude = None
            logarithmic_scale = None
            exponential_scale = None
            upsilon = sum(
                coefficient * tt**power
                for power, coefficient in enumerate(polynomial_coefficients)
            )
            fit_form = "callaway_type60_polynomial"
        else:
            polynomial_coefficients = tuple(float(value) for value in r.reals[2:-3])
            logarithmic_amplitude = float(r.reals[-3])
            logarithmic_scale = float(r.reals[-2])
            exponential_scale = float(r.reals[-1])
            log_argument = logarithmic_scale * tt
            if log_argument <= 0.0:
                return self._base_result(
                    r,
                    s,
                    UCalcStatus.SOURCE_REJECTED,
                    reason="type62_nonpositive_log_argument",
                    diagnostics={
                        "packed_endpoint_1": packed_endpoint_1,
                        "packed_endpoint_2": packed_endpoint_2,
                        "reduced_temperature_t1": t1,
                        "clamped_reduced_temperature_tt": tt,
                        "logarithmic_scale": logarithmic_scale,
                        "log_argument": log_argument,
                    },
                )
            polynomial = sum(
                coefficient * tt**power
                for power, coefficient in enumerate(polynomial_coefficients)
            )
            tail = (
                logarithmic_amplitude
                * math.log(log_argument)
                * math.exp(-exponential_scale * tt)
            )
            upsilon = polynomial + tail
            fit_form = "callaway_type62_polynomial_plus_log_exp_tail"

        if t1 > tt:
            logarithm = math.log(t1)
            upsilon *= 1.0 + logarithm / (logarithm + 1.0)

        gu = float(upper.statistical_weight)
        gl = float(lower.statistical_weight)
        if gu <= 1.0e-24 or gl <= 1.0e-24:
            return self._base_result(
                r,
                s,
                UCalcStatus.SOURCE_REJECTED,
                reason="type6062_nonpositive_statistical_weight",
                diagnostics={
                    "lower_statistical_weight": gl,
                    "upper_statistical_weight": gu,
                },
            )

        delt = de / max(
            XSTAR_KT_EV_PER_1E4K * c.t,
            1.0e-300,
        )
        exptmp = _expo(-delt)
        cji = 8.626e-8 * upsilon / c.tsq / (1.0e-16 + gu)
        cij = cji * gu * exptmp / (1.0e-16 + gl)
        ne = c.electron_density_cm3
        ans1 = cij * ne
        ans2 = cji * ne
        ans6 = ans1 * de * XSTAR_SOURCE_ERG_PER_EV
        ans5 = ans2 * de * XSTAR_SOURCE_ERG_PER_EV

        diagnostics = {
            "source_branch": f"ucalc_label_{r.data_type}_goto_60",
            "source_leaf": "calt6062",
            "fit_form": fit_form,
            "packed_endpoint_1": packed_endpoint_1,
            "packed_endpoint_2": packed_endpoint_2,
            "lower_endpoint": lo,
            "upper_endpoint": up,
            "lower_principal_n": lower.principal_n,
            "lower_orbital_l": lower.orbital_l,
            "lower_label": lower.label,
            "upper_principal_n": upper.principal_n,
            "upper_orbital_l": upper.orbital_l,
            "upper_label": upper.label,
            "lower_statistical_weight": gl,
            "upper_statistical_weight": gu,
            "lower_energy_eV": float(lower.energy_ev),
            "upper_energy_eV": float(upper.energy_ev),
            "delta_energy_eV": de,
            "delt_dimensionless": delt,
            "source_temperature_floor_K": source_temperature_floor_k,
            "effective_temperature_K": effective_temperature_k,
            "reduced_temperature_t1": t1,
            "clamped_reduced_temperature_tt": tt,
            "polynomial_coefficients": polynomial_coefficients,
            "logarithmic_amplitude": logarithmic_amplitude,
            "logarithmic_scale": logarithmic_scale,
            "exponential_scale": exponential_scale,
            "upsilon": upsilon,
            "cij_excitation_cm3_s": cij,
            "cji_deexcitation_cm3_s": cji,
            "exponential_boltzmann_factor": exptmp,
            "hydrogen_v0436_target_record": int(r.record) in {488, 489, 490, 491},
        }
        return self._ctx_result(
            r,
            s,
            ans1=ans1,
            ans2=ans2,
            ans5=ans5,
            ans6=ans6,
            idest1=lo,
            idest2=up,
            diagnostics=diagnostics,
            context_fields_used=("temperature_k", "xpx", "xee", "levels"),
        )

    def _eval_type65(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.xstar_element_solver import _xstar_szirc
        if not r.integers or not r.reals: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type65_short_record")
        id1=r.integers[-2] if len(r.integers)>=2 else 1; eth=max(0.0,c.levels.energy(c.nlevp)-c.levels.energy(id1))
        ci=_xstar_szirc(int(r.integers[0]),c.temperature_k,float(r.reals[0]),float(c.extras.get("type65_rno",c.nlevp+1)))
        if ci is None: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason="szirco_failed")
        ne=c.electron_density_cm3; ans1=ci*ne; gu=c.levels.weight(c.nlevp); gl=c.levels.weight(1)
        ans2=ans1*(2.08e-22)*gl/max(gu,1e-48)/max(c.t*c.tsq,1e-48)*_expo(eth/max(XSTAR_KT_EV_PER_1E4K*c.t,1e-48))
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*eth*ERG_PER_EV,ans6=ans1*eth*ERG_PER_EV,idest1=id1,idest2=c.nlevp,
            diagnostics={"cii_cm3_s":ci},context_fields_used=("temperature_k","xpx","xee","levels","type65_rno"))

    def _calt66(self,reals: Sequence[float],temp: float) -> float:
        from xstar_atomic.collisions import expint_scaled_py
        total=0.0
        for k in range(0,len(reals),6):
            if k+5>=len(reals): break
            de,a,b,cc,d,e=reals[k:k+6]; y=min(de/temp*1.160443e4,77.0)
            if y<=1e-20: continue
            em1=expint_scaled_py(y)
            total += y*((a/y+cc)+d*.5*(1-y))+em1*(b-cc*y+d*y*y*.5+e/y)
        return total

    def _eval_type66(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<6: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type66_short_record")
        a,b=r.integers[:2]; lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a)
        de=r.reals[0]; wav=12398.4016/max(de,1e-48); temp=max(c.temperature_k,2.8777e6/wav); ups=self._calt66(r.reals,temp)
        gu=c.levels.weight(up); gl=c.levels.weight(lo); ne=c.electron_density_cm3; ex=_expo(-de/(XSTAR_KT_EV_PER_1E4K*c.t))
        qd=8.626e-8*ups/c.tsq/max(gu,1e-48); qe=qd*gu*ex/max(gl,1e-48)
        return self._ctx_result(r,s,ans1=qe*ne,ans2=qd*ne,ans5=qd*ne*de*ERG_PER_EV,ans6=qe*ne*de*ERG_PER_EV,idest1=lo,idest2=up,
            diagnostics={"upsilon":ups,"effective_temperature_K":temp},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type73(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.collisions import expint_scaled_py, eint_py
        if len(r.integers)<3 or len(r.reals)<7: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type73_short_record")
        aidx,bidx=r.integers[:2]; lo,up=(aidx,bidx) if c.levels.energy(aidx)<=c.levels.energy(bidx) else (bidx,aidx)
        wav=abs(r.reals[0]); de=12398.4016/max(wav,1e-48); temp=max(c.temperature_k,2.8777e6/max(wav,1e-48)); z=float(r.integers[2]); y=z*z*r.reals[0]*1.578876e5/temp
        if y>40: return self._ctx_result(r,s,idest1=lo,idest2=up)
        z2s,aa,co,cr,cr1,rr=r.reals[1:7]; gam=-.2 if z2s>=.1 else (0.0 if z2s>.01 else .2); zeff=float(r.integers[2])-gam
        em1=expint_scaled_py(y); e1=em1/y*_expo(-y); ee1=ee2=ee3=0.0
        if y*aa+y<=80: ee1,ee2,ee3=eint_py(y*aa+y)
        er,er1=(ee1,ee2) if rr==1 else ((ee2,ee3) if rr==2 else (0.0,0.0))
        qij=co*_expo(-y)+1.55*z2s*e1
        if y*aa+y<=40: qij += y*_expo(y*aa)*(cr*er/(aa+1)**(rr-1)+cr1*er1/(aa+1)**rr)
        crate=max(qij*1.578876e5/temp*math.sqrt(temp)/max(zeff*zeff,1e-48)*5.46538e-11,0.0)
        gl=c.levels.weight(lo); gu=c.levels.weight(up); om=crate/max(gl,1e-48); ex=_expo(-de/(XSTAR_KT_EV_PER_1E4K*c.t)); ne=c.electron_density_cm3
        qd=8.626e-8*om/c.tsq/max(gu,1e-48); qe=qd*gu*ex/max(gl,1e-48)
        return self._ctx_result(r,s,ans1=qe*ne,ans2=qd*ne,ans5=qd*ne*de*ERG_PER_EV,ans6=qe*ne*de*ERG_PER_EV,idest1=lo,idest2=up,
            diagnostics={"crate":crate},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type101(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<2: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type101_short_record")
        a,b=r.integers[:2]; lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a); de=abs(c.levels.energy(up)-c.levels.energy(lo))
        nt=len(r.reals)//2
        if nt==1: om=r.reals[1]
        else:
            tg=r.reals[:nt]; vals=r.reals[nt:2*nt]; j=_linear_hunt(tg,math.log10(c.temperature_k)); om=vals[j]+(vals[j+1]-vals[j])*(math.log10(c.temperature_k)-tg[j])/max(tg[j+1]-tg[j],1e-24)
        om=max(om,0.0); gu=c.levels.weight(up); gl=c.levels.weight(lo); ex=_expo(-de/(XSTAR_KT_EV_PER_1E4K*c.t)); ne=c.electron_density_cm3
        qe=8.626e-8*om*ex/c.tsq/max(gl,1e-48); qd=8.626e-8*om/c.tsq/max(gu,1e-48)
        return self._ctx_result(r,s,ans1=qe*ne,ans2=qd*ne,ans5=qd*ne*de*ERG_PER_EV,ans6=qe*ne*de*ERG_PER_EV,idest1=lo,idest2=up,
            diagnostics={"upsilon":om},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type102(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<4 or len(r.reals)<7: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type102_short_record")
        up,lo=r.integers[2],r.integers[3]
        if c.levels.energy(up)<c.levels.energy(lo): up,lo=lo,up
        eij=1000.0*r.reals[0]; x=eij/max(XSTAR_KT_EV_PER_1E4K*c.t,1e-48); itype=r.integers[0]; a=list(r.reals[1:7])
        ind=((1,2,3,4,0,0,0,5,0),(1,2,3,4,0,0,0,0,0),(0,0,1,2,3,0,0,0,4),(1,2,3,4,0,0,0,5,6),(1,2,3,4,0,0,0,0,5),(0,0,1,2,3,4,0,0,5),(0,0,0,1,2,3,4,0,5),(6,0,1,2,3,4,0,0,5))
        if not 1<=itype<=8: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason="type102_bad_formula_type")
        par=[0.0]*9
        for j,k in enumerate(ind[itype-1]):
            if k: par[j]=a[k-1]
        xr=x*(1+par[8]); scaled1=_ee1expo(xr); en=[scaled1]
        for n in range(1,6): en.append((1.0-xr*en[-1])/n)
        omc=par[0]+xr*(par[1]*en[0]+par[2]*en[1]+2*par[3]*en[2]+6*par[4]*en[3]+24*par[5]*en[4]+120*par[6]*en[5])+par[7]*en[0]
        nr=min(max(r.integers[1],0),4); start=11; xs=list(r.reals[start:start+nr]); amps=list(r.reals[start+nr:start+2*nr]); omr=sum(aa*(xx*x)*_expo(-xx*x) for xx,aa in zip(xs,amps)); om=omc+omr
        gu=c.levels.weight(up); gl=c.levels.weight(lo); ne=c.electron_density_cm3; ex=_expo(-x); qd=8.626e-8*om/c.tsq/max(gu,1e-48); qe=qd*gu*ex/max(gl,1e-48)
        return self._ctx_result(r,s,ans1=qe*ne,ans2=qd*ne,ans5=qd*ne*eij*ERG_PER_EV,ans6=qe*ne*eij*ERG_PER_EV,idest1=lo,idest2=up,
            diagnostics={"omega_cont":omc,"omega_res":omr},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type57(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.xstar_element_solver import _xstar_calt57

        # Literal ucalc.f90 label-57 setup:
        #   i57   = idat(np1i)
        #   idest1= idat(np1i+nidt-2)
        #   idest2= nlevp
        #   e1    = rlev(1,idest1)
        #   eth   = max(0,rlev(1,nlevp)-rlev(1,idest1))
        #   ep    = eth
        # The calt57 gate compares ep with e1.  Passing the absolute parent
        # continuum energy instead of eth changes both the zero/nonzero gate
        # and every active ionization coefficient.
        i = r.integers
        i57 = int(i[0]) if i else 0
        id1 = int(i[-2]) if len(i) >= 2 else 1
        id2 = int(c.nlevp)
        if i57 <= 0 or id1 <= 1 or id1 > id2:
            return self._ctx_result(
                r, s, ans1=0.0, ans2=0.0, idest1=id1, idest2=id2,
                diagnostics={
                    "python_eval_status": "type57_ucalc_gate_zero",
                    "type57_i57": i57,
                    "type57_idest1": id1,
                    "type57_idest2": id2,
                },
                context_fields_used=("temperature_k", "xpx", "xee", "levels"),
            )

        lev = c.levels.require(id1)
        parent = c.levels.require(id2)
        n = int(lev.principal_n or i57)
        e1 = float(lev.energy_ev)
        eth = max(float(parent.energy_ev) - e1, 0.0)
        if eth <= 0.0:
            return self._ctx_result(
                r, s, ans1=0.0, ans2=0.0, idest1=id1, idest2=id2,
                diagnostics={
                    "python_eval_status": "type57_nonpositive_eth_zero",
                    "type57_i57": i57,
                    "type57_e1_ev": e1,
                    "type57_eth_ev": eth,
                },
                context_fields_used=("temperature_k", "xpx", "xee", "levels"),
            )

        ev = _xstar_calt57(
            c.temperature_k,
            c.electron_density_cm3,
            e1,
            eth,
            n,
        )
        ev = dict(ev)
        ev.update({
            "type57_ucalc_energy_convention": "e1_rlev1_ep_eth",
            "type57_i57": i57,
            "type57_e1_ev": e1,
            "type57_eth_ev": eth,
            "type57_ep_ev": eth,
        })
        cion = _finite(ev.get("type57_cion_cm3_s"))
        crec = _finite(ev.get("type57_crec_cm6_s"))
        if cion is None or crec is None:
            return self._base_result(
                r, s, UCalcStatus.SOURCE_REJECTED,
                reason=str(ev.get("python_eval_status")), diagnostics=ev,
            )
        g1 = max(lev.statistical_weight, 1e-48)
        g2 = max(parent.statistical_weight, 1e-48)
        ans1 = cion * c.electron_density_cm3
        ans2 = crec * (g1 / g2) * c.electron_density_cm3**2
        return self._ctx_result(
            r, s, ans1=ans1, ans2=ans2,
            ans5=-ans2 * eth * ERG_PER_EV,
            ans6=-ans1 * eth * ERG_PER_EV,
            idest1=id1, idest2=id2, diagnostics=ev,
            context_fields_used=("temperature_k", "xpx", "xee", "levels"),
        )

    def _eval_type71(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.rates_type71 import evaluate_type71_ucalc_record
        decoded={"reals":list(r.reals),"ints":list(r.integers)}
        i=r.integers; id1=i[-4] if len(i)>=4 else 0; id2=i[-3] if len(i)>=3 else 0
        level1 = c.levels.get(id1) if id1 > 0 else None
        level2 = c.levels.get(id2) if id2 > 0 else None
        ev=evaluate_type71_ucalc_record(
            decoded, temperature_k=c.temperature_k,
            electron_density_cm3=c.hydrogen_density_cm3,
            ptmp1=c.ptmp1, ptmp2=c.ptmp2,
            endpoint1_energy_ev=None if level1 is None else level1.energy_ev,
            endpoint2_energy_ev=None if level2 is None else level2.energy_ev,
        )
        ans2=_finite(ev.get("ans2_downward_s^-1"))
        ans3=_finite(ev.get("ans3_cooling_signed_erg_s^-1"))
        ans4=_finite(ev.get("ans4_heating_signed_erg_s^-1"))
        if ans2 is None or ans3 is None or ans4 is None:
            return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=str(ev.get("reason") or ev.get("status")),diagnostics=ev)
        return self._ctx_result(
            r,s,ans1=0.0,ans2=ans2,ans3=ans3,ans4=ans4,
            idest1=id1,idest2=id2,diagnostics=ev,
            context_fields_used=("temperature_k","xpx","ptmp1","ptmp2","levels"),
        )

    def _calt72_rate(self, r: UCalcRecord, c: UCalcContext) -> float:
        if len(r.reals) < 2: return 0.0
        dele=r.reals[1]; scale=3.3e-11*(13.6/(XSTAR_KT_EV_PER_1E4K*c.t))**1.5
        rtmp=r.reals[2] if len(r.reals)>=3 else 1.0
        return scale*_expo(-dele/(XSTAR_KT_EV_PER_1E4K*c.t))*(r.reals[0]/1e13)*rtmp

    def _eval_type72(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        rate=self._calt72_rate(r,c); ne=c.electron_density_cm3; i=r.integers
        id1=i[-4] if len(i)>=4 else 1; id2=i[-3] if len(i)>=3 else c.nlevp
        gu=c.levels.weight(c.nlevp); gl=c.levels.weight(1); rinf=2.08e-22*gl/max(gu,1e-48)/max(c.t*c.tsq,1e-48)
        de=r.reals[1] if len(r.reals)>1 else 0.0
        return self._ctx_result(r,s,ans1=rate*ne*rinf*ne*_expo(de/c.temperature_k),ans2=rate*ne,idest1=id1,idest2=id2,
            diagnostics={"calt72_rate_cm3_s":rate},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type74(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate XSTAR ``ucalc`` label 74 and ``calt74.f90``.

        Type 74 supplies delta-function resonances added to a bound-free
        photoionization cross section.  ``calt74`` returns a forward
        radiation rate and an *unweighted* DR coefficient.  The source then
        applies only ``g_lower/g_continuum`` to the reverse coefficient; it
        does not multiply either branch by density inside label 74.
        """
        rd = tuple(float(x) for x in r.reals)
        ints = r.integers
        if len(rd) < 3 or len(ints) < 2:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type74_short_record")
        m = (len(rd) - 1) // 2
        if m <= 0 or 1 + 2 * m > len(rd):
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type74_bad_delta_coefficient_layout")
        if c.radiation is None:
            return self._context_blocked(r, s, "type74_requires_live_radiation")
        try:
            epi, bremsa, _ = _radiation_arrays(c.radiation)
        except Exception as exc:
            return self._context_blocked(r, s, f"type74_live_radiation:{exc}")
        if len(epi) < 2 or len(epi) != len(bremsa):
            return self._context_blocked(r, s, "type74_invalid_live_radiation_grid")

        # Literal coefficient layout from calt74.f90.
        xt = rd[0]
        energies = rd[1:1 + m]
        heights = rd[1 + m:1 + 2 * m]
        te = float(c.temperature_k) * 1.38066e-16
        ryk = 4.589343e10
        alpha_sum = 0.0
        alpha_terms_used = 0
        alpha_terms_skipped = 0
        for x, hgh in zip(energies, heights):
            arg = x / max(ryk * te, 1.0e-300)
            if arg < 40.0:
                alpha_sum += _expo(-arg) * (x + xt) * (x + xt) * hgh
                alpha_terms_used += 1
            else:
                alpha_terms_skipped += 1
        alpha = alpha_sum * 213.9577e-9 / max(te ** 1.5 * ryk * ryk, 1.0e-300)

        # Source calt74 returns a zero forward rate when its final resonance
        # lies above the live grid.  Otherwise linearly interpolate bremsa at
        # every resonance energy and apply the literal conversion factor.
        ry_ev = 13.60569253
        resonance_energies = tuple((x + xt) * ry_ev for x in energies)
        rate_sum = 0.0
        rate_terms_used = 0
        if resonance_energies and resonance_energies[-1] <= float(epi[-1]):
            for eres, hgh in zip(resonance_energies, heights):
                if eres < float(epi[0]) or eres > float(epi[-1]):
                    continue
                k = _linear_hunt(epi, eres)
                e0, e1 = float(epi[k]), float(epi[k + 1])
                b0, b1 = float(bremsa[k]), float(bremsa[k + 1])
                frac = 0.0 if e1 == e0 else (eres - e0) / (e1 - e0)
                rate_sum += (b0 + frac * (b1 - b0)) * hgh
                rate_terms_used += 1
        rate = rate_sum * 4.752e-22

        # ucalc.f90 label 74 endpoint semantics:
        # idest1=idat(np1i+nidt-2), idest2=nlevp,
        # idest3=idat(np1i+nidt-1), idest4=idest3+1.
        id1 = int(ints[-2])
        id2 = int(c.nlevp)
        id3 = int(ints[-1])
        id4 = id3 + 1
        gglo = c.levels.weight(id1)
        ggup = c.levels.weight(id2)
        if gglo <= 0.0 or ggup <= 1.0e-24:
            return self._context_blocked(r, s, "type74_missing_or_bad_statistical_weights")
        ans2 = alpha * gglo / ggup
        diagnostics = {
            "type74_calt74_status": "evaluated_type74_calt74_live",
            "type74_rate_unweighted_s^-1": rate,
            "type74_alpha_unweighted_cm3_s": alpha,
            "type74_statistical_weight_ratio": gglo / ggup,
            "type74_m_delta_count": m,
            "type74_delta_terms_alpha_used": alpha_terms_used,
            "type74_delta_terms_alpha_skipped_arg_ge_40": alpha_terms_skipped,
            "type74_delta_terms_rate_used": rate_terms_used,
            "type74_resonance_energy_eV_min": min(resonance_energies) if resonance_energies else None,
            "type74_resonance_energy_eV_max": max(resonance_energies) if resonance_energies else None,
            "source_zero_reverse_rate": bool(alpha == 0.0),
        }
        return self._ctx_result(
            r, s, ans1=rate, ans2=ans2, idest1=id1, idest2=id2,
            idest3=id3, idest4=id4, diagnostics=diagnostics,
            context_fields_used=("temperature_k", "radiation", "levels"),
        )

    def _eval_type75(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        i=r.integers; id1=max(i[-3] if len(i)>=3 else 1,1); id2=max((i[-2] if len(i)>=2 else 1)+c.nlevp-1,1)
        rate=self._calt72_rate(r,c)
        return self._ctx_result(r,s,ans2=rate*c.electron_density_cm3,idest1=id1,idest2=id2,
            diagnostics={"calt72_rate_cm3_s":rate},context_fields_used=("temperature_k","xpx","xee"))

    def _eval_type79(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<5: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type79_short_record")
        a,b=r.integers[:2]; up,lo=(a,b) if c.levels.energy(a)>=c.levels.energy(b) else (b,a)
        wav=abs(r.reals[0]); f=r.reals[1]; mass=r.reals[4]; gu=c.levels.weight(up); gl=c.levels.weight(lo)
        aij=6.67e7*gl*f/max(gu,1e-48)/(wav*1e-4)**2
        if f<=1.01e-12 or wav>=1e9: aij=1e5
        v=math.sqrt((c.turbulent_velocity_km_s*1e5)**2+(1.29e6/math.sqrt(max(mass/c.t,1e-48)))**2)
        op=.02655*f*wav*1e-8/v
        return self._ctx_result(r,s,ans1=aij*(c.ptmp1+c.ptmp2),ans4=aij*(c.ptmp1+c.ptmp2)*12398.4016/wav*ERG_PER_EV,
            idest1=up,idest2=lo,opakab=op,context_fields_used=("temperature_k","turbulent_velocity_km_s","ptmp1","ptmp2","levels"))

    def _eval_type86(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.reals) < 2 or len(r.integers) < 5:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type86_short_record")
        # ucalc.f90 label 86:
        #   idest1=idat(np1i-1+nidt-3)  -> zero-based packed integer [-4]
        #   idest2=nlevp+idat(np1i-1+nidt-4)-1 -> packed integer [-5]
        # The previous Python translation used [-3]/[-4], shifting both
        # endpoints by one metadata field and moving very large Auger rates
        # into the wrong compact superlevels.
        id1 = r.integers[-4]
        id2 = c.nlevp + r.integers[-5] - 1
        return self._ctx_result(r, s, ans1=r.reals[1], idest1=id1, idest2=id2)

    def _eval_type76(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers) < 2 or len(r.reals) < 1:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type76_short_record")
        # ucalc.f90 label 76 starts with ans1=A and ans2=0, constructs the
        # two-photon emissivity spectrum, then performs the universal final
        # swap.  The matrix-facing result is therefore ans1=0, ans2=A.  The
        # line escape factors ptmp1/ptmp2 are not applied to the two-photon
        # population decay rate.
        id1, id2 = int(r.integers[0]), int(r.integers[1])
        aij = max(float(r.reals[0]), 0.0)
        de = abs(c.levels.energy(id1) - c.levels.energy(id2))
        return self._ctx_result(
            r,
            s,
            ans1=0.0,
            ans2=aij,
            ans3=-aij * de * ERG_PER_EV,
            ans4=0.0,
            idest1=id1,
            idest2=id2,
            context_fields_used=("levels",),
        )

    def _eval_type77(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.xstar_element_solver import _xstar_calt77_rates
        i = r.integers
        id1 = i[-4] if len(i) >= 4 else 0
        id2 = i[-3] if len(i) >= 3 else 0

        # ucalc.f90 label 77 applies these gates before calling calt77.  A
        # source-zero result must remain EVALUATED with the valid endpoints so
        # calc_hmc_ion still emits the normal four zero-valued matrix roles.
        nlev = int(c.nlevp)
        if id1 <= 0 or id1 > nlev or id2 <= 0 or id2 > nlev:
            return self._base_result(
                r, s, UCalcStatus.SOURCE_REJECTED,
                reason="type77_endpoint_outside_active_level_range",
                idest1=id1, idest2=id2,
                diagnostics={
                    "type77_source_gate": "endpoint_outside_active_level_range",
                    "type77_nlev": nlev,
                },
            )
        if id1 == id2:
            return self._ctx_result(
                r, s, idest1=id1, idest2=id2,
                diagnostics={
                    "type77_source_gate": "identical_endpoints_zero",
                    "type77_endpoint_energy_difference_eV": 0.0,
                    "type77_calt77_status": "not_called_source_identical_endpoint_gate",
                },
                context_fields_used=("levels",),
            )

        e1 = c.levels.energy(id1)
        e2 = c.levels.energy(id2)
        signed_de = float(e2) - float(e1)
        de = abs(signed_de)
        if de < 1.0:
            return self._ctx_result(
                r, s, idest1=id1, idest2=id2,
                diagnostics={
                    "type77_source_gate": "endpoint_energy_separation_below_1_eV_zero",
                    "type77_endpoint_energy_difference_eV": de,
                    "type77_endpoint_signed_energy_difference_eV": signed_de,
                    "type77_calt77_status": "not_called_source_abs_delta_e_lt_1_eV_gate",
                },
                context_fields_used=("levels",),
            )

        endpoint_wav = 12398.4016 / (signed_de + 1.0e-24)

        ev = _xstar_calt77_rates(
            temperature=float(c.temperature_k),
            electron_density=float(c.hydrogen_density_cm3),
            ion_charge=c.extras.get("ion_charge"),
            reals=list(r.reals),
            ints=list(r.integers),
            temperature_floor_wavelength_a=endpoint_wav,
        )
        # Bounded diagnostic only: reproduce the pre-v0.4.27 record-tail floor
        # so the fixed-population effect can be audited without feeding probe or
        # legacy values back into the production operator.
        legacy = _xstar_calt77_rates(
            temperature=float(c.temperature_k),
            electron_density=float(c.hydrogen_density_cm3),
            ion_charge=c.extras.get("ion_charge"),
            reals=list(r.reals),
            ints=list(r.integers),
        )
        ans1 = _finite(ev.get("type77_calt77_clu_s^-1"))
        ans2 = _finite(ev.get("type77_calt77_cul_s^-1"))
        if ans1 is None or ans2 is None:
            return self._base_result(
                r, s, UCalcStatus.SOURCE_REJECTED,
                reason=str(ev.get("type77_calt77_status") or "calt77_failed"),
                diagnostics=ev,
            )
        diagnostics = dict(ev)
        diagnostics.update({
            "type77_endpoint_energy_difference_eV": de,
            "type77_endpoint_signed_energy_difference_eV": signed_de,
            "type77_source_floor_wavelength_A": endpoint_wav,
            "type77_legacy_record_floor_clu_s^-1": legacy.get("type77_calt77_clu_s^-1"),
            "type77_legacy_record_floor_cul_s^-1": legacy.get("type77_calt77_cul_s^-1"),
            "type77_legacy_record_floor_log10_temperature_used": legacy.get("type77_calt77_log10_temperature_used"),
            "type77_source_minus_legacy_clu_s^-1": (
                float(ans1) - float(legacy.get("type77_calt77_clu_s^-1"))
                if legacy.get("type77_calt77_clu_s^-1") is not None else None
            ),
            "type77_source_minus_legacy_cul_s^-1": (
                float(ans2) - float(legacy.get("type77_calt77_cul_s^-1"))
                if legacy.get("type77_calt77_cul_s^-1") is not None else None
            ),
            "type77_impact_audit_role": "diagnostic_fixed_population_source_vs_legacy_floor",
        })
        return self._ctx_result(
            r, s,
            ans1=ans1, ans2=ans2,
            ans5=ans2 * de * ERG_PER_EV,
            ans6=ans1 * de * ERG_PER_EV,
            idest1=id1, idest2=id2,
            diagnostics=diagnostics,
            context_fields_used=("temperature_k", "xpx", "levels"),
        )

    def _eval_type95(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.xstar_element_solver import _xstar_eint
        if len(r.reals) < 6 or len(r.integers) < 2:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type95_short_record")
        ee = float(r.reals[0])
        ns = (len(r.reals) - 2) // 2
        if ee <= 0.0 or ns < 2 or 2 + 2 * ns > len(r.reals):
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type95_bad_spline_record")
        tt = (XSTAR_KT_EV_PER_1E4K * c.t) / ee
        if tt <= 0.0:
            return self._base_result(r, s, UCalcStatus.SOURCE_REJECTED, reason="type95_bad_scaled_temperature")
        xx = 1.0 - 0.693147 / math.log(tt + 2.0)

        # Reproduce the source's 1-based upper-bracket search and literal
        # spline storage offsets rather than NumPy's endpoint-clamping interp.
        rd = tuple(float(x) for x in r.reals)
        mm = 1
        while mm < ns and xx > rd[1 + mm]:
            mm += 1
        ly, ry = ns + mm, 1 + ns + mm
        lx, rx = mm, 1 + mm
        if max(ly, ry, lx, rx) >= len(rd):
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type95_spline_index_out_of_range")
        denom = rd[rx] - rd[lx]
        if denom == 0.0:
            return self._base_result(r, s, UCalcStatus.INVALID_RECORD, reason="type95_zero_spline_interval")
        rho = rd[ly] + (xx - rd[lx]) * (rd[ry] - rd[ly]) / denom

        # ucalc label 95 calls eint(), whose first output is E1(x).  The old
        # translation used expint's scaled em1=x*exp(x)*E1(x) directly.
        e1, _, _ = _xstar_eint(1.0 / tt)
        if e1 is None:
            return self._base_result(r, s, UCalcStatus.SOURCE_REJECTED, reason="eint_failed")
        citmp1 = 1.0e-6 * e1 * rho / math.sqrt(tt * ee ** 3)
        ans1 = citmp1 * c.electron_density_cm3

        if r.rate_type == 5:
            id1 = int(r.integers[0])
            id2 = int(c.nlevp - 1 + r.integers[1]) if len(r.integers) >= 3 else int(c.nlevp)
        else:
            id1 = id2 = 1
        g1 = c.levels.weight(id1)
        g2 = c.levels.weight(c.nlevp)
        if g1 <= 0.0 or g2 <= 1.0e-24:
            return self._context_blocked(r, s, "type95_missing_or_bad_statistical_weights")
        rinf = 2.08e-22 * g1 / g2 / max(c.t * c.tsq, 1.0e-300)
        ans2 = ans1 * rinf * c.electron_density_cm3 / _expo(-1.0 / tt)
        return self._ctx_result(
            r, s, ans1=ans1, ans2=ans2, ans5=ans2 * ee * ERG_PER_EV,
            ans6=ans1 * ee * ERG_PER_EV, idest1=id1, idest2=id2,
            diagnostics={"rho": rho, "e1": e1, "scaled_temperature_tt": tt,
                         "spline_upper_index_fortran": mm},
            context_fields_used=("temperature_k", "xpx", "xee", "levels"),
        )

    def _eval_type96(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        i=r.integers; id1=max(i[-3] if len(i)>=3 else 1,1); id2=max((i[-2] if len(i)>=2 else 1)+c.nlevp-1,1)
        dele=r.reals[2]; rate=2.069e-3/c.temperature_k**1.5*_expo(-dele/(XSTAR_KT_EV_PER_1E4K*c.t))*r.reals[1]
        return self._ctx_result(r,s,ans2=rate*c.electron_density_cm3,idest1=id1,idest2=id2,
                                context_fields_used=("temperature_k","xpx","xee"))

    def _eval_type99(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate ``calt99 -> phint53hunt`` with the live radiation grid."""
        from xstar_atomic.xstar_element_solver import _xstar_calt99_superlevel_bound_free
        i = r.integers
        # ucalc.f90 label 99:
        #   idest1 = idat(np1i+nidt-2)          -> packed integer [-2]
        #   idest2 = nlev+idat(np1i-1+nidt-3)-1
        #          = nlev+packed integer [-4]-1
        #
        # The packed [-3] field is the linked parent-ion/element identity,
        # not the parent-level offset.  Using it moves type-99 source/sink
        # terms into unrelated excited-parent compact rows.
        id1 = min(int(i[-2]) if len(i) >= 2 else 1, max(c.nlevp - 1, 1))
        off = int(i[-4]) if len(i) >= 4 else 1
        id2 = max(c.nlevp + off - 1, c.nlevp)
        if c.radiation is None:
            return self._context_blocked(r, s, "type99_requires_live_radiation")
        try:
            bound = c.levels.require(id1)
            continuum = c.levels.require(c.nlevp)
        except KeyError as exc:
            return self._context_blocked(r, s, f"type99_level_context:{exc}")
        parent_excitation, destination_g = self._parent_destination_context(c, id2)
        if id2 > c.nlevp:
            threshold_ev = abs(bound.energy_ev + parent_excitation)
            physical_destination_energy = continuum.energy_ev + parent_excitation
        else:
            threshold_ev = abs(bound.energy_ev - continuum.energy_ev)
            physical_destination_energy = continuum.energy_ev
        destination_energy = self._leveltemp_destination_energy(
            c, id2, physical_destination_energy
        )
        if threshold_ev <= 0.0 or bound.statistical_weight <= 0.0 or destination_g <= 0.0:
            return self._context_blocked(r, s, "type99_missing_or_bad_threshold_or_statistical_weight")
        threshold_ryd = threshold_ev / 13.6
        ev = _xstar_calt99_superlevel_bound_free(
            temperature=c.temperature_k,
            electron_density=c.electron_density_cm3,
            calt99_density=c.hydrogen_density_cm3,
            threshold_ry=threshold_ryd,
            bound_stat_weight=bound.statistical_weight,
            continuum_stat_weight=destination_g,
            reals=list(r.reals),
            ints=list(r.integers),
            radiation_context_rows=None,
        )
        rec = _finite(ev.get("type99_calt99_rec_cm3_s"))
        e_ryd = ev.get("type99_cross_section_energy_ryd")
        sigma = ev.get("type99_cross_section_scaled_cm2")
        if rec is None or not e_ryd or not sigma:
            return self._base_result(r, s, UCalcStatus.CONTEXT_BLOCKED, reason=str(ev.get("type99_calt99_status")), diagnostics=ev)
        swrat = bound.statistical_weight / max(destination_g, 1.0e-300)
        ph = _phint53hunt_exact(
            energy_above_threshold_ryd=e_ryd, cross_section_cm2=sigma,
            threshold_ev=threshold_ev, context=c, swrat=swrat, crit=0.01,
        )
        ans2d = _finite(ph.get("rrrt"))
        if ans2d is None or ans2d <= 1.0e-48:
            return self._ctx_result(r, s, idest1=id1, idest2=id2, diagnostics={**ev, **ph, "type99_scale": 0.0},
                                    context_fields_used=("temperature_k", "xpx", "xee", "radiation", "levels"))
        scale = rec * c.electron_density_cm3 / ans2d
        ans1 = float(ph["pirt"]) * scale
        ans2 = rec * c.electron_density_cm3
        ans3 = float(ph["piht"]) * scale
        ans4 = float(ph["rrcl"])
        ans5_pre = float(ph["piht2"]) * scale
        ans6_pre = float(ph["rrcl2"])
        ans5 = -ans6_pre
        ans6 = -ans5_pre
        ans3, ans4 = -ans4, -ans3
        energy_difference = destination_energy - bound.energy_ev
        ans6 *= (abs(ans4) - energy_difference * XSTAR_SOURCE_ERG_PER_EV * ans1) / max(1.0e-43, abs(ans4) - threshold_ev * XSTAR_SOURCE_ERG_PER_EV * ans1)
        ans5 *= (abs(ans3) - energy_difference * XSTAR_SOURCE_ERG_PER_EV * ans2) / max(1.0e-43, abs(ans3) - threshold_ev * XSTAR_SOURCE_ERG_PER_EV * ans2)
        diagnostics = {
            **ev,
            **ph,
            "type99_threshold_eV_derived": threshold_ev,
            "type99_swrat": swrat,
            "type99_scale": scale,
            "type99_parent_level_offset_packed_index": -4,
            "type99_parent_level_offset": off,
            "type99_calt99_density_semantics": "hydrogen_density_xpx",
            "type99_phint53hunt_density_semantics": "electron_density_xpx_times_xee",
            "type99_physical_parent_destination_energy_eV": physical_destination_energy,
            "type99_leveltemp_destination_energy_eV": destination_energy,
            "type99_leveltemp_workspace_semantics": "persistent_higher_columns",
        }
        return self._ctx_result(
            r, s, ans1=ans1, ans2=ans2, ans3=ans3, ans4=ans4, ans5=ans5, ans6=ans6,
            idest1=id1, idest2=id2, diagnostics=diagnostics,
            context_fields_used=("temperature_k", "xpx", "xee", "radiation", "levels"),
        )


def default_source_faithful_ucalc() -> SourceFaithfulUCalc:
    return SourceFaithfulUCalc()


__all__ = [
    "UCalcLevel", "UCalcLevelTable", "UCalcRecord", "UCalcContext",
    "UCalcStatus", "UCalcProvenance", "UCalcResult", "UCalcExecutionError",
    "UCalcUntranslatedBranch", "UCalcBranchSpec", "SourceFaithfulUCalc",
    "complete_ucalc_branch_catalog", "default_source_faithful_ucalc",
]
