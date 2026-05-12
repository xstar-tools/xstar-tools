#!/usr/bin/env python3
"""Populate the Python XSTAR live-state model from XSTAR detail outputs.

This example reads an existing XSTAR run directory containing products such as
``xo01_detail.fits``, ``xo01_detal2.fits``, ``xo01_detal4.fits`` and
``xout_abund1.fits``.  It maps the per-zone detail tables into the Python live
state containers used for future XSTAR-output recreation.
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

from xstar_atomic.xstar_detail import read_xstar_detail_run_state, write_xstar_detail_state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Populate a Python XSTAR live-state object from XSTAR detail FITS outputs.")
    parser.add_argument("--run-dir", required=True, help="XSTAR run directory containing xo01_detail/detal*.fits and xout_abund1.fits")
    parser.add_argument("--command-file", help="Optional run_xstar.sh command file; defaults to <run-dir>/run_xstar.sh when needed")
    parser.add_argument("--out-dir", default="xstar_detail_live_state", help="Output directory")
    parser.add_argument("--write-full-json", action="store_true", help="Write the large full state JSON, including arrays and records")
    parser.add_argument("--print-summary", action="store_true", help="Print status and output paths")
    args = parser.parse_args(argv)

    state = read_xstar_detail_run_state(args.run_dir, command_file=args.command_file)
    paths = write_xstar_detail_state(state, args.out_dir, write_full_json=args.write_full_json)
    if args.print_summary:
        print("XSTAR Python live-state population from detail outputs")
        print("-----------------------------------------------------")
        print(f"run_dir={args.run_dir}")
        print(f"n_zones={len(state.zones)}")
        print(f"status={state.status}")
        if state.zones:
            z = state.zones[-1]
            print(f"last_zone_T={z.temperature} K")
            print(f"last_zone_ne={z.electron_density} cm^-3")
            print(f"last_zone_logxi={z.ionization_parameter}")
            print(f"last_zone_n_epi={len(z.continuum.epi)}")
            print(f"last_zone_n_bremsa={len(z.continuum.bremsa)}")
            print(f"last_zone_n_bremsint={len(z.continuum.bremsint)}")
            print(f"last_zone_n_tau0_lines={z.lines.n_lines()}")
            print(f"last_zone_n_level_population_rows={sum(len(v) for v in z.level_populations.values())}")
            print(f"last_zone_missing_core_fields={';'.join(z.missing_core_fields())}")
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
