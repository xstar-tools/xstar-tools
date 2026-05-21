"""Exact evaluation-2 matrix/solver/cooling parity diagnostic for ``dsec``."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .source_port_dsec_physical_cli import main as physical_main


def _strip_option(args: Sequence[str], option: str, *, takes_value: bool) -> List[str]:
    result: List[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == option:
            index += 2 if takes_value else 1
            continue
        if takes_value and token.startswith(option + "="):
            index += 1
            continue
        result.append(token)
        index += 1
    return result


def _clean_passthrough(args: Sequence[str]) -> List[str]:
    cleaned = list(args)
    for option, takes_value in (
        ("--out-dir", True),
        ("--maximum-evaluations", True),
        ("--global-writeback-mode", True),
        ("--leveltemp-lifecycle", True),
        ("--transition-input-mode", True),
        ("--compare-transition-internals", False),
        ("--transition-internal-evaluation-index", True),
        ("--xstar-transition-internal-probe-dir", True),
        ("--xstar-transition-internal-call-id", True),
        ("--print-summary", False),
    ):
        cleaned = _strip_option(cleaned, option, takes_value=takes_value)
    return cleaned


def _read_eval2_thermal(path: Path) -> Dict[str, Dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if int(row["evaluation_index"]) != 2:
            continue
        result[str(row["quantity"])] = {
            "python_value": float(row["python_value"]),
            "xstar_value": float(row["xstar_value"]),
            "absolute_difference": float(row["absolute_difference"]),
            "relative_difference": float(row["relative_difference"]),
            "within_tolerance": str(row["within_tolerance"]).strip().lower() == "true",
        }
    return result


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _false(value: Any) -> bool:
    return value is False


def _not_true(value: Any) -> bool:
    return value is not True


def _classify(
    runner: Mapping[str, Any],
    internal: Mapping[str, Any],
    thermal: Mapping[str, Mapping[str, Any]],
) -> str:
    if runner.get("dsec_transition_state_ready") is not True:
        return "exact_replay_state_not_verified"
    if _not_true(internal.get("pre_matrix_ready")):
        return "evaluation_2_pre_matrix_ion_rates_or_ion_selection"
    if _false(internal.get("same_call_matrix_topology_ready")):
        return "evaluation_2_matrix_topology"
    if _not_true(internal.get("same_call_matrix_active_closure_ready")):
        return "evaluation_2_active_matrix_or_rate_coefficients"
    if _not_true(internal.get("initial_solver_population_ready")):
        return "evaluation_2_solver_entry_population"
    if _false(internal.get("final_solver_topology_ready")):
        return "evaluation_2_final_solver_operator"
    if _not_true(internal.get("final_solver_active_population_ready")):
        return "evaluation_2_msolvelucy_population_solution"
    if _not_true(internal.get("final_solver_outer_start_ready")):
        return "evaluation_2_msolvelucy_outer_iteration_history"
    if _not_true(internal.get("final_solver_source_xtot_ready")):
        return "evaluation_2_msolvelucy_source_xtot_accumulation"
    if _not_true(internal.get("thermal_family_ready")):
        return "evaluation_2_thermal_coefficient_or_channel_accumulation"
    if _not_true(internal.get("element_array_ready")):
        return "evaluation_2_element_heating_cooling_accumulation"
    primary_ready = bool(
        thermal.get("cltot_pre_continuum", {}).get("within_tolerance")
        and thermal.get("hmctot", {}).get("within_tolerance")
    )
    if primary_ready:
        return "evaluation_2_internal_and_primary_thermal_parity"
    return "post_element_accumulation_or_probe_scope_mismatch"


def _top_failed_rows(rows: Sequence[Mapping[str, str]], *, limit: int = 10) -> List[Dict[str, Any]]:
    failed: List[Dict[str, Any]] = []
    for row in rows:
        marker = str(row.get("within_tolerance", "")).strip().lower()
        count_failure = False
        for name in ("n_outside_tolerance", "n_topology_mismatches"):
            value = row.get(name)
            if value not in (None, ""):
                try:
                    count_failure = count_failure or int(float(value)) > 0
                except ValueError:
                    pass
        if marker not in {"false", "0"} and not count_failure:
            continue
        item: Dict[str, Any] = dict(row)
        score = 0.0
        for name in (
            "relative_difference",
            "cj2_difference",
            "cj_difference",
            "aj1_difference",
            "aj2_difference",
            "absolute_difference",
            "l1_abs_aj1_difference",
            "l1_abs_aj2_difference",
            "l1_abs_cj_difference",
            "l1_abs_cj2_difference",
        ):
            value = row.get(name)
            if value not in (None, ""):
                try:
                    score = max(score, abs(float(value)))
                except ValueError:
                    pass
        item["diagnostic_score"] = score
        failed.append(item)
    failed.sort(key=lambda item: float(item.get("diagnostic_score", 0.0)), reverse=True)
    return failed[:limit]


def _write_summary(
    out: Path,
    *,
    runner: Mapping[str, Any],
    internal: Mapping[str, Any],
    thermal: Mapping[str, Mapping[str, Any]],
    matrix_family_rows: Sequence[Mapping[str, str]],
    thermal_family_rows: Sequence[Mapping[str, str]],
) -> Dict[str, Path]:
    conclusion = _classify(runner, internal, thermal)
    payload = {
        "port_version": "v0.4.54",
        "diagnostic": "exact_xstar_seeded_evaluation_2_internal_parity",
        "diagnostic_conclusion": conclusion,
        "transition_state_ready": runner.get("dsec_transition_state_ready"),
        "pre_matrix_ready": internal.get("pre_matrix_ready"),
        "same_call_matrix_ready": internal.get("same_call_matrix_ready"),
        "same_call_matrix_topology_ready": internal.get("same_call_matrix_topology_ready"),
        "same_call_matrix_coefficient_ready": internal.get("same_call_matrix_coefficient_ready"),
        "same_call_matrix_active_closure_ready": internal.get("same_call_matrix_active_closure_ready"),
        "initial_solver_population_ready": internal.get("initial_solver_population_ready"),
        "final_solver_snapshot_ready": internal.get("final_solver_snapshot_ready"),
        "final_solver_active_population_ready": internal.get("final_solver_active_population_ready"),
        "final_solver_outer_start_ready": internal.get("final_solver_outer_start_ready"),
        "final_solver_source_xtot_ready": internal.get("final_solver_source_xtot_ready"),
        "thermal_family_ready": internal.get("thermal_family_ready"),
        "element_array_ready": internal.get("element_array_ready"),
        "pre_continuum_summary_ready": internal.get("pre_continuum_summary_ready"),
        "primary_thermal": thermal,
        "top_failed_matrix_families": _top_failed_rows(matrix_family_rows),
        "top_failed_thermal_families": _top_failed_rows(thermal_family_rows),
        "internal_summary": dict(internal),
    }
    json_path = out / "xstar_dsec_evaluation2_internal_parity_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Exact XSTAR-seeded evaluation-2 internal parity",
        "",
        f"- Diagnostic conclusion: `{conclusion}`",
        f"- Exact transition state ready: `{payload['transition_state_ready']}`",
        f"- Pre-matrix ready: `{payload['pre_matrix_ready']}`",
        f"- Same-call matrix topology ready: `{payload['same_call_matrix_topology_ready']}`",
        f"- Same-call matrix coefficients ready: `{payload['same_call_matrix_coefficient_ready']}`",
        f"- Initial Lucy population ready: `{payload['initial_solver_population_ready']}`",
        f"- Final Lucy active populations ready: `{payload['final_solver_active_population_ready']}`",
        f"- Final outer-start populations ready: `{payload['final_solver_outer_start_ready']}`",
        f"- Source-order `xtot` ready: `{payload['final_solver_source_xtot_ready']}`",
        f"- Thermal-family parity ready: `{payload['thermal_family_ready']}`",
        f"- Element-array parity ready: `{payload['element_array_ready']}`",
    ]
    for name in ("cltot_pre_continuum", "hmctot", "elcter"):
        item = thermal.get(name)
        if item is None:
            continue
        lines.append(
            f"- {name}: relative difference `{item['relative_difference']:.9g}`, "
            f"within tolerance `{item['within_tolerance']}`"
        )
    md_path = out / "xstar_dsec_evaluation2_internal_parity_summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the exact XSTAR evaluation-2 call-entry state and compare "
            "Python's same-call ion rates, matrix terms, Lucy entry/final "
            "populations, and thermal families against the existing detailed "
            "XSTAR probe products."
        )
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    known, _unknown = build_parser().parse_known_args(raw)
    out = Path(known.out_dir)
    passthrough = _clean_passthrough(raw)
    run_args = [
        *passthrough,
        "--out-dir",
        str(out),
        "--maximum-evaluations",
        "2",
        "--global-writeback-mode",
        "dense-source",
        "--leveltemp-lifecycle",
        "reset-per-call",
        "--transition-input-mode",
        "replay-exact",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index",
        "2",
    ]
    exit_code = int(physical_main(run_args))

    runner = json.loads(
        (out / "xstar_dsec_physical_runner_summary.json").read_text(encoding="utf-8")
    )
    internal_dir = out / "evaluation_internal_parity"
    internal = json.loads(
        (internal_dir / "xstar_calc_hmc_all_pre_continuum_parity_summary.json").read_text(
            encoding="utf-8"
        )
    )
    thermal = _read_eval2_thermal(out / "xstar_dsec_thermal_decomposition_parity.csv")
    matrix_families = _read_csv(
        internal_dir / "xstar_calc_hmc_all_same_call_matrix_family_parity.csv"
    )
    thermal_families = _read_csv(
        internal_dir / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv"
    )
    products = _write_summary(
        out,
        runner=runner,
        internal=internal,
        thermal=thermal,
        matrix_family_rows=matrix_families,
        thermal_family_rows=thermal_families,
    )
    summary = json.loads(products["json"].read_text(encoding="utf-8"))
    if known.print_summary:
        print("Exact XSTAR-seeded evaluation-2 internal parity")
        print("------------------------------------------------")
        print(f"physical_exit_code={exit_code}")
        print(f"transition_state_ready={summary['transition_state_ready']}")
        print(f"pre_matrix_ready={summary['pre_matrix_ready']}")
        print(
            "same_call_matrix_topology_ready="
            f"{summary['same_call_matrix_topology_ready']}"
        )
        print(
            "same_call_matrix_coefficient_ready="
            f"{summary['same_call_matrix_coefficient_ready']}"
        )
        print(
            "initial_solver_population_ready="
            f"{summary['initial_solver_population_ready']}"
        )
        print(
            "final_solver_active_population_ready="
            f"{summary['final_solver_active_population_ready']}"
        )
        print(f"thermal_family_ready={summary['thermal_family_ready']}")
        print(f"element_array_ready={summary['element_array_ready']}")
        print(f"diagnostic_conclusion={summary['diagnostic_conclusion']}")
        for name, path in products.items():
            print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
