#!/usr/bin/env python3
"""Find and validate collision-decoder targets in a local XSTAR atdb.fits file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from xstar_atomic.validation import (
    collision_inventory,
    find_collision_validation_targets,
    summarize_inventory,
    type63_same_n_validation,
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python examples/07_collision_decoder_validation.py /path/to/atdb.fits")
    fitsfile = Path(sys.argv[1])

    inventory = collision_inventory(fitsfile, data_types=(51, 98))
    targets = find_collision_validation_targets(fitsfile, data_types=(51, 98), max_targets=10)
    same_n = type63_same_n_validation(fitsfile, element="O", ion_stage=8, temperatures=[1e6], electron_density_for_lmixing=1.0)

    print(json.dumps({
        "type51_98_inventory": summarize_inventory(inventory),
        "type51_98_validation_targets": targets,
        "o8_type63_same_n_validation": same_n,
    }, indent=2))


if __name__ == "__main__":
    main()
