Latest package note: v0.3.114 continues the source-code-first XSTAR alignment for Mg XI/Ca XIX and C V by changing type-63 n-changing collision evaluation to use the literal XSTAR `ucalc.f90` ATDB record-order endpoint convention. The previous Python path sorted type-63 endpoints by energy and then used an explicit branch selector; v0.3.114 now evaluates the `aa1` selector and `ans1/ans2` swap in the original idat order, maps the resulting forward/reverse rates back to lower->upper and upper->lower matrix coefficients, and records the legacy energy-order rates for audit comparison. No empirical scale fitting is introduced; `--resonance-collisional-feed-scale` remains diagnostic-only and defaults to 1.

# xstar-atomic

Latest package note: v0.3.113 continues the source-code-first Mg XI/Ca XIX validation. It aligns He-like type-67/type-68 collision-strength evaluation with XSTAR `ucalc.f90` by applying the `temp=max(T,2.8777e6/wavelength_A)` floor before `calt67/calt68`, records that effective temperature in collision audits, and adds `examples/49_mg_ca_triplet_source_path_audit.py` to map Mg/Ca triplet-feeding rows to XSTAR source-code branches without fitting scale factors.

Latest package note: v0.3.111 starts the Mg XI and Ca XIX XSTAR-target validation workflow. It adds `examples/47_prepare_mg_ca_xstar_triplet_targets.py` to generate Mg XI/Ca XIX XSTAR run scripts, triplet-line conversion scripts, target-plan CSVs, and solver/compare commands across a log-xi grid. `examples/43_compare_xstar_detail_populations.py` now automatically derives target f/i/r from a supplied `--xstar-triplet-lines-csv`, so Mg/Ca comparisons no longer accidentally use the historical built-in C V target. No default solver physics changed.

Latest package note: v0.3.110 fixes the internal C V resonance-collisional-feed scale-scan context. The scan now uses the same full-global topology, ion-fraction closure, temperature, electron density, and calc-ion-rates audit context as the primary `full_global_xstar_tau0_calc_emis_ion` solve, so `xstar_like_element_solver_resonance_collisional_feed_scale_scan.csv` is aligned with the printed comparison result. The resonance-feed scale remains diagnostic and default physics is unchanged.

Latest package note: v0.3.108 adds a real direct collisional resonance-feed audit and matrix-scale diagnostic for the C V `1s2p 1P1` resonance upper level. `examples/42_xstar_like_element_solver_demo.py` now supports `--resonance-collisional-feed-scale` and writes `xstar_like_element_solver_resonance_collisional_feed_audit.csv` plus a scale-scan CSV.

Previous package note: v0.3.102 makes the He-like triplet-balance diagnostic robust to missing optional audit CSVs in older or partially copied solver-output directories, while preserving all v0.3.101 C V/O VII physics and validation results.


### v0.3.101 C V triplet-balance diagnostics

v0.3.101 adds two validation helpers for the remaining C V intercombination/resonance residual. `examples/44_diagnose_helike_triplet_balance.py` compares C V and O VII solver-output audits, including type-50 3P_J -> 3S1 drains, density-scaled 3S/3P collisional coupling, type-71 cascade feed, and type-99 superlevel-source branch proxies. `examples/45_prepare_c5_xstar_triplet_reference.py` prepares the C V `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv` reference path or converts an existing C V `xout_lines1.fits` file.


### v0.3.100 reference-depth scale warning

v0.3.100 keeps the v0.3.99 O VII reference-depth postprocess unchanged, but prevents accidental silent use of the default depth scale.  When `examples/43_compare_xstar_detail_populations.py` is run with:

```bash
--comparison-case full_global_xstar_reference_depth_emit_outward_calc_emis_ion \
--xstar-triplet-lines-csv xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv
```

and `--xstar-reference-depth-scale` is omitted, the script still uses the backward-compatible default scale `1.0` but prints:

```text
Warning: Using default depth scale 1.0; O VII ne=1e8 validation used 0.37.
```

For the validated O VII `ne=1e8` comparison, continue to pass:

```bash
--xstar-reference-depth-scale 0.37
```

### v0.3.99 O VII reference-depth line escape validation

v0.3.99 adds an optional XSTAR reference-line CSV postprocessing path for He-like triplet `calc_emis_ion` validation.  The solver can now match triplet lines to a converted XSTAR `xout_lines1` CSV, read `depth_inward`/`depth_outward`, evaluate the XSTAR `pescl` escape channels, and write the validation-only comparison case `full_global_xstar_reference_depth_emit_outward_calc_emis_ion`.  This is intended for the O VII case where the population solution had a good `R=f/i` ratio but too much resonance emission, giving `G=6.01` instead of the XSTAR `emit_outward` target `G=10.58`.

For the packaged O VII `ne=1e8` reference, rerun the comparison without rerunning ATDB as:

```bash
PYTHONPATH=src python examples/43_compare_xstar_detail_populations.py \
  --solver-out-dir o7_xstar_like_element_solver_v0398_superlevels \
  --element O --he-like-stage 7 \
  --comparison-case full_global_xstar_reference_depth_emit_outward_calc_emis_ion \
  --xstar-triplet-lines-csv xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv \
  --xstar-value-column emit_outward \
  --xstar-reference-depth-scale 0.37 \
  --target-f nan --target-i nan --target-r nan \
  --print-summary
```

The uploaded v0.3.98 O VII output gives `f/i/r = 0.755947 / 0.157623 / 0.0864298`, `R = 4.79592`, `G = 10.5701`, and `L2 = 9.92e-4` relative to the XSTAR `ne=1e8` target.


### v0.3.98 type-99 target-stage destination assembly fix

For XSTAR data-type 99 records, the destination level belongs to the target ion even when the audit/source row carries `record_ion_stage` from the adjacent parent ion.  v0.3.98 therefore uses `target_ion_stage` for the destination/superlevel global-index lookup in the physical `calt99/phint53hunt` matrix assembly path.  This completes the v0.3.97 `idat(nidt-3)=0` continuum-alias fix by allowing the evaluated source-code rates to enter `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv` as `assembled_global_type99_calt99_phint53hunt` rows.


## v0.3.97 type-99 continuum-parent mapping and physical-only fallback

v0.3.97 fixes the remaining XSTAR `ucalc.f90` type-99 parent-side mapping case: when `idat(nidt-3) <= 0`, XSTAR computes `idest2 = nlev + idat(nidt-3) - 1` and then clips it with `idest2 = max(idest2, nlev)`.  Therefore the parent side is the target-ion continuum slot, not an invalid parent level zero.

In the Python global matrix this maps to the explicit target-ion continuum row.  When `--full-global-topology xstar-continuum-alias` or `xstar-continuum-alias-superlevels` is used, that row is then aliased to the adjacent parent-ion ground row, following the XSTAR `calc_hmc_element` `ipmat = ipmat + nlev - 1` convention.

The default type-99 source fallback is now source-code-only:

```bash
--type99-source-fallback-mode physical-only
```

If `calt99/phint53hunt` cannot produce physical rates, old `source_vector_gain_proxy` scaffold rows are skipped instead of assembled.  The legacy diagnostic proxy can still be restored explicitly with:

```bash
--type99-source-fallback-mode legacy-proxy
```

No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.94 type-99 superlevel bound-free calt99/phint53hunt rates

v0.3.94 ports the XSTAR `calt99.f90` data-type 99 superlevel bound-free evaluator and wires the source-code type-99 `ucalc.f90` closure into the full global/Lucy matrix.  The implementation evaluates the log-density/log-temperature recombination coefficient, rescales the tabulated superlevel cross section through the Milne integral, evaluates the diagnostic `phint53hunt` forward/recombination kernels, and assembles the source-code pair `ans1`/`ans2` as matrix terms:

```text
ans1 = scaled phint53hunt photoionization rate       # destination -> parent continuum
ans2 = rec * xnx                                    # parent continuum -> destination
```

Type 71 (`calt71.f90`) and type 77 (`calt77.f90`) remain active.  The recommended C V comparison row remains:

```text
full_global_xstar_tau0_calc_emis_ion
```

The new type-99 rates are reported in `xstar_like_element_solver_superlevel_cascade_audit.csv` and assembled terms appear in `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv` with `assembly_status=assembled_global_type99_calt99_phint53hunt`.


## v0.3.93 type-77 superlevel collisional coupling

v0.3.93 ports the XSTAR `calt77.f90` data-type 77 evaluator and assembles the paired collisional rates into the full global/Lucy matrix.  In XSTAR `ucalc.f90`, type 77 uses `ans1=clu` for spectroscopic-to-superlevel coupling and `ans2=cul` for superlevel-to-spectroscopic coupling.  This release preserves the v0.3.92 `calt71` type-71 radiative cascade path and adds the missing collisional back-coupling needed for O VII superlevel population validation.


Current development baseline: v0.3.92 ports the XSTAR `calt71.f90` type-71 superlevel-to-spectroscopic cascade evaluator and replaces the old placeholder `type71_A_or_rate_preview_s^-1` / rate=2.0 scaffold in global type-71 cascade assembly.  Type-71 rows now report source-code `type71_calt71_aij_s^-1` rates, grid interpolation status, wavelength, and legacy preview values for comparison.  The C V recommended comparison case remains `full_global_xstar_tau0_calc_emis_ion` as the regression benchmark, while O VII validation should be rerun to test whether the real calt71 cascade rates improve the resonance source balance.  No intentional changes are made to type-50 matrix rates, inverse recombination, line optical-depth construction, `calc_emis_ion`, or `calc_ion_rates/istruc` behavior.

### Recommended C V XSTAR triplet comparison row

For the current C V full-global XSTAR-like validation workflow, use the row

```text
comparison_case = full_global_xstar_tau0_calc_emis_ion
```

in `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`.  This row is the preferred comparison to the XSTAR detailed/emergent C V triplet fractions because it includes the full-global `xstar-lucy` population path, XSTAR-style continuum alias/superlevel handling, and `calc_emis_ion.f90` emergent-line escape treatment with geometry-derived type-50 optical depths.  The older simple per-ion printed baseline is retained only as a legacy diagnostic and should not be used for the current XSTAR C V triplet comparison.

### v0.3.66 calc_emis context writer fix

### v0.3.67 type-50 `ucalc` bound-bound diagnostic

v0.3.67 adds `xstar_like_element_solver_type50_ucalc_rate_audit.csv` and the experimental switch
`--type50-bound-bound-treatment raw-A|xstar-escape|xstar-escape-photoexcitation`. The default `raw-A`
preserves earlier behavior. The escape modes are diagnostic proxies for the XSTAR `ucalc.f90` type-50
path, where downward line rates are attenuated by `ptmp1+ptmp2` escape factors and upward radiative pumping
requires radiation-field/line-absorption context. Use `--type50-escape-factor` and
`--type50-photoexcitation-scale` only for controlled sensitivity tests until real optical-depth and bremsa/flinabs
context is ported.


v0.3.66 fixes the v0.3.65 output writer so `xstar_like_element_solver_calc_emis_context_audit.csv` is retrieved from the result dictionary before writing. It preserves the v0.3.65 diagnostic semantics and makes no intentional solver, matrix, or physical-rate changes.

# xstar-atomic

Latest package note: v0.3.113 continues the source-code-first Mg XI/Ca XIX validation. It aligns He-like type-67/type-68 collision-strength evaluation with XSTAR `ucalc.f90` by applying the `temp=max(T,2.8777e6/wavelength_A)` floor before `calt67/calt68`, records that effective temperature in collision audits, and adds `examples/49_mg_ca_triplet_source_path_audit.py` to map Mg/Ca triplet-feeding rows to XSTAR source-code branches without fitting scale factors.

