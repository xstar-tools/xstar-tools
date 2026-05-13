import math

import numpy as np

from xstar_atomic.xstar_matrix_parity import audit_type53_detail_phint53_bremsa_variants


def test_type53_bremsa_variants_v03166_works_without_numpy_trapz(monkeypatch):
    """Regression for NumPy builds exposing trapezoid but not trapz."""
    monkeypatch.delattr(np, "trapz", raising=False)
    base_rate = math.log(11.0 / 10.0)
    audit = audit_type53_detail_phint53_bremsa_variants(
        ion="O VII",
        matrix_rows=[
            {
                "data_type": "53",
                "full_global_component": "photoionization",
                "record": "1",
                "bound_global_index": "1",
                "continuum_or_parent_global_index": "2",
                "full_global_rate_s^-1": str(2.0 * base_rate),
                "triplet_component": "f",
            }
        ],
        adjacent_rows=[
            {
                "data_type": "53",
                "record": "1",
                "type53_raw_reals_full": f"[0.0, 1.0e18, {1.0/13.605692}, 1.0e18]",
            }
        ],
        global_rows=[
            {
                "global_index": "1",
                "level_label": "synthetic_triplet",
                "binding_from_continuum_eV": "10.0",
                "is_triplet_upper": "true",
                "triplet_component": "f",
            },
            {"global_index": "2", "level_label": "continuum"},
        ],
        continuum_variants={"matches": ([10.0, 11.0], [2.0, 2.0])},
        triplet_only=True,
        profile=True,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.166"
    assert summary["integration_engine"] == "vectorized_numpy_record_precompute_v03166"
    assert summary["best_bremsa_variant_without_free_scale"] == "matches"
    assert summary["n_evaluated_variant_record_pairs"] == 1


def test_type53_bremsa_variants_v03166_local_trapezoid_fallback(monkeypatch):
    """The audit also has a local fallback if trapezoid is unavailable."""
    monkeypatch.delattr(np, "trapz", raising=False)
    monkeypatch.delattr(np, "trapezoid", raising=False)
    base_rate = math.log(11.0 / 10.0)
    audit = audit_type53_detail_phint53_bremsa_variants(
        ion="O VII",
        matrix_rows=[
            {
                "data_type": "53",
                "full_global_component": "photoionization",
                "record": "1",
                "bound_global_index": "1",
                "continuum_or_parent_global_index": "2",
                "full_global_rate_s^-1": str(2.0 * base_rate),
                "triplet_component": "f",
            }
        ],
        adjacent_rows=[
            {
                "data_type": "53",
                "record": "1",
                "type53_raw_reals_full": f"[0.0, 1.0e18, {1.0/13.605692}, 1.0e18]",
            }
        ],
        global_rows=[
            {
                "global_index": "1",
                "level_label": "synthetic_triplet",
                "binding_from_continuum_eV": "10.0",
                "is_triplet_upper": "true",
                "triplet_component": "f",
            },
            {"global_index": "2", "level_label": "continuum"},
        ],
        continuum_variants={"matches": ([10.0, 11.0], [2.0, 2.0])},
        triplet_only=True,
        profile=True,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.166"
    assert summary["best_bremsa_variant_without_free_scale"] == "matches"
