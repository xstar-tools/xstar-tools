"""Python adapter for the v0.6.45 standalone shared-library ABI.

This module intentionally provides only the ABI-validation scaffold in v0.6.45.
The existing production Python and hybrid physics paths remain unchanged.  The
shared-library adapter will acquire full zone physics in later releases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass
class StandaloneContext:
    config: dict[str, Any]
    zones_attempted: int = 0
    zones_completed: int = 0
    batch_calls: int = 0
    fallback_count: int = 0


def create_context(config: Mapping[str, Any]) -> StandaloneContext:
    return StandaloneContext(config=dict(config))


def reset_context(context: StandaloneContext) -> None:
    context.zones_attempted = 0
    context.zones_completed = 0
    context.batch_calls = 0
    context.fallback_count = 0


def context_stats(context: StandaloneContext) -> dict[str, int]:
    return {
        "zones_attempted": context.zones_attempted,
        "zones_completed": context.zones_completed,
        "batch_calls": context.batch_calls,
        "fallback_count": context.fallback_count,
    }


def run_zone(
    context: StandaloneContext,
    zone: Mapping[str, Any],
    *,
    allow_scaffold: bool,
) -> dict[str, Any]:
    context.zones_attempted += 1
    if not allow_scaffold:
        raise NotImplementedError(
            "v0.6.48.7.26 Python standalone zone boundary is architecture-only; "
            "use the existing xstar_tools Python runner for production physics"
        )

    abundances = [float(value) for value in zone.get("abundances", ())]
    radiation_flux = [float(value) for value in zone.get("radiation_flux", ())]
    context.zones_completed += 1
    return {
        "zone_id": int(zone.get("zone_id", 0)),
        "status_flags": 1 | 4,  # scaffold + Python backend
        "heating": 0.0,
        "cooling": 0.0,
        "electron_fraction": float(zone.get("electron_fraction", 0.0)),
        "ion_fractions": abundances,
        "spectrum": radiation_flux,
        "opacity": [0.0] * len(radiation_flux),
        "backend": "python",
        "message": "Python persistent-context scaffold result; no production physics claimed",
    }


def run_batch(
    context: StandaloneContext,
    zones: Sequence[Mapping[str, Any]],
    *,
    allow_scaffold: bool,
) -> list[dict[str, Any]]:
    context.batch_calls += 1
    return [run_zone(context, zone, allow_scaffold=allow_scaffold) for zone in zones]


def echo_json(request: Any) -> Any:
    """Small JSON-bridge self-test callable."""
    return {"backend": "python", "request": request, "version": "0.6.48.7.29"}