Current development baseline: v0.3.80 continues the direct XSTAR-code population path. In addition to the v0.3.77 matrix-level continuum aliasing and `levwk`/`levwkelement`-style population seed, v0.3.78 adds `--inverse-recombination-mode xstar-ucalc`, which assembles type-53 inverse recombination from the source-code `phint53.f90` Milne `ans2` audit and type-74 inverse recombination from the source-aligned `calt74` alpha path with the XSTAR `gglo/ggup` correction. Older inverse-recombination proxy modes remain available for regression.

### v0.3.71 type-53/type-74 ucalc closure audit

v0.3.71 adds `xstar_like_element_solver_type53_type74_ucalc_closure_audit.csv`, a diagnostic-only audit intended to trace the remaining C V f/r mismatch back to XSTAR source-code semantics rather than another empirical scale scan.  The audit compares the current Python type-53/type-74 proxy closure with the relevant `ucalc.f90` branches: type 53 `phint53` forward photoionization and pending Milne inverse recombination, plus type 74 `calt74` forward delta-photoionization and inverse DR alpha after the XSTAR `gglo/ggup` correction.  It also writes component summaries for f/i/r/other inverse-source proxies.  No solver or physical-rate behavior is changed.

### v0.3.70 type-50 escape-factor scan

v0.3.70 adds `xstar_like_element_solver_type50_escape_factor_scan.csv` and the option `--type50-escape-factor-scan`.  The scan runs a controlled sequence of proxy XSTAR `ucalc` type-50 escape factors, using the diagnostic `xstar-escape` treatment for each scanned value while holding the other primary matrix terms fixed.  It reports f/i/r, R, G, L2-to-target, target-aware deltas, and summed raw versus escaped rates for the important He-like `1s2p 3P_J -> 1s2s 3S1` UV drain.  The primary solver remains unchanged unless `--type50-bound-bound-treatment` is explicitly changed from `raw-A`.

Example:

```bash
PYTHONPATH=src python examples/42_xstar_like_element_solver_demo.py \
  ../xstar/data/atdb.fits \
  --element C --he-like-stage 5 \
  --temperature 1000000 --electron-density 1e8 \
  --wavelength-min 40 --wavelength-max 42 \
  --max-level 80 \
  --full-global-linear-solver xstar-lucy \
  --type50-escape-factor-scan 0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1 \
  --out-dir c5_xstar_like_element_solver_v0370_type50_escape_scan \
  --print-summary
```

The scan is diagnostic only until the real XSTAR optical-depth, escape-probability, and line-pumping contexts are ported.

### v0.3.69 type-50 escaped-rate matrix bug fix

v0.3.69 fixes the experimental `--type50-bound-bound-treatment xstar-escape` path so the effective escaped rate is used in the actual assembled matrix `signed_rate_s^-1` entries, not only reported in the audit columns. The default `raw-A` behavior is unchanged.

### v0.3.65 calc_emis_ion runtime-context audit

The element solver now writes `xstar_like_element_solver_calc_emis_context_audit.csv`, a diagnostic companion to the v0.3.64 transparent `calc_emis_ion` triplet audit.  The new context audit keeps the solver unchanged, but reports the available matrix-population context for each He-like f/i/r line, including source-population-weighted feed (`alpha`), loss (`gamma`), dominant feed/loss records, and the line-accounting multipliers that would be required to match the XSTAR triplet target while holding solved populations fixed.  This isolates whether the remaining C V intercombination deficit could plausibly be fixed by `calc_emis_ion` escape/net-emissivity/strong-line accounting or whether the population balance must change.

The v0.3.64 `xstar_like_element_solver_calc_emis_triplet_audit.csv` is still written.  It compares the transparent `population * A * photon_energy` proxy with the `calc_emis_ion.f90` line-output form `max((ans2*abund2 - ans1*abund1) * E * ptmp, 0)`, while explicitly marking the missing XSTAR contexts: true `ucalc` net `ans1/ans2`, optical depths, `pescl` escape probabilities, covering fraction, abundance factors, and strong-line filtering (`nlbin`/`ncbin`).  No solver or rate behavior is intentionally changed.

### v0.3.58 note: explicit diagnostic XSTAR-style bremsa grid

v0.3.58 improves the radiation context used by the type-53/type-74 diagnostics.  The example now writes `xstar_like_element_solver_bremsa_context.csv`, an explicit log-spaced `epi` grid with diagnostic `bremsa` values in the units expected by XSTAR (`erg s^-1 cm^-2 erg^-1`) and a cumulative `bremsint` integral.  New options `--radiation-bremsa-scale`, `--radiation-energy-min-eV`, `--radiation-energy-max-eV`, `--radiation-n-energy-grid`, and `--radiation-powerlaw-index` allow controlled tests of the radiation normalization while preserving the XSTAR-Lucy full-global normalization solve.  This is still a diagnostic context, not the full XSTAR radiation-transfer continuum.


### v0.3.51 note: explicit XSTAR-style LU helpers

v0.3.51 updates the `--full-global-linear-solver xstar-lucy` diagnostic path to use local Numerical-Recipes-style helpers `_xstar_ludcmp`, `_xstar_lubksb`, and `_xstar_mprove`, matching the XSTAR `leqt2f -> ludcmp/lubksb/mprove` solver structure more directly.  The v0.3.50 implementation used NumPy's dense solve as the LU-backed step; v0.3.51 removes that delegation for the XSTAR-Lucy mode.  The package still does not use `scipy.linalg.lu` for this path, and the solve remains proxy-topology only until physical type-53/type-99/type-1 rates are evaluated.


### v0.3.50 note: XSTAR-style Lucy/LU full-global diagnostic solver

v0.3.50 adds `--full-global-linear-solver xstar-lucy`, a diagnostic solver mode patterned on the XSTAR `msolvelucy` path.  It builds a condensed superlevel matrix, replaces one row with number conservation, solves with an LU-style dense solve plus iterative-improvement corrections, expands back to level populations, and applies the Lucy fixed-point update.  The output `xstar_like_element_solver_full_global_normalized_solve_comparison.csv` now reports the XSTAR-Lucy iteration and rank diagnostics.  This is still a proxy-topology diagnostic, not a physical XSTAR solution, because type-53/type-99/type-1 physical rates are not yet evaluated.

### v0.3.49 note: full-global SVD/rank-aware normalized solve controls

The full-global C VI+C V normalized proxy-topology diagnostic now exposes rank-aware controls similar to the earlier He-like/O VII solver diagnostics.  `examples/42_xstar_like_element_solver_demo.py` accepts `--full-global-linear-solver solve|dense|lstsq|svd`, `--full-global-rank-deficient-action solve|lstsq|svd|error`, `--full-global-negative-population-action keep|clip|error`, and `--no-full-global-prune-null-rate-levels`.  Defaults are SVD, SVD rank handling, keep negative populations, and prune null-rate global-index rows.  This is intentionally different from production XSTAR, where `calc_hmc_element` calls `msolvelucy`, which solves a condensed superlevel system with a number-conservation row using LU decomposition (`leqt2f` -> `ludcmp`/`lubksb`) plus `mprove`.


### v0.3.43 note: type-53 radiation-context scaffold

`examples/42_xstar_like_element_solver_demo.py` now includes `--radiation-field-mode none|flat|blackbody|table` as a diagnostic scaffold for future type-53 photoionization and Milne inverse-recombination work. The run writes `xstar_like_element_solver_radiation_context.csv` and `xstar_like_element_solver_type53_rate_audit.csv`. These outputs map type-53 records onto the current global-index state inventory where possible and explicitly report the missing `phint53`/radiation-field context. No type-53 physical rates are evaluated or assembled yet.

### He-like validation summary tagging

`examples/34_summarize_helike_validation_runs.py` preserves condition-specific directory tags such as `ca19_xi3` and `ca19_xi4` in summary CSV/JSON/Markdown outputs.  This avoids merging multiple Ca XIX ionization-parameter grids into a single ambiguous `ca19` label.


### v0.2.97 note: He-like multi-ion validation summaries

The package now includes `examples/34_summarize_helike_validation_runs.py`, which summarizes completed He-like density-grid validation directories and optional XSTAR line-audit directories into CSV, JSON, and Markdown reports.  This is useful after running O VII, C V, Mg XI, or high-ionization Ca XIX grids because it records whether each density is reachable and whether complete XSTAR triplet targets were available.

Example:

```bash
PYTHONPATH=src python examples/34_summarize_helike_validation_runs.py \
  c5_solver_source_fit_density_xstar_grid \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  ca19_xi4_solver_source_fit_density_xstar_grid \
  --audit-dirs ca19_line_audit_ne1 ca19_line_audit_xi3_ne1 \
  --out-dir helike_validation_summary \
  --print-summary
```

### v0.2.96 note: Ca XIX ionization scans

For high-Z He-like ions such as Ca XIX, the default `log xi=1.5` XSTAR setup can produce lower charge states but no `ca_xix` triplet rows. Use the new `--rlogxi-grid` option in `examples/32_prepare_helike_xstar_density_grids.py` to prepare xi-tagged run directories and mapping files, for example:

```bash
PYTHONPATH=src python examples/32_prepare_helike_xstar_density_grids.py \
  --ions "Ca XIX" \
  --densities 1 1e4 1e8 1e10 1e12 \
  --rlogxi-grid 1.5 2 2.5 3 3.5 4 \
  --root . \
  --print-summary
```

This creates directories such as `xstar_runs/helike_type69/ca19_xi3_ne1/` and mapping files such as `xstar_test_run/xstar_ca19_xi3_density_grid_references.csv`. Run XSTAR and convert each xi grid, then audit with `examples/33_audit_helike_xstar_lines.py` to identify a grid that actually contains a complete Ca XIX f/i/r triplet target.


### v0.2.94 note

The non-O VII He-like validation workflow now performs stronger preflight checks on converted XSTAR triplet CSVs.  A mapping row must point to an existing CSV that contains usable forbidden, intercombination, and resonance rows with positive emissivity.  This catches cases such as Ca XIX where XSTAR ran but the converter produced zero matching triplet lines.  Non-O VII runs also now write ion-specific aliases for the legacy `o7_*` diagnostic filenames, for example `c5_solver_source_fit_summary.json` and `mg11_solver_source_fit_density_grid.csv`.  These C V/Mg XI/Ca XIX workflows remain exploratory; only the O VII density-grid suppress-resonance benchmark is currently validated.


### v0.2.83 note

