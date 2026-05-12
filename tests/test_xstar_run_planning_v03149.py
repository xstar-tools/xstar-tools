from pathlib import Path

import xstar_atomic as xa
from xstar_atomic.xstar_run import parse_xstar_command, write_xstar_recreation_plan, standard_xstar_output_products


def test_parse_xstar_command_handles_quoted_values_and_numbers():
    params = parse_xstar_command("xstar spectrum='pow' nsteps=10 rlogxi=1.5 cfrac=1.0 modelname='o7 test'")
    assert params.get("spectrum") == "pow"
    assert params.get("nsteps") == 10
    assert params.get("rlogxi") == 1.5
    assert params.get("cfrac") == 1.0
    assert params.get("modelname") == "o7 test"


def test_standard_output_products_include_xstar_files():
    names = {row["filename"] for row in standard_xstar_output_products()}
    for name in [
        "xo01_detail.fits",
        "xo01_detal2.fits",
        "xo01_detal3.fits",
        "xo01_detal4.fits",
        "xout_abund1.fits",
        "xout_lines1.fits",
        "xout_rrc1.fits",
        "xout_cont1.fits",
        "xout_spect1.fits",
    ]:
        assert name in names


def test_write_xstar_recreation_plan(tmp_path: Path):
    params = parse_xstar_command("xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100")
    paths = write_xstar_recreation_plan(params, tmp_path)
    for path in paths.values():
        assert Path(path).exists()
    text = Path(paths["markdown"]).read_text()
    assert "bremsa(:)" in text
    assert "xout_lines1.fits" in text


def test_top_level_imports_for_xstar_run_planning():
    assert xa.parse_xstar_command("xstar nsteps=1").get("nsteps") == 1
    assert any(row["filename"] == "xout_abund1.fits" for row in xa.standard_xstar_output_products())


def test_parse_xstar_numeric_one_stays_numeric():
    params = parse_xstar_command("xstar density=1 lwrite=1 cfrac=1.0")
    assert params.get("density") == 1
    assert not isinstance(params.get("density"), bool)
    assert params.get("lwrite") == 1
    assert not isinstance(params.get("lwrite"), bool)

