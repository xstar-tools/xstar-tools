"""Source-faithful pre-matrix ionization balance for ``calc_hmc_element``.

This module translates the first pass of ``calc_hmc_element.f90``:

``calc_ion_rates -> istruc/ioneqm -> mml/mmu selection``.

The total-rate pass is intentionally distinct from the population-weighted
``stot/atot`` diagnostics returned after ``msolvelucy``.  XSTAR uses the former
to choose the adjacent ion-stage block and the latter to describe the solved
multilevel operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import math

import numpy as np

from .atomic_database import XSTARMasterData, XSTARDerivedPointers
from .element_equilibrium import build_level_table
from .ucalc import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcStatus,
    default_source_faithful_ucalc,
)


class IonBalanceError(RuntimeError):
    """Raised when the source pre-matrix ion-balance sequence cannot run."""


@dataclass(frozen=True)
class CalcIonRatesContext:
    """Runtime state supplied to XSTAR ``calc_ion_rates.f90``."""

    temperature_k: float
    hydrogen_density_cm3: float
    electron_fraction_xee: float
    radiation: Any = None
    covering_fraction: float = 1.0
    turbulent_velocity_km_s: float = 0.0
    neutral_h_density_cm3: float = 0.0
    ionized_h_density_cm3: float = 0.0
    lfast: int = 2
    strict_context: bool = True

    @property
    def electron_density_cm3(self) -> float:
        return float(self.hydrogen_density_cm3) * float(self.electron_fraction_xee)


@dataclass(frozen=True)
class CalcIonRateContribution:
    """One record considered by the literal total-rate pass."""

    record: int
    data_type: int
    rate_type: int
    status: str
    idest1_packed: int
    idest1: int
    idest2: int
    ans1: float
    ans2: float
    added_to_pirti: float
    added_to_rrrti: float
    reason: str = ""


@dataclass
class CalcIonRatesResult:
    """Total ionization/recombination rates for one XSTAR ion header."""

    ion_index: int
    ion_record: int
    element_z: int
    ion_stage: int
    nlev: int
    pirti: float
    rrrti: float
    contributions: List[CalcIonRateContribution] = field(default_factory=list)
    n_records_seen: int = 0
    n_records_selected: int = 0
    n_records_evaluated: int = 0
    n_records_blocked: int = 0
    ready: bool = False
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IoneqmResult:
    """Literal output of ``ioneqm.f90``."""

    fractions: np.ndarray
    q_ratio: np.ndarray
    jmax: int
    mmn: int
    mmx: int


@dataclass(frozen=True)
class IstrucResult:
    """Literal ``istruc.f90`` ion fractions with one-based guard arrays."""

    ionization_rates: np.ndarray
    recombination_rates: np.ndarray
    fractions: np.ndarray
    ioneqm: IoneqmResult

    @property
    def n_rates(self) -> int:
        return int(self.ionization_rates.size - 1)


@dataclass(frozen=True)
class IonStageLimitResult:
    """Source ``mml/mmu`` stage selection from preliminary ion fractions."""

    mml: int
    mmu: int
    critf: float
    lower_crossing: int
    upper_crossing: int
    iterations: int


def _ion_indices_for_element(derived: XSTARDerivedPointers, element_z: int) -> List[int]:
    values = [
        ion_index
        for ion_index in range(1, int(derived.n_ions) + 1)
        if int(derived.ion_element_z[ion_index]) == int(element_z)
    ]
    values.sort(key=lambda idx: int(derived.ion_stage[idx]))
    return values


def _element_nnz(master: XSTARMasterData, derived: XSTARDerivedPointers, element_z: int) -> int:
    """Return source ``nnz=idat(np1i+nidt-2)`` for an element header."""
    record = int(derived.npfirst[11]) if 11 < len(derived.npfirst) else 0
    while record:
        header = master.header(record)
        ints = master.record_integers(record)
        z = int(ints[0]) if ints.size else 0
        if z == int(element_z):
            if ints.size < 2:
                raise IonBalanceError(f"element Z={element_z} header has too few integers")
            return int(ints[-2])
        record = int(derived.npnxt[record])
    # The supported XSTAR element headers normally have nnz=Z.  Do not use
    # that as a silent production fallback because the packed header is the
    # source authority.
    raise IonBalanceError(f"could not locate element header for Z={element_z}")


def _parent_destination_context(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    *,
    ion_index: int,
    nlev: int,
) -> Tuple[Dict[int, float], Dict[int, float]]:
    """Build the parent-level endpoint maps used by type 49/53/88 branches."""
    element_z = int(derived.ion_element_z[ion_index])
    stage = int(derived.ion_stage[ion_index])
    parent = next(
        (
            idx
            for idx in _ion_indices_for_element(derived, element_z)
            if int(derived.ion_stage[idx]) == stage + 1
        ),
        0,
    )
    energy: Dict[int, float] = {}
    weight: Dict[int, float] = {}
    if parent:
        levels = build_level_table(master, derived, parent)
        for parent_local in range(2, levels.nlev + 1):
            destination = int(nlev) + parent_local - 1
            level = levels.require(parent_local)
            energy[destination] = float(level.energy_ev)
            weight[destination] = float(level.statistical_weight)
    return energy, weight


def calc_ion_rates(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    *,
    ion_index: int,
    context: CalcIonRatesContext,
    dispatcher: Optional[SourceFaithfulUCalc] = None,
) -> CalcIonRatesResult:
    """Translate ``calc_ion_rates.f90`` for one ion.

    The routine follows the source rate-type traversal and only calls ``ucalc``
    for rate types 1, 15, 8, 6, and ground-state rate type 7.  ``pirti`` and
    ``rrrti`` are accumulated from source ``ans1`` exactly as in the Fortran
    routine.  These totals are preliminary adjacent-stage rates, not the
    population-weighted ``stot/atot`` flows produced by ``msolvelucy``.
    """
    if int(ion_index) <= 0 or int(ion_index) > int(derived.n_ions):
        raise IonBalanceError(f"ion_index {ion_index} outside 1..{derived.n_ions}")
    if context.temperature_k <= 0.0 or not math.isfinite(context.temperature_k):
        raise IonBalanceError("temperature_k must be finite and positive")

    dispatch = dispatcher or default_source_faithful_ucalc()
    ion_record = int(derived.ion_records[ion_index])
    element_z = int(derived.ion_element_z[ion_index])
    ion_stage = int(derived.ion_stage[ion_index])
    nlev = int(derived.nlevs[ion_index])
    levels = build_level_table(master, derived, ion_index)
    parent_energy, parent_weight = _parent_destination_context(
        master, derived, ion_index=ion_index, nlev=nlev
    )

    pirti = 0.0
    rrrti = 0.0
    rows: List[CalcIonRateContribution] = []
    n_seen = n_selected = n_evaluated = n_blocked = 0

    # npfi's first axis is XSTAR rate type, despite historical Python variable
    # names that sometimes call it a data-type loop.
    for rate_slot in range(1, int(derived.npfi.shape[0])):
        record = int(derived.npfi[rate_slot, ion_index])
        while record and int(derived.npar[record]) == ion_record:
            n_seen += 1
            header = master.header(record)
            ints = master.record_integers(record)
            idest1_packed = int(ints[-2]) if ints.size >= 2 else 0
            selected = (
                header.rate_type in {1, 15, 8, 6}
                or (header.rate_type == 7 and idest1_packed == 1)
            )
            if selected:
                n_selected += 1
                ucontext = UCalcContext(
                    temperature_k=float(context.temperature_k),
                    hydrogen_density_cm3=float(context.hydrogen_density_cm3),
                    electron_fraction_xee=float(context.electron_fraction_xee),
                    neutral_h_density_cm3=float(context.neutral_h_density_cm3),
                    ionized_h_density_cm3=float(context.ionized_h_density_cm3),
                    turbulent_velocity_km_s=float(context.turbulent_velocity_km_s),
                    covering_fraction=float(context.covering_fraction),
                    ptmp1=0.5,
                    ptmp2=0.5,
                    abund1=0.0,
                    abund2=0.0,
                    jkion=int(ion_index),
                    nlev=nlev,
                    lfast=int(context.lfast),
                    levels=levels,
                    radiation=context.radiation,
                    derived_pointers=derived,
                    master=master,
                    extras={
                        "element_z": element_z,
                        "ion_stage": ion_stage,
                        "ion_charge": ion_stage - 1,
                        "ion_record": ion_record,
                        "lfpi": 1,
                        "parent_level_energy_ev_by_destination": parent_energy,
                        "parent_level_stat_weight_by_destination": parent_weight,
                    },
                )
                result = dispatch.evaluate_record_number(
                    master,
                    record,
                    ucontext,
                    parent_record=ion_record,
                    next_record=int(derived.npnxt[record]),
                    strict=False,
                )
                add_pi = 0.0
                add_rr = 0.0
                if result.status is UCalcStatus.EVALUATED:
                    n_evaluated += 1
                    if (
                        header.rate_type in {1, 15}
                        or (
                            header.rate_type == 7
                            and result.idest1 == 1
                            and result.idest2 <= nlev + 2
                        )
                    ):
                        add_pi = float(result.ans1)
                        pirti += add_pi
                    if header.rate_type in {8, 6}:
                        add_rr = float(result.ans1)
                        rrrti += add_rr
                else:
                    n_blocked += 1
                rows.append(
                    CalcIonRateContribution(
                        record=record,
                        data_type=int(header.data_type),
                        rate_type=int(header.rate_type),
                        status=result.status.value,
                        idest1_packed=idest1_packed,
                        idest1=int(result.idest1),
                        idest2=int(result.idest2),
                        ans1=float(result.ans1),
                        ans2=float(result.ans2),
                        added_to_pirti=add_pi,
                        added_to_rrrti=add_rr,
                        reason=str(result.reason),
                    )
                )
            record = int(derived.npnxt[record])

    ready = n_blocked == 0
    result = CalcIonRatesResult(
        ion_index=int(ion_index),
        ion_record=ion_record,
        element_z=element_z,
        ion_stage=ion_stage,
        nlev=nlev,
        pirti=float(pirti),
        rrrti=float(rrrti),
        contributions=rows,
        n_records_seen=n_seen,
        n_records_selected=n_selected,
        n_records_evaluated=n_evaluated,
        n_records_blocked=n_blocked,
        ready=ready,
        diagnostics={
            "source_file": "xstar/xstarlib/src/calc_ion_rates.f90",
            "lfpi": 1,
            "ptmp1": 0.5,
            "ptmp2": 0.5,
            "abund1": 0.0,
            "abund2": 0.0,
        },
    )
    if context.strict_context and not ready:
        blocked = [row for row in rows if row.status != UCalcStatus.EVALUATED.value]
        first = blocked[0] if blocked else None
        detail = f"; first blocked record={first.record} reason={first.reason}" if first else ""
        raise IonBalanceError(
            f"calc_ion_rates Z={element_z} stage={ion_stage} has {n_blocked} blocked selected records{detail}"
        )
    return result


def ioneqm(
    ionization_rates: Sequence[float],
    recombination_rates: Sequence[float],
    *,
    lower_stage: int = 1,
    eps: float = 1.0e-6,
    delt: float = 1.0e-28,
) -> IoneqmResult:
    """Translate ``ioneqm.f90`` including its overflow-avoidance search."""
    z = np.asarray(ionization_rates, dtype=float).reshape(-1)
    a = np.asarray(recombination_rates, dtype=float).reshape(-1)
    if z.size != a.size or z.size < 1:
        raise IonBalanceError("ioneqm requires equal non-empty rate arrays")
    if np.any(~np.isfinite(z)) or np.any(~np.isfinite(a)):
        raise IonBalanceError("ioneqm rates must be finite")
    m = int(z.size)
    n = m + 1
    l = int(lower_stage)
    if l < 1 or l > n:
        raise IonBalanceError(f"lower_stage {l} outside 1..{n}")

    q = a / (z + float(delt))
    s = np.zeros(n, dtype=float)

    jk = l
    while True:
        jk += 1
        # Fortran q(jk-1), with q one-based.
        if jk < n and q[jk - 2] < 1.0:
            continue
        break
    jmax = jk

    suml = 0.0
    mmx = jmax - 1
    if jmax != n:
        pl = 1.0
        while True:
            mmx += 1
            pl = pl / (q[mmx - 1] + float(delt))
            suml += pl
            tst = pl / (suml + float(delt))
            if not (tst > eps and mmx < m):
                break

    sumg = 0.0
    mmn = jmax
    if jmax != l:
        pg = 1.0
        while True:
            mmn -= 1
            pg = pg * q[mmn - 1]
            sumg += pg
            tst = pg / (sumg + float(delt))
            if not (tst > eps and mmn > l):
                break

    s[jmax - 1] = 1.0 / (1.0 + suml + sumg)
    if jmax != n:
        for j in range(jmax, mmx + 1):
            s[j] = s[j - 1] / (q[j - 1] + float(delt))
    if jmax != l:
        k = jmax - mmn
        for i in range(1, k + 1):
            j = jmax - i
            s[j - 1] = s[j] * q[j - 1]

    return IoneqmResult(
        fractions=s,
        q_ratio=q,
        jmax=int(jmax),
        mmn=int(mmn),
        mmx=int(mmx),
    )


def istruc(
    ionization_rates: Sequence[float],
    recombination_rates: Sequence[float],
) -> IstrucResult:
    """Translate ``istruc.f90`` with one-based guard arrays.

    Inputs are ordinary zero-based vectors of length ``nnz``.  The returned
    arrays have a guard at index zero; ion stages occupy ``1..nnz+1``.
    """
    z = np.asarray(ionization_rates, dtype=float).reshape(-1)
    a = np.asarray(recombination_rates, dtype=float).reshape(-1)
    if z.size != a.size or z.size < 1:
        raise IonBalanceError("istruc requires equal non-empty rate arrays")
    solved = ioneqm(z, a, lower_stage=1)
    nnz = int(z.size)
    z1 = np.zeros(nnz + 1, dtype=float)
    a1 = np.zeros(nnz + 1, dtype=float)
    x1 = np.zeros(nnz + 2, dtype=float)
    z1[1:] = z
    a1[1:] = a
    x1[1 : nnz + 1] = solved.fractions[:nnz]
    x1[nnz + 1] = max(0.0, 1.0 - float(np.sum(x1[1 : nnz + 1])))
    return IstrucResult(
        ionization_rates=z1,
        recombination_rates=a1,
        fractions=x1,
        ioneqm=solved,
    )


def select_ion_stage_limits(
    fractions: Sequence[float],
    *,
    nnz: int,
    critf: float,
) -> IonStageLimitResult:
    """Translate the ``calc_hmc_element`` search for ``mml/mmu``."""
    x = np.asarray(fractions, dtype=float).reshape(-1)
    if x.size < int(nnz) + 2:
        raise IonBalanceError(
            f"one-based ion-fraction array length {x.size} is too small for nnz={nnz}"
        )
    if critf < 0.0 or not math.isfinite(critf):
        raise IonBalanceError("critf must be finite and nonnegative")

    lfu = 0
    lfl = 0
    mmu = int(nnz) + 2
    mml = 0
    mm = 0
    xitpul = 0.0
    xitpll = 0.0
    while mm <= int(nnz) and (lfu == 0 or lfl == 0):
        mm += 1
        mmu -= 1
        mml += 1
        if xitpul < critf and x[mmu] >= critf and lfu == 0:
            lfu = mmu
        if xitpll < critf and x[mml] >= critf and lfl == 0:
            lfl = mml
        xitpll = float(x[mml])
        xitpul = float(x[mmu])

    mmu = lfu
    mml = lfl
    if lfu == 0:
        mmu = int(nnz) + 1
    if lfl == 0:
        mml = 1
    mml = max(1, mml - 1)
    mmu = min(int(nnz), mmu + 1)
    if critf <= 1.0e-34:
        mml = 1
        mmu = int(nnz)
    if mml > mmu:
        raise IonBalanceError(f"source ion-stage selection produced invalid {mml}..{mmu}")
    return IonStageLimitResult(
        mml=int(mml),
        mmu=int(mmu),
        critf=float(critf),
        lower_crossing=int(lfl),
        upper_crossing=int(lfu),
        iterations=int(mm),
    )


def calc_element_pre_matrix_balance(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    *,
    element_z: int,
    context: CalcIonRatesContext,
    critf: float = 1.0e-8,
    dispatcher: Optional[SourceFaithfulUCalc] = None,
) -> Tuple[Dict[int, CalcIonRatesResult], IstrucResult, IonStageLimitResult]:
    """Run the complete total-rate/``istruc``/stage-limit first pass."""
    nnz = _element_nnz(master, derived, element_z)
    ion_indices = _ion_indices_for_element(derived, element_z)
    by_stage: Dict[int, CalcIonRatesResult] = {}
    for ion_index in ion_indices:
        stage = int(derived.ion_stage[ion_index])
        if stage < 1 or stage > nnz:
            continue
        by_stage[stage] = calc_ion_rates(
            master,
            derived,
            ion_index=ion_index,
            context=context,
            dispatcher=dispatcher,
        )
    missing = [stage for stage in range(1, nnz + 1) if stage not in by_stage]
    if missing:
        raise IonBalanceError(f"element Z={element_z} is missing ion headers for stages {missing}")
    pirt = np.asarray([by_stage[stage].pirti for stage in range(1, nnz + 1)], dtype=float)
    rrrt = np.asarray([by_stage[stage].rrrti for stage in range(1, nnz + 1)], dtype=float)
    preliminary = istruc(pirt, rrrt)
    limits = select_ion_stage_limits(preliminary.fractions, nnz=nnz, critf=critf)
    return by_stage, preliminary, limits


__all__ = [
    "IonBalanceError",
    "CalcIonRatesContext",
    "CalcIonRateContribution",
    "CalcIonRatesResult",
    "IoneqmResult",
    "IstrucResult",
    "IonStageLimitResult",
    "calc_ion_rates",
    "ioneqm",
    "istruc",
    "select_ion_stage_limits",
    "calc_element_pre_matrix_balance",
]
