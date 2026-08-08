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
        "schema_version": "0.6.48.3",
        "emisab_calls": 0, "emis_calls": 0,
        "contributions_attempted": 0, "contributions_committed": 0,
        "emissivity_contributions": 0, "opacity_contributions": 0,
        "line_profiles": 0, "source_order_violations": 0,
        "shadow_compared": 0, "shadow_mismatches": 0,
        "shadow_policy": "exact_temporary_grid_oracle",
        "exact_profile_oracle_calls": 0,
        "exact_profile_oracle_values": 0,
        "exact_profile_oracle_line_profiles": 0,
        "exact_grid_oracle_calls": 0,
        "exact_grid_oracle_energy_values": 0,
        "exact_grid_oracle_opacity_values": 0,
        "strict_source_rounding": False,
        "source_hunt_floor": 0.0,
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


def _add_spectral_metrics(summary: MutableMapping[str, Any], metrics: Mapping[str, Any], *, phase: str, status: str, mismatch: Optional[Mapping[str, Any]] = None) -> None:
    summary[f"{phase}_calls"] = int(summary.get(f"{phase}_calls", 0)) + 1
    for key in (
        "contributions_attempted", "contributions_committed", "emissivity_contributions",
        "opacity_contributions", "line_profiles", "source_order_violations",
        "exact_profile_oracle_calls", "exact_profile_oracle_values",
        "exact_profile_oracle_line_profiles", "exact_grid_oracle_calls",
        "exact_grid_oracle_energy_values", "exact_grid_oracle_opacity_values",
    ):
        summary[key] = int(summary.get(key, 0)) + int(metrics.get(key, 0) or 0)
    for key in ("packing_seconds", "ffi_seconds", "construction_seconds", "opacity_seconds", "commit_seconds"):
        summary[key] = float(summary.get(key, 0.0)) + float(metrics.get(key, 0.0) or 0.0)
    if "strict_source_rounding" in metrics:
        summary["strict_source_rounding"] = bool(metrics.get("strict_source_rounding"))
    if "source_hunt_floor" in metrics:
        summary["source_hunt_floor"] = float(metrics.get("source_hunt_floor", 0.0) or 0.0)
    if status == "product":
        summary["product_commits"] = int(summary.get("product_commits", 0)) + 1
    elif status in {"shadow_match", "shadow_mismatch"}:
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
    # Literal xstarcalc passes the reduced epim/bremsam workspace to
    # calc_emisab_all.  calc_emis_all uses the full epi/bremsa workspace.
    # Shared UCalc helpers need this explicit role because the radiation state
    # carries both grids.
    ucalc_radiation_grid_role: str = "reduced"

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


def _next_ion_parent_destination_context(
    context: CalcEmisabContext, ion: _IonDescriptor
) -> tuple[dict[int, float], dict[int, float]]:
    """Build literal next-ion Type-13 parent maps for bound-free UCalc.

    Type 53 consumes both the parent excitation energy and statistical weight;
    Type 49 keeps its own physical threshold but consumes the excited-parent
    statistical weight in the Milne/recombination branch.  A shared source
    map therefore keeps both families on the same literal next-ion topology.

    ``ucalc.f90`` label 53 corrects an excited-parent threshold by walking the
    next ion's Type-13 level table and adding ``rdat1(np1r2)`` for local level
    ``idest2-nlevp+1``.  The old calc_emis/calc_emisab Python context omitted
    these maps, causing ``SourceFaithfulUCalc._parent_destination_context`` to
    fall back to the *current-ion continuum energy*.  For Mg VIII record 43025
    that changed the source threshold from 283.4485 eV to 531.5909 eV and
    displaced hundreds of Type-53 opacity bins.
    """
    derived = context.derived
    element_z = int(ion.element_z)
    target_stage = int(ion.ion_stage) + 1
    parent_ion_index = 0
    for candidate in range(1, int(derived.n_ions) + 1):
        if (int(derived.ion_element_z[candidate]) == element_z and
                int(derived.ion_stage[candidate]) == target_stage):
            parent_ion_index = candidate
            break
    energy: dict[int, float] = {}
    weight: dict[int, float] = {}
    if parent_ion_index > 0:
        parent_levels = build_level_table(context.master, derived, parent_ion_index)
        for parent_local in range(2, int(parent_levels.nlev) + 1):
            destination = int(ion.nlev) + parent_local - 1
            level = parent_levels.require(parent_local)
            energy[destination] = float(level.energy_ev)
            weight[destination] = float(level.statistical_weight)
    return energy, weight


