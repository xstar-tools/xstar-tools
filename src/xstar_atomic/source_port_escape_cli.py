"""CLI for building source-faithful XSTAR line/RRC escape arrays."""
from __future__ import annotations

import argparse
from pathlib import Path

from .source_port import load_atomic_database_state
from .source_port.escape_state import (
    load_escape_state_from_xstar_run,
    write_escape_state_npz,
    write_escape_state_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Map xo01_detal2.fits line tau0 and xo01_detal3.fits RRC tauc "
            "onto the global nplini/npconi2 arrays used by calc_hmc_ion."
        )
    )
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--pointer-cache")
    parser.add_argument("--xstar-run-dir", required=True)
    parser.add_argument("--zone", default="last", help="first, last, zone ordinal, or FITS HDU index")
    parser.add_argument("--out-npz", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--allow-missing-as-zero", action="store_true")
    parser.add_argument(
        "--detail-policy", choices=("source_sparse_reconstruct", "strict_selected_zone"),
        default="source_sparse_reconstruct",
    )
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    built = load_atomic_database_state(args.atdb, pointer_cache=args.pointer_cache)
    try:
        result = load_escape_state_from_xstar_run(
            args.xstar_run_dir,
            built.derived,
            zone=args.zone,
            allow_missing_as_zero=args.allow_missing_as_zero,
            detail_policy=args.detail_policy,
        )
        npz = write_escape_state_npz(result, args.out_npz)
        reports = write_escape_state_summary(result, args.out_dir)
        if args.print_summary:
            print("XSTAR source-faithful line/RRC escape-state builder")
            print("----------------------------------------------------")
            print("port_version=v0.4.15")
            print("status=escape_state_built")
            print(f"xstar_run_dir={result.run_dir}")
            print(f"zone_selector={result.zone_selector}")
            print(f"detail_policy={result.detail_policy}")
            print(f"exact_live_arrays={result.exact_live_arrays}")
            print(f"source_writer_threshold_reconstruction={result.source_writer_threshold_reconstruction}")
            print(f"line_hdu_index={result.line_hdu_index}")
            print(f"rrc_hdu_index={result.rrc_hdu_index}")
            print(f"n_line_indices_loaded={result.n_line_indices_loaded}")
            print(f"n_line_indices_missing={result.n_line_indices_missing}")
            print(f"n_rrc_indices_loaded={result.n_rrc_indices_loaded}")
            print(f"n_rrc_indices_missing={result.n_rrc_indices_missing}")
            print(f"escape_state_global_arrays_complete={result.complete}")
            print(f"npz: {npz}")
            for name, path in reports.items():
                print(f"{name}: {path}")
        return 0
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
