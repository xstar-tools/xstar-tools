"""Real-ATDB collision-decoder validation tests.

These tests are skipped unless XSTAR_ATDB_FITS points to a local atdb.fits file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _atdb_path() -> Path:
    path = os.environ.get("XSTAR_ATDB_FITS")
    if not path:
        pytest.skip("Set XSTAR_ATDB_FITS=/path/to/atdb.fits to run real-ATDB validation tests")
    p = Path(path)
    if not p.exists():
        pytest.skip(f"XSTAR_ATDB_FITS does not exist: {p}")
    return p


def test_type63_same_n_lmixing_o8_validation():
    fitsfile = _atdb_path()
    from xstar_atomic.validation import type63_same_n_validation

    result = type63_same_n_validation(
        fitsfile,
        element="O",
        ion_stage=8,
        temperatures=[1.0e6],
        electron_density_for_lmixing=1.0,
    )
    assert result["validation_status"] == "pass"
    assert result["n_type63_same_n_adjacent_l_records"] > 0
    assert result["n_type63_same_n_evaluated_rows"] > 0
    assert result["q_excitation_max_cm3_s"] is not None
    assert result["q_excitation_max_cm3_s"] > 0.0


@pytest.mark.parametrize("data_type", [51, 98])
def test_type51_type98_inventory_and_evaluable_targets(data_type):
    fitsfile = _atdb_path()
    from xstar_atomic.validation import collision_inventory, find_collision_validation_targets

    inventory = collision_inventory(fitsfile, data_types=[data_type])
    if not inventory:
        pytest.skip(f"No data_type={data_type} collision records found in this ATDB")

    targets = find_collision_validation_targets(
        fitsfile,
        data_types=[data_type],
        temperatures=[1.0e6, 3.0e6, 1.0e7],
        max_targets=5,
    )
    if not targets:
        pytest.skip(f"data_type={data_type} exists but no positive evaluated q_ij target was found")

    first = targets[0]
    assert first["data_type"] == data_type
    assert first["n_positive_rate_rows"] > 0
    assert first["first_q_excitation_cm3_s"] is not None or first["first_q_deexcitation_cm3_s"] is not None
