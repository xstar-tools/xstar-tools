# xstar-atomic examples

This directory contains runnable examples and development/validation workflows for `xstar-atomic`. The examples are organized below by relevance so new users can start with simple database inspection and advanced developers can jump directly to same-run XSTAR validation and source-code audits.

## General usage

Run examples from the package root with `PYTHONPATH=src` unless the package is installed with `pip install -e .`:

```bash
PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/xstar/data/atdb.fits
```

Many later validation examples expect generated products from earlier examples, XSTAR output files such as `xout_lines1.fits`/`xout_abund1.fits`, or solver output directories. Use the examples in order within each group when reproducing a validation sequence.

## Example groups

1. [Getting started and database inspection](#getting-started-and-database-inspection)
2. [Basic atomic data, lines, rates, and emissivity](#basic-atomic-data-lines-rates-and-emissivity)
3. [Prototype solvers, timing, and profiling](#prototype-solvers-timing-and-profiling)
4. [O VII recombination, cascade, and source-fit development](#o-vii-recombination-cascade-and-source-fit-development)
5. [O VII high-density and type-69 diagnostics](#o-vii-high-density-and-type-69-diagnostics)
6. [He-like multi-ion response matrices and source bases](#he-like-multi-ion-response-matrices-and-source-bases)
7. [Same-run XSTAR comparison and C V validation](#same-run-xstar-comparison-and-c-v-validation)
8. [Mg/Ca validation, all-ion local-state validation, and type-50 audits](#mg-ca-validation-all-ion-local-state-validation-and-type-50-audits)

## Getting started and database inspection

| Example | Purpose | Minimal command |
|---|---|---|
| `14_download_or_configure_data.py` | Configure or download `atdb.fits` and test database opening. | `PYTHONPATH=src python examples/14_download_or_configure_data.py --set-path /path/to/xstar/data/atdb.fits` |
| `05_low_level_atdb_index.py` | Use the low-level ATDB reader and print record/element/ion index counts. | `PYTHONPATH=src python examples/05_low_level_atdb_index.py /path/to/atdb.fits` |
| `06_high_level_api_quickstart.py` | Notebook-style high-level API quick start using `XSTARAtomic`. | `PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/atdb.fits` |

## Basic atomic data, lines, rates, and emissivity

| Example | Purpose | Minimal command |
|---|---|---|
| `01_o8_lya_lines.py` | Extract the O VIII Ly-alpha doublet from XSTAR `atdb.fits`. | `PYTHONPATH=src python examples/01_o8_lya_lines.py /path/to/atdb.fits` |
| `02_o8_lya_collisions.py` | Evaluate O VIII Ly-alpha collisional-excitation rates at selected temperatures. | `PYTHONPATH=src python examples/02_o8_lya_collisions.py /path/to/atdb.fits --temperatures 1e6 3e6 1e7` |
| `03_o8_lya_emissivity.py` | Build a direct-excitation O VIII Ly-alpha emissivity CSV. | `PYTHONPATH=src python examples/03_o8_lya_emissivity.py /path/to/atdb.fits --out o8_lya_emissivity_example.csv` |
| `04_oxygen_recombination_inventory.py` | Inventory oxygen recombination-like records and evaluate rates. | `PYTHONPATH=src python examples/04_oxygen_recombination_inventory.py /path/to/atdb.fits --temperature 1e6` |
| `07_collision_decoder_validation.py` | Find collision-decoder targets and validate representative type-51/98/type-63 branches. | `PYTHONPATH=src python examples/07_collision_decoder_validation.py /path/to/atdb.fits` |
| `09_export_band_emissivity.py` | Export line-based band emissivity products for selected ions in CSV/HDF5 form. | `PYTHONPATH=src python examples/09_export_band_emissivity.py /path/to/atdb.fits` |

## Prototype solvers, timing, and profiling

| Example | Purpose | Minimal command |
|---|---|---|
| `10_o7_triplet_sparse_solver.py` | Run an O VII triplet sparse level-population stress test. | `PYTHONPATH=src python examples/10_o7_triplet_sparse_solver.py /path/to/atdb.fits --out-dir o7_triplet_solver_example` |
| `11_solver_timing.py` | Benchmark level-population solver timing for compact cases. | `PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits --repeat 3 --out-dir solver_timing_example` |
| `12_profile_solver_steps.py` | Profile major stages of an emissivity/solver path for a selected ion and wavelength range. | `PYTHONPATH=src python examples/12_profile_solver_steps.py /path/to/atdb.fits --element O --ion-stage 8 --temperature 1e6` |
| `42_xstar_like_element_solver_demo.py` | Run the full-global XSTAR-like element-solver scaffold used by later validation examples. | `PYTHONPATH=src python examples/42_xstar_like_element_solver_demo.py /path/to/atdb.fits --element O --he-like-stage 7 --temperature 1e6 --electron-density 1e8 --wavelength-min 21.4 --wavelength-max 22.3` |

## O VII recombination, cascade, and source-fit development

| Example | Purpose | Minimal command |
|---|---|---|
| `13_o7_recombination_cascade_workflow.py` | Prototype O VII recombination/cascade source allocation workflow. | `PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py /path/to/atdb.fits --temperature 1e6` |
| `15_o7_cascade_tuning_scan.py` | Scan O VII cascade source-map choices against a triplet target. | `PYTHONPATH=src python examples/15_o7_cascade_tuning_scan.py /path/to/atdb.fits --print-summary` |
| `17_o7_type68_cascade_tuning_scan.py` | Repeat the cascade scan with type-68-aware redistribution diagnostics. | `PYTHONPATH=src python examples/17_o7_type68_cascade_tuning_scan.py /path/to/atdb.fits --print-summary` |
| `18_o7_type68_2d_cascade_tuning_scan.py` | Run a two-parameter type-68 cascade redistribution scan. | `PYTHONPATH=src python examples/18_o7_type68_2d_cascade_tuning_scan.py /path/to/atdb.fits --print-summary` |
| `19_o7_cascade_source_fit.py` | Build a radiative cascade-yield matrix and fit non-negative O VII source weights. | `PYTHONPATH=src python examples/19_o7_cascade_source_fit.py /path/to/atdb.fits --out-dir o7_cascade_source_fit` |
| `20_o7_solver_source_fit.py` | Fit empirical O VII source weights against the full level-population response matrix. | `PYTHONPATH=src python examples/20_o7_solver_source_fit.py /path/to/atdb.fits` |
| `21_o7_solver_source_fit_density_grid.py` | Run O VII solver-source fitting across a density grid using a fixed target table. | `PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py /path/to/atdb.fits` |
| `22_o7_solver_source_fit_density_xstar_grid.py` | Run the density-grid source-fit diagnostic using density-dependent same-run XSTAR targets. | `PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py /path/to/atdb.fits --xstar-lines-csv-template 'xstar_test_run/o7_ne{ne_tag}/xstar_o7_triplet_lines.csv'` |

## O VII high-density and type-69 diagnostics

| Example | Purpose | Minimal command |
|---|---|---|
| `16_o7_metastable_coupling_diagnostics.py` | Inspect O VII metastable/intercombination coupling over density. | `PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py /path/to/atdb.fits --print-summary` |
| `23_prepare_o7_xstar_density_grid.py` | Prepare O VII XSTAR density-grid run directories and conversion commands. | `PYTHONPATH=src python examples/23_prepare_o7_xstar_density_grid.py --root . --print-summary` |
| `24_o7_high_density_mismatch_diagnostics.py` | Diagnose the O VII high-density source-fit mismatch. | `PYTHONPATH=src python examples/24_o7_high_density_mismatch_diagnostics.py --density-grid-dir o7_solver_source_fit_density_xstar_grid --print-summary` |
| `25_o7_high_density_expanded_source_scan.py` | Scan expanded O VII source-level sets for the high-density residual. | `PYTHONPATH=src python examples/25_o7_high_density_expanded_source_scan.py /path/to/atdb.fits --print-summary` |
| `26_o7_high_density_rate_sensitivity.py` | Scan high-density rate-network sensitivity for the O VII mismatch. | `PYTHONPATH=src python examples/26_o7_high_density_rate_sensitivity.py --solver-out-dir o7_solver_source_fit_density_xstar_grid --print-summary` |
| `27_o7_type69_transition_sensitivity.py` | Scan individual O VII type-69 transitions at high density. | `PYTHONPATH=src python examples/27_o7_type69_transition_sensitivity.py --solver-out-dir o7_solver_source_fit_density_xstar_grid --print-summary` |
| `28_o7_type69_record_audit.py` | Audit O VII type-69 collision records and their rate interpretation. | `PYTHONPATH=src python examples/28_o7_type69_record_audit.py /path/to/atdb.fits --print-summary` |
| `29_o7_type69_ground_coupling_diagnostic.py` | Interpret O VII type-69 ground-resonance coupling terms. | `PYTHONPATH=src python examples/29_o7_type69_ground_coupling_diagnostic.py /path/to/atdb.fits --print-summary` |
| `30_o7_density_grid_type69_mode_compare.py` | Compare density-grid fits for different type-69 ground-excitation treatments. | `PYTHONPATH=src python examples/30_o7_density_grid_type69_mode_compare.py /path/to/atdb.fits --print-summary` |

## He-like multi-ion response matrices and source bases

| Example | Purpose | Minimal command |
|---|---|---|
| `31_helike_type69_ground_resonance_validation.py` | Audit He-like type-69 ground-resonance candidates across ions. | `PYTHONPATH=src python examples/31_helike_type69_ground_resonance_validation.py /path/to/atdb.fits --print-summary` |
| `32_prepare_helike_xstar_density_grids.py` | Prepare XSTAR density-grid directories for candidate He-like ions. | `PYTHONPATH=src python examples/32_prepare_helike_xstar_density_grids.py --root . --print-summary` |
| `33_audit_helike_xstar_lines.py` | Audit XSTAR `xout_lines1.fits` when He-like triplet conversion is empty. | `PYTHONPATH=src python examples/33_audit_helike_xstar_lines.py --xout-lines-fits xout_lines1.fits --print-summary` |
| `34_summarize_helike_validation_runs.py` | Summarize He-like density-grid validation outputs across ions. | `PYTHONPATH=src python examples/34_summarize_helike_validation_runs.py --root . --print-summary` |
| `35_compare_helike_response_matrices.py` | Compare He-like source-fit response matrices across ions. | `PYTHONPATH=src python examples/35_compare_helike_response_matrices.py --root . --print-summary` |
| `36_source_level_failure_diagnostics.py` | Diagnose source-level response failures across He-like density-grid runs. | `PYTHONPATH=src python examples/36_source_level_failure_diagnostics.py --root . --print-summary` |
| `37_filter_source_basis_response.py` | Compare He-like source-basis filters against fitted triplet targets. | `PYTHONPATH=src python examples/37_filter_source_basis_response.py --root . --print-summary` |
| `38_discover_helike_source_basis.py` | Discover ion-specific He-like source bases from solver response matrices. | `PYTHONPATH=src python examples/38_discover_helike_source_basis.py --root . --print-summary` |
| `39_scan_helike_source_level_blocks.py` | Scan broad He-like source-level blocks for positive triplet-response bases. | `PYTHONPATH=src python examples/39_scan_helike_source_level_blocks.py --root . --print-summary` |
| `40_audit_signed_triplet_response.py` | Audit signed versus absolute He-like triplet response for source levels. | `PYTHONPATH=src python examples/40_audit_signed_triplet_response.py --root . --print-summary` |
| `41_fit_absolute_response_density_grid.py` | Fit absolute He-like triplet response across a density grid. | `PYTHONPATH=src python examples/41_fit_absolute_response_density_grid.py /path/to/atdb.fits --print-summary` |

## Same-run XSTAR comparison and C V validation

| Example | Purpose | Minimal command |
|---|---|---|
| `08_compare_xstar_outputs.py` | Compare xstar-atomic rows with an external XSTAR line-output CSV table. | `PYTHONPATH=src python examples/08_compare_xstar_outputs.py /path/to/atdb.fits xstar_lines.csv --ion 'O VII' --mode both --print-summary` |
| `43_compare_xstar_detail_populations.py` | Compare full-global populations with XSTAR detail populations and triplet targets. | `PYTHONPATH=src python examples/43_compare_xstar_detail_populations.py --solver-out-dir o7_xstar_like_element_solver --element O --he-like-stage 7` |
| `44_diagnose_helike_triplet_balance.py` | Diagnose He-like triplet balance terms in solver outputs. | `PYTHONPATH=src python examples/44_diagnose_helike_triplet_balance.py --case 'O VII:o7_xstar_like_element_solver' --print-summary` |
| `45_prepare_c5_xstar_triplet_reference.py` | Prepare or convert a real C V XSTAR triplet-line reference CSV. | `PYTHONPATH=src python examples/45_prepare_c5_xstar_triplet_reference.py --root .` |
| `46_cv_source_attribution_scan.py` | Run C V f/r source-attribution and source-group scans. | `PYTHONPATH=src python examples/46_cv_source_attribution_scan.py --solver-out-dir c5_xstar_like_element_solver --print-summary` |

## Mg/Ca validation, all-ion local-state validation, and type-50 audits

| Example | Purpose | Minimal command |
|---|---|---|
| `47_prepare_mg_ca_xstar_triplet_targets.py` | Prepare Mg XI and Ca XIX XSTAR triplet targets and validation commands. | `PYTHONPATH=src python examples/47_prepare_mg_ca_xstar_triplet_targets.py --root . --print-summary` |
| `48_sourcecode_first_mg_ca_validation.py` | Run a source-code-first Mg XI / Ca XIX validation audit. | `PYTHONPATH=src python examples/48_sourcecode_first_mg_ca_validation.py --results-root . --print-summary` |
| `49_mg_ca_triplet_source_path_audit.py` | Audit Mg XI / Ca XIX triplet source paths against XSTAR source-code branches. | `PYTHONPATH=src python examples/49_mg_ca_triplet_source_path_audit.py --results-root . --print-summary` |
| `50_mg_ca_xstar_local_state_audit.py` | Audit Mg XI / Ca XIX comparisons against local XSTAR zone conditions. | `PYTHONPATH=src python examples/50_mg_ca_xstar_local_state_audit.py --results-root . --xstar-runs-root xstar_runs --print-summary` |
| `51_run_helike_local_state_validation.py` | Prepare and optionally run He-like validation at same-run local XSTAR states. | `PYTHONPATH=src python examples/51_run_helike_local_state_validation.py --xstar-runs-root xstar_runs --target-root . --atdb /path/to/atdb.fits --selection-mode max --target-electron-density 1e8 --nearest-density --out-dir helike_local_state_validation_v03129 --print-summary` |
| `52_summarize_helike_local_state_comparison.py` | Summarize local-state solver comparisons against same-run XSTAR targets. | `PYTHONPATH=src python examples/52_summarize_helike_local_state_comparison.py --cases-csv helike_local_state_validation_v03129/helike_local_state_cases.csv --solver-root . --print-summary` |
| `53_audit_helike_resonance_deficit.py` | Audit the common He-like low-resonance residual after local-state validation. | `PYTHONPATH=src python examples/53_audit_helike_resonance_deficit.py --cases-csv helike_local_state_validation_v03129/helike_local_state_cases.csv --solver-root . --print-summary` |
| `54_audit_helike_resonance_population_flux.py` | Audit population-weighted feed/loss paths for the resonance upper level. | `PYTHONPATH=src python examples/54_audit_helike_resonance_population_flux.py --cases-csv helike_local_state_validation_v03129/helike_local_state_cases.csv --solver-root . --print-summary` |
| `55_audit_helike_type50_line_pumping.py` | Run the v0.3.128+ API-backed type-50 line-pumping audit wrapper. | `PYTHONPATH=src python examples/55_audit_helike_type50_line_pumping.py --cases-csv helike_local_state_validation_v03129/helike_local_state_cases.csv --solver-root . --xstar-source-root ../xstar --print-summary` |

## Recommended learning paths

- **New user:** 14 -> 05 -> 06 -> 01 -> 02 -> 03.
- **Atomic-data decoder developer:** 05 -> 01 -> 04 -> 07 -> 28 -> 31.
- **Emissivity/export user:** 02 -> 03 -> 09 -> 12.
- **O VII triplet development:** 13 -> 15 -> 17 -> 19 -> 21 -> 22 -> 24 -> 30.
- **Full-global/XSTAR validation:** 42 -> 43 -> 44 -> 51 -> 52 -> 53 -> 54 -> 55.
- **Mg XI / Ca XIX validation:** 47 -> 48 -> 49 -> 50 -> 51 -> 52 -> 55.

## Migration policy

As workflows stabilize, reusable logic should move from `examples/` into `src/xstar_atomic/`, leaving the examples as short command-line wrappers. See `docs/example_to_source_api_map.md` for the current migration plan. The most mature case is `examples/55_audit_helike_type50_line_pumping.py`, which is already a wrapper around `xstar_atomic.audit.type50_line_pumping(...)`.

## Development policy

These examples follow the source-code-first rule: no empirical triplet scale factors should be used as final physics, new physics starts as audit-only, solver-changing modes must be opt-in until same-run XSTAR validation is complete, and every solver-changing rate must carry source-code and local-context provenance.
