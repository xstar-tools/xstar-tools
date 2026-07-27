# xstar_tools 0.6.48.9.6

0.6.48.9.6 is the standalone-native Type50 hot-loop optimization built on the accepted 0.6.48.9.5.1 package. The 9.5 prepared Type49/53 engine and 9.4.2 exact accepted-boundary ownership are frozen. The Type50 optimization is enabled only under the native standalone controller; Python source-port execution retains the 0.6.48.9.5.1 Type50 path. A same-executable `XSTAR_V064896_FORCE_LEGACY_TYPE50=1` mode is provided for blocking A/B qualification.

This release removes retired/version-stamped/Mg-specific Python audit code from the production `src/xstar_tools/xstar/` namespace. The Mg XI case remains under `src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8/` as the frozen benchmark. Current Mg-specific runtime conditions are **inventoried but not changed** in `docs/v0648951_element_z12_inventory.md`; testing/generalization for other elements is deferred until after the 9.6/9.7 speed work.

For cleanup/readiness checks use `tools/qualification/v0648951/check_readiness.py`. For a full host science requalification use `run_v0648951_cpp_against_reference.sh`; it reuses the accepted 9.5 Type49/53 A/B science gates.

Performance roadmap after this cleanup:

- **0.6.48.9.6** — Type50 hot-loop cleanup: remove no-op writes, preserve direct source-order `opakc` updates, and optimize the profile/rebin loop while requiring exact science equivalence. Target ~21.5–23 s.
- **0.6.48.9.7** — compact record state plus PGO/native tuning. Target ~20–22 s.

## v72 exact source-call boundaries

The canonical Mg XI benchmark uses four native DSEC call boundaries of 20, 1, 17, and 16 evaluations followed by four final evaluations; source positions 21, 40, and 57 are structural non-evaluation positions. The retained controller trajectory therefore has 54 DSEC plus four final evaluations = 58 real states. Early thermal convergence or stagnation no longer truncates a declared reference call boundary. General non-reference production runs remain naturally converged.

Publication remains fail-closed. The full-ATDB host run must pass the 61-event topology, the retained physical-content gate, and the external v63 cell-by-cell `.7e` comparator before v72 can be accepted.

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

### 0.6.48.9.5 performance candidate

The standalone C++ engine includes a prepared Type49/53 bound-free path. It caches immutable source-grid geometry, reuses the source-identical reduced-grid integral, and computes full-grid revisits only for source-selected records. The accepted 0.6.48.9.4.2 exact-boundary ownership remains frozen. Set `XSTAR_V064895_FORCE_LEGACY_BOUND_FREE=1` only for A/B qualification/debugging.

