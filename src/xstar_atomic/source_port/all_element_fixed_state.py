"""Full abundant-element fixed-state ``calc_hmc_all`` planning and gating.

This module begins the post-oxygen Milestone-4 expansion.  It does not port the
continuum leaves.  Instead it builds the exact source element loop from a
captured ``calc_hmc_all`` call, preserves the accepted oxygen call-73 result as
an obligatory regression gate, and records which per-element same-call probes
are available for a future all-element parity run.

XSTAR itself skips elements with ``abel(jk) <= 1e-24``.  Consequently the
source-complete fixed-state element scope is the set of positive-abundance
rows in ``xstar_calc_hmc_all_pre_continuum_elements_probe.csv`` rather than
all element headers present in ``atdb.fits``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .element_equilibrium import EscapeProbabilityContext
from .fortran_numbers import parse_fortran_float
from .local_zone import (
    CalcHMCAllError,
    FixedStateCalcHMCAllResult,
    FixedStateElementRequest,
    calc_hmc_all,
)
from .msolvelucy_initial_state import (
    MSolveLucyInitialPopulationReference,
    MSolveLucyInitialStateError,
    load_msolvelucy_initial_population_reference,
)


class AllElementFixedStateError(CalcHMCAllError):
    """Raised when the captured all-element fixed-state plan is incomplete."""


@dataclass(frozen=True)
class OxygenCall73RegressionGate:
    """Validation of the accepted v0.4.34 oxygen call-73 milestone result."""

    ready: bool
    status: str
    call_id: Optional[int]
    source_path: str
    failed_requirements: Tuple[str, ...] = ()
    observed: Mapping[str, Any] = field(default_factory=dict)


OXYGEN_CALL73_REQUIRED_TRUE_FIELDS: Tuple[str, ...] = (
    "pre_matrix_ready",
    "pre_continuum_state_ready",
    "element_array_ready",
    "global_ion_ready",
    "global_level_primary_ready",
    "global_level_active_ready",
    "global_level_derived_ready",
    "global_level_ready",
    "global_arrays_ready",
    "same_call_matrix_ready",
    "same_call_matrix_topology_ready",
    "same_call_matrix_active_closure_ready",
    "thermal_family_ready",
    "initial_solver_population_ready",
    "final_solver_snapshot_ready",
    "final_solver_same_iteration_ready",
    "final_solver_topology_ready",
    "final_solver_active_population_ready",
    "final_solver_outer_start_ready",
    "final_solver_source_xtot_ready",
    "type53_rate7_cj2_ready",
    "leveltemp_energy_ready",
    "type53_leveltemp_energy_ready",
    "oxygen_reassessment_ready",
    "oxygen_pre_continuum_acceptance_ready",
    "acceptance_gate_ready",
    "parity_ready",
)


def _find_parity_summary(path: str | Path) -> Path:
    root = Path(path)
    if root.is_file():
        return root
    candidates = (
        root / "xstar_calc_hmc_all_pre_continuum_parity_summary.json",
        root / "xstar_o_calc_hmc_all_fixed_state_v0434"
        / "xstar_calc_hmc_all_pre_continuum_parity_summary.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted(root.glob("**/xstar_calc_hmc_all_pre_continuum_parity_summary.json"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise AllElementFixedStateError(
            f"could not find xstar_calc_hmc_all_pre_continuum_parity_summary.json under {root}"
        )
    raise AllElementFixedStateError(
        f"multiple oxygen parity summaries found under {root}; pass the exact file"
    )


def validate_oxygen_call73_regression(
    path: str | Path,
    *,
    required_call_id: int = 73,
) -> OxygenCall73RegressionGate:
    """Require the accepted oxygen call-73 result before all-element work.

    The strict all-family diagnostics are intentionally not required.  The
    frozen milestone is the accepted oxygen pre-continuum gate with zero
    blocking and zero public parity rows outside tolerance.
    """

    summary_path = _find_parity_summary(path)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    failures: List[str] = []
    call_id = payload.get("call_id")
    if call_id is None or int(call_id) != int(required_call_id):
        failures.append(
            f"call_id expected {required_call_id}, observed {call_id}"
        )
    for name in OXYGEN_CALL73_REQUIRED_TRUE_FIELDS:
        if payload.get(name) is not True:
            failures.append(f"{name} is not true")
    for name in ("n_outside_tolerance", "n_blocking_outside_tolerance"):
        if int(payload.get(name, -1)) != 0:
            failures.append(f"{name} expected 0, observed {payload.get(name)}")

    ready = not failures
    return OxygenCall73RegressionGate(
        ready=ready,
        status="ready" if ready else "failed",
        call_id=None if call_id is None else int(call_id),
        source_path=str(summary_path),
        failed_requirements=tuple(failures),
        observed={
            "port_version": payload.get("port_version"),
            "n_rows": payload.get("n_rows"),
            "n_outside_tolerance": payload.get("n_outside_tolerance"),
            "n_blocking_outside_tolerance": payload.get(
                "n_blocking_outside_tolerance"
            ),
            "strict_parity_ready": payload.get("strict_parity_ready"),
            "rate7_cj2_ready": payload.get("rate7_cj2_ready"),
        },
    )


@dataclass(frozen=True)
class AllElementProbeElement:
    """One positive-abundance source element row from the bounded probe."""

    call_id: int
    element_index: int
    element_z: int
    abundance: float
    mml: int
    mmu: int
    xstar_heating: float
    xstar_cooling: float
    xstar_heating2: float
    xstar_cooling2: float


@dataclass(frozen=True)
class AllElementFixedStatePlan:
    """Captured source element loop and detailed-probe coverage."""

    call_id: int
    probe_dir: str
    elements: Tuple[AllElementProbeElement, ...]
    initial_population_references: Mapping[int, MSolveLucyInitialPopulationReference]
    pre_matrix_elements: Tuple[int, ...]
    matrix_elements: Tuple[int, ...]
    final_snapshot_elements: Tuple[int, ...]
    thermal_family_elements: Tuple[int, ...]
    leveltemp_elements: Tuple[int, ...]
    oxygen_regression: OxygenCall73RegressionGate
    abundance_floor: float = 1.0e-24

    @property
    def abundant_element_z(self) -> Tuple[int, ...]:
        return tuple(item.element_z for item in self.elements)

    @property
    def initial_population_elements(self) -> Tuple[int, ...]:
        return tuple(sorted(int(z) for z in self.initial_population_references))

    @property
    def missing_initial_population_elements(self) -> Tuple[int, ...]:
        have = set(self.initial_population_elements)
        return tuple(z for z in self.abundant_element_z if z not in have)

    @property
    def full_detailed_probe_coverage(self) -> bool:
        required = set(self.abundant_element_z)
        families = (
            set(self.pre_matrix_elements),
            set(self.matrix_elements),
            set(self.final_snapshot_elements),
            set(self.thermal_family_elements),
        )
        return bool(required) and all(required <= family for family in families)

    @property
    def execution_scope_ready(self) -> bool:
        return bool(self.elements) and self.oxygen_regression.ready


@dataclass(frozen=True)
class AllElementFixedStateRun:
    """All-element execution plus its source/probe coverage plan."""

    plan: AllElementFixedStatePlan
    result: FixedStateCalcHMCAllResult
    initial_population_policy: str

    @property
    def all_element_execution_ready(self) -> bool:
        return bool(
            self.plan.oxygen_regression.ready
            and self.result.element_loop_ready
            and self.result.pre_matrix_ready
            and self.result.charge_closure_scope_complete
        )

    @property
    def all_element_detailed_parity_probe_ready(self) -> bool:
        return self.plan.full_detailed_probe_coverage



def _read_csv_optional(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _resolve_call_id(rows: Sequence[Mapping[str, str]], requested: Optional[int]) -> int:
    ids = sorted({int(row["calc_hmc_all_call_id"]) for row in rows})
    if not ids:
        raise AllElementFixedStateError("probe contains no calc_hmc_all call ids")
    if requested is None:
        return ids[-1]
    if int(requested) not in ids:
        raise AllElementFixedStateError(
            f"call id {requested} not present in element probe; available={ids}"
        )
    return int(requested)


def _elements_in_rows(rows: Iterable[Mapping[str, str]], call_id: int) -> Tuple[int, ...]:
    result = {
        int(row["element_z"])
        for row in rows
        if int(row["calc_hmc_all_call_id"]) == int(call_id)
        and int(row.get("element_z", 0)) > 0
    }
    return tuple(sorted(result))


def load_all_element_fixed_state_plan(
    probe_dir: str | Path,
    *,
    oxygen_regression_dir: str | Path,
    call_id: Optional[int] = None,
    abundance_floor: float = 1.0e-24,
) -> AllElementFixedStatePlan:
    """Load the source positive-abundance element loop for one XSTAR call."""

    root = Path(probe_dir)
    element_path = root / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv"
    rows = _read_csv_optional(element_path)
    if not rows:
        raise AllElementFixedStateError(f"missing or empty element probe: {element_path}")
    selected_call = _resolve_call_id(rows, call_id)

    elements: List[AllElementProbeElement] = []
    seen_z: set[int] = set()
    for row in rows:
        if int(row["calc_hmc_all_call_id"]) != selected_call:
            continue
        abundance = parse_fortran_float(row["abundance"])
        if abundance <= float(abundance_floor):
            continue
        z = int(row["element_z"])
        if z in seen_z:
            raise AllElementFixedStateError(
                f"duplicate positive-abundance element Z={z} for call {selected_call}"
            )
        seen_z.add(z)
        elements.append(
            AllElementProbeElement(
                call_id=selected_call,
                element_index=int(row["element_index"]),
                element_z=z,
                abundance=float(abundance),
                mml=int(row["mml"]),
                mmu=int(row["mmu"]),
                xstar_heating=parse_fortran_float(row["htt"]),
                xstar_cooling=parse_fortran_float(row["cll"]),
                xstar_heating2=parse_fortran_float(row["htt2"]),
                xstar_cooling2=parse_fortran_float(row["cll2"]),
            )
        )
    elements.sort(key=lambda item: item.element_index)
    if not elements:
        raise AllElementFixedStateError(
            f"call {selected_call} contains no element above abundance floor {abundance_floor}"
        )

    initial_path = root / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv"
    initial_rows = _read_csv_optional(initial_path)
    initial_elements = _elements_in_rows(initial_rows, selected_call)
    initial_refs: Dict[int, MSolveLucyInitialPopulationReference] = {}
    for z in initial_elements:
        try:
            initial_refs[z] = load_msolvelucy_initial_population_reference(
                root, element_z=z, call_id=selected_call
            )
        except MSolveLucyInitialStateError as exc:
            raise AllElementFixedStateError(str(exc)) from exc

    pre_matrix_rows = _read_csv_optional(
        root / "xstar_calc_hmc_element_pre_matrix_probe.csv"
    )
    matrix_rows = _read_csv_optional(root / "xstar_calc_hmc_all_matrix_terms_probe.csv")
    final_rows = _read_csv_optional(
        root / "xstar_calc_hmc_all_msolvelucy_final_population_probe.csv"
    )
    thermal_rows = _read_csv_optional(
        root / "xstar_calc_hmc_all_thermal_data_type_probe.csv"
    )
    leveltemp_rows = _read_csv_optional(
        root / "xstar_calc_hmc_all_leveltemp_energy_probe.csv"
    )

    oxygen_gate = validate_oxygen_call73_regression(oxygen_regression_dir)
    if not oxygen_gate.ready:
        raise AllElementFixedStateError(
            "mandatory oxygen call-73 regression failed: "
            + "; ".join(oxygen_gate.failed_requirements)
        )

    return AllElementFixedStatePlan(
        call_id=selected_call,
        probe_dir=str(root),
        elements=tuple(elements),
        initial_population_references=initial_refs,
        pre_matrix_elements=_elements_in_rows(pre_matrix_rows, selected_call),
        matrix_elements=_elements_in_rows(matrix_rows, selected_call),
        final_snapshot_elements=_elements_in_rows(final_rows, selected_call),
        thermal_family_elements=_elements_in_rows(thermal_rows, selected_call),
        leveltemp_elements=_elements_in_rows(leveltemp_rows, selected_call),
        oxygen_regression=oxygen_gate,
        abundance_floor=float(abundance_floor),
    )


def build_all_element_fixed_state_requests(
    plan: AllElementFixedStatePlan,
    *,
    radiation: Any,
    escape: EscapeProbabilityContext,
    covering_fraction: float,
    turbulent_velocity_km_s: float,
    lfast: int,
    critf: float,
    initial_population_policy: str = "use-available",
    strict_context: bool = True,
) -> Tuple[FixedStateElementRequest, ...]:
    """Build source-order requests for every positive-abundance element.

    ``use-available`` replays exact same-call seeds where captured and leaves
    other elements on the autonomous ``levwkelement`` fallback.  ``require-all``
    is the eventual full-parity mode and fails until the all-element helper has
    captured every element.
    """

    allowed = {"use-available", "require-all", "ignore"}
    if initial_population_policy not in allowed:
        raise AllElementFixedStateError(
            f"invalid initial_population_policy={initial_population_policy!r}; "
            f"expected one of {sorted(allowed)}"
        )
    missing = plan.missing_initial_population_elements
    if initial_population_policy == "require-all" and missing:
        raise AllElementFixedStateError(
            "same-call initial populations are missing for abundant elements: "
            + ",".join(str(z) for z in missing)
        )

    requests: List[FixedStateElementRequest] = []
    for item in plan.elements:
        reference = plan.initial_population_references.get(item.element_z)
        if initial_population_policy == "ignore":
            populations = None
            source = "levwkelement_lte_probe_ignored"
        elif reference is None:
            populations = None
            source = "levwkelement_lte_fallback_missing_same_call_xileve_probe"
        else:
            populations = reference.populations.copy()
            source = "xstar_same_call_xileve_replay"
        requests.append(
            FixedStateElementRequest(
                element_z=item.element_z,
                min_ion_stage=item.mml,
                max_ion_stage=item.mmu,
                abundance=item.abundance,
                radiation=radiation,
                escape=escape,
                covering_fraction=float(covering_fraction),
                turbulent_velocity_km_s=float(turbulent_velocity_km_s),
                lfast=int(lfast),
                critf=float(critf),
                use_source_ion_limits=True,
                initial_populations=populations,
                initial_population_source=source,
                strict_context=bool(strict_context),
            )
        )
    return tuple(requests)


def run_all_element_fixed_state(
    master: Any,
    derived: Any,
    *,
    plan: AllElementFixedStatePlan,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    radiation: Any,
    escape: EscapeProbabilityContext,
    covering_fraction: float = 1.0,
    turbulent_velocity_km_s: float = 0.0,
    pressure: float = 0.0,
    lcdd: int = 1,
    lfast: int = 2,
    critf: float = 1.0e-7,
    initial_population_policy: str = "use-available",
    **calc_kwargs: Any,
) -> AllElementFixedStateRun:
    """Execute the complete positive-abundance element loop before continuum."""

    if not plan.oxygen_regression.ready:
        raise AllElementFixedStateError("oxygen call-73 regression gate is not ready")
    requests = build_all_element_fixed_state_requests(
        plan,
        radiation=radiation,
        escape=escape,
        covering_fraction=covering_fraction,
        turbulent_velocity_km_s=turbulent_velocity_km_s,
        lfast=lfast,
        critf=critf,
        initial_population_policy=initial_population_policy,
    )
    result = calc_hmc_all(
        master,
        derived,
        elements=requests,
        required_element_z=plan.abundant_element_z,
        temperature_k=temperature_k,
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
        pressure=pressure,
        lcdd=lcdd,
        **calc_kwargs,
    )
    result.diagnostics.update(
        {
            "element_scope": "all_positive_abundance_elements_from_xstar_probe",
            "element_scope_probe_call_id": plan.call_id,
            "element_scope_probe_dir": plan.probe_dir,
            "oxygen_call73_regression_ready": plan.oxygen_regression.ready,
            "oxygen_call73_regression_source": plan.oxygen_regression.source_path,
            "all_element_initial_population_policy": initial_population_policy,
            "all_element_initial_population_elements": list(
                plan.initial_population_elements
            ),
            "all_element_missing_initial_population_elements": list(
                plan.missing_initial_population_elements
            ),
            "all_element_detailed_probe_coverage_ready": (
                plan.full_detailed_probe_coverage
            ),
        }
    )
    return AllElementFixedStateRun(
        plan=plan,
        result=result,
        initial_population_policy=initial_population_policy,
    )


def write_all_element_fixed_state_products(
    run: AllElementFixedStateRun,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.43",
    parity: Optional[Any] = None,
) -> Dict[str, Path]:
    """Write source-scope and detailed-probe coverage products."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_calc_hmc_all_all_element_scope.csv"
    fields = (
        "element_index",
        "element_z",
        "abundance",
        "captured_mml",
        "captured_mmu",
        "python_selected_mml",
        "python_selected_mmu",
        "initial_population_probe_present",
        "pre_matrix_probe_present",
        "matrix_probe_present",
        "final_snapshot_probe_present",
        "thermal_family_probe_present",
        "leveltemp_probe_present",
        "initial_population_source",
        "element_solver_ready",
        "initial_population_parity_ready",
        "matrix_topology_ready",
        "matrix_active_closure_ready",
        "active_final_population_ready",
        "active_outer_start_population_ready",
        "source_xtot_ready",
        "thermal_family_parity_ready",
        "milestone_blocking_rows",
        "detailed_parity_ready",
    )
    result_by_z = {
        int(item.request.element_z): item for item in run.result.element_results
    }
    parity_by_z = {
        int(item.get("element_z", 0)): item
        for item in getattr(parity, "all_element_element_readiness", [])
    }
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in run.plan.elements:
            result = result_by_z.get(item.element_z)
            writer.writerow(
                {
                    "element_index": item.element_index,
                    "element_z": item.element_z,
                    "abundance": item.abundance,
                    "captured_mml": item.mml,
                    "captured_mmu": item.mmu,
                    "python_selected_mml": (
                        None if result is None else result.selected_min_ion_stage
                    ),
                    "python_selected_mmu": (
                        None if result is None else result.selected_max_ion_stage
                    ),
                    "initial_population_probe_present": (
                        item.element_z in run.plan.initial_population_elements
                    ),
                    "pre_matrix_probe_present": (
                        item.element_z in run.plan.pre_matrix_elements
                    ),
                    "matrix_probe_present": item.element_z in run.plan.matrix_elements,
                    "final_snapshot_probe_present": (
                        item.element_z in run.plan.final_snapshot_elements
                    ),
                    "thermal_family_probe_present": (
                        item.element_z in run.plan.thermal_family_elements
                    ),
                    "leveltemp_probe_present": (
                        item.element_z in run.plan.leveltemp_elements
                    ),
                    "initial_population_source": (
                        None
                        if result is None
                        else result.request.initial_population_source
                    ),
                    "element_solver_ready": (
                        False
                        if result is None
                        else result.equilibrium.full_element_direct_solve_ready
                    ),
                    "initial_population_parity_ready": parity_by_z.get(item.element_z, {}).get("initial_population_ready"),
                    "matrix_topology_ready": parity_by_z.get(item.element_z, {}).get("matrix_topology_ready"),
                    "matrix_active_closure_ready": parity_by_z.get(item.element_z, {}).get("matrix_active_closure_ready"),
                    "active_final_population_ready": parity_by_z.get(item.element_z, {}).get("active_final_population_ready"),
                    "active_outer_start_population_ready": parity_by_z.get(item.element_z, {}).get("active_outer_start_population_ready"),
                    "source_xtot_ready": parity_by_z.get(item.element_z, {}).get("source_xtot_ready"),
                    "thermal_family_parity_ready": parity_by_z.get(item.element_z, {}).get("thermal_family_ready"),
                    "milestone_blocking_rows": parity_by_z.get(item.element_z, {}).get("n_milestone_blocking_rows"),
                    "detailed_parity_ready": parity_by_z.get(item.element_z, {}).get("detailed_parity_ready"),
                }
            )

    summary = {
        "port_version": port_version,
        "status": "ready" if run.all_element_execution_ready else "failed",
        "call_id": run.plan.call_id,
        "element_scope": "all_positive_abundance_elements_from_xstar_probe",
        "abundance_floor": run.plan.abundance_floor,
        "n_abundant_elements": len(run.plan.elements),
        "abundant_element_z": list(run.plan.abundant_element_z),
        "oxygen_call73_regression_ready": run.plan.oxygen_regression.ready,
        "oxygen_call73_regression_source": run.plan.oxygen_regression.source_path,
        "pre_matrix_ready": run.result.pre_matrix_ready,
        "element_loop_ready": run.result.element_loop_ready,
        "charge_closure_scope_complete": run.result.charge_closure_scope_complete,
        "all_element_execution_ready": run.all_element_execution_ready,
        "initial_population_policy": run.initial_population_policy,
        "initial_population_elements": list(run.plan.initial_population_elements),
        "missing_initial_population_elements": list(
            run.plan.missing_initial_population_elements
        ),
        "pre_matrix_probe_elements": list(run.plan.pre_matrix_elements),
        "matrix_probe_elements": list(run.plan.matrix_elements),
        "final_snapshot_probe_elements": list(run.plan.final_snapshot_elements),
        "thermal_family_probe_elements": list(run.plan.thermal_family_elements),
        "leveltemp_probe_elements": list(run.plan.leveltemp_elements),
        "all_element_detailed_parity_probe_ready": (
            run.all_element_detailed_parity_probe_ready
        ),
        "all_element_pre_continuum_acceptance_ready": getattr(
            parity, "all_element_pre_continuum_acceptance_ready", None
        ),
        "all_element_active_solver_ready": getattr(
            parity, "all_element_active_solver_ready", None
        ),
        "all_element_thermal_ready": getattr(
            parity, "all_element_thermal_ready", None
        ),
        "all_element_element_readiness": getattr(
            parity, "all_element_element_readiness", []
        ),
        "continuum_complete": run.result.continuum.complete,
        "complete_fixed_state_ready": run.result.complete_fixed_state_ready,
        "next_required_probe_mode": "XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0",
        "next_source_sequence": "comp2 -> freef -> bremem -> heatf",
    }
    json_path = out / "xstar_calc_hmc_all_all_element_scope_summary.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    md_path = out / "xstar_calc_hmc_all_all_element_scope_summary.md"
    md_path.write_text(
        "# Full abundant-element fixed-state `calc_hmc_all` scope\n\n"
        f"- Port version: `{port_version}`\n"
        f"- Source call: `{run.plan.call_id}`\n"
        f"- Abundant elements: `{', '.join(map(str, run.plan.abundant_element_z))}`\n"
        f"- Oxygen call-73 regression: `{run.plan.oxygen_regression.ready}`\n"
        f"- Element-loop execution: `{run.result.element_loop_ready}`\n"
        f"- Charge-scope coverage: `{run.result.charge_closure_scope_complete}`\n"
        f"- All-element execution ready: `{run.all_element_execution_ready}`\n"
        f"- Detailed all-element probe coverage: `{run.all_element_detailed_parity_probe_ready}`\n"
        f"- Same-call seed elements: `{', '.join(map(str, run.plan.initial_population_elements)) or 'none'}`\n"
        f"- Missing same-call seed elements: `{', '.join(map(str, run.plan.missing_initial_population_elements)) or 'none'}`\n"
        "\nThe detailed all-element parity probe becomes ready after rerunning the "
        "v0.4.35 helper with `XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0`. The accepted "
        "oxygen call-73 result remains mandatory. Continuum leaves remain deferred.\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


__all__ = [
    "AllElementFixedStateError",
    "OxygenCall73RegressionGate",
    "OXYGEN_CALL73_REQUIRED_TRUE_FIELDS",
    "validate_oxygen_call73_regression",
    "AllElementProbeElement",
    "AllElementFixedStatePlan",
    "AllElementFixedStateRun",
    "load_all_element_fixed_state_plan",
    "build_all_element_fixed_state_requests",
    "run_all_element_fixed_state",
    "write_all_element_fixed_state_products",
]
