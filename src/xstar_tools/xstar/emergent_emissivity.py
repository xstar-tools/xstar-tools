"""Source-faithful translation of XSTAR ``calc_emis_all``.

The bounded source chain is::

    xstarcalc.f90
      -> calc_emis_all.f90
      -> rlbin.f90
      -> calc_emis_element.f90
      -> calc_emis_ion.f90
      -> freef.f90
      -> bremem.f90

This stage consumes the line/RRC products produced by ``calc_emisab_all``.
Those arrays are ranked *before* the continuum workspace is reset.  The
translation preserves XSTAR's caller-owned ``fline``/``flinel`` arrays, the
all-ion compact alias map, inactive-ion compact offsets, the rate-type-9
double ``ucalc`` call, and the source-local ``kkkl`` continuum pointer reused
by rate types 9 and 42.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import MutableMapping
import json
import math
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Optional, Sequence

import numpy as np

from .bremsstrahlung import BremsstrahlungResult, bremem
from .compton import XSTAR_THOMSON_CROSS_SECTION_CM2
from .driver import XSTARPythonDriver, XSTARSourceRoutine
from .element_equilibrium import EscapeProbabilityContext, build_level_table, pescl, pescv
from .emissivity import (
    CalcEmisabContext,
    CalcEmisabPortError,
    CalcEmisabWorkspace,
    XSTAR_CALC_EMISAB_ABUNDANCE_FLOOR,
    XSTAR_CALC_EMISAB_ERG_PER_EV,
    _IonDescriptor,
    _accumulate_ucalc_continuum,
    _compact_element_populations,
    _copy_or_initialize_leveltemp,
    _evaluate_ucalc,
    _iter_ion_descriptors,
    _one_based_array_value,
    _overwrite_leveltemp,
    _ucalc_context,
    resolve_calc_emisab_density,
)
from .free_free import FreeFreeResult, freef
from .performance import profile_component, profile_level_at_least, record_profile_event
from .cpp_backend_rates import apply_linopac_profile_cpp, apply_mg_type4_type50_coarse_cpp_detailed, build_mg_type4_line_emissivity_cpp_detailed, rates_backend_status
from .radiation import nbinc
from .state import XSTARPythonState
from .ucalc import SourceFaithfulUCalc, UCalcLevelTable, UCalcResult, UCalcStatus
from .continuum_diagnostics import (
    append_phase_snapshot,
    append_ucalc_continuum_side_effect_diagnostic,
    UCALC_SIDE_EFFECT_KEY,
)


XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM = float(np.float32(12398.4016))
XSTAR_CALC_EMIS_RANK_FLOOR = float(np.float32(1.0e-37))
XSTAR_CALC_EMIS_WAVELENGTH_FLOOR = float(np.float32(1.0e-34))
XSTAR_CALC_EMIS_LINE_WAVELENGTH_FLOOR = 1.0e-36
XSTAR_CALC_EMIS_DENSITY_COEFFICIENT = float(np.float32(1.38e-12))
XSTAR_CALC_EMIS_DEFAULT_RANK_DEPTH = 10
XSTAR_CALC_EMIS_FORCE_ALL_SENTINEL = 9_999_999

# v0.5.18: focused diagnostic for the opacity-selected bins feeding step.f90.
# These are one-based continuum bins; bin 3877 is the current c5_ne1 limiter.
XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS = (3875, 3876, 3877, 3878, 3879)
XSTAR_LINE_OPACITY_DIAGNOSTIC_MAX_ROWS = 2000
XSTAR_TYPE50_LINE_STRENGTH_TARGET_LINES = (119, 120, 410, 411, 1983, 1984)



class CalcEmisPortError(RuntimeError):
    """Raised when the translated ``calc_emis_all`` contract is invalid."""


@dataclass
class CalcEmisWorkspace:
    """Caller-owned arrays entering ``calc_emis_all``.

    ``base`` is the complete output workspace from ``calc_emisab_all``.
    ``fline`` and ``flinel`` are initialized by ``init.f90`` and are *not*
    cleared by ``calc_emis_all``.
    """

    base: CalcEmisabWorkspace
    fline: np.ndarray
    flinel: np.ndarray

    @classmethod
    def allocate(
        cls,
        *,
        n_lines: int,
        n_continua: int,
        n_energy: int,
        continuum_fill: float = 0.0,
        fline_fill: float = 0.0,
        flinel_fill: float = 0.0,
    ) -> "CalcEmisWorkspace":
        return cls(
            base=CalcEmisabWorkspace.allocate(
                n_lines=n_lines,
                n_continua=n_continua,
                n_energy=n_energy,
                continuum_fill=continuum_fill,
            ),
            fline=np.full((2, int(n_lines) + 1), float(fline_fill), dtype=float),
            flinel=np.full(int(n_energy), float(flinel_fill), dtype=float),
        )

    def validate(self, *, n_lines: int, n_continua: int, n_energy: int) -> None:
        self.base.validate(n_lines=n_lines, n_continua=n_continua, n_energy=n_energy)
        if self.fline.shape != (2, int(n_lines) + 1):
            raise CalcEmisPortError(f"invalid fline shape {self.fline.shape}")
        if self.flinel.shape != (int(n_energy),):
            raise CalcEmisPortError(f"invalid flinel shape {self.flinel.shape}")
        if not np.all(np.isfinite(self.fline)) or not np.all(np.isfinite(self.flinel)):
            raise CalcEmisPortError("fline/flinel contain non-finite values")


@dataclass
class CalcEmisContext:
    master: Any
    derived: Any
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
    workspace: CalcEmisWorkspace
    line_wavelength_angstrom: np.ndarray
    rrc_wavelength_angstrom: np.ndarray
    escape: EscapeProbabilityContext = field(default_factory=EscapeProbabilityContext)
    covering_fraction: float = 1.0
    turbulent_velocity_km_s: float = 0.0
    critical_ion_fraction: float = 0.0
    radiation_temperature: float = 0.0
    radius_cm: float = 0.0
    zone_thickness_cm: float = 0.0
    lfast: int = 2
    rank_depth: int = XSTAR_CALC_EMIS_DEFAULT_RANK_DEPTH
    strict_ucalc: bool = True
    ucalc_engine: Optional[SourceFaithfulUCalc] = None
    ucalc_evaluator: Optional[Callable[[int, Any], UCalcResult]] = None
    initial_leveltemp_workspace: Optional[UCalcLevelTable] = None
    retain_traces: bool = True
    active_element_z: Optional[Sequence[int]] = None
    active_line_indices: Optional[Sequence[int]] = None
    active_continuum_indices: Optional[Sequence[int]] = None
    reusable_work_arrays: Optional[MutableMapping[str, Any]] = None
    profile_control: Optional[MutableMapping[str, Any]] = None
    progress_callback: Optional[Callable[[str, Mapping[str, Any]], None]] = None
    mg_line_kernel: str = "python"

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
class FeatureRankTrace:
    feature_kind: str
    feature_index: int
    wavelength_angstrom: float
    energy_eV: float
    bin_one_based: int
    rank_one_based: int
    stored: bool
    reason: str


@dataclass(frozen=True)
class CalcEmisRecordTrace:
    record: int
    rate_type: int
    data_type: int
    ion_index: int
    ion_stage: int
    compact_offset: int
    idest1: int
    idest2: int
    lower_compact: int
    upper_compact: int
    output_index: int
    retained_continuum_index: int
    abundance_lower: float
    abundance_upper: float
    ptmp1: float
    ptmp2: float
    ans1: float
    ans2: float
    ans3: float
    ans4: float
    opakb1: float
    status: str
    output_role: str


@dataclass(frozen=True)
class CalcEmisIonTrace:
    ion_record: int
    ion_index: int
    ion_stage: int
    nlev: int
    compact_offset: int
    active: bool
    n_records_visited: int
    n_ucalc_calls: int


@dataclass(frozen=True)
class CalcEmisElementTrace:
    element_record: int
    element_z: int
    abundance: float
    abundant: bool
    compact_population_count: int
    compact_xileve: tuple[float, ...]
    ion_traces: tuple[CalcEmisIonTrace, ...]


@dataclass(frozen=True)
class CalcEmisResult:
    hydrogen_density_cm3: float
    electron_density_cm3: float
    neutral_h_density_cm3: float
    ionized_h_density_cm3: float
    line_rank_table: np.ndarray
    continuum_rank_table: np.ndarray
    rank_traces: tuple[FeatureRankTrace, ...]
    element_traces: tuple[CalcEmisElementTrace, ...]
    record_traces: tuple[CalcEmisRecordTrace, ...]
    leveltemp_workspace: UCalcLevelTable
    free_free_result: FreeFreeResult
    bremsstrahlung_result: BremsstrahlungResult
    workspace: CalcEmisWorkspace
    source_file: str = "xstar/xstarlib/src/calc_emis_all.f90"
    active_feature_summary: Mapping[str, Any] = field(default_factory=dict)


def _high_resolution_radiation(radiation: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    epi = np.asarray(getattr(radiation, "epi_eV", getattr(radiation, "epi", ())), dtype=float).reshape(-1)
    bremsa = np.asarray(getattr(radiation, "bremsa", ()), dtype=float).reshape(-1)
    bremsint = np.asarray(getattr(radiation, "bremsint", ()), dtype=float).reshape(-1)
    if epi.size < 4 or bremsa.size != epi.size or bremsint.size != epi.size:
        raise CalcEmisPortError("calc_emis_all requires matching epi/bremsa/bremsint arrays")
    if np.any(epi <= 0.0) or np.any(np.diff(epi) <= 0.0):
        raise CalcEmisPortError("calc_emis_all photon grid must be positive and increasing")
    if not all(np.all(np.isfinite(arr)) for arr in (epi, bremsa, bremsint)):
        raise CalcEmisPortError("calc_emis_all radiation arrays contain non-finite values")
    return epi, bremsa, bremsint


def resolve_calc_emis_density(*, xpx: float, pressure: float, t_1e4: float, xee: float, lcdd: int) -> float:
    """Translate the density overrides at the top of ``calc_emis_all``."""
    return resolve_calc_emisab_density(xpx=xpx, pressure=pressure, t_1e4=t_1e4, xee=xee, lcdd=lcdd)


def rlbin_insert(
    *,
    feature_kind: str,
    feature_index: int,
    wavelengths_angstrom: np.ndarray,
    emissivity: np.ndarray,
    opacity: np.ndarray,
    epi_eV: np.ndarray,
    ncn2: int,
    rank_table: np.ndarray,
    rank_by_opacity: bool,
) -> FeatureRankTrace:
    """Translate one ``rlbin.f90`` insertion in literal source order."""
    jkk1 = int(feature_index)
    if jkk1 <= 0:
        return FeatureRankTrace(feature_kind, jkk1, 0.0, 0.0, 0, 0, False, "nonpositive_index")
    if jkk1 >= wavelengths_angstrom.size or jkk1 >= opacity.size or jkk1 >= emissivity.shape[1]:
        raise CalcEmisPortError(f"{feature_kind} index {jkk1} exceeds source arrays")
    opac = float(opacity[jkk1])
    emis = float(emissivity[0, jkk1] + emissivity[1, jkk1])
    wave = float(wavelengths_angstrom[jkk1])
    if opac < XSTAR_CALC_EMIS_RANK_FLOOR and emis < XSTAR_CALC_EMIS_RANK_FLOOR:
        return FeatureRankTrace(feature_kind, jkk1, wave, 0.0, 0, 0, False, "below_source_floor")
    emaxa = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / float(epi_eV[0])
    emina = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / float(epi_eV[int(ncn2) - 1])
    if wave > emaxa or wave < emina:
        return FeatureRankTrace(feature_kind, jkk1, wave, 0.0, 0, 0, False, "wavelength_outside_grid")
    energy = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / (XSTAR_CALC_EMIS_WAVELENGTH_FLOOR + wave)
    nb1 = nbinc(energy, epi_eV, int(ncn2))
    nrank = int(rank_table.shape[0] - 1)
    mm = 0
    done = False
    while not done:
        mm += 1
        jkk2 = int(rank_table[mm, nb1])
        if jkk2 == 0 or jkk1 == 0:
            done = True
        if not done:
            if not rank_by_opacity:
                if emis > float(emissivity[0, jkk2] + emissivity[1, jkk2]):
                    done = True
            else:
                if opac > float(opacity[jkk2]):
                    done = True
            if mm >= nrank:
                done = True
    # Literal source quirk: an insertion reaching rank==nrank is discarded.
    if mm >= nrank:
        return FeatureRankTrace(feature_kind, jkk1, wave, energy, nb1, mm, False, "source_rank_limit")
    for mm2 in range(nrank - 1, mm - 1, -1):
        rank_table[mm2 + 1, nb1] = rank_table[mm2, nb1]
    rank_table[mm, nb1] = jkk1
    return FeatureRankTrace(feature_kind, jkk1, wave, energy, nb1, mm, True, "stored")


def _feature_indices_from_context(context: CalcEmisContext, kind: str) -> np.ndarray:
    """Return one-based feature indices for ranking.

    In production active-subset mode, these lists are precomputed once per run
    from nplin/npcon ownership.  Empty or missing lists deliberately fall back
    to the source-full range, preserving old behavior for synthetic tests and
    unusual ATDB schemas.
    """
    if kind == "line":
        values = getattr(context, "active_line_indices", None)
        limit = int(context.derived.nlsvn)
    else:
        values = getattr(context, "active_continuum_indices", None)
        limit = int(context.derived.ncsvn)
    if values is None:
        return np.arange(1, limit + 1, dtype=np.int64)
    arr = np.asarray(values, dtype=np.int64).reshape(-1)
    arr = arr[(arr >= 1) & (arr <= limit)]
    if arr.size == 0:
        return np.arange(1, limit + 1, dtype=np.int64)
    return arr


def _cached_rank_table(context: CalcEmisContext, key: str, shape: tuple[int, int]) -> np.ndarray:
    cache = getattr(context, "reusable_work_arrays", None)
    if isinstance(cache, MutableMapping):
        arr = cache.get(key)
        if isinstance(arr, np.ndarray) and arr.shape == shape and arr.dtype.kind in ("i", "u"):
            arr.fill(0)
            return arr
        arr = np.zeros(shape, dtype=int)
        cache[key] = arr
        return arr
    return np.zeros(shape, dtype=int)


def build_feature_rank_tables(context: CalcEmisContext, epi: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[FeatureRankTrace, ...], dict[str, Any]]:
    n = int(epi.size)
    nrank = int(context.rank_depth)
    if nrank < 2:
        raise CalcEmisPortError("calc_emis_all rank_depth must be at least 2")
    line_table = _cached_rank_table(context, "calc_emis_all.line_rank_table", (nrank + 1, n + 1))
    continuum_table = _cached_rank_table(context, "calc_emis_all.continuum_rank_table", (nrank + 1, n + 1))
    retain = bool(getattr(context, "retain_traces", True))
    traces: list[FeatureRankTrace] | _TraceSink = [] if retain else _TraceSink()
    continuum_indices = _feature_indices_from_context(context, "continuum")
    line_indices = _feature_indices_from_context(context, "line")
    for index in continuum_indices:
        traces.append(rlbin_insert(
            feature_kind="continuum", feature_index=int(index),
            wavelengths_angstrom=np.asarray(context.rrc_wavelength_angstrom, dtype=float),
            emissivity=context.workspace.base.cemab, opacity=context.workspace.base.opakab,
            epi_eV=epi, ncn2=n, rank_table=continuum_table, rank_by_opacity=True,
        ))
    for index in line_indices:
        traces.append(rlbin_insert(
            feature_kind="line", feature_index=int(index),
            wavelengths_angstrom=np.asarray(context.line_wavelength_angstrom, dtype=float),
            emissivity=context.workspace.base.rcem, opacity=context.workspace.base.oplin,
            epi_eV=epi, ncn2=n, rank_table=line_table, rank_by_opacity=False,
        ))
    summary = {
        "active_subset_used": bool(
            getattr(context, "active_line_indices", None) is not None
            or getattr(context, "active_continuum_indices", None) is not None
        ),
        "n_ranked_line_candidates": int(line_indices.size),
        "n_ranked_continuum_candidates": int(continuum_indices.size),
        "n_total_lines": int(context.derived.nlsvn),
        "n_total_continua": int(context.derived.ncsvn),
        "active_element_z": [int(z) for z in (getattr(context, "active_element_z", None) or ())],
    }
    return line_table, continuum_table, tuple(traces) if retain else tuple(), summary

def _feature_is_ranked(table: np.ndarray, feature_index: int, bin_one_based: int) -> bool:
    mm = 1
    nrank = int(table.shape[0] - 1)
    while int(table[mm, bin_one_based]) != 0 and int(table[mm, bin_one_based]) != int(feature_index) and mm < nrank:
        mm += 1
    return bool(
        int(table[mm, bin_one_based]) == int(feature_index)
        or int(table[1, bin_one_based]) == XSTAR_CALC_EMIS_FORCE_ALL_SENTINEL
    )


def _parent_element_atomic_mass(master: Any, derived: Any, record: int) -> float:
    """Return the source parent-element atomic mass used by ``linopac``."""
    try:
        ion_record = int(derived.npar[int(record)])
        element_record = int(derived.npar[ion_record]) if ion_record > 0 else 0
        reals = master.record_reals(element_record) if element_record > 0 else ()
        if len(reals) > 1 and float(reals[1]) > 0.0:
            return float(reals[1])
    except Exception:
        pass
    return 1.0


def _source_linopac_into_opakc(
    *,
    optpp: float,
    rcem1: float,
    rcem2: float,
    line_energy_eV: float,
    vturb_km_s: float,
    temperature_1e4K: float,
    atomic_mass_amu: float,
    natural_width_eV: float,
    epi: np.ndarray,
    opakc: np.ndarray,
    rccemis: np.ndarray,
    ncn2: int,
    diagnostic_bins_one_based: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Bounded translation of ``linopac.f90`` for line-opacity handoff.

    ``calc_emis_ion.f90`` calls ``ucalc`` for ranked lines and ``ucalc`` calls
    ``linopac`` with ``lfasto=2``.  Earlier Python releases set only the
    per-line ``oplin`` value or added the line-center opacity to one continuum
    bin.  This helper preserves the source profile/rebinning path into the
    continuum-grid ``opakc`` array used later by ``step.f90``.  It intentionally
    does not update ``opakcont`` because the source documents that array as
    continuum opacity with lines excluded.
    """
    n = int(ncn2)
    diagnostic_bins = tuple(int(b) for b in (diagnostic_bins_one_based or ()))
    diagnostic_bin_set = set(diagnostic_bins)
    profile_samples_by_bin: dict[int, int] = {int(b): 0 for b in diagnostic_bins}
    profile_interval_width_by_bin: dict[int, float] = {int(b): 0.0 for b in diagnostic_bins}
    profile_opsum_by_bin: dict[int, float] = {int(b): 0.0 for b in diagnostic_bins}
    contribution_by_bin: dict[int, float] = {int(b): 0.0 for b in diagnostic_bins}
    optp2_by_bin: dict[int, float] = {int(b): 0.0 for b in diagnostic_bins}
    source_opsum_over_sume_by_bin: dict[int, float] = {int(b): 0.0 for b in diagnostic_bins}
    if n < 3 or optpp <= 0.0 or line_energy_eV <= 0.0:
        return {"updated_bins": 0, "max_added_opacity": 0.0, "center_bin_one_based": 0}
    if line_energy_eV <= float(epi[0]) or line_energy_eV >= float(epi[n - 1]):
        return {"updated_bins": 0, "max_added_opacity": 0.0, "center_bin_one_based": 0}
    nbtpp = 20000
    dpcrit = 1.0e-6
    ml1 = int(nbinc(line_energy_eV, epi, n))
    ml1 = max(min(n - 1, ml1), 2)
    mass = max(float(atomic_mass_amu), 1.0e-30)
    vth = 12.9 * np.sqrt(float(temperature_1e4K) / mass)
    vturb = float(vturb_km_s)
    e0 = float(line_energy_eV)
    deleturb = e0 * (vturb / 3.0e5)
    deleth = e0 * (vth / 3.0e5)
    dele = float(np.sqrt(deleth * deleth + deleturb * deleturb))
    if dele <= 0.0:
        return {"updated_bins": 0, "max_added_opacity": 0.0, "center_bin_one_based": ml1}
    aasmall = float(natural_width_eV) / (1.0e-24 + dele) / 12.56
    e00 = float(epi[ml1 - 1])
    etmp = e0
    deleepi = float(epi[ml1] - epi[ml1 - 1])
    ncut = int(deleepi / dele)
    ncut = max(ncut, 1)
    ncut = min(ncut, nbtpp // 10)
    deleused = deleepi / float(ncut)
    prftmp = 2.0 / (float(epi[ml1]) - float(epi[ml1 - 2])) if ml1 >= 2 and ml1 < len(epi) else 0.0
    opsv4 = float(optpp) * float(dele)
    mlc = 0
    ldir = 1
    ldon = [0, 0]
    mlmin = nbtpp
    mlmax = 1
    ml1min = n + 1
    ml1max = 0
    ml2 = nbtpp // 2
    etpp = np.zeros(nbtpp, dtype=float)
    optpp2 = np.zeros(nbtpp, dtype=float)

    delet = (e00 - etmp) / dele
    if aasmall > 1.0e-6:
        from .output_writers import voigte
        profile = voigte(abs(delet), aasmall) / 1.772
    else:
        profile = float(np.exp(-delet * delet) / 1.772)
    etpp[ml2 - 1] = e00
    optpp2[ml2 - 1] = float(optpp) * profile
    tst = 1.0
    while ldon[0] * ldon[1] == 0 and mlc < nbtpp // 2:
        mlc += 1
        for ij in range(2):
            ldir = -ldir
            if ldon[ij] == 1:
                continue
            mlm = ml2 + ldir * mlc
            etptst = e00 + float(ldir * mlc) * deleused
            if mlm <= nbtpp and mlm >= 1 and etptst > 0.0 and etptst < float(epi[n - 1]):
                mlmin = min(mlm, mlmin)
                mlmax = max(mlm, mlmax)
                etpp[mlm - 1] = etptst
                delet = (etptst - etmp) / dele
                if aasmall > 1.0e-9:
                    from .output_writers import voigte
                    profile = voigte(abs(delet), aasmall) / 1.772
                else:
                    profile = float(np.exp(-delet * delet) / 1.772)
                optpp2[mlm - 1] = float(optpp) * profile
                # Source-faithful v0.5.19: linopac.f90 does *not* update
                # ml1min/ml1max inside this temporary-grid construction loop.
                # They remain at ncn+1/0 until after the loop, where they are
                # recomputed from etpp(mlmin) and etpp(mlmax).  Earlier Python
                # code updated them here, which enabled an early stop that the
                # Fortran source cannot take.  Preserve the source order so the
                # profile scan and rebinning window match linopac.f90.
                tst = profile
            delet_now = (etptst - etmp) / dele if dele != 0.0 else 0.0
            if (
                (tst < dpcrit or mlm <= 1 or mlm >= nbtpp or etptst <= 0.0 or etptst >= float(epi[n - 1]) or mlc > nbtpp or abs(delet_now) > max(50.0, 200.0 * aasmall))
                and ml1min < ml1 - 2 and ml1max > ml1 + 2 and ml1min >= 1 and ml1max <= n
            ):
                ldon[ij] = 1
    if mlmin > mlmax:
        return {"updated_bins": 0, "max_added_opacity": 0.0, "center_bin_one_based": ml1}
    ml1min = int(nbinc(float(etpp[mlmin - 1]), epi, n))
    ml1max = int(nbinc(float(etpp[mlmax - 1]), epi, n))
    ml1m = ml1min
    mlmin = max(mlmin, 2)
    mlmax = min(mlmax, nbtpp)
    sume = 0.0
    opsum = 0.0
    tmpop = 0.0
    updated = 0
    max_added = 0.0
    for mlm in range(mlmin + 1, mlmax + 1):
        tmpopo = tmpop
        tmpop = float(optpp2[mlm - 1])
        tmpe = abs(float(etpp[mlm - 1]) - float(etpp[mlm - 2]))
        sume += tmpe
        interval_ops = (tmpop + tmpopo) * tmpe / 2.0
        opsum += interval_ops
        if ml1m in diagnostic_bin_set:
            profile_samples_by_bin[ml1m] = int(profile_samples_by_bin.get(ml1m, 0)) + 1
            profile_interval_width_by_bin[ml1m] = float(profile_interval_width_by_bin.get(ml1m, 0.0)) + float(tmpe)
            profile_opsum_by_bin[ml1m] = float(profile_opsum_by_bin.get(ml1m, 0.0)) + float(interval_ops)
        if float(etpp[mlm - 1]) > float(epi[ml1m - 1]):
            if sume > 1.0e-34:
                optp2 = opsum / sume
                while float(etpp[mlm - 1]) > float(epi[ml1m - 1]) and ml1m < n:
                    opakc[ml1m - 1] += optp2
                    if ml1m in diagnostic_bin_set:
                        contribution_by_bin[ml1m] = float(contribution_by_bin.get(ml1m, 0.0)) + float(optp2)
                        optp2_by_bin[ml1m] = float(optp2)
                        source_opsum_over_sume_by_bin[ml1m] = float(optp2)
                    if rccemis.shape[1] >= ml1m:
                        rccemis[0, ml1m - 1] += float(rcem1) * 0.0
                        rccemis[1, ml1m - 1] += float(rcem2) * 0.0
                    updated += 1
                    max_added = max(max_added, abs(float(optp2)))
                    ml1m += 1
            opsum = 0.0
            sume = 0.0
    return {
        "updated_bins": int(updated),
        "max_added_opacity": float(max_added),
        "center_bin_one_based": int(ml1),
        "source_nbtpp": int(nbtpp),
        "source_ml1_extrema_updated_inside_temp_loop": False,
        "source_early_stop_enabled_by_ml1_extrema": False,
        "lfast_branch": "full_profile" if True else "single_bin",
        "e0_eV": float(e0),
        "elin_A": float(12398.4016 / max(float(e0), 1.0e-49)),
        "optpp_input": float(optpp),
        "dele_eV": float(dele),
        "deleused_eV": float(deleused),
        "ncut": int(ncut),
        "prftmp": float(prftmp),
        "opsv4": float(opsv4),
        "ml1min": int(ml1min),
        "ml1max": int(ml1max),
        "mlmin": int(mlmin),
        "mlmax": int(mlmax),
        "diagnostic_bins_one_based": list(diagnostic_bins),
        "profile_samples_by_bin": {str(k): int(v) for k, v in profile_samples_by_bin.items()},
        "profile_interval_width_by_bin": {str(k): float(v) for k, v in profile_interval_width_by_bin.items()},
        "profile_opsum_by_bin": {str(k): float(v) for k, v in profile_opsum_by_bin.items()},
        "source_opsum_over_sume_by_bin": {str(k): float(v) for k, v in source_opsum_over_sume_by_bin.items()},
        "contribution_by_bin": {str(k): float(v) for k, v in contribution_by_bin.items()},
        "optp2_by_bin": {str(k): float(v) for k, v in optp2_by_bin.items()},
        "fortran_source_compare": "linopac.f90 optp2=opsum/sume; Python source_opsum_over_sume_by_bin is the direct translated value",
        "contributes_to_diagnostic_bins": bool(any(abs(float(v)) > 0.0 for v in contribution_by_bin.values())),
    }


def _bin_continuum_opacity_for_step(context: CalcEmisContext, continuum_index: int, opakab: float, epi: np.ndarray) -> None:
    """Do not re-bin ``opakab`` into the continuum optical-depth grid.

    In source XSTAR, ``calc_emis_ion.f90`` passes ``opakc``/``opakcont`` and
    ``rccemis`` into ``ucalc``.  Bound-free branches such as type 53 update
    those full-grid arrays inside ``ucalc``/``phint53``.  The scalar
    ``opakab(kkkl)`` is retained separately for RRC/edge optical depths and is
    later accumulated by ``stpcut`` into ``tauc``; the caller does not add it
    a second time to ``opakc``.

    Earlier Python releases added ``opakab`` into the nearest continuum bin as
    a convenience carry.  After type-53 was moved to the correct full grid,
    that extra carry became visible as source-nonexistent threshold spikes,
    especially around the H I Lyman edge used by ``pprint(22)`` as ``taulc``.
    Keep this function as a documented no-op so older call sites remain
    harmless while preserving the Fortran ownership split.
    """
    del context, continuum_index, opakab, epi
    return


def _as_emisab_context(context: CalcEmisContext) -> CalcEmisabContext:
    """Create a duck-compatible view for shared ``ucalc`` helpers."""
    return CalcEmisabContext(
        master=context.master,
        derived=context.derived,
        temperature_1e4K=context.temperature_1e4K,
        electron_fraction_xee=context.electron_fraction_xee,
        hydrogen_density_cm3=context.hydrogen_density_cm3,
        pressure_dyn_cm2=context.pressure_dyn_cm2,
        density_control_lcdd=context.density_control_lcdd,
        abundances_by_z=context.abundances_by_z,
        min_ion_stage_by_z=context.min_ion_stage_by_z,
        max_ion_stage_by_z=context.max_ion_stage_by_z,
        xilevg=context.xilevg,
        bilevg=context.bilevg,
        rnisg=context.rnisg,
        radiation=context.radiation,
        workspace=context.workspace.base,
        escape=context.escape,
        covering_fraction=context.covering_fraction,
        turbulent_velocity_km_s=context.turbulent_velocity_km_s,
        critical_ion_fraction=context.critical_ion_fraction,
        radiation_temperature=context.radiation_temperature,
        radius_cm=context.radius_cm,
        zone_thickness_cm=context.zone_thickness_cm,
        lfast=context.lfast,
        strict_ucalc=context.strict_ucalc,
        ucalc_engine=context.ucalc_engine,
        ucalc_evaluator=context.ucalc_evaluator,
        initial_leveltemp_workspace=context.initial_leveltemp_workspace,
    )



def _calc_emis_record_sequence_for_ion(context: CalcEmisContext, ion: _IonDescriptor) -> list[tuple[int, int]]:
    """Return the source-ordered calc_emis_ion record sequence for one ion.

    v0.5.46 caches this sequence for active Mg/Ca-style element loops.  The
    sequence still includes all records for each rate type in source traversal
    order; the downstream rate-type conditions remain authoritative.
    """
    cache = getattr(context, "reusable_work_arrays", None)
    key = ("calc_emis_all.record_sequence", int(ion.ion_index))
    if isinstance(cache, MutableMapping):
        cached = cache.get(key)
        if cached is not None:
            return list(cached)
    max_rate_type = min(int(context.derived.max_rate_type), int(context.derived.npfi.shape[0] - 1))
    seq: list[tuple[int, int]] = []
    for rate_type in range(1, max_rate_type + 1):
        rec = int(context.derived.npfi[rate_type, ion.ion_index])
        while rec and int(context.derived.npar[rec]) == ion.ion_record:
            seq.append((int(rate_type), int(rec)))
            rec = int(context.derived.npnxt[rec])
    if isinstance(cache, MutableMapping):
        cache[key] = tuple(seq)
    return list(seq)


def _compact_mg_line_emissivity_table(
    context: CalcEmisContext,
    ion: _IonDescriptor,
    record_sequence: Sequence[tuple[int, int]],
    levels: UCalcLevelTable,
    line_rank_table: np.ndarray,
    epi: np.ndarray,
) -> dict[int, dict[str, Any]]:
    """Build a compact Mg record_type=4/9 line-emissivity lookup table.

    This v0.5.49 table is deliberately conservative: it precomputes source-stable
    metadata (line index, endpoints, energy/bin/rank decision, and energy-ordered
    lower/upper local levels) but leaves the source-faithful ucalc/linopac update
    loop in control of numerical side effects.  It is only used when
    ``mg_line_kernel='numpy'`` and only for Mg Z=12.
    """
    cache = getattr(context, "reusable_work_arrays", None)
    key = (
        "calc_emis_all.mg_line_emissivity_table.v0549",
        int(ion.ion_index),
        id(line_rank_table),
        id(epi),
    )
    if isinstance(cache, MutableMapping):
        cached = cache.get(key)
        if isinstance(cached, dict):
            return cached
    table: dict[int, dict[str, Any]] = {}
    # Keep the source record order.  NumPy is used for compact array storage of
    # the candidate fields; exact nbinc/source-rank decisions remain identical.
    records: list[int] = []
    rate_types: list[int] = []
    idest1_values: list[int] = []
    idest2_values: list[int] = []
    line_indices: list[int] = []
    for rate_type, rec in record_sequence:
        if int(rate_type) not in (4, 9):
            continue
        ints = context.master.record_integers(int(rec))
        if len(ints) < 2:
            continue
        idest1, idest2 = int(ints[0]), int(ints[1])
        line_index = int(context.derived.nplini[int(rec)])
        if not (line_index and line_index <= int(context.derived.nlsvn) and idest1 > 0):
            continue
        records.append(int(rec))
        rate_types.append(int(rate_type))
        idest1_values.append(idest1)
        idest2_values.append(idest2)
        line_indices.append(line_index)
    if not records:
        if isinstance(cache, MutableMapping):
            cache[key] = table
        return table
    records_arr = np.asarray(records, dtype=np.int64)
    rate_type_arr = np.asarray(rate_types, dtype=np.int16)
    idest1_arr = np.asarray(idest1_values, dtype=np.int32)
    idest2_arr = np.asarray(idest2_values, dtype=np.int32)
    line_index_arr = np.asarray(line_indices, dtype=np.int64)
    wave_arr = np.asarray(context.line_wavelength_angstrom[line_index_arr], dtype=float)
    energy_arr = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / (wave_arr + XSTAR_CALC_EMIS_LINE_WAVELENGTH_FLOOR)
    for i, rec in enumerate(records_arr):
        idest1 = int(idest1_arr[i])
        idest2 = int(idest2_arr[i])
        if not (1 <= idest2 <= int(ion.nlev)):
            table[int(rec)] = {"valid": False, "reason": "line endpoint outside ion nlev"}
            continue
        e1 = levels.require(idest1).energy_ev
        e2 = levels.require(idest2).energy_ev
        if e1 < e2:
            lower_local, upper_local = idest1, idest2
        else:
            lower_local, upper_local = idest2, idest1
        energy = float(energy_arr[i])
        nb1 = nbinc(energy, epi, len(epi))
        line_index = int(line_index_arr[i])
        ranked = bool(_feature_is_ranked(line_rank_table, line_index, nb1))
        table[int(rec)] = {
            "valid": True,
            "rate_type": int(rate_type_arr[i]),
            "idest1": idest1,
            "idest2": idest2,
            "line_index": line_index,
            "wave": float(wave_arr[i]),
            "energy": energy,
            "nb1": int(nb1),
            "ranked": ranked,
            "e1": float(e1),
            "e2": float(e2),
            "lower_local": int(lower_local),
            "upper_local": int(upper_local),
        }
    if isinstance(cache, MutableMapping):
        cache[key] = table
    return table




def _emissivity_cpp_active_for_mg_type4(context: CalcEmisContext) -> bool:
    requested = None
    control = getattr(context, "profile_control", None)
    if isinstance(control, MutableMapping):
        backend_selection = control.get("backend_selection")
        if isinstance(backend_selection, Mapping):
            requested = str(backend_selection.get("emissivity_backend", "python"))
    requested = requested or os.environ.get("XSTAR_ATOMIC_EMISSIVITY_BACKEND") or "python"
    status = rates_backend_status(requested=requested)
    return bool(status.active == "cpp" and (int(status.cpp_feature_flags or 0) & 4))


def _emissivity_upstream_type4_shadow_enabled() -> bool:
    """Diagnostic-only Mg type-4 upstream emissivity C++ shadow gate.

    This intentionally does not depend on XSTAR_ATOMIC_EMISSIVITY_BACKEND=cpp.
    The live product path remains Python; selected C++ type-4/type-50 work is
    replayed on copied arrays and compared before final binemis packing.
    """
    for name in (
        "XSTAR_ATOMIC_EMISSIVITY_UPSTREAM_TYPE4_SHADOW_CPP",
        "XSTAR_ATOMIC_EMISSIVITY_MG_TYPE4_SHADOW_CPP",
    ):
        value = os.environ.get(name)
        if value is not None and str(value).strip().lower() not in {"", "0", "false", "no", "off"}:
            return True
    return False


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or str(default))
    except Exception:
        return int(default)