This release standardizes the O VII density-grid benchmark inputs.  The package now keeps only compact density-specific converted XSTAR CSVs under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`; solver-fit directories such as `o7_solver_source_fit_density_xstar_grid/` are generated outputs, not required inputs.  `examples/22_o7_solver_source_fit_density_xstar_grid.py` and the high-density diagnostics can use `--auto-xstar-test-run-grid`, and `examples/26_o7_high_density_rate_sensitivity.py` now rejects stale `ne=1e12` density-grid outputs whose XSTAR target is inconsistent with the validated density-specific reference.


### v0.2.82 note

This release freezes the v0.2.81 O VII type-69 mode comparison as a reference validation snapshot.  The packaged snapshots under `examples/reference_outputs/` and `docs/validation/xstar_outputs/` record that the default `include` network fails only at `ne=1e12 cm^-3`, while the diagnostic/experimental `suppress-resonance` mode reaches the density-specific XSTAR target there without degrading the lower-density benchmark rows.  The suppress-resonance mode remains validated only for this O VII high-density benchmark and is not a general physical default.

### v0.2.81 note

This release adds `examples/30_o7_density_grid_type69_mode_compare.py`, which runs the O VII density-grid source-fit benchmark in both type-69 modes: the original `include` network and the diagnostic/experimental `suppress-resonance` network.  It writes one merged CSV with the density, include/suppress-resonance R/G ratios, reachability flags, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.

`--collision-type69-ground-excitation-mode suppress-resonance` is intentionally marked diagnostic/experimental.  It suppresses type-69 excitation from the ground level into the He-like resonance upper level and is validated for the O VII high-density benchmark; it is not a general physical default.

### v0.2.80 note

This release fixes the row-level handling of `--collision-type69-ground-excitation-mode suppress-resonance`, so the full density-grid chain can now pass the diagnostic switch through to `xstar_atomic.solver` without rejecting unrelated collision rows.


`xstar-atomic` is an early research Python package for direct access to XSTAR's packed atomic database FITS file, usually:

```text
xstar/data/atdb.fits
```

Unlike ordinary FITS atomic databases, `atdb.fits` is organized as four packed arrays:

```text
POINTERS, REALS, INTEGERS, CHARS
```

This package decodes those arrays, reconstructs the element/ion/level/process hierarchy, and provides first-pass physics extractors and emissivity tools.

### v0.3.18 type-57 `calt57` diagnostic evaluator

Adds a source-code-guided Python port/audit of the XSTAR type-57 collisional-ionization path:

- ports the visible `calt57 -> irc -> szirc/eint/expint` helper chain from the uploaded XSTAR source;
- evaluates type-57 records diagnostically into `cion`, `crec`, `ans1=cion*ne`, and the inverse `ans2` estimate;
- records source/destination level diagnostics, threshold/binding energy, statistical-weight assumptions, and expected matrix role;
- deliberately keeps type-57 rates unassembled by default until the matrix role and destination/source mapping are validated.

### v0.3.17 ucalc-style adjacent-coupling audit

The pure-Python XSTAR-like element solver now writes `xstar_like_element_solver_ucalc_adjacent_audit.csv`.  This table annotates adjacent-ion candidate records with the corresponding XSTAR `ucalc.f90` branch for type 53, 57, 74, 95, and 99 records, the physical context needed to evaluate each branch, and the matrix role if implemented.  Type-95 Bryans collisional-ionization records receive a diagnostic forward-rate estimate; photoionization/DR/superlevel records are deliberately audited but not blindly assembled without the XSTAR radiation-field/continuum context.

## Current status

This is an alpha/development package created by refactoring validated standalone scripts. The following pieces are working or partially working:

- Packed FITS record decoding.
- Element, ion, and level hierarchy reconstruction.
- Level decoder for XSTAR `data_type=6`.
- Radiative line decoder for `data_type=50`.
- Photoionization cross-section decoder for `data_type=53`.
- Collisional excitation decoders:
  - `data_type=56` tabulated effective collision strengths.
  - `data_type=63` Bautista `n,l` algorithmic branch for `nf != ni` and `|Δl| = 1`.
- Recombination / charge-exchange extractors:
  - `data_type=1`, `30`, `38`, `39` electron recombination total rates.
  - `data_type=2` charge exchange with neutral H when explicitly requested.
- Direct emissivity-table builder.
- Prototype level-population solver with connected-component diagnostics and source/sink hooks.
- Prototype cascade source redistribution using radiative branching.

Important limitations:

- Not all XSTAR data types are decoded.
- True level-resolved recombination/cascade records have not been found in the currently decoded oxygen records.
- Same-`n` `l`-mixing for `data_type=63` / XSTAR `amcrs` is implemented as a Python port, but should still be compared against XSTAR outputs for final science.
- The level-population solver is a diagnostic prototype, not a full replacement for XSTAR.


## Scientific validation status

The table below summarizes the current scientific status of the main decoder paths.  ``Validated`` means covered by real-``atdb.fits`` tests and internal consistency checks; it does not replace comparison against full XSTAR model outputs for publication-quality work.

| Component | XSTAR data type(s) | Current status | Validation examples |
|---|---:|---|---|
| Packed FITS reader / hierarchy | pointers/reals/integers/chars | Validated | 1,216,792 records, 30 elements, 465 ions |
| Levels | 6 | Validated | O VIII and O VII level indexing and labels |
| Radiative lines | 50 | Validated | O VIII Ly-alpha, O VII triplet, Ne X, Fe XXVI checks |
| Photoionization grids | 53 | Validated for ordinary OP-style grids | O VIII and O VII ground thresholds |
| Collisions, tabulated Upsilon | 56 | Validated | O VIII Ly-alpha rates and emissivity rows |
| Collisions, Bautista n,l, nf != ni | 63 | Validated internally | O VII/O VIII direct-excitation records |
| Collisions, same-n l-mixing | 63 | Implemented and regression-tested | O VIII same-n diagnostic; compare with XSTAR for final science |
| Collisions, Burgess--Tully 5-point | 51 | Implemented and API-tested | Representative real-ATDB target tests |
| Collisions, CHIANTI 2016 BT | 98 | Implemented and API-tested | Ne IX representative target test |
| Electron recombination totals | 1, 30, 38, 39 | Implemented for total rates | Oxygen RR/DR inventory |
| Charge exchange with H0 | 2 | Implemented when explicitly requested | Low-ion oxygen CX inventory |
| True level-resolved recombination/cascades | various/unknown | Not yet identified in decoded records | Prototype source/cascade hooks only |
| Level-population solver | combined | Prototype | Connected-component and source/sink diagnostics |



## Stage-5 XSTAR comparison runs

The `xstar_test_run/README.md` file records reproducible direct-XSTAR commands
for validation runs. Current documented runs include:

- O VIII / Ne IX high-ionization line validation.
- O VII triplet and high-density O VII triplet validation.
- Ne IX and Ne X focused runs for Stage-5 wavelength comparisons.
- Validated Mg XI/Mg XII, Si XIII/Si XIV, and Fe XXV/Fe XXVI Stage-5 wavelength comparisons.

The Ne-focused and Mg/Si/Fe-focused workflows convert `xout_lines1.fits` to CSV with
`python -m xstar_atomic.xstar_outputs`, then compare wavelengths with
`examples/08_compare_xstar_outputs.py`. The first validated Ne target products are:

```text
xstar_ne9_triplet_lines.csv
compare_ne9_triplet_wavelength.csv/json
xstar_ne10_lya_lines.csv
compare_ne10_lya_wavelength.csv/json
```


Additional Stage-5 validated heavy-ion targets are:

```text
Mg XI  He-like triplet region: 9.0--9.4 Angstrom
Mg XII Ly-alpha region:        8.35--8.50 Angstrom
Si XIII He-like triplet region: 6.55--6.80 Angstrom
Si XIV Ly-alpha region:        6.10--6.25 Angstrom
Fe XXV K-alpha region:         1.83--1.88 Angstrom
Fe XXVI Ly-alpha region:       1.76--1.80 Angstrom
```

These Mg/Si/Fe validation products are now included: `xout_lines1.fits` artifacts under `xstar_test_run/`, selected-line CSV files, and comparison CSV/JSON files under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`. All selected Mg/Si/Fe lines match within the 0.02 Angstrom tolerance used for the wavelength checks.


Validated Mg/Si/Fe wavelength results included in this release:

```text
Mg XI   5/5 matched, max |Delta lambda| = 4.52e-6 Angstrom
Mg XII  2/2 matched, max |Delta lambda| = 1.96e-6 Angstrom
Si XIII 5/5 matched, max |Delta lambda| = 3.51e-6 Angstrom
Si XIV  2/2 matched, max |Delta lambda| = 3.89e-6 Angstrom
Fe XXV  4/4 matched, max |Delta lambda| = 4.10e-6 Angstrom
Fe XXVI 2/2 matched, max |Delta lambda| = 3.55e-6 Angstrom
```

As with the O VIII and O VII examples, these comparisons validate line
identification and wavelength decoding. XSTAR `emit_inward`/`emit_outward`
columns are full model outputs and are not directly normalized to local
`xstar-atomic` emissivity coefficients.

## Data download and path configuration

`xstar-atomic` does not bundle the large XSTAR `atdb.fits` file. Use the data helper to download it or save the path to an existing copy:

```bash
python -m xstar_atomic.data
# or, after installation
xstar-atomic-download-data
```

The helper reports the remote file size, asks whether to download (pressing Enter means yes), asks for a destination directory, downloads with a single-line ASCII progress bar, and stores the selected data directory in `datapath`. In a source checkout the default destination is the project-level `data/` directory and the persistent path file is the project-level `datapath`, not `src/xstar_atomic/datapath`.

Example progress line:

```text
xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)
```

The default public source is:

```text
https://heasarc.gsfc.nasa.gov/FTP/software/lheasoft/lheasoft6.36/heasoft-6.36/ftools/xstar/data/atdb.fits
```

If you already have `atdb.fits`, decline the download and enter the full path, or configure it non-interactively:

```bash
python -m xstar_atomic.data --set-path /path/to/atdb.fits
python -m xstar_atomic.data --show
```

Programmatic helpers are available from the top-level package:

```python
from xstar_atomic import (
    download_data,
    resolve_atdb_path,
    find_atdb_file,
    get_data_path,
    set_data_path,
)

# Interactive download/configuration.
atdb_path = download_data()

# Or save an existing local file for future sessions.
set_data_path('/path/to/xstar/data/atdb.fits')
atdb_path = resolve_atdb_path()
```

After configuration, the high-level API can omit the FITS path:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic(index_cache=True, index_cache_format='npz')
lines = db.lines('O VIII', wavelength=(18.8, 19.1), slim=True)
```

Path resolution order is:

```text
explicit path
XSTAR_ATDB_FITS
datapath
data/atdb.fits
interactive download/configuration
```


### C V detail-population comparison and O VII handoff (v0.3.91)

After running `examples/42_xstar_like_element_solver_demo.py`, compare the full-global C V populations and the recommended emergent triplet row with:

```bash
PYTHONPATH=src python examples/43_compare_xstar_detail_populations.py \
  --solver-out-dir c5_xstar_like_element_solver_v0390_xstar_msolvelucy_superlevels \
  --element C --he-like-stage 5 \
  --comparison-case full_global_xstar_tau0_calc_emis_ion \
  --print-summary
```

If an XSTAR detail population table is available as CSV or FITS, add:

```bash
  --xstar-detail path/to/xstar_detail_populations.csv
```

The utility writes:

```text
xstar_detail_population_comparison.csv
xstar_detail_population_comparison_summary.json
xstar_detail_population_comparison.md
```

For the next O VII validation step, generate an O VII full-global output directory with `--element O --he-like-stage 7` and then run the same comparison utility with:

```bash
PYTHONPATH=src python examples/43_compare_xstar_detail_populations.py \
  --solver-out-dir o7_xstar_like_element_solver_output \
  --element O --he-like-stage 7 \
  --target-f nan --target-i nan --target-r nan \
  --print-summary
```

## Installation

From the package directory:

```bash
python -m pip install -e .
```

## Command-line tools

After installation, these commands are available:

```bash
xstar-atomic-inspect
xstar-atomic-hierarchy
xstar-atomic-lines
xstar-atomic-photoionization
xstar-atomic-collisions
xstar-atomic-recombination
xstar-atomic-emissivity
xstar-atomic-solver
```

## Examples

Inspect the packed database:

```bash
xstar-atomic-inspect ./xstar/data/atdb.fits --summary
```

Extract O VIII Ly-alpha lines:

```bash
xstar-atomic-lines ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1
```

Evaluate O VIII Ly-alpha collisional excitation:

```bash
xstar-atomic-collisions ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --search --lower-level 1 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7
```

Build an O VIII Ly-alpha emissivity table:

```bash
xstar-atomic-emissivity ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o8_lya_emissivity.csv --print-summary
```

Run the prototype level-population solver on the ground-connected component:

```bash
xstar-atomic-solver ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --electron-densities 1.0 \
  --component-mode ground \
  --out-lines-csv o8_lya_pop_lines.csv --print-summary
```

## Python API example

```python
from xstar_atomic import ATDB

