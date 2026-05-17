from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    ElementEquilibriumContext,
    EscapeProbabilityContext,
    MatrixTerm,
    ElementCompactBasis,
    ElementBasisRow,
    build_element_compact_basis,
    load_atomic_database_state,
    msolvelucy,
    solve_element_statistical_equilibrium,
    write_element_equilibrium_products,
    leqt2f,
    XSTARLinearAlgebraError,
)
from xstar_atomic.source_port.element_equilibrium import ElementMatrixAssembly
from test_source_port_ucalc_v042 import _write_ucalc_atdb


class _LabelMaster:
    def record_chars(self, record: int) -> bytes:
        return b""


def test_oxygen_stage_3_to_8_compact_basis_has_exact_607_rows_and_aliases():
    # Production ATDB nlev values from the validated v0.4.1 pointer products.
    nlev = {31: 79, 32: 163, 33: 53, 34: 43, 35: 241, 36: 33}
    derived = SimpleNamespace(
        n_ions=36,
        ion_element_z=np.asarray([0] + [0] * 28 + [8] * 8, dtype=int),
        ion_stage=np.asarray([0] + [0] * 28 + list(range(1, 9)), dtype=int),
        ion_records=np.arange(37, dtype=int) + 1000,
        nlevs=np.asarray([0] + [0] * 30 + [nlev[i] for i in range(31, 37)], dtype=int),
        npfi=np.zeros((103, 37), dtype=int),
    )
    basis = build_element_compact_basis(
        _LabelMaster(), derived, element_z=8, min_ion_stage=3, max_ion_stage=8
    )
    assert basis.n_rows == 607
    assert len(basis.blocks) == 6
    assert basis.normalization_row == 607
    assert sum(row.is_shared_alias for row in basis.rows) == 5
    for left, right in zip(basis.blocks[:-1], basis.blocks[1:]):
        assert left.compact_stop == right.compact_start
        shared = basis.row(left.compact_stop)
        assert len(shared.roles) == 2
        assert {r["ion_stage"] for r in shared.roles} == {left.ion_stage, right.ion_stage}


def test_source_faithful_element_sequence_solves_complete_synthetic_element(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_ucalc_atdb(atdb)
    built = load_atomic_database_state(atdb)
    try:
        context = ElementEquilibriumContext(
            temperature_k=1.0e4,
            hydrogen_density_cm3=1.0,
            electron_fraction_xee=1.0,
            min_ion_stage=1,
            max_ion_stage=1,
            covering_fraction=1.0,
            escape=EscapeProbabilityContext(allow_missing_as_zero=True),
            strict_context=True,
        )
        result = solve_element_statistical_equilibrium(
            built.master, built.derived, element_z=1, context=context
        )
        assert result.assembly.basis.n_rows == 2
        assert result.assembly.n_records_blocked == 0
        assert result.assembly.n_unmapped_endpoints == 0
        assert len(result.assembly.terms) == 4
        assert result.solve is not None
        assert result.solve.converged is True
        assert result.solve.normalization == pytest.approx(1.0)
        assert result.solve.populations.tolist() == pytest.approx([1.0, 0.0])
        assert result.full_element_direct_solve_ready is True

        outputs = write_element_equilibrium_products(result, tmp_path / "products")
        assert outputs["basis_csv"].is_file()
        assert outputs["terms_csv"].is_file()
        assert outputs["matrix_npz"].is_file()
        assert outputs["json"].is_file()
    finally:
        built.atomic_state.close()


def test_msolvelucy_recovers_two_level_bidirectional_balance():
    basis = ElementCompactBasis(
        element_z=1,
        min_ion_stage=1,
        max_ion_stage=1,
        blocks=[],
        rows=[
            ElementBasisRow(1, superlevel=1, ion_counter=1),
            ElementBasisRow(2, superlevel=2, ion_counter=1),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=1,
        normalization_row=2,
    )
    up, down = 2.0, 8.0
    terms = [
        MatrixTerm(1, 10, 50, 4, 1, 1, "forward_offdiag", 2, 1, up, down, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(2, 10, 50, 4, 1, 1, "reverse_offdiag", 1, 2, down, up, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(3, 10, 50, 4, 1, 1, "forward_diag_loss", 1, 1, -up, -up, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(4, 10, 50, 4, 1, 1, "reverse_diag_loss", 2, 2, -down, -down, 0, 0, 1, 2, 1, 2, "evaluated"),
    ]
    matrix = np.asarray([[-up, down], [up, -down]], dtype=float)
    assembly = ElementMatrixAssembly(
        basis=basis,
        initial_populations=np.asarray([0.0, 0.5, 0.5]),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=np.asarray([[ -up, down], [1.0, 1.0]], dtype=float),
        rhs=np.asarray([0.0, 1.0], dtype=float),
        heating_matrix=np.zeros((2, 2)),
        heating_matrix2=np.zeros((2, 2)),
        ion_summaries=[],
        blocked_records=[],
        record_results=[],
        n_records_seen=1,
        n_records_evaluated=1,
        n_records_source_noop=0,
        n_records_skipped=0,
        n_records_blocked=0,
        n_unmapped_endpoints=0,
        strict_assembly_ready=True,
    )
    context = ElementEquilibriumContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0,
        electron_fraction_xee=1.0,
        min_ion_stage=1,
        max_ion_stage=1,
    )
    solved = msolvelucy(assembly, context)
    assert solved.converged
    assert solved.populations == pytest.approx([0.8, 0.2], rel=1e-10)
    assert solved.normalization_error < 1e-12
    assert solved.n_negative_populations == 0


def test_element_equilibrium_cli_and_public_api(tmp_path: Path, capsys):
    import xstar_atomic as xa
    from xstar_atomic.source_port_element_cli import main

    atdb = tmp_path / "atdb.fits"
    _write_ucalc_atdb(atdb)
    out = tmp_path / "out"
    rc = main(
        [
            "--atdb", str(atdb),
            "--element-z", "1",
            "--min-ion-stage", "1",
            "--max-ion-stage", "1",
            "--temperature-k", "10000",
            "--hydrogen-density-cm3", "1",
            "--electron-fraction-xee", "1",
            "--assume-optically-thin",
            "--out-dir", str(out),
            "--print-summary",
        ]
    )
    assert rc == 0
    text = capsys.readouterr().out
    assert "full_element_direct_solve_ready=True" in text
    assert (out / "xstar_element_equilibrium_summary.json").is_file()
    assert xa.__version__ == "0.4.7"
    assert callable(xa.solve_element_statistical_equilibrium)
    assert "solve_element_statistical_equilibrium" in xa.__all__


def test_leqt2f_translated_lu_and_refinement_solve_known_system():
    matrix = np.asarray([[3.0, 2.0], [1.0, 4.0]], dtype=float)
    rhs = np.asarray([7.0, 9.0], dtype=float)
    result = leqt2f(matrix, rhs, clamp_source_range=False)
    assert result.solution == pytest.approx([1.0, 2.0], rel=1e-13)
    assert result.max_scaled_residual < 1e-13


def test_leqt2f_reports_source_singular_rows_explicitly():
    with pytest.raises(XSTARLinearAlgebraError):
        leqt2f(np.zeros((2, 2)), np.asarray([0.0, 1.0]))
