from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(rel: str) -> str:
    return (ROOT / rel).read_text()


def test_revision_version_and_baseline():
    assert 'version = "0.6.82.33.4"' in text('pyproject.toml')
    assert 'PACKAGE_VERSION ?= 0.6.82.33.4' in text('src/xstar_tools/xstar/cpp/Makefile')
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_4.py')
    assert 'BASELINE_VERSION = "0.6.82.32"' in r
    assert 'CANDIDATE_VERSION = "0.6.82.33.4"' in r


def test_only_ordinary_single_pass_uses_immediate_transfer():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'effective_npass_v068227 == 1u && !data.reference_trajectory_mode' in s
    assert '!data.reference_diagnostics_enabled && !data.diagnostic_full_trajectory_continue' in s
    assert 'if (!immediate_final_transfer_v0682334)' in s
    assert 'finals.push_back(pretransport_boundary_v82_patch520145);' in s


def test_pending_newest_is_o1_and_previous_is_compacted_then_transferred():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'std::optional<FixedDsecSnapshot> pending_final_snapshot_v0682334;' in s
    assert 'compact_completed_snapshot_rrc_v068222(' in s
    compact = s.index('auto& completed = *pending_final_snapshot_v0682334;')
    transfer = s.index('append_zone_v0682334(\n                        completed', compact)
    reset = s.index('pending_final_snapshot_v0682334.reset();', transfer)
    assert compact < transfer < reset


def test_terminal_pretransport_snapshot_is_transferred_without_compaction():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    start = s.index('const std::size_t radial_event_count = accepted_boundary_count_v0682334 + 1u;')
    end = s.index('// Source saves a distinct terminal row', start)
    block = s[start:end]
    assert '*pending_final_snapshot_v0682334' in block
    assert 'compact_completed_snapshot_rrc_v068222' not in block


def test_count_only_final_size_uses_are_replaced_on_optimized_path():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'std::size_t accepted_boundary_count_v0682334 = 0u;' in s
    assert 'source_numrec_v068227 = accepted_boundary_count_v0682334 + 1u;' in s
    assert 'V0648110_RADIAL_ZONE_COUNT=" << accepted_boundary_count_v0682334' in s
    assert 'const std::size_t terminal_call_index_v0648110 = accepted_boundary_count_v0682334;' in s


def test_whole_radial_zones_remain_full_owner_in_0334():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    assert 'accepted.evaluation = copy_real_native_snapshot(snapshot, 0.0);' in s
    assert 'whole.radial_zones.push_back(std::move(zone));' in s
    assert 'update_radial_zones_memory_v0682332(whole.radial_zones);' in s


def test_o1_telemetry_and_host_gate():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    for marker in (
        'V0682334_FINAL_TRANSFER_MODE=',
        'V0682334_ACCEPTED_BOUNDARIES=',
        'V0682334_FINAL_SNAPSHOTS_CURRENT_COUNT=',
        'V0682334_FINAL_SNAPSHOTS_PEAK_COUNT=',
        'V0682334_FINAL_SNAPSHOTS_PEAK_BYTES=',
        'V0682334_FINAL_SNAPSHOTS_O1=',
    ):
        assert marker in s
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_4.py')
    assert 'snapshot_peak_count <= 1' in r
    assert 'legacy_final_history_peak == 0' in r
    assert 'o1_marker == "ACCEPT"' in r


def test_0333_publication_hotfix_is_unchanged():
    f = text('src/xstar_tools/xstar/cpp/xstar_science_fits.cpp')
    assert 'finalize_incremental_detal2_terminal_gate_v0682332' in f
    assert 'if (bulk_fits_enabled_v06823088()) flush_bulk_fits_v06823088(fptr);' in f
    assert 'fits_write_chksum(fptr, &status);' in f


def test_host_gate_is_exact_and_tiered():
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_4.py')
    assert 'compare_fits_payloads' in r
    assert 'hashlib.sha256(payload)' in r
    assert 'args.case or ["fe_reference_ne1e8"]' in r
    assert 'rss_ratio <= 0.30' in r
    assert '--milestone-all' in r


def test_deferred_034_correctness_plan_is_not_mixed_into_0334():
    c = text('CHANGELOG.md')
    assert '0.6.82.34' in c
    for item in ('N VI', 'Cr II', 'O IV', 'Mg II', 'cemab/cabab/opakab/tauc', 'Si VI / Ni VI', '1e-49'):
        assert item in c