atdb = ATDB("./xstar/data/atdb.fits")
records, elements, ions = atdb.build_index()
print(len(records), len(elements), len(ions))
```

High-level convenience API:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("./xstar/data/atdb.fits")

# Reuses the same validated decoders as the command-line tools.
lya = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
coll = db.collisions("O VIII", lower_level=1, wavelength=(18.8, 19.1), temperatures=[1e6, 3e6, 1e7])
emiss = db.emissivity("O VIII", wavelength=(18.8, 19.1), temperatures=[1e6, 3e6, 1e7])
recomb = db.recombination(element="O", temperatures=[1e6])

print(len(lya))
print(emiss["summary"])
```

The low-level `ATDB` API remains available for direct packed-FITS access, while `XSTARAtomic` is the recommended science-facing wrapper for rates, emissivities, and solver-related workflows.


## Collision-decoder validation tools

`xstar-atomic` includes a validation helper for collision-rate decoder development.
It can inventory ions containing selected collision data types, find representative
evaluable records, and run a type-63 same-`n` l-mixing diagnostic.

```bash
PYTHONPATH=src python -m xstar_atomic.validation ../xstar/data/atdb.fits \
  --inventory \
  --find-targets \
  --data-types 51 98 \
  --targets-csv collision_type51_98_targets.csv

PYTHONPATH=src python -m xstar_atomic.validation ../xstar/data/atdb.fits \
  --type63-same-n \
  --element O \
  --ion-stage 8 \
  --temperatures 1e6 \
  --electron-density 1.0
```

The same checks are available in `examples/07_collision_decoder_validation.py`.

## Testing

Run metadata/layout tests without the XSTAR database:

```bash
pytest -q
```

Run the real `atdb.fits` smoke tests by setting `XSTAR_ATDB_FITS`:

```bash
XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
```

The ATDB-dependent tests validate the same O VIII/O VII workflows used during development, including O VIII Ly-alpha lines, collisions, emissivity, and oxygen recombination inventory.

## Example scripts

The `examples/` directory contains runnable scripts that work without installing the package when `PYTHONPATH=src` is set:

```bash
PYTHONPATH=src python examples/01_o8_lya_lines.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/02_o8_lya_collisions.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/03_o8_lya_emissivity.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/04_oxygen_recombination_inventory.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/05_low_level_atdb_index.py /path/to/xstar/data/atdb.fits
```

## Changelog

See `CHANGELOG.md`.

## Development roadmap

See `docs/TODO.md`.


### Flexible ion names

The high-level `XSTARAtomic` API accepts several common ion spellings:

```python
db.lines("O VIII", wavelength=(18.8, 19.1))
db.lines("o viii", wavelength=(18.8, 19.1))
db.lines("o_viii", wavelength=(18.8, 19.1))
db.lines("OVIII", wavelength=(18.8, 19.1))
db.lines("o8", wavelength=(18.8, 19.1))
```

## User guide and documentation

Full user guides are included in both Markdown and LaTeX:

```text
docs/user_guide.md
docs/user_guide.tex
```

A Sphinx documentation scaffold using the Read the Docs theme is included under:

```text
docs/sphinx/
```

Build the Sphinx HTML documentation with:

```bash
python -m pip install -e .[docs]
cd docs/sphinx
make html
```

Sphinx API pages use `sphinx.ext.autodoc`, which reads Python docstrings from modules, classes, and functions. New public functions should include docstrings so they appear correctly in the generated API reference.

### Collision decoder status

`xstar-atomic` currently evaluates the main supported collision-rate paths:

- `data_type=56`: tabulated effective collision strengths, interpolated in `log10(T/K)`.
- `data_type=63`: Bautista `n,l` algorithmic collisions, including both `n_f != n_i, |\Delta l|=1` and same-`n` l-mixing through the XSTAR `amcrs`/`velimp` branch.
- `data_type=51`: Burgess--Tully scaled collision strengths.
- `data_type=98`: CHIANTI-2016-style Burgess--Tully scaled collision strengths.

Same-`n` l-mixing depends weakly on the electron density through the impact-parameter cutoff. In the Python API, pass `electron_density_for_lmixing=...` to `collisions()` or `emissivity()` when this matters.


## Plasma post-processing export

Create compact CSV/JSON/HDF5 atomic products for selected ions.  The exporter is intended for superwinds, AGN outflows, and other plasma post-processing workflows:

```bash
PYTHONPATH=src python -m xstar_atomic.export ./xstar/data/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 30.0 \
  --formats csv,hdf5 \
  --out-dir atomic_export \
  --print-summary
```

The export writes levels, lines, collision records/rates, photoionization summaries, emissivity rows, JSON manifests, and optional per-ion HDF5 files.  The installable CLI aliases are `xstar-atomic-export` and the backward-compatible `xstar-atomic-export-superwind`.

### Reading XSTAR output FITS files

Convert an XSTAR `xout_lines1.fits` file to CSV for validation against `xstar-atomic` outputs:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs xout_lines1.fits \
  --out-csv xstar_lines.csv \
  --print-summary
```

You can also filter by ion and wavelength:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs xout_lines1.fits \
  --ion "O VIII" --wavelength-min 18.8 --wavelength-max 19.1 \
  --out-csv xstar_o8_lya_lines.csv --print-summary
```


## XSTAR comparison validation examples

Saved O VIII Ly-alpha and O VII triplet comparisons against XSTAR `xout_lines1.fits` outputs are included under:

```text
docs/validation/xstar_outputs/
examples/reference_outputs/
```

See `docs/xstar_comparison_examples.md` for commands and interpretation. These examples validate line identification and wavelengths; absolute ratios against XSTAR `emit_inward`/`emit_outward` require model-dependent normalization.


### Included XSTAR validation runs

The source distribution includes `xstar_test_run/`, which contains small direct-XSTAR `xout_lines1.fits` outputs and converted CSV line tables for:

- O VIII / Ne IX high-ionization validation.
- O VII triplet validation.
- O VII high-density triplet validation.

See `xstar_test_run/README.md` and `docs/xstar_comparison_examples.md` for the exact XSTAR commands and the `xstar_atomic.xstar_outputs` conversion commands.

### Band emissivity export

Broad-band line emissivity products can be generated with ``--bands-kev``:

```bash
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 40.0 \
  --bands-kev soft:0.5:2.0 osoft:0.3:0.6 med:0.6:1.0 hard:2.0:10.0 \
  --formats csv,hdf5 \
  --out-dir atomic_export \
  --print-summary
```

This writes ``*_band_emissivity.csv`` and, for HDF5 exports, a ``/band_emissivity`` group.

The Stage-4 validation run passed 34 real-ATDB tests and confirmed 12 band-emissivity rows per ion for four bands and three temperatures. Zero-line bands keep nonblank ion labels and use `methods_used="none"`.


### Band-emissivity export notes

Band-emissivity rows keep the ion label even for bands with zero selected lines, and use `methods_used="none"` for zero-line bands. This makes CSV/HDF5 exports easier to ingest in simulation post-processing workflows.

### Stage-3 sparse solver and O VII triplet diagnostics

The level-population solver supports dense, sparse, and auto linear solvers:

```bash
PYTHONPATH=src python -m xstar_atomic.solver /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 \
  --electron-densities 1.0 \
  --electron-density-for-lmixing 1.0 \
  --component-mode ground \
  --linear-solver sparse \
  --summary-json o8_sparse_solver_summary.json \
  --print-summary
```

For O VII triplet stress tests, run:

```bash
PYTHONPATH=src python examples/10_o7_triplet_sparse_solver.py \
  /path/to/atdb.fits \
  --out-dir o7_triplet_solver_example
```

The solver reports sparse/dense matrix diagnostics and can write prototype
O VII triplet `R=f/i` and `G=(f+i)/r` diagnostics. These are solver validation
outputs, not final physical line-ratio predictions unless the recombination and
cascade source model is complete.
### Solver timing example

Benchmark dense and sparse level-population solver modes end-to-end:

```bash
PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits \
  --repeat 3 \
  --out-dir solver_timing_example
```

Include the heavier O VII triplet sparse stress test:

```bash
PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits \
  --include-o7 \
  --repeat 2 \
  --out-dir solver_timing_example \
  --out-csv solver_timing.csv
```

The timing CSV reports elapsed wall time plus matrix size, nonzero count,
sparsity, condition number, solver backend, and residual diagnostics.  The
current sparse solver already uses SciPy's compiled sparse linear algebra; a
future optional C++ backend would mainly accelerate repeated record filtering,
rate evaluation, matrix assembly, and production export loops.


### ATDB index caching

The solver-step profiler showed that repeated workflows are dominated by `build_index`, not by the sparse linear solve.  You can enable an optional on-disk hierarchy cache for repeated runs:

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py \
  ../xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperature 1e6 --electron-density 1.0 \
  --linear-solver sparse \
  --index-cache \
  --index-cache-format npz \
  --out-dir solver_profile_npz_arrays_hit
```

The first cached run writes a file named similar to:

```text
atdb.fits.xstar_atomic_index.npz
```

A later run with `--index-cache` should report `index_cache_status="hit"` and skip the full hierarchy scan.  Use `--rebuild-index-cache` after changing or replacing `atdb.fits`.

The same cache options are available in the solver and export CLIs:

```bash
PYTHONPATH=src python -m xstar_atomic.solver /path/to/atdb.fits ... --index-cache
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits ... --index-cache
```

From Python:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("xstar/data/atdb.fits", index_cache=True)
print(db.db.index_cache_status)
```

The cache stores the decoded hierarchy objects and validates them against the source FITS file size, modification time, array lengths, and cache format version.

### Solver step profiling and O VII recombination/cascade workflow

`xstar-atomic` includes two solver-development examples that are useful before
building an optional compiled backend.

Profile individual solver stages:

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py \
  ../xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperature 1e6 --electron-density 1.0 \
  --linear-solver sparse \
  --index-cache \
  --index-cache-format npz \
  --out-dir solver_profile_npz_arrays_hit
```

Prototype O VII recombination/cascade source workflow:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_recomb_cascade_workflow \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv
```

A future compiled backend can be distributed as an optional shared-object
library (`.so`) loaded by Python.  The best first targets are ATDB filtering,
record unpacking, collision-rate loops, sparse matrix assembly, and band/export
aggregation; SciPy already provides compiled sparse linear solvers.


### Recommended array-backed NPZ index cache

For repeated workflows, use the array-backed NumPy/NPZ cache.  It stores the hierarchy as numeric arrays, filters by element/ion/data type, and converts only selected rows to `IndexedRecord` objects.  This is now the recommended path for solvers, exports, high-level API calls, and profiling.

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py \
  ../xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperature 1e6 --electron-density 1.0 \
  --linear-solver sparse \
  --index-cache \
  --index-cache-format npz \
  --out-dir solver_profile_npz_arrays_hit
```

On the validated O VIII sparse-solver profile, the cache-hit path reduced the run from about `5.31 s` uncached to about `0.53 s` with an NPZ array-backed cache hit.  The `build_index` stage dropped from about `5.00 s` to about `0.058 s`.

The default cache file is `atdb.fits.xstar_atomic_index.npz`.  Use `--rebuild-index-cache` after replacing or modifying `atdb.fits`.  Legacy pickle caching remains available with `--index-cache-format pickle`, but NPZ array-backed caching is preferred for targeted workflows.

The same cache options are accepted by the solver and export CLIs:

```bash
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 40.0 \
  --bands-kev soft:0.5:2.0 med:0.6:1.0 hard:2.0:10.0 \
  --formats csv,hdf5 \
  --index-cache --index-cache-format npz \
  --out-dir atomic_export_cached
```

Download progress is shown on one in-place ASCII progress-bar line, for example:

```text
xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)
```


### Ne IX / Ne X Stage-5 XSTAR comparison artifacts

The package includes saved Ne IX and Ne X direct-XSTAR line-output artifacts under `xstar_test_run/`, plus comparison CSV/JSON outputs under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`. The Ne IX triplet/near-triplet and Ne X Ly-alpha wavelength comparisons both match all selected XSTAR lines within 0.02 Angstrom.


