#!/usr/bin/env python3
"""Use the low-level ATDB reader to build the record/element/ion index."""

from __future__ import annotations

import argparse

from xstar_atomic import ATDB


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fitsfile", help="Path to xstar/data/atdb.fits")
    args = parser.parse_args()

    atdb = ATDB(args.fitsfile)
    records, elements, ions = atdb.build_index()
    print(f"records={len(records)} elements={len(elements)} ions={len(ions)}")


if __name__ == "__main__":
    main()
