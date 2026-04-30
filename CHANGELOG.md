# CHANGELOG

## v0.3.10 - Absolute-response source fitting - 2026-04-30

- Added an absolute-response fitting mode to `examples/40_audit_signed_triplet_response.py`.
- New option `--fit-mode absolute-response` fits XSTAR target triplet fractions using positive source-injected absolute f/i/r emissivities, avoiding negative baseline-subtracted delta-response columns.
- Added `--xstar-lines-csv`, `--xstar-value-column`, `--absolute-fit-min-triplet-sum`, and `--fit-max-iter` controls.
- The audit now writes `helike_absolute_response_fit_weights.csv` plus fit diagnostics in `helike_signed_triplet_response_summary.json` and the Markdown report.
- This mode is intended to test whether C V, Mg XI, and Ca XIX failures are caused by delta-response construction rather than missing source levels.

- Changed `xstar_atomic.data.resolve_atdb_path()` so an ordinary explicit `atdb.fits` argument no longer rewrites the persistent `datapath` file. Use `python -m xstar_atomic.data --set-path /path/to/atdb.fits`, `set_data_path(...)`, or `remember_explicit=True` only when intentionally configuring the shared data location.
- `resolve_atdb_path(..., prompt=False)` now raises a clear configuration error when no ATDB file is found instead of attempting a non-interactive download.
- Made `examples/39_scan_helike_source_level_blocks.py` and `examples/40_audit_signed_triplet_response.py` accept an optional `fitsfile`. If omitted, they resolve `atdb.fits` from `XSTAR_ATDB_FITS`, the saved `datapath`, or `data/atdb.fits`. If supplied, the path is passed through without changing `datapath`.
- Updated regression coverage for the new datapath behavior and dry-run diagnostics.

## v0.3.9 - datapath-safe ATDB resolution for diagnostics - 2026-04-30

- Changed `xstar_atomic.data.resolve_atdb_path()` so an ordinary explicit `atdb.fits` argument no longer rewrites the persistent `datapath` file. `find_atdb_file(..., remember=False)` now also honors non-persistent explicit paths. Use `python -m xstar_atomic.data --set-path /path/to/atdb.fits`, `set_data_path(...)`, or `remember_explicit=True` only when intentionally configuring the shared data location.
- `resolve_atdb_path(..., prompt=False)` now raises a clear configuration error when no ATDB file is found instead of attempting a non-interactive download.
- Made `examples/39_scan_helike_source_level_blocks.py` and `examples/40_audit_signed_triplet_response.py` accept an optional `fitsfile`. If omitted, they resolve `atdb.fits` from `XSTAR_ATDB_FITS`, the saved `datapath`, or `data/atdb.fits`. If supplied, the path is passed through without changing `datapath`.
- Updated regression coverage for the new datapath behavior and dry-run diagnostics.

## v0.3.8 - signed/absolute He-like triplet response audit - 2026-04-30

- Added `examples/40_audit_signed_triplet_response.py`, a diagnostic that compares baseline, source-injected, absolute, and delta f/i/r triplet emissivities for each source level.
- The audit reports raw baseline and injected triplet components, normalized injected fractions, signed normalized delta responses, component-wise increase/decrease flags, sign patterns, and whether negative responses are caused by baseline subtraction.
- This diagnostic is intended to distinguish genuinely destructive population redistribution from response-matrix construction artifacts, normalization artifacts, or missing recombination/cascade source physics in non-O VII He-like ions.
- Added regression coverage for the new diagnostic's dry-run command/output path.

## v0.3.7 - Robust He-like block-scan preflight and XSTAR reference diagnostics - 2026-04-30

- Fixed `examples/39_scan_helike_source_level_blocks.py` source-level preflight, which incorrectly imported a non-existent `parse_element` helper from `xstar_atomic.lines`.
  The scanner now uses the existing `choose_z()` API.
- Added an explicit preflight check for the converted XSTAR triplet reference CSV supplied with `--xstar-lines-csv`.
  The scan now warns clearly when the CSV is missing, empty, has no matching ion rows, or lacks one of the f/i/r components needed to compute XSTAR R and G.
- Kept the v0.3.6 invalid-source-level filtering behavior, but improved the failure path so block-fit failures caused by missing/invalid XSTAR references are easier to diagnose before expensive scans are attempted.
- Documentation updated to mention the new v0.3.7 reference-preflight warning.

## v0.3.6 - robust He-like source-level block preflight - 2026-04-30

- Hardened `examples/39_scan_helike_source_level_blocks.py` after Ca XIX block scans failed before discovery when requested blocks included source levels not present for Ca XIX.
- Added ATDB level-table preflight in the block scanner. By default, requested source levels that do not exist for the selected ion are skipped before launching `examples/20_o7_solver_source_fit.py`.
- Added `--no-skip-invalid-source-levels` to recover the old behavior and `--skip-invalid-source-levels` as the explicit default.
- Block-scan CSV output now records requested levels, actually used levels, skipped invalid levels, and paths to per-block `example20.stdout.log` and `example20.stderr.log` files.
- Failed block warnings now point to the saved stderr log, making solver/preflight failures diagnosable instead of opaque.

## v0.3.5 - 2026-04-30

- Added `examples/39_scan_helike_source_level_blocks.py`, a broad source-level block-scan wrapper that runs `examples/20_o7_solver_source_fit.py` over inclusive level ranges such as `2:40`, `41:80`, then applies the discovered-basis diagnostic from example 38.
- The block scan writes exact child commands, per-block fit status, discovery summaries, source-level tables, JSON, and Markdown reports.
- Added dry-run support for planning expensive ATDB/XSTAR scans without executing solver runs.
- Added tests for the block-scan command generation and summary outputs.

## v0.3.4 - ion-specific He-like source-basis discovery - 2026-04-30

- Added `examples/38_discover_helike_source_basis.py`, an offline diagnostic that ranks sampled source levels by their raw forbidden/intercombination/resonance response and discovers ion-specific positive, nonzero source bases.
- The new utility writes per-source, per-density, and per-run CSV/JSON/Markdown reports, including discovered source-level lists that can be reused with `--source-levels` in follow-up example 20/22 runs.
- This diagnostic follows the v0.3.3 result that strict filtering of the reused O VII source-level basis leaves no positive nonzero source levels for C V, Mg XI, or Ca XIX in the current sampled basis.
- Added regression coverage for discovered-basis classification, summary output, and empty-run warnings.

## v0.3.3 - response-basis filter comparison - 2026-04-29

- Added `examples/37_filter_source_basis_response.py`, an offline diagnostic that refits He-like triplet targets after filtering the source-level response basis.
- The new utility compares four source bases for each density: all levels, zero-response levels removed, negative-response levels removed, and positive nonzero response levels only.
- Reports how many source levels survive each filter, whether the filtered basis can still match XSTAR f/i/r components, and how much of the original fitted weight was carried by zero-response or negative-response levels.
- Added regression coverage for the filtered-basis diagnostic using a synthetic response matrix with active, zero-response, and negative-response source levels.

## v0.3.2 - zero-response source accounting fix - 2026-04-29

- Fixed `examples/20_o7_solver_source_fit.py` so source levels with no positive f/i/r response remain zero-response columns instead of being normalized to artificial `1/3,1/3,1/3` vectors.
- Updated `examples/36_source_level_failure_diagnostics.py` to recompute normalized f/i/r fractions and fitted contribution columns from raw response amplitudes, making old v0.3.1 output folders diagnose correctly.
- Added `zero_response_fitted_weight_sum` and `negative_response_fitted_weight_sum` to density-level source diagnostics and console output.
- Added regression coverage for zero-response source levels so they are not converted into uniform triplet contributors.

## v0.3.1 - Source-level diagnostic robustness - 2026-04-29

- Fixed `examples/36_source_level_failure_diagnostics.py` to use the current `ATDB.build_index()` API when `--fitsfile` is supplied, with a defensive fallback for older local trees.
- Added explicit empty-run reporting when a density-grid directory contains no `fit_ne_*` outputs, which commonly means `examples/22` only wrote a template XSTAR mapping and exited.
- Changed source-level diagnostic summaries to report population availability as `available`/`unavailable` instead of misleading `pop=0` for older or incomplete run folders.
- Updated the Markdown interpretation guide for missing population/transition exports and template-only density-grid runs.

## v0.3.0 - He-like source-level failure diagnostics - 2026-04-29

- Added `examples/36_source_level_failure_diagnostics.py` to compare fitted source vectors and response matrices at the individual source-level level across O VII, C V, Mg XI, and Ca XIX density-grid runs.
- The new diagnostic reports source level labels/configurations, fitted source weights, f/i/r response contributions, zero-response flags, optional source-component population sums, dominant radiative decay paths, dominant collisional sink/source paths, and pruning/weak-connectivity indicators.
- Extended `examples/20_o7_solver_source_fit.py` combined-source validation output to request solver population and transition CSVs (`o7_combined_solver_populations.csv`, `o7_combined_solver_transitions.csv`) so future source-level diagnostics can directly measure source-connected component populations and rate paths.
- The source-level diagnostic remains offline/exploratory and does not change the validated O VII `suppress-resonance` behavior or default solver physics.

## v0.2.99 - 2026-04-29

- Added `examples/35_compare_helike_response_matrices.py`, an offline diagnostic that compares fitted source vectors, response matrices, and combined-solver validation behavior across He-like density-grid runs.
- The new comparison writes density-level CSV, run-level CSV, JSON, and Markdown reports identifying why O VII is reachable while C V, Mg XI, and Ca XIX grids are not.
- The diagnostic records XSTAR R/G ranges, fitted and combined R/G availability, simultaneous-solver residuals, response-matrix active-source counts, response-matrix conditioning, top fitted source levels, and a concise failure diagnosis.
- Added a regression test for the new comparison utility.

## v0.2.98 - 2026-04-29

- Improved `examples/34_summarize_helike_validation_runs.py` reporting for multi-condition He-like validation grids.
- Density-grid summaries now prefer the output-directory stem as the run tag, preserving condition labels such as `ca19_xi3` and `ca19_xi4` instead of collapsing both to `ca19`.
- Line-audit summaries now use the audit-directory stem as the audit tag, so low-ionization and high-ionization Ca XIX audits remain distinct in console, CSV, JSON, and Markdown output.
- Updated the validation-summary regression test to require distinct Ca XIX xi/audit tags.

## v0.2.97 - 2026-04-29

- Added `examples/34_summarize_helike_validation_runs.py`, a lightweight reporting utility for completed He-like density-grid validation products.
- The new summary tool reads one or more density-grid output directories from `examples/21`/`examples/22` and optional line-audit directories from `examples/33`.
- It writes machine-readable CSV/JSON and a Markdown report with per-ion status, XSTAR R/G ranges, reachable-density counts, non-null solver diagnostics, and warning counts.
- This makes the current multi-ion status explicit: O VII remains the only validated suppress-resonance benchmark, while C V, Mg XI, and Ca XIX high-xi runs are exploratory/non-validated until solver-side R/G diagnostics become reachable.
- Added `tests/test_helike_validation_summary_example.py` covering the new reporting workflow.

## v0.2.96 - 2026-04-29

- Added ionization-parameter scan support to `examples/32_prepare_helike_xstar_density_grids.py` via `--rlogxi-grid`.
- The default single-`log xi` behavior is preserved, but multi-value grids now generate xi-tagged XSTAR run directories and mapping CSVs such as `ca19_xi3_ne1/` and `xstar_ca19_xi3_density_grid_references.csv`.
- This is intended for Ca XIX, where the default `log xi=1.5` XSTAR runs produced no `ca_xix` triplet rows; use a scan such as `--rlogxi-grid 1.5 2 2.5 3 3.5 4` to locate conditions that actually produce Ca XIX.
- Updated tests for the He-like XSTAR density-grid preparation helper.

## v0.2.95 - 2026-04-29

- Added `examples/33_audit_helike_xstar_lines.py` to diagnose He-like XSTAR line-output files when a prepared triplet converter finds zero rows.
- The new audit reports XSTAR ion-label counts, all nearby wavelength-window rows, expected-ion rows at any wavelength, and rows with He-like ground-to-`n=2` triplet/resonance level labels.
- Documented the Ca XIX use case where XSTAR runs complete but `convert_ca19_triplet.sh` produces empty CSVs, meaning Ca XIX is not testable until a usable triplet target is located.

# v0.2.94 - 2026-04-29

- Hardened the exploratory non-O VII He-like density-grid workflow after the C V, Mg XI, and Ca XIX tests.
- `examples/22_o7_solver_source_fit_density_xstar_grid.py` now validates that each converted XSTAR triplet CSV is not only present but also contains usable forbidden, intercombination, and resonance rows with positive emissivity before launching the expensive subprocess chain. Empty Ca XIX converted CSVs now fail early with a clear message instead of reaching the generic `Could not read XSTAR He-like triplet R/G reference` error.
- `examples/20_o7_solver_source_fit.py` keeps legacy `o7_*` filenames for compatibility but also writes ion-specific aliases such as `c5_solver_source_fit_summary.json` and `mg11_solver_source_fit_summary.json` for non-O VII runs.
- `examples/21_o7_solver_source_fit_density_grid.py` now writes ion-specific density-grid aliases such as `c5_solver_source_fit_density_grid.csv` and uses generic He-like labels in its top-level summary/console heading.
- The C V and Mg XI density-grid outputs should still be treated as non-validated exploratory diagnostics: both show large mismatches/unreachable rows with the current solver/source model. O VII remains the only validated suppress-resonance benchmark.
- Added regression tests for rejecting empty converted triplet CSVs and accepting complete C V-style converted triplet CSVs.

# v0.2.93 - 2026-04-29

- Fixed non-O VII He-like exploratory source-fit reporting when one or more solver-side triplet ratios are unavailable.
- `examples/20_o7_solver_source_fit.py` now prints `NA` for missing uniform, fitted, or combined R/G diagnostics instead of aborting with a `NoneType.__format__` error.
- This lets C V density-grid runs continue after reading the XSTAR target even when the current solver-side response has no usable resonance or intercombination diagnostic.
- Added `tests/test_example20_optional_ratio_format.py`.

# v0.2.92 - 2026-04-29

