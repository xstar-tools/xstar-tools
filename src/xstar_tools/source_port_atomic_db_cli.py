"""Command-line entry point for the translated XSTAR ATDB setup subsystem."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .xstar import load_atomic_database_state, write_atomic_database_products


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the source-faithful Python translation of XSTAR readtbl/setptrs "
            "and write reusable derived-pointer products."
        )
    )
    parser.add_argument("--atdb", required=True, help="Path to XSTAR atdb.fits")
    parser.add_argument(
        "--out-dir", default="xstar_tools_database_port_v041", help="Output directory"
    )
    parser.add_argument(
        "--pointer-cache",
        help="Optional explicit derived-pointer NPZ cache path; defaults inside --out-dir",
    )
    parser.add_argument("--rebuild-pointer-cache", action="store_true")
    parser.add_argument("--no-pointer-cache", action="store_true")
    parser.add_argument("--llinabs", action="store_true", help="Apply setptrs absolute line wavelengths")
    parser.add_argument("--no-memmap", action="store_true", help="Disable FITS memory mapping")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = (
        None
        if args.no_pointer_cache
        else Path(args.pointer_cache)
        if args.pointer_cache
        else out_dir / "xstar_tools_derived_pointers.npz"
    )

    result = load_atomic_database_state(
        args.atdb,
        llinabs=args.llinabs,
        memmap=not args.no_memmap,
        pointer_cache=cache_path,
        use_pointer_cache=not args.no_pointer_cache,
        rebuild_pointer_cache=args.rebuild_pointer_cache,
    )
    try:
        outputs = write_atomic_database_products(result.master, result.derived, out_dir)
        if args.print_summary:
            p = result.derived
            m = result.master
            print("XSTAR source-faithful atomic-database initialization")
            print("---------------------------------------------------")
            print("port_version=v0.4.1")
            print("status=readtbl_setptrs_completed")
            print(f"atdb={m.path}")
            print(f"creation_date={m.creation_date}")
            print(f"n_records={m.np2}")
            print(f"n_reals={m.np1r}")
            print(f"n_integers={m.np1i}")
            print(f"n_chars={m.np1k}")
            print(f"n_elements={p.n_elements}")
            print(f"n_ions={p.n_ions}")
            print(f"n_level_records={p.n_level_records}")
            print(f"n_lines={p.nlsvn}")
            print(f"n_continua={p.ncsvn}")
            print(f"pointer_cache_status={p.provenance.get('pointer_cache_status', 'not_used')}")
            print("readtbl_ready=True")
            print("setptrs_ready=True")
            print("atomic_database_runtime_subsystem_ready=True")
            print("dbwk2_interactive_editing_modes_ported=False")
            print("dominant_next_target=complete_ucalc_dispatch_and_called_rate_routines")
            for key, value in outputs.items():
                print(f"{key}: {value}")
    finally:
        result.atomic_state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
