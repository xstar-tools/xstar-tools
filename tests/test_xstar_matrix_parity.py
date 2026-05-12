import csv
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import audit_local_matrix_parity, find_solver_product_paths


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_audit_local_matrix_parity_groups_type50_from_source_method(tmp_path):
    matrix = tmp_path / "matrix.csv"
    solve = tmp_path / "solve.csv"
    type50 = tmp_path / "type50.csv"
    _write_csv(matrix, [
        {
            "matrix_row_global_index": "10", "matrix_col_global_index": "1",
            "full_global_signed_rate_s^-1": "5.0", "rate_s^-1": "5.0",
            "source_method": "data_type_50_rate_type_4", "matrix_role": "bound_bound_gain_to_destination",
            "record": "101", "ucalc_context_status": "evaluated_xstar_detail_lines",
        },
        {
            "matrix_row_global_index": "10", "matrix_col_global_index": "10",
            "full_global_signed_rate_s^-1": "-5.0", "rate_s^-1": "5.0",
            "source_method": "data_type_50_rate_type_4", "matrix_role": "bound_bound_loss_from_source",
            "record": "101", "ucalc_context_status": "evaluated_xstar_detail_lines",
        },
        {
            "matrix_row_global_index": "11", "matrix_col_global_index": "1",
            "full_global_signed_rate_s^-1": "2.0", "rate_s^-1": "2.0",
            "data_type": "63", "source_format": "bautista_nl_algorithm_type63",
            "matrix_role": "bound_bound_gain_to_destination", "record": "201", "eval_method": "ucalc_type63",
        },
    ])
    _write_csv(solve, [
        {"row_kind": "summary", "f_fraction": "0.1", "i_fraction": "0.2", "r_fraction": "0.7"},
        {"row_kind": "population", "global_index": "10", "triplet_component": "f", "is_triplet_upper": "True", "level_label": "f"},
        {"row_kind": "population", "global_index": "11", "triplet_component": "r", "is_triplet_upper": "True", "level_label": "r"},
    ])
    _write_csv(type50, [
        {"matrix_residual_classification": "matrix_matches_ucalc_rate"},
    ])
    result = audit_local_matrix_parity(matrix_terms_csv=matrix, normalized_solve_csv=solve, ion="O VII", type50_audit_csv=type50)
    families = {row["data_type"]: row for row in result["family_rows"]}
    assert families["50"]["parity_status"] == "detail_rate_and_matrix_parity_verified_for_audited_type50_lines"
    assert families["50"]["n_terms_touching_f"] == 2
    assert families["63"]["n_terms_touching_r"] == 1
    assert result["overall"]["n_triplet_upper_levels"] == 2


def test_find_solver_product_paths_handles_archived_relative_paths(tmp_path):
    root = tmp_path / "bench"
    prod = root / "solver_products" / "o_vii"
    matrix = prod / "xstar_like_element_solver_full_global_matrix_terms.csv"
    solve = prod / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv"
    matrix.parent.mkdir(parents=True)
    matrix.write_text("a\n", encoding="utf-8")
    solve.write_text("a\n", encoding="utf-8")
    comp = root / "xstar_local_reproduction_suite_comparisons.csv"
    _write_csv(comp, [{
        "ion": "O VII",
        "solver_full_global_matrix_terms_csv": "bench/solver_products/o_vii/xstar_like_element_solver_full_global_matrix_terms.csv",
        "solver_full_global_normalized_solve_comparison_csv": "bench/solver_products/o_vii/xstar_like_element_solver_full_global_normalized_solve_comparison.csv",
    }])
    found = find_solver_product_paths(root, ion="O VII")
    assert found["matrix_terms_csv"] == matrix
    assert found["normalized_solve_csv"] == solve
