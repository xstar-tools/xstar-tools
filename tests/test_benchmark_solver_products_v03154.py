from pathlib import Path

from xstar_atomic.benchmark import write_solver_products_from_result
from xstar_atomic.xstar_detail import find_matrix_terms_csv_from_benchmark


def test_write_solver_products_preserves_full_global_matrix_terms(tmp_path: Path):
    result = {
        "summary": {"status": "ok"},
        "full_global_matrix_terms": [
            {"record": 1, "rate_s^-1": 2.0, "signed_rate_s^-1": 2.0},
            {"record": 1, "rate_s^-1": 2.0, "signed_rate_s^-1": -2.0},
        ],
    }
    paths = write_solver_products_from_result(result, tmp_path)
    matrix = Path(paths["full_global_matrix_terms"])
    assert matrix.name == "xstar_like_element_solver_full_global_matrix_terms.csv"
    assert matrix.exists()
    assert Path(paths["manifest"]).exists()


def test_find_matrix_terms_from_benchmark_comparison_csv(tmp_path: Path):
    matrix = tmp_path / "solver_products" / "o_vii" / "xstar_like_element_solver_full_global_matrix_terms.csv"
    matrix.parent.mkdir(parents=True)
    matrix.write_text("record,rate_s^-1\n1,2\n", encoding="utf-8")
    comp = tmp_path / "xstar_local_reproduction_suite_comparisons.csv"
    comp.write_text(
        "ion,solver_full_global_matrix_terms_csv\n"
        f"O VII,{matrix}\n",
        encoding="utf-8",
    )
    found = find_matrix_terms_csv_from_benchmark(tmp_path, ion="O VII")
    assert found == matrix
