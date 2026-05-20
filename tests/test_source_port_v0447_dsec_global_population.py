from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    DsecMutableRuntimeState,
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    ElementIonBlock,
    ElementMatrixAssembly,
    FixedStateElementRequest,
    MatrixTerm,
    map_global_populations_to_compact_basis,
    msolvelucy,
)


def _two_ion_basis() -> ElementCompactBasis:
    blocks = [
        ElementIonBlock(1, 101, 8, 3, 3, 1, 3, 201, ion_counter=3),
        ElementIonBlock(2, 102, 8, 4, 2, 3, 4, 202, ion_counter=4),
    ]
    rows = [
        ElementBasisRow(1, superlevel=1, ion_counter=3, roles=[{"ion_stage": 3, "local_level": 1}]),
        ElementBasisRow(2, superlevel=2, ion_counter=3, roles=[{"ion_stage": 3, "local_level": 2}]),
        ElementBasisRow(
            3,
            superlevel=3,
            ion_counter=4,
            roles=[
                {"ion_stage": 3, "local_level": 3},
                {"ion_stage": 4, "local_level": 1},
            ],
        ),
        ElementBasisRow(4, superlevel=4, ion_counter=4, roles=[{"ion_stage": 4, "local_level": 2}]),
    ]
    return ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=4,
        blocks=blocks,
        rows=rows,
        n_rows=4,
        n_superlevels=4,
        n_ions=8,
        normalization_row=4,
    )


def test_global_xilevg_mapping_overwrites_shared_alias_in_source_order() -> None:
    basis = _two_ion_basis()
    global_populations = {
        (8, 3, 1): 0.1,
        (8, 3, 2): 0.2,
        (8, 3, 3): 0.3,
        (8, 4, 1): 0.4,
        (8, 4, 2): 0.5,
    }
    mapped = map_global_populations_to_compact_basis(basis, global_populations)
    assert mapped.tolist() == pytest.approx([0.0, 0.1, 0.2, 0.4, 0.5])


def test_empty_global_xilevg_maps_to_exact_zero_for_first_dsec_call() -> None:
    mapped = map_global_populations_to_compact_basis(_two_ion_basis(), {})
    assert np.array_equal(mapped, np.zeros(5))


def test_msolvelucy_accepts_source_valid_zero_population_seed() -> None:
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
        initial_populations=np.asarray([0.0, 0.0, 0.0]),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=np.asarray([[-up, down], [1.0, 1.0]], dtype=float),
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
    assert solved.populations == pytest.approx([0.8, 0.2], rel=1.0e-10)


def test_dsec_global_workspace_supersedes_stale_compact_seed() -> None:
    request = FixedStateElementRequest(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=8,
        initial_populations=np.ones(607),
        initial_population_source="converged_call73_compact_seed",
    )
    state = DsecMutableRuntimeState(
        temperature_t4=100.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        element_requests=(request,),
        global_level_populations={},
    )
    next_request = state.requests_for_next_call()[0]
    assert next_request.initial_populations is None
    assert next_request.initial_global_populations == {}
    assert next_request.initial_population_source == "xstar_init_zero_global_xilevg"


def test_dsec_commit_merges_global_workspace_and_preserves_stale_inactive_rows() -> None:
    state = DsecMutableRuntimeState(
        temperature_t4=1.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        global_level_populations={(8, 3, 9): 0.25},
    )
    result = SimpleNamespace(
        temperature_k=2.0e4,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=1.0e8,
        element_results=(),
        xilevg={(8, 4, 1): 0.75},
        ion_fractions={}, rrrt={}, pirt={}, htt={}, cll={}, htt2={}, cll2={},
        rnisg={}, bilevg={}, gammag={}, alphag={}, stotg={}, atotg={}, xtotg={},
        leveltemp_workspace=None,
        leveltemp_owner_by_column={},
        continuum=SimpleNamespace(opakc=None, brcems=None),
    )
    state.commit_calc_hmc_all(result)
    assert state.global_level_populations == {(8, 3, 9): 0.25, (8, 4, 1): 0.75}
    assert state.temperature_t4 == 2.0
    assert state.electron_fraction_xee == 1.2


def test_physical_cli_rejects_later_dsec_call_without_incoming_global_state(tmp_path) -> None:
    from xstar_atomic.source_port_dsec_physical_cli import main

    with pytest.raises(ValueError, match="bounded to dsec_call_id=1"):
        main(
            [
                "--atdb", str(tmp_path / "missing.fits"),
                "--live-rate-grid-probe-csv", str(tmp_path / "missing.csv"),
                "--xstar-calc-hmc-probe-dir", str(tmp_path),
                "--oxygen-call73-regression-dir", str(tmp_path),
                "--xstar-dsec-trajectory", str(tmp_path / "missing_dsec.csv"),
                "--xstar-dsec-call-id", "3",
                "--out-dir", str(tmp_path / "out"),
            ]
        )
