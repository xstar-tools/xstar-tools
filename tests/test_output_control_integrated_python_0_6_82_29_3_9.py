from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PP = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
OW = ROOT / "src/xstar_tools/xstar/output_writers.py"
PR = ROOT / "src/xstar_tools/xstar/physical_runner.py"


def _function_source(path: Path, name: str) -> str:
    text = path.read_text()
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(name)


def test_version_is_06822939():
    assert 'version = "0.6.82.29.3.9"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.29.3.9" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_level_metadata_retains_literal_type13_payload_fields():
    text = OW.read_text()
    for token in (
        "statistical_weight: float = 0.0",
        "effective_n: float = 0.0",
        "principal_n: int = 0",
        "spin_multiplicity: int = 0",
        "orbital_l: int = 0",
    ):
        assert token in text


def test_metadata_cache_persists_type13_payload_and_is_versioned():
    text = PR.read_text()
    assert "OUTPUT_METADATA_CACHE_FORMAT_VERSION = 14" in text
    for token in (
        "level_statistical_weight", "level_effective_n", "level_principal_n",
        "level_spin_multiplicity", "level_orbital_l",
    ):
        assert token in text
    for token in (
        "statistical_weight=float(statistical_weight[pos])",
        "effective_n=float(effective_n[pos])",
        "principal_n=int(principal_n[pos])",
        "spin_multiplicity=int(spin_multiplicity[pos])",
        "orbital_l=int(orbital_l[pos])",
    ):
        assert token in text


def test_option18_emits_full_fortran_9929_payload():
    text = _function_source(PP, "_option18_line_levels")
    for token in (
        "statistical_weight", "effective_n", "principal_n", "spin_multiplicity", "orbital_l",
        'f"{value:13.5E}"', 'f"{value:6d}"',
        "pprint(18) lacks Type-13 endpoint metadata",
    ):
        assert token in text
    assert "int_payload" in text and "real_payload" in text


def test_type76_endpoint_fallback_uses_actual_python_excitation_field():
    text = _function_source(PP, "_source_ucalc_publication_endpoints")
    assert 'data_type in {50, 76, 91}' in text
    assert '"excitation_eV"' in text
    assert "return id2, id1" in text


def test_option7_and_option10_publication_fixes_are_present():
    pp = PP.read_text()
    source_levels = _function_source(PP, "_source_verbose_level_rows")
    assert 'int(getattr(row, "atomic_number", 0))' in source_levels
    assert '_roman_stage_from_ion_label' in source_levels
    assert 'int(getattr(row, "upper_index", 0))' in source_levels
    assert 'f"      compton  {htcomp:16.8E}' in pp
    assert 'f"      free-free{htfreef:16.8E}' in pp
    assert 'f"      total    {httot:16.8E}' in pp


def test_python_integrated_runner_reuses_closed_cpp_contract_and_exact_science_gate():
    text = (ROOT / "tools/qualification/run_output_control_integrated_python_host_smoke_0_6_82_29_3_9.py").read_text()
    assert "run_output_control_integrated_cpp_host_smoke_0_6_82_29_3_8.py" in text
    assert '"--mode", "pure-python"' in text
    assert "ok = rel == 0.0" in text
    assert "science-invariance python=" in text
    assert "OUTPUT_CONTROL_06822939_PYTHON_RESULT" in text
