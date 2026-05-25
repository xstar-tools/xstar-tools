"""Bounded zone-1 DSEC parity diagnostics for the physical XSTAR gate.

This module is diagnostic-only.  It never changes a production rate, matrix,
population, root-finder branch, or acceptance tolerance.  Original-XSTAR probe
products are external regression oracles and are never used by the ordinary
physical runner.  An optional fail-fast comparison gate may consume those
probe products only when the dedicated zone-1 diagnostic command requests it.
"""
from __future__ import annotations

import copy
import csv
import dataclasses
import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np

from .dsec import DsecCalcHMCAllInputSnapshot, DsecPortError
from .local_zone import FixedStateCalcHMCAllResult, calc_hmc_all

TARGET_CARBON_STAGES = (4, 5, 6)
TARGET_CV_LOCAL_LEVELS = (4, 5, 6, 10, 11, 12, 20)
TARGET_TEMPERATURE_K = 73198.4


@dataclass(frozen=True)
class NumericFingerprint:
    evaluation_index: int
    call_id: int
    name: str
    dtype: str
    shape: str
    count: int
    nonzero_count: int
    finite_count: int
    minimum: float
    maximum: float
    total: float
    total_abs: float
    total_square: float
    weighted_total: float
    first: float
    last: float
    sha256: str


@dataclass(frozen=True)
class ReplayParityRow:
    quantity: str
    first_value: Any
    second_value: Any
    exact_match: bool


@dataclass(frozen=True)
class SameEntryReplayResult:
    evaluation_index: int
    rows: Tuple[ReplayParityRow, ...]
    ready: bool


@dataclass(frozen=True)
class CarbonRateRow:
    source: str
    evaluation_index: int
    call_id: int
    temperature_K: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    ion_stage: int
    preliminary_ion_fraction: float
    preliminary_photoionization_rate: float
    preliminary_recombination_rate: float
    second_pass_photoionization_rate: float
    second_pass_recombination_rate: float
    final_ion_fraction: float


@dataclass(frozen=True)
class MatrixAuditRow:
    source: str
    evaluation_index: int
    call_id: int
    element_z: int
    ion_stage: int
    local_level: int
    record: int
    data_type: int
    rate_type: int
    role: str
    term_index: int
    row: int
    column: int
    idest1: int
    idest2: int
    lower_endpoint: int
    upper_endpoint: int
    escape_factor_in: float
    escape_factor_out: float
    density_scale: float
    ans1: float
    ans2: float
    ans3: float
    ans4: float
    ans5: float
    ans6: float
    aj1: float
    aj2: float
    cj: float
    cj2: float
    population: float
    cooling_contribution: float
    cooling2_contribution: float


@dataclass(frozen=True)
class CoolingComparisonRow:
    evaluation_index: int
    record: int
    term_index: int
    row: int
    python_value: float
    xstar_value: float
    absolute_difference: float
    relative_difference: float
    within_tolerance: bool


class _Accumulator:
    def __init__(self, name: str, dtype: str, call_id: int, evaluation_index: int) -> None:
        self.name = name
        self.dtype = dtype
        self.call_id = int(call_id)
        self.evaluation_index = int(evaluation_index)
        self.count = 0
        self.nonzero = 0
        self.finite = 0
        self.minimum = math.inf
        self.maximum = -math.inf
        self.total = 0.0
        self.total_abs = 0.0
        self.total_square = 0.0
        self.weighted_total = 0.0
        self.first = math.nan
        self.last = math.nan
        self.sha = hashlib.sha256()

    def add(self, value: float | int, *, logical_index: int) -> None:
        x = float(value)
        self.count += 1
        if self.count == 1:
            self.first = x
        self.last = x
        if x != 0.0:
            self.nonzero += 1
        if math.isfinite(x):
            self.finite += 1
            self.minimum = min(self.minimum, x)
            self.maximum = max(self.maximum, x)
            self.total += x
            self.total_abs += abs(x)
            self.total_square += x * x
            self.weighted_total += float(logical_index) * x
        self.sha.update(struct.pack("<q", int(logical_index)))
        if self.dtype.startswith("int"):
            self.sha.update(struct.pack("<q", int(value)))
        else:
            self.sha.update(struct.pack("<d", x))

    def finish(self, shape: Sequence[int]) -> NumericFingerprint:
        return NumericFingerprint(
            evaluation_index=self.evaluation_index,
            call_id=self.call_id,
            name=self.name,
            dtype=self.dtype,
            shape="x".join(str(int(v)) for v in shape),
            count=self.count,
            nonzero_count=self.nonzero,
            finite_count=self.finite,
            minimum=self.minimum if self.finite else math.nan,
            maximum=self.maximum if self.finite else math.nan,
            total=self.total,
            total_abs=self.total_abs,
            total_square=self.total_square,
            weighted_total=self.weighted_total,
            first=self.first,
            last=self.last,
            sha256=self.sha.hexdigest(),
        )


def numeric_fingerprint(
    values: Any,
    *,
    name: str,
    evaluation_index: int,
    call_id: int = 0,
) -> NumericFingerprint:
    array = np.asarray(values)
    dtype = "int64" if np.issubdtype(array.dtype, np.integer) else "float64"
    flat = np.asarray(
        array, dtype=np.int64 if dtype == "int64" else np.float64
    ).ravel(order="F")
    acc = _Accumulator(name, dtype, call_id, evaluation_index)
    for index, value in enumerate(flat, start=1):
        acc.add(int(value) if dtype == "int64" else float(value), logical_index=index)
    return acc.finish(array.shape)


def _text_fingerprint(
    value: Any, *, name: str, evaluation_index: int
) -> NumericFingerprint:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return numeric_fingerprint(
        np.frombuffer(text.encode("utf-8"), dtype=np.uint8),
        name=name,
        evaluation_index=evaluation_index,
    )


def _mapping_values(mapping: Mapping[Any, Any] | None) -> np.ndarray:
    if not mapping:
        return np.zeros((0, 4), dtype=float)
    rows: list[list[float]] = []
    for key, value in sorted(mapping.items(), key=lambda item: repr(item[0])):
        parts = key if isinstance(key, tuple) else (key,)
        numeric = [float(part) for part in parts if isinstance(part, (int, float, np.number))]
        rows.append((numeric + [math.nan, math.nan, math.nan])[:3] + [float(value)])
    return np.asarray(rows, dtype=float)


