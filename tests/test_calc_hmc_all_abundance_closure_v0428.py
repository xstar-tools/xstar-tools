from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    build_xstar_vector_matrix_closure,
    load_calc_hmc_all_probe_element_reference,
)
from xstar_atomic.source_port_local_zone_cli import build_parser


def test_cli_abundance_is_probe_resolved_when_not_requested():
    parser = build_parser()
    args = parser.parse_args([
        "--atdb", "atdb.fits",
        "--temperature-k", "1e6",
        "--hydrogen-density-cm3", "1e8",
        "--electron-fraction-xee", "1",
        "--out-dir", "out",
    ])
    assert args.abundance is None


def test_load_element_probe_reference_reads_abundance(tmp_path):
    path = tmp_path / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv"
    path.write_text(
        "calc_hmc_all_call_id,element_index,element_z,abundance,mml,mmu,htt,cll,htt2,cll2\n"
        "73,8,8,6.8e-4,3,8,1e-7,2e-7,3e-8,4e-8\n"
    )
    ref = load_calc_hmc_all_probe_element_reference(tmp_path, element_z=8)
    assert ref.call_id == 73
    assert ref.element_index == 8
    assert ref.abundance == pytest.approx(6.8e-4)
    assert (ref.mml, ref.mmu) == (3, 8)


def test_xstar_vector_closure_and_thermal_decomposition():
    basis_rows = {
        1: SimpleNamespace(roles=[{"ion_stage": 1, "local_level": 1}]),
        2: SimpleNamespace(roles=[{"ion_stage": 2, "local_level": 1}]),
    }
    basis = SimpleNamespace(n_rows=2, row=lambda index: basis_rows[index])
    terms = [
        SimpleNamespace(row=1, column=1, aj1=-1.0, cj=-2.0, cj2=1.0,
                        record=10, data_type=50, rate_type=4, role="diag1"),
        SimpleNamespace(row=1, column=2, aj1=1.0, cj=0.0, cj2=0.0,
                        record=11, data_type=50, rate_type=4, role="feed1"),
        SimpleNamespace(row=2, column=1, aj1=1.0, cj=0.0, cj2=0.0,
                        record=12, data_type=50, rate_type=4, role="feed2"),
        SimpleNamespace(row=2, column=2, aj1=-1.0, cj=4.0, cj2=-6.0,
                        record=13, data_type=50, rate_type=4, role="diag2"),
    ]
    matrix = np.array([[-1.0, 1.0], [1.0, -1.0]])
    native = np.array([0.4, 0.6])
    native_residual = matrix @ native
    native_scale = np.sum(np.abs(matrix) * np.abs(native[np.newaxis, :]), axis=1)
    solve = SimpleNamespace(
        populations=native,
        row_residual=native_residual,
        relative_row_residual=np.abs(native_residual) / native_scale,
        l1_row_residual=float(np.sum(np.abs(native_residual))),
        l1_relative_row_residual=float(np.sum(np.abs(native_residual)) / np.sum(native_scale)),
    )
    assembly = SimpleNamespace(basis=basis, terms=terms, dense_matrix=matrix)
    equilibrium = SimpleNamespace(assembly=assembly, solve=solve)
    element = SimpleNamespace(
        request=SimpleNamespace(element_z=8, abundance=0.1),
        equilibrium=equilibrium,
    )
    result = SimpleNamespace(
        element_results=[element],
        global_level_index_by_key={(8, 1, 1): 100, (8, 2, 1): 101},
    )
    level_rows = [
        {"global_level_index": "100", "xilevg": "0.5"},
        {"global_level_index": "101", "xilevg": "0.5"},
    ]
    element_rows = [{
        "element_z": "8", "abundance": "0.1",
        "htt": "0.1", "cll": "0.2", "htt2": "0.3", "cll2": "0.05",
    }]
    closure = build_xstar_vector_matrix_closure(
        result,
        level_probe_rows=level_rows,
        element_probe_rows=element_rows,
        rtol=5e-3,
        atol=1e-12,
    )
    assert closure.ready is True
    item = closure.elements[0]
    assert item.xstar_vector_normalization == pytest.approx(1.0)
    assert item.xstar_vector_l1_residual == pytest.approx(0.0)
    summaries = {row["thermal_channel"]: row for row in item.thermal_summary_rows}
    assert summaries["heating"]["xstar_vector_python_coefficients_per_abundance"] == pytest.approx(1.0)
    assert summaries["cooling"]["xstar_vector_python_coefficients_per_abundance"] == pytest.approx(2.0)
    assert summaries["heating2"]["xstar_vector_python_coefficients_per_abundance"] == pytest.approx(3.0)
    assert summaries["cooling2"]["xstar_vector_python_coefficients_per_abundance"] == pytest.approx(0.5)
    for row in summaries.values():
        assert row["remaining_coefficient_or_semantics_gap_per_abundance"] == pytest.approx(0.0)