def _add_cpp_counter_totals(total: dict[str, float], stats: Mapping[str, Any]) -> None:
    """Accumulate all numeric C++ backend statistics.

    Earlier releases used a short whitelist and accidentally dropped new
    coarse-backend counters such as type50_coarse_cpp_hybrid_applied.  Keep the
    aggregator generic so future C++ kernels can expose counters without also
    editing this helper.
    """
    for key, value in stats.items():
        try:
            total[str(key)] = float(total.get(str(key), 0.0)) + float(value or 0.0)
        except Exception:
            continue

def calc_emis_ion(
    context: CalcEmisContext,
    *,
    ion: _IonDescriptor,
    element_abundance: float,
    compact_xileve: np.ndarray,
    compact_offset: int,
    xpx: float,
    xh0: float,
    xh1: float,
    line_rank_table: np.ndarray,
    continuum_rank_table: np.ndarray,
    leveltemp_workspace: UCalcLevelTable,
    record_traces: list[CalcEmisRecordTrace],
    epi: Optional[np.ndarray] = None,
) -> CalcEmisIonTrace:
    """Translate one call to ``calc_emis_ion.f90``."""
    shared = _as_emisab_context(context)
    current_levels = build_level_table(context.master, context.derived, ion.ion_index)
    _overwrite_leveltemp(leveltemp_workspace, current_levels)
    # leveltemp_workspace is caller-owned, but within one ion it is read-only
    # after the source-faithful overwrite.  Avoid copying the full level dict
    # on every Mg/Ca emissivity pass.
    levels = leveltemp_workspace
    if epi is None:
        epi, _, _ = _high_resolution_radiation(context.radiation)
    _epi_for_cpp, _brem_for_cpp, _ = _high_resolution_radiation(context.radiation)
    record_sequence = _calc_emis_record_sequence_for_ion(context, ion)
    mg_line_kernel = str(getattr(context, "mg_line_kernel", "python") or "python").strip().lower()
    mg_line_table: dict[int, dict[str, Any]] = {}
    if mg_line_kernel == "numpy" and int(getattr(ion, "element_z", 0)) == 12:
        mg_line_table = _compact_mg_line_emissivity_table(
            context, ion, record_sequence, levels, line_rank_table, epi
        )
    use_cpp_mg_type4_line = (
        int(getattr(ion, "element_z", 0)) == 12
        and _emissivity_cpp_active_for_mg_type4(context)
    )
    cpp_mg_type4_stats: dict[str, float] = {
        "records_batched": 0.0,
        "cpp_calls": 0.0,
        "packing_seconds": 0.0,
        "cpp_kernel_seconds": 0.0,
        "fallback_count": 0.0,
        "emitted_matrix_terms": 0.0,
        "batches_flushed": 0.0,
        "linopac_cpp_calls": 0.0,
        "linopac_cpp_kernel_seconds": 0.0,
        "linopac_cpp_updated_bins": 0.0,
        "linopac_cpp_fallback_count": 0.0,
        "linopac_cpp_parity_checks": 0.0,
        "linopac_cpp_parity_failures": 0.0,
        "type50_coarse_cpp_applied": 0.0,
        "type50_coarse_cpp_full_applied": 0.0,
        "type50_coarse_cpp_hybrid_applied": 0.0,
        "type50_coarse_cpp_fallback": 0.0,
        "type50_reason_full_cpp_applied": 0.0,
        "type50_reason_linopac_voigt_python_fallback": 0.0,
        "type50_reason_unsupported_data_type": 0.0,
        "type50_reason_linopac_cpp_failure": 0.0,
        "type50_reason_invalid_or_nonfinite_input": 0.0,
    }
    # v0.5.62: queue selected Mg record_type=4/data_type=50 records for a coarse
    # C++ path that evaluates ucalc type-50, scalar line emissivity, linopac, and
    # live array updates in one batch.  Unsupported records replay through Python.
    pending_cpp_mg_type50_coarse_records: list[dict[str, Any]] = []
    pending_cpp_mg_type50_coarse_jobs: list[dict[str, Any]] = []
    # v0.5.59: queue Mg record_type=4 scalar work and call the C++ kernel once
    # per contiguous Mg line block, instead of once per individual line record.
    # Python still owns ucalc and linopac side effects; this is the safe first
    # coarse-grained step toward a full Mg calc_emis_all.element C++ backend.
    pending_cpp_mg_type4_records: list[dict[str, Any]] = []
    pending_cpp_mg_type4_jobs: list[dict[str, Any]] = []
    visited = 0
    calls = 0
    retained_kkkl = 0
    diagnostics_enabled = bool(getattr(context, "retain_traces", True))
    profile_control = getattr(context, "profile_control", None) or {}
    upstream_type4_shadow_enabled = (
        int(getattr(ion, "element_z", 0)) == 12
        and _emissivity_upstream_type4_shadow_enabled()
    )
    upstream_type4_shadow_max_records = max(0, _safe_int_env("XSTAR_ATOMIC_EMISSIVITY_UPSTREAM_TYPE4_SHADOW_MAX_RECORDS", 0))
    upstream_type4_shadow_top_n = max(1, _safe_int_env("XSTAR_ATOMIC_EMISSIVITY_UPSTREAM_TYPE4_SHADOW_TOP_N", 16))
    upstream_type4_shadow_summary: dict[str, Any] | None = None
    upstream_type4_shadow_samples: list[Any] | None = None
    if upstream_type4_shadow_enabled:
        try:
            upstream_type4_shadow_summary = profile_control.setdefault("mg_type4_upstream_shadow_probe_summary", {})
            upstream_type4_shadow_samples = profile_control.setdefault("mg_type4_upstream_shadow_probe_samples", [])
            upstream_type4_shadow_summary.update({
                "probe_version": "0.6.17",
                "enabled": True,
                "product_active": False,
                "live_path": "python",
                "shadow_path": "cpp",
                "target_failed_products_from_v013": ["xo01_detal4.fits:zrems(1)", "xout_spect1.fits:transmitted"],
                "records_checked": int(upstream_type4_shadow_summary.get("records_checked", 0) or 0),
                "records_supported": int(upstream_type4_shadow_summary.get("records_supported", 0) or 0),
                "records_unsupported": int(upstream_type4_shadow_summary.get("records_unsupported", 0) or 0),
                "records_errors": int(upstream_type4_shadow_summary.get("records_errors", 0) or 0),
                "records_skipped_after_limit": int(upstream_type4_shadow_summary.get("records_skipped_after_limit", 0) or 0),
                "max_abs_diff": float(upstream_type4_shadow_summary.get("max_abs_diff", 0.0) or 0.0),
                "max_rel_diff": float(upstream_type4_shadow_summary.get("max_rel_diff", 0.0) or 0.0),
                "max_abs_array": str(upstream_type4_shadow_summary.get("max_abs_array", "") or ""),
                "max_abs_record": int(upstream_type4_shadow_summary.get("max_abs_record", -1) or -1),
                "max_abs_line_index": int(upstream_type4_shadow_summary.get("max_abs_line_index", -1) or -1),
                "max_records_limit": int(upstream_type4_shadow_max_records),
                "max_records_limit_semantics": "0 means scan all supported records",
                "per_array": dict(upstream_type4_shadow_summary.get("per_array", {}) or {}),
                "top_abs_records": list(upstream_type4_shadow_summary.get("top_abs_records", []) or []),
                "top_rel_records": list(upstream_type4_shadow_summary.get("top_rel_records", []) or []),
                "source_real_literal_parity_audit": {
                    "probe_version": "0.6.17",
                    "status": "audit_only_not_product_active",
                    "flinel_formula": "(rcem1 + rcem2) * 2.0 / width / erg_per_ev",
                    "python_source_real_policy": "Python path uses source-real/default-real parity where ported from unsuffixed Fortran literals.",
                    "cpp_type4_scalar_formula_policy": "C++ scalar type-4 uses double intermediates; v0.6.17 reports any resulting array drift before promotion.",
                    "arrays_audited": ["opakc", "rccemis", "oplin", "fline", "flinel"],
                },
            })
        except Exception:
            upstream_type4_shadow_summary = None
            upstream_type4_shadow_samples = None
    progress_callback = getattr(context, "progress_callback", None)
    is_mg_profile = int(getattr(ion, "element_z", 0)) == 12 and profile_level_at_least(profile_control, "nested")
    is_mg_forensic_profile = int(getattr(ion, "element_z", 0)) == 12 and profile_level_at_least(profile_control, "forensic")
    _ion_t0 = time.perf_counter() if is_mg_profile else 0.0
    _record_type_elapsed: dict[str, float] = {}
    _rate_type_elapsed: dict[int, float] = {}

    def evaluate(rec: int, ptmp1: float, ptmp2: float, abund1: float, abund2: float) -> UCalcResult:
        nonlocal calls
        result = _evaluate_ucalc(shared, rec, _ucalc_context(
            shared, ion=ion, levels=levels, xpx=xpx, xh0=xh0, xh1=xh1,
            ptmp1=ptmp1, ptmp2=ptmp2, abund1=abund1, abund2=abund2,
        ))
        calls += 1
        append_ucalc_continuum_side_effect_diagnostic(
            context,
            result,
            ion=ion,
            record=rec,
            ptmp1=ptmp1,
            ptmp2=ptmp2,
            abund1=abund1,
            abund2=abund2,
        )
        if result.ready:
            _accumulate_ucalc_continuum(context.workspace.base, result)
        return result

    def _linopac_cpp_parity_limit() -> int:
        value = None
        try:
            value = profile_control.get("mg_type4_linopac_cpp_parity_records")
        except Exception:
            value = None
        if value is None:
            value = os.environ.get("MG_TYPE4_LINOPAC_CPP_PARITY_RECORDS", "16")
        try:
            return max(0, int(value))
        except Exception:
            return 16

    linopac_cpp_gate: dict[str, Any] = {
        "checked": 0,
        "failed": False,
        "parity_limit": _linopac_cpp_parity_limit(),
    }

    def _apply_linopac_with_cpp_gate(
        *,
        optpp: float,
        rcem1: float,
        rcem2: float,
        line_energy_eV: float,
        vturb_km_s: float,
        temperature_1e4K: float,
        atomic_mass_amu: float,
        natural_width_eV: float,
    ) -> dict[str, Any]:
        """Apply Mg type-4 linopac side effects using C++ after a parity gate.

        The gate compares the C++ Gaussian linopac update against the Python
        source-faithful translation on copies for the first N records.  If any
        mismatch or unsupported Voigt-profile case appears, the live path falls
        back to Python for the rest of the ion.  This keeps v0.5.61 physically
        conservative while moving the live side-effect update to C++ only after
        agreement has been demonstrated.
        """
        if not use_cpp_mg_type4_line or linopac_cpp_gate.get("failed"):
            cpp_mg_type4_stats["linopac_cpp_fallback_count"] = cpp_mg_type4_stats.get("linopac_cpp_fallback_count", 0.0) + 1.0
            return _source_linopac_into_opakc(
                optpp=optpp,
                rcem1=rcem1,
                rcem2=rcem2,
                line_energy_eV=line_energy_eV,
                vturb_km_s=vturb_km_s,
                temperature_1e4K=temperature_1e4K,
                atomic_mass_amu=atomic_mass_amu,
                natural_width_eV=natural_width_eV,
                epi=epi,
                opakc=context.workspace.base.opakc,
                rccemis=context.workspace.base.rccemis,
                ncn2=len(epi),
                diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
            )
        parity_limit = int(linopac_cpp_gate.get("parity_limit", 16))
        checked = int(linopac_cpp_gate.get("checked", 0))
        if checked < parity_limit:
            py_opakc = context.workspace.base.opakc.copy()
            py_rcc = context.workspace.base.rccemis.copy()
            cpp_opakc = context.workspace.base.opakc.copy()
            cpp_rcc = context.workspace.base.rccemis.copy()
            py_diag = _source_linopac_into_opakc(
                optpp=optpp,
                rcem1=rcem1,
                rcem2=rcem2,
                line_energy_eV=line_energy_eV,
                vturb_km_s=vturb_km_s,
                temperature_1e4K=temperature_1e4K,
                atomic_mass_amu=atomic_mass_amu,
                natural_width_eV=natural_width_eV,
                epi=epi,
                opakc=py_opakc,
                rccemis=py_rcc,
                ncn2=len(epi),
                diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
            )
            try:
                cpp_diag, _msg, cpp_stats = apply_linopac_profile_cpp(
                    optpp=optpp,
                    rcem1=rcem1,
                    rcem2=rcem2,
                    line_energy_eV=line_energy_eV,
                    vturb_km_s=vturb_km_s,
                    temperature_1e4K=temperature_1e4K,
                    atomic_mass_amu=atomic_mass_amu,
                    natural_width_eV=natural_width_eV,
                    epi=epi,
                    opakc=cpp_opakc,
                    rccemis=cpp_rcc,
                    ncn2=len(epi),
                )
                _add_cpp_counter_totals(cpp_mg_type4_stats, cpp_stats)
                cpp_mg_type4_stats["linopac_cpp_parity_checks"] = cpp_mg_type4_stats.get("linopac_cpp_parity_checks", 0.0) + 1.0
                opakc_ok = bool(np.allclose(py_opakc, cpp_opakc, rtol=1.0e-10, atol=1.0e-30))
                rcc_ok = bool(np.allclose(py_rcc, cpp_rcc, rtol=1.0e-10, atol=1.0e-30))
                diag_ok = int(py_diag.get("updated_bins", -1)) == int(cpp_diag.get("updated_bins", -2))
                if not (opakc_ok and rcc_ok and diag_ok):
                    linopac_cpp_gate["failed"] = True
                    cpp_mg_type4_stats["linopac_cpp_parity_failures"] = cpp_mg_type4_stats.get("linopac_cpp_parity_failures", 0.0) + 1.0
                    cpp_mg_type4_stats["linopac_cpp_fallback_count"] = cpp_mg_type4_stats.get("linopac_cpp_fallback_count", 0.0) + 1.0
                    return _source_linopac_into_opakc(
                        optpp=optpp,
                        rcem1=rcem1,
                        rcem2=rcem2,
                        line_energy_eV=line_energy_eV,
                        vturb_km_s=vturb_km_s,
                        temperature_1e4K=temperature_1e4K,
                        atomic_mass_amu=atomic_mass_amu,
                        natural_width_eV=natural_width_eV,
                        epi=epi,
                        opakc=context.workspace.base.opakc,
                        rccemis=context.workspace.base.rccemis,
                        ncn2=len(epi),
                        diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
                    )
                linopac_cpp_gate["checked"] = checked + 1
            except Exception:
                linopac_cpp_gate["failed"] = True
                cpp_mg_type4_stats["linopac_cpp_fallback_count"] = cpp_mg_type4_stats.get("linopac_cpp_fallback_count", 0.0) + 1.0
                return _source_linopac_into_opakc(
                    optpp=optpp,
                    rcem1=rcem1,
                    rcem2=rcem2,
                    line_energy_eV=line_energy_eV,
                    vturb_km_s=vturb_km_s,
                    temperature_1e4K=temperature_1e4K,
                    atomic_mass_amu=atomic_mass_amu,
                    natural_width_eV=natural_width_eV,
                    epi=epi,
                    opakc=context.workspace.base.opakc,
                    rccemis=context.workspace.base.rccemis,
                    ncn2=len(epi),
                    diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
                )
        try:
            cpp_diag, _msg, cpp_stats = apply_linopac_profile_cpp(
                optpp=optpp,
                rcem1=rcem1,
                rcem2=rcem2,
                line_energy_eV=line_energy_eV,
                vturb_km_s=vturb_km_s,
                temperature_1e4K=temperature_1e4K,
                atomic_mass_amu=atomic_mass_amu,
                natural_width_eV=natural_width_eV,
                epi=epi,
                opakc=context.workspace.base.opakc,
                rccemis=context.workspace.base.rccemis,
                ncn2=len(epi),
            )
            _add_cpp_counter_totals(cpp_mg_type4_stats, cpp_stats)
            return cpp_diag
        except Exception:
            linopac_cpp_gate["failed"] = True
            cpp_mg_type4_stats["linopac_cpp_fallback_count"] = cpp_mg_type4_stats.get("linopac_cpp_fallback_count", 0.0) + 1.0
            return _source_linopac_into_opakc(
                optpp=optpp,
                rcem1=rcem1,
                rcem2=rcem2,
                line_energy_eV=line_energy_eV,
                vturb_km_s=vturb_km_s,
                temperature_1e4K=temperature_1e4K,
                atomic_mass_amu=atomic_mass_amu,
                natural_width_eV=natural_width_eV,
                epi=epi,
                opakc=context.workspace.base.opakc,
                rccemis=context.workspace.base.rccemis,
                ncn2=len(epi),
                diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
            )

    def _maybe_probe_upstream_type4_shadow(
        *,
        rec: int,
        rate_type: int,
        data_type: int,
        line_index: int,
        nb1: int,
        idest1: int,
        idest2: int,
        lower: int,
        upper: int,
        e1: float,
        e2: float,
        energy: float,
        wave: float,
        width: float,
        ptmp1: float,
        ptmp2: float,
        abund1: float,
        abund2: float,
        result: UCalcResult,
        opakb1: float,
        rcem1: float,
        rcem2: float,
        flinel_delta: float,
        natural_width: float,
        atomic_mass: float,
        py_before: Mapping[str, np.ndarray] | None,
    ) -> None:
        """Replay one upstream Mg type-4 C++ path on copies and compare.

        The live arrays have already been updated by Python when this is called.
        C++ receives the pre-update copies and its output copies are compared to
        the live Python post-update arrays. No C++ output is written back.
        """
        nonlocal upstream_type4_shadow_summary, upstream_type4_shadow_samples
        if not upstream_type4_shadow_enabled or upstream_type4_shadow_summary is None:
            return
        if int(rate_type) != 4 or int(getattr(ion, "element_z", 0)) != 12:
            return
        checked = int(upstream_type4_shadow_summary.get("records_checked", 0) or 0)
        if upstream_type4_shadow_max_records > 0 and checked >= upstream_type4_shadow_max_records:
            upstream_type4_shadow_summary["records_skipped_after_limit"] = int(upstream_type4_shadow_summary.get("records_skipped_after_limit", 0) or 0) + 1
            return
        upstream_type4_shadow_summary["records_checked"] = checked + 1
        try:
            if py_before is None:
                raise RuntimeError("missing pre-update Python arrays for shadow comparison")
            cpp_opakc = np.asarray(py_before["opakc"], dtype=float).copy()
            cpp_rcc = np.asarray(py_before["rccemis"], dtype=float).copy()
            cpp_oplin = np.asarray(py_before["oplin"], dtype=float).copy()
            cpp_fline = np.asarray(py_before["fline"], dtype=float).copy()
            cpp_flinel = np.asarray(py_before["flinel"], dtype=float).copy()
            status_reason = "scalar_cpp_applied"
            cpp_rows: list[Mapping[str, Any]] = []
            if int(data_type) == 50:
                reals_for_cpp = context.master.record_reals(int(rec))
                wavelength_cpp = abs(float(reals_for_cpp[0])) if len(reals_for_cpp) > 0 else abs(float(wave))
                aij_cpp = float(reals_for_cpp[2]) if len(reals_for_cpp) > 2 else 0.0
                if float(e1) < float(e2):
                    source_upper_id, source_lower_id = int(idest2), int(idest1)
                else:
                    source_upper_id, source_lower_id = int(idest1), int(idest2)
                source_upper_weight = float(levels.weight(source_upper_id))
                source_lower_weight = float(levels.weight(source_lower_id))
                bremsa_nb1 = float(_brem_for_cpp[int(nb1)]) if int(nb1) >= 0 and int(nb1) < len(_brem_for_cpp) else 0.0
                cpp_records = [{
                    "record": int(rec), "data_type": int(data_type), "ion_index": int(ion.ion_index), "ion_stage": int(ion.ion_stage),
                    "line_index": int(line_index), "nb1": int(nb1), "wavelength_A": float(wavelength_cpp), "aij_s": float(aij_cpp),
                    "source_upper_weight": float(source_upper_weight), "source_lower_weight": float(source_lower_weight),
                    "endpoint_energy_ev": abs(float(e2) - float(e1)), "bremsa_nb1": float(bremsa_nb1),
                    "ptmp1": float(ptmp1), "ptmp2": float(ptmp2), "abund1": float(abund1), "abund2": float(abund2),
                    "bin_width_ev": float(width), "natural_width_ev": float(natural_width),
                }]
                cpp_rows, _msg, _stats = apply_mg_type4_type50_coarse_cpp_detailed(
                    cpp_records,
                    cfrac=float(context.covering_fraction),
                    hydrogen_density_cm3=float(xpx),
                    turbulent_velocity_km_s=float(context.turbulent_velocity_km_s),
                    temperature_1e4K=float(context.temperature_1e4K),
                    atomic_mass_amu=float(atomic_mass),
                    erg_per_ev=XSTAR_CALC_EMISAB_ERG_PER_EV,
                    epi=epi,
                    opakc=cpp_opakc,
                    rccemis=cpp_rcc,
                    oplin=cpp_oplin,
                    fline=cpp_fline,
                    flinel=cpp_flinel,
                )
                status_reason = str(cpp_rows[0].get("status_reason", "status_unknown")) if cpp_rows else "no_cpp_row"
                if not cpp_rows or int(cpp_rows[0].get("status_code", 0)) != 1:
                    upstream_type4_shadow_summary["records_unsupported"] = int(upstream_type4_shadow_summary.get("records_unsupported", 0) or 0) + 1
                    return
            else:
                cpp_rows, _msg, _stats = build_mg_type4_line_emissivity_cpp_detailed([{
                    "record": int(rec), "data_type": int(data_type), "ion_index": int(ion.ion_index), "ion_stage": int(ion.ion_stage),
                    "line_index": int(line_index), "nb1": int(nb1), "ans1": float(result.ans1), "ans2": float(result.ans2),
                    "opakab": float(result.opakab), "abund1": float(abund1), "abund2": float(abund2),
                    "ptmp1": float(ptmp1), "ptmp2": float(ptmp2), "energy_ev": float(energy), "bin_width_ev": float(width),
                }], erg_per_ev=XSTAR_CALC_EMISAB_ERG_PER_EV)
                row = cpp_rows[0]
                if int(line_index) > 0 and int(line_index) < cpp_oplin.size:
                    cpp_oplin[int(line_index)] = float(row["opakb1"])
                    cpp_fline[0, int(line_index)] = float(row["rcem1"])
                    cpp_fline[1, int(line_index)] = float(row["rcem2"])
                if int(nb1) > 0 and int(nb1) <= cpp_flinel.size:
                    cpp_flinel[int(nb1) - 1] += float(row["flinel_delta"])
                # The scalar C++ helper does not own linopac side effects; mirror Python
                # for array-scope comparison so this probe isolates scalar line products.
                cpp_opakc = context.workspace.base.opakc.copy()
                cpp_rcc = context.workspace.base.rccemis.copy()
            py_arrays = {
                "opakc": context.workspace.base.opakc,
                "rccemis": context.workspace.base.rccemis,
                "oplin": context.workspace.base.oplin,
                "fline": context.workspace.fline,
                "flinel": context.workspace.flinel,
            }
            cpp_arrays = {"opakc": cpp_opakc, "rccemis": cpp_rcc, "oplin": cpp_oplin, "fline": cpp_fline, "flinel": cpp_flinel}
            rec_max_abs = 0.0; rec_max_rel = 0.0; rec_array = ""; rec_index = -1
            rec_max_rel_abs_at_rel = 0.0; rec_rel_array = ""; rec_rel_index = -1
            per_array = upstream_type4_shadow_summary.setdefault("per_array", {})
            for name, py_arr in py_arrays.items():
                c_arr = np.asarray(cpp_arrays[name], dtype=float)
                p_arr = np.asarray(py_arr, dtype=float)
                diff = np.abs(c_arr - p_arr)
                if diff.size:
                    flat_diff = diff.reshape(-1)
                    flat_py = p_arr.reshape(-1)
                    idx = int(np.argmax(flat_diff))
                    abs_val = float(flat_diff[idx])
                    denom = np.maximum(np.abs(flat_py), 1.0e-300)
                    rel = flat_diff / denom
                    ridx = int(np.argmax(rel)) if rel.size else idx
                    rel_val = float(rel[idx]) if rel.size else 0.0
                    rel_peak = float(rel[ridx]) if rel.size else 0.0
                    rel_peak_abs = float(flat_diff[ridx]) if flat_diff.size else 0.0
                    if abs_val > rec_max_abs:
                        rec_max_abs = abs_val; rec_max_rel = rel_val; rec_array = name; rec_index = idx
                    if rel_peak > rec_max_rel:
                        rec_max_rel = rel_peak; rec_max_rel_abs_at_rel = rel_peak_abs; rec_rel_array = name; rec_rel_index = ridx
                    arr = per_array.setdefault(name, {
                        "records_seen": 0, "max_abs_diff": 0.0, "max_rel_diff": 0.0,
                        "max_abs_record": -1, "max_abs_line_index": -1, "max_abs_flat_index": -1,
                        "max_rel_record": -1, "max_rel_line_index": -1, "max_rel_flat_index": -1,
                    })
                    arr["records_seen"] = int(arr.get("records_seen", 0) or 0) + 1
                    if abs_val > float(arr.get("max_abs_diff", 0.0) or 0.0):
                        arr["max_abs_diff"] = float(abs_val)
                        arr["max_abs_rel_at_abs"] = float(rel_val)
                        arr["max_abs_record"] = int(rec)
                        arr["max_abs_line_index"] = int(line_index)
                        arr["max_abs_flat_index"] = int(idx)
                        arr["max_abs_status_reason"] = str(status_reason)
                    if rel_peak > float(arr.get("max_rel_diff", 0.0) or 0.0):
                        arr["max_rel_diff"] = float(rel_peak)
                        arr["max_rel_abs_at_rel"] = float(rel_peak_abs)
                        arr["max_rel_record"] = int(rec)
                        arr["max_rel_line_index"] = int(line_index)
                        arr["max_rel_flat_index"] = int(ridx)
                        arr["max_rel_status_reason"] = str(status_reason)
            if not rec_rel_array:
                rec_rel_array = rec_array; rec_rel_index = rec_index; rec_max_rel_abs_at_rel = rec_max_abs
            upstream_type4_shadow_summary["records_supported"] = int(upstream_type4_shadow_summary.get("records_supported", 0) or 0) + 1
            if rec_max_abs > float(upstream_type4_shadow_summary.get("max_abs_diff", 0.0) or 0.0):
                upstream_type4_shadow_summary["max_abs_diff"] = float(rec_max_abs)
                upstream_type4_shadow_summary["max_rel_diff"] = float(rec_max_rel)
                upstream_type4_shadow_summary["max_abs_array"] = str(rec_array)
                upstream_type4_shadow_summary["max_abs_record"] = int(rec)
                upstream_type4_shadow_summary["max_abs_line_index"] = int(line_index)
                upstream_type4_shadow_summary["max_abs_flat_index"] = int(rec_index)
                upstream_type4_shadow_summary["max_abs_status_reason"] = str(status_reason)
            sample = {
                "record": int(rec), "rate_type": int(rate_type), "data_type": int(data_type), "line_index": int(line_index),
                "nb1": int(nb1), "ion_index": int(ion.ion_index), "ion_stage": int(ion.ion_stage),
                "status_reason": str(status_reason), "max_abs_diff": float(rec_max_abs), "max_rel_diff": float(rec_max_rel),
                "max_abs_array": str(rec_array), "max_abs_flat_index": int(rec_index),
                "max_rel_array": str(rec_rel_array), "max_rel_flat_index": int(rec_rel_index),
                "max_rel_abs_at_rel": float(rec_max_rel_abs_at_rel),
                "energy_eV": float(energy), "wavelength_A": float(wave),
            }
            top_abs = upstream_type4_shadow_summary.setdefault("top_abs_records", [])
            top_rel = upstream_type4_shadow_summary.setdefault("top_rel_records", [])
            top_abs.append(dict(sample)); top_abs.sort(key=lambda x: float(x.get("max_abs_diff", 0.0)), reverse=True); del top_abs[upstream_type4_shadow_top_n:]
            top_rel.append(dict(sample)); top_rel.sort(key=lambda x: float(x.get("max_rel_diff", 0.0)), reverse=True); del top_rel[upstream_type4_shadow_top_n:]
            if upstream_type4_shadow_samples is not None:
                upstream_type4_shadow_samples[:] = list(top_abs)
        except Exception as exc:
            upstream_type4_shadow_summary["records_errors"] = int(upstream_type4_shadow_summary.get("records_errors", 0) or 0) + 1
            upstream_type4_shadow_summary["last_error_type"] = type(exc).__name__
            upstream_type4_shadow_summary["last_error_message"] = str(exc)[:512]

    def _apply_python_type4_line_job(job: Mapping[str, Any]) -> None:
        """Replay one selected type-4 line record through the source Python path."""
        rec0 = int(job["record"])
        rate_type0 = int(job["rate_type"])
        header_data_type = int(job["data_type"])
        idest1_0 = int(job["idest1"])
        idest2_0 = int(job["idest2"])
        lower_0 = int(job["lower"])
        upper_0 = int(job["upper"])
        line_index_0 = int(job["line_index"])
        nb1_0 = int(job["nb1"])
        abund1_0 = float(job["abund1"])
        abund2_0 = float(job["abund2"])
        ptmp1_0 = float(job["ptmp1"])
        ptmp2_0 = float(job["ptmp2"])
        energy_0 = float(job["energy_ev"])
        width_0 = float(job["bin_width_ev"])
        result0 = evaluate(rec0, ptmp1_0, ptmp2_0, abund1_0, abund2_0)
        opakb1_0 = float(result0.opakab) * float(abund1_0)
        net_0 = float(result0.ans2) * float(abund2_0) - float(result0.ans1) * float(abund1_0)
        rcem1_0 = max(net_0 * energy_0 * XSTAR_CALC_EMISAB_ERG_PER_EV * ptmp1_0, 0.0)
        rcem2_0 = max(net_0 * energy_0 * XSTAR_CALC_EMISAB_ERG_PER_EV * ptmp2_0, 0.0)
        flinel_delta_0 = (rcem1_0 + rcem2_0) * 2.0 / width_0 / XSTAR_CALC_EMISAB_ERG_PER_EV
        if line_index_0 > 0 and line_index_0 < context.workspace.base.oplin.size:
            context.workspace.base.oplin[line_index_0] = opakb1_0
        atomic_mass_0 = _parent_element_atomic_mass(context.master, context.derived, rec0)
        natural_width_0 = 0.0
        try:
            reals_for_line_0 = context.master.record_reals(rec0)
            if len(reals_for_line_0) > 2:
                natural_width_0 = float(reals_for_line_0[2]) * 4.136e-15
        except Exception:
            natural_width_0 = 0.0
        _source_linopac_into_opakc(
            optpp=opakb1_0, rcem1=rcem1_0, rcem2=rcem2_0,
            line_energy_eV=energy_0,
            vturb_km_s=float(context.turbulent_velocity_km_s),
            temperature_1e4K=float(context.temperature_1e4K),
            atomic_mass_amu=atomic_mass_0,
            natural_width_eV=natural_width_0,
            epi=epi,
            opakc=context.workspace.base.opakc,
            rccemis=context.workspace.base.rccemis,
            ncn2=len(epi),
            diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
        )
        context.workspace.fline[0, line_index_0] = rcem1_0
        context.workspace.fline[1, line_index_0] = rcem2_0
        context.workspace.flinel[nb1_0 - 1] += flinel_delta_0
        record_traces.append(CalcEmisRecordTrace(
            rec0, rate_type0, header_data_type, ion.ion_index, ion.ion_stage,
            compact_offset, idest1_0, idest2_0, lower_0, upper_0, line_index_0,
            retained_kkkl, abund1_0, abund2_0, ptmp1_0, ptmp2_0,
            float(result0.ans1), float(result0.ans2), float(result0.ans3), float(result0.ans4), opakb1_0,
            result0.status.value, f"python_fallback_strong_line_rate_type_{rate_type0}",
        ))

    def _record_type50_rejection_sample(job: Mapping[str, Any], row: Mapping[str, Any] | None, reason: str) -> None:
        """Store compact examples of rejected Mg type-50 coarse records for summary JSON."""
        try:
            samples = profile_control.setdefault("mg_type4_type50_coarse_rejection_samples", [])
        except Exception:
            return
        if not isinstance(samples, list) or len(samples) >= 16:
            return
        item = {
            "record": int(job.get("record", -1)),
            "rate_type": int(job.get("rate_type", -1)),
            "data_type": int(job.get("data_type", -1)),
            "ion_index": int(ion.ion_index),
            "ion_stage": int(ion.ion_stage),
            "line_index": int(job.get("line_index", -1)),
            "nb1": int(job.get("nb1", -1)),
            "reason": str(reason),
        }
        if row is not None:
            item["status_code"] = int(row.get("status_code", 0))
            item["status_reason"] = str(row.get("status_reason", reason))
            item["linopac_updated_bins"] = int(row.get("linopac_updated_bins", 0))
            item["center_bin_one_based"] = int(row.get("center_bin_one_based", 0))
        samples.append(item)

    def _append_cpp_type50_trace(job: Mapping[str, Any], row: Mapping[str, Any]) -> None:
        rec0 = int(job["record"])
        line_index_0 = int(job["line_index"])
        nb1_0 = int(job["nb1"])
        record_traces.append(CalcEmisRecordTrace(
            rec0, int(job["rate_type"]), int(job["data_type"]), ion.ion_index, ion.ion_stage,
            compact_offset, int(job["idest1"]), int(job["idest2"]), int(job["lower"]), int(job["upper"]), line_index_0,
            retained_kkkl, float(job["abund1"]), float(job["abund2"]), float(job["ptmp1"]), float(job["ptmp2"]),
            float(row.get("ans1", 0.0)), float(row.get("ans2", 0.0)), float(row.get("ans3", 0.0)), float(row.get("ans4", 0.0)), float(row.get("opakb1", 0.0)),
            "evaluated", "cpp_type50_ucalc_linopac_array_update",
        ))

    def _flush_cpp_mg_type50_coarse_batch() -> None:
        if not pending_cpp_mg_type50_coarse_records:
            return
        try:
            atomic_mass = _parent_element_atomic_mass(context.master, context.derived, int(pending_cpp_mg_type50_coarse_records[0]["record"]))
            cpp_rows, _cpp_message, _cpp_stats = apply_mg_type4_type50_coarse_cpp_detailed(
                pending_cpp_mg_type50_coarse_records,
                cfrac=float(context.covering_fraction),
                hydrogen_density_cm3=float(xpx),
                turbulent_velocity_km_s=float(context.turbulent_velocity_km_s),
                temperature_1e4K=float(context.temperature_1e4K),
                atomic_mass_amu=float(atomic_mass),
                erg_per_ev=XSTAR_CALC_EMISAB_ERG_PER_EV,
                epi=epi,
                opakc=context.workspace.base.opakc,
                rccemis=context.workspace.base.rccemis,
                oplin=context.workspace.base.oplin,
                fline=context.workspace.fline,
                flinel=context.workspace.flinel,
            )
            _cpp_stats = dict(_cpp_stats)
            _cpp_stats["batches_flushed"] = 1.0
            _add_cpp_counter_totals(cpp_mg_type4_stats, _cpp_stats)
            for job, row in zip(pending_cpp_mg_type50_coarse_jobs, cpp_rows):
                status_code = int(row.get("status_code", 0))
                status_reason = str(row.get("status_reason", f"status_{status_code}"))
                if status_code == 1:
                    _append_cpp_type50_trace(job, row)
                elif status_code == 2:
                    # C++ owned the selected type-50 ucalc/scalar products, but
                    # Python still owns the source-faithful Voigt/natural-width
                    # linopac side effect.  Apply the returned values in source
                    # order without re-running ucalc.
                    _record_type50_rejection_sample(job, row, status_reason)
                    _apply_mg_type4_line_job(job, row)
                else:
                    _record_type50_rejection_sample(job, row, status_reason)
                    _apply_python_type4_line_job(job)
        except Exception:
            _add_cpp_counter_totals(cpp_mg_type4_stats, {"fallback_count": float(len(pending_cpp_mg_type50_coarse_records)), "batches_flushed": 1.0})
            cpp_mg_type4_stats["type50_coarse_cpp_fallback"] = cpp_mg_type4_stats.get("type50_coarse_cpp_fallback", 0.0) + float(len(pending_cpp_mg_type50_coarse_records))
            for job in pending_cpp_mg_type50_coarse_jobs:
                _record_type50_rejection_sample(job, None, "cpp_batch_exception")
                _apply_python_type4_line_job(job)
        finally:
            pending_cpp_mg_type50_coarse_records.clear()
            pending_cpp_mg_type50_coarse_jobs.clear()

    def _apply_mg_type4_line_job(job: Mapping[str, Any], cpp_row: Mapping[str, Any] | None) -> None:
        """Apply one source-ordered Mg line-emissivity side-effect bundle.

        This mirrors the scalar tail of the type-4 line branch.  It is kept
        intentionally small: no diagnostic-only line-opacity rows are emitted
        from the batched path unless the backend falls back to the old Python
        path in future.  Physical arrays and record traces are still updated in
        source order.
        """
        rec0 = int(job["record"])
        rate_type0 = int(job["rate_type"])
        header_data_type = int(job["data_type"])
        idest1_0 = int(job["idest1"])
        idest2_0 = int(job["idest2"])
        lower_0 = int(job["lower"])
        upper_0 = int(job["upper"])
        line_index_0 = int(job["line_index"])
        nb1_0 = int(job["nb1"])
        abund1_0 = float(job["abund1"])
        abund2_0 = float(job["abund2"])
        ptmp1_0 = float(job["ptmp1"])
        ptmp2_0 = float(job["ptmp2"])
        energy_0 = float(job["energy_ev"])
        width_0 = float(job["bin_width_ev"])
        result0 = job["result"]
        if cpp_row is not None:
            opakb1_0 = float(cpp_row["opakb1"])
            rcem1_0 = float(cpp_row["rcem1"])
            rcem2_0 = float(cpp_row["rcem2"])
            flinel_delta_0 = float(cpp_row["flinel_delta"])
        else:
            opakb1_0 = float(result0.opakab) * float(abund1_0)
            net_0 = float(result0.ans2) * float(abund2_0) - float(result0.ans1) * float(abund1_0)
            rcem1_0 = max(net_0 * energy_0 * XSTAR_CALC_EMISAB_ERG_PER_EV * ptmp1_0, 0.0)
            rcem2_0 = max(net_0 * energy_0 * XSTAR_CALC_EMISAB_ERG_PER_EV * ptmp2_0, 0.0)
            flinel_delta_0 = (rcem1_0 + rcem2_0) * 2.0 / width_0 / XSTAR_CALC_EMISAB_ERG_PER_EV
        if line_index_0 > 0 and line_index_0 < context.workspace.base.oplin.size:
            context.workspace.base.oplin[line_index_0] = opakb1_0
        atomic_mass_0 = _parent_element_atomic_mass(context.master, context.derived, rec0)
        natural_width_0 = 0.0
        try:
            reals_for_line_0 = context.master.record_reals(rec0)
            if len(reals_for_line_0) > 2:
                natural_width_0 = float(reals_for_line_0[2]) * 4.136e-15
        except Exception:
            natural_width_0 = 0.0
        _apply_linopac_with_cpp_gate(
            optpp=opakb1_0,
            rcem1=rcem1_0,
            rcem2=rcem2_0,
            line_energy_eV=energy_0,
            vturb_km_s=float(context.turbulent_velocity_km_s),
            temperature_1e4K=float(context.temperature_1e4K),
            atomic_mass_amu=atomic_mass_0,
            natural_width_eV=natural_width_0,
        )
        context.workspace.fline[0, line_index_0] = rcem1_0
        context.workspace.fline[1, line_index_0] = rcem2_0
        context.workspace.flinel[nb1_0 - 1] += flinel_delta_0
        record_traces.append(CalcEmisRecordTrace(
            rec0, rate_type0, header_data_type, ion.ion_index, ion.ion_stage,
            compact_offset, idest1_0, idest2_0, lower_0, upper_0, line_index_0,
            retained_kkkl, abund1_0, abund2_0, ptmp1_0, ptmp2_0,
            float(result0.ans1), float(result0.ans2), float(result0.ans3), float(result0.ans4), opakb1_0,
            result0.status.value, f"batched_strong_line_rate_type_{rate_type0}",
        ))

    def _flush_cpp_mg_type4_batch() -> None:
        if not pending_cpp_mg_type4_records:
            return
        try:
            cpp_rows, _cpp_message, _cpp_stats = build_mg_type4_line_emissivity_cpp_detailed(
                pending_cpp_mg_type4_records,
                erg_per_ev=XSTAR_CALC_EMISAB_ERG_PER_EV,
            )
            _cpp_stats = dict(_cpp_stats)
            _cpp_stats["batches_flushed"] = 1.0
            _add_cpp_counter_totals(cpp_mg_type4_stats, _cpp_stats)
            for job, cpp_row in zip(pending_cpp_mg_type4_jobs, cpp_rows):
                _apply_mg_type4_line_job(job, cpp_row)
        except Exception:
            _add_cpp_counter_totals(cpp_mg_type4_stats, {
                "fallback_count": float(len(pending_cpp_mg_type4_records)),
                "batches_flushed": 1.0,
            })
            for job in pending_cpp_mg_type4_jobs:
                _apply_mg_type4_line_job(job, None)
        finally:
            pending_cpp_mg_type4_records.clear()
            pending_cpp_mg_type4_jobs.clear()

    for rate_type, rec in record_sequence:
        if int(rate_type) != 4:
            if pending_cpp_mg_type50_coarse_records:
                _flush_cpp_mg_type50_coarse_batch()
            if pending_cpp_mg_type4_records:
                _flush_cpp_mg_type4_batch()
        visited += 1
        _record_t0 = time.perf_counter() if is_mg_profile else 0.0
        header = context.master.header(rec)
        ints = context.master.record_integers(rec)

        if rate_type == 7 and len(ints) >= 4:
            idest1 = int(ints[-2])
            idest2 = ion.nlev + int(ints[-4]) - 1
            retained_kkkl = int(context.derived.npconi2[rec])
            if 0 < retained_kkkl <= int(context.derived.ncsvn) and idest1 > 0:
                wave = float(context.rrc_wavelength_angstrom[retained_kkkl])
                if wave > float(epi[0]) and wave < float(epi[-1]):
                    energy = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / wave
                    nb1 = nbinc(energy, epi, len(epi))
                    if _feature_is_ranked(continuum_rank_table, retained_kkkl, nb1):
                        lower, upper = idest1 + compact_offset, idest2 + compact_offset
                        abund1 = float(compact_xileve[lower]) * element_abundance
                        abund2 = float(compact_xileve[upper]) * element_abundance
                        tau1, tau2 = context.escape.continuum_taus(retained_kkkl)
                        tau1 = 0.0 if tau1 is None else float(tau1)
                        tau2 = 0.0 if tau2 is None else float(tau2)
                        ptmp1 = pescv(tau1) * (1.0 - context.covering_fraction)
                        ptmp2 = pescv(tau2) * (1.0 - context.covering_fraction) + 2.0 * pescv(tau1 + tau2) * context.covering_fraction
                        result = evaluate(rec, ptmp1, ptmp2, abund1, abund2)
                        context.workspace.base.opakab[retained_kkkl] = result.opakab
                        _bin_continuum_opacity_for_step(context, retained_kkkl, result.opakab, epi)
                        record_traces.append(CalcEmisRecordTrace(
                            rec, rate_type, header.data_type, ion.ion_index, ion.ion_stage,
                            compact_offset, idest1, idest2, lower, upper, retained_kkkl,
                            retained_kkkl, abund1, abund2, ptmp1, ptmp2,
                            result.ans1, result.ans2, result.ans3, result.ans4, result.opakab,
                            result.status.value, "strong_rrc_rate_type_7",
                        ))

        if rate_type == 42 and len(ints) >= 4:
            idest1 = int(ints[-2])
            idest2 = int(ints[-4])
            if idest1 > 0:
                if retained_kkkl <= 0 or retained_kkkl > int(context.derived.ncsvn):
                    raise CalcEmisPortError("rate type 42 reached before a valid retained kkkl continuum pointer")
                lower, upper = idest1 + compact_offset, idest2 + compact_offset
                abund1 = float(compact_xileve[lower]) * element_abundance
                abund2 = float(compact_xileve[upper]) * element_abundance
                tau1, tau2 = context.escape.continuum_taus(retained_kkkl)
                tau1 = 0.0 if tau1 is None else float(tau1)
                tau2 = 0.0 if tau2 is None else float(tau2)
                ptmp1 = (1.0 - context.covering_fraction) / 2.0
                ptmp2 = (1.0 + context.covering_fraction) / 2.0
                result = evaluate(rec, ptmp1, ptmp2, abund1, abund2)
                context.workspace.base.opakab[retained_kkkl] = result.opakab
                _bin_continuum_opacity_for_step(context, retained_kkkl, result.opakab, epi)
                record_traces.append(CalcEmisRecordTrace(
                    rec, rate_type, header.data_type, ion.ion_index, ion.ion_stage,
                    compact_offset, idest1, idest2, lower, upper, retained_kkkl,
                    retained_kkkl, abund1, abund2, ptmp1, ptmp2,
                    result.ans1, result.ans2, result.ans3, result.ans4, result.opakab,
                    result.status.value, "rate_type_42_retained_continuum_pointer",
                ))

        if rate_type == 9 and len(ints) >= 2:
            reals = context.master.record_reals(rec)
            idest1, idest2 = int(ints[0]), int(ints[1])
            if len(reals) and float(reals[0]) > 0.01 and 0 < idest1 < ion.nlev and 0 < idest2 < ion.nlev:
                if retained_kkkl <= 0 or retained_kkkl > int(context.derived.ncsvn):
                    raise CalcEmisPortError("rate type 9 prepass reached before a valid retained kkkl continuum pointer")
                lower, upper = idest1 + compact_offset, idest2 + compact_offset
                abund1 = float(compact_xileve[lower]) * element_abundance * xpx
                abund2 = float(compact_xileve[upper]) * element_abundance * xpx
                ptmp1 = pescl(0.0) * (1.0 - context.covering_fraction)
                ptmp2 = pescl(0.0) * (1.0 - context.covering_fraction) + 2.0 * pescl(0.0) * context.covering_fraction
                result = evaluate(rec, ptmp1, ptmp2, abund1, abund2)
                context.workspace.base.opakab[retained_kkkl] = result.opakab
                _bin_continuum_opacity_for_step(context, retained_kkkl, result.opakab, epi)
                record_traces.append(CalcEmisRecordTrace(
                    rec, rate_type, header.data_type, ion.ion_index, ion.ion_stage,
                    compact_offset, idest1, idest2, lower, upper, retained_kkkl,
                    retained_kkkl, abund1, abund2, ptmp1, ptmp2,
                    result.ans1, result.ans2, result.ans3, result.ans4, result.opakab,
                    result.status.value, "rate_type_9_prepass",
                ))

        if rate_type in (4, 9) and len(ints) >= 2:
            line_meta = mg_line_table.get(int(rec)) if mg_line_table else None
            if line_meta is not None:
                if not bool(line_meta.get("valid", False)):
                    raise CalcEmisPortError(str(line_meta.get("reason", "invalid Mg line endpoint")))
                idest1 = int(line_meta["idest1"])
                idest2 = int(line_meta["idest2"])
                line_index = int(line_meta["line_index"])
                wave = float(line_meta["wave"])
                energy = float(line_meta["energy"])
                nb1 = int(line_meta["nb1"])
                ranked = bool(line_meta["ranked"])
                e1 = float(line_meta["e1"])
                e2 = float(line_meta["e2"])
                lower = int(line_meta["lower_local"]) + compact_offset
                upper = int(line_meta["upper_local"]) + compact_offset
            else:
                idest1, idest2 = int(ints[0]), int(ints[1])
                line_index = int(context.derived.nplini[rec])
                ranked = False
                if line_index and line_index <= int(context.derived.nlsvn) and idest1 > 0:
                    wave = float(context.line_wavelength_angstrom[line_index])
                    energy = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / (wave + XSTAR_CALC_EMIS_LINE_WAVELENGTH_FLOOR)
                    nb1 = nbinc(energy, epi, len(epi))
                    ranked = bool(_feature_is_ranked(line_rank_table, line_index, nb1))
                    if ranked:
                        if not (1 <= idest2 <= ion.nlev):
                            raise CalcEmisPortError(f"line endpoint {idest2} outside ion nlev={ion.nlev}")
                        e1 = levels.require(idest1).energy_ev
                        e2 = levels.require(idest2).energy_ev
                        if e1 < e2:
                            lower, upper = idest1 + compact_offset, idest2 + compact_offset
                        else:
                            lower, upper = idest2 + compact_offset, idest1 + compact_offset
            if line_index and line_index <= int(context.derived.nlsvn) and idest1 > 0:
                if ranked:
                    tau1, tau2 = context.escape.line_taus(line_index)
                    tau1 = 0.0 if tau1 is None else float(tau1)
                    tau2 = 0.0 if tau2 is None else float(tau2)
                    abund1 = float(compact_xileve[lower]) * xpx * element_abundance
                    abund2 = float(compact_xileve[upper]) * xpx * element_abundance
                    ptmp1 = pescl(tau1) * (1.0 - context.covering_fraction)
                    ptmp2 = pescl(tau2) * (1.0 - context.covering_fraction) + 2.0 * pescl(tau1 + tau2) * context.covering_fraction
                    result = evaluate(rec, ptmp1, ptmp2, abund1, abund2)
                    width = float(epi[nb1] - epi[max(1, nb1 - 1) - 1])
                    cpp_line_row = None
                    if use_cpp_mg_type4_line and int(rate_type) == 4 and int(header.data_type) == 50:
                        if pending_cpp_mg_type4_records:
                            _flush_cpp_mg_type4_batch()
                        reals_for_cpp = context.master.record_reals(rec)
                        wavelength_cpp = abs(float(reals_for_cpp[0])) if len(reals_for_cpp) > 0 else 0.0
                        aij_cpp = float(reals_for_cpp[2]) if len(reals_for_cpp) > 2 else 0.0
                        natural_width_cpp = aij_cpp * 4.136e-15
                        source_upper_id = int(idest1)
                        source_lower_id = int(idest2)
                        if float(e1) < float(e2):
                            source_upper_id, source_lower_id = int(idest2), int(idest1)
                        source_upper_weight = float(levels.weight(source_upper_id))
                        source_lower_weight = float(levels.weight(source_lower_id))
                        bremsa_nb1 = float(_brem_for_cpp[nb1]) if int(nb1) >= 0 and int(nb1) < len(_brem_for_cpp) else 0.0
                        pending_cpp_mg_type50_coarse_records.append({
                            "record": int(rec), "data_type": int(header.data_type), "ion_index": int(ion.ion_index), "ion_stage": int(ion.ion_stage),
                            "line_index": int(line_index), "nb1": int(nb1), "wavelength_A": float(wavelength_cpp), "aij_s": float(aij_cpp),
                            "source_upper_weight": float(source_upper_weight), "source_lower_weight": float(source_lower_weight),
                            "endpoint_energy_ev": abs(float(e2) - float(e1)), "bremsa_nb1": float(bremsa_nb1),
                            "ptmp1": float(ptmp1), "ptmp2": float(ptmp2), "abund1": float(abund1), "abund2": float(abund2),
                            "bin_width_ev": float(width), "natural_width_ev": float(natural_width_cpp),
                        })
                        pending_cpp_mg_type50_coarse_jobs.append({
                            "record": int(rec), "rate_type": int(rate_type), "data_type": int(header.data_type), "idest1": int(idest1), "idest2": int(idest2),
                            "lower": int(lower), "upper": int(upper), "line_index": int(line_index), "nb1": int(nb1),
                            "abund1": float(abund1), "abund2": float(abund2), "ptmp1": float(ptmp1), "ptmp2": float(ptmp2),
                            "energy_ev": float(energy), "bin_width_ev": float(width), "result": result,
                        })
                        if is_mg_profile:
                            _elapsed = time.perf_counter() - _record_t0
                            _record_type_elapsed["line"] = _record_type_elapsed.get("line", 0.0) + _elapsed
                            _rate_type_elapsed[int(rate_type)] = _rate_type_elapsed.get(int(rate_type), 0.0) + _elapsed
                        continue
                    if use_cpp_mg_type4_line and int(rate_type) == 4:
                        if pending_cpp_mg_type50_coarse_records:
                            _flush_cpp_mg_type50_coarse_batch()
                        pending_cpp_mg_type4_records.append({
                            "record": int(rec),
                            "data_type": int(header.data_type),
                            "ion_index": int(ion.ion_index),
                            "ion_stage": int(ion.ion_stage),
                            "line_index": int(line_index),
                            "nb1": int(nb1),
                            "ans1": float(result.ans1),
                            "ans2": float(result.ans2),
                            "opakab": float(result.opakab),
                            "abund1": float(abund1),
                            "abund2": float(abund2),
                            "ptmp1": float(ptmp1),
                            "ptmp2": float(ptmp2),
                            "energy_ev": float(energy),
                            "bin_width_ev": float(width),
                        })
                        pending_cpp_mg_type4_jobs.append({
                            "record": int(rec),
                            "rate_type": int(rate_type),
                            "data_type": int(header.data_type),
                            "idest1": int(idest1),
                            "idest2": int(idest2),
                            "lower": int(lower),
                            "upper": int(upper),
                            "line_index": int(line_index),
                            "nb1": int(nb1),
                            "abund1": float(abund1),
                            "abund2": float(abund2),
                            "ptmp1": float(ptmp1),
                            "ptmp2": float(ptmp2),
                            "energy_ev": float(energy),
                            "bin_width_ev": float(width),
                            "result": result,
                        })
                        if is_mg_profile:
                            _elapsed = time.perf_counter() - _record_t0
                            _record_type_elapsed["line"] = _record_type_elapsed.get("line", 0.0) + _elapsed
                            _rate_type_elapsed[int(rate_type)] = _rate_type_elapsed.get(int(rate_type), 0.0) + _elapsed
                        continue
                    # Source handoff correction, v0.5.05.
                    #
                    # In the Fortran line branch, ucalc receives caller-owned
                    # ``opakc``/``opakcont`` and may update the continuum-grid
                    # opacity while the caller also stores the per-line opacity
                    # in ``oplin``.  The previous Python translation preserved
                    # the emitted line flux handoff but did not carry the line
                    # opacity into either ``oplin`` or the continuum-grid
                    # ``opakc`` seen by ``step.f90``.  That left the active
                    # kappa above ``ectt`` nearly zero, so the radial Courant
                    # limiter skipped the intermediate column substeps.  Bin the
                    # line opacity at the same source ``nb1`` used for ``flinel``.
                    if cpp_line_row is not None:
                        opakb1 = float(cpp_line_row["opakb1"])
                        net = float(cpp_line_row["net"])
                        rcem1 = float(cpp_line_row["rcem1"])
                        rcem2 = float(cpp_line_row["rcem2"])
                        flinel_delta = float(cpp_line_row["flinel_delta"])
                    else:
                        opakb1 = float(result.opakab) * float(abund1)
                        net = result.ans2 * abund2 - result.ans1 * abund1
                        rcem1 = max(net * energy * XSTAR_CALC_EMISAB_ERG_PER_EV * ptmp1, 0.0)
                        rcem2 = max(net * energy * XSTAR_CALC_EMISAB_ERG_PER_EV * ptmp2, 0.0)
                        flinel_delta = (rcem1 + rcem2) * 2.0 / width / XSTAR_CALC_EMISAB_ERG_PER_EV
                    if line_index > 0 and line_index < context.workspace.base.oplin.size:
                        context.workspace.base.oplin[line_index] = opakb1
                    atomic_mass = _parent_element_atomic_mass(context.master, context.derived, rec)
                    natural_width = 0.0
                    try:
                        reals_for_line = context.master.record_reals(rec)
                        if len(reals_for_line) > 2:
                            natural_width = float(reals_for_line[2]) * 4.136e-15
                    except Exception:
                        natural_width = 0.0
                    _upstream_type4_shadow_before = None
                    if upstream_type4_shadow_enabled and int(rate_type) == 4:
                        _upstream_type4_shadow_before = {
                            "opakc": context.workspace.base.opakc.copy(),
                            "rccemis": context.workspace.base.rccemis.copy(),
                            "oplin": context.workspace.base.oplin.copy(),
                            "fline": context.workspace.fline.copy(),
                            "flinel": context.workspace.flinel.copy(),
                        }
                    _line_opakc_before = context.workspace.base.opakc.copy() if diagnostics_enabled else None
                    _linopac_diag = _source_linopac_into_opakc(
                        optpp=opakb1,
                        rcem1=rcem1,
                        rcem2=rcem2,
                        line_energy_eV=energy,
                        vturb_km_s=float(context.turbulent_velocity_km_s),
                        temperature_1e4K=float(context.temperature_1e4K),
                        atomic_mass_amu=atomic_mass,
                        natural_width_eV=natural_width,
                        epi=epi,
                        opakc=context.workspace.base.opakc,
                        rccemis=context.workspace.base.rccemis,
                        ncn2=len(epi),
                        diagnostic_bins_one_based=XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS,
                    )
                    _line_opakc_after = context.workspace.base.opakc
                    _target_add = ({
                        str(_b): (float(_line_opakc_after[_b - 1] - _line_opakc_before[_b - 1]) if _line_opakc_before is not None and 0 < _b <= _line_opakc_after.size else 0.0)
                        for _b in XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS
                    } if diagnostics_enabled else {})
                    _diag_rows = getattr(context.workspace, "line_opacity_bin_diagnostics", None)
                    if _diag_rows is None:
                        _diag_rows = []
                        setattr(context.workspace, "line_opacity_bin_diagnostics", _diag_rows)
                    if diagnostics_enabled and int(line_index) in XSTAR_TYPE50_LINE_STRENGTH_TARGET_LINES and len(_diag_rows) < XSTAR_LINE_OPACITY_DIAGNOSTIC_MAX_ROWS:
                        try:
                            _rec_reals = tuple(float(x) for x in context.master.record_reals(rec))
                        except Exception:
                            _rec_reals = ()
                        try:
                            _rec_ints = tuple(int(x) for x in context.master.record_integers(rec))
                        except Exception:
                            _rec_ints = ()
                        _local_lower = int(idest1 if e1 <= e2 else idest2)
                        _local_upper = int(idest2 if e1 <= e2 else idest1)
                        _lower_level = levels.get(_local_lower)
                        _upper_level = levels.get(_local_upper)
                        _lower_weight = float(getattr(_lower_level, "statistical_weight", 0.0) or 0.0)
                        _upper_weight = float(getattr(_upper_level, "statistical_weight", 0.0) or 0.0)
                        _flin = result.diagnostics.get("f_osc_from_A", result.diagnostics.get("oscillator_strength", result.diagnostics.get("flin", 0.0)))
                        _aij = result.diagnostics.get("A_s^-1", result.diagnostics.get("aij_s^-1", result.diagnostics.get("aij", 0.0)))
                        try:
                            _flin = float(_flin or 0.0)
                        except Exception:
                            _flin = 0.0
                        try:
                            _aij = float(_aij or 0.0)
                        except Exception:
                            _aij = 0.0
                        try:
                            _vtherm = ((float(context.turbulent_velocity_km_s) * 1.0e5) ** 2 + (1.29e6 / max((float(atomic_mass) / max(float(context.temperature_1e4K), 1.0e-48)) ** 0.5, 1.0e-48)) ** 2) ** 0.5
                        except Exception:
                            _vtherm = 0.0
                        _diag_rows.append({
                            "row_kind": "type50_line_strength_mapping_track",
                            "diagnostic_priority": "pre_linopac_opakb1_source_mapping",
                            "line_index": int(line_index),
                            "record": int(rec),
                            "parent_record": int(getattr(header, "parent_record", 0) or 0),
                            "next_record": int(getattr(header, "next_record", 0) or 0),
                            "ltyp": int(header.data_type),
                            "lrtyp": int(rate_type),
                            "idest1": int(idest1),
                            "idest2": int(idest2),
                            "lower_level_id_local": int(_local_lower),
                            "upper_level_id_local": int(_local_upper),
                            "lower_compact": int(lower),
                            "upper_compact": int(upper),
                            "lower_statistical_weight": float(_lower_weight),
                            "upper_statistical_weight": float(_upper_weight),
                            "source_upper_id_after_energy_swap": int(result.diagnostics.get("source_upper_id_after_energy_swap", 0) or 0),
                            "source_lower_id_after_energy_swap": int(result.diagnostics.get("source_lower_id_after_energy_swap", 0) or 0),
                            "source_upper_statistical_weight": float(result.diagnostics.get("source_upper_statistical_weight", 0.0) or 0.0),
                            "source_lower_statistical_weight": float(result.diagnostics.get("source_lower_statistical_weight", 0.0) or 0.0),
                            "source_swapped_endpoints_for_type50_flin": bool(result.diagnostics.get("source_swapped_endpoints_for_type50_flin", False)),
                            "lower_energy_eV": float(e1 if e1 <= e2 else e2),
                            "upper_energy_eV": float(e2 if e1 <= e2 else e1),
                            "flin_as_read_from_ATDB_or_A": float(_flin),
                            "aij_s_minus1": float(_aij),
                            "elin_eV": float(energy),
                            "wavelength_A": float(wave),
                            "vtherm_cm_s": float(_vtherm),
                            "sigma_cm2": float(result.opakab),
                            "sigvtherm_cm2": float(result.opakab),
                            "abund1": float(abund1),
                            "abund2": float(abund2),
                            "opakab": float(result.opakab),
                            "opakb1": float(opakb1),
                            "tau0_backward": float(tau1),
                            "tau0_forward": float(tau2),
                            "ans1_photoexcitation_s_minus1": float(result.ans1),
                            "ans2_escaped_decay_s_minus1": float(result.ans2),
                            "record_reals": list(_rec_reals[:12]),
                            "record_integers": list(_rec_ints[:12]),
                            "working_hypothesis": "compare 410/411,119/120,1983/1984 flin/statistical-weight/opakb1 before linopac; doublet inversion here cannot be fixed by linopac opsum/sume",
                        })
                    if diagnostics_enabled and (any(abs(v) > 0.0 for v in _target_add.values()) or int(_linopac_diag.get("center_bin_one_based", 0)) in XSTAR_LINE_OPACITY_DIAGNOSTIC_BINS):
                        _rows = _diag_rows
                        if len(_rows) < XSTAR_LINE_OPACITY_DIAGNOSTIC_MAX_ROWS:
                            _rows.append({
                                "row_kind": "linopac_selected_bin_diagnostic",
                                "record": int(rec),
                                "line_index": int(line_index),
                                "ion_index": int(ion.ion_index),
                                "ion_stage": int(ion.ion_stage),
                                "rate_type": int(rate_type),
                                "data_type": int(header.data_type),
                                "idest1": int(idest1),
                                "idest2": int(idest2),
                                "lower_compact": int(lower),
                                "upper_compact": int(upper),
                                "abund1": float(abund1),
                                "abund2": float(abund2),
                                "elin_eV": float(energy),
                                "e0_eV": float(_linopac_diag.get("e0_eV", energy)),
                                "nbinc": int(nb1),
                                "oppp": float(opakb1),
                                "opakb1": float(opakb1),
                                "natural_width_eV": float(natural_width),
                                "atomic_mass_amu": float(atomic_mass),
                                "vturb_km_s": float(context.turbulent_velocity_km_s),
                                "temperature_1e4K": float(context.temperature_1e4K),
                                "target_bin_additions": dict(_target_add),
                                "final_contribution_to_opakc_3877": float(_target_add.get("3877", 0.0)),
                                "opsum_sume_track_priority": "line_410_411" if int(line_index) in (410, 411) else "other_line",
                                "python_vs_fortran_opsum_sume_contract": "compare linopac_source_opsum_over_sume_by_bin['3877'] with instrumented Fortran linopac.f90 opsum/sume for the same line",
                                **{f"linopac_{k}": v for k, v in _linopac_diag.items()},
                            })
                    context.workspace.fline[0, line_index] = rcem1
                    context.workspace.fline[1, line_index] = rcem2
                    context.workspace.flinel[nb1 - 1] += flinel_delta
                    _maybe_probe_upstream_type4_shadow(
                        rec=int(rec), rate_type=int(rate_type), data_type=int(header.data_type),
                        line_index=int(line_index), nb1=int(nb1), idest1=int(idest1), idest2=int(idest2),
                        lower=int(lower), upper=int(upper), e1=float(e1), e2=float(e2), energy=float(energy),
                        wave=float(wave), width=float(width), ptmp1=float(ptmp1), ptmp2=float(ptmp2),
                        abund1=float(abund1), abund2=float(abund2), result=result, opakb1=float(opakb1),
                        rcem1=float(rcem1), rcem2=float(rcem2), flinel_delta=float(flinel_delta),
                        natural_width=float(natural_width), atomic_mass=float(atomic_mass),
                        py_before=_upstream_type4_shadow_before,
                    )
                    record_traces.append(CalcEmisRecordTrace(
                        rec, rate_type, header.data_type, ion.ion_index, ion.ion_stage,
                        compact_offset, idest1, idest2, lower, upper, line_index,
                        retained_kkkl, abund1, abund2, ptmp1, ptmp2,
                        result.ans1, result.ans2, result.ans3, result.ans4, opakb1,
                        result.status.value, f"strong_line_rate_type_{rate_type}",
                    ))

        if is_mg_profile:
            _elapsed = time.perf_counter() - _record_t0
            if int(rate_type) in (4, 9):
                _kind = "line"
            elif int(rate_type) == 7:
                _kind = "rrc"
            elif int(rate_type) == 42:
                _kind = "continuum"
            else:
                _kind = "other"
            _record_type_elapsed[_kind] = _record_type_elapsed.get(_kind, 0.0) + _elapsed
            _rate_type_elapsed[int(rate_type)] = _rate_type_elapsed.get(int(rate_type), 0.0) + _elapsed

    _flush_cpp_mg_type50_coarse_batch()
    _flush_cpp_mg_type4_batch()

    if any(float(v) != 0.0 for v in cpp_mg_type4_stats.values()):
        record_profile_event(
            profile_control,
            "calc_emis_all.element.mg_type4_cpp_kernel",
            float(cpp_mg_type4_stats.get("packing_seconds", 0.0)) + float(cpp_mg_type4_stats.get("cpp_kernel_seconds", 0.0)),
            emit_progress=bool(profile_control.get("profile_backend_calls", False)),
            element_z=int(ion.element_z),
            ion_stage=int(ion.ion_stage),
            ion_index=int(ion.ion_index),
            source_routine="libxstar_rates.so:xstar_rates_build_mg_type4_line_emissivity",
            records_batched=float(cpp_mg_type4_stats.get("records_batched", 0.0)),
            cpp_calls=float(cpp_mg_type4_stats.get("cpp_calls", 0.0)),
            packing_seconds=float(cpp_mg_type4_stats.get("packing_seconds", 0.0)),
            cpp_kernel_seconds=float(cpp_mg_type4_stats.get("cpp_kernel_seconds", 0.0)),
            fallback_count=float(cpp_mg_type4_stats.get("fallback_count", 0.0)),
            emitted_matrix_terms=float(cpp_mg_type4_stats.get("emitted_matrix_terms", 0.0)),
            batches_flushed=float(cpp_mg_type4_stats.get("batches_flushed", 0.0)),
            linopac_cpp_calls=float(cpp_mg_type4_stats.get("linopac_cpp_calls", 0.0)),
            linopac_cpp_updated_bins=float(cpp_mg_type4_stats.get("linopac_cpp_updated_bins", 0.0)),
            type50_coarse_cpp_applied=float(cpp_mg_type4_stats.get("type50_coarse_cpp_applied", 0.0)),
            type50_coarse_cpp_full_applied=float(cpp_mg_type4_stats.get("type50_coarse_cpp_full_applied", 0.0)),
            type50_coarse_cpp_hybrid_applied=float(cpp_mg_type4_stats.get("type50_coarse_cpp_hybrid_applied", 0.0)),
            type50_coarse_cpp_fallback=float(cpp_mg_type4_stats.get("type50_coarse_cpp_fallback", 0.0)),
            type50_reason_full_cpp_applied=float(cpp_mg_type4_stats.get("type50_reason_full_cpp_applied", 0.0)),
            type50_reason_linopac_voigt_python_fallback=float(cpp_mg_type4_stats.get("type50_reason_linopac_voigt_python_fallback", 0.0)),
            type50_reason_unsupported_data_type=float(cpp_mg_type4_stats.get("type50_reason_unsupported_data_type", 0.0)),
            type50_reason_linopac_cpp_failure=float(cpp_mg_type4_stats.get("type50_reason_linopac_cpp_failure", 0.0)),
            type50_reason_invalid_or_nonfinite_input=float(cpp_mg_type4_stats.get("type50_reason_invalid_or_nonfinite_input", 0.0)),
            status="cpp_or_fallback",
        )

    if is_mg_profile:
        _ion_elapsed = time.perf_counter() - _ion_t0
        record_profile_event(
            profile_control,
            "calc_emis_all.element.ion_total",
            _ion_elapsed,
            emit_progress=progress_callback,
            element_z=int(ion.element_z),
            ion_stage=int(ion.ion_stage),
            ion_index=int(ion.ion_index),
            source_routine="calc_emis_ion",
        )
        for _kind, _elapsed in sorted(_record_type_elapsed.items()):
            component = {
                "line": "calc_emis_all.element.line_emissivity",
                "rrc": "calc_emis_all.element.rrc_emissivity",
                "continuum": "calc_emis_all.element.continuum_opacity_emissivity",
            }.get(_kind, "calc_emis_all.element.other_record_loop")
            record_profile_event(
                profile_control,
                component,
                _elapsed,
                emit_progress=progress_callback,
                element_z=int(ion.element_z),
                ion_stage=int(ion.ion_stage),
                ion_index=int(ion.ion_index),
                record_type=_kind,
                source_routine="calc_emis_ion",
            )
        if is_mg_forensic_profile:
            for _rtype, _elapsed in sorted(_rate_type_elapsed.items()):
                record_profile_event(
                    profile_control,
                    "calc_emis_all.element.by_rate_type",
                    _elapsed,
                    emit_progress=progress_callback,
                    element_z=int(ion.element_z),
                    ion_stage=int(ion.ion_stage),
                    ion_index=int(ion.ion_index),
                    record_type=int(_rtype),
                    source_routine="calc_emis_ion",
                )

    return CalcEmisIonTrace(
        ion_record=ion.ion_record, ion_index=ion.ion_index, ion_stage=ion.ion_stage,
        nlev=ion.nlev, compact_offset=compact_offset, active=True,
        n_records_visited=visited, n_ucalc_calls=calls,
    )