# Backward diagnostic/readiness name retained from patch 5.20.9.2.  The
# implementation is now named for its actual shared Type49/Type53 role.
_type53_parent_destination_context = _next_ion_parent_destination_context


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
    parent_energy, parent_weight = _next_ion_parent_destination_context(context, ion)
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
            "parent_level_energy_ev_by_destination": parent_energy,
            "parent_level_stat_weight_by_destination": parent_weight,
            "type53_parent_context_source": "literal_next_ion_type13",
            "bound_free_radiation_grid_role": str(context.ucalc_radiation_grid_role),
            "emit_ucalc_continuum_side_effects": True,
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
    visited_type7_records: Optional[set[int]] = None,
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
                if visited_type7_records is not None:
                    visited_type7_records.add(int(rec))
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
                    _update_source_detail_rrc_type7_final_slot_v064812345339(
                        context.profile_control, source_record=rec, continuum_index=continuum_index,
                        data_type=header.data_type, ptmp1=ptmp1, ptmp2=ptmp2,
                        abund1=abund1, abund2=abund2, xpx=xpx, ans3=result.ans3,
                        ans4=result.ans4, opakab=result.opakab,
                    )
                    _update_source_detail_rrc_slot_absorption_lifetime_v06481234532(
                        context.profile_control, source_record=rec, continuum_index=continuum_index,
                        abund1=abund1, abund2=abund2, xpx=xpx, ans4=result.ans4,
                    )
                    _update_source_detail_rrc_record_shadow_v0648123453(
                        context.profile_control, source_record=rec, continuum_index=continuum_index,
                        ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
                        xpx=xpx, ans3=result.ans3, ans4=result.ans4, opakab=result.opakab,
                    )
                    _update_source_detail_rrc_publication_shadow_v0648123451(
                        context.profile_control, continuum_index=continuum_index,
                        ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
                        xpx=xpx, ans3=result.ans3, ans4=result.ans4, opakab=result.opakab,
                    )
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
                    source_line_index = int(context.derived.nplini[rec]) if rec < len(context.derived.nplini) else int(line_index)
                    _update_source_detail_line_publication_shadow_v064812345334(
                        context.profile_control, rate_type=rate_type, data_type=header.data_type,
                        line_index=source_line_index, abundance_lower=abund1,
                        abundance_upper=abund2, opak_local=result.opakab,
                    )
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
    visited_type7_records: Optional[set[int]] = None,
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
                visited_type7_records=visited_type7_records,
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


def _begin_source_detail_line_publication_shadow_v064812345334(
    control: Optional[MutableMapping[str, Any]],
) -> None:
    """Reset the evaluation-local Type-50 stale-opakb1 publication replay."""
    if not isinstance(control, MutableMapping):
        return
    control["source_detail_line_activity_shadow_v064812345334"] = {}
    control["source_detail_line_stale_opakb1_v064812345334"] = 0.0


def _update_source_detail_line_publication_shadow_v064812345334(
    control: Optional[MutableMapping[str, Any]], *, rate_type: int, data_type: int,
    line_index: int, abundance_lower: float, abundance_upper: float,
    opak_local: float,
) -> None:
    """Replay frozen-44 calc_emisab Type-50 stale-opakb1 identity lifetime.

    Called in the actual source record traversal, this tracks the caller-local
    ``opakb1`` carry across rate types 4/9/14.  Active records update the carry;
    only an inactive rate-4 record may expose a detail-line identity.  The map
    is output-only and never mutates rcem/oplin/tau or any physical workspace.
    """
    if not isinstance(control, MutableMapping):
        return
    if int(data_type) != 50 or int(rate_type) not in (4, 9, 14) or int(line_index) <= 0:
        return
    active = (
        float(abundance_lower) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
        or float(abundance_upper) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
    )
    stale = float(control.get("source_detail_line_stale_opakb1_v064812345334", 0.0) or 0.0)
    if active:
        if np.isfinite(float(opak_local)):
            control["source_detail_line_stale_opakb1_v064812345334"] = float(opak_local)
        return
    if int(rate_type) != 4:
        return
    if abs(stale * float(abundance_lower)) <= 1.0e-64:
        return
    shadow = control.setdefault("source_detail_line_activity_shadow_v064812345334", {})
    if not isinstance(shadow, MutableMapping):
        shadow = {}
        control["source_detail_line_activity_shadow_v064812345334"] = shadow
    shadow[int(line_index)] = True


def _update_source_detail_rrc_record_shadow_v0648123453(
    control: Optional[MutableMapping[str, Any]], *, source_record: int,
    continuum_index: int, ptmp1: float, ptmp2: float, abund1: float,
    abund2: float, xpx: float, ans3: float, ans4: float, opakab: float,
) -> None:
    """Retain the last source-active Type-7 write by source record.

    Unlike the 45.1 continuum-slot map, this state cannot be confused with
    another bound-free rate family.  It intentionally survives repeated
    fixed-state/DSEC evaluations until the corresponding ``savd``/``fstepr3``
    shell publication consumes it.  This mirrors the qualified C++ product
    publication lifetime without mutating the physical emissivity workspace.
    """
    if not isinstance(control, MutableMapping):
        return
    rec = int(source_record); ci = int(continuum_index)
    if rec <= 0 or ci <= 0:
        return
    if not (
        float(abund1) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
        or float(abund2) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
    ):
        return
    den = float(ptmp1) + float(ptmp2)
    if den == 0.0:
        return
    shadow = control.setdefault("source_detail_rrc_record_shadow_v0648123453", {})
    if not isinstance(shadow, MutableMapping):
        shadow = {}
        control["source_detail_rrc_record_shadow_v0648123453"] = shadow
    shadow[rec] = {
        "source_record": rec,
        "continuum_index": ci,
        "emis_inward": float(ptmp1) * abs(float(ans3)) / den * float(abund2) * float(xpx),
        "emis_outward": float(ptmp2) * abs(float(ans3)) / den * float(abund2) * float(xpx),
        "integrated_absn": abs(float(ans4)) * float(abund1) * float(xpx),
        "opacity": float(opakab),
    }


