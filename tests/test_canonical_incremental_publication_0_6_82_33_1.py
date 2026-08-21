from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(rel: str) -> str:
    return (ROOT / rel).read_text()

def test_revision_version_and_frozen_baseline():
    assert 'version = "0.6.82.33.1"' in text('pyproject.toml')
    assert 'PACKAGE_VERSION ?= 0.6.82.33.1' in text('src/xstar_tools/xstar/cpp/Makefile')
    runner = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_1.py')
    assert 'BASELINE_VERSION = "0.6.82.32"' in runner
    assert 'CANDIDATE_VERSION = "0.6.82.33.1"' in runner

def test_incremental_writer_is_production_silent():
    s = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    assert 'ScopedTrueProductionV0682331' in s
    assert '::setenv("XSTAR_TRUE_PRODUCTION", "1", 1)' in s
    assert 'v048746255172542_xo01_detal2_radial_value_null_audit.json' in s
    assert 'v048746255172556_xo01_detal3_rrc_native_surface_audit.json' in s

def test_live_step_has_canonical_prefix_initializer():
    h = text('src/xstar_tools/xstar/cpp/xstar_step_log.hpp')
    c = text('src/xstar_tools/xstar/cpp/xstar_step_log.cpp')
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'initialize_live_step_log_v0682331' in h
    assert ' Loading Atomic Database...' in c
    assert 'append_native_input_parameters(out, state);' in c
    assert ' U(1-1.8),U(1.8-4):' in c
    assert 'initialize_live_step_log_v0682331' in s

def test_failed_host_candidate_preserves_live_products_only_when_opted_in():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_1.py')
    assert 'XSTAR_V0682331_PRESERVE_FAILURE_PRODUCTS' in s
    assert 'if (!preserve_failure_products_v0682331) remove_native_products(output);' in s
    assert 'XSTAR_V0682331_PRESERVE_FAILURE_PRODUCTS' in r
    assert 'label == "candidate"' in r
    assert 'compare_step_structure' in r
    assert 'STEP_SECTIONS=' in r

def test_streaming_science_path_remains_unchanged_from_33():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    f = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    assert 'effective_npass_v068227 == 1u' in s
    assert '!data.reference_diagnostics_enabled && !data.diagnostic_full_trajectory_continue' in s
    assert 'fits_copy_hdu(src, dst, 0, &status);' in f
    assert 'incremental_detail_products_complete_v068233' in f
