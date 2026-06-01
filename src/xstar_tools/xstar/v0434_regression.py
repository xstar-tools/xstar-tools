"""Focused v0.4.34 oxygen correction regression gates.

The gate intentionally targets only the six discrepancy groups isolated by the
production v0.4.33 oxygen archive.  It can be run on the v0.4.33 diagnosis to
verify that the expected bounded target set was selected, and on a v0.4.34
rerun to require that all six groups have closed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping
import csv
import json
import math


V0434_BASELINE_TARGET_COUNTS: Dict[str, int] = {
    "rnisg_rows": 35,
    "bilevg_rows": 349,
    "type53_leveltemp_rows": 205,
    "type53_cj2_records": 196,
    "type99_ans5_records": 7,
    "thermal_family_rows": 2,
}


@dataclass(frozen=True)
class V0434RegressionGateResult:
    counts: Mapping[str, int]
    baseline_target_counts: Mapping[str, int]
    baseline_target_match: bool
    closure_ready: bool
    source_directory: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _false(value: Any) -> bool:
    return str(value).strip().lower() in {"false", "0", "no"}


def _different(a: Any, b: Any) -> bool:
    try:
        av = float(a)
        bv = float(b)
    except (TypeError, ValueError):
        return True
    if not (math.isfinite(av) and math.isfinite(bv)):
        return True
    return av != bv


def assess_v0434_oxygen_correction_gates(
    output_dir: str | Path,
) -> V0434RegressionGateResult:
    """Count the six bounded v0.4.34 discrepancy groups."""

    root = Path(output_dir)
    parity = _rows(root / "xstar_calc_hmc_all_pre_continuum_parity_details.csv")
    leveltemp = _rows(root / "xstar_calc_hmc_all_leveltemp_energy_parity.csv")
    cj2 = _rows(root / "xstar_calc_hmc_all_rate7_cj2_record_summary.csv")
    thermal = _rows(root / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv")

    counts = {
        "rnisg_rows": sum(
            row.get("component") == "global_level_rnisg"
            and _false(row.get("within_tolerance"))
            and not _false(row.get("milestone_blocking"))
            for row in parity
        ),
        "bilevg_rows": sum(
            row.get("component") == "global_level_bilevg"
            and _false(row.get("within_tolerance"))
            for row in parity
        ),
        "type53_leveltemp_rows": sum(
            row.get("data_type") == "53" and _false(row.get("within_tolerance"))
            for row in leveltemp
        ),
        "type53_cj2_records": sum(
            row.get("data_type") == "53" and _false(row.get("within_tolerance"))
            for row in cj2
        ),
        "type99_ans5_records": sum(
            row.get("data_type") == "99"
            and _different(row.get("python_ans5"), row.get("xstar_ans5"))
            for row in leveltemp
        ),
        "thermal_family_rows": sum(
            _false(row.get("within_tolerance")) for row in thermal
        ),
    }
    baseline_match = counts == V0434_BASELINE_TARGET_COUNTS
    closure_ready = all(value == 0 for value in counts.values())
    return V0434RegressionGateResult(
        counts=counts,
        baseline_target_counts=V0434_BASELINE_TARGET_COUNTS,
        baseline_target_match=baseline_match,
        closure_ready=closure_ready,
        source_directory=str(root),
    )


def write_v0434_regression_gate_summary(
    result: V0434RegressionGateResult,
    path: str | Path,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
    return out


__all__ = [
    "V0434_BASELINE_TARGET_COUNTS",
    "V0434RegressionGateResult",
    "assess_v0434_oxygen_correction_gates",
    "write_v0434_regression_gate_summary",
]