def _structural_state(value: Any) -> Any:
    """Return a bounded JSON-safe description of non-array mutable state."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.ndarray):
        return {"dtype": str(value.dtype), "shape": list(value.shape)}
    if isinstance(value, Mapping):
        return {
            str(key): _structural_state(item)
            for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
            if not callable(item)
        }
    if isinstance(value, (tuple, list)):
        return [_structural_state(item) for item in value]
    if dataclasses.is_dataclass(value):
        return {
            field.name: _structural_state(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if not callable(getattr(value, field.name))
        }
    if value.__class__.__name__ == "SourceFaithfulUCalc":
        catalog = getattr(value, "catalog", {})
        return {
            "class": value.__class__.__name__,
            "catalog": {
                str(key): {
                    "implementation": getattr(item, "implementation", None),
                    "validation_status": getattr(item, "validation_status", None),
                    "category": getattr(item, "category", None),
                }
                for key, item in sorted(catalog.items())
            },
            "evaluator_keys": sorted(int(key) for key in getattr(value, "_evaluators", {})),
        }
    data = getattr(value, "__dict__", None)
    if isinstance(data, Mapping):
        return {
            "class": value.__class__.__name__,
            "state": {
                str(key): _structural_state(item)
                for key, item in sorted(data.items())
                if not callable(item) and not str(key).startswith("__")
            },
        }
    return {"class": value.__class__.__name__, "repr": repr(value)}


def _collect_numeric_leaves(
    value: Any,
    *,
    prefix: str,
    output: Dict[str, np.ndarray],
    seen: set[int],
    depth: int = 0,
) -> None:
    if value is None or depth > 12:
        return
    if isinstance(value, (bool, int, float, np.number)):
        output[prefix] = np.asarray([value])
        return
    if isinstance(value, np.ndarray):
        if np.issubdtype(value.dtype, np.number):
            output[prefix] = np.asarray(value)
        return
    if isinstance(value, (str, bytes)) or callable(value):
        return
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(value, Mapping):
        for key, item in sorted(value.items(), key=lambda pair: repr(pair[0])):
            _collect_numeric_leaves(
                item,
                prefix=f"{prefix}.{key}",
                output=output,
                seen=seen,
                depth=depth + 1,
            )
        return
    if isinstance(value, (tuple, list)):
        # Homogeneous numeric sequences are one owned array.
        try:
            array = np.asarray(value)
        except Exception:
            array = np.asarray([], dtype=float)
        if array.size and np.issubdtype(array.dtype, np.number):
            output[prefix] = array
            return
        for index, item in enumerate(value):
            _collect_numeric_leaves(
                item,
                prefix=f"{prefix}[{index}]",
                output=output,
                seen=seen,
                depth=depth + 1,
            )
        return
    if dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            _collect_numeric_leaves(
                getattr(value, field.name),
                prefix=f"{prefix}.{field.name}",
                output=output,
                seen=seen,
                depth=depth + 1,
            )
        return
    data = getattr(value, "__dict__", None)
    if isinstance(data, Mapping):
        for key, item in sorted(data.items()):
            if callable(item):
                continue
            _collect_numeric_leaves(
                item,
                prefix=f"{prefix}.{key}",
                output=output,
                seen=seen,
                depth=depth + 1,
            )


def snapshot_fingerprints(
    snapshot: DsecCalcHMCAllInputSnapshot,
) -> Tuple[NumericFingerprint, ...]:
    """Fingerprint every mutable object passed into one ``calc_hmc_all`` call."""
    arrays: Dict[str, np.ndarray] = {
        "runtime_scalars": np.asarray(
            [
                snapshot.temperature_t4,
                snapshot.temperature_k,
                snapshot.electron_fraction_xee,
                snapshot.hydrogen_density_cm3,
                snapshot.pressure,
                snapshot.lcdd,
                snapshot.covering_fraction,
                snapshot.turbulent_velocity_km_s,
                snapshot.critf,
                float(snapshot.source_global_alias_writeback),
            ],
            dtype=float,
        ),
        "required_element_z": np.asarray(snapshot.required_element_z or (), dtype=np.int64),
        "global_level_populations": _mapping_values(snapshot.global_level_populations),
        "global_bilev_values": _mapping_values(snapshot.global_bilev_values),
        "global_rnist_values": _mapping_values(snapshot.global_rnist_values),
        "global_level_index_by_key": _mapping_values(snapshot.global_level_index_by_key),
        "global_xilevg_by_index": np.asarray(
            snapshot.global_xilevg_by_index
            if snapshot.global_xilevg_by_index is not None
            else (),
            dtype=float,
        ),
        "global_bilevg_by_index": np.asarray(
            snapshot.global_bilevg_by_index
            if snapshot.global_bilevg_by_index is not None
            else (),
            dtype=float,
        ),
        "global_rnisg_by_index": np.asarray(
            snapshot.global_rnisg_by_index
            if snapshot.global_rnisg_by_index is not None
            else (),
            dtype=float,
        ),
        "element_requests.abundance": np.asarray(
            [request.abundance for request in snapshot.element_requests], dtype=float
        ),
        "element_requests.min_ion_stage": np.asarray(
            [request.min_ion_stage for request in snapshot.element_requests], dtype=np.int64
        ),
        "element_requests.max_ion_stage": np.asarray(
            [request.max_ion_stage for request in snapshot.element_requests], dtype=np.int64
        ),
    }
    seen: set[int] = set()
    for name, value in (
        ("radiation", snapshot.radiation),
        ("escape", snapshot.escape),
        ("calc_kwargs", snapshot.calc_kwargs),
        ("leveltemp_workspace", snapshot.leveltemp_workspace),
        ("element_requests", snapshot.element_requests),
        ("dispatcher", snapshot.dispatcher_state),
        ("element_solver", snapshot.element_solver_state),
        ("pre_matrix_solver", snapshot.pre_matrix_solver_state),
    ):
        _collect_numeric_leaves(value, prefix=name, output=arrays, seen=seen)

    rows = [
        numeric_fingerprint(
            value,
            name=name,
            evaluation_index=snapshot.evaluation_index,
        )
        for name, value in sorted(arrays.items())
    ]
    # Numeric leaves do not encode labels, ownership provenance, branch names,
    # or dispatcher registration.  Hash those structures separately as bytes.
    for name, value in (
        ("leveltemp_owner_by_column.structure", snapshot.leveltemp_owner_by_column),
        ("element_requests.structure", snapshot.element_requests),
        ("dispatcher.structure", snapshot.dispatcher_state),
        ("element_solver.structure", snapshot.element_solver_state),
        ("pre_matrix_solver.structure", snapshot.pre_matrix_solver_state),
    ):
        rows.append(
            _text_fingerprint(
                _structural_state(value),
                name=name,
                evaluation_index=snapshot.evaluation_index,
            )
        )
    return tuple(sorted(rows, key=lambda row: row.name))


def result_fingerprints(
    result: FixedStateCalcHMCAllResult, *, evaluation_index: int
) -> Mapping[str, Any]:
    values: Dict[str, Any] = {
        "temperature_k": float(result.temperature_k),
        "electron_fraction_xee": float(result.electron_fraction_xee),
        "hydrogen_density_cm3": float(result.hydrogen_density_cm3),
        "neutral_h_density_cm3": float(
            getattr(result, "neutral_h_density_cm3", 0.0)
        ),
        "ionized_h_density_cm3": float(
            getattr(result, "ionized_h_density_cm3", 0.0)
        ),
        "hydrogen_ground_fraction": float(
            getattr(result, "hydrogen_ground_fraction", 0.0)
        ),
        "hydrogen_abundance": float(getattr(result, "hydrogen_abundance", 0.0)),
        "hmctot": float(result.hmctot),
        "elcter": float(result.elcter),
        "httot": float(result.httot),
        "cltot": float(result.cltot),
        "httot2": float(result.httot2),
        "cltot2": float(result.cltot2),
        "global_xilevg": numeric_fingerprint(
            result.global_xilevg_by_index,
            name="global_xilevg",
            evaluation_index=evaluation_index,
        ).sha256,
        "global_bilevg": numeric_fingerprint(
            result.global_bilevg_by_index,
            name="global_bilevg",
            evaluation_index=evaluation_index,
        ).sha256,
        "global_rnisg": numeric_fingerprint(
            result.global_rnisg_by_index,
            name="global_rnisg",
            evaluation_index=evaluation_index,
        ).sha256,
    }
    for key, value in sorted(result.ion_fractions.items()):
        values[f"ion_fraction_Z{key[0]}_stage{key[1]}"] = float(value)
    for item in result.element_results:
        solve = item.equilibrium.solve
        if solve is not None:
            values[f"Z{item.request.element_z}_population_sha256"] = numeric_fingerprint(
                solve.populations,
                name=f"Z{item.request.element_z}_populations",
                evaluation_index=evaluation_index,
            ).sha256
    return values


def replay_same_entry_state(
    master: Any,
    derived: Any,
    snapshot: DsecCalcHMCAllInputSnapshot,
) -> SameEntryReplayResult:
    """Execute two isolated calls from one identical pre-call snapshot."""
    if not snapshot.element_requests:
        raise DsecPortError(
            "snapshot lacks element_requests required for deterministic replay"
        )

    def run_once() -> FixedStateCalcHMCAllResult:
        kwargs = {
            key: copy.deepcopy(value) for key, value in snapshot.calc_kwargs.items()
        }
        if snapshot.dispatcher_state is not None:
            kwargs["dispatcher"] = copy.deepcopy(snapshot.dispatcher_state)
        if snapshot.element_solver_state is not None:
            kwargs["element_solver"] = copy.deepcopy(snapshot.element_solver_state)
        if snapshot.pre_matrix_solver_state is not None:
            kwargs["pre_matrix_solver"] = copy.deepcopy(
                snapshot.pre_matrix_solver_state
            )
        return calc_hmc_all(
            master,
            derived,
            elements=tuple(copy.deepcopy(snapshot.element_requests)),
            temperature_k=float(snapshot.temperature_k),
            hydrogen_density_cm3=float(snapshot.hydrogen_density_cm3),
            electron_fraction_xee=float(snapshot.electron_fraction_xee),
            pressure=float(snapshot.pressure),
            lcdd=int(snapshot.lcdd),
            required_element_z=snapshot.required_element_z,
            initial_leveltemp_workspace=copy.deepcopy(snapshot.leveltemp_workspace),
            initial_leveltemp_owner_by_column=copy.deepcopy(
                snapshot.leveltemp_owner_by_column
            ),
            initial_global_xilevg_by_index=None
            if snapshot.global_xilevg_by_index is None
            else np.array(snapshot.global_xilevg_by_index, copy=True),
            initial_global_bilevg_by_index=None
            if snapshot.global_bilevg_by_index is None
            else np.array(snapshot.global_bilevg_by_index, copy=True),
            initial_global_rnisg_by_index=None
            if snapshot.global_rnisg_by_index is None
            else np.array(snapshot.global_rnisg_by_index, copy=True),
            source_global_alias_writeback=bool(
                snapshot.source_global_alias_writeback
            ),
            **kwargs,
        )

    first = result_fingerprints(run_once(), evaluation_index=snapshot.evaluation_index)
    second = result_fingerprints(run_once(), evaluation_index=snapshot.evaluation_index)
    rows = tuple(
        ReplayParityRow(
            quantity=key,
            first_value=first.get(key),
            second_value=second.get(key),
            exact_match=first.get(key) == second.get(key),
        )
        for key in sorted(set(first) | set(second))
    )
    return SameEntryReplayResult(
        evaluation_index=snapshot.evaluation_index,
        rows=rows,
        ready=all(row.exact_match for row in rows),
    )


def extract_python_carbon_rates(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> Tuple[CarbonRateRow, ...]:
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None:
        return ()
    return tuple(
        CarbonRateRow(
            source="python",
            evaluation_index=int(evaluation_index),
            call_id=0,
            temperature_K=float(result.temperature_k),
            electron_fraction_xee=float(result.electron_fraction_xee),
            hydrogen_density_cm3=float(result.hydrogen_density_cm3),
            ion_stage=stage,
            preliminary_ion_fraction=float(
                result.preliminary_ion_fractions.get((6, stage), 0.0)
            ),
            preliminary_photoionization_rate=float(
                result.preliminary_pirt.get((6, stage), 0.0)
            ),
            preliminary_recombination_rate=float(
                result.preliminary_rrrt.get((6, stage), 0.0)
            ),
            second_pass_photoionization_rate=float(
                carbon.second_pass_pirt.get(stage, 0.0)
            ),
            second_pass_recombination_rate=float(
                carbon.second_pass_rrrt.get(stage, 0.0)
            ),
            final_ion_fraction=float(result.ion_fractions.get((6, stage), 0.0)),
        )
        for stage in TARGET_CARBON_STAGES
    )


def _format_float_sequence(values: Sequence[float]) -> str:
    return ";".join(f"{float(value):.17e}" for value in values)


def extract_python_civ_preliminary_records(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return every selected C IV record from the preliminary rate pass."""
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None:
        return ()
    rates = carbon.calc_ion_rates.get(4)
    if rates is None:
        return ()
    output: list[dict[str, Any]] = []
    for row in rates.contributions:
        diagnostics = dict(row.diagnostics or {})
        output.append(
            {
                "source": "python",
                "evaluation_index": int(evaluation_index),
                "call_id": 0,
                "element_z": 6,
                "ion_stage": 4,
                "ion_index": int(rates.ion_index),
                "record": int(row.record),
                "data_type": int(row.data_type),
                "rate_type": int(row.rate_type),
                "status": str(row.status),
                "parent_record": int(row.parent_record),
                "parent_threshold_ev": float(row.parent_threshold_ev),
                "shell_thresholds_ev": _format_float_sequence(row.shell_thresholds_ev),
                "shell_d_values": _format_float_sequence(row.shell_d_values),
                "final_effective_threshold_ev": float(row.effective_threshold_ev),
                "final_effective_d": float(row.effective_d),
                "bkhsgo_threshold_ev": float(row.bkhsgo_threshold_ev),
                "bkhsgo_effective_d": float(row.effective_d),
                "phintfo_threshold_ev": float(row.phintfo_threshold_ev),
                "phintfo_effective_d": float(row.effective_d),
                "ans1": float(row.ans1),
                "ans2": float(row.ans2),
                "ans3": float(row.ans3),
                "ans4": float(row.ans4),
                "ans5": float(row.ans5),
                "ans6": float(row.ans6),
                "pirti_before": float(row.pirti_before),
                "pirti_contribution": float(row.added_to_pirti),
                "pirti_after": float(row.pirti_after),
                "rrrti_before": float(row.rrrti_before),
                "rrrti_contribution": float(row.added_to_rrrti),
                "rrrti_after": float(row.rrrti_after),
                "idest1": int(row.idest1),
                "idest2": int(row.idest2),
                "type59_parameter_layout": str(
                    diagnostics.get("type59_parameter_layout", "")
                ),
                "type59_threshold_ev": float(
                    diagnostics.get("type59_threshold_ev", math.nan)
                ),
                "type59_e0_ev": float(
                    diagnostics.get("type59_e0_ev", math.nan)
                ),
                "type59_s0": float(diagnostics.get("type59_s0", math.nan)),
                "type59_ya": float(diagnostics.get("type59_ya", math.nan)),
                "type59_pp": float(diagnostics.get("type59_pp", math.nan)),
                "type59_yw": float(diagnostics.get("type59_yw", math.nan)),
                "type59_l2": int(diagnostics.get("type59_l2", 0)),
                "type59_parent_offset": int(
                    diagnostics.get("type59_parent_offset", 0)
                ),
                "type59_idest3": int(diagnostics.get("type59_idest3", 0)),
                "type59_idest4": int(diagnostics.get("type59_idest4", 0)),
                "type59_reverse_zero_pre_swap_fields": str(
                    diagnostics.get("type59_reverse_zero_pre_swap_fields", "")
                ),
                "type59_reverse_zero_post_swap_fields": str(
                    diagnostics.get("type59_reverse_zero_post_swap_fields", "")
                ),
                "type59_reverse_zero_applied": bool(
                    diagnostics.get("type59_reverse_zero_applied", False)
                ),
                "type59_sigma_max_cm2": float(
                    diagnostics.get("type59_sigma_max_cm2", math.nan)
                ),
            }
        )
    return tuple(output)


