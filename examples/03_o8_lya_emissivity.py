#!/usr/bin/env python3
"""Build a direct-excitation O VIII Ly-alpha emissivity table."""

from __future__ import annotations

import argparse
import csv

from xstar_atomic import XSTARAtomic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fitsfile", help="Path to xstar/data/atdb.fits")
    parser.add_argument("--out", default="o8_lya_emissivity_example.csv")
    parser.add_argument("--temperatures", nargs="+", type=float, default=[1e6, 3e6, 1e7])
    args = parser.parse_args()

    db = XSTARAtomic(args.fitsfile)
    result = db.emissivity("O VIII", wavelength=(18.8, 19.1), temperatures=args.temperatures)

    print(result["summary"])
    rows = result["rows"]
    if rows:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
