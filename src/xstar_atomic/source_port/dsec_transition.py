"""Transition-state diagnostics for repeated physical ``dsec`` evaluations.

v0.4.51 compares the Python state immediately before evaluation *N* with the
call-correlated XSTAR entry state captured for the same evaluation.  The first
production use is evaluation 2, which tests the complete state written by
Python evaluation 1 and the control update performed between the two calls.

The XSTAR capture is a regression oracle only.  None of its values are fed
back into the Python evaluation being tested.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np

from .dsec import DsecCalcHMCAllInputSnapshot, DsecPortError
from .dsec_correlation import DsecMatchingInputState


@dataclass(frozen=True)
class DsecTransitionParityRow:
    category: str
    quantity: str
    index: int
    slot: int
    python_value: float
    xstar_value: float
    absolute_difference: float
    relative_difference: float
    comparison_mode: str
    within_tolerance: bool


@dataclass(frozen=True)
class DsecTransitionStateParity:
    python_evaluation_index: int
    xstar_evaluation_index: int
    xstar_calc_hmc_all_call_id: int
    runtime_state_ready: bool
    radiation_state_ready: bool
    escape_state_ready: bool
    continuum_workspace_ready: bool
    global_mapping_ready: bool
    global_xilevg_ready: bool
    global_bilevg_ready: bool
    global_rnisg_ready: bool
    leveltemp_source_used_slots_ready: bool
    rows: Tuple[DsecTransitionParityRow, ...]
    unmapped_nonzero_global_keys: Tuple[Tuple[int, int, int], ...]
    max_absolute_difference: float
    max_relative_difference: float
    xstar_source_dir: str

    @property
    def ready(self) -> bool:
        return bool(
            self.runtime_state_ready
            and self.radiation_state_ready
            and self.escape_state_ready
            and self.continuum_workspace_ready
            and self.global_mapping_ready
            and self.global_xilevg_ready
            and self.global_bilevg_ready
            and self.global_rnisg_ready
            and self.leveltemp_source_used_slots_ready
        )


def _relative_difference(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0e-300)


def _add_float_row(
    rows: list[DsecTransitionParityRow],
    *,
    category: str,
    quantity: str,
    python_value: float,
    xstar_value: float,
    rtol: float,
    atol: float,
    index: int = 0,
    slot: int = 0,
    comparison_mode: str = "isclose",
) -> bool:
    py = float(python_value)
    xs = float(xstar_value)
    absdiff = abs(py - xs)
    reldiff = _relative_difference(py, xs)
    if comparison_mode == "exact_integer":
        ok = int(round(py)) == int(round(xs))
    else:
        ok = bool(np.isclose(py, xs, rtol=float(rtol), atol=float(atol)))
    rows.append(
        DsecTransitionParityRow(
            category=str(category),
            quantity=str(quantity),
            index=int(index),
            slot=int(slot),
            python_value=py,
            xstar_value=xs,
            absolute_difference=absdiff,
            relative_difference=reldiff,
            comparison_mode=str(comparison_mode),
            within_tolerance=ok,
        )
    )
    return ok


def _sequence(value: Any, *names: str) -> np.ndarray:
    for name in names:
        if hasattr(value, name):
            return np.asarray(getattr(value, name), dtype=float).reshape(-1)
    return np.zeros(0, dtype=float)


def _dense_global(
    values: Mapping[Tuple[int, int, int], float],
    index_by_key: Mapping[Tuple[int, int, int], int],
    n: int,
) -> tuple[np.ndarray, tuple[Tuple[int, int, int], ...]]:
    dense = np.zeros(int(n), dtype=float)
    unmapped: list[Tuple[int, int, int]] = []
    for raw_key, raw_value in values.items():
        key = (int(raw_key[0]), int(raw_key[1]), int(raw_key[2]))
        value = float(raw_value)
        index = int(index_by_key.get(key, 0))
        if 1 <= index <= n:
            dense[index - 1] = value
        elif value != 0.0:
            unmapped.append(key)
    return dense, tuple(sorted(set(unmapped)))


def _dense_snapshot_global(
    direct_values: Optional[Sequence[float]],
    logical_values: Mapping[Tuple[int, int, int], float],
    index_by_key: Mapping[Tuple[int, int, int], int],
    n: int,
) -> tuple[np.ndarray, tuple[Tuple[int, int, int], ...]]:
    """Return the authoritative dense state when available.

    v0.4.52 makes the native-index arrays the owner of repeated-``dsec``
    state.  Older/synthetic snapshots may still provide only logical keys, so
    retain the v0.4.51 reconstruction as a compatibility fallback.
    """

    if direct_values is not None:
        supplied = np.asarray(direct_values, dtype=float).reshape(-1)
        dense = np.zeros(int(n), dtype=float)
        dense[: min(dense.size, supplied.size)] = supplied[: dense.size]
        return dense, ()
    return _dense_global(logical_values, index_by_key, n)


def _leveltemp_python_value(workspace: Any, *, column: int, quantity: str) -> float:
    if workspace is None:
        return 0.0
    level = workspace.get(column) if hasattr(workspace, "get") else None
    if level is None:
        return 0.0
    if quantity == "rlev1":
        return float(getattr(level, "energy_ev", 0.0))
    if quantity == "rlev2":
        return float(getattr(level, "statistical_weight", 0.0))
    if quantity == "rlev4":
        return float(getattr(level, "ionization_potential_ev", 0.0))
    if quantity == "ilev1":
        value = getattr(level, "principal_n", None)
        return float(0 if value is None else int(value))
    if quantity == "ilev3":
        value = getattr(level, "orbital_l", None)
        return float(0 if value is None else int(value))
    raise KeyError(quantity)


def compare_dsec_transition_state(
    snapshot: DsecCalcHMCAllInputSnapshot,
    xstar: DsecMatchingInputState,
    *,
    runtime_rtol: float = 5.0e-12,
    runtime_atol: float = 1.0e-30,
    array_rtol: float = 5.0e-12,
    array_atol: float = 1.0e-30,
    population_rtol: float = 5.0e-12,
    population_atol: float = 1.0e-30,
    leveltemp_rtol: float = 5.0e-12,
    leveltemp_atol: float = 1.0e-30,
    xstar_opakc_before_cm_inv: Optional[Sequence[float]] = None,
    xstar_brcems_before: Optional[Sequence[float]] = None,
) -> DsecTransitionStateParity:
    """Compare one Python pre-call snapshot with the matching XSTAR call entry."""

    if int(snapshot.evaluation_index) != int(xstar.dsec_evaluation_index):
        raise DsecPortError(
            "Python/XSTAR transition evaluation mismatch: "
            f"python={snapshot.evaluation_index}, xstar={xstar.dsec_evaluation_index}"
        )
    if str(xstar.phase) != "dsec_internal":
        raise DsecPortError(
            f"transition reference phase must be dsec_internal, got {xstar.phase!r}"
        )

    rows: list[DsecTransitionParityRow] = []
    runtime_flags = [
        _add_float_row(
            rows,
            category="runtime",
            quantity="temperature_t4",
            python_value=snapshot.temperature_t4,
            xstar_value=xstar.temperature_t4,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="temperature_k",
            python_value=snapshot.temperature_k,
            xstar_value=xstar.temperature_t4 * 1.0e4,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="electron_fraction_xee",
            python_value=snapshot.electron_fraction_xee,
            xstar_value=xstar.electron_fraction_xee,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="hydrogen_density_cm3",
            python_value=snapshot.hydrogen_density_cm3,
            xstar_value=xstar.hydrogen_density_cm3,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="pressure",
            python_value=snapshot.pressure,
            xstar_value=xstar.pressure,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="lcdd",
            python_value=float(snapshot.lcdd),
            xstar_value=float(xstar.lcdd),
            rtol=0.0,
            atol=0.0,
            comparison_mode="exact_integer",
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="covering_fraction",
            python_value=snapshot.covering_fraction,
            xstar_value=xstar.covering_fraction,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="turbulent_velocity_km_s",
            python_value=snapshot.turbulent_velocity_km_s,
            xstar_value=xstar.turbulent_velocity_km_s,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
        _add_float_row(
            rows,
            category="runtime",
            quantity="critf",
            python_value=snapshot.critf,
            xstar_value=xstar.critf,
            rtol=runtime_rtol,
            atol=runtime_atol,
        ),
    ]

    heatf = snapshot.calc_kwargs.get("heatf_context")
    if heatf is not None:
        runtime_flags.extend(
            [
                _add_float_row(
                    rows,
                    category="runtime",
                    quantity="radius_cm",
                    python_value=float(getattr(heatf, "radius_cm")),
                    xstar_value=xstar.radius_cm,
                    rtol=runtime_rtol,
                    atol=runtime_atol,
                ),
                _add_float_row(
                    rows,
                    category="runtime",
                    quantity="zone_thickness_cm",
                    python_value=float(getattr(heatf, "zone_thickness_cm")),
                    xstar_value=xstar.zone_thickness_cm,
                    rtol=runtime_rtol,
                    atol=runtime_atol,
                ),
            ]
        )

    py_epi = _sequence(snapshot.radiation, "epim_eV", "epi_eV")
    py_bremsa = _sequence(snapshot.radiation, "bremsam", "bremsa")
    py_bremsint = _sequence(snapshot.radiation, "bremsint")
    xs_epi = np.asarray(xstar.radiation.epim_eV, dtype=float)
    xs_bremsa = np.asarray(xstar.radiation.bremsam, dtype=float)
    xs_bremsint = np.asarray(xstar.radiation.bremsint, dtype=float)
    radiation_flags: list[bool] = []
    for quantity, py, xs in (
        ("epi_eV", py_epi, xs_epi),
        ("bremsa", py_bremsa, xs_bremsa),
        ("bremsint", py_bremsint, xs_bremsint),
    ):
        if py.size != xs.size:
            radiation_flags.append(False)
            _add_float_row(
                rows,
                category="radiation",
                quantity=f"{quantity}_length",
                python_value=float(py.size),
                xstar_value=float(xs.size),
                rtol=0.0,
                atol=0.0,
                comparison_mode="exact_integer",
            )
            continue
        for index, (pv, xv) in enumerate(zip(py, xs), start=1):
            radiation_flags.append(
                _add_float_row(
                    rows,
                    category="radiation",
                    quantity=quantity,
                    index=index,
                    python_value=float(pv),
                    xstar_value=float(xv),
                    rtol=array_rtol,
                    atol=array_atol,
                )
            )

    escape_flags: list[bool] = []
    for quantity, py, xs in (
        (
            "line_tau_in",
            _sequence(snapshot.escape, "line_tau_in"),
            np.asarray(xstar.escape.line_tau_in, dtype=float),
        ),
        (
            "line_tau_out",
            _sequence(snapshot.escape, "line_tau_out"),
            np.asarray(xstar.escape.line_tau_out, dtype=float),
        ),
        (
            "continuum_tau_in",
            _sequence(snapshot.escape, "continuum_tau_in"),
            np.asarray(xstar.escape.continuum_tau_in, dtype=float),
        ),
        (
            "continuum_tau_out",
            _sequence(snapshot.escape, "continuum_tau_out"),
            np.asarray(xstar.escape.continuum_tau_out, dtype=float),
        ),
    ):
        if py.size != xs.size:
            escape_flags.append(False)
            _add_float_row(
                rows,
                category="escape",
                quantity=f"{quantity}_length",
                python_value=float(py.size),
                xstar_value=float(xs.size),
                rtol=0.0,
                atol=0.0,
                comparison_mode="exact_integer",
            )
            continue
        for index, (pv, xv) in enumerate(zip(py, xs), start=1):
            escape_flags.append(
                _add_float_row(
                    rows,
                    category="escape",
                    quantity=quantity,
                    index=index,
                    python_value=float(pv),
                    xstar_value=float(xv),
                    rtol=array_rtol,
                    atol=array_atol,
                )
            )


    workspace_flags: list[bool] = []
    freef_context = snapshot.calc_kwargs.get("free_free_context")
    bremem_context = snapshot.calc_kwargs.get("bremem_context")
    for quantity, py, xs in (
        (
            "opakc_before_cm_inv",
            _sequence(freef_context, "opakc_before_cm_inv"),
            (
                None
                if xstar_opakc_before_cm_inv is None
                else np.asarray(xstar_opakc_before_cm_inv, dtype=float).reshape(-1)
            ),
        ),
        (
            "brcems_before",
            _sequence(bremem_context, "brcems_before"),
            (
                None
                if xstar_brcems_before is None
                else np.asarray(xstar_brcems_before, dtype=float).reshape(-1)
            ),
        ),
    ):
        if xs is None:
            continue
        if py.size != xs.size:
            workspace_flags.append(False)
            _add_float_row(
                rows,
                category="continuum_workspace",
                quantity=f"{quantity}_length",
                python_value=float(py.size),
                xstar_value=float(xs.size),
                rtol=0.0,
                atol=0.0,
                comparison_mode="exact_integer",
            )
            continue
        for index, (pv, xv) in enumerate(zip(py, xs), start=1):
            workspace_flags.append(
                _add_float_row(
                    rows,
                    category="continuum_workspace",
                    quantity=quantity,
                    index=index,
                    python_value=float(pv),
                    xstar_value=float(xv),
                    rtol=array_rtol,
                    atol=array_atol,
                )
            )

    n_global = max(
        xstar.global_level_values_by_index.size,
        xstar.global_bilev_values_by_index.size,
        xstar.global_rnist_values_by_index.size,
    )
    py_xilev, unmapped_x = _dense_snapshot_global(
        snapshot.global_xilevg_by_index,
        snapshot.global_level_populations,
        snapshot.global_level_index_by_key,
        n_global,
    )
    py_bilev, unmapped_b = _dense_snapshot_global(
        snapshot.global_bilevg_by_index,
        snapshot.global_bilev_values,
        snapshot.global_level_index_by_key,
        n_global,
    )
    py_rnist, unmapped_r = _dense_snapshot_global(
        snapshot.global_rnisg_by_index,
        snapshot.global_rnist_values,
        snapshot.global_level_index_by_key,
        n_global,
    )
    unmapped = tuple(sorted(set(unmapped_x + unmapped_b + unmapped_r)))

    global_flags: Dict[str, list[bool]] = {
        "xilevg": [],
        "bilevg": [],
        "rnisg": [],
    }
    for quantity, py, xs in (
        ("xilevg", py_xilev, xstar.global_level_values_by_index),
        ("bilevg", py_bilev, xstar.global_bilev_values_by_index),
        ("rnisg", py_rnist, xstar.global_rnist_values_by_index),
    ):
        xs_dense = np.zeros(n_global, dtype=float)
        xs_dense[: np.asarray(xs).size] = np.asarray(xs, dtype=float)
        for index, (pv, xv) in enumerate(zip(py, xs_dense), start=1):
            global_flags[quantity].append(
                _add_float_row(
                    rows,
                    category="global_levels",
                    quantity=quantity,
                    index=index,
                    python_value=float(pv),
                    xstar_value=float(xv),
                    rtol=population_rtol,
                    atol=population_atol,
                )
            )

    leveltemp_flags: list[bool] = []
    raw = xstar.leveltemp_snapshot
    if raw is None:
        leveltemp_flags.append(False)
    else:
        # These are exactly the leveltemp slots read by ucalc.f90.  The raw
        # snapshot retains all remaining slots for inspection/output, but they
        # are not part of the strict Python parity gate until the production
        # UCalcLevel representation owns them.
        for column in range(1, raw.n_columns + 1):
            for quantity, slot, xs_value, integer_mode in (
                ("rlev1", 1, raw.rlev[0, column - 1], False),
                ("rlev2", 2, raw.rlev[1, column - 1], False),
                ("rlev4", 4, raw.rlev[3, column - 1], False),
                ("ilev1", 1, raw.ilev[0, column - 1], True),
                ("ilev3", 3, raw.ilev[2, column - 1], True),
            ):
                leveltemp_flags.append(
                    _add_float_row(
                        rows,
                        category="leveltemp_source_used",
                        quantity=quantity,
                        index=column,
                        slot=slot,
                        python_value=_leveltemp_python_value(
                            snapshot.leveltemp_workspace,
                            column=column,
                            quantity=quantity,
                        ),
                        xstar_value=float(xs_value),
                        rtol=(0.0 if integer_mode else leveltemp_rtol),
                        atol=(0.0 if integer_mode else leveltemp_atol),
                        comparison_mode=("exact_integer" if integer_mode else "isclose"),
                    )
                )

    max_abs = max((row.absolute_difference for row in rows), default=0.0)
    max_rel = max((row.relative_difference for row in rows), default=0.0)
    return DsecTransitionStateParity(
        python_evaluation_index=int(snapshot.evaluation_index),
        xstar_evaluation_index=int(xstar.dsec_evaluation_index),
        xstar_calc_hmc_all_call_id=int(xstar.calc_hmc_all_call_id),
        runtime_state_ready=bool(runtime_flags and all(runtime_flags)),
        radiation_state_ready=bool(radiation_flags and all(radiation_flags)),
        escape_state_ready=bool(escape_flags and all(escape_flags)),
        continuum_workspace_ready=(
            True if not workspace_flags else bool(all(workspace_flags))
        ),
        global_mapping_ready=not unmapped,
        global_xilevg_ready=bool(global_flags["xilevg"] and all(global_flags["xilevg"])),
        global_bilevg_ready=bool(global_flags["bilevg"] and all(global_flags["bilevg"])),
        global_rnisg_ready=bool(global_flags["rnisg"] and all(global_flags["rnisg"])),
        leveltemp_source_used_slots_ready=bool(leveltemp_flags and all(leveltemp_flags)),
        rows=tuple(rows),
        unmapped_nonzero_global_keys=unmapped,
        max_absolute_difference=float(max_abs),
        max_relative_difference=float(max_rel),
        xstar_source_dir=str(xstar.source_dir),
    )


def write_dsec_transition_state_products(
    parity: DsecTransitionStateParity,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.53",
) -> Mapping[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_dsec_transition_state_parity.csv"
    fields = list(DsecTransitionParityRow.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in parity.rows:
            writer.writerow({name: getattr(row, name) for name in fields})

    summary = {
        "port_version": port_version,
        "python_evaluation_index": parity.python_evaluation_index,
        "xstar_evaluation_index": parity.xstar_evaluation_index,
        "xstar_calc_hmc_all_call_id": parity.xstar_calc_hmc_all_call_id,
        "runtime_state_ready": parity.runtime_state_ready,
        "radiation_state_ready": parity.radiation_state_ready,
        "escape_state_ready": parity.escape_state_ready,
        "continuum_workspace_ready": parity.continuum_workspace_ready,
        "global_mapping_ready": parity.global_mapping_ready,
        "global_xilevg_ready": parity.global_xilevg_ready,
        "global_bilevg_ready": parity.global_bilevg_ready,
        "global_rnisg_ready": parity.global_rnisg_ready,
        "leveltemp_source_used_slots_ready": parity.leveltemp_source_used_slots_ready,
        "dsec_transition_state_ready": parity.ready,
        "n_unmapped_nonzero_global_keys": len(parity.unmapped_nonzero_global_keys),
        "unmapped_nonzero_global_keys": [list(key) for key in parity.unmapped_nonzero_global_keys],
        "max_absolute_difference": parity.max_absolute_difference,
        "max_relative_difference": parity.max_relative_difference,
        "xstar_source_dir": parity.xstar_source_dir,
    }
    json_path = out / "xstar_dsec_transition_state_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_dsec_transition_state_parity_summary.md"
    md_path.write_text(
        "# Dsec evaluation-transition state parity\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


def write_dsec_input_snapshot_products(
    snapshot: DsecCalcHMCAllInputSnapshot,
    xstar: DsecMatchingInputState,
    out_dir: str | Path,
) -> Mapping[str, Path]:
    """Write compact Python and raw-XSTAR state products for manual diagnosis."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    n_global = max(
        xstar.global_level_values_by_index.size,
        xstar.global_bilev_values_by_index.size,
        xstar.global_rnist_values_by_index.size,
    )
    py_x, _ = _dense_global(snapshot.global_level_populations, snapshot.global_level_index_by_key, n_global)
    py_b, _ = _dense_global(snapshot.global_bilev_values, snapshot.global_level_index_by_key, n_global)
    py_rnist_dense, _ = _dense_global(snapshot.global_rnist_values, snapshot.global_level_index_by_key, n_global)
    global_path = out / "xstar_dsec_transition_global_levels.csv"
    with global_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "global_level_index",
            "python_xilevg",
            "xstar_xilevg",
            "python_bilevg",
            "xstar_bilevg",
            "python_rnisg",
            "xstar_rnisg",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for idx in range(n_global):
            writer.writerow(
                {
                    "global_level_index": idx + 1,
                    "python_xilevg": py_x[idx],
                    "xstar_xilevg": xstar.global_level_values_by_index[idx] if idx < xstar.global_level_values_by_index.size else 0.0,
                    "python_bilevg": py_b[idx],
                    "xstar_bilevg": xstar.global_bilev_values_by_index[idx] if idx < xstar.global_bilev_values_by_index.size else 0.0,
                    "python_rnisg": py_rnist_dense[idx],
                    "xstar_rnisg": xstar.global_rnist_values_by_index[idx] if idx < xstar.global_rnist_values_by_index.size else 0.0,
                }
            )

    leveltemp_path = out / "xstar_dsec_transition_leveltemp.csv"
    raw = xstar.leveltemp_snapshot
    n_columns = 0 if raw is None else raw.n_columns
    with leveltemp_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "column_index",
            "slot",
            "python_rlev",
            "xstar_rlev",
            "python_ilev",
            "xstar_ilev",
            "xstar_nlpt",
            "xstar_iltp",
            "python_owner_phase",
            "python_owner_ion_index",
            "python_owner_ion_stage",
            "python_owner_write_sequence",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for column in range(1, n_columns + 1):
            owner = snapshot.leveltemp_owner_by_column.get(column, {})
            for slot in range(1, 11):
                py_rlev = 0.0
                py_ilev = 0
                if slot == 1:
                    py_rlev = _leveltemp_python_value(snapshot.leveltemp_workspace, column=column, quantity="rlev1")
                    py_ilev = int(_leveltemp_python_value(snapshot.leveltemp_workspace, column=column, quantity="ilev1"))
                elif slot == 2:
                    py_rlev = _leveltemp_python_value(snapshot.leveltemp_workspace, column=column, quantity="rlev2")
                elif slot == 3:
                    py_ilev = int(_leveltemp_python_value(snapshot.leveltemp_workspace, column=column, quantity="ilev3"))
                elif slot == 4:
                    py_rlev = _leveltemp_python_value(snapshot.leveltemp_workspace, column=column, quantity="rlev4")
                writer.writerow(
                    {
                        "column_index": column,
                        "slot": slot,
                        "python_rlev": py_rlev,
                        "xstar_rlev": raw.rlev[slot - 1, column - 1] if raw is not None else 0.0,
                        "python_ilev": py_ilev,
                        "xstar_ilev": raw.ilev[slot - 1, column - 1] if raw is not None else 0,
                        "xstar_nlpt": raw.nlpt[column - 1] if raw is not None else 0,
                        "xstar_iltp": raw.iltp[column - 1] if raw is not None else 0,
                        "python_owner_phase": owner.get("phase", ""),
                        "python_owner_ion_index": owner.get("ion_index", 0),
                        "python_owner_ion_stage": owner.get("ion_stage", 0),
                        "python_owner_write_sequence": owner.get("write_sequence", 0),
                    }
                )
    return {"global_levels_csv": global_path, "leveltemp_csv": leveltemp_path}


__all__ = [
    "DsecTransitionParityRow",
    "DsecTransitionStateParity",
    "compare_dsec_transition_state",
    "write_dsec_transition_state_products",
    "write_dsec_input_snapshot_products",
]
