"""Command-line entry point for the complete source-faithful ``ucalc`` port."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .source_port import load_atomic_database_state
from .source_port.ucalc import SourceFaithfulUCalc
from .source_port.ucalc_inventory import write_ucalc_subsystem_products


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory and exercise the complete Python translation of XSTAR "
            "ucalc.f90 against a packed atdb.fits database."
        )
    )
    parser.add_argument("--atdb", required=True, help="Path to XSTAR atdb.fits")
    parser.add_argument(
        "--out-dir", default="xstar_ucalc_source_port_v042", help="Output directory"
    )
    parser.add_argument(
        "--pointer-cache",
        help="Derived-pointer NPZ cache; defaults to xstar_atomic_derived_pointers.npz beside --atdb",
    )
    parser.add_argument("--rebuild-pointer-cache", action="store_true")
    parser.add_argument("--no-pointer-cache", action="store_true")
    parser.add_argument("--no-memmap", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    atdb = Path(args.atdb)
    cache = None
    if not args.no_pointer_cache:
        cache = Path(args.pointer_cache) if args.pointer_cache else atdb.with_name(
            "xstar_atomic_derived_pointers.npz"
        )

    built = load_atomic_database_state(
        atdb,
        memmap=not args.no_memmap,
        pointer_cache=cache,
        use_pointer_cache=not args.no_pointer_cache,
        rebuild_pointer_cache=args.rebuild_pointer_cache,
    )
    try:
        dispatch = SourceFaithfulUCalc()
        outputs = write_ucalc_subsystem_products(
            built.master, built.derived, out_dir, dispatch
        )
        summary = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))
        if args.print_summary:
            print("XSTAR complete source-faithful ucalc subsystem")
            print("-----------------------------------------------")
            ordered = [
                "port_version", "status", "atdb", "atdb_creation_date",
                "n_atdb_records", "n_registered_data_types",
                "n_native_physical_data_types", "n_source_noop_data_types",
                "n_untranslated_data_types", "n_active_atdb_data_types",
                "active_atdb_data_types", "n_active_ucalc_records",
                "n_active_native_records", "n_active_source_noop_records",
                "n_index_only_samples", "n_index_only_sample_failures",
                "packed_record_decode_ready", "all_source_labels_registered",
                "complete_ucalc_source_branch_translation_ready",
                "complete_ucalc_control_flow_ready", "full_runtime_context_supplied",
                "full_atdb_numerical_evaluation_performed", "no_proxy_fallbacks",
                "dominant_next_target",
            ]
            for key in ordered:
                print(f"{key}={summary[key]}")
            for key, value in outputs.items():
                print(f"{key}: {value}")
    finally:
        built.atomic_state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
