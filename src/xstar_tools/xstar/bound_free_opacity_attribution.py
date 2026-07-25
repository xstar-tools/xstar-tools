"""Diagnostic-only v82 patch 5.20.17.3.2 bound-free opacity attribution.

This module must never feed production physics.  It records exact binary64
fingerprints and scalar summaries of the Python ``calc_emis_all`` bound-free
producer stream so the accepted C++ deferred replay can be compared record by
record at the stable call-2 final state (Python calc_emis_all call 23 / source
sequence 59).
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

_ENV_DIR = "XSTAR_V82_PATCH5201732_PYTHON_ATTRIBUTION_DIR"
_ENV_CALL = "XSTAR_V82_PATCH5201732_PYTHON_CALL_INDEX"
_DEFAULT_CALL = 23


def _target_call() -> int:
    try:
        return max(1, int(os.environ.get(_ENV_CALL, str(_DEFAULT_CALL))))
    except Exception:
        return _DEFAULT_CALL


def attribution_dir(context: Any) -> Path | None:
    raw = os.environ.get(_ENV_DIR, "").strip()
    if not raw:
        return None
    call_index = int(getattr(context, "diagnostic_call_index", 0) or 0)
    if call_index != _target_call():
        return None
    out = Path(raw)
    out.mkdir(parents=True, exist_ok=True)
    return out


def enabled(context: Any) -> bool:
    return attribution_dir(context) is not None


def binary64_fnv1a(values: Any) -> str:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    # C++ binary64_sequence_fnv1a hashes little-endian bytes of each IEEE-754
    # payload, independent of host byte order.
    bits = arr.astype("<f8", copy=False).view("<u8")
    h = 1469598103934665603
    prime = 1099511628211
    mask = (1 << 64) - 1
    for value in bits:
        iv = int(value)
        for shift in range(0, 64, 8):
            h ^= (iv >> shift) & 0xFF
            h = (h * prime) & mask
    return f"{h:016x}"


def array_stats(values: Any) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = np.isfinite(arr)
    nz = finite & (arr != 0.0)
    indices = np.flatnonzero(nz)
    return {
        "count": int(arr.size),
        "nonzero_bins": int(indices.size),
        "first_nonzero_one_based": int(indices[0] + 1) if indices.size else 0,
        "last_nonzero_one_based": int(indices[-1] + 1) if indices.size else 0,
        "sum": float(np.sum(arr[finite], dtype=np.float64)) if np.any(finite) else 0.0,
        "abs_sum": float(np.sum(np.abs(arr[finite]), dtype=np.float64)) if np.any(finite) else 0.0,
        "max": float(np.max(arr[finite])) if np.any(finite) else 0.0,
        "min": float(np.min(arr[finite])) if np.any(finite) else 0.0,
        "hash": binary64_fnv1a(arr),
    }


def _append_csv(path: Path, row: Mapping[str, Any]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def initialize_call(context: Any, opakc_before_reset: Any) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    # This call is unique in a normal trajectory.  Remove stale files from a
    # previous invocation in the same output directory so appends are exact.
    for name in (
        "python_bound_free_records.csv",
        "python_opacity_checkpoints.csv",
        "python_bound_free_sum.bin",
        "python_live_opakc_post_elements.bin",
        "python_live_opakc_return.bin",
    ):
        path = out / name
        if path.exists():
            path.unlink()
    setattr(context, "_patch5201732_bound_free_sum", np.zeros_like(np.asarray(opakc_before_reset, dtype=float)))
    setattr(context, "_patch5201732_record_order", 0)
    checkpoint(context, "calc_emis_all_pre_reset", opakc_before_reset)


def checkpoint(context: Any, phase: str, opakc: Any, *, dump_name: str | None = None) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    stats = array_stats(opakc)
    row = {
        "call_index": int(getattr(context, "diagnostic_call_index", 0) or 0),
        "pass_index": int(getattr(context, "diagnostic_pass_index", 0) or 0),
        "zone_index": int(getattr(context, "diagnostic_zone_index", 0) or 0),
        "phase": str(phase),
        **stats,
    }
    _append_csv(out / "python_opacity_checkpoints.csv", row)
    if dump_name:
        np.asarray(opakc, dtype="<f8").reshape(-1).tofile(out / dump_name)


def record_ucalc_bound_free(
    context: Any,
    *,
    result: Any,
    ion: Any,
    record: int,
    abund1: float,
    abund2: float,
    workspace_before: Any,
    workspace_after: Any,
) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    data_type = int(getattr(result, "data_type", 0) or 0)
    rate_type = int(getattr(result, "rate_type", 0) or 0)
    if data_type not in (49, 53, 88, 99) and rate_type not in (7, 42):
        return
    diagnostics = dict(getattr(result, "diagnostics", {}) or {})
    contribution = diagnostics.get("opakc_cm^-1")
    if contribution is None:
        contribution = np.zeros_like(np.asarray(workspace_before, dtype=float))
    arr = np.asarray(contribution, dtype=np.float64).reshape(-1)
    target = np.asarray(workspace_before, dtype=np.float64).reshape(-1)
    if arr.size < target.size:
        padded = np.zeros_like(target)
        padded[: arr.size] = arr
        arr = padded
    elif arr.size > target.size:
        arr = arr[: target.size]

    aggregate = getattr(context, "_patch5201732_bound_free_sum", None)
    if aggregate is not None and np.asarray(aggregate).size == arr.size:
        aggregate[:] = np.asarray(aggregate, dtype=float) + arr

    order = int(getattr(context, "_patch5201732_record_order", 0) or 0) + 1
    setattr(context, "_patch5201732_record_order", order)
    cstats = array_stats(arr)
    density = float(getattr(context, "hydrogen_density_cm3", 0.0) or 0.0)
    scale = float(abund1) * density
    normalized = arr / scale if scale > 0.0 else np.zeros_like(arr)
    nstats = array_stats(normalized)
    bstats = array_stats(workspace_before)
    astats = array_stats(workspace_after)
    try:
        pair_count = int(len(np.asarray(context.master.record_reals(int(record))).reshape(-1)) // 2)
    except Exception:
        pair_count = 0
    threshold = diagnostics.get("threshold_eV", diagnostics.get("type49_threshold_ev", 0.0))
    row = {
        "call_index": int(getattr(context, "diagnostic_call_index", 0) or 0),
        "pass_index": int(getattr(context, "diagnostic_pass_index", 0) or 0),
        "zone_index": int(getattr(context, "diagnostic_zone_index", 0) or 0),
        "record_order": order,
        "record": int(record),
        "data_type": data_type,
        "rate_type": rate_type,
        "element_z": int(getattr(ion, "element_z", 0) or 0),
        "ion_stage": int(getattr(ion, "ion_stage", 0) or 0),
        "ion_index": int(getattr(ion, "ion_index", 0) or 0),
        "status": str(getattr(getattr(result, "status", ""), "value", getattr(result, "status", ""))),
        "ready": int(bool(getattr(result, "ready", False))),
        "reason": str(getattr(result, "reason", "") or ""),
        "selected_for_opacity": int(cstats["nonzero_bins"] > 0),
        "threshold_ev": float(threshold or 0.0),
        "lower_abundance": float(abund1),
        "upper_abundance": float(abund2),
        "hydrogen_density_cm3": density,
        "raw_pair_count": pair_count,
        "phextrap_grid_points": int(diagnostics.get("type49_phextrap_grid_points", 0) or 0),
        "nb1_one_based": int(diagnostics.get("nb1_1based", diagnostics.get("radiation_bin", 0)) or 0),
        "klmax_one_based": int(diagnostics.get("klmax_1based", 0) or 0),
        "mapping_status": str(diagnostics.get("mapping_status", diagnostics.get("status", "")) or ""),
        "contribution_count": cstats["count"],
        "contribution_nonzero_bins": cstats["nonzero_bins"],
        "contribution_first_nonzero_one_based": cstats["first_nonzero_one_based"],
        "contribution_last_nonzero_one_based": cstats["last_nonzero_one_based"],
        "contribution_sum": cstats["sum"],
        "contribution_abs_sum": cstats["abs_sum"],
        "contribution_max": cstats["max"],
        "contribution_hash": cstats["hash"],
        "shape_nonzero_bins": nstats["nonzero_bins"],
        "shape_sum_cm2": nstats["sum"],
        "shape_max_cm2": nstats["max"],
        "shape_hash": nstats["hash"],
        "workspace_before_sum": bstats["sum"],
        "workspace_before_hash": bstats["hash"],
        "workspace_after_sum": astats["sum"],
        "workspace_after_hash": astats["hash"],
    }
    _append_csv(out / "python_bound_free_records.csv", row)


def finalize_bound_free_sum(context: Any) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    aggregate = getattr(context, "_patch5201732_bound_free_sum", None)
    if aggregate is None:
        return
    checkpoint(context, "diagnostic_bound_free_sum", aggregate, dump_name="python_bound_free_sum.bin")
