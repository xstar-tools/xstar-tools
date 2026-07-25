"""Diagnostic-only v82 patch 5.20.17.3.4 selected-line opacity attribution.

The production physics path must never consume data from this module.  It
records the Python selected-line producer stream at calc_emis_all call 2
(source final 59) and binary64 fingerprints of the aggregate line, continuum,
and merged opacity planes for direct comparison with the C++ retained owner.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .bound_free_opacity_attribution import array_stats

_ENV_DIR = "XSTAR_V82_PATCH5201734_PYTHON_ATTRIBUTION_DIR"
_ENV_CALL = "XSTAR_V82_PATCH5201734_PYTHON_CALL_INDEX"
_DEFAULT_CALL = 2


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


def initialize_call(context: Any) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    for name in (
        "python_selected_line_records.csv",
        "python_selected_line_sum.bin",
        "python_live_selected_line_plane.bin",
        "python_continuum_pre_line.bin",
        "python_combined_opacity.bin",
        "python_line_opacity_checkpoints.csv",
    ):
        path = out / name
        if path.exists():
            path.unlink()
    setattr(context, "_patch5201734_line_record_order", 0)


def _append_csv(path: Path, row: Mapping[str, Any]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def record_line(
    context: Any,
    *,
    record: int,
    rate_type: int,
    data_type: int,
    element_z: int,
    ion_stage: int,
    ion_index: int,
    line_index: int,
    line_wavelength_angstrom: float,
    line_energy_ev: float,
    optpp: float,
    abundance_lower: float,
    abundance_upper: float,
    atomic_mass_amu: float,
    natural_width_ev: float,
    contribution: Any,
    output_role: str,
) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    order = int(getattr(context, "_patch5201734_line_record_order", 0) or 0) + 1
    setattr(context, "_patch5201734_line_record_order", order)
    arr = np.asarray(contribution, dtype=np.float64).reshape(-1)
    cstats = array_stats(arr)
    scale = float(optpp)
    shape = arr / scale if scale > 0.0 else np.zeros_like(arr)
    sstats = array_stats(shape)
    row = {
        "call_index": int(getattr(context, "diagnostic_call_index", 0) or 0),
        "pass_index": int(getattr(context, "diagnostic_pass_index", 0) or 0),
        "zone_index": int(getattr(context, "diagnostic_zone_index", 0) or 0),
        "record_order": order,
        "record": int(record),
        "data_type": int(data_type),
        "rate_type": int(rate_type),
        "element_z": int(element_z),
        "ion_stage": int(ion_stage),
        "ion_index": int(ion_index),
        "line_index_one_based": int(line_index),
        "line_wavelength_angstrom": float(line_wavelength_angstrom),
        "line_energy_ev": float(line_energy_ev),
        "optpp_cm1": float(optpp),
        "abundance_lower_cm3": float(abundance_lower),
        "abundance_upper_cm3": float(abundance_upper),
        "hydrogen_density_cm3": float(getattr(context, "hydrogen_density_cm3", 0.0) or 0.0),
        "atomic_mass_amu": float(atomic_mass_amu),
        "natural_width_ev": float(natural_width_ev),
        "output_role": str(output_role),
        "contribution_nonzero_bins": cstats["nonzero_bins"],
        "contribution_first_nonzero_one_based": cstats["first_nonzero_one_based"],
        "contribution_last_nonzero_one_based": cstats["last_nonzero_one_based"],
        "contribution_sum": cstats["sum"],
        "contribution_abs_sum": cstats["abs_sum"],
        "contribution_max": cstats["max"],
        "contribution_hash": cstats["hash"],
        "shape_nonzero_bins": sstats["nonzero_bins"],
        "shape_sum": sstats["sum"],
        "shape_max": sstats["max"],
        "shape_hash": sstats["hash"],
    }
    _append_csv(out / "python_selected_line_records.csv", row)


def checkpoint(context: Any, phase: str, values: Any, *, dump_name: str | None = None) -> None:
    out = attribution_dir(context)
    if out is None:
        return
    stats = array_stats(values)
    row = {
        "call_index": int(getattr(context, "diagnostic_call_index", 0) or 0),
        "pass_index": int(getattr(context, "diagnostic_pass_index", 0) or 0),
        "zone_index": int(getattr(context, "diagnostic_zone_index", 0) or 0),
        "phase": str(phase),
        **stats,
    }
    _append_csv(out / "python_line_opacity_checkpoints.csv", row)
    if dump_name:
        np.asarray(values, dtype="<f8").reshape(-1).tofile(out / dump_name)
