# xstar-atomic examples

This directory contains runnable examples and development/validation workflows for `xstar-atomic`. The examples are organized by relevance so new users can start with simple database inspection and advanced developers can jump directly to same-run XSTAR validation and source-code audits.

Every example below includes a concrete `bash` command. Commands with `/path/to/atdb.fits`, `xstar_runs`, `xout_lines1.fits`, or solver-output directories require those external files to exist. Run commands from the package root with `PYTHONPATH=src` unless the package is installed with `pip install -e .`.

```bash
PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/xstar/data/atdb.fits
```

Use the examples in order within each group when reproducing a validation sequence. Later validation examples often consume CSV/JSON/FITS products produced by earlier examples or by XSTAR itself.

## Example groups

1. [Getting started and database inspection](#getting-started-and-database-inspection)
2. [Basic atomic data, lines, rates, and emissivity](#basic-atomic-data-lines-rates-and-emissivity)
3. [Prototype solvers, timing, and profiling](#prototype-solvers-timing-and-profiling)
4. [O VII recombination, cascade, and source-fit development](#o-vii-recombination-cascade-and-source-fit-development)
5. [O VII high-density and type-69 diagnostics](#o-vii-high-density-and-type-69-diagnostics)
6. [He-like multi-ion response matrices and source bases](#he-like-multi-ion-response-matrices-and-source-bases)
7. [Same-run XSTAR comparison and C V validation](#same-run-xstar-comparison-and-c-v-validation)
8. [Mg/Ca validation, all-ion local-state validation, and type-50 audits](#mgca-validation-all-ion-local-state-validation-and-type-50-audits)

## Getting started and database inspection

### `14_download_or_configure_data.py`

Configure or download `atdb.fits` and test database opening.

```bash
PYTHONPATH=src python examples/14_download_or_configure_data.py --set-path /path/to/xstar/data/atdb.fits
```

### `05_low_level_atdb_index.py`

Use the low-level ATDB reader and print record/element/ion index counts.

```bash
PYTHONPATH=src python examples/05_low_level_atdb_index.py /path/to/atdb.fits
```

### `06_high_level_api_quickstart.py`

Notebook-style high-level API quick start using `XSTARAtomic`.

```bash
PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/atdb.fits
```

## Basic atomic data, lines, rates, and emissivity

### `01_o8_lya_lines.py`

Extract the O VIII Ly-alpha doublet from XSTAR `atdb.fits`.

```bash
PYTHONPATH=src python examples/01_o8_lya_lines.py /path/to/atdb.fits
```

### `02_o8_lya_collisions.py`

Evaluate O VIII Ly-alpha collisional-excitation rates at selected temperatures.

```bash
PYTHONPATH=src python examples/02_o8_lya_collisions.py /path/to/atdb.fits --temperatures 1e6 3e6 1e7
```

### `03_o8_lya_emissivity.py`

Build a direct-excitation O VIII Ly-alpha emissivity CSV.

```bash
PYTHONPATH=src python examples/03_o8_lya_emissivity.py /path/to/atdb.fits --out o8_lya_emissivity_example.csv
```

### `04_oxygen_recombination_inventory.py`

Inventory oxygen recombination-like records and evaluate rates.

```bash
PYTHONPATH=src python examples/04_oxygen_recombination_inventory.py /path/to/atdb.fits --temperature 1e6
```

### `07_collision_decoder_validation.py`

Find collision-decoder targets and validate representative type-51/98/type-63 branches.

```bash
PYTHONPATH=src python examples/07_collision_decoder_validation.py /path/to/atdb.fits
```

### `09_export_band_emissivity.py`

Export line-based band emissivity products for selected ions in CSV/HDF5 form.

```bash
PYTHONPATH=src python examples/09_export_band_emissivity.py /path/to/atdb.fits
```

## Prototype solvers, timing, and profiling

### `10_o7_triplet_sparse_solver.py`

Run an O VII triplet sparse level-population stress test.

```bash
PYTHONPATH=src python examples/10_o7_triplet_sparse_solver.py /path/to/atdb.fits --out-dir o7_triplet_solver_example
```

### `11_solver_timing.py`

Benchmark level-population solver timing for compact cases.

```bash
PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits --repeat 3 --out-dir solver_timing_example
```

### `12_profile_solver_steps.py`

Profile major stages of an emissivity/solver path for a selected ion and wavelength range.

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py /path/to/atdb.fits --element O --ion-stage 8 --temperature 1e6
```

### `42_xstar_like_element_solver_demo.py`

Run the full-global XSTAR-like element-solver scaffold used by later validation examples.

```bash
PYTHONPATH=src python examples/42_xstar_like_element_solver_demo.py /path/to/atdb.fits --element O --he-like-stage 7 --temperature 1e6 --electron-density 1e8 --wavelength-min 21.4 --wavelength-max 22.3
```

## O VII recombination, cascade, and source-fit development

### `13_o7_recombination_cascade_workflow.py`

Prototype O VII recombination/cascade source allocation workflow.

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py /path/to/atdb.fits --temperature 1e6
```

### `15_o7_cascade_tuning_scan.py`

Scan O VII cascade source-map choices against a triplet target.

```bash
PYTHONPATH=src python examples/15_o7_cascade_tuning_scan.py /path/to/atdb.fits --print-summary
```

### `17_o7_type68_cascade_tuning_scan.py`

Repeat the cascade scan with type-68-aware redistribution diagnostics.

```bash
PYTHONPATH=src python examples/17_o7_type68_cascade_tuning_scan.py /path/to/atdb.fits --print-summary
```

### `18_o7_type68_2d_cascade_tuning_scan.py`

Run a two-parameter type-68 cascade redistribution scan.

```bash
PYTHONPATH=src python examples/18_o7_type68_2d_cascade_tuning_scan.py /path/to/atdb.fits --print-summary
```

### `19_o7_cascade_source_fit.py`

Build a radiative cascade-yield matrix and fit non-negative O VII source weights.

```bash
PYTHONPATH=src python examples/19_o7_cascade_source_fit.py /path/to/atdb.fits --out-dir o7_cascade_source_fit
```

### `20_o7_solver_source_fit.py`

Fit empirical O VII source weights against the full level-population response matrix.

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py /path/to/atdb.fits
```

### `21_o7_solver_source_fit_density_grid.py`

Run O VII solver-source fitting across a density grid using a fixed target table.

```bash
PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py /path/to/atdb.fits
```

### `22_o7_solver_source_fit_density_xstar_grid.py`

Run the density-grid source-fit diagnostic using density-dependent same-run XSTAR targets.

```bash
PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py /path/to/atdb.fits --xstar-lines-csv-template 'xstar_test_run/o7_ne{ne_tag}/xstar_o7_triplet_lines.csv'
```

## O VII high-density and type-69 diagnostics

### `16_o7_metastable_coupling_diagnostics.py`

Inspect O VII metastable/intercombination coupling over density.

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py /path/to/atdb.fits --print-summary
```

### `23_prepare_o7_xstar_density_grid.py`

Prepare O VII XSTAR density-grid run directories and conversion commands.

```bash
PYTHONPATH=src python examples/23_prepare_o7_xstar_density_grid.py --root . --print-summary
```

### `24_o7_high_density_mismatch_diagnostics.py`

Diagnose the O VII high-density source-fit mismatch.

```bash
PYTHONPATH=src python examples/24_o7_high_density_mismatch_diagnostics.py --density-grid-dir o7_solver_source_fit_density_xstar_grid --print-summary
```

### `25_o7_high_density_expanded_source_scan.py`

Scan expanded O VII source-level sets for the high-density residual.

```bash
PYTHONPATH=src python examples/25_o7_high_density_expanded_source_scan.py /path/to/atdb.fits --print-summary
```

### `26_o7_high_density_rate_sensitivity.py`

Scan high-density rate-network sensitivity for the O VII mismatch.

```bash
PYTHONPATH=src python examples/26_o7_high_density_rate_sensitivity.py --solver-out-dir o7_solver_source_fit_density_xstar_grid --print-summary
```

### `27_o7_type69_transition_sensitivity.py`

Scan individual O VII type-69 transitions at high density.

```bash
PYTHONPATH=src python examples/27_o7_type69_transition_sensitivity.py --solver-out-dir o7_solver_source_fit_density_xstar_grid --print-summary
```

### `28_o7_type69_record_audit.py`

Audit O VII type-69 collision records and their rate interpretation.

```bash
PYTHONPATH=src python examples/28_o7_type69_record_audit.py /path/to/atdb.fits --print-summary
```

### `29_o7_type69_ground_coupling_diagnostic.py`

Interpret O VII type-69 ground-resonance coupling terms.

```bash
PYTHONPATH=src python examples/29_o7_type69_ground_coupling_diagnostic.py /path/to/atdb.fits --print-summary
```

### `30_o7_density_grid_type69_mode_compare.py`

Compare density-grid fits for different type-69 ground-excitation treatments.

```bash
PYTHONPATH=src python examples/30_o7_density_grid_type69_mode_compare.py /path/to/atdb.fits --print-summary
```

## He-like multi-ion response matrices and source bases

### `31_helike_type69_ground_resonance_validation.py`

Audit He-like type-69 ground-resonance candidates across ions.

```bash
PYTHONPATH=src python examples/31_helike_type69_ground_resonance_validation.py /path/to/atdb.fits --print-summary
```

### `32_prepare_helike_xstar_density_grids.py`

Prepare XSTAR density-grid directories for candidate He-like ions.

```bash
PYTHONPATH=src python examples/32_prepare_helike_xstar_density_grids.py --root . --print-summary
```

### `33_audit_helike_xstar_lines.py`

Audit XSTAR `xout_lines1.fits` when He-like triplet conversion is empty.

```bash
PYTHONPATH=src python examples/33_audit_helike_xstar_lines.py --xout-lines-fits xout_lines1.fits --print-summary
```

### `34_summarize_helike_validation_runs.py`

Summarize He-like density-grid validation outputs across ions.

```bash
PYTHONPATH=src python examples/34_summarize_helike_validation_runs.py --root . --print-summary
```

### `35_compare_helike_response_matrices.py`

Compare He-like source-fit response matrices across ions.

```bash
PYTHONPATH=src python examples/35_compare_helike_response_matrices.py --root . --print-summary
```

### `36_source_level_failure_diagnostics.py`

Diagnose source-level response failures across He-like density-grid runs.

```bash
PYTHONPATH=src python examples/36_source_level_failure_diagnostics.py --root . --print-summary
```

### `37_filter_source_basis_response.py`

Compare He-like source-basis filters against fitted triplet targets.

```bash
PYTHONPATH=src python examples/37_filter_source_basis_response.py --root . --print-summary
```

### `38_discover_helike_source_basis.py`

Discover ion-specific He-like source bases from solver response matrices.

```bash
PYTHONPATH=src python examples/38_discover_helike_source_basis.py --root . --print-summary
```

### `39_scan_helike_source_level_blocks.py`

Scan broad He-like source-level blocks for positive triplet-response bases.

```bash
PYTHONPATH=src python examples/39_scan_helike_source_level_blocks.py --root . --print-summary
```

### `40_audit_signed_triplet_response.py`

Audit signed versus absolute He-like triplet response for source levels.

```bash
PYTHONPATH=src python examples/40_audit_signed_triplet_response.py --root . --print-summary
```

### `41_fit_absolute_response_density_grid.py`

Fit absolute He-like triplet response across a density grid.

```bash
PYTHONPATH=src python examples/41_fit_absolute_response_density_grid.py /path/to/atdb.fits --print-summary
```

## Same-run XSTAR comparison and C V validation

### `08_compare_xstar_outputs.py`

Compare xstar-atomic rows with an external XSTAR line-output CSV table.

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py /path/to/atdb.fits xstar_lines.csv --ion 'O VII' --mode both --print-summary
```

### `43_compare_xstar_detail_populations.py`

Compare full-global populations with XSTAR detail populations and triplet targets.

```bash
PYTHONPATH=src python examples/43_compare_xstar_detail_populations.py --solver-out-dir o7_xstar_like_element_solver --element O --he-like-stage 7
```

### `44_diagnose_helike_triplet_balance.py`

Diagnose He-like triplet balance terms in solver outputs.

```bash
PYTHONPATH=src python examples/44_diagnose_helike_triplet_balance.py --case 'O VII:o7_xstar_like_element_solver' --print-summary
```

### `45_prepare_c5_xstar_triplet_reference.py`

Prepare or convert a real C V XSTAR triplet-line reference CSV.

```bash
PYTHONPATH=src python examples/45_prepare_c5_xstar_triplet_reference.py --root .
```

### `46_cv_source_attribution_scan.py`

Run C V f/r source-attribution and source-group scans.

```bash
PYTHONPATH=src python examples/46_cv_source_attribution_scan.py --solver-out-dir c5_xstar_like_element_solver --print-summary
```

## Mg/Ca validation, all-ion local-state validation, and type-50 audits

### `47_prepare_mg_ca_xstar_triplet_targets.py`

Prepare Mg XI and Ca XIX XSTAR triplet targets and validation commands.

```bash
PYTHONPATH=src python examples/47_prepare_mg_ca_xstar_triplet_targets.py --root . --print-summary
```

### `48_sourcecode_first_mg_ca_validation.py`

Run a source-code-first Mg XI / Ca XIX validation audit.

```bash
PYTHONPATH=src python examples/48_sourcecode_first_mg_ca_validation.py --results-root . --print-summary
```

### `49_mg_ca_triplet_source_path_audit.py`

Audit Mg XI / Ca XIX triplet source paths against XSTAR source-code branches.

```bash
PYTHONPATH=src python examples/49_mg_ca_triplet_source_path_audit.py --results-root . --print-summary
```

### `50_mg_ca_xstar_local_state_audit.py`

Audit Mg XI / Ca XIX comparisons against local XSTAR zone conditions.

```bash
PYTHONPATH=src python examples/50_mg_ca_xstar_local_state_audit.py --results-root . --xstar-runs-root xstar_runs --print-summary
```

### `51_run_helike_local_state_validation.py`

Prepare and optionally run He-like validation at same-run local XSTAR states.

```bash
PYTHONPATH=src python examples/51_run_helike_local_state_validation.py --xstar-runs-root xstar_runs --target-root . --atdb /path/to/atdb.fits --selection-mode max --target-electron-density 1e8 --nearest-density --out-dir helike_local_state_validation_v03130 --print-summary
```

### `52_summarize_helike_local_state_comparison.py`

Summarize local-state solver comparisons against same-run XSTAR targets.

```bash
PYTHONPATH=src python examples/52_summarize_helike_local_state_comparison.py --cases-csv helike_local_state_validation_v03130/helike_local_state_cases.csv --solver-root . --print-summary
```

### `53_audit_helike_resonance_deficit.py`

Audit the common He-like low-resonance residual after local-state validation.

```bash
PYTHONPATH=src python examples/53_audit_helike_resonance_deficit.py --cases-csv helike_local_state_validation_v03130/helike_local_state_cases.csv --solver-root . --print-summary
```

### `54_audit_helike_resonance_population_flux.py`

Audit population-weighted feed/loss paths for the resonance upper level.

```bash
PYTHONPATH=src python examples/54_audit_helike_resonance_population_flux.py --cases-csv helike_local_state_validation_v03130/helike_local_state_cases.csv --solver-root . --print-summary
```

### `55_audit_helike_type50_line_pumping.py`

Run the v0.3.128+ API-backed type-50 line-pumping audit wrapper.

```bash
PYTHONPATH=src python examples/55_audit_helike_type50_line_pumping.py --cases-csv helike_local_state_validation_v03130/helike_local_state_cases.csv --solver-root . --xstar-source-root ../xstar --print-summary
```

### `56_reproduce_xstar_local_outputs.py`

Extract exact same-run XSTAR benchmark targets from `xout_abund1.fits` and `xout_lines1.fits` before any solver comparison. This is the recommended first check for C V, O VII, Mg XI, and Ca XIX local-state benchmarks.

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py --run-dir xstar_runs/helike_type69/o7_ne1e8 --ion "O VII" --out-dir xstar_o7_local_reproduction --print-summary
```

For the four-ion standard suite, use the built-in C V / O VII / Mg XI / Ca XIX case table:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py --standard-helike-suite --xstar-runs-root xstar_runs --out-dir helike_local_reproduction_suite --print-summary
```

For the physics benchmark, compare against the source-code-first local-state solver preset.  This reports XSTAR and solver `f/i/r`, `R`, `G`, and L2 values:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py --standard-helike-suite --xstar-runs-root xstar_runs --run-solver --solver-preset xstar-local-state --write-solver-products --out-dir helike_local_reproduction_suite_solver_v03154 --print-summary
```

The `--write-solver-products` flag preserves matrix products such as `xstar_like_element_solver_full_global_matrix_terms.csv` under `OUT_DIR/solver_products/`, so they can be handed directly to example 61.

If you want an editable case table, write it first and then run it:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py --write-standard-cases-csv helike_reproduction_cases.csv --xstar-runs-root xstar_runs --print-summary
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py --cases-csv helike_reproduction_cases.csv --out-dir helike_local_reproduction_suite --print-summary
```

## Recommended learning paths

- **New user:** 14 -> 05 -> 06 -> 01 -> 02 -> 03.
- **Atomic-data decoder developer:** 05 -> 01 -> 04 -> 07 -> 28 -> 31.
- **Emissivity/export user:** 02 -> 03 -> 09 -> 12.
- **O VII triplet development:** 13 -> 15 -> 17 -> 19 -> 21 -> 22 -> 24 -> 30.
- **Full-global/XSTAR validation:** 42 -> 43 -> 44 -> 51 -> 56 -> 52 -> 53 -> 54 -> 55.
- **Mg XI / Ca XIX validation:** 47 -> 48 -> 49 -> 50 -> 51 -> 56 -> 52 -> 55.

## Migration policy

As workflows stabilize, reusable logic should move from `examples/` into `src/xstar_atomic/`, leaving the examples as short command-line wrappers. See `docs/example_to_source_api_map.md` for the current migration plan. The most mature case is `examples/55_audit_helike_type50_line_pumping.py`, which is already a wrapper around `xstar_atomic.audit.type50_line_pumping(...)`.

## Development policy

These examples follow the source-code-first rule: no empirical triplet scale factors should be used as final physics, new physics starts as audit-only, solver-changing modes must be opt-in until same-run XSTAR validation is complete, and every solver-changing rate must carry source-code and local-context provenance.


## ATDB path environment variables

Examples that need the full XSTAR atomic database accept an explicit `/path/to/atdb.fits`.  Solver benchmark examples also use the resolver, so either environment variable works:

```bash
export XSTAR_ATDB=/path/to/xstar/data/atdb.fits
# or
export XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits
```

If `--atdb "$XSTAR_ATDB"` expands to an empty string, v0.3.138 treats it as not provided and falls back to the resolver. If neither `XSTAR_ATDB` nor `XSTAR_ATDB_FITS` is set, the resolver uses the configured `datapath` file, then package data.

### `58_plan_xstar_output_recreation.py`

Plan the source-code-parity work needed to recreate standard XSTAR FITS output products from an XSTAR command or `run_xstar.sh` file.  This is a planning/audit example, not yet a full XSTAR replacement.

```bash
PYTHONPATH=src python examples/58_plan_xstar_output_recreation.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_python_recreation_plan_o7 \
  --print-summary
```

### `59_create_xstar_live_state_skeleton.py`

Create the Python live-state skeleton that future source-code-parity loops must populate before writing XSTAR-like FITS products.  The skeleton explicitly carries `epi(:)`, `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc(1:2,continuum)`, `cfrac`, `vturbi`, zone-local `T/ne`, ion fractions, and level populations.

```bash
PYTHONPATH=src python examples/59_create_xstar_live_state_skeleton.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_live_state_skeleton_o7 \
  --print-summary
```

### `60_populate_xstar_live_state_from_detail.py`

Populate the Python live-state containers from an existing XSTAR detail-output directory.  This maps `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal4.fits`, and `xout_abund1.fits` into the Python fields `epi`, `bremsa`, `bremsint`, `tau0`, `tauc/dpthc`, `cfrac`, `vturbi`, local `T/ne`, ion fractions, and level populations.

```bash
PYTHONPATH=src python examples/60_populate_xstar_live_state_from_detail.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --out-dir xstar_detail_live_state_o7 \
  --print-summary
```

### `61_audit_xstar_detail_type50_rates.py`

Audit XSTAR detail-state type-50 rates directly from `xo01_detal2.fits` and `xo01_detal4.fits`.  This matches O VII He-like f/i/r line rows to ATDB type-50 records when `atdb.fits` is available, computes `ptmp1`, `ptmp2`, escaped decay, and photoexcitation with the XSTAR `calc_hmc_ion.f90`/`ucalc.f90` formulas, and writes CSV/JSON/Markdown rate diagnostics.

```bash
PYTHONPATH=src python examples/61_audit_xstar_detail_type50_rates.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_detail_type50_rate_audit_o7 \
  --print-summary
```

With an explicit ATDB and optional matrix-term CSV:

```bash
PYTHONPATH=src python examples/61_audit_xstar_detail_type50_rates.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --atdb "$XSTAR_ATDB" \
  --matrix-terms-csv xstar_like_element_solver_full_global_matrix_terms.csv \
  --out-dir xstar_detail_type50_rate_audit_o7 \
  --print-summary
```

To use the automatic handoff from example 56, point `--benchmark-dir` at a benchmark run created with `--write-solver-products`:

```bash
PYTHONPATH=src python examples/61_audit_xstar_detail_type50_rates.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --benchmark-dir helike_local_reproduction_suite_solver_v03154 \
  --out-dir xstar_detail_type50_rate_audit_o7_with_matrix \
  --print-summary
```

### `62_audit_xstar_local_matrix_parity.py`

Rank preserved full-global matrix terms by source-code rate family and show which families touch the He-like forbidden/intercombination/resonance upper levels. This is the next audit step after detail-state type-50 parity.

```bash
PYTHONPATH=src python examples/62_audit_xstar_local_matrix_parity.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --type50-audit-csv xstar_detail_type50_rate_audit_o7_with_matrix_v03156/xstar_detail_type50_rate_audit.csv \
  --out-dir xstar_local_matrix_parity_o7_v03157 \
  --print-summary
```

### `63_audit_xstar_triplet_rate_terms.py`

Rank individual full-global matrix terms in the He-like triplet population rows. This is a row-level companion to example 62: it identifies concrete records and matrix placements to use as the next source-code-equivalent detail-rate parity targets.

```bash
PYTHONPATH=src python examples/63_audit_xstar_triplet_rate_terms.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --out-dir xstar_triplet_rate_term_audit_o7_v03158 \
  --print-summary
```

To focus on one non-type-50 family, use a data-type filter:

```bash
PYTHONPATH=src python examples/63_audit_xstar_triplet_rate_terms.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --data-types 63 \
  --out-dir xstar_triplet_rate_term_audit_o7_type63_v03158 \
  --print-summary
```

### `86_audit_xstar_element_basis_remap.py`

Reconstructs a selected XSTAR compact element basis from the direct basis probe and remaps Python population rows by physical ion/local-level identity, including parent-continuum aliases.

### `89_audit_xstar_priority_matrix_closure.py`

Builds a source-code-derived compact matrix-closure manifest for the priority rows activated by example 88. It selects a common XSTAR `ucalc` occurrence rank, joins the corresponding four `calc_hmc_ion` matrix insertions, preserves shared parent-continuum aliases, and reports the exact rate families and counterpart compact rows required for native closure.


### `90_audit_xstar_priority_matrix_balance.py`

Aggregates the validated Fortran compact-matrix manifest from example 89 and evaluates steady-state row residuals against the captured XSTAR population vector. Use this before enabling native priority-subset matrix assembly.

```bash
PYTHONPATH=src python examples/90_audit_xstar_priority_matrix_balance.py \
  --priority-matrix-closure-audit xstar_priority_matrix_closure_o7_v03198_latest \
  --population-closure-parity-audit xstar_population_closure_parity_audit_o7_v03190_rank73 \
  --out-dir xstar_priority_matrix_balance_o7_v03199 \
  --print-summary
```

### `91_audit_xstar_priority_conditional_solve.py`

Solves the six activated compact rows while holding the remaining XSTAR population rows fixed. This validates the selected compact matrix and external source/sink closure before native-rate replacement.

```bash
PYTHONPATH=src python examples/91_audit_xstar_priority_conditional_solve.py \
  --priority-matrix-balance-audit xstar_priority_matrix_balance_o7_v03199 \
  --out-dir xstar_priority_conditional_solve_o7_v03201 \
  --print-summary
```

### `92_audit_xstar_priority_native_readiness.py`

Ranks the internal selected-block couplings and external right-hand-side families by population-weighted influence. It assigns conservative native implementation statuses and writes the staged port plan from probe-derived coefficients to native rate assembly.

```bash
PYTHONPATH=src python examples/92_audit_xstar_priority_native_readiness.py \
  --priority-conditional-solve-audit xstar_priority_conditional_solve_o7_v03201 \
  --priority-matrix-balance-audit xstar_priority_matrix_balance_o7_v03199 \
  --out-dir xstar_priority_native_readiness_o7_v03202 \
  --print-summary
```

## Advanced XSTAR source-parity and compact-basis audits

### `64_audit_xstar_type71_cascade_rates.py`

Audit type-71 cascade terms and their compact/full-global matrix placement.

```bash
PYTHONPATH=src python examples/64_audit_xstar_type71_cascade_rates.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --triplet-only \
  --out-dir xstar_type71_cascade_rate_audit_o7 \
  --print-summary
```

### `65_audit_xstar_type68_collision_rates.py`

Audit type-68 He-like collision terms and their matrix partners.

```bash
PYTHONPATH=src python examples/65_audit_xstar_type68_collision_rates.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --triplet-only \
  --out-dir xstar_type68_collision_rate_audit_o7 \
  --print-summary
```

### `66_audit_xstar_type53_source_sink_rates.py`

Audit type-53 photoionization/recombination source-sink topology in the preserved matrix.

```bash
PYTHONPATH=src python examples/66_audit_xstar_type53_source_sink_rates.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --triplet-only \
  --out-dir xstar_type53_source_sink_rate_audit_o7 \
  --print-summary
```

### `67_audit_xstar_type53_detail_phint53_radiation.py`

Recompute type-53 `phint53` rates from an XSTAR detail-continuum state and compare them with preserved matrix terms.

```bash
PYTHONPATH=src python examples/67_audit_xstar_type53_detail_phint53_radiation.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_type53_detail_phint53_radiation_o7 \
  --print-summary
```

### `68_audit_xstar_type53_detail_phint53_scale.py`

Determine whether the type-53 matrix/detail discrepancy is approximately scale-like or strongly record-dependent.

```bash
PYTHONPATH=src python examples/68_audit_xstar_type53_detail_phint53_scale.py \
  --phint53-audit-dir xstar_type53_detail_phint53_radiation_o7 \
  --out-dir xstar_type53_detail_phint53_scale_o7 \
  --print-summary
```

### `69_audit_xstar_type53_detail_phint53_bremsa_variants.py`

Compare several available detail-continuum reconstructions for the type-53 `phint53` integral.

```bash
PYTHONPATH=src python examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --fast \
  --out-dir xstar_type53_detail_phint53_bremsa_variants_o7 \
  --print-summary
```

### `70_audit_xstar_live_bremsa_source_path.py`

Trace the XSTAR source path that constructs the live high-resolution `bremsa` radiation field.

```bash
PYTHONPATH=src python examples/70_audit_xstar_live_bremsa_source_path.py \
  --xstar-source-root /path/to/xstar/xstar \
  --out-dir xstar_live_bremsa_source_path_audit_v03168 \
  --print-summary
```

### `71_audit_xstar_live_rate_grid_bremsa_path.py`

Trace the `bremsmap` path from the live transfer field to `epim`, `bremsam`, and `bremsint` used by `ucalc`.

```bash
PYTHONPATH=src python examples/71_audit_xstar_live_rate_grid_bremsa_path.py \
  --xstar-source-root /path/to/xstar/xstar \
  --out-dir xstar_live_rate_grid_bremsa_path_audit_v03169 \
  --print-summary
```

### `72_prepare_xstar_live_rate_grid_probe.py`

Write or validate the schema and helper products for an instrumented XSTAR live-rate-grid probe.

```bash
PYTHONPATH=src python examples/72_prepare_xstar_live_rate_grid_probe.py \
  --out-dir xstar_live_rate_grid_probe_v03170 \
  --print-summary
```

### `73_prepare_xstar_live_rate_grid_probe_patch.py`

Prepare source insertion snippets for capturing the live XSTAR rate grid after `bremsmap`.

```bash
PYTHONPATH=src python examples/73_prepare_xstar_live_rate_grid_probe_patch.py \
  --xstar-source-root /path/to/xstar/xstar \
  --out-dir xstar_live_rate_grid_probe_patch_v03171 \
  --print-summary
```

### `74_audit_xstar_type53_live_bremsam_phint53.py`

Recompute type-53 `phint53` rates from a captured live `epim`/`bremsam`/`bremsint` state.

```bash
PYTHONPATH=src python examples/74_audit_xstar_type53_live_bremsam_phint53.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv \
  --ion "O VII" \
  --out-dir xstar_type53_live_bremsam_phint53_o7 \
  --print-summary
```

### `75_audit_xstar_type53_live_bremsam_matrix_replacement.py`

Replace preserved type-53 matrix terms with live-rate-grid `phint53` results and compare the re-solved populations.

```bash
PYTHONPATH=src python examples/75_audit_xstar_type53_live_bremsam_matrix_replacement.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --live-phint53-audit-csv xstar_type53_live_bremsam_phint53_o7 \
  --out-dir xstar_type53_live_bremsam_matrix_replacement_o7 \
  --print-summary
```

### `76_audit_xstar_source_code_equivalent_local_closure.py`

Inventory remaining source-code-equivalent local matrix, population, parent, and superlevel closure requirements.

```bash
PYTHONPATH=src python examples/76_audit_xstar_source_code_equivalent_local_closure.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --xstar-source-root /path/to/xstar/xstar \
  --out-dir xstar_source_code_equivalent_local_closure_o7 \
  --print-summary
```

### `77_prepare_xstar_full_parity_probes.py`

Prepare or validate the direct `ucalc` record and `calc_hmc_ion` matrix-insertion probes.

```bash
PYTHONPATH=src python examples/77_prepare_xstar_full_parity_probes.py \
  --xstar-source-root /path/to/xstar/xstar \
  --out-dir xstar_full_parity_probe_o7 \
  --print-summary
```

### `78_audit_xstar_record_level_matrix_parity.py`

Join preserved Python matrix terms to direct XSTAR `ucalc` and matrix-insertion captures at a selected occurrence.

```bash
PYTHONPATH=src python examples/78_audit_xstar_record_level_matrix_parity.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --ucalc-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_ucalc_record_probe.csv \
  --matrix-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_calc_hmc_ion_matrix_probe.csv \
  --selection occurrence-rank \
  --occurrence-rank 73 \
  --out-dir xstar_record_level_matrix_parity_audit_o7_v03183_rank73 \
  --print-summary
```

### `79_audit_xstar_record_level_ucalc_matrix_replay.py`

Replay selected exact XSTAR `ucalc` branches into the preserved matrix and optionally re-solve it.

```bash
PYTHONPATH=src python examples/79_audit_xstar_record_level_ucalc_matrix_replay.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --record-level-audit-csv xstar_record_level_matrix_parity_audit_o7_v03183_rank73 \
  --replacement-mode blockers \
  --run-solver \
  --out-dir xstar_record_level_ucalc_matrix_replay_o7 \
  --print-summary
```

### `80_scan_xstar_record_level_ucalc_replay_families.py`

Replay one rate family at a time and rank each family by its effect on the solved populations.

```bash
PYTHONPATH=src python examples/80_scan_xstar_record_level_ucalc_replay_families.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --record-level-audit-csv xstar_record_level_matrix_parity_audit_o7_v03183_rank73 \
  --run-solver \
  --out-dir xstar_record_level_ucalc_replay_family_scan_o7 \
  --print-summary
```

### `81_diagnose_xstar_population_closure_from_replay_scan.py`

Use the family-replay scan to decide whether remaining differences are dominated by rates or by population/source closure.

```bash
PYTHONPATH=src python examples/81_diagnose_xstar_population_closure_from_replay_scan.py \
  --family-scan-csv xstar_record_level_ucalc_replay_family_scan_o7 \
  --ion "O VII" \
  --out-dir xstar_population_closure_diagnosis_o7 \
  --print-summary
```

### `82_prepare_xstar_population_closure_probe.py`

Prepare or validate direct pre/post-`msolvelucy` population-vector probe products.

```bash
PYTHONPATH=src python examples/82_prepare_xstar_population_closure_probe.py \
  --population-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv \
  --out-dir xstar_population_closure_probe_o7_v03189_validated \
  --print-summary
```

### `83_audit_xstar_population_closure_parity.py`

Compare the captured XSTAR compact population vector with preserved Python population rows.

```bash
PYTHONPATH=src python examples/83_audit_xstar_population_closure_parity.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --population-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv \
  --occurrence-rank 73 \
  --out-dir xstar_population_closure_parity_audit_o7_v03190_rank73 \
  --print-summary
```

### `84_diagnose_xstar_population_basis_mapping.py`

Rank the XSTAR compact rows missing from the then-current Python basis and diagnose incorrect sequential mapping.

```bash
PYTHONPATH=src python examples/84_diagnose_xstar_population_basis_mapping.py \
  --population-closure-parity-audit xstar_population_closure_parity_audit_o7_v03190_rank73 \
  --out-dir xstar_population_basis_mapping_o7_v03191 \
  --print-summary
```

### `85_prepare_xstar_element_basis_probe.py`

Prepare or validate direct `calc_hmc_element` compact-basis topology probes.

```bash
PYTHONPATH=src python examples/85_prepare_xstar_element_basis_probe.py \
  --element-basis-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_element_basis_probe.csv \
  --out-dir xstar_element_basis_probe_o7_v03192_validated \
  --print-summary
```

### `86_audit_xstar_element_basis_remap.py`

Reconstruct the exact compact element basis and remap Python rows by physical ion/local-level identity.

```bash
PYTHONPATH=src python examples/86_audit_xstar_element_basis_remap.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --element-basis-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_element_basis_probe.csv \
  --population-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv \
  --basis-solve-call-id 219 \
  --out-dir xstar_element_basis_remap_audit_o7_v03193 \
  --print-summary
```

### `87_build_xstar_full_element_basis_scaffold.py`

Create an explicit full compact-element scaffold and population-ranked missing-row priorities.

```bash
PYTHONPATH=src python examples/87_build_xstar_full_element_basis_scaffold.py \
  --element-basis-remap-audit xstar_element_basis_remap_audit_o7_v03193 \
  --out-dir xstar_full_element_basis_scaffold_o7_v03194 \
  --print-summary
```

### `88_expand_xstar_priority_element_basis.py`

Activate the smallest missing-row subset needed to reach a requested captured-population coverage.

```bash
PYTHONPATH=src python examples/88_expand_xstar_priority_element_basis.py \
  --full-element-basis-scaffold xstar_full_element_basis_scaffold_o7_v03194 \
  --target-population-coverage 0.999999 \
  --out-dir xstar_priority_basis_expansion_o7_v03195 \
  --print-summary
```

### `89_audit_xstar_priority_matrix_closure.py`

Build the complete direct-Fortran matrix manifest touching the activated compact rows.

```bash
PYTHONPATH=src python examples/89_audit_xstar_priority_matrix_closure.py \
  --priority-basis-expansion xstar_priority_basis_expansion_o7_v03195 \
  --ucalc-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_ucalc_record_probe.csv \
  --matrix-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_calc_hmc_ion_matrix_probe.csv \
  --occurrence-rank -1 \
  --out-dir xstar_priority_matrix_closure_o7_v03198_latest \
  --print-summary
```

### `93_audit_xstar_type51_native_parity.py`

Evaluate selected type-51 records natively and compare `ans1`, `ans2`, and every compact insertion with XSTAR.

```bash
PYTHONPATH=src python examples/93_audit_xstar_type51_native_parity.py \
  --priority-matrix-closure-audit xstar_priority_matrix_closure_o7_v03198_latest \
  --atdb /path/to/xstar/data/atdb.fits \
  --out-dir xstar_type51_native_parity_o7_v03203 \
  --print-summary
```

### `94_integrate_xstar_priority_native_type51.py`

Replace every validated type-51 term whose matrix row belongs to the selected conditional system, classify reciprocal external-row parity terms as out of scope, and rerun row balance plus the conditional solve while retaining explicit probe-backed coefficients for all other families.

```bash
PYTHONPATH=src python examples/94_integrate_xstar_priority_native_type51.py \
  --priority-matrix-balance-audit xstar_priority_matrix_balance_o7_v03199 \
  --type51-native-parity-audit xstar_type51_native_parity_o7_v03203 \
  --out-dir xstar_priority_native_type51_integration_o7_v03205 \
  --print-summary
```

### `95_audit_xstar_type50_type71_native_parity.py`

Evaluate selected type-50 and type-71 records natively, compare both `ucalc` rate branches and every compact insertion with XSTAR, and classify selected-internal, fixed-external, and external-row terms. Type-50 pumping requires an explicit same-capture radiation context unless it is exactly zero.

```bash
PYTHONPATH=src python examples/95_audit_xstar_type50_type71_native_parity.py \
  --priority-matrix-closure-audit xstar_priority_matrix_closure_o7_v03198_latest \
  --atdb /path/to/xstar/data/atdb.fits \
  --out-dir xstar_type50_type71_native_parity_o7_v03206 \
  --print-summary
```

For a partial-covering run, also supply a CSV containing `capture_index`, `record`, and `bremsa_nb1`:

```bash
  --type50-radiation-context-csv xstar_type50_same_capture_radiation.csv
```

### `96_integrate_xstar_priority_native_type50_type71.py`

Replace every validated selected-row type-50/type-71 term after the native type-51 gate, including selected-to-external RHS contributions, then recompute row balance and the conditional solve while preserving all remaining families as explicitly probe-backed.

```bash
PYTHONPATH=src python examples/96_integrate_xstar_priority_native_type50_type71.py \
  --priority-native-type51-integration-audit xstar_priority_native_type51_integration_o7_v03205 \
  --type50-type71-native-parity-audit xstar_type50_type71_native_parity_o7_v03206 \
  --out-dir xstar_priority_native_type50_type71_integration_o7_v03206 \
  --print-summary
```


### `97_audit_xstar_type53_live_native_parity.py`

Evaluate XSTAR type 53 from an explicitly selected live reduced-grid radiation state, compare `ans1..ans6` and every compact insertion, and report separate rate, heating/cooling, matrix, external-RHS, and opacity/RRC readiness.

```bash
PYTHONPATH=src python examples/97_audit_xstar_type53_live_native_parity.py \
  --priority-matrix-closure-audit xstar_priority_matrix_closure_o7_v03198_latest \
  --live-rate-grid-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv \
  --live-rate-grid-state last \
  --live-density-field-semantics electron_density \
  --atdb /path/to/xstar/data/atdb.fits \
  --out-dir xstar_type53_live_native_parity_o7_v03208 \
  --print-summary
```

### `98_integrate_xstar_priority_native_type53.py`

Replace every validated selected-row type-53 term after the native type-51/type-50/type-71 gate, including fixed-external RHS contributions, and rerun row balance plus the conditional solve.

```bash
PYTHONPATH=src python examples/98_integrate_xstar_priority_native_type53.py \
  --priority-native-type50-type71-integration-audit xstar_priority_native_type50_type71_integration_o7_v03207 \
  --type53-live-native-parity-audit xstar_type53_live_native_parity_o7_v03208 \
  --out-dir xstar_priority_native_type53_integration_o7_v03208 \
  --print-summary
```


### `99_inventory_xstar_source_port.py`

Inventory the original XSTAR Fortran source tree or tarball, write file/routine/call-edge tables, and initialize the machine-readable Python translation ledger.  This is the foundation for the v0.4 source-file-by-source-file port.

```bash
PYTHONPATH=src python examples/99_inventory_xstar_source_port.py \
  --source-tar xstar_source.tar.gz \
  --out-dir xstar_python_source_port_inventory_v0400 \
  --print-summary
```

### `100_port_xstar_atomic_database.py`

Run the first complete source-port subsystem, translating XSTAR
`readtbl.f90` and the active pointer-construction path in `setptrs.f90`.  The
command writes a reusable compressed pointer cache and element/ion/rate-family
summaries while retaining the large packed FITS vectors as memory-mapped data.

```bash
PYTHONPATH=src python examples/100_port_xstar_atomic_database.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --out-dir xstar_atomic_database_port_v041 \
  --print-summary
```

### `101_port_xstar_ucalc.py`

Run the complete source-faithful `ucalc.f90` subsystem against a packed XSTAR
atomic database.  The command writes the 1--102 branch catalog, counts active
ATDB records by data/rate type, and performs one index-only packed-record decode
per active data type.

```bash
PYTHONPATH=src python examples/101_port_xstar_ucalc.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --out-dir xstar_ucalc_source_port_v042 \
  --print-summary
```

The command validates complete source control flow and packed-record decoding;
it does not claim that all records were numerically evaluated without a full
zone plasma/radiation context.
### `102_port_xstar_element_equilibrium.py`

Run the complete translated element statistical-equilibrium subsystem:
`levwkelement -> calc_hmc_ion -> calc_hmc_element -> msolvelucy`.  The command
builds the exact compact basis, preserves parent-continuum aliases, traverses
all records through the source pointer tables, assembles raw and normalized
matrices plus RHS, and solves the complete element population vector.  For
oxygen stages O III--O VIII the target contains 607 compact rows.

```bash
PYTHONPATH=src python examples/102_port_xstar_element_equilibrium.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --element-z 8 --min-ion-stage 3 --max-ion-stage 8 \
  --temperature-k 1.0e6 \
  --hydrogen-density-cm3 1.0e8 \
  --electron-fraction-xee 1.0 \
  --live-rate-grid-probe-csv /path/to/xstar_live_rate_grid_probe.csv \
  --xstar-run-dir /path/to/xstar_run \
  --escape-zone last \
  --escape-detail-policy source_sparse_reconstruct \
  --write-derived-escape-npz xstar_o7_escape_state.npz \
  --out-dir xstar_o_element_equilibrium_v046 \
  --print-summary
```

Use `--assume-optically-thin` only for a genuinely optically thin model or a
controlled smoke test.  In strict mode, missing radiation or escape state
blocks readiness rather than falling back to old probe coefficients.

v0.4.6 also reproduces XSTAR's source-zero type-63 branches and the
`msolvelucy` `min(ipmat, indb)` endpoint alias. The summary reports
`n_source_ipmat_endpoint_clamps`; raw and clamped rows are retained in the
matrix-term CSV.


### `103_build_xstar_escape_state.py`

Build the exact line and RRC optical-depth arrays consumed by `calc_hmc_ion`.
The source products are `xo01_detal2.fits` for `tau0(1:2,line)` and
`xo01_detal3.fits` for `tauc(1:2,rrc)`.

```bash
PYTHONPATH=src python examples/103_build_xstar_escape_state.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --xstar-run-dir /path/to/xstar_run \
  --zone last \
  --out-npz xstar_o7_escape_state.npz \
  --out-dir xstar_escape_state_v044 \
  --print-summary
```

The default command-line policy reconstructs sparse detail history through the selected zone and zero-fills indices never emitted because they remained below the XSTAR writer thresholds. Use `--detail-policy strict_selected_zone` to preserve absent rows as unavailable, or `--allow-missing-as-zero` only when zero optical depth is independently intended.


### `104_prepare_xstar_msolvelucy_state_probe.py`

Write a free-form Fortran helper and five source-local insertion snippets for a debug XSTAR build. The resulting CSVs can be passed to example 102 with `--xstar-msolvelucy-state-probe-dir` to compare every outer, condensed-superlevel, and fixed-point state against the XSTAR-before-seeded Python solve.

```bash
PYTHONPATH=src python examples/104_prepare_xstar_msolvelucy_state_probe.py \
  --out-dir xstar_msolvelucy_state_probe_v047 \
  --print-summary
```

### `105_port_xstar_calc_hmc_all_fixed_state.py`

Run the fixed-temperature/fixed-electron-fraction `calc_hmc_all` path through the translated pre-matrix sequence, source-derived ion limits, and the validated multilevel element solver. The output keeps preliminary `pirt/rrrt` distinct from post-solve `stotg/atotg`, writes per-record first-pass diagnostics, and can compare directly with the bounded XSTAR probe.

```bash
PYTHONPATH=src python examples/105_port_xstar_calc_hmc_all_fixed_state.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --element-z 8 --min-ion-stage 3 --max-ion-stage 8 \
  --ion-stage-selection source \
  --temperature-k 1.0e6 \
  --hydrogen-density-cm3 1.0e8 \
  --electron-fraction-xee 1.0 \
  --live-rate-grid-probe-csv /path/to/xstar_live_rate_grid_probe.csv \
  --escape-npz /path/to/xstar_o7_escape_state.npz \
  --xstar-population-probe-csv /path/to/xstar_population_closure_probe.csv \
  --xstar-population-solve-call-id 219 \
  --population-probe-runtime-policy use \
  --xstar-calc-hmc-probe-dir /path/to/xstar_probe_run \
  --out-dir xstar_o_calc_hmc_all_fixed_state_v0434 \
  --print-summary
```

Omit `--xstar-calc-hmc-probe-dir` before the instrumented XSTAR run is available. Use `--ion-stage-selection explicit` only for controlled regression against a fixed stage subset. `complete_fixed_state_ready` remains false until all-element charge closure and `comp2 -> freef -> bremem -> heatf` are complete.

### `106_prepare_xstar_calc_hmc_all_probe.py`

Write the bounded, diagnostic-only nine-hook Fortran helper and source-local insertion snippets for `calc_hmc_ion.f90`, `calc_hmc_element.f90`, `msolvelucy.f90`, and `calc_hmc_all.f90`. The helper captures the pre-matrix and pre-continuum state, complete same-call input `xileve` vector, exact mutable `leveltemp` reads for type 49/53/99 rate-7 records, same-call matrix, thermal families, synchronized final `msolvelucy` matrix/`x`/`xo` products, and the exact post-`comp2` continuum grid and Compton outputs. `XSTAR_ATOMIC_HMC_TARGET_CALL` selects an exact `calc_hmc_all` invocation; `XSTAR_ATOMIC_HMC_TARGET_RECORD` can bound the exact leveltemp trace to one record. The default detailed target is oxygen (`XSTAR_ATOMIC_HMC_TARGET_ELEMENT=8`); set `XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0` to capture every positive-abundance element for the selected call.

```bash
PYTHONPATH=src python examples/106_prepare_xstar_calc_hmc_all_probe.py \
  --out-dir xstar_calc_hmc_all_probe_v0433 \
  --print-summary
```

### `107_audit_v0434_oxygen_corrections.py`

Count the six bounded discrepancy groups isolated from the production v0.4.33
oxygen diagnosis. Running it on the v0.4.33 output must reproduce the target
counts `35/349/205/196/7/2`; running it on the v0.4.34 output requires all six
counts to be zero before oxygen acceptance can pass.

```bash
PYTHONPATH=src python examples/107_audit_v0434_oxygen_corrections.py \
  xstar_o_calc_hmc_all_fixed_state_v0434 \
  --json xstar_o_calc_hmc_all_fixed_state_v0434/v0434_correction_gates.json
```


### `108_port_xstar_calc_hmc_all_all_elements_fixed_state.py`

Run the complete source-order pre-continuum element loop for every element with
positive abundance in a captured `calc_hmc_all` call. The accepted v0.4.34
oxygen call-73 result is mandatory and is checked before execution. With the
existing oxygen-focused probe, `use-available` replays the exact oxygen seed and
uses translated autonomous initialization for H and He.

```bash
PYTHONPATH=src python \
  examples/108_port_xstar_calc_hmc_all_all_elements_fixed_state.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --temperature-k 76655.18557758832 \
  --hydrogen-density-cm3 1.0e8 \
  --electron-fraction-xee 1.2046560563936872 \
  --live-rate-grid-probe-csv /path/to/xstar_live_rate_grid_probe.csv \
  --live-rate-grid-state last \
  --escape-npz /path/to/xstar_o7_escape_state.npz \
  --xstar-population-probe-csv /path/to/xstar_population_closure_probe.csv \
  --xstar-population-solve-call-id 219 \
  --population-probe-runtime-policy check \
  --xstar-calc-hmc-probe-dir /path/to/call73_probe_directory \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir /path/to/xstar_o_calc_hmc_all_fixed_state_v0434 \
  --initial-population-policy use-available \
  --out-dir xstar_all_calc_hmc_all_fixed_state_v0435 \
  --print-summary
```

For a fresh complete detailed all-element capture, use the v0.4.36-packaged
eight-hook helper (functionally unchanged from v0.4.35) and run XSTAR with:

```bash
export XSTAR_ATOMIC_HMC_TARGET_CALL=73
export XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0
```

Then rerun example 108 with `--initial-population-policy require-all`. Require
`all_element_detailed_parity_probe_ready=True` and close all-element summary,
global-array, matrix, final-solver, and thermal parity before beginning `comp2`.

### `109_validate_v0436_hydrogen_all_element.py`

After rerunning example 108 with v0.4.36, validate the four H I type-62
records, the 16 restored matrix terms, all 718 initial populations, the H I
active solver rows, thermal families, and the new all-element acceptance gate:

```bash
PYTHONPATH=src python examples/109_validate_v0436_hydrogen_all_element.py \
  xstar_all_calc_hmc_all_fixed_state_v0436_allprobe \
  --print-summary
```

The required final line is:

```text
v0436_hydrogen_all_element_validation_ready=True
```

### `110_validate_v0437_type77_all_element.py`

Validate the v0.4.37 type-77 all-element acceptance.

After rerunning example 108 with v0.4.37, validate the literal H/He type-77
sub-eV source-zero gate and the complete H/He/O pre-continuum acceptance:

```bash
PYTHONPATH=src python examples/110_validate_v0437_type77_all_element.py \
  xstar_all_calc_hmc_all_fixed_state_v0437_allprobe \
  --print-summary
```

The required final line is:

```text
v0437_type77_all_element_validation_ready=True
```

### `111_validate_v0438_xiin_final_vector.py`

Validate the v0.4.38 distinction between returned final-`x` ion fractions and
final-outer-start `xtot` diagnostics after rerunning example 108:

```bash
PYTHONPATH=src python examples/111_validate_v0438_xiin_final_vector.py \
  xstar_all_calc_hmc_all_fixed_state_v0438_allprobe \
  --print-summary
```

The required final line is:

```text
v0438_xiin_final_vector_validation_ready=True
```

### `112_port_xstar_comp2.py`

Validate the source-faithful `comp2 -> cmpfnc -> hunt3` translation against the
new same-call XSTAR post-`comp2` probe. The command also requires the frozen
oxygen and H/He/O pre-continuum regression gates:

```bash
PYTHONPATH=src python examples/112_port_xstar_comp2.py \
  --xstar-comp2-probe-dir /path/to/new_call73_nine_hook_probe \
  --xstar-calc-hmc-call-id 73 \
  --coheat-data /path/to/xstar/data/coheat.dat \
  --oxygen-call73-regression-dir \
    /path/to/oxygen_call73_v0434_acceptance/xstar_o_calc_hmc_all_fixed_state_v0434 \
  --all-element-v0438-regression-dir \
    /path/to/xstar_all_calc_hmc_all_fixed_state_v0438_allprobe \
  --out-dir xstar_comp2_call73_v0439 \
  --print-summary
```

The required final line is:

```text
v0439_comp2_acceptance_ready=True
```

The same comparison can be executed as part of example 108 by adding
`--xstar-comp2-probe-dir` and `--coheat-data`. `freef`, `bremem`, and `heatf`
remain deferred until this Compton gate passes.


### `113_port_xstar_freef.py`

Validates the source-faithful `freef.f90` translation against the eleven-hook
call-73 XSTAR probe. It compares the exact per-bin free--free opacity increment,
the in-place `opakc` mutation, and source-order `htfreef`, while requiring the
frozen oxygen, H/He/O, and v0.4.39 Compton regressions.

```bash
PYTHONPATH=src python examples/113_port_xstar_freef.py \
  --xstar-calc-hmc-probe-dir /path/to/v0440_call73_probe \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir /path/to/v0434_oxygen \
  --all-element-v0438-regression-dir /path/to/v0438_all_elements \
  --comp2-v0439-regression-dir /path/to/v0439_comp2 \
  --out-dir xstar_freef_call73_v0440 \
  --print-summary
```


### `114_port_xstar_bremem.py`

Validates the source-faithful `bremem.f90` translation against the thirteen-hook
call-73 XSTAR probe. It compares the exact per-bin bremsstrahlung emissivity,
verifies that the incoming `brcems` workspace is cleared before population,
and confirms that the post-`freef` `opakc` workspace is unchanged. Acceptance
also requires the frozen oxygen, H/He/O, v0.4.39 Compton, and v0.4.40 free--free
regressions.

```bash
PYTHONPATH=src python examples/114_port_xstar_bremem.py \
  --xstar-calc-hmc-probe-dir /path/to/v0441_call73_probe \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir /path/to/v0434_oxygen \
  --all-element-v0438-regression-dir /path/to/v0438_all_elements \
  --comp2-v0439-regression-dir /path/to/v0439_comp2 \
  --freef-v0440-regression-dir /path/to/v0440_freef \
  --out-dir xstar_bremem_call73_v0441 \
  --print-summary
```

The required final line is:

```text
v0441_bremem_acceptance_ready=True
```

`heatf` remains deferred until this gate passes.

### `115_port_xstar_heatf.py`

Validates the source-faithful `heatf.f90` translation against the sixteen-hook
call-73 XSTAR probe. It compares the source-order trapezoidal bremsstrahlung
cooling integral, Compton heating/cooling conversion, free--free heating and
bremsstrahlung cooling accumulation, both primary and secondary thermal totals,
and `hmctot`. Acceptance also requires the frozen oxygen, H/He/O, v0.4.39
Compton, v0.4.40 free--free, and v0.4.41 bremsstrahlung regressions.

```bash
PYTHONPATH=src python examples/115_port_xstar_heatf.py \
  --xstar-calc-hmc-probe-dir /path/to/v0442_call73_probe \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir /path/to/v0434_oxygen \
  --all-element-v0438-regression-dir /path/to/v0438_all_elements \
  --comp2-v0439-regression-dir /path/to/v0439_comp2 \
  --freef-v0440-regression-dir /path/to/v0440_freef \
  --bremem-v0441-regression-dir /path/to/v0441_bremem \
  --out-dir xstar_heatf_call73_v0442 \
  --print-summary
```

The required final line is:

```text
v0442_heatf_acceptance_ready=True
```

After this gate passes, the next bounded target is complete fixed-state
`calc_hmc_all` thermal/charge parity, followed by `dsec`.

### `116_validate_xstar_calc_hmc_all_complete_fixed_state.py`

Executes the complete translated fixed-state `calc_hmc_all` chain and compares
its final thermal and charge state against the existing seventeen-hook
v0.4.43 call-73 XSTAR probe. v0.4.44 gives the pre-continuum element-loop
totals explicit ownership and reruns the current same-call pre-continuum,
`comp2`, `freef`, `bremem`, and `heatf` comparisons while requiring every
frozen regression through v0.4.42. No XSTAR rebuild is required.

```bash
PYTHONPATH=src python   examples/116_validate_xstar_calc_hmc_all_complete_fixed_state.py   --atdb /media/linux/mhd/xstar/xstar/data/atdb.fits   --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz   --temperature-k 76655.18557758832   --hydrogen-density-cm3 1.0e8   --electron-fraction-xee 1.2046560563936872   --live-rate-grid-probe-csv     xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv   --live-rate-grid-state last   --escape-npz xstar_o7_escape_state_v045.npz   --xstar-population-probe-csv     xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv   --xstar-population-solve-call-id 219   --population-probe-runtime-policy use   --xstar-calc-hmc-probe-dir     xstar_runs/helike_type69/o7_ne1e8_all_elements_v0443_complete   --xstar-calc-hmc-call-id 73   --coheat-data /media/linux/mhd/xstar/xstar/data/coheat.dat   --oxygen-call73-regression-dir     oxygen_call73_v0434_acceptance/xstar_o_calc_hmc_all_fixed_state_v0434   --all-element-v0438-regression-dir     xstar_all_calc_hmc_all_fixed_state_v0438_allprobe   --comp2-v0439-regression-dir xstar_comp2_call73_v0439   --freef-v0440-regression-dir xstar_freef_call73_v0440   --bremem-v0441-regression-dir xstar_bremem_call73_v0441   --heatf-v0442-regression-dir xstar_heatf_call73_v0442   --initial-population-policy require-all   --out-dir xstar_calc_hmc_all_complete_call73_v0444   --print-summary
```

The required final line is:

```text
v0444_complete_fixed_state_acceptance_ready=True
```

Only after this gate passes should development proceed to `dsec`.

### `117_port_xstar_dsec.py`

Runs the translated `dsec.f90` control path on a deterministic synthetic
heating/charge function, or compares a saved Python trajectory with an
instrumented XSTAR trajectory. The synthetic mode validates branch semantics;
it is not a physical XSTAR acceptance run.

```bash
PYTHONPATH=src python examples/117_port_xstar_dsec.py synthetic \
  --out-dir dsec_synthetic_v0445
```

After an instrumented physical run and a Python run using the same dynamic
local state:

```bash
PYTHONPATH=src python examples/117_port_xstar_dsec.py compare \
  --python-trajectory /path/to/python_dsec_products \
  --xstar-trajectory /path/to/xstar_dsec_trajectory_probe.csv \
  --xstar-dsec-call-id 1 \
  --out-dir dsec_trajectory_parity_v0445
```

### `118_prepare_xstar_dsec_probe.py`

Writes the diagnostic-only Fortran helper and twelve insertion snippets for
`dsec.f90`:

```bash
PYTHONPATH=src python examples/118_prepare_xstar_dsec_probe.py \
  --out-dir xstar_dsec_probe_v0445
```

Compile the helper before `dsec.f90`, apply the snippets, remove stale probe
CSV files, set `XSTAR_ATOMIC_DSEC_TARGET_CALL`, and rebuild XSTAR. The physical
v0.4.45 acceptance flag must remain false until the resulting trajectory and
the final complete `calc_hmc_all` state pass parity while the frozen v0.4.44
gate remains true.

### `119_validate_xstar_dsec_complete.py`

Runs the real translated `calc_hmc_all` inside every stateful `dsec` trial,
compares the complete Python branch trajectory with one instrumented XSTAR
`dsec` call, then performs the additional post-`dsec` `calc_hmc_all` call made
by `xstarcalc.f90` and compares it with the accepted call-73 fixed-state
reference.

```bash
PYTHONPATH=src python examples/119_validate_xstar_dsec_complete.py \
  --atdb /media/linux/mhd/xstar/xstar/data/atdb.fits \
  --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz \
  --live-rate-grid-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv \
  --live-rate-grid-state last \
  --escape-npz xstar_o7_escape_state_v045.npz \
  --xstar-calc-hmc-probe-dir xstar_runs/helike_type69/o7_ne1e8_all_elements_v0443_complete \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir oxygen_call73_v0434_acceptance/xstar_o_calc_hmc_all_fixed_state_v0434 \
  --xstar-dsec-trajectory xstar_runs/helike_type69/o7_ne1e8_dsec_v0445/xstar_dsec_trajectory_probe.csv \
  --xstar-dsec-call-id 1 \
  --coheat-data /media/linux/mhd/xstar/xstar/data/coheat.dat \
  --initial-population-policy require-all \
  --out-dir xstar_dsec_complete_v0446 \
  --print-summary
```

Use `--prepare-only` first to resolve and validate all input products without
running the expensive atomic calculation. The required physical gate is:

```text
v0445_bounded_dsec_acceptance_ready=True
```

A false gate is a diagnostic result. Inspect the first failure in
`xstar_dsec_trajectory_parity.csv`; do not compare the synthetic example-117
trajectory with the physical XSTAR trajectory.

## v0.4.48 call-correlated dsec validation

- `119_validate_xstar_dsec_complete.py` now consumes distinct correlated input
  and post-dsec `calc_hmc_all` states and supports `--maximum-evaluations` and
  `--progress`.
- `120_prepare_xstar_dsec_matching_probe.py` writes the shared call-correlation,
  complete matching-state `calc_hmc_all`, and dsec trajectory/thermal probe
  bundle required for the production rerun.


## v0.4.48-v0.4.51 matching and transition probes

### `120_prepare_xstar_dsec_matching_probe.py`

Generates the shared call-correlation helper, the complete `calc_hmc_all`
matching-state probe, the `dsec` trajectory/thermal probe, and the required
Fortran insertion snippets:

```bash
PYTHONPATH=src python examples/120_prepare_xstar_dsec_matching_probe.py \
  --target-dsec-call 1 \
  --target-evaluation 1 \
  --target-phase dsec_input_and_post \
  --out-dir xstar_dsec_matching_probe_v0448
```

Use a separate generated/captured probe directory for a later selected
evaluation such as evaluation 2.

### `121_validate_xstar_dsec_transition_state.py`

Runs the physical translated `dsec` prefix and compares the complete Python
state entering a selected later evaluation with the corresponding captured
XSTAR state:

```bash
PYTHONPATH=src python examples/121_validate_xstar_dsec_transition_state.py \
  --atdb /path/to/atdb.fits \
  --xstar-dsec-trajectory /path/to/xstar_dsec_trajectory_probe.csv \
  --xstar-call-correlation /path/to/main/xstar_dsec_calc_hmc_all_call_correlation.csv \
  --xstar-dsec-input-probe-dir /path/to/main \
  --xstar-post-dsec-probe-dir /path/to/main \
  --xstar-transition-input-probe-dir /path/to/evaluation2 \
  --xstar-transition-call-correlation /path/to/evaluation2/xstar_dsec_calc_hmc_all_call_correlation.csv \
  --xstar-transition-evaluation-index 2 \
  --xstar-dsec-thermal-decomposition /path/to/main/xstar_dsec_thermal_decomposition_probe.csv \
  --oxygen-call73-regression-dir /path/to/oxygen_call73_reference \
  --coheat-data /path/to/coheat.dat \
  --maximum-evaluations 2 \
  --out-dir xstar_dsec_transition_v0451_eval2 \
  --print-summary
```

## v0.4.52 repeated-`dsec` state ownership and causality scan

### `122_validate_xstar_dsec_transition_causality.py`

Runs four controlled two-evaluation calculations against the same correlated
XSTAR evaluation-2 entry state:

```text
A_current_v0451        legacy selected writeback + carried leveltemp
B_zero_leveltemp_only  legacy selected writeback + per-call leveltemp reset
C_dense_alias_only     dense native alias writeback + carried leveltemp
D_production_both      dense native alias writeback + per-call leveltemp reset
```

All physical/probe arguments accepted by examples 119/121 are passed through.
The wrapper owns `--out-dir`, forces `--maximum-evaluations 2`, and writes
`xstar_dsec_transition_causality_scan.csv/.json/.md`.  The ordinary physical
runner defaults to mode D through:

```text
--global-writeback-mode dense-source
--leveltemp-lifecycle reset-per-call
```

No XSTAR rebuild is required; reuse the v0.4.48 instrumented executable and the
v0.4.51 evaluation-2 input-state probe products.

```bash
PYTHONPATH=src python examples/122_validate_xstar_dsec_transition_causality.py \
  [the example-121 physical/probe arguments] \
  --out-dir xstar_dsec_causality_v0452 \
  --print-summary
```


## v0.4.53 exact XSTAR-seeded evaluation-2 replay

### `123_validate_xstar_dsec_exact_transition_replay.py`

Runs the selected later `dsec` evaluation twice while Python continues to
compute all rates, matrices, level populations, and thermal totals:

```text
P_python_transition
    Python evaluation-1 output -> Python evaluation 2

X_xstar_seeded_transition
    exact captured XSTAR evaluation-2 call-entry state -> Python evaluation 2
```

The second mode replaces only the call-entry runtime and mutable state:
`xilevg`, `bilevg`, `rnisg`, `leveltemp`, radiation, escape arrays, continuum
scratch workspaces, and geometry.  It never injects an XSTAR matrix, solved
population vector, rate, or cooling coefficient.

Use the same physical/probe arguments as example 122 and change only the
wrapper and output directory:

```bash
PYTHONPATH=src python examples/123_validate_xstar_dsec_exact_transition_replay.py \
  [the example-122 physical/probe arguments] \
  --out-dir xstar_dsec_exact_replay_v0453 \
  --print-summary
```

The wrapper writes aggregate P-versus-X thermal products and
`xstar_dsec_transition_exact_replay_elements.csv`, sorted by the absolute
change in element cooling.  No XSTAR rebuild or new XSTAR run is required.
`replay-exact` is diagnostic-only; production retains dense native writeback
and per-call `leveltemp` reset.

## v0.4.54 exact evaluation-2 internal parity

### `124_validate_xstar_dsec_evaluation2_internals.py`

The v0.4.53 exact replay verified the complete captured evaluation-2 call-entry
state but retained essentially the entire XSTAR cooling discrepancy.  Example
124 therefore runs the existing detailed same-call `calc_hmc_all` parity audit
on the exact-replayed Python evaluation 2.

The audit compares, in source order:

```text
active ion selection and pre-matrix rates
full matrix topology and coefficients
active-row matrix closure
initial Lucy population vector
final Lucy matrix and active populations
outer-iteration entry populations and source-order xtot
thermal data-type and rate-type families
element heating/cooling arrays and pre-continuum summary
```

Use the same arguments and probe directories as example 123:

```bash
PYTHONPATH=src python examples/124_validate_xstar_dsec_evaluation2_internals.py \
  [the example-123 physical/probe arguments] \
  --out-dir xstar_dsec_eval2_internals_v0454 \
  --print-summary
```

The wrapper forces two evaluations, production dense writeback, per-call
`leveltemp` reset, exact XSTAR evaluation-2 input replay, and the internal
comparison.  It writes the detailed audit under
`evaluation_internal_parity/` and the aggregate
`xstar_dsec_evaluation2_internal_parity_summary.json/.md`.  The first failed
layer is classified without allowing tiny inactive matrix-coefficient
differences to preempt an otherwise passing active matrix closure.

No XSTAR rebuild or new XSTAR execution is required when the existing
`o7_ne1e8_dsec_v0451_eval2` directory contains the same-call matrix, Lucy, and
thermal-family probe CSVs.
## v0.4.55 terminal compact-continuum seed causality

### `125_validate_xstar_dsec_terminal_continuum_seed.py`

The v0.4.54 audit found that the only pre-`msolvelucy` population mismatch for
each of H, He, and O is the final compact continuum/normalization row.  XSTAR
sets this row to exact zero immediately before the solve.  Example 125 runs two
exact-replay evaluation-2 modes:

```text
A_legacy_global_terminal_seed
B_source_zero_terminal_seed
```

Use the same arguments and probe directories as example 124:

```bash
PYTHONPATH=src python examples/125_validate_xstar_dsec_terminal_continuum_seed.py \
  [the example-124 physical/probe arguments] \
  --out-dir xstar_dsec_terminal_seed_v0455 \
  --print-summary
```

The wrapper writes `xstar_dsec_terminal_continuum_seed_scan.csv/.json/.md` and
advances the first-failure diagnosis from solver entry through final Lucy
populations, iteration history, source `xtot`, thermal families, element
accumulation, or complete primary thermal parity.  No XSTAR rebuild or new run
is required.


## v0.4.56 natural source-zero four-evaluation prefix

### `126_validate_xstar_dsec_source_zero_prefix.py`

```bash
PYTHONPATH=src python examples/126_validate_xstar_dsec_source_zero_prefix.py \
  [the same ATDB, dsec trajectory, transition, and oxygen regression options \
   used by example 125] \
  --out-dir xstar_dsec_source_zero_prefix_v0456 \
  --print-summary
```

The wrapper forces production state semantics (`dense-source`, `reset-per-call`,
`source-zero`), disables exact transition replay, and runs four natural
`calc_hmc_all` evaluations.  It compares the natural evaluation-2 call-entry
state and same-call internals with XSTAR while validating the first four thermal
and charge-balance trajectory events.  Its summary reports strict runtime parity
separately from source branch/residual parity so tiny carried work-bound roundoff
cannot be mistaken for a changed source branch.

## v0.4.57 unrestricted source-zero `dsec` acceptance

### `127_validate_xstar_dsec_source_zero_unrestricted.py`

Use the same physical/probe arguments as example 126 and change only the wrapper
and output directory:

```bash
PYTHONPATH=src python examples/127_validate_xstar_dsec_source_zero_unrestricted.py \
  [the example-126 ATDB, trajectory, transition, and regression options] \
  --out-dir xstar_dsec_source_zero_unrestricted_v0457 \
  --print-summary
```

The wrapper removes any `--maximum-evaluations` option and runs natural `dsec`
convergence with production `dense-source`, `reset-per-call`, and `source-zero`
semantics.  It compares every captured thermal/charge evaluation, retains the
evaluation-2 internal audit, executes the correlated post-`dsec`
`calc_hmc_all`, and writes:

```text
xstar_dsec_source_zero_unrestricted_evaluations.csv
xstar_dsec_source_zero_unrestricted_runtime_failures.csv
xstar_dsec_source_zero_unrestricted_summary.json
xstar_dsec_source_zero_unrestricted_summary.md
```

`unrestricted_source_semantic_acceptance_ready=True` and
`ready_to_advance_to_bremsmap=True` require natural convergence, full evaluation
count, source branch/residual parity, all-evaluation thermal parity,
evaluation-2 active solver parity, final fixed-state parity, and the frozen
v0.4.44 regression.  Strict floating-point trajectory and transition-array
results remain separate fields and are never silently relaxed.


## v0.4.58 exact post-`dsec` final-call replay

`examples/128_validate_xstar_dsec_post_final_replay.py` runs unrestricted natural
source-zero `dsec`, classifies the same-sign near-zero `hmctot` row separately
from its passing heating/cooling components, and then replays the complete
captured XSTAR call-entry state for the correlated post-`dsec` `calc_hmc_all`.
It requires no new XSTAR run when the v0.4.48 call-1 probe directory contains
call 34 input, `freef`, and `bremem` products.

Use the example-127 command with these substitutions:

```diff
- examples/127_validate_xstar_dsec_source_zero_unrestricted.py
+ examples/128_validate_xstar_dsec_post_final_replay.py

- --out-dir xstar_dsec_source_zero_unrestricted_v0457
+ --out-dir xstar_dsec_post_final_replay_v0458
```

The decisive fields are `source_control_flow_ready`,
`thermal_component_trajectory_ready`,
`exact_post_dsec_fixed_state_parity_ready`, and
`ready_to_advance_to_bremsmap`.

### `128_validate_xstar_dsec_post_final_replay.py`

Run the unrestricted production `dsec` path, classify same-sign near-zero
`hmctot` roundoff separately from component parity, and replay the exact
correlated XSTAR post-`dsec` `calc_hmc_all` call-entry state:

```bash
PROBE_DIR=xstar_runs/helike_type69/o7_ne1e8_dsec_v0448
TRANSITION_DIR=xstar_runs/helike_type69/o7_ne1e8_dsec_v0451_eval2

PYTHONPATH=src python \
  examples/128_validate_xstar_dsec_post_final_replay.py \
  --atdb /media/linux/mhd/xstar/xstar/data/atdb.fits \
  --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz \
  --xstar-dsec-trajectory "$PROBE_DIR/xstar_dsec_trajectory_probe.csv" \
  --xstar-dsec-call-id 1 \
  --xstar-call-correlation "$PROBE_DIR/xstar_dsec_calc_hmc_all_call_correlation.csv" \
  --xstar-dsec-input-probe-dir "$PROBE_DIR" \
  --xstar-post-dsec-probe-dir "$PROBE_DIR" \
  --xstar-dsec-thermal-decomposition "$PROBE_DIR/xstar_dsec_thermal_decomposition_probe.csv" \
  --xstar-transition-input-probe-dir "$TRANSITION_DIR" \
  --xstar-transition-call-correlation "$TRANSITION_DIR/xstar_dsec_calc_hmc_all_call_correlation.csv" \
  --xstar-transition-evaluation-index 2 \
  --oxygen-call73-regression-dir oxygen_call73_v0434_acceptance/xstar_o_calc_hmc_all_fixed_state_v0434 \
  --coheat-data /media/linux/mhd/xstar/xstar/data/coheat.dat \
  --initial-population-policy require-all \
  --out-dir xstar_dsec_post_final_replay_v0458 \
  --print-summary
```


## v0.4.59 offline final-residual source semantics

### `129_validate_xstar_dsec_final_residual_semantics.py`

Reclassify a completed v0.4.58 post-final replay without rerunning the physical
33-evaluation calculation:

```bash
PYTHONPATH=src python \
  examples/129_validate_xstar_dsec_final_residual_semantics.py \
  --v0458-results-dir xstar_dsec_post_final_replay_v0458 \
  --out-dir xstar_dsec_final_residual_semantics_v0459 \
  --print-summary
```

The validator preserves `exact_post_dsec_fixed_state_parity_ready=False` when
the normalized residual misses the strict relative tolerance.  It separately
requires that all underlying fixed-state quantities pass, both Python and XSTAR
`hmctot` values reproduce the literal `heatf.f90` expression, and both satisfy
the `dsec.f90` convergence decision `abs(hmctot) <= 1.e-4`.  A successful result
writes `exact_post_dsec_fixed_state_semantic_ready=True` and
`ready_to_advance_to_bremsmap=True`.


## v0.4.60 `bremsmap` source validation

### `130_validate_xstar_bremsmap.py`

Validate the literal `bremsmap -> nbinc -> huntf` translation against two
frozen direct-original-Fortran cases:

```bash
PYTHONPATH=src python examples/130_validate_xstar_bremsmap.py \
  --out-dir xstar_bremsmap_source_validation_v0460 \
  --print-summary
```

The gate requires exact reduced-grid mapping and preservation of the
caller-owned `bremsint(ncn2m+1)` tail boundary.

## v0.4.61 `calc_emisab_all` source validation

### `131_validate_xstar_calc_emisab_all.py`

Validate the literal `calc_emisab_all -> calc_emisab_element ->
calc_emisab_ion` translation with a bounded synthetic pointer state:

```bash
PYTHONPATH=src python examples/131_validate_xstar_calc_emisab_all.py \
  --out-dir xstar_calc_emisab_all_source_validation_v0461 \
  --print-summary
```

The gate verifies density control, full-output resets, carried continuum
workspaces, compact continuum aliases, inactive-ion offsets, rate types
4/7/9/14, and `ucalc` continuum side effects.

## v0.4.62 `calc_emis_all` source validation

### `132_validate_xstar_calc_emis_all.py`

Validate the literal `calc_emis_all -> rlbin -> calc_emis_element ->
calc_emis_ion -> freef -> bremem` translation with a bounded source-order
fixture:

```bash
PYTHONPATH=src python examples/132_validate_xstar_calc_emis_all.py \
  --out-dir xstar_calc_emis_all_source_validation_v0462 \
  --print-summary
```

The gate verifies precomputed `calc_emisab_all` ranking, the source rank-table
limit, all-ion compact aliases, inactive offsets, rate-type-7 strong RRC,
rate-type-9 double `ucalc`, rate-type-42 retained-continuum-pointer behavior,
strong-line `fline/flinel`, caller-owned non-reset arrays, Thomson continuum
reset, `ucalc` continuum side effects, and the final `freef`/`bremem` calls.



## v0.4.63 complete local `xstarcalc` validation

### `133_validate_xstar_complete_local_xstarcalc.py`

Validate literal local `xstarcalc` ordering, `nlimdt` skip behavior, `lpri`
ownership, shared reduced/full-grid continuum workspaces, precomputed feature
ranking, caller-owned array continuity, and final `nry`.

```bash
PYTHONPATH=src python examples/133_validate_xstar_complete_local_xstarcalc.py \
  --out-dir xstar_complete_local_xstarcalc_source_validation_v0463 \
  --print-summary
```

## v0.4.64 bounded radial-shell validation

### `134_validate_xstar_bounded_radial_shell.py`

Validate `step`, `trnfrc`, `stpcut`, and `trnfrn` against frozen outputs from
direct compilation of the unmodified XSTAR routines, then exercise the bounded
first-pass caller around the accepted local `xstarcalc`:

```bash
PYTHONPATH=src python examples/134_validate_xstar_bounded_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0464 \
  --print-summary
```

The caller gate requires zone 1 to skip `step`, later first-pass zones to run
it, exact `trnfrc -> xstarcalc -> heatt -> stpcut -> trnfrn` ordering, shared
caller-owned radial arrays, explicit failure at missing reverse-pass `unsavd`,
explicit failure at missing turbulent `gsmooth`, and no output-writer calls.
