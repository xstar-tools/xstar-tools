"""Compact active-ATDB export for modular C++ backends.

The export intentionally preserves one-based XSTAR indices while packing only
records owned by active elements/ions.  It is a bridge format for Python-driven
Athena++ post-processing plus shared-library C++ kernels.  The arrays are
source-faithful metadata only; v0.5.54 adds Mg record_type=7 compact subsets used by the first C++ rates kernel; source-faithful Python remains the physics reference path.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .active_subsets import ActiveATDBSubset, build_active_atdb_subset


@dataclass(frozen=True)
class CompactATDBExportResult:
    path: Path
    summary_path: Path | None
    n_active_elements: int
    n_active_ions: int
    n_active_levels: int
    n_active_lines: int
    n_active_continua: int
    n_active_rate_records: int
    active_element_z: tuple[int, ...]
    schema_version: int = 2

    def as_dict(self) -> dict[str, Any]:
        data = dict(asdict(self))
        data["path"] = str(self.path)
        data["summary_path"] = None if self.summary_path is None else str(self.summary_path)
        return data


def _record_headers(master: Any, records: Sequence[int] | np.ndarray) -> np.ndarray:
    recs = np.asarray(records, dtype=np.int64).reshape(-1)
    out = np.zeros((recs.size, 11), dtype=np.int64)
    for row, rec in enumerate(recs.tolist()):
        if int(rec) <= 0:
            continue
        h = master.header(int(rec))
        out[row, :] = [
            int(h.recno), int(h.raw_pointer), int(h.data_type), int(h.rate_type), int(h.continuation),
            int(h.nreal), int(h.nint), int(h.nchar), int(h.real_ptr), int(h.int_ptr), int(h.char_ptr),
        ]
    return out


def _parent_ion_index(derived: Any, subset: ActiveATDBSubset, recno: int) -> int:
    npar = np.asarray(getattr(derived, "npar", ()), dtype=np.int64).reshape(-1)
    if int(recno) <= 0 or int(recno) >= npar.size:
        return 0
    ion_rec = int(npar[int(recno)])
    return int(subset.ion_record_to_index.get(ion_rec, 0))


def _line_rows(master: Any, derived: Any, subset: ActiveATDBSubset) -> tuple[np.ndarray, np.ndarray]:
    line_indices = np.asarray(subset.line_indices, dtype=np.int64).reshape(-1)
    nplin = np.asarray(getattr(derived, "nplin", ()), dtype=np.int64).reshape(-1)
    ion_z = np.asarray(getattr(derived, "ion_element_z", ()), dtype=np.int64).reshape(-1)
    ion_stage = np.asarray(getattr(derived, "ion_stage", ()), dtype=np.int64).reshape(-1)
    rows = np.zeros((line_indices.size, 9), dtype=np.int64)
    int_preview = np.zeros((line_indices.size, 8), dtype=np.int64)
    for row, line_index in enumerate(line_indices.tolist()):
        rec = int(nplin[int(line_index)]) if 0 < int(line_index) < nplin.size else 0
        ion_index = _parent_ion_index(derived, subset, rec)
        ints = master.record_integers(rec, dtype=np.int64) if rec > 0 else np.asarray([], dtype=np.int64)
        if ints.size:
            int_preview[row, : min(8, ints.size)] = ints[: min(8, ints.size)]
        rows[row, :] = [
            int(line_index), rec, ion_index,
            int(ion_z[ion_index]) if 0 < ion_index < ion_z.size else 0,
            int(ion_stage[ion_index]) if 0 < ion_index < ion_stage.size else 0,
            int(ints[0]) if ints.size > 0 else 0,
            int(ints[1]) if ints.size > 1 else 0,
            int(ints[-2]) if ints.size > 1 else 0,
            int(ints[-1]) if ints.size > 0 else 0,
        ]
    return rows, int_preview


def _continuum_rows(master: Any, derived: Any, subset: ActiveATDBSubset) -> tuple[np.ndarray, np.ndarray]:
    cont_indices = np.asarray(subset.continuum_indices, dtype=np.int64).reshape(-1)
    npcon = np.asarray(getattr(derived, "npcon", ()), dtype=np.int64).reshape(-1)
    ion_z = np.asarray(getattr(derived, "ion_element_z", ()), dtype=np.int64).reshape(-1)
    ion_stage = np.asarray(getattr(derived, "ion_stage", ()), dtype=np.int64).reshape(-1)
    rows = np.zeros((cont_indices.size, 9), dtype=np.int64)
    int_preview = np.zeros((cont_indices.size, 8), dtype=np.int64)
    for row, continuum_index in enumerate(cont_indices.tolist()):
        rec = int(npcon[int(continuum_index)]) if 0 < int(continuum_index) < npcon.size else 0
        ion_index = _parent_ion_index(derived, subset, rec)
        ints = master.record_integers(rec, dtype=np.int64) if rec > 0 else np.asarray([], dtype=np.int64)
        if ints.size:
            int_preview[row, : min(8, ints.size)] = ints[: min(8, ints.size)]
        rows[row, :] = [
            int(continuum_index), rec, ion_index,
            int(ion_z[ion_index]) if 0 < ion_index < ion_z.size else 0,
            int(ion_stage[ion_index]) if 0 < ion_index < ion_stage.size else 0,
            int(ints[0]) if ints.size > 0 else 0,
            int(ints[1]) if ints.size > 1 else 0,
            int(ints[-2]) if ints.size > 1 else 0,
            int(ints[-1]) if ints.size > 0 else 0,
        ]
    return rows, int_preview


def _level_rows(derived: Any, subset: ActiveATDBSubset) -> np.ndarray:
    ion_indices = np.asarray(subset.ion_indices, dtype=np.int64).reshape(-1)
    npilev = np.asarray(getattr(derived, "npilev", ()), dtype=np.int64)
    nlevs = np.asarray(getattr(derived, "nlevs", ()), dtype=np.int64).reshape(-1)
    level_record_by_global = np.asarray(getattr(derived, "level_record_by_global_index", ()), dtype=np.int64).reshape(-1)
    ion_z = np.asarray(getattr(derived, "ion_element_z", ()), dtype=np.int64).reshape(-1)
    ion_stage = np.asarray(getattr(derived, "ion_stage", ()), dtype=np.int64).reshape(-1)
    rows: list[tuple[int, int, int, int, int, int]] = []
    if npilev.ndim != 2:
        return np.zeros((0, 6), dtype=np.int64)
    for ion_index in ion_indices.tolist():
        ii = int(ion_index)
        if ii <= 0 or ii >= npilev.shape[1] or ii >= nlevs.size:
            continue
        nlev = int(nlevs[ii])
        for local in range(1, min(nlev + 1, npilev.shape[0])):
            global_index = int(npilev[local, ii])
            if global_index <= 0:
                continue
            rec = int(level_record_by_global[global_index]) if global_index < level_record_by_global.size else 0
            rows.append((
                global_index, rec, ii, local,
                int(ion_z[ii]) if ii < ion_z.size else 0,
                int(ion_stage[ii]) if ii < ion_stage.size else 0,
            ))
    return np.asarray(rows, dtype=np.int64).reshape((-1, 6)) if rows else np.zeros((0, 6), dtype=np.int64)


def _rate_record_rows(master: Any, derived: Any, subset: ActiveATDBSubset) -> np.ndarray:
    ion_indices = np.asarray(subset.ion_indices, dtype=np.int64).reshape(-1)
    npfi = np.asarray(getattr(derived, "npfi", ()), dtype=np.int64)
    npnxt = np.asarray(getattr(derived, "npnxt", ()), dtype=np.int64).reshape(-1)
    ion_z = np.asarray(getattr(derived, "ion_element_z", ()), dtype=np.int64).reshape(-1)
    ion_stage = np.asarray(getattr(derived, "ion_stage", ()), dtype=np.int64).reshape(-1)
    rows: list[tuple[int, int, int, int, int, int, int, int, int, int, int, int]] = []
    if npfi.ndim != 2:
        return np.zeros((0, 12), dtype=np.int64)
    max_rate = npfi.shape[0] - 1
    for ion_index in ion_indices.tolist():
        ii = int(ion_index)
        if ii <= 0 or ii >= npfi.shape[1]:
            continue
        for rate_type in range(1, max_rate + 1):
            rec = int(npfi[rate_type, ii])
            guard = 0
            while rec > 0 and rec < npnxt.size:
                h = master.header(rec)
                rows.append((
                    rec, ii,
                    int(ion_z[ii]) if ii < ion_z.size else 0,
                    int(ion_stage[ii]) if ii < ion_stage.size else 0,
                    int(rate_type), int(h.data_type), int(h.rate_type), int(h.continuation),
                    int(h.nreal), int(h.nint), int(h.real_ptr), int(h.int_ptr),
                ))
                nxt = int(npnxt[rec])
                if nxt == rec:
                    break
                rec = nxt
                guard += 1
                if guard > 1_000_000:
                    raise RuntimeError(f"rate linked-list guard exceeded for ion {ii} rate {rate_type}")
    if not rows:
        return np.zeros((0, 12), dtype=np.int64)
    data = np.asarray(rows, dtype=np.int64).reshape((-1, 12))
    order = np.lexsort((data[:, 0], data[:, 4], data[:, 1]))
    return data[order]



def _mg_type7_payload_rows(master: Any, rate_record_rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return compact payload previews for Mg header rate_type=7 records."""
    if rate_record_rows.size == 0:
        return (
            np.zeros((0, 12), dtype=np.int64),
            np.zeros((0, 16), dtype=np.int64),
            np.zeros((0, 16), dtype=np.float64),
        )
    data = np.asarray(rate_record_rows, dtype=np.int64).reshape((-1, 12))
    mask = (data[:, 2] == 12) & (data[:, 6] == 7)
    rows = data[mask].copy()
    int_preview = np.zeros((rows.shape[0], 16), dtype=np.int64)
    real_preview = np.zeros((rows.shape[0], 16), dtype=np.float64)
    for row_idx, rec in enumerate(rows[:, 0].tolist()):
        rec = int(rec)
        if rec <= 0:
            continue
        ints = master.record_integers(rec, dtype=np.int64)
        reals = master.record_reals(rec, dtype=np.float64)
        if ints.size:
            int_preview[row_idx, : min(16, ints.size)] = ints[: min(16, ints.size)]
        if reals.size:
            real_preview[row_idx, : min(16, reals.size)] = reals[: min(16, reals.size)]
    return rows, int_preview, real_preview


