from __future__ import annotations

import time

from xstar_tools.xstar.performance import profile_component, record_profile_event, summarize_profile


def test_nested_profile_reports_exclusive_time() -> None:
    control = {"profile_components": "forensic"}
    with profile_component(control, "outer"):
        time.sleep(0.002)
        with profile_component(control, "inner"):
            time.sleep(0.003)
        time.sleep(0.002)

    rows = {row["component"]: row for row in control["performance_profile"]}
    outer = rows["outer"]
    inner = rows["inner"]
    assert inner["parent_component"] == "outer"
    assert outer["inclusive_seconds"] >= inner["inclusive_seconds"]
    assert outer["exclusive_seconds"] > 0.0
    assert outer["exclusive_seconds"] < outer["inclusive_seconds"]
    assert abs(
        outer["inclusive_seconds"]
        - outer["exclusive_seconds"]
        - outer["child_seconds"]
    ) < 0.003


def test_pre_measured_child_can_be_subtracted() -> None:
    control = {"profile_components": "forensic"}
    with profile_component(control, "parent"):
        t0 = time.perf_counter()
        time.sleep(0.002)
        record_profile_event(
            control,
            "manual_child",
            time.perf_counter() - t0,
            counts_as_child=True,
        )
        time.sleep(0.001)

    rows = {row["component"]: row for row in control["performance_profile"]}
    assert rows["manual_child"]["counts_as_child"] is True
    assert rows["parent"]["child_seconds"] > 0.0
    summary = summarize_profile(control)
    assert summary["exclusive_timing_available"] is True
    assert summary["top_exclusive_components"]


def test_legacy_aggregate_event_does_not_reduce_parent_exclusive_time() -> None:
    control = {"profile_components": "forensic"}
    with profile_component(control, "parent"):
        t0 = time.perf_counter()
        time.sleep(0.001)
        record_profile_event(control, "legacy_aggregate", time.perf_counter() - t0)
        time.sleep(0.001)

    rows = {row["component"]: row for row in control["performance_profile"]}
    assert rows["legacy_aggregate"]["exclusive_known"] is False
    assert rows["legacy_aggregate"]["exclusive_seconds"] == 0.0
    assert rows["parent"]["child_seconds"] == 0.0
