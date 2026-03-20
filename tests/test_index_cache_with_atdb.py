import os
from pathlib import Path

import pytest


def test_atdb_index_cache_roundtrip_with_real_atdb(tmp_path):
    pytest.importorskip("astropy")
    fitsfile = os.environ.get("XSTAR_ATDB_FITS")
    if not fitsfile:
        pytest.skip("Set XSTAR_ATDB_FITS to run real ATDB index-cache test")

    from xstar_atomic.hierarchy import ATDB

    cache_path = tmp_path / "atdb_index_cache.pkl"

    with ATDB(fitsfile, load_reals=False) as db:
        records, elements, ions = db.build_index(use_cache=True, cache_path=cache_path, rebuild_cache=True)
        assert cache_path.exists()
        assert db.index_cache_status in {"rebuilt", "written"}
        assert len(records) > 1_000_000
        assert len(elements) == 30
        assert len(ions) >= 400

    with ATDB(fitsfile, load_reals=False) as db:
        records2, elements2, ions2 = db.build_index(use_cache=True, cache_path=cache_path)
        assert db.index_cache_status == "hit"
        assert len(records2) == len(records)
        assert len(elements2) == len(elements)
        assert len(ions2) == len(ions)
