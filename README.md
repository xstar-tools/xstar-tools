## v68 general standalone C++ production

Build and run:

```bash
make -C src/xstar_tools/xstar/cpp -j1 xstar_cpp
src/xstar_tools/xstar/cpp/xstar_cpp run-production \
  --parameters parameters.json \
  --output-dir output
```

The default artifact profile is `none`: the output directory contains only nine FITS files and `xout_step.log`. The executable lowers the active ATDB records, derives product metadata, runs the controller, and retains product workspaces in memory. It does not accept external lowered-case, product-metadata, qualification-contract, checkpoint, or command-line ATDB assets.

`atdb.fits` is resolved in this order: `atomic_database`, `atomic_db`, or `atdb` in `parameters.json`; `atdb.fits` beside the parameter file; `XSTAR_ATOMIC_DB`; `XSTAR_ATDB_FITS`; `$XSTAR_DATA/atdb.fits`; `$XSTAR_HOME/data/atdb.fits`; executable-relative data directories; package-relative data; current-directory `atdb.fits`.

Use `--artifact-profile summary|failure|full` for diagnostics. Each artifact class can also be independently controlled with `--emit-*` or `--no-emit-*` switches for `lowered-case`, `runtime-metadata`, `checkpoints`, `audits`, `qualification-summaries`, `trajectory-diagnostics`, `benchmark-diagnostics`, and `timing-summary`.

The public path fails before publication if ATDB lowering, metadata derivation, controller convergence, accepted radial boundaries, or source workspaces are incomplete.

v68 reads both fixed-width packed FITS columns and production-style `P`/`Q` variable-length packed columns. POINTERS, REALS, INTEGERS, and CHARS are addressed as global logical vectors even when their payload is stored in the FITS heap or split across rows.

## v66 standalone production status

The public command is now `xstar_cpp run-production --parameters parameters.json --output-dir output`. It is fail-closed and creates no output directory until the C++ executable can derive the atomic program, product metadata, and controller trajectory internally. Use `xstar_cpp standalone-capabilities` to inspect readiness. The old asset-backed path is validation-only under `run-production-assets`.

# xstar_tools 0.6.48.7.46.25.5.17.25.63

This candidate fixes full-element-row versus compact-active-row population projection in line and bound-free spectral construction, restores the retained radial sequence `[58,59,60,61,60]`, and preserves v60's complete option-15 inventory and native `zrtmp` accumulator.

See `V048746255172561_ACTIVE_POPULATION_SPECTRAL_PROJECTION.md` and `V60_ORACLE_FITS_XOUT_STEP_COMPARISON_AND_V61_FIX.md`.

See `V04874625517255_SEQUENCE16_MG_RESIDUAL_CLOSURE.md` and `v25517255_sequence16_mg_residual_closure_report.md`.

## v17.25.4 sequence-16 contract classification

The generic resumable trajectory now classifies and accepts sequences 1–16. Sequence 16 retains the Mg stages 3–12 topology, uses a 17,028-row source-faithful thermal ledger, and adds an ion-budget-aware zero criterion for numerically negligible level-population rows. Sequence 17 remains fail-closed. ProductWritingState retention and public product publication remain disabled.

# xstar_tools 0.6.48.7.46.25.5.17.25.4

See `V04874625517254_SEQUENCE16_CONTRACT.md` and `v25517254_sequence16_contract_report.md`.