- Generalized solver-side He-like triplet diagnostics in `src/xstar_atomic/solver.py` so combined simultaneous-solver validation can report R=f/i and G=(f+i)/r for C V, Mg XI, Ca XIX, and other He-like ions, not only O VII.
- The solver now classifies He-like triplet components from `upper_label`/level-label strings such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`, while preserving the historical O VII wavelength/level-number fallback.
- Fixed `examples/20_o7_solver_source_fit.py` printing so missing combined-validation R/G values are reported as `NA` instead of raising a `TypeError`.
- Added regression coverage for generic solver-side C V triplet diagnostics.

# v0.2.91 - 2026-04-28

- Added preflight validation for He-like density-grid mapping CSVs before launching the solver-fit subprocess chain.
- Non-O VII density-grid mappings now fail early with a clear message if converted XSTAR triplet CSVs such as `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv` are missing in the current package tree.
- Stale non-O VII mappings that still point to `xstar_test_run/xstar_o7_triplet_lines.csv` are now rejected with an explicit diagnostic and regeneration/copy instructions.
- This avoids the confusing downstream `Could not read XSTAR He-like triplet R/G reference` error when users generated C V, Mg XI, or Ca XIX XSTAR products in a different working directory.

# v0.2.90 - 2026-04-28

- Fixed non-O VII density-grid template generation in `examples/22_o7_solver_source_fit_density_xstar_grid.py`.
- New missing mapping CSVs are now written with ion-specific He-like paths such as `xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv`, not the old O VII placeholder path.
- Updated template messages to instruct users to run the example 32 XSTAR/convert workflow if the listed converted triplet CSVs are missing.
- Added regression coverage for C V template generation so `xstar_c5_density_grid_references.csv` does not point to `xstar_o7_triplet_lines.csv`.

# v0.2.89 - 2026-04-28

- Fixed stale non-O VII He-like density-grid mapping propagation in `examples/22_o7_solver_source_fit_density_xstar_grid.py`.
- The density-grid front end now repairs old candidate-ion mapping CSVs, such as `xstar_test_run/xstar_c5_density_grid_references.csv`, when they still point to the O VII placeholder `xstar_test_run/xstar_o7_triplet_lines.csv` and the correct converted per-density files already exist under `xstar_test_run/<ion>_ne*/`.
- A `.bak` copy of the original mapping is preserved before in-place repair.
- This keeps generated solver-fit directories as outputs only while allowing C V, Mg XI, and Ca XIX density-grid comparisons to reuse converted XSTAR triplet CSVs generated by the v0.2.87 helper.

# v0.2.88 - 2026-04-28

- Generalized the XSTAR He-like triplet reference reader used by `examples/20_o7_solver_source_fit.py` and the density-grid wrappers so converted C V, Mg XI, Ca XIX, and other He-like triplet CSVs can be classified from `lower_level`/`upper_level` labels rather than O VII-only wavelengths.
- Fixed non-O VII density-grid validation runs such as C V, which previously failed with `Could not read XSTAR O VII triplet R/G reference` even when the converted XSTAR triplet CSV contained the correct five He-like components.
- Kept the O VII wavelength fallback for older O VII reference files while using label-based f/i/r classification for all He-like ions.

# v0.2.87 - 2026-04-28

- Added `examples/32_prepare_helike_xstar_density_grids.py`, a run-plan generator for density-specific XSTAR triplet grids for the non-O VII candidate ions identified by the He-like type-69 audit.
- The new helper prepares XSTAR run scripts, conversion scripts, per-ion mapping CSVs, a combined run-plan CSV, and a README for C V, Mg XI, and Ca XIX by default.
- The generated references are placed under `xstar_test_run/<ion>_ne*/` after conversion, so `examples/31_helike_type69_ground_resonance_validation.py` can detect them in follow-up audits.
- This release does not mark any additional ion as validated; it only prepares the external XSTAR density-grid runs needed before include-vs-suppress-resonance comparisons can be trusted beyond O VII.

# v0.2.86 - 2026-04-28

- Fixed the He-like type-69 ground-resonance validation audit for multi-letter element symbols.
  The audit now normalizes symbols before looking them up in the ATDB element table, so
  `Ne`, `Mg`, `Si`, `Ar`, `Ca`, and `Fe` are no longer reported as unknown symbols.
- Added regression coverage for normalized ATDB element lookup in
  `examples/31_helike_type69_ground_resonance_validation.py`.
- Clarified that zero-candidate or pending statuses for non-O VII ions are audit results
  and must not be interpreted as validation until density-specific XSTAR triplet grids are supplied.

# v0.2.85 - 2026-04-28

- Added `examples/31_helike_type69_ground_resonance_validation.py`, a broader He-like type-69 ground-resonance audit/validation-status tool.
- The new example audits candidate type-69 ground-to-resonance records for C V, N VI, O VII, Ne IX, Mg XI, Si XIII, S XV, Ar XVII, Ca XIX, and Fe XXV.
- The tool explicitly marks O VII as validated only when the packaged density-specific `xstar_test_run/o7_ne*/` references are present, and marks other He-like ions as pending until density-specific XSTAR triplet grids are supplied.
- Added tests for ion parsing, resonance-label detection, and validation-status classification.

# v0.2.84 - 2026-04-28

- Packaging cleanup: removed the empty generated-output directory `o7_solver_source_fit_density_xstar_grid/` from the source archive. This directory is produced by examples 21/22/30 and is not a package input.
- Packaging cleanup: removed transient `.pytest_cache/` artifacts from the archive.
- Added regression coverage that generated O VII density-grid output directories are not present in the package tree, while compact density-specific inputs remain under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.
- Clarified that `examples/26_o7_high_density_rate_sensitivity.py --auto-xstar-test-run-grid` is available in v0.2.83+; older working trees such as v0.2.80 do not expose that option.

# v0.2.83 - 2026-04-28

- Standardized the O VII density-dependent XSTAR benchmark inputs under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.
- Added `--auto-xstar-test-run-grid` support to `examples/22_o7_solver_source_fit_density_xstar_grid.py`, so density-specific compact XSTAR CSVs can be discovered automatically without requiring a root-level mapping CSV.
- Updated `examples/26_o7_high_density_rate_sensitivity.py` to accept `--auto-xstar-test-run-grid` or `--xstar-grid-summary-csv` directly, and to reject stale/generated density-grid directories whose `ne=1e12` XSTAR target is inconsistent with the validated density-specific reference.
- Updated `examples/30_o7_density_grid_type69_mode_compare.py` to use packaged `xstar_test_run` density references automatically when no mapping CSV is present.
- Kept generated density-grid solver directories as reproducible outputs, not required package inputs.
- Updated documentation to mark `o7_solver_source_fit_density_xstar_grid/` and related high-density diagnostic directories as outputs and to use the corrected LaTeX user guide baseline.

## v0.2.82

- Added reference snapshots for the v0.2.81 O VII type-69 mode comparison: `o7_density_grid_type69_mode_compare.csv` and `o7_density_grid_type69_mode_compare_summary.json` under both `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added regression tests that lock in the benchmark behavior: the default `include` network is not reachable at `ne=1e12 cm^-3`, while diagnostic/experimental `suppress-resonance` is reachable and matches the density-specific XSTAR R/G target; lower-density rows remain reachable in both modes.
- Expanded documentation for the O VII high-density benchmark result and reiterated that `suppress-resonance` is a validated diagnostic switch for this benchmark, not a general physical default.

## v0.2.81

- Added `examples/30_o7_density_grid_type69_mode_compare.py`, a side-by-side O VII density-grid comparison of the original type-69 network (`include`) and the diagnostic `suppress-resonance` mode.
- The comparison runs the density-dependent XSTAR grid workflow for both modes, then writes `o7_density_grid_type69_mode_compare.csv` and a JSON summary with per-density R/G ratios, reachability flags, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.
- Documented that `--collision-type69-ground-excitation-mode suppress-resonance` is diagnostic/experimental: it is validated for the O VII high-density benchmark but is not a general physical default.

## v0.2.80

- Fixed `--collision-type69-ground-excitation-mode suppress-resonance` in `xstar_atomic.solver`.
  v0.2.79 validated the command-line propagation through examples 22 -> 21 -> 20, but the row-level
  mode handler incorrectly raised an error for non-resonance collision rows whenever the mode was
  `suppress-resonance`. The handler now validates the mode once, then applies suppression only to
  matching type-69 ground-to-resonance rows and leaves all other collision rows unchanged.
- Added a regression test that `suppress-resonance` leaves unrelated type-69 rows valid while suppressing
  the O VII ground-to-resonance excitation row.

## v0.2.79

- Fixed propagation of `--collision-type69-ground-excitation-mode` through the chained O VII density-grid workflow.  In v0.2.78, examples 21/22 forwarded the option to `examples/20_o7_solver_source_fit.py`, but example 20 did not expose the corresponding CLI parser option, causing an `unrecognized arguments` failure.
- Added a regression check that example 20 exposes the type-69 ground-excitation suppression option used by the v0.2.78 density-grid command.

## v0.2.78

- Added the diagnostic/experimental solver option `--collision-type69-ground-excitation-mode include|suppress-resonance|suppress-all`.  The `suppress-resonance` mode suppresses type-69 excitation from the ground level into the He-like resonance upper level while preserving the de-excitation direction; for the validated O VII case this targets record 22490, level 1 -> 7.
- Propagated the new mode through `examples/20_o7_solver_source_fit.py`, the density-grid front end (`examples/21/22`), the rate-sensitivity diagnostic (`examples/26`), and the ground-coupling diagnostic (`examples/29`).
- Extended `examples/29_o7_type69_ground_coupling_diagnostic.py` with built-in solver-switch cases for `suppress-resonance` and `suppress-all`, allowing direct comparison with the previous record/direction scaling experiments.
- Added regression coverage for the new switch and the O VII ground-resonance row selection logic.

## v0.2.77

- Hotfix for `examples/29_o7_type69_ground_coupling_diagnostic.py`: fixed `top_weight()` so empty or missing weights-path fields in the example-20 summary are not interpreted as `Path(".")`, which caused `IsADirectoryError` during the baseline case.
- The ground-coupling diagnostic now falls back to the standard per-case fit outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`) when the summary omits a usable weights path.
- Added a regression test for the empty-path/directory fallback.

# Changelog

## v0.2.76

- Fixed the v0.2.75 O VII type-69 record-audit annotation lookup so `examples/28_o7_type69_record_audit.py` can find `o7_type69_transition_sensitivity.csv` when given either the CSV path, the output directory, or a parent directory.
- Added `examples/29_o7_type69_ground_coupling_diagnostic.py` to interpret the high-density record-22490 ground--resonance coupling.  The diagnostic compares baseline, record-scaled, all-type-69-scaled, record-removed, excitation-only, de-excitation-only, and direction-specific variants.
- Added solver support for diagnostic direction-specific collision scaling via `--collision-record-direction-scale RECORD:DIRECTION:SCALE`, propagated through `examples/20_o7_solver_source_fit.py`.  This is explicitly diagnostic and intentionally can break detailed balance to isolate excitation versus de-excitation effects.
- Added regression tests for the record-audit annotation lookup, ground-coupling case builder, and direction-scale parser.

## v0.2.75

- Added `examples/28_o7_type69_record_audit.py`, a targeted O VII high-density diagnostic that audits raw XSTAR type-69 records, with emphasis on records `22490`--`22495` and the record `22490` level `1 -> 7` channel identified by the v0.2.74 transition-sensitivity scan.
- The audit writes raw record metadata, decoded level labels/energies/statistical weights, Kato--Nakazaki `calt69` effective collision strengths, excitation/de-excitation coefficients, density-scaled rates, detailed-balance checks, and temperature-grid behavior.
- The audit can optionally ingest the v0.2.74 `o7_type69_transition_sensitivity.csv` output and annotate each record with its best sensitivity case and reachable scaling factors.
- Added regression tests for the new audit helper functions.


## v0.2.74

Added:
- Added `examples/27_o7_type69_transition_sensitivity.py`, a high-density O VII diagnostic that scans individual XSTAR type-69 collision records or level pairs to identify which transitions drive the `ne=1e12 cm^-3` triplet mismatch.
- Added diagnostic collision record scaling to `xstar_atomic.solver` via `--collision-record-scale RECORD:SCALE`; the existing O VII solver-source-fit example now propagates this option to all unit-source and combined-source solver calls.
- Added `tests/test_o7_type69_transition_sensitivity.py` for the transition-sensitivity helper logic.

Notes:
- This is a diagnostic sensitivity scan only. Record-specific or pair-specific scaling is not a physical correction by itself; it is intended to isolate the type-69 transition(s) that make the high-density XSTAR target reachable.

## v0.2.73

Added:
- Added `examples/26_o7_high_density_rate_sensitivity.py`, a high-density O VII rate-network sensitivity diagnostic for the `ne=1e12 cm^-3` mismatch.
- Added diagnostic collision-rate scaling controls to `xstar_atomic.solver`:
  - `--collision-rate-scale` for global evaluated electron-impact rates,
  - `--collision-data-type-scale DATA_TYPE:SCALE`,
  - `--collision-pair-scale LEVEL1:LEVEL2:SCALE`.
- Propagated the diagnostic collision-rate scaling options through `examples/20_o7_solver_source_fit.py` so empirical source fits can be repeated for scaled rate networks.
- Added `tests/test_o7_high_density_rate_sensitivity.py` for scan-case construction and scale specification checks.

Notes:
- The new rate scales are diagnostic sensitivity factors only. They do not modify the packaged atomic data and should not be interpreted as recommended physical rate corrections.
- The primary goal is to determine whether the high-density O VII mismatch is driven by type-68/69 or level-2-to-3/4/5 collisional coupling, or whether additional physics is required.

## v0.2.72

Added:
- `examples/25_o7_high_density_expanded_source_scan.py` for expanded O VII high-density source-level scans.
- The new diagnostic tests whether larger source bases (`baseline`, `n<=5`, `n<=6`, `n<=8`, and `all_levels`) can reach the density-specific XSTAR target at `ne=1e12 cm^-3`.
- `tests/test_o7_high_density_expanded_source_scan.py` dry-run coverage for CI-friendly source-set planning.


## v0.2.71

Added:
- Added `examples/24_o7_high_density_mismatch_diagnostics.py` to investigate the O VII high-density (`ne=1e12 cm^-3`) density-grid mismatch.
- The new diagnostic reads outputs from `examples/21`/`examples/22` and writes component, source-weight, collision-rate, and JSON summary diagnostics.
- It reports which triplet component drives the mismatch, whether the target is reachable, source-weight collapse metrics, solver diagnostics, and optional type-68/69 level-2 -> level-3/4/5 collision rates when `atdb.fits` is supplied.

Updated:
- Documented the high-density mismatch workflow in README, Markdown, LaTeX, and Sphinx example documentation.

## v0.2.70

Added:
- Added `examples/23_prepare_o7_xstar_density_grid.py`, which prepares real O VII XSTAR density-grid validation runs at `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3`.
- The helper writes `xstar_runs/o7_ne*/run_xstar.sh` scripts containing the full XSTAR commands, `convert_o7_triplet.sh` scripts for converting `xout_lines1.fits` to O VII triplet CSV files, a density-to-CSV mapping file `xstar_o7_density_grid_references.csv`, a run-plan CSV, and `xstar_runs/README_o7_density_grid.md` containing all commands.
- Added tests for the run-preparation helper and generated command contents.

Notes:
- The helper does not run XSTAR.  It prepares reproducible external XSTAR commands and conversion commands so `examples/22_o7_solver_source_fit_density_xstar_grid.py` can later perform a true density-dependent XSTAR comparison once the XSTAR runs have been completed.

## v0.2.69

Fixed:
- Improved `examples/22_o7_solver_source_fit_density_xstar_grid.py` when the requested `--xstar-grid-summary-csv` file is missing. The wrapper now writes a template density-to-XSTAR-lines mapping CSV and exits with a clear message instead of failing with a raw `FileNotFoundError`.

Added:
- `--write-template-grid-csv` to create a starter density-reference mapping CSV.
- `--allow-placeholder-grid` for low-density-placeholder smoke tests only.
- Packaged template CSVs under `examples/reference_inputs/` and `docs/validation/xstar_inputs/`.

Notes:
- The template intentionally reuses the packaged low-density O VII reference as a placeholder for every row. Replace each `xstar_lines_csv` entry with a converted density-specific XSTAR line CSV before using it for scientific validation.

# CHANGELOG

## v0.2.68 - 2026-04-30

Density-dependent XSTAR references for the O VII density-grid diagnostic.

Added:
- Added `examples/22_o7_solver_source_fit_density_xstar_grid.py`, a density-dependent XSTAR reference front end for the O VII density-grid source-fit diagnostic.
- Added `--xstar-lines-csv-by-density DENSITY:CSV` and `--xstar-grid-summary-csv` support to `examples/21_o7_solver_source_fit_density_grid.py`, allowing each density to be compared against its own XSTAR line CSV instead of reusing a single low-density reference.
- Added reference snapshots for the O VII density-grid diagnostic under `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added lightweight tests for density-specific XSTAR reference parsing, dry-run command generation, and the new example-22 front end.

Documentation:
- Added a short validated O VII diagnostic commands section to README, Markdown guide, LaTeX guide, and Sphinx examples.
- Added a top-level known-limitation note that empirical O VII fitted source weights are diagnostic and are not physical level-resolved recombination rates.
- Documented the density-dependent XSTAR mapping CSV format and repeated `--xstar-lines-csv-by-density` syntax.


## v0.2.67 - 2026-04-29

Data-path resolver and test isolation fixes.

Fixed:
- `resolve_atdb_path(path, prompt=False)` now treats an explicitly supplied path as strict precedence.  If that path is invalid, it raises a clear error instead of silently falling back to `XSTAR_ATDB_FITS` or a saved datapath.
- Updated data-path helper tests to use a minimal FITS-like file that passes the lightweight resolver validation added for zero-byte/truncated-file protection.
- Isolated data-path helper tests from the `XSTAR_ATDB_FITS` environment variable so full-suite runs with a real ATDB configured do not mask explicit-path behavior.

Notes:
- This is a bug-fix release for the v0.2.66 test failures observed when running `XSTAR_ATDB_FITS=../xstar/data/atdb.fits PYTHONPATH=src pytest -q`.

## v0.2.66 - 2026-04-28

Density-grid feasibility flags and clearer XSTAR-target labeling.

Changed:
- Updated `examples/21_o7_solver_source_fit_density_grid.py` so the reused XSTAR target is explicitly labeled as a low-density XSTAR O VII reference reused at all densities.
- Added fit-feasibility columns: `fit_success_vs_xstar` and `target_reachable`.
- Added ratio columns: `refitted_R_over_xstar`, `refitted_G_over_xstar`, `fixed_R_over_refitted`, and `fixed_G_over_refitted`.
- Added warning generation when the source-fit objective is large or the refitted combined R/G ratios remain outside tolerance, with explicit high-density wording for the type-68 coupling regime.
- The density-grid summary JSON now records the XSTAR target label, feasibility tolerances, warnings, and per-density feasibility flags.
- Added tests for the new density-grid feasibility logic and warning behavior without requiring full `atdb.fits`.

