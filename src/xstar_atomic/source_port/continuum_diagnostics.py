"""Focused continuum/detail diagnostics for the physical XSTAR runner.

The routines in this module are deliberately passive: they never modify the
caller-owned transfer arrays.  They only summarize the raw arrays that feed
``fstepr4`` and the per-record UCalc continuum side-effect increments that
populate ``opakc`` and ``rccemis`` during ``calc_emis_all``.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


DIAGNOSTIC_BINS_ONE_BASED: tuple[int, ...] = (
    # H I Lyman-edge / pprint(22) taulc neighborhood for the 9999-bin
    # c5_ne1 grid.  ``pprint(22)`` samples dpthc(1, nbinc(13.6 eV)+1),
    # which is bin 3169 for this benchmark.
    3167,
    3168,
    3169,
    3170,
    # Historical high-energy/detail-tail probes.
    548,
    3877,
    5835,
    6154,
    6301,
    6481,
    8858,
    9226,
)

PHASE_SNAPSHOT_KEY = "continuum_phase_snapshots_v0530"
UCALC_SIDE_EFFECT_KEY = "ucalc_continuum_side_effects_v0530"


def _json_safe(value: Any) -> Any:
    """Return a JSON/CSV-friendly scalar or compact container."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.reshape(-1).tolist()]
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    try:
        out = float(value)
    except Exception:
        return str(value)
    if math.isfinite(out):
        return out
    return str(out)


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    return out if math.isfinite(out) else float(default)


def _finite_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _value_at_one_based(arr: np.ndarray, bin_one_based: int) -> float:
    idx = int(bin_one_based) - 1
    if idx < 0 or idx >= arr.size:
        return 0.0
    return _finite_float(arr[idx])


def summarize_array(values: Any, *, bins: Sequence[int] = DIAGNOSTIC_BINS_ONE_BASED) -> dict[str, Any]:
    """Summarize one continuum-grid vector with strict nonzero semantics."""
    arr = np.asarray(values, dtype=float).reshape(-1)
    nz = np.nonzero(arr != 0.0)[0]
    out: dict[str, Any] = {
        "nonzero_count": int(nz.size),
        "first_nonzero_bin": int(nz[0] + 1) if nz.size else 0,
        "last_nonzero_bin": int(nz[-1] + 1) if nz.size else 0,
        "sum": _finite_float(np.sum(arr, dtype=float)),
        "abs_sum": _finite_float(np.sum(np.abs(arr), dtype=float)),
        "min": _finite_float(np.min(arr)) if arr.size else 0.0,
        "max": _finite_float(np.max(arr)) if arr.size else 0.0,
    }
    for bin_one_based in bins:
        out[f"value_bin_{int(bin_one_based)}"] = _value_at_one_based(arr, int(bin_one_based))
    return out