### Stage 6 cascade-yield source allocation

The O VII recombination/cascade workflow now supports a less purely statistical
source distribution for total O VIII -> O VII recombination.  The new
`selected-cascade-yield` mode weights each candidate source level by its
radiative-cascade probability of feeding user-selected target levels, such as
the O VII triplet upper levels.  This remains a prototype because the decoded
oxygen recombination records are total rates rather than true level-resolved
recombination feeds.

Example:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-cascade-yield \
  --cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0 \
  --cascade-weight-floor 0.02 \
  --out-dir o7_recomb_cascade_workflow \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

The workflow writes initial source rows, cascade-redistributed source rows,
cascade path diagnostics, sparse-solver populations and O VII triplet `R=f/i`
and `G=(f+i)/r` diagnostics.


### Stage-6 O VII triplet target maps

The recommended Stage-6 baseline remains the equal-target cascade-yield map:

```bash
--source-mode selected-cascade-yield \
--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0
```

This baseline preserved the good `G=(f+i)/r` agreement with the XSTAR O VII reference. For experiments that try to reduce `R=f/i` without strongly changing `G`, use a forbidden-to-intercombination shift preset such as:

```bash
--cascade-target-preset o7-triplet-f2i025-rkeep
```

which expands to `2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`. It preserves the resonance target and approximately preserves the total triplet-target weight. Manual `--cascade-target-levels` overrides any preset.

### Stage-6 O VII cascade tuning scan

The equal-target `selected-cascade-yield` map remains the recommended Stage-6
baseline because it preserves the good XSTAR agreement in `G=(f+i)/r`:

```bash
--source-mode selected-cascade-yield \
--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0
```

For controlled experiments, the preferred presets now shift target weight from the forbidden upper level into the intercombination upper levels while preserving the resonance target and the total triplet-target weight. This is intended to reduce `R=f/i` without strongly moving `G=(f+i)/r` away from the equal-target baseline:

```text
o7-triplet-f2i010-rkeep -> 2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0
o7-triplet-f2i015-rkeep -> 2:0.85,3:1.05,4:1.05,5:1.05,7:1.0
o7-triplet-f2i025-rkeep -> 2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0
o7-triplet-f2i050-rkeep -> 2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0
```

The older simple `fdown` presets remain available for reproducibility, but they reduced `G` too much in the first tuning scan.

Use the tuning scan helper to run the equal baseline plus the experimental
presets and summarize `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII
reference:

```bash
PYTHONPATH=src python examples/15_o7_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

The scan writes `o7_cascade_tuning_scan.csv` and a JSON summary. The aim is to
reduce `R` while keeping `G` close to the equal-target/XSTAR value; the equal
map should remain the baseline unless an experimental preset improves both.


### O VII metastable/intercombination coupling diagnostics

Stage 6 includes a focused diagnostic for the density-sensitive O VII triplet coupling between the forbidden-line upper level and the intercombination manifold.  It inspects level 2 -> levels 3, 4, and 5 and compares collisional transfer rates with decoded radiative rates over a density grid.

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
  ../xstar/data/atdb.fits \
  --temperature 1e6 \
  --electron-densities 1 1e4 1e8 1e10 1e12 \
  --index-cache --index-cache-format npz \
  --out-dir o7_metastable_coupling \
  --print-summary
```

The outputs are `o7_metastable_coupling_rates.csv` and `o7_metastable_coupling_summary.json`.  This diagnostic does not change the cascade source model; it shows whether collisional transfer can compete with forbidden-level radiative decay at the densities of interest.

### He-like collisional coupling diagnostics

Version 0.2.47 adds XSTAR He-like collision decoders for data types 67, 68, and 69. These are important for testing whether O VII metastable/intercombination coupling is present in `atdb.fits` outside the previously decoded type-63 collision records. The O VII diagnostic now also writes a collision inventory for all records involving levels 2, 3, 4, and 5:

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
  ../xstar/data/atdb.fits \
  --temperature 1e6 \
  --electron-densities 1 1e4 1e8 1e10 1e12 \
  --index-cache --index-cache-format npz \
  --out-dir o7_metastable_coupling \
  --print-summary
```

New output:

```text
o7_metastable_coupling/o7_metastable_coupling_collision_inventory.csv
```

### Type-68-aware O VII cascade tuning scan

After He-like collision data types 67/68/69 are enabled, O VII includes the
metastable-to-intercombination coupling from level 2 into levels 3, 4, and 5.
This gives the expected density-sensitive behavior in `R=f/i`, but it can make
the low-density `G=(f+i)/r` too small for the previous cascade-source map.
The type-68-aware scan keeps the equal triplet weights fixed and progressively
downweights the resonance target level 7:

```text
o7-triplet-type68-r095 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.95
o7-triplet-type68-r090 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.90
o7-triplet-type68-r085 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.85
o7-triplet-type68-r080 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.80
o7-triplet-type68-r075 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.75
o7-triplet-type68-r070 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.70
o7-triplet-type68-r060 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.60
o7-triplet-type68-r050 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.50
```

Run the scan with:

```bash
PYTHONPATH=src python examples/17_o7_type68_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_type68_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

The scan writes `o7_type68_cascade_tuning_scan.csv`,
`o7_type68_cascade_tuning_scan_all_densities.csv`, and a JSON summary. Use this
scan after the type-67/68/69 He-like collision decoders are active. The equal
target map remains the reference baseline; the type-68-aware presets are
experiments for restoring `G` while preserving the density-sensitive `R` physics.

### Stage-6 two-parameter O VII type-68 cascade scan

After enabling He-like type 67/68/69 collisions, the package includes a broader O VII triplet scan that varies both forbidden/intercombination redistribution and resonance suppression while keeping the equal-target map as the reference baseline:

```bash
PYTHONPATH=src python examples/18_o7_type68_2d_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_type68_2d_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

For a forbidden-to-intercombination shift `d` and resonance weight `r`, the scan uses:

```text
2:(1-d), 3:(1+d/3), 4:(1+d/3), 5:(1+d/3), 7:r
```

It writes compact, ranked, and all-density CSV tables plus a JSON summary.

### Stage-6 cascade source-fit diagnostic

For O VII, empirical target-weight scans indicate that the remaining mismatch is likely tied to the unknown level-resolved recombination source distribution. The diagnostic example `examples/19_o7_cascade_source_fit.py` builds a radiative cascade yield matrix,

```text
Y(source level -> forbidden, intercombination, resonance)
```

then solves for nonnegative source weights that best reproduce the saved XSTAR O VII triplet ratios `R=f/i` and `G=(f+i)/r`.

```bash
PYTHONPATH=src python examples/19_o7_cascade_source_fit.py \
  ../xstar/data/atdb.fits \
  --index-cache --index-cache-format npz \
  --out-dir o7_cascade_source_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

Outputs:

```text
o7_cascade_source_fit/o7_cascade_yield_matrix.csv
xstar_test_run/o7_source_fit_weights.csv
o7_cascade_source_fit/o7_source_fit_summary.json
```

This is a diagnostic tool, not a final physical recombination model. It asks what source-level distribution would be required by the current radiative cascade network to reproduce XSTAR-like O VII triplet ratios.



### Stage-6 full-solver source-fit diagnostic

The cascade-yield fit in `examples/19_o7_cascade_source_fit.py` is useful for testing the radiative branching network, but its fitted weights are not guaranteed to reproduce the same R/G ratios when injected into the full statistical-equilibrium solver.  For the stricter full-solver diagnostic, use the rank-aware SVD treatment that was validated against the saved XSTAR O VII triplet reference:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

The recommended diagnostic solver settings are:

```text
linear_solver = svd
rank_deficient_action = svd
negative_population_action = keep
prune_null_rate_levels = true
source_total_rate = 1.0 s^-1
```

These settings are important because the O VII statistical-equilibrium matrix is rank-deficient and highly ill-conditioned.  In the validation run, the combined-source solve used `numpy.linalg.svd_lstsq`, had matrix rank `231/238`, condition number about `3.1e18`, residuals `linear_residual_l2 ~ 0.0032` and `linear_residual_linf ~ 0.0032`, and one raw negative population retained for diagnostic linearity.  Null-rate pruning removed levels `44`, `45`, and `241`.

The script automatically performs a combined-source validation solve after fitting the weights.  Its summary reports the XSTAR R/G target, the fitted linear-response R/G prediction, and the actual simultaneous-solver R/G result, together with matrix rank, condition number, residuals, null-rate pruning diagnostics, source/sink summaries, and negative-population diagnostics.  Use `--skip-combined-validation` only when you want the older response-matrix-only behavior.

A validated v0.2.62 run gave:

```text
XSTAR R=3.20837 G=10.5622
Fitted linear-response R=3.20838 G=10.5622
Combined simultaneous-solver R=3.20838 G=10.5622
R/R_XSTAR = 1.00000146
G/G_XSTAR = 0.99999836
```

The compatible output weights can then be used with the recombination/cascade workflow.  Use the same SVD/rank-aware solver treatment and scale the solver source CSV to the same total source rate used by the fit:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv o7_solver_source_fit/o7_source_fit_weights.csv \
  --solver-source-csv-mode initial \
  --solver-source-total-rate 1.0 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --out-dir o7_recomb_cascade_workflow_solver_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

These weights are empirical diagnostics, not physical level-resolved recombination rates.  The recommended SVD path is the validated path for this O VII/XSTAR-fit diagnostic; direct dense or sparse solves should not be trusted for this rank-deficient matrix unless their residual and combined-source validation diagnostics are checked.

For package regression tests, the validated v0.2.62 O VII source-fit summary is saved as `examples/reference_outputs/o7_solver_source_fit_summary_reference.json`.  The lightweight CI tests in `tests/test_o7_solver_source_fit_reference.py` verify the saved XSTAR R/G match, the agreement between fitted linear-response and combined simultaneous-solver validation, and the recommended SVD/null-rate-pruning solver treatment without requiring the full `atdb.fits` file.  When using `examples/13_o7_recombination_cascade_workflow.py` with `selected-fit-weights` or `o7-xstar-fit`, v0.2.64 emits a warning unless `--solver-source-total-rate` is supplied, because the empirical weights are amplitude-dependent.


### Validated O VII diagnostic commands

The validated O VII empirical solver-source-fit path is:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

The matching cascade-workflow validation should use the same total source amplitude:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv o7_solver_source_fit/o7_source_fit_weights.csv \
  --solver-source-csv-mode initial \
  --solver-source-total-rate 1.0 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --out-dir o7_recomb_cascade_workflow_solver_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

Reference snapshots for the density-grid diagnostic are saved in `examples/reference_outputs/o7_solver_source_fit_density_grid.csv` and `examples/reference_outputs/o7_solver_source_fit_density_grid_summary.json`.

### Known limitation of empirical O VII weights

The O VII fitted source weights in these examples are empirical diagnostics.  They are fitted to reproduce XSTAR triplet ratios for a specified solver setup, density, source-level set, and total source amplitude.  They are not physical level-resolved recombination rates and should not be used as a substitute for a recombination/cascade source model derived from atomic data.

### O VII density-grid source-fit diagnostic

After validating the empirical O VII full-solver source fit at `ne = 1 cm^-3`, use `examples/21_o7_solver_source_fit_density_grid.py` to test whether the fitted source distribution is stable with density.  The default grid is:

```text
ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3
```

Run:

```bash
PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_grid \
  --print-summary