def calc_emis_element(
    context: CalcEmisContext,
    *,
    element_record: int,
    element_z: int,
    element_abundance: float,
    ions: Sequence[_IonDescriptor],
    compact_xileve: np.ndarray,
    xpx: float,
    xh0: float,
    xh1: float,
    line_rank_table: np.ndarray,
    continuum_rank_table: np.ndarray,
    leveltemp_workspace: UCalcLevelTable,
    record_traces: list[CalcEmisRecordTrace],
    epi: Optional[np.ndarray] = None,
) -> CalcEmisElementTrace:
    ipmat = 0
    ion_traces: list[CalcEmisIonTrace] = []
    for ion in ions:
        active = context.min_stage(element_z) <= ion.ion_stage <= context.max_stage(element_z)
        if active:
            trace = calc_emis_ion(
                context, ion=ion, element_abundance=element_abundance,
                compact_xileve=compact_xileve, compact_offset=ipmat,
                xpx=xpx, xh0=xh0, xh1=xh1,
                line_rank_table=line_rank_table, continuum_rank_table=continuum_rank_table,
                leveltemp_workspace=leveltemp_workspace, record_traces=record_traces,
                epi=epi,
            )
        else:
            trace = CalcEmisIonTrace(
                ion_record=ion.ion_record, ion_index=ion.ion_index, ion_stage=ion.ion_stage,
                nlev=ion.nlev, compact_offset=ipmat, active=False,
                n_records_visited=0, n_ucalc_calls=0,
            )
        ion_traces.append(trace)
        ipmat += ion.nlev - 1
    return CalcEmisElementTrace(
        element_record=element_record, element_z=element_z, abundance=element_abundance,
        abundant=True, compact_population_count=ipmat + 1,
        compact_xileve=tuple(float(v) for v in compact_xileve[1:ipmat + 2]),
        ion_traces=tuple(ion_traces),
    )


