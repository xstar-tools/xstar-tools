# 0.6.48.9.5.1 legacy Python cleanup

0.6.48.9.5 is frozen as the accepted prepared Type49/53 production/science baseline. 0.6.48.9.5.1 changes packaging and source organization only; it does not intentionally change XSTAR science or standalone C++ performance.

## Removed from the production Python namespace

- 99 directly identified version-stamped or Mg-named top-level `src/xstar_tools/xstar/*.py` modules.
- 13 additional non-versioned modules whose only dependency path was through that retired audit/capture component.
- Total retired production-namespace modules: **112**.
- Retired tests tied directly to those modules: **68**.
- Retired console scripts: **13**.
- Removed checked-in `src/xstar_tools.egg-info/` generated metadata.
- The Mg XI compiled benchmark and all 9.5 C++ qualification/performance tooling are retained.

No directly retired version/Mg module was reachable from the production roots `xstar_tools.xstar.driver`, `physical_runner`, or `standalone`.

## Retired modules

- `all61_thermal_state_consumption_audit.py`
- `canonical_thermal_controller_parity_v048746217.py`
- `canonical_thermal_ownership_v048746212.py`
- `compact_population_parity_v048746212.py`
- `compact_population_solve_stage_parity_v048746213.py`
- `compact_population_solve_stage_parity_v0487462131.py`
- `continuum_freef_pow_hotfix_v048746172.py`
- `continuum_grid_binary64_hotfix_v048746171.py`
- `continuum_workspace_correction_v04874617.py`
- `helium_matrix_residual_decomposition.py`
- `helium_solve_response_decomposition.py`
- `helium_type53_controller_residual_v048746226.py`
- `hydrogen_type50_cooling_v04874618.py`
- `hydrogen_type6062_thermal_closure_v048746219.py`
- `independent_thermal_parity_v04874621.py`
- `independent_thermal_parity_v048746211.py`
- `independent_thermal_parity_v048746212.py`
- `iteration_resolved_trajectory_parity_v048746214.py`
- `iteration_resolved_trajectory_parity_v048746215.py`
- `iteration_resolved_trajectory_parity_v048746216.py`
- `magnesium_primary_cooling_source_order_v048746202.py`
- `magnesium_type49_leveltemp_closure_v048746222.py`
- `magnesium_type50_cooling_v04874619.py`
- `magnesium_type50_endpoint_energy_v048746193.py`
- `magnesium_type50_thermal_channel_preservation_v0487461931.py`
- `magnesium_type53_leveltemp_closure_v048746221.py`
- `magnesium_type57_thermal_closure_v048746220.py`
- `magnesium_type99_leveltemp_closure_v048746223.py`
- `magnesium_type99_primary_cooling_v04874620.py`
- `magnesium_type99_runtime_domain_v0487462011.py`
- `mg_bound_free_finite_state_attribution.py`
- `mg_bound_free_source_faithful_attribution.py`
- `mg_milne_excited_threshold_attribution.py`
- `mg_primary_workspace_transport_audit.py`
- `mg_type50_endpoint_orientation_attribution.py`
- `mg_type51_source_faithful_attribution.py`
- `mg_type99_secondary_energy_correction.py`
- `native_replay_resume.py`
- `native_replay_resume_v04874621.py`
- `native_replay_resume_v048746211.py`
- `native_replay_resume_v048746212.py`
- `post_type99_type68_residual_audit_v0487462231.py`
- `product_oracle_v04874622.py`
- `row46_dsec_residual_audit.py`
- `source_capture_resolver_v0487462271.py`
- `source_capture_trajectory_v0487462272.py`
- `source_order_electron_controller_closure_v048746227.py`
- `thermal_answer_path_correction_v048746218.py`
- `thermal_component_parity_closure.py`
- `type49_leveltemp_case_contract_v048746222.py`
- `type50_dsec_coupled_replacement_audit.py`
- `type50_manifold_replacement_audit.py`
- `type53_leveltemp_case_contract_v048746221.py`
- `type53_row46_dsec_runtime_contract_audit.py`
- `type53_row46_source_faithful_replacement_audit.py`
- `type53_runtime_state_abi_audit.py`
- `type57_case_contract_v0487462201.py`
- `type57_diagnostic_threshold_e10_gate_semantics_hotfix_v04874622321.py`
- `type57_diagnostic_threshold_regression_chain_closure_v0487462232.py`
- `type71_type99_replacement_audit.py`
- `type73_ucalc_parity_v048746224.py`
- `type99_leveltemp_case_contract_v048746223.py`
- `type99_type71_coupled_audit.py`
- `v0434_regression.py`
- `v0438_regression.py`
- `v0439_regression.py`
- `v0440_regression.py`
- `v0441_regression.py`
- `v0442_regression.py`
- `v0472_all61_fixed_state_capture.py`
- `v0472_all61_hydrogen_type50_escape_capture.py`
- `v0472_all61_independent_thermal_capture_v04874621.py`
- `v0472_all61_independent_thermal_capture_v048746211.py`
- `v0472_all61_independent_thermal_capture_v048746212.py`
- `v0472_all61_magnesium_primary_cooling_source_order_capture.py`
- `v0472_all61_magnesium_type50_endpoint_capture.py`
- `v0472_all61_magnesium_type50_escape_capture.py`
- `v0472_all61_magnesium_type99_primary_cooling_capture.py`
- `v0472_all61_post_seed_system_capture.py`
- `v0472_all61_solve_stage_capture_v048746213.py`
- `v0472_all61_solve_stage_capture_v0487462131.py`
- `v0472_all61_source_record_contribution_capture_v82_patch5193.py`
- `v0472_all61_thermal_state_capture.py`
- `v0472_all61_type88_rate_lifetime_capture_v82_patch51941.py`
- `v0472_call2_helium_solve_state_capture.py`
- `v0472_call2_helium_source_family_capture.py`
- `v0472_dsec_row46_runtime_capture.py`
- `v0472_dsec_type50_runtime_capture.py`
- `v0472_full_dsec_thermal_budget_capture.py`
- `v0472_heatt_zrems_running_sum_capture_v82_patch520.py`
- `v0472_heatt_zrems_running_sum_capture_v82_patch52051.py`
- `v0472_iteration_resolved_trajectory_capture_v048746214.py`
- `v0472_type50_manifold_runtime_capture.py`
- `v0472_type53_runtime_capture.py`
- `v0472_type71_runtime_capture.py`
- `v0472_type99_runtime_capture.py`
- `v4613_baseline_gate_vocabulary.py`
- `v46141_baseline_gate_vocabulary.py`
- `v4615_baseline_gate.py`
- `v4616_baseline_gate_v04874617.py`
- `v46171_baseline_gate_v048746172.py`
- `v461721_baseline_gate_v04874618.py`
- `v4617_baseline_gate_v048746171.py`
- `v46181_baseline_gate_v04874619.py`
- `v46191_sequence_mask_gate_v048746192.py`
- `v46192_endpoint_energy_gate_v048746193.py`
- `v461931_baseline_gate_v04874620.py`
- `v46193_thermal_channel_gate_v0487461931.py`
- `v4619_runtime_inventory_gate_v048746191.py`
- `v462011_baseline_gate_v048746202.py`
- `v46201_downstream_gate_v0487462011.py`
- `v4620_runtime_inventory_gate_v048746201.py`

