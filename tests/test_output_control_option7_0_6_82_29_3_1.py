from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    path = ROOT / "tools/qualification/run_output_control_host_smoke_0_6_82_29_3_1.py"
    spec = importlib.util.spec_from_file_location("output_control_host_06822931", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_version_and_frozen_identifiers():
    assert 'version = "0.6.82.29.3.1"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.29.3.1" in (
        ROOT / "src/xstar_tools/xstar/cpp/Makefile"
    ).read_text()
    assert "science revision" not in (ROOT / "CHANGELOG.md").read_text().lower() or "frozen" in (ROOT / "CHANGELOG.md").read_text().lower()


def test_cpp_option7_retains_full_source_payload():
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    run_state = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp").read_text()
    engine = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    internal = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_internal.hpp").read_text()
    for token in (
        "source_global_bilevg",
        "source_global_gammag",
        "source_global_alphag",
        "source_global_igammamaxg",
        "source_global_ialphamaxg",
        "pop / (rn + 1.0e-36)",
    ):
        assert token in step + run_state
    for token in ("level_gamma", "level_alpha", "level_igammamax", "level_ialphamax"):
        assert token in engine + internal


def test_python_option7_uses_existing_full_source_state():
    text = (ROOT / "src/xstar_tools/xstar/pprint_legacy.py").read_text()
    for token in (
        "global_bilevg_by_index",
        'getattr(fixed, "gammag"',
        'getattr(fixed, "alphag"',
        'getattr(fixed, "igammamaxg"',
        'getattr(fixed, "ialphamaxg"',
        "dep = pop / (rnval + 1.0e-36)",
    ):
        assert token in text


def test_option7_parser_rejects_old_short_row(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref"; cand = tmp_path / "cand"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option: 7\n"
        "      1 h_i      1s1.2S_1/2 0.0 1.0e-7 4.0e-17 2.5e9 2.5e9 9.0 469 1.0e-6 187\n"
        " print option:10\n"
    )
    (cand / "xout_step.log").write_text(
        " print option: 7\n"
        "      1 h_i      1s1.2S_1/2 0.0 1.0e-7 4.0e-17\n"
        " print option:10\n"
    )
    rs = mod.verbose_shape(ref, 7)
    cs = mod.verbose_shape(cand, 7)
    assert rs["rows"] == 1
    assert cs["rows"] == 0
    assert not mod.shape_matches(rs, cs, 7)


def test_option7_parser_checks_dominant_record_identity_and_payload(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref"; same = tmp_path / "same"; bad = tmp_path / "bad"
    for p in (ref, same, bad): p.mkdir()
    row = "      1 h_i      1s1.2S_1/2 0.0 1.0e-7 4.0e-17 2.5e9 2.5e9 9.0 469 1.0e-6 187\n"
    (ref / "xout_step.log").write_text(" print option: 7\n" + row + " print option:10\n")
    (same / "xout_step.log").write_text(" print option: 7\n" + row + " print option:10\n")
    badrow = "      1 h_i      1s1.2S_1/2 0.0 1.0e-7 4.0e-17 2.5e9 2.5e9 9.0 470 2.0e-6 188\n"
    (bad / "xout_step.log").write_text(" print option: 7\n" + badrow + " print option:10\n")
    rs = mod.verbose_shape(ref, 7)
    assert mod.shape_matches(rs, mod.verbose_shape(same, 7), 7)
    assert not mod.shape_matches(rs, mod.verbose_shape(bad, 7), 7)


def test_option7_has_narrow_cpp_host_gate():
    text = (ROOT / "tools/qualification/run_output_control_option7_host_smoke_0_6_82_29_3_1.py").read_text()
    assert 'CASE = "lprint_2"' in text
    assert "OUTPUT_CONTROL_OPTION7_06822931_CPP_RESULT" in text
    assert "verbose_shape(ref, 7)" in text
    assert "shape_matches(ref_shape, cpp_shape, 7)" in text
    assert "Options 4/6/10/18/29/30" in text