def build_compact_active_atdb(
    master: Any,
    derived: Any,
    *,
    active_subset: ActiveATDBSubset | None = None,
    active_element_z: Sequence[int] = (1, 2, 12),
) -> dict[str, Any]:
    subset = active_subset or build_active_atdb_subset(master, derived, active_element_z)
    ion_indices = np.asarray(subset.ion_indices, dtype=np.int64).reshape(-1)
    ion_records = np.asarray(getattr(derived, "ion_records", ()), dtype=np.int64).reshape(-1)
    ion_z = np.asarray(getattr(derived, "ion_element_z", ()), dtype=np.int64).reshape(-1)
    ion_stage = np.asarray(getattr(derived, "ion_stage", ()), dtype=np.int64).reshape(-1)
    nlevs = np.asarray(getattr(derived, "nlevs", ()), dtype=np.int64).reshape(-1)
    ion_rows = np.zeros((ion_indices.size, 5), dtype=np.int64)
    for row, ion_index in enumerate(ion_indices.tolist()):
        ii = int(ion_index)
        ion_rows[row, :] = [
            ii,
            int(ion_records[ii]) if ii < ion_records.size else 0,
            int(ion_z[ii]) if ii < ion_z.size else 0,
            int(ion_stage[ii]) if ii < ion_stage.size else 0,
            int(nlevs[ii]) if ii < nlevs.size else 0,
        ]

    level_rows = _level_rows(derived, subset)
    line_rows, line_int_preview = _line_rows(master, derived, subset)
    continuum_rows, continuum_int_preview = _continuum_rows(master, derived, subset)
    rate_record_rows = _rate_record_rows(master, derived, subset)
    rate_headers = _record_headers(master, rate_record_rows[:, 0] if rate_record_rows.size else np.zeros(0, dtype=np.int64))
    line_headers = _record_headers(master, line_rows[:, 1] if line_rows.size else np.zeros(0, dtype=np.int64))
    continuum_headers = _record_headers(master, continuum_rows[:, 1] if continuum_rows.size else np.zeros(0, dtype=np.int64))
    mg_type7_rate_record_rows, mg_type7_int_preview, mg_type7_real_preview = _mg_type7_payload_rows(master, rate_record_rows)

    manifest = {
        "schema": "xstar_atomic.compact_active_atdb",
        "schema_version": 2,
        "source_indexing": "one_based_xstar_fortran_indices",
        "active_element_z": list(subset.active_element_z),
        "columns": {
            "ion_rows": ["ion_index", "ion_record", "element_z", "ion_stage", "n_levels"],
            "level_rows": ["global_level_index", "level_record", "ion_index", "local_level", "element_z", "ion_stage"],
            "line_rows": ["line_index", "line_record", "ion_index", "element_z", "ion_stage", "int0", "int1", "int_last_minus_1", "int_last"],
            "continuum_rows": ["continuum_index", "continuum_record", "ion_index", "element_z", "ion_stage", "int0", "int1", "int_last_minus_1", "int_last"],
            "rate_record_rows": ["record", "ion_index", "element_z", "ion_stage", "npfi_rate_type", "data_type", "header_rate_type", "continuation", "nreal", "nint", "real_ptr", "int_ptr"],
            "record_headers": ["record", "raw_pointer", "data_type", "rate_type", "continuation", "nreal", "nint", "nchar", "real_ptr", "int_ptr", "char_ptr"],
            "mg_type7_rate_record_rows": ["record", "ion_index", "element_z", "ion_stage", "npfi_rate_type", "data_type", "header_rate_type", "continuation", "nreal", "nint", "real_ptr", "int_ptr"],
            "mg_type7_int_preview": ["first_16_source_ints"],
            "mg_type7_real_preview": ["first_16_source_reals"],
        },
        "counts": {
            "active_ions": int(ion_rows.shape[0]),
            "active_levels": int(level_rows.shape[0]),
            "active_lines": int(line_rows.shape[0]),
            "active_continua": int(continuum_rows.shape[0]),
            "active_rate_records": int(rate_record_rows.shape[0]),
            "mg_type7_rate_records": int(mg_type7_rate_record_rows.shape[0]),
        },
        "kernel_notes": {
            "v0.5.54": "mg_type7_* arrays are the compact payload preview for libxstar_rates.so; Python still evaluates ucalc formulas before C++ builds matrix/rate terms."
        },
    }
    return {
        "manifest": manifest,
        "subset_summary": subset.as_summary(),
        "active_element_z": np.asarray(subset.active_element_z, dtype=np.int16),
        "ion_rows": ion_rows,
        "level_rows": level_rows,
        "line_rows": line_rows,
        "line_int_preview": line_int_preview,
        "continuum_rows": continuum_rows,
        "continuum_int_preview": continuum_int_preview,
        "rate_record_rows": rate_record_rows,
        "rate_record_headers": rate_headers,
        "line_record_headers": line_headers,
        "continuum_record_headers": continuum_headers,
        "mg_type7_rate_record_rows": mg_type7_rate_record_rows,
        "mg_type7_int_preview": mg_type7_int_preview,
        "mg_type7_real_preview": mg_type7_real_preview,
    }