Notes:
- The current density-grid example still uses one XSTAR reference at all densities.  A later extension should allow density-dependent XSTAR references, for example `--xstar-lines-csv-by-density` or `--xstar-grid-summary-csv`.

## v0.2.65 - 2026-04-27

Density-grid O VII solver-source-fit diagnostic.

Added:
- Added `examples/21_o7_solver_source_fit_density_grid.py`, which runs the validated O VII full-solver source-fit workflow over a density grid.  The default grid is `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3` at `T = 1e6 K`.
- The density-grid diagnostic reports both fixed-weight validation, using the reference `ne=1 cm^-3` fitted weights at all densities, and separately refitted weights at each density.
- The output CSV `o7_solver_source_fit_density_grid.csv` includes XSTAR R/G, fixed-weight R/G, refitted linear-response R/G, refitted combined simultaneous-solver R/G, matrix rank, condition number, residuals, negative-population diagnostics, and weight-change metrics relative to the reference density.
- The output JSON `o7_solver_source_fit_density_grid_summary.json` records per-density summary paths, fixed-weight validation products, solver diagnostics, and the largest source-weight changes.
- Added lightweight tests in `tests/test_o7_solver_source_fit_density_grid.py` for the new density-grid example, including dry-run command construction and reference-density ordering without requiring the full `atdb.fits`.

Notes:
- This diagnostic is intended to show whether the empirical fitted O VII source distribution is stable or density-dependent after type-68 metastable/intercombination coupling is active.
- The fitted weights remain empirical solver-response weights, not physical level-resolved recombination rates.

## v0.2.64 - 2026-04-26

Regression/reference checks for the validated O VII solver-source-fit workflow.

Added:
- Added compact saved reference output `examples/reference_outputs/o7_solver_source_fit_summary_reference.json` for the validated O VII full-solver source-fit diagnostic.  This reference stores the XSTAR R/G target, fitted linear-response R/G, combined simultaneous-solver R/G, SVD solver diagnostics, null-rate pruning diagnostics, and negative-population handling without requiring the full 830 MB `atdb.fits` in CI.
- Added `tests/test_o7_solver_source_fit_reference.py` with CI-friendly tests that verify:
  - fitted linear-response R/G matches the saved XSTAR reference,
  - combined-source validation agrees with the fitted linear-response prediction to tight tolerance,
  - the validated diagnostic path uses `linear_solver=svd`, `rank_deficient_action=svd`, `negative_population_action=keep`, and null-rate pruning,
  - the raw-response simplex fitting helper remains numerically reproducible.
- Added a warning in `examples/13_o7_recombination_cascade_workflow.py` when `selected-fit-weights` or `o7-xstar-fit` is used without `--solver-source-total-rate`.  The warning tells users to pass `--solver-source-total-rate 1.0` when consuming weights produced by `examples/20_o7_solver_source_fit.py` with the default `--source-rate=1.0`.
- Workflow summaries from `examples/13_o7_recombination_cascade_workflow.py` now include a `warnings` list so this source-amplitude warning is preserved in machine-readable outputs.

Notes:
- These tests are reference/regression tests for the validated diagnostic output, not full physical ATDB tests.  Full real-ATDB validation is still done by running examples 20 and 13 locally with the real XSTAR `atdb.fits`.
- The empirical fitted-source mode remains diagnostic and amplitude-dependent, not a physical level-resolved recombination model.

## v0.2.63 - 2026-04-25

Documentation update for the validated O VII full-solver source-fit path.

Changed:
- Updated README and Markdown user guide with the validated O VII solver settings: `--linear-solver svd`, `--rank-deficient-action svd`, `--negative-population-action keep`, and `--prune-null-rate-levels`.
- Documented that the combined-source validation in `examples/20_o7_solver_source_fit.py` matches the saved XSTAR O VII triplet ratios with `R/R_XSTAR = 1.00000146` and `G/G_XSTAR = 0.99999836` in the v0.2.62 validation run.
- Added the same validated command sequence to the recombination/cascade workflow documentation, including `--solver-source-total-rate 1.0` and the SVD/rank-aware solver controls.
- Updated the LaTeX user guide with a dedicated Stage-6 full-solver source-fit section and a compact diagnostic summary table.
- Updated Sphinx examples documentation with the same validated workflow and diagnostic caveats.

Notes:
- The fitted source weights remain empirical/diagnostic, not true level-resolved recombination rates.
- Direct dense or sparse solvers are not recommended for this O VII diagnostic unless residuals and combined-source validation are explicitly checked, because the matrix is rank-deficient and highly ill-conditioned.

## v0.2.62 - 2026-04-24

Automatic combined-source validation for the O VII solver-response source-fit diagnostic.

Added:
- `examples/20_o7_solver_source_fit.py` now runs one simultaneous combined-source validation solve after fitting the nonnegative source weights, unless `--skip-combined-validation` is supplied.
- The validation writes `combined_source_validation/o7_combined_fitted_sources.csv`, `o7_combined_solver_lines.csv`, `o7_combined_solver_triplet.csv`, and `o7_combined_solver_summary.json`.
- The top-level `o7_solver_source_fit_summary.json` now reports three R/G comparisons in one place: XSTAR reference, fitted linear-response prediction, and combined simultaneous-solver validation.
- Combined validation diagnostics include matrix rank/size, condition number, linear residuals, source/sink summary, null-rate pruning diagnostics, and raw negative-population counts/minimum/sum diagnostics.
- New options: `--skip-combined-validation` and `--combined-source-total-rate` for controlling the simultaneous validation solve.

Purpose:
- This prevents confusion between an exact response-matrix fit and the actual behavior when the fitted sources are injected together into the full statistical-equilibrium solver.

## v0.2.61 - 2026-04-23

Numerical solver hardening for Stage-6 O VII diagnostics.

Added:
- Rank-aware matrix handling in `xstar_atomic.solver` via `--rank-deficient-action warn|lstsq|svd|reject`.
- Explicit least-squares/SVD solver choices through `--linear-solver lstsq|svd` in addition to `dense|sparse|auto`.
- Per-solve null-rate pruning with `--prune-null-rate-levels` and `--null-rate-floor`, preserving ground, output, and source/sink levels.
- Negative-population controls: `--negative-population-action clip|zero-small|keep|reject` and `--negative-population-tol`.
- Residual diagnostics and optional rejection: `--residual-l2-max`, `--residual-linf-max`, and `--reject-large-residual`.
- Raw population diagnostics before any negative-population handling, including counts and absolute negative-population sum.
- `examples/20_o7_solver_source_fit.py` now defaults to SVD/rank-aware diagnostic solving, keeps raw negative populations by default, and passes null-rate pruning to unit-source solves.
- `examples/13_o7_recombination_cascade_workflow.py` now exposes the same solver-matrix treatment options and records them in the workflow summary.

Changed:
- Rank-deficient matrices are no longer treated as ordinary direct-solve cases by default; the default action is least-squares in the solver CLI and SVD in the O VII diagnostic examples.
- Negative populations are no longer clipped silently: the chosen action and raw negative-population diagnostics are always written to solver summaries.

Notes:
- The default library/CLI behavior remains compatible for general use (`clip` remains the solver default), while the O VII empirical diagnostic examples use `keep` to avoid introducing nonlinear clipping into response-matrix fits.

## v0.2.60 - 2026-04-22

- Corrected `examples/20_o7_solver_source_fit.py` so the empirical solver-response weights are fitted against the **raw full-solver triplet response amplitudes**, with the combined triplet vector normalized only for comparison to the XSTAR R/G target.
- This fixes the v0.2.54--v0.2.59 diagnostic inconsistency where the source-fit script could match XSTAR using per-level normalized response fractions, but the same weights did not reproduce the target when injected simultaneously into `examples/13_o7_recombination_cascade_workflow.py`.
- Added raw-response columns to `o7_source_fit_weights.csv` / `o7_solver_source_fit_weights.csv` so each fitted level shows its raw forbidden, intercombination, and resonance response per unit source.
- The fitted weights remain empirical/diagnostic and amplitude-dependent; continue using `--solver-source-total-rate 1.0` in the cascade workflow when applying weights generated with the default `--source-rate 1.0`.

## v0.2.59 - 2026-04-21

- Captures SciPy `MatrixRankWarning` during sparse statistical-equilibrium solves and falls back to the existing least-squares solver instead of printing repeated warning spam.
- This is especially useful for the O VII solver-response source-fit diagnostic, where some unit-source response matrices are rank-deficient because selected source levels do not independently constrain a unique sparse solution.
- The warning/fallback remains recorded in the solver summary via `solver_warning`; fitted source-response diagnostics should still be judged from the output summary ratios.

## v0.2.58 - 2026-04-20

- Added source-amplitude controls to `examples/13_o7_recombination_cascade_workflow.py`:
  - `--solver-source-scale` multiplies the source/sink CSV passed to the solver.
  - `--solver-source-total-rate` rescales the solver source CSV so the first T/ne block has a requested total source rate.
- This fixes the diagnostic mismatch where solver-response fitted weights from `examples/20_o7_solver_source_fit.py` were derived with unit source rate `1.0 s^-1`, but the cascade workflow applied them at the physical RR source scale (`~1.345e-12 s^-1` at ne=1), causing baseline collisional excitation to dominate.
- `examples/20_o7_solver_source_fit.py` now records `source_rate_s^-1`, `source_rate_note`, and `fit_source_rate_s^-1` in its outputs so the required workflow source amplitude is explicit.
- Recommended fitted-source workflow now uses `--solver-source-total-rate 1.0` when consuming default solver-response weights.

## v0.2.57 - 2026-04-19

Safety fix:
- Hardened NPZ hierarchy index-cache writing so it never uses or replaces the input `atdb.fits` path.
- The cache writer now rejects cache paths that resolve to the FITS file, uses a unique temporary filename in the cache directory, and verifies that the FITS file signature is unchanged before and after cache replacement.
- Added `--index-cache-path` to `examples/20_o7_solver_source_fit.py` so repeated unit-source solver runs can use an explicit cache file away from the XSTAR data file.

Recommended safe usage:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

## v0.2.56 - 2026-04-18

Fixed:
- Made explicit `--source-fit-weights-csv` paths strict, except for the documented legacy cascade-fit path `o7_cascade_source_fit/o7_source_fit_weights.csv`. This prevents a missing solver-response fit file such as `o7_solver_source_fit/o7_source_fit_weights.csv` from silently falling back to the packaged older cascade-fit reference by basename.

Added:
- Recombination summaries now record `source_fit_weights_csv_requested`, `source_fit_weights_csv_resolved`, `source_fit_weight_column`, and `n_source_fit_weights` so fitted-source workflow outputs show exactly which weight file was used.

Notes:
- The uploaded v0.2.55 solver-fit workflow used `solver_source_csv_mode=initial`, but its initial source weights matched the older packaged cascade-fit weights. This happened because the requested solver-response weights CSV was not found relative to the run directory and the basename fallback selected the packaged `o7_source_fit_weights.csv`. v0.2.56 fails fast instead.

## v0.2.55 - 2026-04-17

Fixed:
- Added lightweight `atdb.fits` path validation in the data resolver so empty, truncated, or wrong relative FITS paths fail with a clear message before Astropy raises a low-level `OSError: Empty or corrupt FITS file`.
- `python -m xstar_atomic.data --set-path ...` now rejects invalid `atdb.fits` candidates and suggests setting `XSTAR_ATDB_FITS` or the persistent datapath to the real local XSTAR atomic database.

Notes:
- This version does not change the O VII solver-response source-fit physics. It only improves diagnostics for the path problem seen when rerunning the v0.2.54 workflow with an empty/corrupt `../xstar/data/atdb.fits`.

## v0.2.54 - 2026-04-16

### Added
- Added `examples/20_o7_solver_source_fit.py`, a stricter O VII empirical diagnostic that fits source weights against the full `xstar_atomic.solver` unit-source response matrix rather than the simpler radiative cascade yield matrix.
- The new solver-response fit writes `o7_solver_response_matrix.csv`, `o7_solver_source_fit_weights.csv`, a compatibility alias `o7_source_fit_weights.csv`, and `o7_solver_source_fit_summary.json`.

### Changed
- Documented that the earlier cascade-yield source-fit weights are not expected to reproduce XSTAR R/G when injected into the full statistical-equilibrium solver, because the solver response includes radiative rates, branching, collisional coupling, and normalization effects beyond the cascade-yield matrix.

## v0.2.53 - 2026-04-15

Fixed:
  - examples/13_o7_recombination_cascade_workflow.py now feeds the initial fitted source CSV to the level-population solver for selected-fit-weights and o7-xstar-fit modes by default.
  - Added --solver-source-csv-mode auto|initial|cascade to make this behavior explicit and reproducible.
  - This avoids applying the radiative cascade twice: once in recombination.py and again inside the solver radiative network.

## v0.2.52 - 2026-04-14

Fixed:
- Resolved a path bug in `selected-fit-weights` workflows: missing relative weight CSV paths such as `o7_cascade_source_fit/o7_source_fit_weights.csv` are now resolved against packaged reference locations (`xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`) when the basename exists there.
- Updated the explicit `selected-fit-weights` documentation examples to use the packaged reference file `xstar_test_run/o7_source_fit_weights.csv`.

## v0.2.51 - 2026-04-14

- Added diagnostic source mode `selected-fit-weights`, which reads fitted level-source weights from `--source-fit-weights-csv`.
- Added convenience source mode `o7-xstar-fit`, which uses `xstar_test_run/o7_source_fit_weights.csv` when no explicit weight CSV is provided.
- Added O VII source-fit reference products to `xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`.
- Updated the O VII recombination/cascade workflow example to pass source-fit weight CSV options through to `xstar_atomic.recombination`.
- These modes are empirical/diagnostic only; they are not a replacement for true level-resolved recombination rates.

## v0.2.50 - 2026-04-13

- Added `examples/19_o7_cascade_source_fit.py`, a Stage-6 diagnostic for level-resolved O VII cascade-source construction from radiative yield matrices.
- The example builds `Y(source_level -> forbidden, intercombination, resonance)`, writes `o7_cascade_yield_matrix.csv`, fits nonnegative source weights against the saved XSTAR O VII `R=f/i` and `G=(f+i)/r` ratios, and writes `o7_source_fit_weights.csv` plus `o7_source_fit_summary.json`.
- Added helper tests for the nonnegative simplex projection and source-fit optimizer used by the diagnostic.

## v0.2.49 - 2026-04-12

- Added `examples/18_o7_type68_2d_cascade_tuning_scan.py`, a broader Stage-6 O VII type-68-aware tuning scan.
- The new scan varies both forbidden-to-intercombination redistribution and resonance-target suppression using maps of the form `2:(1-d),3:(1+d/3),4:(1+d/3),5:(1+d/3),7:r`.
- The scan writes compact, ranked, all-density CSV tables plus a JSON summary, so the best compromise against the XSTAR O VII `R=f/i` and `G=(f+i)/r` reference can be identified.
- Kept the equal-target `selected-cascade-yield` map as the documented Stage-6 baseline.

## v0.2.48 - 2026-04-11

### Added
- Added type-68-aware O VII cascade tuning presets that preserve equal triplet target weights while progressively downweighting the resonance target level 7: `o7-triplet-type68-r095`, `r090`, `r085`, `r080`, `r075`, `r070`, `r060`, and `r050`.
- Added `examples/17_o7_type68_cascade_tuning_scan.py` to run the equal baseline plus the type-68-aware resonance-weight grid, writing compact and all-density CSV/JSON summaries.

### Changed
- Documentation now distinguishes the pre-type-68 f2i/fdown scans from the type-68-aware resonance-weight scan needed after He-like collision types 67/68/69 are enabled.

## v0.2.47 - 2026-04-10

- Added He-like collisional-excitation decoders/evaluators for XSTAR data types 67, 68, and 69.
  - Type 67 follows `calt67`: `gamma = a + b log10(T) + c log10(T)^2`.
  - Type 68 follows `calt68`: `gamma = a + b log10(T/Z^3) + c log10(T/Z^3)^2`.
  - Type 69 follows `calt69`: Kato--Nakazaki He-like collision-strength fit.
