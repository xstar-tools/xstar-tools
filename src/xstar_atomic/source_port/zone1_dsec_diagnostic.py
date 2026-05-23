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
        "diagnostic_release": "0.4.78",
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
        "production_rates_modified": False,
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
    "extract_python_cv_matrix_audit",
    "carbon_cooling_rows",
    "compare_cooling_terms",
    "enforce_cooling_gate",
    "write_zone1_python_diagnostic_products",
]
