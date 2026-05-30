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
    callback = emit_progress or control.get("progress_callback")
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
        callback = emit_progress or control.get("progress_callback")
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
    by_source_routine: dict[str, dict[str, float]] = {}
    counter_fields = (
        "records_batched",
        "cpp_calls",
        "packing_seconds",
        "cpp_kernel_seconds",
        "fallback_count",
        "emitted_matrix_terms",
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
