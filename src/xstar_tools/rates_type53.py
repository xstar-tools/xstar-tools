"""Source-aligned XSTAR data-type 53 photoionization/Milne evaluator.

This module ports the rate-grid kernel in ``xstarlib/src/phint53.f90`` and the
surrounding type-53 branch in ``ucalc.f90``.  For the continuum side effects
that populate ``opakc``, ``opakcont`` and ``rccemis(1:2)``, the physical runner
supplies the live high-resolution radiation state: ``epi``, ``bremsa`` and
``bremsint``.  The dataclass field name ``epim_eV`` is retained for compatibility
with older callers, but the production type-53 path must not use the reduced
``epim``/``bremsam`` grid.  No analytic or empirical continuum normalization is
accepted.

The matrix gate primarily uses ``ans1`` (photoionization) and ``ans2`` (Milne
recombination).  The implementation also returns the two heating/cooling pairs
and, when bound/parent populations are supplied, the opacity and RRC-emissivity
arrays produced by the same source loop.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

RYDBERG_EV = 13.605692
ERG_PER_EV = 1.602176634e-12
BOLTZMANN_ERG_K = 1.380649e-16
XSTAR_KT_EV_PER_1E4K = 0.861707


def _expo(value: float) -> float:
    """XSTAR ``expo.f90``: exponential with the historical +/-60 clamp."""
    return math.exp(min(max(float(value), -60.0), 60.0))


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


@dataclass(frozen=True)
class Type53LiveRadiationState:
    """One exact radiation state supplied to ``phint53``.

    In production this is the full high-resolution continuum grid used by
    ``fstepr4``/``xoNN_detal4``.  ``bremsint`` is carried as a first-class array
    because it is part of the XSTAR call state, although the current
    ``phint53.f90`` implementation consumes the energy grid and radiation field
    directly.
    """

    epim_eV: tuple[float, ...]
    bremsam: tuple[float, ...]
    bremsint: tuple[float, ...]
    metadata: Mapping[str, Any]

    @classmethod
    def from_sequences(
        cls,
        epim_eV: Sequence[float],
        bremsam: Sequence[float],
        bremsint: Sequence[float] | None = None,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "Type53LiveRadiationState":
        epi = tuple(float(v) for v in epim_eV)
        brem = tuple(float(v) for v in bremsam)
        bint = tuple(float(v) for v in (bremsint if bremsint is not None else [0.0] * len(epi)))
        return cls(epi, brem, bint, dict(metadata or {}))

    def validate(self) -> dict[str, Any]:
        n = len(self.epim_eV)
        same = n == len(self.bremsam) == len(self.bremsint)
        monotonic = all(self.epim_eV[i + 1] > self.epim_eV[i] for i in range(max(0, n - 1)))
        finite = all(math.isfinite(v) for seq in (self.epim_eV, self.bremsam, self.bremsint) for v in seq)
        nonnegative = all(v >= 0.0 for v in self.bremsam)
        return {
            "n_grid_points": n,
            "array_lengths_match": same,
            "energy_grid_strictly_increasing": monotonic,
            "all_values_finite": finite,
            "bremsam_nonnegative": nonnegative,
            "ready": bool(n >= 3 and same and monotonic and finite and nonnegative),
            "type53_grid_policy": str(self.metadata.get("type53_grid_policy", "unspecified")),
            "type53_grid_source": str(self.metadata.get("type53_grid_source", "unspecified")),
            "type53_reduced_grid_points": int(self.metadata.get("type53_reduced_grid_points", 0) or 0),
            "type53_full_grid_points": int(self.metadata.get("type53_full_grid_points", n) or n),
        }


@dataclass(frozen=True)
class Type53PhintResult:
    """Outputs of the source-aligned ``phint53`` kernel before ucalc swaps."""

    pirt_s_inv: float
    rrrt_s_inv: float
    piht_erg_s_inv: float
    rrcl_erg_s_inv: float
    piht2_erg_s_inv: float
    rrcl2_erg_s_inv: float
    opakab_cm_inv: float
    opakc_cm_inv: tuple[float, ...]
    opakcont_cm_inv: tuple[float, ...]
    rccemis_inward: tuple[float, ...]
    rccemis_outward: tuple[float, ...]
    diagnostics: Mapping[str, Any]


def _lower_bracket_index(energy: float, grid: Sequence[float], usable_n: int) -> int:
    """Return the zero-based lower bracket equivalent of ``nbinc`` adjustment."""
    n = min(len(grid), max(1, int(usable_n)))
    if n <= 1 or energy <= grid[0]:
        return 0
    lo, hi = 0, n - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if grid[mid] <= energy:
            lo = mid
        else:
            hi = mid
    if grid[hi] <= energy:
        return hi
    return lo


def _metadata_grid(metadata: Mapping[str, Any], *keys: str) -> tuple[float, ...]:
    """Extract an optional diagnostic energy grid from metadata."""
    for key in keys:
        values = metadata.get(key)
        if values is None:
            continue
        try:
            out = tuple(float(v) for v in values)
        except Exception:
            continue
        if len(out) >= 3 and all(math.isfinite(v) for v in out):
            return out
    return ()


def _full_grid_mapping_diagnostics(
    *,
    threshold_eV: float,
    mapped_nb1_1based: int,
    live_radiation: Type53LiveRadiationState,
    tolerance_bins: int = 3,
) -> dict[str, Any]:
    """Compare the mapped threshold bin with the full ``epi`` grid.

    This catches the historical bug where type-53 side-effect arrays were
    mapped on the reduced ``epim``/``bremsam`` grid and then accumulated into
    the full 9999-bin detail workspace.
    """
    metadata = live_radiation.metadata
    grid_source = str(metadata.get("type53_grid_source", "unspecified"))
    full_grid = _metadata_grid(
        metadata,
        "type53_full_epi_eV",
        "type53_expected_full_epi_eV",
        "full_epi_eV",
    )
    if not full_grid and grid_source == "full_epi_bremsa":
        full_grid = tuple(float(v) for v in live_radiation.epim_eV)
    if not full_grid:
        return {
            "expected_full_grid_nb1": 0,
            "type53_nb1_full_grid_delta": 0,
            "type53_full_grid_mismatch": False,
            "type53_full_grid_check_status": "not_available",
            "type53_full_grid_tolerance_bins": int(tolerance_bins),
        }
    n_full = len(full_grid)
    numcon2 = max(2, n_full // 50)
    usable_n = max(1, n_full - numcon2)
    expected = _lower_bracket_index(float(threshold_eV), full_grid, usable_n) + 1
    delta = int(mapped_nb1_1based) - int(expected)
    mismatch = abs(delta) > int(tolerance_bins)
    return {
        "expected_full_grid_nb1": int(expected),
        "type53_nb1_full_grid_delta": int(delta),
        "type53_full_grid_mismatch": bool(mismatch),
        "type53_full_grid_check_status": "checked",
        "type53_full_grid_tolerance_bins": int(tolerance_bins),
    }


def _map_cross_section_phint53(
    *,
    energy_above_threshold_ryd: Sequence[float],
    cross_section_cm2: Sequence[float],
    threshold_eV: float,
    epim_eV: Sequence[float],
) -> tuple[list[float], int, int, dict[str, Any]]:
    """Port the ``sgbar`` mapping loop in ``phint53.f90``.

    The source intentionally stops when its cross-section cursor reaches
    ``ntmp-1`` (Fortran indexing), leaving the final packed point as an upper
    range marker.  This historical behavior is preserved here.
    """
    ncn2 = len(epim_eV)
    ntmp = min(len(energy_above_threshold_ryd), len(cross_section_cm2))
    sgbar = [0.0] * ncn2
    numcon2 = max(2, ncn2 // 50)
    nphint_1 = ncn2 - numcon2  # Fortran 1-based maximum useful index.
    if ntmp <= 0 or ncn2 < 3:
        return sgbar, 0, 0, {"status": "empty_cross_section_or_grid", "nphint_1based": nphint_1}

    xs = [float(threshold_eV) + float(energy_above_threshold_ryd[i]) * RYDBERG_EV for i in range(ntmp)]
    ys = [max(0.0, float(cross_section_cm2[i])) for i in range(ntmp)]
    ener = xs[0]
    nb1 = _lower_bracket_index(ener, epim_eV, nphint_1)
    if nb1 + 1 >= nphint_1:
        return sgbar, nb1, nb1, {"status": "threshold_in_guard_tail", "nphint_1based": nphint_1}

    # Fortran sets sgbar(max(1,nb1-1)) and sgbar(nb1) to zero.
    sgbar[max(0, nb1 - 1)] = 0.0
    sgbar[nb1] = 0.0
    k = nb1
    j = 0
    e1 = float(epim_eV[k])
    e2 = xs[j]
    s2 = ys[j]
    if e1 < e2 and k + 1 < ncn2:
        k += 1
        e1 = float(epim_eV[k])
    e1o = e2
    integral = 0.0
    done = False
    iterations = 0
    max_iterations = max(8, 4 * (ncn2 + ntmp))
    e2o = e2
    s2o = s2
    s2t = s2
    e2t = e1

    while not done and iterations < max_iterations and k < ncn2:
        iterations += 1
        advanced = False
        # Fortran: while (e2 < e1 .and. jk < ntmp-1), with jk 1-based.
        while e2 < e1 and j < ntmp - 2:
            j += 1
            e2o, s2o = e2, s2
            e2, s2 = xs[j], ys[j]
            integral += (s2 + s2o) * (e2 - e2o) / 2.0
            advanced = True
        if not advanced and iterations == 1:
            # Defensive initialization for pathological grids.  Normal XSTAR
            # grids enter the loop at least once because nb1 is the lower bin.
            e2o, s2o = e2, s2

        integral -= (s2 + s2o) * (e2 - e2o) / 2.0
        e2t = e1
        if e2 - e2o > 1.0e-8:
            s2t = s2o + (s2 - s2o) * (e2t - e2o) / (e2 - e2o + 1.0e-24)
        else:
            s2t = s2o
        integral += (s2t + s2o) * (e2t - e2o) / 2.0
        denom = e1 - e1o
        sgbar[k] = integral / denom if abs(denom) > 1.0e-36 else 0.0
        e1o = e1
        k += 1
        if k >= ncn2:
            break
        e1 = float(epim_eV[k])

        while e1 < e2 and k < ncn2 - 1:
            e2t = e1
            if e2 - e2o > 1.0e-8:
                s2t = s2o + (s2 - s2o) * (e2t - e2o) / (e2 - e2o)
            else:
                s2t = s2o
            # Preserve the source assignment s2to=s2t followed by a one-point
            # trapezoid over the rate-grid interval.
            integral = s2t * (e1 - e1o)
            denom = e1 - e1o
            sgbar[k] = integral / denom if abs(denom) > 1.0e-36 else 0.0
            e1o = e1
            k += 1
            if k >= ncn2:
                break
            e1 = float(epim_eV[k])

        integral = (s2 + s2t) * (e2 - e2t) / 2.0
        # Fortran: kl > nphint-1 or jk >= ntmp-1, all 1-based.
        if k >= nphint_1 - 1 or j >= ntmp - 2:
            done = True

    klmax = max(nb1, k - 1)
    return sgbar, nb1, klmax, {
        "status": "mapped" if iterations < max_iterations else "mapping_iteration_guard_reached",
        "nphint_1based": nphint_1,
        "nb1_1based": nb1 + 1,
        "klmax_1based": klmax + 1,
        "mapping_iterations": iterations,
        "cross_section_cursor_1based": j + 1,
        "source_last_packed_point_used_as_upper_marker": ntmp >= 2,
    }


def evaluate_phint53_exact(
    *,
    energy_above_threshold_ryd: Sequence[float],
    cross_section_cm2: Sequence[float],
    threshold_eV: float,
    live_radiation: Type53LiveRadiationState,
    temperature_1e4K: float,
    rnist: float,
    ptmp1: float,
    ptmp2: float,
    lfast: int = 2,
    abund1: float = 0.0,
    abund2: float = 0.0,
    xpx_cm3: float = 0.0,
) -> Type53PhintResult:
    """Evaluate the complete ``phint53.f90`` kernel on a live rate grid."""
    validation = live_radiation.validate()
    n = len(live_radiation.epim_eV)
    zeros = tuple(0.0 for _ in range(n))
    if not validation["ready"]:
        return Type53PhintResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, zeros, zeros, zeros, zeros, {
            "status": "not_evaluated_invalid_live_radiation_state", **validation
        })
    ntmp = min(len(energy_above_threshold_ryd), len(cross_section_cm2))
    if ntmp <= 0 or threshold_eV <= 0.0:
        return Type53PhintResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, zeros, zeros, zeros, zeros, {
            "status": "not_evaluated_invalid_type53_record", **validation
        })

    epi = list(live_radiation.epim_eV)
    bremsa = list(live_radiation.bremsam)
    sgbar, nb1, klmax, mapdiag = _map_cross_section_phint53(
        energy_above_threshold_ryd=energy_above_threshold_ryd[:ntmp],
        cross_section_cm2=cross_section_cm2[:ntmp],
        threshold_eV=float(threshold_eV),
        epim_eV=epi,
    )
    grid_diag = _full_grid_mapping_diagnostics(
        threshold_eV=float(threshold_eV),
        mapped_nb1_1based=int(mapdiag.get("nb1_1based", nb1 + 1)),
        live_radiation=live_radiation,
    )
    mapping_base_status = str(mapdiag.get("status", ""))
    mapping_status = "grid_mismatch" if bool(grid_diag.get("type53_full_grid_mismatch")) else mapping_base_status
    if mapdiag.get("status") != "mapped" or nb1 >= klmax or nb1 >= n:
        return Type53PhintResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, zeros, zeros, zeros, zeros, {
            "status": "evaluated_zero_outside_rate_grid",
            **validation,
            **mapdiag,
            **grid_diag,
            "mapping_base_status": mapping_base_status,
            "mapping_status": mapping_status,
        })

    t = float(temperature_1e4K)
    tm = t * 1.0e4
    bktm = BOLTZMANN_ERG_K * tm / ERG_PER_EV
    if bktm <= 0.0:
        return Type53PhintResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, zeros, zeros, zeros, zeros, {
            "status": "not_evaluated_nonpositive_temperature", **validation, **mapdiag
        })

    ptmp_sum = float(ptmp1) + float(ptmp2)
    sumr = sumh = sumh2 = sumi = sumc = sumc2 = 0.0
    opakc = [0.0] * n
    opakcont = [0.0] * n
    rcc1 = [0.0] * n
    rcc2 = [0.0] * n
    opakab = 0.0

    sgtpp = sgbar[nb1]
    bremtmpp = bremsa[nb1] / 12.56
    epiip = epi[nb1]
    temprp = 12.56 * sgtpp * bremtmpp / epiip if epiip != 0.0 else 0.0
    temphp = temprp * epiip
    temphp2 = temprp * (epiip - threshold_eV)
    exptst = (epiip - threshold_eV) / bktm
    exptmpp = _expo(-exptst)
    bbnurjp = min(2.0e4, epiip) ** 3 * 1.571e22 * 2.0
    tempip = float(rnist) * bbnurjp * sgtpp * exptmpp / epiip * ptmp_sum if epiip != 0.0 else 0.0
    tempcp = tempip * epiip
    tempcp2 = tempip * (epiip - threshold_eV)

    kl = nb1
    intervals = 0
    while kl < klmax and kl + 1 < n:
        intervals += 1
        sgtp = max(0.0, sgbar[kl])
        sgtpp = sgbar[kl + 1]
        bremtmpp = bremsa[kl + 1] / 12.56
        epii = epi[kl]
        epiip = epi[kl + 1]

        tempr = temprp
        temprp = 12.56 * sgtpp * bremtmpp / epiip if epiip != 0.0 else 0.0
        wwir = (epiip - epii) / 2.0
        sumr += tempr * wwir + temprp * wwir

        temph, temph2 = temphp, temphp2
        temphp = temprp * epiip
        temphp2 = temprp * (epiip - threshold_eV)
        sumh += temph * wwir + temphp * wwir
        sumh2 += temph2 * wwir + temphp2 * wwir

        exptsto = exptst
        exptst = (epiip - threshold_eV) / bktm
        exptmpp = 0.0
        optmp2 = 0.0
        if exptsto < 200.0 and int(lfast) >= 2:
            exptmpp = _expo(-exptst)
            bbnurjp = min(2.0e4, epiip) ** 3 * 1.571e22 * 2.0
            tempi = tempip
            tempip_unescaped = float(rnist) * bbnurjp * sgtpp * exptmpp * 12.56 / epiip if epiip != 0.0 else 0.0
            atmp2 = tempip_unescaped * epiip
            tempip = tempip_unescaped * ptmp_sum
            sumi += tempi * wwir + tempip * wwir

            tempc, tempc2 = tempcp, tempcp2
            tempcp = tempip * epiip
            tempcp2 = tempip * (epiip - threshold_eV)
            sumc += tempc * wwir + tempcp * wwir
            sumc2 += tempc2 * wwir + tempcp2 * wwir

            rcc1[kl] += float(abund2) * atmp2 * float(ptmp1) * float(xpx_cm3) / 12.56
            rcc2[kl] += float(abund2) * atmp2 * float(ptmp2) * float(xpx_cm3) / 12.56
            optmp2 = float(rnist) * exptmpp * sgtp * float(abund2) * ptmp_sum * float(xpx_cm3)

        optmp = float(abund1) * float(xpx_cm3) * sgtp
        opakc[kl] += optmp
        opakcont[kl] += optmp
        if kl == nb1 + 2:
            opakab = max(0.0, optmp - optmp2)
        kl += 1

    return Type53PhintResult(
        pirt_s_inv=sumr,
        rrrt_s_inv=sumi,
        piht_erg_s_inv=sumh * ERG_PER_EV,
        rrcl_erg_s_inv=sumc * ERG_PER_EV,
        piht2_erg_s_inv=sumh2 * ERG_PER_EV,
        rrcl2_erg_s_inv=sumc2 * ERG_PER_EV,
        opakab_cm_inv=opakab,
        opakc_cm_inv=tuple(opakc),
        opakcont_cm_inv=tuple(opakcont),
        rccemis_inward=tuple(rcc1),
        rccemis_outward=tuple(rcc2),
        diagnostics={
            **validation,
            **mapdiag,
            **grid_diag,
            "mapping_base_status": mapping_base_status,
            "mapping_status": mapping_status,
            "status": "evaluated_source_aligned_phint53",
            "n_integration_intervals": intervals,
            "threshold_eV": float(threshold_eV),
            "temperature_1e4K": t,
            "temperature_K": tm,
            "bktm_eV": bktm,
            "rnist": float(rnist),
            "ptmp_sum": ptmp_sum,
            "lfast": int(lfast),
            # v0.6.0a32 type53 shadow diagnostics: expose the raw
            # phint53 integration accumulators so C++ shadow output can be
            # compared before ucalc sign swaps and energy corrections.
            "sumr": float(sumr),
            "sumi": float(sumi),
            "sumh": float(sumh),
            "sumh2": float(sumh2),
            "sumc": float(sumc),
            "sumc2": float(sumc2),
            "phint53_ans1_pre_ucalc": float(sumr),
            "phint53_ans2_pre_ucalc": float(sumi),
            "phint53_ans3_pre_ucalc": float(sumh * ERG_PER_EV),
            "phint53_ans4_pre_ucalc": float(sumc * ERG_PER_EV),
            "phint53_ans5_pre_ucalc": float(sumh2 * ERG_PER_EV),
            "phint53_ans6_pre_ucalc": float(sumc2 * ERG_PER_EV),
            "bremsint_carried_as_live_state": True,
            "bremsint_consumed_by_phint53_source": False,
            "type53_grid_policy": str(live_radiation.metadata.get("type53_grid_policy", "unspecified")),
            "type53_grid_source": str(live_radiation.metadata.get("type53_grid_source", "unspecified")),
            "type53_reduced_grid_points": int(live_radiation.metadata.get("type53_reduced_grid_points", 0) or 0),
            "type53_full_grid_points": int(live_radiation.metadata.get("type53_full_grid_points", len(epi)) or len(epi)),
        },
    )


def evaluate_type53_ucalc_record(
    record: Mapping[str, Any],
    live_radiation: Type53LiveRadiationState,
    *,
    temperature_k: float,
    xpx_cm3: float,
    electron_fraction_xee: float,
    ptmp1: float,
    ptmp2: float,
    lfast: int = 2,
    abund1: float = 0.0,
    abund2: float = 0.0,
) -> dict[str, Any]:
    """Evaluate the complete XSTAR ``ucalc`` type-53 branch for one record."""
    e_ryd = [float(v) for v in record.get("energy_above_threshold_ryd", [])]
    sigma = [float(v) for v in record.get("cross_section_cm2", [])]
    threshold = _finite_float(record.get("threshold_eV"), 0.0)
    bound_g = _finite_float(record.get("bound_statistical_weight"), 0.0)
    continuum_g = _finite_float(record.get("continuum_statistical_weight", record.get("parent_statistical_weight")), 0.0)
    destination_g = _finite_float(record.get("destination_statistical_weight", continuum_g), continuum_g)
    continuum_energy = _finite_float(record.get("continuum_energy_eV"), 0.0)
    bound_energy = _finite_float(record.get("bound_energy_eV"), 0.0)
    destination_energy = _finite_float(record.get("destination_energy_eV"), continuum_energy)
    if not e_ryd or len(e_ryd) != len(sigma):
        return {"status": "not_evaluated_missing_cross_section_pairs"}
    if threshold <= 0.0 or bound_g <= 0.0 or continuum_g <= 0.0:
        return {"status": "not_evaluated_missing_level_context"}
    if temperature_k <= 0.0 or xpx_cm3 < 0.0 or electron_fraction_xee < 0.0:
        return {"status": "not_evaluated_invalid_plasma_context"}

    t = float(temperature_k) / 1.0e4
    electron_density = float(xpx_cm3) * float(electron_fraction_xee)
    q2 = 2.07e-16 * electron_density * float(temperature_k) ** (-1.5)
    # ucalc.f90 uses rlev(2,nlev), the current-ion continuum statistical
    # weight, even when idest2 is an excited parent level.  ggup/swrat are
    # diagnostic inputs to phint53 and do not enter this rnist expression.
    rs = q2 / continuum_g
    rnissel = bound_g * rs
    ethtmp = max(0.0, threshold - continuum_energy)
    exponent_energy = max(0.0, ethtmp + RYDBERG_EV * e_ryd[0])
    rnist = rnissel * _expo(-exponent_energy / XSTAR_KT_EV_PER_1E4K / t)
    swrat = bound_g / max(destination_g, 1.0e-300)

    ph = evaluate_phint53_exact(
        energy_above_threshold_ryd=e_ryd,
        cross_section_cm2=sigma,
        threshold_eV=threshold,
        live_radiation=live_radiation,
        temperature_1e4K=t,
        rnist=rnist,
        ptmp1=ptmp1,
        ptmp2=ptmp2,
        lfast=lfast,
        abund1=abund1,
        abund2=abund2,
        xpx_cm3=xpx_cm3,
    )
    if not str(ph.diagnostics.get("status", "")).startswith("evaluated"):
        return {"status": ph.diagnostics.get("status", "not_evaluated"), **dict(ph.diagnostics)}

    ans1 = ph.pirt_s_inv
    ans2 = ph.rrrt_s_inv
    # ucalc swaps/signs the phint53 heating and electron-POV channels.
    ans3 = -ph.rrcl_erg_s_inv
    ans4 = -ph.piht_erg_s_inv
    ans5 = -ph.rrcl2_erg_s_inv
    ans6 = -ph.piht2_erg_s_inv

    ans5_pre_energy_correction = ans5
    ans6_pre_energy_correction = ans6
    energy_difference = abs(destination_energy - bound_energy)
    den6 = max(1.0e-43, abs(ans4) - threshold * ERG_PER_EV * ans1)
    den5 = max(1.0e-43, abs(ans3) - threshold * ERG_PER_EV * ans2)
    energy_correction_factor_ans6 = (abs(ans4) - energy_difference * ERG_PER_EV * ans1) / den6
    energy_correction_factor_ans5 = (abs(ans3) - energy_difference * ERG_PER_EV * ans2) / den5
    ans6 *= energy_correction_factor_ans6
    ans5 *= energy_correction_factor_ans5

    return {
        "status": "evaluated",
        "source_branch": "ucalc_type53_phint53_exact_live_rate_grid",
        "ans1_photoionization_s^-1": ans1,
        "ans2_milne_recombination_s^-1": ans2,
        "ans3_cooling_signed_erg_s^-1": ans3,
        "ans4_heating_signed_erg_s^-1": ans4,
        "ans5_electron_pov_cooling_signed_erg_s^-1": ans5,
        "ans6_electron_pov_heating_signed_erg_s^-1": ans6,
        "phint53_pirt_s^-1": ph.pirt_s_inv,
        "phint53_rrrt_s^-1": ph.rrrt_s_inv,
        "phint53_piht_erg_s^-1": ph.piht_erg_s_inv,
        "phint53_rrcl_erg_s^-1": ph.rrcl_erg_s_inv,
        "phint53_piht2_erg_s^-1": ph.piht2_erg_s_inv,
        "phint53_rrcl2_erg_s^-1": ph.rrcl2_erg_s_inv,
        "rnist": rnist,
        "swrat": swrat,
        "sumr": float(ph.diagnostics.get("sumr", 0.0)),
        "sumi": float(ph.diagnostics.get("sumi", 0.0)),
        "sumh": float(ph.diagnostics.get("sumh", 0.0)),
        "sumh2": float(ph.diagnostics.get("sumh2", 0.0)),
        "sumc": float(ph.diagnostics.get("sumc", 0.0)),
        "sumc2": float(ph.diagnostics.get("sumc2", 0.0)),
        "ans5_pre_energy_correction": float(ans5_pre_energy_correction),
        "ans6_pre_energy_correction": float(ans6_pre_energy_correction),
        "ans5_energy_correction_factor": float(energy_correction_factor_ans5),
        "ans6_energy_correction_factor": float(energy_correction_factor_ans6),
        "energy_difference_eV": float(energy_difference),
        "ans5_energy_correction_denominator": float(den5),
        "ans6_energy_correction_denominator": float(den6),
        "electron_density_xpx_times_xee_cm^-3": electron_density,
        "threshold_eV": threshold,
        "bound_energy_eV": bound_energy,
        "destination_energy_eV": destination_energy,
        "bound_statistical_weight": bound_g,
        "continuum_statistical_weight": continuum_g,
        "destination_statistical_weight": destination_g,
        "lfast": int(lfast),
        "opacity_rrc_population_context_supplied": bool(abund1 != 0.0 or abund2 != 0.0),
        "opakab_cm^-1": ph.opakab_cm_inv,
        # ``phint53.f90`` mutates these caller-owned continuum arrays in
        # addition to returning the six scalar channels.  Expose the exact
        # per-record increments so ``calc_emisab_ion`` can replay the source
        # side effects rather than treating ``ucalc`` as a scalar-only API.
        "opakc_cm^-1": list(ph.opakc_cm_inv),
        "opakcont_cm^-1": list(ph.opakcont_cm_inv),
        "rccemis_inward": list(ph.rccemis_inward),
        "rccemis_outward": list(ph.rccemis_outward),
        "phint53_diagnostics": dict(ph.diagnostics),
    }


__all__ = [
    "Type53LiveRadiationState",
    "Type53PhintResult",
    "evaluate_phint53_exact",
    "evaluate_type53_ucalc_record",
]
