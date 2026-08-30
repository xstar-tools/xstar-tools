from __future__ import annotations

import argparse
import sys

from xstar_tools.tables import XSpecTableProducts, build_xspec_tables


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xstar-tools-xstar2table",
        description="Build canonical-compatible XSPEC table spectra from ordinary XSTAR xout_spect1.fits files.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--initable", help="native/canonical xstinitable.fits metadata contract")
    source.add_argument("--metadata", help="legacy 0.6.81 characterization metadata file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--native-bin", default=None, help="optional explicit xstar-xspec-table executable")
    parser.add_argument("spectra", nargs="+", help="xout_spect1.fits files in loopcontrol order")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = args.initable or args.metadata
        proc = build_xspec_tables(
            config,
            args.spectra,
            args.output_dir,
            initable=bool(args.initable),
            native_executable=args.native_bin,
        )
    except FileNotFoundError as exc:
        print(f"xstar-tools-xstar2table: {exc}", file=sys.stderr)
        return 69
    except Exception as exc:
        print(f"xstar-tools-xstar2table: {exc}", file=sys.stderr)
        return 1
    if proc.stdout:
        print(proc.stdout, end="")
    products = XSpecTableProducts.from_directory(args.output_dir)
    for path in (products.ain, products.aout, products.mtable, products.etable):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
