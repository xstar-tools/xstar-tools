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
