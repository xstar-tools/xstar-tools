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
        "--mode",
        choices=("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp"),
        default=None,
        help=(
            "stable public execution mode. pure-python is the reference path; "
            "zone-python keeps Python radial orchestration with qualified modular C++ kernels; "
            "zone-cpp and zone-all map exactly to the frozen cpp-zone/cpp-all shared production paths; "
            "xstar-cpp invokes the native standalone executable. Legacy backend flags remain advanced aliases."
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
        "--zone-backend",
        choices=("python", "cpp-all", "cpp-zone"),
        default="python",
        help=(
            "radial-zone controller ownership. python preserves the accepted 10.1.1 "
            "Python controller; cpp-all delegates the complete trajectory in one C++ call; "
            "cpp-zone repeatedly calls run_next_zone() on one persistent shared-production C++ context until its natural source predicate reports done."
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
        "--profile-rss",
        action="store_true",
        help="include rss_start_mb/rss_end_mb/rss_delta_mb in performance profile rows; disabled by default",
    )
    parser.add_argument(
        "--profile-backend-calls",
        action="store_true",
        help="emit per-call C++ backend profile rows to live progress; summary counters are still accumulated when this is disabled",
    )
    parser.add_argument(
        "--profile-terminal",
        action="store_true",
        help="mirror profile_component timing rows to live terminal progress; disabled by default because summary.json carries the same timings",
    )
    parser.add_argument(
        "--progress-debug",
        action="store_true",
        help=(
            "print raw high-volume progress events such as dsec_evaluation; "
            "disabled by default so terminal output stays close to Fortran XSTAR"
        ),
    )
    parser.add_argument(
        "--skip-final-local-recompute",
        action="store_true",
        help=(
            "build final FITS products from the saved radial state instead of "
            "running the slow final xstarcalc/heatt/stpcut recompute; this is a "
            "performance mode and is recorded in provenance"
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


def _format_float(value: object, width: int, precision: int) -> str:
    try:
        number = float(value)
    except Exception:
        number = 0.0
    return f"{number:{width}.{precision}f}"


def _source_package_version() -> str:
    # Distribution/productization version.  Keep this distinct from the frozen
    # scientific revision reported by the execution layer.
    try:
        from xstar_tools.execution import package_version
        value = str(package_version()).strip()
        if value:
            return value
    except Exception:
        pass
    try:
        from importlib.metadata import version
        return str(version("xstar-tools")).strip()
    except Exception:
        return "unknown"


def _source_science_revision() -> str:
    try:
        from xstar_tools.execution import SCIENCE_REVISION
        return str(SCIENCE_REVISION).strip() or "unknown"
    except Exception:
        return "unknown"


def _make_progress_printer(*, include_memory: bool = False, debug: bool = False):
    _xstar_tools_package_version = _source_package_version()
    _xstar_tools_science_revision = _source_science_revision()

    printed_version = {"value": False}
    printed_radial_header = {"value": False}

    def _print_version_once() -> None:
        if not printed_version["value"]:
            print(f" xstar_tools package version {_xstar_tools_package_version}", flush=True)
            print(f" xstar_tools science revision {_xstar_tools_science_revision}", flush=True)
            print("", flush=True)
            printed_version["value"] = True

    def _print_raw(event: str, details: dict[str, object]) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        merged = dict(details)
        if include_memory:
            rss = _rss_mb()
            if rss is not None:
                merged["rss_mb"] = f"{rss:.1f}"
        payload = " ".join(f"{key}={value}" for key, value in sorted(merged.items()))
        print(f"[{stamp}] {event}" + (f" {payload}" if payload else ""), flush=True)

    def _print_xstar_header(details: dict[str, object]) -> None:
        _print_version_once()
        print(
            f" pass number={int(details.get('pass_index', 0)):12d}"
            f"{int(details.get('direction', 0)):12d}",
            flush=True,
        )
        print(
            "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)",
            flush=True,
        )
        print("                                                                  fwd    rev", flush=True)
        printed_radial_header["value"] = True

    def _print_zone_summary(details: dict[str, object]) -> None:
        if not printed_radial_header["value"]:
            _print_xstar_header(details)
        source_line = str(details.get("legacy_pprint_line", "") or "")
        if source_line.strip():
            print(source_line, flush=True)
            return
        line = (
            _format_float(details.get("log_radius_cm"), 8, 2)
            + _format_float(details.get("log_delta_r_over_r"), 7, 2)
            + _format_float(details.get("log_column_cm2"), 7, 2)
            + _format_float(details.get("log_xi"), 7, 2)
            + _format_float(details.get("electron_fraction"), 7, 2)
            + _format_float(details.get("log_density_cm3"), 7, 2)
            + _format_float(details.get("log_temperature_K"), 7, 2)
            + _format_float(details.get("heat_cool_forward_percent"), 7, 2)
            + _format_float(details.get("heat_cool_reverse_percent"), 7, 2)
            + _format_float(details.get("log_tau_forward"), 7, 2)
            + _format_float(details.get("log_tau_reverse"), 7, 2)
            + f"{int(details.get('numrec', 0)):3d}"
        )
        print(line, flush=True)

    def _progress_printer(event: str, details: dict[str, object]) -> None:
        if debug:
            _print_raw(event, details)
            return
        if event == "radial_pass_start":
            _print_xstar_header(details)
        elif event == "radial_zone_summary":
            _print_zone_summary(details)
        elif event == "radial_terminal_summary":
            _print_zone_summary(details)
        elif event == "output_writer_start":
            _print_version_once()
            print(" final print:           1", flush=True)
        elif event == "spectral_writer_start":
            _print_version_once()
            print(" xstar: Prepping to write spectral data", flush=True)
        elif event == "spectral_writer_done":
            print(" xstar: Done writing spectral data", flush=True)
        elif event == "output_writer_done":
            timing = details.get("timing_footer")
            if isinstance(timing, dict):
                try:
                    print(f" total time   {float(timing.get('total', 0.0))}", flush=True)
                except Exception:
                    pass
        elif event == "profile_component" and bool(details.get("emit_terminal", False)):
            _print_raw(event, details)

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
    execution = summary.get("provenance", {}).get("execution", {})
    if execution:
        print("requested_mode=" + str(execution.get("requested_mode", "unknown")))
        print("actual_mode=" + str(execution.get("actual_mode", "unknown")))
        print("package_version=" + str(execution.get("package_version", "unknown")))
        print("science_revision=" + str(execution.get("science_revision", "unknown")))
        print("c_api_abi=" + str(execution.get("c_api_abi", "unknown")))
        print("zone_abi=" + str(execution.get("zone_abi", "unknown")))
        print("cpp=" + repr(execution.get("cpp", {})))
        print("cpu=" + repr(execution.get("cpu", {})))
        print("fallback_events=" + repr(execution.get("fallback_events", [])))
        print("atomic_data=" + repr(execution.get("atomic_data", {})))
    if "zone_backend" in summary.get("provenance", {}):
        print("zone_backend=" + repr(summary.get("provenance", {}).get("zone_backend")))
    compact = summary.get("provenance", {}).get("compact_active_atdb_export")
    if compact:
        print("compact_active_atdb_export=" + repr(compact))
    warnings = summary.get("warnings", [])
    if warnings:
        print("warnings=" + repr(warnings))


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw_argv)
    from .execution import advanced_execution_provenance, infer_public_mode, resolve_mode, execution_provenance, package_version, run_xstar as run_public_xstar

    advanced_flags = ("--backend", "--solver-backend", "--zone-backend", "--rates-backend", "--matrix-backend", "--emissivity-backend")
    if args.mode is not None and any(flag in raw_argv for flag in advanced_flags):
        print("xstar-tools: --mode cannot be combined with advanced backend flags; use either the stable public mode or the legacy aliases", file=sys.stderr)
        return 2
    explicit_public_mapping = None
    if args.mode is not None:
        mapping = resolve_mode(args.mode)
        explicit_public_mapping = mapping
        args.backend = mapping.global_backend
        args.solver_backend = mapping.solver_backend
        args.rates_backend = mapping.rates_backend
        args.matrix_backend = mapping.matrix_backend
        args.emissivity_backend = mapping.emissivity_backend
        args.zone_backend = mapping.zone_backend
        requested_public_mode = mapping.public_mode
    else:
        requested_public_mode = infer_public_mode(
            zone_backend=args.zone_backend, backend=args.backend, solver_backend=args.solver_backend,
            rates_backend=args.rates_backend, matrix_backend=args.matrix_backend, emissivity_backend=args.emissivity_backend,
        )

    _apply_thread_limit(args.blas_threads)

    if requested_public_mode == "xstar-cpp":
        if args.original_run_dir is not None:
            print("xstar-tools: xstar-cpp uses external qualification and does not accept --original-run-dir", file=sys.stderr)
            return 2
        command = args.command
        if args.command_file is not None:
            command = Path(args.command_file).read_text(encoding="utf-8").strip()
        try:
            result = run_public_xstar(
                mode="xstar-cpp", run_script=args.run_script, command=command, atdb_path=args.atdb,
                coheat_path=args.coheat_data, output_dir=args.output_dir, overwrite=not args.no_overwrite,
            )
            summary = result.as_dict()
        except Exception as exc:
            print(f"xstar-tools: xstar-cpp failed: {exc}", file=sys.stderr)
            return 2
        if args.print_summary:
            _print_run(summary)
        if args.summary_json:
            path = Path(args.summary_json); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if bool(summary.get("ready")) else 2

    os.environ["XSTAR_ATOMIC_BACKEND"] = str(args.backend)
    os.environ["XSTAR_ATOMIC_SOLVER_BACKEND"] = str(args.solver_backend)
    if args.rates_backend is not None:
        os.environ["XSTAR_ATOMIC_RATES_BACKEND"] = str(args.rates_backend)
    if args.matrix_backend is not None:
        os.environ["XSTAR_ATOMIC_MATRIX_BACKEND"] = str(args.matrix_backend)
    if args.emissivity_backend is not None:
        os.environ["XSTAR_ATOMIC_EMISSIVITY_BACKEND"] = str(args.emissivity_backend)
    # Stable public modes own the complete modular backend selection.  In
    # particular, pure-python must not inherit a component-specific C++ choice
    # from the caller's environment.  Legacy advanced flags keep their prior
    # environment semantics when --mode is not used.
    if explicit_public_mapping is not None:
        os.environ["XSTAR_ATOMIC_OPACITY_BACKEND"] = explicit_public_mapping.opacity_backend
        os.environ["XSTAR_ATOMIC_THERMAL_BACKEND"] = explicit_public_mapping.thermal_backend
        os.environ["XSTAR_ATOMIC_ENGINE_BACKEND"] = explicit_public_mapping.engine_backend

    def annotate(summary: dict[str, object]) -> dict[str, object]:
        provenance = dict(summary.get("provenance", {}) or {})
        if requested_public_mode == "advanced":
            provenance["execution"] = advanced_execution_provenance(
                provenance=provenance,
                atdb_path=provenance.get("atdb_path", args.atdb),
                coheat_path=args.coheat_data,
                mapping={
                    "zone_backend": args.zone_backend, "backend": args.backend, "solver_backend": args.solver_backend,
                    "rates_backend": args.rates_backend, "matrix_backend": args.matrix_backend,
                    "emissivity_backend": args.emissivity_backend,
                },
            )
        else:
            provenance["execution"] = execution_provenance(
                requested_mode=requested_public_mode, provenance=provenance,
                atdb_path=provenance.get("atdb_path", args.atdb), coheat_path=args.coheat_data,
            )
        summary["provenance"] = provenance
        return summary

    if args.zone_backend in {"cpp-all", "cpp-zone"}:
        requested_components = {
            "global": args.backend,
            "solver": args.solver_backend,
            "rates": args.rates_backend or args.backend,
            "matrix": args.matrix_backend or args.backend,
            "emissivity": args.emissivity_backend or args.backend,
        }
        non_cpp = {k: v for k, v in requested_components.items() if v != "cpp"}
        if non_cpp:
            print(f"xstar-atomic Python runner: --zone-backend {args.zone_backend} requires an all-C++ backend selection; observed {non_cpp}", file=sys.stderr)
            return 2
        if args.run_script is None:
            print(f"xstar-atomic Python runner: --zone-backend {args.zone_backend} requires --run-script", file=sys.stderr)
            return 2
        if args.original_run_dir is not None:
            print(f"xstar-atomic Python runner: --zone-backend {args.zone_backend} uses external qualification rather than --original-run-dir", file=sys.stderr)
            return 2
        try:
            from .xstar.cpp_backend_production_zone import (
                SharedProductionZoneError,
                run_shared_production_zone_backend,
            )
            summary = run_shared_production_zone_backend(
                mode=args.zone_backend,
                run_script=args.run_script,
                atdb_path=args.atdb,
                coheat_path=args.coheat_data,
                output_dir=args.output_dir,
                overwrite=not args.no_overwrite,
                version=package_version(),
            )
            summary = annotate(summary)
        except SharedProductionZoneError as exc:
            print(f"xstar-atomic Python runner: {exc}", file=sys.stderr)
            return 2
        if args.print_summary:
            _print_run(summary)
        if args.summary_json:
            path = Path(args.summary_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if bool(summary.get("ready")) else 2
    # Import NumPy-heavy runner modules only after thread caps/backend selection are set.
    from .xstar.physical_output_diagnostics import diagnose_physical_output_mismatch
    from .xstar.physical_runner import (
        XSTARPythonRunnerError,
        run_c5_ne1_acceptance,
        run_xstar_python_command,
        run_xstar_python_script,
    )

    progress_callback = (
        _make_progress_printer(include_memory=args.progress_memory, debug=args.progress_debug)
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
                profile_rss=args.profile_rss,
                profile_backend_calls=args.profile_backend_calls,
                profile_terminal=args.profile_terminal,
                progress_debug=args.progress_debug,
                mg_line_kernel=args.mg_line_kernel,
                backend=args.backend,
                rates_backend=args.rates_backend,
                matrix_backend=args.matrix_backend,
                emissivity_backend=args.emissivity_backend,
                compact_atdb_export=args.compact_atdb_export,
                output_final_recompute=not args.skip_final_local_recompute,
            )
            summary = result.as_dict()
            if "provenance" in summary:
                summary = annotate(summary)
            elif isinstance(summary.get("python_run"), dict):
                summary["python_run"] = annotate(dict(summary["python_run"]))
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
                provenance = dict(result.python_run.provenance or {})
                selection = dict(provenance.get("backend_selection", {}))
                print(f"global_backend_requested={selection.get('global_backend', args.backend)}")
                for backend_name, requested_value in (
                    ("solver_backend", args.solver_backend),
                    ("rates_backend", args.rates_backend or args.backend),
                    ("matrix_backend", args.matrix_backend or args.backend),
                    ("emissivity_backend", args.emissivity_backend or args.backend),
                ):
                    status = dict(provenance.get(backend_name, {}))
                    active = status.get("active", "unknown")
                    requested = status.get("requested", requested_value)
                    if active == "python":
                        backend_label = "python_reference"
                    elif active == "unavailable":
                        backend_label = status.get("cpp_import_error") or "unavailable"
                    else:
                        backend_label = status.get("cpp_backend_name") or status.get("status") or "python_reference"
                    print(f"{backend_name}_requested={requested}")
                    print(f"{backend_name}_active={active}")
                    print(f"{backend_name}_implementation={backend_label}")
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
                profile_rss=args.profile_rss,
                profile_backend_calls=args.profile_backend_calls,
                profile_terminal=args.profile_terminal,
                progress_debug=args.progress_debug,
                mg_line_kernel=args.mg_line_kernel,
                backend=args.backend,
                rates_backend=args.rates_backend,
                matrix_backend=args.matrix_backend,
                emissivity_backend=args.emissivity_backend,
                compact_atdb_export=args.compact_atdb_export,
                output_final_recompute=not args.skip_final_local_recompute,
            )
            summary = annotate(result.as_dict())
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
                profile_rss=args.profile_rss,
                profile_backend_calls=args.profile_backend_calls,
                profile_terminal=args.profile_terminal,
                progress_debug=args.progress_debug,
                mg_line_kernel=args.mg_line_kernel,
                backend=args.backend,
                rates_backend=args.rates_backend,
                matrix_backend=args.matrix_backend,
                emissivity_backend=args.emissivity_backend,
                compact_atdb_export=args.compact_atdb_export,
                output_final_recompute=not args.skip_final_local_recompute,
            )
            summary = annotate(result.as_dict())
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