- Extended `COLLISION_DATA_TYPES` to include 67, 68, and 69.
- Updated the O VII metastable/intercombination coupling diagnostic to write `o7_metastable_coupling_collision_inventory.csv`, which inventories all decoded/evaluated collision records involving the selected source/target levels.
- Added unit tests for the type-67/68/69 helper evaluators.

## v0.2.46 - 2026-04-09

Stage-6 diagnostic update.

Added:

- `examples/16_o7_metastable_coupling_diagnostics.py`, a focused O VII diagnostic for level 2 -> levels 3, 4, and 5.
- The diagnostic compares collisional transfer rates `C_2_to_j = n_e q_2j` with decoded radiative rates as a function of electron density.
- Outputs `o7_metastable_coupling_rates.csv` and `o7_metastable_coupling_summary.json`.

Notes:

- The equal-target `selected-cascade-yield` map remains the documented Stage-6 baseline.
- The new diagnostic is intended to determine whether the remaining high O VII `R=f/i` ratio is caused by under-coupled metastable/intercombination transfer or by source/cascade feeding.

## v0.2.45 - 2026-04-08

Stage-6 O VII cascade tuning update.

### Added
- Added forbidden-to-intercombination shift presets that preserve the resonance target and approximately preserve the total triplet-target weight:
  - `o7-triplet-f2i010-rkeep` -> `2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0`
  - `o7-triplet-f2i015-rkeep` -> `2:0.85,3:1.05,4:1.05,5:1.05,7:1.0`
  - `o7-triplet-f2i025-rkeep` -> `2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`
  - `o7-triplet-f2i050-rkeep` -> `2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0`

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the documented Stage-6 baseline.
- Updated `examples/15_o7_cascade_tuning_scan.py` so the default tuning scan now includes the new forbidden-to-intercombination shift presets before the older simple `fdown` comparison cases.
- Updated `o7-triplet-xstar-tuned` as a backward-compatible alias to the preferred `f2i025` shift experiment.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the new Stage-6 tuning strategy: preserve `G=(f+i)/r` by keeping the total triplet/resonance balance close to the equal-target case while shifting source weight from forbidden to intercombination levels.

## v0.2.44 - 2026-04-07

### Added
- Added Stage-6 O VII cascade tuning presets that downweight the forbidden target while preserving the resonance target: `o7-triplet-fdown090-rkeep`, `o7-triplet-fdown085-rkeep`, and `o7-triplet-fdown075-rkeep`.
- Added `examples/15_o7_cascade_tuning_scan.py`, which runs the equal-target baseline plus forbidden-downweighted presets and writes CSV/JSON summaries of `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII reference.

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the recommended Stage-6 baseline.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the Stage-6 tuning scan workflow.

## v0.2.43 - 2026-04-06

Completed Stage-5 heavy-ion XSTAR wavelength validation.

- Added validated Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI XSTAR `xout_lines1.fits` artifacts under `xstar_test_run/`.
- Added converted selected-line CSV products for Mg/Si/Fe validation under `xstar_test_run/`.
- Added Mg/Si/Fe wavelength comparison CSV/JSON files under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added tests checking the Mg/Si/Fe validation artifacts and wavelength matches.
- Updated README and Sphinx/Markdown comparison docs to mark Mg/Si/Fe Stage-5 validation as completed rather than pending.

## v0.2.42 - 2026-04-06

Stage-5 heavy-ion validation planning update.

- Added reproducible direct-XSTAR run recipes to `xstar_test_run/README.md` for Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI.
- Added suggested first-pass wavelength windows and `xstar_atomic.xstar_outputs` FITS-to-CSV commands for Mg/Si/Fe validation products.
- Added wavelength-comparison command templates for the corresponding `examples/08_compare_xstar_outputs.py` runs.
- Updated README and XSTAR comparison documentation to mark Mg/Si/Fe as the pending Stage-5 completion targets after the validated O/Ne workflow.

## v0.2.41 - 2026-04-05

- Fixed Sphinx ``user_guide.rst`` heading underline length for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.

## v0.2.40 - 2026-04-05

Fixed:

- Corrected the Sphinx user-guide heading underline for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.
- Kept the v0.2.39 documentation updates for ``download_data()``, data-path resolution, NPZ cache performance, and Stage-6 cascade workflow notes.

## v0.2.39 - 2026-04-05

Documentation and Stage-6 result update.

- Refreshed Markdown, LaTeX, and Sphinx documentation for the current data-management API: `download_data()`, `resolve_atdb_path()`, `find_atdb_file()`, `get_data_path()`, and `set_data_path()`.
- Documented path-resolution precedence: explicit path, `XSTAR_ATDB_FITS`, persistent `datapath`, project/package `data/atdb.fits`, then interactive download/configuration.
- Documented the single-line ASCII download progress bar and the source-tree default `data/` and `datapath` locations.
- Updated solver/cache documentation to recommend the array-backed NPZ cache path validated in v0.2.27/v0.2.28.
- Added Stage-6 result guidance: equal-target cascade-yield remains the recommended baseline; the `o7-triplet-fdown-rkeep` preset decreases `R=f/i` but also lowers `G=(f+i)/r`, so it is experimental.
- Fixed LaTeX listing styles using `ctpython` and `ctterminal`; Python listings now have syntax highlighting and terminal listings use a separate style.
- Normalized code listings so ion names appear as `O VIII`, not with visible-space markers.

## v0.2.38 - 2026-04-04

- Fixed `examples/13_o7_recombination_cascade_workflow.py` so the recommended equal O VII target map is only passed when no non-`none` `--cascade-target-preset` is selected.
- This prevents the default `--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` from overriding experimental presets such as `o7-triplet-fdown-rkeep`.
- The recommended Stage-6 baseline remains the equal-target map. The `o7-triplet-fdown-rkeep` preset remains an experimental forbidden-downweighted, resonance-preserved map.

## v0.2.37 - 2026-04-03

Stage-6 O VII cascade-source tuning update.

Changed:
- Keep the documented/recommended ``selected-cascade-yield`` target map as equal triplet targets: ``2:1.0,3:1.0,4:1.0,5:1.0,7:1.0``.
- Add a new forbidden-downweighted, resonance-preserved experimental preset: ``--cascade-target-preset o7-triplet-fdown-rkeep`` -> ``2:0.5,3:1.0,4:1.0,5:1.0,7:1.0``.
- Update ``o7-triplet-xstar-tuned`` as a backward-compatible alias to the new resonance-preserved map, replacing the earlier resonance-downweighted map.
- Update the Stage-6 workflow example and docs to avoid recommending the resonance-downweighted preset, which overestimated G=(f+i)/r.

## v0.2.36 - 2026-04-02

Fixed:
- Data-path helper round-trip test now removes ``XSTAR_ATDB_FITS`` during the isolated datapath test. This preserves the intended runtime precedence: explicit path, ``XSTAR_ATDB_FITS``, saved ``datapath``, project/package ``data/``, then interactive download/configuration.

Added:
- ``--cascade-target-preset o7-triplet-xstar-tuned`` for Stage-6 O VII triplet cascade-source experiments.
- The preset expands to ``2:0.6,3:1.0,4:1.0,5:1.0,7:0.4``.
- Manual ``--cascade-target-levels`` remains available and overrides the preset.

## v0.2.35 - 2026-04-01

Stage 6 recombination/cascade improvements:
- Added `selected-cascade-yield` recombination source allocation mode.
- Added `--cascade-target-levels` and `--cascade-weight-floor` to `xstar_atomic.recombination`.
- Updated the O VII recombination/cascade workflow example to use cascade-yield source weighting by default.
- Added unit coverage for cascade-yield source allocation helpers.

## v0.2.34 - 2026-03-31

- Added validated Ne IX / Ne X Stage-5 XSTAR comparison artifacts.
- Added `xstar_test_run/ne_xi25/xout_lines1.fits` and `xstar_test_run/ne_xi35/xout_lines1.fits`.
- Added converted CSV line lists for Ne IX triplet/near-triplet and Ne X Ly-alpha.
- Added saved comparison CSV/JSON outputs to `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Updated XSTAR comparison documentation from planned neon runs to completed validation examples.

## v0.2.33 - 2026-03-30

Documentation/examples:
- Added dedicated Stage-5 Ne IX and Ne X direct-XSTAR validation run commands to `xstar_test_run/README.md`.
- Added FITS-to-CSV and `examples/08_compare_xstar_outputs.py` commands for Ne IX He-like triplet/near-triplet and Ne X Ly-alpha wavelength comparisons.
- Updated XSTAR comparison documentation and Sphinx comparison page to list the planned Ne IX/Ne X validation products.

## v0.2.32 - 2026-03-29

Fixed:
  - Replaced multi-line download progress messages with a single in-place ASCII progress bar.
  - Download progress now displays as: `xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)`.

## v0.2.31 - 2026-03-28

Fixed:
- Store the source-tree ``datapath`` file at the project root (for example ``xstar_atomic/datapath``) rather than in ``src/xstar_atomic/``.
- Removed the packaged ``src/xstar_atomic/datapath`` data file from package-data/MANIFEST entries.
- Kept the project-level ``data/`` directory as the default ``atdb.fits`` download destination when running from ``PYTHONPATH=src``.

## v0.2.30 - 2026-03-27

Fixed:
- Changed the default interactive ``download_data()`` destination for source-tree use from ``src/xstar_atomic/data`` to the project-level ``data`` directory.
- Changed the source-tree ``datapath`` file location from ``src/xstar_atomic/datapath`` to the project-level ``datapath`` file, while retaining installed-package fallback behavior.

## v0.2.28 - 2026-03-25

Documentation/examples:
- Documented the validated array-backed NPZ cache performance from v0.2.27: O VIII sparse solver profile dropped from about 5.31 s uncached to about 0.53 s on an NPZ array-backed cache hit.
- Made the array-backed NPZ cache the recommended default for repeated solver, export, high-level API, and profiler workflows.
- Updated README, Markdown user guide, LaTeX user guide, and Sphinx user/examples pages with `--index-cache --index-cache-format npz` examples.
- Updated `examples/12_profile_solver_steps.py` documentation to use the recommended NPZ cache path.

## v0.2.27 - 2026-03-24

Fixed:
- Restored the public array-backed `ATDB.select_records(z=..., ion_stage=..., data_type=..., rate_type=...)` API by renaming the legacy materialized-list filter helper to `filter_records`.
- Fixed `examples/12_profile_solver_steps.py --index-cache --index-cache-format npz`, which failed in v0.2.26 because the legacy helper shadowed the new fast-selection method.

## v0.2.26 - 2026-03-23

Added:
- Added `ATDBIndexArrays`, an array-backed hierarchy index for fast targeted selection.
- Added `ATDB.build_index_arrays(...)` and `ATDB.select_records(...)`.
- NPZ cache hits can now filter numeric arrays and convert only selected rows to `IndexedRecord` objects.
- Updated solver, profiler, and high-level API paths to use array-backed selection for NPZ index caches.
- Added tests for array-backed selection/reconstruction.

Changed:
- `--index-cache-format npz` now avoids reconstructing all 1.2 million records in targeted solver/profiler/API paths.

## v0.2.25 - 2026-03-22

Fixed:
- Reworked the NPZ index cache into a slimmer numeric v2 layout.
- Avoided storing large repeated Unicode arrays for each ATDB record in the NPZ cache.
- Old v0.2.24 NPZ caches are now treated as stale and rebuilt automatically.

Changed:
- The compact cache still returns normal IndexedRecord objects for decoder compatibility, but reconstructs repeated labels from numeric fields and the small element/ion tables.

## v0.2.24 - 2026-03-21

Added:
- Added compact NumPy/NPZ hierarchy index cache support for `ATDB.build_index()`.
- `--index-cache` now defaults to the NPZ cache path `atdb.fits.xstar_atomic_index.npz`.
- Added `--index-cache-format npz|pickle` to hierarchy, solver, export, and solver-step profiler CLIs.
- Preserved legacy pickle cache support with `--index-cache-format pickle`.

Changed:
- `XSTARAtomic(..., index_cache=True)` now uses the NPZ cache by default.
- Cache status strings now distinguish `npz_hit`, `npz_written`, `pickle_hit`, and related states.

## v0.2.23 - 2026-03-20

Added:
- Optional on-disk ATDB hierarchy index caching via ``ATDB.build_index(use_cache=True)``.
- ``--index-cache`` and ``--rebuild-index-cache`` options for the hierarchy, solver, export, and solver-step profiling workflows.
- Cache metadata validation against the source ``atdb.fits`` file size, modification time, array lengths, and cache format version.
- Real-ATDB cache round-trip test for cache creation and cache hits.

Changed:
- Solver/export/profile summaries now report ``index_cache_status`` and ``index_cache_path`` when caching is used.

## v0.2.22 - 2026-03-19

### Fixed

- Fixed `examples/12_profile_solver_steps.py` by adding the missing
  `auto_recombination_cascade=False` default to the solver argument namespace used
  by the profiling workflow.

### Documentation

- Documented that an optional C++ backend can be implemented as a shared-object
  library while preserving the Python/SciPy reference backend.
- Added notes on the Stage-6 O VII recombination/cascade workflow: total O VIII
  -> O VII recombination is redistributed over selected O VII levels, radiative
  branching cascade sources are written to CSV, the sparse solver reads those
  sources, and prototype R=f/i and G=(f+i)/r diagnostics are compared with XSTAR
  triplet output ratios.

## v0.2.21 - 2026-03-18

### Added
- Added `examples/12_profile_solver_steps.py` to profile individual solver stages: ATDB open/read, index building, level/line/collision extraction, collision evaluation, matrix assembly, solve, and output writing.
- Added `examples/13_o7_recombination_cascade_workflow.py`, a prototype Stage-6 O VII workflow that builds recombination source CSVs, performs approximate radiative cascade redistribution, feeds the cascade source into the sparse solver, and compares O VII triplet diagnostics with an optional XSTAR line-output CSV.

### Notes
- Documented that an optional C++ backend can be implemented as a shared-object (`.so`) library loaded from Python, with the pure-Python/SciPy implementation retained as the reference/fallback path.
- The O VII cascade workflow remains a prototype: current oxygen RR/DR records are total recombination rates, not true level-resolved recombination-cascade records.

## v0.2.20 - 2026-03-17

### Added
- Added `examples/11_solver_timing.py` to benchmark end-to-end level-population solver execution times.
- The timing example compares O VIII dense and sparse solver modes and can optionally include the heavier O VII triplet sparse stress test.
- Timing CSV rows include elapsed wall time, solver used, sparse status, matrix size, nonzero count, density, condition number, and residual diagnostics.

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user guides with solver timing commands and notes on when a C++ backend could improve performance.

## v0.2.19 - 2026-03-16

### Solver
- Improved Stage-3 level-population solver diagnostics for sparse and dense solves, including matrix nonzero counts, matrix density, singular-value/rank diagnostics, diagonal and row-sum ranges, residual norms, and explicit sparse-use flags.
- Added optional connectivity pruning with `--prune-unconnected-levels`, preserving ground, output, and explicit source/sink levels.
- Added source/sink vector summaries to solver JSON output, including nonzero level terms and source/sink totals for recombination/cascade source-file tests.
- Added O VII triplet diagnostic support with `--triplet-diagnostics` and `--out-triplet-csv`, reporting prototype `R=f/i` and `G=(f+i)/r` ratios when O VII triplet lines are selected.

### Documentation and examples
- Updated the user guide and examples for sparse solver runs, connectivity pruning, source/sink diagnostics, and O VII triplet diagnostics.
- Added `examples/10_o7_triplet_sparse_solver.py` as the Stage-3 solver stress-test example.

### Tests
- Added unit tests for solver diagnostics, pruning, source/sink summaries, and O VII triplet R/G helper calculations.

## v0.2.18 - 2026-03-15

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user-guide material for the validated Stage-4 band-emissivity export workflow.
- Documented `--bands-kev`, `*_band_emissivity.csv`, and HDF5 `/band_emissivity` products.
- Recorded the v0.2.17 Stage-4 real-ATDB validation result: 34 passing tests, 12 band-emissivity rows per ion for four bands and three temperatures, nonblank `ion`, and `methods_used="none"` for zero-line bands.

### Examples
- Added `examples/09_export_band_emissivity.py` for CSV/HDF5 export of line-based X-ray band emissivity products.

## v0.2.17 - 2026-03-14

### Fixed
- Filled the `ion` field for all band-emissivity rows, including zero-line bands.
- Set `methods_used="none"` for zero-line band-emissivity rows.

### Tests
- Added unit and real-ATDB export tests that check band-emissivity rows do not contain blank ion names or blank method fields.

