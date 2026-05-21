"""Exact XSTAR-seeded evaluation replay for the dsec transition diagnostic."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .source_port_dsec_physical_cli import main as physical_main


_MODES = (
    ("P_python_transition", "compare-only", "Python evaluation-1 output seeds evaluation 2"),
    ("X_xstar_seeded_transition", "replay-exact", "Exact XSTAR evaluation-2 call-entry state"),
)


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
        ("--terminal-continuum-seed-mode", True),
        ("--transition-input-mode", True),
        ("--print-summary", False),
    ):
        cleaned = _strip_option(cleaned, option, takes_value=takes_value)
    return cleaned


def _read_eval2(path: Path) -> Dict[str, float]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    row = next((item for item in rows if int(item["evaluation_index"]) == 2), None)
    if row is None:
        raise RuntimeError(f"evaluation 2 missing from {path}")
    fields = (
        "httot_pre_continuum",
        "cltot_pre_continuum",
        "httot2_pre_continuum",
        "cltot2_pre_continuum",
        "hmctot",
        "elcter",
    )
    return {field: float(row[field]) for field in fields}


def _read_xstar_eval2(path: Path) -> tuple[Dict[str, float], Dict[str, bool]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    wanted = {
        "httot_pre_continuum",
        "cltot_pre_continuum",
        "httot2_pre_continuum",
        "cltot2_pre_continuum",
        "hmctot",
        "elcter",
    }
    values: Dict[str, float] = {}
    ready: Dict[str, bool] = {}
    for row in rows:
        if int(row["evaluation_index"]) != 2 or row["quantity"] not in wanted:
            continue
        quantity = row["quantity"]
        values[quantity] = float(row["xstar_value"])
        ready[quantity] = str(row["within_tolerance"]).strip().lower() == "true"
    missing = wanted - values.keys()
    if missing:
        raise RuntimeError(f"missing XSTAR evaluation-2 quantities in {path}: {sorted(missing)}")
    return values, ready


def _read_elements(path: Path) -> Dict[int, Dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if int(row["evaluation_index"]) != 2:
            continue
        z = int(row["element_z"])
        result[z] = dict(row)
    return result


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _element_comparison(
    current: Mapping[int, Mapping[str, Any]],
    replay: Mapping[int, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    numeric = (
        "heating_per_abundance",
        "cooling_per_abundance",
        "heating2_per_abundance",
        "cooling2_per_abundance",
        "heating",
        "cooling",
        "heating2",
        "cooling2",
        "electron_contribution",
    )
    for z in sorted(set(current) | set(replay)):
        p = current.get(z)
        x = replay.get(z)
        row: Dict[str, Any] = {
            "element_z": z,
            "present_in_python_transition": p is not None,
            "present_in_xstar_seeded_transition": x is not None,
        }
        source = x or p or {}
        for name in (
            "abundance",
            "selected_min_ion_stage",
            "selected_max_ion_stage",
            "basis_size",
            "n_superlevels",
            "solver_converged",
            "solver_method",
            "outer_iterations",
            "fixed_point_iterations",
            "used_dense_fallback",
        ):
            row[name] = source.get(name, "")
        for name in numeric:
            p_value = float(p[name]) if p is not None else float("nan")
            x_value = float(x[name]) if x is not None else float("nan")
            row[f"python_transition_{name}"] = p_value
            row[f"xstar_seeded_{name}"] = x_value
            row[f"{name}_absolute_change"] = abs(p_value - x_value)
            row[f"{name}_relative_change"] = _relative_difference(p_value, x_value)
        rows.append(row)
    rows.sort(key=lambda item: float(item["cooling_absolute_change"]), reverse=True)
    return rows


def _write_products(
    out: Path,
    mode_rows: List[Dict[str, Any]],
    element_rows: List[Dict[str, Any]],
) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    scan_csv = out / "xstar_dsec_transition_exact_replay_scan.csv"
    with scan_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mode_rows[0]))
        writer.writeheader()
        writer.writerows(mode_rows)

    element_csv = out / "xstar_dsec_transition_exact_replay_elements.csv"
    with element_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(element_rows[0]) if element_rows else ["element_z"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(element_rows)

    exact = next(row for row in mode_rows if row["mode_id"] == "X_xstar_seeded_transition")
    primary_ready = bool(
        exact["cltot_pre_continuum_within_tolerance"]
        and exact["hmctot_within_tolerance"]
    )
    transition_ready = bool(exact["transition_state_ready"])
    if not transition_ready:
        conclusion = "exact_replay_state_not_verified"
    elif primary_ready:
        conclusion = "evaluation_1_population_solution_or_writeback"
    else:
        conclusion = "evaluation_2_element_matrix_solver_or_cooling"
    leading = element_rows[0]["element_z"] if element_rows else None
    summary = {
        "port_version": "v0.4.53",
        "diagnostic": "exact_xstar_seeded_evaluation_2_replay",
        "transition_state_ready": transition_ready,
        "exact_seed_primary_thermal_ready": primary_ready,
        "diagnostic_conclusion": conclusion,
        "largest_seed_sensitive_element_z": leading,
        "modes": mode_rows,
        "element_comparison_rows": len(element_rows),
    }
    summary_json = out / "xstar_dsec_transition_exact_replay_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Exact XSTAR-seeded `dsec` evaluation-2 replay",
        "",
        "| Mode | cltot pre-cont. rel. diff. | hmctot rel. diff. | Transition state ready |",
        "|---|---:|---:|---|",
    ]
    for row in mode_rows:
        lines.append(
            "| {mode_id} | {cltot_pre_continuum_relative_difference:.6g} | "
            "{hmctot_relative_difference:.6g} | {transition_state_ready} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"- Exact-seed primary thermal parity: `{primary_ready}`",
            f"- Diagnostic conclusion: `{conclusion}`",
            f"- Largest seed-sensitive element Z: `{leading}`",
        ]
    )
    summary_md = out / "xstar_dsec_transition_exact_replay_summary.md"
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "scan_csv": scan_csv,
        "elements_csv": element_csv,
        "json": summary_json,
        "markdown": summary_md,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run evaluation 2 twice: first from Python evaluation-1 output, then "
            "from the exact captured XSTAR evaluation-2 call-entry state. Python "
            "still computes all rates, matrices, populations, and thermal totals."
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

    mode_rows: List[Dict[str, Any]] = []
    elements: Dict[str, Dict[int, Dict[str, Any]]] = {}
    xstar_values: Optional[Dict[str, float]] = None
    for mode_id, input_mode, label in _MODES:
        mode_out = out / mode_id
        mode_args = [
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
            "legacy-global",
            "--transition-input-mode",
            input_mode,
        ]
        exit_code = int(physical_main(mode_args))
        py_values = _read_eval2(mode_out / "xstar_dsec_physical_evaluations.csv")
        parity_path = mode_out / "xstar_dsec_thermal_decomposition_parity.csv"
        values, ready = _read_xstar_eval2(parity_path)
        if xstar_values is None:
            xstar_values = values
        runner = json.loads(
            (mode_out / "xstar_dsec_physical_runner_summary.json").read_text(
                encoding="utf-8"
            )
        )
        row: Dict[str, Any] = {
            "mode_id": mode_id,
            "label": label,
            "transition_input_mode": input_mode,
            "exit_code": exit_code,
            "trajectory_parity_ready": bool(runner.get("dsec_trajectory_parity_ready")),
            "thermal_parity_ready": bool(runner.get("dsec_thermal_parity_ready")),
            "transition_state_ready": bool(runner.get("dsec_transition_state_ready")),
        }
        for name, py_value in py_values.items():
            xstar_value = float(values[name])
            row[f"python_{name}"] = py_value
            row[f"xstar_{name}"] = xstar_value
            row[f"{name}_absolute_difference"] = abs(py_value - xstar_value)
            row[f"{name}_relative_difference"] = _relative_difference(py_value, xstar_value)
            row[f"{name}_within_tolerance"] = bool(ready[name])
        mode_rows.append(row)
        elements[mode_id] = _read_elements(
            mode_out / "xstar_dsec_element_thermal_decomposition.csv"
        )

    element_rows = _element_comparison(
        elements["P_python_transition"], elements["X_xstar_seeded_transition"]
    )
    products = _write_products(out, mode_rows, element_rows)
    if known.print_summary:
        print("Exact XSTAR-seeded evaluation-2 replay")
        print("--------------------------------------")
        for row in mode_rows:
            print(
                f"{row['mode_id']}: "
                f"cltot_pre_rel={row['cltot_pre_continuum_relative_difference']:.6g} "
                f"hmctot_rel={row['hmctot_relative_difference']:.6g} "
                f"transition_ready={row['transition_state_ready']}"
            )
        summary = json.loads(products["json"].read_text(encoding="utf-8"))
        print(f"diagnostic_conclusion={summary['diagnostic_conclusion']}")
        for name, path in products.items():
            print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
