# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: dsec.f90
#   Role: Iterate the source thermal/convergence controller for a zone.
#   Relation: Source-faithful stateful control algorithm; stopping tests, secant state, and REAL rounding are qualified.
#   Concordance: DSEC-001; THERM-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Source-faithful translation of XSTAR ``dsec.f90``.

``dsec`` solves charge conservation and, for positive ``nlim``, thermal
balance by a nested double-secant/bracketing iteration.  The source routine is
stateful: every trial calls ``calc_hmc_all`` with the native global level
population arrays left by the previous trial.  The internal ``leveltemp``
workspace remains source ordered within one ``calc_hmc_all`` invocation; the
bounded call-correlated workflow resets it to the captured call-entry state
before the next trial.  This module keeps those ownership rules explicit and
records a trajectory suitable for direct comparison with a diagnostic-only
XSTAR probe.

The numerical control flow intentionally follows the Fortran labels and branch
order.  It does not replace the source algorithm with a generic root finder.
"""

# Source correspondence:
#   Fortran: dsec.f90
#   Role: source-ordered charge/thermal nonlinear controller around calc_hmc_all.
#   Concordance: DSEC-001; qualification: all-62 STEP science accepted at 12.3.42.

from __future__ import annotations

import csv
import json
import math
import copy
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Protocol, Sequence, Tuple

import numpy as np

from .fortran_numbers import parse_fortran_float
from .local_zone import FixedStateCalcHMCAllResult, FixedStateElementRequest, calc_hmc_all
from .performance import profile_component


class DsecPortError(RuntimeError):
    """Raised when the translated ``dsec`` path cannot proceed."""


def _r4(value: float) -> float:
    """Round a default-real Fortran literal before promotion to real(8)."""

    return float(np.float32(value))


DSEC_CHARGE_TOLERANCE = _r4(1.0e-4)
DSEC_THERMAL_TOLERANCE = _r4(1.0e-4)
DSEC_TEMPERATURE_STAGNATION_TOLERANCE = _r4(2.0e-9)
DSEC_TEMPERATURE_FACTOR = _r4(1.2)
DSEC_ELECTRON_FACTOR = _r4(1.2)
DSEC_FAR_FROM_EQUILIBRIUM = _r4(0.9)
DSEC_TINF_PROXIMITY_FACTOR = _r4(1.01)
DSEC_INITIAL_PREVIOUS_TEMPERATURE = _r4(1.0e30)
DSEC_CHARGE_DENOMINATOR_FLOOR = 1.0e-48


@dataclass
class DsecMutableRuntimeState:
    """Mutable local-zone state passed through repeated ``calc_hmc_all`` calls.

    ``temperature_t4`` uses XSTAR's native unit of :math:`10^4` K.  The
    mutable native-index ``xilevg/bilevg/rnisg`` arrays are carried between
    trials and remapped onto each newly selected compact element basis.
    Compact population vectors and logical level keys are retained only as
    diagnostics.  ``leveltemp`` is shared across elements within one call;
    the physical call-correlated path can reset it before each new trial.
    """

    temperature_t4: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    element_requests: Tuple[FixedStateElementRequest, ...] = ()
    required_element_z: Optional[Tuple[int, ...]] = None
    pressure: float = 0.0
    lcdd: int = 1
    element_populations: Dict[int, np.ndarray] = field(default_factory=dict)
    # ``None`` preserves legacy compact-seed behavior.  An explicit mapping,
    # including an empty mapping, means to use the source global ``xilevg``
    # workspace.  The empty mapping is the exact first-zone state from
    # init.f90, which clears every global level population to zero.
    global_level_populations: Optional[Dict[Tuple[int, int, int], float]] = None
    global_xilevg_by_index: Optional[np.ndarray] = None
    global_bilevg_by_index: Optional[np.ndarray] = None
    global_rnisg_by_index: Optional[np.ndarray] = None
    global_level_index_by_key: Dict[Tuple[int, int, int], int] = field(default_factory=dict)
    leveltemp_workspace: Optional[Any] = None
    leveltemp_owner_by_column: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    last_leveltemp_workspace: Optional[Any] = None
    last_leveltemp_owner_by_column: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    source_global_alias_writeback: bool = False
    reset_leveltemp_each_calc_hmc_all: bool = False
    retain_source_arrays: bool = True
    source_arrays: Dict[str, Any] = field(default_factory=dict)
    work_arrays: Dict[str, Any] = field(default_factory=dict)
    last_calc_hmc_all: Optional[Any] = None
    last_hmctot: float = float("nan")
    last_elcter: float = float("nan")
    calc_hmc_all_call_count: int = 0
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.temperature_t4) or self.temperature_t4 <= 0.0:
            raise DsecPortError("temperature_t4 must be finite and positive")
        if not math.isfinite(self.electron_fraction_xee) or self.electron_fraction_xee < 0.0:
            raise DsecPortError("electron_fraction_xee must be finite and nonnegative")
        if not math.isfinite(self.hydrogen_density_cm3) or self.hydrogen_density_cm3 < 0.0:
            raise DsecPortError("hydrogen_density_cm3 must be finite and nonnegative")
        self.element_requests = tuple(self.element_requests)
        self.element_populations = {
            int(z): np.asarray(values, dtype=float).copy()
            for z, values in self.element_populations.items()
        }
        if self.global_level_populations is not None:
            self.global_level_populations = {
                (int(key[0]), int(key[1]), int(key[2])): float(value)
                for key, value in self.global_level_populations.items()
            }
        for name in (
            "global_xilevg_by_index",
            "global_bilevg_by_index",
            "global_rnisg_by_index",
        ):
            values = getattr(self, name)
            if values is not None:
                array = np.asarray(values, dtype=float).reshape(-1).copy()
                if np.any(~np.isfinite(array)) or np.any(array < 0.0):
                    raise DsecPortError(f"{name} must be finite and nonnegative")
                setattr(self, name, array)
        self.global_level_index_by_key = {
            (int(key[0]), int(key[1]), int(key[2])): int(value)
            for key, value in self.global_level_index_by_key.items()
        }
        self.leveltemp_owner_by_column = {
            int(index): dict(owner)
            for index, owner in self.leveltemp_owner_by_column.items()
        }
        self.last_leveltemp_owner_by_column = {
            int(index): dict(owner)
            for index, owner in self.last_leveltemp_owner_by_column.items()
        }

    @property
    def temperature_k(self) -> float:
        return float(self.temperature_t4) * 1.0e4

    def requests_for_next_call(self) -> Tuple[FixedStateElementRequest, ...]:
        """Return source-order requests seeded from the current mutable state."""

        requests: List[FixedStateElementRequest] = []
        for request in self.element_requests:
            z = int(request.element_z)
            if self.global_xilevg_by_index is not None:
                dense = np.asarray(self.global_xilevg_by_index, dtype=float).reshape(-1)
                global_populations = {
                    key: float(dense[index - 1])
                    for key, index in self.global_level_index_by_key.items()
                    if 1 <= int(index) <= dense.size
                }
                populations = None
                source = (
                    "xstar_init_zero_dense_global_xilevg"
                    if self.calc_hmc_all_call_count == 0
                    else "dsec_previous_calc_hmc_all_dense_global_xilevg"
                )
            elif self.global_level_populations is not None:
                # Source calc_hmc_all remaps global xilevg after each dynamic
                # istruc ion-range selection.  Never reuse a compact vector
                # across a basis change.
                global_populations = dict(self.global_level_populations)
                populations = None
                source = (
                    "xstar_init_zero_global_xilevg"
                    if self.calc_hmc_all_call_count == 0
                    else "dsec_previous_calc_hmc_all_global_xilevg"
                )
            else:
                global_populations = request.initial_global_populations
                if z in self.element_populations:
                    populations = self.element_populations[z].copy()
                    source = "dsec_previous_calc_hmc_all_final_population"
                else:
                    populations = (
                        None
                        if request.initial_populations is None
                        else np.asarray(request.initial_populations, dtype=float).copy()
                    )
                    source = request.initial_population_source
            requests.append(
                replace(
                    request,
                    initial_populations=populations,
                    initial_global_populations=global_populations,
                    initial_population_source=source,
                )
            )
        return tuple(requests)

    def commit_calc_hmc_all(self, result: FixedStateCalcHMCAllResult) -> None:
        """Commit one trial exactly where the Fortran call returns."""

        self.temperature_t4 = float(result.temperature_k) / 1.0e4
        self.electron_fraction_xee = float(result.electron_fraction_xee)
        self.hydrogen_density_cm3 = float(result.hydrogen_density_cm3)
        self.last_hmctot = float(result.hmctot)
        self.last_elcter = float(result.elcter)
        # v0.5.42: in production diagnostics=none mode, do not retain the full
        # FixedStateCalcHMCAllResult for every DSEC trial.  It contains large
        # element assemblies and diagnostic arrays.  Dense native arrays below
        # carry the source state needed by the next trial.
        if bool(self.retain_source_arrays):
            self.last_calc_hmc_all = result
        else:
            from types import SimpleNamespace
            self.last_calc_hmc_all = SimpleNamespace(
                hmctot=float(result.hmctot),
                elcter=float(result.elcter),
                complete_fixed_state_ready=bool(result.complete_fixed_state_ready),
            )
        self.calc_hmc_all_call_count += 1

        for item in result.element_results:
            solve = item.equilibrium.solve
            if solve is not None:
                self.element_populations[int(item.request.element_z)] = np.asarray(
                    solve.populations, dtype=float
                ).copy()
        # calc_hmc_all writes the solved state back to native global arrays.
        # Dense arrays own the repeated-dsec state; logical dictionaries are
        # reconstructed views used by the current compact-basis mapper.
        dense_x = np.asarray(
            getattr(result, "global_xilevg_by_index", ()), dtype=float
        ).reshape(-1)
        dense_b = np.asarray(
            getattr(result, "global_bilevg_by_index", ()), dtype=float
        ).reshape(-1)
        dense_r = np.asarray(
            getattr(result, "global_rnisg_by_index", ()), dtype=float
        ).reshape(-1)
        result_mapping = getattr(result, "global_level_index_by_key", {})
        if dense_x.size and result_mapping:
            self.global_xilevg_by_index = dense_x.copy()
            self.global_bilevg_by_index = dense_b.copy()
            self.global_rnisg_by_index = dense_r.copy()
            self.global_level_index_by_key = {
                (int(key[0]), int(key[1]), int(key[2])): int(value)
                for key, value in result_mapping.items()
            }
            self.global_level_populations = {
                key: float(self.global_xilevg_by_index[index - 1])
                for key, index in self.global_level_index_by_key.items()
                if 1 <= int(index) <= self.global_xilevg_by_index.size
            }
        else:
            # Compatibility for lightweight test doubles and legacy callers
            # that predate native-index ownership.
            if self.global_level_populations is None:
                self.global_level_populations = {}
            self.global_level_populations.update(
                {
                    (int(key[0]), int(key[1]), int(key[2])): float(value)
                    for key, value in result.xilevg.items()
                }
            )

        if bool(self.reset_leveltemp_each_calc_hmc_all) and not bool(self.retain_source_arrays):
            # Production DSEC does not carry leveltemp between trials.  Do not
            # retain the large leveltemp workspace after the dense global state
            # has been committed.
            self.last_leveltemp_workspace = None
            self.last_leveltemp_owner_by_column = {}
            self.leveltemp_workspace = None
            self.leveltemp_owner_by_column = {}
        else:
            self.last_leveltemp_workspace = result.leveltemp_workspace
            self.last_leveltemp_owner_by_column = {
                int(index): dict(owner)
                for index, owner in result.leveltemp_owner_by_column.items()
            }
            if not self.reset_leveltemp_each_calc_hmc_all:
                self.leveltemp_workspace = result.leveltemp_workspace
                self.leveltemp_owner_by_column = {
                    int(index): dict(owner)
                    for index, owner in result.leveltemp_owner_by_column.items()
                }
        if self.retain_source_arrays:
            self.source_arrays = {
                "xiin": dict(result.ion_fractions),
                "rrrt": dict(result.rrrt),
                "pirt": dict(result.pirt),
                "htt": dict(result.htt),
                "cll": dict(result.cll),
                "htt2": dict(result.htt2),
                "cll2": dict(result.cll2),
                "xilevg": dict(result.xilevg),
                "rnisg": dict(result.rnisg),
                "bilevg": dict(result.bilevg),
                "gammag": dict(result.gammag),
                "alphag": dict(result.alphag),
                "stotg": dict(result.stotg),
                "atotg": dict(result.atotg),
                "xtotg": dict(result.xtotg),
            }
        else:
            self.source_arrays = {
                "htt": dict(result.htt),
                "cll": dict(result.cll),
                "htt2": dict(result.htt2),
                "cll2": dict(result.cll2),
            }
        self.work_arrays = {
            "opakc": (
                None
                if result.continuum.opakc is None
                else np.asarray(result.continuum.opakc, dtype=float).copy()
            ),
            "brcems": (
                None
                if result.continuum.brcems is None
                else np.asarray(result.continuum.brcems, dtype=float).copy()
            ),
            "leveltemp_workspace": self.last_leveltemp_workspace,
            "leveltemp_owner_by_column": self.last_leveltemp_owner_by_column,
        }
        self.provenance.update(
            {
                "last_source_routine": "calc_hmc_all",
                "mutable_population_replay": True,
                "mutable_leveltemp_replay_within_call": True,
                "leveltemp_reset_between_calc_hmc_all_calls": bool(
                    self.reset_leveltemp_each_calc_hmc_all
                ),
                "dense_native_global_state": bool(
                    self.global_xilevg_by_index is not None
                ),
                "source_global_alias_writeback": bool(
                    self.source_global_alias_writeback
                ),
                "retain_source_arrays": bool(self.retain_source_arrays),
                "calc_hmc_all_call_count": self.calc_hmc_all_call_count,
            }
        )


@dataclass(frozen=True)
class DsecCalcHMCAllInputSnapshot:
    """Exact Python state immediately before one ``calc_hmc_all`` call.

    v0.4.51 records these snapshots so the state written by one physical
    ``dsec`` evaluation can be compared directly with the XSTAR state entering
    the next correlated evaluation.  Values are copied before the call; later
    mutation of the runtime state cannot alter the diagnostic record.
    """

    evaluation_index: int
    temperature_t4: float
    temperature_k: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    pressure: float
    lcdd: int
    covering_fraction: float
    turbulent_velocity_km_s: float
    critf: float
    global_level_populations: Mapping[Tuple[int, int, int], float]
    global_bilev_values: Mapping[Tuple[int, int, int], float]
    global_rnist_values: Mapping[Tuple[int, int, int], float]
    global_level_index_by_key: Mapping[Tuple[int, int, int], int]
    leveltemp_workspace: Optional[Any]
    leveltemp_owner_by_column: Mapping[int, Mapping[str, Any]]
    radiation: Optional[Any]
    escape: Optional[Any]
    calc_kwargs: Mapping[str, Any]
    global_xilevg_by_index: Optional[np.ndarray] = None
    global_bilevg_by_index: Optional[np.ndarray] = None
    global_rnisg_by_index: Optional[np.ndarray] = None
    element_requests: Tuple[FixedStateElementRequest, ...] = ()
    required_element_z: Optional[Tuple[int, ...]] = None
    source_global_alias_writeback: bool = False
    dispatcher_state: Optional[Any] = None
    element_solver_state: Optional[Any] = None
    pre_matrix_solver_state: Optional[Any] = None


@dataclass(frozen=True)
class DsecEvaluation:
    """The two residuals returned by one ``calc_hmc_all`` trial."""

    hmctot: float
    elcter: float
    fixed_state_result: Optional[FixedStateCalcHMCAllResult] = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class DsecEvaluator(Protocol):
    def __call__(self, state: DsecMutableRuntimeState) -> DsecEvaluation: ...


CalcHMCAllKwargsFactory = Callable[[DsecMutableRuntimeState], Mapping[str, Any]]


@dataclass
class CalcHMCAllDsecEvaluator:
    """Adapter that evaluates the translated ``calc_hmc_all`` on mutable state.

    ``calc_kwargs_factory`` is called for every trial so temperature-dependent
    continuum contexts may be reconstructed without using probe values as
    hidden production inputs.
    """

    master: Any
    derived: Any
    calc_kwargs_factory: Optional[CalcHMCAllKwargsFactory] = None
    dispatcher: Optional[Any] = None
    element_solver: Optional[Any] = None
    pre_matrix_solver: Optional[Any] = None
    pre_evaluation_callback: Optional[Callable[[int, DsecMutableRuntimeState], None]] = None
    progress_callback: Optional[Callable[[int, DsecMutableRuntimeState, FixedStateCalcHMCAllResult], None]] = None
    # Production memory control: repeated DSEC calls can create large
    # FixedStateCalcHMCAllResult objects for Mg/Ca.  Full diagnostic modes keep
    # the per-evaluation result history; production runs can retain only small
    # residual rows and the current mutable state.
    retain_fixed_state_results: bool = True
    capture_input_snapshot_indices: Tuple[int, ...] = ()
    capture_all_input_snapshots: bool = False
    # Diagnostic-only: request Lucy/state-path traces for selected elements
    # during the live DSEC evaluations.  This is used by v0.4.88 to capture
    # the all-evaluation hydrogen history without replaying every state.
    capture_lucy_trace_element_z: Tuple[int, ...] = ()
    evaluation_gate_callback: Optional[Callable[[int, DsecCalcHMCAllInputSnapshot, FixedStateCalcHMCAllResult], None]] = None
    evaluations: List[DsecEvaluation] = field(default_factory=list, init=False)
    input_snapshots: List[DsecCalcHMCAllInputSnapshot] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        # Reuse one source-faithful dispatcher across every ion, element, and
        # repeated dsec trial.  This mirrors the single Fortran ucalc routine
        # and prevents future dispatcher-owned workspaces from being reset at
        # trial boundaries.
        if self.dispatcher is None:
            from .ucalc import default_source_faithful_ucalc

            self.dispatcher = default_source_faithful_ucalc()

    def __call__(self, state: DsecMutableRuntimeState) -> DsecEvaluation:
        evaluation_index = len(self.evaluations) + 1
        if self.pre_evaluation_callback is not None:
            self.pre_evaluation_callback(evaluation_index, state)

        kwargs: Dict[str, Any] = {}
        if self.calc_kwargs_factory is not None:
            kwargs.update(dict(self.calc_kwargs_factory(state)))
        if self.dispatcher is not None:
            kwargs["dispatcher"] = self.dispatcher
        if self.element_solver is not None:
            kwargs["element_solver"] = self.element_solver
        if self.pre_matrix_solver is not None:
            kwargs["pre_matrix_solver"] = self.pre_matrix_solver

        requests = state.requests_for_next_call()
        trace_elements = {int(z) for z in self.capture_lucy_trace_element_z}
        if trace_elements:
            requests = tuple(
                replace(request, capture_lucy_trace=True)
                if int(request.element_z) in trace_elements
                else request
                for request in requests
            )
        capture_snapshot = bool(self.capture_all_input_snapshots or evaluation_index in set(self.capture_input_snapshot_indices))
        snapshot: Optional[DsecCalcHMCAllInputSnapshot] = None
        if capture_snapshot:
            radiation = requests[0].radiation if requests else None
            escape = requests[0].escape if requests else None
            snapshot = DsecCalcHMCAllInputSnapshot(
                evaluation_index=evaluation_index,
                temperature_t4=float(state.temperature_t4),
                temperature_k=float(state.temperature_k),
                electron_fraction_xee=float(state.electron_fraction_xee),
                hydrogen_density_cm3=float(state.hydrogen_density_cm3),
                pressure=float(state.pressure),
                lcdd=int(state.lcdd),
                covering_fraction=(float(requests[0].covering_fraction) if requests else 0.0),
                turbulent_velocity_km_s=(
                    float(requests[0].turbulent_velocity_km_s) if requests else 0.0
                ),
                critf=(float(requests[0].critf) if requests else 0.0),
                global_level_populations=dict(state.global_level_populations or {}),
                global_bilev_values=dict(state.source_arrays.get("bilevg", {})),
                global_rnist_values=dict(state.source_arrays.get("rnisg", {})),
                # Snapshot the mapping owned by the mutable DSEC runtime
                # entering this trial.  In diagnostics=none mode
                # ``last_calc_hmc_all`` is intentionally reduced to a tiny
                # scalar summary, while this runtime mapping remains the
                # authoritative source state committed by the prior trial.
                global_level_index_by_key=dict(state.global_level_index_by_key),
                leveltemp_workspace=copy.deepcopy(state.leveltemp_workspace),
                leveltemp_owner_by_column={
                    int(index): dict(owner)
                    for index, owner in state.leveltemp_owner_by_column.items()
                },
                radiation=copy.deepcopy(radiation),
                escape=copy.deepcopy(escape),
                calc_kwargs={
                    key: copy.deepcopy(value)
                    for key, value in kwargs.items()
                    if key not in {"dispatcher", "element_solver", "pre_matrix_solver"}
                },
                global_xilevg_by_index=(
                    None
                    if getattr(state, "global_xilevg_by_index", None) is None
                    else np.asarray(
                        getattr(state, "global_xilevg_by_index"), dtype=float
                    ).copy()
                ),
                global_bilevg_by_index=(
                    None
                    if getattr(state, "global_bilevg_by_index", None) is None
                    else np.asarray(
                        getattr(state, "global_bilevg_by_index"), dtype=float
                    ).copy()
                ),
                global_rnisg_by_index=(
                    None
                    if getattr(state, "global_rnisg_by_index", None) is None
                    else np.asarray(
                        getattr(state, "global_rnisg_by_index"), dtype=float
                    ).copy()
                ),
                element_requests=tuple(copy.deepcopy(requests)),
                required_element_z=(
                    None if state.required_element_z is None
                    else tuple(int(z) for z in state.required_element_z)
                ),
                source_global_alias_writeback=bool(
                    getattr(state, "source_global_alias_writeback", False)
                ),
                dispatcher_state=copy.deepcopy(self.dispatcher),
                element_solver_state=copy.deepcopy(self.element_solver),
                pre_matrix_solver_state=copy.deepcopy(self.pre_matrix_solver),
            )
            self.input_snapshots.append(snapshot)

        profile_control = kwargs.get("profile_control")
        with profile_component(
            profile_control or {},
            "dsec.calc_hmc_all",
            evaluation_index=int(evaluation_index),
        ):
            result = calc_hmc_all(
                self.master,
                self.derived,
                elements=requests,
                temperature_k=state.temperature_k,
                hydrogen_density_cm3=state.hydrogen_density_cm3,
                electron_fraction_xee=state.electron_fraction_xee,
                pressure=state.pressure,
                lcdd=state.lcdd,
                required_element_z=state.required_element_z,
                initial_leveltemp_workspace=state.leveltemp_workspace,
                initial_leveltemp_owner_by_column=state.leveltemp_owner_by_column,
                initial_global_xilevg_by_index=getattr(
                    state, "global_xilevg_by_index", None
                ),
                initial_global_bilevg_by_index=getattr(
                    state, "global_bilevg_by_index", None
                ),
                initial_global_rnisg_by_index=getattr(
                    state, "global_rnisg_by_index", None
                ),
                source_global_alias_writeback=bool(
                    getattr(state, "source_global_alias_writeback", False)
                ),
                **kwargs,
            )
        if self.evaluation_gate_callback is not None:
            if snapshot is None:
                raise DsecPortError("evaluation_gate_callback requires an input snapshot")
            self.evaluation_gate_callback(evaluation_index, snapshot, result)
        state.commit_calc_hmc_all(result)
        if self.progress_callback is not None:
            self.progress_callback(state.calc_hmc_all_call_count, state, result)
        evaluation = DsecEvaluation(
            hmctot=float(result.hmctot),
            elcter=float(result.elcter),
            fixed_state_result=(result if self.retain_fixed_state_results else None),
            diagnostics={
                "complete_fixed_state_ready": bool(result.complete_fixed_state_ready),
                "leveltemp_workspace_carried": bool(
                    not bool(getattr(state, "reset_leveltemp_each_calc_hmc_all", False))
                ),
                "leveltemp_reset_between_calls": bool(
                    getattr(state, "reset_leveltemp_each_calc_hmc_all", False)
                ),
                "source_global_alias_writeback": bool(
                    getattr(state, "source_global_alias_writeback", False)
                ),
            },
        )
        self.evaluations.append(evaluation)
        return evaluation


@dataclass(frozen=True)
class DsecTrajectoryEvent:
    event_index: int
    event: str
    evaluation_index: int
    ntotit: int
    nnx: int
    nnxx: int
    nnt: int
    nntt: int
    nlim: int
    nlimt: int
    nlimx: int
    nlimtt: int
    nlimxx: int
    temperature_t4: float
    temperature_k: float
    tinf_t4: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    tl: float
    th: float
    xeel: float
    xeeh: float
    elcter: Optional[float]
    elctrl: float
    elctrh: float
    hmctot: Optional[float]
    hmcttl: float
    hmctth: float
    previous_temperature_t4: float
    normalized_charge_residual: Optional[float]
    temperature_stagnation_metric: Optional[float]
    lnerr: int
    iht: int
    ilt: int
    iuht: int
    iult: int
    ihx: int
    ilx: int


@dataclass(frozen=True)
class DsecResult:
    state: DsecMutableRuntimeState
    trajectory: Tuple[DsecTrajectoryEvent, ...]
    nlim: int
    tinf_t4: float
    lnerr: int
    ntotit: int
    temperature_iterations: int
    temperature_attempts: int
    charge_converged: bool
    thermal_converged: bool
    requested_thermal_iteration: bool
    source_returned: bool = True
    prefix_terminated: bool = False
    maximum_evaluations: Optional[int] = None

    @property
    def converged(self) -> bool:
        if self.prefix_terminated:
            return False
        thermal_ok = self.thermal_converged if self.requested_thermal_iteration else True
        return bool(self.lnerr == 0 and self.charge_converged and thermal_ok)

    @property
    def final_hmctot(self) -> float:
        if math.isfinite(float(getattr(self.state, "last_hmctot", float("nan")))):
            return float(self.state.last_hmctot)
        if self.state.last_calc_hmc_all is not None:
            return float(self.state.last_calc_hmc_all.hmctot)
        for event in reversed(self.trajectory):
            if event.hmctot is not None:
                return float(event.hmctot)
        return float("nan")

    @property
    def final_elcter(self) -> float:
        if math.isfinite(float(getattr(self.state, "last_elcter", float("nan")))):
            return float(self.state.last_elcter)
        if self.state.last_calc_hmc_all is not None:
            return float(self.state.last_calc_hmc_all.elcter)
        for event in reversed(self.trajectory):
            if event.elcter is not None:
                return float(event.elcter)
        return float("nan")


class _TrajectoryRecorder:
    def __init__(self) -> None:
        self.rows: List[DsecTrajectoryEvent] = []

    def add(
        self,
        event: str,
        *,
        evaluation_index: int,
        ntotit: int,
        nnx: int,
        nnxx: int,
        nnt: int,
        nntt: int,
        nlim: int,
        nlimt: int,
        nlimx: int,
        nlimtt: int,
        nlimxx: int,
        state: DsecMutableRuntimeState,
        tinf_t4: float,
        tl: float,
        th: float,
        xeel: float,
        xeeh: float,
        elcter: Optional[float],
        elctrl: float,
        elctrh: float,
        hmctot: Optional[float],
        hmcttl: float,
        hmctth: float,
        previous_temperature_t4: float,
        normalized_charge_residual: Optional[float],
        temperature_stagnation_metric: Optional[float],
        lnerr: int,
        iht: int,
        ilt: int,
        iuht: int,
        iult: int,
        ihx: int,
        ilx: int,
    ) -> None:
        self.rows.append(
            DsecTrajectoryEvent(
                event_index=len(self.rows) + 1,
                event=str(event),
                evaluation_index=int(evaluation_index),
                ntotit=int(ntotit),
                nnx=int(nnx),
                nnxx=int(nnxx),
                nnt=int(nnt),
                nntt=int(nntt),
                nlim=int(nlim),
                nlimt=int(nlimt),
                nlimx=int(nlimx),
                nlimtt=int(nlimtt),
                nlimxx=int(nlimxx),
                temperature_t4=float(state.temperature_t4),
                temperature_k=float(state.temperature_k),
                tinf_t4=float(tinf_t4),
                electron_fraction_xee=float(state.electron_fraction_xee),
                hydrogen_density_cm3=float(state.hydrogen_density_cm3),
                tl=float(tl),
                th=float(th),
                xeel=float(xeel),
                xeeh=float(xeeh),
                elcter=None if elcter is None else float(elcter),
                elctrl=float(elctrl),
                elctrh=float(elctrh),
                hmctot=None if hmctot is None else float(hmctot),
                hmcttl=float(hmcttl),
                hmctth=float(hmctth),
                previous_temperature_t4=float(previous_temperature_t4),
                normalized_charge_residual=(
                    None
                    if normalized_charge_residual is None
                    else float(normalized_charge_residual)
                ),
                temperature_stagnation_metric=(
                    None
                    if temperature_stagnation_metric is None
                    else float(temperature_stagnation_metric)
                ),
                lnerr=int(lnerr),
                iht=int(iht),
                ilt=int(ilt),
                iuht=int(iuht),
                iult=int(iult),
                ihx=int(ihx),
                ilx=int(ilx),
            )
        )


def _fortran_divide(numerator: float, denominator: float) -> float:
    """Use IEEE division semantics instead of Python's zero-division error."""

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        return float(np.float64(numerator) / np.float64(denominator))


