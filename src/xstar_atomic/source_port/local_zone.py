"""Fixed-state core of XSTAR ``calc_hmc_all.f90``.

This module is the first Milestone-4 source port.  It preserves the outer
``calc_hmc_all`` element loop and source-shaped accounting while reusing the
validated Milestone-3 ``calc_hmc_element`` kernel.  Temperature and electron
fraction are fixed inputs here; ``dsec`` remains the subsequent nonlinear
translation target.

The continuum leaves ``comp2 -> freef -> bremem -> heatf`` are represented by
an explicit callback.  Omitting that callback is allowed for element-loop and
charge-accounting development, but the result then advertises that complete
fixed-state local-zone parity is not yet ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .performance import profile_component

from .element_equilibrium import (
    ElementEquilibriumContext,
    ElementEquilibriumResult,
    EscapeProbabilityContext,
    solve_element_statistical_equilibrium,
)
from .ucalc import SourceFaithfulUCalc
from .compton import Comp2Context, comp2_continuum_result
from .free_free import FreeFreeContext, freef_continuum_result
from .bremsstrahlung import (
    BremsstrahlungContext,
    bremem_continuum_result,
)
from .thermal_balance import HeatFContext, heatf
from .ion_balance import (
    CalcIonRatesContext,
    CalcIonRatesResult,
    IstrucResult,
    IonStageLimitResult,
    calc_element_pre_matrix_balance,
)


class CalcHMCAllError(RuntimeError):
    """Raised when the fixed-state local-zone source sequence cannot run."""


@dataclass(frozen=True)
class FixedStateElementRequest:
    """One element passed through the translated ``calc_hmc_all`` loop."""

    element_z: int
    min_ion_stage: int
    max_ion_stage: int
    abundance: float = 1.0
    radiation: Any = None
    escape: EscapeProbabilityContext = field(default_factory=EscapeProbabilityContext)
    covering_fraction: float = 1.0
    turbulent_velocity_km_s: float = 0.0
    neutral_h_density_cm3: float = 0.0
    ionized_h_density_cm3: float = 0.0
    lfast: int = 2
    allow_lstsq_fallback: bool = False
    allow_dense_matrix_rescue: bool = False
    critf: float = 1.0e-7
    use_source_ion_limits: bool = True
    initial_populations: Optional[np.ndarray] = None
    # Optional global XSTAR ``xilevg`` state.  When supplied, the element
    # solver remaps it onto the *current* compact basis after ``istruc`` has
    # selected the active ion range.  This is required by ``dsec`` because the
    # compact dimension can change from one thermal/charge trial to the next.
    initial_global_populations: Optional[Mapping[Tuple[int, int, int], float]] = None
    initial_population_source: str = "levwkelement_lte_fallback"
    # Source ``calc_hmc_element.f90`` explicitly resets the final compact
    # continuum/normalization row to zero after mapping all selected ions and
    # immediately before ``msolvelucy``.  ``legacy-global`` preserves the
    # pre-v0.4.55 diagnostic behavior for controlled causality scans only.
    terminal_continuum_seed_mode: str = "source-zero"
    strict_context: bool = True
    capture_lucy_trace: bool = False

    def validate(self) -> None:
        if self.element_z <= 0:
            raise CalcHMCAllError("element_z must be positive")
        if self.min_ion_stage <= 0 or self.max_ion_stage < self.min_ion_stage:
            raise CalcHMCAllError("invalid ion-stage range")
        if not np.isfinite(self.abundance) or self.abundance < 0.0:
            raise CalcHMCAllError("element abundance must be finite and nonnegative")
        if not np.isfinite(self.critf) or self.critf < 0.0:
            raise CalcHMCAllError("critf must be finite and nonnegative")
        if self.terminal_continuum_seed_mode not in {"source-zero", "legacy-global"}:
            raise CalcHMCAllError(
                "terminal_continuum_seed_mode must be 'source-zero' or "
                "'legacy-global'"
            )


@dataclass(frozen=True)
class FixedStateContinuumResult:
    """Source-shaped continuum contribution returned by a leaf callback."""

    heating: float = 0.0
    cooling: float = 0.0
    heating2: float = 0.0
    cooling2: float = 0.0
    htcomp: float = 0.0
    clcomp: float = 0.0
    clbrems: float = 0.0
    htfreef: float = 0.0
    brcems: Optional[np.ndarray] = None
    opakc: Optional[np.ndarray] = None
    httot_after: Optional[float] = None
    cltot_after: Optional[float] = None
    httot2_after: Optional[float] = None
    cltot2_after: Optional[float] = None
    hmctot_after: Optional[float] = None
    complete: bool = False
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class FixedStateElementResult:
    """One completed element-loop iteration."""

    request: FixedStateElementRequest
    equilibrium: ElementEquilibriumResult
    calc_ion_rates: Dict[int, CalcIonRatesResult]
    preliminary_pirt: Dict[int, float]
    preliminary_rrrt: Dict[int, float]
    second_pass_pirt: Dict[int, float]
    second_pass_rrrt: Dict[int, float]
    preliminary_istruc: IstrucResult
    source_limits: IonStageLimitResult
    selected_min_ion_stage: int
    selected_max_ion_stage: int
    ion_fractions: Dict[int, float]
    preliminary_ion_fractions: Dict[int, float]
    fully_stripped_fraction: float
    heating: float
    cooling: float
    heating2: float
    cooling2: float
    heating_per_abundance: float
    cooling_per_abundance: float
    heating2_per_abundance: float
    cooling2_per_abundance: float
    electron_contribution: float


@dataclass
class FixedStateCalcHMCAllResult:
    """Result of the fixed-temperature/electron-fraction ``calc_hmc_all`` core."""

    temperature_k: float
    hydrogen_density_cm3: float
    electron_fraction_xee: float
    electron_density_cm3: float
    neutral_h_density_cm3: float
    ionized_h_density_cm3: float
    hydrogen_ground_fraction: float
    hydrogen_abundance: float
    pressure: float
    lcdd: int
    element_results: List[FixedStateElementResult]
    ion_fractions: Dict[Tuple[int, int], float]
    preliminary_ion_fractions: Dict[Tuple[int, int], float]
    preliminary_rrrt: Dict[Tuple[int, int], float]
    preliminary_pirt: Dict[Tuple[int, int], float]
    rrrt: Dict[Tuple[int, int], float]
    pirt: Dict[Tuple[int, int], float]
    htt: Dict[int, float]
    cll: Dict[int, float]
    htt2: Dict[int, float]
    cll2: Dict[int, float]
    xilevg: Dict[Tuple[int, int, int], float]
    rnisg: Dict[Tuple[int, int, int], float]
    bilevg: Dict[Tuple[int, int, int], float]
    gammag: Dict[Tuple[int, int, int], float]
    alphag: Dict[Tuple[int, int, int], float]
    fgammag: Dict[Tuple[int, int, int], np.ndarray]
    falphag: Dict[Tuple[int, int, int], np.ndarray]
    igammamaxg: Dict[Tuple[int, int, int], int]
    ialphamaxg: Dict[Tuple[int, int, int], int]
    stotg: Dict[Tuple[int, int], float]
    atotg: Dict[Tuple[int, int], float]
    fstotg: Dict[Tuple[int, int], np.ndarray]
    fatotg: Dict[Tuple[int, int], np.ndarray]
    xtotg: Dict[Tuple[int, int], float]
    mml: Dict[int, int]
    mmu: Dict[int, int]
    httot_pre_continuum: float
    cltot_pre_continuum: float
    httot2_pre_continuum: float
    cltot2_pre_continuum: float
    httot: float
    cltot: float
    httot2: float
    cltot2: float
    hmctot: float
    elcter: float
    electron_contribution: float
    continuum: FixedStateContinuumResult
    pre_matrix_ready: bool
    element_loop_ready: bool
    charge_closure_scope_complete: bool
    complete_fixed_state_ready: bool
    # Diagnostic-only, source-ordered carbon state-path trace.  Production
    # calculations do not consume these rows.  The trace is populated only
    # when the carbon request enables ``capture_lucy_trace``.
    carbon_state_path: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    # Shared mutable ``leveltemp`` state after the final element in this
    # ``calc_hmc_all`` call.  ``dsec`` feeds these objects into the next call.
    leveltemp_workspace: Optional[Any] = None
    leveltemp_owner_by_column: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    global_element_index_by_z: Dict[int, int] = field(default_factory=dict)
    global_ion_index_by_key: Dict[Tuple[int, int], int] = field(default_factory=dict)
    global_level_index_by_key: Dict[Tuple[int, int, int], int] = field(default_factory=dict)
    # Dense native XSTAR global arrays.  Array position ``i-1`` corresponds
    # to Fortran global level index ``i``.  These are the authoritative
    # mutable state for repeated ``dsec`` calls; the logical dictionaries
    # above remain diagnostic views.
    global_xilevg_by_index: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=float)
    )
    global_bilevg_by_index: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=float)
    )
    global_rnisg_by_index: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=float)
    )


ContinuumKernel = Callable[..., FixedStateContinuumResult]
ElementSolver = Callable[..., ElementEquilibriumResult]
PreMatrixSolver = Callable[..., Tuple[Dict[int, CalcIonRatesResult], IstrucResult, IonStageLimitResult]]


def resolve_calc_hmc_all_density(
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    pressure: float,
    lcdd: int,
) -> float:
    """Reproduce the source ``xpx`` mutation at entry to ``calc_hmc_all``.

    XSTAR stores temperature in units of ``1e4 K``.  The historical ``lcdd``
    branch names are preserved literally rather than reinterpreted.
    """
    t4 = float(temperature_k) / 1.0e4
    xpx = float(hydrogen_density_cm3)
    if int(lcdd) == 0:
        xpx = float(pressure) / (1.38e-12 * max(t4, 1.0e-24))
    if int(lcdd) == 2:
        xpx = float(pressure) / (float(electron_fraction_xee) + 1.0e-34)
    return xpx


def _role_key(element_z: int, role: Mapping[str, Any]) -> Optional[Tuple[int, int, int]]:
    stage = int(role.get("ion_stage", 0))
    level = int(role.get("local_level", role.get("level", 0)))
    if stage <= 0 or level <= 0:
        return None
    return int(element_z), stage, level


def calc_hmc_all(
    master: Any,
    derived: Any,
    *,
    elements: Sequence[FixedStateElementRequest],
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    pressure: float = 0.0,
    lcdd: int = 1,
    continuum_kernel: Optional[ContinuumKernel] = None,
    compton_context: Optional[Comp2Context] = None,
    free_free_context: Optional[FreeFreeContext] = None,
    bremem_context: Optional[BremsstrahlungContext] = None,
    heatf_context: Optional[HeatFContext] = None,
    required_element_z: Optional[Sequence[int]] = None,
    dispatcher: Optional[SourceFaithfulUCalc] = None,
    element_solver: ElementSolver = solve_element_statistical_equilibrium,
    pre_matrix_solver: PreMatrixSolver = calc_element_pre_matrix_balance,
    initial_leveltemp_workspace: Optional[Any] = None,
    initial_leveltemp_owner_by_column: Optional[Mapping[int, Mapping[str, Any]]] = None,
    initial_global_xilevg_by_index: Optional[Sequence[float]] = None,
    initial_global_bilevg_by_index: Optional[Sequence[float]] = None,
    initial_global_rnisg_by_index: Optional[Sequence[float]] = None,
    source_global_alias_writeback: bool = False,
    active_subset: Optional[Any] = None,
    profile_control: Optional[Mapping[str, Any]] = None,
) -> FixedStateCalcHMCAllResult:
    """Run the fixed-state element/charge/heating core of ``calc_hmc_all``.

    The function does not iterate temperature or electron fraction.  It calls
    the validated complete element solver once per supplied element, stores
    source-shaped ion/level diagnostics, accumulates abundance-weighted
    heating/cooling, and evaluates the source charge residual
    ``elcter = xee - enelec``.
    """
    if temperature_k <= 0.0 or not np.isfinite(temperature_k):
        raise CalcHMCAllError("temperature_k must be finite and positive")
    if electron_fraction_xee < 0.0 or not np.isfinite(electron_fraction_xee):
        raise CalcHMCAllError("electron_fraction_xee must be finite and nonnegative")
    if not elements:
        raise CalcHMCAllError("at least one element request is required")

    xpx = resolve_calc_hmc_all_density(
        temperature_k=temperature_k,
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
        pressure=pressure,
        lcdd=lcdd,
    )
    if xpx < 0.0 or not np.isfinite(xpx):
        raise CalcHMCAllError("resolved hydrogen density is invalid")

    ion_fractions: Dict[Tuple[int, int], float] = {}
    preliminary_ion_fractions: Dict[Tuple[int, int], float] = {}
    preliminary_rrrt: Dict[Tuple[int, int], float] = {}
    preliminary_pirt: Dict[Tuple[int, int], float] = {}
    rrrt: Dict[Tuple[int, int], float] = {}
    pirt: Dict[Tuple[int, int], float] = {}
    htt: Dict[int, float] = {}
    cll: Dict[int, float] = {}
    htt2: Dict[int, float] = {}
    cll2: Dict[int, float] = {}
    xilevg: Dict[Tuple[int, int, int], float] = {}
    rnisg: Dict[Tuple[int, int, int], float] = {}
    bilevg: Dict[Tuple[int, int, int], float] = {}
    gammag: Dict[Tuple[int, int, int], float] = {}
    alphag: Dict[Tuple[int, int, int], float] = {}
    fgammag: Dict[Tuple[int, int, int], np.ndarray] = {}
    falphag: Dict[Tuple[int, int, int], np.ndarray] = {}
    igammamaxg: Dict[Tuple[int, int, int], int] = {}
    ialphamaxg: Dict[Tuple[int, int, int], int] = {}
    stotg: Dict[Tuple[int, int], float] = {}
    atotg: Dict[Tuple[int, int], float] = {}
    fstotg: Dict[Tuple[int, int], np.ndarray] = {}
    fatotg: Dict[Tuple[int, int], np.ndarray] = {}
    xtotg: Dict[Tuple[int, int], float] = {}
    mml: Dict[int, int] = {}
    mmu: Dict[int, int] = {}

    element_results: List[FixedStateElementResult] = []
    httot = cltot = httot2 = cltot2 = 0.0
    enelec = 0.0
    all_ready = True
    all_pre_matrix_ready = True
    ion_element_z = getattr(derived, "ion_element_z", ())
    available_element_z = {
        int(z) for z in np.asarray(ion_element_z).reshape(-1) if int(z) > 0
    }
    requested_element_z = {int(item.element_z) for item in elements if float(item.abundance) > 1.0e-24}
    leveltemp_workspace = initial_leveltemp_workspace
    leveltemp_owner_by_column: Dict[int, Dict[str, Any]] = {
        int(index): dict(owner)
        for index, owner in (initial_leveltemp_owner_by_column or {}).items()
    }
    if required_element_z is None:
        charge_scope_reference = "all_atdb_elements_legacy_default"
        required_element_z_set = set(available_element_z)
    else:
        charge_scope_reference = "explicit_positive_abundance_element_scope"
        required_element_z_set = {int(z) for z in required_element_z if int(z) > 0}
        unknown = required_element_z_set - available_element_z
        if unknown:
            raise CalcHMCAllError(
                "required element scope contains elements absent from the ATDB: "
                + ",".join(str(z) for z in sorted(unknown))
            )
    charge_scope_complete = bool(required_element_z_set) and requested_element_z == required_element_z_set

    # Preserve the native XSTAR global array indices so bounded probe products
    # can be compared without guessing from element/stage/local-level labels.
    # v0.5.41 can reuse a per-case active subset instead of rebuilding these
    # maps during every repeated dsec evaluation.
    n_ions = int(getattr(derived, "n_ions", 0))
    ion_records = np.asarray(getattr(derived, "ion_records", ()), dtype=int).reshape(-1)
    ion_stages = np.asarray(getattr(derived, "ion_stage", ()), dtype=int).reshape(-1)
    ion_elements = np.asarray(getattr(derived, "ion_element_z", ()), dtype=int).reshape(-1)
    npilev = np.asarray(getattr(derived, "npilev", ()), dtype=int)
    nlevs = np.asarray(getattr(derived, "nlevs", ()), dtype=int).reshape(-1)
    if active_subset is not None:
        global_ion_index_by_key = {
            (int(k[0]), int(k[1])): int(v)
            for k, v in dict(getattr(active_subset, "global_ion_index_by_key", {})).items()
            if int(k[0]) in requested_element_z
        }
        ion_record_to_index = {
            int(k): int(v)
            for k, v in dict(getattr(active_subset, "ion_record_to_index", {})).items()
        }
        global_element_index_by_z = {
            int(k): int(v)
            for k, v in dict(getattr(active_subset, "global_element_index_by_z", {})).items()
        }
        global_element_index_source = str(
            getattr(active_subset, "global_element_index_source", "active_subset")
        )
        global_level_index_by_key = {
            (int(k[0]), int(k[1]), int(k[2])): int(v)
            for k, v in dict(getattr(active_subset, "global_level_index_by_key", {})).items()
            if int(k[0]) in requested_element_z
        }
    else:
        global_ion_index_by_key: Dict[Tuple[int, int], int] = {}
        ion_record_to_index: Dict[int, int] = {}
        for ion_index in range(1, min(n_ions + 1, ion_records.size, ion_stages.size, ion_elements.size)):
            ion_record_to_index[int(ion_records[ion_index])] = ion_index
            key = (int(ion_elements[ion_index]), int(ion_stages[ion_index]))
            if key[0] in requested_element_z and key[0] > 0 and key[1] > 0:
                global_ion_index_by_key[key] = ion_index

        # Element arrays such as htt/cll are indexed by source element ordinal
        # ``jk``, not by atomic number.  Decode the exact ordinal from the packed
        # rate-type-11 element headers.
        global_element_index_by_z: Dict[int, int] = {}
        global_element_index_source = "packed_type11_element_ordinal"
        element_records = np.asarray(getattr(derived, "element_records", ()), dtype=int).reshape(-1)
        for element_index in range(1, element_records.size):
            element_record = int(element_records[element_index])
            if element_record <= 0 or not hasattr(master, "record_integers"):
                continue
            integers = np.asarray(master.record_integers(element_record), dtype=int).reshape(-1)
            if integers.size and int(integers[0]) > 0:
                global_element_index_by_z[int(integers[0])] = element_index
        # Synthetic/minimal tests may omit packed element headers.  Preserve a
        # deterministic fallback without using it in production provenance.
        if not global_element_index_by_z:
            global_element_index_source = "synthetic_sorted_element_fallback"
            for element_index, z in enumerate(sorted(available_element_z), start=1):
                global_element_index_by_z[int(z)] = element_index

        # Global level arrays use the source ordinal ``mm`` in
        # derivedpointers%npilev(mm,jkk).  Packed local level labels are metadata
        # and are not valid substitutes for this ordinal.
        global_level_index_by_key: Dict[Tuple[int, int, int], int] = {}
        if npilev.ndim == 2:
            for ion_index in range(1, min(n_ions + 1, ion_stages.size, ion_elements.size, nlevs.size)):
                z = int(ion_elements[ion_index])
                stage = int(ion_stages[ion_index])
                if z not in requested_element_z or stage <= 0:
                    continue
                nlev = int(nlevs[ion_index])
                for local_ordinal in range(1, min(nlev + 1, npilev.shape[0])):
                    if ion_index >= npilev.shape[1]:
                        break
                    global_level_index = int(npilev[local_ordinal, ion_index])
                    if global_level_index > 0:
                        global_level_index_by_key[(z, stage, local_ordinal)] = global_level_index

    n_global_levels = max(
        [
            0,
            *global_level_index_by_key.values(),
            (
                len(np.asarray(initial_global_xilevg_by_index).reshape(-1))
                if initial_global_xilevg_by_index is not None
                else 0
            ),
            (
                len(np.asarray(initial_global_bilevg_by_index).reshape(-1))
                if initial_global_bilevg_by_index is not None
                else 0
            ),
            (
                len(np.asarray(initial_global_rnisg_by_index).reshape(-1))
                if initial_global_rnisg_by_index is not None
                else 0
            ),
            int(getattr(active_subset, "n_global_levels_active", 0) or 0)
            if active_subset is not None
            else 0,
        ]
    )

    def _dense_seed(values: Optional[Sequence[float]], *, name: str) -> np.ndarray:
        dense = np.zeros(n_global_levels, dtype=float)
        if values is None:
            return dense
        supplied = np.asarray(values, dtype=float).reshape(-1)
        if np.any(~np.isfinite(supplied)):
            raise CalcHMCAllError(f"{name} contains non-finite values")
        if np.any(supplied < 0.0):
            raise CalcHMCAllError(f"{name} contains negative values")
        dense[: min(dense.size, supplied.size)] = supplied[: dense.size]
        return dense

    global_xilevg_by_index = _dense_seed(
        initial_global_xilevg_by_index, name="initial_global_xilevg_by_index"
    )
    global_bilevg_by_index = _dense_seed(
        initial_global_bilevg_by_index, name="initial_global_bilevg_by_index"
    )
    global_rnisg_by_index = _dense_seed(
        initial_global_rnisg_by_index, name="initial_global_rnisg_by_index"
    )

    # Literal calc_hmc_all.f90 entry state.  XSTAR constructs the neutral and
    # ionized hydrogen charge-exchange densities once per calc_hmc_all call
    # from the *incoming* global H I ground population, before the element
    # loop mutates xilevg:
    #
    #   xh0=xpx*xilevg(1)*abel(1)
    #   xh1=xpx*(1.-xilevg(1))*abel(1)
    #
    # The dense native array is authoritative in production.  Synthetic
    # bounded callers without that array retain XSTAR init semantics
    # (xilevg(1)=0) rather than using stale per-request defaults.
    hydrogen_abundance = next(
        (float(item.abundance) for item in elements if int(item.element_z) == 1),
        0.0,
    )
    hydrogen_ground_fraction = (
        float(global_xilevg_by_index[0])
        if global_xilevg_by_index.size >= 1
        else 0.0
    )
    if not np.isfinite(hydrogen_ground_fraction):
        raise CalcHMCAllError("incoming global H I ground population is non-finite")
    live_xh0 = xpx * hydrogen_ground_fraction * hydrogen_abundance
    live_xh1 = xpx * (1.0 - hydrogen_ground_fraction) * hydrogen_abundance

    capture_carbon_state_path = any(
        int(item.element_z) == 6 and bool(item.capture_lucy_trace)
        for item in elements
    )
    capture_hydrogen_state_path = any(
        int(item.element_z) == 1 and bool(item.capture_lucy_trace)
        for item in elements
    )
    # Diagnostic-only source-order state-path traces.  The historical field
    # name is retained for compatibility with v0.4.86/v0.4.87 callers, but
    # v0.4.88 also carries all-evaluation hydrogen history and lightweight
    # electron/carbon correlation rows.  Production code never consumes these
    # lists.
    carbon_state_path: Dict[str, List[Dict[str, Any]]] = {
        "hydrogen": [],
        "hydrogen_history": [],
        "levels": [],
        "stage_totals": [],
        "aliases": [],
        "electron_history": [],
        "carbon_correlation_stage_totals": [],
    }
    if capture_carbon_state_path or capture_hydrogen_state_path:
        entry_row = {
            "source": "python",
            "phase_code": 10,
            "phase": "calc_hmc_all_entry_hydrogen",
            "element_z": 1,
            "ion_stage": 1,
            "hydrogen_ground_fraction": float(hydrogen_ground_fraction),
            "hydrogen_abundance": float(hydrogen_abundance),
            "hydrogen_density_cm3": float(xpx),
            "neutral_h_density_cm3": float(live_xh0),
            "ionized_h_density_cm3": float(live_xh1),
            "population": float(hydrogen_ground_fraction),
        }
        carbon_state_path["hydrogen"].append(dict(entry_row))
        carbon_state_path["hydrogen_history"].append(dict(entry_row))

    def _native_element_rows(
        *, phase_code: int, phase: str, element_z: int, values: np.ndarray
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        full_index_offset = 0
        for ion_index in range(
            1, min(n_ions + 1, ion_stages.size, ion_elements.size, nlevs.size)
        ):
            if int(ion_elements[ion_index]) != int(element_z):
                continue
            stage = int(ion_stages[ion_index])
            nlev = int(nlevs[ion_index])
            for local_level in range(1, nlev + 1):
                global_index = int(
                    global_level_index_by_key.get(
                        (int(element_z), stage, local_level), 0
                    )
                )
                population = (
                    float(values[global_index - 1])
                    if 1 <= global_index <= values.size
                    else 0.0
                )
                rows.append(
                    {
                        "source": "python",
                        "phase_code": int(phase_code),
                        "phase": str(phase),
                        "outer_iteration": 0,
                        "fixed_iteration": 0,
                        "compact_index": 0,
                        "superlevel": 0,
                        "ion_counter": 0,
                        "ion_stage": stage,
                        "ion_index": ion_index,
                        "local_level": local_level,
                        "global_index": global_index,
                        "full_element_index": full_index_offset + local_level,
                        "population": population,
                    }
                )
            full_index_offset += max(0, nlev - 1)
        return rows

    def _stage_totals_from_native_rows(
        *, phase_code: int, phase: str, element_z: int, values: np.ndarray
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        full_index_offset = 0
        for ion_index in range(
            1, min(n_ions + 1, ion_stages.size, ion_elements.size, nlevs.size)
        ):
            if int(ion_elements[ion_index]) != int(element_z):
                continue
            stage = int(ion_stages[ion_index])
            nlev = int(nlevs[ion_index])
            total = 0.0
            continuum = 0.0
            ground = 0.0
            ground_global_index = 0
            continuum_global_index = 0
            for local_level in range(1, nlev + 1):
                global_index = int(
                    global_level_index_by_key.get(
                        (int(element_z), stage, local_level), 0
                    )
                )
                population = (
                    float(values[global_index - 1])
                    if 1 <= global_index <= values.size
                    else 0.0
                )
                if local_level == 1:
                    ground = population
                    ground_global_index = global_index
                if local_level < nlev:
                    total += population
                else:
                    continuum = population
                    continuum_global_index = global_index
            next_stage = stage + 1
            next_ground_global_index = int(
                global_level_index_by_key.get((int(element_z), next_stage, 1), 0)
            )
            next_ground_population = (
                float(values[next_ground_global_index - 1])
                if 1 <= next_ground_global_index <= values.size
                else 0.0
            )
            rows.append(
                {
                    "source": "python",
                    "phase_code": int(phase_code),
                    "phase": str(phase),
                    "outer_iteration": 0,
                    "ion_counter": 0,
                    "ion_stage": stage,
                    "ion_index": ion_index,
                    "nlev": int(nlev),
                    "ground_local_level": 1,
                    "ground_global_index": int(ground_global_index),
                    "continuum_local_level": int(nlev),
                    "continuum_global_index": int(continuum_global_index),
                    "next_ion_stage": int(next_stage),
                    "next_ground_local_level": 1,
                    "next_ground_global_index": int(next_ground_global_index),
                    "full_element_index": full_index_offset + 1,
                    "population_total": float(total),
                    "ground_population": float(ground),
                    "continuum_population": float(continuum),
                    "next_ground_population": float(next_ground_population),
                    "continuum_next_ground_difference": float(abs(continuum - next_ground_population)),
                }
            )
            full_index_offset += max(0, nlev - 1)
        return rows

    for request in elements:
        request.validate()
        effective_request = replace(
            request,
            neutral_h_density_cm3=float(live_xh0),
            ionized_h_density_cm3=float(live_xh1),
        )
        z = int(effective_request.element_z)
        abundance = float(effective_request.abundance)
        if capture_carbon_state_path and z == 6:
            carbon_state_path["levels"].extend(
                _native_element_rows(
                    phase_code=20,
                    phase="calc_hmc_all_map_global_to_element_entry",
                    element_z=6,
                    values=global_xilevg_by_index,
                )
            )
        if capture_hydrogen_state_path and z == 1:
            carbon_state_path["hydrogen_history"].extend(
                _native_element_rows(
                    phase_code=21,
                    phase="calc_hmc_all_map_global_to_hydrogen_entry",
                    element_z=1,
                    values=global_xilevg_by_index,
                )
            )
        if (capture_carbon_state_path or capture_hydrogen_state_path) and z == 6:
            carbon_state_path["carbon_correlation_stage_totals"].extend(
                _stage_totals_from_native_rows(
                    phase_code=20,
                    phase="calc_hmc_all_map_global_to_element_entry_stage_total",
                    element_z=6,
                    values=global_xilevg_by_index,
                )
            )

        ion_rate_context = CalcIonRatesContext(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            radiation=effective_request.radiation,
            covering_fraction=float(effective_request.covering_fraction),
            turbulent_velocity_km_s=float(effective_request.turbulent_velocity_km_s),
            neutral_h_density_cm3=float(effective_request.neutral_h_density_cm3),
            ionized_h_density_cm3=float(effective_request.ionized_h_density_cm3),
            lfast=int(effective_request.lfast),
            strict_context=bool(effective_request.strict_context),
        )
        with profile_component(
            profile_control or {},
            "calc_hmc_all.pre_matrix_solver",
            element_z=int(z),
        ):
            calc_rates_by_stage, preliminary, source_limits = pre_matrix_solver(
                master,
                derived,
                element_z=z,
                context=ion_rate_context,
                critf=float(effective_request.critf),
                dispatcher=dispatcher,
            )
        pre_matrix_ok = all(item.ready for item in calc_rates_by_stage.values())
        all_pre_matrix_ready &= pre_matrix_ok
        if effective_request.use_source_ion_limits:
            selected_min = int(source_limits.mml)
            selected_max = int(source_limits.mmu)
        else:
            selected_min = int(effective_request.min_ion_stage)
            selected_max = int(effective_request.max_ion_stage)
        mml[z] = selected_min
        mmu[z] = selected_max

        for stage, item in calc_rates_by_stage.items():
            key = (z, int(stage))
            preliminary_pirt[key] = float(item.pirti)
            preliminary_rrrt[key] = float(item.rrrti)
            # calc_hmc_element starts its returned arrays with these
            # preliminary values; active ions are overwritten by the second
            # calc_hmc_ion pass below.
            pirt[key] = float(item.pirti)
            rrrt[key] = float(item.rrrti)
        for stage in range(1, preliminary.n_rates + 2):
            preliminary_ion_fractions[(z, stage)] = float(preliminary.fractions[stage])
        if capture_hydrogen_state_path and z == 1:
            for stage, item in sorted(calc_rates_by_stage.items()):
                stage_int = int(stage)
                carbon_state_path["hydrogen_history"].append(
                    {
                        "source": "python",
                        "phase_code": 25,
                        "phase": "calc_hmc_all_preliminary_hydrogen_rates",
                        "element_z": 1,
                        "ion_stage": stage_int,
                        "ion_index": int(getattr(item, "ion_index", 0)),
                        "photoionization_rate": float(item.pirti),
                        "recombination_rate": float(item.rrrti),
                        "preliminary_ion_fraction": float(
                            preliminary.fractions[stage_int]
                            if 0 <= stage_int < preliminary.fractions.size
                            else 0.0
                        ),
                    }
                )

        context = ElementEquilibriumContext(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            min_ion_stage=selected_min,
            max_ion_stage=selected_max,
            radiation=effective_request.radiation,
            escape=request.escape,
            covering_fraction=float(effective_request.covering_fraction),
            turbulent_velocity_km_s=float(effective_request.turbulent_velocity_km_s),
            neutral_h_density_cm3=float(effective_request.neutral_h_density_cm3),
            ionized_h_density_cm3=float(effective_request.ionized_h_density_cm3),
            abundance=abundance,
            lfast=int(effective_request.lfast),
            initial_populations=effective_request.initial_populations,
            initial_global_populations=effective_request.initial_global_populations,
            terminal_continuum_seed_mode=effective_request.terminal_continuum_seed_mode,
            strict_context=bool(effective_request.strict_context),
            capture_lucy_trace=bool(effective_request.capture_lucy_trace),
            allow_lstsq_fallback=bool(effective_request.allow_lstsq_fallback),
            allow_dense_matrix_rescue=bool(effective_request.allow_dense_matrix_rescue),
            initial_leveltemp_workspace=leveltemp_workspace,
            initial_leveltemp_owner_by_column=leveltemp_owner_by_column,
        )
        with profile_component(
            profile_control or {},
            "calc_hmc_all.element_solver",
            element_z=int(z),
        ):
            equilibrium = element_solver(
                master,
                derived,
                element_z=z,
                context=context,
                dispatcher=dispatcher,
            )
        solve = equilibrium.solve
        ready = bool(equilibrium.full_element_direct_solve_ready and solve is not None)
        all_ready &= ready
        final_leveltemp_workspace = getattr(
            equilibrium.assembly, "leveltemp_workspace_final", None
        )
        if final_leveltemp_workspace is not None:
            leveltemp_workspace = final_leveltemp_workspace
            leveltemp_owner_by_column = {
                int(index): dict(owner)
                for index, owner in getattr(
                    equilibrium.assembly, "leveltemp_owner_by_column", {}
                ).items()
            }
        if solve is None:
            raise CalcHMCAllError(f"element Z={z} did not produce a population solution")

        if capture_hydrogen_state_path and z == 1:
            basis = equilibrium.assembly.basis
            initial = np.asarray(equilibrium.assembly.initial_populations, dtype=float)

            def _hydrogen_compact_identity(compact_index: int) -> Dict[str, int]:
                basis_row = basis.row(int(compact_index))
                ion_stage = int(basis.ion_stage[int(compact_index)])
                role = next(
                    (
                        item for item in reversed(basis_row.roles)
                        if int(item.get("ion_stage", 0)) == ion_stage
                    ),
                    basis_row.roles[-1] if basis_row.roles else {},
                )
                local_level = int(role.get("local_level", 0))
                return {
                    "element_z": 1,
                    "superlevel": int(basis_row.superlevel),
                    "ion_counter": int(basis_row.ion_counter),
                    "ion_stage": ion_stage,
                    "ion_index": int(role.get("ion_index", 0)),
                    "local_level": local_level,
                    "global_index": int(
                        global_level_index_by_key.get((1, ion_stage, local_level), 0)
                    ),
                }

            def _append_hydrogen_compact(
                phase_code: int,
                phase: str,
                compact_index: int,
                population: float,
                *,
                outer_iteration: int = 0,
                fixed_iteration: int = 0,
            ) -> None:
                identity = _hydrogen_compact_identity(compact_index)
                identity["ion_index"] = 0
                identity["local_level"] = 0
                identity["global_index"] = 0
                carbon_state_path["hydrogen_history"].append(
                    {
                        "source": "python",
                        "phase_code": int(phase_code),
                        "phase": str(phase),
                        "outer_iteration": int(outer_iteration),
                        "fixed_iteration": int(fixed_iteration),
                        "compact_index": int(compact_index),
                        "full_element_index": 0,
                        "population": float(population),
                        **identity,
                    }
                )

            for compact_index in range(1, int(basis.n_rows) + 1):
                _append_hydrogen_compact(
                    30,
                    "calc_hmc_element_pre_msolvelucy",
                    compact_index,
                    float(initial[compact_index]),
                )

            trace = solve.trace
            if trace is not None:
                for row in trace.outer_level_rows:
                    compact_index = int(row["compact_index"])
                    outer = int(row["outer_iteration"])
                    _append_hydrogen_compact(
                        40, "msolvelucy_outer_start", compact_index,
                        float(row["population_outer_start"]),
                        outer_iteration=outer,
                    )
                    _append_hydrogen_compact(
                        50, "msolvelucy_post_condensed", compact_index,
                        float(row["population_after_condensed"]),
                        outer_iteration=outer,
                    )
                    _append_hydrogen_compact(
                        70, "msolvelucy_post_fixed_point_outer", compact_index,
                        float(row["population_after_fixed_point"]),
                        outer_iteration=outer,
                        fixed_iteration=int(row["fixed_iterations_this_outer"]),
                    )
                for row in trace.fixed_point_rows:
                    _append_hydrogen_compact(
                        60, "msolvelucy_fixed_point_after_normalization",
                        int(row["compact_index"]),
                        float(row["population_after"]),
                        outer_iteration=int(row["outer_iteration"]),
                        fixed_iteration=int(row["fixed_iteration"]),
                    )
                outer_groups: Dict[int, List[Dict[str, Any]]] = {}
                for row in trace.outer_level_rows:
                    outer_groups.setdefault(int(row["outer_iteration"]), []).append(row)
                counter_to_stage = {
                    int(block.ion_counter): int(block.ion_stage)
                    for block in basis.blocks
                }
                for outer, rows in sorted(outer_groups.items()):
                    totals: Dict[int, float] = {}
                    for row in sorted(rows, key=lambda item: int(item["compact_index"])):
                        compact_index = int(row["compact_index"])
                        if compact_index >= int(basis.n_rows):
                            continue
                        counter = int(row["ion_counter"])
                        totals[counter] = totals.get(counter, 0.0) + float(
                            row["population_outer_start"]
                        )
                    for counter, total_value in sorted(totals.items()):
                        carbon_state_path["hydrogen_history"].append(
                            {
                                "source": "python",
                                "phase_code": 41,
                                "phase": "msolvelucy_outer_start_xtot",
                                "element_z": 1,
                                "outer_iteration": int(outer),
                                "ion_counter": int(counter),
                                "ion_stage": int(counter_to_stage.get(counter, 0)),
                                "population_total": float(total_value),
                            }
                        )

            final_populations = np.asarray(solve.populations, dtype=float)
            for compact_index in range(1, int(basis.n_rows) + 1):
                _append_hydrogen_compact(
                    80, "msolvelucy_final_vector", compact_index,
                    float(final_populations[compact_index - 1]),
                    outer_iteration=int(solve.outer_iterations),
                )
            counter_to_stage = {
                int(block.ion_counter): int(block.ion_stage)
                for block in basis.blocks
            }
            source_totals = np.asarray(solve.ion_population_totals, dtype=float)
            final_totals = np.asarray(
                solve.ion_population_totals_final_vector, dtype=float
            )
            for counter, stage in sorted(counter_to_stage.items()):
                slot = counter - 1
                if 0 <= slot < source_totals.size:
                    carbon_state_path["hydrogen_history"].append(
                        {
                            "source": "python",
                            "phase_code": 90,
                            "phase": "msolvelucy_final_outer_start_xtot",
                            "element_z": 1,
                            "outer_iteration": int(solve.outer_iterations),
                            "ion_counter": counter,
                            "ion_stage": stage,
                            "population_total": float(source_totals[slot]),
                        }
                    )
                if 0 <= slot < final_totals.size:
                    carbon_state_path["hydrogen_history"].append(
                        {
                            "source": "python",
                            "phase_code": 100,
                            "phase": "calc_hmc_element_final_vector_xii",
                            "element_z": 1,
                            "outer_iteration": int(solve.outer_iterations),
                            "ion_counter": counter,
                            "ion_stage": stage,
                            "population_total": float(final_totals[slot]),
                        }
                    )

        if capture_carbon_state_path and z == 6:
            basis = equilibrium.assembly.basis
            initial = np.asarray(equilibrium.assembly.initial_populations, dtype=float)

            def _compact_identity(compact_index: int) -> Dict[str, int]:
                basis_row = basis.row(int(compact_index))
                ion_stage = int(basis.ion_stage[int(compact_index)])
                role = next(
                    (
                        item for item in reversed(basis_row.roles)
                        if int(item.get("ion_stage", 0)) == ion_stage
                    ),
                    basis_row.roles[-1] if basis_row.roles else {},
                )
                return {
                    "superlevel": int(basis_row.superlevel),
                    "ion_counter": int(basis_row.ion_counter),
                    "ion_stage": ion_stage,
                    "ion_index": int(role.get("ion_index", 0)),
                    "local_level": int(role.get("local_level", 0)),
                    "global_index": int(
                        global_level_index_by_key.get(
                            (6, ion_stage, int(role.get("local_level", 0))), 0
                        )
                    ),
                }

            def _append_compact(
                phase_code: int,
                phase: str,
                compact_index: int,
                population: float,
                *,
                outer_iteration: int = 0,
                fixed_iteration: int = 0,
            ) -> None:
                identity = _compact_identity(compact_index)
                # The original msolvelucy interface owns only compact-row,
                # superlevel and ion-counter identities.  Keep native/global
                # endpoint fields zero for phases 30--80 so the Python and
                # Fortran probes compare the same caller-visible state.
                identity["ion_index"] = 0
                identity["local_level"] = 0
                identity["global_index"] = 0
                carbon_state_path["levels"].append(
                    {
                        "source": "python",
                        "phase_code": int(phase_code),
                        "phase": str(phase),
                        "outer_iteration": int(outer_iteration),
                        "fixed_iteration": int(fixed_iteration),
                        "compact_index": int(compact_index),
                        "full_element_index": 0,
                        "population": float(population),
                        **identity,
                    }
                )

            for compact_index in range(1, int(basis.n_rows) + 1):
                _append_compact(
                    30,
                    "calc_hmc_element_pre_msolvelucy",
                    compact_index,
                    float(initial[compact_index]),
                )

            trace = solve.trace
            if trace is not None:
                for row in trace.outer_level_rows:
                    compact_index = int(row["compact_index"])
                    outer = int(row["outer_iteration"])
                    _append_compact(
                        40, "msolvelucy_outer_start", compact_index,
                        float(row["population_outer_start"]),
                        outer_iteration=outer,
                    )
                    _append_compact(
                        50, "msolvelucy_post_condensed", compact_index,
                        float(row["population_after_condensed"]),
                        outer_iteration=outer,
                    )
                    _append_compact(
                        70, "msolvelucy_post_fixed_point_outer", compact_index,
                        float(row["population_after_fixed_point"]),
                        outer_iteration=outer,
                        fixed_iteration=int(row["fixed_iterations_this_outer"]),
                    )
                for row in trace.fixed_point_rows:
                    _append_compact(
                        60, "msolvelucy_fixed_point_after_normalization",
                        int(row["compact_index"]),
                        float(row["population_after"]),
                        outer_iteration=int(row["outer_iteration"]),
                        fixed_iteration=int(row["fixed_iteration"]),
                    )
                # Source xtot is accumulated from the vector at the start of
                # every outer iteration.  Group the traced rows in the same
                # compact-index order.
                outer_groups: Dict[int, List[Dict[str, Any]]] = {}
                for row in trace.outer_level_rows:
                    outer_groups.setdefault(int(row["outer_iteration"]), []).append(row)
                counter_to_stage = {
                    int(block.ion_counter): int(block.ion_stage)
                    for block in basis.blocks
                }
                for outer, rows in sorted(outer_groups.items()):
                    totals: Dict[int, float] = {}
                    for row in sorted(rows, key=lambda item: int(item["compact_index"])):
                        compact_index = int(row["compact_index"])
                        if compact_index >= int(basis.n_rows):
                            continue
                        counter = int(row["ion_counter"])
                        totals[counter] = totals.get(counter, 0.0) + float(
                            row["population_outer_start"]
                        )
                    for counter, total_value in sorted(totals.items()):
                        carbon_state_path["stage_totals"].append(
                            {
                                "source": "python",
                                "phase_code": 41,
                                "phase": "msolvelucy_outer_start_xtot",
                                "outer_iteration": int(outer),
                                "ion_counter": int(counter),
                                "ion_stage": int(counter_to_stage.get(counter, 0)),
                                "population_total": float(total_value),
                            }
                        )

            final_populations = np.asarray(solve.populations, dtype=float)
            for compact_index in range(1, int(basis.n_rows) + 1):
                _append_compact(
                    80, "msolvelucy_final_vector", compact_index,
                    float(final_populations[compact_index - 1]),
                    outer_iteration=int(solve.outer_iterations),
                )
            counter_to_stage = {
                int(block.ion_counter): int(block.ion_stage)
                for block in basis.blocks
            }
            source_totals = np.asarray(solve.ion_population_totals, dtype=float)
            final_totals = np.asarray(
                solve.ion_population_totals_final_vector, dtype=float
            )
            for counter, stage in sorted(counter_to_stage.items()):
                slot = counter - 1
                if 0 <= slot < source_totals.size:
                    carbon_state_path["stage_totals"].append(
                        {
                            "source": "python",
                            "phase_code": 90,
                            "phase": "msolvelucy_final_outer_start_xtot",
                            "outer_iteration": int(solve.outer_iterations),
                            "ion_counter": counter,
                            "ion_stage": stage,
                            "population_total": float(source_totals[slot]),
                        }
                    )
                if 0 <= slot < final_totals.size:
                    carbon_state_path["stage_totals"].append(
                        {
                            "source": "python",
                            "phase_code": 100,
                            "phase": "calc_hmc_element_final_vector_xii",
                            "outer_iteration": int(solve.outer_iterations),
                            "ion_counter": counter,
                            "ion_stage": stage,
                            "population_total": float(final_totals[slot]),
                        }
                    )

        second_pass_pirt: Dict[int, float] = {}
        second_pass_rrrt: Dict[int, float] = {}
        for ion_summary in getattr(equilibrium.assembly, "ion_summaries", ()):
            stage = int(ion_summary.ion_stage)
            second_pass_pirt[stage] = float(ion_summary.second_pass_pirt)
            second_pass_rrrt[stage] = float(ion_summary.second_pass_rrrt)
            pirt[(z, stage)] = float(ion_summary.second_pass_pirt)
            rrrt[(z, stage)] = float(ion_summary.second_pass_rrrt)

        element_ht = float(solve.heating) * abundance
        element_cl = float(solve.cooling) * abundance
        element_ht2 = float(solve.heating2) * abundance
        element_cl2 = float(solve.cooling2) * abundance
        htt[z], cll[z], htt2[z], cll2[z] = element_ht, element_cl, element_ht2, element_cl2
        httot += element_ht
        cltot += element_cl
        httot2 += element_ht2
        cltot2 += element_cl2

        stage_fractions: Dict[int, float] = {}
        source_xtot = np.asarray(solve.ion_population_totals, dtype=float)
        final_xii = np.asarray(
            getattr(solve, "ion_population_totals_final_vector", source_xtot),
            dtype=float,
        )
        for selected_slot, block in enumerate(equilibrium.assembly.basis.blocks):
            # Source ``nionp`` counts every ion of the element before the
            # active-stage test, so selected blocks may begin at a slot > 0.
            # ``calc_hmc_element`` maps returned ``x`` into ``xii`` after the
            # solve, while ``msolvelucy`` accumulates diagnostic ``xtot`` from
            # ``xo`` at the start of the final outer iteration.  These vectors
            # are intentionally distinct and must not share one Python array.
            # The fallback preserves compatibility with synthetic test doubles
            # that predate the explicit final-vector total.
            ion_slot = int(getattr(block, "ion_counter", selected_slot + 1)) - 1
            fraction = float(final_xii[ion_slot])
            stage = int(block.ion_stage)
            stage_fractions[stage] = fraction
            ion_fractions[(z, stage)] = fraction
            stotg[(z, stage)] = float(solve.ionization_totals[ion_slot])
            atotg[(z, stage)] = float(solve.recombination_totals[ion_slot])
            fstotg[(z, stage)] = np.asarray(solve.ionization_components[:, ion_slot], dtype=float).copy()
            fatotg[(z, stage)] = np.asarray(solve.recombination_components[:, ion_slot], dtype=float).copy()
            xtotg[(z, stage)] = float(source_xtot[ion_slot])
            enelec += fraction * float(stage - 1) * abundance

        xisum = float(sum(stage_fractions.values()))
        fully_stripped = max(0.0, 1.0 - xisum)
        if fully_stripped > 0.0:
            ion_fractions[(z, z + 1)] = fully_stripped
        enelec += fully_stripped * float(z) * abundance

        populations = np.asarray(solve.populations, dtype=float)
        lte_source = getattr(equilibrium.assembly, "lte_populations", None)
        if lte_source is None:
            # Compatibility for synthetic/legacy assemblies predating the
            # explicit source ``rnise`` field.
            lte_source = equilibrium.assembly.initial_populations
        lte = np.asarray(lte_source, dtype=float)
        lte_has_guard = lte.size == populations.size + 1
        nlev_by_stage = {
            int(block.ion_stage): int(block.nlev)
            for block in equilibrium.assembly.basis.blocks
        }
        for row in equilibrium.assembly.basis.rows:
            idx = row.compact_index - 1
            for role in row.roles:
                key = _role_key(z, role)
                if key is None:
                    continue
                pop = float(populations[idx])
                lte_index = row.compact_index if lte_has_guard else idx
                rn = float(lte[lte_index]) if lte_index < lte.size else 0.0
                local_level = int(key[2])
                ion_nlev = int(nlev_by_stage.get(int(key[1]), 0))
                is_final_continuum = bool(ion_nlev > 0 and local_level == ion_nlev)

                if not source_global_alias_writeback:
                    xilevg[key] = pop
                    rnisg[key] = rn
                    # calc_hmc_element writes bileve for spectroscopic rows using
                    # 1e-37. calc_hmc_all recomputes only the final continuum row
                    # with 1e-48. Preserve the literal two-floor source rule.
                    bilevg[key] = pop / (
                        rn + (1.0e-48 if is_final_continuum else 1.0e-37)
                    )
                gammag[key] = float(solve.gamma[idx])
                alphag[key] = float(solve.alpha[idx])
                fgammag[key] = np.asarray(solve.fgamma[:, idx], dtype=float).copy()
                falphag[key] = np.asarray(solve.falpha[:, idx], dtype=float).copy()
                # calc_hmc_all copies the dominant-record indices only for
                # mm=1..nlev-1. The final continuum row retains its zeroed
                # global-array value even though gamma/alpha are copied.
                igammamaxg[key] = 0 if is_final_continuum else int(solve.igammamax_record[idx])
                ialphamaxg[key] = 0 if is_final_continuum else int(solve.ialphamax_record[idx])

        if source_global_alias_writeback:
            # Reproduce the two distinct source loops exactly:
            #
            # 1. ``calc_hmc_element`` maps the selected compact solution back
            #    into a full-element ``xileve/rnise/bileve`` workspace while
            #    zeroing every inactive ion.  Adjacent ion blocks overlap by
            #    one position because ``ipmat = ipmat + nlev - 1``.
            # 2. ``calc_hmc_all`` then writes every native ion level to its
            #    distinct global ``npilev`` index.  A shared element-workspace
            #    position is therefore copied to both the lower-ion continuum
            #    and next-ion ground rows.  The continuum copy recomputes
            #    ``bilevg`` with the literal 1d-48 floor; all other rows retain
            #    the 1e-37 ``calc_hmc_element`` rule.
            all_ions = [
                (
                    int(ion_index),
                    int(ion_stages[ion_index]),
                    int(nlevs[ion_index]),
                )
                for ion_index in range(
                    1,
                    min(n_ions + 1, ion_stages.size, ion_elements.size, nlevs.size),
                )
                if int(ion_elements[ion_index]) == z
            ]
            full_nrows = 1 + sum(max(0, nlev - 1) for _, _, nlev in all_ions)
            full_x = np.zeros(full_nrows + 1, dtype=float)
            full_rn = np.zeros(full_nrows + 1, dtype=float)
            full_bile = np.zeros(full_nrows + 1, dtype=float)
            block_by_ion = {
                int(block.ion_index): block
                for block in equilibrium.assembly.basis.blocks
            }

            ipmat = 0
            for ion_index, _stage, nlev in all_ions:
                block = block_by_ion.get(ion_index)
                if block is not None:
                    for local_level in range(1, nlev + 1):
                        compact_index = int(block.compact_index(local_level))
                        compact_zero = compact_index - 1
                        full_index = ipmat + local_level
                        pop = float(populations[compact_zero])
                        lte_index = compact_index if lte_has_guard else compact_zero
                        rn = float(lte[lte_index]) if lte_index < lte.size else 0.0
                        full_x[full_index] = pop
                        full_rn[full_index] = rn
                        full_bile[full_index] = pop / (rn + 1.0e-37)
                else:
                    # Literal inactive-ion branch in calc_hmc_element.f90.
                    for local_level in range(1, nlev + 1):
                        full_index = ipmat + local_level
                        full_x[full_index] = 0.0
                        full_rn[full_index] = 0.0
                        full_bile[full_index] = 0.0
                ipmat += nlev - 1

            if capture_carbon_state_path and z == 6:
                full_offset = 0
                for ion_index, stage, nlev in all_ions:
                    for local_level in range(1, nlev + 1):
                        full_index = full_offset + local_level
                        global_index = int(
                            global_level_index_by_key.get(
                                (6, int(stage), local_level), 0
                            )
                        )
                        carbon_state_path["levels"].append(
                            {
                                "source": "python",
                                "phase_code": 110,
                                "phase": "calc_hmc_element_workspace_writeback",
                                "outer_iteration": int(solve.outer_iterations),
                                "fixed_iteration": 0,
                                "compact_index": int(
                                    block_by_ion[ion_index].compact_index(local_level)
                                    if ion_index in block_by_ion else 0
                                ),
                                "superlevel": int(
                                    basis.row(block_by_ion[ion_index].compact_index(local_level)).superlevel
                                    if ion_index in block_by_ion else 0
                                ),
                                "ion_counter": int(
                                    getattr(block_by_ion.get(ion_index), "ion_counter", 0)
                                ),
                                "ion_stage": int(stage),
                                "ion_index": int(ion_index),
                                "local_level": int(local_level),
                                "global_index": global_index,
                                "full_element_index": int(full_index),
                                "population": float(full_x[full_index]),
                            }
                        )
                    full_offset += nlev - 1

            if capture_hydrogen_state_path and z == 1:
                full_offset = 0
                for ion_index, stage, nlev in all_ions:
                    for local_level in range(1, nlev + 1):
                        full_index = full_offset + local_level
                        global_index = int(
                            global_level_index_by_key.get(
                                (1, int(stage), local_level), 0
                            )
                        )
                        carbon_state_path["hydrogen_history"].append(
                            {
                                "source": "python",
                                "phase_code": 110,
                                "phase": "calc_hmc_element_workspace_writeback",
                                "element_z": 1,
                                "outer_iteration": int(solve.outer_iterations),
                                "fixed_iteration": 0,
                                "compact_index": int(
                                    block_by_ion[ion_index].compact_index(local_level)
                                    if ion_index in block_by_ion else 0
                                ),
                                "superlevel": int(
                                    basis.row(block_by_ion[ion_index].compact_index(local_level)).superlevel
                                    if ion_index in block_by_ion else 0
                                ),
                                "ion_counter": int(
                                    getattr(block_by_ion.get(ion_index), "ion_counter", 0)
                                ),
                                "ion_stage": int(stage),
                                "ion_index": int(ion_index),
                                "local_level": int(local_level),
                                "global_index": global_index,
                                "full_element_index": int(full_index),
                                "population": float(full_x[full_index]),
                            }
                        )
                    full_offset += nlev - 1

            ipmat = 0
            for ion_index, stage, nlev in all_ions:
                for local_level in range(1, nlev + 1):
                    key = (z, stage, local_level)
                    global_index = int(global_level_index_by_key.get(key, 0))
                    if global_index <= 0 or global_index > n_global_levels:
                        continue
                    full_index = ipmat + local_level
                    pop = float(full_x[full_index])
                    rn = float(full_rn[full_index])
                    bile = (
                        pop / (rn + 1.0e-48)
                        if local_level == nlev
                        else float(full_bile[full_index])
                    )
                    global_xilevg_by_index[global_index - 1] = pop
                    global_rnisg_by_index[global_index - 1] = rn
                    global_bilevg_by_index[global_index - 1] = bile
                    xilevg[key] = pop
                    rnisg[key] = rn
                    bilevg[key] = bile
                ipmat += nlev - 1

            if capture_carbon_state_path and z == 6:
                carbon_state_path["levels"].extend(
                    _native_element_rows(
                        phase_code=120,
                        phase="calc_hmc_all_global_writeback",
                        element_z=6,
                        values=global_xilevg_by_index,
                    )
                )
                for lower, upper in zip(all_ions[:-1], all_ions[1:]):
                    lower_ion, lower_stage, lower_nlev = lower
                    upper_ion, upper_stage, _upper_nlev = upper
                    lower_global = int(
                        global_level_index_by_key.get(
                            (6, int(lower_stage), int(lower_nlev)), 0
                        )
                    )
                    upper_global = int(
                        global_level_index_by_key.get(
                            (6, int(upper_stage), 1), 0
                        )
                    )
                    lower_value = (
                        float(global_xilevg_by_index[lower_global - 1])
                        if 1 <= lower_global <= global_xilevg_by_index.size
                        else 0.0
                    )
                    upper_value = (
                        float(global_xilevg_by_index[upper_global - 1])
                        if 1 <= upper_global <= global_xilevg_by_index.size
                        else 0.0
                    )
                    carbon_state_path["aliases"].append(
                        {
                            "source": "python",
                            "phase_code": 130,
                            "phase": "calc_hmc_all_alias_boundary",
                            "lower_ion_index": int(lower_ion),
                            "lower_ion_stage": int(lower_stage),
                            "lower_local_level": int(lower_nlev),
                            "lower_global_index": lower_global,
                            "lower_population": lower_value,
                            "upper_ion_index": int(upper_ion),
                            "upper_ion_stage": int(upper_stage),
                            "upper_local_level": 1,
                            "upper_global_index": upper_global,
                            "upper_population": upper_value,
                            "absolute_difference": abs(lower_value - upper_value),
                        }
                    )
            if capture_hydrogen_state_path and z == 1:
                carbon_state_path["hydrogen_history"].extend(
                    _native_element_rows(
                        phase_code=120,
                        phase="calc_hmc_all_global_writeback",
                        element_z=1,
                        values=global_xilevg_by_index,
                    )
                )
            if (capture_carbon_state_path or capture_hydrogen_state_path) and z == 6:
                carbon_state_path["carbon_correlation_stage_totals"].extend(
                    _stage_totals_from_native_rows(
                        phase_code=120,
                        phase="calc_hmc_all_global_writeback_stage_total",
                        element_z=6,
                        values=global_xilevg_by_index,
                    )
                )

        element_electron_increment = sum(
            value * float(stage - 1) * abundance
            for stage, value in stage_fractions.items()
        ) + fully_stripped * float(z) * abundance
        if capture_carbon_state_path or capture_hydrogen_state_path:
            carbon_state_path["electron_history"].append(
                {
                    "source": "python",
                    "phase_code": 140,
                    "phase": "calc_hmc_all_element_electron_contribution",
                    "element_z": int(z),
                    "element_abundance": float(abundance),
                    "selected_min_ion_stage": int(selected_min),
                    "selected_max_ion_stage": int(selected_max),
                    "xisum": float(xisum),
                    "fully_stripped_fraction": float(fully_stripped),
                    "electron_contribution_increment": float(element_electron_increment),
                    "electron_contribution_after_element": float(enelec),
                }
            )

        element_results.append(
            FixedStateElementResult(
                request=effective_request,
                equilibrium=equilibrium,
                calc_ion_rates=calc_rates_by_stage,
                preliminary_pirt={stage: float(item.pirti) for stage, item in calc_rates_by_stage.items()},
                preliminary_rrrt={stage: float(item.rrrti) for stage, item in calc_rates_by_stage.items()},
                second_pass_pirt=second_pass_pirt,
                second_pass_rrrt=second_pass_rrrt,
                preliminary_istruc=preliminary,
                source_limits=source_limits,
                selected_min_ion_stage=selected_min,
                selected_max_ion_stage=selected_max,
                ion_fractions=stage_fractions,
                preliminary_ion_fractions={
                    stage: float(preliminary.fractions[stage])
                    for stage in range(1, preliminary.n_rates + 2)
                },
                fully_stripped_fraction=fully_stripped,
                heating=element_ht,
                cooling=element_cl,
                heating2=element_ht2,
                cooling2=element_cl2,
                heating_per_abundance=float(solve.heating),
                cooling_per_abundance=float(solve.cooling),
                heating2_per_abundance=float(solve.heating2),
                cooling2_per_abundance=float(solve.cooling2),
                electron_contribution=sum(
                    value * float(stage - 1) * abundance
                    for stage, value in stage_fractions.items()
                ) + fully_stripped * float(z) * abundance,
            )
        )

    if not source_global_alias_writeback:
        # Backward-compatible logical selected-role writeback.  Populate the
        # dense views so callers can transition to native-index ownership
        # without changing fixed-state numerical behavior.
        for key, pop in xilevg.items():
            global_index = int(global_level_index_by_key.get(key, 0))
            if 1 <= global_index <= n_global_levels:
                global_xilevg_by_index[global_index - 1] = float(pop)
                global_rnisg_by_index[global_index - 1] = float(rnisg.get(key, 0.0))
                global_bilevg_by_index[global_index - 1] = float(bilevg.get(key, 0.0))

    # v0.4.44: own the pre-continuum thermal snapshot explicitly.  These
    # values belong to the completed positive-abundance element loop and are
    # captured before comp2/freef/bremem/heatf mutate the final return totals.
    httot_pre_continuum = float(httot)
    cltot_pre_continuum = float(cltot)
    httot2_pre_continuum = float(httot2)
    cltot2_pre_continuum = float(cltot2)

    if continuum_kernel is not None and (
        compton_context is not None
        or free_free_context is not None
        or bremem_context is not None
        or heatf_context is not None
    ):
        raise CalcHMCAllError(
            "continuum_kernel is mutually exclusive with translated continuum contexts"
        )
    if (
        compton_context is not None
        or free_free_context is not None
        or bremem_context is not None
        or heatf_context is not None
    ):
        diagnostics: Dict[str, Any] = {}
        htcomp = 0.0
        clcomp = 0.0
        htfreef = 0.0
        clbrems = 0.0
        brcems = None
        opakc = None
        comp2_result = None
        freef_result = None
        bremem_result = None
        heatf_result = None
        if compton_context is not None:
            with profile_component(profile_control or {}, "calc_hmc_all.comp2"):
                comp2_result, comp2_diagnostics = comp2_continuum_result(
                    compton_context,
                    temperature_k=float(temperature_k),
                    hydrogen_density_cm3=xpx,
                    electron_fraction_xee=float(electron_fraction_xee),
                )
            htcomp = float(comp2_diagnostics["htcomp"])
            clcomp = float(comp2_diagnostics["clcomp"])
            diagnostics.update(comp2_diagnostics)
            diagnostics["cmp1"] = float(comp2_result.cmp1)
            diagnostics["cmp2"] = float(comp2_result.cmp2)
        else:
            diagnostics["comp2_translated"] = False
        if free_free_context is not None:
            with profile_component(profile_control or {}, "calc_hmc_all.freef"):
                freef_result, freef_diagnostics = freef_continuum_result(
                    free_free_context,
                    temperature_k=float(temperature_k),
                    hydrogen_density_cm3=xpx,
                    electron_fraction_xee=float(electron_fraction_xee),
                )
            htfreef = float(freef_result.htfreef_erg_cm3_s)
            opakc = np.asarray(freef_result.opakc_after_cm_inv, dtype=float)
            diagnostics.update(freef_diagnostics)
        else:
            diagnostics["freef_translated"] = False
        if bremem_context is not None:
            if free_free_context is not None:
                if not np.array_equal(
                    np.asarray(bremem_context.epi_eV, dtype=float)[: int(bremem_context.ncn2 or len(bremem_context.epi_eV))],
                    np.asarray(freef_result.epi_eV, dtype=float),
                ):
                    raise CalcHMCAllError(
                        "bremem continuum grid does not match preceding freef state"
                    )
                bremem_n = int(
                    bremem_context.ncn2
                    if bremem_context.ncn2 is not None
                    else len(bremem_context.opakc_before_cm_inv)
                )
                if not np.array_equal(
                    np.asarray(bremem_context.opakc_before_cm_inv, dtype=float)[:bremem_n],
                    np.asarray(freef_result.opakc_after_cm_inv, dtype=float),
                ):
                    raise CalcHMCAllError(
                        "bremem incoming opakc does not match preceding freef output"
                    )
            with profile_component(profile_control or {}, "calc_hmc_all.bremem"):
                bremem_result, bremem_diagnostics = bremem_continuum_result(
                    bremem_context,
                    temperature_k=float(temperature_k),
                    hydrogen_density_cm3=xpx,
                    electron_fraction_xee=float(electron_fraction_xee),
                )
            brcems = np.asarray(bremem_result.brcems_after, dtype=float)
            opakc = np.asarray(bremem_result.opakc_after_cm_inv, dtype=float)
            diagnostics.update(bremem_diagnostics)
        else:
            diagnostics["bremem_translated"] = False

        if heatf_context is not None:
            if comp2_result is None or freef_result is None or bremem_result is None:
                raise CalcHMCAllError(
                    "heatf requires translated comp2, freef, and bremem state"
                )
            heatf_n = int(
                heatf_context.ncn2
                if heatf_context.ncn2 is not None
                else len(heatf_context.epi_eV)
            )
            if not np.array_equal(
                np.asarray(heatf_context.epi_eV, dtype=float)[:heatf_n],
                np.asarray(bremem_result.epi_eV, dtype=float),
            ):
                raise CalcHMCAllError(
                    "heatf continuum grid does not match preceding bremem state"
                )
            if not np.array_equal(
                np.asarray(heatf_context.brcems, dtype=float)[:heatf_n],
                np.asarray(bremem_result.brcems_after, dtype=float),
            ):
                raise CalcHMCAllError(
                    "heatf brcems does not match preceding bremem output"
                )
            diagnostics.update(
                {
                    "calc_hmc_all_httot_before_heatf": httot_pre_continuum,
                    "calc_hmc_all_cltot_before_heatf": cltot_pre_continuum,
                    "calc_hmc_all_httot2_before_heatf": httot2_pre_continuum,
                    "calc_hmc_all_cltot2_before_heatf": cltot2_pre_continuum,
                    "calc_hmc_all_pre_continuum_state_owned_explicitly": True,
                }
            )
            with profile_component(profile_control or {}, "calc_hmc_all.heatf"):
                heatf_result = heatf(
                    bremem_result.epi_eV,
                    bremem_result.brcems_after,
                    temperature_k=float(temperature_k),
                    radius_cm=float(heatf_context.radius_cm),
                    zone_thickness_cm=float(heatf_context.zone_thickness_cm),
                    hydrogen_density_cm3=xpx,
                    electron_fraction_xee=float(electron_fraction_xee),
                    htfreef_erg_cm3_s=htfreef,
                    cmp1=float(comp2_result.cmp1),
                    cmp2=float(comp2_result.cmp2),
                    httot_before=httot,
                    cltot_before=cltot,
                    httot2_before=httot2,
                    cltot2_before=cltot2,
                    ncn2=heatf_n,
                )
            htcomp = float(heatf_result.htcomp_erg_cm3_s)
            clcomp = float(heatf_result.clcomp_erg_cm3_s)
            clbrems = float(heatf_result.clbrems_erg_cm3_s)
            diagnostics.update(
                {
                    "heatf_translated": True,
                    "heatf_source_file": heatf_result.source_file,
                    "heatf_context_source": heatf_context.source,
                    "heatf_source_order_accumulation": True,
                    "missing_source_sequence": "",
                    "calc_hmc_all_continuum_source_sequence_complete": True,
                    "calc_hmc_all_fixed_state_thermal_complete": True,
                }
            )
            continuum = FixedStateContinuumResult(
                heating=float(htcomp + htfreef),
                cooling=float(clcomp + clbrems),
                heating2=float(htcomp + htfreef),
                cooling2=float(clcomp + clbrems),
                htcomp=htcomp,
                clcomp=clcomp,
                clbrems=clbrems,
                htfreef=htfreef,
                brcems=brcems,
                opakc=opakc,
                httot_after=float(heatf_result.httot_after),
                cltot_after=float(heatf_result.cltot_after),
                httot2_after=float(heatf_result.httot2_after),
                cltot2_after=float(heatf_result.cltot2_after),
                hmctot_after=float(heatf_result.hmctot),
                complete=True,
                diagnostics=diagnostics,
            )
        else:
            diagnostics["heatf_translated"] = False
            missing = []
            if compton_context is None:
                missing.append("comp2")
            if free_free_context is None:
                missing.append("freef")
            if bremem_context is None:
                missing.append("bremem")
            missing.append("heatf")
            diagnostics["missing_source_sequence"] = " -> ".join(missing)
            continuum = FixedStateContinuumResult(
                # ``comp2``, ``freef``, and ``bremem`` produce coefficients
                # and workspaces. ``heatf`` performs source accumulation.
                heating=0.0,
                cooling=0.0,
                heating2=0.0,
                cooling2=0.0,
                htcomp=htcomp,
                clcomp=clcomp,
                clbrems=clbrems,
                htfreef=htfreef,
                brcems=brcems,
                opakc=opakc,
                complete=False,
                diagnostics=diagnostics,
            )
    elif continuum_kernel is None:
        continuum = FixedStateContinuumResult(
            complete=False,
            diagnostics={
                "status": "deferred",
                "comp2_translated": False,
                "freef_translated": False,
                "bremem_translated": False,
                "heatf_translated": False,
                "missing_source_sequence": "comp2 -> freef -> bremem -> heatf",
            },
        )
    else:
        continuum = continuum_kernel(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            pressure=float(pressure),
            lcdd=int(lcdd),
            element_results=tuple(element_results),
        )
        if not isinstance(continuum, FixedStateContinuumResult):
            raise CalcHMCAllError("continuum_kernel must return FixedStateContinuumResult")

    if continuum.complete and all(
        value is not None
        for value in (
            continuum.httot_after,
            continuum.cltot_after,
            continuum.httot2_after,
            continuum.cltot2_after,
            continuum.hmctot_after,
        )
    ):
        httot = float(continuum.httot_after)
        cltot = float(continuum.cltot_after)
        httot2 = float(continuum.httot2_after)
        cltot2 = float(continuum.cltot2_after)
        hmctot = float(continuum.hmctot_after)
    else:
        httot += float(continuum.heating)
        cltot += float(continuum.cooling)
        httot2 += float(continuum.heating2)
        cltot2 += float(continuum.cooling2)
        hmctot = 2.0 * (httot - cltot) / (1.0e-37 + httot + cltot)
    elcter = float(electron_fraction_xee) - enelec
    complete = bool(all_pre_matrix_ready and all_ready and charge_scope_complete and continuum.complete)

    return FixedStateCalcHMCAllResult(
        temperature_k=float(temperature_k),
        hydrogen_density_cm3=xpx,
        electron_fraction_xee=float(electron_fraction_xee),
        electron_density_cm3=xpx * float(electron_fraction_xee),
        neutral_h_density_cm3=float(live_xh0),
        ionized_h_density_cm3=float(live_xh1),
        hydrogen_ground_fraction=float(hydrogen_ground_fraction),
        hydrogen_abundance=float(hydrogen_abundance),
        pressure=float(pressure),
        lcdd=int(lcdd),
        element_results=element_results,
        ion_fractions=ion_fractions,
        preliminary_ion_fractions=preliminary_ion_fractions,
        preliminary_rrrt=preliminary_rrrt,
        preliminary_pirt=preliminary_pirt,
        rrrt=rrrt,
        pirt=pirt,
        htt=htt,
        cll=cll,
        htt2=htt2,
        cll2=cll2,
        xilevg=xilevg,
        rnisg=rnisg,
        bilevg=bilevg,
        gammag=gammag,
        alphag=alphag,
        fgammag=fgammag,
        falphag=falphag,
        igammamaxg=igammamaxg,
        ialphamaxg=ialphamaxg,
        stotg=stotg,
        atotg=atotg,
        fstotg=fstotg,
        fatotg=fatotg,
        xtotg=xtotg,
        mml=mml,
        mmu=mmu,
        httot_pre_continuum=httot_pre_continuum,
        cltot_pre_continuum=cltot_pre_continuum,
        httot2_pre_continuum=httot2_pre_continuum,
        cltot2_pre_continuum=cltot2_pre_continuum,
        httot=httot,
        cltot=cltot,
        httot2=httot2,
        cltot2=cltot2,
        hmctot=hmctot,
        elcter=elcter,
        electron_contribution=enelec,
        continuum=continuum,
        pre_matrix_ready=all_pre_matrix_ready,
        element_loop_ready=all_ready,
        charge_closure_scope_complete=charge_scope_complete,
        complete_fixed_state_ready=complete,
        carbon_state_path=carbon_state_path,
        leveltemp_workspace=leveltemp_workspace,
        leveltemp_owner_by_column=leveltemp_owner_by_column,
        global_element_index_by_z=global_element_index_by_z,
        global_ion_index_by_key=global_ion_index_by_key,
        global_level_index_by_key=global_level_index_by_key,
        global_xilevg_by_index=global_xilevg_by_index,
        global_bilevg_by_index=global_bilevg_by_index,
        global_rnisg_by_index=global_rnisg_by_index,
        diagnostics={
            "source_file": "xstar/xstarlib/src/calc_hmc_all.f90",
            "source_mode": "fixed_temperature_fixed_electron_fraction",
            "n_elements": len(element_results),
            "pre_matrix_ready": bool(all_pre_matrix_ready),
            "calc_ion_rates_translated": True,
            "istruc_ioneqm_translated": True,
            "second_pass_calc_hmc_ion_rates_translated": True,
            "global_level_mapping_source": "derivedpointers.npilev(local_ordinal,ion_index)",
            "global_element_index_source": global_element_index_source,
            "continuum_complete": bool(continuum.complete),
            "charge_scope_reference": charge_scope_reference,
            "required_element_z": sorted(required_element_z_set),
            "requested_element_z": sorted(requested_element_z),
            "missing_required_element_z": sorted(required_element_z_set - requested_element_z),
            "extra_requested_element_z": sorted(requested_element_z - required_element_z_set),
            "calc_hmc_all_fixed_state_thermal_complete": bool(continuum.complete),
            "calc_hmc_all_fixed_state_charge_complete": bool(charge_scope_complete),
            "remaining_source_sequence": "dsec" if complete else "complete fixed-state calc_hmc_all closure",
            "dsec_available_as_stateful_outer_iteration": True,
            "leveltemp_mutable_state_carried_between_elements": True,
            "incoming_leveltemp_workspace_present": initial_leveltemp_workspace is not None,
            "source_global_alias_writeback": bool(source_global_alias_writeback),
            "dense_global_state_ready": bool(n_global_levels > 0),
            "hydrogen_charge_exchange_state_source": "calc_hmc_all_entry_xpx_xilevg1_abel1",
            "incoming_hydrogen_ground_fraction": float(hydrogen_ground_fraction),
            "hydrogen_abundance": float(hydrogen_abundance),
            "neutral_h_density_cm3": float(live_xh0),
            "ionized_h_density_cm3": float(live_xh1),
        },
    )


def register_fixed_state_calc_hmc_all(
    driver: Any,
    *,
    elements: Sequence[FixedStateElementRequest],
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    pressure: float = 0.0,
    lcdd: int = 1,
    continuum_kernel: Optional[ContinuumKernel] = None,
    compton_context: Optional[Comp2Context] = None,
    free_free_context: Optional[FreeFreeContext] = None,
    bremem_context: Optional[BremsstrahlungContext] = None,
    heatf_context: Optional[HeatFContext] = None,
    required_element_z: Optional[Sequence[int]] = None,
    dispatcher: Optional[SourceFaithfulUCalc] = None,
) -> None:
    """Register fixed-state ``calc_hmc_all`` on the source-routine driver."""
    from .driver import XSTARSourceRoutine

    def _handler(state: Any) -> None:
        if state.atomic.master is None or state.atomic.derived is None:
            raise CalcHMCAllError("atomic database state must be initialized first")
        result = calc_hmc_all(
            state.atomic.master,
            state.atomic.derived,
            elements=elements,
            temperature_k=temperature_k,
            hydrogen_density_cm3=hydrogen_density_cm3,
            electron_fraction_xee=electron_fraction_xee,
            pressure=pressure,
            lcdd=lcdd,
            continuum_kernel=continuum_kernel,
            compton_context=compton_context,
            free_free_context=free_free_context,
            bremem_context=bremem_context,
            heatf_context=heatf_context,
            required_element_z=required_element_z,
            dispatcher=dispatcher,
        )
        state.plasma.temperature = result.temperature_k
        state.plasma.xpx = result.hydrogen_density_cm3
        state.plasma.xee = result.electron_fraction_xee
        state.plasma.electron_density = result.electron_density_cm3
        state.plasma.ion_fractions = result.ion_fractions
        state.thermal.heating = result.httot
        state.thermal.cooling = result.cltot
        state.thermal.electron_fraction = result.electron_fraction_xee
        state.thermal.residual = result.hmctot
        state.local_zone.calc_hmc_all = result
        state.local_zone.fixed_state_ready = result.complete_fixed_state_ready
        state.local_zone.source_arrays = {
            "xiin": result.ion_fractions,
            "xitp_preliminary": result.preliminary_ion_fractions,
            "rrrt": result.rrrt,
            "pirt": result.pirt,
            "htt": result.htt,
            "cll": result.cll,
            "htt2": result.htt2,
            "cll2": result.cll2,
            "xilevg": result.xilevg,
            "rnisg": result.rnisg,
            "bilevg": result.bilevg,
            "gammag": result.gammag,
            "alphag": result.alphag,
            "fgammag": result.fgammag,
            "falphag": result.falphag,
            "igammamaxg": result.igammamaxg,
            "ialphamaxg": result.ialphamaxg,
            "stotg": result.stotg,
            "atotg": result.atotg,
            "fstotg": result.fstotg,
            "fatotg": result.fatotg,
            "xtotg": result.xtotg,
            "mml": result.mml,
            "mmu": result.mmu,
        }
        state.outputs["calc_hmc_all_fixed_state"] = result
        state.provenance["calc_hmc_all_fixed_state_ready"] = result.complete_fixed_state_ready

    driver.register_source_routine(XSTARSourceRoutine.CALC_HMC_ALL, _handler)


def _type77_floor_impact_rows(result: FixedStateCalcHMCAllResult) -> List[Dict[str, Any]]:
    """Build a fixed-population source-vs-legacy type-77 floor audit.

    The legacy branch reproduces the pre-v0.4.27 record-wavelength temperature
    floor. It is diagnostic only and never modifies the production matrix.
    """

    rows: List[Dict[str, Any]] = []

    def as_float(value: Any) -> Optional[float]:
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        return out if np.isfinite(out) else None

    for element in result.element_results:
        equilibrium = element.equilibrium
        solve = getattr(equilibrium, "solve", None)
        if solve is None:
            continue
        populations = np.asarray(solve.populations, dtype=float)
        block_by_ion = {
            int(block.ion_index): block for block in equilibrium.assembly.basis.blocks
        }
        for record in getattr(equilibrium.assembly, "record_results", ()):
            if int(record.get("data_type", 0) or 0) != 77:
                continue
            if str(record.get("status", "")) != "evaluated":
                continue
            ion_index = int(record.get("ion_index", 0) or 0)
            block = block_by_ion.get(ion_index)
            if block is None:
                continue
            idest1 = int(record.get("idest1", 0) or 0)
            idest2 = int(record.get("idest2", 0) or 0)
            if idest1 <= 0 or idest2 <= 0:
                continue
            row1 = min(len(populations), int(block.compact_index(idest1)))
            row2 = min(len(populations), int(block.compact_index(idest2)))
            pop1 = float(populations[row1 - 1])
            pop2 = float(populations[row2 - 1])
            source_clu = as_float(record.get("ans1_after_calc_hmc_ion_filter", record.get("ans1")))
            source_cul = as_float(record.get("ans2_after_calc_hmc_ion_filter", record.get("ans2")))
            legacy_clu = as_float(record.get("diag_type77_legacy_record_floor_clu_s^-1"))
            legacy_cul = as_float(record.get("diag_type77_legacy_record_floor_cul_s^-1"))
            if None in {source_clu, source_cul, legacy_clu, legacy_cul}:
                continue
            source_net = float(source_clu) * pop1 - float(source_cul) * pop2
            legacy_net = float(legacy_clu) * pop1 - float(legacy_cul) * pop2
            delta_clu = float(source_clu) - float(legacy_clu)
            delta_cul = float(source_cul) - float(legacy_cul)
            rows.append({
                "element_z": int(element.request.element_z),
                "ion_stage": int(record.get("ion_stage", block.ion_stage) or block.ion_stage),
                "ion_index": ion_index,
                "record": int(record.get("record", 0) or 0),
                "idest1": idest1,
                "idest2": idest2,
                "compact_row_idest1": row1,
                "compact_row_idest2": row2,
                "population_idest1": pop1,
                "population_idest2": pop2,
                "endpoint_energy_difference_eV": record.get("diag_type77_endpoint_energy_difference_eV"),
                "source_floor_wavelength_A": record.get("diag_type77_source_floor_wavelength_A"),
                "record_wavelength_A": record.get("diag_type77_calt77_wavelength_A"),
                "source_log10_temperature_used": record.get("diag_type77_calt77_log10_temperature_used"),
                "legacy_log10_temperature_used": record.get("diag_type77_legacy_record_floor_log10_temperature_used"),
                "source_clu_s_inv": source_clu,
                "source_cul_s_inv": source_cul,
                "legacy_clu_s_inv": legacy_clu,
                "legacy_cul_s_inv": legacy_cul,
                "source_minus_legacy_clu_s_inv": delta_clu,
                "source_minus_legacy_cul_s_inv": delta_cul,
                "source_net_population_flux_s_inv": source_net,
                "legacy_net_population_flux_s_inv": legacy_net,
                "source_minus_legacy_net_population_flux_s_inv": source_net - legacy_net,
                "fixed_population_l1_impact_s_inv": abs(delta_clu * pop1) + abs(delta_cul * pop2),
                "production_operator_uses": "source_endpoint_floor",
                "legacy_branch_role": "diagnostic_only",
            })
    return rows


def write_fixed_state_calc_hmc_all_products(
    result: FixedStateCalcHMCAllResult,
    out_dir: str,
    *,
    port_version: str = "v0.4.44",
) -> Dict[str, str]:
    """Write compact fixed-state ``calc_hmc_all`` diagnostics."""
    import csv
    import json
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ion_csv = out / "xstar_calc_hmc_all_fixed_state_ions.csv"
    with ion_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "ion_stage",
                "preliminary_istruc_fraction", "final_ion_fraction",
                "preliminary_pirt_s_inv", "preliminary_rrrt_s_inv",
                "pirt_s_inv", "rrrt_s_inv",
                "stot_flow_s_inv", "atot_flow_s_inv", "xtot",
            ),
        )
        writer.writeheader()
        ion_keys = sorted(
            set(result.preliminary_ion_fractions)
            | set(result.ion_fractions)
            | set(result.preliminary_pirt)
            | set(result.preliminary_rrrt)
            | set(result.pirt)
            | set(result.rrrt)
            | set(result.stotg)
            | set(result.atotg)
        )
        for z, stage in ion_keys:
            writer.writerow({
                "element_z": z,
                "ion_stage": stage,
                "preliminary_istruc_fraction": result.preliminary_ion_fractions.get((z, stage), 0.0),
                "final_ion_fraction": result.ion_fractions.get((z, stage), 0.0),
                "preliminary_pirt_s_inv": result.preliminary_pirt.get((z, stage), 0.0),
                "preliminary_rrrt_s_inv": result.preliminary_rrrt.get((z, stage), 0.0),
                "pirt_s_inv": result.pirt.get((z, stage), 0.0),
                "rrrt_s_inv": result.rrrt.get((z, stage), 0.0),
                "stot_flow_s_inv": result.stotg.get((z, stage), 0.0),
                "atot_flow_s_inv": result.atotg.get((z, stage), 0.0),
                "xtot": result.xtotg.get((z, stage), 0.0),
            })

    hydrogen_target_csv = out / "xstar_calc_hmc_all_hydrogen_records_488_491.csv"
    hydrogen_target_fields = (
        "element_z", "ion_stage", "ion_index", "record", "data_type", "rate_type",
        "status", "ready", "reason", "idest1", "idest2",
        "diag_packed_endpoint_1", "diag_packed_endpoint_2",
        "diag_lower_endpoint", "diag_upper_endpoint",
        "diag_lower_principal_n", "diag_lower_orbital_l", "diag_lower_label",
        "diag_upper_principal_n", "diag_upper_orbital_l", "diag_upper_label",
        "diag_lower_energy_eV", "diag_upper_energy_eV", "diag_delta_energy_eV",
        "diag_lower_statistical_weight", "diag_upper_statistical_weight",
        "diag_fit_form", "diag_polynomial_coefficients",
        "diag_logarithmic_amplitude", "diag_logarithmic_scale",
        "diag_exponential_scale", "diag_upsilon",
        "ans1", "ans2", "ans5", "ans6",
        "ans1_after_calc_hmc_ion_filter", "ans2_after_calc_hmc_ion_filter",
        "matrix_insertion_status", "n_matrix_terms",
    )
    with hydrogen_target_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=hydrogen_target_fields, extrasaction="ignore")
        writer.writeheader()
        for element in result.element_results:
            if int(element.request.element_z) != 1:
                continue
            assembly = getattr(getattr(element, "equilibrium", None), "assembly", None)
            if assembly is None:
                continue
            term_count = {}
            for term in assembly.terms:
                term_count[int(term.record)] = term_count.get(int(term.record), 0) + 1
            for record_row in assembly.record_results:
                record_number = int(record_row.get("record", 0) or 0)
                if record_number not in {488, 489, 490, 491}:
                    continue
                row = dict(record_row)
                row["element_z"] = 1
                row["n_matrix_terms"] = term_count.get(record_number, 0)
                writer.writerow(row)

    element_csv = out / "xstar_calc_hmc_all_fixed_state_elements.csv"
    with element_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "global_element_index",
                "requested_abundance", "effective_abundance", "abundance_source",
                "abundance", "requested_min_ion_stage", "requested_max_ion_stage",
                "selected_min_ion_stage", "selected_max_ion_stage", "critf",
                "ion_stage_selection", "pre_matrix_ready",
                "heating_per_abundance", "cooling_per_abundance",
                "heating2_per_abundance", "cooling2_per_abundance",
                "heating", "cooling", "heating2", "cooling2",
                "electron_contribution", "fully_stripped_fraction",
                "element_solver_ready",
            ),
        )
        writer.writeheader()
        for item in result.element_results:
            writer.writerow({
                "element_z": item.request.element_z,
                "global_element_index": result.global_element_index_by_z.get(item.request.element_z, 0),
                "requested_abundance": result.diagnostics.get("requested_abundance"),
                "effective_abundance": item.request.abundance,
                "abundance_source": result.diagnostics.get("abundance_source", "fixed_state_request"),
                "abundance": item.request.abundance,
                "requested_min_ion_stage": item.request.min_ion_stage,
                "requested_max_ion_stage": item.request.max_ion_stage,
                "selected_min_ion_stage": item.selected_min_ion_stage,
                "selected_max_ion_stage": item.selected_max_ion_stage,
                "critf": item.request.critf,
                "ion_stage_selection": "source_istruc" if item.request.use_source_ion_limits else "explicit_override",
                "pre_matrix_ready": all(rate.ready for rate in item.calc_ion_rates.values()),
                "heating_per_abundance": item.heating_per_abundance,
                "cooling_per_abundance": item.cooling_per_abundance,
                "heating2_per_abundance": item.heating2_per_abundance,
                "cooling2_per_abundance": item.cooling2_per_abundance,
                "heating": item.heating,
                "cooling": item.cooling,
                "heating2": item.heating2,
                "cooling2": item.cooling2,
                "electron_contribution": item.electron_contribution,
                "fully_stripped_fraction": item.fully_stripped_fraction,
                "element_solver_ready": item.equilibrium.full_element_direct_solve_ready,
            })

    contribution_csv = out / "xstar_calc_hmc_all_calc_ion_rates_records.csv"
    with contribution_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "ion_stage", "ion_index", "record",
                "data_type", "rate_type", "status", "parent_record",
                "parent_threshold_ev", "shell_thresholds_ev", "shell_d_values",
                "effective_threshold_ev", "effective_d",
                "bkhsgo_threshold_ev", "phintfo_threshold_ev",
                "idest1_packed", "idest1", "idest2",
                "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
                "pirti_before", "added_to_pirti", "pirti_after",
                "rrrti_before", "added_to_rrrti", "rrrti_after", "reason",
            ),
        )
        writer.writeheader()
        for item in result.element_results:
            for stage, rate_result in sorted(item.calc_ion_rates.items()):
                for row in rate_result.contributions:
                    writer.writerow({
                        "element_z": item.request.element_z,
                        "ion_stage": stage,
                        "ion_index": rate_result.ion_index,
                        "record": row.record,
                        "data_type": row.data_type,
                        "rate_type": row.rate_type,
                        "status": row.status,
                        "parent_record": row.parent_record,
                        "parent_threshold_ev": row.parent_threshold_ev,
                        "shell_thresholds_ev": ";".join(
                            f"{value:.17e}" for value in row.shell_thresholds_ev
                        ),
                        "shell_d_values": ";".join(
                            f"{value:.17e}" for value in row.shell_d_values
                        ),
                        "effective_threshold_ev": row.effective_threshold_ev,
                        "effective_d": row.effective_d,
                        "bkhsgo_threshold_ev": row.bkhsgo_threshold_ev,
                        "phintfo_threshold_ev": row.phintfo_threshold_ev,
                        "idest1_packed": row.idest1_packed,
                        "idest1": row.idest1,
                        "idest2": row.idest2,
                        "ans1": row.ans1,
                        "ans2": row.ans2,
                        "ans3": row.ans3,
                        "ans4": row.ans4,
                        "ans5": row.ans5,
                        "ans6": row.ans6,
                        "pirti_before": row.pirti_before,
                        "added_to_pirti": row.added_to_pirti,
                        "pirti_after": row.pirti_after,
                        "rrrti_before": row.rrrti_before,
                        "added_to_rrrti": row.added_to_rrrti,
                        "rrrti_after": row.rrrti_after,
                        "reason": row.reason,
                    })

    level_csv = out / "xstar_calc_hmc_all_fixed_state_levels.csv"
    with level_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "ion_stage", "local_level", "global_level_index", "population", "lte_population",
                "departure_coefficient", "gamma", "alpha",
                "igammamax_record", "ialphamax_record",
            ),
        )
        writer.writeheader()
        for key in sorted(result.xilevg):
            z, stage, level = key
            writer.writerow({
                "element_z": z,
                "ion_stage": stage,
                "local_level": level,
                "global_level_index": result.global_level_index_by_key.get(key, 0),
                "population": result.xilevg[key],
                "lte_population": result.rnisg.get(key, 0.0),
                "departure_coefficient": result.bilevg.get(key, 0.0),
                "gamma": result.gammag.get(key, 0.0),
                "alpha": result.alphag.get(key, 0.0),
                "igammamax_record": result.igammamaxg.get(key, 0),
                "ialphamax_record": result.ialphamaxg.get(key, 0),
            })

    type77_rows = _type77_floor_impact_rows(result)
    type77_csv = out / "xstar_calc_hmc_all_type77_floor_impact.csv"
    type77_fields = (
        "element_z", "ion_stage", "ion_index", "record", "idest1", "idest2",
        "compact_row_idest1", "compact_row_idest2", "population_idest1",
        "population_idest2", "endpoint_energy_difference_eV",
        "source_floor_wavelength_A", "record_wavelength_A",
        "source_log10_temperature_used", "legacy_log10_temperature_used",
        "source_clu_s_inv", "source_cul_s_inv", "legacy_clu_s_inv",
        "legacy_cul_s_inv", "source_minus_legacy_clu_s_inv",
        "source_minus_legacy_cul_s_inv", "source_net_population_flux_s_inv",
        "legacy_net_population_flux_s_inv",
        "source_minus_legacy_net_population_flux_s_inv",
        "fixed_population_l1_impact_s_inv", "production_operator_uses",
        "legacy_branch_role",
    )
    with type77_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=type77_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(type77_rows)
    type77_summary = {
        "mode": "diagnostic_fixed_population_source_endpoint_floor_vs_legacy_record_floor",
        "production_operator_uses": "source_endpoint_floor",
        "legacy_values_enter_operator": False,
        "n_records": len(type77_rows),
        "n_records_with_rate_change": sum(
            abs(float(row["source_minus_legacy_clu_s_inv"])) > 0.0
            or abs(float(row["source_minus_legacy_cul_s_inv"])) > 0.0
            for row in type77_rows
        ),
        "max_absolute_rate_change_s_inv": max((
            max(abs(float(row["source_minus_legacy_clu_s_inv"])),
                abs(float(row["source_minus_legacy_cul_s_inv"])))
            for row in type77_rows
        ), default=0.0),
        "sum_fixed_population_l1_impact_s_inv": sum(
            float(row["fixed_population_l1_impact_s_inv"]) for row in type77_rows
        ),
        "max_fixed_population_l1_impact_s_inv": max((
            float(row["fixed_population_l1_impact_s_inv"]) for row in type77_rows
        ), default=0.0),
        "max_absolute_net_flux_change_s_inv": max((
            abs(float(row["source_minus_legacy_net_population_flux_s_inv"]))
            for row in type77_rows
        ), default=0.0),
    }
    type77_json = out / "xstar_calc_hmc_all_type77_floor_impact_summary.json"
    type77_json.write_text(json.dumps(type77_summary, indent=2) + "\n")

    summary = {
        "port_version": port_version,
        "source_routine": "calc_hmc_all",
        "mode": "fixed_temperature_fixed_electron_fraction",
        "temperature_k": result.temperature_k,
        "hydrogen_density_cm3": result.hydrogen_density_cm3,
        "electron_fraction_xee": result.electron_fraction_xee,
        "electron_density_cm3": result.electron_density_cm3,
        "pressure": result.pressure,
        "lcdd": result.lcdd,
        "n_elements": len(result.element_results),
        "n_ion_entries": len(result.ion_fractions),
        "n_preliminary_ion_entries": len(result.preliminary_ion_fractions),
        "n_preliminary_rate_entries": len(result.preliminary_pirt),
        "n_second_pass_rate_entries": len(result.pirt),
        "n_level_entries": len(result.xilevg),
        "n_global_element_mappings": len(result.global_element_index_by_z),
        "n_global_ion_mappings": len(result.global_ion_index_by_key),
        "n_global_level_mappings": len(result.global_level_index_by_key),
        "pre_matrix_ready": result.pre_matrix_ready,
        "httot_pre_continuum": result.httot_pre_continuum,
        "cltot_pre_continuum": result.cltot_pre_continuum,
        "httot2_pre_continuum": result.httot2_pre_continuum,
        "cltot2_pre_continuum": result.cltot2_pre_continuum,
        "httot": result.httot,
        "cltot": result.cltot,
        "httot2": result.httot2,
        "cltot2": result.cltot2,
        "hmctot": result.hmctot,
        "electron_contribution": result.electron_contribution,
        "elcter": result.elcter,
        "element_loop_ready": result.element_loop_ready,
        "charge_closure_scope_complete": result.charge_closure_scope_complete,
        "continuum_complete": result.continuum.complete,
        "comp2_translated": bool(result.continuum.diagnostics.get("comp2_translated", False)),
        "cmpfnc_table_loaded": bool(result.continuum.diagnostics.get("cmpfnc_table_loaded", False)),
        "cmp1": result.continuum.diagnostics.get("cmp1"),
        "cmp2": result.continuum.diagnostics.get("cmp2"),
        "htcomp": result.continuum.htcomp,
        "clcomp": result.continuum.clcomp,
        "htfreef": result.continuum.htfreef,
        "clbrems": result.continuum.clbrems,
        "freef_translated": bool(result.continuum.diagnostics.get("freef_translated", False)),
        "bremem_translated": bool(result.continuum.diagnostics.get("bremem_translated", False)),
        "heatf_translated": bool(result.continuum.diagnostics.get("heatf_translated", False)),
        "complete_fixed_state_ready": result.complete_fixed_state_ready,
        "diagnostics": dict(result.diagnostics),
        "continuum_diagnostics": dict(result.continuum.diagnostics),
        "type77_floor_impact": type77_summary,
    }
    json_path = out / "xstar_calc_hmc_all_fixed_state_summary.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")

    md_path = out / "xstar_calc_hmc_all_fixed_state_summary.md"
    md_path.write_text(
        "# Fixed-state calc_hmc_all summary\n\n"
        f"- Port version: `{port_version}`\n"
        f"- Temperature: `{result.temperature_k:.16g} K`\n"
        f"- Hydrogen density: `{result.hydrogen_density_cm3:.16g} cm^-3`\n"
        f"- Electron fraction: `{result.electron_fraction_xee:.16g}`\n"
        f"- Elements: `{len(result.element_results)}`\n"
        f"- Pre-matrix calc_ion_rates/istruc ready: `{result.pre_matrix_ready}`\n"
        f"- Second-pass calc_hmc_ion rate entries: `{len(result.pirt)}`\n"
        f"- Source global-level mappings: `{len(result.global_level_index_by_key)}`\n"
        f"- Element loop ready: `{result.element_loop_ready}`\n"
        f"- Charge-closure scope complete: `{result.charge_closure_scope_complete}`\n"
        f"- Continuum leaves complete: `{result.continuum.complete}`\n"
        f"- Pre-continuum thermal snapshot explicit: `True`\n"
        f"- Complete fixed-state ready: `{result.complete_fixed_state_ready}`\n"
        f"- Heating/cooling residual: `{result.hmctot:.16g}`\n"
        f"- Charge residual: `{result.elcter:.16g}`\n"
    )
    return {
        "ions_csv": str(ion_csv),
        "elements_csv": str(element_csv),
        "hydrogen_records_488_491_csv": str(hydrogen_target_csv),
        "calc_ion_rates_records_csv": str(contribution_csv),
        "levels_csv": str(level_csv),
        "type77_floor_impact_csv": str(type77_csv),
        "type77_floor_impact_json": str(type77_json),
        "json": str(json_path),
        "markdown": str(md_path),
    }
