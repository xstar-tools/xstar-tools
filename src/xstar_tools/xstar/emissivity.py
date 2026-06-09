"""Source-faithful translation of XSTAR ``calc_emisab_all``.

The translated source chain is::

    xstarcalc.f90
      -> calc_emisab_all.f90
      -> calc_emisab_element.f90
      -> calc_emisab_ion.f90
      -> calc_rates_level_lte.f90 / ucalc.f90 / pescl.f90 / pescv.f90

This module deliberately preserves the original ownership boundaries:
``calc_emisab_all`` clears only the line/RRC output arrays, while continuum
emissivity and opacity arrays remain caller-owned and are incremented by
``ucalc``.  Compact element populations retain XSTAR's repeated continuum /
next-ion-ground alias, including source-order overwrite by every ion of the
element even when that ion is outside the active stage limits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import numpy as np

from .spectral_parity import classify_spectral_shadow_arrays as _classify_spectral_shadow_arrays

from .atomic_database import XSTARMasterData, XSTARDerivedPointers
from .driver import XSTARPythonDriver, XSTARSourceRoutine
from .element_equilibrium import EscapeProbabilityContext, build_level_table, pescl, pescv
from .state import XSTARPythonState
from .ucalc import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcResult,
    UCalcStatus,
    default_source_faithful_ucalc,
)


XSTAR_CALC_EMISAB_PRESSURE_COEFFICIENT = float(np.float32(1.38e-12))
XSTAR_CALC_EMISAB_ERG_PER_EV = 1.602176634e-12
XSTAR_CALC_EMISAB_FOUR_PI = float(np.float32(12.56))
XSTAR_CALC_EMISAB_ABUNDANCE_FLOOR = 1.0e-24
XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR = float(np.float32(1.0e-34))


def _env_true(name: str) -> bool:
    return str(os.environ.get(name, "0")).strip().lower() in {"1", "true", "yes", "on"}


def _native_spectral_requested(*, product: bool = False, shadow: bool = False) -> bool:
    if not _env_true("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP"):
        return False
    if product and not _env_true("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP_PRODUCT"):
        return False
    if shadow and not _env_true("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP_SHADOW"):
        return False
    return True


class _TraceSink(list):
    def append(self, value: Any) -> None:  # type: ignore[override]
        return None


def _spectral_summary_bucket(context: CalcEmisabContext) -> MutableMapping[str, Any]:
    control = context.profile_control if isinstance(context.profile_control, MutableMapping) else {}
    summary = control.setdefault("native_spectral_engine_summary", {
        "schema_version": "0.6.46.1",
        "emisab_calls": 0, "emis_calls": 0,
        "contributions_attempted": 0, "contributions_committed": 0,
        "emissivity_contributions": 0, "opacity_contributions": 0,
        "line_profiles": 0, "source_order_violations": 0,
        "shadow_compared": 0, "shadow_mismatches": 0,
        "shadow_ulp_tolerated_calls": 0, "shadow_ulp_tolerated_values": 0,
        "shadow_max_ulp": 0, "shadow_ulp_policy": "emis_opakc_only_max_1_ulp",
        "first_ulp_tolerated": {},
        "product_commits": 0, "fallbacks": 0,
        "packing_seconds": 0.0, "ffi_seconds": 0.0,
        "construction_seconds": 0.0, "opacity_seconds": 0.0, "commit_seconds": 0.0,
        "python_record_traces_materialized": 0,
        "first_mismatch": {},
    })
    if not isinstance(summary, MutableMapping):
        summary = {}
    return summary


def _record_spectral_shadow_result(
    summary: MutableMapping[str, Any], status: str, detail: Optional[Mapping[str, Any]] = None
) -> None:
    summary["shadow_compared"] = int(summary.get("shadow_compared", 0)) + 1
    if status == "shadow_mismatch":
        summary["shadow_mismatches"] = int(summary.get("shadow_mismatches", 0)) + 1
        if detail and not summary.get("first_mismatch"):
            summary["first_mismatch"] = dict(detail)
    elif status == "shadow_ulp_tolerated":
        summary["shadow_ulp_tolerated_calls"] = int(summary.get("shadow_ulp_tolerated_calls", 0)) + 1
        summary["shadow_ulp_tolerated_values"] = int(summary.get("shadow_ulp_tolerated_values", 0)) + int((detail or {}).get("differing_values", 0) or 0)
        summary["shadow_max_ulp"] = max(
            int(summary.get("shadow_max_ulp", 0) or 0),
            int((detail or {}).get("max_ulp", 0) or 0),
        )
        summary["shadow_ulp_policy"] = "emis_opakc_only_max_1_ulp"
        if detail and not summary.get("first_ulp_tolerated"):
            summary["first_ulp_tolerated"] = dict(detail)


def _add_spectral_metrics(summary: MutableMapping[str, Any], metrics: Mapping[str, Any], *, phase: str, status: str, mismatch: Optional[Mapping[str, Any]] = None) -> None:
    summary[f"{phase}_calls"] = int(summary.get(f"{phase}_calls", 0)) + 1
    for key in ("contributions_attempted", "contributions_committed", "emissivity_contributions", "opacity_contributions", "line_profiles", "source_order_violations"):
        summary[key] = int(summary.get(key, 0)) + int(metrics.get(key, 0) or 0)
    for key in ("packing_seconds", "ffi_seconds", "construction_seconds", "opacity_seconds", "commit_seconds"):
        summary[key] = float(summary.get(key, 0.0)) + float(metrics.get(key, 0.0) or 0.0)
    if status == "product":
        summary["product_commits"] = int(summary.get("product_commits", 0)) + 1
    elif status in {"shadow_match", "shadow_mismatch", "shadow_ulp_tolerated"}:
        _record_spectral_shadow_result(summary, status, mismatch)
    elif status == "fallback":
        summary["fallbacks"] = int(summary.get("fallbacks", 0)) + 1


class CalcEmisabPortError(RuntimeError):
    """Raised when the translated source contract cannot be executed."""


@dataclass
class CalcEmisabWorkspace:
    """Caller-owned output/work arrays used by ``calc_emisab_all``.

    Line and RRC-indexed arrays use a zero guard so XSTAR one-based pointer
    values can be used directly.  Continuum-energy arrays are ordinary
    zero-based NumPy arrays because ``ucalc`` diagnostics already expose the
    complete physical grid as Python sequences.
    """

    rcem: np.ndarray
    oplin: np.ndarray
    brcems: np.ndarray
    rccemis: np.ndarray
    opakc: np.ndarray
    opakcont: np.ndarray
    cemab: np.ndarray
    cabab: np.ndarray
    opakab: np.ndarray

    @classmethod
    def allocate(
        cls,
        *,
        n_lines: int,
        n_continua: int,
        n_energy: int,
        continuum_fill: float = 0.0,
    ) -> "CalcEmisabWorkspace":
        return cls(
            rcem=np.zeros((2, int(n_lines) + 1), dtype=float),
            oplin=np.zeros(int(n_lines) + 1, dtype=float),
            brcems=np.full(int(n_energy), float(continuum_fill), dtype=float),
            rccemis=np.full((2, int(n_energy)), float(continuum_fill), dtype=float),
            opakc=np.full(int(n_energy), float(continuum_fill), dtype=float),
            opakcont=np.full(int(n_energy), float(continuum_fill), dtype=float),
            cemab=np.zeros((2, int(n_continua) + 1), dtype=float),
            cabab=np.zeros(int(n_continua) + 1, dtype=float),
            opakab=np.zeros(int(n_continua) + 1, dtype=float),
        )

    def validate(self, *, n_lines: int, n_continua: int, n_energy: int) -> None:
        # The continuum work arrays are dimensioned on the caller's full
        # ``ncn`` grid even when ``calc_emisab_all`` receives the reduced
        # ``epim(1:ncn2m)`` grid.  Require capacity for the active reduced
        # range, but preserve caller-owned rows above ``ncn2m``.
        checks = {
            "rcem": self.rcem.shape == (2, int(n_lines) + 1),
            "oplin": self.oplin.shape == (int(n_lines) + 1,),
            "brcems": self.brcems.ndim == 1 and self.brcems.shape[0] >= int(n_energy),
            "rccemis": self.rccemis.ndim == 2 and self.rccemis.shape[0] == 2 and self.rccemis.shape[1] >= int(n_energy),
            "opakc": self.opakc.ndim == 1 and self.opakc.shape[0] >= int(n_energy),
            "opakcont": self.opakcont.ndim == 1 and self.opakcont.shape[0] >= int(n_energy),
            "cemab": self.cemab.shape == (2, int(n_continua) + 1),
            "cabab": self.cabab.shape == (int(n_continua) + 1,),
            "opakab": self.opakab.shape == (int(n_continua) + 1,),
        }
        bad = [name for name, ok in checks.items() if not ok]
        if bad:
            raise CalcEmisabPortError("invalid calc_emisab workspace shapes: " + ", ".join(bad))
        for name in checks:
            if not np.all(np.isfinite(np.asarray(getattr(self, name), dtype=float))):
                raise CalcEmisabPortError(f"{name} contains non-finite values")

    def clear_source_outputs(self) -> None:
        """Replay only the arrays cleared by ``calc_emisab_all.f90``."""
        self.cemab[:, :] = 0.0
        self.cabab[:] = 0.0
        self.opakab[:] = 0.0
        self.rcem[:, :] = 0.0
        self.oplin[:] = 0.0


@dataclass
class CalcEmisabContext:
    master: XSTARMasterData
    derived: XSTARDerivedPointers
    temperature_1e4K: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    pressure_dyn_cm2: float
    density_control_lcdd: int
    abundances_by_z: Mapping[int, float]
    min_ion_stage_by_z: Mapping[int, int]
    max_ion_stage_by_z: Mapping[int, int]
    xilevg: np.ndarray
    bilevg: np.ndarray
    rnisg: np.ndarray
    radiation: Any
    workspace: CalcEmisabWorkspace
    escape: EscapeProbabilityContext = field(default_factory=EscapeProbabilityContext)
    covering_fraction: float = 1.0
    turbulent_velocity_km_s: float = 0.0
    critical_ion_fraction: float = 0.0
    radiation_temperature: float = 0.0
    radius_cm: float = 0.0
    zone_thickness_cm: float = 0.0
    lfast: int = 2
    strict_ucalc: bool = True
    ucalc_engine: Optional[SourceFaithfulUCalc] = None
    ucalc_evaluator: Optional[Callable[[int, UCalcContext], UCalcResult]] = None
    initial_leveltemp_workspace: Optional[UCalcLevelTable] = None
    retain_traces: bool = True
    profile_control: Optional[MutableMapping[str, Any]] = None

    @property
    def temperature_k(self) -> float:
        return float(self.temperature_1e4K) * 1.0e4

    def abundance(self, z: int) -> float:
        return float(self.abundances_by_z.get(int(z), 0.0))

    def min_stage(self, z: int) -> int:
        return int(self.min_ion_stage_by_z.get(int(z), 1))

    def max_stage(self, z: int) -> int:
        return int(self.max_ion_stage_by_z.get(int(z), int(z) + 1))


@dataclass(frozen=True)
class CalcEmisabRecordTrace:
    record: int
    data_type: int
    rate_type: int
    element_z: int
    ion_index: int
    ion_stage: int
    compact_offset: int
    idest1: int
    idest2: int
    lower_compact: int
    upper_compact: int
    output_index: int
    abundance_lower: float
    abundance_upper: float
    ptmp1: float
    ptmp2: float
    ans3: float
    ans4: float
    opak_local: float
    status: str
    output_role: str


@dataclass(frozen=True)
class CalcEmisabIonTrace:
    ion_record: int
    ion_index: int
    ion_stage: int
    nlev: int
    compact_offset: int
    active: bool
    n_records_visited: int
    n_records_evaluated: int


@dataclass(frozen=True)
class CalcEmisabElementTrace:
    element_record: int
    element_z: int
    abundance: float
    abundant: bool
    compact_population_count: int
    compact_xileve: tuple[float, ...]
    ion_traces: tuple[CalcEmisabIonTrace, ...]


@dataclass(frozen=True)
class CalcEmisabResult:
    hydrogen_density_cm3: float
    electron_density_cm3: float
    neutral_h_density_cm3: float
    ionized_h_density_cm3: float
    element_traces: tuple[CalcEmisabElementTrace, ...]
    record_traces: tuple[CalcEmisabRecordTrace, ...]
    leveltemp_workspace: UCalcLevelTable
    workspace: CalcEmisabWorkspace
    source_file: str = "xstar/xstarlib/src/calc_emisab_all.f90"


@dataclass(frozen=True)
class _IonDescriptor:
    element_record: int
    ion_record: int
    element_z: int
    ion_stage: int
    ion_index: int
    nlev: int


def _one_based_array_value(values: np.ndarray, index: int, name: str) -> float:
    arr = np.asarray(values, dtype=float).reshape(-1)
    ii = int(index)
    if ii <= 0 or ii >= arr.size:
        raise CalcEmisabPortError(f"{name} missing one-based index {ii}; array length={arr.size}")
    return float(arr[ii])


def _radiation_arrays(radiation: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    epi = np.asarray(getattr(radiation, "epim_eV", getattr(radiation, "epim", ())), dtype=float).reshape(-1)
    brem = np.asarray(getattr(radiation, "bremsam", ()), dtype=float).reshape(-1)
    bint = np.asarray(getattr(radiation, "bremsint", ()), dtype=float).reshape(-1)
    if epi.size < 4 or brem.size < epi.size or bint.size < epi.size:
        raise CalcEmisabPortError(
            "calc_emisab requires epim with at least four bins and "
            "bremsam/bremsint capacity for the active reduced grid"
        )
    if np.any(np.diff(epi) <= 0.0) or not all(
        np.all(np.isfinite(x)) for x in (epi, brem[: epi.size], bint[: epi.size])
    ):
        raise CalcEmisabPortError("invalid calc_emisab radiation arrays")
    return epi, brem[: epi.size], bint[: epi.size]


def resolve_calc_emisab_density(*, xpx: float, pressure: float, t_1e4: float, xee: float, lcdd: int) -> float:
    """Translate the two density overrides at the top of ``calc_emisab_all``."""
    value = float(xpx)
    if int(lcdd) == 0:
        value = float(pressure) / XSTAR_CALC_EMISAB_PRESSURE_COEFFICIENT / max(float(t_1e4), 1.0e-24)
    if int(lcdd) == 2:
        value = float(pressure) / (float(xee) + 1.0e-34)
    return value


def _iter_ion_descriptors(context: CalcEmisabContext, element_record: int, element_z: int) -> list[_IonDescriptor]:
    out: list[_IonDescriptor] = []
    rec = int(context.derived.npfirst[12])
    while rec:
        if int(context.derived.npar[rec]) == int(element_record):
            ints = context.master.record_integers(rec)
            if len(ints) < 1:
                raise CalcEmisabPortError(f"ion record {rec} has no integer payload")
            ion_stage = int(ints[0])
            ion_index = int(ints[-1])
            nlev = int(context.derived.nlevs[ion_index])
            out.append(_IonDescriptor(element_record, rec, element_z, ion_stage, ion_index, nlev))
        rec = int(context.derived.npnxt[rec])
    return out


def _copy_or_initialize_leveltemp(initial: Optional[UCalcLevelTable]) -> UCalcLevelTable:
    if initial is None:
        return UCalcLevelTable(levels={}, nlev=0)
    return UCalcLevelTable(levels=dict(initial.levels), nlev=int(initial.nlev))


def _overwrite_leveltemp(workspace: UCalcLevelTable, current: UCalcLevelTable) -> UCalcLevelTable:
    for index in range(1, int(current.nlev) + 1):
        workspace.levels[index] = current.require(index)
    workspace.nlev = int(current.nlev)
    return workspace


def _compact_element_populations(
    context: CalcEmisabContext,
    ions: Sequence[_IonDescriptor],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    total = 1 + sum(max(0, ion.nlev - 1) for ion in ions)
    x = np.zeros(total + 1, dtype=float)
    b = np.zeros(total + 1, dtype=float)
    r = np.zeros(total + 1, dtype=float)
    ipmat = 0
    for ion in ions:
        for local in range(1, ion.nlev + 1):
            global_index = int(context.derived.npilev[local, ion.ion_index])
            compact = local + ipmat
            x[compact] = _one_based_array_value(context.xilevg, global_index, "xilevg")
            b[compact] = _one_based_array_value(context.bilevg, global_index, "bilevg")
            r[compact] = _one_based_array_value(context.rnisg, global_index, "rnisg")
        ipmat += ion.nlev - 1
    return x, b, r


def _accumulate_ucalc_continuum(workspace: CalcEmisabWorkspace, result: UCalcResult) -> None:
    diagnostics = result.diagnostics
    for key, target in (
        ("opakc_cm^-1", workspace.opakc),
        ("opakcont_cm^-1", workspace.opakcont),
    ):
        values = diagnostics.get(key)
        if values is not None:
            arr = np.asarray(values, dtype=float).reshape(-1)
            if arr.size > target.size:
                raise CalcEmisabPortError(
                    f"ucalc {key} length {arr.size} exceeds continuum capacity {target.size}"
                )
            target[: arr.size] += arr
    inward = diagnostics.get("rccemis_inward")
    outward = diagnostics.get("rccemis_outward")
    if inward is not None:
        arr = np.asarray(inward, dtype=float).reshape(-1)
        if arr.size > workspace.rccemis.shape[1]:
            raise CalcEmisabPortError("ucalc inward continuum emissivity exceeds workspace")
        workspace.rccemis[0, : arr.size] += arr
    if outward is not None:
        arr = np.asarray(outward, dtype=float).reshape(-1)
        if arr.size > workspace.rccemis.shape[1]:
            raise CalcEmisabPortError("ucalc outward continuum emissivity exceeds workspace")
        workspace.rccemis[1, : arr.size] += arr


def _evaluate_ucalc(context: CalcEmisabContext, record: int, ucontext: UCalcContext) -> UCalcResult:
    if context.ucalc_evaluator is not None:
        return context.ucalc_evaluator(int(record), ucontext)
    engine = context.ucalc_engine or default_source_faithful_ucalc()
    return engine.evaluate_record_number(
        context.master,
        int(record),
        ucontext,
        parent_record=int(context.derived.npar[int(record)]),
        next_record=int(context.derived.npnxt[int(record)]),
        strict=bool(context.strict_ucalc),
    )


def _ucalc_context(
    context: CalcEmisabContext,
    *,
    ion: _IonDescriptor,
    levels: UCalcLevelTable,
    xpx: float,
    xh0: float,
    xh1: float,
    ptmp1: float,
    ptmp2: float,
    abund1: float,
    abund2: float,
) -> UCalcContext:
    return UCalcContext(
        temperature_k=context.temperature_k,
        hydrogen_density_cm3=xpx,
        electron_fraction_xee=context.electron_fraction_xee,
        neutral_h_density_cm3=xh0,
        ionized_h_density_cm3=xh1,
        turbulent_velocity_km_s=context.turbulent_velocity_km_s,
        covering_fraction=context.covering_fraction,
        ptmp1=ptmp1,
        ptmp2=ptmp2,
        abund1=abund1,
        abund2=abund2,
        jkion=ion.ion_index,
        nlev=ion.nlev,
        lfast=context.lfast,
        indonly=False,
        levels=levels,
        radiation=context.radiation,
        derived_pointers=context.derived,
        master=context.master,
        extras={
            "radius_cm": context.radius_cm,
            "zone_thickness_cm": context.zone_thickness_cm,
            "radiation_temperature": context.radiation_temperature,
            "lfpi": 2,
        },
    )


def calc_emisab_ion(
    context: CalcEmisabContext,
    *,
    ion: _IonDescriptor,
    element_abundance: float,
    compact_xileve: np.ndarray,
    compact_offset: int,
    xpx: float,
    xh0: float,
    xh1: float,
    leveltemp_workspace: UCalcLevelTable,
    record_traces: list[CalcEmisabRecordTrace],
    native_contributions: Optional[list[dict[str, Any]]] = None,
) -> CalcEmisabIonTrace:
    """Translate one call to ``calc_emisab_ion.f90``."""
    current_levels = build_level_table(context.master, context.derived, ion.ion_index)
    _overwrite_leveltemp(leveltemp_workspace, current_levels)
    # The Fortran ``nlev`` argument is current-ion length while higher retained
    # columns remain addressable in leveltemp.  Keep that composite view.
    levels = UCalcLevelTable(levels=dict(leveltemp_workspace.levels), nlev=ion.nlev)
    visited = evaluated = 0
    max_rate_type = min(int(context.derived.max_rate_type), int(context.derived.npfi.shape[0] - 1))
    epi, _, _ = _radiation_arrays(context.radiation)

    for rate_type in range(1, max_rate_type + 1):
        rec = int(context.derived.npfi[rate_type, ion.ion_index])
        while rec and int(context.derived.npar[rec]) == ion.ion_record:
            visited += 1
            header = context.master.header(rec)
            ints = context.master.record_integers(rec)

            if rate_type == 7 and len(ints) >= 4:
                idest1 = int(ints[-2])
                idest2 = ion.nlev + int(ints[-4]) - 1
                continuum_index = int(context.derived.npconi2[rec])
                if 0 < continuum_index <= context.derived.ncsvn and idest1 > 0:
                    lower = idest1 + compact_offset
                    upper = idest2 + compact_offset
                    abund1 = float(compact_xileve[lower]) * element_abundance
                    abund2 = float(compact_xileve[upper]) * element_abundance
                    tau1, tau2 = context.escape.continuum_taus(continuum_index)
                    if tau1 is None or tau2 is None:
                        if not context.escape.allow_missing_as_zero:
                            raise CalcEmisabPortError(f"missing continuum optical depth {continuum_index}")
                        tau1 = 0.0 if tau1 is None else tau1
                        tau2 = 0.0 if tau2 is None else tau2
                    ptmp1 = pescv(tau1) * (1.0 - context.covering_fraction)
                    ptmp2 = pescv(tau2) * (1.0 - context.covering_fraction) + 2.0 * pescv(tau1 + tau2) * context.covering_fraction
                    result = UCalcResult(rec, header.data_type, header.rate_type, UCalcStatus.EVALUATED)
                    if abund1 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR or abund2 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR:
                        result = _evaluate_ucalc(context, rec, _ucalc_context(
                            context, ion=ion, levels=levels, xpx=xpx, xh0=xh0, xh1=xh1,
                            ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
                        ))
                        if result.ready:
                            evaluated += 1
                            _accumulate_ucalc_continuum(context.workspace, result)
                    denom = ptmp1 + ptmp2
                    if denom == 0.0:
                        raise CalcEmisabPortError("zero continuum escape denominator")
                    if native_contributions is not None:
                        native_contributions.append({
                            "source_position": len(native_contributions) + 1,
                            "record": int(rec), "kind": 1,
                            "rate_type": int(rate_type), "data_type": int(header.data_type),
                            "output_index": int(continuum_index),
                            "ptmp1": float(ptmp1), "ptmp2": float(ptmp2),
                            "abundance_lower": float(abund1), "abundance_upper": float(abund2),
                            "hydrogen_density": float(xpx),
                            "ans1": float(result.ans1), "ans2": float(result.ans2),
                            "ans3": float(result.ans3), "ans4": float(result.ans4),
                            "opakab": float(result.opakab),
                        })
                    if not _native_spectral_requested(product=True):
                        context.workspace.opakab[continuum_index] = result.opakab
                        context.workspace.cabab[continuum_index] = abs(result.ans4) * abund1 * xpx
                        context.workspace.cemab[0, continuum_index] = ptmp1 * abs(result.ans3) / denom * abund2 * xpx
                        context.workspace.cemab[1, continuum_index] = ptmp2 * abs(result.ans3) / denom * abund2 * xpx
                    record_traces.append(CalcEmisabRecordTrace(
                        rec, header.data_type, rate_type, ion.element_z, ion.ion_index, ion.ion_stage,
                        compact_offset, idest1, idest2, lower, upper, continuum_index,
                        abund1, abund2, ptmp1, ptmp2, result.ans3, result.ans4,
                        result.opakab, result.status.value, "bound_free_rate_type_7",
                    ))

            if rate_type in (4, 9, 14):
                if rate_type in (4, 9) and len(ints) >= 2:
                    idest1, idest2 = int(ints[0]), int(ints[1])
                    line_index = int(context.derived.nplini[rec])
                    tau1, tau2 = context.escape.line_taus(line_index)
                    if tau1 is None or tau2 is None:
                        if not context.escape.allow_missing_as_zero:
                            raise CalcEmisabPortError(f"missing line optical depth {line_index}")
                        tau1 = 0.0 if tau1 is None else tau1
                        tau2 = 0.0 if tau2 is None else tau2
                elif rate_type == 14 and len(ints) >= 3:
                    idest1, idest2 = int(ints[-3]), int(ints[-2])
                    line_index = 0
                    tau1 = tau2 = 0.0
                else:
                    rec = int(context.derived.npnxt[rec])
                    continue

                if 0 < idest1 < ion.nlev and 0 < idest2 < ion.nlev:
                    e1 = levels.require(idest1).energy_ev
                    e2 = levels.require(idest2).energy_ev
                    if e1 < e2:
                        lower, upper = idest1 + compact_offset, idest2 + compact_offset
                    else:
                        lower, upper = idest2 + compact_offset, idest1 + compact_offset
                    abund1 = float(compact_xileve[lower]) * xpx * element_abundance
                    abund2 = float(compact_xileve[upper]) * xpx * element_abundance
                    ptmp1 = pescl(tau1) * (1.0 - context.covering_fraction)
                    ptmp2 = pescl(tau2) * (1.0 - context.covering_fraction) + 2.0 * pescl(tau1 + tau2) * context.covering_fraction
                    result = UCalcResult(rec, header.data_type, header.rate_type, UCalcStatus.EVALUATED)
                    if abund1 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR or abund2 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR:
                        result = _evaluate_ucalc(context, rec, _ucalc_context(
                            context, ion=ion, levels=levels, xpx=xpx, xh0=xh0, xh1=xh1,
                            ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
                        ))
                        if result.ready:
                            evaluated += 1
                            _accumulate_ucalc_continuum(context.workspace, result)
                    denom = ptmp1 + ptmp2
                    if denom == 0.0:
                        raise CalcEmisabPortError("zero line escape denominator")
                    role = "rate_type_9_no_direct_output"
                    if rate_type == 14:
                        rcemm = abund2 * abs(result.ans3)
                        context.workspace.rccemis[1, 2] += rcemm / (float(epi[3]) - float(epi[2]) + float(np.float32(1.0e-24))) / XSTAR_CALC_EMISAB_ERG_PER_EV / XSTAR_CALC_EMISAB_FOUR_PI
                        role = "radiative_superlevel_continuum_bin_3"
                    elif rate_type == 4 and line_index != 0:
                        if native_contributions is not None:
                            native_contributions.append({
                                "source_position": len(native_contributions) + 1,
                                "record": int(rec), "kind": 2,
                                "rate_type": int(rate_type), "data_type": int(header.data_type),
                                "output_index": int(line_index),
                                "ptmp1": float(ptmp1), "ptmp2": float(ptmp2),
                                "abundance_lower": float(abund1), "abundance_upper": float(abund2),
                                "hydrogen_density": float(xpx),
                                "ans1": float(result.ans1), "ans2": float(result.ans2),
                                "ans3": float(result.ans3), "ans4": float(result.ans4),
                                "opakab": float(result.opakab),
                            })
                        if not _native_spectral_requested(product=True):
                            context.workspace.rcem[0, line_index] = -abund2 * result.ans3 * ptmp1 / denom
                            context.workspace.rcem[1, line_index] = -abund2 * result.ans3 * ptmp2 / denom
                            context.workspace.oplin[line_index] = result.opakab * abund1
                        role = "bound_bound_rate_type_4"
                    record_traces.append(CalcEmisabRecordTrace(
                        rec, header.data_type, rate_type, ion.element_z, ion.ion_index, ion.ion_stage,
                        compact_offset, idest1, idest2, lower, upper, line_index,
                        abund1, abund2, ptmp1, ptmp2, result.ans3, result.ans4,
                        result.opakab, result.status.value, role,
                    ))

            rec = int(context.derived.npnxt[rec])

    return CalcEmisabIonTrace(
        ion_record=ion.ion_record,
        ion_index=ion.ion_index,
        ion_stage=ion.ion_stage,
        nlev=ion.nlev,
        compact_offset=compact_offset,
        active=True,
        n_records_visited=visited,
        n_records_evaluated=evaluated,
    )


def calc_emisab_element(
    context: CalcEmisabContext,
    *,
    element_record: int,
    element_z: int,
    element_abundance: float,
    ions: Sequence[_IonDescriptor],
    compact_xileve: np.ndarray,
    xpx: float,
    xh0: float,
    xh1: float,
    leveltemp_workspace: UCalcLevelTable,
    record_traces: list[CalcEmisabRecordTrace],
    native_contributions: Optional[list[dict[str, Any]]] = None,
) -> CalcEmisabElementTrace:
    """Translate ``calc_emisab_element.f90`` in ion source order."""
    ipmat = 0
    ion_traces: list[CalcEmisabIonTrace] = []
    for ion in ions:
        active = context.min_stage(element_z) <= ion.ion_stage <= context.max_stage(element_z)
        if active:
            trace = calc_emisab_ion(
                context,
                ion=ion,
                element_abundance=element_abundance,
                compact_xileve=compact_xileve,
                compact_offset=ipmat,
                xpx=xpx,
                xh0=xh0,
                xh1=xh1,
                leveltemp_workspace=leveltemp_workspace,
                record_traces=record_traces,
                native_contributions=native_contributions,
            )
        else:
            trace = CalcEmisabIonTrace(
                ion_record=ion.ion_record, ion_index=ion.ion_index, ion_stage=ion.ion_stage,
                nlev=ion.nlev, compact_offset=ipmat, active=False,
                n_records_visited=0, n_records_evaluated=0,
            )
        ion_traces.append(trace)
        # Source increments even for inactive ions.
        ipmat += ion.nlev - 1
    return CalcEmisabElementTrace(
        element_record=int(element_record),
        element_z=int(element_z),
        abundance=float(element_abundance),
        abundant=True,
        compact_population_count=int(ipmat + 1),
        compact_xileve=tuple(float(v) for v in compact_xileve[1 : ipmat + 2]),
        ion_traces=tuple(ion_traces),
    )


def calc_emisab_all(context: CalcEmisabContext) -> CalcEmisabResult:
    """Execute ``calc_emisab_all.f90`` in literal source order."""
    epi, _, _ = _radiation_arrays(context.radiation)
    context.workspace.validate(
        n_lines=context.derived.nlsvn,
        n_continua=context.derived.ncsvn,
        n_energy=len(epi),
    )
    context.workspace.clear_source_outputs()
    native_product = _native_spectral_requested(product=True)
    native_shadow = _native_spectral_requested(shadow=True)
    native_contributions: Optional[list[dict[str, Any]]] = [] if (native_product or native_shadow) else None
    xpx = resolve_calc_emisab_density(
        xpx=context.hydrogen_density_cm3,
        pressure=context.pressure_dyn_cm2,
        t_1e4=context.temperature_1e4K,
        xee=context.electron_fraction_xee,
        lcdd=context.density_control_lcdd,
    )
    xnx = xpx * context.electron_fraction_xee
    h_abundance = context.abundance(1)
    h_ground = _one_based_array_value(context.xilevg, 1, "xilevg")
    xh0 = xpx * h_ground * h_abundance
    xh1 = xpx * (1.0 - h_ground) * h_abundance
    leveltemp = _copy_or_initialize_leveltemp(context.initial_leveltemp_workspace)
    retain_traces = bool(getattr(context, "retain_traces", True))
    element_traces: list[CalcEmisabElementTrace] = []
    record_traces: list[CalcEmisabRecordTrace] | _TraceSink = [] if retain_traces else _TraceSink()

    element_record = int(context.derived.npfirst[11])
    while element_record:
        ints = context.master.record_integers(element_record)
        if len(ints) < 1:
            raise CalcEmisabPortError(f"element record {element_record} has no integer payload")
        z = int(ints[0])
        abundance = context.abundance(z) if z > 0 else 0.0
        if abundance > XSTAR_CALC_EMISAB_ABUNDANCE_FLOOR:
            ions = _iter_ion_descriptors(context, element_record, z)
            compact_x, _, _ = _compact_element_populations(context, ions)
            element_traces.append(calc_emisab_element(
                context,
                element_record=element_record,
                element_z=z,
                element_abundance=abundance,
                ions=ions,
                compact_xileve=compact_x,
                xpx=xpx,
                xh0=xh0,
                xh1=xh1,
                leveltemp_workspace=leveltemp,
                record_traces=record_traces,
                native_contributions=native_contributions,
            ))
        else:
            element_traces.append(CalcEmisabElementTrace(
                element_record=element_record, element_z=z, abundance=abundance,
                abundant=False, compact_population_count=0, compact_xileve=(), ion_traces=(),
            ))
        element_record = int(context.derived.npnxt[element_record])

    if native_contributions is not None:
        from .cpp_backend_spectral import apply_spectral_contributions_cpp
        summary = _spectral_summary_bucket(context)
        summary["python_record_traces_materialized"] = int(summary.get("python_record_traces_materialized", 0)) + (len(record_traces) if retain_traces else 0)

        def _apply_python_fallback(rows: Sequence[Mapping[str, Any]]) -> None:
            rcem_stride = context.workspace.rcem.shape[1]
            cemab_stride = context.workspace.cemab.shape[1]
            del rcem_stride, cemab_stride
            for row in rows:
                kind = int(row.get("kind", 0))
                idx = int(row.get("output_index", 0))
                p1 = float(row.get("ptmp1", 0.0)); p2 = float(row.get("ptmp2", 0.0))
                a1 = float(row.get("abundance_lower", 0.0)); a2 = float(row.get("abundance_upper", 0.0))
                ans3 = float(row.get("ans3", 0.0)); ans4 = float(row.get("ans4", 0.0))
                opak = float(row.get("opakab", 0.0)); den = p1 + p2
                if kind == 1 and idx > 0 and den != 0.0:
                    context.workspace.opakab[idx] = opak
                    context.workspace.cabab[idx] = abs(ans4) * a1 * xpx
                    context.workspace.cemab[0, idx] = p1 * abs(ans3) / den * a2 * xpx
                    context.workspace.cemab[1, idx] = p2 * abs(ans3) / den * a2 * xpx
                elif kind == 2 and int(row.get("rate_type", 0)) == 4 and idx > 0 and den != 0.0:
                    context.workspace.rcem[0, idx] = -a2 * ans3 * p1 / den
                    context.workspace.rcem[1, idx] = -a2 * ans3 * p2 / den
                    context.workspace.oplin[idx] = opak * a1

        try:
            if native_shadow and not native_product:
                # Preserve Python-only branches (for example rate type 14),
                # then clear only cells owned by native contributions before
                # replaying those contributions through C++.
                candidate_rcem = context.workspace.rcem.copy()
                candidate_oplin = context.workspace.oplin.copy()
                candidate_cemab = context.workspace.cemab.copy()
                candidate_cabab = context.workspace.cabab.copy()
                candidate_opakab = context.workspace.opakab.copy()
                for row in native_contributions:
                    idx = int(row.get("output_index", 0))
                    kind = int(row.get("kind", 0))
                    if kind == 1 and idx > 0:
                        candidate_opakab[idx] = 0.0
                        candidate_cabab[idx] = 0.0
                        candidate_cemab[:, idx] = 0.0
                    elif kind == 2 and idx > 0:
                        candidate_oplin[idx] = 0.0
                        candidate_rcem[:, idx] = 0.0
                metrics = apply_spectral_contributions_cpp(
                    native_contributions,
                    rcem=candidate_rcem, oplin=candidate_oplin,
                    cemab=candidate_cemab, cabab=candidate_cabab, opakab=candidate_opakab,
                    rccemis=context.workspace.rccemis.copy(), opakc=context.workspace.opakc.copy(),
                    opakcont=context.workspace.opakcont.copy(),
                    fline=np.zeros_like(context.workspace.rcem), flinel=np.zeros_like(context.workspace.opakc),
                    epi_eV=epi,
                )
                shadow_status, shadow_detail = _classify_spectral_shadow_arrays((
                    ("rcem", context.workspace.rcem, candidate_rcem),
                    ("oplin", context.workspace.oplin, candidate_oplin),
                    ("cemab", context.workspace.cemab, candidate_cemab),
                    ("cabab", context.workspace.cabab, candidate_cabab),
                    ("opakab", context.workspace.opakab, candidate_opakab),
                ), phase="emisab")
                _add_spectral_metrics(
                    summary, metrics, phase="emisab", status=shadow_status, mismatch=shadow_detail
                )
            elif native_product:
                metrics = apply_spectral_contributions_cpp(
                    native_contributions,
                    rcem=context.workspace.rcem, oplin=context.workspace.oplin,
                    cemab=context.workspace.cemab, cabab=context.workspace.cabab, opakab=context.workspace.opakab,
                    rccemis=context.workspace.rccemis, opakc=context.workspace.opakc, opakcont=context.workspace.opakcont,
                    fline=np.zeros_like(context.workspace.rcem), flinel=np.zeros_like(context.workspace.opakc),
                    epi_eV=epi,
                )
                _add_spectral_metrics(summary, metrics, phase="emisab", status="product")
        except Exception as exc:
            if native_product:
                _apply_python_fallback(native_contributions)
            _add_spectral_metrics(summary, {}, phase="emisab", status="fallback", mismatch={"phase": "emisab", "error": str(exc)})
            if _env_true("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP_STRICT"):
                raise

    return CalcEmisabResult(
        hydrogen_density_cm3=xpx,
        electron_density_cm3=xnx,
        neutral_h_density_cm3=xh0,
        ionized_h_density_cm3=xh1,
        element_traces=tuple(element_traces),
        record_traces=tuple(record_traces),
        leveltemp_workspace=leveltemp,
        workspace=context.workspace,
    )


def apply_calc_emisab_all_to_state(state: XSTARPythonState) -> CalcEmisabResult:
    """Execute the translated routine using explicit state-owned context."""
    context = state.control.get("calc_emisab_context")
    if not isinstance(context, CalcEmisabContext):
        raise CalcEmisabPortError("state.control['calc_emisab_context'] must be CalcEmisabContext")
    result = calc_emisab_all(context)
    state.plasma.xpx = result.hydrogen_density_cm3
    state.plasma.electron_density = result.electron_density_cm3
    state.local_zone.source_arrays["calc_emisab_all"] = result
    state.local_zone.provenance["calc_emisab_all"] = {
        "source_file": result.source_file,
        "n_elements": len(result.element_traces),
        "n_records": len(result.record_traces),
    }
    return result


def register_calc_emisab_all_source_routine(driver: XSTARPythonDriver) -> None:
    driver.register_source_routine(XSTARSourceRoutine.CALC_EMISAB_ALL, apply_calc_emisab_all_to_state)


# ---------------------------------------------------------------------------
# Bounded source-order validation.  This independent synthetic model exercises
# all four rate-type branches and the compact alias / inactive-ion offset
# semantics without requiring a production ATDB installation.

class _SyntheticHeader:
    def __init__(self, data_type: int, rate_type: int):
        self.data_type = data_type
        self.rate_type = rate_type


class _SyntheticMaster:
    def __init__(self) -> None:
        self._ints = {
            1: np.asarray([8, 0, 8]),
            2: np.asarray([1, 8, 1]),
            3: np.asarray([2, 8, 2]),
            10: np.asarray([1, 2]),
            11: np.asarray([1, 2]),
            12: np.asarray([0, 0, 1, 0, 1, 0]),
            13: np.asarray([0, 1, 2, 0]),
            14: np.asarray([0, 1, 2, 0]),
            20: np.asarray([1, 0, 0, 1, 0]),
            21: np.asarray([2, 0, 1, 2, 0]),
            22: np.asarray([0, 0, 0, 3, 0]),
            23: np.asarray([1, 0, 0, 1, 0]),
            24: np.asarray([2, 0, 1, 2, 0]),
            25: np.asarray([0, 0, 0, 3, 0]),
        }
        self._headers = {
            1: _SyntheticHeader(13, 11), 2: _SyntheticHeader(14, 12), 3: _SyntheticHeader(14, 12),
            10: _SyntheticHeader(50, 4), 11: _SyntheticHeader(11, 9),
            12: _SyntheticHeader(53, 7), 13: _SyntheticHeader(71, 14),
            14: _SyntheticHeader(74, 7),
            20: _SyntheticHeader(6, 13), 21: _SyntheticHeader(6, 13), 22: _SyntheticHeader(6, 13),
            23: _SyntheticHeader(6, 13), 24: _SyntheticHeader(6, 13), 25: _SyntheticHeader(6, 13),
        }
        self._reals = {
            20: np.asarray([0.0, 1.0, 0.0, 10.0]),
            21: np.asarray([10.0, 3.0, 0.0, 20.0]),
            22: np.asarray([20.0, 1.0, 0.0, 20.0]),
            23: np.asarray([0.0, 1.0, 0.0, 10.0]),
            24: np.asarray([8.0, 3.0, 0.0, 15.0]),
            25: np.asarray([15.0, 1.0, 0.0, 15.0]),
        }

    def header(self, rec: int) -> _SyntheticHeader:
        return self._headers[int(rec)]

    def record_integers(self, rec: int) -> np.ndarray:
        return self._ints.get(int(rec), np.asarray([], dtype=int))

    def record_reals(self, rec: int) -> np.ndarray:
        return self._reals.get(int(rec), np.asarray([], dtype=float))

    def record_chars(self, rec: int) -> bytes:
        return b"synthetic"


class _SyntheticDerived:
    def __init__(self) -> None:
        self.nlsvn = 1
        self.ncsvn = 2
        self.max_rate_type = 14
        self.npfirst = np.zeros(15, dtype=int); self.npfirst[11] = 1; self.npfirst[12] = 2
        self.npar = np.zeros(30, dtype=int)
        self.npnxt = np.zeros(30, dtype=int)
        self.npnxt[2] = 3
        self.npar[2] = self.npar[3] = 1
        for rec in (10, 11, 12, 13): self.npar[rec] = 2
        self.npar[14] = 3
        self.npnxt[10] = 0; self.npnxt[11] = 0; self.npnxt[12] = 0; self.npnxt[13] = 0; self.npnxt[14] = 0
        for rec in (20, 21, 22): self.npar[rec] = 2
        for rec in (23, 24, 25): self.npar[rec] = 3
        self.npnxt[20] = 21; self.npnxt[21] = 22
        self.npnxt[23] = 24; self.npnxt[24] = 25
        self.npfi = np.zeros((15, 3), dtype=int)
        self.npfi[4,1]=10; self.npfi[7,1]=12; self.npfi[9,1]=11; self.npfi[13,1]=20; self.npfi[14,1]=13
        self.npfi[7,2]=14; self.npfi[13,2]=23
        self.nplini = np.zeros(30, dtype=int); self.nplini[10]=1; self.nplini[11]=1
        self.npconi2 = np.zeros(30, dtype=int); self.npconi2[12]=1; self.npconi2[14]=2
        self.nlevs = np.asarray([0,3,3], dtype=int)
        self.ion_records = np.asarray([0,2,3], dtype=int)
        self.npilev = np.zeros((4,3), dtype=int)
        self.npilev[1:4,1]=[1,2,3]
        self.npilev[1:4,2]=[3,4,5]


def _synthetic_ucalc(record: int, context: UCalcContext) -> UCalcResult:
    data = {
        10: (-4.0, 0.0, 0.25, {}),
        11: (-9.0, 0.0, 0.75, {}),
        12: (-6.0, -2.0, 0.125, {
            "opakc_cm^-1": [1.0, 2.0, 3.0, 4.0],
            "opakcont_cm^-1": [0.5, 1.0, 1.5, 2.0],
            "rccemis_inward": [0.1, 0.2, 0.3, 0.4],
            "rccemis_outward": [0.4, 0.3, 0.2, 0.1],
        }),
        13: (-8.0, 0.0, 0.0, {}),
        14: (-7.0, -3.0, 0.2, {}),
    }
    ans3, ans4, opak, diag = data[int(record)]
    return UCalcResult(
        record=int(record), data_type={10:50,11:11,12:53,13:71,14:74}[int(record)],
        rate_type={10:4,11:9,12:7,13:14,14:7}[int(record)],
        status=UCalcStatus.EVALUATED, ans3=ans3, ans4=ans4, opakab=opak,
        diagnostics=diag,
    )


def run_source_order_validation(*, rtol: float = 2.0e-14, atol: float = 1.0e-30) -> Mapping[str, Any]:
    master = _SyntheticMaster()
    derived = _SyntheticDerived()
    radiation = SimpleNamespace(
        epim=np.asarray([1.0, 2.0, 4.0, 8.0]),
        bremsam=np.asarray([10.0, 8.0, 4.0, 1.0]),
        bremsint=np.asarray([20.0, 10.0, 3.0, 0.0]),
    )
    workspace = CalcEmisabWorkspace.allocate(n_lines=1, n_continua=2, n_energy=4, continuum_fill=7.0)
    context = CalcEmisabContext(
        master=master, derived=derived,
        temperature_1e4K=2.0, electron_fraction_xee=1.2,
        hydrogen_density_cm3=99.0, pressure_dyn_cm2=2.0 * XSTAR_CALC_EMISAB_PRESSURE_COEFFICIENT * 5.0,
        density_control_lcdd=0,
        abundances_by_z={1:1.0,8:0.5}, min_ion_stage_by_z={8:1}, max_ion_stage_by_z={8:1},
        xilevg=np.asarray([0.0,0.2,0.1,0.7,0.3,0.1]),
        bilevg=np.ones(6), rnisg=np.ones(6), radiation=radiation, workspace=workspace,
        escape=EscapeProbabilityContext(
            line_tau_in=np.asarray([0.0]), line_tau_out=np.asarray([0.0]),
            continuum_tau_in=np.asarray([0.0,0.0]), continuum_tau_out=np.asarray([0.0,0.0]),
        ),
        covering_fraction=0.25, ucalc_evaluator=_synthetic_ucalc,
    )
    before_continuum = {
        "brcems": workspace.brcems.copy(), "rccemis": workspace.rccemis.copy(),
        "opakc": workspace.opakc.copy(), "opakcont": workspace.opakcont.copy(),
    }
    result = calc_emisab_all(context)
    elem = next(e for e in result.element_traces if e.element_z == 8)
    compact_expected = np.asarray([0.2,0.1,0.7,0.3,0.1])
    compact_ready = bool(np.allclose(elem.compact_xileve, compact_expected, rtol=0.0, atol=0.0))
    inactive = elem.ion_traces[1]
    inactive_ready = bool((not inactive.active) and inactive.compact_offset == 2)
    roles = {t.output_role: t for t in result.record_traces}
    line = roles["bound_bound_rate_type_4"]
    bf = roles["bound_free_rate_type_7"]
    rt9 = roles["rate_type_9_no_direct_output"]
    rt14 = roles["radiative_superlevel_continuum_bin_3"]
    # Independent expected values from the literal source equations.  With
    # tau=0 and cfrac=0.25, ptmp1=0.75 and ptmp2=1.25.
    p1, p2 = 0.75, 1.25
    xpx = 5.0
    abund_lo = 0.2*xpx*0.5
    abund_up = 0.1*xpx*0.5
    line_expected = np.asarray([-abund_up*(-4.0)*p1/(p1+p2), -abund_up*(-4.0)*p2/(p1+p2)])
    line_ready = bool(np.allclose(workspace.rcem[:,1], line_expected, rtol=rtol, atol=atol) and math.isclose(workspace.oplin[1],0.25*abund_lo,rel_tol=rtol,abs_tol=atol))
    bf_abund1, bf_abund2 = 0.2*0.5, 0.7*0.5
    bf_expected = np.asarray([p1*6.0/(p1+p2)*bf_abund2*xpx, p2*6.0/(p1+p2)*bf_abund2*xpx])
    bf_ready = bool(np.allclose(workspace.cemab[:,1],bf_expected,rtol=rtol,atol=atol) and math.isclose(workspace.cabab[1],2.0*bf_abund1*xpx,rel_tol=rtol,abs_tol=atol))
    rt9_ready = bool(rt9.output_index == 1 and len([t for t in result.record_traces if t.rate_type == 9]) == 1)
    rt14_expected_increment = (0.1*xpx*0.5)*8.0/(8.0-4.0+float(np.float32(1e-24)))/XSTAR_CALC_EMISAB_ERG_PER_EV/XSTAR_CALC_EMISAB_FOUR_PI
    rt14_ready = bool(math.isclose(workspace.rccemis[1,2], 7.0+0.2+rt14_expected_increment, rel_tol=rtol, abs_tol=atol))
    reset_ready = bool(np.count_nonzero(workspace.cemab[:,2]) == 0 and workspace.cabab[2] == 0.0 and workspace.opakab[2] == 0.0)
    carried_ready = bool(
        np.array_equal(workspace.brcems, before_continuum["brcems"])
        and np.allclose(workspace.opakc, before_continuum["opakc"] + np.asarray([1,2,3,4]))
        and np.allclose(workspace.opakcont, before_continuum["opakcont"] + np.asarray([.5,1,1.5,2]))
    )
    summary = {
        "port_version": "v0.4.61",
        "calc_emisab_all_translated": True,
        "calc_emisab_element_translated": True,
        "calc_emisab_ion_translated": True,
        "density_branch_lcdd0_ready": math.isclose(result.hydrogen_density_cm3, 5.0, rel_tol=0.0, abs_tol=0.0),
        "full_output_reset_semantics_ready": reset_ready,
        "carried_continuum_workspace_ready": carried_ready,
        "shared_continuum_alias_mapping_ready": compact_ready,
        "inactive_ion_offset_ready": inactive_ready,
        "rate_type_4_ready": line_ready,
        "rate_type_7_ready": bf_ready,
        "rate_type_9_no_output_ready": rt9_ready,
        "rate_type_14_ready": rt14_ready,
        "ucalc_continuum_side_effects_ready": carried_ready,
        "record_source_order": [t.record for t in result.record_traces],
    }
    summary["calc_emisab_all_source_acceptance_ready"] = bool(all(
        value for key, value in summary.items() if key.endswith("_ready")
    ))
    summary["next_source_target"] = "calc_emis_all"
    return summary


def write_calc_emisab_validation_products(summary: Mapping[str, Any], out_dir: str | Path) -> Mapping[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    json_path = out / "xstar_calc_emisab_all_source_validation_summary.json"
    md_path = out / "xstar_calc_emisab_all_source_validation_summary.md"
    json_path.write_text(json.dumps(dict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "# XSTAR `calc_emisab_all` source validation\n\n"
        + "\n".join(f"- {k}: `{v}`" for k, v in summary.items()) + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "CalcEmisabPortError", "CalcEmisabWorkspace", "CalcEmisabContext",
    "CalcEmisabRecordTrace", "CalcEmisabIonTrace", "CalcEmisabElementTrace", "CalcEmisabResult",
    "resolve_calc_emisab_density", "calc_emisab_ion", "calc_emisab_element", "calc_emisab_all",
    "apply_calc_emisab_all_to_state", "register_calc_emisab_all_source_routine",
    "run_source_order_validation", "write_calc_emisab_validation_products",
]