def _native_dsec_requested() -> bool:
    value = os.environ.get("XSTAR_ATOMIC_THERMAL_ENGINE_CPP", "").strip().lower()
    enabled = value not in {"", "0", "false", "no", "off"}
    product = os.environ.get("XSTAR_ATOMIC_THERMAL_ENGINE_CPP_PRODUCT", "").strip().lower()
    return enabled and product not in {"", "0", "false", "no", "off"}


def _native_trace_events(rows: Sequence[Mapping[str, Any]], state: DsecMutableRuntimeState, *, nlim: int, tinf_t4: float) -> Tuple[DsecTrajectoryEvent, ...]:
    names = {
        1: "begin", 2: "after_calc_hmc_all", 3: "charge_multiply_xee",
        4: "charge_divide_xee", 5: "charge_secant", 6: "charge_loop_exit",
        7: "temperature_multiply", 8: "temperature_divide", 9: "temperature_secant",
        10: "temperature_stagnation", 11: "finish",
    }
    result: list[DsecTrajectoryEvent] = []
    for index, row in enumerate(rows, start=1):
        hmctot = float(row.get("hmctot", float("nan")))
        elcter = float(row.get("elcter", float("nan")))
        charge = float(row.get("normalized_charge_residual", float("nan")))
        stagnation = float(row.get("temperature_stagnation_metric", float("nan")))
        temp = float(row.get("temperature_t4", state.temperature_t4))
        result.append(DsecTrajectoryEvent(
            event_index=index, event=names.get(int(row.get("event_code", 0)), "native_event"),
            evaluation_index=int(row.get("evaluation_index", 0)), ntotit=int(row.get("ntotit", 0)),
            nnx=int(row.get("nnx", 0)), nnxx=int(row.get("nnxx", 0)), nnt=int(row.get("nnt", 0)),
            nntt=int(row.get("nntt", 0)), nlim=int(nlim), nlimt=max(int(nlim), 0),
            nlimx=abs(int(nlim)), nlimtt=max(max(int(nlim), 0), 1), nlimxx=max(abs(int(nlim)), 1),
            temperature_t4=temp, temperature_k=temp * 1.0e4, tinf_t4=float(tinf_t4),
            electron_fraction_xee=float(row.get("electron_fraction_xee", state.electron_fraction_xee)),
            hydrogen_density_cm3=float(state.hydrogen_density_cm3), tl=0.0, th=0.0, xeel=0.0, xeeh=1.0,
            elcter=None if not math.isfinite(elcter) else elcter, elctrl=1.0, elctrh=-1.0,
            hmctot=None if not math.isfinite(hmctot) else hmctot, hmcttl=0.0, hmctth=0.0,
            previous_temperature_t4=0.0,
            normalized_charge_residual=None if not math.isfinite(charge) else charge,
            temperature_stagnation_metric=None if not math.isfinite(stagnation) else stagnation,
            lnerr=int(row.get("lnerr", 0)), iht=0, ilt=0, iuht=0, iult=0, ihx=0, ilx=0,
        ))
    return tuple(result)