class _TraceSink(list):
    """List-like sink used in production runs to avoid retaining trace rows."""
    def append(self, value: Any) -> None:  # type: ignore[override]
        return None


def calc_emis_all(context: CalcEmisContext) -> CalcEmisResult:
    """Execute ``calc_emis_all.f90`` in literal source order."""
    epi, bremsa, _ = _high_resolution_radiation(context.radiation)
    n = len(epi)
    context.workspace.validate(
        n_lines=int(context.derived.nlsvn), n_continua=int(context.derived.ncsvn), n_energy=n,
    )
    if len(context.line_wavelength_angstrom) <= int(context.derived.nlsvn):
        raise CalcEmisPortError("line wavelength array lacks one-based entries")
    if len(context.rrc_wavelength_angstrom) <= int(context.derived.ncsvn):
        raise CalcEmisPortError("RRC wavelength array lacks one-based entries")

    # Ranking consumes the calc_emisab products before continuum reset.
    profile_control = getattr(context, "profile_control", None) or {}
    progress_callback = getattr(context, "progress_callback", None)
    with profile_component(
        profile_control,
        "calc_emis_all.rank_features",
        emit_progress=progress_callback,
        source_routine="rlbin/build_feature_rank_tables",
    ):
        line_rank, continuum_rank, rank_traces, active_feature_summary = build_feature_rank_tables(context, epi)

    xpx = resolve_calc_emis_density(
        xpx=context.hydrogen_density_cm3, pressure=context.pressure_dyn_cm2,
        t_1e4=context.temperature_1e4K, xee=context.electron_fraction_xee,
        lcdd=context.density_control_lcdd,
    )
    xnx = xpx * context.electron_fraction_xee
    thomson = xnx * XSTAR_THOMSON_CROSS_SECTION_CM2 * max(0.0, 1.0 - context.covering_fraction)
    context.workspace.base.rccemis[:, :n] = 0.0
    context.workspace.base.opakc[:n] = thomson
    context.workspace.base.opakcont[:n] = thomson

    h_abundance = context.abundance(1)
    h_ground = _one_based_array_value(context.xilevg, 1, "xilevg")
    xh0 = xpx * h_ground * h_abundance
    xh1 = xpx * (1.0 - h_ground) * h_abundance
    leveltemp = _copy_or_initialize_leveltemp(context.initial_leveltemp_workspace)
    retain_traces = bool(getattr(context, "retain_traces", True))
    element_traces: list[CalcEmisElementTrace] = []
    record_traces: list[CalcEmisRecordTrace] | _TraceSink = [] if retain_traces else _TraceSink()

    shared = _as_emisab_context(context)
    active_element_filter = {int(z) for z in (getattr(context, "active_element_z", None) or ()) if int(z) > 0}
    element_record = int(context.derived.npfirst[11])
    while element_record:
        ints = context.master.record_integers(element_record)
        if len(ints) < 1:
            raise CalcEmisPortError(f"element record {element_record} has no integer payload")
        z = int(ints[0])
        abundance = context.abundance(z) if z > 0 else 0.0
        if active_element_filter and z not in active_element_filter:
            if retain_traces:
                element_traces.append(CalcEmisElementTrace(
                    element_record=element_record, element_z=z, abundance=abundance,
                    abundant=False, compact_population_count=0, compact_xileve=(), ion_traces=(),
                ))
        elif abundance > XSTAR_CALC_EMISAB_ABUNDANCE_FLOOR:
            ions = _iter_ion_descriptors(shared, element_record, z)
            compact_x, _, _ = _compact_element_populations(shared, ions)
            with profile_component(
                profile_control, "calc_emis_all.element",
                emit_progress=progress_callback, element_z=int(z),
            ):
                trace = calc_emis_element(
                    context, element_record=element_record, element_z=z,
                    element_abundance=abundance, ions=ions, compact_xileve=compact_x,
                    xpx=xpx, xh0=xh0, xh1=xh1,
                    line_rank_table=line_rank, continuum_rank_table=continuum_rank,
                    leveltemp_workspace=leveltemp, record_traces=record_traces,
                    epi=epi,
                )
            if retain_traces:
                element_traces.append(trace)
        else:
            if retain_traces:
                element_traces.append(CalcEmisElementTrace(
                    element_record=element_record, element_z=z, abundance=abundance,
                    abundant=False, compact_population_count=0, compact_xileve=(), ion_traces=(),
                ))
        element_record = int(context.derived.npnxt[element_record])

    ff = freef(
        epi, bremsa, context.workspace.base.opakc,
        temperature_k=context.temperature_k, hydrogen_density_cm3=xpx,
        electron_fraction_xee=context.electron_fraction_xee, ncn2=n,
    )
    context.workspace.base.opakc[:n] = ff.opakc_after_cm_inv
    br = bremem(
        epi, context.workspace.base.brcems, context.workspace.base.opakc,
        temperature_k=context.temperature_k, hydrogen_density_cm3=xpx,
        electron_fraction_xee=context.electron_fraction_xee, ncn2=n,
    )
    context.workspace.base.brcems[:n] = br.brcems_after
    context.workspace.base.opakc[:n] = br.opakc_after_cm_inv

    return CalcEmisResult(
        hydrogen_density_cm3=xpx, electron_density_cm3=xnx,
        neutral_h_density_cm3=xh0, ionized_h_density_cm3=xh1,
        line_rank_table=line_rank, continuum_rank_table=continuum_rank,
        rank_traces=rank_traces, element_traces=tuple(element_traces),
        record_traces=tuple(record_traces), leveltemp_workspace=leveltemp,
        free_free_result=ff, bremsstrahlung_result=br, workspace=context.workspace,
        active_feature_summary=active_feature_summary,
    )