def export_compact_active_atdb(
    master: Any,
    derived: Any,
    path: str | Path,
    *,
    active_subset: ActiveATDBSubset | None = None,
    active_element_z: Sequence[int] = (1, 2, 12),
    write_summary_json: bool = True,
) -> CompactATDBExportResult:
    """Write compact active ATDB arrays to an NPZ file."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_compact_active_atdb(
        master,
        derived,
        active_subset=active_subset,
        active_element_z=active_element_z,
    )
    manifest = dict(payload["manifest"])
    np.savez_compressed(
        out,
        manifest_json=np.asarray(json.dumps(manifest, sort_keys=True), dtype=np.str_),
        active_element_z=payload["active_element_z"],
        ion_rows=payload["ion_rows"],
        level_rows=payload["level_rows"],
        line_rows=payload["line_rows"],
        line_int_preview=payload["line_int_preview"],
        continuum_rows=payload["continuum_rows"],
        continuum_int_preview=payload["continuum_int_preview"],
        rate_record_rows=payload["rate_record_rows"],
        rate_record_headers=payload["rate_record_headers"],
        line_record_headers=payload["line_record_headers"],
        continuum_record_headers=payload["continuum_record_headers"],
        mg_type7_rate_record_rows=payload["mg_type7_rate_record_rows"],
        mg_type7_int_preview=payload["mg_type7_int_preview"],
        mg_type7_real_preview=payload["mg_type7_real_preview"],
    )
    summary_path: Path | None = None
    if write_summary_json:
        summary_path = out.with_suffix(out.suffix + ".summary.json")
        summary = {
            "path": str(out),
            "manifest": manifest,
            "subset_summary": payload["subset_summary"],
        }
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = manifest["counts"]
    return CompactATDBExportResult(
        path=out,
        summary_path=summary_path,
        n_active_elements=len(tuple(int(z) for z in manifest["active_element_z"])),
        n_active_ions=int(counts["active_ions"]),
        n_active_levels=int(counts["active_levels"]),
        n_active_lines=int(counts["active_lines"]),
        n_active_continua=int(counts["active_continua"]),
        n_active_rate_records=int(counts["active_rate_records"]),
        active_element_z=tuple(int(z) for z in manifest["active_element_z"]),
    )