## Retired console entry points

- `xstar-tools-product-oracle` → `xstar_tools.xstar.product_oracle_v04874622:main`
- `xstar-tools-v0472-type53-capture` → `xstar_tools.xstar.v0472_type53_runtime_capture:main`
- `xstar-tools-v0472-type99-capture` → `xstar_tools.xstar.v0472_type99_runtime_capture:main`
- `xstar-tools-type99-type71-audit` → `xstar_tools.xstar.type99_type71_coupled_audit:main`
- `xstar-tools-v0472-type71-capture` → `xstar_tools.xstar.v0472_type71_runtime_capture:main`
- `xstar-tools-type71-type99-replacement-audit` → `xstar_tools.xstar.type71_type99_replacement_audit:main`
- `xstar-tools-helium-matrix-residual-decomposition` → `xstar_tools.xstar.helium_matrix_residual_decomposition:main`
- `xstar-tools-v0472-type50-manifold-capture` → `xstar_tools.xstar.v0472_type50_manifold_runtime_capture:main`
- `xstar-tools-type50-manifold-replacement-audit` → `xstar_tools.xstar.type50_manifold_replacement_audit:main`
- `xstar-tools-type50-dsec-coupled-replacement-audit` → `xstar_tools.xstar.type50_dsec_coupled_replacement_audit:main`
- `xstar-tools-v0472-dsec-row46-capture` → `xstar_tools.xstar.v0472_dsec_row46_runtime_capture:main`
- `xstar-tools-row46-dsec-residual-audit` → `xstar_tools.xstar.row46_dsec_residual_audit:main`
- `xstar-tools-type53-row46-dsec-audit` → `xstar_tools.xstar.type53_row46_dsec_runtime_contract_audit:main`

## Retired tests

