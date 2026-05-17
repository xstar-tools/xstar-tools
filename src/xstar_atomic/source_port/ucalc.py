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
    epi = np.asarray(getattr(state, "epim_eV", getattr(state, "epi_eV", ())), dtype=float)
    brem = np.asarray(getattr(state, "bremsam", getattr(state, "bremsa", ())), dtype=float)
    bint = np.asarray(getattr(state, "bremsint", np.zeros_like(epi)), dtype=float)
    if epi.size < 3 or epi.size != brem.size or epi.size != bint.size or np.any(np.diff(epi) <= 0):
        raise ValueError("invalid live radiation arrays")
    return epi, brem, bint


def _nbinc(energy: float, epi: Sequence[float]) -> int:
    arr = np.asarray(epi, dtype=float)
    return max(0, min(int(np.searchsorted(arr, float(energy), side="right") - 1), len(arr) - 1))


def _enxt_bounds(eth: float, epi: Sequence[float], t_1e4: float, lfast: int) -> tuple[int, int, int]:
    n = len(epi); nb = _nbinc(eth, epi); bktm = XSTAR_KT_EV_PER_1E4K * t_1e4
    if lfast <= 2:
        nph = n - max(2, n // 50) - 1; skip = 1
    elif lfast == 3:
        nph = _nbinc(max(3.0 * eth, eth + 3.0 * bktm), epi); nph = max(nph, nb + 1); skip = max(1, (nph - nb) // 16)
    else:
        nph = _nbinc(1.0e4, epi); skip = 1
    nph = min(max(nph, nb + skip), n - max(2, n // 50) - 1)
    return nb, nph, skip


def _phintfo_exact(*, sigma_cm2: Sequence[float], threshold_ev: float, context: "UCalcContext", swrat: float) -> dict[str, float]:
    """Direct Python translation of ``phintfo.f90`` scalar outputs."""
    epi, bremsa, _ = _radiation_arrays(context.radiation)
    sig = np.asarray(sigma_cm2, dtype=float)
    if sig.size != epi.size:
        raise ValueError("cross section must be mapped to the live radiation grid")
    nb, nph, skip = _enxt_bounds(threshold_ev, epi, context.t, context.lfast)
    bktm = XSTAR_KT_EV_PER_1E4K * context.t
    rnist = 5.216e-21 * float(swrat) / max(context.t * context.tsq, 1e-48)
    sumr=sumh=sumh2=sumi=sumc=sumc2=0.0
    tempro=tempio=atmp2o=atmp22o=0.0; enero=float(epi[nb]); opakab=0.0
    indices=list(range(nb,nph+1,skip))
    if indices[-1] != nph: indices.append(nph)
    for pos,k in enumerate(indices):
        ener=float(epi[k]); s=max(float(sig[k]),0.0); brem=float(bremsa[k])/25.3
        tempr=25.3*s*brem/max(ener,1e-48); de=ener-enero
        sumr += (tempr+tempro)*de/2.0
        sumh += (tempr*ener+tempro*enero)*de*ERG_PER_EV/2.0
        sumh2 += (tempr*(ener-threshold_ev)+tempro*(enero-threshold_ev))*de*ERG_PER_EV/2.0
        exptst=max(1e-36,(ener-threshold_ev)/max(bktm,1e-48)); ex=_expo(-exptst)
        bbnurj=min(ener,2e4)**3*1.571e22
        tempi1=rnist*bbnurj*ex*s/max(ener,1e-48); tempi2=rnist*brem*ex*s/max(ener,1e-48); tempi=tempi1+tempi2
        atmp2=tempi1*ener; atmp22=tempi1*(ener-threshold_ev)
        sumi += (tempi+tempio)*de/2.0
        sumc += (atmp2+atmp2o)*de*ERG_PER_EV/2.0
        sumc2 += (atmp22+atmp22o)*de*ERG_PER_EV/2.0
        optmp=context.abund1*s*context.hydrogen_density_cm3
        if pos <= 1: opakab=optmp
        tempro=tempr; tempio=tempi; atmp2o=atmp2; atmp22o=atmp22; enero=ener
    ne=context.electron_density_cm3
    return {"ans1":sumr,"ans2":ne*sumi,"ans3":sumh,"ans4":ne*sumc,"ans5":sumh2,"ans6":ne*sumc2,"opakab":opakab,"nb1":nb,"nphint":nph}


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
    """Translate ``phint53hunt.f90`` for the type-99 live-grid branch."""
    egrid = np.asarray(energy_above_threshold_ryd, dtype=float)
    sigma = np.asarray(cross_section_cm2, dtype=float)
    if egrid.size < 2 or egrid.size != sigma.size:
        return {"status": "not_evaluated_bad_cross_section_grid"}
    epi, bremsa, _ = _radiation_arrays(context.radiation)
    n = epi.size
    numcon3 = n - max(2, n // 50)
    nb = _nbinc(threshold_ev, epi)
    if nb >= numcon3:
        return {"status": "not_evaluated_threshold_above_guard_tail"}
    emax = threshold_ev + float(egrid[-1]) * 13.605692
    nph = min(_nbinc(emax, epi), numcon3 - 1)
    span = max(nph - nb, 1)
    power = max(0, int(math.log(max(float(span), 1.0), 2.0) + 0.5))
    ndelt = 2 ** power
    while ndelt > 2 and (nb + ndelt >= numcon3 or (epi[min(nb + ndelt, n - 1)] - threshold_ev) / 13.605692 > egrid[-1]):
        ndelt //= 2
    nph = min(nb + max(ndelt, 1), numcon3 - 1)
    t = context.t
    bktm = XSTAR_KT_EV_PER_1E4K * t
    rnist = 5.216e-21 * float(swrat) / max(t * math.sqrt(max(t, 0.0)), 1.0e-48)
    previous = None
    nskip = max(nph - nb, 1)
    npass = 0
    sums = (0.0,) * 6
    while nskip > 1 or previous is None:
        npass += 1
        nskip = max(1, nskip // 2)
        sumr = sumh = sumi = sumc = sumh2 = sumc2 = 0.0
        tempr = tempi = atmp2 = atmp22 = 0.0
        ener = float(epi[nb])
        indices = list(range(max(0, nb - 1), nph + 1, nskip))
        if indices[-1] != nph:
            indices.append(nph)
        for k in indices:
            enero = ener
            ener = float(epi[k])
            bremtmp = float(bremsa[k]) / 25.3
            tempio, atmp2o, atmp22o = tempi, atmp2, atmp22
            sgtmp = 0.0
            if ener >= threshold_ev:
                efnd = (ener - threshold_ev) / 13.605692
                sgtmp = _find53_cross_section(egrid, sigma, efnd)
                exptmp = _expo(-(ener - threshold_ev) / max(bktm, 1.0e-48))
                bbnurj = min(2.0e4, ener) ** 3
                tempi1 = rnist * bbnurj * sgtmp * exptmp * 1.571e22 / max(ener, 1.0e-48)
                tempi2 = rnist * bremtmp * sgtmp * exptmp / max(ener, 1.0e-48)
                tempi = tempi1 + tempi2
                atmp2 = tempi * ener
                atmp22 = tempi * (ener - threshold_ev)
            tempro = tempr
            tempr = 25.3 * sgtmp * bremtmp / max(ener, 1.0e-48)
            de = ener - enero
            sumr += (tempr + tempro) * de / 2.0
            sumh += (tempr * ener + tempro * enero) * de / 2.0
            sumh2 += (tempr * (ener - threshold_ev) + tempro * (enero - threshold_ev)) * de / 2.0
            sumi += (tempi + tempio) * de / 2.0
            sumc += (atmp2 + atmp2o) * de / 2.0
            sumc2 += (atmp22 + atmp22o) * de / 2.0
        sums = (sumr, sumi, sumh, sumc, sumh2, sumc2)
        if previous is not None:
            tests = [abs((a-b)/(a+b+1.0e-24)) for a,b in zip(previous[:4], sums[:4])]
            if max(tests) <= crit and sumi > 1.0e-24:
                break
        previous = sums
        if nskip <= 1:
            break
    sumr, sumi, sumh, sumc, sumh2, sumc2 = sums
    ne = context.electron_density_cm3
    return {
        "status": "evaluated_phint53hunt_live_grid", "pirt": sumr, "rrrt": ne * sumi,
        "piht": sumh * ERG_PER_EV, "rrcl": ne * sumc * ERG_PER_EV,
        "piht2": sumh2 * ERG_PER_EV, "rrcl2": ne * sumc2 * ERG_PER_EV,
        "npass": npass, "nb1_zero_based": nb, "nphint_zero_based": nph,
    }


def _photo_result_swapped(dispatch: "SourceFaithfulUCalc", r: "UCalcRecord", c: "UCalcContext", s: "UCalcBranchSpec", *, sigma: Sequence[float], threshold: float, swrat: float, id1: int, id2: int, zero_reverse: bool = False) -> "UCalcResult":
    ph=_phintfo_exact(sigma_cm2=sigma,threshold_ev=threshold,context=c,swrat=swrat)
    a1,a2=ph["ans1"],ph["ans2"]; a3,a4=-ph["ans4"],-ph["ans3"]; a5,a6=-ph["ans6"],-ph["ans5"]
    if zero_reverse: a2=a4=a6=0.0
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
    13, 14, 24, 29, 40, 41, 42, 43, 44, 45, 46, 47, 48, 52, 58, 61, 62,
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
    57: ("calt57",), 59: ("drd", "enxt", "phintfo"), 60: ("calt6062",),
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
        54: "translated_formula", 55: "translated_formula", 59: "translated_formula", 60: "translated_formula", 64: "translated_formula",
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
        elif dt in {12, 15, 19, 23, 27, 35, 36, 49, 53, 55, 59, 64, 70, 85, 88, 99}:
            id1 = i[-2] if len(i) >= 2 else (i[0] if i else 0)
            parent_offset = i[-3] if len(i) >= 3 else 1
            id2 = max(nlev + parent_offset - 1, nlev)
        elif dt in {16, 25, 26, 32, 57, 65, 95, 97}:
            if record.rate_type == 5:
                id1 = i[0] if i else 1
                id2 = nlev + (i[1] - 1 if len(i) >= 3 else 0)
            else:
                id1 = id2 = 1
        elif dt in {17, 18, 28, 33, 54, 60, 63, 73, 77, 102} and len(i) >= 2:
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
        return self._base_result(record, spec, UCalcStatus.INDEX_ONLY, idest1=id1, idest2=id2)

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

    def _live_type53_state(self, context: UCalcContext) -> Any:
        from xstar_atomic.rates_type53 import Type53LiveRadiationState
        epi,brem,bint=_radiation_arrays(context.radiation)
        if isinstance(context.radiation,Type53LiveRadiationState): return context.radiation
        return Type53LiveRadiationState.from_sequences(epi,brem,bint,metadata=getattr(context.radiation,"metadata",{}))

    def _type53_from_pairs(self, record: UCalcRecord, context: UCalcContext, spec: UCalcBranchSpec, *, energy_ryd: Sequence[float], sigma_cm2: Sequence[float], threshold_ev: float, idest1: int, idest2: int, zero_reverse: bool = False, zero_all_heating: bool = False) -> UCalcResult:
        from xstar_atomic.rates_type53 import evaluate_type53_ucalc_record
        dest_energy,dest_weight=self._parent_destination_context(context,idest2)
        continuum=context.levels.require(context.nlevp); bound=context.levels.require(idest1)
        decoded={
            "energy_above_threshold_ryd":list(float(x) for x in energy_ryd),
            "cross_section_cm2":list(float(x) for x in sigma_cm2),
            "threshold_eV":float(threshold_ev),
            "bound_statistical_weight":bound.statistical_weight,
            "continuum_statistical_weight":continuum.statistical_weight,
            "destination_statistical_weight":dest_weight or continuum.statistical_weight,
            "continuum_energy_eV":continuum.energy_ev,
            "bound_energy_eV":bound.energy_ev,
            "destination_energy_eV":dest_energy,
        }
        ev=evaluate_type53_ucalc_record(decoded,self._live_type53_state(context),temperature_k=context.temperature_k,xpx_cm3=context.hydrogen_density_cm3,electron_fraction_xee=context.electron_fraction_xee,ptmp1=context.ptmp1,ptmp2=context.ptmp2,lfast=context.lfast,abund1=context.abund1,abund2=context.abund2)
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
        if len(r.reals)<6 or len(r.integers)<2: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type59_short_record")
        eth=r.reals[0]; epi=self._mapped_grid(c); sig=np.zeros_like(epi)
        if len(r.reals)==9:
            _,emax,e0,s0,ya,pp,yw,y0,y1=r.reals; l2=0
        else:
            e0,s0,ya,pp,yw=r.reals[:5]; y0=y1=0.0; l2=r.integers[2] if len(r.integers)>2 else 0
        qq=5.5+l2-pp/2.0
        for k,e in enumerate(epi):
            if e>=eth:
                xx=e/e0-y0; yy=math.sqrt(xx*xx+y1*y1) if len(r.reals)==9 else xx
                if yy>0: sig[k]=s0*((xx-1.0)**2+yw*yw)*_expo(-max(-60.0,min(60.0,qq*math.log(max(yy,1e-48)))))*(1.0+math.sqrt(max(yy/ya,0.0)))**(-pp)*1e-18
        id1=r.integers[-2]; off=r.integers[-3] if len(r.integers)>=3 else 1; id2=max(c.nlevp+off-1,1)
        sw=c.levels.weight(1)/max(c.levels.weight(c.nlevp),1e-48); zero=(r.rate_type==1 or id1>1)
        return _photo_result_swapped(self,r,c,s,sigma=sig,threshold=eth,swrat=sw,id1=id1,id2=id2,zero_reverse=zero)

    def _eval_type12(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Source label 12 is an unconditional jump to the type-36 branch."""
        return self._eval_type36(r,c,s)

    def _eval_type15(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from .ucalc_leaves import bkhsgo
        if len(r.integers)<5 or len(r.reals)<14:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type15_short_record")
        parent=self._parent_record(r,c)
        threshold=_finite(c.extras.get("type15_threshold_ev"))
        if threshold is None and parent is not None and parent.reals: threshold=float(parent.reals[0])
        if threshold is None or threshold<=0:
            return self._context_blocked(r,s,"type15_requires_parent_threshold_record")
        na=max(1,int(r.integers[-5])); b=[]; coeff=[]; d=None
        for k in range(na):
            off=15*k
            if off+14>len(r.reals): break
            d=float(r.reals[off+1]); b.append(float(r.reals[off+2])); coeff.append(tuple(float(x) for x in r.reals[off+3:off+14]))
        if not b or d is None:
            return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type15_missing_bkh_shell_coefficients")
        epi=self._mapped_grid(c); sigma=bkhsgo(epi,threshold,d,b,coeff)
        id1=int(r.integers[-2]); id2=int(r.integers[-3])-int(r.integers[-1])
        sw=c.levels.weight(1)/max(c.levels.weight(c.nlevp),1e-48)
        out=_photo_result_swapped(self,r,c,s,sigma=sigma,threshold=threshold,swrat=sw,id1=id1,id2=id2)
        return replace(out,diagnostics={**dict(out.diagnostics),"bkh_n_shells":len(b),"bkh_d":d,"threshold_source":"parent_record_or_context"})

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
        id1=int(r.integers[-2]); off=max(0,int(r.integers[-3])); id2=c.nlevp+off-1
        threshold=self._level_threshold(c,id1)
        e=np.asarray(r.reals[0::2],float); xs=np.maximum(np.asarray(r.reals[1::2],float)*1e-18,0.0); n=min(e.size,xs.size)
        if n<2: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type49_missing_cross_section_pairs")
        e,xs=phextrap(e[:n],xs[:n],threshold,len(self._mapped_grid(c)))
        return self._type53_from_pairs(r,c,s,energy_ryd=e,sigma_cm2=xs,threshold_ev=threshold,idest1=id1,idest2=id2)

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
            if wavelength and aij is not None and id1 > 0 and id2 > 0:
                ggup = c.levels.weight(id1)
                gglo = c.levels.weight(id2)
                if ggup > 0.0 and gglo > 0.0:
                    flin = 1.0e-16 * aij * ggup * wavelength * wavelength / (0.667274 * gglo)
            decoded = {
                "A_s^-1": aij,
                "f_osc_from_A": flin,
                "wavelength_A": wavelength,
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
        ev = evaluate_type50_ucalc_record(
            decoded, ptmp1=c.ptmp1, ptmp2=c.ptmp2,
            cfrac=c.covering_fraction, bremsa_nb1=bremsa,
            hydrogen_density_cm3=c.hydrogen_density_cm3,
        )
        if ev.get("status") != "evaluated":
            return self._base_result(r, s, UCalcStatus.CONTEXT_BLOCKED, reason=str(ev.get("reason")), diagnostics=ev)
        return self._ctx_result(
            r, s, ans1=float(ev["ans1_photoexcitation_s^-1"]),
            ans2=float(ev["ans2_escaped_decay_s^-1"]), idest1=id1, idest2=id2,
            diagnostics=ev, context_fields_used=("ptmp1", "ptmp2", "cfrac", "radiation", "xpx", "levels"),
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
        qexc=_finite(ev.get("q_excitation_cm3_s")); qde=_finite(ev.get("q_deexcitation_cm3_s"))
        if qexc is None or qde is None:
            reason = str(
                ev.get("eval_diagnostic")
                or ev.get("type63_reason")
                or ev.get("diagnostic")
                or "collision_evaluation_failed"
            )
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
        ans1=qexc*c.electron_density_cm3; ans2=qde*c.electron_density_cm3
        de=float(row.get("delta_e_level_eV") or 0.0)
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*de*ERG_PER_EV,ans6=ans1*de*ERG_PER_EV,
                                idest1=int(row["lower_level"]),idest2=int(row["upper_level"]),diagnostics=ev,
                                context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type53(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.rates_type53 import evaluate_type53_ucalc_record
        decoded = c.extras.get("decoded_type53_by_record", {}).get(r.record) or c.extras.get("decoded_type53")
        i = r.integers
        id1 = int(i[-2]) if len(i) >= 2 else 0
        off = int(i[-3]) if len(i) >= 3 else 1
        id2 = max(c.nlevp + off - 1, c.nlevp)
        if decoded is None and c.radiation is not None and id1 > 0:
            try:
                bound = c.levels.require(id1)
                continuum = c.levels.require(c.nlevp)
                parent_excitation, destination_g = self._parent_destination_context(c, id2)
                # For excited parents the map stores excitation above the
                # parent ground; the physical destination energy includes the
                # current-ion continuum energy.
                destination_energy = continuum.energy_ev + (parent_excitation if id2 > c.nlevp else 0.0)
                threshold = self._level_threshold(c, id1) + (parent_excitation if id2 > c.nlevp else 0.0)
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
                    "destination_energy_eV": destination_energy,
                    "packed_parent_offset": off,
                    "decode_source": "packed_type53_record_plus_element_level_context",
                }
            except (KeyError, ValueError, IndexError) as exc:
                return self._context_blocked(r, s, f"type53_decode:{exc}")
        if decoded is None or c.radiation is None:
            return self._context_blocked(r, s, "type53 requires packed cross-section/level context and live epim/bremsam/bremsint")
        ev = evaluate_type53_ucalc_record(
            decoded, self._live_type53_state(c), temperature_k=c.temperature_k,
            xpx_cm3=c.hydrogen_density_cm3, electron_fraction_xee=c.electron_fraction_xee,
            ptmp1=c.ptmp1, ptmp2=c.ptmp2, lfast=c.lfast, abund1=c.abund1, abund2=c.abund2,
        )
        if ev.get("status") != "evaluated":
            return self._base_result(r, s, UCalcStatus.SOURCE_REJECTED, reason=str(ev.get("status")), diagnostics=ev)
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
        return self._ctx_result(r,s,ans2=rate,ans3=-rate*de*ERG_PER_EV,idest1=lo,idest2=up,
            diagnostics={"alm":alm,"alp":alp,"ni":ni,"nf":nf,"li":li,"lf":lf},context_fields_used=("levels",))

    def _eval_type60(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        if len(r.integers)<2 or len(r.reals)<3: return self._base_result(r,s,UCalcStatus.INVALID_RECORD,reason="type60_short_record")
        a,b=r.integers[0],r.integers[1]; lo,up=(a,b) if c.levels.energy(a)<=c.levels.energy(b) else (b,a)
        t1=min(c.temperature_k,1e9)*6.33652e-6; tt=min(t1,1.0)
        rat=sum(r.reals[k]*tt**(k-2) for k in range(2,len(r.reals)))
        ups=rat*(1.0+math.log(t1)/(math.log(t1)+1.0)) if t1>1.0 else rat
        gu=c.levels.weight(up); gl=c.levels.weight(lo); de=abs(c.levels.energy(up)-c.levels.energy(lo)); ne=c.electron_density_cm3
        ex=_expo(-de/(XSTAR_KT_EV_PER_1E4K*c.t)); qd=8.626e-8*ups/c.tsq/max(gu,1e-48); qe=qd*gu*ex/max(gl,1e-48)
        return self._ctx_result(r,s,ans1=qe*ne,ans2=qd*ne,ans5=qd*ne*de*ERG_PER_EV,ans6=qe*ne*de*ERG_PER_EV,idest1=lo,idest2=up,
            diagnostics={"upsilon":ups},context_fields_used=("temperature_k","xpx","xee","levels"))

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
        i=r.integers; id1=i[-2] if len(i)>=2 else 1; id2=c.nlevp
        lev=c.levels.require(id1); parent=c.levels.require(c.nlevp)
        n=lev.principal_n or (i[0] if i else 1)
        ev=_xstar_calt57(c.temperature_k,c.electron_density_cm3,lev.energy_ev,parent.continuum_energy_ev or parent.energy_ev,int(n))
        cion=_finite(ev.get("type57_cion_cm3_s")); crec=_finite(ev.get("type57_crec_cm6_s"))
        if cion is None or crec is None:
            return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=str(ev.get("python_eval_status")),diagnostics=ev)
        g1=max(lev.statistical_weight,1e-48); g2=max(parent.statistical_weight,1e-48)
        ans1=cion*c.electron_density_cm3; ans2=crec*(g1/g2)*c.electron_density_cm3**2
        eth=max(parent.energy_ev-lev.energy_ev,0.0)
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=-ans2*eth*ERG_PER_EV,ans6=-ans1*eth*ERG_PER_EV,
                                idest1=id1,idest2=id2,diagnostics=ev,context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type71(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.rates_type71 import evaluate_type71_ucalc_record
        decoded={"reals":list(r.reals),"ints":list(r.integers)}
        ev=evaluate_type71_ucalc_record(decoded,temperature_k=c.temperature_k,
                                         electron_density_cm3=c.hydrogen_density_cm3,ptmp1=c.ptmp1,ptmp2=c.ptmp2)
        ans2=_finite(ev.get("ans2_downward_s^-1"))
        if ans2 is None:
            return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=str(ev.get("reason") or ev.get("status")),diagnostics=ev)
        i=r.integers; id1=i[-4] if len(i)>=4 else 0; id2=i[-3] if len(i)>=3 else 0
        return self._ctx_result(r,s,ans1=0.0,ans2=ans2,idest1=id1,idest2=id2,diagnostics=ev,
                                context_fields_used=("temperature_k","xpx","ptmp1","ptmp2"))

    def _calt72_rate(self, r: UCalcRecord, c: UCalcContext) -> float:
        if len(r.reals) < 2: return 0.0
        dele=r.reals[1]; scale=3.3e-11*(13.6/(XSTAR_KT_EV_PER_1E4K*c.t))**1.5
        rtmp=r.reals[2] if len(r.reals)>=3 else 1.0
        return scale*_expo(-dele/(XSTAR_KT_EV_PER_1E4K*c.t))*(r.reals[0]/1e13)*rtmp

    def _eval_type72(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        rate=self._calt72_rate(r,c); ne=c.electron_density_cm3; i=r.integers
        id1=i[-3] if len(i)>=3 else 1; id2=i[-2] if len(i)>=2 else c.nlevp
        gu=c.levels.weight(c.nlevp); gl=c.levels.weight(1); rinf=2.08e-22*gl/max(gu,1e-48)/max(c.t*c.tsq,1e-48)
        de=r.reals[1] if len(r.reals)>1 else 0.0
        return self._ctx_result(r,s,ans1=rate*ne*rinf*ne*_expo(de/c.temperature_k),ans2=rate*ne,idest1=id1,idest2=id2,
            diagnostics={"calt72_rate_cm3_s":rate},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type74(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.xstar_element_solver import _xstar_calt74_alpha_diagnostic
        ev=_xstar_calt74_alpha_diagnostic(c.temperature_k,r.reals)
        alpha=_finite(ev.get("type74_alpha_unweighted_cm3_s")) or _finite(ev.get("calt74_alpha_cm3_s")) or _finite(ev.get("alpha_cm3_s"))
        if alpha is None:
            return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=str(ev.get("status") or "calt74_failed"),diagnostics=ev)
        i=r.integers; id1=i[-2] if len(i)>=2 else 0; id2=c.nlevp+(i[-3] if len(i)>=3 else 1)-1
        return self._ctx_result(r,s,ans2=alpha*c.electron_density_cm3,idest1=id1,idest2=id2,diagnostics=ev,
                                context_fields_used=("temperature_k","xpx","xee"))

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
        ev=_xstar_calt77_rates(temperature=float(c.temperature_k), electron_density=float(c.hydrogen_density_cm3), ion_charge=c.extras.get("ion_charge"), reals=list(r.reals), ints=list(r.integers))
        ans1=_finite(ev.get("type77_calt77_clu_s^-1")); ans2=_finite(ev.get("type77_calt77_cul_s^-1"))
        if ans1 is None or ans2 is None:
            return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason=str(ev.get("type77_calt77_status") or "calt77_failed"),diagnostics=ev)
        i=r.integers; id1=i[-4] if len(i)>=4 else 0; id2=i[-3] if len(i)>=3 else 0
        de=abs(c.levels.energy(id1)-c.levels.energy(id2))
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*de*ERG_PER_EV,ans6=ans1*de*ERG_PER_EV,
                                idest1=id1,idest2=id2,diagnostics=ev,context_fields_used=("temperature_k","xpx","levels"))

    def _eval_type95(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        from xstar_atomic.xstar_element_solver import _xstar_expint_em1
        ee=r.reals[0]; ns=(len(r.reals)-2)//2; tt=(XSTAR_KT_EV_PER_1E4K*c.t)/ee
        xx=1.0-0.693147/math.log(tt+2.0); xg=r.reals[2:2+ns]; yg=r.reals[2+ns:2+2*ns]
        rho=float(np.interp(xx,xg,yg)); e1=_xstar_expint_em1(1.0/tt)
        if e1 is None: return self._base_result(r,s,UCalcStatus.SOURCE_REJECTED,reason="eint_failed")
        ans1=1e-6*e1*rho/math.sqrt(tt*ee**3)*c.electron_density_cm3
        id1=1; id2=c.nlevp+(r.integers[1]-1 if r.rate_type==5 and len(r.integers)>=3 else 0) if r.rate_type==5 else 1
        g1=max(c.levels.weight(id1),1e-48); g2=max(c.levels.weight(c.nlevp),1e-48)
        rinf=2.08e-22*g1/g2/c.t/c.tsq; ans2=ans1*rinf*c.electron_density_cm3/_expo(-1.0/tt)
        return self._ctx_result(r,s,ans1=ans1,ans2=ans2,ans5=ans2*ee*ERG_PER_EV,ans6=ans1*ee*ERG_PER_EV,
                                idest1=id1,idest2=id2,diagnostics={"rho":rho,"e1":e1},context_fields_used=("temperature_k","xpx","xee","levels"))

    def _eval_type96(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        i=r.integers; id1=max(i[-3] if len(i)>=3 else 1,1); id2=max((i[-2] if len(i)>=2 else 1)+c.nlevp-1,1)
        dele=r.reals[2]; rate=2.069e-3/c.temperature_k**1.5*_expo(-dele/(XSTAR_KT_EV_PER_1E4K*c.t))*r.reals[1]
        return self._ctx_result(r,s,ans2=rate*c.electron_density_cm3,idest1=id1,idest2=id2,
                                context_fields_used=("temperature_k","xpx","xee"))

    def _eval_type99(self, r: UCalcRecord, c: UCalcContext, s: UCalcBranchSpec) -> UCalcResult:
        """Translate ``calt99 -> phint53hunt`` with the live radiation grid."""
        from xstar_atomic.xstar_element_solver import _xstar_calt99_superlevel_bound_free
        i = r.integers
        id1 = min(int(i[-2]) if len(i) >= 2 else 1, max(c.nlevp - 1, 1))
        off = int(i[-3]) if len(i) >= 3 else 1
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
            destination_energy = continuum.energy_ev + parent_excitation
        else:
            threshold_ev = abs(bound.energy_ev - continuum.energy_ev)
            destination_energy = continuum.energy_ev
        if threshold_ev <= 0.0 or bound.statistical_weight <= 0.0 or destination_g <= 0.0:
            return self._context_blocked(r, s, "type99_missing_or_bad_threshold_or_statistical_weight")
        threshold_ryd = threshold_ev / 13.6
        ev = _xstar_calt99_superlevel_bound_free(
            temperature=c.temperature_k, electron_density=c.electron_density_cm3, threshold_ry=threshold_ryd,
            bound_stat_weight=bound.statistical_weight, continuum_stat_weight=destination_g,
            reals=list(r.reals), ints=list(r.integers), radiation_context_rows=None,
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
        ans6 *= (abs(ans4) - energy_difference * ERG_PER_EV * ans1) / max(1.0e-43, abs(ans4) - threshold_ev * ERG_PER_EV * ans1)
        ans5 *= (abs(ans3) - energy_difference * ERG_PER_EV * ans2) / max(1.0e-43, abs(ans3) - threshold_ev * ERG_PER_EV * ans2)
        diagnostics = {**ev, **ph, "type99_threshold_eV_derived": threshold_ev, "type99_swrat": swrat, "type99_scale": scale}
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
