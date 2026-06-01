"""CLI for the bounded v0.4.79 zone-1 DSEC diagnostic."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .xstar.physical_runner import (
    XSTARPythonRunnerError,
    run_zone1_dsec_diagnostic_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run only physical zone 1, retain every calc_hmc_all DSEC entry "
            "state, execute exact same-entry deterministic replays, and write "
            "carbon rate/matrix/cooling diagnostics."
        )
    )
    parser.add_argument("--run-script", required=True)
    parser.add_argument("--atdb")
    parser.add_argument("--coheat-data")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--summary-json")
    parser.add_argument(
        "--xstar-probe-dir",
        help=(
            "Original-XSTAR zone-1 probe directory. When supplied, the fixed "
            "73198.4 K comparison uses the exact original xee/xpx state."
        ),
    )
    parser.add_argument(
        "--enforce-cooling-gate",
        action="store_true",
        help=(
            "Compare every carbon cooling matrix term against the original "
            "probe and stop before DSEC commits the first mismatching trial."
        ),
    )
    parser.add_argument("--cooling-rtol", type=float, default=5.0e-5)
    parser.add_argument("--cooling-atol", type=float, default=1.0e-30)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def _progress(event: str, details: dict[str, object]) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    payload = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
    print(f"[{stamp}] {event}" + (f" {payload}" if payload else ""), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_zone1_dsec_diagnostic_script(
            args.run_script,
            atdb_path=args.atdb,
            output_dir=args.output_dir,
            coheat_path=args.coheat_data,
            cache_dir=args.cache_dir,
            use_cache=not args.no_cache,
            rebuild_cache=args.rebuild_cache,
            progress_callback=_progress if args.progress else None,
            xstar_probe_dir=args.xstar_probe_dir,
            enforce_cooling_gate=args.enforce_cooling_gate,
            cooling_rtol=args.cooling_rtol,
            cooling_atol=args.cooling_atol,
        )
    except XSTARPythonRunnerError as exc:
        print(f"xstar-atomic zone-1 DSEC diagnostic: {exc}", file=sys.stderr)
        return 2
    try:
        summary = result.as_dict()
        if args.summary_json:
            path = Path(args.summary_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.print_summary:
            print("XSTAR Python zone-1 DSEC diagnostic")
            print("-----------------------------------")
            for key, value in summary.items():
                print(f"{key}={value}")
        return 0 if result.ready else 2
    finally:
        result.close()


if __name__ == "__main__":
    raise SystemExit(main())
