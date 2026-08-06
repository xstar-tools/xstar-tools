"""Diagnostic-only radial checkpoint capture for 0.6.48.12.3.45.2.

The hook is inert unless XSTAR_V0648123452_DIAGNOSTIC_DIR is set.  It is
strictly observational: arrays are copied for serialization and no simulation
state is mutated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def _enabled_dir() -> Path | None:
    raw = os.environ.get("XSTAR_V0648123452_DIAGNOSTIC_DIR", "").strip()
    return Path(raw).resolve() if raw else None


def _target_zones() -> set[int]:
    raw = os.environ.get("XSTAR_V0648123452_ZONES", "2,3")
    out: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(int(token))
        except ValueError:
            pass
    return out or {2, 3}


def _target_lines() -> tuple[int, ...]:
    raw = os.environ.get("XSTAR_V0648123452_TARGET_LINES", "508,515")
    vals: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        try:
            value = int(token)
        except ValueError:
            continue
        if value > 0:
            vals.append(value)
    return tuple(dict.fromkeys(vals))


def _array_hash(arr: Any) -> str:
    a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
    return hashlib.sha256(a.view(np.uint8)).hexdigest()


def _array_summary(name: str, arr: Any) -> dict[str, Any]:
    a = np.asarray(arr, dtype=np.float64)
    finite = a[np.isfinite(a)]
    return {
        "name": name,
        "shape": list(a.shape),
        "sha256_float64": _array_hash(a),
        "nonzero": int(np.count_nonzero(a)),
        "sum": float(np.sum(finite)) if finite.size else 0.0,
        "max_abs": float(np.max(np.abs(finite))) if finite.size else 0.0,
    }


def _write_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _append_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file() and path.stat().st_size > 0
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    # Existing file has a stable schema in this diagnostic package.
    if exists:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            old = next(reader, [])
        if old:
            fields = old
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def _workspace_arrays(state: Any) -> dict[str, np.ndarray]:
    workspace = state.control.get("radial_transfer_workspace")
    if workspace is None:
        return {}
    names = (
        "zrems", "zremso", "dpthc", "dpthcont", "tau0", "tauc",
        "elum", "elumo", "elumab", "elumabo", "opakc", "opakcont",
        "oplin_physical", "opakab_physical",
    )
    out: dict[str, np.ndarray] = {}
    for name in names:
        try:
            value = getattr(workspace, name)
            out[name] = np.asarray(value, dtype=np.float64).copy()
        except Exception:
            continue
    try:
        out["populations"] = np.asarray(state.plasma.populations, dtype=np.float64).copy()
    except Exception:
        pass
    return out


def _line_metadata(state: Any) -> dict[int, Any]:
    metadata = state.control.get("output_atomic_metadata")
    rows = getattr(metadata, "lines", ()) if metadata is not None else ()
    return {int(getattr(row, "line_index", 0)): row for row in rows}


def _line_rows(state: Any, phase: str, arrays: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    meta = _line_metadata(state)
    zone = int(getattr(state.transfer, "zone_index", 0) or 0)
    pas = int(getattr(state.transfer, "pass_index", 0) or 0)
    direction = int(getattr(state.transfer, "direction", 0) or 0)
    rows: list[dict[str, Any]] = []
    for line_index in _target_lines():
        i = line_index - 1
        row = meta.get(line_index)
        def val(name: str, plane: int) -> float | None:
            arr = arrays.get(name)
            if arr is None or arr.ndim < 2 or plane >= arr.shape[0] or i < 0 or i >= arr.shape[1]:
                return None
            return float(arr[plane, i])
        rows.append({
            "pass_index": pas,
            "zone_index": zone,
            "direction": direction,
            "phase": phase,
            "line_index": line_index,
            "ion_label": "" if row is None else str(getattr(row, "ion_label", "")),
            "wavelength_angstrom": "" if row is None else float(getattr(row, "wavelength_angstrom", 0.0)),
            "source_record": "" if row is None else int(getattr(row, "source_record", 0)),
            "elum_in": val("elum", 0),
            "elum_out": val("elum", 1),
            "elumo_in": val("elumo", 0),
            "elumo_out": val("elumo", 1),
            "tau0_in": val("tau0", 0),
            "tau0_out": val("tau0", 1),
        })
    return rows


def checkpoint(state: Any, *, phase: str) -> None:
    out = _enabled_dir()
    if out is None:
        return
    zone = int(getattr(state.transfer, "zone_index", 0) or 0)
    if zone not in _target_zones():
        return
    pas = int(getattr(state.transfer, "pass_index", 0) or 0)
    direction = int(getattr(state.transfer, "direction", 0) or 0)
    arrays = _workspace_arrays(state)
    scalar = {
        "schema": "xstar-tools-v0648123452-radial-checkpoint-v1",
        "pass_index": pas,
        "zone_index": zone,
        "direction": direction,
        "phase": str(phase),
        "radius_cm": float(getattr(state.transfer, "radius", 0.0) or 0.0),
        "radial_depth_cm": float(getattr(state.transfer, "radial_depth", 0.0) or 0.0),
        "column_cm2": float(getattr(state.transfer, "column", 0.0) or 0.0),
        "step_size_cm": float(getattr(state.transfer, "step_size", 0.0) or 0.0),
        "temperature_K": float(getattr(state.plasma, "temperature", 0.0) or 0.0),
        "electron_fraction_xee": float(getattr(state.plasma, "xee", 0.0) or 0.0),
        "hydrogen_density_cm3": float(getattr(state.plasma, "xpx", 0.0) or 0.0),
        "xi": float(state.control.get("xi", 0.0) or 0.0),
        "zeta": float(state.control.get("zeta", 0.0) or 0.0),
        "thermal_heating": float(getattr(state.thermal, "heating", 0.0) or 0.0),
        "thermal_cooling": float(getattr(state.thermal, "cooling", 0.0) or 0.0),
        "thermal_residual": float(getattr(state.thermal, "residual", 0.0) or 0.0),
        "control_p": float(state.control.get("p", 0.0) or 0.0),
        "control_httot": float(state.control.get("httot", 0.0) or 0.0),
        "control_cltot": float(state.control.get("cltot", 0.0) or 0.0),
        "control_hmctot": float(state.control.get("hmctot", 0.0) or 0.0),
        "control_ntotit": int(state.control.get("ntotit", 0) or 0),
        "arrays": [_array_summary(name, arr) for name, arr in arrays.items()],
    }
    out.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out / "checkpoint_summary.jsonl", scalar)
    _append_csv(out / "selected_lines.csv", _line_rows(state, str(phase), arrays))

    # Save full numerical arrays at these deliberately sparse source-order
    # boundaries so a later comparator can locate the first differing cell.
    stem = f"p{pas:02d}_z{zone:03d}_{str(phase)}"
    if arrays:
        np.savez_compressed(out / f"{stem}.npz", **arrays)

    if str(phase) == "post_xstarcalc":
        terminal = list(state.control.get("dsec_terminal_summary", []))
        trajectory = list(state.control.get("dsec_residual_trajectory_summary", []))
        _write_jsonl(out / "dsec_checkpoint.jsonl", {
            "pass_index": pas,
            "zone_index": zone,
            "phase": str(phase),
            "terminal": terminal[-1] if terminal else None,
            "trajectory_tail": trajectory[-32:],
            "note": "electron_fraction is the DSEC trial/state value; elcter is retained separately in the trajectory/terminal summary",
        })
