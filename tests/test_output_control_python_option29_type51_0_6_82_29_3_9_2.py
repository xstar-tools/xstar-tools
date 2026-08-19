from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PP = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"


def _function_source(path: Path, name: str) -> str:
    text = path.read_text()
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(name)


def _import_helper():
    sys.path.insert(0, str(ROOT / "src"))
    astropy = types.ModuleType("astropy")
    astropy_io = types.ModuleType("astropy.io")
    astropy_fits = types.ModuleType("astropy.io.fits")
    astropy_io.fits = astropy_fits
    astropy.io = astropy_io
    sys.modules.setdefault("astropy", astropy)
    sys.modules.setdefault("astropy.io", astropy_io)
    sys.modules.setdefault("astropy.io.fits", astropy_fits)
    from xstar_tools.xstar.pprint_legacy import _source_ucalc_publication_endpoints
    return _source_ucalc_publication_endpoints


def test_version_is_068229392():
    assert 'version = "0.6.82.29.3.9.2"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.29.3.9.2" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_type51_publication_is_upper_energy_first():
    helper = _import_helper()
    levels = {
        (18, 1): SimpleNamespace(excitation_eV=0.0),
        (18, 4): SimpleNamespace(excitation_eV=12.5),
    }
    # Python retained operational rows are lower-first. Canonical UCalc Type 51
    # returns idest1 as the upper-energy endpoint before pprint(29) stores it.
    row = {"data_type": 51, "rate_type": 3, "idest1": 1, "idest2": 4}
    assert helper(row, 18, levels) == (4, 1)


def test_type51_already_upper_first_is_stable():
    helper = _import_helper()
    levels = {
        (18, 1): SimpleNamespace(excitation_eV=0.0),
        (18, 4): SimpleNamespace(excitation_eV=12.5),
    }
    row = {"data_type": 51, "rate_type": 3, "idest1": 4, "idest2": 1}
    assert helper(row, 18, levels) == (4, 1)


def test_type51_rule_matches_host_closed_cpp_helper_family():
    text = _function_source(PP, "_source_ucalc_publication_endpoints")
    assert "data_type in {50, 51, 76, 91}" in text
    assert "if e1 is not None and e2 is not None and e1 < e2" in text
    assert "return id2, id1" in text


def test_option29_still_uses_source_endpoint_helper_and_raw_rates():
    text = _function_source(PP, "_option29_rates")
    assert "_source_ucalc_publication_endpoints" in text
    assert 'row.get("ans1"' in text
    assert "compact_start" in text


def test_single_lprint6_runner_still_covers_all_options():
    path = ROOT / "tools/qualification/run_output_control_python_lprint6_host_smoke_0_6_82_29_3_9_2.py"
    text = path.read_text()
    assert 'CASE = "lprint_6"' in text
    assert 'EXPECTED_OPTIONS = (14, 21, 7, 10, 4, 6, 18, 29, 30)' in text
    assert 'OUTPUT_CONTROL_068229392_LPRINT6_PYTHON_RESULT' in text
