#!/usr/bin/env python3
"""Inventory oxygen recombination-like records in atdb.fits."""

from __future__ import annotations

import argparse
from pprint import pprint

from xstar_atomic import XSTARAtomic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fitsfile", help="Path to xstar/data/atdb.fits")
    parser.add_argument("--temperature", type=float, default=1e6)
    args = parser.parse_args()

    db = XSTARAtomic(args.fitsfile)
    result = db.recombination(element="O", temperatures=[args.temperature])
    pprint(result["summary"])


if __name__ == "__main__":
    main()