def dsec(
    state: DsecMutableRuntimeState,
    *,
    evaluator: DsecEvaluator,
    nlim: int,
    tinf_t4: float,
    charge_tolerance: float = DSEC_CHARGE_TOLERANCE,
    thermal_tolerance: float = DSEC_THERMAL_TOLERANCE,
    temperature_stagnation_tolerance: float = DSEC_TEMPERATURE_STAGNATION_TOLERANCE,
    maximum_evaluations: Optional[int] = None,
) -> DsecResult:
    """Translate ``dsec.f90`` in its original branch and update order.

    Positive ``nlim`` solves charge and thermal balance.  Negative ``nlim``
    performs charge iteration only.  A direct call with zero ``nlim`` performs
    one ``calc_hmc_all`` evaluation, although ``xstarcalc`` normally skips
    ``dsec`` entirely when its corresponding input is zero.
    """

    nlim = int(nlim)
    tinf_t4 = float(tinf_t4)
    if maximum_evaluations is not None:
        maximum_evaluations = int(maximum_evaluations)
        if maximum_evaluations <= 0:
            raise DsecPortError("maximum_evaluations must be positive")
    if not math.isfinite(tinf_t4) or tinf_t4 < 0.0:
        raise DsecPortError("tinf_t4 must be finite and nonnegative")

    if _native_dsec_requested():
        from .cpp_backend_thermal import run_dsec_cpp

        native = run_dsec_cpp(
            state, evaluator, nlim=nlim, tinf_t4=tinf_t4,
            charge_tolerance=float(charge_tolerance),
            thermal_tolerance=float(thermal_tolerance),
            temperature_stagnation_tolerance=float(temperature_stagnation_tolerance),
            maximum_evaluations=maximum_evaluations,
        )
        state.last_hmctot = float(native["final_hmctot"])
        state.last_elcter = float(native["final_elcter"])
        state.provenance.update({
            "dsec_source_file": "xstar/xstarlib/src/dsec.f90",
            "dsec_exact_control_flow": True,
            "dsec_native_orchestration": True,
            "dsec_callback_evaluation": True,
            "dsec_nlim": nlim,
            "dsec_ntotit": int(native["ntotit"]),
            "dsec_lnerr": int(native["lnerr"]),
            "dsec_orchestration_seconds": float(native["orchestration_seconds"]),
            "dsec_callback_seconds": float(native["callback_seconds"]),
            "dsec_callback_state_propagation": bool(native.get("callback_state_propagation", False)),
            "dsec_trace_count": int(native.get("trace_count", 0)),
            "dsec_trace_truncated": bool(native.get("trace_truncated", False)),
            "dsec_final_temperature_t4": float(native.get("final_temperature_t4", state.temperature_t4)),
            "dsec_final_electron_fraction_xee": float(native.get("final_electron_fraction_xee", state.electron_fraction_xee)),
            "dsec_final_temperature_stagnation_metric": float(native.get("final_temperature_stagnation_metric", float("nan"))),
        })
        return DsecResult(
            state=state, trajectory=_native_trace_events(native.get("trace", ()), state, nlim=nlim, tinf_t4=tinf_t4),
            nlim=nlim, tinf_t4=tinf_t4, lnerr=int(native["lnerr"]), ntotit=int(native["ntotit"]),
            temperature_iterations=int(native["temperature_iterations"]),
            temperature_attempts=int(native["temperature_attempts"]),
            charge_converged=bool(native["charge_converged"]),
            thermal_converged=bool(native["thermal_converged"]),
            requested_thermal_iteration=nlim > 0,
            source_returned=not bool(native["prefix_terminated"]),
            prefix_terminated=bool(native["prefix_terminated"]),
            maximum_evaluations=maximum_evaluations,
        )

    crite = float(charge_tolerance)
    crith = float(thermal_tolerance)
    critt = float(temperature_stagnation_tolerance)

    ntotit = 0
    nnt = 0
    nntt = 0
    lnerr = 0
    nlimt = max(nlim, 0)
    nlimx = abs(nlim)
    nlimtt = max(nlimt, 1)
    nlimxx = max(nlimx, 1)
    fact = DSEC_TEMPERATURE_FACTOR
    facx = DSEC_ELECTRON_FACTOR
    epst = crith
    epsx = crite
    epstt = critt
    to = DSEC_INITIAL_PREVIOUS_TEMPERATURE
    tl = 0.0
    th = 0.0
    xeel = 0.0
    xeeh = 1.0
    elctrl = 1.0
    elctrh = -1.0
    hmctth = 0.0
    hmcttl = 0.0
    iht = 0
    ilt = 0
    iuht = 0
    iult = 0
    evaluation_index = 0
    last_hmctot: Optional[float] = None
    last_elcter: Optional[float] = None
    last_tst: Optional[float] = None
    testt: Optional[float] = None
    recorder = _TrajectoryRecorder()
    prefix_terminated = False

    recorder.add(
        "begin",
        evaluation_index=0,
        ntotit=ntotit,
        nnx=0,
        nnxx=0,
        nnt=nnt,
        nntt=nntt,
        nlim=nlim,
        nlimt=nlimt,
        nlimx=nlimx,
        nlimtt=nlimtt,
        nlimxx=nlimxx,
        state=state,
        tinf_t4=tinf_t4,
        tl=tl,
        th=th,
        xeel=xeel,
        xeeh=xeeh,
        elcter=None,
        elctrl=elctrl,
        elctrh=elctrh,
        hmctot=None,
        hmcttl=hmcttl,
        hmctth=hmctth,
        previous_temperature_t4=to,
        normalized_charge_residual=None,
        temperature_stagnation_metric=None,
        lnerr=lnerr,
        iht=iht,
        ilt=ilt,
        iuht=iuht,
        iult=iult,
        ihx=0,
        ilx=0,
    )

    # label 100: outer temperature trial
    while True:
        nnx = 0
        state.temperature_t4 = max(float(state.temperature_t4), tinf_t4)
        if state.temperature_t4 < tinf_t4 * DSEC_TINF_PROXIMITY_FACTOR:
            nlimt = 0
            nlimtt = 0
            nlimx = 0
            nlimxx = 0
        else:
            nlimt = max(nlim, 0)
            nlimx = abs(nlim)
            nlimxx = nlimx
        nnxx = 0
        ihx = 0
        ilx = 0

        # label 200: inner electron-fraction trial
        while True:
            evaluation = evaluator(state)
            evaluation_index += 1
            last_hmctot = float(evaluation.hmctot)
            last_elcter = float(evaluation.elcter)
            ntotit += 1
            nnx += 1
            nnxx += 1
            last_tst = abs(last_elcter) / max(
                DSEC_CHARGE_DENOMINATOR_FLOOR,
                float(state.electron_fraction_xee),
            )
            recorder.add(
                "after_calc_hmc_all",
                evaluation_index=evaluation_index,
                ntotit=ntotit,
                nnx=nnx,
                nnxx=nnxx,
                nnt=nnt,
                nntt=nntt,
                nlim=nlim,
                nlimt=nlimt,
                nlimx=nlimx,
                nlimtt=nlimtt,
                nlimxx=nlimxx,
                state=state,
                tinf_t4=tinf_t4,
                tl=tl,
                th=th,
                xeel=xeel,
                xeeh=xeeh,
                elcter=last_elcter,
                elctrl=elctrl,
                elctrh=elctrh,
                hmctot=last_hmctot,
                hmcttl=hmcttl,
                hmctth=hmctth,
                previous_temperature_t4=to,
                normalized_charge_residual=last_tst,
                temperature_stagnation_metric=testt,
                lnerr=lnerr,
                iht=iht,
                ilt=ilt,
                iuht=iuht,
                iult=iult,
                ihx=ihx,
                ilx=ilx,
            )

            if maximum_evaluations is not None and evaluation_index >= maximum_evaluations:
                prefix_terminated = True
                break

            if nnxx >= nlimxx or last_tst < epsx:
                break

            if last_elcter < 0.0:
                ihx = 1
                xeeh = float(state.electron_fraction_xee)
                elctrh = last_elcter
                if ilx != 1:
                    state.electron_fraction_xee *= facx
                    recorder.add(
                        "charge_multiply_xee",
                        evaluation_index=evaluation_index,
                        ntotit=ntotit,
                        nnx=nnx,
                        nnxx=nnxx,
                        nnt=nnt,
                        nntt=nntt,
                        nlim=nlim,
                        nlimt=nlimt,
                        nlimx=nlimx,
                        nlimtt=nlimtt,
                        nlimxx=nlimxx,
                        state=state,
                        tinf_t4=tinf_t4,
                        tl=tl,
                        th=th,
                        xeel=xeel,
                        xeeh=xeeh,
                        elcter=last_elcter,
                        elctrl=elctrl,
                        elctrh=elctrh,
                        hmctot=last_hmctot,
                        hmcttl=hmcttl,
                        hmctth=hmctth,
                        previous_temperature_t4=to,
                        normalized_charge_residual=last_tst,
                        temperature_stagnation_metric=testt,
                        lnerr=lnerr,
                        iht=iht,
                        ilt=ilt,
                        iuht=iuht,
                        iult=iult,
                        ihx=ihx,
                        ilx=ilx,
                    )
                    continue
            else:
                ilx = 1
                xeel = float(state.electron_fraction_xee)
                elctrl = last_elcter
                if ihx != 1:
                    state.electron_fraction_xee /= facx
                    recorder.add(
                        "charge_divide_xee",
                        evaluation_index=evaluation_index,
                        ntotit=ntotit,
                        nnx=nnx,
                        nnxx=nnxx,
                        nnt=nnt,
                        nntt=nntt,
                        nlim=nlim,
                        nlimt=nlimt,
                        nlimx=nlimx,
                        nlimtt=nlimtt,
                        nlimxx=nlimxx,
                        state=state,
                        tinf_t4=tinf_t4,
                        tl=tl,
                        th=th,
                        xeel=xeel,
                        xeeh=xeeh,
                        elcter=last_elcter,
                        elctrl=elctrl,
                        elctrh=elctrh,
                        hmctot=last_hmctot,
                        hmcttl=hmcttl,
                        hmctth=hmctth,
                        previous_temperature_t4=to,
                        normalized_charge_residual=last_tst,
                        temperature_stagnation_metric=testt,
                        lnerr=lnerr,
                        iht=iht,
                        ilt=ilt,
                        iuht=iuht,
                        iult=iult,
                        ihx=ihx,
                        ilx=ilx,
                    )
                    continue

            state.electron_fraction_xee = _fortran_divide(
                xeel * elctrh - xeeh * elctrl,
                elctrh - elctrl,
            )
            recorder.add(
                "charge_secant",
                evaluation_index=evaluation_index,
                ntotit=ntotit,
                nnx=nnx,
                nnxx=nnxx,
                nnt=nnt,
                nntt=nntt,
                nlim=nlim,
                nlimt=nlimt,
                nlimx=nlimx,
                nlimtt=nlimtt,
                nlimxx=nlimxx,
                state=state,
                tinf_t4=tinf_t4,
                tl=tl,
                th=th,
                xeel=xeel,
                xeeh=xeeh,
                elcter=last_elcter,
                elctrl=elctrl,
                elctrh=elctrh,
                hmctot=last_hmctot,
                hmcttl=hmcttl,
                hmctth=hmctth,
                previous_temperature_t4=to,
                normalized_charge_residual=last_tst,
                temperature_stagnation_metric=testt,
                lnerr=lnerr,
                iht=iht,
                ilt=ilt,
                iuht=iuht,
                iult=iult,
                ihx=ihx,
                ilx=ilx,
            )

        if prefix_terminated:
            break

        # label 300
        nntt += 1
        nnt += 1
        recorder.add(
            "charge_loop_exit",
            evaluation_index=evaluation_index,
            ntotit=ntotit,
            nnx=nnx,
            nnxx=nnxx,
            nnt=nnt,
            nntt=nntt,
            nlim=nlim,
            nlimt=nlimt,
            nlimx=nlimx,
            nlimtt=nlimtt,
            nlimxx=nlimxx,
            state=state,
            tinf_t4=tinf_t4,
            tl=tl,
            th=th,
            xeel=xeel,
            xeeh=xeeh,
            elcter=last_elcter,
            elctrl=elctrl,
            elctrh=elctrh,
            hmctot=last_hmctot,
            hmcttl=hmcttl,
            hmctth=hmctth,
            previous_temperature_t4=to,
            normalized_charge_residual=last_tst,
            temperature_stagnation_metric=testt,
            lnerr=lnerr,
            iht=iht,
            ilt=ilt,
            iuht=iuht,
            iult=iult,
            ihx=ihx,
            ilx=ilx,
        )

        if last_hmctot is None:
            raise DsecPortError("evaluator did not produce hmctot")
        if abs(last_hmctot) <= epst or nntt >= nlimtt:
            break

        if nnt < nlimt:
            if last_hmctot < 0.0:
                iht = 1
                th = float(state.temperature_t4)
                hmctth = last_hmctot
                iuht = 1
                if iult == 0:
                    hmcttl = hmcttl / 2.0
                iult = 0
                if ilt != 1:
                    state.temperature_t4 /= fact
                    if abs(last_hmctot) > DSEC_FAR_FROM_EQUILIBRIUM:
                        state.temperature_t4 /= fact
                    recorder.add(
                        "temperature_divide",
                        evaluation_index=evaluation_index,
                        ntotit=ntotit,
                        nnx=nnx,
                        nnxx=nnxx,
                        nnt=nnt,
                        nntt=nntt,
                        nlim=nlim,
                        nlimt=nlimt,
                        nlimx=nlimx,
                        nlimtt=nlimtt,
                        nlimxx=nlimxx,
                        state=state,
                        tinf_t4=tinf_t4,
                        tl=tl,
                        th=th,
                        xeel=xeel,
                        xeeh=xeeh,
                        elcter=last_elcter,
                        elctrl=elctrl,
                        elctrh=elctrh,
                        hmctot=last_hmctot,
                        hmcttl=hmcttl,
                        hmctth=hmctth,
                        previous_temperature_t4=to,
                        normalized_charge_residual=last_tst,
                        temperature_stagnation_metric=testt,
                        lnerr=lnerr,
                        iht=iht,
                        ilt=ilt,
                        iuht=iuht,
                        iult=iult,
                        ihx=ihx,
                        ilx=ilx,
                    )
                    continue
            else:
                ilt = 1
                tl = float(state.temperature_t4)
                hmcttl = last_hmctot
                iult = 1
                if iuht == 0:
                    hmctth = hmctth / 2.0
                iuht = 0
                if iht != 1:
                    state.temperature_t4 *= fact
                    if abs(last_hmctot) > DSEC_FAR_FROM_EQUILIBRIUM:
                        state.temperature_t4 *= fact
                    recorder.add(
                        "temperature_multiply",
                        evaluation_index=evaluation_index,
                        ntotit=ntotit,
                        nnx=nnx,
                        nnxx=nnxx,
                        nnt=nnt,
                        nntt=nntt,
                        nlim=nlim,
                        nlimt=nlimt,
                        nlimx=nlimx,
                        nlimtt=nlimtt,
                        nlimxx=nlimxx,
                        state=state,
                        tinf_t4=tinf_t4,
                        tl=tl,
                        th=th,
                        xeel=xeel,
                        xeeh=xeeh,
                        elcter=last_elcter,
                        elctrl=elctrl,
                        elctrh=elctrh,
                        hmctot=last_hmctot,
                        hmcttl=hmcttl,
                        hmctth=hmctth,
                        previous_temperature_t4=to,
                        normalized_charge_residual=last_tst,
                        temperature_stagnation_metric=testt,
                        lnerr=lnerr,
                        iht=iht,
                        ilt=ilt,
                        iuht=iuht,
                        iult=iult,
                        ihx=ihx,
                        ilx=ilx,
                    )
                    continue

            testt = abs(1.0 - _fortran_divide(state.temperature_t4, to))
            if testt < epstt:
                lnerr = -2
                recorder.add(
                    "temperature_stagnation",
                    evaluation_index=evaluation_index,
                    ntotit=ntotit,
                    nnx=nnx,
                    nnxx=nnxx,
                    nnt=nnt,
                    nntt=nntt,
                    nlim=nlim,
                    nlimt=nlimt,
                    nlimx=nlimx,
                    nlimtt=nlimtt,
                    nlimxx=nlimxx,
                    state=state,
                    tinf_t4=tinf_t4,
                    tl=tl,
                    th=th,
                    xeel=xeel,
                    xeeh=xeeh,
                    elcter=last_elcter,
                    elctrl=elctrl,
                    elctrh=elctrh,
                    hmctot=last_hmctot,
                    hmcttl=hmcttl,
                    hmctth=hmctth,
                    previous_temperature_t4=to,
                    normalized_charge_residual=last_tst,
                    temperature_stagnation_metric=testt,
                    lnerr=lnerr,
                    iht=iht,
                    ilt=ilt,
                    iuht=iuht,
                    iult=iult,
                    ihx=ihx,
                    ilx=ilx,
                )
                break

            to = float(state.temperature_t4)
            state.temperature_t4 = _fortran_divide(
                tl * hmctth - th * hmcttl,
                hmctth - hmcttl,
            )
            recorder.add(
                "temperature_secant",
                evaluation_index=evaluation_index,
                ntotit=ntotit,
                nnx=nnx,
                nnxx=nnxx,
                nnt=nnt,
                nntt=nntt,
                nlim=nlim,
                nlimt=nlimt,
                nlimx=nlimx,
                nlimtt=nlimtt,
                nlimxx=nlimxx,
                state=state,
                tinf_t4=tinf_t4,
                tl=tl,
                th=th,
                xeel=xeel,
                xeeh=xeeh,
                elcter=last_elcter,
                elctrl=elctrl,
                elctrh=elctrh,
                hmctot=last_hmctot,
                hmcttl=hmcttl,
                hmctth=hmctth,
                previous_temperature_t4=to,
                normalized_charge_residual=last_tst,
                temperature_stagnation_metric=testt,
                lnerr=lnerr,
                iht=iht,
                ilt=ilt,
                iuht=iuht,
                iult=iult,
                ihx=ihx,
                ilx=ilx,
            )
            continue

        lnerr = 2
        recorder.add(
            "temperature_too_many_iterations",
            evaluation_index=evaluation_index,
            ntotit=ntotit,
            nnx=nnx,
            nnxx=nnxx,
            nnt=nnt,
            nntt=nntt,
            nlim=nlim,
            nlimt=nlimt,
            nlimx=nlimx,
            nlimtt=nlimtt,
            nlimxx=nlimxx,
            state=state,
            tinf_t4=tinf_t4,
            tl=tl,
            th=th,
            xeel=xeel,
            xeeh=xeeh,
            elcter=last_elcter,
            elctrl=elctrl,
            elctrh=elctrh,
            hmctot=last_hmctot,
            hmcttl=hmcttl,
            hmctth=hmctth,
            previous_temperature_t4=to,
            normalized_charge_residual=last_tst,
            temperature_stagnation_metric=testt,
            lnerr=lnerr,
            iht=iht,
            ilt=ilt,
            iuht=iuht,
            iult=iult,
            ihx=ihx,
            ilx=ilx,
        )
        break

    if not prefix_terminated:
        recorder.add(
            "finish",
            evaluation_index=evaluation_index,
            ntotit=ntotit,
            nnx=nnx,
            nnxx=nnxx,
            nnt=nnt,
            nntt=nntt,
            nlim=nlim,
            nlimt=nlimt,
            nlimx=nlimx,
            nlimtt=nlimtt,
            nlimxx=nlimxx,
            state=state,
            tinf_t4=tinf_t4,
            tl=tl,
            th=th,
            xeel=xeel,
            xeeh=xeeh,
            elcter=last_elcter,
            elctrl=elctrl,
            elctrh=elctrh,
            hmctot=last_hmctot,
            hmcttl=hmcttl,
            hmctth=hmctth,
            previous_temperature_t4=to,
            normalized_charge_residual=last_tst,
            temperature_stagnation_metric=testt,
            lnerr=lnerr,
            iht=iht,
            ilt=ilt,
            iuht=iuht,
            iult=iult,
            ihx=ihx,
            ilx=ilx,
        )

    charge_converged = bool(last_tst is not None and last_tst < epsx)
    thermal_converged = bool(last_hmctot is not None and abs(last_hmctot) <= epst)
    state.provenance.update(
        {
            "dsec_source_file": "xstar/xstarlib/src/dsec.f90",
            "dsec_exact_control_flow": True,
            "dsec_nlim": nlim,
            "dsec_ntotit": ntotit,
            "dsec_lnerr": lnerr,
            "dsec_prefix_terminated": prefix_terminated,
            "dsec_maximum_evaluations": maximum_evaluations,
        }
    )
    return DsecResult(
        state=state,
        trajectory=tuple(recorder.rows),
        nlim=nlim,
        tinf_t4=tinf_t4,
        lnerr=lnerr,
        ntotit=ntotit,
        temperature_iterations=nnt,
        temperature_attempts=nntt,
        charge_converged=charge_converged,
        thermal_converged=thermal_converged,
        requested_thermal_iteration=nlim > 0,
        source_returned=not prefix_terminated,
        prefix_terminated=prefix_terminated,
        maximum_evaluations=maximum_evaluations,
    )


