"""CLI for the public source-faithful Python XSTAR execution API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .source_port.physical_runner import (
    XSTARPythonRunnerError,
    run_c5_ne1_acceptance,
    run_xstar_python_command,
    run_xstar_python_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the translated Python XSTAR path from a literal XSTAR command "
            "or run_xstar.sh, write the strict ten products, and optionally "
            "compare them directly with original XSTAR products."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-script", help="run_xstar.sh parsed as data; it is never sourced")
    source.add_argument("--command", help="literal xstar key=value command")
    source.add_argument("--command-file", help="text file containing a literal XSTAR command")
    parser.add_argument("--atdb", help="atdb.fits path or directory; otherwise use configured resolver")
    parser.add_argument("--coheat-data", help="optional explicit coheat.dat path")
    parser.add_argument("--output-dir", required=True, help="directory for Python XSTAR products")
    parser.add_argument("--original-run-dir", help="directory containing the ten original XSTAR products")
    parser.add_argument("--parity-rtol", type=float, default=5.0e-5)
    parser.add_argument("--parity-atol", type=float, default=1.0e-30)
    parser.add_argument("--step-rtol", type=float, default=5.0e-3)
    parser.add_argument("--step-atol", type=float, default=5.0e-3)
    parser.add_argument("--no-overwrite", action="store_true")
    parser.add_argument("--summary-json", help="write machine-readable run/parity summary")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def _load_command(args: argparse.Namespace) -> str:
    if args.command is not None:
        return args.command
    if args.command_file is not None:
        return Path(args.command_file).read_text(encoding="utf-8")
    raise AssertionError("command source not selected")


def _print_run(summary: dict[str, object]) -> None:
    print("Python XSTAR physical runner")
    print("----------------------------")
    for key in (
        "ready", "output_dir", "completed_passes", "completed_zones",
    ):
        print(f"{key}={summary.get(key)}")
    products = summary.get("products", {})
    print("written_products=" + repr(sorted(products)))
    print("xstar_outputs_used_as_python_inputs=" + str(summary.get("provenance", {}).get("xstar_outputs_used_as_python_inputs")))
    warnings = summary.get("warnings", [])
    if warnings:
        print("warnings=" + repr(warnings))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.original_run_dir is not None:
            if args.run_script is None:
                raise XSTARPythonRunnerError(
                    "the strict c5_ne1 acceptance gate requires --run-script"
                )
            result = run_c5_ne1_acceptance(
                run_script=args.run_script,
                atdb_path=args.atdb,
                python_output_dir=args.output_dir,
                original_run_dir=args.original_run_dir,
                coheat_path=args.coheat_data,
                rtol=args.parity_rtol,
                atol=args.parity_atol,
                step_rtol=args.step_rtol,
                step_atol=args.step_atol,
                require_original_products=True,
                raise_on_failure=False,
            )
            summary = result.as_dict()
            if args.print_summary:
                print("Python XSTAR c5_ne1 direct parity acceptance")
                print("------------------------------------------------")
                for key in (
                    "all_ten_python_products_ready",
                    "original_products_available",
                    "parity_run",
                    "all_files_match",
                    "ready",
                    "xstar_outputs_used_as_python_inputs",
                ):
                    print(f"{key}={summary[key]}")
                print(f"python_output_dir={result.python_run.output_dir}")
                print(f"original_run_dir={result.original_run_dir}")
        elif args.run_script is not None:
            result = run_xstar_python_script(
                args.run_script,
                atdb_path=args.atdb,
                output_dir=args.output_dir,
                coheat_path=args.coheat_data,
                overwrite=not args.no_overwrite,
            )
            summary = result.as_dict()
            if args.print_summary:
                _print_run(summary)
        else:
            result = run_xstar_python_command(
                _load_command(args),
                atdb_path=args.atdb,
                output_dir=args.output_dir,
                coheat_path=args.coheat_data,
                overwrite=not args.no_overwrite,
            )
            summary = result.as_dict()
            if args.print_summary:
                _print_run(summary)
    except XSTARPythonRunnerError as exc:
        print(f"xstar-atomic Python runner: {exc}", file=sys.stderr)
        return 2

    if args.summary_json:
        path = Path(args.summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if bool(summary.get("ready")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
