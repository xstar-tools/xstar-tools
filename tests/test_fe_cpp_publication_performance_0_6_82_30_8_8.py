from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FITS = ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp"
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
STATE = ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp"
STANDALONE = ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp"


def test_version():
    assert 'version = "0.6.82.30.8.8"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30.8.8' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_bulk_fits_column_writer_is_common_publication_layer():
    text = FITS.read_text()
    assert "BulkFitsBufferV06823088" in text
    assert "bulk_fits_enabled_v06823088" in text
    assert "flush_bulk_fits_v06823088" in text
    assert "fits_write_col(fptr, TFLOAT" in text
    assert "fits_write_col(fptr, TSTRING" in text
    assert "XSTAR_DISABLE_BULK_FITS_06823088" in text
    for helper in ("write_float", "write_int", "write_longlong", "write_short", "write_string"):
        block = text[text.index(f"void {helper}("):]
        block = block[:block.index("\n}") + 2]
        assert "bulk_fits_enabled_v06823088()" in block


def test_bulk_flushes_before_hdu_transition_and_checksum_close():
    text = FITS.read_text()
    close = text[text.index("void close_fits("):text.index("std::vector<std::string> normalize_tform_for_table", text.index("void close_fits("))]
    create = text[text.index("void create_table("):text.index("void write_float(", text.index("void create_table("))]
    assert "flush_bulk_fits_v06823088(fptr)" in close
    assert "flush_bulk_fits_v06823088(fptr)" in create


def test_sparse_line_and_rrc_identity_lookup_is_preindexed():
    text = FITS.read_text()
    assert "build_line_identity_lookup_v06823088" in text
    assert "line_identity_from_lookup_v06823088" in text
    assert "build_rrc_identity_lookup_v06823088" in text
    assert "rrc_identity_from_lookup_v06823088" in text
    line_detail = text[text.index("void write_line_detail("):text.index("void write_rrc_detail(")]
    public_lines = text[text.index("void write_public_lines("):text.index("void write_public_rrc(")]
    assert "line_identity_lookup_v06823088" in line_detail
    assert "line_identity_lookup_v06823088" in public_lines


def test_step_footer_distinguishes_controller_publication_and_end_to_end():
    text = STEP.read_text()
    assert '"  native_controller "' in text
    assert '"  native_publication_before_step "' in text
    assert '"  native_step_log_formatter "' in text
    assert '"  native_publication_total "' in text
    assert '"  native_end_to_end "' in text
    assert "native_controller_and_fits" not in text
    state = STATE.read_text()
    assert "measured_controller_seconds" in state
    assert "measured_publication_before_step_seconds" in state
    assert "measured_end_to_end_before_step_seconds" in state
    standalone = STANDALONE.read_text()
    assert "product.measured_controller_seconds" in standalone
    assert "product.measured_publication_before_step_seconds" in standalone
    assert "product.measured_end_to_end_before_step_seconds" in standalone


def test_accepted_3087_controller_optimization_and_type82_remain_present():
    local = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    runtime = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text()
    assert "BoundFreeEvaluatedPayloadV06823087" in local
    assert "retain_element_diagnostics_v06823087" in local
    assert "case 82:" in runtime
    assert "energy_order_pair(ii[0],ii[1]);" in runtime
