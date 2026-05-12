from pathlib import Path

import pytest

import xstar_atomic as xa
from xstar_atomic.xstar_outputs import read_fits_table_hdus


def test_reconstruct_bremsint_simple():
    out = xa.reconstruct_bremsint([0.0, 1.0, 2.0], [2.0, 2.0, 4.0])
    assert out == [0.0, 2.0, 5.0]


def test_top_level_detail_state_imports():
    assert callable(xa.read_xstar_detail_run_state)
    assert callable(xa.write_xstar_detail_state)
    assert callable(xa.reconstruct_bremsa_from_detal4_rows)


def test_read_o7_detail_state_if_available(tmp_path: Path):
    run_dir = Path("/mnt/data/o7_ne1_inspect/o7_ne1")
    if not run_dir.exists():
        pytest.skip("local o7_ne1 detail-output fixture not available")
    state = xa.read_xstar_detail_run_state(run_dir)
    assert state.status == "populated_from_xstar_detail_outputs_not_full_recreation"
    assert len(state.zones) >= 1
    last = state.zones[-1]
    assert last.continuum.epi
    assert last.continuum.bremsa
    assert last.continuum.bremsint
    assert last.lines.tau0_in
    assert last.lines.tau0_out
    assert last.cfrac is not None
    assert last.vturbi is not None
    assert last.temperature is not None
    assert last.electron_density is not None
    assert last.ion_fractions
    assert last.level_populations
    paths = xa.write_xstar_detail_state(state, tmp_path, write_full_json=False)
    assert Path(paths["zones_csv"]).exists()
    assert Path(paths["fields_csv"]).exists()


def test_builtin_fits_reader_reads_xstar_bintable_if_available():
    run_dir = Path("/mnt/data/o7_ne1_inspect/o7_ne1")
    path = run_dir / "xo01_detal4.fits"
    if not path.exists():
        pytest.skip("local o7_ne1 detail-output fixture not available")
    hdus = read_fits_table_hdus(path, "XSTAR_RADIAL")
    assert hdus
    assert hdus[0]["rows"]
    row = hdus[0]["rows"][0]
    assert "energy" in row
    assert "zrems(1)" in row
