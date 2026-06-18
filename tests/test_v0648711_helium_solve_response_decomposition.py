from __future__ import annotations

import numpy as np
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.helium_solve_response_decomposition import (
    RELEASE,
    SCHEMA,
    _effective_system,
    _pivot_sequence,
    _verify_source_order_assembly,
)

ROOT = Path(__file__).resolve().parents[1]


def test_release_and_native_diagnostic_gate() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.11.1"
    assert RELEASE == "0.6.48.7.13"
    assert SCHEMA == "xstar-tools-v0648711-helium-solve-response-decomposition-v1"
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert 'environment_flag("XSTAR_QUALIFICATION_SOLVE_RESPONSE")' in cpp
    assert "XSTAR_ELEMENT_RETURN_MATRICES" in cpp
    assert "_helium_source_order_terms.csv" in cpp
    assert "_helium_solve_matrix.csv" in cpp
    assert "_helium_solve_rows.csv" in cpp


def test_effective_normalization_system() -> None:
    dense = np.asarray([[2.0, -2.0], [-3.0, 3.0]])
    matrix, rhs = _effective_system(dense, 1)
    assert np.array_equal(matrix, np.asarray([[2.0, -2.0], [1.0, 1.0]]))
    assert np.array_equal(rhs, np.asarray([0.0, 1.0]))
    assert _pivot_sequence(matrix) == [1, 2]


def test_source_order_reconstruction_is_ieee_exact() -> None:
    dense = np.zeros((2, 2), dtype=np.float64)
    terms = [
        {"source_order_index": 1, "compact_row": 1, "compact_column": 2, "aj1": 3.0},
        {"source_order_index": 2, "compact_row": 1, "compact_column": 2, "aj1": -1.0},
        {"source_order_index": 3, "compact_row": 2, "compact_column": 1, "aj1": 4.0},
    ]
    dense[0, 1] = 2.0
    dense[1, 0] = 4.0
    report = _verify_source_order_assembly(terms, dense)
    assert report["matrix_ieee_exact"]
    assert report["terms"] == 3
    assert report["maximum_absolute_matrix_difference"] == 0.0
