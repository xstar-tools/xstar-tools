"""Frozen accepted v0.4.39 call-73 ``comp2`` regression gate."""
from __future__ import annotations

from dataclasses import dataclass
import json
from importlib import resources
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


V0439_COMP2_REQUIRED_TRUE_FIELDS: Tuple[str, ...] = (
    "comp2_translated",
    "cmpfnc_table_loaded",
    "cmp1_parity",
    "cmp2_parity",
    "compton_heating_coefficient_parity",
    "compton_cooling_coefficient_parity",
    "frozen_oxygen_regression",
    "frozen_h_he_o_pre_continuum_regression",
    "v0439_comp2_acceptance_ready",
)


@dataclass(frozen=True)
class V0439Comp2RegressionGate:
    ready: bool
    source_path: str
    summary: Mapping[str, Any]
    failed_requirements: Tuple[str, ...]


def _packaged_summary() -> Path:
    target = resources.files("xstar_atomic.benchmarks").joinpath(
        "comp2_call73_v0439_acceptance/xstar_calc_hmc_all_v0439_acceptance_summary.json"
    )
    return Path(str(target))


def _resolve(path: str | Path | None) -> Path:
    if path is None:
        return _packaged_summary()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "xstar_calc_hmc_all_v0439_acceptance_summary.json"
    return candidate


def validate_v0439_comp2_regression(
    path: str | Path | None = None,
) -> V0439Comp2RegressionGate:
    target = _resolve(path)
    if not target.is_file():
        return V0439Comp2RegressionGate(
            ready=False,
            source_path=str(target),
            summary={},
            failed_requirements=("summary_missing",),
        )
    try:
        summary = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return V0439Comp2RegressionGate(
            ready=False,
            source_path=str(target),
            summary={},
            failed_requirements=("summary_unreadable",),
        )
    failed = []
    if int(summary.get("calc_hmc_all_call_id", -1)) != 73:
        failed.append("calc_hmc_all_call_id")
    for field in V0439_COMP2_REQUIRED_TRUE_FIELDS:
        if summary.get(field) is not True:
            failed.append(field)
    return V0439Comp2RegressionGate(
        ready=not failed,
        source_path=str(target),
        summary=summary,
        failed_requirements=tuple(failed),
    )


__all__ = [
    "V0439_COMP2_REQUIRED_TRUE_FIELDS",
    "V0439Comp2RegressionGate",
    "validate_v0439_comp2_regression",
]
