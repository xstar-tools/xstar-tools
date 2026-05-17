#!/usr/bin/env python3
"""Audit exact live-radiation XSTAR type-53 rates on the priority subsystem."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_type53_live_native_parity import (
    build_type53_live_native_parity_audit,
    write_type53_live_native_parity_audit,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--priority-matrix-closure-audit", required=True)
    p.add_argument("--live-rate-grid-probe-csv", required=True)
    p.add_argument("--live-rate-grid-state", default="last", help="first, last, or capture_index")
    p.add_argument("--live-density-field-semantics", choices=["xee", "electron_density", "ignore"], default="electron_density")
    p.add_argument("--atdb", required=True)
    p.add_argument("--index-cache")
    p.add_argument("--rebuild-index-cache", action="store_true")
    p.add_argument("--lfast", type=int, default=2)
    p.add_argument("--relative-rate-tolerance", type=float, default=5.0e-5)
    p.add_argument("--live-context-relative-tolerance", type=float, default=5.0e-5)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    a = p.parse_args()
    audit = build_type53_live_native_parity_audit(
        priority_matrix_closure_audit=a.priority_matrix_closure_audit,
        live_rate_grid_probe_csv=a.live_rate_grid_probe_csv,
        live_rate_grid_state=a.live_rate_grid_state,
        live_density_field_semantics=a.live_density_field_semantics,
        atdb_fits=a.atdb,
        relative_rate_tolerance=a.relative_rate_tolerance,
        live_context_relative_tolerance=a.live_context_relative_tolerance,
        lfast=a.lfast,
        index_cache_path=a.index_cache,
        rebuild_index_cache=a.rebuild_index_cache,
    )
    paths = write_type53_live_native_parity_audit(a.out_dir, audit)
    if a.print_summary:
        print("XSTAR exact live-radiation native type-53 parity audit")
        print("------------------------------------------------------")
        s = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "selected_xstar_ipmat2_indices",
            "relative_rate_tolerance", "live_context_relative_tolerance",
            "atdb_fits", "atdb_status", "index_cache_status",
            "live_rate_grid_probe_csv", "live_rate_grid_state_selector",
            "live_rate_grid_state_selection_status", "live_density_field_semantics",
            "live_state_context_ready", "type53_decoder_context_ready", "lfast",
            "n_selected_type53_ucalc_records", "n_type53_records_decoded",
            "n_type53_records_nlevp_inferred_from_ucalc_endpoint",
            "n_type53_records_nlevp_fallback_to_atdb_max",
            "n_type53_records_nlevp_inference_inconsistent",
            "n_type53_records_missing_continuum_row_at_xstar_nlevp",
            "n_type53_records_rate_parity_pass",
            "n_type53_records_heating_cooling_parity_pass",
            "n_type53_compact_matrix_terms", "n_type53_compact_matrix_terms_match",
            "n_type53_selected_row_terms", "n_type53_selected_internal_terms",
            "n_type53_fixed_external_terms", "n_type53_external_row_out_of_scope_terms",
            "native_type53_exact_live_rate_parity_ready",
            "native_type53_heating_cooling_parity_ready",
            "native_type53_opacity_rrc_parity_ready",
            "native_type53_compact_matrix_parity_ready",
            "native_type53_external_rhs_parity_ready",
            "native_type53_selected_system_parity_ready",
            "type53_scale44_resolved_by_exact_live_state",
            "empirical_type53_scale_applied", "dominant_next_target",
        ]:
            print(f"{key}={s.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
