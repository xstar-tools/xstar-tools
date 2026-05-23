"""Analyze and optionally compare the bounded original-XSTAR zone-1 probe with constant-memory streaming."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .source_port.zone1_dsec_probe_analysis import analyze_xstar_zone1_probe, compare_zone1_probe_with_python


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xstar-probe-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--python-diagnostic-dir")
    parser.add_argument("--compare-out-dir")
    parser.add_argument("--rtol", type=float, default=5.0e-5)
    parser.add_argument("--atol", type=float, default=1.0e-30)
    parser.add_argument(
        "--skip-input-fingerprints",
        action="store_true",
        help=(
            "skip the observation-only full-capacity input fingerprint pass; "
            "the physical record/topology/population/cooling gates are still evaluated"
        ),
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="print streaming analyzer stage/file progress to stderr",
    )
    args = parser.parse_args(argv)

    progress = None
    if args.progress:
        def progress(message: str) -> None:
            print(f"[zone1-analyzer] {message}", file=sys.stderr, flush=True)

    products = analyze_xstar_zone1_probe(
        args.xstar_probe_dir,
        out_dir=args.out_dir,
        include_input_fingerprints=not args.skip_input_fingerprints,
        progress=progress,
    )
    for key, value in sorted(products.items()):
        print(f"{key}={value}")
    if args.python_diagnostic_dir:
        compare_dir = args.compare_out_dir or str(Path(args.out_dir) / "comparison")
        compared = compare_zone1_probe_with_python(
            xstar_analysis_dir=args.out_dir,
            python_diagnostic_dir=args.python_diagnostic_dir,
            out_dir=compare_dir,
            rtol=args.rtol,
            atol=args.atol,
        )
        for key, value in sorted(compared.items()):
            print(f"comparison_{key}={value}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