def _phase_array_rows(state: Any, phase: str, *, note: str = "", phase_index: int = 0) -> list[dict[str, Any]]:
    workspace = state.control.get("radial_transfer_workspace")
    if workspace is None:
        return []
    try:
        ncn2 = int(state.control.get("ncn2", len(np.asarray(state.radiation.epi).reshape(-1))))
    except Exception:
        ncn2 = 0
    arrays: tuple[tuple[str, str, Any], ...] = (
        ("opakc", "opakc", getattr(workspace, "opakc", ())),
        ("opakcont", "opakcont", getattr(workspace, "opakcont", ())),
        ("rccemis[0]", "rccemis(1) / fstepr4 emis out", getattr(workspace, "rccemis", np.zeros((2, 0)))[0]),
        ("rccemis[1]", "rccemis(2) / fstepr4 emis in", getattr(workspace, "rccemis", np.zeros((2, 0)))[1]),
        ("brcems", "brcems", getattr(getattr(workspace, "emissivity", None), "base", None).brcems if getattr(getattr(workspace, "emissivity", None), "base", None) is not None else ()),
        ("zrems[2]", "zrems(3)", getattr(workspace, "zrems", np.zeros((5, 0)))[2]),
        ("zrems[4]", "zrems(5)", getattr(workspace, "zrems", np.zeros((5, 0)))[4]),
        ("dpthc[0]", "dpthc(1) / fstepr4 fwd dpth", getattr(workspace, "dpthc", np.zeros((2, 0)))[0]),
    )
    if phase_index <= 0:
        phase_index = len(state.outputs.get(PHASE_SNAPSHOT_KEY, ())) + 1
    base = {
        "phase_index": int(phase_index),
        "phase": str(phase),
        "note": str(note),
        "pass_index": _finite_int(getattr(state.transfer, "pass_index", 0)),
        "zone_index": _finite_int(getattr(state.transfer, "zone_index", 0)),
        "direction": _finite_int(getattr(state.transfer, "direction", 0)),
        "radius_cm": _finite_float(getattr(state.transfer, "radius", 0.0)),
        "radial_depth_cm": _finite_float(getattr(state.transfer, "radial_depth", 0.0)),
        "step_size_cm": _finite_float(getattr(state.transfer, "step_size", 0.0)),
        "column_cm2": _finite_float(getattr(state.transfer, "column", 0.0)),
        "temperature_K": _finite_float(getattr(state.plasma, "temperature", 0.0)),
        "electron_fraction_xee": _finite_float(getattr(state.plasma, "xee", 0.0)),
        "hydrogen_density_cm3": _finite_float(getattr(state.plasma, "xpx", 0.0)),
        "ncn2": int(ncn2),
    }
    rows: list[dict[str, Any]] = []
    for array_name, source_name, values in arrays:
        row = dict(base)
        row.update({
            "array_name": array_name,
            "source_array": source_name,
        })
        try:
            row.update(summarize_array(values))
        except Exception as exc:
            row.update({
                "nonzero_count": 0,
                "first_nonzero_bin": 0,
                "last_nonzero_bin": 0,
                "summary_error": str(exc),
            })
        rows.append(row)
    return rows


def append_phase_snapshot(state: Any, phase: str, *, note: str = "") -> None:
    """Append compact per-array summaries for one source-order phase."""
    if not bool(state.control.get("continuum_phase_snapshot_enabled", True)):
        return
    phase_index = int(state.control.get("continuum_phase_snapshot_index", 0)) + 1
    state.control["continuum_phase_snapshot_index"] = phase_index
    rows = _phase_array_rows(state, phase, note=note, phase_index=phase_index)
    if rows:
        state.outputs.setdefault(PHASE_SNAPSHOT_KEY, []).extend(rows)


def _diagnostics_mapping(result: Any) -> Mapping[str, Any]:
    diagnostics = getattr(result, "diagnostics", {})
    return diagnostics if isinstance(diagnostics, Mapping) else {}


