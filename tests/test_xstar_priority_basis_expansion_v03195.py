from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from xstar_atomic.xstar_priority_basis_expansion import (
    build_priority_basis_expansion,
    write_priority_basis_expansion,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root: Path) -> None:
    scaffold = [
        {
            "xstar_ipmat2_index": 1,
            "basis_row_status": "existing_python_row",
            "proposed_primary_python_global_index": 0,
            "mapped_python_global_indices": "0",
            "xstar_after_population": 0.90,
            "row_kinds": "ion_population_row",
            "sharing_class": "single_role",
            "role_count": 1,
            "primary_nionp_current": 7,
            "primary_local_level_index": 1,
        },
        {
            "xstar_ipmat2_index": 2,
            "basis_row_status": "missing_python_placeholder",
            "proposed_primary_python_global_index": 2,
            "missing_priority_rank": 1,
            "xstar_after_population": 0.08,
            "row_kinds": "ion_parent_continuum_link;ion_population_row",
            "sharing_class": "parent_continuum_shared_with_next_ion_population",
            "role_count": 2,
            "primary_nionp_current": 6,
            "primary_local_level_index": 1,
            "population_role_nionp": 6,
            "population_role_local_level_index": 1,
            "parent_role_nionp": 5,
            "parent_role_local_level_index": 10,
        },
        {
            "xstar_ipmat2_index": 3,
            "basis_row_status": "missing_python_placeholder",
            "proposed_primary_python_global_index": 3,
            "missing_priority_rank": 2,
            "xstar_after_population": 0.019,
            "row_kinds": "ion_population_row",
            "sharing_class": "single_role",
            "role_count": 1,
            "primary_nionp_current": 5,
            "primary_local_level_index": 2,
        },
        {
            "xstar_ipmat2_index": 4,
            "basis_row_status": "missing_python_placeholder",
            "proposed_primary_python_global_index": 4,
            "missing_priority_rank": 3,
            "xstar_after_population": 0.001,
            "row_kinds": "ion_population_row",
            "sharing_class": "single_role",
            "role_count": 1,
            "primary_nionp_current": 5,
            "primary_local_level_index": 3,
        },
    ]
    priority = [
        {
            "missing_priority_rank": 1,
            "xstar_ipmat2_index": 2,
            "xstar_after_population": 0.08,
            "primary_nionp_current": 6,
            "primary_local_level_index": 1,
            "row_kinds": scaffold[1]["row_kinds"],
            "sharing_class": scaffold[1]["sharing_class"],
            "proposed_python_global_index": 2,
        },
        {
            "missing_priority_rank": 2,
            "xstar_ipmat2_index": 3,
            "xstar_after_population": 0.019,
            "primary_nionp_current": 5,
            "primary_local_level_index": 2,
            "row_kinds": scaffold[2]["row_kinds"],
            "sharing_class": scaffold[2]["sharing_class"],
            "proposed_python_global_index": 3,
        },
        {
            "missing_priority_rank": 3,
            "xstar_ipmat2_index": 4,
            "xstar_after_population": 0.001,
            "primary_nionp_current": 5,
            "primary_local_level_index": 3,
            "row_kinds": scaffold[3]["row_kinds"],
            "sharing_class": scaffold[3]["sharing_class"],
            "proposed_python_global_index": 4,
        },
    ]
    blocks = [
        {"nionp_current": 5, "ml_ion": 50, "klion": 5, "jkk_ion": 20},
        {"nionp_current": 6, "ml_ion": 60, "klion": 6, "jkk_ion": 21},
    ]
    _write_csv(root / "xstar_full_element_basis_scaffold.csv", scaffold)
    _write_csv(root / "xstar_full_element_basis_scaffold_missing_priority.csv", priority)
    _write_csv(root / "xstar_full_element_basis_scaffold_ion_block_summary.csv", blocks)
    (root / "xstar_full_element_basis_scaffold.json").write_text(
        json.dumps({
            "summary": {
                "ion": "O VII",
                "selected_basis_solve_call_id": 219,
                "current_population_coverage": 0.90,
                "n_existing_python_population_rows": 1,
                "n_unique_xstar_rows_represented_by_python": 1,
            }
        }),
        encoding="utf-8",
    )


def test_population_ranked_activation_preserves_alias(tmp_path: Path) -> None:
    _fixture(tmp_path)
    audit = build_priority_basis_expansion(
        full_element_basis_scaffold=tmp_path,
        target_population_coverage=0.999,
    )
    summary = audit["summary"]
    assert summary["n_selected_missing_rows"] == 2
    assert summary["selected_xstar_ipmat2_indices"] == "2;3"
    assert summary["achieved_population_coverage"] == pytest.approx(0.999)
    assert summary["n_selected_shared_parent_rows"] == 1
    assert summary["n_active_unique_compact_basis_rows"] == 3
    assert summary["priority_basis_expansion_ready"] is True
    assert summary["native_priority_subset_matrix_closure_ready"] is False
    alias = next(row for row in audit["alias_rows"] if row["xstar_ipmat2_index"] == 2)
    assert alias["active_in_priority_basis"] is True
    assert alias["alias_policy"] == "single_compact_unknown_multiple_physical_roles"


def test_explicit_selection_and_writer(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _fixture(source)
    audit = build_priority_basis_expansion(
        full_element_basis_scaffold=source,
        explicit_xstar_ipmat2_indices=[4],
        target_population_coverage=0.95,
    )
    assert audit["summary"]["selection_mode"] == "explicit-ipmat2"
    assert audit["summary"]["selected_xstar_ipmat2_indices"] == "4"
    assert audit["summary"]["target_population_coverage_met"] is False
    paths = write_priority_basis_expansion(tmp_path / "out", audit)
    for path in paths.values():
        assert Path(path).exists()


def test_rejects_nonmissing_explicit_row(tmp_path: Path) -> None:
    _fixture(tmp_path)
    with pytest.raises(ValueError, match="not missing scaffold rows"):
        build_priority_basis_expansion(
            full_element_basis_scaffold=tmp_path,
            explicit_xstar_ipmat2_indices=[1],
        )
