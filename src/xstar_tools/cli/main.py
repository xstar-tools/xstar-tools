"""Unified xstar-tools command line interface."""
from __future__ import annotations

import argparse
import json
import sys


def _print_backend_table(data: dict) -> None:
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
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_backend_table(data)
    return 0


def _doctor(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xstar-tools doctor", description="Check xstar-tools execution-mode readiness.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--require", choices=("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp"), default="pure-python")
    ns = p.parse_args(argv)
    from xstar_tools.backends import describe
    data = describe()
    ok = bool(data["modes"][ns.require]["available"])
    data["doctor"] = {"required_mode": ns.require, "ready": ok}
    if ns.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_backend_table(data)
        print(f"doctor_required_mode={ns.require}")
        print(f"doctor_ready={str(ok).lower()}")
    return 0 if ok else 2


def usage() -> str:
    return (
        "Usage: xstar-tools <command> [options]\n\n"
        "Commands:\n"
        "  run       Run XSTAR using --mode pure-python|zone-python|zone-cpp|zone-all|xstar-cpp\n"
        "  backends  Show available execution modes and native capabilities\n"
        "  doctor    Check runtime readiness (optionally --require MODE)\n"
        "  version   Show package and science revisions\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(usage(), end="")
        return 0
    command, rest = args[0], args[1:]
    if command == "run":
        from xstar_tools.source_port_physical_runner_cli import main as run_main
        return int(run_main(rest))
    if command == "backends":
        return _backends(rest)
    if command == "doctor":
        return _doctor(rest)
    if command == "benchmark":
        from xstar_tools.benchmarks.public_suite import main as benchmark_main
        return int(benchmark_main(rest))
    if command in {"version", "--version", "-V"}:
        from xstar_tools.execution import package_version, SCIENCE_REVISION
        print(f"xstar-tools {package_version()} (science {SCIENCE_REVISION})")
        return 0
    print(f"unknown xstar-tools command: {command}", file=sys.stderr)
    print(usage(), file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
