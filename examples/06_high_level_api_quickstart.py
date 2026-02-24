#!/usr/bin/env python3
"""High-level API quickstart for xstar-atomic.

Usage
-----
PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/atdb.fits
"""

from __future__ import annotations

import argparse
import json

from xstar_atomic import XSTARAtomic


def main() -> None:
    parser = argparse.ArgumentParser(description="High-level xstar_atomic API quickstart.")
    parser.add_argument("fitsfile", help="Path to XSTAR atdb.fits")
    args = parser.parse_args()

    db = XSTARAtomic(args.fitsfile)

    lines = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
    collisions = db.collisions(
        "O VIII",
        lower_level=1,
        wavelength=(18.8, 19.1),
        temperatures=[1e6, 3e6, 1e7],
    )
    emissivity = db.emissivity(
        "O VIII",
        wavelength=(18.8, 19.1),
        temperatures=[1e6, 3e6, 1e7],
    )
    recombination = db.recombination(element="O", temperatures=[1e6])

    summary = {
        "n_o8_lya_lines": len(lines),
        "n_collision_records": len(collisions["summary"]),
        "n_collision_evaluations": len(collisions["evaluated"]),
        "n_emissivity_rows": len(emissivity["emissivity"]),
        "n_oxygen_recombination_records": len(recombination["records"]),
        "first_line": lines[0] if lines else None,
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
