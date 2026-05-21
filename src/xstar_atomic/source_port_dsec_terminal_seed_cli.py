"""Causality scan for the terminal compact-continuum Lucy seed."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .source_port_dsec_physical_cli import main as physical_main


_MODES = (
    (
        "A_legacy_global_terminal_seed",
        "legacy-global",
        "pre-v0.4.55 global xilevg value retained in the final compact row",
    ),
    (
        "B_source_zero_terminal_seed",
        "source-zero",
        "calc_hmc_element.f90 x(ipmat2+1)=0 before msolvelucy",
    ),
)


def _strip_option(args: Sequence[str], option: str, *, takes_value: bool) -> List[str]:
    out: List[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == option:
            index += 2 if takes_value else 1
            continue
        if takes_value and token.startswith(option + "="):
            index += 1
            continue
        out.append(token)
        index += 1
    return out


def _clean_passthrough(args: Sequence[str]) -> List[str]:
    cleaned = list(args)
    for option, takes_value in (
        ("--out-dir", True),
        ("--maximum-evaluations", True),
        ("--global-writeback-mode", True),
        ("--leveltemp-lifecycle", True),
        ("--terminal-continuum-seed-mode", True),
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
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if int(row["evaluation_index"]) != 2:
            continue
        out[str(row["quantity"])] = {
            "python_value": float(row["python_value"]),
            "xstar_value": float(row["xstar_value"]),
            "absolute_difference": float(row["absolute_difference"]),
            "relative_difference": float(row["relative_difference"]),
            "within_tolerance": str(row["within_tolerance"]).strip().lower() == "true",
        }
    return out


def _initial_failures(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    failures: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("within_tolerance", "")).strip().lower() == "true":
            continue
        failures.append(
            {
                "element_z": int(row["element_z"]),
                "compact_index": int(row["compact_index"]),
                "python_initial_population": float(row["python_initial_population"]),
                "xstar_initial_population": float(row["xstar_initial_population"]),
                "absolute_difference": float(row["absolute_difference"]),
                "relative_difference": float(row["relative_difference"]),
            }
        )
    return failures


def _classify(source: Mapping[str, Any]) -> str:
    if source.get("transition_state_ready") is not True:
        return "exact_replay_state_not_verified"
    if source.get("initial_solver_population_ready") is not True:
        return "source_terminal_zero_seed_not_verified"
    primary_ready = bool(
        source.get("cltot_pre_continuum_within_tolerance")
        and source.get("hmctot_within_tolerance")
    )
    if primary_ready:
        return "terminal_continuum_seed_was_primary_cause"
    if source.get("final_solver_active_population_ready") is not True:
        return "terminal_seed_corrected_remaining_msolvelucy_population_solution"
    if source.get("final_solver_outer_start_ready") is not True:
        return "terminal_seed_corrected_remaining_msolvelucy_iteration_history"
    if source.get("final_solver_source_xtot_ready") is not True:
        return "terminal_seed_corrected_remaining_source_xtot"
    if source.get("thermal_family_ready") is not True:
        return "terminal_seed_corrected_remaining_thermal_family"
    if source.get("element_array_ready") is not True:
        return "terminal_seed_corrected_remaining_element_accumulation"
    return "post_element_accumulation_or_probe_scope_mismatch"


def _write_products(out: Path, rows: List[Dict[str, Any]]) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_dsec_terminal_continuum_seed_scan.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["mode_id"])
        writer.writeheader()
        writer.writerows(rows)

    source = next(row for row in rows if row["terminal_continuum_seed_mode"] == "source-zero")
    conclusion = _classify(source)
    payload = {
        "port_version": "v0.4.55",
        "diagnostic": "evaluation_2_terminal_continuum_seed_causality",
        "diagnostic_conclusion": conclusion,
        "source_zero_transition_state_ready": source["transition_state_ready"],
        "source_zero_initial_solver_population_ready": source[
            "initial_solver_population_ready"
        ],
        "source_zero_final_solver_active_population_ready": source[
            "final_solver_active_population_ready"
        ],
        "source_zero_thermal_family_ready": source["thermal_family_ready"],
        "source_zero_element_array_ready": source["element_array_ready"],
        "modes": rows,
    }
    json_path = out / "xstar_dsec_terminal_continuum_seed_scan_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Evaluation-2 terminal continuum seed causality",
        "",
        "| Mode | Initial seed ready | Final active populations ready | cltot pre-cont. rel. diff. | hmctot rel. diff. |",
        "|---|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {mode_id} | {initial_solver_population_ready} | "
            "{final_solver_active_population_ready} | "
            "{cltot_pre_continuum_relative_difference:.9g} | "
            "{hmctot_relative_difference:.9g} |".format(**row)
        )
    lines.extend(["", f"- Diagnostic conclusion: `{conclusion}`"])
    md_path = out / "xstar_dsec_terminal_continuum_seed_scan_summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run exact XSTAR-seeded evaluation 2 with the pre-v0.4.55 terminal "
            "global seed and with the source calc_hmc_element x(ipmat2+1)=0 seed."
        )
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    known, _unknown = parser.parse_known_args(raw)
    out = Path(known.out_dir)
    passthrough = _clean_passthrough(raw)
    rows: List[Dict[str, Any]] = []

    for mode_id, seed_mode, label in _MODES:
        mode_out = out / mode_id
        run_args = [
            *passthrough,
            "--out-dir",
            str(mode_out),
            "--maximum-evaluations",
            "2",
            "--global-writeback-mode",
            "dense-source",
            "--leveltemp-lifecycle",
            "reset-per-call",
            "--terminal-continuum-seed-mode",
            seed_mode,
            "--transition-input-mode",
            "replay-exact",
            "--compare-transition-internals",
            "--transition-internal-evaluation-index",
            "2",
        ]
        exit_code = int(physical_main(run_args))
        runner = json.loads(
            (mode_out / "xstar_dsec_physical_runner_summary.json").read_text(
                encoding="utf-8"
            )
        )
        internal_dir = mode_out / "evaluation_internal_parity"
        internal = json.loads(
            (internal_dir / "xstar_calc_hmc_all_pre_continuum_parity_summary.json").read_text(
                encoding="utf-8"
            )
        )
        thermal = _read_eval2_thermal(
            mode_out / "xstar_dsec_thermal_decomposition_parity.csv"
        )
        failures = _initial_failures(
            internal_dir / "xstar_calc_hmc_all_msolvelucy_initial_population_parity.csv"
        )
        row: Dict[str, Any] = {
            "mode_id": mode_id,
            "label": label,
            "terminal_continuum_seed_mode": seed_mode,
            "exit_code": exit_code,
            "transition_state_ready": runner.get("dsec_transition_state_ready") is True,
            "pre_matrix_ready": internal.get("pre_matrix_ready") is True,
            "same_call_matrix_active_closure_ready": (
                internal.get("same_call_matrix_active_closure_ready") is True
            ),
            "initial_solver_population_ready": (
                internal.get("initial_solver_population_ready") is True
            ),
            "n_initial_solver_population_failures": len(failures),
            "initial_solver_population_failures_json": json.dumps(
                failures, sort_keys=True
            ),
            "final_solver_active_population_ready": (
                internal.get("final_solver_active_population_ready") is True
            ),
            "final_solver_outer_start_ready": (
                internal.get("final_solver_outer_start_ready") is True
            ),
            "final_solver_source_xtot_ready": (
                internal.get("final_solver_source_xtot_ready") is True
            ),
            "thermal_family_ready": internal.get("thermal_family_ready") is True,
            "element_array_ready": internal.get("element_array_ready") is True,
            "primary_thermal": thermal,
        }
        for quantity in (
            "httot_pre_continuum",
            "cltot_pre_continuum",
            "httot2_pre_continuum",
            "cltot2_pre_continuum",
            "hmctot",
            "elcter",
        ):
            item = thermal[quantity]
            row[f"python_{quantity}"] = item["python_value"]
            row[f"xstar_{quantity}"] = item["xstar_value"]
            row[f"{quantity}_absolute_difference"] = item["absolute_difference"]
            row[f"{quantity}_relative_difference"] = item["relative_difference"]
            row[f"{quantity}_within_tolerance"] = item["within_tolerance"]
        # CSV cannot store the nested object directly.
        row["primary_thermal_json"] = json.dumps(row.pop("primary_thermal"), sort_keys=True)
        rows.append(row)

    products = _write_products(out, rows)
    if known.print_summary:
        print("Terminal compact-continuum seed causality")
        print("-----------------------------------------")
        for row in rows:
            print(
                f"{row['mode_id']}: "
                f"initial_ready={row['initial_solver_population_ready']} "
                f"final_active_ready={row['final_solver_active_population_ready']} "
                f"cltot_pre_rel={row['cltot_pre_continuum_relative_difference']:.9g} "
                f"hmctot_rel={row['hmctot_relative_difference']:.9g}"
            )
        payload = json.loads(products["json"].read_text(encoding="utf-8"))
        print(f"diagnostic_conclusion={payload['diagnostic_conclusion']}")
        for name, path in products.items():
            print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