def _nested_phint53_diagnostics(diagnostics: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = diagnostics.get("phint53_diagnostics", {})
    return nested if isinstance(nested, Mapping) else {}


def _array_diag_summary(diagnostics: Mapping[str, Any], key: str) -> dict[str, Any]:
    values = diagnostics.get(key)
    if values is None:
        return {
            f"{key}_present": False,
            f"{key}_nonzero_count": 0,
            f"{key}_first_nonzero_bin": 0,
            f"{key}_last_nonzero_bin": 0,
            f"{key}_sum": 0.0,
        }
    summary = summarize_array(values)
    out = {
        f"{key}_present": True,
        f"{key}_nonzero_count": int(summary["nonzero_count"]),
        f"{key}_first_nonzero_bin": int(summary["first_nonzero_bin"]),
        f"{key}_last_nonzero_bin": int(summary["last_nonzero_bin"]),
        f"{key}_sum": _finite_float(summary["sum"]),
        f"{key}_abs_sum": _finite_float(summary["abs_sum"]),
    }
    for bin_one_based in DIAGNOSTIC_BINS_ONE_BASED:
        out[f"{key}_value_bin_{int(bin_one_based)}"] = _finite_float(
            summary.get(f"value_bin_{int(bin_one_based)}", 0.0)
        )
    return out


def append_ucalc_continuum_side_effect_diagnostic(
    context: Any,
    result: Any,
    *,
    ion: Any,
    record: int,
    ptmp1: float,
    ptmp2: float,
    abund1: float,
    abund2: float,
) -> None:
    """Append one row for a UCalc result carrying continuum side-effect arrays."""
    if not bool(getattr(context, "ucalc_continuum_side_effect_diagnostics_enabled", False)):
        return
    diagnostics = _diagnostics_mapping(result)
    side_keys = ("opakc_cm^-1", "opakcont_cm^-1", "rccemis_inward", "rccemis_outward")
    if not any(key in diagnostics for key in side_keys):
        return
    nested = _nested_phint53_diagnostics(diagnostics)
    nb1 = diagnostics.get("nb1_1based", nested.get("nb1_1based", 0))
    klmax = diagnostics.get("klmax_1based", nested.get("klmax_1based", 0))
    mapping_status = diagnostics.get("mapping_status", nested.get("mapping_status", nested.get("status", "")))
    mapping_base_status = diagnostics.get("mapping_base_status", nested.get("mapping_base_status", ""))
    threshold = diagnostics.get("threshold_eV", nested.get("threshold_eV", 0.0))
    rnist = diagnostics.get("rnist", nested.get("rnist", 0.0))
    lfast = diagnostics.get("lfast", nested.get("lfast", getattr(context, "lfast", 0)))
    expected_full_grid_nb1 = diagnostics.get("expected_full_grid_nb1", nested.get("expected_full_grid_nb1", 0))
    nb1_full_grid_delta = diagnostics.get("type53_nb1_full_grid_delta", nested.get("type53_nb1_full_grid_delta", 0))
    full_grid_mismatch = diagnostics.get("type53_full_grid_mismatch", nested.get("type53_full_grid_mismatch", False))
    full_grid_check_status = diagnostics.get("type53_full_grid_check_status", nested.get("type53_full_grid_check_status", ""))
    full_grid_tolerance_bins = diagnostics.get("type53_full_grid_tolerance_bins", nested.get("type53_full_grid_tolerance_bins", 0))
    type53_grid_policy = diagnostics.get("type53_grid_policy", nested.get("type53_grid_policy", ""))
    type53_grid_source = diagnostics.get("type53_grid_source", nested.get("type53_grid_source", ""))
    type53_full_grid_points = diagnostics.get("type53_full_grid_points", nested.get("type53_full_grid_points", 0))
    type53_reduced_grid_points = diagnostics.get("type53_reduced_grid_points", nested.get("type53_reduced_grid_points", 0))
    row: dict[str, Any] = {
        "calc_emis_all_call": _finite_int(getattr(context, "diagnostic_call_index", 0)),
        "pass_index": _finite_int(getattr(context, "diagnostic_pass_index", 0)),
        "zone_index": _finite_int(getattr(context, "diagnostic_zone_index", 0)),
        "record": int(record),
        "data_type": _finite_int(getattr(result, "data_type", 0)),
        "rate_type": _finite_int(getattr(result, "rate_type", 0)),
        "status": str(getattr(getattr(result, "status", ""), "value", getattr(result, "status", ""))),
        "ready": bool(getattr(result, "ready", False)),
        "ion": f"Z={_finite_int(getattr(ion, 'element_z', 0))} stage={_finite_int(getattr(ion, 'ion_stage', 0))} ion_index={_finite_int(getattr(ion, 'ion_index', 0))}",
        "element_z": _finite_int(getattr(ion, "element_z", 0)),
        "ion_stage": _finite_int(getattr(ion, "ion_stage", 0)),
        "ion_index": _finite_int(getattr(ion, "ion_index", 0)),
        "threshold_eV": _finite_float(threshold),
        "nb1": _finite_int(nb1),
        "klmax": _finite_int(klmax),
        "abund1": _finite_float(abund1),
        "abund2": _finite_float(abund2),
        "ptmp1": _finite_float(ptmp1),
        "ptmp2": _finite_float(ptmp2),
        "rnist": _finite_float(rnist),
        "lfast": _finite_int(lfast),
        "mapping_status": str(mapping_status),
        "mapping_base_status": str(mapping_base_status),
        "expected_full_grid_nb1": _finite_int(expected_full_grid_nb1),
        "nb1_full_grid_delta": _finite_int(nb1_full_grid_delta),
        "full_grid_mismatch": bool(full_grid_mismatch),
        "full_grid_check_status": str(full_grid_check_status),
        "full_grid_tolerance_bins": _finite_int(full_grid_tolerance_bins),
        "type53_grid_policy": str(type53_grid_policy),
        "type53_grid_source": str(type53_grid_source),
        "type53_full_grid_points": _finite_int(type53_full_grid_points),
        "type53_reduced_grid_points": _finite_int(type53_reduced_grid_points),
        "source_branch": str(diagnostics.get("source_branch", "")),
    }
    for key in side_keys:
        row.update(_array_diag_summary(diagnostics, key))
    # User-facing aliases using fstepr4/source row names.
    row["opakc_nonzero_count"] = row.get("opakc_cm^-1_nonzero_count", 0)
    row["first_nonzero_opakc_bin"] = row.get("opakc_cm^-1_first_nonzero_bin", 0)
    row["last_nonzero_opakc_bin"] = row.get("opakc_cm^-1_last_nonzero_bin", 0)
    row["rccemis1_nonzero_count"] = row.get("rccemis_inward_nonzero_count", 0)
    row["first_nonzero_rccemis1_bin"] = row.get("rccemis_inward_first_nonzero_bin", 0)
    row["last_nonzero_rccemis1_bin"] = row.get("rccemis_inward_last_nonzero_bin", 0)
    row["rccemis2_nonzero_count"] = row.get("rccemis_outward_nonzero_count", 0)
    row["first_nonzero_rccemis2_bin"] = row.get("rccemis_outward_first_nonzero_bin", 0)
    row["last_nonzero_rccemis2_bin"] = row.get("rccemis_outward_last_nonzero_bin", 0)
    rows = getattr(context, "ucalc_continuum_side_effect_diagnostics", None)
    if rows is None:
        rows = []
        setattr(context, "ucalc_continuum_side_effect_diagnostics", rows)
    rows.append(row)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(str(key))
                seen.add(str(key))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _json_safe(row.get(key, "")) for key in fields})


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_json_safe(dict(row)), sort_keys=True) + "\n")


