"""Smoke tests that exercise the real XSTAR atdb.fits file.

These tests are skipped unless XSTAR_ATDB_FITS points to a readable atdb.fits.
Example:
    XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _atdb_path() -> Path | None:
    raw = os.environ.get("XSTAR_ATDB_FITS")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        return None
    return path


ATDB_PATH = _atdb_path()
needs_atdb = pytest.mark.skipif(
    ATDB_PATH is None,
    reason="set XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits to run ATDB smoke tests",
)




def test_parse_ion_aliases():
    pytest.importorskip("astropy")
    from xstar_atomic import parse_ion

    expected = (8, 8, "O")
    for ion in ["O VIII", "o viii", "o_viii", "O_VIII", "O-VIII", "OVIII", "o8"]:
        assert parse_ion(ion) == expected

    assert parse_ion("Fe XXVI") == (26, 26, "Fe")
    assert parse_ion("fexxvi") == (26, 26, "Fe")

@needs_atdb
def test_low_level_index_counts():
    from xstar_atomic import ATDB

    atdb = ATDB(str(ATDB_PATH))
    records, elements, ions = atdb.build_index()
    assert len(records) == 1_216_792
    assert len(elements) == 30
    assert len(ions) == 465


@needs_atdb
def test_o8_lya_lines_high_level_api():
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(str(ATDB_PATH))
    rows = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
    wavelengths = sorted(round(row["wavelength_A"], 4) for row in rows)
    assert len(rows) == 2
    assert wavelengths == [18.9671, 18.9725]
    assert {row["data_type"] for row in rows} == {50}




@needs_atdb
def test_o8_lya_line_ion_aliases_high_level_api():
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(str(ATDB_PATH))
    reference = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
    for ion in ["o viii", "o_viii", "O_VIII", "OVIII", "o8"]:
        rows = db.lines(ion, wavelength=(18.8, 19.1), slim=True)
        assert [round(r["wavelength_A"], 4) for r in rows] == [round(r["wavelength_A"], 4) for r in reference]

@needs_atdb
def test_o8_lya_collisions_high_level_api():
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(str(ATDB_PATH))
    result = db.collisions(
        "O VIII",
        lower_level=1,
        wavelength=(18.8, 19.1),
        temperatures=[1e6, 3e6, 1e7],
    )
    matches = result["matches"]
    rates = result["evaluated_rates"]
    assert len(matches) == 3  # 2p_1/2, 2p_3/2, and nearby 2s record in the window
    assert len(rates) == 9
    assert {row["eval_method"] for row in rates} == {"linear_logT_type56"}
    assert all(row["q_excitation_cm3_s"] is not None for row in rates)


@needs_atdb
def test_o8_lya_emissivity_high_level_api():
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(str(ATDB_PATH))
    result = db.emissivity("O VIII", wavelength=(18.8, 19.1), temperatures=[1e6, 3e6, 1e7])
    summary = result["summary"]
    rows = result["rows"]
    assert summary["n_radiative_lines_selected"] == 2
    assert summary["n_emissivity_rows"] == 6
    assert summary["n_level_pairs_with_both_line_and_collision"] == 2
    assert {row["collision_eval_method"] for row in rows} == {"linear_logT_type56"}


@needs_atdb
def test_o_recombination_inventory_high_level_api():
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(str(ATDB_PATH))
    result = db.recombination(element="O", temperatures=[1e6])
    summary = result["summary"]
    assert summary["n_recombination_like_records"] == 18
    assert summary["n_evaluated_rows"] == 14
    assert summary["counts_by_source_kind"]["electron_recombination"] == 14
    assert summary["counts_by_source_kind"]["charge_exchange_H0"] == 4
    assert summary["n_true_level_resolved_recombination_records_found"] == 0


@needs_atdb
def test_type63_same_n_lmixing_high_level_api():
    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(str(ATDB_PATH))
    result = db.collisions(
        "O VIII",
        data_type=63,
        temperatures=[1e6],
        electron_density_for_lmixing=1.0,
    )
    rates = result["evaluated_rates"]
    assert any(row.get("eval_method") == "type63_same_n_lmixing_amcrs_velimp" for row in rates)
    assert any(
        row.get("eval_method") == "type63_same_n_lmixing_amcrs_velimp"
        and row.get("q_excitation_cm3_s") is not None
        for row in rates
    )