def _source_detail_rrc_lifetime_trace_targets_v06481234532() -> set[int]:
    raw = str(os.environ.get("XSTAR_V06481234532_RRC_TARGETS", "709,762"))
    out: set[int] = set()
    for token in raw.replace(";", ",").split(","):
        try:
            value = int(token.strip())
        except Exception:
            continue
        if value > 0:
            out.add(value)
    return out


def _append_source_detail_rrc_lifetime_trace_v06481234532(
    control: Optional[MutableMapping[str, Any]], event: Mapping[str, Any],
) -> None:
    if not isinstance(control, MutableMapping):
        return
    ci = int(event.get("continuum_index", 0) or 0)
    if ci > 0 and ci not in _source_detail_rrc_lifetime_trace_targets_v06481234532():
        return
    trace = control.setdefault("source_detail_rrc_lifetime_trace_v06481234532", [])
    if not isinstance(trace, list):
        trace = []
        control["source_detail_rrc_lifetime_trace_v06481234532"] = trace
    if len(trace) < 20000:
        trace.append(dict(event))


def _begin_source_detail_rrc_evaluation_v06481234532(
    control: Optional[MutableMapping[str, Any]],
) -> int:
    """Advance the shell-local calc_emisab evaluation sequence.

    The sequence is intentionally not reset by ``calc_emisab_all``.  It is
    consumed/reset only after ``savd``/``fstepr3`` materializes a shell, so a
    publication-only compatibility layer can distinguish a retained value from
    an earlier DSEC/fixed-state evaluation from an intermediate write in the
    currently published evaluation.
    """
    if not isinstance(control, MutableMapping):
        return 0
    seq = int(control.get("source_detail_rrc_eval_sequence_v06481234532", 0) or 0) + 1
    control["source_detail_rrc_eval_sequence_v06481234532"] = seq
    _append_source_detail_rrc_lifetime_trace_v06481234532(control, {
        "phase": "calc_emisab_begin", "eval_sequence": seq, "continuum_index": 0,
    })
    return seq


def _update_source_detail_rrc_slot_absorption_lifetime_v06481234532(
    control: Optional[MutableMapping[str, Any]], *, source_record: int,
    continuum_index: int, abund1: float, abund2: float, xpx: float, ans4: float,
) -> None:
    """Retain positive Type-7 absorption by continuum slot across evaluations.

    Frozen-44 C++ retains two Carbon detail identities (709/762) that are not
    literal FORTRAN ``fstepr3`` rows.  They are a cross-mode publication
    compatibility artifact of the retained native source workspace.  The old
    45.1 slot shadow was too broad because it also exposed intermediate writes
    from the *current* evaluation, creating four Ca-only rows.

    This state therefore stores only positive integrated absorption and keeps
    both the latest and preceding evaluation owners.  The writer may consume
    only an entry whose evaluation sequence is strictly older than the one
    being published, and only for a canonical Type-7 identity whose source
    record differs from the retained writer.  No physical workspace is changed.
    """
    if not isinstance(control, MutableMapping):
        return
    rec = int(source_record); ci = int(continuum_index)
    if rec <= 0 or ci <= 0:
        return
    if not (
        float(abund1) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
        or float(abund2) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
    ):
        return
    absorption = abs(float(ans4)) * float(abund1) * float(xpx)
    activity_floor = float(np.float32(1.0e-36))
    if not np.isfinite(absorption) or not (absorption > activity_floor):
        return
    seq = int(control.get("source_detail_rrc_eval_sequence_v06481234532", 0) or 0)
    if seq <= 0:
        seq = _begin_source_detail_rrc_evaluation_v06481234532(control)
    history = control.setdefault("source_detail_rrc_slot_absorption_lifetime_v06481234532", {})
    if not isinstance(history, MutableMapping):
        history = {}
        control["source_detail_rrc_slot_absorption_lifetime_v06481234532"] = history
    slot = history.get(ci)
    if not isinstance(slot, MutableMapping):
        slot = {"latest": None, "previous": None}
        history[ci] = slot
    latest = slot.get("latest")
    if isinstance(latest, Mapping) and int(latest.get("eval_sequence", 0) or 0) != seq:
        slot["previous"] = dict(latest)
    entry = {
        "eval_sequence": seq,
        "source_record": rec,
        "continuum_index": ci,
        "integrated_absn": float(absorption),
        "abundance_lower": float(abund1),
        "abundance_upper": float(abund2),
    }
    slot["latest"] = entry
    _append_source_detail_rrc_lifetime_trace_v06481234532(control, {
        "phase": "type7_absorption_update", **entry,
    })


