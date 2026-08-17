from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_bumped_after_rejected_3332_host_candidate():
    assert 'version = "0.6.82.29.3.3.3"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.3' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_fortran_source_flinel_is_pass_owned_additive_state():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'std::vector<double> pprint4_flinel_accumulator_v068229333;' in stand
    assert 'data.pprint4_flinel_accumulator_v068229333.assign(n, 0.0);' in stand
    assert 'data.pprint4_flinel_accumulator_v068229333[i_v068229333] += snapshot.flinel[i_v068229333];' in stand
    assert 'snapshot.pprint4_flinel = data.pprint4_flinel_accumulator_v068229333;' in stand


def test_flinel_reset_is_at_radial_pass_init_not_fixed_state_evaluation():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    begin=stand.index('void initialize_native_radial_pass_v068227(')
    end=stand.index('void source_init_repeated_global_workspaces_v0682274(', begin)
    body=stand[begin:end]
    assert 'pprint4_flinel_accumulator_v068229333.assign(n, 0.0);' in body
    finalize_begin=stand.index('FixedDsecSnapshot finalize_accepted_boundary_snapshot(')
    finalize_end=stand.index('void write_fixed_radial_input(', finalize_begin)
    finalize=stand[finalize_begin:finalize_end]
    assert 'pprint4_flinel_accumulator_v068229333.assign(n, 0.0);' not in finalize
    assert '+= snapshot.flinel[i_v068229333];' in finalize


def test_final_zero_thickness_copy_preserves_pass_accumulator_then_adds_current_call():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    copy=stand.index('auto final_pprint_data = data;')
    eval_call=stand.index('auto final_pprint = evaluate_full_boundary(', copy)
    reset=stand.find('initialize_native_radial_pass_v068227(', copy, eval_call)
    assert reset == -1
    assert copy < eval_call
    # evaluate_full_boundary returns through finalize_accepted_boundary_snapshot,
    # where current selected-line flinel is added to the copied pass history.
    assert 'return finalize_accepted_boundary_snapshot(data, std::move(snapshot));' in stand


def test_snapshot_bridge_and_writer_still_use_private_option4_surface():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    writer=(ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    assert 'ws.pprint4_flinel = source.pprint4_flinel;' in stand
    assert 'ws.pprint4_flinel.empty() ? ws.flinel : ws.pprint4_flinel' in writer
    assert 'vector_value(option4_flinel, i)' in writer


def test_other_option4_publication_surfaces_remain_unchanged():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    anchor=stand.index('final_pprint.pprint4_opakc = final_pprint.opakc;')
    smooth=stand.index('advance_source_continuum_radiation(', anchor)
    body=stand[anchor:smooth]
    assert 'final_pprint.pprint4_rccemis = final_pprint.rccemis;' in body
    assert 'final_pprint.pprint4_brcems = dense_bremem_source(' in body


def test_narrow_host_runner_requires_full_payload_and_tails():
    runner=(ROOT/'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_3.py').read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.3"' in runner
    assert 'OUTPUT_CONTROL_OPTION4_068229333_CPP_RESULT' in runner
    assert 'len(fields) < 12' in runner
    assert '_payload_matches' in runner and '_tails_match' in runner
    for name in ('energy','opacity','sigma_e3','scattered','rec_in','rec_out','brem_em','source','bbe','photon_occ','flinel'):
        assert name in runner


def test_science_revision_and_abis_remain_frozen():
    api=(ROOT/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod=(ROOT/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
