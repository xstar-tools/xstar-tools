"""Four-mode causality scan for the evaluation-1 -> evaluation-2 dsec transition."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .source_port_dsec_physical_cli import main as physical_main


_MODES = (
    ("A_current_v0451", "legacy-selected", "carry", "current v0.4.51 state"),
    ("B_zero_leveltemp_only", "legacy-selected", "reset-per-call", "zero leveltemp only"),
    ("C_dense_alias_only", "dense-source", "carry", "dense alias writeback only"),
    ("D_production_both", "dense-source", "reset-per-call", "both production corrections"),
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
    names = (
        "httot_pre_continuum",
        "cltot_pre_continuum",
        "httot2_pre_continuum",
        "cltot2_pre_continuum",
        "hmctot",
        "elcter",
    )
    return {name: float(row[name]) for name in names}


def _read_xstar_eval2(path: Path) -> Dict[str, float]:
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
    result: Dict[str, float] = {}
    for row in rows:
        if int(row["evaluation_index"]) == 2 and row["quantity"] in wanted:
            result[row["quantity"]] = float(row["xstar_value"])
    missing = wanted - result.keys()
    if missing:
        raise RuntimeError(f"missing XSTAR evaluation-2 quantities in {path}: {sorted(missing)}")
    return result


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _write_products(out: Path, rows: List[Dict[str, Any]]) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_dsec_transition_causality_scan.csv"
    fieldnames = list(rows[0]) if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    production = next((row for row in rows if row["mode_id"] == "D_production_both"), None)
    summary = {
        "port_version": "v0.4.52",
        "diagnostic": "evaluation_1_to_evaluation_2_causality_scan",
        "n_modes": len(rows),
        "production_mode_completed": production is not None,
        "production_transition_state_ready": (
            None if production is None else production["transition_state_ready"]
        ),
        "production_thermal_parity_ready": (
            None if production is None else production["thermal_parity_ready"]
        ),
        "modes": rows,
    }
    json_path = out / "xstar_dsec_transition_causality_scan_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_lines = [
        "# XSTAR/Python `dsec` evaluation-2 causality scan",
        "",
        "The four controlled modes isolate cross-call `leveltemp` reset and dense native global alias writeback.",
        "",
        "| Mode | Global writeback | leveltemp | cltot pre-cont rel. diff. | hmctot rel. diff. | Transition ready |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        md_lines.append(
            "| {mode_id} | {global_writeback_mode} | {leveltemp_lifecycle} | "
            "{cltot_pre_continuum_relative_difference:.6g} | "
            "{hmctot_relative_difference:.6g} | {transition_state_ready} |".format(**row)
        )
    md_path = out / "xstar_dsec_transition_causality_scan_summary.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run four two-evaluation physical dsec modes: current state, leveltemp reset only, "
            "dense global alias writeback only, and both production corrections. All other "
            "arguments are passed to examples/119/121 physical validation."
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
    xstar_values: Optional[Dict[str, float]] = None

    for mode_id, global_mode, leveltemp_mode, label in _MODES:
        mode_out = out / mode_id
        mode_args = [
            *passthrough,
            "--out-dir", str(mode_out),
            "--maximum-evaluations", "2",
            "--global-writeback-mode", global_mode,
            "--leveltemp-lifecycle", leveltemp_mode,
            "--terminal-continuum-seed-mode", "legacy-global",
        ]
        exit_code = int(physical_main(mode_args))
        py_values = _read_eval2(mode_out / "xstar_dsec_physical_evaluations.csv")
        if xstar_values is None:
            xstar_values = _read_xstar_eval2(
                mode_out / "xstar_dsec_thermal_decomposition_parity.csv"
            )
        runner = json.loads(
            (mode_out / "xstar_dsec_physical_runner_summary.json").read_text(
                encoding="utf-8"
            )
        )
        row: Dict[str, Any] = {
            "mode_id": mode_id,
            "label": label,
            "global_writeback_mode": global_mode,
            "leveltemp_lifecycle": leveltemp_mode,
            "exit_code": exit_code,
            "trajectory_parity_ready": bool(runner.get("dsec_trajectory_parity_ready")),
            "thermal_parity_ready": bool(runner.get("dsec_thermal_parity_ready")),
            "transition_state_ready": bool(runner.get("dsec_transition_state_ready")),
        }
        for name, py_value in py_values.items():
            xs_value = float(xstar_values[name])
            row[f"python_{name}"] = py_value
            row[f"xstar_{name}"] = xs_value
            row[f"{name}_absolute_difference"] = abs(py_value - xs_value)
            row[f"{name}_relative_difference"] = _relative_difference(py_value, xs_value)
        rows.append(row)

    products = _write_products(out, rows)
    if known.print_summary:
        print("Controlled evaluation-2 dsec causality scan")
        print("-------------------------------------------")
        for row in rows:
            print(
                f"{row['mode_id']}: cltot_pre_rel={row['cltot_pre_continuum_relative_difference']:.6g} "
                f"hmctot_rel={row['hmctot_relative_difference']:.6g} "
                f"transition_ready={row['transition_state_ready']}"
            )
        for name, path in products.items():
            print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