## v0.2.15 - 2026-03-13

### Added
- Added HDF5 export support to `xstar_atomic.export` via `--formats hdf5` or `--formats csv,hdf5`.
- Added a general CLI alias `xstar-atomic-export` while keeping `xstar-atomic-export-superwind` for backward compatibility.
- Added optional SciPy sparse-matrix support to the level-population solver via `--linear-solver sparse` or `--linear-solver auto`.
- Added tests for HDF5 export helpers and sparse-solver fallback/consistency.

### Changed
- Generalized export documentation and manifests for plasma post-processing workflows beyond superwinds, including AGN outflows.
- The export manifest is now written as `atomic_export_manifest.json` and also as the legacy `superwind_export_manifest.json`.


## v0.2.14 - 2026-03-12

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.13 - 2026-03-11

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.12 - 2026-03-10

### Added
- Added saved XSTAR-vs-`xstar-atomic` comparison outputs for O VIII Ly-alpha and the O VII triplet under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added `docs/xstar_comparison_examples.md` documenting the XSTAR-output comparison workflow and validation results.
- Added Sphinx page `xstar_comparisons.rst` and linked it from the Sphinx index.

### Documentation
- Documented that O VIII Ly-alpha wavelength agreement is at the ~1e-5 Angstrom level.
- Documented that O VII triplet wavelength agreement is at the ~1e-7 to 8e-7 Angstrom level.
- Clarified that XSTAR model `emit_*` columns are not directly equivalent to local `xstar-atomic` emissivity coefficients without model-dependent normalization.

## v0.2.11 - 2026-03-09

Added:
- Extended ``examples/08_compare_xstar_outputs.py`` with explicit ``--mode`` choices: ``wavelength``, ``emissivity``, and ``both``.
- Added ``--out-csv`` and ``--out-json`` outputs for XSTAR-vs-xstar-atomic comparison tables.
- Added clearer warnings/notes that XSTAR model ``emit_*`` columns are not directly equivalent to local atomic emissivity coefficients.

## v0.2.10 - 2026-03-08

Fixed:
- Added `--wavelength-column` to `examples/08_compare_xstar_outputs.py`.
- The comparison example now auto-detects `wavelength_A` or `wavelength` columns in XSTAR-output CSV files.

## v0.2.9 - 2026-03-07

### Added
- Added `xstar_atomic.xstar_outputs` for reading XSTAR `xout_lines*.fits` files.
- Added CLI entry point `xstar-atomic-xstar-outputs` and module execution with `python -m xstar_atomic.xstar_outputs`.
- Supports CSV export, JSON summaries, and filtering by ion, wavelength, and emission columns.

## v0.2.8 - 2026-03-06

### Fixed
- Added the missing solver CLI argument `--electron-density-for-lmixing`.
- Fixed the real-ATDB solver status test failure caused by the solver referencing `args.electron_density_for_lmixing` without registering the argparse option.

## v0.2.7 - 2026-03-05

### Added
- Added a scientific validation status table to the Markdown and LaTeX user guides.
- Added `xstar_atomic.export` with CSV/JSON export helpers for superwind/Athena++ post-processing.
- Added CLI entry point `xstar-atomic-export-superwind`.
- Added `examples/08_compare_xstar_outputs.py` for comparing selected xstar-atomic outputs against user-supplied XSTAR CSV outputs.
- Added lightweight import tests for the export module.

### Improved
- Updated solver diagnostics to report that the XSTAR-derived type-63 same-n l-mixing collision decoder is enabled.
- Updated docs to reflect the implemented type-63 same-n l-mixing path and the current validation status of data types 51 and 98.

## v0.2.6 - 2026-03-04

### Added
- Added `tests/data/collision_type51_98_targets.csv`, generated from the collision validation inventory.
- Added API-level real-ATDB pytest coverage for representative collision `data_type=51` and `data_type=98` targets through `XSTARAtomic.collisions(...)`.
- Added a type-98 ion-alias API regression test using the `ne_ix` alias.

### Validation
- The type-51 API test validates a representative Burgess--Tully 5-point target against the inventory reference rate.
- The type-98 API test validates the Ne IX CHIANTI-style Burgess--Tully target against the inventory reference rate.

## v0.2.5 - 2026-03-03

### Fixed
- Restored the lightweight top-level `parse_ion` export so `from xstar_atomic import parse_ion` works again after the lazy-import cleanup.
- Kept the minimal top-level API limited to `ATDB`, `XSTARAtomic`, and `parse_ion`; decoder functions remain importable from their submodules.


## v0.2.4 - 2026-03-02

### Fixed
- Cleaned reStructuredText in module docstrings for the Sphinx API build.
- Fixed docutils warnings/errors in `photoionization`, `collisions`, and `recombination` module documentation.

## v0.2.3 - 2026-03-01

### Added
- Added `xstar_atomic.validation` with collision-decoder inventory and validation helpers.
- Added CLI entry point `xstar-atomic-validate-collisions`.
- Added `examples/07_collision_decoder_validation.py` for type 51/98 target discovery and type-63 same-`n` diagnostics.
- Added real-ATDB pytest checks for:
  - O VIII type-63 same-`n` l-mixing regression diagnostics.
  - Type 51 and type 98 inventory plus representative positive-rate targets when present in the local `atdb.fits`.

### Notes
- The type-63 same-`n` diagnostic checks the Python port of the XSTAR `amcrs/velimp` branch, but independent validation against XSTAR model outputs is still recommended for production science.

## v0.2.2 - 2026-02-28

### Fixed
- Corrected LaTeX backslash corruption in `docs/user_guide.tex` for the `center` and `tabular` environments.

## v0.2.1 - 2026-02-27

### Changed
- Simplified ``xstar_atomic.__init__`` to expose only ``ATDB``, ``XSTARAtomic``, and ``__version__``.
- Moved heavy decoder imports in ``api.py`` to lazy method-level imports.
- Preserved submodule-level imports such as ``xstar_atomic.collisions`` and ``xstar_atomic.recombination``.

### Fixed
- Avoids ``runpy`` warnings when executing CLI modules with ``python -m xstar_atomic.<module>`` after importing the package.

## v0.2.0 - 2026-02-26

### Added
- Implemented the type-63 same-`n` l-changing collision branch using the XSTAR `amcrs`/`velimp` ecm=0 logic.
- Added `electron_density_for_lmixing` to the high-level collision/emissivity APIs for the density-dependent impact-parameter cutoff used by same-`n` l-mixing.
- Added `--electron-density` to `xstar-atomic-collisions` and `--electron-density-for-lmixing` to emissivity/solver CLIs.
- Added diagnostic columns for same-`n` type-63 l-mixing: shell radiative sum, `cn`, selected `l` branch, and density.

### Improved
- Promoted collision data type 51 and 98 Burgess--Tully evaluators as supported collision-rate paths alongside type 56 and type 63.
- Updated package tests to check that real-ATDB type-63 same-`n` l-mixing returns finite evaluated rates when `XSTAR_ATDB_FITS` is supplied.

## v0.1.8 - 2026-02-25

### Documentation
- Added `\usepackage{amsmath,amssymb}` to the LaTeX user guide preamble for math support.


All notable changes to `xstar-atomic` are documented here.

## v0.1.7 - 2026-02-24

Fixed:
- Restored backward-compatible high-level API keys used by the examples:
  - `collisions()["matches"]` and `collisions()["evaluated_rates"]`.
  - `emissivity()["rows"]`.
  - `recombination()["summary"]`.
- Updated example/API behavior so the examples work with the current return dictionaries.

## v0.1.6 - 2026-02-23

### Added
- Added full user guide in Markdown: `docs/user_guide.md`.
- Added full user guide in LaTeX: `docs/user_guide.tex`.
- Added Sphinx documentation scaffold under `docs/sphinx/` using `sphinx.ext.autodoc`, `sphinx.ext.napoleon`, and the Read the Docs theme.
- Added Sphinx pages for user guide, examples, API reference, development notes, and changelog.
- Added `examples/06_high_level_api_quickstart.py`.
- Added optional `docs` dependency group with `sphinx` and `sphinx-rtd-theme`.

### Notes
- Sphinx API pages are generated from Python docstrings. Future public functions/classes should include clear docstrings.

## v0.1.5 - 2026-02-22

### Added
- Added flexible ion-name parsing in the high-level API. Accepted forms now include `O VIII`, `o viii`, `o_viii`, `O_VIII`, `O-VIII`, `OVIII`, and `o8`.
- Added unit tests for ion-name aliases.

## v0.1.4 - 2026-02-21

### Added
- Added real pytest smoke tests for the direct `atdb.fits` workflow.
- Added API smoke tests for:
  - low-level `ATDB.build_index()` counts,
  - O VIII Ly-alpha line extraction,
  - O VIII Ly-alpha collision-rate evaluation,
  - O VIII Ly-alpha emissivity table generation,
  - oxygen recombination inventory.
- Added CLI smoke tests using `python -m xstar_atomic.*` modules.
- Added `examples/` scripts:
  - `01_o8_lya_lines.py`,
  - `02_o8_lya_collisions.py`,
  - `03_o8_lya_emissivity.py`,
  - `04_oxygen_recombination_inventory.py`,
  - `05_low_level_atdb_index.py`.
- Added this versioned `CHANGELOG.md`.

### Notes
- Tests that require the real XSTAR database are skipped unless `XSTAR_ATDB_FITS` points to a readable `atdb.fits` file.
- Example test command:

  ```bash
  XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
  ```

## v0.1.3 - 2026-02-20

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `collision_data_type` default expected by the emissivity filters.

## v0.1.2 - 2026-02-19

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `include_superlevel_radiative` default expected by the emissivity filters.

## v0.1.1 - 2026-02-18

### Added
- Added the high-level `XSTARAtomic` API wrapper around the low-level `ATDB` reader.
- Added convenience methods for lines, collisions, recombination, and emissivity workflows.
- Kept `ATDB` as the low-level direct packed-FITS API.

## v0.1.0 - 2026-02-17

### Added
- Initial package refactor from validated standalone scripts.
- Added package namespace `xstar_atomic` and project name `xstar-atomic`.
- Added command-line modules for:
  - inspecting `atdb.fits`,
  - hierarchy reconstruction,
  - lines,
  - photoionization,
  - collisions,
  - recombination,
  - emissivity,
  - prototype level-population solving.

## v0.2.82 - 2026-04-28

- Added reference snapshots for the v0.2.81 O VII type-69 mode comparison: `o7_density_grid_type69_mode_compare.csv` and `o7_density_grid_type69_mode_compare_summary.json` under both `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added regression tests that lock in the benchmark behavior: the default `include` network is not reachable at `ne=1e12 cm^-3`, while diagnostic/experimental `suppress-resonance` is reachable and matches the density-specific XSTAR R/G target; lower-density rows remain reachable in both modes.
- Expanded documentation for the O VII high-density benchmark result and reiterated that `suppress-resonance` is a validated diagnostic switch for this benchmark, not a general physical default.

## v0.2.81 - 2026-04-28

- Added `examples/30_o7_density_grid_type69_mode_compare.py`, a side-by-side O VII density-grid comparison of the original type-69 network (`include`) and the diagnostic `suppress-resonance` mode.
- The comparison runs the density-dependent XSTAR grid workflow for both modes, then writes `o7_density_grid_type69_mode_compare.csv` and a JSON summary with per-density R/G ratios, reachability flags, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.
- Documented that `--collision-type69-ground-excitation-mode suppress-resonance` is diagnostic/experimental: it is validated for the O VII high-density benchmark but is not a general physical default.

## v0.2.80 - 2026-04-28

- Fixed `--collision-type69-ground-excitation-mode suppress-resonance` in `xstar_atomic.solver`.
  v0.2.79 validated the command-line propagation through examples 22 -> 21 -> 20, but the row-level
  mode handler incorrectly raised an error for non-resonance collision rows whenever the mode was
  `suppress-resonance`. The handler now validates the mode once, then applies suppression only to
  matching type-69 ground-to-resonance rows and leaves all other collision rows unchanged.
- Added a regression test that `suppress-resonance` leaves unrelated type-69 rows valid while suppressing
  the O VII ground-to-resonance excitation row.

## v0.2.79 - 2026-04-27

- Fixed propagation of `--collision-type69-ground-excitation-mode` through the chained O VII density-grid workflow.  In v0.2.78, examples 21/22 forwarded the option to `examples/20_o7_solver_source_fit.py`, but example 20 did not expose the corresponding CLI parser option, causing an `unrecognized arguments` failure.
- Added a regression check that example 20 exposes the type-69 ground-excitation suppression option used by the v0.2.78 density-grid command.

## v0.2.78 - 2026-04-27

- Added the diagnostic/experimental solver option `--collision-type69-ground-excitation-mode include|suppress-resonance|suppress-all`.  The `suppress-resonance` mode suppresses type-69 excitation from the ground level into the He-like resonance upper level while preserving the de-excitation direction; for the validated O VII case this targets record 22490, level 1 -> 7.
- Propagated the new mode through `examples/20_o7_solver_source_fit.py`, the density-grid front end (`examples/21/22`), the rate-sensitivity diagnostic (`examples/26`), and the ground-coupling diagnostic (`examples/29`).
- Extended `examples/29_o7_type69_ground_coupling_diagnostic.py` with built-in solver-switch cases for `suppress-resonance` and `suppress-all`, allowing direct comparison with the previous record/direction scaling experiments.
- Added regression coverage for the new switch and the O VII ground-resonance row selection logic.

## v0.2.77 - 2026-04-27

- Hotfix for `examples/29_o7_type69_ground_coupling_diagnostic.py`: fixed `top_weight()` so empty or missing weights-path fields in the example-20 summary are not interpreted as `Path(".")`, which caused `IsADirectoryError` during the baseline case.
- The ground-coupling diagnostic now falls back to the standard per-case fit outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`) when the summary omits a usable weights path.
- Added a regression test for the empty-path/directory fallback.

# Changelog

## v0.2.76 - 2026-04-27

- Fixed the v0.2.75 O VII type-69 record-audit annotation lookup so `examples/28_o7_type69_record_audit.py` can find `o7_type69_transition_sensitivity.csv` when given either the CSV path, the output directory, or a parent directory.
- Added `examples/29_o7_type69_ground_coupling_diagnostic.py` to interpret the high-density record-22490 ground--resonance coupling.  The diagnostic compares baseline, record-scaled, all-type-69-scaled, record-removed, excitation-only, de-excitation-only, and direction-specific variants.
- Added solver support for diagnostic direction-specific collision scaling via `--collision-record-direction-scale RECORD:DIRECTION:SCALE`, propagated through `examples/20_o7_solver_source_fit.py`.  This is explicitly diagnostic and intentionally can break detailed balance to isolate excitation versus de-excitation effects.
- Added regression tests for the record-audit annotation lookup, ground-coupling case builder, and direction-scale parser.

## v0.2.75 - 2026-04-27

- Added `examples/28_o7_type69_record_audit.py`, a targeted O VII high-density diagnostic that audits raw XSTAR type-69 records, with emphasis on records `22490`--`22495` and the record `22490` level `1 -> 7` channel identified by the v0.2.74 transition-sensitivity scan.
- The audit writes raw record metadata, decoded level labels/energies/statistical weights, Kato--Nakazaki `calt69` effective collision strengths, excitation/de-excitation coefficients, density-scaled rates, detailed-balance checks, and temperature-grid behavior.
- The audit can optionally ingest the v0.2.74 `o7_type69_transition_sensitivity.csv` output and annotate each record with its best sensitivity case and reachable scaling factors.
- Added regression tests for the new audit helper functions.

## v0.2.74 - 2026-04-27

Added:
- Added `examples/27_o7_type69_transition_sensitivity.py`, a high-density O VII diagnostic that scans individual XSTAR type-69 collision records or level pairs to identify which transitions drive the `ne=1e12 cm^-3` triplet mismatch.
- Added diagnostic collision record scaling to `xstar_atomic.solver` via `--collision-record-scale RECORD:SCALE`; the existing O VII solver-source-fit example now propagates this option to all unit-source and combined-source solver calls.
- Added `tests/test_o7_type69_transition_sensitivity.py` for the transition-sensitivity helper logic.

Notes:
- This is a diagnostic sensitivity scan only. Record-specific or pair-specific scaling is not a physical correction by itself; it is intended to isolate the type-69 transition(s) that make the high-density XSTAR target reachable.

## v0.2.73 - 2026-04-27

