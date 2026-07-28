## xstar_tools 0.6.48.10.2.1.1.2 qualifier-only closure

This release changes qualification only. It extends step-log normalization to the measurement-only accelerated-Python writer/finalization wall timers observed in the accepted 10.1.1 versus 10.2.1.1.1 fallback run. Runtime science and all three zone modes are unchanged.

## 0.6.48.10.2.1.1.1 qualifier-only hotfix

This release is qualification-only: the `python`, `cpp-all`, and `cpp-zone` runtime/science implementations are unchanged from 0.6.48.10.2.1.1. It corrects step-log science normalization so legacy measurement-only footer timers do not cause false rejection.

`--zone-backend` now accepts exactly `python`, `cpp-all`, and `cpp-zone`. `cpp-all` keeps the accepted one-call standalone-production trajectory. `cpp-zone` uses four sequential calls into a persistent native context running the same production controller, so no Python state reconstruction occurs between zones. `python` retains the 0.6.48.10.1.1 accelerated-Python trajectory.

# xstar_tools 0.6.48.10.2.1

This release redesigns `--zone-backend cpp-all` around the accepted standalone-production controller rather than a second reconstructed DSEC controller. The native zone library is compiled from `xstar_standalone.cpp` itself and calls the same `command_run_standalone_production_v67` used by `xstar_cpp run-production`. `--zone-backend python` remains the scientifically accepted 0.6.48.10.1.1 Python controller with modular C++ kernels.

For safety, the first shared-engine release gives C++ ownership of the complete radial trajectory (DSEC + accepted boundaries + STEP/TRNFRC + retained radial state) and native ProductWritingState. Python does not re-project native zone workspaces; it only provides parameters and updates FITS provenance headers.

# xstar_tools 0.6.48.10.1.1

0.6.48.10.1.1 corrects the narrow RRC science rejection in the 10.1 native final-zero-thickness bridge. The 10.1 bridge reduced the accelerated-Python terminal recompute from about 70.96 s to 9.87 s and the whole run from 562.07 s to 503.47 s, but its fresh native context leaked two source-inactive Mg II RRC slots into the final 1052-row inventory. 10.1.1 restores the retained source `mml/mmu` active-stage ownership before HEATT without changing any accepted native numerical kernel or the 10.0 C++ `binemis` promotion.

For Python runs explicitly selecting the C++ backend, the final zero-thickness source replay now uses `libxstar_final_recompute.so`, a thin bridge around the already-qualified native fixed-state engine. It replaces only `bremsmap -> calc_hmc_all -> calc_emisab_all -> calc_emis_all`; the existing HEATT/STPCUT handlers, final product writers, and 10.0 C++ `binemis` promotion remain in their accepted order. Pure Python is unchanged.

Use `XSTAR_V0648101_FORCE_PYTHON_FINAL_RECOMPUTE=1` to restore the accepted 10.0 Python terminal recompute for A/B qualification. The accelerated native bridge fails closed by default; `XSTAR_V0648101_ALLOW_PYTHON_FINAL_RECOMPUTE_FALLBACK=1` explicitly permits the slow fallback. Final thermal diagnostic sidecars retain the Python path.

Blocking host qualification is provided by `run_v0648101_python_accel_final_recompute.sh`. It runs both the native candidate and the forced-10.0 path from the same package, requires exact fallback reproduction of the accepted 10.0 products, checks bridge product/science closure, and reports the terminal recompute speedup.

## Historical standalone performance baseline

0.6.48.9.6 introduced the standalone-native Type50 hot-loop optimization built on the accepted 0.6.48.9.5.1 package; 0.6.48.9.7 then became the accepted standalone C++ performance baseline. The 9.5 prepared Type49/53 engine and 9.4.2 exact accepted-boundary ownership remain frozen.

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