- `tests/test_v048712_dsec_type50_runtime_capture.py`
- `tests/test_v0648710_type50_manifold_replacement_audit.py`
- `tests/test_v0648711_helium_solve_response_decomposition.py`
- `tests/test_v0648713_type50_dsec_coupled_replacement.py`
- `tests/test_v0648714_dsec_row46_capture_and_audit.py`
- `tests/test_v0648715_type53_row46_dsec_runtime_contract_audit.py`
- `tests/test_v0648716_type53_row46_source_faithful_replacement.py`
- `tests/test_v0648717_type53_runtime_state_abi.py`
- `tests/test_v0648723_mg_primary_workspace_transport.py`
- `tests/test_v0648726_post_call1_decomposition.py`
- `tests/test_v06487281_call2_helium_retained_capture_hotfix.py`
- `tests/test_v06487311_element_basis_row_metadata_capture_hotfix.py`
- `tests/test_v06487312_helium_solve_state_json_serialization_hotfix.py`
- `tests/test_v0648731_call2_helium_solve_state_rate_matrix_decomposition.py`
- `tests/test_v064873_v0472_type53_runtime_capture.py`
- `tests/test_v0648743_all61_h_he_mg_fixed_state_closure.py`
- `tests/test_v0648746101_zero_residual_audit_hotfix.py`
- `tests/test_v0648746121_canonical_scalar_resume.py`
- `tests/test_v064874612_all61_thermal_state_consumption.py`
- `tests/test_v0648746141_v4613_baseline_gate_vocabulary.py`
- `tests/test_v064874615_mg_type99_destination_secondary_energy.py`
- `tests/test_v064874616_helium_non_type53_cooling_reduction.py`
- `tests/test_v0648746171_continuum_grid_binary64_hotfix.py`
- `tests/test_v06487461721_continuum_preservation_gate_vocabulary_hotfix.py`
- `tests/test_v0648746172_continuum_freef_pow_hotfix.py`
- `tests/test_v064874617_continuum_workspace_correction.py`
- `tests/test_v0648746181_hydrogen_type50_source_capture_context_hotfix.py`
- `tests/test_v064874618_hydrogen_type50_cooling.py`
- `tests/test_v0648746191_magnesium_runtime_active_inventory_hotfix.py`
- `tests/test_v0648746192_magnesium_runtime_active_sequence_mask_hotfix.py`
- `tests/test_v064874619_magnesium_primary_cooling.py`
- `tests/test_v06487461_source_diagnostic_retention_hotfix.py`
- `tests/test_v06487462011_type99_runtime_domain_downstream_gate_vocabulary_hotfix.py`
- `tests/test_v0648746201_magnesium_type99_runtime_active_inventory_hotfix.py`
- `tests/test_v0648746202_magnesium_primary_cooling_source_order.py`
- `tests/test_v064874620_magnesium_type99_primary_cooling.py`
- `tests/test_v064874621162_type57_fresh_case_hotfix.py`
- `tests/test_v06487462131_solve_stage_diagnostic_semantics_hotfix.py`
- `tests/test_v0648746213_compact_population_solve_stage_parity.py`
- `tests/test_v0648746214_iteration_resolved_trajectory_parity.py`
- `tests/test_v0648746215_source_faithful_element_convergence_contract.py`
- `tests/test_v0648746216_all_sequence_ieee_e10_trajectory_parity.py`
- `tests/test_v0648746217_canonical_thermal_controller_parity.py`
- `tests/test_v0648746218_thermal_answer_path_corrections.py`
- `tests/test_v0648746219_hydrogen_type6062_thermal_closure.py`
- `tests/test_v0648746220_magnesium_type57_thermal_closure.py`
- `tests/test_v0648746221_magnesium_type53_leveltemp_closure.py`
- `tests/test_v0648746222_magnesium_type49_leveltemp_closure.py`
- `tests/test_v064874622321_type57_diagnostic_threshold_e10_gate_semantics_hotfix.py`
- `tests/test_v06487462232_type57_diagnostic_threshold_regression_chain_closure.py`
- `tests/test_v0648746223_magnesium_type99_leveltemp_closure.py`
- `tests/test_v06487462271_permanent_source_capture_and_controller_closure.py`
- `tests/test_v06487462272_coherent_source_trajectory_controller_alignment.py`
- `tests/test_v064874622_native_physical_run_state_product_oracle.py`
- `tests/test_v064874624_complete_python_product_archive_closure.py`
- `tests/test_v06487462_source_solve_summary_retention.py`
- `tests/test_v06487463_generated_probe_retention_contract.py`
- `tests/test_v06487465_probe_component_contract_hotfix.py`
- `tests/test_v06487466_genuine_post_seed_system_capture.py`
- `tests/test_v06487467_probe_runtime_dependency_closure.py`
- `tests/test_v0648746941_mg_milne_excited_threshold.py`
- `tests/test_v0648746942_type53_audit_type49_grid_parity.py`
- `tests/test_v064874694_mg_bound_free_source_faithful.py`
- `tests/test_v064874695_mg_type51_source_faithful.py`
- `tests/test_v06487469_dense_matrix_causal_attribution.py`
- `tests/test_v064876_type99_type71_coupled_audit.py`
- `tests/test_v064877_type71_type99_replacement_audit.py`
- `tests/test_v064878_helium_matrix_residual_decomposition.py`

## Mg XI benchmark retention

`src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8/` remains in the package as the frozen Mg XI benchmark/qualification case. It is benchmark material, not a statement that the runtime is intended to be Mg-only.

## Deferred generalization work

All remaining current-source Z=12 branches are inventoried separately in `docs/v0648951_element_z12_inventory.md` and `.csv`. They are deliberately not changed in 9.5.1. Multi-element qualification will follow the 9.6/9.7 performance work.