Added:
- Added `examples/26_o7_high_density_rate_sensitivity.py`, a high-density O VII rate-network sensitivity diagnostic for the `ne=1e12 cm^-3` mismatch.
- Added diagnostic collision-rate scaling controls to `xstar_atomic.solver`:
  - `--collision-rate-scale` for global evaluated electron-impact rates,
  - `--collision-data-type-scale DATA_TYPE:SCALE`,
  - `--collision-pair-scale LEVEL1:LEVEL2:SCALE`.
- Propagated the diagnostic collision-rate scaling options through `examples/20_o7_solver_source_fit.py` so empirical source fits can be repeated for scaled rate networks.
- Added `tests/test_o7_high_density_rate_sensitivity.py` for scan-case construction and scale specification checks.

Notes:
- The new rate scales are diagnostic sensitivity factors only. They do not modify the packaged atomic data and should not be interpreted as recommended physical rate corrections.
- The primary goal is to determine whether the high-density O VII mismatch is driven by type-68/69 or level-2-to-3/4/5 collisional coupling, or whether additional physics is required.

## v0.2.72 - 2026-04-27

Added:
- `examples/25_o7_high_density_expanded_source_scan.py` for expanded O VII high-density source-level scans.
- The new diagnostic tests whether larger source bases (`baseline`, `n<=5`, `n<=6`, `n<=8`, and `all_levels`) can reach the density-specific XSTAR target at `ne=1e12 cm^-3`.
- `tests/test_o7_high_density_expanded_source_scan.py` dry-run coverage for CI-friendly source-set planning.

## v0.2.71 - 2026-04-27

Added:
- Added `examples/24_o7_high_density_mismatch_diagnostics.py` to investigate the O VII high-density (`ne=1e12 cm^-3`) density-grid mismatch.
- The new diagnostic reads outputs from `examples/21`/`examples/22` and writes component, source-weight, collision-rate, and JSON summary diagnostics.
- It reports which triplet component drives the mismatch, whether the target is reachable, source-weight collapse metrics, solver diagnostics, and optional type-68/69 level-2 -> level-3/4/5 collision rates when `atdb.fits` is supplied.

Updated:
- Documented the high-density mismatch workflow in README, Markdown, LaTeX, and Sphinx example documentation.

## v0.2.70 - 2026-04-27

Added:
- Added `examples/23_prepare_o7_xstar_density_grid.py`, which prepares real O VII XSTAR density-grid validation runs at `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3`.
- The helper writes `xstar_runs/o7_ne*/run_xstar.sh` scripts containing the full XSTAR commands, `convert_o7_triplet.sh` scripts for converting `xout_lines1.fits` to O VII triplet CSV files, a density-to-CSV mapping file `xstar_o7_density_grid_references.csv`, a run-plan CSV, and `xstar_runs/README_o7_density_grid.md` containing all commands.
- Added tests for the run-preparation helper and generated command contents.

Notes:
- The helper does not run XSTAR.  It prepares reproducible external XSTAR commands and conversion commands so `examples/22_o7_solver_source_fit_density_xstar_grid.py` can later perform a true density-dependent XSTAR comparison once the XSTAR runs have been completed.

## v0.2.69 - 2026-04-27

Fixed:
- Improved `examples/22_o7_solver_source_fit_density_xstar_grid.py` when the requested `--xstar-grid-summary-csv` file is missing. The wrapper now writes a template density-to-XSTAR-lines mapping CSV and exits with a clear message instead of failing with a raw `FileNotFoundError`.

Added:
- `--write-template-grid-csv` to create a starter density-reference mapping CSV.
- `--allow-placeholder-grid` for low-density-placeholder smoke tests only.
- Packaged template CSVs under `examples/reference_inputs/` and `docs/validation/xstar_inputs/`.

Notes:
- The template intentionally reuses the packaged low-density O VII reference as a placeholder for every row. Replace each `xstar_lines_csv` entry with a converted density-specific XSTAR line CSV before using it for scientific validation.

# CHANGELOG

## v0.2.68 - 2026-04-27

Density-dependent XSTAR references for the O VII density-grid diagnostic.

Added:
- Added `examples/22_o7_solver_source_fit_density_xstar_grid.py`, a density-dependent XSTAR reference front end for the O VII density-grid source-fit diagnostic.
- Added `--xstar-lines-csv-by-density DENSITY:CSV` and `--xstar-grid-summary-csv` support to `examples/21_o7_solver_source_fit_density_grid.py`, allowing each density to be compared against its own XSTAR line CSV instead of reusing a single low-density reference.
- Added reference snapshots for the O VII density-grid diagnostic under `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added lightweight tests for density-specific XSTAR reference parsing, dry-run command generation, and the new example-22 front end.

Documentation:
- Added a short validated O VII diagnostic commands section to README, Markdown guide, LaTeX guide, and Sphinx examples.
- Added a top-level known-limitation note that empirical O VII fitted source weights are diagnostic and are not physical level-resolved recombination rates.
- Documented the density-dependent XSTAR mapping CSV format and repeated `--xstar-lines-csv-by-density` syntax.

## v0.2.67 - 2026-04-27

Data-path resolver and test isolation fixes.

Fixed:
- `resolve_atdb_path(path, prompt=False)` now treats an explicitly supplied path as strict precedence.  If that path is invalid, it raises a clear error instead of silently falling back to `XSTAR_ATDB_FITS` or a saved datapath.
- Updated data-path helper tests to use a minimal FITS-like file that passes the lightweight resolver validation added for zero-byte/truncated-file protection.
- Isolated data-path helper tests from the `XSTAR_ATDB_FITS` environment variable so full-suite runs with a real ATDB configured do not mask explicit-path behavior.

Notes:
- This is a bug-fix release for the v0.2.66 test failures observed when running `XSTAR_ATDB_FITS=../xstar/data/atdb.fits PYTHONPATH=src pytest -q`.

## v0.2.66 - 2026-04-27

Density-grid feasibility flags and clearer XSTAR-target labeling.

Changed:
- Updated `examples/21_o7_solver_source_fit_density_grid.py` so the reused XSTAR target is explicitly labeled as a low-density XSTAR O VII reference reused at all densities.
- Added fit-feasibility columns: `fit_success_vs_xstar` and `target_reachable`.
- Added ratio columns: `refitted_R_over_xstar`, `refitted_G_over_xstar`, `fixed_R_over_refitted`, and `fixed_G_over_refitted`.
- Added warning generation when the source-fit objective is large or the refitted combined R/G ratios remain outside tolerance, with explicit high-density wording for the type-68 coupling regime.
- The density-grid summary JSON now records the XSTAR target label, feasibility tolerances, warnings, and per-density feasibility flags.
- Added tests for the new density-grid feasibility logic and warning behavior without requiring full `atdb.fits`.

Notes:
- The current density-grid example still uses one XSTAR reference at all densities.  A later extension should allow density-dependent XSTAR references, for example `--xstar-lines-csv-by-density` or `--xstar-grid-summary-csv`.

## v0.2.65 - 2026-04-27

Density-grid O VII solver-source-fit diagnostic.

Added:
- Added `examples/21_o7_solver_source_fit_density_grid.py`, which runs the validated O VII full-solver source-fit workflow over a density grid.  The default grid is `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3` at `T = 1e6 K`.
- The density-grid diagnostic reports both fixed-weight validation, using the reference `ne=1 cm^-3` fitted weights at all densities, and separately refitted weights at each density.
- The output CSV `o7_solver_source_fit_density_grid.csv` includes XSTAR R/G, fixed-weight R/G, refitted linear-response R/G, refitted combined simultaneous-solver R/G, matrix rank, condition number, residuals, negative-population diagnostics, and weight-change metrics relative to the reference density.
- The output JSON `o7_solver_source_fit_density_grid_summary.json` records per-density summary paths, fixed-weight validation products, solver diagnostics, and the largest source-weight changes.
- Added lightweight tests in `tests/test_o7_solver_source_fit_density_grid.py` for the new density-grid example, including dry-run command construction and reference-density ordering without requiring the full `atdb.fits`.

Notes:
- This diagnostic is intended to show whether the empirical fitted O VII source distribution is stable or density-dependent after type-68 metastable/intercombination coupling is active.
- The fitted weights remain empirical solver-response weights, not physical level-resolved recombination rates.

## v0.2.64 - 2026-04-26

Regression/reference checks for the validated O VII solver-source-fit workflow.

Added:
- Added compact saved reference output `examples/reference_outputs/o7_solver_source_fit_summary_reference.json` for the validated O VII full-solver source-fit diagnostic.  This reference stores the XSTAR R/G target, fitted linear-response R/G, combined simultaneous-solver R/G, SVD solver diagnostics, null-rate pruning diagnostics, and negative-population handling without requiring the full 830 MB `atdb.fits` in CI.
- Added `tests/test_o7_solver_source_fit_reference.py` with CI-friendly tests that verify:
  - fitted linear-response R/G matches the saved XSTAR reference,
  - combined-source validation agrees with the fitted linear-response prediction to tight tolerance,
  - the validated diagnostic path uses `linear_solver=svd`, `rank_deficient_action=svd`, `negative_population_action=keep`, and null-rate pruning,
  - the raw-response simplex fitting helper remains numerically reproducible.
- Added a warning in `examples/13_o7_recombination_cascade_workflow.py` when `selected-fit-weights` or `o7-xstar-fit` is used without `--solver-source-total-rate`.  The warning tells users to pass `--solver-source-total-rate 1.0` when consuming weights produced by `examples/20_o7_solver_source_fit.py` with the default `--source-rate=1.0`.
- Workflow summaries from `examples/13_o7_recombination_cascade_workflow.py` now include a `warnings` list so this source-amplitude warning is preserved in machine-readable outputs.

Notes:
- These tests are reference/regression tests for the validated diagnostic output, not full physical ATDB tests.  Full real-ATDB validation is still done by running examples 20 and 13 locally with the real XSTAR `atdb.fits`.
- The empirical fitted-source mode remains diagnostic and amplitude-dependent, not a physical level-resolved recombination model.

## v0.2.63 - 2026-04-25

Documentation update for the validated O VII full-solver source-fit path.

Changed:
- Updated README and Markdown user guide with the validated O VII solver settings: `--linear-solver svd`, `--rank-deficient-action svd`, `--negative-population-action keep`, and `--prune-null-rate-levels`.
- Documented that the combined-source validation in `examples/20_o7_solver_source_fit.py` matches the saved XSTAR O VII triplet ratios with `R/R_XSTAR = 1.00000146` and `G/G_XSTAR = 0.99999836` in the v0.2.62 validation run.
- Added the same validated command sequence to the recombination/cascade workflow documentation, including `--solver-source-total-rate 1.0` and the SVD/rank-aware solver controls.
- Updated the LaTeX user guide with a dedicated Stage-6 full-solver source-fit section and a compact diagnostic summary table.
- Updated Sphinx examples documentation with the same validated workflow and diagnostic caveats.

Notes:
- The fitted source weights remain empirical/diagnostic, not true level-resolved recombination rates.
- Direct dense or sparse solvers are not recommended for this O VII diagnostic unless residuals and combined-source validation are explicitly checked, because the matrix is rank-deficient and highly ill-conditioned.

## v0.2.62 - 2026-04-24

Automatic combined-source validation for the O VII solver-response source-fit diagnostic.

Added:
- `examples/20_o7_solver_source_fit.py` now runs one simultaneous combined-source validation solve after fitting the nonnegative source weights, unless `--skip-combined-validation` is supplied.
- The validation writes `combined_source_validation/o7_combined_fitted_sources.csv`, `o7_combined_solver_lines.csv`, `o7_combined_solver_triplet.csv`, and `o7_combined_solver_summary.json`.
- The top-level `o7_solver_source_fit_summary.json` now reports three R/G comparisons in one place: XSTAR reference, fitted linear-response prediction, and combined simultaneous-solver validation.
- Combined validation diagnostics include matrix rank/size, condition number, linear residuals, source/sink summary, null-rate pruning diagnostics, and raw negative-population counts/minimum/sum diagnostics.
- New options: `--skip-combined-validation` and `--combined-source-total-rate` for controlling the simultaneous validation solve.

Purpose:
- This prevents confusion between an exact response-matrix fit and the actual behavior when the fitted sources are injected together into the full statistical-equilibrium solver.

## v0.2.61 - 2026-04-23

Numerical solver hardening for Stage-6 O VII diagnostics.

Added:
- Rank-aware matrix handling in `xstar_atomic.solver` via `--rank-deficient-action warn|lstsq|svd|reject`.
- Explicit least-squares/SVD solver choices through `--linear-solver lstsq|svd` in addition to `dense|sparse|auto`.
- Per-solve null-rate pruning with `--prune-null-rate-levels` and `--null-rate-floor`, preserving ground, output, and source/sink levels.
- Negative-population controls: `--negative-population-action clip|zero-small|keep|reject` and `--negative-population-tol`.
- Residual diagnostics and optional rejection: `--residual-l2-max`, `--residual-linf-max`, and `--reject-large-residual`.
- Raw population diagnostics before any negative-population handling, including counts and absolute negative-population sum.
- `examples/20_o7_solver_source_fit.py` now defaults to SVD/rank-aware diagnostic solving, keeps raw negative populations by default, and passes null-rate pruning to unit-source solves.
- `examples/13_o7_recombination_cascade_workflow.py` now exposes the same solver-matrix treatment options and records them in the workflow summary.

Changed:
- Rank-deficient matrices are no longer treated as ordinary direct-solve cases by default; the default action is least-squares in the solver CLI and SVD in the O VII diagnostic examples.
- Negative populations are no longer clipped silently: the chosen action and raw negative-population diagnostics are always written to solver summaries.

Notes:
- The default library/CLI behavior remains compatible for general use (`clip` remains the solver default), while the O VII empirical diagnostic examples use `keep` to avoid introducing nonlinear clipping into response-matrix fits.

## v0.2.60 - 2026-04-22

- Corrected `examples/20_o7_solver_source_fit.py` so the empirical solver-response weights are fitted against the **raw full-solver triplet response amplitudes**, with the combined triplet vector normalized only for comparison to the XSTAR R/G target.
- This fixes the v0.2.54--v0.2.59 diagnostic inconsistency where the source-fit script could match XSTAR using per-level normalized response fractions, but the same weights did not reproduce the target when injected simultaneously into `examples/13_o7_recombination_cascade_workflow.py`.
- Added raw-response columns to `o7_source_fit_weights.csv` / `o7_solver_source_fit_weights.csv` so each fitted level shows its raw forbidden, intercombination, and resonance response per unit source.
- The fitted weights remain empirical/diagnostic and amplitude-dependent; continue using `--solver-source-total-rate 1.0` in the cascade workflow when applying weights generated with the default `--source-rate 1.0`.

## v0.2.59 - 2026-04-21

- Captures SciPy `MatrixRankWarning` during sparse statistical-equilibrium solves and falls back to the existing least-squares solver instead of printing repeated warning spam.
- This is especially useful for the O VII solver-response source-fit diagnostic, where some unit-source response matrices are rank-deficient because selected source levels do not independently constrain a unique sparse solution.
- The warning/fallback remains recorded in the solver summary via `solver_warning`; fitted source-response diagnostics should still be judged from the output summary ratios.

## v0.2.58 - 2026-04-20

- Added source-amplitude controls to `examples/13_o7_recombination_cascade_workflow.py`:
  - `--solver-source-scale` multiplies the source/sink CSV passed to the solver.
  - `--solver-source-total-rate` rescales the solver source CSV so the first T/ne block has a requested total source rate.
- This fixes the diagnostic mismatch where solver-response fitted weights from `examples/20_o7_solver_source_fit.py` were derived with unit source rate `1.0 s^-1`, but the cascade workflow applied them at the physical RR source scale (`~1.345e-12 s^-1` at ne=1), causing baseline collisional excitation to dominate.
- `examples/20_o7_solver_source_fit.py` now records `source_rate_s^-1`, `source_rate_note`, and `fit_source_rate_s^-1` in its outputs so the required workflow source amplitude is explicit.
- Recommended fitted-source workflow now uses `--solver-source-total-rate 1.0` when consuming default solver-response weights.

## v0.2.57 - 2026-04-19

Safety fix:
- Hardened NPZ hierarchy index-cache writing so it never uses or replaces the input `atdb.fits` path.
- The cache writer now rejects cache paths that resolve to the FITS file, uses a unique temporary filename in the cache directory, and verifies that the FITS file signature is unchanged before and after cache replacement.
- Added `--index-cache-path` to `examples/20_o7_solver_source_fit.py` so repeated unit-source solver runs can use an explicit cache file away from the XSTAR data file.

Recommended safe usage:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

## v0.2.56 - 2026-04-18

Fixed:
- Made explicit `--source-fit-weights-csv` paths strict, except for the documented legacy cascade-fit path `o7_cascade_source_fit/o7_source_fit_weights.csv`. This prevents a missing solver-response fit file such as `o7_solver_source_fit/o7_source_fit_weights.csv` from silently falling back to the packaged older cascade-fit reference by basename.

Added:
- Recombination summaries now record `source_fit_weights_csv_requested`, `source_fit_weights_csv_resolved`, `source_fit_weight_column`, and `n_source_fit_weights` so fitted-source workflow outputs show exactly which weight file was used.

Notes:
- The uploaded v0.2.55 solver-fit workflow used `solver_source_csv_mode=initial`, but its initial source weights matched the older packaged cascade-fit weights. This happened because the requested solver-response weights CSV was not found relative to the run directory and the basename fallback selected the packaged `o7_source_fit_weights.csv`. v0.2.56 fails fast instead.

## v0.2.55 - 2026-04-17

Fixed:
- Added lightweight `atdb.fits` path validation in the data resolver so empty, truncated, or wrong relative FITS paths fail with a clear message before Astropy raises a low-level `OSError: Empty or corrupt FITS file`.
- `python -m xstar_atomic.data --set-path ...` now rejects invalid `atdb.fits` candidates and suggests setting `XSTAR_ATDB_FITS` or the persistent datapath to the real local XSTAR atomic database.

Notes:
- This version does not change the O VII solver-response source-fit physics. It only improves diagnostics for the path problem seen when rerunning the v0.2.54 workflow with an empty/corrupt `../xstar/data/atdb.fits`.

## v0.2.54 - 2026-04-16

### Added
- Added `examples/20_o7_solver_source_fit.py`, a stricter O VII empirical diagnostic that fits source weights against the full `xstar_atomic.solver` unit-source response matrix rather than the simpler radiative cascade yield matrix.
- The new solver-response fit writes `o7_solver_response_matrix.csv`, `o7_solver_source_fit_weights.csv`, a compatibility alias `o7_source_fit_weights.csv`, and `o7_solver_source_fit_summary.json`.

### Changed
- Documented that the earlier cascade-yield source-fit weights are not expected to reproduce XSTAR R/G when injected into the full statistical-equilibrium solver, because the solver response includes radiative rates, branching, collisional coupling, and normalization effects beyond the cascade-yield matrix.

## v0.2.53 - 2026-04-15

Fixed:
  - examples/13_o7_recombination_cascade_workflow.py now feeds the initial fitted source CSV to the level-population solver for selected-fit-weights and o7-xstar-fit modes by default.
  - Added --solver-source-csv-mode auto|initial|cascade to make this behavior explicit and reproducible.
  - This avoids applying the radiative cascade twice: once in recombination.py and again inside the solver radiative network.

## v0.2.52 - 2026-04-14

Fixed:
- Resolved a path bug in `selected-fit-weights` workflows: missing relative weight CSV paths such as `o7_cascade_source_fit/o7_source_fit_weights.csv` are now resolved against packaged reference locations (`xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`) when the basename exists there.
- Updated the explicit `selected-fit-weights` documentation examples to use the packaged reference file `xstar_test_run/o7_source_fit_weights.csv`.

## v0.2.51 - 2026-04-14

- Added diagnostic source mode `selected-fit-weights`, which reads fitted level-source weights from `--source-fit-weights-csv`.
- Added convenience source mode `o7-xstar-fit`, which uses `xstar_test_run/o7_source_fit_weights.csv` when no explicit weight CSV is provided.
- Added O VII source-fit reference products to `xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`.
- Updated the O VII recombination/cascade workflow example to pass source-fit weight CSV options through to `xstar_atomic.recombination`.
- These modes are empirical/diagnostic only; they are not a replacement for true level-resolved recombination rates.

## v0.2.50 - 2026-04-13

- Added `examples/19_o7_cascade_source_fit.py`, a Stage-6 diagnostic for level-resolved O VII cascade-source construction from radiative yield matrices.
- The example builds `Y(source_level -> forbidden, intercombination, resonance)`, writes `o7_cascade_yield_matrix.csv`, fits nonnegative source weights against the saved XSTAR O VII `R=f/i` and `G=(f+i)/r` ratios, and writes `o7_source_fit_weights.csv` plus `o7_source_fit_summary.json`.
- Added helper tests for the nonnegative simplex projection and source-fit optimizer used by the diagnostic.

## v0.2.49 - 2026-04-12

- Added `examples/18_o7_type68_2d_cascade_tuning_scan.py`, a broader Stage-6 O VII type-68-aware tuning scan.
- The new scan varies both forbidden-to-intercombination redistribution and resonance-target suppression using maps of the form `2:(1-d),3:(1+d/3),4:(1+d/3),5:(1+d/3),7:r`.
- The scan writes compact, ranked, all-density CSV tables plus a JSON summary, so the best compromise against the XSTAR O VII `R=f/i` and `G=(f+i)/r` reference can be identified.
- Kept the equal-target `selected-cascade-yield` map as the documented Stage-6 baseline.

## v0.2.48 - 2026-04-11

### Added
- Added type-68-aware O VII cascade tuning presets that preserve equal triplet target weights while progressively downweighting the resonance target level 7: `o7-triplet-type68-r095`, `r090`, `r085`, `r080`, `r075`, `r070`, `r060`, and `r050`.
- Added `examples/17_o7_type68_cascade_tuning_scan.py` to run the equal baseline plus the type-68-aware resonance-weight grid, writing compact and all-density CSV/JSON summaries.

### Changed
- Documentation now distinguishes the pre-type-68 f2i/fdown scans from the type-68-aware resonance-weight scan needed after He-like collision types 67/68/69 are enabled.

## v0.2.47 - 2026-04-10

- Added He-like collisional-excitation decoders/evaluators for XSTAR data types 67, 68, and 69.
  - Type 67 follows `calt67`: `gamma = a + b log10(T) + c log10(T)^2`.
  - Type 68 follows `calt68`: `gamma = a + b log10(T/Z^3) + c log10(T/Z^3)^2`.
  - Type 69 follows `calt69`: Kato--Nakazaki He-like collision-strength fit.
- Extended `COLLISION_DATA_TYPES` to include 67, 68, and 69.
- Updated the O VII metastable/intercombination coupling diagnostic to write `o7_metastable_coupling_collision_inventory.csv`, which inventories all decoded/evaluated collision records involving the selected source/target levels.
- Added unit tests for the type-67/68/69 helper evaluators.

## v0.2.46 - 2026-04-09

Stage-6 diagnostic update.

Added:

- `examples/16_o7_metastable_coupling_diagnostics.py`, a focused O VII diagnostic for level 2 -> levels 3, 4, and 5.
- The diagnostic compares collisional transfer rates `C_2_to_j = n_e q_2j` with decoded radiative rates as a function of electron density.
- Outputs `o7_metastable_coupling_rates.csv` and `o7_metastable_coupling_summary.json`.

Notes:

- The equal-target `selected-cascade-yield` map remains the documented Stage-6 baseline.
- The new diagnostic is intended to determine whether the remaining high O VII `R=f/i` ratio is caused by under-coupled metastable/intercombination transfer or by source/cascade feeding.

## v0.2.45 - 2026-04-08

Stage-6 O VII cascade tuning update.

### Added
- Added forbidden-to-intercombination shift presets that preserve the resonance target and approximately preserve the total triplet-target weight:
  - `o7-triplet-f2i010-rkeep` -> `2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0`
  - `o7-triplet-f2i015-rkeep` -> `2:0.85,3:1.05,4:1.05,5:1.05,7:1.0`
  - `o7-triplet-f2i025-rkeep` -> `2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`
  - `o7-triplet-f2i050-rkeep` -> `2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0`

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the documented Stage-6 baseline.
- Updated `examples/15_o7_cascade_tuning_scan.py` so the default tuning scan now includes the new forbidden-to-intercombination shift presets before the older simple `fdown` comparison cases.
- Updated `o7-triplet-xstar-tuned` as a backward-compatible alias to the preferred `f2i025` shift experiment.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the new Stage-6 tuning strategy: preserve `G=(f+i)/r` by keeping the total triplet/resonance balance close to the equal-target case while shifting source weight from forbidden to intercombination levels.

## v0.2.44 - 2026-04-07

### Added
- Added Stage-6 O VII cascade tuning presets that downweight the forbidden target while preserving the resonance target: `o7-triplet-fdown090-rkeep`, `o7-triplet-fdown085-rkeep`, and `o7-triplet-fdown075-rkeep`.
- Added `examples/15_o7_cascade_tuning_scan.py`, which runs the equal-target baseline plus forbidden-downweighted presets and writes CSV/JSON summaries of `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII reference.

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the recommended Stage-6 baseline.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the Stage-6 tuning scan workflow.

