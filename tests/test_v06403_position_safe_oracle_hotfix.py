from __future__ import annotations

from pathlib import Path

from xstar_tools.xstar.element_equilibrium import _reverse_oracle_terms_by_position
from xstar_tools.xstar.performance import summarize_rate_payload_four_family_product


def test_position_safe_oracle_ignores_duplicate_term_indices() -> None:
    # The strings stand in for MatrixTerm objects; the helper intentionally
    # keys only on stable list position and never inspects term_index.
    candidate = ["type7-index-17", "type50-index-17", "unchanged"]
    accepted = {1: "accepted-type50-index-17"}
    assert _reverse_oracle_terms_by_position(candidate, accepted) == [
        "type7-index-17", "accepted-type50-index-17", "unchanged"
    ]


def test_v06403_summary_reports_position_safe_alias_avoidance() -> None:
    evaluation = {
        "schema_version": "0.6.40.3",
        "accepted_gate": True,
        "product_candidate": True,
        "product_promoted": False,
        "seed_elision_differential": False,
        "active": True,
        "live_matrix_commit": True,
        "whole_evaluation_fallback": True,
        "python_seed_path_retained": False,
        "verification_enabled": True,
        "full_reverse_verification": True,
        "order_preserving_commit": True,
        "order_preserving_commit_verified": True,
        "status": "POSITION_SAFE_ORACLE_HOTFIX_CANDIDATE_EXACT",
        "reverse_oracle_mapping_strategy": "stable_term_list_position",
        "reverse_oracle_position_records": 8,
        "reverse_oracle_duplicate_term_index_count": 3,
        "reverse_oracle_term_index_aliases_avoided": 2,
        "ordered_stream_exact": True,
        "all_matrix_checkpoints_exact": True,
        "solver_input_checkpoint_exact": True,
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["status"] == "POSITION_SAFE_ORACLE_HOTFIX_CANDIDATE_EXACT"
    assert summary["reverse_oracle_mapping_strategy"] == "stable_term_list_position"
    assert summary["reverse_oracle_position_records"] == 8
    assert summary["reverse_oracle_duplicate_term_index_count"] == 3
    assert summary["reverse_oracle_term_index_aliases_avoided"] == 2


def test_v06403_candidate_disables_nonexact_upstream_type4_product() -> None:
    runner = (
        Path(__file__).parents[1]
        / "run_v0403_xstar_tools_position_safe_oracle_hotfix_product_candidate.sh"
    ).read_text()
    assert "XSTAR_ATOMIC_EMISSIVITY_UPSTREAM_TYPE4_PRODUCT_CPP=0" in runner
    assert "XSTAR_ATOMIC_EMISSIVITY_MG_TYPE4_PRODUCT_CPP=0" in runner
    assert "XSTAR_ATOMIC_EMISSIVITY_BINEMIS_PRODUCT_CPP=1" in runner
