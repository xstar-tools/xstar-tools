"""Physical bounded runner support for the translated XSTAR ``dsec`` path.

This module bridges the accepted fixed-state ``calc_hmc_all`` machinery and
:mod:`xstar_tools.xstar.dsec`.  It intentionally remains a bounded
same-zone validation path: the incident continuum, escape state, source element
scope, and geometry are supplied from the already validated XSTAR capture, but
all temperature- and density-dependent continuum leaves are recomputed for
every Python ``dsec`` trial.

The helper does **not** read XSTAR residuals, temperatures, rates, or
populations during iteration.  The XSTAR trajectory is used only to select the
initial/control state and later as a regression oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import copy
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np

from .all_element_local_zone import (
    AllElementFixedStatePlan,
    build_all_element_fixed_state_requests,
)
from .bremsstrahlung import (
    BremsstrahlungContext,
    bremem_continuum_result,
)
from .compton import (
    Comp2Context,
    ComptonTableState,
    comp2_continuum_result,
)
from .dsec import DsecMutableRuntimeState, DsecPortError, DsecProbeTrajectory
from .dsec_correlation import DsecMatchingInputState
from .element_equilibrium import EscapeProbabilityContext
from .free_free import FreeFreeContext, freef_continuum_result
from .thermal_balance import HeatFContext


@dataclass(frozen=True)
class PhysicalDsecInitialState:
    """Resolved initial/control state for one bounded physical ``dsec`` run."""

    temperature_t4: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    nlim: int
    tinf_t4: float
    source: str


@dataclass(frozen=True)
class PhysicalDsecContinuumTemplate:
    """Same-zone continuum inputs reused while rebuilding trial contexts.

    ``epi_eV`` and ``bremsa`` are fixed during one call to XSTAR ``dsec``.
    ``freef``, ``bremem``, and ``heatf`` are nevertheless rebuilt at every
    trial because they depend on the current temperature, density, and electron
    fraction.

    The Fortran ``opakc`` and ``brcems`` arrays are local scratch arrays inside
    ``calc_hmc_all``.  ``brcems`` is explicitly cleared by ``bremem``.  The
    caller may choose either zero-initialized scratch or the captured call-73
    scratch for the first evaluation; subsequent trials carry the previous
    returned arrays through :class:`~xstar_tools.xstar.dsec.DsecMutableRuntimeState`.
    """

    epi_eV: np.ndarray
    bremsa: np.ndarray
    compton_table: ComptonTableState
    radius_cm: float
    zone_thickness_cm: float
    ncn2: int
    initial_opakc_cm_inv: np.ndarray
    initial_brcems: np.ndarray
    source: str = "bounded_same_zone_xstar_capture"
    first_workspace_policy: str = "zero"
    carry_continuum_workspace: bool = True

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Validate/normalize dataclass state immediately after construction.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
    # XSTAR-FUNCTION-COMMENT-END
    def __post_init__(self) -> None:
        epi = np.asarray(self.epi_eV, dtype=float).reshape(-1)
        bremsa = np.asarray(self.bremsa, dtype=float).reshape(-1)
        opakc = np.asarray(self.initial_opakc_cm_inv, dtype=float).reshape(-1)
        brcems = np.asarray(self.initial_brcems, dtype=float).reshape(-1)
        n = int(self.ncn2)
        if n < 2:
            raise DsecPortError("physical dsec continuum requires at least two bins")
        if min(epi.size, bremsa.size, opakc.size, brcems.size) < n:
            raise DsecPortError(
                "physical dsec continuum arrays are shorter than ncn2="
                f"{n}: epi={epi.size}, bremsa={bremsa.size}, "
                f"opakc={opakc.size}, brcems={brcems.size}"
            )
        if np.any(~np.isfinite(epi[:n])) or np.any(epi[:n] <= 0.0):
            raise DsecPortError("physical dsec photon grid must be finite and positive")
        if np.any(np.diff(epi[:n]) <= 0.0):
            raise DsecPortError("physical dsec photon grid must be strictly increasing")
        for name, values in (
            ("bremsa", bremsa),
            ("initial_opakc", opakc),
            ("initial_brcems", brcems),
        ):
            if np.any(~np.isfinite(values[:n])):
                raise DsecPortError(f"physical dsec {name} contains non-finite values")
        if self.first_workspace_policy not in {"zero", "probe", "call73-probe"}:
            raise DsecPortError(
                "first_workspace_policy must be 'zero', 'probe', or the "
                "legacy alias 'call73-probe'"
            )
        if not np.isfinite(float(self.radius_cm)):
            raise DsecPortError("radius_cm must be finite")
        if not np.isfinite(float(self.zone_thickness_cm)):
            raise DsecPortError("zone_thickness_cm must be finite")
        self.compton_table.validate()


@dataclass
class PhysicalDsecCalcKwargsFactory:
    """Rebuild translated continuum contexts for every physical trial."""

    template: PhysicalDsecContinuumTemplate
    build_count: int = 0

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the first workspace operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
    # XSTAR-FUNCTION-COMMENT-END
    def _first_workspace(self, name: str) -> np.ndarray:
        n = int(self.template.ncn2)
        if self.template.first_workspace_policy == "call73-probe":
            values = (
                self.template.initial_opakc_cm_inv
                if name == "opakc"
                else self.template.initial_brcems
            )
            return np.asarray(values, dtype=float)[:n].copy()
        return np.zeros(n, dtype=float)

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the valid workspace operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
    # XSTAR-FUNCTION-COMMENT-END
    @staticmethod
    def _valid_workspace(value: Any, n: int) -> Optional[np.ndarray]:
        if value is None:
            return None
        array = np.asarray(value, dtype=float).reshape(-1)
        if array.size < n or np.any(~np.isfinite(array[:n])):
            return None
        return array[:n].copy()

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Evaluate this object as a callable using its configured runtime/scientific state.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
    # XSTAR-FUNCTION-COMMENT-END
    def __call__(self, state: DsecMutableRuntimeState) -> Mapping[str, Any]:
        self.build_count += 1
        n = int(self.template.ncn2)
        epi = np.asarray(self.template.epi_eV, dtype=float)[:n].copy()
        bremsa = np.asarray(self.template.bremsa, dtype=float)[:n].copy()

        opakc_before: Optional[np.ndarray] = None
        brcems_before: Optional[np.ndarray] = None
        if self.template.carry_continuum_workspace:
            opakc_before = self._valid_workspace(state.work_arrays.get("opakc"), n)
            brcems_before = self._valid_workspace(state.work_arrays.get("brcems"), n)
        if opakc_before is None:
            opakc_before = self._first_workspace("opakc")
        if brcems_before is None:
            brcems_before = self._first_workspace("brcems")

        comp2_context = Comp2Context(
            epi_eV=epi,
            bremsa=bremsa,
            table=self.template.compton_table,
            ncn2=n,
            source=f"{self.template.source}:dynamic_comp2",
        )
        comp2_result, _ = comp2_continuum_result(
            comp2_context,
            temperature_k=state.temperature_k,
            hydrogen_density_cm3=state.hydrogen_density_cm3,
            electron_fraction_xee=state.electron_fraction_xee,
        )

        free_free_context = FreeFreeContext(
            epi_eV=epi,
            bremsa=bremsa,
            opakc_before_cm_inv=opakc_before,
            ncn2=n,
            source=f"{self.template.source}:dynamic_freef",
        )
        freef_result, _ = freef_continuum_result(
            free_free_context,
            temperature_k=state.temperature_k,
            hydrogen_density_cm3=state.hydrogen_density_cm3,
            electron_fraction_xee=state.electron_fraction_xee,
        )

        bremem_context = BremsstrahlungContext(
            epi_eV=epi,
            brcems_before=brcems_before,
            opakc_before_cm_inv=freef_result.opakc_after_cm_inv,
            ncn2=n,
            source=f"{self.template.source}:dynamic_bremem",
        )
        bremem_result, _ = bremem_continuum_result(
            bremem_context,
            temperature_k=state.temperature_k,
            hydrogen_density_cm3=state.hydrogen_density_cm3,
            electron_fraction_xee=state.electron_fraction_xee,
        )

        # The scalar total fields in HeatFContext are caller-state
        # documentation/validation fields. calc_hmc_all supplies the actual
        # element-loop totals and the freshly recomputed leaf results to heatf.
        heatf_context = HeatFContext(
            epi_eV=epi,
            brcems=bremem_result.brcems_after,
            htfreef_erg_cm3_s=freef_result.htfreef_erg_cm3_s,
            cmp1=comp2_result.cmp1,
            cmp2=comp2_result.cmp2,
            httot_before=0.0,
            cltot_before=0.0,
            httot2_before=0.0,
            cltot2_before=0.0,
            radius_cm=float(self.template.radius_cm),
            zone_thickness_cm=float(self.template.zone_thickness_cm),
            ncn2=n,
            source=f"{self.template.source}:dynamic_heatf",
        )

        return {
            "compton_context": comp2_context,
            "free_free_context": free_free_context,
            "bremem_context": bremem_context,
            "heatf_context": heatf_context,
        }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the initial state from xstar trajectory operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
# XSTAR-FUNCTION-COMMENT-END
def initial_state_from_xstar_trajectory(
    reference: DsecProbeTrajectory,
    *,
    temperature_t4: Optional[float] = None,
    electron_fraction_xee: Optional[float] = None,
    hydrogen_density_cm3: Optional[float] = None,
    nlim: Optional[int] = None,
    tinf_t4: Optional[float] = None,
    policy: str = "use",
    relative_tolerance: float = 5.0e-12,
    absolute_tolerance: float = 1.0e-30,
) -> PhysicalDsecInitialState:
    """Resolve the Python initial/control state against an XSTAR trajectory.

    ``use`` adopts the first XSTAR ``begin`` row. ``check`` requires supplied
    values and verifies them. ``ignore`` uses supplied values without checking.
    """

    if not reference.events or reference.events[0].event != "begin":
        raise DsecPortError("XSTAR dsec trajectory must start with a begin event")
    begin = reference.events[0]
    allowed = {"use", "check", "ignore"}
    if policy not in allowed:
        raise DsecPortError(f"invalid dsec runtime policy {policy!r}; expected {sorted(allowed)}")

    observed = {
        "temperature_t4": float(begin.temperature_t4),
        "electron_fraction_xee": float(begin.electron_fraction_xee),
        "hydrogen_density_cm3": float(begin.hydrogen_density_cm3),
        "nlim": int(begin.nlim),
        "tinf_t4": float(begin.tinf_t4),
    }
    requested = {
        "temperature_t4": temperature_t4,
        "electron_fraction_xee": electron_fraction_xee,
        "hydrogen_density_cm3": hydrogen_density_cm3,
        "nlim": nlim,
        "tinf_t4": tinf_t4,
    }

    if policy == "use":
        return PhysicalDsecInitialState(**observed, source="xstar_dsec_begin_probe")

    missing = [name for name, value in requested.items() if value is None]
    if missing:
        raise DsecPortError(
            f"dsec runtime policy {policy!r} requires explicit values for: "
            + ", ".join(missing)
        )
    resolved = {
        "temperature_t4": float(temperature_t4),
        "electron_fraction_xee": float(electron_fraction_xee),
        "hydrogen_density_cm3": float(hydrogen_density_cm3),
        "nlim": int(nlim),
        "tinf_t4": float(tinf_t4),
    }
    if policy == "check":
        mismatches = []
        for name in ("temperature_t4", "electron_fraction_xee", "hydrogen_density_cm3", "tinf_t4"):
            got = float(resolved[name])
            expected = float(observed[name])
            if not np.isclose(got, expected, rtol=relative_tolerance, atol=absolute_tolerance):
                mismatches.append(f"{name}: requested={got:.17g}, xstar={expected:.17g}")
        if int(resolved["nlim"]) != int(observed["nlim"]):
            mismatches.append(
                f"nlim: requested={resolved['nlim']}, xstar={observed['nlim']}"
            )
        if mismatches:
            raise DsecPortError("requested dsec state differs from XSTAR begin row: " + "; ".join(mismatches))
        source = "command_line_checked_against_xstar_dsec_begin_probe"
    else:
        source = "command_line_unchecked"
    return PhysicalDsecInitialState(**resolved, source=source)




# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Apply dsec matching input state for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
# XSTAR-FUNCTION-COMMENT-END
def apply_dsec_matching_input_state(
    state: DsecMutableRuntimeState,
    matching_input: DsecMatchingInputState,
    *,
    opakc_before_cm_inv: Optional[Sequence[float]] = None,
    brcems_before: Optional[Sequence[float]] = None,
    continuum_factory: Optional[PhysicalDsecCalcKwargsFactory] = None,
) -> Dict[str, Any]:
    """Replace one pending ``calc_hmc_all`` entry with a captured XSTAR state.

    This is a diagnostic replay hook, not a production input path.  It is used
    to decide whether a later ``dsec`` discrepancy was produced by the previous
    Python evaluation or is generated inside the selected evaluation itself.
    Rates, matrices, and thermal residuals are still computed by Python.
    """

    dense_x = np.asarray(
        matching_input.global_level_values_by_index, dtype=float
    ).reshape(-1).copy()
    dense_b = np.asarray(
        matching_input.global_bilev_values_by_index, dtype=float
    ).reshape(-1).copy()
    dense_r = np.asarray(
        matching_input.global_rnist_values_by_index, dtype=float
    ).reshape(-1).copy()
    if not (dense_x.size == dense_b.size == dense_r.size):
        raise DsecPortError(
            "captured XSTAR global xilevg/bilevg/rnisg arrays have unequal lengths"
        )
    if np.any(~np.isfinite(dense_x)) or np.any(dense_x < 0.0):
        raise DsecPortError("captured XSTAR xilevg must be finite and nonnegative")
    if np.any(~np.isfinite(dense_b)) or np.any(dense_b < 0.0):
        raise DsecPortError("captured XSTAR bilevg must be finite and nonnegative")
    if np.any(~np.isfinite(dense_r)) or np.any(dense_r < 0.0):
        raise DsecPortError("captured XSTAR rnisg must be finite and nonnegative")

    mapping = {
        (int(key[0]), int(key[1]), int(key[2])): int(index)
        for key, index in state.global_level_index_by_key.items()
    }
    if np.count_nonzero(dense_x) and not mapping:
        raise DsecPortError(
            "exact transition replay requires the global-index mapping produced "
            "by the preceding Python calc_hmc_all evaluation"
        )
    invalid = [index for index in mapping.values() if index <= 0 or index > dense_x.size]
    if invalid:
        raise DsecPortError(
            "global-index mapping exceeds the captured XSTAR level array: "
            f"first invalid index={invalid[0]}, n_global={dense_x.size}"
        )

    state.temperature_t4 = float(matching_input.temperature_t4)
    state.electron_fraction_xee = float(matching_input.electron_fraction_xee)
    state.hydrogen_density_cm3 = float(matching_input.hydrogen_density_cm3)
    state.pressure = float(matching_input.pressure)
    state.lcdd = int(matching_input.lcdd)
    state.global_xilevg_by_index = dense_x
    state.global_bilevg_by_index = dense_b
    state.global_rnisg_by_index = dense_r
    state.global_level_populations = {
        key: float(dense_x[index - 1]) for key, index in mapping.items()
    }
    state.leveltemp_workspace = copy.deepcopy(matching_input.leveltemp_workspace)
    state.leveltemp_owner_by_column = {}

    requests = []
    for request in state.element_requests:
        requests.append(
            replace(
                request,
                radiation=copy.deepcopy(matching_input.radiation),
                escape=copy.deepcopy(matching_input.escape),
                covering_fraction=float(matching_input.covering_fraction),
                turbulent_velocity_km_s=float(
                    matching_input.turbulent_velocity_km_s
                ),
                critf=float(matching_input.critf),
            )
        )
    state.element_requests = tuple(requests)

    if opakc_before_cm_inv is not None:
        opakc = np.asarray(opakc_before_cm_inv, dtype=float).reshape(-1).copy()
        if np.any(~np.isfinite(opakc)):
            raise DsecPortError("captured XSTAR opakc workspace contains non-finite values")
        state.work_arrays["opakc"] = opakc
    if brcems_before is not None:
        brcems = np.asarray(brcems_before, dtype=float).reshape(-1).copy()
        if np.any(~np.isfinite(brcems)):
            raise DsecPortError("captured XSTAR brcems workspace contains non-finite values")
        state.work_arrays["brcems"] = brcems

    if continuum_factory is not None:
        template = continuum_factory.template
        opakc_template = (
            np.asarray(opakc_before_cm_inv, dtype=float).reshape(-1).copy()
            if opakc_before_cm_inv is not None
            else np.asarray(template.initial_opakc_cm_inv, dtype=float).copy()
        )
        brcems_template = (
            np.asarray(brcems_before, dtype=float).reshape(-1).copy()
            if brcems_before is not None
            else np.asarray(template.initial_brcems, dtype=float).copy()
        )
        continuum_factory.template = replace(
            template,
            epi_eV=np.asarray(matching_input.radiation.epim_eV, dtype=float).copy(),
            bremsa=np.asarray(matching_input.radiation.bremsam, dtype=float).copy(),
            radius_cm=float(matching_input.radius_cm),
            zone_thickness_cm=float(matching_input.zone_thickness_cm),
            ncn2=int(matching_input.ncn2),
            initial_opakc_cm_inv=opakc_template,
            initial_brcems=brcems_template,
            source=(
                f"exact_xstar_dsec_transition_evaluation_"
                f"{matching_input.dsec_evaluation_index}"
            ),
        )

    state.provenance.update(
        {
            "diagnostic_exact_xstar_transition_replay": True,
            "replayed_dsec_evaluation_index": int(
                matching_input.dsec_evaluation_index
            ),
            "replayed_calc_hmc_all_call_id": int(
                matching_input.calc_hmc_all_call_id
            ),
            "replayed_state_source_dir": matching_input.source_dir,
        }
    )
    return {
        "evaluation_index": int(matching_input.dsec_evaluation_index),
        "calc_hmc_all_call_id": int(matching_input.calc_hmc_all_call_id),
        "n_global_levels": int(dense_x.size),
        "n_nonzero_xilevg": int(np.count_nonzero(dense_x)),
        "n_global_mappings": int(len(mapping)),
        "leveltemp_nonzero_columns": int(
            len(getattr(matching_input.leveltemp_workspace, "levels", {}) or {})
        ),
        "opakc_replayed": opakc_before_cm_inv is not None,
        "brcems_replayed": brcems_before is not None,
    }

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the clone physical dsec runtime state operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
# XSTAR-FUNCTION-COMMENT-END
def clone_physical_dsec_runtime_state(
    state: DsecMutableRuntimeState,
) -> DsecMutableRuntimeState:
    """Clone the mutable state for the post-``dsec`` ``calc_hmc_all`` call.

    ``xstarcalc.f90`` calls ``calc_hmc_all`` once more after ``dsec`` returns.
    The bounded runner must reproduce that call for comparison with the frozen
    call-73 oracle without changing the already-recorded ``dsec`` call count or
    trajectory.  This helper copies every input workspace that can affect the
    next evaluation while intentionally dropping ``last_calc_hmc_all``.
    """

    return DsecMutableRuntimeState(
        temperature_t4=float(state.temperature_t4),
        electron_fraction_xee=float(state.electron_fraction_xee),
        hydrogen_density_cm3=float(state.hydrogen_density_cm3),
        element_requests=tuple(state.element_requests),
        required_element_z=(
            None if state.required_element_z is None
            else tuple(int(z) for z in state.required_element_z)
        ),
        pressure=float(state.pressure),
        lcdd=int(state.lcdd),
        element_populations={
            int(z): np.asarray(values, dtype=float).copy()
            for z, values in state.element_populations.items()
        },
        global_level_populations=(
            None
            if state.global_level_populations is None
            else {
                (int(key[0]), int(key[1]), int(key[2])): float(value)
                for key, value in state.global_level_populations.items()
            }
        ),
        global_xilevg_by_index=(
            None
            if state.global_xilevg_by_index is None
            else np.asarray(state.global_xilevg_by_index, dtype=float).copy()
        ),
        global_bilevg_by_index=(
            None
            if state.global_bilevg_by_index is None
            else np.asarray(state.global_bilevg_by_index, dtype=float).copy()
        ),
        global_rnisg_by_index=(
            None
            if state.global_rnisg_by_index is None
            else np.asarray(state.global_rnisg_by_index, dtype=float).copy()
        ),
        global_level_index_by_key={
            (int(key[0]), int(key[1]), int(key[2])): int(value)
            for key, value in state.global_level_index_by_key.items()
        },
        leveltemp_workspace=copy.deepcopy(state.leveltemp_workspace),
        leveltemp_owner_by_column={
            int(index): dict(owner)
            for index, owner in state.leveltemp_owner_by_column.items()
        },
        last_leveltemp_workspace=copy.deepcopy(state.last_leveltemp_workspace),
        last_leveltemp_owner_by_column={
            int(index): dict(owner)
            for index, owner in state.last_leveltemp_owner_by_column.items()
        },
        source_global_alias_writeback=bool(state.source_global_alias_writeback),
        reset_leveltemp_each_calc_hmc_all=bool(
            state.reset_leveltemp_each_calc_hmc_all
        ),
        source_arrays=copy.deepcopy(state.source_arrays),
        work_arrays=copy.deepcopy(state.work_arrays),
        last_calc_hmc_all=None,
        calc_hmc_all_call_count=0,
        provenance={
            **dict(state.provenance),
            "post_dsec_xstarcalc_clone": True,
        },
    )

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build physical dsec runtime state for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6.5; source dsec physical controller state.
# XSTAR-FUNCTION-COMMENT-END
def build_physical_dsec_runtime_state(
    plan: AllElementFixedStatePlan,
    *,
    initial: PhysicalDsecInitialState,
    radiation: Any,
    escape: EscapeProbabilityContext,
    covering_fraction: float,
    turbulent_velocity_km_s: float,
    lfast: int,
    critf: float,
    initial_population_policy: str,
    terminal_continuum_seed_mode: str = "source-zero",
    pressure: float,
    lcdd: int,
    matching_input: Optional[DsecMatchingInputState] = None,
) -> DsecMutableRuntimeState:
    """Build the mutable source-order element state for a physical run.

    When ``matching_input`` is supplied, v0.4.48 restores the exact XSTAR
    state entering the correlated first internal ``calc_hmc_all`` call.
    The current bounded call-1 workflow requires the captured global xilevg
    array to be identically zero; later calls need a derived-pointer mapping
    from global indices to physical level keys.
    """

    requests = build_all_element_fixed_state_requests(
        plan,
        radiation=radiation,
        escape=escape,
        covering_fraction=covering_fraction,
        turbulent_velocity_km_s=turbulent_velocity_km_s,
        lfast=lfast,
        critf=critf,
        initial_population_policy=initial_population_policy,
        terminal_continuum_seed_mode=terminal_continuum_seed_mode,
        strict_context=True,
    )
    global_populations: Dict[Tuple[int, int, int], float] = {}
    global_xilevg_by_index: Optional[np.ndarray] = None
    global_bilevg_by_index: Optional[np.ndarray] = None
    global_rnisg_by_index: Optional[np.ndarray] = None
    leveltemp_workspace = None
    initial_global_source = "xstar_init_f90_zero_xilevg"
    if matching_input is not None:
        if not matching_input.global_xilevg_is_zero:
            raise DsecPortError(
                "v0.4.48 bounded call-1 runner captured nonzero incoming global "
                "xilevg but cannot yet map global indices onto physical level keys"
            )
        leveltemp_workspace = matching_input.leveltemp_workspace
        global_xilevg_by_index = np.asarray(
            matching_input.global_level_values_by_index, dtype=float
        ).copy()
        global_bilevg_by_index = np.asarray(
            matching_input.global_bilev_values_by_index, dtype=float
        ).copy()
        global_rnisg_by_index = np.asarray(
            matching_input.global_rnist_values_by_index, dtype=float
        ).copy()
        initial_global_source = "xstar_correlated_dsec_input_global_xilevg"
    return DsecMutableRuntimeState(
        temperature_t4=initial.temperature_t4,
        electron_fraction_xee=initial.electron_fraction_xee,
        hydrogen_density_cm3=initial.hydrogen_density_cm3,
        element_requests=requests,
        required_element_z=plan.abundant_element_z,
        pressure=float(pressure),
        lcdd=int(lcdd),
        global_level_populations=global_populations,
        global_xilevg_by_index=global_xilevg_by_index,
        global_bilevg_by_index=global_bilevg_by_index,
        global_rnisg_by_index=global_rnisg_by_index,
        leveltemp_workspace=leveltemp_workspace,
        source_global_alias_writeback=True,
        reset_leveltemp_each_calc_hmc_all=False,
        provenance={
            "physical_dsec_runner": True,
            "initial_runtime_source": initial.source,
            "element_scope_probe_call_id": plan.call_id,
            "element_scope_probe_dir": plan.probe_dir,
            "initial_population_policy": initial_population_policy,
            "terminal_continuum_seed_mode": terminal_continuum_seed_mode,
            "initial_global_population_source": initial_global_source,
            "matching_input_call_id": (
                None if matching_input is None
                else matching_input.calc_hmc_all_call_id
            ),
            "matching_input_probe_dir": (
                None if matching_input is None else matching_input.source_dir
            ),
            "dense_native_global_state": True,
            "source_global_alias_writeback": True,
            "leveltemp_lifecycle": "persistent_source_workspace_across_calc_hmc_all",
        },
    )


__all__ = [
    "PhysicalDsecInitialState",
    "PhysicalDsecContinuumTemplate",
    "PhysicalDsecCalcKwargsFactory",
    "initial_state_from_xstar_trajectory",
    "build_physical_dsec_runtime_state",
    "apply_dsec_matching_input_state",
    "clone_physical_dsec_runtime_state",
]
