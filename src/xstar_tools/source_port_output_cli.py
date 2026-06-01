"""CLI for legacy pprint, detail/final writers, and physical parity."""
from __future__ import annotations

import argparse
from pathlib import Path

from .xstar.output_writers import (
    run_output_writer_validation,
    write_output_writer_validation_products,
)
from .xstar.physical_output_parity import compare_physical_output_directories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the source-order legacy pprint, savd/fstepr detail writers, "
            "and final writespectra sequence. Optionally compare independently "
            "generated standard XSTAR and Python output directories."
        )
    )
    parser.add_argument("--rtol", type=float, default=2.0e-7,
                        help="direct source-fragment reference tolerance")
    parser.add_argument("--atol", type=float, default=0.0)
    parser.add_argument(
        "--out-dir",
        default="xstar_output_writer_source_validation_v0470",
    )
    parser.add_argument("--xstar-run-dir", help="original XSTAR benchmark output directory")
    parser.add_argument("--python-run-dir", help="Python benchmark output directory")
    parser.add_argument("--parity-rtol", type=float, default=5.0e-5)
    parser.add_argument("--parity-atol", type=float, default=1.0e-30)
    parser.add_argument("--step-rtol", type=float, default=5.0e-3)
    parser.add_argument("--step-atol", type=float, default=5.0e-3)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.xstar_run_dir) != bool(args.python_run_dir):
        raise SystemExit("--xstar-run-dir and --python-run-dir must be supplied together")

    summary = run_output_writer_validation(
        out_dir=args.out_dir,
        rtol=args.rtol,
        atol=args.atol,
    )
    parity_requested = bool(args.xstar_run_dir)
    if parity_requested:
        parity = compare_physical_output_directories(
            args.xstar_run_dir,
            args.python_run_dir,
            rtol=args.parity_rtol,
            atol=args.parity_atol,
            step_rtol=args.step_rtol,
            step_atol=args.step_atol,
        )
        pdata = parity.as_dict()
        summary["physical_standard_benchmark_inputs_available"] = parity.inputs_available
        summary["physical_standard_benchmark_parity_run"] = parity.parity_run
        summary["physical_standard_benchmark_all_files_match"] = parity.all_files_ready
        summary["physical_standard_benchmark_required_files"] = list(parity.required_files)
        summary["physical_standard_benchmark_file_results"] = pdata["files"]
        summary["next_source_target"] = (
            "physical_all_atdb_standard_benchmark_output_parity_passed"
            if parity.all_files_ready
            else "diagnose_physical_all_atdb_standard_benchmark_output_differences"
        )

    paths = write_output_writer_validation_products(summary, args.out_dir)
    if args.print_summary:
        print("XSTAR legacy pprint, detail/final writer, and output-parity validation")
        print("--------------------------------------------------------------------")
        for key, value in summary.items():
            if key == "physical_standard_benchmark_file_results":
                print(f"{key}=<{len(value)} file results>")
            else:
                print(f"{key}={value}")
        for key, value in paths.items():
            print(f"{key}={value}")

    bounded_ready = bool(summary["detail_and_final_output_writer_source_acceptance_ready"])
    parity_ready = (not parity_requested) or bool(summary["physical_standard_benchmark_all_files_match"])
    return 0 if bounded_ready and parity_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
