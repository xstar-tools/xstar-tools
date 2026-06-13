from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import xstar_tools

from xstar_tools.xstar import type53_row46_dsec_runtime_contract_audit as audit


def _bundle() -> Path:
    return Path(__file__).resolve().parents[1] / audit.BUNDLE


def test_release_is_pinned() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.20"


def test_embedded_oracle_verifies() -> None:
    result = audit.verify_oracle(_bundle())
    assert result['result'] == 'ACCEPT'
    assert result['records'] == 44
    assert result['answers'] == 264
    assert result['matrix_terms'] == 176
    assert result['source_order_contribution_exact_columns'] == 78


def test_oracle_inventory_is_one_coupled_manifold() -> None:
    records = audit.read_csv(_bundle() / audit.RECORDS_NAME)
    terms = audit.read_csv(_bundle() / audit.TERMS_NAME)
    keys = {(int(row['source_position']), int(row['record'])) for row in records}
    assert len(keys) == 44
    assert {int(row['data_type']) for row in records} == {53}
    assert {int(row['rate_type']) for row in records} == {7}
    counts = {key: 0 for key in keys}
    for row in terms:
        counts[(int(row['source_position']), int(row['record']))] += 1
    assert set(counts.values()) == {4}


def test_substitution_replaces_all_four_channels() -> None:
    dense = np.zeros((78, 78), dtype=np.float64)
    heat = np.zeros_like(dense)
    heat2 = np.zeros_like(dense)
    candidate = []
    oracle = {}
    role_pairs = [
        ('forward_gain', 'forward_offdiag', 46, 1),
        ('reverse_gain', 'reverse_offdiag', 1, 46),
        ('forward_diag_loss', 'forward_diag_loss', 1, 1),
        ('reverse_diag_loss', 'reverse_diag_loss', 46, 46),
    ]
    for index, (native_role, oracle_role, row, column) in enumerate(role_pairs, 1):
        candidate.append({
            'contribution_source_position': '100', 'record': '200',
            'role': native_role, 'compact_row': str(row), 'compact_column': str(column),
            'aj1': str(index), 'cj': str(index + 10), 'cj2': str(index + 20),
        })
        oracle[(100, 200, oracle_role)] = {
            'aj1': str(index + 0.5), 'cj': str(index + 10.5), 'cj2': str(index + 20.5),
        }
        dense[row - 1, column - 1] = index
        heat[row - 1, column - 1] = index + 10
        heat2[row - 1, column - 1] = index + 20
    out_dense, out_heat, out_heat2, replaced = audit._substitute_manifold(
        dense, heat, heat2, candidate, oracle
    )
    assert replaced == 4
    for index, (_, _, row, column) in enumerate(role_pairs, 1):
        assert out_dense[row - 1, column - 1] == index + 0.5
        assert out_heat[row - 1, column - 1] == index + 10.5
        assert out_heat2[row - 1, column - 1] == index + 20.5


def test_frozen_source_contribution_reconstructs_ieee_exactly() -> None:
    terms = audit.read_csv(_bundle() / audit.TERMS_NAME)
    frozen = audit.read_csv(_bundle() / audit.CONTRIBUTION_NAME)
    reconstructed = np.zeros(78, dtype=np.float64)
    for row in sorted(terms, key=lambda item: int(item['source_order_index'])):
        if int(row['row']) == 46:
            reconstructed[int(row['column']) - 1] += float(row['aj1'])
    expected = np.asarray([float(row['dense_contribution']) for row in frozen])
    assert all(audit._bits(a) == audit._bits(b) for a, b in zip(reconstructed, expected))