def apply_calc_emis_all_to_state(state: XSTARPythonState) -> CalcEmisResult:
    context = state.control.get("calc_emis_context")
    if not isinstance(context, CalcEmisContext):
        raise CalcEmisPortError("state.control['calc_emis_context'] must be CalcEmisContext")

    call_index = int(state.control.get("calc_emis_all_call_counter", 0)) + 1
    state.control["calc_emis_all_call_counter"] = call_index
    setattr(context, "diagnostic_call_index", call_index)
    setattr(context, "diagnostic_pass_index", int(getattr(state.transfer, "pass_index", 0)))
    setattr(context, "diagnostic_zone_index", int(getattr(state.transfer, "zone_index", 0)))
    setattr(
        context,
        "ucalc_continuum_side_effect_diagnostics_enabled",
        bool(state.control.get("ucalc_continuum_side_effect_diagnostics_enabled", True)),
    )
    setattr(context, "ucalc_continuum_side_effect_diagnostics", [])

    result = calc_emis_all(context)
    rows = list(getattr(context, "ucalc_continuum_side_effect_diagnostics", ()))
    if rows:
        state.outputs.setdefault(UCALC_SIDE_EFFECT_KEY, []).extend(rows)

    state.plasma.xpx = result.hydrogen_density_cm3
    state.plasma.electron_density = result.electron_density_cm3
    state.local_zone.emissivity_ready = True
    state.local_zone.source_arrays["calc_emis_all"] = result
    state.local_zone.provenance["calc_emis_all"] = {
        "source_file": result.source_file,
        "n_elements": len(result.element_traces),
        "n_records": len(result.record_traces),
        "rank_depth": int(context.rank_depth),
        "diagnostic_call_index": int(call_index),
        "ucalc_continuum_side_effect_rows": int(len(rows)),
        "retain_traces": bool(getattr(context, "retain_traces", True)),
        "active_feature_summary": dict(getattr(result, "active_feature_summary", {})),
    }
    phase_context = str(state.control.get("continuum_phase_context", ""))
    phase = "final calc_emis_all" if phase_context == "final" else "calc_emis_all"
    append_phase_snapshot(state, phase, note=f"calc_emis_all_call={call_index}")
    return result


