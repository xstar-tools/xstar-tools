"""Unified ``xstar-tools`` command line interface.

Milestone 5 keeps the normal user surface deliberately small.  Scientific
execution is delegated to the same :class:`xstar_tools.XStarConfig` /
:func:`xstar_tools.run_xstar` orchestration layer used by the public Python API.
Historical development and qualification tools remain available through
``dev`` / ``qualify`` namespaces and their legacy console-script entry points
for one deprecation cycle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Callable

_LOG = logging.getLogger("xstar_tools.cli")


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")
    return target


class _JsonEventLog:
    """Small JSONL event/provenance writer for normal CLI runs."""

    def __init__(self, path: str | Path | None):
        self.path = None if path is None else Path(path).expanduser().resolve()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **payload: Any) -> None:
        if self.path is None:
            return
        row = {
            "schema": "xstar-tools-cli-event-v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=_json_default) + "\n")


def _configure_logging(level: str) -> None:
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=numeric, format="%(levelname)s %(name)s: %(message)s")
    _LOG.setLevel(numeric)


def _print_backend_table(data: dict[str, Any]) -> None:
    print(f"xstar-tools package={data['package_version']} science={data['science_revision']} zone_abi={data['zone_abi']}")
    print("mode         available  execution")
    print("-----------  ---------  ------------------------------------------------------------")
    for name, info in data["modes"].items():
        print(f"{name:<11}  {str(bool(info['available'])):<9}  {info['description']}")


def _backends(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xstar-tools backends", description="Show stable execution modes and native capabilities.")
    p.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    from xstar_tools.backends import describe
    data = describe()
    if ns.json:
        print(json.dumps(data, indent=2, sort_keys=True, default=_json_default))
    else:
        _print_backend_table(data)
    return 0


def _doctor(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xstar-tools doctor", description="Check xstar-tools execution-mode and optional data readiness.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--require", choices=("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp"), default="pure-python")
    p.add_argument("--data-dir", help="also validate a local XSTAR scientific-data directory")
    ns = p.parse_args(argv)
    from xstar_tools.backends import describe
    data = describe()
    mode_ok = bool(data["modes"][ns.require]["available"])
    data_ok = True
    data_report: dict[str, Any] | None = None
    if ns.data_dir:
        try:
            from xstar_tools.data import XStarData
            locator = XStarData.from_directory(ns.data_dir)
            validation = locator.validate()
            data_report = {"validation": validation.as_dict(), "identity": locator.identity()}
        except Exception as exc:
            data_ok = False
            data_report = {"valid": False, "error": str(exc), "directory": str(Path(ns.data_dir).expanduser())}
    ok = mode_ok and data_ok
    data["doctor"] = {"required_mode": ns.require, "mode_ready": mode_ok, "data": data_report, "ready": ok}
    if ns.json:
        print(json.dumps(data, indent=2, sort_keys=True, default=_json_default))
    else:
        _print_backend_table(data)
        print(f"doctor_required_mode={ns.require}")
        print(f"doctor_mode_ready={str(mode_ok).lower()}")
        if data_report is not None:
            print(f"doctor_data_ready={str(data_ok).lower()}")
            if not data_ok:
                print(f"doctor_data_error={data_report['error']}")
        print(f"doctor_ready={str(ok).lower()}")
    return 0 if ok else 2


def _run(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="xstar-tools run",
        description="Run XSTAR through the stable public XStarConfig/run_xstar orchestration layer.",
    )
    p.add_argument("input", help="XSTAR .par file or source-faithful run_xstar.sh/.cmd input")
    p.add_argument("--mode", choices=("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp"), default="pure-python")
    p.add_argument("--data-dir", required=True, help="directory containing atdb.fits and coheat.dat")
    p.add_argument("--output-dir", default="run1", help="output directory; default: run1")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--overwrite", action="store_true", help="replace a non-empty output directory deterministically")
    p.add_argument("--no-progress", action="store_true", help="disable human-readable science progress")
    p.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"), default="INFO")
    p.add_argument("--json-log", help="write structured JSONL run events and final provenance")
    p.add_argument("--summary-json", help="write the final XStarResult as JSON")
    p.add_argument("--cache-dir")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--rebuild-cache", action="store_true")
    p.add_argument("--no-reproducible", action="store_true")
    ns = p.parse_args(argv)

    _configure_logging(ns.log_level)
    events = _JsonEventLog(ns.json_log)
    try:
        # This import is intentionally the public API, not a second CLI-specific
        # execution path.  The Milestone-5 gate characterizes this invariant.
        from xstar_tools import XStarConfig, run_xstar
        config = XStarConfig.from_par_file(
            ns.input,
            data_dir=ns.data_dir,
            output_dir=ns.output_dir,
            mode=ns.mode,
            threads=ns.threads,
            progress=not ns.no_progress,
            log_level=ns.log_level,
            reproducible=not ns.no_reproducible,
            overwrite=ns.overwrite,
            cache_dir=ns.cache_dir,
            use_cache=not ns.no_cache,
            rebuild_cache=ns.rebuild_cache,
        )
        events.emit(
            "run_started",
            input=str(Path(ns.input).expanduser()),
            requested_mode=ns.mode,
            output_dir=str(config.output_dir),
            threads=ns.threads,
        )
        _LOG.info("starting XSTAR mode=%s input=%s output=%s", ns.mode, ns.input, config.output_dir)
        result = run_xstar(config)
        payload = result.as_dict()
        events.emit("run_completed", result=payload, provenance=payload.get("provenance", {}))
        if ns.summary_json:
            target = _write_json(ns.summary_json, payload)
            _LOG.info("wrote run summary %s", target)
        execution = dict(payload.get("provenance", {}).get("execution", {}))
        _LOG.info(
            "completed status=%s actual_mode=%s runtime_seconds=%.6g output=%s",
            result.status,
            execution.get("actual_mode", result.mode),
            result.runtime_seconds,
            result.output_dir,
        )
        for warning in result.warnings:
            _LOG.warning("%s", warning)
        return 0 if result.success else (result.return_code or 2)
    except Exception as exc:
        events.emit("run_failed", error=type(exc).__name__, message=str(exc))
        _LOG.error("run failed: %s", exc)
        return 2


def _inspect(argv: list[str]) -> int:
    from xstar_tools.inspect import main as inspect_main
    result = inspect_main(argv)
    return int(result or 0)


def _data(argv: list[str]) -> int:
    from xstar_tools.data import main as data_main
    result = data_main(argv)
    return int(result or 0)


def _compare(argv: list[str]) -> int:
    from xstar_tools.benchmarks.public_suite import compare_suite, _repo_root
    p = argparse.ArgumentParser(
        prog="xstar-tools compare",
        description="Compare completed public-mode runs with the accepted Fortran and optional frozen-C++ references.",
    )
    p.add_argument("--package", default=str(_repo_root()))
    p.add_argument("--run-root", required=True)
    p.add_argument("--fortran-reference-archive", required=True)
    p.add_argument("--cpp-reference-archive")
    p.add_argument("--out")
    ns = p.parse_args(argv)
    report = compare_suite(
        package=ns.package,
        run_root=ns.run_root,
        fortran_reference_archive=ns.fortran_reference_archive,
        cpp_reference_archive=ns.cpp_reference_archive,
        out_dir=ns.out,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=_json_default))
    ok = bool(report["fortran_all_science_accept"]) and report["cpp44_all_exact_accept"] is not False
    return 0 if ok else 3


def _dispatch_namespace(prog: str, argv: list[str], commands: dict[str, tuple[str, Callable[[list[str]], int]]]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(f"Usage: {prog} <command> [options]\n\nCommands:")
        for name, (help_text, _func) in commands.items():
            print(f"  {name:<18} {help_text}")
        return 0
    command, rest = argv[0], argv[1:]
    item = commands.get(command)
    if item is None:
        print(f"unknown {prog} command: {command}", file=sys.stderr)
        return 2
    return int(item[1](rest))


def _dev(argv: list[str]) -> int:
    def legacy_run(args: list[str]) -> int:
        from xstar_tools.source_port_physical_runner_cli import main as legacy_main
        return int(legacy_main(args))

    def benchmark(args: list[str]) -> int:
        from xstar_tools.benchmarks.public_suite import main as benchmark_main
        return int(benchmark_main(args))

    return _dispatch_namespace(
        "xstar-tools dev",
        argv,
        {
            "legacy-run": ("advanced historical source-port runner", legacy_run),
            "benchmark": ("public benchmark runner/listing development interface", benchmark),
        },
    )


def _qualify(argv: list[str]) -> int:
    def benchmark(args: list[str]) -> int:
        from xstar_tools.benchmarks.public_suite import main as benchmark_main
        return int(benchmark_main(args))

    def original(args: list[str]) -> int:
        from xstar_tools.xstar.original_parity_gate import main as gate_main
        return int(gate_main(args))

    def cpp(args: list[str]) -> int:
        from xstar_tools.xstar.cpp_parity_gate import main as gate_main
        return int(gate_main(args))

    def reference(args: list[str]) -> int:
        from xstar_tools.xstar.qualification import main as qualify_main
        return int(qualify_main(args))

    return _dispatch_namespace(
        "xstar-tools qualify",
        argv,
        {
            "benchmark": ("run/list/compare the canonical qualification suite", benchmark),
            "original-parity": ("legacy original-XSTAR parity gate", original),
            "cpp-parity": ("legacy Python/C++ parity gate", cpp),
            "reference": ("reference-bundle qualification utilities", reference),
        },
    )


def _version(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xstar-tools version", add_help=False)
    p.add_argument("--json", action="store_true")
    p.add_argument("-h", "--help", action="help")
    ns = p.parse_args(argv)
    from xstar_tools.execution import C_API_ABI_VERSION, SCIENCE_REVISION, ZONE_ABI_VERSION, package_version
    data = {
        "package_version": package_version(),
        "science_revision": SCIENCE_REVISION,
        "c_api_abi": C_API_ABI_VERSION,
        "production_zone_abi": ZONE_ABI_VERSION,
    }
    if ns.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"xstar-tools package version {data['package_version']}")
        print(f"xstar-tools science revision {data['science_revision']}")
        print(f"xstar-tools C API ABI {data['c_api_abi']}")
        print(f"xstar-tools production-zone ABI {data['production_zone_abi']}")
    return 0


def usage() -> str:
    return (
        "Usage: xstar-tools <command> [options]\n\n"
        "User commands:\n"
        "  run       Run XSTAR through the stable public Python orchestration layer\n"
        "  inspect   Inspect the packed XSTAR atomic database\n"
        "  data      Configure, locate, validate, or explicitly download XSTAR data\n"
        "  backends  Show available execution modes and native capabilities\n"
        "  compare   Compare completed runs with accepted references\n"
        "  doctor    Check runtime/backend/data readiness\n"
        "  version   Show package, science, and ABI revisions\n\n"
        "Development/qualification:\n"
        "  dev       Advanced/development compatibility interfaces\n"
        "  qualify   Qualification and parity interfaces\n\n"
        "Legacy compatibility:\n"
        "  benchmark Retained for one deprecation cycle; use 'xstar-tools qualify benchmark'\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(usage(), end="")
        return 0
    command, rest = args[0], args[1:]
    commands: dict[str, Callable[[list[str]], int]] = {
        "run": _run,
        "inspect": _inspect,
        "data": _data,
        "backends": _backends,
        "compare": _compare,
        "doctor": _doctor,
        "version": _version,
        "dev": _dev,
        "qualify": _qualify,
    }
    if command in {"--version", "-V"}:
        return _version(rest)
    if command == "benchmark":
        print("xstar-tools: 'benchmark' is deprecated; use 'xstar-tools qualify benchmark'", file=sys.stderr)
        from xstar_tools.benchmarks.public_suite import main as benchmark_main
        return int(benchmark_main(rest))
    handler = commands.get(command)
    if handler is not None:
        return handler(rest)
    print(f"unknown xstar-tools command: {command}", file=sys.stderr)
    print(usage(), file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