```

This script runs the validated `examples/20_o7_solver_source_fit.py` workflow at each density, then also validates the fixed `ne=1 cm^-3` source weights at every density.  It writes:

```text
o7_solver_source_fit_density_grid/o7_solver_source_fit_density_grid.csv
o7_solver_source_fit_density_grid/o7_solver_source_fit_density_grid_summary.json
```

The CSV reports the reused low-density XSTAR R/G reference, fixed-`ne=1` R/G, refitted linear-response R/G, refitted combined simultaneous-solver R/G, matrix rank, condition number, residuals, negative-population diagnostics, and source-weight changes relative to the reference density.  In v0.2.66 it also adds `fit_success_vs_xstar` and `target_reachable` feasibility flags; `refitted_R_over_xstar`, `refitted_G_over_xstar`, `fixed_R_over_refitted`, and `fixed_G_over_refitted` ratio columns; and per-density warnings when the fit objective is large or the refitted combined R/G ratios remain outside tolerance.  The XSTAR target label is written explicitly as a low-density reference reused at all densities unless a later density-dependent XSTAR reference-table option is added.  This is a diagnostic for density dependence of the empirical source distribution after type-68 metastable/intercombination coupling; the fitted weights remain empirical and should not be interpreted as physical level-resolved recombination rates.


For density-dependent XSTAR reference products, use `examples/22_o7_solver_source_fit_density_xstar_grid.py`.  This front end calls the same density-grid machinery but requires one XSTAR line CSV per density, so each density is compared against its own XSTAR target rather than against the reused low-density reference.

A mapping CSV can be written as:

```text
electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label
1,xstar_o7_ne1_lines.csv,emit_outward,O VII XSTAR ne=1
1e10,xstar_o7_ne1e10_lines.csv,emit_outward,O VII XSTAR ne=1e10
1e12,xstar_o7_ne1e12_lines.csv,emit_outward,O VII XSTAR ne=1e12
```

Run:

```bash
Before running the density-specific grid, create a starter mapping CSV and replace each placeholder `xstar_lines_csv` value with the converted XSTAR line CSV for that density:

```bash
PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  --write-template-grid-csv xstar_test_run/xstar_o7_density_grid_references.template.csv
```

Then run the grid with the edited mapping file:

PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_xstar_grid \
  --print-summary
```

Alternatively, supply repeated `--xstar-lines-csv-by-density DENSITY:CSV` arguments.  The output CSV keeps `xstar_target_is_reused_low_density_reference=false` and records the XSTAR CSV path and target label used for each density.


### Stage-6 empirical source-fit mode

The O VII cascade source-fit diagnostic writes `o7_source_fit_weights.csv`. These weights can be reused as an empirical diagnostic source allocation with:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv xstar_test_run/o7_source_fit_weights.csv \
  --out-dir o7_recomb_cascade_workflow_fit_weights \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

A convenience diagnostic mode is also available:

```bash
--source-mode o7-xstar-fit
```

When no explicit `--source-fit-weights-csv` is supplied, this mode looks for the packaged/source-tree reference file `xstar_test_run/o7_source_fit_weights.csv`. These fitted weights are empirical diagnostics derived from the current O VII/XSTAR comparison, not true level-resolved recombination rates.

## Preparing O VII density-dependent XSTAR references

Use `examples/23_prepare_o7_xstar_density_grid.py` to create the real XSTAR run plan needed by the density-dependent O VII comparison.  The helper writes one clean XSTAR run directory per density, each with a `run_xstar.sh` script containing the full XSTAR command, plus conversion scripts and the mapping CSV consumed by `examples/22_o7_solver_source_fit_density_xstar_grid.py`.

```bash
PYTHONPATH=src python examples/23_prepare_o7_xstar_density_grid.py \
  --root . \
  --mapping-csv xstar_test_run/xstar_o7_density_grid_references.csv \
  --print-summary
```

Run the generated XSTAR scripts externally:

```bash
bash xstar_runs/o7_ne1/run_xstar.sh
bash xstar_runs/o7_ne1e4/run_xstar.sh
bash xstar_runs/o7_ne1e8/run_xstar.sh
bash xstar_runs/o7_ne1e10/run_xstar.sh
bash xstar_runs/o7_ne1e12/run_xstar.sh
```

After each run produces `xout_lines1.fits`, convert the line files:

```bash
bash xstar_runs/o7_ne1/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e4/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e8/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e10/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e12/convert_o7_triplet.sh
```

Then run the true density-dependent XSTAR-grid comparison:

```bash
PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_xstar_grid \
  --print-summary
```

### O VII high-density mismatch diagnostic

After running the density-dependent XSTAR-grid comparison, use `examples/24_o7_high_density_mismatch_diagnostics.py` to focus on the high-density failure case, usually `ne=1e12 cm^-3`:

```bash
PYTHONPATH=src python examples/24_o7_high_density_mismatch_diagnostics.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --reference-density 1 \
  --index-cache \
  --out-dir o7_high_density_mismatch \
  --print-summary
```

The diagnostic reads the outputs from examples 21/22 and writes component, source-weight, collision-rate, and JSON summaries.  It reports which normalized triplet component drives the mismatch, whether the XSTAR target is reachable, whether fitted source weights collapse onto a small number of levels, solver rank/residual/negative-population diagnostics, and type-68/69 level-2 to level-3/4/5 collision rates when `atdb.fits` is supplied.  This remains an empirical diagnostic; it does not provide physical level-resolved recombination rates.

### O VII high-density expanded source scan

`examples/25_o7_high_density_expanded_source_scan.py` tests whether the high-density O VII mismatch can be removed by expanding the empirical source-level set beyond the validated baseline.  It scans baseline, `n<=5`, `n<=6`, `n<=8`, and all-level source proxies against the density-specific XSTAR target from the density-grid workflow.

### O VII high-density rate-sensitivity diagnostic

`examples/26_o7_high_density_rate_sensitivity.py` scans temporary diagnostic
scale factors for selected collision-rate families after the expanded source
scan has shown that source-level expansion alone does not recover the
`ne=1e12 cm^-3` XSTAR O VII target.  It supports scans of the symmetric
level-2-to-3/4/5 metastable coupling and the XSTAR type-68/type-69 decoded
collision blocks.  These scale factors are diagnostics only; they do not change
the atomic database.

```bash
PYTHONPATH=src python examples/26_o7_high_density_rate_sensitivity.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --families metastable,type68,type69 \
  --scales 0.1,0.2,0.5,1,2,5,10 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_high_density_rate_sensitivity \
  --print-summary
```

The output `o7_high_density_rate_sensitivity_scan.csv` reports the best R/G,
R/XSTAR, G/XSTAR, component mismatch, and solver diagnostics for each scaled
network.

### O VII high-density type-69 transition sensitivity

After the high-density rate-family scan showed that reducing type-69 collision rates can recover the `ne=1e12 cm^-3` XSTAR O VII triplet target, v0.2.74 adds an individual-transition diagnostic:

```bash
PYTHONPATH=src python examples/27_o7_type69_transition_sensitivity.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --scan-mode record \
  --scales 0.1,0.2,0.5,2,5,10 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_type69_transition_sensitivity \
  --print-summary
```

This scan writes `o7_type69_transitions.csv`, `o7_type69_transition_sensitivity.csv`, and `o7_type69_transition_sensitivity_summary.json`. The record/pair scaling is diagnostic only and does not modify the atomic data.

### v0.2.75 O VII type-69 record audit

After `examples/27_o7_type69_transition_sensitivity.py` identifies the individual type-69 records that control the high-density O VII mismatch, version 0.2.75 adds a raw-record audit:

```bash
PYTHONPATH=src python examples/28_o7_type69_record_audit.py \
  ../xstar/data/atdb.fits \
  --records 22490,22491,22492,22493,22494,22495 \
  --density 1e12 \
  --audit-temperature 1e6 \
  --temperature-grid 1e5,3e5,1e6,3e6,1e7 \
  --transition-sensitivity o7_type69_transition_sensitivity \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_type69_record_audit \
  --print-summary
```

The audit writes `o7_type69_record_audit.csv`, `o7_type69_record_raw_audit.csv`, `o7_type69_record_temperature_grid.csv`, and `o7_type69_record_audit_summary.json`. These files expose the raw `idat`/`rdat` fields, decoded lower/upper levels, level labels, energy separations, statistical weights, `calt69` Upsilon values, excitation/de-excitation rates, detailed-balance checks, and any record-level sensitivity results inherited from the v0.2.74 scan. This is diagnostic only; it does not apply a physical correction.

### v0.2.77 ground-coupling diagnostic hotfix

Version 0.2.77 fixes the ground-coupling diagnostic introduced in v0.2.76.  Some example-20 summaries do not include a usable fitted-weights CSV path; the diagnostic now treats empty or directory paths as missing and falls back to the standard per-case outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`).

### v0.2.76 O VII type-69 ground-coupling diagnostic

After the type-69 record audit, the next diagnostic isolates whether the
high-density O VII mismatch is caused by the whole record-22490 pair, by its
excitation direction, or by its de-excitation direction:

```bash
PYTHONPATH=src python examples/29_o7_type69_ground_coupling_diagnostic.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --record 22490 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_type69_ground_coupling_diagnostic \
  --print-summary
```

The script writes `o7_type69_ground_coupling_diagnostic.csv` and a JSON
summary.  Direction-specific cases use the diagnostic solver option
`--collision-record-direction-scale RECORD:DIRECTION:SCALE`; these cases are
not physical corrections by themselves, because they intentionally break
detailed balance to separate the lower-to-upper excitation and upper-to-lower
de-excitation influence of a single ATDB collision record.

### v0.2.78 diagnostic type-69 ground-excitation suppression switch

Version 0.2.78 adds a controlled diagnostic/experimental solver option for the high-density O VII investigation:

```bash
--collision-type69-ground-excitation-mode include|suppress-resonance|suppress-all
```

The default, `include`, preserves the original v0.2.77 behavior.  `suppress-resonance` suppresses only type-69 excitation from the ground level into the He-like resonance upper level while preserving the reverse/de-excitation rate.  For the validated O VII high-density case this is record 22490, level `1 -> 7` (`1s2.1S_0 -> 1s.2p 1P_1`).  `suppress-all` suppresses all type-69 excitation out of the ground level and is broader.

Example density-grid rerun using the targeted switch:

```bash
PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --collision-type69-ground-excitation-mode suppress-resonance \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_xstar_grid_type69_suppressed \
  --print-summary
```

The option is diagnostic and should not yet be treated as a final physical correction.  It makes the v0.2.77 conclusion reproducible with a single switch: the high-density O VII XSTAR target is recovered when the ground-to-resonance type-69 excitation path is suppressed while de-excitation is retained.


Generated density-grid output directories are intentionally not bundled as package inputs. In particular, `o7_solver_source_fit_density_xstar_grid/`, `o7_high_density_rate_sensitivity/`, and `o7_density_grid_type69_mode_compare/` are reproducible outputs created by the examples, while the compact density-specific XSTAR line CSVs live under `xstar_test_run/o7_ne*/`.


### He-like type-69 ground-resonance validation audit

Example 31 broadens the O VII type-69 investigation to other He-like ions.  It audits candidate type-69 ground-to-resonance excitation records for ions such as C V, N VI, O VII, Ne IX, Mg XI, Si XIII, S XV, Ar XVII, Ca XIX, and Fe XXV, and writes candidate and validation-status tables.  The script does not mark non-O VII ions as validated unless density-specific XSTAR triplet grids are supplied; without those external references they remain `pending_xstar_density_grid`.  O VII is the currently validated benchmark because the package includes compact converted density-specific XSTAR references under `xstar_test_run/o7_ne*/`.

```bash
PYTHONPATH=src python examples/31_helike_type69_ground_resonance_validation.py \
  ../xstar/data/atdb.fits \
  --ions "C V,N VI,O VII,Ne IX,Mg XI,Si XIII,S XV,Ar XVII,Ca XIX,Fe XXV" \
  --temperature-grid 1e6 \
  --density 1e12 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_helike_index.npz \
  --out-dir helike_type69_ground_resonance_validation \
  --print-summary
```

This keeps `suppress-resonance` as a diagnostic/experimental O VII benchmark mode until similar density-grid XSTAR validation exists for other He-like ions.