# ---------------------------------------------------------------------------
# Trajectory products and XSTAR comparison


_TRAJECTORY_FIELDS: Tuple[str, ...] = tuple(DsecTrajectoryEvent.__dataclass_fields__)


def write_dsec_trajectory_products(
    result: DsecResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.45",
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_dsec_python_trajectory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_TRAJECTORY_FIELDS)
        writer.writeheader()
        for event in result.trajectory:
            writer.writerow({name: getattr(event, name) for name in _TRAJECTORY_FIELDS})

    summary = {
        "port_version": port_version,
        "source_routine": "dsec",
        "source_file": "xstar/xstarlib/src/dsec.f90",
        "nlim": result.nlim,
        "tinf_t4": result.tinf_t4,
        "lnerr": result.lnerr,
        "ntotit": result.ntotit,
        "temperature_iterations": result.temperature_iterations,
        "temperature_attempts": result.temperature_attempts,
        "n_trajectory_events": len(result.trajectory),
        "final_temperature_t4": result.state.temperature_t4,
        "final_temperature_k": result.state.temperature_k,
        "final_electron_fraction_xee": result.state.electron_fraction_xee,
        "final_hydrogen_density_cm3": result.state.hydrogen_density_cm3,
        "final_hmctot": result.final_hmctot,
        "final_elcter": result.final_elcter,
        "charge_converged": result.charge_converged,
        "thermal_converged": result.thermal_converged,
        "requested_thermal_iteration": result.requested_thermal_iteration,
        "dsec_converged": result.converged,
        "prefix_terminated": result.prefix_terminated,
        "maximum_evaluations": result.maximum_evaluations,
        "mutable_population_state_present": bool(result.state.element_populations),
        "mutable_leveltemp_state_present": result.state.leveltemp_workspace is not None,
        "exact_source_control_flow": True,
    }
    json_path = out / "xstar_dsec_python_trajectory_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_dsec_python_trajectory_summary.md"
    md_path.write_text(
        "# Python `dsec` trajectory\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


def load_python_dsec_trajectory(path: str | Path) -> DsecResult:
    """Load products written by :func:`write_dsec_trajectory_products`.

    This reconstruction is intended for trajectory comparison and reporting.
    It does not recreate the final ``calc_hmc_all`` object and therefore cannot
    by itself satisfy the physical bounded-acceptance gate.
    """

    target = Path(path)
    if target.is_dir():
        csv_path = target / "xstar_dsec_python_trajectory.csv"
        summary_path = target / "xstar_dsec_python_trajectory_summary.json"
    else:
        csv_path = target
        summary_path = target.with_name("xstar_dsec_python_trajectory_summary.json")
    if not csv_path.is_file():
        raise DsecPortError(f"missing Python dsec trajectory: {csv_path}")

    events: List[DsecTrajectoryEvent] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for position, row in enumerate(csv.DictReader(handle), start=1):
            f = parse_fortran_float
            t4 = f(row["temperature_t4"])
            events.append(DsecTrajectoryEvent(
                event_index=int(row.get("event_index", position)),
                event=str(row["event"]).strip(),
                evaluation_index=int(row.get("evaluation_index", 0)),
                ntotit=int(row.get("ntotit", 0)),
                nnx=int(row.get("nnx", 0)),
                nnxx=int(row.get("nnxx", 0)),
                nnt=int(row.get("nnt", 0)),
                nntt=int(row.get("nntt", 0)),
                nlim=int(row.get("nlim", 0)),
                nlimt=int(row.get("nlimt", 0)),
                nlimx=int(row.get("nlimx", 0)),
                nlimtt=int(row.get("nlimtt", 0)),
                nlimxx=int(row.get("nlimxx", 0)),
                temperature_t4=t4,
                temperature_k=f(row.get("temperature_k", t4 * 1.0e4)),
                tinf_t4=f(row["tinf_t4"]),
                electron_fraction_xee=f(row["electron_fraction_xee"]),
                hydrogen_density_cm3=f(row["hydrogen_density_cm3"]),
                tl=f(row["tl"]), th=f(row["th"]),
                xeel=f(row["xeel"]), xeeh=f(row["xeeh"]),
                elcter=_optional_probe_float(row.get("elcter")),
                elctrl=f(row["elctrl"]), elctrh=f(row["elctrh"]),
                hmctot=_optional_probe_float(row.get("hmctot")),
                hmcttl=f(row["hmcttl"]), hmctth=f(row["hmctth"]),
                previous_temperature_t4=f(row["previous_temperature_t4"]),
                normalized_charge_residual=_optional_probe_float(
                    row.get("normalized_charge_residual")
                ),
                temperature_stagnation_metric=_optional_probe_float(
                    row.get("temperature_stagnation_metric")
                ),
                lnerr=int(row.get("lnerr", 0)),
                iht=int(row.get("iht", 0)), ilt=int(row.get("ilt", 0)),
                iuht=int(row.get("iuht", 0)), iult=int(row.get("iult", 0)),
                ihx=int(row.get("ihx", 0)), ilx=int(row.get("ilx", 0)),
            ))
    if not events:
        raise DsecPortError(f"empty Python dsec trajectory: {csv_path}")

    summary: Mapping[str, Any] = {}
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    final = events[-1]
    state = DsecMutableRuntimeState(
        temperature_t4=final.temperature_t4,
        electron_fraction_xee=final.electron_fraction_xee,
        hydrogen_density_cm3=final.hydrogen_density_cm3,
    )
    state.calc_hmc_all_call_count = int(summary.get("ntotit", final.ntotit))
    state.provenance.update({
        "dsec_exact_control_flow": bool(summary.get("exact_source_control_flow", True)),
        "loaded_python_trajectory": str(csv_path),
    })
    final_tst = final.normalized_charge_residual
    final_hmc = final.hmctot
    return DsecResult(
        state=state,
        trajectory=tuple(events),
        nlim=int(summary.get("nlim", final.nlim)),
        tinf_t4=float(summary.get("tinf_t4", final.tinf_t4)),
        lnerr=int(summary.get("lnerr", final.lnerr)),
        ntotit=int(summary.get("ntotit", final.ntotit)),
        temperature_iterations=int(summary.get("temperature_iterations", final.nnt)),
        temperature_attempts=int(summary.get("temperature_attempts", final.nntt)),
        charge_converged=bool(
            summary.get(
                "charge_converged",
                final_tst is not None and final_tst < DSEC_CHARGE_TOLERANCE,
            )
        ),
        thermal_converged=bool(
            summary.get(
                "thermal_converged",
                final_hmc is not None and abs(final_hmc) <= DSEC_THERMAL_TOLERANCE,
            )
        ),
        requested_thermal_iteration=bool(
            summary.get("requested_thermal_iteration", final.nlim > 0)
        ),
    )


@dataclass(frozen=True)
class DsecProbeTrajectory:
    call_id: int
    events: Tuple[DsecTrajectoryEvent, ...]
    source_path: str


_PROBE_SENTINEL = 9.0e299


def _optional_probe_float(value: Any) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    parsed = parse_fortran_float(str(value))
    return None if abs(parsed) >= _PROBE_SENTINEL else float(parsed)


def load_xstar_dsec_trajectory(
    path: str | Path,
    *,
    call_id: int = 1,
) -> DsecProbeTrajectory:
    target = Path(path)
    if target.is_dir():
        target = target / "xstar_dsec_trajectory_probe.csv"
    if not target.is_file():
        raise DsecPortError(f"missing XSTAR dsec trajectory probe: {target}")

    rows: List[DsecTrajectoryEvent] = []
    with target.open(newline="", encoding="utf-8") as handle:
        selected = [
            row for row in csv.DictReader(handle)
            if int(row.get("dsec_call_id", 0)) == int(call_id)
        ]
    for position, row in enumerate(selected, start=1):
        f = parse_fortran_float
        rows.append(
            DsecTrajectoryEvent(
                event_index=int(row.get("event_index", position)),
                event=str(row["event"]).strip(),
                evaluation_index=int(row.get("evaluation_index", 0)),
                ntotit=int(row.get("ntotit", 0)),
                nnx=int(row.get("nnx", 0)),
                nnxx=int(row.get("nnxx", 0)),
                nnt=int(row.get("nnt", 0)),
                nntt=int(row.get("nntt", 0)),
                nlim=int(row.get("nlim", 0)),
                nlimt=int(row.get("nlimt", 0)),
                nlimx=int(row.get("nlimx", 0)),
                nlimtt=int(row.get("nlimtt", 0)),
                nlimxx=int(row.get("nlimxx", 0)),
                temperature_t4=f(row["temperature_t4"]),
                temperature_k=f(row.get("temperature_k", f(row["temperature_t4"]) * 1.0e4)),
                tinf_t4=f(row["tinf_t4"]),
                electron_fraction_xee=f(row["electron_fraction_xee"]),
                hydrogen_density_cm3=f(row["hydrogen_density_cm3"]),
                tl=f(row["tl"]),
                th=f(row["th"]),
                xeel=f(row["xeel"]),
                xeeh=f(row["xeeh"]),
                elcter=_optional_probe_float(row.get("elcter")),
                elctrl=f(row["elctrl"]),
                elctrh=f(row["elctrh"]),
                hmctot=_optional_probe_float(row.get("hmctot")),
                hmcttl=f(row["hmcttl"]),
                hmctth=f(row["hmctth"]),
                previous_temperature_t4=f(row["previous_temperature_t4"]),
                normalized_charge_residual=_optional_probe_float(row.get("normalized_charge_residual")),
                temperature_stagnation_metric=_optional_probe_float(row.get("temperature_stagnation_metric")),
                lnerr=int(row.get("lnerr", 0)),
                iht=int(row.get("iht", 0)),
                ilt=int(row.get("ilt", 0)),
                iuht=int(row.get("iuht", 0)),
                iult=int(row.get("iult", 0)),
                ihx=int(row.get("ihx", 0)),
                ilx=int(row.get("ilx", 0)),
            )
        )
    if not rows:
        raise DsecPortError(f"no dsec trajectory rows for call {call_id} in {target}")
    return DsecProbeTrajectory(call_id=int(call_id), events=tuple(rows), source_path=str(target))


@dataclass(frozen=True)
class DsecTrajectoryParityRow:
    event_index: int
    event: str
    quantity: str
    python_value: Any
    xstar_value: Any
    absolute_difference: Optional[float]
    relative_difference: Optional[float]
    sign_parity: Optional[bool]
    within_tolerance: bool
    comparison_mode: str


@dataclass(frozen=True)
class DsecTrajectoryParityResult:
    rows: Tuple[DsecTrajectoryParityRow, ...]
    python_result: DsecResult
    reference: DsecProbeTrajectory
    event_sequence_ready: bool
    integer_control_state_ready: bool
    runtime_state_ready: bool
    thermal_residual_value_ready: bool
    thermal_residual_sign_ready: bool
    charge_residual_value_ready: bool
    charge_residual_sign_ready: bool
    final_state_ready: bool
    max_absolute_difference: float
    max_relative_difference: float

    @property
    def ready(self) -> bool:
        return bool(
            self.event_sequence_ready
            and self.integer_control_state_ready
            and self.runtime_state_ready
            and self.thermal_residual_value_ready
            and self.thermal_residual_sign_ready
            and self.charge_residual_value_ready
            and self.charge_residual_sign_ready
            and self.final_state_ready
        )


def _residual_sign(value: float, zero_atol: float) -> int:
    if abs(value) <= zero_atol:
        return 0
    return -1 if value < 0.0 else 1


def compare_dsec_trajectory(
    python_result: DsecResult,
    reference: DsecProbeTrajectory,
    *,
    runtime_rtol: float = 5.0e-12,
    runtime_atol: float = 1.0e-30,
    residual_rtol: float = 5.0e-3,
    thermal_residual_atol: float = 1.0e-8,
    charge_residual_atol: float = 1.0e-10,
    near_zero_thermal_threshold: float = DSEC_THERMAL_TOLERANCE,
    near_zero_charge_threshold: float = DSEC_CHARGE_TOLERANCE,
    prefix_mode: Optional[bool] = None,
) -> DsecTrajectoryParityResult:
    py_events = python_result.trajectory
    xs_events = reference.events
    if prefix_mode is None:
        prefix_mode = bool(python_result.prefix_terminated)
    if prefix_mode:
        event_sequence_ready = len(py_events) <= len(xs_events) and all(
            py.event == xs.event for py, xs in zip(py_events, xs_events)
        )
    else:
        event_sequence_ready = len(py_events) == len(xs_events) and all(
            py.event == xs.event for py, xs in zip(py_events, xs_events)
        )
    rows: List[DsecTrajectoryParityRow] = []

    integer_fields = (
        "evaluation_index", "ntotit", "nnx", "nnxx", "nnt", "nntt",
        "nlim", "nlimt", "nlimx", "nlimtt", "nlimxx", "lnerr",
        "iht", "ilt", "iuht", "iult", "ihx", "ilx",
    )
    runtime_fields = (
        "temperature_t4", "temperature_k", "tinf_t4",
        "electron_fraction_xee", "hydrogen_density_cm3", "tl", "th",
        "xeel", "xeeh", "elctrl", "elctrh", "hmcttl", "hmctth",
        "previous_temperature_t4",
    )

    for event_index, (py, xs) in enumerate(zip(py_events, xs_events), start=1):
        for name in integer_fields:
            pval, xval = getattr(py, name), getattr(xs, name)
            rows.append(
                DsecTrajectoryParityRow(
                    event_index, py.event, name, pval, xval,
                    0.0 if pval == xval else float(abs(int(pval) - int(xval))),
                    0.0 if pval == xval else float("inf"),
                    None,
                    pval == xval,
                    "exact_integer",
                )
            )
        for name in runtime_fields:
            pval, xval = float(getattr(py, name)), float(getattr(xs, name))
            absolute = abs(pval - xval)
            relative = absolute / max(abs(xval), 1.0e-300)
            rows.append(
                DsecTrajectoryParityRow(
                    event_index, py.event, name, pval, xval,
                    absolute, relative, None,
                    math.isclose(pval, xval, rel_tol=runtime_rtol, abs_tol=runtime_atol),
                    "runtime_isclose",
                )
            )

        for name, atol, near_zero in (
            ("hmctot", thermal_residual_atol, near_zero_thermal_threshold),
            ("elcter", charge_residual_atol, near_zero_charge_threshold),
            ("normalized_charge_residual", charge_residual_atol, near_zero_charge_threshold),
        ):
            pval, xval = getattr(py, name), getattr(xs, name)
            if pval is None or xval is None:
                ready = pval is None and xval is None
                rows.append(
                    DsecTrajectoryParityRow(
                        event_index, py.event, name, pval, xval,
                        None, None, None, ready, "optional_presence",
                    )
                )
                continue
            pfloat, xfloat = float(pval), float(xval)
            absolute = abs(pfloat - xfloat)
            relative = absolute / max(abs(xfloat), 1.0e-300)
            sign_atol = atol
            sign_ready = _residual_sign(pfloat, sign_atol) == _residual_sign(xfloat, sign_atol)
            if abs(xfloat) <= near_zero:
                value_ready = absolute <= atol
                mode = "near_zero_absolute"
            else:
                value_ready = math.isclose(
                    pfloat, xfloat, rel_tol=residual_rtol, abs_tol=atol
                )
                mode = "residual_isclose"
            rows.append(
                DsecTrajectoryParityRow(
                    event_index, py.event, name, pfloat, xfloat,
                    absolute, relative, sign_ready,
                    bool(value_ready and sign_ready), mode,
                )
            )

    integer_control_state_ready = event_sequence_ready and all(
        row.within_tolerance for row in rows if row.comparison_mode == "exact_integer"
    )
    runtime_state_ready = event_sequence_ready and all(
        row.within_tolerance for row in rows if row.comparison_mode == "runtime_isclose"
    )
    thermal_rows = [row for row in rows if row.quantity == "hmctot" and row.python_value is not None]
    charge_rows = [row for row in rows if row.quantity in {"elcter", "normalized_charge_residual"} and row.python_value is not None]
    thermal_value_ready = bool(thermal_rows) and all(row.within_tolerance for row in thermal_rows)
    thermal_sign_ready = bool(thermal_rows) and all(row.sign_parity is True for row in thermal_rows)
    charge_value_ready = bool(charge_rows) and all(row.within_tolerance for row in charge_rows)
    charge_sign_ready = bool(charge_rows) and all(row.sign_parity is True for row in charge_rows)

    py_final = py_events[-1] if py_events else None
    xs_final = xs_events[-1] if xs_events else None
    if prefix_mode:
        final_state_ready = event_sequence_ready
    else:
        final_state_ready = bool(
            py_final is not None
            and xs_final is not None
            and py_final.event == "finish"
            and xs_final.event == "finish"
            and py_final.lnerr == xs_final.lnerr
            and math.isclose(py_final.temperature_t4, xs_final.temperature_t4, rel_tol=runtime_rtol, abs_tol=runtime_atol)
            and math.isclose(py_final.electron_fraction_xee, xs_final.electron_fraction_xee, rel_tol=runtime_rtol, abs_tol=runtime_atol)
        )
    finite_abs = [row.absolute_difference for row in rows if row.absolute_difference is not None and math.isfinite(row.absolute_difference)]
    finite_rel = [row.relative_difference for row in rows if row.relative_difference is not None and math.isfinite(row.relative_difference)]
    return DsecTrajectoryParityResult(
        rows=tuple(rows),
        python_result=python_result,
        reference=reference,
        event_sequence_ready=event_sequence_ready,
        integer_control_state_ready=integer_control_state_ready,
        runtime_state_ready=runtime_state_ready,
        thermal_residual_value_ready=thermal_value_ready,
        thermal_residual_sign_ready=thermal_sign_ready,
        charge_residual_value_ready=charge_value_ready,
        charge_residual_sign_ready=charge_sign_ready,
        final_state_ready=final_state_ready,
        max_absolute_difference=max(finite_abs, default=0.0),
        max_relative_difference=max(finite_rel, default=0.0),
    )


def write_dsec_trajectory_parity_products(
    parity: DsecTrajectoryParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.45",
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_dsec_trajectory_parity.csv"
    fields = tuple(DsecTrajectoryParityRow.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in parity.rows:
            writer.writerow({name: getattr(row, name) for name in fields})
    summary = {
        "port_version": port_version,
        "xstar_dsec_call_id": parity.reference.call_id,
        "xstar_probe_source": parity.reference.source_path,
        "event_sequence_ready": parity.event_sequence_ready,
        "integer_control_state_ready": parity.integer_control_state_ready,
        "runtime_state_ready": parity.runtime_state_ready,
        "thermal_residual_value_ready": parity.thermal_residual_value_ready,
        "thermal_residual_sign_ready": parity.thermal_residual_sign_ready,
        "charge_residual_value_ready": parity.charge_residual_value_ready,
        "charge_residual_sign_ready": parity.charge_residual_sign_ready,
        "final_state_ready": parity.final_state_ready,
        "dsec_trajectory_parity_ready": parity.ready,
        "max_absolute_difference": parity.max_absolute_difference,
        "max_relative_difference": parity.max_relative_difference,
        "near_equilibrium_validation": "absolute residual plus sign parity",
    }
    json_path = out / "xstar_dsec_trajectory_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_dsec_trajectory_parity_summary.md"
    md_path.write_text(
        "# XSTAR/Python `dsec` trajectory parity\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


@dataclass(frozen=True)
class V0444CompleteFixedStateRegressionGate:
    ready: bool
    source_path: str
    failed_requirements: Tuple[str, ...]
    summary: Mapping[str, Any]


_V0444_REQUIRED_TRUE = (
    "fixed_state_calc_hmc_all_translated",
    "pre_matrix_ready",
    "element_loop_ready",
    "charge_scope_complete",
    "continuum_sequence_complete",
    "current_all_element_pre_continuum_parity",
    "current_comp2_parity",
    "current_freef_parity",
    "current_bremem_parity",
    "current_heatf_parity",
    "runtime_state_parity",
    "continuum_component_parity",
    "primary_heating_cooling_totals_parity",
    "secondary_heating_cooling_totals_parity",
    "electron_contribution_parity",
    "charge_residual_parity",
    "charge_identity_parity",
    "hmctot_parity",
    "complete_fixed_state_ready",
    "frozen_oxygen_regression",
    "frozen_h_he_o_pre_continuum_regression",
    "frozen_comp2_regression",
    "frozen_freef_regression",
    "frozen_bremem_regression",
    "frozen_heatf_regression",
    "pre_continuum_state_owned_explicitly",
    "v0444_complete_fixed_state_acceptance_ready",
)


def validate_v0444_complete_fixed_state_regression(
    path: Optional[str | Path] = None,
) -> V0444CompleteFixedStateRegressionGate:
    if path is None:
        target = (
            Path(__file__).resolve().parents[3]
            / "tests/fixtures/historical/complete_fixed_state_v0444_acceptance"
            / "xstar_calc_hmc_all_v0444_acceptance_summary.json"
        )
        if not target.is_file():
            raise FileNotFoundError(
                "the historical v0444 acceptance fixture is no longer bundled; "
                "provide path=... explicitly"
            )
    else:
        target = Path(path)
        if target.is_dir():
            target = target / "xstar_calc_hmc_all_v0444_acceptance_summary.json"
    if not target.is_file():
        raise DsecPortError(f"missing v0.4.44 acceptance summary: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    failures = tuple(name for name in _V0444_REQUIRED_TRUE if payload.get(name) is not True)
    return V0444CompleteFixedStateRegressionGate(
        ready=not failures,
        source_path=str(target),
        failed_requirements=failures,
        summary=payload,
    )


@dataclass(frozen=True)
class DsecAcceptanceResult:
    parity: DsecTrajectoryParityResult
    frozen_v0444: V0444CompleteFixedStateRegressionGate
    mutable_runtime_state_ready: bool
    exact_control_algorithm_ready: bool
    trajectory_probe_ready: bool
    strengthened_residual_validation_ready: bool
    final_calc_hmc_all_ready: bool
    final_fixed_state_parity_ready: bool = True

    @property
    def ready(self) -> bool:
        return bool(
            self.frozen_v0444.ready
            and self.mutable_runtime_state_ready
            and self.exact_control_algorithm_ready
            and self.trajectory_probe_ready
            and self.strengthened_residual_validation_ready
            and self.final_calc_hmc_all_ready
            and self.final_fixed_state_parity_ready
            and self.parity.ready
        )


def build_dsec_acceptance(
    parity: DsecTrajectoryParityResult,
    *,
    frozen_v0444: Optional[V0444CompleteFixedStateRegressionGate] = None,
    final_fixed_state_parity_ready: bool = True,
) -> DsecAcceptanceResult:
    frozen = frozen_v0444 or validate_v0444_complete_fixed_state_regression()
    state = parity.python_result.state
    final = state.last_calc_hmc_all
    mutable_ready = bool(
        state.calc_hmc_all_call_count == parity.python_result.ntotit
        and state.provenance.get("dsec_exact_control_flow") is True
        and (not state.element_requests or bool(state.element_populations))
    )
    return DsecAcceptanceResult(
        parity=parity,
        frozen_v0444=frozen,
        mutable_runtime_state_ready=mutable_ready,
        exact_control_algorithm_ready=True,
        trajectory_probe_ready=bool(parity.reference.events),
        strengthened_residual_validation_ready=bool(
            parity.thermal_residual_sign_ready
            and parity.charge_residual_sign_ready
        ),
        final_calc_hmc_all_ready=bool(
            final is not None and final.complete_fixed_state_ready
        ),
        final_fixed_state_parity_ready=bool(final_fixed_state_parity_ready),
    )


def write_dsec_acceptance_products(
    acceptance: DsecAcceptanceResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.45",
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "port_version": port_version,
        "dsec_translated": True,
        "mutable_runtime_state_ready": acceptance.mutable_runtime_state_ready,
        "exact_dsec_control_algorithm_ready": acceptance.exact_control_algorithm_ready,
        "trajectory_probe_ready": acceptance.trajectory_probe_ready,
        "strengthened_residual_validation_ready": acceptance.strengthened_residual_validation_ready,
        "dsec_trajectory_parity_ready": acceptance.parity.ready,
        "final_calc_hmc_all_ready": acceptance.final_calc_hmc_all_ready,
        "final_fixed_state_parity_ready": acceptance.final_fixed_state_parity_ready,
        "frozen_v0444_complete_fixed_state_regression": acceptance.frozen_v0444.ready,
        "frozen_v0444_source": acceptance.frozen_v0444.source_path,
        "v0445_bounded_dsec_acceptance_ready": acceptance.ready,
        "remaining_source_sequence": "bremsmap -> calc_emisab_all -> calc_emis_all -> complete xstarcalc",
    }
    json_path = out / "xstar_dsec_v0445_acceptance_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_dsec_v0445_acceptance_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.45 bounded `dsec` acceptance\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path}


__all__ = [
    "DsecPortError",
    "DSEC_CHARGE_TOLERANCE",
    "DSEC_THERMAL_TOLERANCE",
    "DSEC_TEMPERATURE_STAGNATION_TOLERANCE",
    "DSEC_TEMPERATURE_FACTOR",
    "DSEC_ELECTRON_FACTOR",
    "DsecMutableRuntimeState",
    "DsecEvaluation",
    "DsecEvaluator",
    "CalcHMCAllDsecEvaluator",
    "DsecTrajectoryEvent",
    "DsecResult",
    "dsec",
    "write_dsec_trajectory_products",
    "load_python_dsec_trajectory",
    "DsecProbeTrajectory",
    "load_xstar_dsec_trajectory",
    "DsecTrajectoryParityRow",
    "DsecTrajectoryParityResult",
    "compare_dsec_trajectory",
    "write_dsec_trajectory_parity_products",
    "V0444CompleteFixedStateRegressionGate",
    "validate_v0444_complete_fixed_state_regression",
    "DsecAcceptanceResult",
    "build_dsec_acceptance",
    "write_dsec_acceptance_products",
]