def _update_source_detail_rrc_type7_final_slot_v064812345339(
    control: Optional[MutableMapping[str, Any]], *, source_record: int,
    continuum_index: int, data_type: int, ptmp1: float, ptmp2: float,
    abund1: float, abund2: float, xpx: float, ans3: float, ans4: float,
    opakab: float,
) -> None:
    """Retain the final source-order rate-7 continuum-slot write.

    Frozen standalone C++ owns generic ``xo01_detal3`` membership from the
    final one-based local ``cemab/cabab/opakab`` continuum slot.  The writer
    does not require the record that last wrote that slot to be the canonical
    ``npcon`` owner.  Conversely, a later source-order zero write must erase an
    earlier positive write.

    Python's older record-keyed shadows cannot represent either rule.  This
    output-only slot state is therefore updated for *every* visited rate-7
    record, including zero/inactive writes.  It never mutates the
    physical emissivity workspace and is reset at the beginning of every
    ``calc_emisab_all`` evaluation.
    """
    if not isinstance(control, MutableMapping):
        return
    rec = int(source_record); ci = int(continuum_index); dt = int(data_type)
    if rec <= 0 or ci <= 0:
        return
    den = float(ptmp1) + float(ptmp2)
    if den == 0.0:
        emis_in = emis_out = 0.0
    else:
        common = abs(float(ans3)) / den * float(abund2) * float(xpx)
        emis_in = float(ptmp1) * common
        emis_out = float(ptmp2) * common
    absorption = abs(float(ans4)) * float(abund1) * float(xpx)
    values = (float(emis_in), float(emis_out), float(absorption), float(opakab))
    activity_floor = float(np.float32(1.0e-36))
    active = any(np.isfinite(v) and v > activity_floor for v in values)
    slots = control.setdefault('source_detail_rrc_type7_final_slot_v064812345339', {})
    if not isinstance(slots, MutableMapping):
        slots = {}
        control['source_detail_rrc_type7_final_slot_v064812345339'] = slots
    slots[ci] = {
        'continuum_index': ci,
        'source_record': rec,
        'rate_type': 7,
        'data_type': dt,
        'emis_inward': values[0],
        'emis_outward': values[1],
        'integrated_absn': values[2],
        'opacity': values[3],
        'active': bool(active),
        'abundance_lower': float(abund1),
        'abundance_upper': float(abund2),
        'endpoint_active': bool(
            float(abund1) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
            or float(abund2) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
        ),
        'eval_sequence': int(control.get('source_detail_rrc_eval_sequence_v06481234532', 0) or 0),
        'publication_owner': 'source_type7_final_slot_v064812345339',
    }


def _update_source_detail_rrc_publication_shadow_v0648123451(
    control: Optional[MutableMapping[str, Any]], *, continuum_index: int,
    ptmp1: float, ptmp2: float, abund1: float, abund2: float, xpx: float,
    ans3: float, ans4: float, opakab: float,
) -> None:
    """Legacy 45.1 same-evaluation slot shadow (diagnostic only).

    Later attribution showed that literal FORTRAN ``calc_emisab_ion`` does
    overwrite cemab/cabab after a skipped Type-7 UCalc, so this map must not
    own ``fstepr3`` membership.  It is retained only for backward diagnostics
    and is reset at every ``calc_emisab_all`` entry.  45.3.2 uses a separate
    prior-evaluation absorption lifetime for frozen-C++ cross-mode parity.
    """
    if not isinstance(control, MutableMapping) or int(continuum_index) <= 0:
        return
    if not (
        float(abund1) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
        or float(abund2) > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR
    ):
        return
    den = float(ptmp1) + float(ptmp2)
    if den == 0.0:
        return
    shadow = control.setdefault(
        "source_detail_rrc_publication_shadow_v0648123451", {}
    )
    if not isinstance(shadow, MutableMapping):
        shadow = {}
        control["source_detail_rrc_publication_shadow_v0648123451"] = shadow
    shadow[int(continuum_index)] = {
        "emis_inward": float(ptmp1) * abs(float(ans3)) / den * float(abund2) * float(xpx),
        "emis_outward": float(ptmp2) * abs(float(ans3)) / den * float(abund2) * float(xpx),
        "integrated_absn": abs(float(ans4)) * float(abund1) * float(xpx),
        "opacity": float(opakab),
    }


def _append_source_detail_rrc_orphan_trace_v06481234533(
    control: Optional[MutableMapping[str, Any]], event: Mapping[str, Any],
) -> None:
    if not isinstance(control, MutableMapping):
        return
    trace = control.setdefault("source_detail_rrc_orphan_trace_v06481234533", [])
    if not isinstance(trace, list):
        trace = []
        control["source_detail_rrc_orphan_trace_v06481234533"] = trace
    if len(trace) < 20000:
        trace.append(dict(event))


