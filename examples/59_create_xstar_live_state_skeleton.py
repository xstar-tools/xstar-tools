#!/usr/bin/env python3
"""Create a Python live-state skeleton for recreating XSTAR outputs.

This example parses an XSTAR command or ``run_xstar.sh`` file and writes the
Python state object that future source-code-parity loops must populate before
writing ``xo01_detail.fits``, ``xo01_detal2.fits``, ``xo01_detal3.fits``,
``xo01_detal4.fits``, ``xout_abund1.fits``, ``xout_lines1.fits``,
``xout_rrc1.fits``, ``xout_cont1.fits``, and ``xout_spect1.fits``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    here = Path(__file__).resolve()
    root = here.parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_bootstrap_src_path()

from xstar_atomic.xstar_run import parse_xstar_command, parse_xstar_command_file
from xstar_atomic.xstar_state import create_initial_xstar_run_state_from_input, write_xstar_state_skeleton


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create a Python XSTAR live-state skeleton from an XSTAR command.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--command", help="Shell-style xstar command string")
    group.add_argument("--command-file", help="File containing an xstar command, e.g. run_xstar.sh")
    parser.add_argument("--n-zones", type=int, default=None, help="Override the number of state zones; default uses nsteps")
    parser.add_argument("--out-dir", default="xstar_live_state_skeleton", help="Output directory")
    parser.add_argument("--print-summary", action="store_true", help="Print written products and key status")
    args = parser.parse_args(argv)

    params = parse_xstar_command_file(args.command_file) if args.command_file else parse_xstar_command(args.command or "")
    state = create_initial_xstar_run_state_from_input(params, n_zones=args.n_zones)
    paths = write_xstar_state_skeleton(state, args.out_dir)
    if args.print_summary:
        print("XSTAR Python live-state skeleton")
        print("--------------------------------")
        print(f"n_parameters={len(params.parameters)}")
        print(f"n_zones={len(state.zones)}")
        print(f"status={state.status}")
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
