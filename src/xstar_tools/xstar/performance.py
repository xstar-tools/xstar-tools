"""Lightweight runtime timing/RSS helpers for memory-sensitive radial runs.

The helpers in this module are intentionally observational.  They do not
change the physics state; they only append compact timing/RSS records to
``state.control['performance_profile']`` and optionally mirror those records to
normal progress output.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import time
from typing import Any, Iterator, MutableMapping


def current_rss_mb() -> float | None:
    """Return current process resident set size in MiB on Linux, else ``None``."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except OSError:
        return None
    return None


def _append_profile(control: MutableMapping[str, Any], record: dict[str, Any]) -> None:
    rows = control.setdefault("performance_profile", [])
    if isinstance(rows, list):
        rows.append(record)


PROFILE_LEVELS = {"none": 0, "summary": 1, "nested": 2, "forensic": 3}


def normalize_profile_level(value: Any) -> str:
    """Normalize profiling level for v0.5.49 timing controls.

    Backward compatibility:
    - True / "1" / "true" -> "summary"
    - False / "0" / "false" / None -> "none"
    """
    if isinstance(value, bool):
        return "summary" if value else "none"
    if value is None:
        return "none"
    text = str(value).strip().lower()
    if text in {"", "0", "false", "off", "no", "none"}:
        return "none"
    if text in {"1", "true", "on", "yes"}:
        return "summary"
    if text in PROFILE_LEVELS:
        return text
    return "summary"


def profile_level(control: MutableMapping[str, Any]) -> str:
    return normalize_profile_level(control.get("profile_components", False))


def profile_level_at_least(control: MutableMapping[str, Any], minimum: str) -> bool:
    current = PROFILE_LEVELS.get(profile_level(control), 0)
    required = PROFILE_LEVELS.get(normalize_profile_level(minimum), 0)
    return current >= required


def performance_enabled(control: MutableMapping[str, Any]) -> bool:
    return profile_level_at_least(control, "summary")


