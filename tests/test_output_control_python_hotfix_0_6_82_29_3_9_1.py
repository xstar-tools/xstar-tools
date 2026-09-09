from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PP = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
PR = ROOT / "src/xstar_tools/xstar/physical_runner.py"


def _function_source(path: Path, name: str) -> str:
    text = path.read_text()
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(name)




def test_final_verbose_recompute_retains_record_results_only_for_publication():
    text = _function_source(PR, "_calc_kwargs_factory")
    assert 'state.control.get("continuum_phase_context", "")' in text
    assert 'state.control.get("requested_lpri", 0)' in text
    assert '>= 2' in text
    assert 'or final_verbose_publication' in text


def test_option10_uses_full_source_element_names():
    text = _function_source(PP, "_option10_ion_rates")
    assert "element_name = _pprint_element_column_name(element)" in text
    assert "element_name[:10]" in text


def test_option7_reconstructs_shared_continuum_next_ground_rate_roles():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import types
    astropy = types.ModuleType("astropy")
    astropy_io = types.ModuleType("astropy.io")
    astropy_fits = types.ModuleType("astropy.io.fits")
    astropy_io.fits = astropy_fits
    astropy.io = astropy_io
    sys.modules.setdefault("astropy", astropy)
    sys.modules.setdefault("astropy.io", astropy_io)
    sys.modules.setdefault("astropy.io.fits", astropy_fits)
    from xstar_tools.xstar.pprint_legacy import _option7_source_role_rate_maps

    def level(global_index, ion_index, excitation_eV, ion_label, atomic_number, level_label, upper_index):
        return SimpleNamespace(
            global_index=global_index, ion_index=ion_index, excitation_eV=excitation_eV,
            ion_label=ion_label, atomic_number=atomic_number, level_label=level_label,
            upper_index=upper_index,
        )
    levels = (
        level(10, 17, 0.0, "c_ii", 6, "ground", 1),
        level(11, 17, 24.0, "c_ii", 6, "continuum", 2),
        level(12, 18, 0.0, "c_iii", 6, "ground", 1),
        level(13, 18, 10.0, "c_iii", 6, "excited", 2),
        level(14, 18, 48.0, "c_iii", 6, "continuum", 3),
    )
    state = SimpleNamespace(control={"output_atomic_metadata": SimpleNamespace(levels=levels)})
    solve = SimpleNamespace(
        gamma=np.asarray([8.51401, 2.0, 3.0]),
        alpha=np.asarray([1.27634e-8, 5.0, 6.0]),
        igammamax_record=np.asarray([99, 100, 101]),
        ialphamax_record=np.asarray([199, 200, 201]),
    )
    basis = SimpleNamespace(blocks=(SimpleNamespace(ion_index=18, compact_start=1),))
    element = SimpleNamespace(
        request=SimpleNamespace(element_z=6),
        equilibrium=SimpleNamespace(assembly=SimpleNamespace(basis=basis), solve=solve),
    )
    fixed = SimpleNamespace(
        element_results=[element], gammag={}, alphag={}, igammamaxg={}, ialphamaxg={}
    )
    gamma, alpha, igamma, ialpha = _option7_source_role_rate_maps(state, fixed)
    # c_ii continuum shares the first active c_iii ground compact row.
    assert gamma[(6, 2, 2)] == 8.51401
    assert alpha[(6, 2, 2)] == 1.27634e-8
    # Source calc_hmc_all leaves dominant-record pointers zero for continua.
    assert igamma[(6, 2, 2)] == 0
    assert ialpha[(6, 2, 2)] == 0
    # The next-ion ground sees the same shared compact-row rate values.
    assert gamma[(6, 3, 1)] == 8.51401
    assert alpha[(6, 3, 1)] == 1.27634e-8


def test_options29_and30_consume_retained_final_record_results():
    o29 = _function_source(PP, "_option29_rates")
    o30 = _function_source(PP, "_option30_auger_fluorescence")
    for text in (o29, o30):
        assert 'getattr(fixed, "element_results", ())' in text
        assert 'getattr(assembly, "record_results", ())' in text
    assert 'row.get("ans1"' in o29
    assert '_source_ucalc_publication_endpoints' in o29
    assert '_source_ucalc_publication_endpoints' in o30


