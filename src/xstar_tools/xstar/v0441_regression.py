"""Frozen accepted v0.4.41 call-73 ``bremem`` regression gate."""
from __future__ import annotations

from dataclasses import dataclass
import json
from importlib import resources
from pathlib import Path
from typing import Any, Mapping, Tuple


V0441_BREMEM_REQUIRED_TRUE_FIELDS: Tuple[str, ...] = (
    "bremem_translated",
    "gaunt_factor_mode_unity",
    "continuum_grid_parity",
    "bremsstrahlung_emissivity_parity",
    "brcems_reset_semantics_parity",
    "continuum_opacity_preserved_parity",
    "frozen_oxygen_regression",
    "frozen_h_he_o_pre_continuum_regression",
    "frozen_comp2_regression",
    "frozen_freef_regression",
    "v0441_bremem_acceptance_ready",
)


@dataclass(frozen=True)
class V0441BremsstrahlungRegressionGate:
    ready: bool
    source_path: str
    summary: Mapping[str, Any]
    failed_requirements: Tuple[str, ...]


def _packaged_summary() -> Path:
    target = resources.files("xstar_tools.benchmarks").joinpath(
        "bremem_call73_v0441_acceptance/xstar_calc_hmc_all_v0441_acceptance_summary.json"
    )
    return Path(str(target))


def _resolve(path: str | Path | None) -> Path:
    if path is None:
        return _packaged_summary()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "xstar_calc_hmc_all_v0441_acceptance_summary.json"
    return candidate


def validate_v0441_bremem_regression(
    path: str | Path | None = None,
) -> V0441BremsstrahlungRegressionGate:
    target = _resolve(path)
    if not target.is_file():
        return V0441BremsstrahlungRegressionGate(
            ready=False,
            source_path=str(target),
            summary={},
            failed_requirements=("summary_missing",),
        )
    try:
        summary = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return V0441BremsstrahlungRegressionGate(
            ready=False,
            source_path=str(target),
            summary={},
            failed_requirements=("summary_unreadable",),
        )
    failed = []
    if int(summary.get("calc_hmc_all_call_id", -1)) != 73:
        failed.append("calc_hmc_all_call_id")
    for field in V0441_BREMEM_REQUIRED_TRUE_FIELDS:
        if summary.get(field) is not True:
            failed.append(field)
    return V0441BremsstrahlungRegressionGate(
        ready=not failed,
        source_path=str(target),
        summary=summary,
        failed_requirements=tuple(failed),
    )


__all__ = [
    "V0441_BREMEM_REQUIRED_TRUE_FIELDS",
    "V0441BremsstrahlungRegressionGate",
    "validate_v0441_bremem_regression",
]
