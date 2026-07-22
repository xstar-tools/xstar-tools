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
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple
import math
import os
import time

import numpy as np

from .atomic_database import XSTARMasterData, XSTARDerivedPointers
from .element_equilibrium import build_level_table
from .performance import profile_component, profile_level_at_least, record_profile_event
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
    retain_contributions: bool = True
    reusable_work_arrays: Optional[Dict[str, Any]] = None
    profile_control: Optional[MutableMapping[str, Any]] = None

    @property
    def electron_density_cm3(self) -> float:
        return float(self.hydrogen_density_cm3) * float(self.electron_fraction_xee)


@dataclass(frozen=True)
class CalcIonRateContribution:
    """One selected record in the literal ``calc_ion_rates`` pass.

    v0.4.79 retains the cumulative-rate state and type-15 threshold provenance
    needed for a direct original-XSTAR record-level comparison. v0.4.82 also
    retains branch diagnostics so the corrected type-59 compact parameter and
    endpoint mapping is visible in the Python C IV record product. Empty shell
    tuples and NaN threshold fields are used for non-type-15 records.
    """

    record: int
    data_type: int
    rate_type: int
    status: str
    parent_record: int
    parent_threshold_ev: float
    shell_thresholds_ev: Tuple[float, ...]
    shell_d_values: Tuple[float, ...]
    effective_threshold_ev: float
    effective_d: float
    bkhsgo_threshold_ev: float
    phintfo_threshold_ev: float
    idest1_packed: int
    idest1: int
    idest2: int
    ans1: float
    ans2: float
    ans3: float
    ans4: float
    ans5: float
    ans6: float
    pirti_before: float
    added_to_pirti: float
    pirti_after: float
    rrrti_before: float
    added_to_rrrti: float
    rrrti_after: float
    reason: str = ""
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


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



def _selected_rate_records_for_ion(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    *,
    ion_index: int,
    ion_record: int,
    cache: Optional[Dict[str, Any]] = None,
) -> List[Tuple[int, int]]:
    """Return selected preliminary calc-ion-rate records for one ion.

    v0.5.46 precomputes the subset of rate records that can contribute to the
    preliminary ionization/recombination balance.  This removes a repeated full
    rate-slot traversal from the Mg/Ca ``calc_hmc_all.pre_matrix_solver`` hot
    path while preserving the source order within each rate-type chain.
    """
    key = ("calc_ion_rates.selected_records", int(ion_index))
    if isinstance(cache, dict):
        cached = cache.get(key)
        if cached is not None:
            return list(cached)
    selected_records: List[Tuple[int, int]] = []
    for rate_slot in range(1, int(derived.npfi.shape[0])):
        record = int(derived.npfi[rate_slot, ion_index])
        while record and int(derived.npar[record]) == ion_record:
            header = master.header(record)
            ints = master.record_integers(record)
            idest1_packed = int(ints[-2]) if ints.size >= 2 else 0
            selected = (
                header.rate_type in {1, 15, 8, 6}
                or (header.rate_type == 7 and idest1_packed == 1)
            )
            if selected:
                selected_records.append((int(rate_slot), int(record)))
            record = int(derived.npnxt[record])
    if isinstance(cache, dict):
        cache[key] = tuple(selected_records)
    return list(selected_records)


def _mg_pre_matrix_candidate_topology(
    master: XSTARMasterData,
    *,
    ion_index: int,
    selected_records: Sequence[Tuple[int, int]],
    cache: Optional[Dict[str, Any]] = None,
    enable_type53: bool = True,
) -> Tuple[Tuple[Tuple[int, float, float], ...], Tuple[Tuple[int, float, float], ...], bool]:
    """Return cached Mg Type-49/53 candidate lists in source order.

    The topology is immutable for one atomic database.  v0.6.43 classifies it
    once and reuses it across all 61 evaluations.  The 0.5 escape factors are
    the literal preliminary ``calc_ion_rates`` values.
    """
    key = ("calc_ion_rates.mg_pre_matrix_coarse_topology", int(ion_index), bool(enable_type53))
    if isinstance(cache, dict) and key in cache:
        value = cache[key]
        return tuple(value[0]), tuple(value[1]), True
    cand49: List[Tuple[int, float, float]] = []
    cand53: List[Tuple[int, float, float]] = []
    for _rate_slot, record in selected_records:
        header = master.header(int(record))
        if int(header.rate_type) != 7:
            continue
        if int(header.data_type) == 49:
            cand49.append((int(record), 0.5, 0.5))
        elif enable_type53 and int(header.data_type) == 53:
            cand53.append((int(record), 0.5, 0.5))
    value = (tuple(cand49), tuple(cand53))
    if isinstance(cache, dict):
        cache[key] = value
    return value[0], value[1], False


