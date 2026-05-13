import math
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_detail_phint53_bremsa_variants,
    write_type53_detail_phint53_bremsa_variants_audit,
)


def test_type53_bremsa_variants_identifies_matching_variant(tmp_path: Path):
    # Cross section is constant and equal to 1 cm^2 between threshold=10 eV
    # and 11 eV.  The phint53 photo integral is therefore integral brem/E dE.
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
            # type-53 raw pairs are energy above threshold [Ry], sigma [Mb].
            # 1e18 Mb is decoded by the audit as 1 cm^2.
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
    }
    audit = audit_type53_detail_phint53_bremsa_variants(
        ion="O VII",
        matrix_rows=matrix_rows,
        adjacent_rows=adjacent_rows,
        global_rows=global_rows,
        continuum_variants=variants,
        triplet_only=True,
    )
    summary = audit["summary"]
    assert summary["n_bremsa_variants"] == 2
    assert summary["best_bremsa_variant_without_free_scale"] == "matches"
    assert abs(summary["best_variant_median_matrix_over_detail"] - 1.0) < 5.0e-3
    paths = write_type53_detail_phint53_bremsa_variants_audit(audit, tmp_path / "out")
    assert Path(paths["variant_summary_csv"]).exists()
    assert Path(paths["records_csv"]).exists()
    assert Path(paths["markdown"]).exists()
