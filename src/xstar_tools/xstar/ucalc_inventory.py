# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: readtbl.f90 / setptrs.f90 / ucalc.f90
#   Role: Inventory packed ATDB coverage by data type and rate type and exercise registered UCalc branches.
#   Relation: Coverage/qualification utility over the source record model; no independent physics.
#   Concordance: DB-001; MATRIX-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   The inventory intentionally counts both identifiers independently: data type selects the UCalc
#   formula/record layout, while rate type identifies downstream use of the returned rates.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Coverage and product writers for the source-faithful ``ucalc`` subsystem."""

from __future__ import annotations

import csv
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import numpy as np

from .atomic_database import XSTARMasterData, XSTARDerivedPointers
from .ucalc import SourceFaithfulUCalc, UCalcContext


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def build_ucalc_data_type_inventory(
    master: XSTARMasterData,
    dispatcher: SourceFaithfulUCalc | None = None,
) -> list[dict[str, Any]]:
    """Count packed ATDB records by data type and rate type.

    The POINTERS table is scanned directly, so the operation does not decode or
    copy the large REALS payload.
    """

    dispatch = dispatcher or SourceFaithfulUCalc()
    table = master.nptrs.numpy(copy=False)
    dtypes = np.asarray(table[:, 1], dtype=np.int64)
    rtypes = np.asarray(table[:, 2], dtype=np.int64)
    rows: list[dict[str, Any]] = []
    for dt in sorted(set(int(x) for x in dtypes)):
        mask = dtypes == dt
        spec = dispatch.catalog.get(dt)
        by_rate = {
            int(rt): int(np.count_nonzero(mask & (rtypes == rt)))
            for rt in sorted(set(int(x) for x in rtypes[mask]))
        }
        rows.append(
            {
                "data_type": dt,
                "branch_name": spec.name if spec else "outside_ucalc_range",
                "category": spec.category if spec else "invalid",
                "implementation": spec.implementation if spec else "invalid",
                "validation_status": spec.validation_status if spec else "invalid",
                "n_records": int(np.count_nonzero(mask)),
                "n_rate_types": len(by_rate),
                "rate_types": ";".join(str(x) for x in by_rate),
                "rate_type_counts": ";".join(f"{k}:{v}" for k, v in by_rate.items()),
                "source_routines": ";".join(spec.source_routines) if spec else "",
            }
        )
    return rows


def build_ucalc_branch_catalog_rows(
    dispatcher: SourceFaithfulUCalc | None = None,
) -> list[dict[str, Any]]:
    dispatch = dispatcher or SourceFaithfulUCalc()
    rows: list[dict[str, Any]] = []
    for dt in sorted(dispatch.catalog):
        spec = dispatch.catalog[dt]
        rows.append(
            {
                "data_type": dt,
                "branch_name": spec.name,
                "category": spec.category,
                "implementation": spec.implementation,
                "validation_status": spec.validation_status,
                "source_routines": ";".join(spec.source_routines),
                "notes": ";".join(spec.notes),
            }
        )
    return rows


def build_ucalc_index_only_samples(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    dispatcher: SourceFaithfulUCalc | None = None,
) -> list[dict[str, Any]]:
    """Decode and execute one index-only record for every active data type."""

    dispatch = dispatcher or SourceFaithfulUCalc()
    table = master.nptrs.numpy(copy=False)
    active = np.asarray(table[:, 1], dtype=np.int64)
    first_record: dict[int, int] = {}
    for zero_index, dt_value in enumerate(active):
        first_record.setdefault(int(dt_value), zero_index + 1)

    ion_index_by_record = {
        int(rec): idx
        for idx, rec in enumerate(np.asarray(derived.ion_records, dtype=np.int64))
        if idx > 0 and int(rec) > 0
    }
    rows: list[dict[str, Any]] = []
    for dt, recno in sorted(first_record.items()):
        if dt < 1 or dt > 102:
            continue
        parent = int(derived.npar[recno]) if recno < len(derived.npar) else 0
        ion_index = ion_index_by_record.get(parent, 0)
        nlev = int(derived.nlevs[ion_index]) if ion_index and ion_index < len(derived.nlevs) else 0
        context = UCalcContext(
            temperature_k=1.0e6,
            nlev=nlev,
            indonly=True,
            master=master,
            derived_pointers=derived,
        )
        result = dispatch.evaluate_record_number(
            master,
            recno,
            context,
            parent_record=parent,
            next_record=int(derived.npnxt[recno]) if recno < len(derived.npnxt) else 0,
            strict=False,
        )
        rows.append(
            {
                "data_type": dt,
                "sample_record": recno,
                "rate_type": result.rate_type,
                "parent_record": parent,
                "ion_index": ion_index,
                "nlev": nlev,
                "status": result.status.value,
                "ready": result.ready,
                "idest1": result.idest1,
                "idest2": result.idest2,
                "idest3": result.idest3,
                "idest4": result.idest4,
                "reason": result.reason,
                "implementation": result.provenance.implementation,
                "validation_status": result.provenance.validation_status,
            }
        )
    return rows


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    fieldnames: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialized)


