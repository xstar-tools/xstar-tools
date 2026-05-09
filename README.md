Latest package note: v0.3.121 improves the He-like local-state validation driver. `examples/51_run_helike_local_state_validation.py` now handles C/O density-only XSTAR runs such as `helike_type69/c5_ne1e8` and `helike_type69/o7_ne1e8` more clearly, reports available local `log xi`/`ne` values when filters exclude a case, and can auto-convert a matched `xout_lines1.fits` into a triplet target CSV if no preconverted `xstar_*_triplet_lines.csv` is found. No solver physics changed and no triplet scale fitting was added.

Recommended all-ion local-state discovery at `ne≈1e8`:

```bash
PYTHONPATH=src python examples/51_run_helike_local_state_validation.py \
  --xstar-runs-root xstar_runs \
  --target-root xstar_atomic_v0.3.111_results \
  --atdb ../xstar/data/atdb.fits \
  --selection-mode max \
  --target-electron-density 1e8 \
  --nearest-density \
  --out-dir helike_local_state_validation_v03121_ne1e8_allions \
  --print-summary
```

Use the `--log-xi` filter only when all requested ions have matching ion-specific XSTAR runs at that local `log xi`; C V/O VII density-only runs may have their own local `log xi` from `xout_abund1.fits`.

Latest package note: v0.3.117 makes the Mg XI / Ca XIX XSTAR local-state audit easier to use on isolated solver outputs. `examples/50_mg_ca_xstar_local_state_audit.py` now accepts repeated `--solver-out-dir` arguments and falls back to scanning the current working directory when `--results-root` contains no Mg/Ca solver cases. This fixes the previous confusing `cases=0` result when XSTAR target CSVs and solver outputs were kept in different directories. No default solver physics changed and no triplet scale fitting was added.

Latest package note: v0.3.116 adds a source-code-first Mg XI / Ca XIX local-state audit. It does not fit scale factors or change default physics. The new `examples/50_mg_ca_xstar_local_state_audit.py` checks whether each solver comparison has the matching XSTAR `xout_abund1.fits` local zone state, selects the zone with maximum He-like ion fraction, and compares XSTAR T/ne/xi/radiation prerequisites against the solver assumptions.

Recommended next validation: rerun the Mg XI/Ca XIX XSTAR targets while preserving `xout_abund1.fits`, then run the local-state audit. If XSTAR selected-zone temperature or electron density differs from the current fixed solver assumptions (`T=1e6 K`, `ne=1e8 cm^-3`), rerun the solver at the selected XSTAR zone values before judging f/i/r, R, and G.

Latest package note: v0.3.115 is a source-code-first Mg XI / Ca XIX audit bookkeeping release. It does not tune scale factors or change default physics. It propagates collision-evaluator diagnostics into transition and full-global matrix products so future Mg/Ca solver outputs retain XSTAR type-63 record-order ans1/ans2 audit columns, legacy energy-order comparison columns, same-n l-mixing diagnostics, and type-67/type-68 effective-temperature-floor diagnostics. The Mg/Ca source-path audit now also classifies type-56 tabulated upsilon rows, which are important for Ca XIX.

Recommended next validation: rerun one Mg XI and one Ca XIX v0.3.115 solver case, then run `examples/49_mg_ca_triplet_source_path_audit.py` on those new output directories. Confirm that `mg_ca_triplet_source_path_detail.csv` now contains type-56 rows for Ca XIX and type-63 record-order audit columns for Mg XI when present.

### v0.3.119 He-like local-state validation

`examples/51_run_helike_local_state_validation.py` prepares C V, O VII, Mg XI, and Ca XIX solver runs using local XSTAR zone conditions read from `xout_abund1.fits`. It can write full-grid or selected-log-xi command scripts and optional comparisons against matching triplet target CSVs. This is a prerequisite step before judging Mg/Ca triplet discrepancies or row-level type-56/type-63/type-68/type-69 rates.
### v0.3.120 density-filtered local-state validation

`examples/51_run_helike_local_state_validation.py` can now prepare He-like solver runs at XSTAR `xout_abund1.fits` local states while filtering to a requested electron density:

```bash
PYTHONPATH=src python examples/51_run_helike_local_state_validation.py \
  --xstar-runs-root xstar_runs \
  --target-root xstar_atomic_v0.3.111_results \
  --atdb ../xstar/data/atdb.fits \
  --selection-mode grid \
  --log-xi 3 \
  --target-electron-density 1e8 \
  --out-dir helike_local_state_validation_v03120_logxi3_ne1e8 \
  --print-summary
```

The script does not fit triplet scale factors. It uses only matching ion-specific `xout_abund1.fits` directories for C V, O VII, Mg XI, and Ca XIX, and reports missing local state when no matching XSTAR run is available.