def _evaluate_canonical_npcon_orphan_type7_absorption_v06481234533(
    context: CalcEmisabContext, *, visited_type7_records: set[int],
    xpx: float, xh0: float, xh1: float,
) -> None:
    """Evaluate publication-only absorption for canonical Type-7 runtime orphans.

    A runtime orphan is a canonical ``npcon`` Type-7 record that was not
    visited by the active ``npfi(7,ion)`` source traversal in this
    ``calc_emisab_all`` evaluation.  The evaluator reuses the already selected
    UCalc implementation, but commits *only* ``abs(ans4)*abund1*n_H`` to an
    output-only map.  It never mutates cemab/cabab/opakab or continuum side
    effects.
    """
    control = context.profile_control
    if not isinstance(control, MutableMapping):
        return
    orphan_map: dict[int, dict[str, Any]] = {}
    canonical: list[tuple[int,int]] = []
    npcon = np.asarray(getattr(context.derived, "npcon", ()), dtype=np.int64).reshape(-1)
    limit = min(int(context.derived.ncsvn) + 1, int(npcon.size))
    for ci in range(1, limit):
        rec = int(npcon[ci])
        if rec <= 0:
            continue
        try:
            hdr = context.master.header(rec)
        except Exception:
            continue
        if int(getattr(hdr, "rate_type", 0)) == 7:
            canonical.append((ci, rec))
    orphans = [(ci, rec) for ci, rec in canonical if rec not in visited_type7_records]
    if not canonical:
        control["source_detail_rrc_orphan_absorption_v06481234533"] = {}
        control["source_detail_rrc_orphan_summary_v06481234533"] = {
            "canonical_type7_count": 0, "visited_type7_count": len(set(visited_type7_records)),
            "orphan_type7_count": 0, "orphan_active_absorption_count": 0,
            "orphan_709_present": False, "orphan_762_present": False,
            "orphan_709_absorption": 0.0, "orphan_762_absorption": 0.0,
        }
        return
    ion_record_to_index = {
        int(context.derived.ion_records[ii]): ii
        for ii in range(1, min(int(context.derived.n_ions) + 1, len(context.derived.ion_records)))
        if int(context.derived.ion_records[ii]) > 0
    }
    element_cache: dict[int, tuple[list[_IonDescriptor], np.ndarray, dict[int,int]]] = {}
    active_count = 0
    activity_floor = float(np.float32(1.0e-36))
    for ci, rec in orphans:
        parent_ion_record = int(context.derived.npar[rec]) if rec < len(context.derived.npar) else 0
        ion_index = int(ion_record_to_index.get(parent_ion_record, 0))
        event: dict[str, Any] = {
            "phase": "orphan_type7_evaluation", "continuum_index": int(ci),
            "source_record": int(rec), "parent_ion_record": parent_ion_record,
            "visited": False, "status": "unresolved",
        }
        if ion_index <= 0:
            _append_source_detail_rrc_orphan_trace_v06481234533(control, event); continue
        z = int(context.derived.ion_element_z[ion_index])
        stage = int(context.derived.ion_stage[ion_index])
        event.update(element_z=z, ion_stage=stage, runtime_stage_active=bool(context.min_stage(z) <= stage <= context.max_stage(z)))
        elem_ab = float(context.abundance(z))
        if not (elem_ab > XSTAR_CALC_EMISAB_ABUNDANCE_FLOOR):
            event["status"] = "element_below_floor"; _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
        element_record = int(context.derived.npar[parent_ion_record]) if 0 < parent_ion_record < len(context.derived.npar) else 0
        if element_record not in element_cache:
            ions = _iter_ion_descriptors(context, element_record, z)
            compact_x, _, _ = _compact_element_populations(context, ions)
            offsets: dict[int,int] = {}
            off = 0
            for ion in ions:
                offsets[int(ion.ion_index)] = off
                off += int(ion.nlev) - 1
            element_cache[element_record] = (ions, compact_x, offsets)
        ions, compact_x, offsets = element_cache[element_record]
        ion = next((x for x in ions if int(x.ion_index) == ion_index), None)
        if ion is None:
            event["status"] = "ion_not_in_element_chain"; _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
        ints = context.master.record_integers(rec)
        if len(ints) < 4:
            event["status"] = "short_record"; _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
        idest1 = int(ints[-2]); idest2 = int(ion.nlev) + int(ints[-4]) - 1
        off = int(offsets.get(ion_index, 0)); lower = idest1 + off; upper = idest2 + off
        if lower <= 0 or upper <= 0 or lower >= compact_x.size or upper >= compact_x.size:
            event.update(status="compact_index_out_of_range", idest1=idest1, idest2=idest2, compact_offset=off); _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
        abund1 = float(compact_x[lower]) * elem_ab; abund2 = float(compact_x[upper]) * elem_ab
        event.update(idest1=idest1, idest2=idest2, compact_offset=off, abundance_lower=abund1, abundance_upper=abund2)
        if not (abund1 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR or abund2 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR):
            event["status"] = "endpoints_below_floor"; _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
        tau1, tau2 = context.escape.continuum_taus(ci)
        if tau1 is None or tau2 is None:
            if not context.escape.allow_missing_as_zero:
                event["status"] = "missing_tau"; _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
            tau1 = 0.0 if tau1 is None else tau1; tau2 = 0.0 if tau2 is None else tau2
        ptmp1 = pescv(tau1) * (1.0 - context.covering_fraction)
        ptmp2 = pescv(tau2) * (1.0 - context.covering_fraction) + 2.0 * pescv(tau1 + tau2) * context.covering_fraction
        current_levels = build_level_table(context.master, context.derived, ion_index)
        leveltemp = _copy_or_initialize_leveltemp(context.initial_leveltemp_workspace)
        _overwrite_leveltemp(leveltemp, current_levels)
        levels = UCalcLevelTable(levels=dict(leveltemp.levels), nlev=int(ion.nlev))
        try:
            result = _evaluate_ucalc(context, rec, _ucalc_context(
                context, ion=ion, levels=levels, xpx=xpx, xh0=xh0, xh1=xh1,
                ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
            ))
        except Exception as exc:
            event.update(status="ucalc_error", error=str(exc)); _append_source_detail_rrc_orphan_trace_v06481234533(control,event); continue
        absorption = abs(float(result.ans4)) * abund1 * float(xpx)
        event.update(status=str(result.status.value), ans4=float(result.ans4), integrated_absn=float(absorption))
        if result.ready and np.isfinite(absorption) and absorption > activity_floor:
            orphan_map[int(ci)] = {
                "continuum_index": int(ci), "source_record": int(rec),
                "parent_ion_record": parent_ion_record, "ion_index": ion_index,
                "element_z": z, "ion_stage": stage, "integrated_absn": float(absorption),
                "runtime_stage_active": bool(context.min_stage(z) <= stage <= context.max_stage(z)),
            }
            active_count += 1
        _append_source_detail_rrc_orphan_trace_v06481234533(control,event)
    control["source_detail_rrc_orphan_absorption_v06481234533"] = orphan_map
    control["source_detail_rrc_orphan_summary_v06481234533"] = {
        "canonical_type7_count": len(canonical),
        "visited_type7_count": len(set(visited_type7_records)),
        "orphan_type7_count": len(orphans),
        "orphan_active_absorption_count": active_count,
        "orphan_709_present": 709 in orphan_map,
        "orphan_762_present": 762 in orphan_map,
        "orphan_709_absorption": float(orphan_map.get(709, {}).get("integrated_absn", 0.0)),
        "orphan_762_absorption": float(orphan_map.get(762, {}).get("integrated_absn", 0.0)),
    }
    _append_source_detail_rrc_orphan_trace_v06481234533(control, {
        "phase": "orphan_type7_summary", **control["source_detail_rrc_orphan_summary_v06481234533"]
    })


