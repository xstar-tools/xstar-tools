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


def summarize_runtime_phase_map(
    control: MutableMapping[str, Any],
    *,
    explicit_timing: dict[str, Any] | None = None,
    output_breakdown: dict[str, Any] | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Build a coarse runtime phase map for port-planning decisions.

    v0.6.22 cleanup rules:
    - only aggregate explicit timing values or known profile elapsed rows;
    - never treat row/slot/count/flag diagnostic values as seconds;
    - keep sharper other-emissivity buckets and top-N groupings for the
      next C++ port decision.
    """
    phases = [
        "initialization_atomic_data_loading",
        "rates",
        "matrix_assembly",
        "solver",
        "emissivity_upstream_type4_type50",
        "other_emissivity",
        "opacity",
        "thermal_heating_cooling",
        "spectrum_output_construction",
        "fits_writing",
        "outer_zone_pass_orchestration",
        "diagnostics_overhead",
        "uncategorized_profiled",
    ]
    phase_map: dict[str, dict[str, Any]] = {
        name: {"wall_seconds": 0.0, "call_count": 0.0, "components": {}}
        for name in phases
    }

    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except Exception:
            return default

    def _add(phase: str, seconds: Any, *, count: float = 1.0, component: str | None = None) -> None:
        value = _as_float(seconds, 0.0)
        if value == 0.0 and count == 0.0:
            return
        item = phase_map.setdefault(phase, {"wall_seconds": 0.0, "call_count": 0.0, "components": {}})
        item["wall_seconds"] = float(item.get("wall_seconds", 0.0)) + value
        item["call_count"] = float(item.get("call_count", 0.0)) + float(count)
        if component:
            comps = item.setdefault("components", {})
            comp = comps.setdefault(str(component), {"wall_seconds": 0.0, "call_count": 0.0})
            comp["wall_seconds"] = float(comp.get("wall_seconds", 0.0)) + value
            comp["call_count"] = float(comp.get("call_count", 0.0)) + float(count)

    def _is_actual_timing_metric(key: str) -> bool:
        """Return True only for writer/provenance values that are wall times.

        The output writer breakdown also stores rows/slots/flags/counters.  In
        v0.6.21 those were incorrectly summed as seconds.  This whitelist keeps
        known timing names and drops diagnostic counters.
        """
        k = str(key).lower()
        counter_markers = (
            "_rows", ".rows", "rows", "_slots", ".slots", "slots",
            "_applied", "_attempted", "_enabled", "_accepted", "_present",
            "_scope", "_parity", "_count", "count", "nonzero", "saved",
        )
        if any(marker in k for marker in counter_markers):
            return False
        if k.endswith("_seconds") or "_seconds." in k or ".seconds" in k:
            return True
        known_exact = {
            "detail_fits_write",
            "final_fits_write",
            "pprint_legacy",
            "final_product_build",
            "output_writer_sequence_seconds",
        }
        return k in known_exact

    def _classify_profile_component(name: str) -> str:
        lname = name.lower()
        phase = "uncategorized_profiled"
        if "pre_matrix" in lname or "calc_ion_rates" in lname or "rate" in lname:
            phase = "rates"
        if "matrix" in lname or "assembly" in lname or "level_table" in lname:
            phase = "matrix_assembly"
        if "solver_call" in lname or "msolvelucy" in lname or "leqt" in lname:
            phase = "solver"
        if "calc_emis" in lname or "emiss" in lname or "linopac" in lname:
            if "type4" in lname or "type50" in lname or "upstream" in lname or "linopac" in lname:
                phase = "emissivity_upstream_type4_type50"
            else:
                phase = "other_emissivity"
        if "opac" in lname or "opacity" in lname:
            phase = "opacity"
        if "heat" in lname or "cool" in lname or "thermal" in lname or "heatt" in lname:
            phase = "thermal_heating_cooling"
        if "writer" in lname or "writespectra" in lname or "output" in lname or "pprint" in lname:
            phase = "spectrum_output_construction"
        if "radial" in lname or "dsec" in lname or "xstarcalc" in lname:
            phase = "outer_zone_pass_orchestration"
        return phase

    def _group_add(group: dict[str, dict[str, Any]], key: Any, seconds: float, row: dict[str, Any]) -> None:
        if key is None:
            return
        skey = str(key)
        if skey == "" or skey.lower() == "none":
            return
        item = group.setdefault(skey, {"wall_seconds": 0.0, "call_count": 0.0})
        item["wall_seconds"] = float(item.get("wall_seconds", 0.0)) + float(seconds)
        item["call_count"] = float(item.get("call_count", 0.0)) + 1.0
        for meta_key in ("component", "source_routine", "record_type"):
            if meta_key in row and meta_key not in item:
                item[meta_key] = row.get(meta_key)

    def _top_group(group: dict[str, dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
        rows_out: list[dict[str, Any]] = []
        for key, values in sorted(group.items(), key=lambda kv: float(kv[1].get("wall_seconds", 0.0)), reverse=True):
            rows_out.append({key_name: key, **values})
        return rows_out[:max(1, int(top_n))]

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
        if key in explicit and _is_actual_timing_metric(key):
            _add(phase, explicit[key], component=key)

    out = dict(output_breakdown or {})
    dropped_output_metrics: dict[str, Any] = {}
    for key, value in out.items():
        if not _is_actual_timing_metric(str(key)):
            dropped_output_metrics[str(key)] = value
            continue
        k = str(key).lower()
        if "fits_write" in k or k in {"pprint_legacy", "detail_fits_write", "final_fits_write"}:
            _add("fits_writing", value, component=str(key))
        elif k.startswith("final_product_build") or "spectrum_seconds" in k or "table_pack" in k or "binemis_profile_seconds" in k:
            _add("spectrum_output_construction", value, component=str(key))
        elif "final_local_recompute" in k:
            _add("outer_zone_pass_orchestration", value, component=str(key))

    rows = control.get("performance_profile", [])
    top_sections: list[dict[str, Any]] = []
    other_rows: list[dict[str, Any]] = []
    other_by_element: dict[str, dict[str, Any]] = {}
    other_by_ion: dict[str, dict[str, Any]] = {}
    other_by_data_type: dict[str, dict[str, Any]] = {}
    other_by_rate_type: dict[str, dict[str, Any]] = {}
    other_by_record_type: dict[str, dict[str, Any]] = {}
    other_by_component: dict[str, dict[str, Any]] = {}

    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("component", "unknown"))
            elapsed = _as_float(row.get("elapsed_seconds", 0.0), 0.0)
            phase = _classify_profile_component(name)
            _add(phase, elapsed, component=name)
            enriched = {
                "component": name,
                "phase": phase,
                "elapsed_seconds": elapsed,
                **{k: v for k, v in row.items() if k not in {"component", "elapsed_seconds"}},
            }
            top_sections.append(enriched)
            if phase == "other_emissivity":
                other_rows.append(enriched)
                _group_add(other_by_component, name, elapsed, row)
                _group_add(other_by_element, row.get("element_z"), elapsed, row)
                ion_key = None
                if row.get("ion_index") is not None:
                    ion_key = row.get("ion_index")
                    if row.get("ion_stage") is not None:
                        ion_key = f"{row.get('ion_index')}|stage={row.get('ion_stage')}"
                _group_add(other_by_ion, ion_key, elapsed, row)
                _group_add(other_by_data_type, row.get("data_type") or row.get("result_data_type") or row.get("source_data_type"), elapsed, row)
                # v0.6.21 stored by-rate-type rows in record_type.  Preserve that
                # while also accepting future explicit rate_type metadata.
                rate_key = row.get("rate_type")
                if rate_key is None and name == "calc_emis_all.element.by_rate_type":
                    rate_key = row.get("record_type")
                _group_add(other_by_rate_type, rate_key, elapsed, row)
                _group_add(other_by_record_type, row.get("record_type"), elapsed, row)

    top_sections = sorted(top_sections, key=lambda r: float(r.get("elapsed_seconds", 0.0)), reverse=True)[:max(1, int(top_n))]
    phase_totals = [
        {"phase": name, **{k: v for k, v in values.items() if k != "components"}}
        for name, values in sorted(
            phase_map.items(),
            key=lambda kv: float(kv[1].get("wall_seconds", 0.0)),
            reverse=True,
        )
    ]
    total_profiled = sum(float(item.get("wall_seconds", 0.0)) for item in phase_map.values())
    total_run = float(explicit.get("total_run_seconds", 0.0) or 0.0)

    other_emissivity_hotspot_summary = {
        "rows": len(other_rows),
        "components": other_by_component,
        "top_components": _top_group(other_by_component, "component"),
        "top_by_element_z": _top_group(other_by_element, "element_z"),
        "top_by_ion": _top_group(other_by_ion, "ion"),
        "top_by_data_type": _top_group(other_by_data_type, "data_type"),
        "top_by_rate_type": _top_group(other_by_rate_type, "rate_type"),
        "top_by_record_type": _top_group(other_by_record_type, "record_type"),
    }

    return {
        "schema_version": "0.6.22",
        "observational_only": True,
        "profile_rows": len(rows) if isinstance(rows, list) else 0,
        "total_run_seconds": total_run,
        "total_grouped_wall_seconds": float(total_profiled),
        "phase_map": phase_map,
        "phase_totals": phase_totals,
        "top_sections": top_sections,
        "other_emissivity_hotspot_summary": other_emissivity_hotspot_summary,
        "explicit_timing": explicit,
        "output_writer_breakdown": out,
        "dropped_non_timing_output_metrics": dropped_output_metrics,
        "notes": [
            "v0.6.22 only sums explicit *_seconds/known timing metrics and profile elapsed_seconds rows; rows/slots/counts/flags are retained but not added as seconds.",
            "Phase totals still include nested profile rows, so grouped totals can exceed elapsed wall time; compare components/top sections rather than summing to wall time.",
            "Use other_emissivity_hotspot_summary to choose the next C++ porting target; do not use this diagnostic as a science-output input.",
        ],
    }
