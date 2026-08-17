from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_bumped_after_rejected_334_host_candidate():
    assert 'version = "0.6.82.29.3.3.5"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.5' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_option4_flinel_publication_uses_source_nbinc_owner_not_lower_bound_bin():
    local=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    assert 'const int nb1_v068229334 = line_consumer_v82_patch5208.nb1_one_based;' in local
    assert 'pprint4_flinel_v068229334[static_cast<std::size_t>(nb1_v068229334 - 1)] +=' in local
    # The operational broad contribution still retains its historical bin owner.
    assert 'sc.bin_one_based = static_cast<int32_t>(std::min<std::size_t>(' in local


def test_option4_flinel_publication_uses_source_local_two_sided_width():
    local=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    anchor=local.index('const int nb1_v068229334 = line_consumer_v82_patch5208.nb1_one_based;')
    block=local[anchor:anchor+2500]
    assert 'const int lower_one_based_v068229334 = std::max(1, nb1_v068229334 - 1);' in block
    assert 'input.radiation_energy_ev[static_cast<std::size_t>(nb1_v068229334)] -' in block
    assert 'input.radiation_energy_ev[static_cast<std::size_t>(lower_one_based_v068229334 - 1)]' in block
    assert 'width_v068229334 / ergsev_v068229334' in block


def test_option4_flinel_private_delta_does_not_change_operational_selected_replay():
    local=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    assert 'std::vector<double> pprint4_flinel_v068229334(continuum_capacity, 0.0);' in local
    assert 'flinel.swap(selected_flinel);' in local
    assert 'pprint4_flinel_v068229331[k_v068229331] += selected_flinel[k_v068229331]' not in local


def test_standalone_accumulates_private_option4_delta_not_operational_flinel():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'std::vector<double> pprint4_flinel_accumulator_v068229334;' in stand
    assert 'const auto& pprint4_delta_v068229334 = snapshot.pprint4_flinel;' in stand
    assert '+= pprint4_delta_v068229334[i_v068229334];' in stand
    finalize_begin=stand.index('FixedDsecSnapshot finalize_accepted_boundary_snapshot(')
    finalize_end=stand.index('void write_fixed_radial_input(', finalize_begin)
    finalize=stand[finalize_begin:finalize_end]
    assert '+= snapshot.flinel[' not in finalize


def test_flinel_accumulator_reset_remains_at_radial_pass_init():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    begin=stand.index('void initialize_native_radial_pass_v068227(')
    end=stand.index('void source_init_repeated_global_workspaces_v0682274(', begin)
    body=stand[begin:end]
    assert 'pprint4_flinel_accumulator_v068229334.assign(n, 0.0);' in body


def test_snapshot_bridge_and_writer_still_use_private_option4_surface():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    writer=(ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    assert 'ws.pprint4_flinel = source.pprint4_flinel;' in stand
    assert 'ws.pprint4_flinel.empty() ? ws.flinel : ws.pprint4_flinel' in writer
    assert 'vector_value(option4_flinel, i)' in writer


def test_narrow_host_runner_requires_full_payload_tails_and_columns():
    runner=(ROOT/'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_5.py').read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.5"' in runner
    assert 'OUTPUT_CONTROL_OPTION4_068229335_CPP_RESULT' in runner
    assert 'len(fields) < 12' in runner
    for name in ('energy','opacity','sigma_e3','scattered','rec_in','rec_out','brem_em','source','bbe','photon_occ','flinel'):
        assert name in runner
    assert 'flinel nonzero: fortran=' in runner
    assert 'flinel cpp-only channels:' in runner



def test_option4_private_flinel_replay_uses_literal_source_rate_family_gate():
    local=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    anchor=local.index('for (const auto& original_c : spectral) {', local.index('std::vector<double> pprint4_flinel_v068229334'))
    block=local[anchor:anchor+1800]
    assert 'if (original_c.rate_type != 4 && original_c.rate_type != 9)' in block
    assert 'continue;' in block
    # The gate is private to the pprint(4) replay; the operational spectral
    # stream and selected replay remain available below it.
    assert 'selected_lines_v82_patch5206.push_back(c);' in local

def test_science_revision_and_abis_remain_frozen():
    api=(ROOT/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod=(ROOT/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
