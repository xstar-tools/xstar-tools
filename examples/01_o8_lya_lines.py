#!/usr/bin/env python3
"""Extract the O VIII Ly-alpha doublet from XSTAR atdb.fits."""

from __future__ import annotations

import argparse
from pprint import pprint

from xstar_atomic import XSTARAtomic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fitsfile", help="Path to xstar/data/atdb.fits")
    args = parser.parse_args()

    db = XSTARAtomic(args.fitsfile)
    lines = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)

    print(f"Found {len(lines)} O VIII Ly-alpha line records")
    for row in lines:
        pprint(row)


if __name__ == "__main__":
    main()
