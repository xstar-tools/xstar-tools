from __future__ import annotations

import ast
from pathlib import Path

from xstar_tools.benchmarks.public_suite import _frozen_cpp_semantic_exception

ROOT = Path(__file__).resolve().parents[1]


def metric(**updates):
    base = {
        "inventory_gate": False,
        "numeric_gate": True,
        "metadata_gate": True,
        "common_order_gate": True,
        "column_inventory_gate": True,
        "hdu_presence_gate": True,
        "attachment_mismatches": 0,
        "candidate_duplicates": 0,
        "reference_duplicates": 0,
        "candidate_only_records": [],
        "reference_only_records": [],
        "union_max_surface_nl1": 0.0,
    }
    base.update(updates)
    return base


def rec(key, **meta):
    return {"hdu": "XSTAR_RADIAL#1", "key": list(key), **meta}


def test_frozen_cpp_detal2_rule_is_narrow_and_fail_closed():
    ok, why = _frozen_cpp_semantic_exception(
        "xo01_detal2.fits",
        metric(reference_only_records=[rec((66822, "ca_v", "lo", "up")), rec((88440, "ca_xviii", "lo", "up"))]),
    )
    assert ok and why == "CPP43_DETAL2_STALE_OPAKB1"
    bad, _ = _frozen_cpp_semantic_exception(
        "xo01_detal2.fits", metric(reference_only_records=[rec((99999, "ca_v", "lo", "up"))])
    )
    assert not bad


def test_frozen_cpp_rrc_rule_accepts_only_proven_cutoff_identity():
    ok, why = _frozen_cpp_semantic_exception(
        "xout_rrc1.fits", metric(reference_only_records=[rec((23595, "ca_xiii", "2p4.1S_0"))])
    )
    assert ok and why == "CPP43_RRC_TYPE49_CUTOFF"
    bad, _ = _frozen_cpp_semantic_exception(
        "xout_rrc1.fits", metric(reference_only_records=[rec((23596, "ca_xiii", "2p4.1S_0"))])
    )
    assert not bad


def test_frozen_cpp_detal3_carbon_and_oiv_rules_include_union_material_gate():
    carbon = metric(
        candidate_only_records=[rec((709, 334, "c_ii", "lo", "continuum")), rec((762, 378, "c_iv", "lo", "continuum"))],
        reference_only_records=[rec((681, 341, "c_ii", "lo", "continuum")), rec((726, 361, "c_iii", "lo", "continuum"))],
        union_max_surface_nl1=4.6e-4,
    )
    ok, why = _frozen_cpp_semantic_exception("xo01_detal3.fits", carbon)
    assert ok and why == "CPP4332_DETAL3_CARBON_INVENTORY"
    carbon["union_max_surface_nl1"] = 0.01
    assert not _frozen_cpp_semantic_exception("xo01_detal3.fits", carbon)[0]

    oiv = metric(
        candidate_only_records=[rec((3000, 1037, "o_iv", "lo", "continuum"), energy=-0.961998)],
        union_max_surface_nl1=2.0e-5,
    )
    ok, why = _frozen_cpp_semantic_exception("xo01_detal3.fits", oiv)
    assert ok and why == "CPP4332_DETAL3_OIV_NONPOSITIVE"
    oiv["candidate_only_records"][0]["energy"] = 0.1
    assert not _frozen_cpp_semantic_exception("xo01_detal3.fits", oiv)[0]


def test_frozen_cpp_semantic_rule_rejects_attachment_or_order_regression():
    known = metric(reference_only_records=[rec((88440, "ca_xviii", "lo", "up"))])
    known["attachment_mismatches"] = 1
    assert not _frozen_cpp_semantic_exception("xo01_detal2.fits", known)[0]
    known["attachment_mismatches"] = 0
    known["common_order_gate"] = False
    assert not _frozen_cpp_semantic_exception("xo01_detal2.fits", known)[0]


def test_python_bridge_includes_python_h_before_project_and_standard_headers():
    text = (ROOT / "src/xstar_tools/xstar/cpp/xstar_backend_python.cpp").read_text()
    py = text.index("#include <Python.h>")
    assert py < text.index('#include "xstar_backend_plugin.h"')
    assert py < text.index("#include <algorithm>")


def test_comp2_source_diagnostic_accumulator_is_explicitly_intentional():
    text = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    assert text.count("[[maybe_unused]] double sum2") == 2
    assert "Fortran comp2" in text
    assert "cfake" in text


def test_retired_physical_output_diagnostics_is_not_a_module_startup_import():
    path = ROOT / "src/xstar_tools/source_port_physical_runner_cli.py"
    tree = ast.parse(path.read_text())
    top_imports = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            top_imports.append(node.module or "")
    assert not any("physical_output_diagnostics" in name for name in top_imports)
    text = path.read_text()
    assert "if args.diagnostics_dir is not None:" in text
    assert "from .xstar.physical_output_diagnostics import diagnose_physical_output_mismatch" in text
