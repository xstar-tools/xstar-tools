#!/usr/bin/env python3
"""Export line-based X-ray band emissivity products for selected ions.

This example writes CSV, HDF5, and JSON manifest products using the general
``xstar_atomic.export`` module.  The bands are line-emissivity sums over the
selected radiative lines and are therefore local coefficients per n_e n_ion;
combine them with ion fractions and abundances for plasma post-processing.

Usage
-----
PYTHONPATH=src python examples/09_export_band_emissivity.py /path/to/atdb.fits
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

from xstar_atomic.export import export_superwind_bundle, parse_band_specs


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: 09_export_band_emissivity.py /path/to/atdb.fits")

    fitsfile = sys.argv[1]
    out_dir = Path("atomic_export_example")
    bands = parse_band_specs([
        "soft:0.5:2.0",
        "osoft:0.3:0.6",
        "med:0.6:1.0",
        "hard:2.0:10.0",
    ])

    bundle = export_superwind_bundle(
        fitsfile,
        ions="O VIII,Ne IX",
        out_dir=out_dir,
        temperatures=[1e6, 3e6, 1e7],
        wavelength=(1.0, 40.0),
        formats=["csv", "hdf5"],
        bands=bands,
    )

    print("Wrote export bundle to", out_dir)
    for manifest in bundle["manifests"]:
        print("\n", manifest["ion"])
        pprint(manifest["files"])
        print("band rows:", manifest["counts"].get("band_emissivity_rows"))


if __name__ == "__main__":
    main()
