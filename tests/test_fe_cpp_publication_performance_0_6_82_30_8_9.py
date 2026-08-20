from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FITS = ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp"
HPP = ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.hpp"
STANDALONE = ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp"
LOCAL = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
RUNTIME = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"


def test_version():
    assert 'version = "0.6.82.30.8.9"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30.8.9' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_retained_public_line_arrays_are_checked_before_reconstruction():
    text = FITS.read_text()
    block = text[text.index("void write_public_lines("):text.index("void write_public_rrc(")]
    idx_arrays = block.index('product_write_public_line_index')
    idx_terminal = block.index('auto terminal_list =')
    idx_diag = block.index('std::vector<std::map<long long,LineRow>> diagnostics_by_zone')
    assert idx_arrays < idx_terminal < idx_diag
    assert 'kRetainedPublicLineRowsV06823089 = 600u' in block
    assert 'retained_public_line_arrays_complete_v06823089' in block
    assert 'retained_labels_v06823089.size() == kRetainedPublicLineRowsV06823089' in block


def test_retained_fast_path_directly_serializes_arrays_and_returns():
    text = FITS.read_text()
    block = text[text.index("void write_public_lines("):text.index("// Fail-soft fallback:", text.index("void write_public_lines("))]
    assert 'g_public_lines_fast_path_v06823089 = true' in block
    assert 'line_identity_from_lookup_v06823088' in block
    for name in (
        'pw_line_emit_in[i]', 'pw_line_emit_out[i]',
        'pw_line_depth_in[i]', 'pw_line_depth_out[i]',
    ):
        assert name in block
    assert 'terminal_list' in block  # comment documents avoided construction
    assert 'auto terminal_list =' not in block
    assert 'terminal_depth_list;' not in block
    assert 'diagnostics_by_zone;' not in block
    assert 'close_fits(fptr);\n            return;' in block


def test_fail_soft_fallback_retains_reconstruction_path():
    text = FITS.read_text()
    start = text.index("// Fail-soft fallback:", text.index("void write_public_lines("))
    end = text.index("void write_public_rrc(", start)
    block = text[start:end]
    assert 'auto terminal_list = public_line_rows_from_identities' in block
    assert 'std::vector<LineRow> terminal_depth_list' in block
    assert 'std::vector<std::map<long long,LineRow>> diagnostics_by_zone' in block
    assert 'diagnostic_line_rows_by_index' in block
    assert 'terminal_for_label' in block
    assert 'terminal_depth_for_label' in block


def test_requested_product_timers_are_exposed():
    hpp = HPP.read_text()
    standalone = STANDALONE.read_text()
    expected_fields = (
        'detail_population_seconds', 'detail_line_seconds', 'detail_rrc_seconds',
        'detail_spectrum_seconds', 'public_lines_seconds', 'public_rrc_seconds',
        'public_cont_seconds', 'public_spect_seconds',
    )
    for field in expected_fields:
        assert field in hpp
        assert field in standalone
    for label in (
        'DETAIL_POPULATION_SECONDS', 'DETAIL_LINE_SECONDS', 'DETAIL_RRC_SECONDS',
        'DETAIL_SPECTRUM_SECONDS', 'PUBLIC_LINES_SECONDS', 'PUBLIC_RRC_SECONDS',
        'PUBLIC_CONT_SECONDS', 'PUBLIC_SPECT_SECONDS',
    ):
        assert f'"{label}="' in standalone
    assert 'V06823089_PUBLIC_LINES_RETAINED_FAST_PATH' in standalone


def test_3088_bulk_fits_layer_is_unchanged_and_still_enabled():
    text = FITS.read_text()
    assert 'BulkFitsBufferV06823088' in text
    assert 'bulk_fits_enabled_v06823088' in text
    assert 'flush_bulk_fits_v06823088' in text
    assert 'XSTAR_DISABLE_BULK_FITS_06823088' in text
    assert 'V06823088_BULK_FITS_COLUMN_WRITES' in text


def test_accepted_3087_controller_and_type82_remain_present():
    local = LOCAL.read_text()
    runtime = RUNTIME.read_text()
    assert 'BoundFreeEvaluatedPayloadV06823087' in local
    assert 'retain_element_diagnostics_v06823087' in local
    assert 'case 82:' in runtime
    assert 'energy_order_pair(ii[0],ii[1]);' in runtime