def profile_rss_enabled(control: MutableMapping[str, Any]) -> bool:
    value = control.get("profile_rss", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def profile_terminal_enabled(control: MutableMapping[str, Any]) -> bool:
    """Return whether profile rows should be mirrored to live terminal progress.

    Timing rows are always accumulated in ``performance_profile`` when
    profiling is enabled.  Printing every row is useful during debugging but
    adds terminal I/O noise and can perturb wall-clock benchmarks, so it is
    disabled by default as of v0.5.60.
    """
    value = control.get("profile_terminal", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _profile_callback(control: MutableMapping[str, Any], emit_progress: Any) -> Any:
    if emit_progress is False:
        return None
    if emit_progress is True:
        return control.get("progress_callback")
    if callable(emit_progress):
        return emit_progress if profile_terminal_enabled(control) else None
    if emit_progress is None and profile_terminal_enabled(control):
        return control.get("progress_callback")
    return None


def record_profile_event(
    control: MutableMapping[str, Any],
    name: str,
    elapsed_seconds: float,
    *,
    emit_progress: Any = None,
    **metadata: Any,
) -> None:
    """Append one pre-measured timing/RSS row when profiling is enabled.

    This is used for low-overhead nested hot-path profiling where a context
    manager around every tiny record branch would add too much noise.  It is
    observational only and never mutates physics state.
    """
    if not performance_enabled(control):
        return
    record: dict[str, Any] = {
        "component": str(name),
        "elapsed_seconds": float(elapsed_seconds),
    }
    if profile_rss_enabled(control):
        rss = current_rss_mb()
        if rss is not None:
            record["rss_end_mb"] = float(rss)
    record.update(metadata)
    _append_profile(control, record)
    callback = _profile_callback(control, emit_progress)
    if callable(callback):
        details = {k: v for k, v in record.items() if k != "component"}
        callback("profile_component", {"component": str(name), **details})


@contextmanager
def profile_component(
    control: MutableMapping[str, Any],
    name: str,
    *,
    emit_progress: Any = None,
    **metadata: Any,
) -> Iterator[None]:
    """Record wall time and RSS delta for one named component.

    ``control['profile_components']`` gates the whole helper.  When disabled,
    this context manager has almost no overhead beyond one dictionary lookup.
    """
    if not performance_enabled(control):
        yield
        return
    t0 = time.perf_counter()
    rss_enabled = profile_rss_enabled(control)
    rss0 = current_rss_mb() if rss_enabled else None
    try:
        yield
    finally:
        t1 = time.perf_counter()
        rss1 = current_rss_mb() if rss_enabled else None
        record: dict[str, Any] = {
            "component": str(name),
            "elapsed_seconds": float(t1 - t0),
        }
        if rss0 is not None:
            record["rss_start_mb"] = float(rss0)
        if rss1 is not None:
            record["rss_end_mb"] = float(rss1)
        if rss0 is not None and rss1 is not None:
            record["rss_delta_mb"] = float(rss1 - rss0)
        record.update(metadata)
        _append_profile(control, record)
        callback = _profile_callback(control, emit_progress)
        if callable(callback):
            details = {k: v for k, v in record.items() if k != "component"}
            callback("profile_component", {"component": str(name), **details})


def _add_grouped(grouped: dict[str, dict[str, float]], name: str, row: dict[str, Any]) -> None:
    item = grouped.setdefault(
        name,
        {"count": 0.0, "elapsed_seconds": 0.0, "max_rss_end_mb": 0.0, "max_rss_delta_mb": 0.0},
    )
    item["count"] += 1.0
    item["elapsed_seconds"] += float(row.get("elapsed_seconds", 0.0) or 0.0)
    if "rss_end_mb" in row:
        item["max_rss_end_mb"] = max(item["max_rss_end_mb"], float(row["rss_end_mb"]))
    if "rss_delta_mb" in row:
        item["max_rss_delta_mb"] = max(item["max_rss_delta_mb"], float(row["rss_delta_mb"]))


def summarize_profile(control: MutableMapping[str, Any]) -> dict[str, Any]:
    """Return compact timing/RSS totals grouped by component and element."""
    rows = control.get("performance_profile", [])
    if not isinstance(rows, list):
        return {"rows": 0, "components": {}, "top_components": [], "by_element": {}}
    grouped: dict[str, dict[str, float]] = {}
    by_element: dict[str, dict[str, float]] = {}
    by_ion: dict[str, dict[str, float]] = {}
    by_record_type: dict[str, dict[str, float]] = {}
    by_data_type: dict[str, dict[str, float]] = {}
    by_rate_data_type: dict[str, dict[str, float]] = {}
    by_source_routine: dict[str, dict[str, float]] = {}
    counter_fields = (
        "records_batched",
        "cpp_calls",
        "packing_seconds",
        "cpp_kernel_seconds",
        "fallback_count",
        "emitted_matrix_terms",
        "batches_flushed",
        "linopac_cpp_calls",
        "linopac_cpp_kernel_seconds",
        "linopac_cpp_updated_bins",
        "linopac_cpp_fallback_count",
        "linopac_cpp_parity_checks",
        "linopac_cpp_parity_failures",
        "type50_coarse_cpp_applied",
        "type50_coarse_cpp_full_applied",
        "type50_coarse_cpp_hybrid_applied",
        "type50_coarse_cpp_fallback",
        "type50_reason_full_cpp_applied",
        "type50_reason_linopac_voigt_python_fallback",
        "type50_reason_unsupported_data_type",
        "type50_reason_linopac_cpp_failure",
        "type50_reason_invalid_or_nonfinite_input",
        "records_seen",
        "matrix_inserted",
        "ucalc_cpp_applied",
        "ucalc_cpp_unsupported",
        "matrix_dense_terms",
        "matrix_dense_rows",
    )
    counter_totals: dict[str, dict[str, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("component", "unknown"))
        _add_grouped(grouped, name, row)
        if "element_z" in row:
            key = f"{name}:Z{int(row['element_z'])}"
            _add_grouped(by_element, key, row)
        if "element_z" in row and "ion_stage" in row:
            ion_index = row.get("ion_index")
            if ion_index is None:
                key = f"{name}:Z{int(row['element_z'])}:ion{int(row['ion_stage'])}"
            else:
                key = f"{name}:Z{int(row['element_z'])}:ion{int(row['ion_stage'])}:idx{int(ion_index)}"
            _add_grouped(by_ion, key, row)
        if "record_type" in row:
            key = f"{name}:record_type:{row['record_type']}"
            _add_grouped(by_record_type, key, row)
        if "data_type" in row:
            key = f"{name}:data_type:{row['data_type']}"
            _add_grouped(by_data_type, key, row)
        if "record_type" in row and "data_type" in row:
            key = f"{name}:record_type:{row['record_type']}:data_type:{row['data_type']}"
            _add_grouped(by_rate_data_type, key, row)
        if "source_routine" in row:
            key = f"{name}:source:{row['source_routine']}"
            _add_grouped(by_source_routine, key, row)
        if any(field in row for field in counter_fields):
            item = counter_totals.setdefault(name, {"count": 0.0, **{field: 0.0 for field in counter_fields}})
            item["count"] += 1.0
            for field in counter_fields:
                if field in row:
                    try:
                        item[field] += float(row[field])
                    except (TypeError, ValueError):
                        pass
    top_components = [
        {"component": name, **values}
        for name, values in sorted(
            grouped.items(),
            key=lambda kv: float(kv[1].get("elapsed_seconds", 0.0)),
            reverse=True,
        )[:20]
    ]
    top_by_element = [
        {"component_element": name, **values}
        for name, values in sorted(
            by_element.items(),
            key=lambda kv: float(kv[1].get("elapsed_seconds", 0.0)),
            reverse=True,
        )[:30]
    ]
    top_by_ion = [
        {"component_ion": name, **values}
        for name, values in sorted(
            by_ion.items(),
            key=lambda kv: float(kv[1].get("elapsed_seconds", 0.0)),
            reverse=True,
        )[:50]
    ]
    top_by_record_type = [
        {"component_record_type": name, **values}
        for name, values in sorted(
            by_record_type.items(),
            key=lambda kv: float(kv[1].get("elapsed_seconds", 0.0)),
            reverse=True,
        )[:50]
    ]
    top_by_source_routine = [
        {"component_source_routine": name, **values}
        for name, values in sorted(
            by_source_routine.items(),
            key=lambda kv: float(kv[1].get("elapsed_seconds", 0.0)),
            reverse=True,
        )[:50]
    ]
    return {
        "rows": len(rows),
        "components": grouped,
        "top_components": top_components,
        "by_element": by_element,
        "top_by_element": top_by_element,
        "by_ion": by_ion,
        "top_by_ion": top_by_ion,
        "by_record_type": by_record_type,
        "top_by_record_type": top_by_record_type,
        "by_source_routine": by_source_routine,
        "top_by_source_routine": top_by_source_routine,
        "counter_totals": counter_totals,
    }


def _summarize_other_emissivity_hotspots(rows: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    selected = [r for r in rows if str(r.get("component", "")).startswith("calc_emis")]

    def _group(key_name: str, value_fn: Any) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in selected:
            value = value_fn(row)
            if value in {None, "", "none"}:
                continue
            key = str(value)
            item = grouped.setdefault(key, {key_name: key, "wall_seconds": 0.0, "call_count": 0.0})
            item["wall_seconds"] += float(row.get("elapsed_seconds", 0.0) or 0.0)
            item["call_count"] += 1.0
            for field in ("component", "source_routine", "record_type"):
                if field in row:
                    item[field] = row[field]
        return sorted(grouped.values(), key=lambda x: float(x.get("wall_seconds", 0.0)), reverse=True)[:max(1, top_n)]

    components: dict[str, dict[str, Any]] = {}
    for row in selected:
        name = str(row.get("component", "unknown"))
        item = components.setdefault(name, {"component": name, "wall_seconds": 0.0, "call_count": 0.0})
        item["wall_seconds"] += float(row.get("elapsed_seconds", 0.0) or 0.0)
        item["call_count"] += 1.0
        for field in ("source_routine", "record_type"):
            if field in row:
                item[field] = row[field]
    top_components = sorted(components.values(), key=lambda x: float(x.get("wall_seconds", 0.0)), reverse=True)[:max(1, top_n)]
    return {
        "rows": len(selected),
        "components": components,
        "top_components": top_components,
        "top_by_element_z": _group("element_z", lambda r: r.get("element_z")),
        "top_by_ion": _group("ion", lambda r: f"{r.get('ion_index')}|stage={r.get('ion_stage')}" if r.get("ion_index") is not None else None),
        "top_by_data_type": _group("data_type", lambda r: r.get("data_type")),
        "top_by_rate_type": _group("rate_type", lambda r: r.get("rate_type")),
        "top_by_record_type": _group("record_type", lambda r: r.get("record_type")),
    }


def _summarize_simple_payload_batching_probe(
    control: MutableMapping[str, Any], rows: list[dict[str, Any]], top_n: int
) -> dict[str, Any]:
    names = {
        "calc_hmc_all.element_solver.mg_ion_simple_payload_cpp_kernel",
        "calc_hmc_all.element_solver.mg_simple_payload_batch_shadow_cpp_kernel",
        "calc_hmc_all.element_solver.mg_simple_payload_batch_product_cpp_kernel",
        "calc_hmc_all.element_solver.mg_ion_simple_payload_verification_shadow_cpp_kernel",
        "calc_hmc_all.element_solver.mg_simple_payload_batch_shadow_compare",
        "calc_hmc_all.element_solver.mg_simple_payload_batch_verification_compare",
    }
    selected = [r for r in rows if str(r.get("component", "")) in names]
    call_rows = [r for r in selected if str(r.get("component", "")).endswith("cpp_kernel")]

    def _call_projection(row: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "component", "elapsed_seconds", "element_z", "ion_index", "ion_stage",
            "evaluation_index", "matrix_dimension", "payload_length", "source_records",
            "records_seen", "records_supported", "terms_processed", "records_processed",
            "input_preparation_seconds", "python_to_cpp_call_seconds",
            "cpp_kernel_compute_seconds", "output_copy_commit_seconds",
            "allocation_count", "input_bytes", "output_capacity_bytes", "output_emitted_bytes", "bytes_copied",
            "actual_bytes_copied", "immutable_cache_bytes", "immutable_copy_bytes",
            "evaluation_input_bytes", "compact_ion_metadata_bytes", "npfi_slice_bytes",
            "source_index_entries", "peak_working_set_bytes", "cache_hits", "cache_misses",
            "support_index_hits", "support_index_misses", "zero_output_ions_skipped",
            "total_ion_count", "batch_ion_count", "expected_supported_records", "status",
        )
        return {k: row.get(k) for k in fields if k in row}

    top_calls = [
        _call_projection(row)
        for row in sorted(call_rows, key=lambda r: float(r.get("elapsed_seconds", 0.0) or 0.0), reverse=True)[:max(1, top_n)]
    ]

    def _group(label: str, key_fn: Any) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in call_rows:
            value = key_fn(row)
            if value in {None, ""}:
                continue
            key = str(value)
            item = grouped.setdefault(key, {label: key, "wall_seconds": 0.0, "call_count": 0.0})
            item["wall_seconds"] += float(row.get("elapsed_seconds", 0.0) or 0.0)
            item["call_count"] += 1.0
            item["records_processed"] = float(item.get("records_processed", 0.0)) + float(row.get("records_processed", row.get("records_seen", 0.0)) or 0.0)
            item["terms_processed"] = float(item.get("terms_processed", 0.0)) + float(row.get("terms_processed", row.get("emitted_records", 0.0)) or 0.0)
            item["bytes_copied"] = float(item.get("bytes_copied", 0.0)) + float(row.get("bytes_copied", 0.0) or 0.0)
        return sorted(grouped.values(), key=lambda x: float(x.get("wall_seconds", 0.0)), reverse=True)[:max(1, top_n)]

    stage_totals = {
        "input_preparation_seconds": 0.0,
        "python_to_cpp_call_seconds": 0.0,
        "cpp_kernel_compute_seconds": 0.0,
        "output_copy_commit_seconds": 0.0,
        "allocation_count": 0.0,
        "bytes_copied": 0.0,
        "actual_bytes_copied": 0.0,
        "cache_hits": 0.0,
        "cache_misses": 0.0,
        "support_index_hits": 0.0,
        "support_index_misses": 0.0,
        "zero_output_ions_skipped": 0.0,
        "records_processed": 0.0,
        "terms_processed": 0.0,
    }
    for row in call_rows:
        for key in stage_totals:
            stage_totals[key] += float(row.get(key, 0.0) or 0.0)

    shadow = dict(control.get("mg_simple_payload_batch_shadow_summary", {}) or {})
    samples = list(control.get("mg_simple_payload_batch_shadow_samples", []) or [])
    product_active = bool(shadow.get("product_active", False))
    product_requested = bool(shadow.get("product_requested", False))
    verification_enabled = bool(shadow.get("verification_enabled", False))
    product_promoted = bool(shadow.get("product_promoted", False))
    failed = float(shadow.get("evaluations_failed", 0.0) or 0.0)
    fallback = float(shadow.get("fallback_evaluations", 0.0) or 0.0)
    missing = float(shadow.get("missing_rows", 0.0) or 0.0)
    extra = float(shadow.get("extra_rows", 0.0) or 0.0)
    integer_mismatches = float(shadow.get("integer_field_mismatches", 0.0) or 0.0)
    float_mismatches = float(shadow.get("float_field_mismatches", 0.0) or 0.0)
    exact = bool(shadow.get("all_rows_exact", False))
    comparison_exact = exact and missing == 0.0 and extra == 0.0 and integer_mismatches == 0.0 and float_mismatches == 0.0
    if product_requested and fallback != 0.0:
        parity_status = "PRODUCT_FALLBACK"
    elif product_active and product_promoted and verification_enabled and comparison_exact:
        parity_status = "PRODUCT_PROMOTED_VERIFIED_EXACT"
    elif product_active and product_promoted and verification_enabled:
        parity_status = "PRODUCT_PROMOTED_VERIFICATION_FAILED"
    elif product_active and product_promoted:
        parity_status = "PRODUCT_PROMOTED"
    elif product_active and verification_enabled and comparison_exact:
        parity_status = "PRODUCT_VERIFIED_EXACT"
    elif product_active and verification_enabled:
        parity_status = "PRODUCT_VERIFICATION_FAILED"
    elif product_active:
        parity_status = "PRODUCT_ACTIVE_UNVERIFIED"
    elif failed != 0.0:
        parity_status = "SHADOW_ERRORS"
    elif comparison_exact:
        parity_status = "EXACT"
    elif bool(shadow.get("all_rows_roundoff_equivalent", False)):
        parity_status = "ROUNDOFF_EQUIVALENT"
    else:
        parity_status = "NOT_READY"
    return {
        "observational_only": not product_active,
        "product_active": product_active,
        "product_requested": product_requested,
        "product_promoted": product_promoted,
        "verification_enabled": verification_enabled,
        "rows": len(selected),
        "call_rows": len(call_rows),
        "stage_totals": stage_totals,
        "top_calls": top_calls,
        "top_by_element_z": _group("element_z", lambda r: r.get("element_z")),
        "top_by_ion": _group("ion", lambda r: f"{r.get('ion_index')}|stage={r.get('ion_stage')}" if r.get("ion_index") is not None else "batch"),
        "top_by_evaluation_index": _group("evaluation_index", lambda r: r.get("evaluation_index")),
        "top_by_matrix_dimension": _group("matrix_dimension", lambda r: r.get("matrix_dimension")),
        "top_by_payload_length": _group("payload_length", lambda r: r.get("payload_length")),
        "top_by_source_records": _group("source_records", lambda r: r.get("source_records", r.get("records_seen"))),
        "batch_shadow_summary": shadow,
        "batch_shadow_parity_status": parity_status,
        "cache_summary": {
            "cache_hits": float(shadow.get("cache_hits", 0.0) or 0.0),
            "cache_misses": float(shadow.get("cache_misses", 0.0) or 0.0),
            "support_index_hits": float(shadow.get("support_index_hits", 0.0) or 0.0),
            "support_index_misses": float(shadow.get("support_index_misses", 0.0) or 0.0),
            "immutable_cache_bytes": float(shadow.get("immutable_cache_bytes", 0.0) or 0.0),
            "immutable_copy_bytes": float(shadow.get("immutable_copy_bytes", 0.0) or 0.0),
            "evaluation_input_bytes": float(shadow.get("evaluation_input_bytes", 0.0) or 0.0),
            "compact_ion_metadata_bytes": float(shadow.get("compact_ion_metadata_bytes", 0.0) or 0.0),
            "npfi_slice_bytes": float(shadow.get("npfi_slice_bytes", 0.0) or 0.0),
            "source_index_entries": float(shadow.get("source_index_entries", 0.0) or 0.0),
            "actual_bytes_copied": float(shadow.get("actual_bytes_copied", shadow.get("bytes_copied", 0.0)) or 0.0),
            "peak_working_set_bytes": float(shadow.get("peak_working_set_bytes", 0.0) or 0.0),
            "zero_output_ions_skipped": float(shadow.get("zero_output_ions_skipped", 0.0) or 0.0),
        },
        "batch_shadow_samples": samples[:max(1, top_n)],
        "product_checkpoints": list(control.get("mg_simple_payload_product_checkpoints", []) or []),
        "notes": [
            "v0.6.26 promotes the validated cached one-call-per-element Mg simple-payload batch.",
            "Any batch validation error falls back immediately to the accepted per-ion C++ implementation before live matrix consumption.",
            "Optional verification runs the old per-ion implementation in shadow and compares exact payload rows.",
            "Heavy matrix/population/heating checkpoints are opt-in via XSTAR_ATOMIC_MATRIX_MG_SIMPLE_PAYLOAD_CHECKPOINTS.",
        ],
    }



MATRIX_ASSEMBLY_DATAFLOW_SECTIONS = (
    "matrix_workspace_allocation_zeroing",
    "level_and_ion_index_construction",
    "rate_payload_generation",
    "batch_simple_payload_generation",
    "python_payload_row_decoding",
    "python_matrix_row_insertion",
    "heating_matrix_row_insertion",
    "type53_preparation",
    "type53_cpp_call",
    "type53_output_commit",
    "normalization_row_construction",
    "normalization_row_commit",
    "repeated_matrix_traversal",
    "dense_to_solver_workspace_copy",
    "checkpoint_hashing",
    "unclassified_matrix_assembly",
)


def summarize_matrix_assembly_dataflow(
    control: MutableMapping[str, Any],
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    """Summarize v0.6.27 exclusive Mg matrix-assembly dataflow ledgers."""
    raw = control.get("mg_matrix_assembly_dataflow_evaluations", [])
    rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    metric_fields = (
        "exclusive_wall_seconds", "call_count", "rows_processed", "nonzero_entries_before",
        "nonzero_entries_after", "bytes_read", "bytes_written", "allocation_count",
    )
    totals: dict[str, dict[str, Any]] = {
        name: {field: 0.0 for field in metric_fields} | {"matrix_dimension": 0}
        for name in MATRIX_ASSEMBLY_DATAFLOW_SECTIONS
    }
    missing_sections: dict[str, list[str]] = {}
    accounting_failures: list[dict[str, Any]] = []
    total_enclosing = 0.0
    total_exclusive = 0.0
    max_overrun = 0.0
    for row in rows:
        evaluation_index = int(row.get("evaluation_index", 0) or 0)
        sections = row.get("sections", {}) if isinstance(row.get("sections", {}), dict) else {}
        missing = [name for name in MATRIX_ASSEMBLY_DATAFLOW_SECTIONS if name not in sections]
        if missing:
            missing_sections[str(evaluation_index)] = missing
        for name in MATRIX_ASSEMBLY_DATAFLOW_SECTIONS:
            item = sections.get(name, {}) if isinstance(sections.get(name, {}), dict) else {}
            target = totals[name]
            for field in metric_fields:
                target[field] += float(item.get(field, 0.0) or 0.0)
            target["matrix_dimension"] = max(int(target.get("matrix_dimension", 0)), int(item.get("matrix_dimension", 0) or 0))
        enclosing = float(row.get("enclosing_matrix_assembly_wall_seconds", 0.0) or 0.0)
        exclusive = float(row.get("exclusive_child_wall_seconds", 0.0) or 0.0)
        overrun = float(row.get("accounting_overrun_seconds", max(0.0, exclusive - enclosing)) or 0.0)
        total_enclosing += enclosing
        total_exclusive += exclusive
        max_overrun = max(max_overrun, overrun)
        if not bool(row.get("accounting_ok", False)):
            accounting_failures.append({
                "evaluation_index": evaluation_index,
                "enclosing_matrix_assembly_wall_seconds": enclosing,
                "exclusive_child_wall_seconds": exclusive,
                "accounting_overrun_seconds": overrun,
            })
    top = sorted(
        rows,
        key=lambda row: float(row.get("enclosing_matrix_assembly_wall_seconds", 0.0) or 0.0),
        reverse=True,
    )[:max(1, int(top_n))]
    top_projection = []
    for row in top:
        sections = row.get("sections", {}) if isinstance(row.get("sections", {}), dict) else {}
        top_projection.append({
            "evaluation_index": int(row.get("evaluation_index", 0) or 0),
            "matrix_dimension": int(row.get("matrix_dimension", 0) or 0),
            "term_count": int(row.get("term_count", 0) or 0),
            "assembly_function_wall_seconds": float(row.get("assembly_function_wall_seconds", 0.0) or 0.0),
            "enclosing_matrix_assembly_wall_seconds": float(row.get("enclosing_matrix_assembly_wall_seconds", 0.0) or 0.0),
            "exclusive_child_wall_seconds": float(row.get("exclusive_child_wall_seconds", 0.0) or 0.0),
            "unclassified_matrix_assembly_seconds": float(
                sections.get("unclassified_matrix_assembly", {}).get("exclusive_wall_seconds", 0.0) or 0.0
            ),
            "accounting_overrun_seconds": float(row.get("accounting_overrun_seconds", 0.0) or 0.0),
            "accounting_ok": bool(row.get("accounting_ok", False)),
        })
    batch = dict(control.get("mg_simple_payload_batch_shadow_summary", {}) or {})
    checkpoints_enabled = any(
        float(row.get("sections", {}).get("checkpoint_hashing", {}).get("call_count", 0.0) or 0.0) > 0.0
        for row in rows
    )
    ready = bool(rows) and not missing_sections and not accounting_failures
    return {
        "schema_version": "0.6.27",
        "observational_only": True,
        "probe_enabled": bool(rows),
        "status": "READY" if ready else "NOT_READY",
        "evaluation_count": len(rows),
        "required_sections": list(MATRIX_ASSEMBLY_DATAFLOW_SECTIONS),
        "section_totals": totals,
        "total_enclosing_matrix_assembly_wall_seconds": float(total_enclosing),
        "total_exclusive_child_wall_seconds": float(total_exclusive),
        "max_accounting_overrun_seconds": float(max_overrun),
        "accounting_identity": "sum(exclusive child times) <= enclosing matrix assembly wall time",
        "accounting_all_ok": not accounting_failures and bool(rows),
        "accounting_failures": accounting_failures,
        "missing_sections_by_evaluation": missing_sections,
        "checkpoint_hashing_enabled": bool(checkpoints_enabled),
        "batch_product_active": bool(batch.get("product_active", False)),
        "batch_product_promoted": bool(batch.get("product_promoted", False)),
        "batch_reverse_verification_enabled": bool(batch.get("verification_enabled", False)),
        "batch_fallback_evaluations": float(batch.get("fallback_evaluations", 0.0) or 0.0),
        "top_evaluations": top_projection,
        "evaluations": rows,
        "notes": [
            "Every named section is exclusive; nested type-53 work is subtracted from the rate-payload residual.",
            "unclassified_matrix_assembly is the non-negative remainder needed to close each per-evaluation ledger.",
            "The enclosing time includes assemble_element_matrix, optional pre-solver checkpoint hashing, and the initial solver-input copy.",
            "Checkpoint hashing is disabled in the main v0.6.27 probe wrapper and timed separately when explicitly enabled.",
            "Byte counts are exact for NumPy buffers and C++ bridge statistics; Python object-row byte counts are conservative accounting estimates.",
        ],
    }


RATE_PAYLOAD_DATAFLOW_SECTIONS = (
    "source_record_traversal",
    "record_header_filter_dispatch",
    "escape_factor_context_preparation",
    "cpp_simple_payload_materialization",
    "python_rate_evaluation",
    "cpp_rate_kernel_calls",
    "payload_object_creation",
    "scalar_status_bookkeeping",
    "matrix_term_payload_construction",
    "deferred_type51_batch",
    "deferred_type7_batch",
    "transition_family_bookkeeping",
    "per_ion_setup_finalization",
    "list_array_materialization",
    "heating_payload_generation",
    "unclassified_rate_payload_generation",
)


def summarize_rate_payload_dataflow(
    control: MutableMapping[str, Any],
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    """Summarize v0.6.28 exclusive Mg rate-payload dataflow ledgers."""
    raw = control.get("mg_rate_payload_dataflow_evaluations", [])
    rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    metric_fields = (
        "exclusive_wall_seconds", "call_count", "ions_processed", "records_processed",
        "terms_emitted", "bytes_read", "bytes_written", "allocation_count",
    )
    totals: dict[str, dict[str, Any]] = {
        name: {field: 0.0 for field in metric_fields}
        for name in RATE_PAYLOAD_DATAFLOW_SECTIONS
    }
    missing_sections: dict[str, list[str]] = {}
    accounting_failures: list[dict[str, Any]] = []
    total_enclosing = 0.0
    total_exclusive = 0.0
    max_overrun = 0.0
    grouped: dict[str, dict[str, dict[str, float]]] = {
        "by_rate_type": {}, "by_data_type": {}, "by_rate_data_type": {},
    }
    for row in rows:
        evaluation_index = int(row.get("evaluation_index", 0) or 0)
        sections = row.get("sections", {}) if isinstance(row.get("sections", {}), dict) else {}
        missing = [name for name in RATE_PAYLOAD_DATAFLOW_SECTIONS if name not in sections]
        if missing:
            missing_sections[str(evaluation_index)] = missing
        for name in RATE_PAYLOAD_DATAFLOW_SECTIONS:
            item = sections.get(name, {}) if isinstance(sections.get(name, {}), dict) else {}
            target = totals[name]
            for field in metric_fields:
                target[field] += float(item.get(field, 0.0) or 0.0)
        for group_name in grouped:
            source = row.get(group_name, {}) if isinstance(row.get(group_name, {}), dict) else {}
            for key, item in source.items():
                if not isinstance(item, dict):
                    continue
                target = grouped[group_name].setdefault(str(key), {
                    "exclusive_wall_seconds": 0.0, "call_count": 0.0,
                    "records_processed": 0.0, "terms_emitted": 0.0,
                })
                for field in target:
                    target[field] += float(item.get(field, 0.0) or 0.0)
        enclosing = float(row.get("enclosing_rate_payload_wall_seconds", 0.0) or 0.0)
        exclusive = float(row.get("exclusive_child_wall_seconds", 0.0) or 0.0)
        overrun = float(row.get("accounting_overrun_seconds", max(0.0, exclusive - enclosing)) or 0.0)
        total_enclosing += enclosing
        total_exclusive += exclusive
        max_overrun = max(max_overrun, overrun)
        if not bool(row.get("accounting_ok", False)):
            accounting_failures.append({
                "evaluation_index": evaluation_index,
                "enclosing_rate_payload_wall_seconds": enclosing,
                "exclusive_child_wall_seconds": exclusive,
                "accounting_overrun_seconds": overrun,
            })
    top = sorted(rows, key=lambda row: float(row.get("enclosing_rate_payload_wall_seconds", 0.0) or 0.0), reverse=True)[:max(1, int(top_n))]
    top_projection = []
    for row in top:
        sections = row.get("sections", {}) if isinstance(row.get("sections", {}), dict) else {}
        top_projection.append({
            "evaluation_index": int(row.get("evaluation_index", 0) or 0),
            "matrix_dimension": int(row.get("matrix_dimension", 0) or 0),
            "enclosing_rate_payload_wall_seconds": float(row.get("enclosing_rate_payload_wall_seconds", 0.0) or 0.0),
            "exclusive_child_wall_seconds": float(row.get("exclusive_child_wall_seconds", 0.0) or 0.0),
            "python_rate_evaluation_seconds": float(sections.get("python_rate_evaluation", {}).get("exclusive_wall_seconds", 0.0) or 0.0),
            "source_record_traversal_seconds": float(sections.get("source_record_traversal", {}).get("exclusive_wall_seconds", 0.0) or 0.0),
            "unclassified_rate_payload_generation_seconds": float(sections.get("unclassified_rate_payload_generation", {}).get("exclusive_wall_seconds", 0.0) or 0.0),
            "accounting_overrun_seconds": float(row.get("accounting_overrun_seconds", 0.0) or 0.0),
            "accounting_ok": bool(row.get("accounting_ok", False)),
        })
    def _top_group(table: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        items = sorted(table.items(), key=lambda kv: float(kv[1].get("exclusive_wall_seconds", 0.0)), reverse=True)
        return [{"key": key, **dict(values)} for key, values in items[:max(1, int(top_n))]]
    ready = bool(rows) and not missing_sections and not accounting_failures
    return {
        "schema_version": "0.6.28",
        "observational_only": True,
        "probe_enabled": bool(rows),
        "status": "READY" if ready else "NOT_READY",
        "evaluation_count": len(rows),
        "required_sections": list(RATE_PAYLOAD_DATAFLOW_SECTIONS),
        "section_totals": totals,
        "total_enclosing_rate_payload_wall_seconds": float(total_enclosing),
        "total_exclusive_child_wall_seconds": float(total_exclusive),
        "max_accounting_overrun_seconds": float(max_overrun),
        "accounting_identity": "sum(exclusive child times) <= enclosing rate payload wall time",
        "accounting_all_ok": not accounting_failures and bool(rows),
        "accounting_failures": accounting_failures,
        "missing_sections_by_evaluation": missing_sections,
        "top_by_rate_type": _top_group(grouped["by_rate_type"]),
        "top_by_data_type": _top_group(grouped["by_data_type"]),
        "top_by_rate_data_type": _top_group(grouped["by_rate_data_type"]),
        "top_evaluations": top_projection,
        "evaluations": rows,
        "notes": [
            "The enclosing total is the v0.6.27 exclusive rate_payload_generation section for the same evaluation.",
            "Named sections are measured directly and the non-negative residual is assigned to unclassified_rate_payload_generation.",
            "Type groupings classify measured per-record rate evaluation/materialization time and are observational; they are not added to section totals.",
            "The promoted Mg simple-payload batch remains live and reverse verification/checkpoint hashing remain disabled in the main probe.",
        ],
    }


def summarize_rate_payload_batched_orchestration_shadow(
    control: MutableMapping[str, Any],
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    raw = control.get("mg_rate_payload_batched_orchestration_shadow_evaluations", [])
    rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    if not rows:
        return {
            "schema_version": "0.6.33", "enabled": False, "shadow_only": True,
            "evaluation_count": 0, "status": "DISABLED", "native_scalar_status": "DISABLED",
        }
    family_totals: dict[str, float] = {}
    native_family_totals: dict[str, float] = {}
    timing_keys = (
        "shared_context_preparation_seconds", "compact_record_index_build_seconds",
        "input_packing_seconds", "python_to_cpp_call_seconds", "cpp_rate_evaluation_seconds",
        "cpp_matrix_term_construction_seconds", "output_decoding_seconds",
        "exact_row_comparison_seconds", "call_wall_seconds",
        "native_scalar_packet_build_seconds", "native_scalar_input_packing_seconds",
        "native_scalar_python_to_cpp_call_seconds", "native_scalar_cpp_seconds",
        "native_scalar_output_decoding_seconds", "native_scalar_comparison_seconds",
        "native_scalar_call_wall_seconds",
    )
    timing_totals = {key: 0.0 for key in timing_keys}
    status_counts: dict[str, int] = {}
    native_status_counts: dict[str, int] = {}
    type88_grid_source_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "UNKNOWN"))
        native_status = str(row.get("native_scalar_status", "DISABLED"))
        status_counts[status] = status_counts.get(status, 0) + 1
        native_status_counts[native_status] = native_status_counts.get(native_status, 0) + 1
        grid_source = str(row.get("native_scalar_type88_grid_source", "missing"))
        type88_grid_source_counts[grid_source] = type88_grid_source_counts.get(grid_source, 0) + 1
        for key in timing_keys:
            timing_totals[key] += float(row.get(key, 0.0) or 0.0)
        for key, value in dict(row.get("family_record_counts", {})).items():
            family_totals[str(key)] = family_totals.get(str(key), 0.0) + float(value or 0.0)
        for key, value in dict(row.get("native_scalar_family_record_counts", {})).items():
            native_family_totals[str(key)] = native_family_totals.get(str(key), 0.0) + float(value or 0.0)
    top = sorted(
        rows,
        key=lambda row: (
            float(row.get("call_wall_seconds", 0.0) or 0.0)
            + float(row.get("exact_row_comparison_seconds", 0.0) or 0.0)
            + float(row.get("native_scalar_call_wall_seconds", 0.0) or 0.0)
            + float(row.get("native_scalar_comparison_seconds", 0.0) or 0.0)
        ),
        reverse=True,
    )[:max(1, int(top_n))]
    top_projection = [{
        "evaluation_index": int(row.get("evaluation_index", 0) or 0),
        "status": str(row.get("status", "UNKNOWN")),
        "native_scalar_status": str(row.get("native_scalar_status", "DISABLED")),
        "records_expected": int(row.get("records_expected", 0) or 0),
        "terms_expected": int(row.get("terms_expected", 0) or 0),
        "native_scalar_records_expected": int(row.get("native_scalar_records_expected", 0) or 0),
        "native_scalar_records_compared": int(row.get("native_scalar_records_compared", 0) or 0),
        "call_wall_seconds": float(row.get("call_wall_seconds", 0.0) or 0.0),
        "exact_row_comparison_seconds": float(row.get("exact_row_comparison_seconds", 0.0) or 0.0),
        "native_scalar_call_wall_seconds": float(row.get("native_scalar_call_wall_seconds", 0.0) or 0.0),
        "native_scalar_comparison_seconds": float(row.get("native_scalar_comparison_seconds", 0.0) or 0.0),
        "matrix_checkpoint_exact": bool(row.get("matrix_checkpoint_exact", False)),
        "native_scalar_max_abs_diff": float(row.get("native_scalar_max_abs_diff", 0.0) or 0.0),
        "native_scalar_max_rel_diff": float(row.get("native_scalar_max_rel_diff", 0.0) or 0.0),
    } for row in top]
    exact_count = status_counts.get("EXACT", 0)
    tolerance_count = status_counts.get("TOLERANCE_APPROVED", 0)
    native_exact_count = native_status_counts.get("EXACT", 0)
    native_tolerance_count = native_status_counts.get("TOLERANCE_APPROVED", 0)
    row_ready = exact_count + tolerance_count == len(rows)
    native_ready = native_exact_count + native_tolerance_count == len(rows)
    combined_status = (
        "NATIVE_SCALARS_EXACT"
        if exact_count == len(rows) and native_exact_count == len(rows)
        else "NATIVE_SCALARS_TOLERANCE_APPROVED"
        if row_ready and native_ready
        else "NOT_READY"
    )
    return {
        "schema_version": "0.6.33",
        "enabled": True,
        "shadow_only": True,
        "live_matrix_commit": False,
        "evaluation_count": len(rows),
        "status": combined_status,
        "row_shadow_status": "EXACT" if exact_count == len(rows) else "TOLERANCE_APPROVED" if row_ready else "NOT_READY",
        "native_scalar_status": "EXACT" if native_exact_count == len(rows) else "TOLERANCE_APPROVED" if native_ready else "NOT_READY",
        "status_counts": status_counts,
        "native_scalar_status_counts": native_status_counts,
        "all_evaluations_exact": bool(exact_count == len(rows)),
        "all_evaluations_tolerance_approved": bool(row_ready),
        "all_matrix_checkpoints_exact": bool(all(bool(row.get("matrix_checkpoint_exact", False)) for row in rows)),
        "all_native_scalars_exact": bool(native_exact_count == len(rows)),
        "all_native_scalars_tolerance_approved": bool(native_ready),
        "records_expected": int(sum(int(row.get("records_expected", 0) or 0) for row in rows)),
        "records_compared": int(sum(int(row.get("records_compared", 0) or 0) for row in rows)),
        "terms_expected": int(sum(int(row.get("terms_expected", 0) or 0) for row in rows)),
        "terms_compared": int(sum(int(row.get("terms_compared", 0) or 0) for row in rows)),
        "missing_terms": int(sum(int(row.get("missing_terms", 0) or 0) for row in rows)),
        "extra_terms": int(sum(int(row.get("extra_terms", 0) or 0) for row in rows)),
        "integer_field_mismatches": int(sum(int(row.get("integer_field_mismatches", 0) or 0) for row in rows)),
        "float_field_mismatches": int(sum(int(row.get("float_field_mismatches", 0) or 0) for row in rows)),
        "float_fields_within_tolerance": int(sum(int(row.get("float_fields_within_tolerance", 0) or 0) for row in rows)),
        "accepted_duplicate_term_index_count": int(sum(int(row.get("accepted_duplicate_term_index_count", 0) or 0) for row in rows)),
        "cpp_duplicate_term_index_count": int(sum(int(row.get("cpp_duplicate_term_index_count", 0) or 0) for row in rows)),
        "accepted_duplicate_replacement_key_count": int(sum(int(row.get("accepted_duplicate_replacement_key_count", 0) or 0) for row in rows)),
        "cpp_duplicate_replacement_key_count": int(sum(int(row.get("cpp_duplicate_replacement_key_count", 0) or 0) for row in rows)),
        "replacement_terms_expected": int(sum(int(row.get("replacement_terms_expected", 0) or 0) for row in rows)),
        "replacement_terms_applied": int(sum(int(row.get("replacement_terms_applied", 0) or 0) for row in rows)),
        "max_abs_diff": max((float(row.get("max_abs_diff", 0.0) or 0.0) for row in rows), default=0.0),
        "max_rel_diff": max((float(row.get("max_rel_diff", 0.0) or 0.0) for row in rows), default=0.0),
        "native_scalar_records_expected": int(sum(int(row.get("native_scalar_records_expected", 0) or 0) for row in rows)),
        "native_scalar_records_compared": int(sum(int(row.get("native_scalar_records_compared", 0) or 0) for row in rows)),
        "native_scalar_missing_records": int(sum(int(row.get("native_scalar_missing_records", 0) or 0) for row in rows)),
        "native_scalar_extra_records": int(sum(int(row.get("native_scalar_extra_records", 0) or 0) for row in rows)),
        "native_scalar_exact_field_mismatches": int(sum(int(row.get("native_scalar_exact_field_mismatches", 0) or 0) for row in rows)),
        "native_scalar_fields_within_tolerance": int(sum(int(row.get("native_scalar_fields_within_tolerance", 0) or 0) for row in rows)),
        "native_scalar_fields_outside_tolerance": int(sum(int(row.get("native_scalar_fields_outside_tolerance", 0) or 0) for row in rows)),
        "native_scalar_nonfinite_fields": int(sum(int(row.get("native_scalar_nonfinite_fields", 0) or 0) for row in rows)),
        "native_scalar_max_abs_diff": max((float(row.get("native_scalar_max_abs_diff", 0.0) or 0.0) for row in rows), default=0.0),
        "native_scalar_max_rel_diff": max((float(row.get("native_scalar_max_rel_diff", 0.0) or 0.0) for row in rows), default=0.0),
        "family_record_counts": family_totals,
        "native_scalar_family_record_counts": native_family_totals,
        "native_scalar_type63_exact_operation_order_refinement": bool(all(
            bool(row.get("native_scalar_type63_exact_operation_order_refinement", False)) for row in rows
        )),
        "native_scalar_type63_python_lgamma_table_max_argument": min((
            int(row.get("native_scalar_type63_python_lgamma_table_max_argument", 0) or 0) for row in rows
        ), default=0),
        "native_scalar_type63_max_principal_n": max((
            int(row.get("native_scalar_type63_max_principal_n", 0) or 0) for row in rows
        ), default=0),
        "native_scalar_type63_max_factorial_argument": max((
            int(row.get("native_scalar_type63_max_factorial_argument", 0) or 0) for row in rows
        ), default=0),
        "native_scalar_type63_lgamma_table_coverage_ok": bool(all(
            bool(row.get("native_scalar_type63_lgamma_table_coverage_ok", False)) for row in rows
        )),
        "native_scalar_type63_exact_validation_failures": int(sum(
            int(row.get("native_scalar_type63_exact_validation_failures", 0) or 0) for row in rows
        )),
        "native_scalar_type88_full_grid_required": True,
        "native_scalar_type88_grid_source_counts": type88_grid_source_counts,
        "native_scalar_type88_full_grid_evaluations": int(sum(
            1 for row in rows if str(row.get("native_scalar_type88_grid_source", "")) == "full_epi_bremsa"
        )),
        "native_scalar_type88_reduced_grid_fallbacks": int(sum(
            int(row.get("native_scalar_type88_reduced_grid_fallbacks", 0) or 0) for row in rows
        )),
        "native_scalar_type88_grid_validation_failures": int(sum(
            int(row.get("native_scalar_type88_grid_validation_failures", 0) or 0) for row in rows
        )),
        "native_scalar_type88_min_full_grid_points": min((
            int(row.get("native_scalar_type88_full_grid_points", 0) or 0)
            for row in rows if int(row.get("native_scalar_family_record_counts", {}).get("42:88", 0) or 0) > 0
        ), default=0),
        "native_scalar_type88_max_full_grid_points": max((
            int(row.get("native_scalar_type88_full_grid_points", 0) or 0)
            for row in rows if int(row.get("native_scalar_family_record_counts", {}).get("42:88", 0) or 0) > 0
        ), default=0),
        "timing_totals": timing_totals,
        "top_evaluations": top_projection,
        "notes": [
            "The accepted path owns every live scalar rate and matrix term in v0.6.33.",
            "The v0.6.30 exact row/checkpoint orchestration shadow remains active for all four selected families.",
            "Native C++ scalar formulas are independently evaluated for 3:63 and 42:88 and compared against accepted ans1..ans6 channels.",
            "Type-63 uses literal Python operation grouping plus a CPython math.lgamma binary64 table through argument 256; out-of-range qualification is rejected.",
            "Type-88 qualification requires the full high-resolution epi_eV/bremsa grid; reduced-grid fallback is prohibited and reported as NOT_READY.",
            "No native scalar or reconstructed row can enter a live matrix in this release.",
        ],
    }

def summarize_runtime_phase_map(
    control: MutableMapping[str, Any],
    *,
    explicit_timing: dict[str, Any] | None = None,
    output_breakdown: dict[str, Any] | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Build the runtime map plus promoted-batch and v0.6.27 dataflow summaries."""
    phases = [
        "initialization_atomic_data_loading", "rates", "matrix_assembly", "solver",
        "emissivity_upstream_type4_type50", "other_emissivity", "opacity",
        "thermal_heating_cooling", "spectrum_output_construction", "fits_writing",
        "outer_zone_pass_orchestration", "diagnostics_overhead", "uncategorized_profiled",
    ]
    phase_map: dict[str, dict[str, Any]] = {
        name: {"wall_seconds": 0.0, "call_count": 0.0, "components": {}} for name in phases
    }

    def _add(phase: str, seconds: Any, *, count: float = 1.0, component: str | None = None) -> None:
        try:
            value = float(seconds or 0.0)
        except Exception:
            value = 0.0
        item = phase_map.setdefault(phase, {"wall_seconds": 0.0, "call_count": 0.0, "components": {}})
        item["wall_seconds"] += value
        item["call_count"] += float(count)
        if component:
            comp = item.setdefault("components", {}).setdefault(str(component), {"wall_seconds": 0.0, "call_count": 0.0})
            comp["wall_seconds"] += value
            comp["call_count"] += float(count)

    explicit = dict(explicit_timing or {})
    for key, phase in (
        ("initialization_atomic_data_loading_seconds", "initialization_atomic_data_loading"),
        ("output_cleanup_seconds", "initialization_atomic_data_loading"),
        ("radial_multipass_seconds", "outer_zone_pass_orchestration"),
        ("radial_spectrum_diagnostics_seconds", "diagnostics_overhead"),
        ("continuum_diagnostics_seconds", "diagnostics_overhead"),
        ("output_writer_sequence_seconds", "spectrum_output_construction"),
        ("total_run_seconds", "outer_zone_pass_orchestration"),
    ):
        if key in explicit:
            _add(phase, explicit[key], component=key)

    out = dict(output_breakdown or {})
    dropped: dict[str, Any] = {}
    known_times = {"pprint_legacy", "detail_fits_write", "final_fits_write", "final_product_build"}
    for key, value in out.items():
        skey = str(key)
        k = skey.lower()
        is_time = k.endswith("_seconds") or k in known_times
        if not is_time:
            dropped[skey] = value
            continue
        if "fits_write" in k or k in {"pprint_legacy", "detail_fits_write", "final_fits_write"}:
            _add("fits_writing", value, component=skey)
        elif k.startswith("final_product_build") or "spectrum_seconds" in k or "table_pack" in k or "binemis_profile_seconds" in k:
            _add("spectrum_output_construction", value, component=skey)
        elif "final_local_recompute" in k:
            _add("outer_zone_pass_orchestration", value, component=skey)

    raw_rows = control.get("performance_profile", [])
    rows = [r for r in raw_rows if isinstance(r, dict)] if isinstance(raw_rows, list) else []
    top_sections: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("component", "unknown")); lname = name.lower()
        try: elapsed = float(row.get("elapsed_seconds", 0.0) or 0.0)
        except Exception: elapsed = 0.0
        phase = "uncategorized_profiled"
        if "pre_matrix" in lname or "calc_ion_rates" in lname or "rate" in lname: phase = "rates"
        if "matrix" in lname or "assembly" in lname or "level_table" in lname or "simple_payload" in lname: phase = "matrix_assembly"
        if "solver_call" in lname or "msolvelucy" in lname or "leqt" in lname: phase = "solver"
        if "calc_emis" in lname or "emiss" in lname or "linopac" in lname:
            phase = "emissivity_upstream_type4_type50" if any(x in lname for x in ("type4", "type50", "upstream", "linopac")) else "other_emissivity"
        if "opac" in lname or "opacity" in lname: phase = "opacity"
        if "heat" in lname or "cool" in lname or "thermal" in lname or "heatt" in lname: phase = "thermal_heating_cooling"
        if "writer" in lname or "writespectra" in lname or "output" in lname or "pprint" in lname: phase = "spectrum_output_construction"
        if "radial" in lname or "dsec" in lname or "xstarcalc" in lname: phase = "outer_zone_pass_orchestration"
        _add(phase, elapsed, component=name)
        top_sections.append({"component": name, "phase": phase, "elapsed_seconds": elapsed, **{k: v for k, v in row.items() if k not in {"component", "elapsed_seconds"}}})

    top_sections = sorted(top_sections, key=lambda r: float(r.get("elapsed_seconds", 0.0)), reverse=True)[:max(1, int(top_n))]
    phase_totals = [
        {"phase": name, **{k: v for k, v in values.items() if k != "components"}}
        for name, values in sorted(phase_map.items(), key=lambda kv: float(kv[1].get("wall_seconds", 0.0)), reverse=True)
    ]
    total_profiled = sum(float(item.get("wall_seconds", 0.0)) for item in phase_map.values())
    total_run = float(explicit.get("total_run_seconds", 0.0) or 0.0)
    return {
        "schema_version": "0.6.25",
        "observational_only": True,
        "profile_rows": len(rows),
        "total_run_seconds": total_run,
        "total_grouped_wall_seconds": float(total_profiled),
        "dropped_non_timing_output_metrics": dropped,
        "phase_map": phase_map,
        "phase_totals": phase_totals,
        "top_sections": top_sections,
        "other_emissivity_hotspot_summary": _summarize_other_emissivity_hotspots(rows, int(top_n)),
        "matrix_simple_payload_batching_probe": _summarize_simple_payload_batching_probe(control, rows, int(top_n)),
        "explicit_timing": explicit,
        "output_writer_breakdown": out,
        "notes": [
            "Only explicit *_seconds, known writer timings, and profile elapsed_seconds rows are summed; rows/slots/counts/flags are retained but not treated as seconds.",
            "Phase totals include nested profile rows and can exceed elapsed wall time; compare components and stage totals rather than summing them.",
            "The Mg simple-payload batch implementation is shadow-only and cannot affect science products.",
        ],
    }


def summarize_rate_payload_four_family_product(
    control: MutableMapping[str, Any],
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    raw = control.get("mg_rate_payload_four_family_product_evaluations", [])
    rows = [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    if not rows:
        return {
            "schema_version": "0.6.34", "requested": False, "product_candidate": True,
            "active": False, "evaluation_count": 0, "status": "DISABLED",
        }
    family_totals: dict[str, int] = {"4:50": 0, "3:51": 0, "3:63": 0, "42:88": 0}
    for row in rows:
        for key, value in dict(row.get("family_record_counts", {})).items():
            family_totals[str(key)] = family_totals.get(str(key), 0) + int(value or 0)
    attempted = len(rows)
    completed = sum(1 for row in rows if str(row.get("status")) == "PRODUCT_CANDIDATE_EXACT")
    failed = attempted - completed
    activations = sum(1 for row in rows if bool(row.get("active")) and bool(row.get("live_matrix_commit")))
    fallbacks = sum(1 for row in rows if str(row.get("status")) == "FALLBACK_ACCEPTED_PATH")
    status = "PRODUCT_CANDIDATE_EXACT" if completed == attempted and attempted > 0 else "FALLBACK" if fallbacks else "NOT_READY"
    timing_keys = (
        "packet_build_seconds", "native_scalar_call_seconds", "row_cpp_call_seconds",
        "verification_seconds", "replacement_seconds",
    )
    timing_totals = {key: sum(float(row.get(key, 0.0) or 0.0) for row in rows) for key in timing_keys}
    return {
        "schema_version": "0.6.34",
        "requested": True,
        "accepted_gate": bool(all(bool(row.get("accepted_gate")) for row in rows)),
        "product_candidate": True,
        "product_promoted": False,
        "active": bool(activations == attempted and attempted > 0),
        "live_matrix_commit": bool(activations == attempted and attempted > 0),
        "whole_evaluation_fallback": True,
        "python_seed_path_retained": bool(all(bool(row.get("python_seed_path_retained")) for row in rows)),
        "verification_enabled": bool(all(bool(row.get("verification_enabled")) for row in rows)),
        "evaluation_count": attempted,
        "evaluations_attempted": attempted,
        "evaluations_completed": completed,
        "evaluations_failed": failed,
        "product_activations": activations,
        "fallback_evaluations": fallbacks,
        "status": status,
        "records_expected": int(sum(int(row.get("records_expected", 0) or 0) for row in rows)),
        "records_completed": int(sum(int(row.get("records_completed", 0) or 0) for row in rows)),
        "terms_expected": int(sum(int(row.get("terms_expected", 0) or 0) for row in rows)),
        "terms_committed": int(sum(int(row.get("terms_committed", 0) or 0) for row in rows)),
        "missing_terms": int(sum(int(row.get("missing_terms", 0) or 0) for row in rows)),
        "extra_terms": int(sum(int(row.get("extra_terms", 0) or 0) for row in rows)),
        "integer_field_mismatches": int(sum(int(row.get("integer_field_mismatches", 0) or 0) for row in rows)),
        "float_field_mismatches": int(sum(int(row.get("float_field_mismatches", 0) or 0) for row in rows)),
        "native_scalar_records_expected": int(sum(int(row.get("native_scalar_records_expected", 0) or 0) for row in rows)),
        "native_scalar_records_completed": int(sum(int(row.get("native_scalar_records_completed", 0) or 0) for row in rows)),
        "native_scalar_mismatches": int(sum(int(row.get("native_scalar_mismatches", 0) or 0) for row in rows)),
        "family_record_counts": family_totals,
        "timing_totals": timing_totals,
        "fallback_reasons": [str(row.get("fallback_reason")) for row in rows if row.get("fallback_reason")][:max(1, int(top_n))],
        "evaluations": rows,
        "notes": [
            "v0.6.34 commits exact C++ matrix terms for the four validated Mg families.",
            "The accepted path is retained as the whole-evaluation fallback and verification oracle in this candidate.",
            "A later promoted release may elide the accepted seed path after external product-candidate acceptance.",
        ],
    }