def write_continuum_diagnostics(state: Any, out_dir: str | Path) -> dict[str, str]:
    """Write phase-snapshot and UCalc side-effect diagnostics, if present."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    products: dict[str, str] = {}
    phase_rows = list(state.outputs.get(PHASE_SNAPSHOT_KEY, ()))
    if phase_rows:
        phase_csv = out / "xstar_atomic_phase_snapshots.csv"
        phase_jsonl = out / "xstar_atomic_phase_snapshots.jsonl"
        _write_csv(phase_csv, phase_rows)
        _write_jsonl(phase_jsonl, phase_rows)
        products["phase_snapshots_csv"] = str(phase_csv)
        products["phase_snapshots_jsonl"] = str(phase_jsonl)
    ucalc_rows = list(state.outputs.get(UCALC_SIDE_EFFECT_KEY, ()))
    if ucalc_rows:
        ucalc_csv = out / "xstar_atomic_ucalc_continuum_side_effects.csv"
        ucalc_jsonl = out / "xstar_atomic_ucalc_continuum_side_effects.jsonl"
        _write_csv(ucalc_csv, ucalc_rows)
        _write_jsonl(ucalc_jsonl, ucalc_rows)
        products["ucalc_side_effects_csv"] = str(ucalc_csv)
        products["ucalc_side_effects_jsonl"] = str(ucalc_jsonl)
    if products:
        summary = {
            "phase_snapshot_rows": len(phase_rows),
            "ucalc_continuum_side_effect_rows": len(ucalc_rows),
            "diagnostic_bins_one_based": list(DIAGNOSTIC_BINS_ONE_BASED),
            "products": dict(products),
        }
        summary_path = out / "xstar_atomic_continuum_diagnostics_summary.json"
        summary_path.write_text(json.dumps(_json_safe(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        products["summary_json"] = str(summary_path)
    return products
