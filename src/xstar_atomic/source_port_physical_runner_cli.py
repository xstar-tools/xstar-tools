"""CLI for the public source-faithful Python XSTAR execution API."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys


def _apply_thread_limit(value: int | None) -> None:
    """Set BLAS/OpenMP thread caps before importing NumPy-heavy runner code."""
    if value is None:
        return
    threads = max(1, int(value))
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        os.environ[name] = str(threads)
    os.environ.setdefault("MALLOC_ARENA_MAX", "2")


def _rss_mb() -> float | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except OSError:
        return None
    return None


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
    parser.add_argument(
        "--cache-dir",
        help=(
            "directory for vectorized source-port NPZ caches; by default the "
            "cache sidecars are written beside atdb.fits"
        ),
    )
    parser.add_argument("--no-cache", action="store_true", help="disable NPZ pointer/metadata caches")
    parser.add_argument("--rebuild-cache", action="store_true", help="rebuild both source-port NPZ caches")
    parser.add_argument("--summary-json", help="write machine-readable run/parity summary")
    parser.add_argument(
        "--diagnostics",
        choices=("full", "summary", "none"),
        default="full",
        help=(
            "optional Python diagnostic products: full preserves v0.5.35 "
            "CSV/JSONL runtime diagnostics; summary suppresses high-volume "
            "runtime files but keeps compact in-memory parity summaries; none "
            "suppresses optional diagnostics while still writing ordinary XSTAR products"
        ),
    )
    parser.add_argument(
        "--diagnostics-dir",
        help=(
            "after an original/Python parity run, write compact structural, "
            "thermal, line, and level mismatch diagnostics to this directory"
        ),
    )
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument(
        "--progress",
        action="store_true",
        help="print live ATDB/cache/pass/zone/writer/comparator progress",
    )
    parser.add_argument(
        "--progress-memory",
        action="store_true",
        help="include current process RSS in progress lines",
    )
    parser.add_argument(
        "--blas-threads",
        type=int,
        default=None,
        help=(
            "cap BLAS/OpenMP numerical-library threads before importing NumPy; "
            "use 1 for memory-safe Mg/Ca benchmark runs"
        ),
    )
    parser.add_argument(
        "--solver-backend",
        choices=("python", "cpp", "auto"),
        default="python",
        help=(
            "level-population/ionization linear-solve backend: python is the "
            "source-faithful reference, cpp requires the optional C++ extension, "
            "and auto uses C++ when available with Python fallback"
        ),
    )
    parser.add_argument(
        "--backend",
        choices=("python", "cpp", "auto"),
        default="python",
        help=(
            "global backend default for modular kernels. Per-kernel flags below "
            "override this value. Python remains the source-faithful reference."
        ),
    )
    parser.add_argument(
        "--rates-backend",
        choices=("python", "cpp", "auto"),
        default=None,
        help="rate-construction backend selection for future compact C++ kernels",
    )
    parser.add_argument(
        "--matrix-backend",
        choices=("python", "cpp", "auto"),
        default=None,
        help="matrix-assembly backend selection for future compact C++ kernels",
    )
    parser.add_argument(
        "--emissivity-backend",
        choices=("python", "cpp", "auto"),
        default=None,
        help="emissivity/opacity backend selection for future compact C++ kernels",
    )
    parser.add_argument(
        "--compact-atdb-export",
        help=(
            "write a compact active-ATDB NPZ for the active H/He/Mg subset; "
            "used by modular C++ backend development and Athena++ post-processing"
        ),
    )
    parser.add_argument(
        "--no-active-subset",
        action="store_true",
        help=(
            "disable per-case active ATDB subset precomputation; by default "
            "the runner caches active element/ion/level maps to reduce repeated radial-solve work"
        ),
    )
    parser.add_argument(
        "--profile-components",
        nargs="?",
        const="summary",
        default="none",
        choices=("none", "summary", "nested", "forensic"),
        help=(
            "profiling detail level. summary records coarse component timings; "
            "nested adds selected Mg ion/category totals; forensic enables the "
            "v0.5.48-style per-ion/per-record detail. Supplying the flag without "
            "a value is equivalent to summary."
        ),
    )
    parser.add_argument(
        "--mg-line-kernel",
        choices=("python", "numpy"),
        default="python",
        help=(
            "Mg Z=12 record_type=4 line-emissivity kernel. python is the "
            "source-faithful reference; numpy enables the guarded compact-array path "
            "where available and falls back to python otherwise."
        ),
    )
    return parser


def _make_progress_printer(*, include_memory: bool = False):
    def _progress_printer(event: str, details: dict[str, object]) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        merged = dict(details)
        if include_memory:
            rss = _rss_mb()
            if rss is not None:
                merged["rss_mb"] = f"{rss:.1f}"
        payload = " ".join(f"{key}={value}" for key, value in sorted(merged.items()))
        print(f"[{stamp}] {event}" + (f" {payload}" if payload else ""), flush=True)
    return _progress_printer


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
    provenance = summary.get("provenance", {})
    for key in (
        "pointer_cache_path", "pointer_cache_status",
        "metadata_cache_path", "metadata_cache_status",
    ):
        if key in provenance:
            print(f"{key}={provenance.get(key)}")
    print("diagnostics=" + str(summary.get("provenance", {}).get("diagnostics_mode", "unknown")))
    print("solver_backend=" + str(summary.get("provenance", {}).get("solver_backend", "unknown")))
    print("backend_selection=" + repr(summary.get("provenance", {}).get("backend_selection", {})))
    compact = summary.get("provenance", {}).get("compact_active_atdb_export")
    if compact:
        print("compact_active_atdb_export=" + repr(compact))
    warnings = summary.get("warnings", [])
    if warnings:
        print("warnings=" + repr(warnings))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _apply_thread_limit(args.blas_threads)
    os.environ["XSTAR_ATOMIC_BACKEND"] = str(args.backend)
    os.environ["XSTAR_ATOMIC_SOLVER_BACKEND"] = str(args.solver_backend)
    if args.rates_backend is not None:
        os.environ["XSTAR_ATOMIC_RATES_BACKEND"] = str(args.rates_backend)
    if args.matrix_backend is not None:
        os.environ["XSTAR_ATOMIC_MATRIX_BACKEND"] = str(args.matrix_backend)
    if args.emissivity_backend is not None:
        os.environ["XSTAR_ATOMIC_EMISSIVITY_BACKEND"] = str(args.emissivity_backend)
    # Import NumPy-heavy runner modules only after thread caps/backend selection are set.
    from .source_port.physical_output_diagnostics import diagnose_physical_output_mismatch
    from .source_port.physical_runner import (
        XSTARPythonRunnerError,
        run_c5_ne1_acceptance,
        run_xstar_python_command,
        run_xstar_python_script,
    )

    progress_callback = (
        _make_progress_printer(include_memory=args.progress_memory)
        if args.progress
        else None
    )
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
                cache_dir=args.cache_dir,
                use_cache=not args.no_cache,
                rebuild_cache=args.rebuild_cache,
                progress_callback=progress_callback,
                diagnostics_mode=args.diagnostics,
                active_subset=not args.no_active_subset,
                profile_components=args.profile_components,
                mg_line_kernel=args.mg_line_kernel,
                backend=args.backend,
                rates_backend=args.rates_backend,
                matrix_backend=args.matrix_backend,
                emissivity_backend=args.emissivity_backend,
                compact_atdb_export=args.compact_atdb_export,
            )
            summary = result.as_dict()
            if args.diagnostics_dir is not None:
                diagnosis = diagnose_physical_output_mismatch(
                    result.original_run_dir,
                    result.python_run.output_dir,
                    output_dir=args.diagnostics_dir,
                    state=result.python_run.final_state,
                )
                summary["diagnostics"] = diagnosis.as_dict()
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
                print(f"diagnostics={args.diagnostics}")
                print(f"solver_backend={args.solver_backend}")
                print(f"backend={args.backend}")
                print(f"rates_backend={args.rates_backend or args.backend}")
                if args.diagnostics_dir is not None:
                    print(f"diagnostics_dir={Path(args.diagnostics_dir).resolve()}")
        elif args.run_script is not None:
            result = run_xstar_python_script(
                args.run_script,
                atdb_path=args.atdb,
                output_dir=args.output_dir,
                coheat_path=args.coheat_data,
                overwrite=not args.no_overwrite,
                cache_dir=args.cache_dir,
                use_cache=not args.no_cache,
                rebuild_cache=args.rebuild_cache,
                progress_callback=progress_callback,
                diagnostics_mode=args.diagnostics,
                active_subset=not args.no_active_subset,
                profile_components=args.profile_components,
                mg_line_kernel=args.mg_line_kernel,
                backend=args.backend,
                rates_backend=args.rates_backend,
                matrix_backend=args.matrix_backend,
                emissivity_backend=args.emissivity_backend,
                compact_atdb_export=args.compact_atdb_export,
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
                cache_dir=args.cache_dir,
                use_cache=not args.no_cache,
                rebuild_cache=args.rebuild_cache,
                progress_callback=progress_callback,
                diagnostics_mode=args.diagnostics,
                active_subset=not args.no_active_subset,
                profile_components=args.profile_components,
                mg_line_kernel=args.mg_line_kernel,
                backend=args.backend,
                rates_backend=args.rates_backend,
                matrix_backend=args.matrix_backend,
                emissivity_backend=args.emissivity_backend,
                compact_atdb_export=args.compact_atdb_export,
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
