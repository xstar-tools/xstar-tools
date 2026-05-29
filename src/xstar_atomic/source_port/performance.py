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


def performance_enabled(control: MutableMapping[str, Any]) -> bool:
    return bool(control.get("profile_components", False))


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
    rss0 = current_rss_mb()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        rss1 = current_rss_mb()
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
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("component", "unknown"))
        _add_grouped(grouped, name, row)
        if "element_z" in row:
            key = f"{name}:Z{int(row['element_z'])}"
            _add_grouped(by_element, key, row)
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
    return {
        "rows": len(rows),
        "components": grouped,
        "top_components": top_components,
        "by_element": by_element,
        "top_by_element": top_by_element,
    }
