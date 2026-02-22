#!/usr/bin/env python3
"""Evaluate O VIII Ly-alpha collisional-excitation rates."""

from __future__ import annotations

import argparse
from pprint import pprint

from xstar_atomic import XSTARAtomic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fitsfile", help="Path to xstar/data/atdb.fits")
    parser.add_argument("--temperatures", nargs="+", type=float, default=[1e6, 3e6, 1e7])
    args = parser.parse_args()

    db = XSTARAtomic(args.fitsfile)
    result = db.collisions(
        "O VIII",
        lower_level=1,
        wavelength=(18.8, 19.1),
        temperatures=args.temperatures,
    )

    print(f"Collision records in window: {len(result['matches'])}")
    print(f"Evaluated rate rows: {len(result['evaluated_rates'])}")
    for row in result["evaluated_rates"][:6]:
        pprint(row)


if __name__ == "__main__":
    main()