Version 0.2.88 note: the density-grid wrappers now use an ion-generic He-like triplet reader for converted XSTAR line CSVs.  The reader classifies the forbidden, intercombination, and resonance components from `lower_level`/`upper_level` labels such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`, so C V, Mg XI, Ca XIX, and similar He-like grids can be fitted with the same workflow used for O VII.

### Preparing non-O VII He-like XSTAR density grids

Example 32 prepares the external XSTAR density-grid runs needed to test whether the O VII `suppress-resonance` behavior also appears for other candidate He-like ions.  By default it prepares C V, Mg XI, and Ca XIX, the non-O VII ions with candidate type-69 ground-to-resonance records in the audit.  The helper writes run scripts and conversion scripts only; it does not run XSTAR and does not validate those ions by itself.

```bash
PYTHONPATH=src python examples/32_prepare_helike_xstar_density_grids.py \
  --ions "C V,Mg XI,Ca XIX" \
  --densities 1 1e4 1e8 1e10 1e12 \
  --root . \
  --print-summary
```

After running XSTAR externally and converting `xout_lines1.fits`, the generated per-ion mappings, such as `xstar_test_run/xstar_c5_density_grid_references.csv`, `xstar_test_run/xstar_mg11_density_grid_references.csv`, and `xstar_test_run/xstar_ca19_density_grid_references.csv`, can be used for ion-specific density-grid comparisons.  Until those converted XSTAR triplet grids are supplied and compared, only O VII should be treated as validated.



Version 0.2.90 note: the density-grid front end now writes ion-specific He-like mapping templates.  If `xstar_test_run/xstar_c5_density_grid_references.csv` is missing, the generated template points to `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv`; it no longer writes the O VII placeholder path.  Run the example 32 XSTAR scripts and converters first, or copy the converted triplet CSVs into those paths, then rerun the C V density-grid command.

Version 0.2.89 note: the He-like density-grid front end now detects stale non-O VII mapping CSVs that still point to the O VII placeholder file and repairs them when the correct converted per-density files exist under `xstar_test_run/<ion>_ne*/`.  For example, a C V mapping is repaired to use `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv`, with the original mapping saved as a `.bak` file.

Version 0.2.91 note: the He-like density-grid front end now validates mapping CSV paths before launching the solver-fit subprocesses.  If a C V, Mg XI, or Ca XIX mapping points to files that are not present in the current package tree, the script stops with a clear message telling you to run the example 32 XSTAR/convert scripts in this tree, or to copy the converted `<ion>_ne*` folders from the tree where you generated them.  This prevents confusing downstream failures from missing files such as `xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv`.

### v0.2.92 He-like combined-solver triplet diagnostics

The solver-side triplet diagnostics are now generic for He-like ions. Combined simultaneous-solver validation can report R=f/i and G=(f+i)/r for C V, Mg XI, Ca XIX, and other He-like ions using level labels such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`. O VII wavelength-based fallback remains available for legacy O VII outputs.

### v0.2.93 robust printing for exploratory non-O VII He-like fits

The C V density-grid validation path can read the XSTAR C V triplet target, but some exploratory solver-side response matrices may have incomplete triplet diagnostics, for example a missing resonance component in a uniform or fitted response.  `examples/20_o7_solver_source_fit.py` now prints `NA` for missing uniform, fitted, or combined R/G values instead of formatting `None` as a floating-point value and aborting.  The JSON and CSV outputs continue to store missing values as `null`/blank so downstream density-grid summaries can mark the target as not reached rather than crashing.


### Auditing empty He-like XSTAR triplet conversions

If a prepared He-like density grid runs in XSTAR but the converter reports `n_lines=0`/`n_rows=0`, inspect the raw `xout_lines1.fits` file before trying the solver.  For example, for Ca XIX:

```bash
PYTHONPATH=src python examples/33_audit_helike_xstar_lines.py \
  xstar_runs/helike_type69/ca19_ne1/xout_lines1.fits \
  --expected-ion "Ca XIX" \
  --wavelength-min 3.0 \
  --wavelength-max 3.4 \
  --out-dir ca19_line_audit_ne1 \
  --print-rows
```

This reports all XSTAR ion labels, nearby rows in the wavelength window, and rows whose lower/upper labels look like He-like ground-to-`n=2` forbidden/intercombination/resonance transitions.  It is diagnostic only; an ion with empty triplet CSVs remains not testable until a complete XSTAR triplet target is found.


### He-like source-level failure diagnostics (v0.3.0)

After running the density-grid source-fit workflows, compare the fitted source vectors and response matrices at source-level resolution:

```bash
PYTHONPATH=src python examples/36_source_level_failure_diagnostics.py \
  o7_solver_source_fit_density_xstar_grid_type69_suppressed \
  c5_solver_source_fit_density_xstar_grid \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  ca19_xi4_solver_source_fit_density_xstar_grid \
  --out-dir helike_source_level_failure_diagnostics \
  --print-summary
```

For deeper atomic-rate annotation, pass the real XSTAR database:

```bash
PYTHONPATH=src python examples/36_source_level_failure_diagnostics.py \
  c5_solver_source_fit_density_xstar_grid \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  --fitsfile ../xstar/data/atdb.fits \
  --out-dir helike_source_level_failure_diagnostics \
  --print-summary
```

The output CSV/JSON/Markdown tables report the source level label/configuration, fitted weight, f/i/r response contribution, zero-response flags, optional source-component population, dominant radiative decay path, dominant collisional sink/source, and pruning/weak-connectivity flags. Older v0.2.x archives lack combined-solver population CSVs; rerunning the v0.3.0 workflows fills those population columns.
#### v0.3.1 diagnostic notes

`examples/36_source_level_failure_diagnostics.py` now reports template-only or otherwise empty density-grid directories explicitly instead of silently writing empty tables.  When population exports are absent, the summary prints `pop=unavailable` rather than `pop=0`.  Supplying `--fitsfile` uses the current `ATDB.build_index()` API to annotate dominant radiative and collisional paths.


### v0.3.2 source-level zero-response accounting

Version 0.3.2 fixes a diagnostic normalization artifact in the He-like
source-level workflow.  Source levels whose unit-source solver output has
zero positive forbidden/intercombination/resonance response are now kept as
zero-response columns rather than being normalized to an artificial
`1/3,1/3,1/3` response vector.  The source-level diagnostic also reports the
sum of fitted source weight assigned to all-zero response levels and to levels
with negative raw response components.

### v0.3.3 response-basis filtering diagnostic

`examples/37_filter_source_basis_response.py` compares fitted He-like source bases after dropping source levels with zero or negative raw f/i/r response. It is intended to distinguish source-basis contamination from missing physics in non-O VII He-like triplet runs. Example:

```bash
PYTHONPATH=src python examples/37_filter_source_basis_response.py \
  o7_solver_source_fit_density_xstar_grid_type69_suppressed \
  c5_solver_source_fit_density_xstar_grid_v031 \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  ca19_xi4_solver_source_fit_density_xstar_grid \
  --out-dir helike_source_basis_filter_comparison \
  --print-summary
```

The utility writes CSV, JSON, and Markdown reports and compares `all`, `drop_zero_response`, `drop_negative_response`, and `positive_nonzero_response` bases.

### v0.3.6 robust source-level block preflight

`examples/39_scan_helike_source_level_blocks.py` now preflights the ATDB level table before running each block.  This avoids the Ca XIX failure mode where a requested block such as `2:40` includes level indices outside the levels available for Ca XIX.  Invalid levels are skipped by default and recorded in `helike_source_level_block_scan.csv`.

Each block also writes child-process logs:

```text
<out-dir>/<block-tag>/example20.stdout.log
<out-dir>/<block-tag>/example20.stderr.log
```

Use `--no-skip-invalid-source-levels` to restore the old behavior when deliberately testing invalid or edge-case level lists.


### v0.3.7 block-scan preflight diagnostics

`examples/39_scan_helike_source_level_blocks.py` now performs two best-effort preflight checks before launching block fits:

1. the ATDB level table is inspected, when available, so invalid source levels can be skipped;
2. the converted XSTAR triplet CSV supplied with `--xstar-lines-csv` is checked for matching ion rows and complete f/i/r components.

This makes failures such as a missing `xstar_test_run/ca19_xi3_ne1e8/xstar_ca19_triplet_lines.csv` file explicit before the scan falls through to `examples/20_o7_solver_source_fit.py`.

### v0.3.8 signed/absolute triplet-response audit

`examples/40_audit_signed_triplet_response.py` runs a baseline solver calculation and one source-injected calculation per requested level. It writes `helike_signed_triplet_response_audit.csv`, `helike_signed_triplet_response_commands.csv`, `helike_signed_triplet_response_summary.json`, and `helike_signed_triplet_response_audit.md`. The audit compares baseline f/i/r emissivities, source-injected f/i/r emissivities, delta responses, signed normalized delta vectors, sign patterns, and component-wise increase/decrease flags. It is designed to test whether negative non-O VII response columns are caused by baseline subtraction, normalization artifacts, or genuinely destructive population redistribution.

Example:

```bash
PYTHONPATH=src python examples/40_audit_signed_triplet_response.py \
  ../xstar/data/atdb.fits \
  --element C --ion-stage 5 \
  --temperature 1000000 --electron-density 1e8 \
  --wavelength-min 40 --wavelength-max 42 \
  --source-levels 2:80 \
  --index-cache --index-cache-path .xstar_atomic_cache/atdb_c5_index.npz \
  --out-dir c5_signed_triplet_response_audit \
  --print-summary
```


### v0.3.9 datapath-safe ATDB resolution

Examples that were added for the He-like response diagnostics no longer need a positional `../xstar/data/atdb.fits` once the package data path has been configured. Configure it once with:

```bash
PYTHONPATH=src python -m xstar_atomic.data --set-path /path/to/atdb.fits
PYTHONPATH=src python -m xstar_atomic.data --show
```

Then run diagnostics without the positional FITS argument, for example:

```bash
PYTHONPATH=src python examples/40_audit_signed_triplet_response.py \
  --element C --ion-stage 5 \
  --temperature 1000000 --electron-density 1e8 \
  --wavelength-min 40 --wavelength-max 42 \
  --source-levels 2:80 \
  --index-cache --index-cache-path .xstar_atomic_cache/atdb_c5_index.npz \
  --out-dir c5_signed_triplet_response_audit \
  --print-summary
```

Supplying an explicit `atdb.fits` path still works, but it is now treated as a per-command override and does not rewrite `datapath`.


## v0.3.27 note

Adds diagnostic-only type-74 direct triplet-source audit output `xstar_like_element_solver_type74_triplet_source_audit.csv`.


## v0.3.28 note

This version adds an optional diagnostic triplet-source injection mode:

```bash
--triplet-source-mode type74-direct-diagnostic
```

When enabled, the example evaluates direct type-74 DR-delta triplet source candidates and injects their candidate source rates into the existing single-ion source vector for a before/after solve.  It writes `xstar_like_element_solver_triplet_source_injection_comparison.csv` with baseline, injected, and C V target f/i/r fractions.  The default remains `--triplet-source-mode none`; the diagnostic injection is not the final global element-wide matrix assembly.
## v0.3.29 note

`examples/42_xstar_like_element_solver_demo.py` now accepts `--triplet-source-scale` for diagnostic type-74 direct triplet-source injection.  A comma-separated list such as `1,1e2,1e4,1e6,1e8,1e10` writes `xstar_like_element_solver_triplet_source_scale_scan.csv`, with one solved row per scale plus baseline and target rows.  This remains a single-ion diagnostic source-vector experiment and does not assemble type-74 terms into the final element-wide matrix.



## v0.3.30 note

This release fixes the v0.3.29 type-74 direct triplet-source scale-scan crash caused by a missing `_xstar_triplet_target()` helper. The scan now writes target-fraction and L2-distance columns when the built-in C V ne=1e8 target applies. No source term is physically assembled into the global matrix; this remains a diagnostic single-ion source-vector experiment.


