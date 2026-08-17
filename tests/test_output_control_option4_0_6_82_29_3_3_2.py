from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_bumped():
    assert 'version = "0.6.82.29.3.3.2"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.2' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_final_snapshot_bridge_copies_option4_publication_surfaces():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    start=stand.index('xstar_run_state::FixedEvaluationState copy_real_native_snapshot(')
    end=stand.index('bool vector_has_nonzero', start)
    body=stand[start:end]
    for token in (
        'ws.pprint4_opakc = source.pprint4_opakc;',
        'ws.pprint4_rccemis = source.pprint4_rccemis;',
        'ws.pprint4_brcems = source.pprint4_brcems;',
        'ws.pprint4_flinel = source.pprint4_flinel;',
    ):
        assert token in body


def test_private_option4_publication_surfaces_exist():
    state=(ROOT/'src/xstar_tools/xstar/cpp/xstar_run_state.hpp').read_text()
    for token in ('pprint4_opakc','pprint4_rccemis','pprint4_brcems','pprint4_flinel'):
        assert token in state


def test_final_writer_freezes_pre_gsmooth_option4_state():
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    anchor=stand.index('final_pprint.pprint4_opakc = final_pprint.opakc;')
    smooth=stand.index('advance_source_continuum_radiation(', anchor)
    assert anchor < smooth
    assert 'final_pprint.pprint4_rccemis = final_pprint.rccemis;' in stand[anchor:smooth]
    assert 'final_pprint.pprint4_brcems = dense_bremem_source(' in stand[anchor:smooth]


def test_source_owned_flinel_publication_is_additive_not_operational():
    eng=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    assert 'std::vector<double> pprint4_flinel_v068229331 = flinel;' in eng
    assert 'pprint4_flinel_v068229331[k_v068229331] += selected_flinel[k_v068229331];' in eng
    assert 'flinel.swap(selected_flinel);' in eng
    bridge=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_internal.hpp').read_text()
    assert 'std::vector<double> option4_flinel;' in bridge


def test_option4_writer_prefers_publication_surfaces():
    cpp=(ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    for token in (
        'ws.pprint4_opakc.empty() ? ws.opakc : ws.pprint4_opakc',
        'ws.pprint4_rccemis.empty() ? ws.rccemis : ws.pprint4_rccemis',
        'ws.pprint4_flinel.empty() ? ws.flinel : ws.pprint4_flinel',
        'if (!ws.pprint4_brcems.empty())',
        'vector_value(option4_opakc, i)',
        'flat_plane(option4_rccemis, 2u, 1u, i)',
        'vector_value(option4_flinel, i)',
    ):
        assert token in cpp


def test_hotfix_does_not_change_python_option4_implementation():
    py=(ROOT/'src/xstar_tools/xstar/pprint_legacy.py').read_text()
    for token in ('sigma*e**3','flinel[i]','opsum cont=','rosseland mean opacity='):
        assert token in py


def test_narrow_host_runner_requires_full_payload_and_tails():
    runner=(ROOT/'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_2.py').read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.2"' in runner
    assert "len(fields) < 12" in runner
    assert '_payload_matches' in runner and '_tails_match' in runner
    assert 'OUTPUT_CONTROL_OPTION4_068229332_CPP_RESULT' in runner
