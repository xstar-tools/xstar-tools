from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    path = ROOT / "tools/qualification/run_output_control_host_smoke_0_6_82_29_2.py"
    spec = importlib.util.spec_from_file_location("output_control_host_0682292", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_successor_versions_and_frozen_science_contract():
    pyproject = (ROOT / "pyproject.toml").read_text()
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert 'version = "0.6.82.29.2"' in pyproject
    assert "PACKAGE_VERSION ?= 0.6.82.29.2" in makefile
    # The publication-only hotfix does not change any science or ABI identifiers.
    text = (ROOT / "qualification/output_control_verbose_0_6_82_29_2/output_control_verbose_scope_0_6_82_29_2.json").read_text()
    assert '"science_revision": "0.6.48.12.3.45.3.3.8"' in text
    assert '"c_api_abi": 60487' in text
    assert '"production_zone_abi": 6048110' in text
    assert '"fixed_state_abi": 60488' in text


def test_cpp_verbose_publication_uses_retained_active_state():
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    engine = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    internal = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_internal.hpp").read_text()
    for token in (
        "first_ion_rrcs_by_z",
        "source_ionization_rates",
        "source_recombination_rates",
        "free_free_heating",
        "record_product_diagnostics",
        "source_detail_active_windows",
        "std::abs(row.ans[0]) > 1.0e-34",
    ):
        assert token in step
    assert "last_source_ionization_rates_v0682292" in engine
    assert "last_source_recombination_rates_v0682292" in engine
    assert "capture_publication_state_v0682292" in engine
    assert "PublicationStateV0682292" in internal
    assert "capture_publication_state_v0682292" in standalone
    for banned in ("retained-rate-components-unavailable", "retained-k-shell-scalars-unavailable", "retained-source-norms-unavailable"):
        assert banned not in step.lower()


def test_python_verbose_publication_retains_source_payloads_without_placeholders():
    pprint = (ROOT / "src/xstar_tools/xstar/pprint_legacy.py").read_text()
    runner = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text()
    for token in (
        "_source_verbose_line_rows",
        "_source_verbose_level_rows",
        "oplin_physical",
        "rcem_physical",
        "cemab_physical",
        'getattr(assembly, "record_results", ())',
        'source_arrays["pirt"]',
        'source_arrays["rrrt"]',
    ):
        assert token in (pprint + runner)
    for banned in ("retained-rate-components-unavailable", "retained-k-shell-scalars-unavailable", "retained-source-norms-unavailable", "retained per-record rate workspace unavailable"):
        assert banned not in pprint.lower()
    assert "301301" not in pprint
    assert "733824" not in pprint


def test_verbose_shape_parser_rejects_placeholders_even_when_row_count_matches(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref_placeholder"; cand = tmp_path / "cand_placeholder"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option:30\n"
        " he_i 0.0 1.0 0.0 1.0e34\n"
        " total time\n"
    )
    (cand / "xout_step.log").write_text(
        " print option:30\n"
        " he_i retained-k-shell-scalars-unavailable\n"
        " total time\n"
    )
    rs = mod.verbose_shape(ref, 30)
    cs = mod.verbose_shape(cand, 30)
    assert rs["rows"] == cs["rows"] == 1
    assert cs["placeholder"]
    assert not mod.shape_matches(rs, cs, 30)


def test_verbose_shape_parser_option29_rejects_equal_count_wrong_source_identity(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref29"; cand = tmp_path / "cand29"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option:29\n"
        " 36 h_i lo up 53 7 29 33 29 33 1 2 3 4 5 6\n"
        " print option:30\n"
    )
    (cand / "xout_step.log").write_text(
        " print option:29\n"
        " 36 h_i lo up 53 7 29 33 29 34 1 2 3 4 5 6\n"
        " print option:30\n"
    )
    rs = mod.verbose_shape(ref, 29)
    cs = mod.verbose_shape(cand, 29)
    assert rs["rows"] == cs["rows"] == 1
    assert not mod.shape_matches(rs, cs, 29)


def test_option30_roman_stage_parser_covers_multi_element_stages():
    import ast
    path = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
    tree = ast.parse(path.read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_roman_stage_from_ion_label")
    module = ast.Module(body=[fn], type_ignores=[])
    ns = {}
    exec(compile(module, str(path), "exec"), ns)
    parse = ns["_roman_stage_from_ion_label"]
    assert parse("c_vi") == 6
    assert parse("fe_xvii") == 17
    assert parse("fe_xxvi") == 26

def test_verbose_shape_parser_rejects_equal_count_wrong_identity(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref"; cand = tmp_path / "cand"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option:18\n"
        " 1 1.0 h_i lo up 1 2\n"
        " 7 2.0 c_iv lo up 3 4\n"
        " print option:29\n"
    )
    (cand / "xout_step.log").write_text(
        " print option:18\n"
        " 1 1.0 h_i lo up 1 2\n"
        " 8 2.0 c_iv lo up 3 4\n"
        " print option:29\n"
    )
    rs = mod.verbose_shape(ref, 18)
    cs = mod.verbose_shape(cand, 18)
    assert rs["rows"] == cs["rows"] == 2
    assert not mod.shape_matches(rs, cs, 18)


def test_verbose_shape_parser_ignores_option14_capacity_scalar(tmp_path: Path):
    mod = _load_runner()
    out = tmp_path / "run"; out.mkdir()
    (out / "xout_step.log").write_text(
        " print option:14\n"
        " 736256\n"
        " 1 1.0 2.0 h_i 0.0 1.0\n"
        " 2 2.0 3.0 h_i 0.0 2.0\n"
        " print option:21\n"
    )
    shape = mod.verbose_shape(out, 14)
    assert shape["rows"] == 2
    assert shape["keys"] == ("1", "2")


def test_verbose_shape_parser_rejects_option10_wrong_identity(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref10"; cand = tmp_path / "cand10"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option:10\n"
        " 1 h_i 1.0 2.0 3.0\n"
        " 16 c_i 1.0 2.0 3.0\n"
        " 1 hydrogen 1.0 2.0 3.0\n"
        " compton 1.0 2.0 3.0\n"
        " print option:26\n"
    )
    (cand / "xout_step.log").write_text(
        " print option:10\n"
        " 1 h_i 1.0 2.0 3.0\n"
        " 6 c_i 1.0 2.0 3.0\n"
        " 1 hydrogen 1.0 2.0 3.0\n"
        " compton 1.0 2.0 3.0\n"
        " print option:26\n"
    )
    rs = mod.verbose_shape(ref, 10)
    cs = mod.verbose_shape(cand, 10)
    assert rs["rows"] == cs["rows"] == 4
    assert not mod.shape_matches(rs, cs, 10)


def test_verbose_shape_parser_accepts_reduced_native_option4_rows(tmp_path: Path):
    mod = _load_runner()
    out = tmp_path / "opt4"; out.mkdir()
    (out / "xout_step.log").write_text(
        " print option: 4\n"
        " 2 1.0 2.0 0.0 3.0 4.0\n"
        " 3 2.0 3.0 0.0 4.0 5.0\n"
        " print option: 6\n"
    )
    shape = mod.verbose_shape(out, 4)
    assert shape["rows"] == 2
    assert shape["keys"] == ("2", "3")


def test_verbose_shape_parser_option21_checks_rrc_identity_not_just_slot(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref21"; cand = tmp_path / "cand21"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option:21\n"
        " 33 51 he_ii 18 47 lower continuum 1.0 2.0\n"
        " print option: 7\n"
    )
    (cand / "xout_step.log").write_text(
        " print option:21\n"
        " 33 51 he_i 18 47 lower continuum 1.0 2.0\n"
        " print option: 7\n"
    )
    rs = mod.verbose_shape(ref, 21)
    cs = mod.verbose_shape(cand, 21)
    assert rs["rows"] == cs["rows"] == 1
    assert not mod.shape_matches(rs, cs, 21)


def test_verbose_shape_parser_option7_checks_source_level_role(tmp_path: Path):
    mod = _load_runner()
    ref = tmp_path / "ref7"; cand = tmp_path / "cand7"
    ref.mkdir(); cand.mkdir()
    (ref / "xout_step.log").write_text(
        " print option: 7\n"
        " 79 he_i continuum 1.0 2.0\n"
        " print option:10\n"
    )
    (cand / "xout_step.log").write_text(
        " print option: 7\n"
        " 79 he_ii 1s1.2S 1.0 2.0\n"
        " print option:10\n"
    )
    rs = mod.verbose_shape(ref, 7)
    cs = mod.verbose_shape(cand, 7)
    assert rs["rows"] == cs["rows"] == 1
    assert not mod.shape_matches(rs, cs, 7)