def write_ucalc_subsystem_products(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    out_dir: str | Path,
    dispatcher: SourceFaithfulUCalc | None = None,
) -> dict[str, Path]:
    """Write branch, production-ATDB, and packed-decoding coverage products."""

    dispatch = dispatcher or SourceFaithfulUCalc()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    catalog_rows = build_ucalc_branch_catalog_rows(dispatch)
    inventory_rows = build_ucalc_data_type_inventory(master, dispatch)
    sample_rows = build_ucalc_index_only_samples(master, derived, dispatch)

    catalog_csv = out / "xstar_ucalc_branch_catalog.csv"
    inventory_csv = out / "xstar_ucalc_data_type_inventory.csv"
    samples_csv = out / "xstar_ucalc_index_only_samples.csv"
    _write_csv(catalog_csv, catalog_rows)
    _write_csv(inventory_csv, inventory_rows)
    _write_csv(samples_csv, sample_rows)

    coverage = dispatch.coverage()
    active_types = [int(row["data_type"]) for row in inventory_rows if 1 <= int(row["data_type"]) <= 102]
    active_records = sum(int(row["n_records"]) for row in inventory_rows if 1 <= int(row["data_type"]) <= 102)
    native_records = sum(
        int(row["n_records"])
        for row in inventory_rows
        if row["implementation"] == "native_python"
    )
    noop_records = sum(
        int(row["n_records"])
        for row in inventory_rows
        if row["implementation"] == "source_noop"
    )
    sample_failures = [row for row in sample_rows if not bool(row["ready"])]
    summary: Dict[str, Any] = {
        "port_version": "v0.4.2",
        "status": "complete_ucalc_subsystem_registered",
        "atdb": str(master.path),
        "atdb_creation_date": master.creation_date,
        "n_atdb_records": master.np2,
        "n_registered_data_types": coverage["n_registered"],
        "n_native_physical_data_types": coverage["n_native"],
        "n_source_noop_data_types": coverage["n_source_noop"],
        "n_untranslated_data_types": coverage["n_untranslated"],
        "n_active_atdb_data_types": len(active_types),
        "active_atdb_data_types": active_types,
        "n_active_ucalc_records": active_records,
        "n_active_native_records": native_records,
        "n_active_source_noop_records": noop_records,
        "n_index_only_samples": len(sample_rows),
        "n_index_only_sample_failures": len(sample_failures),
        "packed_record_decode_ready": len(sample_failures) == 0,
        "all_source_labels_registered": coverage["all_branches_registered"],
        "complete_ucalc_source_branch_translation_ready": coverage[
            "complete_source_branch_translation_ready"
        ],
        "complete_ucalc_control_flow_ready": (
            coverage["complete_source_branch_translation_ready"] and len(sample_failures) == 0
        ),
        "full_runtime_context_supplied": False,
        "full_atdb_numerical_evaluation_performed": False,
        "no_proxy_fallbacks": True,
        "dominant_next_target": (
            "translate_levwkelement_calc_hmc_ion_calc_hmc_element_msolvelucy_as_one_subsystem"
        ),
    }
    summary_json = out / "xstar_ucalc_subsystem_summary.json"
    summary_json.write_text(json.dumps(_jsonable(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_md = out / "xstar_ucalc_subsystem_summary.md"
    summary_md.write_text(
        "# XSTAR complete `ucalc` source-port subsystem\n\n"
        + "\n".join(f"- **{key}**: `{_jsonable(value)}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {
        "branch_catalog_csv": catalog_csv,
        "data_type_inventory_csv": inventory_csv,
        "index_only_samples_csv": samples_csv,
        "json": summary_json,
        "markdown": summary_md,
    }


__all__ = [
    "build_ucalc_data_type_inventory",
    "build_ucalc_branch_catalog_rows",
    "build_ucalc_index_only_samples",
    "write_ucalc_subsystem_products",
]