def _pre_matrix_rate_additions(
    *, rate_type: int, idest1: int, idest2: int, nlev: int, ans1: float
) -> Tuple[float, float]:
    """Return the literal calc_ion_rates pirt/rrrt contribution."""
    add_pi = 0.0
    add_rr = 0.0
    if int(rate_type) in {1, 15} or (
        int(rate_type) == 7 and int(idest1) == 1 and int(idest2) <= int(nlev) + 2
    ):
        add_pi = float(ans1)
    if int(rate_type) in {8, 6}:
        add_rr = float(ans1)
    return add_pi, add_rr


def _mg_pre_matrix_summary(control: Optional[MutableMapping[str, Any]]) -> Optional[MutableMapping[str, Any]]:
    if not isinstance(control, MutableMapping):
        return None
    summary = control.setdefault(
        "mg_pre_matrix_coarse_cpp_summary",
        {
            "schema_version": "0.6.43.1",
            "requested": False,
            "shadow_enabled": False,
            "product_candidate": False,
            "product_enabled": False,
            "source_order_commit": True,
            "whole_record_fallback": True,
            "evaluations_attempted": 0,
            "evaluations_completed": 0,
            "ions_attempted": 0,
            "ions_completed": 0,
            "selected_records": 0,
            "selected_type49_records": 0,
            "selected_type53_records": 0,
            "cpp_supported_records": 0,
            "cpp_type49_supported_records": 0,
            "cpp_type53_supported_records": 0,
            "cpp_committed_records": 0,
            "python_fallback_records": 0,
            "type53_product_enabled": False,
            "type53_excluded_from_product": True,
            "shadow_records_compared": 0,
            "shadow_mismatches": 0,
            "topology_cache_hits": 0,
            "topology_cache_misses": 0,
            "cpp_calls": 0,
            "packing_seconds": 0.0,
            "cpp_kernel_seconds": 0.0,
            "errors": 0,
            "first_shadow_mismatch": {},
        },
    )
    return summary if isinstance(summary, MutableMapping) else None


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

    v0.5.46 keeps the numerical source path unchanged while adding two hot-path
    production controls: selected preliminary-rate record lists can be cached in
    ``context.reusable_work_arrays`` and detailed contribution rows can be
    suppressed with ``retain_contributions=False``.
    """
    if int(ion_index) <= 0 or int(ion_index) > int(derived.n_ions):
        raise IonBalanceError(f"ion_index {ion_index} outside 1..{derived.n_ions}")
    if context.temperature_k <= 0.0 or not math.isfinite(context.temperature_k):
        raise IonBalanceError("temperature_k must be finite and positive")

    profile_control = context.profile_control if context.profile_control is not None else {}
    _forensic_profile = profile_level_at_least(profile_control, "forensic")
    _setup_t0 = time.perf_counter() if _forensic_profile else 0.0
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
    n_evaluated = n_blocked = 0
    selected_records = _selected_rate_records_for_ion(
        master, derived, ion_index=ion_index, ion_record=ion_record,
        cache=context.reusable_work_arrays,
    )
    n_seen = len(selected_records)
    n_selected = len(selected_records)
    retain_contributions = bool(getattr(context, "retain_contributions", True))
    if _forensic_profile:
        record_profile_event(
            profile_control,
            "calc_hmc_all.pre_matrix.ion_setup",
            time.perf_counter() - _setup_t0,
            counts_as_child=True,
            element_z=int(element_z),
            ion_stage=int(ion_stage),
            ion_index=int(ion_index),
            selected_records=float(n_selected),
            source_routine="build_level_table/selected_record_cache",
            allocation_count=float(2 + int(bool(parent_energy)) + int(bool(parent_weight))),
        )

    # v0.6.4: keep the preliminary Mg rate7 C++ path product-inactive by
    # default.  v0.6.2 showed that enabling this shortcut changed ion/rate
    # traversal counts and downstream Mg products.  The C++ evaluator can now be
    # run in shadow mode to compare against the Python preliminary-rate path
    # without skipping Python records.  Product use requires the explicit
    # XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_PRODUCT_CPP opt-in.
    _truthy = {"1", "true", "yes", "on"}
    _coarse_requested = str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_CPP", "0")).strip().lower() in _truthy
    _prematrix_requested = _coarse_requested or str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_PHOTO_CPP", "0")).strip().lower() in _truthy
    _prematrix_shadow = str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_SHADOW", os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_SHADOW_CPP", "0"))).strip().lower() in _truthy
    _prematrix_product_candidate = str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT_CANDIDATE", "0")).strip().lower() in _truthy
    _prematrix_product = str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT", os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_PRODUCT_CPP", "0"))).strip().lower() in _truthy
    # v0.6.43.1: the inherited Type-53 preliminary kernel is not bit-exact
    # against SourceFaithfulUCalc (the v0.6.43 qualification found one mismatch
    # for every Mg ion/evaluation).  Keep Type-53 on Python until a separately
    # qualified exact kernel is available.  This flag is deliberately distinct
    # from the accepted element-matrix Type-53 feature flag.
    _coarse_type53_enabled = str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_TYPE53", "0")).strip().lower() in _truthy
    # Contribution rows require all six Python ans channels.  The production
    # coarse path is therefore active only when high-volume contribution
    # materialization is disabled; qualification/full diagnostics retain the
    # complete Python record object and can run the C++ path in shadow mode.
    _prematrix_product_live = bool(_prematrix_product and not retain_contributions and not _prematrix_shadow)
    cpp_prematrix_records: set[int] = set()
    cpp_prematrix_product_records: set[int] = set()
    cpp_prematrix_result_by_record: Dict[int, Dict[str, Any]] = {}
    cpp_prematrix_result_by_position: Dict[int, Dict[str, Any]] = {}
    cpp_prematrix_product_positions: set[int] = set()
    cpp_prematrix_pirt = 0.0
    cpp_prematrix_python_pirt = 0.0
    cpp_prematrix_python_rrrt = 0.0
    cpp_prematrix_python_records = 0
    cpp_prematrix_stats: Dict[str, float] = {
        "requested": 1.0 if _prematrix_requested else 0.0,
        "shadow_enabled": 1.0 if _prematrix_shadow else 0.0,
        "product_enabled": 1.0 if _prematrix_product_live else 0.0,
        "product_candidate": 1.0 if _prematrix_product_candidate else 0.0,
        "coarse_requested": 1.0 if _coarse_requested else 0.0,
    }
    _selected_type49_records = 0
    _selected_type53_records = 0
    if int(element_z) == 12:
        for _rate_slot_count, _record_count in selected_records:
            _header_count = master.header(int(_record_count))
            if int(_header_count.rate_type) == 7 and int(_header_count.data_type) == 49:
                _selected_type49_records += 1
            elif int(_header_count.rate_type) == 7 and int(_header_count.data_type) == 53:
                _selected_type53_records += 1

    _coarse_summary = _mg_pre_matrix_summary(profile_control)
    if _coarse_summary is not None and int(element_z) == 12:
        _coarse_summary["requested"] = bool(_prematrix_requested)
        _coarse_summary["shadow_enabled"] = bool(_prematrix_shadow)
        _coarse_summary["product_candidate"] = bool(_prematrix_product_candidate)
        _coarse_summary["product_enabled"] = bool(_prematrix_product_live)
        _coarse_summary["ions_attempted"] = int(_coarse_summary.get("ions_attempted", 0)) + 1
        _coarse_summary["selected_records"] = int(_coarse_summary.get("selected_records", 0)) + int(n_selected)
        _coarse_summary["selected_type49_records"] = int(_coarse_summary.get("selected_type49_records", 0)) + int(_selected_type49_records)
        _coarse_summary["selected_type53_records"] = int(_coarse_summary.get("selected_type53_records", 0)) + int(_selected_type53_records)
        _coarse_summary["type53_product_enabled"] = bool(_coarse_type53_enabled)
        _coarse_summary["type53_excluded_from_product"] = not bool(_coarse_type53_enabled)
    _cpp_t0 = time.perf_counter() if _forensic_profile else 0.0
    if (
        int(element_z) == 12
        and _prematrix_requested
        and (_prematrix_shadow or _prematrix_product)
        and str(os.environ.get("XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP", "0")).strip().lower() in _truthy
    ):
        try:
            from .cpp_backend_matrix import (
                accumulate_mg_ion_rate7_type49_terms_cpp_detailed,
                accumulate_mg_ion_rate7_type53_terms_cpp_detailed,
            )

            _enable_type53 = bool(_coarse_type53_enabled) and str(os.environ.get("XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_TYPE53_CPP", os.environ.get("XSTAR_ATOMIC_MATRIX_MG_ION_TYPE53_PHOTO_CPP", "0"))).strip().lower() in _truthy
            cand49, cand53, _topology_hit = _mg_pre_matrix_candidate_topology(
                master, ion_index=int(ion_index), selected_records=selected_records,
                cache=context.reusable_work_arrays, enable_type53=_enable_type53,
            )
            if _coarse_summary is not None:
                _key = "topology_cache_hits" if _topology_hit else "topology_cache_misses"
                _coarse_summary[_key] = int(_coarse_summary.get(_key, 0)) + 1

            for _label, _func, _cands in (
                ("type49", accumulate_mg_ion_rate7_type49_terms_cpp_detailed, cand49),
                ("type53", accumulate_mg_ion_rate7_type53_terms_cpp_detailed, cand53),
            ):
                if not _cands:
                    continue
                _rows, _message, _stats = _func(
                    master=master,
                    derived=derived,
                    levels=levels,
                    radiation=context.radiation,
                    ion_index=int(ion_index),
                    ion_stage=int(ion_stage),
                    compact_start=1,
                    basis_n_rows=max(1, int(nlev)),
                    term_start=1,
                    temperature_k=float(context.temperature_k),
                    hydrogen_density_cm3=float(context.hydrogen_density_cm3),
                    electron_fraction_xee=float(context.electron_fraction_xee),
                    nlevp=int(nlev),
                    candidates=_cands,
                )
                _supported_records: set[int] = set()
                for _row in _rows:
                    if str(_row.get("role")) != "scalar_pirt":
                        continue
                    _record_number = int(_row.get("record", 0))
                    if _record_number <= 0:
                        continue
                    _supported_records.add(_record_number)
                    _candidate = {
                        "record": _record_number,
                        "data_type": int(_row.get("data_type", 0)),
                        "rate_type": int(_row.get("rate_type", 7)),
                        "idest1": int(_row.get("idest1", 0)),
                        "idest2": int(_row.get("idest2", 0)),
                        "ans1": float(_row.get("aj1", 0.0)),
                        "ans2": float(_row.get("aj2", 0.0)),
                        "ans3": float(_row.get("cj", 0.0)),
                        "ans4": float(_row.get("cj2", 0.0)),
                    }
                    cpp_prematrix_result_by_record[_record_number] = _candidate
                    if _coarse_summary is not None:
                        _dtype_key = "cpp_type49_supported_records" if int(_candidate["data_type"]) == 49 else "cpp_type53_supported_records"
                        _coarse_summary[_dtype_key] = int(_coarse_summary.get(_dtype_key, 0)) + 1
                    if int(_candidate["idest1"]) == 1:
                        cpp_prematrix_pirt += float(_candidate["ans1"])
                cpp_prematrix_records.update(_supported_records)
                if _prematrix_product_live:
                    cpp_prematrix_product_records.update(_supported_records)
                if _coarse_summary is not None:
                    _coarse_summary["cpp_calls"] = int(_coarse_summary.get("cpp_calls", 0)) + int(float((_stats or {}).get("cpp_calls", 0.0)))
                    _coarse_summary["packing_seconds"] = float(_coarse_summary.get("packing_seconds", 0.0)) + float((_stats or {}).get("packing_seconds", 0.0))
                    _coarse_summary["cpp_kernel_seconds"] = float(_coarse_summary.get("cpp_kernel_seconds", 0.0)) + float((_stats or {}).get("cpp_kernel_seconds", 0.0))
                for _k, _v in (_stats or {}).items():
                    try:
                        cpp_prematrix_stats[f"{_label}_{_k}"] = cpp_prematrix_stats.get(f"{_label}_{_k}", 0.0) + float(_v)
                    except (TypeError, ValueError):
                        pass
        except Exception as _exc:
            cpp_prematrix_records = set()
            cpp_prematrix_product_records = set()
            cpp_prematrix_result_by_record = {}
            cpp_prematrix_result_by_position = {}
            cpp_prematrix_product_positions = set()
            cpp_prematrix_pirt = 0.0
            cpp_prematrix_stats.update({"fallback": 1.0, "error_hash": float(abs(hash(str(_exc))) % 1000000)})
            if _coarse_summary is not None:
                _coarse_summary["errors"] = int(_coarse_summary.get("errors", 0)) + 1
    # Convert record-keyed kernel output to the literal selected-stream
    # position.  This remains safe even if a packed record is aliased by more
    # than one source chain.
    cpp_prematrix_result_by_position = {
        int(position): cpp_prematrix_result_by_record[int(record)]
        for position, (_rate_slot, record) in enumerate(selected_records)
        if int(record) in cpp_prematrix_result_by_record
    }
    if _prematrix_product_live:
        cpp_prematrix_product_positions = set(cpp_prematrix_result_by_position)

    if _forensic_profile:
        record_profile_event(
            profile_control,
            ("calc_hmc_all.pre_matrix.mg_coarse_cpp_kernel" if _coarse_requested else "calc_hmc_all.pre_matrix.cpp_shadow_or_product"),
            time.perf_counter() - _cpp_t0,
            counts_as_child=True,
            element_z=int(element_z),
            ion_stage=int(ion_stage),
            ion_index=int(ion_index),
            selected_records=float(n_selected),
            supported_records=float(len(cpp_prematrix_result_by_position)),
            product_records=float(len(cpp_prematrix_product_positions)),
            source_routine="libxstar_matrix.so:pre_matrix_rate7",
        )

    # v0.6.43 never pre-sums C++ records by family.  Each supported result is
    # committed below at its original selected-record position.

    _context_build_seconds = 0.0
    _dispatch_seconds = 0.0
    _accumulation_seconds = 0.0
    _contribution_seconds = 0.0
    _context_allocations = 0
    for source_position, (rate_slot, record) in enumerate(selected_records):
        header = master.header(record)
        ints = master.record_integers(record)
        idest1_packed = int(ints[-2]) if ints.size >= 2 else 0
        pirti_before = float(pirti)
        rrrti_before = float(rrrti)
        _cpp_candidate = cpp_prematrix_result_by_position.get(int(source_position))
        if int(source_position) in cpp_prematrix_product_positions and _cpp_candidate is not None:
            add_pi, add_rr = _pre_matrix_rate_additions(
                rate_type=int(header.rate_type),
                idest1=int(_cpp_candidate.get("idest1", 0)),
                idest2=int(_cpp_candidate.get("idest2", 0)),
                nlev=int(nlev),
                ans1=float(_cpp_candidate.get("ans1", 0.0)),
            )
            n_evaluated += 1
            pirti += add_pi
            rrrti += add_rr
            if _coarse_summary is not None:
                _coarse_summary["cpp_committed_records"] = int(_coarse_summary.get("cpp_committed_records", 0)) + 1
            continue
        if _coarse_summary is not None and int(element_z) == 12:
            _coarse_summary["python_fallback_records"] = int(_coarse_summary.get("python_fallback_records", 0)) + 1
        _context_t0 = time.perf_counter() if _forensic_profile else 0.0
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
            lfast=1,
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
                "requested_lfast": int(context.lfast),
                "calc_ion_rates_lfast": 1,
                # v82 patch 5.20.12.1: literal calc_hmc_all/calc_ion_rates
                # receives epim/ncn2m/bremsam.  Do not let the presence of
                # full epi/bremsa promote Type49/53/88/99 matrix rates to
                # the 9999-bin spectral grid.
                "bound_free_radiation_grid_role": "reduced",
                "bound_free_radiation_grid_owner": "calc_hmc_all.calc_ion_rates",
                "parent_level_energy_ev_by_destination": parent_energy,
                "parent_level_stat_weight_by_destination": parent_weight,
            },
        )
        if _forensic_profile:
            _context_build_seconds += time.perf_counter() - _context_t0
            _context_allocations += 2
        _dispatch_t0 = time.perf_counter() if _forensic_profile else 0.0
        result = dispatch.evaluate_record_number(
            master,
            record,
            ucontext,
            parent_record=ion_record,
            next_record=int(derived.npnxt[record]),
            strict=False,
        )
        if _forensic_profile:
            _dispatch_seconds += time.perf_counter() - _dispatch_t0
        _accum_t0 = time.perf_counter() if _forensic_profile else 0.0
        add_pi = 0.0
        add_rr = 0.0
        if result.status is UCalcStatus.EVALUATED:
            n_evaluated += 1
            add_pi, add_rr = _pre_matrix_rate_additions(
                rate_type=int(header.rate_type), idest1=int(result.idest1),
                idest2=int(result.idest2), nlev=int(nlev), ans1=float(result.ans1),
            )
            pirti += add_pi
            rrrti += add_rr
        else:
            n_blocked += 1

        if int(record) in cpp_prematrix_records and result.status is UCalcStatus.EVALUATED:
            cpp_prematrix_python_records += 1
            cpp_prematrix_python_pirt += float(add_pi)
            cpp_prematrix_python_rrrt += float(add_rr)
            if _prematrix_shadow and _cpp_candidate is not None:
                _candidate_add_pi, _candidate_add_rr = _pre_matrix_rate_additions(
                    rate_type=int(header.rate_type),
                    idest1=int(_cpp_candidate.get("idest1", 0)),
                    idest2=int(_cpp_candidate.get("idest2", 0)),
                    nlev=int(nlev),
                    ans1=float(_cpp_candidate.get("ans1", 0.0)),
                )
                _exact = (
                    float(add_pi).hex() == float(_candidate_add_pi).hex()
                    and int(result.idest1) == int(_cpp_candidate.get("idest1", 0))
                    and int(result.idest2) == int(_cpp_candidate.get("idest2", 0))
                )
                if _coarse_summary is not None:
                    _coarse_summary["shadow_records_compared"] = int(_coarse_summary.get("shadow_records_compared", 0)) + 1
                    if not _exact:
                        _coarse_summary["shadow_mismatches"] = int(_coarse_summary.get("shadow_mismatches", 0)) + 1
                        if not _coarse_summary.get("first_shadow_mismatch"):
                            _coarse_summary["first_shadow_mismatch"] = {
                                "record": int(record),
                                "ion_index": int(ion_index),
                                "ion_stage": int(ion_stage),
                                "data_type": int(header.data_type),
                                "python_add_pi": float(add_pi),
                                "candidate_add_pi": float(_candidate_add_pi),
                                "python_idest1": int(result.idest1),
                                "candidate_idest1": int(_cpp_candidate.get("idest1", 0)),
                                "python_idest2": int(result.idest2),
                                "candidate_idest2": int(_cpp_candidate.get("idest2", 0)),
                            }
        if _forensic_profile:
            _accumulation_seconds += time.perf_counter() - _accum_t0

        if retain_contributions:
            _contrib_t0 = time.perf_counter() if _forensic_profile else 0.0
            diagnostics = dict(getattr(result, "diagnostics", {}) or {})
            try:
                parent_reals = np.asarray(master.record_reals(ion_record), dtype=float)
            except (AttributeError, KeyError, TypeError, ValueError):
                parent_reals = np.asarray((), dtype=float)
            parent_threshold = (
                float(diagnostics.get("type15_parent_threshold_ev"))
                if diagnostics.get("type15_parent_threshold_ev") is not None
                else (float(parent_reals[0]) if parent_reals.size else math.nan)
            )
            shell_thresholds = tuple(float(value) for value in diagnostics.get("type15_shell_thresholds_ev", ()))
            shell_d_values = tuple(float(value) for value in diagnostics.get("type15_shell_d_values", ()))
            rows.append(
                CalcIonRateContribution(
                    record=record,
                    data_type=int(header.data_type),
                    rate_type=int(header.rate_type),
                    status=result.status.value,
                    parent_record=ion_record,
                    parent_threshold_ev=parent_threshold,
                    shell_thresholds_ev=shell_thresholds,
                    shell_d_values=shell_d_values,
                    effective_threshold_ev=float(diagnostics.get("type15_effective_threshold_ev", math.nan)),
                    effective_d=float(diagnostics.get("type15_effective_d", math.nan)),
                    bkhsgo_threshold_ev=float(diagnostics.get("type15_bkhsgo_threshold_ev", math.nan)),
                    phintfo_threshold_ev=float(diagnostics.get("phintfo_threshold_ev", diagnostics.get("type15_phintfo_threshold_ev", math.nan))),
                    idest1_packed=idest1_packed,
                    idest1=int(result.idest1),
                    idest2=int(result.idest2),
                    ans1=float(result.ans1),
                    ans2=float(result.ans2),
                    ans3=float(getattr(result, "ans3", 0.0)),
                    ans4=float(getattr(result, "ans4", 0.0)),
                    ans5=float(getattr(result, "ans5", 0.0)),
                    ans6=float(getattr(result, "ans6", 0.0)),
                    pirti_before=pirti_before,
                    added_to_pirti=add_pi,
                    pirti_after=float(pirti),
                    rrrti_before=rrrti_before,
                    added_to_rrrti=add_rr,
                    rrrti_after=float(rrrti),
                    reason=str(result.reason),
                    diagnostics=diagnostics,
                )
            )
            if _forensic_profile:
                _contribution_seconds += time.perf_counter() - _contrib_t0

    if _forensic_profile:
        for _name, _elapsed, _source, _allocations in (
            ("calc_hmc_all.pre_matrix.ucalc_context_build", _context_build_seconds, "UCalcContext", _context_allocations),
            ("calc_hmc_all.pre_matrix.record_dispatch", _dispatch_seconds, "SourceFaithfulUCalc.evaluate_record_number", 0),
            ("calc_hmc_all.pre_matrix.rate_accumulation", _accumulation_seconds, "calc_ion_rates", 0),
            ("calc_hmc_all.pre_matrix.contribution_materialization", _contribution_seconds, "CalcIonRateContribution", len(rows)),
        ):
            record_profile_event(
                profile_control,
                _name,
                _elapsed,
                counts_as_child=True,
                element_z=int(element_z),
                ion_stage=int(ion_stage),
                ion_index=int(ion_index),
                selected_records=float(n_selected),
                contribution_rows=float(len(rows)),
                allocation_count=float(_allocations),
                source_routine=_source,
            )

    ready = n_blocked == 0
    if _coarse_summary is not None and int(element_z) == 12:
        _coarse_summary["cpp_supported_records"] = int(_coarse_summary.get("cpp_supported_records", 0)) + len(cpp_prematrix_result_by_position)
        _coarse_summary["ions_completed"] = int(_coarse_summary.get("ions_completed", 0)) + 1
    return CalcIonRatesResult(
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
            "local_lfpi": 1,
            "cached_selected_records": isinstance(context.reusable_work_arrays, dict),
            "retain_contributions": retain_contributions,
            "prematrix_cpp_records": len(cpp_prematrix_result_by_position),
            "prematrix_cpp_product_records": len(cpp_prematrix_product_positions),
            "prematrix_cpp_pirt": float(cpp_prematrix_pirt),
            "prematrix_python_records": int(cpp_prematrix_python_records),
            "prematrix_python_pirt": float(cpp_prematrix_python_pirt),
            "prematrix_python_rrrt": float(cpp_prematrix_python_rrrt),
            "prematrix_shadow_pirt_abs_diff": float(abs(cpp_prematrix_python_pirt - cpp_prematrix_pirt)) if cpp_prematrix_records else 0.0,
            "prematrix_shadow_product_active": bool(cpp_prematrix_product_records),
            "prematrix_source_order_commit": True,
            "prematrix_coarse_requested": bool(_coarse_requested),
            "prematrix_product_candidate": bool(_prematrix_product_candidate),
            "prematrix_product_live": bool(_prematrix_product_live),
            "prematrix_cpp_stats": dict(cpp_prematrix_stats),
        },
    )

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
    """Run the total-rate/``istruc``/stage-limit first pass with exclusive splits."""
    profile_control = context.profile_control if context.profile_control is not None else {}
    _coarse_summary = _mg_pre_matrix_summary(profile_control) if int(element_z) == 12 else None
    if _coarse_summary is not None:
        _coarse_summary["evaluations_attempted"] = int(_coarse_summary.get("evaluations_attempted", 0)) + 1
    with profile_component(
        profile_control,
        "calc_hmc_all.pre_matrix.metadata_lookup",
        element_z=int(element_z),
        source_routine="calc_element_pre_matrix_balance",
    ):
        nnz = _element_nnz(master, derived, element_z)
        ion_indices = _ion_indices_for_element(derived, element_z)

    by_stage: Dict[int, CalcIonRatesResult] = {}
    with profile_component(
        profile_control,
        "calc_hmc_all.pre_matrix.ion_rate_evaluation",
        element_z=int(element_z),
        source_routine="calc_ion_rates",
        ion_count=float(len(ion_indices)),
    ):
        for ion_index in ion_indices:
            stage = int(derived.ion_stage[ion_index])
            if stage < 1 or stage > nnz:
                continue
            with profile_component(
                profile_control,
                "calc_hmc_all.pre_matrix.ion",
                element_z=int(element_z),
                ion_stage=int(stage),
                ion_index=int(ion_index),
                source_routine="calc_ion_rates",
            ):
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

    with profile_component(
        profile_control,
        "calc_hmc_all.pre_matrix.rate_vector_allocation",
        element_z=int(element_z),
        source_routine="numpy.asarray",
        allocation_count=2.0,
        bytes_allocated=float(2 * nnz * 8),
    ):
        pirt = np.asarray([by_stage[stage].pirti for stage in range(1, nnz + 1)], dtype=float)
        rrrt = np.asarray([by_stage[stage].rrrti for stage in range(1, nnz + 1)], dtype=float)
    with profile_component(
        profile_control,
        "calc_hmc_all.pre_matrix.ion_fraction_solve",
        element_z=int(element_z),
        source_routine="istruc/ioneqm",
    ):
        preliminary = istruc(pirt, rrrt)
    with profile_component(
        profile_control,
        "calc_hmc_all.pre_matrix.stage_limit_selection",
        element_z=int(element_z),
        source_routine="select_ion_stage_limits",
    ):
        limits = select_ion_stage_limits(preliminary.fractions, nnz=nnz, critf=critf)
    if _coarse_summary is not None:
        _coarse_summary["evaluations_completed"] = int(_coarse_summary.get("evaluations_completed", 0)) + 1
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