## v0.2.43 - 2026-04-06

Completed Stage-5 heavy-ion XSTAR wavelength validation.

- Added validated Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI XSTAR `xout_lines1.fits` artifacts under `xstar_test_run/`.
- Added converted selected-line CSV products for Mg/Si/Fe validation under `xstar_test_run/`.
- Added Mg/Si/Fe wavelength comparison CSV/JSON files under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added tests checking the Mg/Si/Fe validation artifacts and wavelength matches.
- Updated README and Sphinx/Markdown comparison docs to mark Mg/Si/Fe Stage-5 validation as completed rather than pending.

## v0.2.42 - 2026-04-06

Stage-5 heavy-ion validation planning update.

- Added reproducible direct-XSTAR run recipes to `xstar_test_run/README.md` for Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI.
- Added suggested first-pass wavelength windows and `xstar_atomic.xstar_outputs` FITS-to-CSV commands for Mg/Si/Fe validation products.
- Added wavelength-comparison command templates for the corresponding `examples/08_compare_xstar_outputs.py` runs.
- Updated README and XSTAR comparison documentation to mark Mg/Si/Fe as the pending Stage-5 completion targets after the validated O/Ne workflow.

## v0.2.41 - 2026-04-05

- Fixed Sphinx ``user_guide.rst`` heading underline length for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.

## v0.2.40 - 2026-04-05

Fixed:

- Corrected the Sphinx user-guide heading underline for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.
- Kept the v0.2.39 documentation updates for ``download_data()``, data-path resolution, NPZ cache performance, and Stage-6 cascade workflow notes.

## v0.2.39 - 2026-04-05

Documentation and Stage-6 result update.

- Refreshed Markdown, LaTeX, and Sphinx documentation for the current data-management API: `download_data()`, `resolve_atdb_path()`, `find_atdb_file()`, `get_data_path()`, and `set_data_path()`.
- Documented path-resolution precedence: explicit path, `XSTAR_ATDB_FITS`, persistent `datapath`, project/package `data/atdb.fits`, then interactive download/configuration.
- Documented the single-line ASCII download progress bar and the source-tree default `data/` and `datapath` locations.
- Updated solver/cache documentation to recommend the array-backed NPZ cache path validated in v0.2.27/v0.2.28.
- Added Stage-6 result guidance: equal-target cascade-yield remains the recommended baseline; the `o7-triplet-fdown-rkeep` preset decreases `R=f/i` but also lowers `G=(f+i)/r`, so it is experimental.
- Fixed LaTeX listing styles using `ctpython` and `ctterminal`; Python listings now have syntax highlighting and terminal listings use a separate style.
- Normalized code listings so ion names appear as `O VIII`, not with visible-space markers.

## v0.2.38 - 2026-04-04

- Fixed `examples/13_o7_recombination_cascade_workflow.py` so the recommended equal O VII target map is only passed when no non-`none` `--cascade-target-preset` is selected.
- This prevents the default `--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` from overriding experimental presets such as `o7-triplet-fdown-rkeep`.
- The recommended Stage-6 baseline remains the equal-target map. The `o7-triplet-fdown-rkeep` preset remains an experimental forbidden-downweighted, resonance-preserved map.

## v0.2.37 - 2026-04-03

Stage-6 O VII cascade-source tuning update.

Changed:
- Keep the documented/recommended ``selected-cascade-yield`` target map as equal triplet targets: ``2:1.0,3:1.0,4:1.0,5:1.0,7:1.0``.
- Add a new forbidden-downweighted, resonance-preserved experimental preset: ``--cascade-target-preset o7-triplet-fdown-rkeep`` -> ``2:0.5,3:1.0,4:1.0,5:1.0,7:1.0``.
- Update ``o7-triplet-xstar-tuned`` as a backward-compatible alias to the new resonance-preserved map, replacing the earlier resonance-downweighted map.
- Update the Stage-6 workflow example and docs to avoid recommending the resonance-downweighted preset, which overestimated G=(f+i)/r.

## v0.2.36 - 2026-04-02

Fixed:
- Data-path helper round-trip test now removes ``XSTAR_ATDB_FITS`` during the isolated datapath test. This preserves the intended runtime precedence: explicit path, ``XSTAR_ATDB_FITS``, saved ``datapath``, project/package ``data/``, then interactive download/configuration.

Added:
- ``--cascade-target-preset o7-triplet-xstar-tuned`` for Stage-6 O VII triplet cascade-source experiments.
- The preset expands to ``2:0.6,3:1.0,4:1.0,5:1.0,7:0.4``.
- Manual ``--cascade-target-levels`` remains available and overrides the preset.

## v0.2.35 - 2026-04-01

Stage 6 recombination/cascade improvements:
- Added `selected-cascade-yield` recombination source allocation mode.
- Added `--cascade-target-levels` and `--cascade-weight-floor` to `xstar_atomic.recombination`.
- Updated the O VII recombination/cascade workflow example to use cascade-yield source weighting by default.
- Added unit coverage for cascade-yield source allocation helpers.

## v0.2.34 - 2026-03-31

