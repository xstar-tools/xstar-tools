"""Offline v0.4.59 final-residual source-semantic acceptance.

This reuses a completed v0.4.58 post-final replay tree.  It does not rerun XSTAR
or the physical Python solver.  Strict residual parity remains visible while
acceptance follows the literal ``dsec.f90`` convergence decision.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .xstar_dsec_post_final_replay_cli import (
    _classify,
    _exact_final_source_semantic_summary,
)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required post-final-replay product is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise RuntimeError(f"required post-final-replay CSV is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _resolve_results_dir(path: str | Path) -> Path:
    root = Path(path)
    if (root / "xstar_dsec_post_final_replay_summary.json").is_file():
        return root
    nested = root / "xstar_dsec_post_final_replay_v0458"
    if (nested / "xstar_dsec_post_final_replay_summary.json").is_file():
        return nested
    raise RuntimeError(
        "could not find xstar_dsec_post_final_replay_summary.json under "
        f"{root} or {nested}"
    )


def _acceptance_ready(payload: Mapping[str, Any]) -> bool:
    return bool(
        payload.get("python_dsec_converged")
        and payload.get("evaluation_count_ready")
        and payload.get("source_control_flow_ready")
        and payload.get("thermal_component_trajectory_ready")
        and payload.get("thermal_residual_sign_ready")
        and payload.get("evaluation2_internal_ready")
        and payload.get("post_dsec_calc_hmc_all_executed")
        and payload.get("natural_final_physics_ready")
        and payload.get("exact_post_dsec_replay_executed")
        and payload.get("exact_post_dsec_fixed_state_semantic_ready")
        and payload.get("frozen_v0444_complete_fixed_state_regression")
    )


def _write_products(out: Path, payload: Dict[str, Any]) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data["port_version"] = "v0.4.59"
    data["diagnostic"] = "offline_post_dsec_final_residual_source_semantics"
    data["unrestricted_source_semantic_acceptance_ready"] = _acceptance_ready(data)
    data["ready_to_advance_to_bremsmap"] = data[
        "unrestricted_source_semantic_acceptance_ready"
    ]
    data["diagnostic_conclusion"] = _classify(data)

    json_path = out / "xstar_dsec_final_residual_semantics_summary.json"
    json_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path = out / "xstar_dsec_final_residual_semantics_summary.md"
    md_path.write_text(
        "# Final post-`dsec` residual source semantics\n\n"
        f"- Diagnostic conclusion: `{data['diagnostic_conclusion']}`\n"
        f"- Source-semantic acceptance: `{data['unrestricted_source_semantic_acceptance_ready']}`\n"
        f"- Ready to advance to `bremsmap`: `{data['ready_to_advance_to_bremsmap']}`\n"
        f"- Exact strict fixed-state parity: `{data.get('exact_post_dsec_fixed_state_parity_ready')}`\n"
        f"- Exact source-semantic fixed-state parity: `{data.get('exact_post_dsec_fixed_state_semantic_ready')}`\n"
        f"- Residual-only strict failure: `{data.get('exact_post_dsec_hmctot_residual_only_failure')}`\n"
        f"- Source expression parity: `{data.get('exact_post_dsec_hmctot_source_expression_ready')}`\n"
        f"- Python/XSTAR source convergence: `{data.get('exact_post_dsec_python_hmctot_converged')}/{data.get('exact_post_dsec_xstar_hmctot_converged')}`\n"
        f"- Source thermal tolerance: `{data.get('exact_post_dsec_source_thermal_tolerance')}`\n"
        f"- Strict failure quantities: `{data.get('exact_post_dsec_strict_failure_quantities')}`\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reclassify a completed v0.4.58 post-final replay using XSTAR's "
            "literal heatf/dsec residual expression and convergence criterion."
        )
    )
    parser.add_argument("--v0458-results-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_results_dir(args.v0458_results_dir)
    payload = _read_json(root / "xstar_dsec_post_final_replay_summary.json")
    exact_dir = (
        root
        / "unrestricted_source_zero_post_replay"
        / "post_dsec_exact_replay"
    )
    exact_summary = _read_json(
        exact_dir / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.json"
    )
    exact_rows = _read_rows(
        exact_dir / "xstar_calc_hmc_all_complete_fixed_state_parity.csv"
    )
    payload.update(_exact_final_source_semantic_summary(exact_summary, exact_rows))
    payload["source_results_dir"] = str(root)
    products = _write_products(Path(args.out_dir), payload)
    data = _read_json(products["json"])
    if args.print_summary:
        print("Final post-dsec normalized-residual source semantics")
        print("------------------------------------------------------")
        print(
            "exact_post_dsec_fixed_state_parity_ready="
            f"{data.get('exact_post_dsec_fixed_state_parity_ready')}"
        )
        print(
            "exact_post_dsec_fixed_state_semantic_ready="
            f"{data.get('exact_post_dsec_fixed_state_semantic_ready')}"
        )
        print(
            "exact_post_dsec_hmctot_source_expression_ready="
            f"{data.get('exact_post_dsec_hmctot_source_expression_ready')}"
        )
        print(
            "exact_post_dsec_hmctot_convergence_decision_ready="
            f"{data.get('exact_post_dsec_hmctot_convergence_decision_ready')}"
        )
        print(
            "unrestricted_source_semantic_acceptance_ready="
            f"{data['unrestricted_source_semantic_acceptance_ready']}"
        )
        print(f"ready_to_advance_to_bremsmap={data['ready_to_advance_to_bremsmap']}")
        print(f"diagnostic_conclusion={data['diagnostic_conclusion']}")
        print(f"json={products['json']}")
        print(f"markdown={products['markdown']}")
    return 0 if data["unrestricted_source_semantic_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
