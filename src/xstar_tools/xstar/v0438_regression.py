"""Frozen v0.4.38 H/He/O all-element pre-continuum regression gate."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any, Mapping, Tuple


@dataclass(frozen=True)
class V0438AllElementRegressionGate:
    ready: bool
    source_path: str
    source_sha256: str
    failed_requirements: Tuple[str, ...]
    summary: Mapping[str, Any]


def _packaged_paths() -> tuple[Path, Path]:
    root = resources.files("xstar_tools.benchmarks").joinpath(
        "all_element_call73_v0438_acceptance"
    )
    return Path(str(root.joinpath("xstar_calc_hmc_all_pre_continuum_parity_summary.json"))), Path(
        str(root.joinpath("benchmark_manifest.json"))
    )


def validate_v0438_all_element_regression(
    source: str | Path | None = None,
) -> V0438AllElementRegressionGate:
    """Validate the accepted H/He/O call-73 result or its packaged copy."""
    packaged_summary, manifest_path = _packaged_paths()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = packaged_summary if source is None else Path(source)
    if path.is_dir():
        path = path / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    if not path.is_file():
        return V0438AllElementRegressionGate(
            ready=False,
            source_path=str(path),
            source_sha256="",
            failed_requirements=("summary_missing",),
            summary={},
        )
    raw = path.read_bytes()
    summary = json.loads(raw.decode("utf-8"))
    failures: list[str] = []
    for key in manifest["required_true_fields"]:
        if summary.get(key) is not True:
            failures.append(f"{key}!=True")
    for key in manifest["required_zero_fields"]:
        if int(summary.get(key, -1)) != 0:
            failures.append(f"{key}!=0")
    if int(summary.get("call_id", -1)) != int(manifest["call_id"]):
        failures.append("call_id_mismatch")
    readiness = summary.get("all_element_element_readiness", [])
    by_z = {int(item.get("element_z", 0)): item for item in readiness}
    for z in manifest["required_elements"]:
        item = by_z.get(int(z))
        if item is None:
            failures.append(f"element_{z}_missing")
        elif item.get("detailed_parity_ready") is not True:
            failures.append(f"element_{z}_detailed_parity_ready!=True")
        elif int(item.get("n_milestone_blocking_rows", -1)) != 0:
            failures.append(f"element_{z}_milestone_blocking_rows!=0")
    return V0438AllElementRegressionGate(
        ready=not failures,
        source_path=str(path),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        failed_requirements=tuple(failures),
        summary=summary,
    )


__all__ = ["V0438AllElementRegressionGate", "validate_v0438_all_element_regression"]
