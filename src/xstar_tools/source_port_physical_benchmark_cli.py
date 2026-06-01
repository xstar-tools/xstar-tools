"""CLI for original-XSTAR versus Python physical output benchmark suites."""
from __future__ import annotations

import argparse

from .xstar.physical_benchmark_suite import (
    run_physical_benchmark_suite,
    write_physical_benchmark_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory original XSTAR run scripts, optionally regenerate the "
            "original products, and strictly compare independently generated "
            "Python detail/final outputs case by case."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--suite-archive", help="archive containing the original_xstar run tree")
    source.add_argument("--suite-root", help="already extracted original_xstar run tree")
    parser.add_argument("--out-dir", default="xstar_physical_benchmark_v0471")
    parser.add_argument("--selection", choices=("canonical-four", "all"), default="canonical-four")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="case path glob relative to the suite root; repeatable and overrides --selection",
    )
    parser.add_argument(
        "--original-run-root",
        help="mirrored root containing original products; defaults to the staged suite root",
    )
    parser.add_argument(
        "--python-run-root",
        help="mirrored root containing independently generated Python products",
    )
    parser.add_argument("--run-original", action="store_true")
    parser.add_argument("--xstar-executable", default="xstar")
    parser.add_argument("--clean-original-products", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--parity-rtol", type=float, default=5.0e-5)
    parser.add_argument("--parity-atol", type=float, default=1.0e-30)
    parser.add_argument("--step-rtol", type=float, default=5.0e-3)
    parser.add_argument("--step-atol", type=float, default=5.0e-3)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_physical_benchmark_suite(
        suite_archive=args.suite_archive,
        suite_root=args.suite_root,
        work_root=args.out_dir,
        selection=args.selection,
        case_patterns=args.case,
        original_run_root=args.original_run_root,
        python_run_root=args.python_run_root,
        run_original=args.run_original,
        xstar_executable=args.xstar_executable,
        clean_original_products=args.clean_original_products,
        timeout=args.timeout,
        rtol=args.parity_rtol,
        atol=args.parity_atol,
        step_rtol=args.step_rtol,
        step_atol=args.step_atol,
    )
    paths = write_physical_benchmark_products(result, args.out_dir)
    summary = result.as_dict()
    if args.print_summary:
        print("Original XSTAR versus Python physical benchmark")
        print("------------------------------------------------")
        for key in (
            "n_cases_discovered",
            "n_cases_selected",
            "n_canonical_cases_discovered",
            "attached_suite_62_case_inventory_ready",
            "canonical_four_case_gate_ready",
            "strict_ten_product_contract_ready",
            "original_run_scripts_parsed_ready",
            "original_output_cases_complete",
            "original_output_cases_incomplete",
            "original_execution_requested",
            "original_execution_ready",
            "parity_requested",
            "physical_benchmark_cases_run",
            "physical_benchmark_all_selected_cases_match",
            "python_physical_runner_built_in",
            "xstar_outputs_used_as_python_inputs",
            "physical_all_atdb_parity_claimed",
            "next_source_target",
        ):
            print(f"{key}={summary[key]}")
        print("selected_cases=" + repr([case.relative_case_dir for case in result.selected_cases]))
        for key, value in paths.items():
            print(f"{key}={value}")

    execution_ok = (not args.run_original) or result.original_execution_ready
    parity_ok = (args.python_run_root is None) or result.all_selected_cases_match
    return 0 if result.scripts_parsed_ready and execution_ok and parity_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
