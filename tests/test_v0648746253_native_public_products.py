from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
PUBLIC = {
    "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
    "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits",
    "xout_spect1.fits", "xout_step.log",
}


def test_no_embedded_public_products():
    found = [p for p in ROOT.rglob("*") if p.is_file() and p.name in PUBLIC]
    assert found == []


def test_native_writer_has_no_raw_payload_or_header_template_path():
    text = (CPP / "xstar_science_fits.cpp").read_text()
    assert "fits_write_tblbytes" not in text
    assert "apply_python_header_templates" not in text
    assert "NATIVE_CPP_LIVE_STATE" in text
    assert "fits_write_date" in text
    assert "RUNID" in text


def test_native_runner_has_three_arguments_and_no_oracle_input():
    text = (ROOT / "run_v048746253_native_public_product_construction.sh").read_text()
    assert 'if [ "$#" -ne 3 ]' in text
    assert "usage: $0 PARAMETERS_JSON ATDB_FITS OUTPUT_DIR" in text
    assert "--skip-fits" not in text
    assert "--oracle-dir" not in text.lower()
    assert "XSTAR_PUBLIC_PRODUCT_ORACLE" in text
    assert "XSTAR_PRODUCT_ORACLE_DIR" in text


def test_all_ten_products_are_required_by_output_checker():
    text = (ROOT / "check_v048746253_native_product_output.py").read_text()
    for name in PUBLIC:
        assert name in text
    assert "XSTAR_CPP_PUBLIC_PRODUCT_COUNT_10" in text
    assert "FITS_ATDATA_MATCHES_SUPPLIED_ATDB" in text
    assert "ALL_PRODUCTS_SHARE_NATIVE_RUN_ID" in text


def test_direct_emissivity_link_is_retained():
    text = (CPP / "Makefile").read_text()
    assert "$(EMISSIVITY_TARGET)" in text
    assert "-lxstar_emissivity" in text
    executable_rule = text.split("$(EXECUTABLE_TARGET):", 1)[1].splitlines()[0]
    assert "$(CPP_BACKEND_TARGET)" in executable_rule
