import math
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_detail_phint53_bremsa_variants,
    write_type53_detail_phint53_bremsa_variants_audit,
)


def _synthetic_inputs():
    base_rate = math.log(11.0 / 10.0)
    matrix_rows = [
        {
            "data_type": "53",
            "full_global_component": "photoionization",
            "record": "1",
            "bound_global_index": "1",
            "continuum_or_parent_global_index": "2",
            "full_global_rate_s^-1": str(2.0 * base_rate),
            "triplet_component": "f",
        }
    ]
    adjacent_rows = [
        {
            "data_type": "53",
            "record": "1",
            "type53_raw_reals_full": f"[0.0, 1.0e18, {1.0/13.605692}, 1.0e18]",
        }
    ]
    global_rows = [
        {
            "global_index": "1",
            "level_label": "synthetic_triplet",
            "binding_from_continuum_eV": "10.0",
            "is_triplet_upper": "true",
            "triplet_component": "f",
        },
        {"global_index": "2", "level_label": "continuum"},
    ]
    variants = {
        "too_low": ([10.0, 11.0], [1.0, 1.0]),
        "matches": ([10.0, 11.0], [2.0, 2.0]),
        "too_high": ([10.0, 11.0], [4.0, 4.0]),
    }
    return matrix_rows, adjacent_rows, global_rows, variants


def test_type53_bremsa_variants_v03165_filters_variants_and_profiles(tmp_path: Path):
    matrix_rows, adjacent_rows, global_rows, variants = _synthetic_inputs()
    audit = audit_type53_detail_phint53_bremsa_variants(
        ion="O VII",
        matrix_rows=matrix_rows,
        adjacent_rows=adjacent_rows,
        global_rows=global_rows,
        continuum_variants=variants,
        triplet_only=True,
        variant_names=["matches", "missing"],
        profile=True,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.165"
    assert summary["n_bremsa_variants"] == 1
    assert summary["requested_bremsa_variants_missing"] == ["missing"]
    assert summary["best_bremsa_variant_without_free_scale"] == "matches"
    assert summary["integration_engine"] == "vectorized_numpy_record_precompute_v03165"
    assert summary["n_vectorized_record_batches"] == 1
    assert summary["n_evaluated_variant_record_pairs"] == 1
    assert summary["integration_seconds"] >= 0.0
    paths = write_type53_detail_phint53_bremsa_variants_audit(
        audit,
        tmp_path / "out",
        write_records_csv=False,
    )
    assert Path(paths["variant_summary_csv"]).exists()
    assert "records_csv" not in paths
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