def _evaluate_canonical_npcon_non_type7_detail3_absorption_v064812345335(
    context: CalcEmisabContext, *, xpx: float, xh0: float, xh1: float,
) -> None:
    """Produce output-only detail3 absorption for canonical rate-1 Type49/53 rows.

    Frozen-44 generic ``xo01_detal3`` ownership is broader than the executable
    rate-type-7 ``npfi`` chain: canonical ``npcon/npconi2`` also contains
    rate-type-1 bound-free identities.  Python's physical calc_emisab workspace
    intentionally remains source-faithful to the rate-7 writer, so evaluate the
    missing canonical rate-1 Type49/53 records here and retain *only*
    ``abs(ans4)*abund1*n_H`` in an output-publication map.  No physical
    cemab/cabab/opakab or continuum side-effect array is mutated.
    """
    control = context.profile_control
    if not isinstance(control, MutableMapping):
        return
    published: dict[int, dict[str, Any]] = {}
    npcon = np.asarray(getattr(context.derived, "npcon", ()), dtype=np.int64).reshape(-1)
    limit = min(int(context.derived.ncsvn) + 1, int(npcon.size))
    candidates: list[tuple[int, int]] = []
    for ci in range(1, limit):
        rec = int(npcon[ci])
        if rec <= 0:
            continue
        try:
            hdr = context.master.header(rec)
        except Exception:
            continue
        if int(getattr(hdr, "rate_type", 0)) == 1 and int(getattr(hdr, "data_type", 0)) in (49, 53):
            # Require literal canonical continuum ownership, not merely npcon
            # array occupancy in a malformed fixture.
            npconi2 = getattr(context.derived, "npconi2", ())
            if rec < len(npconi2) and int(npconi2[rec]) == ci:
                candidates.append((ci, rec))
    if not candidates:
        control["source_detail_rrc_non_type7_absorption_v064812345335"] = {}
        control["source_detail_rrc_non_type7_summary_v064812345335"] = {
            "candidate_count": 0, "active_absorption_count": 0,
            "continuum_709_present": False, "continuum_762_present": False,
        }
        return

    ion_record_to_index = {
        int(context.derived.ion_records[ii]): ii
        for ii in range(1, min(int(getattr(context.derived, "n_ions", 0)) + 1, len(context.derived.ion_records)))
        if int(context.derived.ion_records[ii]) > 0
    }
    element_cache: dict[int, tuple[list[_IonDescriptor], np.ndarray, dict[int, int]]] = {}
    activity_floor = float(np.float32(1.0e-36))
    for ci, rec in candidates:
        parent_ion_record = int(context.derived.npar[rec]) if rec < len(context.derived.npar) else 0
        ion_index = int(ion_record_to_index.get(parent_ion_record, 0))
        if ion_index <= 0:
            continue
        z = int(context.derived.ion_element_z[ion_index])
        stage = int(context.derived.ion_stage[ion_index])
        elem_ab = float(context.abundance(z))
        if not (elem_ab > XSTAR_CALC_EMISAB_ABUNDANCE_FLOOR):
            continue
        element_record = int(context.derived.npar[parent_ion_record]) if 0 < parent_ion_record < len(context.derived.npar) else 0
        if element_record not in element_cache:
            ions = _iter_ion_descriptors(context, element_record, z)
            compact_x, _, _ = _compact_element_populations(context, ions)
            offsets: dict[int, int] = {}
            off = 0
            for ion in ions:
                offsets[int(ion.ion_index)] = off
                off += int(ion.nlev) - 1
            element_cache[element_record] = (ions, compact_x, offsets)
        ions, compact_x, offsets = element_cache[element_record]
        ion = next((x for x in ions if int(x.ion_index) == ion_index), None)
        if ion is None:
            continue
        ints = context.master.record_integers(rec)
        if len(ints) < 4:
            continue
        idest1 = int(ints[-2])
        idest2 = int(ion.nlev) + int(ints[-4]) - 1
        off = int(offsets.get(ion_index, 0))
        lower = idest1 + off
        upper = idest2 + off
        if lower <= 0 or upper <= 0 or lower >= compact_x.size or upper >= compact_x.size:
            continue
        abund1 = float(compact_x[lower]) * elem_ab
        abund2 = float(compact_x[upper]) * elem_ab
        if not (abund1 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR or abund2 > XSTAR_CALC_EMISAB_LEVEL_ABUNDANCE_FLOOR):
            continue
        tau1, tau2 = context.escape.continuum_taus(ci)
        if tau1 is None or tau2 is None:
            if not context.escape.allow_missing_as_zero:
                continue
            tau1 = 0.0 if tau1 is None else tau1
            tau2 = 0.0 if tau2 is None else tau2
        ptmp1 = pescv(tau1) * (1.0 - context.covering_fraction)
        ptmp2 = pescv(tau2) * (1.0 - context.covering_fraction) + 2.0 * pescv(tau1 + tau2) * context.covering_fraction
        current_levels = build_level_table(context.master, context.derived, ion_index)
        leveltemp = _copy_or_initialize_leveltemp(context.initial_leveltemp_workspace)
        _overwrite_leveltemp(leveltemp, current_levels)
        levels = UCalcLevelTable(levels=dict(leveltemp.levels), nlev=int(ion.nlev))
        try:
            result = _evaluate_ucalc(context, rec, _ucalc_context(
                context, ion=ion, levels=levels, xpx=xpx, xh0=xh0, xh1=xh1,
                ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
            ))
        except Exception:
            continue
        absorption = abs(float(result.ans4)) * abund1 * float(xpx)
        if result.ready and np.isfinite(absorption) and absorption > activity_floor:
            hdr = context.master.header(rec)
            published[int(ci)] = {
                "continuum_index": int(ci), "source_record": int(rec),
                "rate_type": int(hdr.rate_type), "data_type": int(hdr.data_type),
                "parent_ion_record": parent_ion_record, "ion_index": ion_index,
                "element_z": z, "ion_stage": stage,
                "integrated_absn": float(absorption),
                "abundance_lower": float(abund1), "abundance_upper": float(abund2),
                "ans4": float(result.ans4),
            }
    control["source_detail_rrc_non_type7_absorption_v064812345335"] = published
    control["source_detail_rrc_non_type7_summary_v064812345335"] = {
        "candidate_count": len(candidates),
        "active_absorption_count": len(published),
        "continuum_709_present": 709 in published,
        "continuum_762_present": 762 in published,
        "continuum_709_absorption": float(published.get(709, {}).get("integrated_absn", 0.0)),
        "continuum_762_absorption": float(published.get(762, {}).get("integrated_absn", 0.0)),
    }
    trace_path = str(os.environ.get("XSTAR_V064812345335_NON_TYPE7_TRACE", "")).strip()
    if trace_path:
        payload = dict(control["source_detail_rrc_non_type7_summary_v064812345335"])
        payload["published_continuum_indices"] = sorted(int(k) for k in published)
        path = Path(trace_path); path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def calc_emisab_all(context: CalcEmisabContext) -> CalcEmisabResult:
    """Execute ``calc_emisab_all.f90`` in literal source order."""
    epi, _, _ = _radiation_arrays(context.radiation)
    context.workspace.validate(
        n_lines=context.derived.nlsvn,
        n_continua=context.derived.ncsvn,
        n_energy=len(epi),
    )
    context.workspace.clear_source_outputs()
    _begin_source_detail_line_publication_shadow_v064812345334(context.profile_control)
    _begin_source_detail_rrc_evaluation_v06481234532(context.profile_control)
    if isinstance(context.profile_control, MutableMapping):
        context.profile_control["source_detail_rrc_publication_shadow_v0648123451"] = {}
        context.profile_control["source_detail_rrc_type7_final_slot_v064812345339"] = {}
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
    visited_type7_records: set[int] = set()
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
                visited_type7_records=visited_type7_records,
            ))
        else:
            element_traces.append(CalcEmisabElementTrace(
                element_record=element_record, element_z=z, abundance=abundance,
                abundant=False, compact_population_count=0, compact_xileve=(), ion_traces=(),
            ))
        element_record = int(context.derived.npnxt[element_record])

    _evaluate_canonical_npcon_orphan_type7_absorption_v06481234533(
        context, visited_type7_records=visited_type7_records, xpx=xpx, xh0=xh0, xh1=xh1
    )
    _evaluate_canonical_npcon_non_type7_detail3_absorption_v064812345335(
        context, xpx=xpx, xh0=xh0, xh1=xh1
    )

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
            15: np.asarray([0, 0, 1, 0, 1, 0]),
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
            14: _SyntheticHeader(74, 7), 15: _SyntheticHeader(49, 1),
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
        self.ncsvn = 3
        self.max_rate_type = 14
        self.npfirst = np.zeros(15, dtype=int); self.npfirst[11] = 1; self.npfirst[12] = 2
        self.npar = np.zeros(30, dtype=int)
        self.npnxt = np.zeros(30, dtype=int)
        self.npnxt[2] = 3
        self.npar[2] = self.npar[3] = 1
        for rec in (10, 11, 12, 13): self.npar[rec] = 2
        self.npar[14] = 3
        self.npar[15] = 2
        self.npnxt[10] = 0; self.npnxt[11] = 0; self.npnxt[12] = 0; self.npnxt[13] = 0; self.npnxt[14] = 0
        for rec in (20, 21, 22): self.npar[rec] = 2
        for rec in (23, 24, 25): self.npar[rec] = 3
        self.npnxt[20] = 21; self.npnxt[21] = 22
        self.npnxt[23] = 24; self.npnxt[24] = 25
        self.npfi = np.zeros((15, 3), dtype=int)
        self.npfi[4,1]=10; self.npfi[7,1]=12; self.npfi[9,1]=11; self.npfi[13,1]=20; self.npfi[14,1]=13
        self.npfi[7,2]=14; self.npfi[13,2]=23
        self.nplini = np.zeros(30, dtype=int); self.nplini[10]=1; self.nplini[11]=1
        self.npconi2 = np.zeros(30, dtype=int); self.npconi2[12]=1; self.npconi2[14]=2; self.npconi2[15]=3
        self.npcon = np.asarray([0,12,14,15], dtype=int)
        self.nlevs = np.asarray([0,3,3], dtype=int)
        self.n_ions = 2
        self.ion_records = np.asarray([0,2,3], dtype=int)
        self.ion_element_z = np.asarray([0,8,8], dtype=int)
        self.ion_stage = np.asarray([0,1,2], dtype=int)
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
        15: (-5.0, -5.0, 0.0, {}),
    }
    ans3, ans4, opak, diag = data[int(record)]
    return UCalcResult(
        record=int(record), data_type={10:50,11:11,12:53,13:71,14:74,15:49}[int(record)],
        rate_type={10:4,11:9,12:7,13:14,14:7,15:1}[int(record)],
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
    workspace = CalcEmisabWorkspace.allocate(n_lines=1, n_continua=3, n_energy=4, continuum_fill=7.0)
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
            continuum_tau_in=np.asarray([0.0,0.0,0.0]), continuum_tau_out=np.asarray([0.0,0.0,0.0]),
        ),
        covering_fraction=0.25, ucalc_evaluator=_synthetic_ucalc, profile_control={},
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
    reset_ready = bool(
        np.count_nonzero(workspace.cemab[:,2:4]) == 0
        and workspace.cabab[2] == 0.0 and workspace.opakab[2] == 0.0
        and workspace.cabab[3] == 0.0 and workspace.opakab[3] == 0.0
    )
    non_type7 = context.profile_control.get("source_detail_rrc_non_type7_absorption_v064812345335", {}) if isinstance(context.profile_control, Mapping) else {}
    non_type7_ready = bool(
        isinstance(non_type7, Mapping)
        and 3 in non_type7
        and int(non_type7[3].get("source_record", 0)) == 15
        and int(non_type7[3].get("rate_type", 0)) == 1
        and int(non_type7[3].get("data_type", 0)) == 49
        and math.isclose(float(non_type7[3].get("integrated_absn", 0.0)), 2.5, rel_tol=rtol, abs_tol=atol)
        and workspace.cabab[3] == 0.0 and workspace.opakab[3] == 0.0
        and np.count_nonzero(workspace.cemab[:,3]) == 0
    )
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
        "canonical_non_type7_detail3_absorption_producer_ready": non_type7_ready,
        "canonical_non_type7_detail3_absorption_map": dict(non_type7) if isinstance(non_type7, Mapping) else {},
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
