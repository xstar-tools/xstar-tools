from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text()


def test_version_and_frozen_fp_policy():
    assert 'version = "0.6.82.33"' in text('pyproject.toml')
    makefile = text('src/xstar_tools/xstar/cpp/Makefile')
    assert 'PACKAGE_VERSION ?= 0.6.82.33' in makefile
    assert 'rejects -ffast-math' in makefile


def test_incremental_detail_is_single_pass_and_diagnostic_safe():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'incremental_detail_stream_v068233' in s
    assert 'effective_npass_v068227 == 1u' in s
    assert '!data.reference_diagnostics_enabled && !data.diagnostic_full_trajectory_continue' in s
    assert 'source_savd_detail_enabled_v0682307 && !incremental_detail_stream_v068233' in s


def test_incremental_detail_uses_one_radial_hdu_append():
    s = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    assert 'incremental detail append requires exactly one radial zone' in s
    assert 'fits_movabs_hdu(src, 3' in s
    assert 'fits_copy_hdu(src, dst, 0, &status);' in s
    assert 'incremental_detail_products_complete_v068233' in s


def test_live_step_keeps_final_exact_serializer():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert s.count('append_live_step_row_v068233(') >= 3
    assert 'xstar_step_log::write_native_step_log(output, product)' in s


def test_memory_markers_present():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    for marker in (
        'V068233_PUBLICATION_RETAINED_CURRENT_BYTES=',
        'V068233_PUBLICATION_RETAINED_PEAK_BYTES=',
        'V068233_ZONE_PUBLICATION_SCRATCH_BYTES=',
        'V068233_STEP_ROWS_STREAMED=',
        'V068233_DETAIL_ROWS_STREAMED=',
        'V068233_RADIAL_RSS_SAMPLES_BYTES=',
    ):
        assert marker in s


def test_host_runner_is_fe_first_and_broad_explicit():
    s = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33.py')
    assert 'args.case or ["fe_reference_ne1e8"]' in s
    assert '--milestone-all' in s
    assert 'BASELINE_VERSION = "0.6.82.32"' in s
    assert 'CANDIDATE_VERSION = "0.6.82.33"' in s
    assert 'rss_ratio <= 0.80' in s