- Added validated Ne IX / Ne X Stage-5 XSTAR comparison artifacts.
- Added `xstar_test_run/ne_xi25/xout_lines1.fits` and `xstar_test_run/ne_xi35/xout_lines1.fits`.
- Added converted CSV line lists for Ne IX triplet/near-triplet and Ne X Ly-alpha.
- Added saved comparison CSV/JSON outputs to `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Updated XSTAR comparison documentation from planned neon runs to completed validation examples.

## v0.2.33 - 2026-03-30

Documentation/examples:
- Added dedicated Stage-5 Ne IX and Ne X direct-XSTAR validation run commands to `xstar_test_run/README.md`.
- Added FITS-to-CSV and `examples/08_compare_xstar_outputs.py` commands for Ne IX He-like triplet/near-triplet and Ne X Ly-alpha wavelength comparisons.
- Updated XSTAR comparison documentation and Sphinx comparison page to list the planned Ne IX/Ne X validation products.

## v0.2.32 - 2026-03-29

Fixed:
  - Replaced multi-line download progress messages with a single in-place ASCII progress bar.
  - Download progress now displays as: `xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)`.

## v0.2.31 - 2026-03-28

Fixed:
- Store the source-tree ``datapath`` file at the project root (for example ``xstar_atomic/datapath``) rather than in ``src/xstar_atomic/``.
- Removed the packaged ``src/xstar_atomic/datapath`` data file from package-data/MANIFEST entries.
- Kept the project-level ``data/`` directory as the default ``atdb.fits`` download destination when running from ``PYTHONPATH=src``.

## v0.2.30 - 2026-03-27

Fixed:
- Changed the default interactive ``download_data()`` destination for source-tree use from ``src/xstar_atomic/data`` to the project-level ``data`` directory.
- Changed the source-tree ``datapath`` file location from ``src/xstar_atomic/datapath`` to the project-level ``datapath`` file, while retaining installed-package fallback behavior.

## v0.2.28 - 2026-03-25

Documentation/examples:
- Documented the validated array-backed NPZ cache performance from v0.2.27: O VIII sparse solver profile dropped from about 5.31 s uncached to about 0.53 s on an NPZ array-backed cache hit.
- Made the array-backed NPZ cache the recommended default for repeated solver, export, high-level API, and profiler workflows.
- Updated README, Markdown user guide, LaTeX user guide, and Sphinx user/examples pages with `--index-cache --index-cache-format npz` examples.
- Updated `examples/12_profile_solver_steps.py` documentation to use the recommended NPZ cache path.

## v0.2.27 - 2026-03-24

Fixed:
- Restored the public array-backed `ATDB.select_records(z=..., ion_stage=..., data_type=..., rate_type=...)` API by renaming the legacy materialized-list filter helper to `filter_records`.
- Fixed `examples/12_profile_solver_steps.py --index-cache --index-cache-format npz`, which failed in v0.2.26 because the legacy helper shadowed the new fast-selection method.

## v0.2.26 - 2026-03-23

Added:
- Added `ATDBIndexArrays`, an array-backed hierarchy index for fast targeted selection.
- Added `ATDB.build_index_arrays(...)` and `ATDB.select_records(...)`.
- NPZ cache hits can now filter numeric arrays and convert only selected rows to `IndexedRecord` objects.
- Updated solver, profiler, and high-level API paths to use array-backed selection for NPZ index caches.
- Added tests for array-backed selection/reconstruction.

Changed:
- `--index-cache-format npz` now avoids reconstructing all 1.2 million records in targeted solver/profiler/API paths.

## v0.2.25 - 2026-03-22

Fixed:
- Reworked the NPZ index cache into a slimmer numeric v2 layout.
- Avoided storing large repeated Unicode arrays for each ATDB record in the NPZ cache.
- Old v0.2.24 NPZ caches are now treated as stale and rebuilt automatically.

Changed:
- The compact cache still returns normal IndexedRecord objects for decoder compatibility, but reconstructs repeated labels from numeric fields and the small element/ion tables.

## v0.2.24 - 2026-03-21

Added:
- Added compact NumPy/NPZ hierarchy index cache support for `ATDB.build_index()`.
- `--index-cache` now defaults to the NPZ cache path `atdb.fits.xstar_atomic_index.npz`.
- Added `--index-cache-format npz|pickle` to hierarchy, solver, export, and solver-step profiler CLIs.
- Preserved legacy pickle cache support with `--index-cache-format pickle`.

Changed:
- `XSTARAtomic(..., index_cache=True)` now uses the NPZ cache by default.
- Cache status strings now distinguish `npz_hit`, `npz_written`, `pickle_hit`, and related states.

## v0.2.23 - 2026-03-20

Added:
- Optional on-disk ATDB hierarchy index caching via ``ATDB.build_index(use_cache=True)``.
- ``--index-cache`` and ``--rebuild-index-cache`` options for the hierarchy, solver, export, and solver-step profiling workflows.
- Cache metadata validation against the source ``atdb.fits`` file size, modification time, array lengths, and cache format version.
- Real-ATDB cache round-trip test for cache creation and cache hits.

Changed:
- Solver/export/profile summaries now report ``index_cache_status`` and ``index_cache_path`` when caching is used.

## v0.2.22 - 2026-03-19

### Fixed

- Fixed `examples/12_profile_solver_steps.py` by adding the missing
  `auto_recombination_cascade=False` default to the solver argument namespace used
  by the profiling workflow.

### Documentation

- Documented that an optional C++ backend can be implemented as a shared-object
  library while preserving the Python/SciPy reference backend.
- Added notes on the Stage-6 O VII recombination/cascade workflow: total O VIII
  -> O VII recombination is redistributed over selected O VII levels, radiative
  branching cascade sources are written to CSV, the sparse solver reads those
  sources, and prototype R=f/i and G=(f+i)/r diagnostics are compared with XSTAR
  triplet output ratios.

## v0.2.21 - 2026-03-18

### Added
- Added `examples/12_profile_solver_steps.py` to profile individual solver stages: ATDB open/read, index building, level/line/collision extraction, collision evaluation, matrix assembly, solve, and output writing.
- Added `examples/13_o7_recombination_cascade_workflow.py`, a prototype Stage-6 O VII workflow that builds recombination source CSVs, performs approximate radiative cascade redistribution, feeds the cascade source into the sparse solver, and compares O VII triplet diagnostics with an optional XSTAR line-output CSV.

### Notes
- Documented that an optional C++ backend can be implemented as a shared-object (`.so`) library loaded from Python, with the pure-Python/SciPy implementation retained as the reference/fallback path.
- The O VII cascade workflow remains a prototype: current oxygen RR/DR records are total recombination rates, not true level-resolved recombination-cascade records.

## v0.2.20 - 2026-03-17

### Added
- Added `examples/11_solver_timing.py` to benchmark end-to-end level-population solver execution times.
- The timing example compares O VIII dense and sparse solver modes and can optionally include the heavier O VII triplet sparse stress test.
- Timing CSV rows include elapsed wall time, solver used, sparse status, matrix size, nonzero count, density, condition number, and residual diagnostics.

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user guides with solver timing commands and notes on when a C++ backend could improve performance.

## v0.2.19 - 2026-03-16

### Solver
- Improved Stage-3 level-population solver diagnostics for sparse and dense solves, including matrix nonzero counts, matrix density, singular-value/rank diagnostics, diagonal and row-sum ranges, residual norms, and explicit sparse-use flags.
- Added optional connectivity pruning with `--prune-unconnected-levels`, preserving ground, output, and explicit source/sink levels.
- Added source/sink vector summaries to solver JSON output, including nonzero level terms and source/sink totals for recombination/cascade source-file tests.
- Added O VII triplet diagnostic support with `--triplet-diagnostics` and `--out-triplet-csv`, reporting prototype `R=f/i` and `G=(f+i)/r` ratios when O VII triplet lines are selected.

### Documentation and examples
- Updated the user guide and examples for sparse solver runs, connectivity pruning, source/sink diagnostics, and O VII triplet diagnostics.
- Added `examples/10_o7_triplet_sparse_solver.py` as the Stage-3 solver stress-test example.

### Tests
- Added unit tests for solver diagnostics, pruning, source/sink summaries, and O VII triplet R/G helper calculations.

## v0.2.18 - 2026-03-15

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user-guide material for the validated Stage-4 band-emissivity export workflow.
- Documented `--bands-kev`, `*_band_emissivity.csv`, and HDF5 `/band_emissivity` products.
- Recorded the v0.2.17 Stage-4 real-ATDB validation result: 34 passing tests, 12 band-emissivity rows per ion for four bands and three temperatures, nonblank `ion`, and `methods_used="none"` for zero-line bands.

### Examples
- Added `examples/09_export_band_emissivity.py` for CSV/HDF5 export of line-based X-ray band emissivity products.

## v0.2.17 - 2026-03-14

### Fixed
- Filled the `ion` field for all band-emissivity rows, including zero-line bands.
- Set `methods_used="none"` for zero-line band-emissivity rows.

### Tests
- Added unit and real-ATDB export tests that check band-emissivity rows do not contain blank ion names or blank method fields.

## v0.2.15 - 2026-03-13

### Added
- Added HDF5 export support to `xstar_atomic.export` via `--formats hdf5` or `--formats csv,hdf5`.
- Added a general CLI alias `xstar-atomic-export` while keeping `xstar-atomic-export-superwind` for backward compatibility.
- Added optional SciPy sparse-matrix support to the level-population solver via `--linear-solver sparse` or `--linear-solver auto`.
- Added tests for HDF5 export helpers and sparse-solver fallback/consistency.

### Changed
- Generalized export documentation and manifests for plasma post-processing workflows beyond superwinds, including AGN outflows.
- The export manifest is now written as `atomic_export_manifest.json` and also as the legacy `superwind_export_manifest.json`.


## v0.2.14 - 2026-03-12

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.13 - 2026-03-11

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.12 - 2026-03-10

### Added
- Added saved XSTAR-vs-`xstar-atomic` comparison outputs for O VIII Ly-alpha and the O VII triplet under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added `docs/xstar_comparison_examples.md` documenting the XSTAR-output comparison workflow and validation results.
- Added Sphinx page `xstar_comparisons.rst` and linked it from the Sphinx index.

### Documentation
- Documented that O VIII Ly-alpha wavelength agreement is at the ~1e-5 Angstrom level.
- Documented that O VII triplet wavelength agreement is at the ~1e-7 to 8e-7 Angstrom level.
- Clarified that XSTAR model `emit_*` columns are not directly equivalent to local `xstar-atomic` emissivity coefficients without model-dependent normalization.

## v0.2.11 - 2026-03-09

Added:
- Extended ``examples/08_compare_xstar_outputs.py`` with explicit ``--mode`` choices: ``wavelength``, ``emissivity``, and ``both``.
- Added ``--out-csv`` and ``--out-json`` outputs for XSTAR-vs-xstar-atomic comparison tables.
- Added clearer warnings/notes that XSTAR model ``emit_*`` columns are not directly equivalent to local atomic emissivity coefficients.

## v0.2.10 - 2026-03-08

Fixed:
- Added `--wavelength-column` to `examples/08_compare_xstar_outputs.py`.
- The comparison example now auto-detects `wavelength_A` or `wavelength` columns in XSTAR-output CSV files.

## v0.2.9 - 2026-03-07

### Added
- Added `xstar_atomic.xstar_outputs` for reading XSTAR `xout_lines*.fits` files.
- Added CLI entry point `xstar-atomic-xstar-outputs` and module execution with `python -m xstar_atomic.xstar_outputs`.
- Supports CSV export, JSON summaries, and filtering by ion, wavelength, and emission columns.

## v0.2.8 - 2026-03-06

### Fixed
- Added the missing solver CLI argument `--electron-density-for-lmixing`.
- Fixed the real-ATDB solver status test failure caused by the solver referencing `args.electron_density_for_lmixing` without registering the argparse option.

## v0.2.7 - 2026-03-05

### Added
- Added a scientific validation status table to the Markdown and LaTeX user guides.
- Added `xstar_atomic.export` with CSV/JSON export helpers for superwind/Athena++ post-processing.
- Added CLI entry point `xstar-atomic-export-superwind`.
- Added `examples/08_compare_xstar_outputs.py` for comparing selected xstar-atomic outputs against user-supplied XSTAR CSV outputs.
- Added lightweight import tests for the export module.

### Improved
- Updated solver diagnostics to report that the XSTAR-derived type-63 same-n l-mixing collision decoder is enabled.
- Updated docs to reflect the implemented type-63 same-n l-mixing path and the current validation status of data types 51 and 98.

## v0.2.6 - 2026-03-04

### Added
- Added `tests/data/collision_type51_98_targets.csv`, generated from the collision validation inventory.
- Added API-level real-ATDB pytest coverage for representative collision `data_type=51` and `data_type=98` targets through `XSTARAtomic.collisions(...)`.
- Added a type-98 ion-alias API regression test using the `ne_ix` alias.

### Validation
- The type-51 API test validates a representative Burgess--Tully 5-point target against the inventory reference rate.
- The type-98 API test validates the Ne IX CHIANTI-style Burgess--Tully target against the inventory reference rate.

## v0.2.5 - 2026-03-03

### Fixed
- Restored the lightweight top-level `parse_ion` export so `from xstar_atomic import parse_ion` works again after the lazy-import cleanup.
- Kept the minimal top-level API limited to `ATDB`, `XSTARAtomic`, and `parse_ion`; decoder functions remain importable from their submodules.


## v0.2.4 - 2026-03-02

### Fixed
- Cleaned reStructuredText in module docstrings for the Sphinx API build.
- Fixed docutils warnings/errors in `photoionization`, `collisions`, and `recombination` module documentation.

## v0.2.3 - 2026-03-01

### Added
- Added `xstar_atomic.validation` with collision-decoder inventory and validation helpers.
- Added CLI entry point `xstar-atomic-validate-collisions`.
- Added `examples/07_collision_decoder_validation.py` for type 51/98 target discovery and type-63 same-`n` diagnostics.
- Added real-ATDB pytest checks for:
  - O VIII type-63 same-`n` l-mixing regression diagnostics.
  - Type 51 and type 98 inventory plus representative positive-rate targets when present in the local `atdb.fits`.

### Notes
- The type-63 same-`n` diagnostic checks the Python port of the XSTAR `amcrs/velimp` branch, but independent validation against XSTAR model outputs is still recommended for production science.

## v0.2.2 - 2026-02-28

### Fixed
- Corrected LaTeX backslash corruption in `docs/user_guide.tex` for the `center` and `tabular` environments.

## v0.2.1 - 2026-02-27

### Changed
- Simplified ``xstar_atomic.__init__`` to expose only ``ATDB``, ``XSTARAtomic``, and ``__version__``.
- Moved heavy decoder imports in ``api.py`` to lazy method-level imports.
- Preserved submodule-level imports such as ``xstar_atomic.collisions`` and ``xstar_atomic.recombination``.

### Fixed
- Avoids ``runpy`` warnings when executing CLI modules with ``python -m xstar_atomic.<module>`` after importing the package.

## v0.2.0 - 2026-02-26

### Added
- Implemented the type-63 same-`n` l-changing collision branch using the XSTAR `amcrs`/`velimp` ecm=0 logic.
- Added `electron_density_for_lmixing` to the high-level collision/emissivity APIs for the density-dependent impact-parameter cutoff used by same-`n` l-mixing.
- Added `--electron-density` to `xstar-atomic-collisions` and `--electron-density-for-lmixing` to emissivity/solver CLIs.
- Added diagnostic columns for same-`n` type-63 l-mixing: shell radiative sum, `cn`, selected `l` branch, and density.

### Improved
- Promoted collision data type 51 and 98 Burgess--Tully evaluators as supported collision-rate paths alongside type 56 and type 63.
- Updated package tests to check that real-ATDB type-63 same-`n` l-mixing returns finite evaluated rates when `XSTAR_ATDB_FITS` is supplied.

## v0.1.8 - 2026-02-25

### Documentation
- Added `\usepackage{amsmath,amssymb}` to the LaTeX user guide preamble for math support.


All notable changes to `xstar-atomic` are documented here.

## v0.1.7 - 2026-02-24

Fixed:
- Restored backward-compatible high-level API keys used by the examples:
  - `collisions()["matches"]` and `collisions()["evaluated_rates"]`.
  - `emissivity()["rows"]`.
  - `recombination()["summary"]`.
- Updated example/API behavior so the examples work with the current return dictionaries.

## v0.1.6 - 2026-02-23

### Added
- Added full user guide in Markdown: `docs/user_guide.md`.
- Added full user guide in LaTeX: `docs/user_guide.tex`.
- Added Sphinx documentation scaffold under `docs/sphinx/` using `sphinx.ext.autodoc`, `sphinx.ext.napoleon`, and the Read the Docs theme.
- Added Sphinx pages for user guide, examples, API reference, development notes, and changelog.
- Added `examples/06_high_level_api_quickstart.py`.
- Added optional `docs` dependency group with `sphinx` and `sphinx-rtd-theme`.

### Notes
- Sphinx API pages are generated from Python docstrings. Future public functions/classes should include clear docstrings.

## v0.1.5 - 2026-02-22

### Added
- Added flexible ion-name parsing in the high-level API. Accepted forms now include `O VIII`, `o viii`, `o_viii`, `O_VIII`, `O-VIII`, `OVIII`, and `o8`.
- Added unit tests for ion-name aliases.

## v0.1.4 - 2026-02-21

### Added
- Added real pytest smoke tests for the direct `atdb.fits` workflow.
- Added API smoke tests for:
  - low-level `ATDB.build_index()` counts,
  - O VIII Ly-alpha line extraction,
  - O VIII Ly-alpha collision-rate evaluation,
  - O VIII Ly-alpha emissivity table generation,
  - oxygen recombination inventory.
- Added CLI smoke tests using `python -m xstar_atomic.*` modules.
- Added `examples/` scripts:
  - `01_o8_lya_lines.py`,
  - `02_o8_lya_collisions.py`,
  - `03_o8_lya_emissivity.py`,
  - `04_oxygen_recombination_inventory.py`,
  - `05_low_level_atdb_index.py`.
- Added this versioned `CHANGELOG.md`.

### Notes
- Tests that require the real XSTAR database are skipped unless `XSTAR_ATDB_FITS` points to a readable `atdb.fits` file.
- Example test command:

  ```bash
  XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
  ```

## v0.1.3 - 2026-02-20

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `collision_data_type` default expected by the emissivity filters.

## v0.1.2 - 2026-02-19

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `include_superlevel_radiative` default expected by the emissivity filters.

## v0.1.1 - 2026-02-18

### Added
- Added the high-level `XSTARAtomic` API wrapper around the low-level `ATDB` reader.
- Added convenience methods for lines, collisions, recombination, and emissivity workflows.
- Kept `ATDB` as the low-level direct packed-FITS API.

## v0.1.0 - 2026-02-17

### Added
- Initial package refactor from validated standalone scripts.
- Added package namespace `xstar_atomic` and project name `xstar-atomic`.
- Added command-line modules for:
  - inspecting `atdb.fits`,
  - hierarchy reconstruction,
  - lines,
  - photoionization,
  - collisions,
  - recombination,
  - emissivity,
  - prototype level-population solving.
