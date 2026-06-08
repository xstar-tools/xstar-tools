from __future__ import annotations

from pathlib import Path

from xstar_tools.xstar.performance import summarize_rate_payload_four_family_product


def test_v06402_candidate_summary_preserves_conditional_order_contract() -> None:
    evaluation = {
        "schema_version": "0.6.40.2",
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
        "order_preserving_commit_strategy": "flush_pending_type51_before_fast_record_when_nonempty",
        "order_preserving_commit_verified": True,
        "status": "TYPE51_ORDER_RESTORATION_HOTFIX_CANDIDATE_EXACT",
        "type51_order_barrier_count": 4,
        "type51_order_barrier_flushes": 1,
        "type51_order_barrier_pending_records": 2,
        "type51_order_barrier_terms": 8,
        "ordered_stream_exact": True,
        "all_matrix_checkpoints_exact": True,
        "solver_input_checkpoint_exact": True,
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["status"] == "TYPE51_ORDER_RESTORATION_HOTFIX_CANDIDATE_EXACT"
    assert summary["product_activations"] == 1
    assert summary["order_preserving_commit"] is True
    assert summary["order_preserving_commit_verified"] is True
    assert summary["type51_order_barrier_count"] == 4
    assert summary["type51_order_barrier_flushes"] == 1
    assert summary["type51_order_barrier_pending_records"] == 2
    assert summary["type51_order_barrier_terms"] == 8


def test_v06402_ordered_stream_divergence_is_aggregated() -> None:
    divergence = {
        "kind": "ordered_stream",
        "evaluation_index": 1,
        "stream_position": 17,
        "accepted_term": {"record": 40380, "term_index": 17},
        "candidate_term": {"record": 40756, "term_index": 17},
    }
    evaluation = {
        "schema_version": "0.6.40.2",
        "accepted_gate": True,
        "product_candidate": True,
        "product_promoted": False,
        "seed_elision_differential": False,
        "active": False,
        "live_matrix_commit": False,
        "whole_evaluation_fallback": True,
        "verification_enabled": True,
        "full_reverse_verification": True,
        "order_preserving_commit": True,
        "status": "FALLBACK_ACCEPTED_PATH",
        "first_ordered_stream_divergence": divergence,
        "fallback_provenance": divergence,
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["status"] == "FALLBACK"
    assert summary["first_ordered_stream_divergences"] == [divergence]
    assert summary["fallback_provenance_samples"] == [divergence]


def test_v06402_live_path_contains_conditional_flush_boundary() -> None:
    source = Path(__file__).parents[1] / "src/xstar_tools/xstar/element_equilibrium.py"
    text = source.read_text()
    assert "flush_pending_type51_before_fast_record_when_nonempty" in text
    assert "if _pending_before > 0:" in text
    assert "_timed_flush_pending_mg_rates_matrix()" in text