## v0.3.32 note

Version v0.3.32 fixes the explicit element-wide state-index scaffold.  Superlevel-like ATDB labels such as `sprlevls` and `sprlevlt` are now classified as `level_kind=superlevel` with `is_superlevel=True`.  Continuum rows remain `level_kind=continuum` with `is_continuum=True`.  The global-index CSV also now reports `parent_level_index` and `continuum_represents_parent`, so a lower-ion continuum row can explicitly indicate that it represents the adjacent parent ion stage, usually parent level 1.  This version does not assemble a global matrix yet; it prepares the state map for the next element-wide matrix-assembly step.

## v0.3.31 note

Version v0.3.31 adds the first explicit element-wide state-index scaffold for the pure-Python XSTAR-like element solver.  `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_index.csv`, which assigns a stable `global_index` to all decoded levels for the selected ion stages and adds explicit parent-continuum placeholder rows where adjacent lower/upper ion stages need a future continuum coupling column.  The file reports `ion_stage`, `level_index`, `level_kind`, `energy_eV`, `stat_weight`, `configuration`, `is_triplet_upper`, `is_superlevel`, and `is_continuum`.  This version does not yet assemble or solve a global matrix; it provides the structural map needed for later XSTAR-like element-wide coupling.

### v0.3.33 global bound-bound matrix scaffold

Version v0.3.33 adds the first sparse-like global bound-bound matrix term table for the pure-Python XSTAR-like element solver.  The example now writes `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, which maps the existing per-ion radiative and collisional transition logs onto the explicit `global_index` rows.  Each transition contributes an off-diagonal gain term and a diagonal loss term using global matrix row/column indices.  This prepares the C VI + C V element-wide matrix assembly while preserving the existing single-ion solve; the global matrix is not solved yet.


### v0.3.35 global type-71 superlevel cascade matrix scaffold

Version v0.3.35 adds the first global-index matrix scaffold for radiative superlevel cascades.  The element-solver example now writes `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`, which maps type-71 superlevel-to-spectroscopic records onto the explicit `global_index` state table.  Each assembled cascade contributes an off-diagonal gain term `M[spectroscopic_global_index, superlevel_global_index] += A` and a diagonal loss term `M[superlevel_global_index, superlevel_global_index] -= A`.  This is still a diagnostic scaffold: the type-71 terms are not yet included in the solved global matrix, and the type-77/type-70/type-74/type-99 superlevel source/cascade paths remain diagnostic-only.

### v0.3.34 global bound-bound block solve comparison

Version v0.3.34 adds the first diagnostic solve using the explicit global-index bound-bound matrix scaffold. The example writes `xstar_like_element_solver_global_bound_bound_solve_comparison.csv`, which solves the He-like ion intra-ion bound-bound block assembled from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv` using the same adjacent source vector as the current per-ion solver. The output compares baseline per-ion populations and triplet f/i/r ratios against the global-index block solution. This is an equivalence test and does not yet solve the full element-wide C VI + C V coupled matrix.


### v0.3.38 type-71 solve-comparison CSV writer fix

Version v0.3.38 fixes the v0.3.36 output handoff for `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv`. The extended global bound-bound+type-71 solve rows were being built and summarized internally, but they were not returned from `solve_element_reference()`, so the CSV writer received an empty list. This version returns those rows and writes the populated comparison CSV. No physics behavior is intentionally changed; this remains a diagnostic global-block scaffold rather than the full element-wide coupled solver.

### v0.3.36 global bound-bound plus type-71 solve diagnostic

Version v0.3.36 adds the next global-matrix scaffold test. The element-solver example now writes `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv`, which assembles the verified He-like global bound-bound block, adds the type-71 superlevel-to-spectroscopic cascade matrix triplets, rebuilds the same adjacent source vector used by the current per-ion solve, and solves the extended global-index block. This diagnostic reports summary rows for the old per-ion baseline and the global bound-bound+type-71 block, plus level-by-level population comparisons including superlevel rows. No type-70/type-74/type-99 superlevel source terms are included yet, so this remains a structural test rather than the full element-wide coupled solution.


### v0.3.38 diagnostic type-99 superlevel source scaffold

The element solver now writes `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv`, a diagnostic global-index scaffold that maps type-99 superlevel source candidates to explicit superlevel rows and parent-continuum proxy columns. These proxy terms are not included in the solved matrix yet.

### v0.3.39 diagnostic bound-bound+type71+type99-proxy solve

Version v0.3.39 adds a nonphysical diagnostic solve that combines the global-index bound-bound block, type-71 superlevel-cascade matrix terms, and v0.3.38 type-99 superlevel source-vector proxy rows.  The new output `xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv` compares the existing per-ion baseline with a global-index block solve that feeds mapped type-99 superlevels through proxy source terms.  These proxy terms are not XSTAR `phint53pl` rates and are not a final physical assembly; the purpose is to test matrix topology and the direction of superlevel feeding before porting/evaluating true type-99 rates and full adjacent-ion normalization.

### v0.3.40 type-99 proxy scale scan

Version v0.3.40 adds a diagnostic scale scan for the nonphysical type-99 superlevel source proxy used by the global bound-bound+type-71 scaffold.  Use `--type99-proxy-scale` with one value or a comma-separated list, for example `0,1e-8,1e-6,1e-4,1e-2,1,1e2`.  The example writes `xstar_like_element_solver_type99_proxy_scale_scan.csv`, which reports the solved f/i/r fractions, R, G, L2 distance to the C V target, type-99 proxy source sum, superlevel population sum, and solver status for each scale.  The proxy values are not XSTAR `phint53pl` rates; this scan only diagnoses source normalization and matrix topology before physical type-99 radiation integrals are implemented.


### v0.3.41 note

Fixes the v0.3.40 CLI handoff for `--type99-proxy-scale` by adding the corresponding `solve_element_reference()` keyword argument. No physics behavior is intentionally changed.

### v0.3.42 note

Fixes the remaining v0.3.41 signature regression for `--type99-proxy-scale`: the solver entry point now actually accepts the keyword used by `examples/42_xstar_like_element_solver_demo.py`. No physics behavior is intentionally changed.

### v0.3.48 full global normalized proxy-topology solve

Version v0.3.48 adds `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`, the first diagnostic normalized solve over the unified C VI+C V global-index matrix scaffold.  The solver assembles a dense matrix over all explicit `global_index` rows from `xstar_like_element_solver_full_global_matrix_terms.csv`, includes only matrix triplet rows, deliberately excludes source-vector proxy rows, replaces one row with `sum_i n_i = 1`, and solves the resulting system.  The output compares the normalized full-global proxy-topology populations and C V f/i/r fractions against the existing per-ion baseline.  This remains diagnostic only: the matrix still contains nonphysical proxy topology terms and does not yet evaluate XSTAR `phint53`, Milne inverse recombination, or type-99 `phint53pl` rates.

### v0.3.47 full global C VI+C V matrix-topology scaffold

Version v0.3.47 adds `xstar_like_element_solver_full_global_matrix_terms.csv`, a unified diagnostic topology table for the future element-wide matrix solve.  It combines the existing C VI and C V bound-bound matrix blocks, C V type-71 superlevel cascade matrix terms, type-99 parent-continuum-to-superlevel proxy topology, type-53 flat photoionization proxy topology, and mappable type-1 recombination source/topology rows.  This file is not yet solved as a normalized global matrix.  It is a scaffold for the next step, where a true C VI+C V population normalization row can be added and the full matrix can be solved.


### v0.3.53 note: type-53 phint53 summary crash fix

v0.3.53 fixes a v0.3.52 summary-generation crash in the type-53 `phint53` diagnostic path (`NameError: name '_sum_float' is not defined`).  The release adds the missing module-level finite-sum helper used by the phint53 audit and matrix-term summaries.  No physics behavior is intentionally changed.

### v0.3.52 note: type-53 phint53 photoionization-kernel diagnostic

v0.3.52 keeps the full-global diagnostic default on the XSTAR-Lucy solver path and adds the first type-53 `phint53` forward-photoionization kernel diagnostic. The run now writes `xstar_like_element_solver_type53_phint53_rate_audit.csv` and `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv`. These rows replace the older flat type-53 proxy in the full-global matrix topology whenever the phint53-kernel rows are matrix-ready. The kernel maps type-53 cross-section pairs onto the radiation grid and integrates the XSTAR-style `sigma(E) * bremsa(E) / E` photoionization term. The continuum field is still a placeholder in this release; Milne inverse recombination, opacity/escape probability, and the real XSTAR radiation field remain pending.


### v0.3.54 note: type-53 phint53 scale scan and radiation normalization audit

v0.3.54 adds a diagnostic `phint53` scale scan for the full-global XSTAR-Lucy path.  The option `--type53-phint53-scale` now accepts comma-separated scale factors; the first value controls the primary phint53 audit/matrix outputs, while all values are evaluated in `xstar_like_element_solver_type53_phint53_scale_scan.csv`.  The release also writes `xstar_like_element_solver_radiation_normalization_audit.csv`, which records the placeholder radiation-grid/bremsa normalization currently used by the forward phint53 kernel.  This is still not a physical XSTAR continuum: true bremsa/radiation field, Milne inverse recombination, opacity/escape probabilities, and physical type-99/type-1 rates remain pending.


### v0.3.55 inverse-recombination scaffold

The element-solver demo now accepts `--inverse-recombination-mode none|type53-milne-diagnostic|type74-direct-diagnostic|type53-type74|xstar-ucalc`.  The new mode writes diagnostic topology/audit CSVs for type-53 Milne inverse recombination and type-74 direct DR-delta inverse routes. These are scaffolds only: they are not yet physical XSTAR Milne or DR rates.

### v0.3.56 inverse-recombination scale scan

The diagnostic full-global solver now exposes independent inverse-recombination scale controls:

```bash
--inverse-recombination-mode type53-type74 \
--type53-milne-scale 1,1e10,1e20,1e30 \
--type74-inverse-scale 1,1e5,1e10,1e15
```

The first scale in each list is used for the primary full-global matrix.  All requested scales are scanned and written to `xstar_like_element_solver_inverse_recombination_scale_scan.csv`.  This matches the XSTAR source direction: type 53 uses `phint53`/`milne`, while type 74 uses `calt74`; the current Python rows remain diagnostic proxies until the true radiation and continuum context is ported.


### v0.3.57 source-aligned type-74 calt74 diagnostic

Version 0.3.57 adds `xstar_like_element_solver_type74_calt74_rate_audit.csv` and `xstar_like_element_solver_global_type74_calt74_matrix_terms.csv`.  The diagnostic ports the two-output structure of XSTAR `calt74`: forward DR-delta photoionization `rate` and inverse recombination `alpha`, then applies the `ucalc` statistical-weight correction `alpha *= gglo/ggup` for the inverse topology.  The full-global matrix prefers these source-aligned type-74 rows when available.  Absolute forward rates are still tied to the placeholder radiation/bremsa context, so this remains a diagnostic scaffold rather than a physical XSTAR solution.


### v0.3.73 diagnostic correction

v0.3.73 fixes the v0.3.72 `phint53` Milne integral audit so the audit uses the original type-53 cross-section grids from the raw type-53 audit rows. The solver behavior is unchanged.
### v0.3.79 experimental XSTAR ion-fraction closure

`v0.3.79` adds `--ion-fraction-closure xstar-istruc`, an experimental
implementation of the two-stage XSTAR `calc_ion_rates` / `istruc` closure for
the full-global `xstar-lucy` path.  It sums positive inter-stage matrix rates,
forms the adjacent-stage equilibrium `x_low I = x_high R`, and applies the
resulting ion-stage targets during the Lucy level-population iteration.  The
default `--ion-fraction-closure none` preserves earlier behavior.
