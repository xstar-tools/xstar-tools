from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(rel: str) -> str:
    return (ROOT / rel).read_text()

def test_revision_version_and_accepted_baseline():
    assert 'version = "0.6.82.33.2"' in text('pyproject.toml')
    assert 'PACKAGE_VERSION ?= 0.6.82.33.2' in text('src/xstar_tools/xstar/cpp/Makefile')
    runner = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_2.py')
    assert 'BASELINE_VERSION = "0.6.82.32"' in runner
    assert 'CANDIDATE_VERSION = "0.6.82.33.2"' in runner

def test_incremental_streaming_architecture_is_preserved():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    f = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    assert 'stream_saved_shell_detail_v068233(' in s
    assert 'effective_npass_v068227 == 1u' in s
    assert '!data.reference_diagnostics_enabled && !data.diagnostic_full_trajectory_continue' in s
    assert 'source_savd_detail_enabled_v0682307 && !incremental_detail_stream_v068233' in s
    assert 'fits_copy_hdu(src, dst, 0, &status);' in f

def test_detal2_fix_is_terminal_gate_provenance_not_c5_hardcode():
    f = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    start = f.index('diagnostic_emis_in_v0682332')
    end = f.index('continue;\n        }', start)
    block = f[start:end]
    assert 'r.emis_in == 0.0 && found_diag->second.emis_in != 0.0' in block
    assert 'r.emis_out == 0.0 && found_diag->second.emis_out != 0.0' in block
    assert 'patch.element_z = found_diag->second.z' in block
    assert 'patch.ion_stage = found_diag->second.stage' in block
    assert 'c_v' not in block.lower()
    assert '1625' not in block and '1805' not in block

def test_terminal_gate_finalizer_restores_frozen_deferred_behavior():
    f = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    h = text('src/xstar_tools/xstar/cpp/xstar_science_fits.hpp')
    assert 'finalize_incremental_detal2_terminal_gate_v0682332' in h
    assert 'finalize_incremental_detal2_terminal_gate_v0682332' in f
    assert 'active_product_element_stage(' in f
    assert 'write_real4(fptr, 6, row, 0.0)' in f
    assert 'write_real4(fptr, 7, row, 0.0)' in f
    assert 'fits_write_chksum(fptr, &status)' in f

def test_patch_ledger_is_compact_and_transferred_to_final_state():
    h = text('src/xstar_tools/xstar/cpp/xstar_run_state.hpp')
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'struct IncrementalDetal2TerminalPatchStateV0682332' in h
    assert 'std::vector<IncrementalDetal2TerminalPatchStateV0682332>' in h
    assert 'result.detal2_terminal_patches_v0682332' in s
    assert 'whole.incremental_detal2_terminal_patches_v0682332' in s

def test_remaining_boundary_memory_is_accounted_logical_and_capacity():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    for marker in (
        'V0682332_FINAL_SNAPSHOTS_CURRENT_BYTES=',
        'V0682332_FINAL_SNAPSHOTS_PEAK_BYTES=',
        'V0682332_FINAL_SNAPSHOTS_CURRENT_CAPACITY_BYTES=',
        'V0682332_FINAL_SNAPSHOTS_PEAK_CAPACITY_BYTES=',
        'V0682332_RADIAL_ZONES_CURRENT_BYTES=',
        'V0682332_RADIAL_ZONES_PEAK_BYTES=',
        'V0682332_RADIAL_ZONES_CURRENT_CAPACITY_BYTES=',
        'V0682332_RADIAL_ZONES_PEAK_CAPACITY_BYTES=',
    ):
        assert marker in s
    assert 'final_snapshots_memory_v0682332' in s
    assert 'radial_zones_memory_v0682332' in s

def test_host_gate_keeps_exact_payload_and_tiered_cadence():
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_2.py')
    assert 'compare_fits_payloads' in r
    assert 'hashlib.sha256(payload)' in r
    assert 'args.case or ["fe_reference_ne1e8"]' in r
    assert 'rss_ratio <= 0.80' in r
    assert '--milestone-all' in r