def register_calc_emis_all_source_routine(driver: XSTARPythonDriver) -> None:
    driver.register_source_routine(XSTARSourceRoutine.CALC_EMIS_ALL, apply_calc_emis_all_to_state)


# ---------------------------------------------------------------------------
# Independent bounded fixture.  It exercises rank ordering/limit semantics,
# all-ion aliases, inactive offsets, rate 7, rate 9 prepass+line double call,
# rate 42 retained-kkkl behavior, Thomson reset, freef, and bremem.

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
            14: np.asarray([0, 1, 2, 0]),
            15: np.asarray([0, 0, 2, 0, 1, 0]),
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
            12: _SyntheticHeader(53, 7), 14: _SyntheticHeader(74, 7),
            15: _SyntheticHeader(42, 42),
            20: _SyntheticHeader(6, 13), 21: _SyntheticHeader(6, 13), 22: _SyntheticHeader(6, 13),
            23: _SyntheticHeader(6, 13), 24: _SyntheticHeader(6, 13), 25: _SyntheticHeader(6, 13),
        }
        self._reals = {
            11: np.asarray([1.0]),
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
        self.nlsvn = 3
        self.ncsvn = 3
        self.max_rate_type = 42
        self.npfirst = np.zeros(43, dtype=int)
        self.npfirst[11] = 1
        self.npfirst[12] = 2
        self.npar = np.zeros(40, dtype=int)
        self.npnxt = np.zeros(40, dtype=int)
        self.npnxt[2] = 3
        self.npar[2] = self.npar[3] = 1
        for rec in (10, 11, 12, 15):
            self.npar[rec] = 2
        self.npar[14] = 3
        for rec in (20, 21, 22):
            self.npar[rec] = 2
        for rec in (23, 24, 25):
            self.npar[rec] = 3
        self.npnxt[20] = 21; self.npnxt[21] = 22
        self.npnxt[23] = 24; self.npnxt[24] = 25
        self.npfi = np.zeros((43, 3), dtype=int)
        self.npfi[4, 1] = 10
        self.npfi[7, 1] = 12
        self.npfi[9, 1] = 11
        self.npfi[13, 1] = 20
        self.npfi[42, 1] = 15
        self.npfi[7, 2] = 14
        self.npfi[13, 2] = 23
        self.nplini = np.zeros(40, dtype=int)
        self.nplini[10] = 1
        self.nplini[11] = 2
        self.npconi2 = np.zeros(40, dtype=int)
        self.npconi2[12] = 1
        self.npconi2[14] = 2
        self.nlevs = np.asarray([0, 3, 3], dtype=int)
        self.ion_records = np.asarray([0, 2, 3], dtype=int)
        self.npilev = np.zeros((4, 3), dtype=int)
        self.npilev[1:4, 1] = [1, 2, 3]
        self.npilev[1:4, 2] = [3, 4, 5]


def _synthetic_ucalc(record: int, context: Any) -> UCalcResult:
    payload = {
        10: (1.0, 4.0, -4.0, 0.0, 0.25, {}),
        11: (0.5, 3.0, -9.0, 0.0, 0.55, {}),
        12: (0.0, 0.0, -6.0, -2.0, 0.125, {
            "opakc_cm^-1": [1.0, 2.0, 3.0, 4.0],
            "opakcont_cm^-1": [0.5, 1.0, 1.5, 2.0],
            "rccemis_inward": [0.1, 0.2, 0.3, 0.4],
            "rccemis_outward": [0.4, 0.3, 0.2, 0.1],
        }),
        14: (0.0, 0.0, -7.0, -3.0, 0.2, {}),
        15: (0.0, 0.0, -2.0, -1.0, 0.375, {
            "opakc_cm^-1": [0.1, 0.2, 0.3, 0.4],
            "opakcont_cm^-1": [0.05, 0.1, 0.15, 0.2],
            "rccemis_inward": [0.01, 0.02, 0.03, 0.04],
            "rccemis_outward": [0.04, 0.03, 0.02, 0.01],
        }),
    }
    ans1, ans2, ans3, ans4, opak, diagnostics = payload[int(record)]
    header = {10: (50, 4), 11: (11, 9), 12: (53, 7), 14: (74, 7), 15: (42, 42)}[int(record)]
    return UCalcResult(
        record=int(record), data_type=header[0], rate_type=header[1],
        status=UCalcStatus.EVALUATED,
        ans1=ans1, ans2=ans2, ans3=ans3, ans4=ans4,
        opakab=opak, diagnostics=diagnostics,
    )


def run_calc_emis_source_order_validation(*, rtol: float = 2.0e-14, atol: float = 1.0e-30) -> Mapping[str, Any]:
    master = _SyntheticMaster()
    derived = _SyntheticDerived()
    epi = np.asarray([1.0, 10.0, 100.0, 10000.0])
    radiation = SimpleNamespace(
        epi=epi,
        bremsa=np.asarray([10.0, 8.0, 4.0, 1.0]),
        bremsint=np.asarray([20.0, 10.0, 3.0, 0.0]),
    )
    workspace = CalcEmisWorkspace.allocate(
        n_lines=3, n_continua=3, n_energy=4,
        continuum_fill=7.0, fline_fill=9.0, flinel_fill=5.0,
    )
    # Frozen calc_emisab products consumed by rlbin before continuum reset.
    workspace.base.rcem[:, 1] = [1.0, 1.0]
    workspace.base.rcem[:, 2] = [2.0, 2.0]
    workspace.base.rcem[:, 3] = [0.5, 0.5]
    workspace.base.oplin[1:4] = [0.1, 0.2, 0.05]
    workspace.base.cemab[:, 1] = [0.5, 0.5]
    workspace.base.cemab[:, 2] = [0.5, 0.5]
    workspace.base.cemab[:, 3] = [0.5, 0.5]
    workspace.base.opakab[1:4] = [0.3, 0.8, 0.1]
    wavelengths = np.asarray([
        0.0,
        XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / 2.0,
        XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / 3.0,
        XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / 4.0,
    ])
    context = CalcEmisContext(
        master=master, derived=derived,
        temperature_1e4K=2.0, electron_fraction_xee=1.2,
        hydrogen_density_cm3=99.0,
        pressure_dyn_cm2=2.0 * XSTAR_CALC_EMIS_DENSITY_COEFFICIENT * 5.0,
        density_control_lcdd=0,
        abundances_by_z={1: 1.0, 8: 0.5},
        min_ion_stage_by_z={8: 1}, max_ion_stage_by_z={8: 1},
        xilevg=np.asarray([0.0, 0.2, 0.1, 0.7, 0.3, 0.1]),
        bilevg=np.ones(6), rnisg=np.ones(6),
        radiation=radiation, workspace=workspace,
        line_wavelength_angstrom=wavelengths.copy(),
        rrc_wavelength_angstrom=wavelengths.copy(),
        escape=EscapeProbabilityContext(
            line_tau_in=np.asarray([0.0, 0.0, 0.0]),
            line_tau_out=np.asarray([0.0, 0.0, 0.0]),
            continuum_tau_in=np.asarray([0.0, 0.0, 0.0]),
            continuum_tau_out=np.asarray([0.0, 0.0, 0.0]),
        ),
        covering_fraction=0.25, rank_depth=3,
        ucalc_evaluator=_synthetic_ucalc,
    )
    initial_fline3 = workspace.fline[:, 3].copy()
    initial_flinel = workspace.flinel.copy()
    result = calc_emis_all(context)
    elem = next(e for e in result.element_traces if e.element_z == 8)
    compact_ready = bool(np.array_equal(np.asarray(elem.compact_xileve), np.asarray([0.2, 0.1, 0.7, 0.3, 0.1])))
    inactive_ready = bool((not elem.ion_traces[1].active) and elem.ion_traces[1].compact_offset == 2)
    rank_bin = nbinc(2.0, epi, len(epi))
    line_rank_ready = bool(np.array_equal(result.line_rank_table[1:4, rank_bin], np.asarray([2, 1, 0])))
    continuum_rank_ready = bool(np.array_equal(result.continuum_rank_table[1:4, rank_bin], np.asarray([2, 1, 0])))
    rank_limit_ready = bool(
        any(t.feature_index == 3 and t.reason == "source_rank_limit" for t in result.rank_traces if t.feature_kind == "line")
        and any(t.feature_index == 3 and t.reason == "source_rank_limit" for t in result.rank_traces if t.feature_kind == "continuum")
    )
    roles = [t.output_role for t in result.record_traces]
    order_ready = roles == [
        "strong_line_rate_type_4", "strong_rrc_rate_type_7",
        "rate_type_9_prepass", "strong_line_rate_type_9",
        "rate_type_42_retained_continuum_pointer",
    ]
    type9_double_ready = bool(sum(t.record == 11 for t in result.record_traces) == 2 and elem.ion_traces[0].n_ucalc_calls == 5)
    type42_ready = bool(result.record_traces[-1].retained_continuum_index == 1 and math.isclose(workspace.base.opakab[1], 0.375, rel_tol=0.0, abs_tol=0.0))

    xpx = 5.0
    p1 = pescl(0.0) * 0.75
    p2 = pescl(0.0) * 0.75 + 2.0 * pescl(0.0) * 0.25
    abund_lo = 0.2 * xpx * 0.5
    abund_up = 0.1 * xpx * 0.5
    net4 = 4.0 * abund_up - 1.0 * abund_lo
    expected4 = np.asarray([
        max(net4 * 2.0 * XSTAR_CALC_EMISAB_ERG_PER_EV * p1, 0.0),
        max(net4 * 2.0 * XSTAR_CALC_EMISAB_ERG_PER_EV * p2, 0.0),
    ])
    net9 = 3.0 * abund_up - 0.5 * abund_lo
    expected9 = np.asarray([
        max(net9 * 3.0 * XSTAR_CALC_EMISAB_ERG_PER_EV * p1, 0.0),
        max(net9 * 3.0 * XSTAR_CALC_EMISAB_ERG_PER_EV * p2, 0.0),
    ])
    fline_ready = bool(
        np.allclose(workspace.fline[:, 1], expected4, rtol=rtol, atol=atol)
        and np.allclose(workspace.fline[:, 2], expected9, rtol=rtol, atol=atol)
    )
    width = epi[rank_bin] - epi[max(1, rank_bin - 1) - 1]
    expected_flinel = initial_flinel[rank_bin - 1] + (expected4.sum() + expected9.sum()) * 2.0 / width / XSTAR_CALC_EMISAB_ERG_PER_EV
    flinel_ready = bool(math.isclose(workspace.flinel[rank_bin - 1], expected_flinel, rel_tol=rtol, abs_tol=atol))
    caller_owned_ready = bool(np.array_equal(workspace.fline[:, 3], initial_fline3) and np.all(workspace.flinel[np.arange(4) != rank_bin - 1] == initial_flinel[np.arange(4) != rank_bin - 1]))

    thomson = xpx * 1.2 * XSTAR_THOMSON_CROSS_SECTION_CM2 * 0.75
    continuum_increments = np.asarray([1.1, 2.2, 3.3, 4.4])
    opacity_reset_ready = bool(np.allclose(
        workspace.base.opakc,
        thomson + continuum_increments + result.free_free_result.opacity_increment_cm_inv,
        rtol=rtol, atol=atol,
    ))
    opakcont_ready = bool(np.allclose(
        workspace.base.opakcont,
        thomson + np.asarray([0.55, 1.1, 1.65, 2.2]),
        rtol=rtol, atol=atol,
    ))
    rccemis_ready = bool(np.allclose(
        workspace.base.rccemis,
        np.asarray([[0.11, 0.22, 0.33, 0.44], [0.44, 0.33, 0.22, 0.11]]),
        rtol=rtol, atol=atol,
    ))
    bremem_ready = bool(np.array_equal(workspace.base.brcems, result.bremsstrahlung_result.brcems_after))

    summary = {
        "port_version": "v0.4.62",
        "calc_emis_all_translated": True,
        "rlbin_translated": True,
        "calc_emis_element_translated": True,
        "calc_emis_ion_translated": True,
        "density_branch_lcdd0_ready": math.isclose(result.hydrogen_density_cm3, 5.0, rel_tol=0.0, abs_tol=0.0),
        "precomputed_calc_emisab_ranking_ready": bool(line_rank_ready and continuum_rank_ready),
        "rlbin_source_rank_limit_ready": rank_limit_ready,
        "shared_continuum_alias_mapping_ready": compact_ready,
        "inactive_ion_offset_ready": inactive_ready,
        "source_record_order_ready": order_ready,
        "rate_type_7_strong_rrc_ready": "strong_rrc_rate_type_7" in roles,
        "rate_type_9_double_ucalc_ready": type9_double_ready,
        "rate_type_42_retained_continuum_pointer_ready": type42_ready,
        "strong_line_fline_ready": fline_ready,
        "flinel_source_accumulation_ready": flinel_ready,
        "caller_owned_fline_flinel_nonreset_ready": caller_owned_ready,
        "thomson_continuum_reset_ready": bool(opacity_reset_ready and opakcont_ready),
        "ucalc_continuum_side_effects_ready": rccemis_ready,
        "freef_source_slot_ready": result.free_free_result.htfreef_erg_cm3_s >= 0.0,
        "bremem_source_slot_ready": bremem_ready,
        "record_source_order": [t.record for t in result.record_traces],
        "record_output_roles": roles,
    }
    summary["calc_emis_all_source_acceptance_ready"] = bool(all(
        value for key, value in summary.items() if key.endswith("_ready")
    ))
    summary["next_source_target"] = "complete_local_xstarcalc"
    return summary


def write_calc_emis_validation_products(summary: Mapping[str, Any], out_dir: str | Path) -> Mapping[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "xstar_calc_emis_all_source_validation_summary.json"
    md_path = out / "xstar_calc_emis_all_source_validation_summary.md"
    json_path.write_text(json.dumps(dict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "# XSTAR `calc_emis_all` source validation\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "CalcEmisPortError", "CalcEmisWorkspace", "CalcEmisContext",
    "FeatureRankTrace", "CalcEmisRecordTrace", "CalcEmisIonTrace",
    "CalcEmisElementTrace", "CalcEmisResult",
    "resolve_calc_emis_density", "rlbin_insert", "build_feature_rank_tables",
    "calc_emis_ion", "calc_emis_element", "calc_emis_all",
    "apply_calc_emis_all_to_state", "register_calc_emis_all_source_routine",
    "run_calc_emis_source_order_validation", "write_calc_emis_validation_products",
]