def extract_python_carbon_topology(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None:
        return ()
    preliminary_civ = float(carbon.preliminary_ion_fractions.get(4, 0.0))
    selected_min = int(carbon.selected_min_ion_stage)
    selected_max = int(carbon.selected_max_ion_stage)
    return (
        {
            "source": "python",
            "evaluation_index": int(evaluation_index),
            "element_z": 6,
            "critf": float(carbon.request.critf),
            "civ_preliminary_fraction": preliminary_civ,
            "selected_min_ion_stage": selected_min,
            "selected_max_ion_stage": selected_max,
            "civ_retained": bool(selected_min <= 4 <= selected_max),
            "compact_dimension": int(carbon.equilibrium.assembly.basis.n_rows),
            "normalization_row": int(carbon.equilibrium.assembly.basis.normalization_row),
        },
    )


def extract_python_carbon_initial_populations(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None:
        return ()
    assembly = carbon.equilibrium.assembly
    values = np.asarray(assembly.initial_populations, dtype=float)
    return tuple(
        {
            "source": "python",
            "evaluation_index": int(evaluation_index),
            "compact_dimension": int(assembly.basis.n_rows),
            "compact_index": index,
            "population": float(values[index]),
        }
        for index in range(1, int(assembly.basis.n_rows) + 1)
    )


def extract_python_carbon_state_path(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return the diagnostic-only source-ordered carbon level path."""
    trace = getattr(result, "carbon_state_path", {}) or {}
    return tuple(
        {"evaluation_index": int(evaluation_index), **dict(row)}
        for row in trace.get("levels", ())
    )


def extract_python_carbon_stage_totals(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return source-ordered C III--C VI totals around ``msolvelucy``."""
    trace = getattr(result, "carbon_state_path", {}) or {}
    return tuple(
        {"evaluation_index": int(evaluation_index), **dict(row)}
        for row in trace.get("stage_totals", ())
    )



def extract_python_carbon_msolvelucy_inner_eval11_outer1(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return v0.4.94 inner-Lucy audit rows for carbon evaluation 11.

    This is diagnostic-only.  It observes the first condensed superlevel solve
    where v0.4.91 localized the C II-continuum / C III-ground shared row drift.
    The rows deliberately keep source-order term indices and compact-row
    identities so the analyzer can separate matrix/RHS/solve/scatter and
    normalization-denominator causes.
    """
    if int(evaluation_index) != 11:
        return ()
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None or carbon.equilibrium.solve is None:
        return ()
    assembly = carbon.equilibrium.assembly
    solve = carbon.equilibrium.solve
    trace = solve.trace
    if trace is None:
        return ()
    basis = assembly.basis
    if basis.n_rows < 1:
        return ()
    shared_compact = 1
    shared_row = basis.row(shared_compact)
    shared_super = int(shared_row.superlevel)
    shared_ion_counter = int(shared_row.ion_counter)
    shared_stage = int(basis.ion_stage[shared_compact])
    selected_compact: set[int] = {shared_compact}
    for row in basis.rows:
        for role in row.roles:
            if int(role.get("ion_stage", 0)) == 3 and int(role.get("local_level", 0)) <= 7:
                selected_compact.add(int(row.compact_index))
    rr_by_compact: dict[int, float] = {}
    outer_rows = [r for r in trace.outer_level_rows if int(r.get("outer_iteration", 0)) == 1]
    for r in outer_rows:
        rr_by_compact[int(r["compact_index"])] = float(r.get("rr", 0.0))
    rows: list[dict[str, Any]] = []
    base = {
        "source": "python",
        "evaluation_index": int(evaluation_index),
        "element_z": 6,
        "outer_iteration": 1,
        "physical_identity": "C_II_continuum_equals_C_III_ground",
        "shared_compact_index": shared_compact,
        "shared_superlevel": shared_super,
        "shared_ion_counter": shared_ion_counter,
        "shared_ion_stage": shared_stage,
    }
    # Superlevel mapping for the shared row and neighboring C III rows.
    for compact_index in sorted(selected_compact):
        brow = basis.row(compact_index)
        roles = ";".join(
            f"ion_stage={int(role.get('ion_stage',0))}:local_level={int(role.get('local_level',0))}:global_index={int(role.get('global_index',0))}"
            for role in brow.roles
        )
        row = dict(base)
        row.update({
            "row_kind": "superlevel_mapping",
            "compact_index": compact_index,
            "superlevel": int(brow.superlevel),
            "ion_counter": int(brow.ion_counter),
            "ion_stage": int(basis.ion_stage[compact_index]),
            "roles": roles,
            "population": float(assembly.initial_populations[compact_index]),
        })
        rows.append(row)
    # Condensed source/population vector p before solve and solved
    # superlevel populations after leqt2f.  Keep all superlevels in v0.4.94.
    for r in trace.superlevel_rows:
        if int(r.get("outer_iteration", 0)) != 1:
            continue
        sp = int(r.get("superlevel", 0))
        row = dict(base)
        row.update({
            "row_kind": "condensed_rhs_source_before_solve",
            "superlevel": sp,
            "population_before_condensed_solve": float(r.get("population_before_condensed_solve", 0.0)),
        })
        rows.append(row)
        # Backward-compatible compact row for the focused shared and nearby rows.
        if sp == shared_super or sp <= min(shared_super + 4, basis.n_superlevels):
            row = dict(base)
            row.update({
                "row_kind": "condensed_rhs_and_solution",
                "superlevel": sp,
                "population_before_condensed_solve": float(r.get("population_before_condensed_solve", 0.0)),
                "population_after_condensed_solve": float(r.get("population_after_condensed_solve", 0.0)),
            })
            rows.append(row)
        row = dict(base)
        row.update({
            "row_kind": "leqt2f_output_solution",
            "superlevel": sp,
            "population_after_condensed_solve": float(r.get("population_after_condensed_solve", 0.0)),
        })
        rows.append(row)
    # Full condensed matrix before the conservation row is injected.
    # v0.4.94 keeps the old shared-row kind for continuity and adds full
    # matrix/leqt2f input rows with row-kind-specific comparator keys.
    for r in trace.condensed_matrix_rows:
        if int(r.get("outer_iteration", 0)) != 1:
            continue
        row_super = int(r.get("row_superlevel", 0))
        col_super = int(r.get("column_superlevel", 0))
        raw_value = float(r.get("raw_matrix_value", 0.0))
        leqt_value = float(r.get("normalized_matrix_value", 0.0))
        row = dict(base)
        row.update({
            "row_kind": "condensed_matrix_full_before_solve",
            "row_superlevel": row_super,
            "column_superlevel": col_super,
            "raw_matrix_value": raw_value,
        })
        rows.append(row)
        if row_super == shared_super:
            row = dict(base)
            row.update({
                "row_kind": "condensed_matrix_row_before_solve",
                "row_superlevel": row_super,
                "column_superlevel": col_super,
                "raw_matrix_value": raw_value,
                "normalized_matrix_value": leqt_value,
            })
            rows.append(row)
        row = dict(base)
        row.update({
            "row_kind": "leqt2f_input_matrix",
            "row_superlevel": row_super,
            "column_superlevel": col_super,
            "normalized_matrix_value": leqt_value,
        })
        rows.append(row)
    # leqt2f receives bmatsup as RHS, not the p-start vector.
    # Source sets bmatsup(:)=0 and bmatsup(nspmx)=1 after replacing the
    # conservation row.
    for sp in range(1, int(basis.n_superlevels) + 1):
        row = dict(base)
        row.update({
            "row_kind": "leqt2f_input_rhs",
            "superlevel": sp,
            "population_before_condensed_solve": 1.0 if sp == int(basis.n_superlevels) else 0.0,
        })
        rows.append(row)
    # Expansion/scatter back to compact rows from rr * p(superlevel).
    for r in outer_rows:
        ci = int(r.get("compact_index", 0))
        if ci not in selected_compact:
            continue
        row = dict(base)
        row.update({
            "row_kind": "expansion_scatter_after_condensed",
            "compact_index": ci,
            "superlevel": int(r.get("superlevel", 0)),
            "ion_counter": int(r.get("ion_counter", 0)),
            "ion_stage": int(basis.ion_stage[ci]),
            "rr": float(r.get("rr", 0.0)),
            "population_outer_start": float(r.get("population_outer_start", 0.0)),
            "population_after_condensed": float(r.get("population_after_condensed", 0.0)),
            "population_after_fixed_point": float(r.get("population_after_fixed_point", 0.0)),
        })
        rows.append(row)
    # Normalization denominator xm before phase 60 can be reconstructed from
    # the fixed-point numerator/denominator before source normalization.
    fixed1 = [r for r in trace.fixed_point_rows if int(r.get("outer_iteration",0)) == 1 and int(r.get("fixed_iteration",0)) == 1]
    xm = 0.0
    for r in fixed1:
        denom = float(r.get("ril", 0.0)) + float(r.get("riu", 0.0)) + 1.0e-24
        xm += (float(r.get("rli", 0.0)) + float(r.get("rui", 0.0))) / denom
    row = dict(base)
    row.update({"row_kind": "normalization_denominator_before_phase60", "xm_before_normalization": float(xm), "normalization_denominator": float(1.0e-24 + xm)})
    rows.append(row)
    for r in fixed1:
        ci = int(r.get("compact_index",0))
        if ci not in selected_compact:
            continue
        denom = float(r.get("ril", 0.0)) + float(r.get("riu", 0.0)) + 1.0e-24
        unnormalized = (float(r.get("rli", 0.0)) + float(r.get("rui", 0.0))) / denom
        row = dict(base)
        row.update({
            "row_kind": "fixed_point_row_before_after_normalization",
            "compact_index": ci,
            "superlevel": int(r.get("superlevel", 0)),
            "ion_counter": int(r.get("ion_counter", 0)),
            "ion_stage": int(basis.ion_stage[ci]),
            "population_before": float(r.get("population_before", 0.0)),
            "riu": float(r.get("riu", 0.0)),
            "rui": float(r.get("rui", 0.0)),
            "ril": float(r.get("ril", 0.0)),
            "rli": float(r.get("rli", 0.0)),
            "population_unnormalized": float(unnormalized),
            "population_after": float(r.get("population_after", 0.0)),
            "xm_before_normalization": float(xm),
        })
        rows.append(row)
    # Ordered dominant contributions to the shared superlevel condensed row.
    contributions: list[dict[str, Any]] = []
    nsup = basis.nsup[1:]
    for term_index, term in enumerate(assembly.terms, start=1):
        mm = min(basis.n_rows, int(term.row)) - 1
        nn = min(basis.n_rows, int(term.column)) - 1
        spm = int(nsup[mm])
        spn = int(nsup[nn])
        if spm != shared_super or spm == spn or spm <= 0 or spn <= 0:
            continue
        if not (abs(float(term.aj1)) > 1.0e-48 or abs(float(term.aj2)) > 1.0e-48):
            continue
        rr_mm = rr_by_compact.get(mm + 1, 1.0)
        rr_nn = rr_by_compact.get(nn + 1, 1.0)
        offdiag = float(term.aj1) * rr_nn
        diag = -float(term.aj2) * rr_mm
        contributions.append({
            "term_index": term_index,
            "source_record": int(getattr(term, "record", 0)),
            "rate_type": int(getattr(term, "rate_type", 0)),
            "data_type": int(getattr(term, "data_type", 0)),
            "source_row": int(term.row),
            "source_column": int(term.column),
            "row_superlevel": spm,
            "column_superlevel": spn,
            "aj1": float(term.aj1),
            "aj2": float(term.aj2),
            "rr_mm": float(rr_mm),
            "rr_nn": float(rr_nn),
            "offdiag_contribution": offdiag,
            "diag_contribution": diag,
            "importance": abs(offdiag) + abs(diag),
        })
    contributions.sort(key=lambda item: (-float(item["importance"]), int(item["term_index"])))
    for item in contributions[:80]:
        row = dict(base)
        row.update({"row_kind": "ordered_dominant_matrix_contribution", **item})
        rows.append(row)
    return tuple(rows)


def extract_python_carbon_alias_boundaries(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return lower-continuum/next-ground alias values after global writeback."""
    trace = getattr(result, "carbon_state_path", {}) or {}
    return tuple(
        {"evaluation_index": int(evaluation_index), **dict(row)}
        for row in trace.get("aliases", ())
    )


def extract_python_hydrogen_state_path(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return all diagnostic-only hydrogen state-history rows.

    v0.4.86/v0.4.87 emitted only the live H I/H II entry scalar row.
    v0.4.88 keeps that row and, when the diagnostic runner enabled the H trace,
    adds H global mapping, compact solve path, final ``xii`` totals, and
    writeback rows for every DSEC evaluation.
    """
    trace = getattr(result, "carbon_state_path", {}) or {}
    rows = list(trace.get("hydrogen_history", ())) or list(trace.get("hydrogen", ()))
    if not rows:
        rows = [
            {
                "source": "python",
                "phase_code": 10,
                "phase": "calc_hmc_all_entry_hydrogen",
                "element_z": 1,
                "ion_stage": 1,
                "hydrogen_ground_fraction": float(result.hydrogen_ground_fraction),
                "hydrogen_abundance": float(result.hydrogen_abundance),
                "hydrogen_density_cm3": float(result.hydrogen_density_cm3),
                "neutral_h_density_cm3": float(result.neutral_h_density_cm3),
                "ionized_h_density_cm3": float(result.ionized_h_density_cm3),
                "population": float(result.hydrogen_ground_fraction),
            }
        ]
    return tuple(
        {"evaluation_index": int(evaluation_index), **dict(row)}
        for row in rows
    )


def extract_python_electron_fraction_path(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return element-by-element electron-fraction contribution history."""
    trace = getattr(result, "carbon_state_path", {}) or {}
    return tuple(
        {"evaluation_index": int(evaluation_index), **dict(row)}
        for row in trace.get("electron_history", ())
    )


def extract_python_carbon_stage_correlation(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    """Return lightweight C phase-20/120 stage totals for all-eval correlation."""
    trace = getattr(result, "carbon_state_path", {}) or {}
    return tuple(
        {"evaluation_index": int(evaluation_index), **dict(row)}
        for row in trace.get("carbon_correlation_stage_totals", ())
    )


def extract_python_carbon_normalization_row(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None:
        return ()
    solve = carbon.equilibrium.solve
    trace = None if solve is None else solve.trace
    if trace is None or not trace.condensed_matrix_rows:
        return ()
    first_outer = min(int(row["outer_iteration"]) for row in trace.condensed_matrix_rows)
    rows = [
        row for row in trace.condensed_matrix_rows
        if int(row["outer_iteration"]) == first_outer
    ]
    dimension = max(int(row["row_superlevel"]) for row in rows)
    return tuple(
        {
            "source": "python",
            "evaluation_index": int(evaluation_index),
            "outer_iteration": first_outer,
            "condensed_dimension": dimension,
            "normalization_row": dimension,
            "column": int(row["column_superlevel"]),
            "matrix_value": float(row["normalized_matrix_value"]),
            "rhs_value": 1.0,
        }
        for row in rows
        if int(row["row_superlevel"]) == dimension
    )


def extract_python_cv_level_populations(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> tuple[dict[str, Any], ...]:
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None or carbon.equilibrium.solve is None:
        return ()
    block = next(
        (
            item for item in carbon.equilibrium.assembly.basis.blocks
            if int(item.ion_stage) == 5
        ),
        None,
    )
    if block is None:
        return ()
    populations = np.asarray(carbon.equilibrium.solve.populations, dtype=float)
    output: list[dict[str, Any]] = []
    for local_level in TARGET_CV_LOCAL_LEVELS:
        if local_level > int(block.nlev):
            continue
        compact_index = int(block.compact_index(local_level))
        output.append(
            {
                "source": "python",
                "evaluation_index": int(evaluation_index),
                "element_z": 6,
                "ion_stage": 5,
                "ion_index": int(block.ion_index),
                "local_level": int(local_level),
                "compact_index": compact_index,
                "population": float(populations[compact_index - 1]),
            }
        )
    return tuple(output)


def carbon_cooling_logical_rows(
    result: FixedStateCalcHMCAllResult, *, evaluation_index: int
) -> list[dict[str, Any]]:
    """Return fixed-state carbon diagonal terms keyed by physical identity."""
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None or carbon.equilibrium.solve is None:
        return []
    populations = np.asarray(carbon.equilibrium.solve.populations, dtype=float)
    rows: list[dict[str, Any]] = []
    for term in carbon.equilibrium.assembly.terms:
        if int(term.row) != int(term.column):
            continue
        population = (
            float(populations[int(term.row) - 1])
            if 1 <= int(term.row) <= populations.size
            else 0.0
        )
        rows.append(
            {
                "source": "python",
                "evaluation_index": int(evaluation_index),
                "element_z": 6,
                "ion_stage": int(term.ion_stage),
                "record": int(term.record),
                "data_type": int(term.data_type),
                "rate_type": int(term.rate_type),
                "role": str(term.role),
                "idest1": int(term.idest1),
                "idest2": int(term.idest2),
                "lower_endpoint": int(term.lower_endpoint),
                "upper_endpoint": int(term.upper_endpoint),
                "population": population,
                "cj": float(term.cj),
                "cj2": float(term.cj2),
                "cooling_contribution": population * float(term.cj),
                "cooling2_contribution": population * float(term.cj2),
            }
        )
    return rows


def extract_python_cv_matrix_audit(
    result: FixedStateCalcHMCAllResult,
    *,
    evaluation_index: int,
) -> Tuple[MatrixAuditRow, ...]:
    """Return every C V term touching the requested local levels.

    ``assembly.record_results`` preserves the raw ``ucalc`` outputs and the
    two escape factors.  ``assembly.terms`` preserves all four literal matrix
    insertions and their density-scaled heating/cooling coefficients.
    """
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None or carbon.equilibrium.solve is None:
        return ()
    assembly = carbon.equilibrium.assembly
    populations = np.asarray(carbon.equilibrium.solve.populations, dtype=float)
    records: Dict[int, Mapping[str, Any]] = {}
    for row in assembly.record_results:
        try:
            record = int(row.get("record", 0))
            stage = int(row.get("ion_stage", 0))
        except (TypeError, ValueError):
            continue
        if record > 0 and stage == 5:
            records[record] = row

    output: list[MatrixAuditRow] = []
    targets = set(TARGET_CV_LOCAL_LEVELS)
    for term in assembly.terms:
        if int(term.ion_stage) != 5:
            continue
        touched = sorted(
            targets.intersection({int(term.idest1), int(term.idest2)})
        )
        if not touched:
            continue
        source = records.get(int(term.record), {})
        population = (
            float(populations[int(term.row) - 1])
            if 1 <= int(term.row) <= populations.size
            else 0.0
        )
        for local_level in touched:
            output.append(
                MatrixAuditRow(
                    source="python",
                    evaluation_index=int(evaluation_index),
                    call_id=0,
                    element_z=6,
                    ion_stage=5,
                    local_level=local_level,
                    record=int(term.record),
                    data_type=int(term.data_type),
                    rate_type=int(term.rate_type),
                    role=str(term.role),
                    term_index=int(term.term_index),
                    row=int(term.row),
                    column=int(term.column),
                    idest1=int(term.idest1),
                    idest2=int(term.idest2),
                    lower_endpoint=int(term.lower_endpoint),
                    upper_endpoint=int(term.upper_endpoint),
                    escape_factor_in=float(source.get("escape_factor_in", math.nan)),
                    escape_factor_out=float(source.get("escape_factor_out", math.nan)),
                    density_scale=float(source.get("density_scale", result.hydrogen_density_cm3)),
                    ans1=float(source.get("ans1_after_calc_hmc_ion_filter", source.get("ans1", math.nan))),
                    ans2=float(source.get("ans2_after_calc_hmc_ion_filter", source.get("ans2", math.nan))),
                    ans3=float(source.get("ans3", math.nan)),
                    ans4=float(source.get("ans4", math.nan)),
                    ans5=float(source.get("ans5", math.nan)),
                    ans6=float(source.get("ans6", math.nan)),
                    aj1=float(term.aj1),
                    aj2=float(term.aj2),
                    cj=float(term.cj),
                    cj2=float(term.cj2),
                    population=population,
                    cooling_contribution=population * float(term.cj),
                    cooling2_contribution=population * float(term.cj2),
                )
            )
    return tuple(output)


def carbon_cooling_rows(
    result: FixedStateCalcHMCAllResult, *, evaluation_index: int
) -> list[dict[str, Any]]:
    carbon = next(
        (item for item in result.element_results if int(item.request.element_z) == 6),
        None,
    )
    if carbon is None or carbon.equilibrium.solve is None:
        return []
    populations = np.asarray(carbon.equilibrium.solve.populations, dtype=float)
    rows: list[dict[str, Any]] = []
    for term in carbon.equilibrium.assembly.terms:
        if int(term.row) != int(term.column):
            continue
        population = (
            float(populations[int(term.row) - 1])
            if 1 <= int(term.row) <= populations.size
            else 0.0
        )
        rows.append(
            {
                "evaluation_index": int(evaluation_index),
                "record": int(term.record),
                "term_index": int(term.term_index),
                "row": int(term.row),
                "data_type": int(term.data_type),
                "rate_type": int(term.rate_type),
                "population": population,
                "cj": float(term.cj),
                "cj2": float(term.cj2),
                "cooling_contribution": population * float(term.cj),
                "cooling2_contribution": population * float(term.cj2),
            }
        )
    return rows


def compare_cooling_terms(
    python_rows: Sequence[Mapping[str, Any]],
    xstar_rows: Sequence[Mapping[str, Any]],
    *,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
) -> Tuple[CoolingComparisonRow, ...]:
    def key(row: Mapping[str, Any]) -> tuple[int, int, int, int]:
        return (
            int(row["evaluation_index"]),
            int(row["record"]),
            int(row["term_index"]),
            int(row["row"]),
        )

    py = {key(row): float(row["cooling_contribution"]) for row in python_rows}
    xs = {key(row): float(row["cooling_contribution"]) for row in xstar_rows}
    output: list[CoolingComparisonRow] = []
    for item in sorted(set(py) | set(xs)):
        pv = py.get(item, 0.0)
        xv = xs.get(item, 0.0)
        diff = abs(pv - xv)
        scale = max(abs(pv), abs(xv), atol)
        output.append(
            CoolingComparisonRow(
                evaluation_index=item[0],
                record=item[1],
                term_index=item[2],
                row=item[3],
                python_value=pv,
                xstar_value=xv,
                absolute_difference=diff,
                relative_difference=diff / scale,
                within_tolerance=bool(diff <= atol + rtol * abs(xv)),
            )
        )
    return tuple(output)


def enforce_cooling_gate(rows: Sequence[CoolingComparisonRow]) -> None:
    failed = [row for row in rows if not row.within_tolerance]
    if failed:
        first = failed[0]
        raise DsecPortError(
            "zone-1 carbon cooling gate failed before the thermal root finder "
            "could continue: "
            f"evaluation={first.evaluation_index} record={first.record} "
            f"term={first.term_index} python={first.python_value:.17e} "
            f"xstar={first.xstar_value:.17e}"
        )


def _write_rows(path: Path, rows: Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    dictionaries = [
        asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row)
        for row in rows
    ]
    fields: list[str] = []
    for row in dictionaries:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dictionaries)


def write_zone1_python_diagnostic_products(
    *,
    snapshots: Sequence[DsecCalcHMCAllInputSnapshot],
    evaluations: Sequence[Any],
    master: Any,
    derived: Any,
    out_dir: str | Path,
    target_temperature_k: float = TARGET_TEMPERATURE_K,
    target_result: FixedStateCalcHMCAllResult | None = None,
    target_metadata: Mapping[str, Any] | None = None,
) -> Mapping[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if len(snapshots) != len(evaluations):
        raise DsecPortError(
            "zone-1 snapshot/evaluation count mismatch: "
            f"{len(snapshots)} != {len(evaluations)}"
        )

    fingerprint_rows = [
        item for snapshot in snapshots for item in snapshot_fingerprints(snapshot)
    ]
    fingerprint_path = out / "python_zone1_calc_hmc_all_input_fingerprints.csv"
    _write_rows(fingerprint_path, fingerprint_rows)
    manifest_path = out / "python_zone1_calc_hmc_all_input_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "evaluation_count": len(snapshots),
                "fingerprint_count": len(fingerprint_rows),
                "names_by_evaluation": {
                    str(snapshot.evaluation_index): [
                        row.name for row in snapshot_fingerprints(snapshot)
                    ]
                    for snapshot in snapshots
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    replay_rows: list[dict[str, Any]] = []
    replay_summary: list[dict[str, Any]] = []
    for snapshot in snapshots:
        replay = replay_same_entry_state(master, derived, snapshot)
        replay_rows.extend(
            {"evaluation_index": replay.evaluation_index, **asdict(row)}
            for row in replay.rows
        )
        replay_summary.append(
            {"evaluation_index": replay.evaluation_index, "ready": replay.ready}
        )
    replay_path = out / "python_zone1_same_entry_replay.csv"
    _write_rows(replay_path, replay_rows)
    replay_json = out / "python_zone1_same_entry_replay_summary.json"
    replay_json.write_text(
        json.dumps(
            {
                "evaluations": replay_summary,
                "ready": bool(replay_summary)
                and all(row["ready"] for row in replay_summary),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if target_result is None:
        if not evaluations:
            raise DsecPortError("zone-1 diagnostic has no DSEC evaluations")
        target_index = min(
            range(len(evaluations)),
            key=lambda index: abs(
                float(evaluations[index].fixed_state_result.temperature_k)
                - float(target_temperature_k)
            ),
        )
        target_result = evaluations[target_index].fixed_state_result
        target_metadata = {
            "source": "nearest_dsec_evaluation",
            "source_evaluation_index": target_index + 1,
        }
    target_metadata = dict(target_metadata or {})
    target_eval = int(target_metadata.get("source_evaluation_index", 0))

    rates_path = out / "python_zone1_carbon_rates_T73198p4K.csv"
    _write_rows(
        rates_path,
        extract_python_carbon_rates(target_result, evaluation_index=target_eval),
    )
    civ_records_path = out / "python_zone1_civ_calc_ion_rates_records_T73198p4K.csv"
    civ_records = extract_python_civ_preliminary_records(
        target_result, evaluation_index=target_eval
    )
    _write_rows(civ_records_path, civ_records)
    topology_path = out / "python_zone1_carbon_topology_T73198p4K.csv"
    _write_rows(
        topology_path,
        extract_python_carbon_topology(target_result, evaluation_index=target_eval),
    )
    initial_population_path = out / "python_zone1_carbon_initial_population_T73198p4K.csv"
    _write_rows(
        initial_population_path,
        extract_python_carbon_initial_populations(
            target_result, evaluation_index=target_eval
        ),
    )
    state_path = out / "python_zone1_carbon_state_path_T73198p4K.csv"
    state_path_rows = extract_python_carbon_state_path(
        target_result, evaluation_index=target_eval
    )
    _write_rows(state_path, state_path_rows)

    # v0.4.93 diagnostic-only: keep the historical target-temperature
    # state-path product above unchanged, but also export the full carbon
    # solve path for evaluations 9--11.  These are the evaluations where
    # v0.4.90 showed the C II-continuum / C III-ground boundary crossing
    # tolerance during the carbon solve/writeback, before the hydrogen
    # recombination-side mismatch becomes gate-significant.
    carbon_solve_eval09_11_rows: list[dict[str, Any]] = []
    for evaluation_index, evaluation in enumerate(evaluations, start=1):
        if 9 <= evaluation_index <= 11 and evaluation.fixed_state_result is not None:
            for row in extract_python_carbon_state_path(
                evaluation.fixed_state_result, evaluation_index=evaluation_index
            ):
                if int(row.get("phase_code", 0)) in (30, 40, 50, 60, 70, 80, 120):
                    carbon_solve_eval09_11_rows.append(dict(row))
    carbon_solve_eval09_11_path = out / "python_zone1_carbon_solve_path_eval09_11_T73198p4K.csv"
    _write_rows(carbon_solve_eval09_11_path, carbon_solve_eval09_11_rows)

    carbon_inner_eval11_rows: list[dict[str, Any]] = []
    for evaluation_index, evaluation in enumerate(evaluations, start=1):
        if evaluation_index == 11 and evaluation.fixed_state_result is not None:
            carbon_inner_eval11_rows.extend(
                extract_python_carbon_msolvelucy_inner_eval11_outer1(
                    evaluation.fixed_state_result, evaluation_index=evaluation_index
                )
            )
    carbon_inner_eval11_path = out / "python_zone1_carbon_msolvelucy_inner_eval11_outer1_T73198p4K.csv"
    _write_rows(carbon_inner_eval11_path, carbon_inner_eval11_rows)

    stage_totals_path = out / "python_zone1_carbon_stage_totals_T73198p4K.csv"
    stage_total_rows = extract_python_carbon_stage_totals(
        target_result, evaluation_index=target_eval
    )
    _write_rows(stage_totals_path, stage_total_rows)

    carbon_solve_stage_eval09_11_rows: list[dict[str, Any]] = []
    for evaluation_index, evaluation in enumerate(evaluations, start=1):
        if 9 <= evaluation_index <= 11 and evaluation.fixed_state_result is not None:
            for row in extract_python_carbon_stage_totals(
                evaluation.fixed_state_result, evaluation_index=evaluation_index
            ):
                if int(row.get("phase_code", 0)) in (41, 90, 100):
                    carbon_solve_stage_eval09_11_rows.append(dict(row))
    carbon_solve_stage_eval09_11_path = out / "python_zone1_carbon_solve_stage_totals_eval09_11_T73198p4K.csv"
    _write_rows(carbon_solve_stage_eval09_11_path, carbon_solve_stage_eval09_11_rows)
    alias_path = out / "python_zone1_carbon_alias_boundaries_T73198p4K.csv"
    alias_rows = extract_python_carbon_alias_boundaries(
        target_result, evaluation_index=target_eval
    )
    _write_rows(alias_path, alias_rows)
    hydrogen_rows: list[dict[str, Any]] = []
    for evaluation_index, evaluation in enumerate(evaluations, start=1):
        result = evaluation.fixed_state_result
        if result is not None:
            hydrogen_rows.extend(
                extract_python_hydrogen_state_path(
                    result, evaluation_index=evaluation_index
                )
            )
    hydrogen_path = out / "python_zone1_hydrogen_state_path.csv"
    _write_rows(hydrogen_path, hydrogen_rows)

    electron_rows: list[dict[str, Any]] = []
    carbon_correlation_rows: list[dict[str, Any]] = []
    for evaluation_index, evaluation in enumerate(evaluations, start=1):
        result = evaluation.fixed_state_result
        if result is not None:
            electron_rows.extend(
                extract_python_electron_fraction_path(
                    result, evaluation_index=evaluation_index
                )
            )
            carbon_correlation_rows.extend(
                extract_python_carbon_stage_correlation(
                    result, evaluation_index=evaluation_index
                )
            )
    electron_path = out / "python_zone1_electron_fraction_path.csv"
    _write_rows(electron_path, electron_rows)
    carbon_correlation_path = out / "python_zone1_carbon_stage_correlation.csv"
    _write_rows(carbon_correlation_path, carbon_correlation_rows)

    normalization_path = out / "python_zone1_carbon_normalization_row_T73198p4K.csv"
    _write_rows(
        normalization_path,
        extract_python_carbon_normalization_row(
            target_result, evaluation_index=target_eval
        ),
    )
    logical_cooling_path = out / "python_zone1_carbon_cooling_logical_T73198p4K.csv"
    _write_rows(
        logical_cooling_path,
        carbon_cooling_logical_rows(target_result, evaluation_index=target_eval),
    )
    level_population_path = out / "python_zone1_cv_level_populations_T73198p4K.csv"
    _write_rows(
        level_population_path,
        extract_python_cv_level_populations(
            target_result, evaluation_index=target_eval
        ),
    )
    matrix_path = out / "python_zone1_cv_matrix_levels_4_6_10_12_20.csv"
    _write_rows(
        matrix_path,
        extract_python_cv_matrix_audit(target_result, evaluation_index=target_eval),
    )

    cooling_rows: list[dict[str, Any]] = []
    for evaluation_index, evaluation in enumerate(evaluations, start=1):
        result = evaluation.fixed_state_result
        if result is not None:
            cooling_rows.extend(
                carbon_cooling_rows(result, evaluation_index=evaluation_index)
            )
    cooling_path = out / "python_zone1_carbon_cooling_terms.csv"
    _write_rows(cooling_path, cooling_rows)

    summary = {
        "diagnostic_release": "0.4.94",
        "zone_index": 1,
        "n_evaluations": len(evaluations),
        "n_snapshots": len(snapshots),
        "target_temperature_K": float(target_temperature_k),
        "target_result_temperature_K": float(target_result.temperature_k),
        "target_result_electron_fraction_xee": float(
            target_result.electron_fraction_xee
        ),
        "target_result_hydrogen_density_cm3": float(
            target_result.hydrogen_density_cm3
        ),
        "target_result_metadata": target_metadata,
        "same_entry_replay_ready": bool(replay_summary)
        and all(item["ready"] for item in replay_summary),
        "type15_literal_threshold_order_corrected": True,
        "type59_literal_compact_layout_corrected": True,
        "type59_literal_continuum_offset_corrected": True,
        "type59_literal_pre_swap_reverse_zeroing_corrected": True,
        "n_civ_preliminary_record_rows": len(civ_records),
        "n_carbon_state_path_rows": len(state_path_rows),
        "n_carbon_solve_path_eval09_11_rows": len(carbon_solve_eval09_11_rows),
        "n_carbon_msolvelucy_inner_eval11_outer1_rows": len(carbon_inner_eval11_rows),
        "n_carbon_stage_total_rows": len(stage_total_rows),
        "n_carbon_solve_stage_total_eval09_11_rows": len(carbon_solve_stage_eval09_11_rows),
        "n_carbon_alias_rows": len(alias_rows),
        "n_hydrogen_state_rows": len(hydrogen_rows),
        "n_electron_fraction_path_rows": len(electron_rows),
        "n_carbon_stage_correlation_rows": len(carbon_correlation_rows),
        "source_order_state_path_probe_added": True,
        "production_physics_modified_in_this_release": False,
        "production_rates_modified": True,
        "production_rate_change_scope": (
            "ucalc_data_type_15_final_shell_threshold_plus_"
            "data_type_59_compact_fields_continuum_offset_pre_swap_zeroing_"
            "literal_nbinc_enxt_excited_parent_weight_plus_calc_ion_rates_lfpi1_"
            "plus_calc_hmc_all_live_xh0_xh1_and_strict_msolvelucy"
        ),
        "production_solver_modified": True,
        "production_solver_change_scope": (
            "msolvelucy_no_lstsq_no_dense_rescue_literal_1dminus24_"
            "normalization_ordered_diff_diff2_and_rate_type5_falpha"
        ),
        "live_hydrogen_charge_exchange_state": True,
        "production_tolerances_modified": False,
        "empirical_corrections_added": False,
    }
    summary_path = out / "python_zone1_dsec_diagnostic_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "fingerprints_csv": fingerprint_path,
        "fingerprint_manifest_json": manifest_path,
        "replay_csv": replay_path,
        "replay_json": replay_json,
        "rates_csv": rates_path,
        "civ_records_csv": civ_records_path,
        "topology_csv": topology_path,
        "initial_population_csv": initial_population_path,
        "carbon_state_path_csv": state_path,
        "carbon_solve_path_eval09_11_csv": carbon_solve_eval09_11_path,
        "carbon_msolvelucy_inner_eval11_outer1_csv": carbon_inner_eval11_path,
        "carbon_stage_totals_csv": stage_totals_path,
        "carbon_solve_stage_totals_eval09_11_csv": carbon_solve_stage_eval09_11_path,
        "carbon_alias_boundaries_csv": alias_path,
        "hydrogen_state_path_csv": hydrogen_path,
        "electron_fraction_path_csv": electron_path,
        "carbon_stage_correlation_csv": carbon_correlation_path,
        "normalization_row_csv": normalization_path,
        "cv_level_populations_csv": level_population_path,
        "logical_cooling_csv": logical_cooling_path,
        "matrix_csv": matrix_path,
        "cooling_csv": cooling_path,
        "summary_json": summary_path,
    }


__all__ = [
    "TARGET_CARBON_STAGES",
    "TARGET_CV_LOCAL_LEVELS",
    "TARGET_TEMPERATURE_K",
    "NumericFingerprint",
    "ReplayParityRow",
    "SameEntryReplayResult",
    "CarbonRateRow",
    "MatrixAuditRow",
    "CoolingComparisonRow",
    "numeric_fingerprint",
    "snapshot_fingerprints",
    "result_fingerprints",
    "replay_same_entry_state",
    "extract_python_carbon_rates",
    "extract_python_civ_preliminary_records",
    "extract_python_carbon_topology",
    "extract_python_carbon_initial_populations",
    "extract_python_carbon_state_path",
    "extract_python_carbon_stage_totals",
    "extract_python_carbon_alias_boundaries",
    "extract_python_hydrogen_state_path",
    "extract_python_electron_fraction_path",
    "extract_python_carbon_stage_correlation",
    "extract_python_carbon_normalization_row",
    "extract_python_cv_level_populations",
    "extract_python_cv_matrix_audit",
    "carbon_cooling_rows",
    "carbon_cooling_logical_rows",
    "compare_cooling_terms",
    "enforce_cooling_gate",
    "write_zone1_python_diagnostic_products",
]
