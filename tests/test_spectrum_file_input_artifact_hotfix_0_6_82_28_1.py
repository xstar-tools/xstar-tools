from __future__ import annotations
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def test_0682281_scope_and_frozen_identifiers():
    d=json.loads((ROOT/'qualification/spectrum_0_6_82_28_1/spectrum_file_input_artifact_hotfix_scope_0_6_82_28_1.json').read_text())
    assert d['milestone']=='0.6.82.28.1'
    assert d['baseline']=='0.6.82.28'
    assert d['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert (d['c_api_abi'],d['production_zone_abi'],d['fixed_state_abi'])==(60487,6048110,60488)
    assert d['production_numerical_changed']==['src/xstar_tools/xstar/cpp/xstar_standalone.cpp']
    assert d['scope_accept'] is True

def test_0682281_cpp_retains_historical_file_spectrum_helper_after_06851_guard_retirement():
    cpp=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'add_public_source_input_allowances_v0682281(' in cpp
    assert 'if (spectrum_mode != "file") return;' in cpp
    assert 'json_string_value(publication_json, "spectrum_file", "spct.dat")' in cpp
    assert 'std::filesystem::is_regular_file(candidate_abs)' in cpp
    assert 'candidate_abs.parent_path() == output_abs' in cpp
    # 0.6.85.1 supersedes the old directory-exclusivity policy: unrelated
    # files no longer require special allowance and are never rejection causes.
    assert 'file-silent production created a non-product artifact:' not in cpp
    assert 'true production created a non-product artifact:' not in cpp

def test_0682281_host_runner_targets_all_file_units():
    text=(ROOT/'tools/qualification/run_spectrum_contract_host_smoke_0_6_82_28_1.py').read_text()
    assert 'EXPECTED_VERSION = "0.6.82.28.1"' in text
    assert 'SPECTRUM_CONTRACT_0682281_RESULT' in text
    for case in ('file_e0','file_p1','file_log2'):
        assert f'"{case}"' in text
