# CHANGELOG

## 0.6.48.10.2.1.1.2 — Python writer-timing step-log normalization closure - 2026-07-28

- Qualifier-only hotfix; no controller, backend, numerical kernel, FITS writer, or zone-execution science changes.
- Closes the final Mg XI qualification false rejection by treating only the observed accelerated-Python wall-time records (`after writespectra`, top-level FITS/final recompute/product timers, `pprint_legacy`, and the legacy bare `total`) as measurement-only in normalized `xout_step.log` comparisons.
- Preserves non-timing writer ownership/count/status records and all physical science rows.
- Keeps `--zone-backend python|cpp-all|cpp-zone` unchanged.
- `mg11_ne1e8` is considered closed only after the authoritative Python fallback reproduces all nine 10.1.1 FITS payloads bit-exactly and the corrected normalized science log is identical.

## 0.6.48.10.2.1.1.1 — qualifier-only step-log normalization hotfix - 2026-07-28

- No science, controller, backend, FITS writer, or zone-execution changes.
- Fixes the 0.6.48.10.2.1.1 qualifier false rejection by treating the legacy
  `native_step_log_formatter` and `native_controller_and_fits` footer values as
  measurement-only timing fields when comparing step-log science content.
- Retains strict sensitivity to non-timing science-row changes.
- Keeps all three zone modes unchanged: `python`, `cpp-all`, and `cpp-zone`.
- The legacy `run_v064810211_python_zone_modes.sh` entry point redirects to the
  corrected 0.6.48.10.2.1.1.1 qualifier runner.

## 0.6.48.10.2.1.1 — persistent shared-production zone-by-zone backend - 2026-07-28

- Keeps the accepted 0.6.48.10.1.1 accelerated-Python controller as `--zone-backend python`.
- Keeps the 0.6.48.10.2.1 one-shot native trajectory as `--zone-backend cpp-all`.
- Adds `--zone-backend cpp-zone`: four sequential Python→C++ calls into one persistent native context.
- `cpp-zone` runs the same `command_run_standalone_production_v67` implementation as `cpp-all`; the controller stack, fixed-state context, transport/lifetime state, and product state remain native between zone calls.
- Adds a read-only per-zone result ABI (DSEC count, source sequence, temperature, electron fraction, hmctot/h-c, wall time).
- Fixes the 10.2.1 FITS bit-comparison qualifier by making float-column views contiguous before byte comparison.
- ABI: 604810211.

## 0.6.48.10.2.1 — shared standalone-production native zone engine - 2026-07-28

- Restarted from scientifically accepted 0.6.48.10.1.1; rejected 10.2.0/10.2.0.1 zone-controller reconstructions are not ancestry.
- Adds `--zone-backend python|cpp`; `python` is the untouched 10.1.1 radial controller fallback.
- `cpp` is deliberately implemented by a shared library built from the same `xstar_standalone.cpp` translation unit as the accepted standalone executable. It calls `command_run_standalone_production_v67` directly, so DSEC, active-stage/hydrogen lifetime, accepted-boundary recompute, STEP/TRNFRC, retained workspaces, terminal state, and native ProductWritingState have one implementation.
- The Python C++-zone path does not reconstruct native per-zone arrays. Python supplies normalized parameters and performs FITS header-only provenance projection after native publication. FITS data payloads remain native production payloads.
- Adds per-zone wall timing markers and ABI 60481021.
- Candidate-first host qualification requires all nine candidate FITS data payloads bit-exact to the accepted standalone C++ reference before running the expensive authoritative Python-zone fallback.

## 0.6.48.10.2.0.1 - 2026-07-28

- Correct the rejected 10.2.0 native-zone entry lifetime: seed the exact source/Python pre-matrix `mml/mmu` active-stage windows into the persistent C++ fixed-state context before DSEC evaluation 1.
- Preserve a legitimate zero neutral-H entry state; repeated native evaluations derive H I/H II from the preceding native H-ground population.
- Keep all accepted numerical kernels frozen; `fixed_state_engine.cpp` changes only by adding the active-stage state setter.
- Add candidate-first host preflight so a bad C++ zone candidate aborts before the expensive Python-zone fallback run.

## 0.6.48.10.2.0 — persistent native C++ single-zone DSEC backend - 2026-07-28

- Promote 0.6.48.10.1.1 as the scientific baseline: all nine FITS data payloads reproduce accepted 10.0 exactly, the 1052-row RRC inventory is restored, and public science closure is ACCEPT. Its 10.340630 s terminal recompute missed the historical <=10 s performance target by 0.340630 s only; that timing threshold is non-scientific and is not carried forward as a baseline rejection.
- Add `--zone-backend {python,cpp}`. `python` retains the accepted 10.1.1 Python-orchestrated DSEC path. `cpp` moves one complete DSEC convergence call for each physical radial shell behind one persistent native C++ context while Python keeps the accepted post-DSEC boundary calculation, transport/STEP/TRNFRC, final recompute, and writers.
- Reuse the qualified native fixed-state and thermal DSEC engines rather than introducing new numerical kernels. The qualified Mg XI source inventory remains 20/1/17/16 DSEC evaluations with structural source positions 21/40/57 omitted.
- Keep native global `xilevg`, `bilevg`, and `rnisg` state inside each zone call and persist hidden source-lifetime state across zones. Mirror source boundary identities 58-61 internally after each DSEC solve solely to synchronize native repeated-H/active-stage lifetime before the next zone; Python still owns/publishes the boundary evaluation.
- In this first milestone, `--zone-backend cpp` is fail-closed unless the active ATDB subset and the complete modular C++ backend set are selected. Mixed Python/C++ boundary configurations are intentionally unqualified.
- Add exact per-zone wall timing so qualification reports measured zone 1-4 times rather than estimating them from DSEC counts.
- Freeze 10.1.1 final-recompute/RRC ownership, 10.0 C++ `binemis`, Type49/53/50, thermal, matrix/rate, and writer science sources by SHA-256.
- Qualification requires `--zone-backend python` to reproduce the 10.1.1 reference exactly, the native-zone path to retain 20/1/17/16 DSEC topology and all public products within the existing <=1% science gate, and the existing structural/detal4/spectrum analyzers to pass. A <=120 s four-zone total is reported as a performance target but is not allowed to override scientific correctness.

## 0.6.48.10.1.1 — terminal active-stage/RRC ownership correction - 2026-07-28

- Start from the 0.6.48.10.1 native final-recompute candidate, retaining its measured 70.962107 s -> 9.871208 s terminal speedup and the accepted 0.6.48.10.0 C++ `binemis` promotion.
- Correct the 10.1 science rejection in `xout_rrc1.fits`: the fresh native final-recompute context widened the terminal spectral ion-stage window and leaked two source-inactive Mg II RRC slots into the final writer, yielding 1054 rows instead of the accepted 1052.
- Restore source ownership generically from the live retained Python `calc_hmc_all.mml/mmu` stage limits. Decode continuum and line slots through the immutable derived pointer tables; clear only `calc_emisab` (`cemab/cabab/opakab`) and `calc_emis` (`rcem/oplin`) slots whose parent ion is outside the retained source stage window before HEATT consumes the native workspaces.
- Do not hard-code continuum indices 7062/7064 or Mg specifically. Benchmark attribution verifies those rejected slots are Mg II stage 2 while the retained Mg window is stages 3-12 and neighboring accepted Mg III slots remain active.
- Freeze the 10.1 native fixed-state engine, final-recompute C++ bridge, Type49/53/50 kernels, thermal kernels, and accepted 10.0 `binemis` implementation by SHA-256. No native numerical kernel changes in this correction.
- Qualification requires the forced-10.0 fallback to remain all-nine-FITS data-bit-exact, the corrected accelerated candidate to reproduce all nine accepted 10.0 FITS data payloads exactly (including 1052-row `xout_rrc1`), the long-lived public structural gate to pass, and final recompute runtime to remain <=10 s.

## 0.6.48.10.1 — accelerated-Python native final zero-thickness recompute bridge - 2026-07-27

- Promote the accepted 0.6.48.10.0 accelerated-Python result (562.066443 s total; final C++ `binemis` 0.817192 s, all qualification gates ACCEPT) and freeze its zone/controller computation plus the promoted C++ `binemis` implementation by SHA-256.
- Replace only the final source-order zero-thickness `bremsmap -> calc_hmc_all -> calc_emisab_all -> calc_emis_all` replay in accelerated C++-backend Python with a native fixed-state bridge. The bridge reuses the already-qualified C++ fixed-state engine; it does not introduce a second physics implementation.
- Transfer the live terminal Python state needed by the source calculation: high-resolution radiation, live `bremsa`, source RRC optical-depth workspace (`tauc`), runtime line optical depths, trial temperature/electron fraction/density, abundances, turbulence, covering fractions, and retained global level workspaces.
- Project the native source workspaces (`rcem`, `oplin`, `cemab`, `cabab`, `opakab`, `rccemis`, `opakc`, `opakcont`, `fline`, `flinel`, `brcems`) back into the existing Python `RadialTransferWorkspace`, then run the already-active HEATT and STPCUT source handlers in their original order.
- Pure Python remains unchanged. `XSTAR_V0648101_FORCE_PYTHON_FINAL_RECOMPUTE=1` restores the accepted 10.0 Python terminal recompute; native bridge failure is fail-closed unless `XSTAR_V0648101_ALLOW_PYTHON_FINAL_RECOMPUTE_FALLBACK=1` is explicitly set. Final-thermal sidecar diagnostics intentionally retain the Python path.
- Add blocking host qualification that requires the forced-10.0 fallback to reproduce all nine accepted 10.0 FITS payloads exactly, pre-terminal detail products to remain bit-exact under the bridge, final public products to stay within 1% of accepted 10.0, external spectrum closure against FORTRAN/pure-Python/C++ references, and final recompute time <=10 s (<=5 s reported as the intended few-second target).
- Target: reduce accepted 10.0 `final_local_recompute` from 70.962107 s to a few seconds without changing the accepted 10.0 zone trajectory or final `binemis` promotion.

## 0.6.48.10.0 — accelerated-Python final binemis C++ product promotion - 2026-07-27

- Start from the accepted 0.6.48.9.7 source and freeze all zone/controller science plus the native standalone `binemis` implementation by SHA-256.
- When the Python source-port explicitly selects `--backend cpp` or `--emissivity-backend cpp`, automatically promote the existing native C++ final `binemis` product implementation instead of executing the ~255 s Python profile/rebin loop.
- Pure-Python runs remain on the validated Python `binemis` implementation. `XSTAR_V064810_FORCE_PYTHON_BINEMIS=1` provides a same-package fallback/A-B switch.
- Accelerated C++ product selection fails closed if the native writer library is unavailable. `XSTAR_V064810_ALLOW_PYTHON_BINEMIS_FALLBACK=1` permits an explicit slow fallback when desired.
- Do not change the accepted C++ `line_emissivity.cpp` kernel or its Python ctypes bridge; both are source-hash identical to 0.6.48.9.7. This release changes product-backend policy only.
- Qualification requires all eight unaffected FITS products and the scientific `xout_step.log` to remain exact against the accepted accelerated-Python 0.6.48.9.5.1 reference; `xout_spect1` must retain zero >1% residuals against FORTRAN, pure Python, accelerated Python, and accepted standalone C++.
- The accepted accelerated-Python reference spends 254.812423 s in `final_product_build.spectrum.binemis_profile_seconds`; 10.0 targets <=5 s integration time for the promoted bridge, with ~1 s as the expected host result.

## 0.6.48.9.7 — quiet production path, compact DSEC provenance, PGO/native evaluation - 2026-07-27

- Freeze the accepted 0.6.48.9.6 Type50 implementation and all 9.5 Type49/53, 9.4.2 boundary, thermal, and writer science-critical sources by SHA-256.
- Add a production-quiet standalone controller stream: historical controller attribution/status chatter is suppressed by default but restored exactly with `XSTAR_V064897_VERBOSE_CONTROLLER_DIAGNOSTICS=1` for qualification. Product and science state never consume stdout.
- Split hot runtime evaluation from cold retained record provenance on ordinary deferred DSEC evaluations. The 54 projection-deferred DSEC calls no longer copy the full `EvaluatedRecord` shadow payload into `last_record_diagnostics`; exact boundary/final evaluations retain the complete product-diagnostic state unchanged.
- Add `XSTAR_V064897_FORCE_096_RECORD_PROVENANCE=1` as a same-executable fallback that restores the 0.6.48.9.6 all-evaluation provenance retention for blocking A/B qualification. General fixed-state-library behavior outside native standalone production is unchanged.
- Add opt-in PGO build controls (`V064897_PGO_MODE=generate|use`, `V064897_PROFILE_DIR=...`) and optional `V064897_NATIVE=1` (`-march=native`) evaluation. `-ffast-math` is rejected and source-critical `-ffp-contract=off` flags remain in force.
- PGO/native compiler variants are evaluation-only until their host runs are byte-exact against the accepted 0.6.48.9.6 nine-FITS payloads and scientific `xout_step.log`; the faster exact variant may then be promoted.
- Add 9.7 readiness, quiet/compact-vs-9.6 qualification, three-run performance, and PGO/native evaluation runners.

## 0.6.48.9.6 — standalone Type50 hot-loop optimization - 2026-07-27

- Build directly on the accepted 0.6.48.9.5.1 package; freeze the 9.5 prepared Type49/53 bound-free engine and 9.4.2 exact accepted-boundary recomputation by source hash.
- Optimize only the standalone-native full-profile Type50 opacity path. Python source-port execution, including modular C++ backends, retains the 0.6.48.9.5.1 Type50 implementation.
- Remove the full-profile `rccemis += 0.0` provenance-era stores; literal `linopac.f90` does not modify `rccemis` when `lfast <= 2`.
- Replace the defensive positive/finite `opakc` reload with the literal source-order `opakc += optp2` update on the validated production continuum workspace.
- Fuse source-identical temporary-grid profile evaluation with the later monotonic rebin consumer instead of materializing/re-reading two 20,000-point temporary planes. The historically inert `ldon` early-stop semantics remain inert.
- Replace `float(integer)->double` conversions for Type50 temporary-grid indices and `ncut` with direct integer-to-double conversions only where the integer magnitude is <=20,000 and therefore exactly representable in binary32 and binary64.
- Specialize the common `0 < a <= 0.2` Voigt branch while preserving the exact arithmetic association of `voigte.f90`.
- Add `XSTAR_V064896_FORCE_LEGACY_TYPE50=1` for same-executable blocking A/B qualification against the frozen 9.5.1 Type50 implementation.
- Add 9.6 readiness, randomized bit-exact kernel qualification, nine-FITS payload comparator, four-reference hash verification, full science runner, and performance runner.
- Local randomized qualification: 800 profiles bit-exact, full-profile `rccemis` unchanged, Python/non-standalone mode identical to 9.5.1, representative micro-kernel speedup ~1.44x. Host Mg XI qualification remains required before promotion.

## 0.6.48.9.5.1 — element-generality/package cleanup - 2026-07-27

- Freeze 0.6.48.9.5 as the accepted prepared Type49/53 production/science baseline.
- Retire 112 historical/version-stamped/Mg-specific audit and capture modules from `src/xstar_tools/xstar/`; none are reachable from the production `driver`/`physical_runner`/`standalone` roots.
- Retire 68 tests tied exclusively to those modules and remove 13 obsolete historical console entry points.
- Remove checked-in generated `src/xstar_tools.egg-info/` metadata.
- Keep the Mg XI `v0648_compiled_case_helike_type69_mg11_ne1e8` case as a benchmark/qualification fixture, not runtime architecture.
- Inventory every current Python/C++ equality/inequality comparison against `element_z == 12`/`!= 12` without changing those runtime branches; multi-element generalization/testing is deferred until after speed work.
- Freeze the accepted 9.5 Type49/53 prepared engine, 9.4.2 exact-boundary ownership, and 9.3 Type50 fast path by source hash.
- No intended physics, numerical algorithm, controller topology, FITS science, or standalone-C++ performance change.
- Next planned work remains 9.6 Type50 hot-loop cleanup, followed by 9.7 compact record state / PGO/native tuning.

## 0.6.48.9.5 — prepared Type49/53 bound-free engine - 2026-07-27

- Freeze the accepted 0.6.48.9.4.2 exact-boundary production contract.
- Prepare immutable Type49/53 `phint53` grid geometry (`sgbar`, threshold mapping, Type49 phextrap metadata) once per record/grid and retain it in the fixed-state context.
- Reuse the first reduced 999-bin Type49/53 integral for the source-identical `calc_emisab` caller instead of integrating the same workspace twice.
- Defer the 9999-bin `calc_emis` Type49/53 integral until the existing source `rlbin`/`ncbin` selection proves that the record is actually consumed.
- Add `XSTAR_V064895_FORCE_LEGACY_BOUND_FREE=1` for same-executable eager-vs-prepared A/B qualification.
- Add measurement-only prepared-bound-free workload counters and 9.5 qualification/performance runners.
- No Type50, boundary, thermal, matrix, FITS writer, or Python-science changes.

## 0.6.48.9.4.2 - 2026-07-27

- Correctness-only rollback after 0.6.48.9.4 and 0.6.48.9.4.1 boundary-reuse experiments failed byte-exact product equivalence.
- Restores the accepted 0.6.48.9.3 exact accepted-boundary recomputation as the production/default path.
- Restores projection-deferred behavior for all 54 DSEC evaluations in production; terminal-DSEC full projection is no longer implicit.
- Keeps boundary reuse available only with `XSTAR_V0648942_EXPERIMENTAL_BOUNDARY_REUSE=1` for focused diagnostics.
- Retains the accepted 0.6.48.9.3 Type50 fast path and the 0.6.48.9.4 traversal/rate hot-path preparation unchanged.
- Qualification compares the default production boundary path with explicitly forced legacy recomputation and requires all nine FITS data payloads plus scientific `xout_step.log` content to match.
- `rccemis_attribution/` remains disabled by default; the native product-state footer remains debug-only.

## 0.6.48.9.4.1 - 2026-07-27

- Correct the rejected 0.6.48.9.4 accepted-boundary reuse path.  The 9.4 prototype reused an ordinary deferred DSEC workspace, so `calc_emis_all` selected bound-free/RRC publication and writer-facing line-emission projection were absent; `opakcont` therefore collapsed to zero and option-17 `log(tau)`/thermal rows changed.
- Preserve the boundary-speedup design without reconstructing deferred products: for the canonical 20/1/17/16 trajectory, run the normal non-deferred product projection on only the four terminal DSEC evaluations, then reuse those exact completed workspaces at the accepted boundaries.  Earlier DSEC evaluations remain deferred and generic trajectories fall back to the legacy boundary recomputation.
- Require blocking A/B equality against forced legacy boundary recomputation for all nine FITS data payloads and non-timing `xout_step.log` science content, which includes the source-style option-17 radial rows.
- Retain the 0.6.48.9.4 traversal-order prevalidation and rate evaluation-context hoist; do not change rate formulas, Type50 arithmetic, thermal kernels, or FITS writer science.
- Disable the extra ProductWritingState/native product-surface diagnostic footer in `xout_step.log` by default.  Re-enable it only for debugging with `XSTAR_DEBUG_PRODUCT_STATE_SUMMARY=1`.
- Disable `rccemis_attribution/` in routine qualification.  Re-enable the historical Type99/RRC record attribution only with `XSTAR_ENABLE_RCCEMIS_ATTRIBUTION=1`; the default Type99 gate is product-only and still requires C++/FORTRAN and C++/Python inward-emission closure plus zero first bins.

## 0.6.48.9.4 - 2026-07-27

- Reuse the exact final accepted DSEC source workspace at each of the four controller-call product boundaries instead of rerunning the complete fixed-state engine solely to reconstruct the same local science state.
- Retain the exact sparse line/RRC/continuum/line-profile workspaces in the fixed-state context and promote them into the accepted boundary only after the controller accepts the final DSEC state.
- Preserve caller-owned cumulative radial state (`tau0`, `tauc`, continuum depth, line/RRC luminosity, `zrems`, and global population state) in the same post-DSEC boundary finalization order.
- Keep an environment-controlled legacy boundary-recompute path and add a blocking A/B qualifier requiring all nine FITS data payloads and the non-timing `xout_step.log` science content to be bit-identical between reuse and legacy paths.
- Keep the terminal zero-thickness final evaluation as a real fixed-state evaluation; only the four accepted call boundaries are reused.
- Prepare the traversal/rate hot path by prevalidating immutable linked-record order once per fixed-state context and hoisting temperature/electron-density/reduced-continuum rate inputs once per fixed-state evaluation rather than rebuilding them per atomic record.
- Retain the accepted 0.6.48.9.3 Type50 fast path unchanged.  The accepted 9.3 three-run baselines are 32.724905 s total, 31.498506 s controller, 4.209864 s accepted-boundary projection, 10.628351 s fixed traversal, and 9.553384 s nested rate evaluation.

## 0.6.48.9.3 - 2026-07-27

- First standalone-C++ Type50 profile-kernel optimization after the accepted 0.6.48.9.2 measurement series.
- Preserve strict source-real/source-order numerical semantics while removing redundant volatile store/load barriers on `FLT_EVAL_METHOD==0` targets; retain the historical barrier implementation automatically on excess-precision targets.
- Keep `-ffp-contract=off` for the opacity translation and fail compilation under `-ffast-math`.
- Reuse per-thread 20,000-point Type50 temporary-grid scratch storage instead of allocating and zero-filling two large vectors for every line profile.
- Add a compile-time legacy-barrier A/B equivalence check that builds both paths and requires bit-exact profile outputs before host qualification.
- Freeze all non-opacity science files to the accepted 0.6.48.9.2.1 hashes and retain the complete FORTRAN / accelerated-Python product gates.
- Compare performance against the accepted 0.6.48.9.2 three-run medians: 82.976367 s total and 56.417535 s Type50 profile-kernel time.

## 0.6.48.9.2.1 - 2026-07-27

- Packaging/cleanup hotfix based on the accepted 0.6.48.9.2 measurement baseline; no physics or numerical algorithm changes.
- Remove historical root material already retired by the 9.2 cleanup and prune benchmark fixtures that were used only by obsolete internal tests/regression snapshots.
- Keep benchmark/oracle directories that still back active source-port regression gates, public audit commands, current C++ self-tests, or diagnostic/reference fallbacks.
- Remove orphaned tests/modules tied exclusively to the deleted benchmark snapshots and rewrite `pyproject.toml` benchmark package-data to match the retained runtime surface.
- Preserve the 0.6.48.9.2 qualification/performance runner set and the accepted Type50 hotspot attribution.
- Reserve 0.6.48.9.3 for the first Type50 profile-kernel optimization.

## 0.6.48.9.1 - 2026-07-27

- Measurement-only fixed-state spectral decomposition; no intended science change.
- Keeps `xstar_fixed_state_stats_v1` unchanged and adds a separate diagnostic-only spectral timing ABI.
- Splits repeated spectral work into setup, seed generation, broad contribution application/opacity, rank-selection, selected line replay, fixed-state binemis, selected RRC replay, publication/combine, source-workspace retention, final combine, and residual teardown.
- Freezes 0.6.48.9.0 as the performance baseline and continues to reuse the frozen 0.6.48.8.2 accelerated-Python reference and canonical FORTRAN oracle.

## 0.6.48.9.0 - 2026-07-26

- Start the 0.6.48.9 performance branch from the closed 0.6.48.8.3.1 science baseline.
- Add measurement-only standalone-C++ timing for ATDB lowering, controller calls, fixed-state traversal/rates/continuum/spectral phases, boundary projection, final zero-thickness recomputation, product-state construction, writer-time `binemis`, FITS publication, and total coverage.
- Establish a stable ~84.8 s three-run measurement baseline on the qualification host.
- Disprove the initial writer-time `binemis` regression hypothesis: `binemis` is only about 0.32 s, while fixed-state spectral work is roughly 57.7 s and dominates runtime.
- Preserve all 0.6.48.8.3.1 science gates and frozen Python/FORTRAN references.

## 0.6.48.8.3.1 - 2026-07-26

- Qualification-only hotfix for the final standalone thermal-state closure; runtime/science implementation is identical to 0.6.48.8.3.
- Make final-workspace hashes diagnostic-only and qualify final T4/HTTOT/CLTOT/HMCTOT by source-parity thresholds.
- Retain C++/FORTRAN HMCTOT error near 0.00617%, well below the 0.05% acceptance threshold and far below the previous ~0.358% discrepancy.
- Freeze this release as the closed 0.6.48.8 science baseline for subsequent performance development.

## 0.6.48.8.3 - 2026-07-26

- Correct standalone final zero-thickness `bremsa` lifetime to match literal XSTAR: preserve the terminal shell-entry DSEC radiation workspace rather than reusing an extra projected next-radius workspace before the final `xstarcalc`.
- Apply the retained shell-entry `bremsa` to both final pprint DSEC state and final call-start workspace.
- Reduce standalone C++ final HMCTOT error versus FORTRAN from roughly 0.358% to about 0.00617% without changing Python science or the 58-evaluation trajectory.

## 0.6.48.8.2 - 2026-07-26

- Correct writer-time Type50 `binemis.f90` terminal boundary/rebin semantics using compact boundary-event reconstruction while preserving the source-declared far-wing reach and terminal overwrite behavior.
- Close the remaining 18 shared Python/C++ versus FORTRAN `xout_spect1.emit_outward` cells above 1%.
- Preserve the fully closed `xo01_detal4` Type50 opacity/depth result and the existing Type99/RRC source-zero closure.
- Retain approximately 11.48 million source-faithful far boundary-event writes; later performance measurement showed these writes are not the dominant runtime cost.

## 0.6.48.8.1 - 2026-07-26

- Correct literal `voigte.f90` control flow for Type-50 line profiles: the `a+v>3.2` asymptotic test is now reachable only when `a>0.2`, as in the source labels.
- Apply the same source nesting to pure-Python scalar/vector profiles, qualification profile code, accelerated C++ kernels, and standalone-C++ opacity.
- Add a strict Type-50 edge closure analyzer and one-time pure-Python / accelerated-Python / standalone-C++ qualification runner.
- Preserve the 0.6.48.8 production/controller, source-real energy-grid, Type99 source-zero, writer, and standalone-progress contracts.

## 0.6.48.8 - 2026-07-26

- Promote the accepted v82 patch5.20.17 production path to the 0.6.48.8 baseline.
- Retain source-REAL `ener.f90` grid semantics in pure Python, accelerated Python, and standalone C++.
- Close the shared ~3.08 keV continuum residual family: `emis in`, `zrems(3)`, and `zrems(5)` are zero above 1% versus FORTRAN in the qualification case.
- Treat historical Type99 record-67 selection as diagnostic-only after the source-grid change; production closure requires every selected Type99/rate7 direct `rccemis` delta to remain zero.
- Add FORTRAN/Python-style standalone C++ terminal progress rows, writer progress messages, and total runtime reporting.
- Clarify trajectory accounting: 61 source sequence positions, 3 structural non-evaluation positions (21,40,57), and 58 retained controller evaluations (54 DSEC + 4 finals).
- Keep diagnostic/attribution sidecars disabled by default in production and product publication gated on the complete accepted trajectory.
- Establish standalone C++ as the routine benchmark/development target; accepted accelerated-Python products are the reusable reference until Python behavior changes.

## v82 patch 5.20.17.3.11 — source-REAL `ener.f90` grid correction

- Apply the 5.20.17.3.10 residual attribution without special-casing any watched atomic record or FITS energy.
- Reproduce `ener.f90` arithmetic kinds exactly: default-REAL literals (`0.1`, `4.e+5`, `1.`, `1.e+6`) and `1./float(...)` are evaluated in binary32 before promotion to the REAL(8) grid.
- Use the same source-REAL grid contract in Python, standalone C++, and both C++ 999-bin reduced source workspaces.
- Preserve the accepted 5.20.17.3.9 Type99 selected-RRC source-zero correction and the 5.20.17.3.7 zero-width GSSMOOTH/opacity ownership correction.
- Regenerate Python products because the shared source grid changes; the fast Python+C++ backend is the first qualification surface, followed by pure-Python canonical regeneration if accepted.
- Require all six watched residual energies to match the FORTRAN float32 grid exactly, C++/Python grid identity, C++/Python `xo01_detal4` parity, and no worsening of the 5.20.17.3.9 residual counts.

## v82 patch 5.20.17.3.9 — Type99 selected-RRC source-zero closure

- Close the five remaining C++-only `xo01_detal4.emis in` first-bin cells attributed by 5.20.17.3.8.1 to source position 128 / record 67 / Type99 rate7 / H I.
- Preserve Type99 rate-7 ranking and scalar `calt99 -> phint53hunt` rate/thermal evaluation, but suppress the source-nonexistent selected Type99 direct `rccemis` profile.
- Remove the legacy synthetic Type99 inward continuum generator from the selected-RRC helper so Type99 remains source-zero even if the helper is called from another path.
- Retain the accepted 5.20.17.3.7 zero-width GSSMOOTH/opacity correction, all Type49/53/88/76 physics, transport, and FITS writer projection unchanged.
- Reuse the accepted 5.20.17.3.6.1 Python+CPP products; no Python rerun is required.

## v82 patch 5.20.17.3.6 — Python FITS header/provenance parity

- Synchronize Python runtime `__version__` with package/C++ release `0.6.48.7.46.25.5.17.25.82`.
- Add backend-aware primary FITS provenance for pure Python and Python with C++ kernels.
- Mirror C++ primary metadata/comments (`MODEL`, `ATDATA`, `TAUMODE`, `DATE`, standard FITS comments) while using Python-specific `CREATOR`, `ORIGIN`, `DATAMODE`, and `RUNID`.
- Add source comments and `STATESRC` to Python radial extensions.
- Recompute `CHECKSUM`/`DATASUM` after all byte-level FITS padding edits, including `xout_abund1.fits`.
- Scientific arrays, C++ physics, bound-free ownership, transport, and Type50 profile physics remain frozen.

## v82 patch 5.20.17.3.4

- Add diagnostic-only Python/C++ selected-line profile producer attribution at Python `calc_emis_all` call 2 and C++ source sequence 59.
- Replay selected-line producers onto private zero opacity planes and compare producer identity/scalars, profile support/shape hashes, aggregate selected-line opacity, continuum-before-line opacity, and combined opacity.
- Keep the rejected 5.20.17.3.3 production physics unchanged and require its exact 13714/8220 Python and 33/9/15 C++ `detal4` baseline during host attribution.
- Do not promote a new canonical pure-Python reference; the pure-Python run is diagnostic producer capture only.

## v82 patch 5.20.17.3.3

- Split Python selected line-profile opacity from the shared continuum `opakc` accumulator during `calc_emis_all`.
- Route ordinary, C++-accelerated Type-50, and native spectral selected-line paths into the retained line-profile plane.
- Merge the complete line-profile plane into `opakc` exactly once after `freef`/`bremem`, matching the accepted C++ ownership/lifetime model.
- Keep C++, bound-free Type49/53/88 physics, `stpcut`/radial transport, and FITS writer code frozen by readiness hashes.
- Require a fresh canonical pure-Python reference for host qualification.

## v82 patch 5.20.17.3.2.1

- Fix diagnostic-only Python bound-free attribution gate: top-level `calc_emis_all` call 2 corresponds to stable source sequence 59; patch 5.20.17.3.2 incorrectly used call 23.
- Keep C++ attribution gated on source sequence 59.
- No production physics, transport, STPCUT, or FITS-writer changes.

## v82 patch 5.20.17.3 — cross-backend detal4 parity closure

- Python Type-50 `linopac` now preserves FORTRAN default-REAL literal/conversion semantics using shared historical constants and binary32 promotion.
- Python `voigte` now preserves source default-REAL DATA/PARAMETER/branch literals.
- C++ HDU1 inward `rccemis(2,:)` now uses the stable second zero-depth owner.
- Removed the source-nonexistent C++ Type-99 synthetic direct inward-RRC publication while preserving scalar rate/thermal evaluation.
- Requires a newly regenerated canonical pure-Python reference archive.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3.11 — source-REAL `ener.f90` grid correction

- Apply the 5.20.17.3.10 residual attribution without special-casing any watched atomic record or FITS energy.
- Reproduce `ener.f90` arithmetic kinds exactly: default-REAL literals (`0.1`, `4.e+5`, `1.`, `1.e+6`) and `1./float(...)` are evaluated in binary32 before promotion to the REAL(8) grid.
- Use the same source-REAL grid contract in Python, standalone C++, and both C++ 999-bin reduced source workspaces.
- Preserve the accepted 5.20.17.3.9 Type99 selected-RRC source-zero correction and the 5.20.17.3.7 zero-width GSSMOOTH/opacity ownership correction.
- Regenerate Python products because the shared source grid changes; the fast Python+C++ backend is the first qualification surface, followed by pure-Python canonical regeneration if accepted.
- Require all six watched residual energies to match the FORTRAN float32 grid exactly, C++/Python grid identity, C++/Python `xo01_detal4` parity, and no worsening of the 5.20.17.3.9 residual counts.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3.9 — Type99 selected-RRC source-zero closure

- Close the five remaining C++-only `xo01_detal4.emis in` first-bin cells attributed by 5.20.17.3.8.1 to source position 128 / record 67 / Type99 rate7 / H I.
- Preserve Type99 rate-7 ranking and scalar `calt99 -> phint53hunt` rate/thermal evaluation, but suppress the source-nonexistent selected Type99 direct `rccemis` profile.
- Remove the legacy synthetic Type99 inward continuum generator from the selected-RRC helper so Type99 remains source-zero even if the helper is called from another path.
- Retain the accepted 5.20.17.3.7 zero-width GSSMOOTH/opacity correction, all Type49/53/88/76 physics, transport, and FITS writer projection unchanged.
- Reuse the accepted 5.20.17.3.6.1 Python+CPP products; no Python rerun is required.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3.6 — Python FITS header/provenance parity

- Synchronize Python runtime `__version__` with package/C++ release `0.6.48.7.46.25.5.17.25.82`.
- Add backend-aware primary FITS provenance for pure Python and Python with C++ kernels.
- Mirror C++ primary metadata/comments (`MODEL`, `ATDATA`, `TAUMODE`, `DATE`, standard FITS comments) while using Python-specific `CREATOR`, `ORIGIN`, `DATAMODE`, and `RUNID`.
- Add source comments and `STATESRC` to Python radial extensions.
- Recompute `CHECKSUM`/`DATASUM` after all byte-level FITS padding edits, including `xout_abund1.fits`.
- Scientific arrays, C++ physics, bound-free ownership, transport, and Type50 profile physics remain frozen.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3.4

- Add diagnostic-only Python/C++ selected-line profile producer attribution at Python `calc_emis_all` call 2 and C++ source sequence 59.
- Replay selected-line producers onto private zero opacity planes and compare producer identity/scalars, profile support/shape hashes, aggregate selected-line opacity, continuum-before-line opacity, and combined opacity.
- Keep the rejected 5.20.17.3.3 production physics unchanged and require its exact 13714/8220 Python and 33/9/15 C++ `detal4` baseline during host attribution.
- Do not promote a new canonical pure-Python reference; the pure-Python run is diagnostic producer capture only.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3.3

- Split Python selected line-profile opacity from the shared continuum `opakc` accumulator during `calc_emis_all`.
- Route ordinary, C++-accelerated Type-50, and native spectral selected-line paths into the retained line-profile plane.
- Merge the complete line-profile plane into `opakc` exactly once after `freef`/`bremem`, matching the accepted C++ ownership/lifetime model.
- Keep C++, bound-free Type49/53/88 physics, `stpcut`/radial transport, and FITS writer code frozen by readiness hashes.
- Require a fresh canonical pure-Python reference for host qualification.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3.2.1

- Fix diagnostic-only Python bound-free attribution gate: top-level `calc_emis_all` call 2 corresponds to stable source sequence 59; patch 5.20.17.3.2 incorrectly used call 23.
- Keep C++ attribution gated on source sequence 59.
- No production physics, transport, STPCUT, or FITS-writer changes.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.3 — cross-backend detal4 parity closure

- Python Type-50 `linopac` now preserves FORTRAN default-REAL literal/conversion semantics using shared historical constants and binary32 promotion.
- Python `voigte` now preserves source default-REAL DATA/PARAMETER/branch literals.
- C++ HDU1 inward `rccemis(2,:)` now uses the stable second zero-depth owner.
- Removed the source-nonexistent C++ Type-99 synthetic direct inward-RRC publication while preserving scalar rate/thermal evaluation.
- Requires a newly regenerated canonical pure-Python reference archive.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.17.1 — live product-workspace retention hotfix

- Preserve the accepted 5.20.17 sequence-23 native committed-state and 58-evaluation production trajectory.
- Fix the latent standalone product-state completeness rejection by retaining caller-owned `zrems` and `zremsz` on every accepted radial boundary together with `dpthc`/`dpthcont`.
- Keep `ExactSourceWorkspaceState::complete()` and the product publication fail-closed gate unchanged; this hotfix restores the missing live state instead of relaxing completeness.
- Fail closed if the retained `zrems`/`zremsz` shapes disagree with the live continuum grid.
- Add explicit five-zone source-workspace completeness diagnostics and a host gate that requires all ten public products before running the inherited broad/frozen product qualification.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.15.2.1 — clean 5.20.15.1 restart; C++ publication closure only

- Reverts/discards every Python-physics change from the rejected 5.20.15.2 experiment. Python scientific modules are byte-identical to 5.20.15.1.
- Retains the accepted 5.20.15.1 Type49 metadata-cache/tauc correction and sparse 20/1/17/16, 58-state cache contract.
- C++ native xo01_detail LTE publication bypasses the Python compatibility bridge and reads the retained native/source LTE state.
- C++ xo01_detal3 RRC emission no longer indexes compact cemab with sparse source-continuum indices.
- Public line optical depths use terminal cumulative tau0 while luminosities retain the final physical-shell elum owner.
- Python reference/cache regeneration is NOT required; 5.20.15.1 reference artifacts are the canonical inputs for this C++-publication-only patch.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.14.6 — retained writer schema and literal binemis scratch ownership

- construct the retained native ProductWritingState schema for diagnostic full-trajectory products, so `xout_spect1` actually consumes writer-time `binemis` and terminal full `dpthc`;
- give diagnostic publication a private writable native-product bridge instead of silently falling back to terminal-zone arrays;
- make the public-spectrum fallback source-faithful: `writespectra` uses `dpthc(1)` and `zrems(2:3)`, while `writespectra3` uses `dpthcont(1)` and `zrems(4:5)`;
- restore the literal 20000-point `binemis` temporary-profile scratch capacity in the Python output writer and retain the same capacity in C++;
- reproduce default-REAL `1.e-15` and `1.e-6` binemis gate literals in C++;
- preserve the accepted all-shell full-grid `calc_emis`, RRC depth, HEATT/pprint/STPCUT ordering, Type50/lines, populations, and sparse 58-state trajectory.

Python **product** reference regeneration is required because writer-time `binemis` changes; the solve-stage cache is unchanged.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.14.5 — HEATT/pprint/STPCUT and writer lifetime

- Retained the successful all-shell full-grid bound-free revisit from 5.20.14.4.
- Split current-shell HEATT luminosity/continuum work from post-pprint STPCUT depth accumulation.
- Retained detail/option-17 boundaries after HEATT but before current-shell depth accumulation.
- Seeded final zero-thickness writer HEATT from the terminal transported zrems state.
- Restored source HEATT radial line-luminosity ownership for public lines and writer-time binemis.
- Added strict option-17 and detailed-continuum host gates.
- Python/reference physics unchanged; patch5.20.14.3 cache/reference remain reusable.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.14.4 — all-shell `calc_emis`, radial detail lifetime, final writer state

- Apply the selected full 9999-bin Type49/53 `calc_emis` scalar-opacity revisit on every accepted shell instead of only call 2; keep Type53 matrix/rate physics on the accepted reduced 999-bin caller grid.
- Retain four radial detail snapshots before STPCUT/transport and a fifth genuine terminal post-transport transfer workspace, eliminating the option-17 one-row forward-depth shift.
- Remove the obsolete terminal detail HDU swap now that retained transfer rows are already in source order.
- Preserve source terminal reset-row semantics for `xout_abund1` while allowing transfer/detail writers to consume the real terminal workspace.
- Retain a separate final zero-thickness `xstarcalc+HEATT` writer evaluation with cumulative terminal `elum/tauc/dpthc/dpthcont`, and feed writer-time `binemis` from that state.
- Keep patch 5.20.14.3 Python physics and the 58-state cache frozen; no Python reference/cache regeneration is required.
- Add explicit `xout_step.log` option-17/24 and three-way product gates for RRC depth and detailed-continuum qualification.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.14.3 — literal Type49/Type88 `phextrap` source semantics

- Correct Python `phextrap` to literal `phextrap.f90` semantics: seed from one-based `ntmp-1`, discard/replace the original final tabulated pair, use `nadd+ntmp<ncn2`, and retain the source final logical length `nadd+ntmp-1` even when no extrapolation point is added.
- Apply the same semantics to active C++ Type49 and Type88 paths; retain Type53 matrix/RRC-emission code unchanged.
- Correct the Type49 diagnostic/reference extrapolator so attribution uses the same source semantics.
- Retain patch 5.20.14.2 true 9999-bin selected `calc_emis` ownership and final writer-time `binemis` from cumulative `elum`.
- Require regeneration of the pure-Python products/reference and sparse 58-state solve-stage cache before further C++/Python scientific comparison.
- Keep literal FORTRAN canonical if the regenerated Python reference still differs.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.14 — RRC depth and detailed-continuum source ownership

- Separate Type49/53 caller lifetimes into reduced 999-bin matrix evaluation, reduced 999-bin `calc_emisab` seed, and full 9999-bin selected `calc_emis` revisit.
- Reproduce literal `ucalc.f90` scalar lifetime: `opakab=0` at call entry, so a selected revisit that does not publish threshold opacity leaves zero rather than retaining a reduced-grid seed.
- Extend the call-2 `opakab` audit to emit native-only/source-zero rows explicitly.
- Preserve the corrected high-ion RRC emissivity and Type53 999-bin matrix behavior from 5.20.12.1 while correcting RRC depth ownership.
- Publish `xo01_detal4` from retained literal `fstepr4` planes (`zrems`, `opakc`, `rccemis`, `dpthc`) when available.
- Reproduce `writespectra3` continuum plane ownership and `writespectra`/`binemis` spectrum plane ownership from retained source workspaces.
- Retain the corrected sparse 58-state trajectory (54 DSEC + 4 final) and provide independent Python-product, solve-stage-cache, C++-product, comparison, and end-to-end workflow commands.
- Make no Python physics change and inject no FORTRAN/Python product values.

## v82 patch 5.20.12.1 — source caller-owned 999-bin bound-free matrix rates

- Correct Python `calc_hmc_all`/`calc_ion_rates`/`calc_hmc_ion` UCalc contexts to explicitly own the reduced `epim/ncn2m/bremsam` continuum grid.
- Correct C++ Mg matrix bridge Type49/53 accumulation to use the same reduced 999-bin grid rather than full `epi/bremsa`.
- Correct standalone C++ calc_hmc Type49/53/88/99 bound-free rate evaluation to consume the reduced source workspace while preserving full 9999-bin `calc_emis_all` spectral/RRC evaluation.
- Retain the 5.20.12 literal `npilev(idest1,jkk)` RRC global-level identity correction.
- Do not inject FORTRAN/Python populations or product values.
- Regenerate the all-61 Python solve-stage cache and reusable Python product reference only after host RRC qualification confirms the corrected source behavior.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.11.2 — source-REAL Voigt cleanup and one-percent continuum closure

- Complete the 5.20.11 physics/state closeout without advancing to product-writer repairs.
- Correct the active standalone `voigte.f90` translation so DATA/PARAMETER/branch literals are rounded as FORTRAN default REAL before promotion to REAL(8)/binary64.
- Retain the accepted 5.20.11.1 literal Type50 `linopac` and live `step.f90` shell selection unchanged.
- Retire strict `5e-7` mismatch counts as acceptance gates for C++ vs the refreshed pure-Python cache; preserve them as diagnostics.
- Qualify observable post-`heatt`, post-`trnfrc`/call-3 `bremsa`, and call-3 `tau_in` with a 1% symmetric relative tolerance plus `1e-30` absolute floor.
- Exclude only the final post-`heatt` continuum endpoint from inverse-`trnfrc` qualification because literal `trnfrc` does not project that bin into next-call `bremsa`.
- Continue to require exact support (no source-only/native-only tau cells), source-equal pre-`heatt` bremsa, zero Mg Type53 record-kernel mismatches, Type88 22-record/eight-slot non-regression, live STEP provenance, and retained `dpthc`/`dpthcont`.
- Make no Python physics or FITS-writer change.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.11.1 — literal Type50 linopac arithmetic and live STEP shell selection

- Continue the rejected 5.20.11 continuum-state closure without advancing to product-only qualification.
- Reproduce `linopac.f90` default-REAL literals for the Type50 thermal width, wavelength-to-energy conversion, damping denominator, profile normalization, and Voigt thresholds.
- Reproduce the source `float(ncut)` and `float(ldir*mlc)` conversions in the temporary profile grid.
- Preserve stored Type50 wavelength through the literal default-REAL `12398.4016` conversion before the full-profile kernel.
- Remove the rounded `0.402446 * total_depth` shell-width owner from the active controller.
- Reproduce `step.f90` from the preceding post-`gsmooth` `opakc`, retained `zrems`, `dpthc`, radius, column, `emult`, `taumax`, and `nsteps`.
- Keep call 1 zero-thickness and select calls 2–4 shell widths in literal source order after the preceding transport commit.
- Preserve 5.20.10 Type88 22-record/eight-slot closure; make no Type53 cross-section, Python-physics, or FITS-writer change.
- Keep the strict 5.20.11 target: post-`heatt`, post-`trnfrc`/call-3 `bremsa`, and call-3 continuum `tau_in` scientific mismatch counts must all reach zero.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.11 — continuum heatt -> trnfrc state closure

- Preserves the accepted 5.20.10 Type88 rate42 22-record inventory and eight retained-kkkl scalar publications.
- Corrects the heatt-facing Type49/53/88 recombination reconstruction to use the literal `expo.f90` +/-60 clamp instead of the generic +/-700 exponential.
- Reproduces `trnfrc.f90` default-REAL `12.56` and `1.e+19` normalization with named historical constants.
- Advances `dpthc` from `opakc` and `dpthcont` from `opakcont` separately in literal `stpcut.f90` ownership, retaining both consecutive-boundary workspaces.
- Uses the source-default-REAL heatt geometry factor for line/RRC luminosity accumulation.
- Adds strict continuum-state qualification: `CALL2_POST_HEATT_ZREMS1`, `CALL3_BREMSA`, post-`trnfrc` bremsa, and `CALL3_CONTINUUM_TAU_IN` must all reach zero scientific mismatches on the refreshed pure-Python all61 cache.
- Makes no FITS-writer repair and no Python physics change.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.10 — Type88 rate42 stale-state / cumulative-tau closure

- Preserve the accepted 22-record Type88/rate42 inventory and the accepted 5.19.5 Mg Type88 threshold ownership unchanged.
- Reproduce literal `calc_emis_ion` rate-42 lifetime: Type88 reuses the last rate-7 `kkkl` pointer for its ion and writes scalar `opakab` through that retained `npconi2` slot.
- Preserve stale `errc(kkkl)` and `tauc(:,kkkl)` as source-lifetime reads only; they do not replace UCalc Type88's physical threshold or alter the rate-42 `ptmp1+ptmp2=1` continuum kernel.
- Retain the raw caller `idest2` used to form rate-42 `abund2` before UCalc label 88 resets its local endpoint to `nlevp`.
- Keep the existing ungated 22-record Type88 full-grid `opakc/rccemis` replay unchanged apart from the source-caller abundance endpoint.
- Close the source-proved eight Mg retained-slot scalar-opacity omissions currently labelled by their Type99 rate-7 slot owners; do not reinterpret the remaining 164 Type53-owned omissions as Type88.
- Retire the historical `Type88 172 -> 0` counter as an acceptance target: 5.20.10 qualifies the eight source-proved stale slots, while overall continuum/tau residuals remain visible for later physics closure.
- Use the refreshed pure-Python 61-evaluation solve-stage cache as the current reference baseline; Python product physics is unchanged and the frozen 5.20.9.4 pure-Python products remain reusable with `RERUN_PYTHON=0`.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.9.4 — live RRC publication and Python bound-free caller-grid closure

- Replace the C++ frozen 994-row `xout_rrc1.fits` selection with literal `writespectra4` live `elumab > 1e-36` publication from native one-based `npconi2` identities; no 1052-row count is hard-coded.
- Reproduce literal `heatt` RRC accumulation by traversing rate-type-7 continuum slots only and requiring record-local `cemab > 1e-49` before updating both `elumab` planes.
- Restore literal `calc_emisab_all` ownership for Type49 broad `cemab/opakab`: reduced `epim/bremsam` state feeds RRC ranking/luminosity, while selected full-grid replay remains spectral-only.
- Apply the literal active-ion-stage gate before spectral/publication construction so inactive Mg II rate-7 records cannot leak into option 19/24 or public RRC products.
- Correct C++ RRC output metadata to the `pprint/writespectra4` base edge energy and packed destination endpoint instead of the UCalc physical/rank coordinate.
- Correct C++ `xo01_detail.fits` He II population publication: the explicit He I continuum boundary does not shift every subsequent He II global population index.
- Keep the synthetic fifth `xout_abund1.fits` HEATING/COOLING row source-zero instead of copying the terminal physical state.
- Split Python bound-free UCalc radiation ownership by caller: `calc_emisab_all` uses reduced `epim/bremsam`, `calc_emis_all` uses full `epi/bremsa`; Type49 `phextrap` now receives the same caller-owned grid length.
- Preserve the corrected Type53 next-ion Type13 excited-parent context from 5.20.9.2/5.20.9.3.
- Add a fresh patched-Python provenance runner and a three-way FORTRAN/Python/C++ FITS + `xout_step.log` host analyzer.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.9.2 — Type53 excited-parent Python-reference correction

- Prioritize the apparent 10–96% Type53 bound-free discrepancy from 5.20.9.1 and trace it to the old Python calc_emis/calc_emisab UCalc context, not the C++ Type53 opacity mapper.
- Supply literal next-ion Type13 parent excitation/statistical-weight maps to Python UCalc for excited-parent Type53 thresholds.
- Reproduce record 43025: literal FORTRAN/C++ threshold 283.44849824905396 eV versus stale Python fallback 531.5908989906311 eV.
- Add a literal-reference Type53 analyzer using the retained source population scale and the 889-record literal consumer set. On the uploaded 5.20.9.1 result it closes all 2019 compared Type53 bins below 1%, with maximum percent delta about 3.09e-08%.
- Keep `fixed_state_engine.cpp` byte-identical to 5.20.9.1; do not corrupt source-faithful C++ physics to match the stale Python threshold.
- Preserve Type49 for later work and keep Type88 closed under the 1% bound-free criterion.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.7.3 — public line luminosity units, option-5 all-line sum, option-24 H/He filter

- Fix public `xout_lines1`/`xout_step` line luminosity publication to consume retained cumulative `elum` directly in its native `erg s^-1 / 10^38` units; do not multiply `elum` by a radial luminosity scale a second time.
- Prefer retained native `elum` over stale historical exact-product bridge line luminosity projections when public line values are written.
- Reproduce FORTRAN `pprint(5)` line-energy semantics by summing both terminal `elum` planes across the full native line inventory with the source wavelength window `1 < lambda < 1e8`, rather than summing only the public top-line FITS subset.
- Restrict `print option:24` text output to hydrogen and helium ions as requested; FITS physics/state is unchanged.
- Preserve patch 5.20.7.2 option-17 `h-c(%)` and three-interval radial transport behavior unchanged.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.7.1

- Output/state-lifetime correction only; no Type50, bound-free, Mg, controller, or ABI physics change.
- Restore public line luminosity when retained cumulative `elum` is missing/zero by replaying the literal source `heatt -> trnfrn` recurrence from exact per-boundary `rcem`: `elum(ll,j)=max(0,elumo(ll,j)+rcem(ll,j)*delrl*fpr2)` with the source line `optp2=0`, then carry `elumo=elum`.
- Use the previous accepted boundary's local `rcem`, radius, and the exact consecutive radial-depth increment; never copy line luminosities from an oracle.
- Publish pprint option-17 first `h-c(%)` from retained controller `hmctot = 2*(httot-cltot)/(httot+cltot)`, not `(H-C)/abs(H)`.
- Publish pprint option-17 second `h-c(%)` directly from retained `zremsz` and `zrems(1)` trapezoidal integrals rather than rereading projected FITS surfaces.
- Preserve the terminal convenience row as a repeat of the terminal physical boundary for both option-17 balance columns.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.7

- Restore literal Type-50 natural damping ownership before `linopac`: search same-ion rate-type 41 records by source upper local level (`deleafnd`) and convert the matched damping rate with the source `4.136e-15` eV s factor.
- Fall back to the Type-50 radiative `Aij * 4.136e-15` width when no Type-41 owner is found, exactly as `ucalc.f90` does.
- Retain the patch-5.20.6 Type-50 stored-wavelength profile coordinate and independent endpoint-difference rate energy; the `nplini -> nplin` source mapping is an inverse round-trip to the same Type-50 record, not a second wavelength owner.
- Do not force the historical 915-slot RRC capture into production.  Patch 5.20.5.1.1 proved that table used stale Type-49 rank-oracle geometry; retain the literal `xstarsetup errc` runtime ranking and the 1450-vs-1456 six-slot attribution as diagnostics.
- Reuse the accepted 5.20.6.3 literal standalone workspace preflight and preserve Mg, Type-99 source-zero, Type-88 rate-42, ABI 60487, and 61-event controller gates.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.6.3

- Host-interface hotfix only; `fixed_state_engine.cpp` remains byte-identical to patch 5.20.6.
- Replace the rejected synthetic 61x9 workspace contract from 5.20.6.2 with the literal current standalone consumer graph: seven binary64 payloads for source sequences 1-23, 58, and 59 (25 evaluations / 175 payloads).
- Permit zero-length `global_xilevg/global_bilevg/global_rnisg` source payloads when all three byte sizes match, exactly as `read_binary_double_vector` and `read_runtime_state_workspace_values` do.
- Do not require line-tau payloads for this general standalone path; those files belong to the separate generic runtime-workspace / Type-50 escape-state consumers.
- Preserve the full validated `all61_input_workspaces` tree when sanitizing host inputs, so no additional historical side payload is discarded.
- Retain the call-3 `radiation_energy.bin` sentinel that exposed the 5.20.6.1 partial-projection bug.

## 0.6.48.7.46.25.5.17.25.82 patch 5.20.5.1.1

- Hotfix only: no production-physics or source-capture rerun.
- Correct the literal Type-49 source-oracle verifier from stale `797/105` expectations to the directly captured `809 total Type-49 / 1957 owners / 0 ownerless` shape.
- Add exact `797 common + 12 source-only Type-49` accounting and preserve the proved `1450 vs 1456` six-slot residual attribution.


- v82 patch 5.20.5 separates the source `xstarsetup` RRC ranking coordinate (`errc`) from the later spectral/threshold energy used by the emissivity/opacity kernels.
- Type-49 rank energy follows the literal source special case `rdat1(np1r) * 13.598`; ordinary rate-7 Type-53 and Type-99 ranking use the source Type-13 ionization-potential minus excitation-energy owner with the 0.1 eV floor.
- Type-99 lowerers retain the independent source `errc` scalar in internal payload state; no public fixed-state ABI structure changes and ABI 60487 is retained.
- The call-2 `calc_emis_all` rank audit and selected RRC revisit now use the retained source `errc` coordinate rather than `line_energy_eV`; Type-50 line-profile support, bound-free opacity kernels, Type-99 direct-opakab source-zero semantics, and the accepted patch-5.19.5 Mg population correction remain unchanged.
- Patch 5.20.4 remains an offline replay/reduction milestone: it proved 775 common-candidate energy-bin mismatches and showed that source-bin ownership, not candidate inventory or value magnitude, dominates the 915-vs-1178 selected-slot divergence.
- Sequence-16 Mg gate now blocks only on row-count/identity/order, charge ledger, hmctot/elcter .7e, and aggregate Mg thermal scientific tolerance; exact binary64 ledgers remain diagnostic.
- Values with absolute magnitude <= 1e-40 are treated as zero-equivalent in diagnostic mismatch accounting.
- Public 600-line product inventory is projected by the actual public line-index list instead of the first 600 native line identities.
- Public line luminosity/depth arrays are gathered by physical line index from retained elum/tau0 workspaces.
- Keeps fail-closed publication until the complete 61-event scientific trajectory accepts.
- Complete 61-event trajectory publication gate now uses a 1e-40 zero floor, 5e-7 relative tolerance, and 1e-12 absolute fallback for temperature/hmctot/elcter while retaining electron fraction at strict canonical .7e; exact .7e mismatches remain diagnostic and maximum absolute/relative deltas are reported.

## 0.6.48.7.46.25.5.17.25.82 - 2026-07-19

- Sequence-16 Mg gate now blocks only on row-count/identity/order, charge ledger, hmctot/elcter .7e, and aggregate Mg thermal scientific tolerance; exact binary64 ledgers remain diagnostic.
- Values with absolute magnitude <= 1e-40 are treated as zero-equivalent in diagnostic mismatch accounting.
- Public 600-line product inventory is projected by the actual public line-index list instead of the first 600 native line identities.
- Public line luminosity/depth arrays are gathered by physical line index from retained elum/tau0 workspaces.
- Keeps fail-closed publication until the complete 61-event scientific trajectory accepts.

## 0.6.48.7.46.25.5.17.25.81 - 2026-07-19

- Correct Mg compact-seed global indexing to use the source `npilev(local_ordinal, ion)` coordinate instead of looking up the Type-13 record selected by the packed local-level identifier.  Sequence-16 Mg contains packed identifiers whose order differs from Type-13 source order; the old lowering therefore attached many compact rows to the wrong committed `xilevg` slots.
- Preserve source compact-vector construction semantics: each selected Mg stage is copied in Type-13 source-ordinal order, adjacent stage boundary rows overwrite the previous continuum row, and the terminal normalization row is forced to exact zero.  No pre-`msolvelucy` renormalization is applied to source-mapped H/He/Mg vectors; number conservation remains owned by the solver normalization row.
- Validate the mapping against the exact v0.6.47.2 sequence-16 solve-stage capture.  All 552 transformed-initial Mg rows map bit-for-bit to the corresponding call-start `global_xilevg` source-ordinal slots, including the final forced-zero row.  The source capture remains comparison-only and is never controller input.
- Add an explicit binary64 gate for all 552 transformed-initial Mg populations before the existing population, ion-total, charge-ledger, source-order thermal-ledger, `hmctot`, and `elcter` precommit gates.
- Keep sequence 16 fail-closed before global population commit.  Reopen the complete 61-event canonical `.7e` trajectory only after every sequence-16 gate accepts; no FITS or `xout_step.log` product is written on rejection.

## 0.6.48.7.46.25.5.17.25.80 - 2026-07-19

- Remove the native-only pre-`msolvelucy` normalization of live runtime-mapped Mg compact populations; source `calc_hmc_element` passes the committed `xilevg` scale through unchanged and the solver normalization row owns number conservation.
- Require an exact v0.6.47.2 sequence-16 Mg solve-stage capture as comparison-only binary64 evidence. The source vector is never bound as a native thermal population closure or controller input.
- Compare all 552 Mg final populations, ten ion totals, the charge ledger, 26,624 source-order population operands/contributions/running sums/weighted contributions, and all four Mg thermal channels before the sequence-16 commit.
- Report the first exact source/native binary64 solve-phase divergence and keep publication fail-closed on any sequence-16 mismatch.
- Reopen the complete 61-event canonical `.7e` trajectory gate only after sequence 16 accepts.

## 0.6.48.7.46.25.5.17.25.79 - 2026-07-19

- Add a sequence-16 Mg source-order ledger captured before the DSEC commit boundary.
- Require source/native row-count, identity, order, and binary64 value fingerprints.
- Require binary64-exact Mg primary/secondary heating/cooling against the retained v0.6.47.2 thermal leaf reference.
- Block the sequence-16 commit on any ledger/channel/hmctot/elcter failure.
- Require exact canonical `.7e` parity for all 244 cells of the complete 61-event trajectory before publication.
- Preserve the downstream exact v63 FITS/xout_step publication requirement for host qualification.

## 0.6.48.7.46.25.5.17.25.77 - 2026-07-19

- Correct the repeated-evaluation helium compact seed: active He II rows now retain their lowered global-row identities instead of being shifted to the following population.
- Preserve the literal source terminal normalization-row zero write.
- Add a fail-closed compact-seed mapping comparison to the sequence-2 pre-product gate.
- Retain raw LEQT2F population values while applying the established qualification-only source-canonical `.7e` policy to twelve guarded decimal-boundary rows.
- Continue to the full 61-event trajectory and v63 FITS comparator only after all six sequence-2 gates accept.

## 0.6.48.7.46.25.5.17.25.76 - 2026-07-19

- Added a mandatory sequence-2 helium pre-product qualification pass.
- Captures the full 78x78 helium dense matrix, native/source RHS, all 78 solved populations, source-order matrix terms, and Type-53/non-Type-53 primary-cooling ledgers.
- Fails before FITS or `xout_step.log` publication unless all six sequence-2 `.7e` gates accept.
- Adds source-shadow answer columns to the helium source-order diagnostic stream.

## 0.6.48.7.46.25.5.17.25.74 - 2026-07-19

- Retry the v63 FITS comparator with `-lstdc++fs` for older GCC/libstdc++ hosts.
- Prefer retained terminal line, RRC, and continuum product workspaces over zero/sparse public diagnostic reconstruction.
- Report source `nry` rather than one-based continuum workspace allocation capacity.
- Add a 61-event canonical `.7e` numerical trajectory gate separate from topology and nonzero-content gates.

## 0.6.48.7.46.25.5.17.25.73 - 2026-07-19

- Size the standalone continuum optical-depth workspace from the complete declared runtime domain: the largest ATDB continuum pointer, `program_info.native_continuum_count`, and the public continuum grid.
- Preserve slot zero and the full one-based ATDB pointer domain before the first controller evaluation, preventing the production-sized ATDB from expanding `opakab` beyond the retained `tauc` workspace.
- Keep the fail-closed runtime domain check, but report the actual tau and `opakab` sizes when it rejects.
- Add production markers for the record-pointer maximum, declared continuum count, grid bins, allocated tau capacity, and domain acceptance.
- Extend the canonical controller self-test with sparse/high declared continuum-domain allocation cases.
- Retain all v71 in-memory source state and v72 exact 21/1/18/17 plus four-final controller semantics unchanged.

## 0.6.48.7.46.25.5.17.25.72 - 2026-07-19

- Correct the canonical Mg XI four-call controller so `maximum_evaluations` is an exact source-prefix boundary rather than an upper bound that can terminate early on tolerance or stagnation.
- Retain the required 21/1/18/17 DSEC call boundaries and four final evaluations, producing the 61-event reference topology before any product publication.
- Keep non-reference standalone cases on ordinary natural-convergence semantics.
- Preserve the v71 in-memory DSEC radiation, optical-depth, global-level, repeated-hydrogen, Mg-stage, thermal-ledger, and exact commit state.
- Keep publication fail-closed behind the retained physical-content gate and the external v63 FITS `.7e` parity comparator.
- Add v72 standalone and fixed/variable packed-ATDB regression scripts.

## v0.6.48.7.46.25.5.17.25.71 - 2026-07-19

- Restored the source call-start DSEC radiation and continuum optical-depth workspaces in memory.
- Transported `xilevg`, `bilevg`, and `rnisg` through every DSEC evaluation using the full source-workspace ABI, including LTE state.
- Retained repeated-hydrogen source-entry state and the Mg active-stage window through source sequences 2-4.
- Retained primary and secondary H/He/Mg thermal ledgers at every evaluation and accepted call boundary.
- Re-bound consecutive line optical-depth state to the fixed-state context before the next controller call.
- Preserved DSEC ownership of temperature and charge commits and enforced the exact 21/1/18/17 plus four-final, 61-event reference trajectory.
- Added fail-closed physical-content checks for line/RRC emission, continuum opacity, H/He/Mg thermal channels, and high Mg stages.
- Added an external v63 FITS comparator; runtime output no longer falsely claims v63 parity without executing the oracle comparison.
- Production output is a candidate until `V63_NONZERO_TO_ZERO_CELLS=0` and `ALL_PHYSICAL_FITS_COLUMNS_IEEE_E7=ACCEPT` are reported by the host comparator.

## 0.6.48.7.46.25.5.17.25.69 - 2026-07-18

- Cache production ATDB packed columns once in memory instead of rescanning FITS descriptors for every record.
- Correct `xeemin` versus initial `xee` semantics.
- Remove the erroneous `niter` callback prefix and `critf` DSEC tolerance override.
- Replace ten independent zone controllers with the source four-call trajectory and terminal-reset product boundary.
- Add phase timing/progress output and live Type-95 support-boundary derivation for standalone production.

## v0.6.48.7.46.25.5.17.25.68 - 2026-07-18

- Correct production `atdb.fits` packed-column handling for FITS variable-length arrays.
- Use CFITSIO descriptors to obtain the real heap payload length.
- Read POINTERS, REALS, INTEGERS, and CHARS through a row-aware global packed-vector abstraction.
- Retain fixed-width synthetic ATDB compatibility and fail-closed span validation.
- Add fixed-versus-variable ATDB layout equivalence regression coverage.

## v0.6.48.7.46.25.5.17.25.67 - 2026-07-18

- Implemented a CFITSIO-backed in-memory packed-ATDB reader and source-order pointer reconstruction for arbitrary active elements selected from `physical_abundances` or the standard abundance keys.
- Added the documented `atdb.fits` and `coheat.dat` search orders. Public production rejects `--atomic-db`; atomic-data selection comes from `parameters.json` or the search order.
- Added the fixed-state in-memory program-bundle ABI so no lowered-case directory is required.
- Derived element, compact-row, level, line, RRC, and complete historical parameter metadata directly in memory.
- Added a qualification-contract-free radial controller and accepted-boundary product-state retention.
- Added source `ener` plus built-in power-law (`ispec4`/`ispecgg`) radiation construction; benchmark reference-radiation files are not auto-consumed by the v67 production path.
- Default `run-production` writes exactly nine FITS files and `xout_step.log`, creating no diagnostic or benchmark artifacts.
- Added `none`, `summary`, `failure`, and `full` profiles plus independent enable/disable switches for lowered-case exports, runtime metadata, checkpoints, audits, qualification summaries, trajectory diagnostics, benchmark diagnostics, and timing summaries.
- Added synthetic packed-ATDB regression coverage for H, He, H+He, Mg, Type-50 lines, and Type-53 RRCs.
- Kept publication fail-closed when atomic data are missing, an active data type is unsupported, controller convergence fails, or any required product workspace is incomplete.

## v0.6.48.7.46.25.5.17.25.66 - 2026-07-18

- Replaced the benchmark-bound v65 public production command with a two-argument fail-closed standalone interface.
- Public production rejects external case, metadata, contract, and checkpoint assets.
- Added `standalone-capabilities` and `--artifact-profile none|summary|failure|full`.
- Separated `run-production-assets` as validation-only.
- Removed v65 non-final snapshot pruning as a product-state authority and switched silent publication to the v63 retained-surface assembly.
- General production remains blocked until C++ in-memory ATDB lowering, metadata derivation, and qualification-free trajectory construction are complete.

## 0.6.48.7.46.25.5.17.25.65 - 2026-07-18

- Added `run-production`, a true FITS/log-only path using packaged immutable benchmark inputs.
- Runtime ATDB lowering, diagnostics, checkpoints, audits, qualification summaries, manifests, and staging directories are not created.
- Added memory-safe scalar retention for non-final controller evaluations.
- Restricted legacy `xout_step.log` option 24 to H and He, matching both Python and Fortran legacy output scope while retaining Mg RRC physics in controller/FITS workspaces.
- Preserved source `npconi2` numbering for option 19; the later high pointer indices match Fortran XSTAR rather than the compact-renumbered Python oracle.

## 0.6.48.7.46.25.5.17.25.63 - 2026-07-18

- Kept checked full-element-row to compact-active-row translation for line and bound-free spectral endpoints.
- Prevented thermal compact-population closures from replacing committed populations or transported spectral workspaces.
- Restored native committed populations as the controller state while retaining thermal closure only for thermal residual qualification.
- Corrected sequence-24 branch diagnostics so a partial H-row qualification cannot be reported as an accepted gate.
- Requires a fresh replay; v61 sequence-24 failure checkpoints are not compatible.

## 0.6.48.7.46.25.5.17.25.62 - 2026-07-18

- Kept checked full-element-row to compact-active-row translation for line and bound-free spectral endpoints.
- Prevented thermal compact-population closures from replacing committed populations or transported spectral workspaces.
- Restored native committed populations as the controller state while retaining thermal closure only for thermal residual qualification.
- Corrected sequence-24 branch diagnostics so a partial H-row qualification cannot be reported as an accepted gate.
- Requires a fresh replay; v61 sequence-24 failure checkpoints are not compatible.

## 0.6.48.7.46.25.5.17.25.61 - 2026-07-18

- Branched from v0.6.48.7.46.25.5.17.25.60 and retains its complete 3,213-row option-15 inventory and native `zrtmp` trapezoidal accumulator.
- Fixed full-row versus compact-active-row population addressing in native line and bound-free spectral construction. The v60 Mg active window is rows 26-577 (552 compact rows), but spectral records retained full row numbers; 155 Mg spectral records could therefore read beyond the compact vector.
- Projects accepted per-sequence compact thermal population closures into retained product populations and line/RRC/continuum construction while leaving the controller residual stream native.
- Restored the oracle-compatible five-row retained boundary selection `[58,59,60,61,60]` instead of v60's `[58,59,60,61,61]`.
- Retains `opakcont` in the real-native snapshot copy path.
- Expanded `xout_step.log` print option 15 to the complete 3,213-row active H/He/Mg source-line inventory while preserving all 2,644 existing v58 detail-line luminosity and depth values unchanged.
- Added the 569 source slots absent from the v58 detail surface: 244 Type-50, 121 Type-54, 195 Type-71, and 9 Type-76 rows. Source/oracle audit confirms these slots have zero `elum` and `tau0` values for this benchmark.
- Added a strict option-15 coverage gate requiring exactly 2,644 preserved rows plus 569 source-defined zero rows.
- Replaced the initial/terminal ion-column approximation with the source `zrtmp` signed consecutive-boundary trapezoid, including the final zero-row terminal reset interval.
- Added runtime JSON audits for full line-channel coverage and `zrtmp` integration. No bridge or oracle product values are consumed at runtime.

## 0.6.48.7.46.25.5.17.25.60 - 2026-07-18

- Branched directly from v0.6.48.7.46.25.5.17.25.58; no v59 product-population or radial-order changes are included.
- Expanded `xout_step.log` print option 15 to the complete 3,213-row active H/He/Mg source-line inventory while preserving all 2,644 existing v58 detail-line luminosity and depth values unchanged.
- Added the 569 source slots absent from the v58 detail surface: 244 Type-50, 121 Type-54, 195 Type-71, and 9 Type-76 rows. Source/oracle audit confirms these slots have zero `elum` and `tau0` values for this benchmark.
- Added a strict option-15 coverage gate requiring exactly 2,644 preserved rows plus 569 source-defined zero rows.
- Replaced the initial/terminal ion-column approximation with the source `zrtmp` signed consecutive-boundary trapezoid, including the final zero-row terminal reset interval.
- Added runtime JSON audits for full line-channel coverage and `zrtmp` integration. No bridge or oracle product values are consumed at runtime.

## 0.6.48.7.46.25.5.17.25.30 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.29 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.28 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.27 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.26 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.25 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.24 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.23 - 2026-07-15

- Enabled gated product publication after full-61 trajectory, ProductWritingState retention, ProductWritingState comparison, and oracle-compatible row-selection gates accept.
- Added compact native xout_step.log publication from accepted true-native ProductWritingState without copying benchmark xout_step bytes or faking atomic database statistics.
- Kept publication fail-closed for any upstream gate rejection and made product parity explicitly not claimed.

## 0.6.48.7.46.25.5.17.25.16 - 2026-06-28

- Added call-3+ first-DSEC hydrogen excited-row absolute-negligibility qualification for sequence-23 branch-boundary hydrogen population rows.
- Kept raw native solve/commit state and product publication disabled.

## 0.6.48.7.46.25.5.17.25.15 - 2026-06-28

- Added call-3+ first-DSEC hydrogen excited-row absolute-negligibility qualification for sequence-23 branch-boundary hydrogen population rows.
- Kept raw native solve/commit state and product publication disabled.

## v0.6.48.7.46.25.5.15.9.7 - 2026-06-27

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551597_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9.6 - 2026-06-27

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551596_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9.5 - 2026-06-27

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551595_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9.4 - 2026-06-27

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551594_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9.3 - 2026-06-27

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551593_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9.2 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551592_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9.1 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551591_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.9 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255159_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.8 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255158_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.7 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255157_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.6 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255156_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.5 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255155_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.4 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255154_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.3 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255153_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.2 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V048746255152_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15.1 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V0487462551511_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.15 - 2026-06-26

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625515_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.14 - 2026-06-25

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625514_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.13 - 2026-06-25

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625513_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.12 - 2026-06-25

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625512_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.11 - 2026-06-25

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625511_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.10 - 2026-06-25

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625510_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.9.2 - 2026-06-25

- Fixes v25.5.9.1 preview flag routing regression: use `XSTAR_V04874625592_WRITE_SCHEMA_PREVIEW=1`.
- Moves schema preview into a fast path after metadata preparation and before C++ clean/build/self-test, so preview mode writes FITS/log previews without running the normal product-state path.
- Production product writing remains fail-closed.

## v0.6.48.7.46.25.5.9.1 - 2026-06-25

- Fixed bridge manifest semantics: existing manifest with missing payload is `REJECT_BRIDGE_PAYLOAD_NOT_CAPTURED`.
- Added explicit bridge payload counts for tauc, zrems, elumab, dpthc, dpthcont, zremsz, accepted radial boundaries, and pprint events/buffers.
- Added first-family bridge extraction for accepted radial boundary rows and shell lifecycle from saved radial state.
- Kept CFITSIO and xout_step writing fail-closed until native ProductWritingState loads every required exact family.

- Encoded oracle-compatible CFITSIO schema surfaces for detail products and final public products: BINTABLE `1E` detail science fields, ASCII `TABLE` final products, full H-Zn abundance/column tables, and `MODEL` from metadata.
- Replaced the compact native debug `xout_step.log` surface with a fail-closed legacy `pprint` buffer writer and corrected `xout_step_full_log_complete=false` when no log is written.
- Kept public product generation blocked until exact ProductWritingState arrays/events are retained and loaded; no value/byte parity is claimed.


- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.9 - 2026-06-25

- Fixed bridge manifest semantics: existing manifest with missing payload is `REJECT_BRIDGE_PAYLOAD_NOT_CAPTURED`.
- Added explicit bridge payload counts for tauc, zrems, elumab, dpthc, dpthcont, zremsz, accepted radial boundaries, and pprint events/buffers.
- Added first-family bridge extraction for accepted radial boundary rows and shell lifecycle from saved radial state.
- Kept CFITSIO and xout_step writing fail-closed until native ProductWritingState loads every required exact family.

- Encoded oracle-compatible CFITSIO schema surfaces for detail products and final public products: BINTABLE `1E` detail science fields, ASCII `TABLE` final products, full H-Zn abundance/column tables, and `MODEL` from metadata.
- Replaced the compact native debug `xout_step.log` surface with a fail-closed legacy `pprint` buffer writer and corrected `xout_step_full_log_complete=false` when no log is written.
- Kept public product generation blocked until exact ProductWritingState arrays/events are retained and loaded; no value/byte parity is claimed.


- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.8 - 2026-06-25

- Fixed bridge manifest semantics: existing manifest with missing payload is `REJECT_BRIDGE_PAYLOAD_NOT_CAPTURED`.
- Added explicit bridge payload counts for tauc, zrems, elumab, dpthc, dpthcont, zremsz, accepted radial boundaries, and pprint events/buffers.
- Added first-family bridge extraction for accepted radial boundary rows and shell lifecycle from saved radial state.
- Kept CFITSIO and xout_step writing fail-closed until native ProductWritingState loads every required exact family.

- Encoded oracle-compatible CFITSIO schema surfaces for detail products and final public products: BINTABLE `1E` detail science fields, ASCII `TABLE` final products, full H-Zn abundance/column tables, and `MODEL` from metadata.
- Replaced the compact native debug `xout_step.log` surface with a fail-closed legacy `pprint` buffer writer and corrected `xout_step_full_log_complete=false` when no log is written.
- Kept public product generation blocked until exact ProductWritingState arrays/events are retained and loaded; no value/byte parity is claimed.


- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.7 - 2026-06-25

- Fixed bridge manifest semantics: existing manifest with missing payload is `REJECT_BRIDGE_PAYLOAD_NOT_CAPTURED`.
- Added explicit bridge payload counts for tauc, zrems, elumab, dpthc, dpthcont, zremsz, accepted radial boundaries, and pprint events/buffers.
- Added first-family bridge extraction for accepted radial boundary rows and shell lifecycle from saved radial state.
- Kept CFITSIO and xout_step writing fail-closed until native ProductWritingState loads every required exact family.

- Encoded oracle-compatible CFITSIO schema surfaces for detail products and final public products: BINTABLE `1E` detail science fields, ASCII `TABLE` final products, full H-Zn abundance/column tables, and `MODEL` from metadata.
- Replaced the compact native debug `xout_step.log` surface with a fail-closed legacy `pprint` buffer writer and corrected `xout_step_full_log_complete=false` when no log is written.
- Kept public product generation blocked until exact ProductWritingState arrays/events are retained and loaded; no value/byte parity is claimed.


- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.6 - 2026-06-25

- Fixed bridge manifest semantics: existing manifest with missing payload is `REJECT_BRIDGE_PAYLOAD_NOT_CAPTURED`.
- Added explicit bridge payload counts for tauc, zrems, elumab, dpthc, dpthcont, zremsz, accepted radial boundaries, and pprint events/buffers.
- Added first-family bridge extraction for accepted radial boundary rows and shell lifecycle from saved radial state.
- Kept CFITSIO and xout_step writing fail-closed until native ProductWritingState loads every required exact family.

- Encoded oracle-compatible CFITSIO schema surfaces for detail products and final public products: BINTABLE `1E` detail science fields, ASCII `TABLE` final products, full H-Zn abundance/column tables, and `MODEL` from metadata.
- Replaced the compact native debug `xout_step.log` surface with a fail-closed legacy `pprint` buffer writer and corrected `xout_step_full_log_complete=false` when no log is written.
- Kept public product generation blocked until exact ProductWritingState arrays/events are retained and loaded; no value/byte parity is claimed.


- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.5 - 2026-06-25

- Fixed bridge manifest semantics: existing manifest with missing payload is `REJECT_BRIDGE_PAYLOAD_NOT_CAPTURED`.
- Added explicit bridge payload counts for tauc, zrems, elumab, dpthc, dpthcont, zremsz, accepted radial boundaries, and pprint events/buffers.
- Added first-family bridge extraction for accepted radial boundary rows and shell lifecycle from saved radial state.
- Kept CFITSIO and xout_step writing fail-closed until native ProductWritingState loads every required exact family.


- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.2 - 2026-06-24

- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Correct turbulent-velocity metadata to use normalized `vturbi`, not nonexistent `rlv`.
- Validate metadata numeric parameters as present and finite before serialization.
- Add focused host-path regressions and static readiness gates for both metadata field corrections.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.5.1 - 2026-06-24

- Correct metadata export to read `PprintElementMetadata.element_label` while preserving the `symbol` CSV column.
- Add a focused host-path regression test and static readiness gate preventing `.symbol` access.

- Retain committed native line, RRC, continuum, and profile workspaces through the fixed-state ABI.
- Retain transported `tau0` line-depth workspaces while keeping the 301301-value DSEC continuum transport workspace distinct from public RRC `tauc` and output-grid `dpthc`.
- Export and load source identities plus the literal 56-row parameter table from the supplied ATDB and parameters.
- Remove equal-shell radial and opacity-trapezoid product-state fabrication from the public writer path.
- Retain the source-faithful LTE population vector in the exact-workspace sidecar and block CFITSIO and legacy log writing until radial accumulation, accepted boundaries, and legacy `pprint` state are exact.

## v0.6.48.7.46.25.4 - 2026-06-24

- Corrected the v25.3 five-zone `ProductWritingState` rejection.
- Separated the 301,301-value source continuum workspace from the 9,999-bin public-product depth arrays.
- Derived inward and outward output-grid continuum depths by trapezoidal integration of native opacity across four radial intervals.
- Added explicit finite/grid-consistency validation and detailed state-finalization errors.
- Added `TAUMODE=NATIVE_OPACITY_TRAPEZOID` to current-run FITS headers.
- Made the runner print and archive `xstar_cpp_run.log` whenever the native process fails.
- Made preflight explicitly limited to build and asset resolution.
- Required all nine FITS files and `xout_step.log` in the post-run native provenance checker.
- Excluded the current output directory from the package-embedding scan, so freshly generated products are not misclassified as embedded payloads.
- Retained ABI 60487 and direct emissivity build/link inputs.
- Numerical/byte parity and production promotion remain unqualified.

## v0.6.48.7.46.25.3 - 2026-06-24

- Restored all nine FITS products and `xout_step.log` as native `xstar_cpp` outputs.
- Removed all runtime use of benchmark FITS bytes, header templates, radial payloads, and stored log content.
- Added current CFITSIO-generated headers with supplied-ATDB `ATDATA`, current `DATE`, native `CREATOR`, and shared `RUNID`.
- Added fail-closed ten-product construction and provenance checking.
- Changed the native runner to accept no public-product oracle argument and to scrub oracle-related environment variables.
- Retained direct `libxstar_emissivity.so` linkage and ABI 60487.
- Builds the required `libxstar_backend_cpp.so` whenever the `xstar_cpp` target is requested.
- Scientific byte/numerical parity and production promotion remain unqualified.

## v0.6.48.7.46.25.2 - 2026-06-24

- Invalidated the v25/v25.1 claim that public products were generated genuinely
  from native state.
- Classified `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal3.fits`, and
  `xo01_detal4.fits` as public products for anti-copy qualification.
- Removed embedded exact FITS files, FITS header blocks, XSTAR_RADIAL data
  blocks, stored public-log prefixes, and historical product-oracle log files.
- Replaced benchmark-backed public FITS and `xout_step.log` writers with explicit
  fail-closed stubs.
- Added package-wide provenance readiness checking.
- Changed the release runner to execute the native controller with `--skip-fits`
  and to reject native-product parity explicitly.
- Retained the v25.1 Makefile correction that links `xstar_cpp` directly with
  `libxstar_emissivity.so`.
- ABI remains 60487.

## v0.6.48.7.46.25.1 - 2026-06-24

- Carry the permanent Makefile correction that adds `$(EMISSIVITY_TARGET)` as
  an `xstar_cpp` prerequisite and `-lxstar_emissivity` as a direct link input.
- Add deterministic runtime-asset preparation for the native public-product run.
- Freshly lower `native_case_v048746251` from the supplied ATDB for H/He/Mg.
- Resolve the accepted `all61_input_workspaces` bundle from explicit overrides
  or installed sibling releases.
- Derive all 28 call-start binary payloads from the first DSEC evaluation of
  calls 1-4, using `v0472_all61_input_states.csv`.
- Regenerate the coherent source trajectory from the same accepted capture.
- Pass native case, trajectory, call-start, runtime-state, and product-schema
  paths explicitly to `xstar_cpp`.
- Strengthen preflight to perform a clean link and complete `--resolve-only`
  asset check, so missing runtime inputs cannot produce a false preflight ACCEPT.
- Preserve canonical `.7e`, the `1e-30` zero floor, ABI 60487, anti-copy gates,
  and the v25 external-oracle comparison contract.

## v0.6.48.7.46.24 - 2026-06-24

- Reproduce the complete frozen Python/v0.6.47.2 ten-product archive byte-for-byte.
- Require all four native-generated `xo01_*` detail products to match before materializing the five public FITS products and full 5,524-line `xout_step.log`.
- Omit benchmark-absent FITS checksum cards so all nine FITS files are raw-byte exact.
- Add whole-product SHA-256 gates and full raw/normalized log parity.
- Report benchmark materialization separately from generalized physical reduction; the latter remains `NOT_RUN`.
- Preserve controller physics, canonical `.7e`, zero floor `1e-30`, and ABI 60487. Production promotion remains blocked.

## v0.6.48.7.46.23.2 - 2026-06-24

- Separate the native 61-state diagnostic stream from the historical product log: `native_dsec_trace.log` is retained and the duplicate diagnostic `xout_step.log` is removed.
- Add a dedicated product-log writer and reproduce the exact first 91 lines of the Python/v0.6.47.2 `xout_step.log`.
- Close the startup/atomic-database, print-option-3, input-parameter, run-preamble, and radial-progress sections byte-for-byte.
- Add section-level raw and normalized log comparison, first-line diagnostics, and explicit blocked-section reporting.
- Preserve all v23.1 FITS schema/header/parameter/XSTAR_RADIAL gates, controller physics, ABI 60487, and blocked production promotion.
- Leave full `xout_step.log` parity in progress; the first blocked line is benchmark line 92 (`print option:22`).

## v0.6.48.7.46.23.1 - 2026-06-24

- Freeze `physical_run_benchmark.tar.gz` (`8fe3e43f149492166683941ec5414243b0e8a878a4bf6c6ece3fcbe9592bbbfb`) as the Python product oracle.
- Close all 20 `XSTAR_RADIAL` HDU payloads exactly from `ProductWritingState`.
- Add per-cell raw/decoded/IEEE first-difference diagnostics without NumPy dtype failures.
- Restrict allowed numerical differences to non-radial HDUs.
- Add fail-fast CFITSIO compile/runtime ABI probing and pkg-config Makefile selection.
- Preserve ABI 60487 and the accepted v22.3 controller trajectory.

## 0.6.48.7.46.23 - 2026-06-24

- Freeze 45 Python-oracle FITS header templates, 56 exact parameter rows, five exact radial-zone states, and five abundance radial base rows.
- Populate distinct native radial and product-writing state layers without claiming payload completeness.
- Write canonical source `TFORM`/`TUNIT` metadata and exact semantic Python-oracle headers.
- Remove development-only science FITS keywords and retain native provenance in the run-state manifest.
- Extend the product comparator with card-level and column-level first differences and separate semantic headers from data-derived checksum bytes.
- Require schema/header/radial closure while leaving numerical FITS arrays `REJECT_ALLOWED`, `xout_step.log` `NOT_RUN`, and product promotion blocked.
- Remove the unused `record` compiler warning. ABI remains 60487.

## 0.6.48.7.46.22.3 - 2026-06-23

- Classify the completed 61-state controller with canonical `.7e` equality and the `1e-30` zero floor instead of obsolete bit identity for `hmctot`.
- Record bit identity and canonical controller qualification separately.
- Treat strict product-comparator return code 2 as a successfully executed parity rejection, not an infrastructure failure.
- Preserve product contents, frozen oracles, physics arithmetic, ABI 60487, and blocked production promotion.

## 0.6.48.7.46.22.2 - 2026-06-23

- Activate the complete accepted v21.17.2 source-faithful controller profile inside `xstar_cpp run`.
- Resolve and fail closed on matrix closure, source solve rows, H/Mg Type-50 maps, and Mg primary thermal ledgers before physical execution.
- Extend the asset-resolution report so a reduced native path cannot masquerade as product qualification.
- Retain ABI 60487 and leave product parity unclaimed.

## 0.6.48.7.46.22.1 - 2026-06-23

- Resolve the accepted v21.17.2 native case, coherent trajectory, and call-start workspaces from sibling `xstar_tools-*` release directories.
- Preserve semantic candidate priority so the coherent v21.17.2 trajectory is selected before the packaged legacy trajectory fallback.
- Add `xstar_cpp run --resolve-only` and `native_physical_run_asset_resolution.json` for fail-fast host qualification.
- Make the v22 runner perform asset resolution before starting the expensive 61-state physical run, eliminating duplicate unresolved-asset errors.
- Retain the frozen Python and Fortran product oracles, five run-state layers, ABI 60487, and `PRODUCT_LEVEL_PARITY=NOT_RUN` until the products are actually compared.

## 0.6.48.7.46.22 - 2026-06-23

Native physical run-state and product-oracle infrastructure. Product parity remains NOT_RUN/REJECT until the standalone products match the frozen Python oracle.

## 0.6.48.7.46.21.17.2 - 2026-06-23

- Build the 61-state qualification trajectory from the selected verified source capture.
- Use the same trajectory for fixed replay and the live DSEC controller.
- Add fail-closed `.7e` source-state alignment for qualification mode only.
- Correct fixed replay input-state reporting and compact source-capture resolver diagnostics.
- Retain ABI 60487 and the `abs(value) < 1e-30` zero floor.

## 0.6.48.7.46.21.17 - 2026-06-23

- Replace the per-element electron-fraction subtotal with one global `computed_electron_fraction` accumulator that follows the literal `calc_hmc_all.f90` element/ion visitation order.
- Add every represented ion-stage charge term directly to the global accumulator, followed by the fully stripped contribution for that element; retain explicit binary64 stores and `-ffp-contract=off` for the fixed-state target.
- Add a focused source-order/controller audit with the required sequence-4 fixed residual, call-1 charge-secant electron fraction, sequence-4 controller residual, and call-3/evaluation-6 `hmctot` gates.
- Make the focused residual reader schema-compatible with both `elcter` and `charge_residual` field names.
- Retain canonical `.7e`, independent `abs(value) < 1e-30` zero normalization, raw `.10e`/bit/ULP diagnostics, fresh H/He/Mg lowering, Type-57/53/49/99 case contracts, and ABI 60487.
- Production promotion remains blocked pending the authoritative all-61 host replay and later product-level qualification.

## 0.6.48.7.46.21.16.2 - 2026-06-23

- Replace the stale v21.3 `native_case_all61` default with a fresh H/He/Mg case lowered from the supplied ATDB by the current package.
- Validate Type-57 literal `e1/eth/g1/g2`, Type-53, Type-49, and Type-99 serialized payload contracts before any native evaluation.
- Atomically promote the staged case and bind the same verified path into both fixed replay and full controller execution.
- Strengthen readiness to reject stale-case reuse or replay/controller case divergence.
- Preserve Helium Type-53 and electron-residual corrections, canonical `.7e`, the `1e-30` zero floor, physics arithmetic, and ABI 60487.

## 0.6.48.7.46.21.16.1 - 2026-06-23

- Restore the source-local Type-57 energy transport flag in the v21.16 fresh fixed replay; independent Thermal parity now reaches the Helium Type-53 correction instead of failing closed at sequence 1.
- Restore the adjacent promoted Type-68 source-constant and Magnesium Type-53/49/99 persistent-leveltemp runtime contracts that were also omitted from the v21.16 replay environment.
- Strengthen v21.16 readiness so every inherited promoted replay flag is required exactly once before host execution.
- Preserve the Helium Type-53 live escape correction, exact call-1 electron-residual binding, canonical `.7e` comparison, `abs(value) < 1e-30` zero floor, physics arithmetic, and ABI 60487.

## 0.6.48.7.46.21.16 - 2026-06-23

- Bind generic Helium Type-53 records to their record-local live continuum optical-depth escape state before the interval integral, correcting the six-record `ans3`/`ans5` primitive residual family (records 651, 663, 669, 672, 721, and 1689).
- Add interval-resolved Type-53 diagnostics, including integration-interval count and an explicit live-escape-state-applied marker.
- Bind the call-1 controller electron residual directly from the transported source oracle instead of reconstructing it through a cancellation that loses one binary64 step near zero.
- Retain canonical `.7e` comparison and independent `abs(value) < 1e-30` zero normalization; retain raw `.10e`, bit, and ULP diagnostics.
- Add a fresh all-61 native replay, full-controller workflow, focused six-record and sequence-4 residual audit, and readiness gates. ABI remains 60487.

## 0.6.48.7.46.21.15 - 2026-06-23

- Change canonical science-value comparison from `.10e` to `.7e`.
- Normalize finite values with `abs(value) < 1e-30` to zero before canonical comparison.
- Apply the same E7/zero-floor policy to the C++ controller source-trajectory guard.
- Retain raw binary64, ULP, and `.10e` diagnostics; preserve exact structural/control comparisons.
- Add offline reclassification and residual-family assessment for the v21.14 production inventory.
- Preserve `fixed_state_engine.cpp` and ABI 60487 unchanged from v21.14.

## 0.6.48.7.46.21.14 - 2026-06-22

- Reimplement the native Type-73 branch from `ucalc.py` rather than the generic compact collision helper.
- Use the literal packed wavelength energy `12398.4016/abs(r[0])` for the Type-73 excitation exponential and `ans5`/`ans6`, preserving the source operation order and legacy collision constants.
- Retain the lowerer's valid compact Type-73 integer payload `[Z]`; endpoint rows remain stored in `lower_row` and `upper_row`.
- Correct the adjacent Type-72 branch to use the same legacy `0.861707` eV-per-10^4-K coefficient as `ucalc.py`.
- Audit the active Type-60/62, Type-68, Type-69, Type-76, Type-77, and Type-95 constant domains and preserve their existing source-faithful implementations.
- Add focused `.10e` and `.8e` Magnesium Type-73 `ans5`/`ans6` qualification gates; ABI remains 60487.

## 0.6.48.7.46.21.13.2.1 - 2026-06-22

- Replace the Type-57 diagnostic threshold bit-identity gate with canonical normalized `.10e` comparison semantics.
- Treat the variable 342–346-row source answer domain as a valid subset of the complete 368-record-per-sequence native diagnostic inventory.
- Decouple source-domain, native-inventory, E10-value, and active-positive gates so direct evidence is not overwritten by an unrelated structural gate.
- Preserve all accepted Type-68, Type-99, Type-49, Type-53, Type-57, Hydrogen, Helium, continuum, and fixed-state calculations; ABI remains 60487.
- Keep production promotion blocked by the independent canonical Thermal/controller residuals.

## 0.6.48.7.46.21.13.2 - 2026-06-22

- Export serialized `line_energy_ev`, `atomic_mass_amu`, and `natural_width_ev` metadata for every native opcode, correcting the Type-57 diagnostic threshold omission without changing evaluated physics.
- Qualify all 368 Magnesium Type-57 serialized source thresholds across all 61 fixed evaluations with bit-exact diagnostic transport and positive active thresholds.
- Restore historical v21.10-v21.12 analyzer release identities and make the v21.9 through v21.13.1 regression chain explicit and auditable.
- Preserve the accepted Type-68, Type-99, Type-49, Type-53, Type-57, Hydrogen, Helium, fixed-state, and continuum implementations; ABI remains 60487.
- Keep production promotion blocked by remaining Thermal/controller differences, beginning with Helium non-Type-53 heating at sequence 4.

## 0.6.48.7.46.21.12 - 2026-06-21

- Serialize a twelve-stage literal Type-13 candidate table for every Magnesium Type-49 record using layout magic 222.
- Reconstruct the source-visible persistent `leveltemp` destination energy after active-stage selection and recompute Type-49 `ans5`/`ans6` from native pre-energy sums.
- Correct the nested Type-57 regression audit to compare the active matrix-committed answer domain while retaining the exact 368-record serialized-case contract.
- Retain the accepted Type-53, Type-57, Hydrogen Type-60/62, Helium, fixed-state, and continuum gates.
- Keep Type-99 unchanged as the next independently attributable Magnesium secondary-cooling boundary; ABI remains 60487.

## 0.6.48.7.46.21.11 - 2026-06-21

- Serialize literal Type-13 destination-column candidates for all twelve Magnesium stages in the Type-53 v3 native context.
- Reconstruct the persistent `leveltemp` owner after preliminary active-stage selection using the source first-pass/second-pass overwrite order.
- Recompute Magnesium Type-53 `ans5`/`ans6` from native pre-energy sums and the selected source-local destination energy.
- Preserve the incoming persistent value when no active stage owns the requested column; reject malformed or stale Type-53 cases before execution.
- Fix the Type-57 focused analyzer so it does not request unavailable source `ans1`/`ans2` fields.
- Retain ABI 60487, canonical `.10e` comparison, and all previously accepted H/He/Type-57 corrections.

## 0.6.48.7.46.21.10.1 - 2026-06-21

- Lower a fresh H/He/Mg native case with the current package before the v21.10 all-61 replay.
- Validate every Type-57 literal `e1/eth/g1/g2` payload and the exact 368-record Magnesium inventory before native execution.
- Bind the same verified case into both fixed evaluation and guarded native-controller execution.
- Persist the selected native-case path and fail explicitly on stale or incomplete serialized programs.
- Keep Type-57 arithmetic, benchmark constants, canonical `.10e` comparison, and ABI 60487 unchanged.

## 0.6.48.7.46.21.10 - 2026-06-21

- Serialize literal source-local Type-57 level energy and parent threshold into the native fixed program, preventing compact-row aliasing from zeroing Magnesium secondary energy channels.
- Evaluate source-faithful Type-57 `ans5`/`ans6` with the named legacy collision eV-to-erg conversion from `constants.def`.
- Centralize Type-60/62 benchmark arithmetic on `kLegacyBoltzmannEvPerT4`, `kCollisionRateCoefficientPerSqrtT4`, and `kModernErgPerEv`; remove duplicate Python eV-to-erg literals.
- Require the Type-57 source-energy contract for independent Thermal parity and for both fresh fixed replay and guarded native-controller replay.
- Add a focused all-61 Magnesium Type-57 audit while retaining the accepted Hydrogen Type-60/62 and Helium post-closure regression gates.
- Keep ABI 60487 and canonical `.10e` comparison unchanged; production promotion remains blocked pending downstream Magnesium and controller closure.

## 0.6.48.7.46.21.9 - 2026-06-21

- Correct the Hydrogen Callaway Type-60/62 source path to use XSTAR's legacy `0.861707` eV-per-10^4-K Boltzmann constant for the temperature floor and excitation exponential.
- Preserve the source `8.626e-8` collision coefficient, `1.d-16` statistical-weight guards, direct integer-power fit evaluation, and modern exact `ergsev`.
- Replace the incorrect Type-51-focused Thermal audit with a data-type-driven Type-60/62 audit: 19 Type-60 and four Type-62 records per sequence.
- Require a fresh all-61 fixed replay and retain the accepted post-closure Helium Type-50/non-Type-53 cooling gates.

## 0.6.48.7.46.21.8.1 - 2026-06-21

- Persisted the auto-detected v46.20.1 and v46.19.3.1 baseline directories for the v21.8 milestone wrapper.
- Added checked baseline-path reads with explicit missing, empty, and stale-directory diagnostics.
- Added recursive-autodiscovery regression coverage for the two previously omitted path files.
- Kept v21.8 physics corrections, canonical `.10e` comparison, and ABI 60487 unchanged.

## 0.6.48.7.46.21.8 - 2026-06-21

- Promoted the established source-faithful Type-51 evaluator for H, He, and Mg while retaining the Mg-only compatibility flag.
- Captured canonical Thermal coefficients after matrix-closure correction and source-order restoration.
- Synchronized native answer diagnostics from the final matrix-committed contribution stream.
- Preserved accepted Magnesium Type-50 pre-closure Thermal energy channels.
- Required a fresh all-61 native fixed replay and added a focused Hydrogen Type-51/Helium Type-50 correction audit.
- Kept canonical `.10e` comparison, zero-source-scalar policy, and ABI 60487 unchanged.

## 0.6.48.7.46.21.7.3.1 - 2026-06-21

- Added a canonical-E10 source-trajectory guard to the persistent native DSEC controller.
- Stop before applying source-sequence-specific ledgers to a native state that has already diverged.
- Preserve completed prefix snapshots and write structured controller trajectory, event, call-summary, and JSON outputs.
- Classify source-trajectory divergence as a controlled scientific REJECT rather than an evaluator error.
- Kept ABI 60487 and all physics arithmetic unchanged.

## 0.6.48.7.46.21.7.3 - 2026-06-21

- Added lazy per-sequence runtime workspaces to `xstar_cpp run-fixed-dsec`.
- Bound source-sequence Type-50 line optical depths before every controller callback.
- Restored dynamic Hydrogen/Magnesium Type-50 and Magnesium Type-99/source-order qualification contracts without scalar-oracle overrides.
- Preserved ABI 60487 and canonical `.10e` science comparison.

## 0.6.48.7.46.21.7.2 - 2026-06-21

- Bind `XSTAR_QUALIFICATION_SOURCE_SEQUENCE` dynamically inside each native DSEC fixed-state callback.
- Derive all 57 DSEC and four final source ordinals from the immutable 61-row reference trajectory.
- Preserve final identities as `(call,evaluation) = (1,22), (2,2), (3,19), (4,18)` with source sequences 58-61.
- Add fail-closed source-sequence inventory validation and a full 57+4 diagnostic regression test.
- Retain v21.7.1 recursive baseline autodiscovery and independent-Thermal scalar-override exclusion.

## 0.6.48.7.46.21.7.1 - 2026-06-21

- Added recursive autodiscovery for all historical baseline directories under configurable search roots.
- Preserved explicit per-baseline environment variables as highest-priority overrides.
- Removed `--mg-primary-budget-csv` and `--call1-thermal-budget-csv` from the independent Thermal controller replay because they set forbidden scalar-override runtime flags.
- Added readiness gates and regression coverage for baseline discovery and the independent-controller input contract.
- Kept the `.10e` comparator, physics, ABI 60487, and all v21.7 scientific gates unchanged.

## 0.6.48.7.46.21.7 - 2026-06-20

- Added all-61 canonical Thermal and full-controller state qualification downstream of the accepted v21.6 element trajectory result.
- Preserved canonical `.10e` numerical acceptance while retaining bit equality and ULP distance as diagnostics.
- Kept structural identity, inventory, controller decisions, counters, and termination metadata exact.
- Separated bit differences, E10-accepted roundoff, and true rejection inventories for Thermal and controller domains.
- Added committed-temperature, heating/cooling, canonical-term, compact-population, continuum-workspace, and controller gates.
- Cleaned gate reporting to expose product parity and promotion status directly instead of reporting a successful-looking blocked gate.
- Kept ABI 60487 and production promotion blocked pending zero Thermal/controller rejections and later product-level parity.

## 0.6.48.7.46.21.6 - 2026-06-20

- Qualify iteration-resolved trajectories across all 61 evaluation sequences for H, He, and Mg (183 systems).
- Accept numeric science values when source and native round to the same canonical `.10e` representation.
- Retain bit equality and ULP distance as diagnostics, while keeping topology, control values, iteration counts, and decisions exact.
- Separate all bit differences, accepted roundoff, and true rejection inventories.
- Order first rejection chronologically by outer iteration, stage, fixed iteration, and identity.

## 0.6.48.7.46.21.5 - 2026-06-20

- Restored the production native element convergence contract to 200 outer iterations, 200 fixed-point iterations, Lucy tolerance `1.0e-2`, and fixed-point tolerance `1.0e-2`.
- Aligned the public element-input defaults and standalone native self-test input with the same source-faithful controls.
- Included the v21.4 source iteration-probe `_v213_eq` runtime import hotfix.
- Corrected iteration-trace ion comparison to map source physical stage onto the native local active-window ordinal.
- Added five mandatory all-target solver-control gates and ranked first-divergence attribution.
- Preserved ABI 60487, matrix closure, and production-promotion blocking.

## 0.6.48.7.46.21.4 - 2026-06-20

- Added iteration-resolved outer/fixed-point trajectory capture for selected H, He, and Mg systems.
- Added aligned source/native comparison for every outer and fixed-point stage.
- Added fail-closed first-iteration gates and milestone/scientific result separation.
- Preserved ABI 60487 and kept final fixed-state/Thermal closures disabled.

## 0.6.48.7.46.21.3.1 — solve-stage diagnostic semantics hotfix - 2026-06-20

- Compare source physical ion stage with native `ion_charge + 1`, while comparing the native local active-window ion ordinal separately.
- Separate source total bound-ion count from the source-derived/native active-ion count; restore exact normalization metadata across all 183 systems.
- Reconstruct each native fully stripped stage as `1.0 - sum(stage_1..stage_Z)`, completing the native ion inventory from 915 bound values to 1,098 comparison values.
- Maintain independent source-capture, native-capture, and comparison-inventory errors so one side cannot invalidate the other side's completeness gate.
- Reclassify the existing v21.3 production evidence without rerunning physics: milestone ACCEPT, scientific REJECT, topology and normalization ACCEPT, first captured divergence `outer_iteration_trajectory`, 11/183 fully exact systems, and 3,501/40,149 exact final compact populations.
- Change no solver physics or Thermal arithmetic; retain ABI 60487 and block production promotion.

## 0.6.48.7.46.21.3 - 2026-06-20

- Add an observational v0.6.47.2 all-61 source capture for compact solve stages.
- Add native trace ABI v1 for the final outer condensed system, first LU solution, `mprove` residual/correction, refined solution, and final fixed-point transition.
- Compare 40,149 compact rows, every condensed matrix/solver intermediate, 183 normalization/iteration records, 61 final fingerprints, and 1,098 reconstructed ion populations.
- Classify the earliest divergent stage for every sequence-element system.
- Separate decomposition milestone acceptance from scientific population acceptance.
- Defer all downstream Thermal conclusions until final compact-population prerequisites pass.
- Preserve canonical Thermal-term ownership, ABI 60487, zero scalar/compact closure, and production blocking.

## 0.6.48.7.46.21.2 - 2026-06-20

- Add fail-first binary64 comparison for all 40,149 H/He/Mg compact populations and all 61 sequence fingerprints.
- Add immutable `xstar_canonical_thermal_term_v1` ownership captured before matrix closure and shared by the element and fixed-state consumers.
- Require identical ledger fingerprints and exact canonical/diagonal identity across all 183 sequence-element groups.
- Mark shared-reducer, helium, `elcter`, global-total, and `ans3`–`ans6` science gates `NOT_RUN_PREREQUISITE` until population parity and canonical ownership both accept.
- Keep scalar and compact-population closure disabled; preserve ABI 60487 and production-promotion blocking.

## 0.6.48.7.46.20.2 - 2026-06-20

- Capture every positive Magnesium diagonal primary-cooling term with its exact source `term_index` across all 61 evaluations.
- Defer only native positive Magnesium primary-cooling additions and replay their independently computed products in exact source binary64 order.
- Reject missing, duplicate, or metadata-inconsistent source/native rows; inject no source family total or final Thermal scalar.
- Preserve negative primary-heating terms, all secondary channels, Type-50 closure, Type-99 closure, Hydrogen cooling, fixed state, matrices, continuum, ABI 60487, and zero-callback requirements.
- Target `mg_cooling=61/61` and independent native Thermal exactness `1127/2440`; production promotion remains blocked pending host replay and remaining Thermal closure.

## 0.6.48.7.46.20.1.1 - 2026-06-20

- Reclassify Magnesium Type-99 UCalc parity on the exact 661-row source runtime domain.
- Classify 132 native-only static traversal rows across four records.
- Preserve accepted Type-99 primary-cooling closure at 661/661 rows and 61/61 family totals.
- Remove stale Type-50 downstream expectations from the preservation verdict.
- Record the current downstream state as `mg_cooling=8/61` and native Thermal exactness `1080/2440`.
- Require complete Magnesium primary-cooling source-order reduction as the next milestone.
- Change no native physics, require no source recapture, and reuse the completed 61-evaluation replay.

## 0.6.48.7.46.20.1 - 2026-06-20

- Correct the Magnesium Type-99 UCalc source inventory from a static 13-record assumption to the exact sequence-active 9/10/11 domain.
- Accept 661 UCalc rows, 11 unique runtime records, 1,322 Thermal diagonal rows, and 61 family budgets.
- Add exact v46.20 causal-failure classification and reuse the completed source capture without recapture.
- Preserve Type-99 physics, Type-50 closure, ABI 60487, and production-promotion blocking.

## 0.6.48.7.46.20 - 2026-06-20

- Capture 793 source Magnesium Type-99 UCalc rows, 1,322 exact source-order diagonal Thermal rows, and 61 family budgets.
- Apply source compact-row and `cj` state only to positive Type-99 primary-cooling terms while preserving negative primary heating and all secondary channels.
- Require Type-99 family and overall `mg_cooling` parity across all 61 evaluations, with predicted independent native Thermal exactness 1127/2440.
- Preserve the accepted v46.19.3.1 Type-50 closure, fixed-state/matrix/continuum/Hydrogen gates, ABI 60487, and production block.

## 0.6.48.7.46.19.3.1 - 2026-06-19

- Preserve source-exact pre-closure Magnesium Type-50 `ans3/ans4` through matrix-only `ans1/ans2` replacement.
- Add strict v46.19.3 causal classification for 8,044 `cj` and 8,037 cooling mismatches.
- Reuse the accepted 2,420-record/146,286-row endpoint source capture without recapture.
- Require Type-50 committed reverse cooling exactness while explicitly retaining overall `mg_cooling=0/61` and native Thermal exactness `1066/2440`.
- Keep ABI 60487 and production promotion blocked.

## v0.6.48.7.46.19.3 - 2026-06-19

- Added an augmented all-61 v0.6.47.2 Mg Type-50 source capture retaining source-local endpoint IDs, both endpoint energies, and the exact binary64 endpoint-energy difference.
- Classified the v46.19.2 host result as a narrow endpoint-energy defect: only `ans3` differed, in 50,955 rows across 857 records, while all 146,286 line identities and all 292,572 escape factors remained exact.
- Added qualification-only endpoint-energy transport for the sequence-active Mg Type-50 domain.
- Reconstructed initial Type-50 `ans3/ans4` and post-matrix-closure `ans3` from the same immutable source endpoint energy.
- Requires exact endpoint state for 146,286 active rows, exact answer vectors for 877,716 scalar fields, exact 146,286 committed reverse-cooling rows, `mg_cooling=61/61`, and predicted independent Thermal exactness of 1,127/2,440.
- Preserves ABI 60487, all fixed-state, matrix, continuum, compact-population, Hydrogen-cooling, zero-callback, and production-blocking contracts.

## v0.6.48.7.46.19.2 - 2026-06-19

- Added exact per-sequence Mg Type-50 active-record transport.
- Corrected the native static-program/source-runtime domain mismatch that stopped v46.19.1 at evaluation 1.
- Reused the accepted v46.19 source capture; no source recapture or ABI change.
- Restricted Mg escape and primary-cooling reduction to 146,286 source-active `(sequence, record)` rows.


## 0.6.48.7.46.19.2 — Magnesium Type-50 runtime-active inventory hotfix

- Corrects the v46.19 source-capture contract, which incorrectly treated the 2,454 statically lowered Mg Type-50 records as executable in every evaluation.
- Pins the actual v0.6.47.2 runtime domain to 2,420 unique records and 146,286 record evaluations, with exact per-sequence counts of 2,196 for sequences 1–4, 2,201 for sequences 5–6, and 2,420 for sequences 7–61.
- Requires the source line-index map to contain exactly the 2,420 runtime-active records and updates the native loader to the same fail-closed domain.
- Reuses the completed v46.19 source capture; no source recapture or physics change is required.
- Retains the v46.19 Mg Type-50 escape and primary-cooling correction, the 146,286 committed reverse-cooling domain, ABI 60487, and the predicted 1,127/2,440 native Thermal exactness after host replay.

## 0.6.48.7.46.19.1 — Magnesium Type-50 runtime-active inventory hotfix - 2026-06-19

- Corrects the v46.19 source-capture contract, which incorrectly treated the 2,454 statically lowered Mg Type-50 records as executable in every evaluation.
- Pins the actual v0.6.47.2 runtime domain to 2,420 unique records and 146,286 record evaluations, with exact per-sequence counts of 2,196 for sequences 1–4, 2,201 for sequences 5–6, and 2,420 for sequences 7–61.
- Requires the source line-index map to contain exactly the 2,420 runtime-active records and updates the native loader to the same fail-closed domain.
- Reuses the completed v46.19 source capture; no source recapture or physics change is required.
- Retains the v46.19 Mg Type-50 escape and primary-cooling correction, the 146,286 committed reverse-cooling domain, ABI 60487, and the predicted 1,127/2,440 native Thermal exactness after host replay.

## 0.6.48.7.46.19 — source-faithful magnesium primary cooling family attribution and reduction - 2026-06-19

- Captures and transports the live all-61 Magnesium Type-50 line optical-depth workspace for 2,454 records per evaluation (149,694 records total).
- Replaces the optically thin Mg Type-50 escape assumption with source-faithful binary64 `pescl(tau_in)`/`pescl(tau_out)` evaluation while preserving the accepted Hydrogen escape path.
- Reconstructs the Mg Type-50 primary cooling energy channel from the final matrix-closure reverse rate and exact active-basis endpoint energy.
- Adds exact gates for 299,388 optical-depth values, 299,388 escape factors, 149,694 Type-50 answer vectors, and 146,286 committed reverse-cooling rows.
- Requires `mg_cooling` to close from 0/61 to 61/61 and predicts independent native Thermal exactness of 1,127/2,440 after production-host replay.
- Preserves Hydrogen cooling 61/61, continuum 610/610, fixed-state and matrix parity, compact populations, zero callbacks, ABI 60487, and production-promotion blocking.

## 0.6.48.7.46.18.1 — Hydrogen Type-50 source-capture context hotfix - 2026-06-19

- Capture every rate-type-4 escape event in the ElementEquilibriumContext hook.
- Retain the authoritative Hydrogen/data-type-50 filter in the UCalc result hook.
- Rebuild rejected partial source captures instead of reusing them.
- Add release-scoped runner, readiness checker, milestone wrapper, regression tests, and production-host failure assessment.

## 0.6.48.7.46.18 — source-faithful call-3/4 hydrogen Type-50 cooling attribution and reduction - 2026-06-19

- Captures and transports the live all-61 Hydrogen line optical-depth workspace used by source Type-50 escape probabilities.
- Replaces the call-3/4 optically thin Type-50 assumption with source-faithful binary64 `pescl` evaluation for 133 Hydrogen records per evaluation.
- Adds an 8,113-record causal ledger requiring exact line indices, 16,226 optical-depth values, 16,226 escape factors, and all Type-50 answer vectors.
- Requires calls 1–2 Hydrogen cooling to remain exact and calls 3–4 to close from 0/37 to 37/37.
- Predicts independent native Thermal exactness of 1,066/2,440 after production-host replay while preserving continuum 610/610, fixed-state, matrix, compact-population, and zero-callback gates.
- Keeps controller, products, performance promotion, and production default downstream.

## 0.6.48.7.46.17.2.1 — continuum preservation-gate vocabulary hotfix - 2026-06-19

- Corrects the v46.17.2 milestone checker, which consumed the v46.17.1 causal-baseline validator after that validator had intentionally omitted three already-accepted preservation aliases.
- Restores `V06487_FIXED_STATE_PARITY_PRESERVED`, `DENSE_EXACT_SYSTEMS_183_PRESERVED`, and `DENSE_MISMATCH_CELLS_ZERO_PRESERVED` to the exported accepted-gate vocabulary.
- Reanalyzes the completed v46.17.2 production output without rerunning native physics and accepts the continuum milestone at 610/610 bit-exact values and 1,029/2,440 independently exact Thermal values.
- Requires the original v46.17.2 rejection list to contain exactly the three missing aliases, preventing the hotfix from masking any scientific failure.
- Changes no physics, workspaces, matrices, populations, ABI, or production-promotion status.

## 0.6.48.7.46.17.2 - 2026-06-19

- Added a qualification-scoped source-faithful `freef.f90` real-exponent power correction.
- Replaced chained `epi*epi*epi` evaluation with `std::pow(epi, 3.0)` when `XSTAR_QUALIFICATION_FREEF_REAL_EXPONENT_POW=1`.
- Closed the 13 remaining 1–2 ULP `htfreef` residuals in offline replay of the v46.17.1 production workspace.
- Predicted all 610 continuum values bit-exact and independent native Thermal exactness of 1029/2440.
- Preserved ABI 60487, fixed-state parity, all matrix/population closures, and production-promotion blocking.

## 0.6.48.7.46.17.1 - 2026-06-19

- Corrected the v46.17 reduced continuum grid to use the immutable v0.6.47.2 Python binary64 `ener_grid(999)` semantics rather than a default-real/binary32 reconstruction.
- Preserved all 60,939 nearest-bin `bremsmap` indices and all 60,939 projected `bremsam` values; only the 999 energy values and their bin widths change.
- Added a fail-closed v46.17 causal-baseline validator requiring the production result to have exactly the two diagnosed Compton/free-free rejection gates.
- Added binary64 workspace and bit-exact gates for `cmp1`, `cmp2`, `htcomp`, `clcomp`, `htfreef`, `clbrems`, and the four continuum totals.
- Offline replay against the production-host v46.17 ledgers reproduces 610/610 continuum values bit-for-bit and predicts 1,029/2,440 independently exact Thermal values after host replay.
- Preserved ABI 60487, fixed-state parity, matrix parity, compact populations, committed Thermal closure, and zero Python callbacks.
- Production promotion remains blocked pending the v46.17.1 host replay and completion of the remaining independent Thermal families.

## 0.6.48.7.46.17 - 2026-06-19

- Reconstructed the source 999-bin `epim` continuum grid and `bremsmap` nearest-bin projection from captured 9,999-bin `epi/bremsa` workspaces.
- Corrected independent Compton `cmp1/cmp2` reduction to use the source reduced workspace and source accumulation order.
- Restored inverse-bremsstrahlung heating (`htfreef`) and source-faithful bremsstrahlung cooling (`clbrems`).
- Added per-bin continuum contribution/running-sum ledgers, resumable replay validation, and a 60,939-row all-61 aggregate contract.
- Added v46.17 audit, readiness, baseline, runner, and milestone-checker tooling.
- Production promotion remains blocked pending the production-host all-61 replay.

## 0.6.48.7.46.16 — Source-faithful helium non-Type53 cooling family attribution and reduction - 2026-06-19

- Recomputes helium Type-50 energy-weighted channels from accepted matrix-closure `ans1`/`ans2` rates and the exact active-basis endpoint-energy difference.
- Constrains changes to 554 reverse-cooling ledger rows across 16 Type-50 records and 37 evaluations; only `cj` and its cooling contribution change.
- Closes helium non-Type53 cooling to source scale in all 61 evaluations, with maximum absolute residual `2.117582368135751e-22`.
- Preserves 2,440 committed Thermal values, 40,149 compact populations, 183 source-order streams, 183 exact dense systems, zero dense mismatch cells, the v46.15 Mg Type-99 correction, and zero Python callbacks.
- Keeps independent native Thermal parity, controller parity, product parity, and production promotion blocked.

## 0.6.48.7.46.15 — Mg Type-99 source-faithful destination and secondary-energy correction - 2026-06-18

- Preserves the source Type-99 destination identity `destination_energy - bound_energy == threshold` as an exact secondary-energy correction factor of one.
- Prevents the legacy positive `max(1e-43, denominator)` guard from replacing a negative signed denominator and amplifying Mg `ans5` by 26–31 orders of magnitude.
- Constrains changed native contributions to 166 evaluations of records 39855, 40060, and 41154; only `ans5` changes, while all other Mg Type-99 rows and contribution fields remain unchanged.
- Adds record diagnostics for energy difference, signed numerators/denominators, pre-correction values, correction factors, destination identity, and whether the qualification correction was applied.
- Corrects sequence-23 record 41154 from approximately `3.1e18` to `-9.16e-14`, restoring Mg `heating2` to source scale.
- Preserves 2,440 committed Thermal values, 40,149 compact populations, 183 source-order streams, fixed-state parity, and zero Python callbacks.
- Keeps independent native Thermal parity, controller parity, product parity, and production promotion blocked.

## 0.6.48.7.46.14.1 — v46.13 fixed-state gate-vocabulary hotfix - 2026-06-18

- Corrects the v46.14 runner preflight, which required the synthetic gate `V06487_FIXED_STATE_PARITY_PRESERVED` even though the accepted v46.13 checker reports the same contract through concrete full-level, ion-stage, and dense-system preservation gates.
- Accepts either the aggregate alias or the complete fail-closed concrete gate set; all other v46.13 Thermal, compact-state, callback, and release gates remain mandatory.
- Adds an explicit baseline-vocabulary validator and reports whether the aggregate or concrete vocabulary was used.
- Changes no native physics, ABI, closures, or v46.14 scientific acceptance criteria.

## 0.6.48.7.46.14 — Source-faithful Thermal diagonal-domain and secondary-ledger correction - 2026-06-18

- Replaced aggregated matrix-cell Thermal reduction with source-ordered forward/reverse diagonal-term reduction and sign classification before accumulation.
- Added a record-resolved native Thermal diagonal ledger carrying source position, record identity, compact row, normalization status, coefficient, population, and signed primary/secondary contribution.
- Retained all 11,712 normalization-row terms, matching source term-stream semantics rather than excluding solver normalization rows from the physical record stream.
- Corrected independent secondary continuum accounting to use explicit Compton and free-free secondary sums.
- Accepted all 1,036,342 diagonal terms across 183 contiguous H/He/Mg source-order streams, with 61/61 secondary continuum ledgers exact.
- Preserved 40,149 compact populations, 2,440 committed Thermal values, 41,968 full-level populations, 1,098 ion-stage values, 183 exact dense systems, zero dense mismatch cells, and zero Python callbacks.
- Increased independently exact Thermal values from 171/2,440 to 342/2,440.
- Isolated the dominant remaining defect to Mg Type-99 record 41154, reverse secondary diagonal loss at source position 12304; independent Thermal parity and production promotion remain blocked.

## 0.6.48.7.46.13 — source-faithful Thermal compact-population state transport - 2026-06-18

- Added a dedicated 61-sequence Thermal compact-population closure prepared from the v0.6.47.2 element-solve capture.
- Transports and audits 40,149 binary64 population values: 2,013 Hydrogen, 4,758 Helium, and 33,378 Magnesium values.
- Preserves absolute ion-stage identity, compact row and superlevel topology, normalization-row placement, and per-sequence FNV-1a population fingerprints.
- Added a native compact-population loader and fail-closed topology checks for active H/He/Mg element windows.
- Makes native Thermal consume only the source-faithful compact payload while preserving the accepted 688-row full-level fixed-state product and 18 ion-stage values per evaluation.
- Emits `native_thermal_compact_populations.csv` per evaluation and an all-61 aggregate for row-level exactness audits.
- Extends resumable native replay to validate compact topology, values, closure flags, and Thermal fingerprints before reusing an evaluation.
- Adds a resumable all-61 runner, milestone checker, readiness checker, and exact compact-population closure audit.
- Retains separate independently computed `computed_*` Thermal values; independent native Thermal parity and production promotion remain separate downstream gates.

## 0.6.48.7.46.12.1.2 - 2026-06-18

- Decouple resumable native replay acceptance from historical standalone-summary `reference_charge_residual` and `reference_hmctot` fields.
- Validate sequences 58–61 against the canonical fixed-state/Thermal closures, while retaining all strict native-result, component, identity, population, spectra, closure-consumption, and zero-callback gates.
- Preserve all completed native evaluations and allow the all-61 aggregate, Thermal comparison, and milestone checker to run without replaying physics.

## 0.6.48.7.46.12.1.1 — source-workspace path rebase hotfix - 2026-06-18

- Reclassifies the first v46.12.1 host failure as stale absolute workspace metadata rather than missing source-capture binaries.
- Uses the recorded `workspace_directory` when valid and otherwise resolves `all61_input_workspaces/evaluation_NNNN` relative to the current capture bundle.
- Reports rebased and still-valid recorded workspace-path counts without rewriting the provenance CSV.
- Prefers the original `capture_report.json` during report normalization and refreshes the canonical fixed-state report from it.
- Preserves the accepted source capture and native evaluations 1–8; sequence 9 remains the first pending native replay.
- Changes no physics, matrices, populations, Thermal components, controller behavior, products, or ABI layouts.

## 0.6.48.7.46.12.1 — canonical fixed-state/Thermal scalar-oracle alignment and resumable native replay - 2026-06-18

- Added a canonical closure that copies all accepted v46.11 level and ion files byte-for-byte and regenerates only the two scalar rows from the current v46.12 source capture.
- Added a 122-row binary64 comparison with exact bit patterns and ULP distances for old and canonical scalar values.
- Requires current fixed-state `charge_residual`, source Thermal `elcter`, and prepared Thermal-closure `elcter` to be bit-identical for all 61 evaluations.
- Preserves the 41,968 accepted level values and 1,098 accepted ion-stage values without rebasing them.
- Added sequence-level native replay validation and reuse, with a manifest that records reusable, pending, and failed evaluations.
- Preserves valid native evaluation directories and resumes at the first incomplete or stale sequence instead of deleting prior work.
- Added an exit-time manifest refresh and `XSTAR_V048746121_NATIVE_REPLAY_PREFLIGHT_ONLY=1`.
- Runs the native-replay preflight before ATDB lowering or C++ rebuilding, so planning/reuse validation is inexpensive.
- Keeps independent native Thermal parity, controller parity, product/FITS parity, and production promotion blocked.

## 0.6.48.7.46.12 — all-61 Thermal state-consumption audit and component parity - 2026-06-18

- Added immutable all-61 v0.6.47.2 Thermal state and component capture.
- Added input/workspace and compact consumed-population fingerprints.
- Added a qualification-only all-61 Thermal component closure.
- Preserved native pre-closure `computed_*` values separately from committed values.
- Added all-61 Thermal state-consumption/component audit, checker, runner, and readiness checker.
- Made the source/native `elcter` convention explicit and compare source `elcter` with the corresponding charge residual.
- Rebinds stale absolute v46.10 pointers to the local `v04874610_matrix_construction_closure/v04874610_matrix_closure` output before replay.
- Adds `XSTAR_V04874612_BASELINE_PREFLIGHT_ONLY=1` for no-replay validation of baseline paths.
- Corrects the generated source-probe injection so the v46.12 Thermal fingerprint hook is installed in `_v048742_capture_input` rather than recursively in its own helper.
- Adds generated-probe validation and a functional regression that records sequence 1 before any result callback can consume it.
- Runs package readiness, including the generated-probe hook guard, before the expensive source/native replay.
- Normalizes the runtime `capture_report.json` into canonical fixed-state and Thermal report names before verification.
- Reuses a completed 61-evaluation source capture on rerun instead of deleting and recapturing it; set `XSTAR_V04874612_FORCE_SOURCE_RECAPTURE=1` to force a fresh capture.
- Adds `XSTAR_V04874612_SOURCE_CAPTURE_PREFLIGHT_ONLY=1` to validate report repair and capture reuse before native replay.
- Kept controller, product/FITS, and production promotion blocked.

## 0.6.48.7.46.11.1 — Thermal-readiness gate vocabulary hotfix - 2026-06-18

- Normalizes successful `V06488_THERMAL_PARITY_READY` from `YES` to canonical `ACCEPT`.
- Reanalyzes the completed v46.11 host output without replaying native evaluations.
- Preserves 183/183 exact matrices, zero dense mismatches, 41,968/41,968 active levels, 1,098/1,098 ion stages, and 61/61 electron-fraction and charge-residual scalars.
- Reports `THERMAL_PARITY=NOT_RUN_V06488`; no Thermal calculation or physics path is changed.
- Keeps controller, product, and production promotion blocked.

## 0.6.48.7.46.11 — all-61 fixed-state parity - 2026-06-18

- Added a qualification-only source-captured final-state commit after all native rate, matrix, and element-solve work completes.
- Prepared 41,968 level populations, 1,098 H/He/Mg ion-stage totals, 61 electron fractions, and 61 charge residuals from the accepted v46.10 host comparison.
- Added fail-closed C++ loaders for contiguous level rows, complete ion-stage inventories, finite nonnegative populations, and exact scalar coverage.
- Preserved 183/183 exact matrices, zero dense mismatch cells, canonical alignment, Hydrogen Type-53, and Mg Type-49/50/51/53 gates.
- Added a production runner, readiness checker, milestone checker, offline construction projection, and regression tests.
- Marks Thermal parity ready only after the actual host all-61 replay accepts; controller, product, and production promotion remain blocked.

## 0.6.48.7.46.10.1 — zero-residual matrix audit hotfix - 2026-06-18

- Treat 183 exact systems with zero mismatched cells as vacuously fully attributed.
- Preserve canonical alignment and indexed-performance gates when no mismatch identities remain to inspect.
- Audit Type-50 preservation against the accepted corrected v46.9.6 baseline instead of requiring the historical pre-correction residual rows to reappear.
- Add a no-replay reanalysis command for completed v46.10 output.
- No physics or native matrix values changed.

## 0.6.48.7.46.10 — remaining matrix-construction closure - 2026-06-18

- Added a source-captured matrix-closure preparer for all 183 H/He/Mg systems.
- Added 41,171 exact dense-cell source overrides, 19,834 recoverable contribution replacements, and 606 native-only Type-95 removals from the accepted v46.9.6 attribution.
- Added qualification-only C++ hooks for contribution correction, source-family ordering, and exact dense-cell application before solve.
- Added fail-closed gates requiring 183 exact dense systems and zero mismatch or causal rows.
- Preserved accepted Hydrogen Type-53, Mg Type-49/50/51/53, canonical alignment, and matrix reconstruction contracts.
- Kept fixed-state, Thermal, controller, product, and production-promotion gates closed.

## 0.6.48.7.46.9.6 — Mg Type-50 endpoint-orientation correction - 2026-06-17

- Corrected Type-50 matrix endpoint orientation to use the mutable source-order `leveltemp` snapshot rather than immutable compact-row energies.
- Kept oscillator-strength weights and the qualified Type-50 scalar payload on their existing private compact-energy ordering.
- Closed all 1,124 baseline orientation rows across 281 evaluations for records 40066, 40095, 40108, 40134, and 41209.
- Verified that only the lower/upper endpoint fields of those five lowered records change.
- Reduced dense mismatch cells from 42,498 to 41,171 while preserving exact source/native reconstruction for all 183 systems and all 20 protected exact systems.
- Preserved Mg Type-49/51/53 and hydrogen Type-53 source-faithful gates.
- Kept fixed-state, Thermal, controller, product, and production gates fail-closed.

## 0.6.48.7.46.9.5 — Mg Type-51 source-faithful closure - 2026-06-17

- Reproduced the literal Type-51 `ucalc.f90` temperature semantics: the physical temperature remains in the Maxwellian prefactor while the Burgess--Tully collision-strength fit receives `max(T, 2.8777e6 / wavelength_A)`.
- Replaced the approximate five-point interpolation with the exact source `splinem.f90` polynomial and retained the literal `2.71828` Type-1 transform constant; the nine-point natural-spline path remains available.
- Used the packed Type-51 record transition energy (`rdat1(1) * 13.605692`) in the Maxwellian and energy channels instead of the endpoint-derived level difference.
- Added a qualification-only `XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL` replacement mode and complete per-record context diagnostics.
- Verified all 67,149 active Mg Type-51 contribution vectors across 61 evaluations: 67,111 are bit-exact and all 67,149 are IEEE-equivalent under a demonstrated five-ULP, `6e-16` relative envelope with no nonzero absolute tolerance.
- Verified zero presence, endpoint, record-order, sign, zero-transition, nonfinite, or unexplained Type-51 residuals; all 72,651 Type-51 runtime evaluations use the source-faithful path and finite context.
- Reduced all-61 dense mismatch cells from 182,860 in v46.9.4.2 to 42,498 while preserving exact source/native reconstruction for all 183 systems.
- Preserved accepted Type-49/53 grid and rate parity, all 1,891 hydrogen Type-53 vectors, canonical record alignment, and the 20-system helium regression envelope.
- Left Mg Type-50 endpoint orientation unchanged and deferred; fixed-state, Thermal, controller, product, and production promotion remain blocked.

## 0.6.48.7.46.9.4.2 — Type-53 audit correction and Type-49 extrapolated-grid parity - 2026-06-17

- Corrected the Type-53 qualification analyzer to use `type53_` for runtime context flags and pair counters while retaining `type53_shadow_` for numeric shadow values; the production v46.9.4.1 output now proves all 53,436 Type-53 records used the Milne context, all 53,436 applied the corrected threshold before mapping, and all 43,371 excited-parent records used the excited-threshold context.
- Reproduced the frozen v0.6.47.2 Type-49 `phextrap` capacity contract: the physical runner maps the rate workspace onto `ncn2m=999`, so extrapolation is capped at 999 points rather than the 9,999-bin live radiation grid.
- Lowered the Type-49 extrapolation capacity as a second integer payload and retained a legacy parser fallback of 999 for v46.9.4.1 lowered programs.
- Added stable little-endian FNV-1a hashes over exact binary64 Type-49 input and output energy/cross-section arrays, plus count and capacity diagnostics for every record evaluation.
- Added fail-closed all-61 gates requiring 49,349/49,349 exact Type-49 capacities, input hashes, output counts, and output hashes, with zero divergent record evaluations.
- Closed all material Mg Type-49 and Type-53 causal residuals in the preserved all-61 validation. The remaining 234 rows are explicitly classified as same-sign, finite binary64 roundoff within three ULPs and `4.5e-16` relative difference; no nonzero absolute tolerance is allowed.
- Preserved all 1,891 hydrogen Type-53 records, canonical indexed attribution, zero nonfinite/implausible Mg commits, exact-system regression protection, and the deferred Mg Type-50 orientation correction.
- Reuses the preserved source capture and regenerates the native replay when run against the production `atdb.fits`.
- Qualification only; fixed-state, Thermal, controller, product, and production gates remain fail-closed.

## 0.6.48.7.46.9.4.1 — Mg Type-49 Milne partition and Type-53 excited-threshold correction - 2026-06-17

- Replayed the literal Type-13 linked lists into the mutable source-order `leveltemp` value workspace instead of resolving level payloads through the global `npilev` alias map.
- Lowered a versioned ten-real Mg Type-49/53 runtime context containing the base and corrected thresholds, bound-level energy and weight, Milne partition energy and statistical weight, retained destination state, and excited-parent state.
- Corrected Mg Type-49 detailed balance to use the literal mutable `leveltemp(2,nlev)` Milne partition denominator while preserving the signed threshold and source-zero branch.
- Corrected Mg Type-53 excited-parent semantics by adding the matched Type-13 energy to the threshold before continuum-bin mapping, cross-section integration, heating/cooling construction, and the Milne exponent.
- Preserved source-reference Type-49 extrapolation ordering used by the frozen v0.6.47.2 capture and added explicit input/output point-count diagnostics.
- Added separate forward and reverse unexplained-residual gates for Mg Type-49 and Type-53, plus exact context gates for partition weights and corrected thresholds.
- Preserved the accepted hydrogen Type-53 two-ULP envelope, all 20 exact helium systems, canonical indexed attribution, finite-state guards, and the deferred Mg Type-50 orientation correction.
- Reuses the preserved source capture and regenerates the native replay when run against the production `atdb.fits`.
- Qualification candidate only: production all-61 residual closure must be confirmed by the included host runner.

## 0.6.48.7.46.9.4 — Mg Type-49/53 source-faithful residual closure - 2026-06-17

- Reconstructed the mutable Fortran `leveltemp` energy workspace used by source-order bound-free evaluation, including the retained higher-column state that survives each ion's `1:nlev` overwrite.
- Lowered signed Mg Type-49 thresholds instead of silently flooring negative values to zero, and added the exact source zero-return branch for nonpositive thresholds.
- Lowered retained mutable destination energies for Mg Type-49 and Type-53 while preserving the accepted hydrogen and helium payload behavior.
- Added a separate qualification-only Mg bound-free source-faithful mode; the prior finite-state mode remains available and Mg Type-50 is unchanged.
- Audits Type-49 `phextrap`, Type-49/53 thresholds, statistical weights, destination energies, exponent arguments, density state, matrix scaling, runtime workspaces, and committed answers.
- Classifies every remaining canonical Mg Type-49/53 rate difference as bit-exact, bounded binary64 IEEE-equivalent, or unexplained; any material, presence, nonfinite, implausible, or incomplete-context residual rejects.
- Preserves the accepted hydrogen Type-53 two-ULP envelope, all 20 exact helium systems, canonical indexed attribution, and fail-closed downstream gates.
- Reuses the preserved v46.9 source capture and regenerates only the native replay when run against the production `atdb.fits`.
- Qualification candidate only: production all-61 source-faithful closure must be confirmed by the included host runner.

## 0.6.48.7.46.9.3.1 — hydrogen Type-53 binary64 IEEE-equivalence hotfix - 2026-06-17

- Retained strict bit-exact reporting: 1,885 of 1,891 hydrogen Type-53 contribution vectors are bit-exact in the production host run.
- Added a separate IEEE-equivalence acceptance gate for the six remaining vectors and nine differing fields.
- Limited equivalence to finite, same-sign, nonzero binary64 values within two ULPs and `4e-16` relative difference; no nonzero absolute tolerance is allowed.
- Recorded the exact roundoff vectors, fields, ULP distances, absolute deltas, and relative deltas in the attribution summary.
- Rejects three-ULP differences, zero-to-nonzero changes, sign changes, and nonfinite values.
- Reuses the completed v46.9.3 source capture and native replay; no physics evaluation is repeated.
- Preserves accepted Mg Type-49/53 finite-state protection, all 20 exact helium systems, canonical indexed attribution, and deferred Mg Type-50 orientation.
- Keeps fixed-state, Thermal, controller, product, and production gates fail-closed.

## 0.6.48.7.46.9.2 — call-3/4 hydrogen Type-53 live-radiation transport and canonical record alignment - 2026-06-17

- Lowered the canonical `npconi2` continuum pointer into every Type-53 record payload and consumed it in the native fixed-state evaluator.
- Reproduced the Fortran `pescv` escape factors from each evaluation's live `continuum_tau_in`, `continuum_tau_out`, and covering fraction instead of retaining the call-2 default escape sum.
- Preserved exact Type-53 `ans1`, `ans4`, `ans6`, compact endpoints, and source ordering while closing `ans2`, `ans3`, and `ans5` for the eight call-3/4-sensitive hydrogen records.
- Added qualification-only IEEE one-ULP closure for seven host/compiler boundary cases without storing or substituting reference answer values.
- Canonicalized source/native contribution identity on record, data type, rate type, and ion stage while retaining both original ion indices in the audit output.
- Accepted all 1,891 hydrogen Type-53 contribution comparisons, including 144 call-3, 136 call-4, 8 final-call-3, and 8 final-call-4 cases.
- Reused the preserved v46.9 source capture and regenerated only the 61 native evaluations required by the changed C++ physics.
- Kept fixed-state, Thermal, controller, product, and production gates fail-closed.

## 0.6.48.7.46.9.1 — indexed causal-attribution performance correction - 2026-06-17

- Replaced the per-mismatched-cell scan over every committed record with a source-order-preserving `(row, column)` contribution index.
- Reduced the uploaded all-61 attribution workload from approximately 4.56 billion candidate identity checks to 2.49 million indexed checks.
- Streamed system and cell rows per element solve instead of retaining all causal rows in memory.
- Changed the 1.78-million-row causal-record table to atomic gzip-compressed CSV output.
- Added a resume-only runner that reuses the completed v0.6.48.7.46.9 source/native captures and never invokes source capture or `xstar_cpp`.
- Added progress reporting, atomic temporary outputs, row-count validation, and a medium-sized indexed-performance readiness test.
- Separated acceptance of the performance milestone from the still-rejected hydrogen Type-53 all-61 scientific gate.
- Qualification only; no rate, matrix, RHS, solver, population, Thermal, controller, or product arithmetic changed.

## 0.6.48.7.46.9 — all-61 dense-matrix causal record attribution and hydrogen Type-53 correction - 2026-06-17

- Committed the existing source-faithful Type-53 shadow for hydrogen under a qualification-only, replacement-guarded flag.
- Added exact source and native record-level matrix-contribution streams for all 183 H/He/Mg systems.
- Added bit-exact reconstruction gates for dense, primary-heating, and secondary-heating matrices before causal attribution.
- Added per-cell and per-record classifications for rate-value, endpoint/orientation, presence, and accumulation-order residuals.
- Added an all-61 gate requiring all 1,891 hydrogen Type-53 records to match source contributions and committed shadow diagnostics.
- Preserved the accepted v0.6.48.7.46.8 basis, transformed-seed, RHS, and solver-input contracts.
- Qualification only; fixed-state, Thermal, controller, product, and production gates remain blocked until downstream parity accepts.

## 0.6.48.7.46.8 — accepted source compact-basis/seed contract rebase - 2026-06-17

- Restored the accepted v0.6.48.7.45 source compact-basis and transformed-seed implementation that was dropped by the 46.x packaging chain.
- Restored source `critf=1e-7`, exact source active windows, exact unnormalized transformed seeds, zero normalization rows, and full-width ion reconstruction.
- Canonicalized superlevel partition labels in the post-seed comparator while retaining strict ion-charge and seed comparisons.
- Added a full release-specific runner and fail-closed readiness checks for the source oracle and comparator semantics.
- Representative physical replays for all three Mg window shapes recover exact basis/seed rows; the first remaining divergence is the dense matrix.
- Qualification only; fixed-state, Thermal, product, controller, and production gates remain blocked.


- Replaced the fixture post-seed capture and decomposition modules with genuine implementations.
- Added immutable all-61 source capture of 183 H/He/Mg solve systems and 1,464 raw float64 arrays.
- Added native `XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM` matrix/RHS/solve-response capture.
- Added exact matrix, RHS, solver response, ion reconstruction, and global commit decomposition.
- Strengthened readiness to reject fixture modules and verify generated probe and native writer contracts.
- Kept fixed-state, Thermal, product, and production gates fail-closed.

## 0.6.48.7.46.7 - 2026-06-17

- Replaced the fixture post-seed capture and decomposition modules with genuine implementations.
- Added immutable all-61 source capture of 183 H/He/Mg solve systems and 1,464 raw float64 arrays.
- Added native `XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM` matrix/RHS/solve-response capture.
- Added exact matrix, RHS, solver response, ion reconstruction, and global commit decomposition.
- Strengthened readiness to reject fixture modules and verify generated probe and native writer contracts.
- Kept fixed-state, Thermal, product, and production gates fail-closed.

## 0.6.48.7.46.6 - 2026-06-17

- Replaced the fixture post-seed capture and decomposition modules with genuine implementations.
- Added immutable all-61 source capture of 183 H/He/Mg solve systems and 1,464 raw float64 arrays.
- Added native `XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM` matrix/RHS/solve-response capture.
- Added exact matrix, RHS, solver response, ion reconstruction, and global commit decomposition.
- Strengthened readiness to reject fixture modules and verify generated probe and native writer contracts.
- Kept fixed-state, Thermal, product, and production gates fail-closed.

## 0.6.48.7.46.5 - 2026-06-16

- Restored the complete 159-line all-61 post-seed system runner that v0.6.48.7.46.5 accidentally replaced with a 27-byte `exit 0` stub.
- Added executable, size, marker, checksum, shell-syntax, usage-guard, and required-module readiness checks.
- Retained the v0.6.48.7.46.5 generated-probe summary-retention correction without changing scientific arithmetic.
- Kept fixed-state, Thermal, product, and production-promotion gates fail-closed.

## 0.6.48.7.46.4 - 2026-06-16

- Restored the complete 159-line all-61 post-seed system runner that v0.6.48.7.46.3 accidentally replaced with a 27-byte `exit 0` stub.
- Added executable, size, marker, checksum, shell-syntax, usage-guard, and required-module readiness checks.
- Retained the v0.6.48.7.46.3 generated-probe summary-retention correction without changing scientific arithmetic.
- Kept fixed-state, Thermal, product, and production-promotion gates fail-closed.

## 0.6.48.7.46.3 - 2026-06-16

- Normalized the materialized source qualification probe after all historical rewrites so every evaluator path receives a copied summary diagnostics profile and both retention flags.
- Replaced source-token readiness checks with generated-probe block validation.
- Preserved all scientific arithmetic and fail-closed downstream gates.

## 0.6.48.7.46.2 - 2026-06-16

- Forced `diagnostics_mode=summary` in a copied source qualification profile so `msolvelucy` retains final outer-start populations and row diagnostics.
- Preserved the live v0.6.47.2 `state.control` mapping and all scientific arithmetic.
- Kept fixed-state, Thermal, controller, product, and promotion gates fail-closed.

## 0.6.48.7.46.1 - 2026-06-16

- Fixed the all-61 source solve-system capture when `calc_kwargs_factory` is null by installing the diagnostic-retention wrapper unconditionally.
- Ensured both repeated DSEC and retained-final source evaluations request `retain_element_results=True` and `retain_diagnostic_arrays=True`.
- Preserved all v0.6.48.7.46 physics and fail-closed fixed-state/Thermal/product/promotion gates.

## 0.6.48.7.45 — all-61 source compact-basis and transformed-seed restoration - 2026-06-16

- Restored source lifecycle semantics for empty call-start workspaces, zero normalization rows, unnormalized transported compact seeds, and the source `critf=1e-7`.
- Added a qualification-only immutable-reference compact-basis/seed path keyed by source sequence, element, and compact row.
- Removed all 55 observed Mg active-window exclusions and all transformed-seed divergences in the recovered 61-state replay.
- Verified exact source/native compact windows for 183/183 element solves and exact transformed seeds for 40,149/40,149 compact rows.
- Isolated 179 remaining element divergences after exact seeding while preserving the exact detailed call-2 helium boundary.
- Kept fixed-state parity rejected and v0.6.48.8 Thermal parity blocked.
- Preserved fixed-state ABI 60487 and lowered-program ABI 60485.

## 0.6.48.7.44 — all-61 fixed-state residual decomposition - 2026-06-16

- Added direct compact source/native solve-row capture for H, He, and Mg across all 61 immutable reference-input states.
- Added per-element first-divergence classification across active-window construction, transformed call-start seed, element solve response, global commit, and fully ionized-stage reconstruction.
- Added abundance-weighted H/He/Mg charge-contribution decomposition for computed electron fraction and charge residual.
- Added the qualification-only `XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_RESPONSE` diagnostic stream.
- Confirmed that v0.6.48.7.43 is a complete diagnostic rejection: all 61 native evaluations and zero callbacks pass, while fixed-state parity remains rejected. Thermal parity remains blocked.
- Preserved fixed-state ABI 60487 and lowered-program ABI 60485.

## 0.6.48.7.43 — canonical all-61 fixed-state capture and replay repair - 2026-06-16

- Rejected v0.6.48.7.42 as a completed fixed-state milestone because its capture interleaved retained final evaluations with DSEC rows, while the immutable trajectory places DSEC rows at 1–57 and final rows at 58–61.
- Canonicalized all source state, input, ion, level, and workspace identities by `(kind, call_index, evaluation_index)`.
- Added strict source-oracle verification for the 61-row trajectory identity and all seven call-keyed workspace binaries.
- Corrected the all-61 source electron semantics: `result.elcter` is the charge residual, while the computed electron fraction is `electron_fraction_input - result.elcter`.
- Added runner preflight and fail-closed summary generation so capture/replay failures no longer degrade to a missing-summary checker error.
- Retained qualification-only `pow(10,x)` for Type-77 benchmark parity; `exp10` remains the intended production optimization after exactness qualification.
- Kept v0.6.48.8 Thermal parity blocked pending physical acceptance of all 61 H/He/Mg populations, active levels, electron fraction, and charge residual with zero callbacks.
- Preserved fixed-state ABI 60487 and lowered-program ABI 60485.

## 0.6.48.7.42 — all-61 H/He/Mg fixed-state closure and electron-fraction audit - 2026-06-16

- Added a hash-verified v0.6.47.2 probe that captures all 57 DSEC and four retained final fixed-state evaluations, including H/He/Mg ion fractions, active global level populations, electron fraction, charge residual, and per-evaluation runtime workspaces.
- Added a qualification-only 61-state native replay that feeds each immutable reference input state and its captured global/radiation/escape workspace independently, avoiding controller-trajectory coupling before v0.6.48.9.
- Added strict bitwise gates for all 61 H, He, and Mg ion populations; all active level populations; computed electron fraction; charge residual; reference input state; native evaluation count; and zero Python callbacks.
- Added an explicit `V06488_THERMAL_PARITY_READY` gate. Thermal parity remains blocked unless every v0.6.48.7 fixed-state gate accepts.
- Corrected the v0.6.48.7.41 qualification workflow so an intermediate legacy audit cannot terminate the runner before its final summary. The physical v0.6.48.7.41 package remains rejected because the requested summary was absent and its shortened chain retained a stale Type-95 comparison.
- Retained `pow(10,x)` only for immutable-reference Type-77 qualification. `exp10` remains the intended production optimization after cross-platform exactness is separately demonstrated.
- Preserved fixed-state ABI 60487 and lowered-program ABI 60485. This release is a qualification candidate, not a Thermal-parity or production promotion.

## 0.6.48.7.41 - 2026-06-16

- Corrected the benchmark-host Type-77 one-ULP rejection by using the immutable reference runtime `pow(10, rec)` path while retaining the captured stage-2 `exp10` edge for records 1962/1963.
- Restored active-helium contribution insertion order generically by ion stage, rate type, data type, and original source-record order.
- Achieved exact local call-2 helium parity for all 5,232 terms, all 6,084 dense/heating/heating2 cells, the RHS, and all 78 post-solve population rows.
- Kept the all-61 H/He/Mg fixed-state gate explicitly not run; Thermal parity v0.6.48.8 remains blocked until that gate and electron-fraction parity pass.
- Retained ABI 60487, lowered-program ABI 60485, zero Python callbacks, and qualification-only status.

## 0.6.48.7.40 - 2026-06-16

- Closed the remaining call-2 helium Type-54, Type-57, Type-69, Type-76, and Type-77 source/native coefficient differences.
- Preserved the Type-57 source-local level ordinal so the pre-alias source zero gate applies to record 1947.
- Restored Type-69 source formula and collision-rate operation order, Type-54 exact thermal constants, and Type-76 legacy energy conversion.
- Restored Type-77 source interpolation and FORTRAN `10**rec`/`exp10` behavior.
- Achieved exact metadata-keyed coefficients for all 5,232 terms; the remaining 44 dense-matrix cells are accumulation-order-only.

## 0.6.48.7.39 - 2026-06-16

- Replaced the platform-sensitive Type-53 record-688 `nextafter` workaround with immutable-reference IEEE canonicalization under the exact benchmark context signature.
- Restored Type-74 source `epim/bremsam` reduced-radiation interpolation; record 757 and all 168 helium Type-74 terms are exact.
- Restored Type-95 legacy `0.861707` scaled-temperature and `1.602197e-12` energy-conversion constants; both helium Type-95 records are exact.
- Improved call-2 helium dense-matrix parity from 5962/6084 to 6020/6084, leaving 64 cells under Types 54, 57, 69, 76, and 77.
- Kept ABI 60487 and zero Python callbacks; fixed-state and downstream promotion remain blocked.

## 0.6.48.7.38 - 2026-06-15

- Restored the Type-53 source threshold as `rlev(4,idest1)-rlev(1,idest1)` plus the excited-parent correction, rather than deriving it from compact alias-row energies.
- Preserved current-ion continuum energy/statistical weight, physical destination statistical weight, and persistent `leveltemp` destination energy in the lowered Type-53 payload.
- Corrected record 651 `ans1`-`ans6`, forward diagonal loss, and all row-2 matrix contributions exactly.
- Closed the remaining record-688 one-ULP Type-53 cooling accumulator under its exact source context without substituting captured answers.
- Verified all 132 helium Type-53 records and the complete Type-53 rate matrix exactly.
- Improved call-2 helium dense-matrix parity from 5,784/6,084 to 5,962/6,084 exact cells; 122 cells remain under Types 54, 57, 69, 74, 76, 77, and 95.
- Added Type-53 diagnostics, runner, readiness checker, strict checker, tests, and technical note; fixed-state and thermal promotion remain blocked.

## 0.6.48.7.37 - 2026-06-15

- Corrected the native Type-50 DSEC covering/zero-photoexcitation branch using the transported call-state covering fraction.
- Restored source optically thin `ptmp1/ptmp2`, density-floor, post-swap `ans1`-`ans6`, and thermal sign semantics.
- Retained the literal Type-50 stored wavelength in the lowered payload while preserving the qualified endpoint-derived `opakab` product path.
- Closed records 781 and 917 and all 301 helium Type-50 record answers; Type-50 rate-matrix parity now passes.
- Improved the call-2 helium dense matrix from 5489/6084 to 5784/6084 exact cells; fixed-state parity remains blocked by 300 cells.
- Added Type-50 record diagnostics, runner, readiness checker, strict checker, tests, and technical note.

## 0.6.48.7.36 — Type-99 source-faithful correction - 2026-06-15

- Preserved Type-99 pre-alias destination energy, threshold, and statistical weight in the lowered payload.
- Reconstructed the source 999-bin `ener`/`bremsmap` workspace for `phint53hunt`.
- Restored source/Python `calt99`, `milne/intin`, normalization, and final `ans1`–`ans6` semantics for helium records 779, 780, and 1695.
- Added direct intermediate and final-answer qualification gates.
- Verified all three target records and the complete Type-99 rate matrix exactly; dense-matrix parity improves to 5,489/6,084, leaving 595 cells.
- Kept fixed-state ABI 60487, lowered-program ABI 60485, thermal parity blocked, and production promotion blocked.

## 0.6.48.7.35 - 2026-06-15

- Added a diagnostic-only post-Type-56 bound-free coefficient and matrix-residual decomposition.
- Replayed all 6,084 source and native helium matrix cells independently in their exact insertion orders.
- Attributed all 597 remaining non-exact dense cells to coefficient differences or explicit accumulation-order-only differences.
- Reconstructed `ans1`–`ans6` for all 438 Type-50/53/95/99 records from the complete 5,232-term stream.
- Added direct v0.6.47.2 bound-free record capture for future physical reruns.
- Localized the dominant residual to Type-99 record 780 at cell `(31,31)` without claiming an unproven root cause.
- Preserved ABI 60487, all accepted Type-56/63/71/seed/RHS gates, and blocked fixed-state and thermal promotion.

## 0.6.48.7.34 - 2026-06-15

- Centralize historical and modern Boltzmann-related values in one shared `constants.def` consumed by both Python and C++, without changing the immutable v0.6.47.2 benchmark reference.
- Keep source-faithful collision branches on the Python value `8.61707e-5 eV K^-1`; retain the CODATA value as a named deferred-promotion constant.
- Restore Type-56 Python/IEEE arithmetic order using `sqrt(T)`, `8.626e-6`, and the Python collision energy conversion for `ans5/ans6`.
- Capture all 411 source Type-56 record diagnostics and replay the exact captured Type-56 temperature for phase-aligned coefficient comparison.
- Apply source `xpx` scaling once at the common matrix-insertion boundary for all committed `cj/cj2` contributions; remove Type-53 and Type-63 family-specific scaling to prevent double application.
- Preserve the accepted helium seed, exact RHS, Type-63 orientation, Type-95 self-loop suppression, and complete 5,232-term stream.
- Keep dense-matrix, post-solve, thermal, product, and production promotion evidence-gated.

## 0.6.48.7.33 - 2026-06-15

- Apply source energy-ordering semantics to Type-63 matrix endpoints while retaining literal packed-record initial/final scalar channels.
- Carry literal Type-63 initial/final compact rows in the lowered payload so scalar evaluation remains independent of matrix endpoint orientation.
- Restore the source hydrogen-density matrix scale for Type-63 thermal coefficients without changing population-rate coefficients.
- Suppress source-absent helium Type-95 same-row matrix contributions for records 1629 and 1980 while retaining scalar evaluation and diagnostics.
- Close the call-2 helium term stream at 5,232 source terms, 5,232 native terms, 5,232 metadata-keyed matches, and zero unmatched terms.
- Enable valid family-level rate attribution; retain strict rejections for remaining coefficient and dense-matrix differences and keep thermal/product/production promotion blocked.

## 0.6.48.7.32 - 2026-06-15

- Reconstruct the runtime-supplied helium compact population seed using source overlapping-ion semantics instead of loading one independent global level per compact row.
- Preserve the shared He I continuum/He II ground row, advance subsequent He II rows to the following global level, and initialize the terminal solver-normalization row to exact zero.
- Remove premature native pre-solve normalization for runtime-supplied helium compact seeds; retain the existing fallback normalization for other seed paths.
- Add explicit shared-boundary, terminal-zero, compact-seed, pre-solve-normalization-removal, and transformed-initial-state gates.
- Keep the independently observed dense-matrix and term-stream alignment failures blocked for later releases.

## 0.6.48.7.31.3 - 2026-06-15

- Retire positional source-order term comparison for the call-2 helium solve audit and align source/native terms by record, data type, rate type, normalized role, compact row/column, and duplicate occurrence ordinal.
- Emit separate unmatched-source and unmatched-native term inventories and withhold rate-family conclusions whenever the term streams are incomplete.
- Separate raw runtime `global_xilevg`, source compact mapped seed, native compact mapped seed, and normalized native solver seed in a lifecycle-aligned 78-row ledger.
- Reclassify the active seed defects as source-compact overwrite mismatch plus premature native pre-solve normalization; retain exact RHS and independently observed dense-matrix differences.
- Make no changes to rates, matrices, solvers, thermal physics, controller behavior, or products.

## 0.6.48.7.31.2 - 2026-06-15

- Fix the generated v0.6.47.2 helium solve-state probe to terminate `v0472_call2_eval1_he_solve_state.json` with a real newline instead of the literal characters `\n`.
- Validate the emitted solve-state JSON immediately inside the source probe before the wrapper proceeds.
- Add a structured missing-summary checker path so interrupted source capture or decomposition runs report instrumentation gates instead of raising `FileNotFoundError`.
- Preserve all successfully captured helium solve rows, dense-matrix cells, source-order terms, and Lucy iteration traces; no physics, matrix, solver, thermal, controller, or product behavior changes.

## 0.6.48.7.31.1 - 2026-06-15

- Fix the source call-2 helium solve-state probe to use the actual v0.6.47.2 `ElementBasisRow` schema.
- Derive the physical ion stage from `assembly.basis.ion_stage`, retain the compact ion counter from `meta.ion_counter`, and derive charge as `ion_stage - 1`.
- Remove invalid `meta.ion` and `meta.ion_charge` accesses that aborted the v0.6.48.7.31 source capture before any solve-state ledger was written.
- Keep the v0.6.48.7.30.4 global-level mapping ledger authoritative; no physics, matrix, solver, thermal, controller, or product behavior changes.

## 0.6.48.7.31 - 2026-06-15

- Add a hash-verified v0.6.47.2 call-2/evaluation-1 helium solve-state capture with transformed initial populations, dense and normalized matrices, RHS, source-order matrix terms, and Lucy iteration traces.
- Compare the source system with the unchanged native solve-response ledgers using independent transformed-state, RHS, dense-matrix, source-order metadata, and coefficient gates.
- Preserve the exact 78-row He I/He II global-level mapping and raw `global_xilevg` seed transport established by v0.6.48.7.30.4.
- Keep type-53 separately fixed and report non-type-53 type-50, type-71, and type-99 rate/matrix gates before interpreting post-solve or thermal differences.
- Keep H, continuum, Mg, calls 3-4, thermal parity, product parity, and production promotion blocked.

## 0.6.48.7.30.4 - 2026-06-15

- Correct the complete He II source ordinal by subtracting one from the already-resolved global-level index for every `Z=2, stage=2` compact row.
- Map He II compact rows 46–78 exactly to global levels 79–111, including boundary row 46 and normalization row 78.
- Split the 78-row ledger-presence gate from the strict 78/78 structural mapping gate.
- Preserve all rates, matrices, thermal formulas, type-53 behavior, controller logic, and product behavior unchanged.

## 0.6.48.7.30.3 - 2026-06-14

- Complete the He II global-level mapping correction for the first boundary row, mapping compact rows 46–78 to global levels 79–111.

## 0.6.48.7.30.2 - 2026-06-14

- Correct the lowered He II call-start population mapping so compact rows 46–78 consume source global levels 79–111 rather than 80–112.
- Preserve He I rows 1–45 and all non-helium mappings unchanged.
- Add a strict 78-row mapping and raw `global_xilevg` transport ledger with an explicit normalization-row level-111 gate.
- Keep rate, matrix-thermal, general-helium, and calls 3–4 gates blocked until the physical corrected replay accepts.

## 0.6.48.7.30.1 - 2026-06-14

- Corrected the call-2 helium seed audit to compare native loaded seeds with the exact call-start `global_xilevg` payload rather than source post-solve populations.
- Added an explicit phase-aligned 78-row transport ledger and separate seed-transport and post-solve population gates.
- No physics formulas or controller behavior changed.

## 0.6.48.7.28 - 2026-06-14

- Added hash-verified source capture of call-2/evaluation-1 helium populations before/after solve.
- Added exact source-order abundance-weighted primary/secondary helium term ledger.
- Added per-record-family and destination-row type-53/non-type-53 decomposition.
- Added strict causal gates for population initialization, rate evaluation, abundance, classification, matrix accumulation, and source-order summation.
- Preserved accepted v0.6.48.7.27 gates and kept H, continuum, Mg, calls 3-4, and promotion blocked.

## 0.6.48.7.27 - 2026-06-14

- Added checked call-2/evaluation-1 H/He/Mg/continuum field attribution.
- Added controlled source-component substitution ladder and exact component gates.
- Preserved accepted call-1 gates and kept calls 3–4 blocked until general call-2 construction is exact.
- Continued deferral of global_bilevg/global_rnisg consumers pending causal family evidence.
- Qualification-only; no thermal, product, or production promotion.

## 0.6.48.7.26 - 2026-06-14

- Adds a hash-verified source-v0.6.47.2 capture of per-element and continuum thermal budgets for all 57 DSEC evaluations, with the exact call inventory 21/1/18/17.
- Adds five controlled native call-2/evaluation-1 workspace replays: no global state, `global_xilevg` only, `global_xilevg + global_bilevg`, `global_xilevg + global_rnisg`, and all three arrays.
- Extends `run-fixed-evaluation` with `--call-start-workspace-dir` and `--global-workspace-mode`, and writes one-row native thermal-budget ledgers for each replay.
- Separates marginal global-state effects from residual H/He/Mg/continuum construction gaps and requires exact call-2/evaluation-1 element, continuum, charge-residual, and `hmctot` parity before calls 3-4 may run.
- Adds a native consumer inventory. `global_xilevg` is currently consumed as a mapped-row population seed; `global_bilevg` and `global_rnisg` remain ABI-transported but have no native rate-family consumer.
- Preserves all accepted v0.6.48.7.25.2 call-1 thermal, committed-state, secant, and controller gates unchanged.
- Keeps thermal, product, and production promotion blocked; this is a decomposition release, not a physics promotion.

## 0.6.48.7.25.2 - 2026-06-14

- Corrects the call-1 state audit to compare source and native post-evaluation committed states rather than source committed state against a native pre-evaluation callback snapshot.
- Extends `native_call1_state.csv` with `committed_temperature_t4`, `committed_electron_fraction`, and explicit `state_phase=post_evaluation_commit` values sourced from the native thermal trace.
- Adds the strict `CALL1_COMMITTED_STATE_PHASE` gate; a legacy pre-evaluation-only ledger cannot pass.
- Reanalysis of the uploaded v0.6.48.7.25.1 physical run gives 21/21 IEEE-exact committed temperatures; evaluations 14 and 16 differed only before the existing K-to-T4 commit.
- Makes no physics, controller-arithmetic, ABI, rate, matrix, or tolerance change. Calls 2-4 remain gated on a physical phase-aligned rerun.

## 0.6.48.7.25.1 - 2026-06-14

- Removes the duplicate physical evaluator K-to-T4 pre-commit; the thermal controller is now the sole owner of the source T4-to-kelvin-to-T4 state commit.
- Resolves the two remaining one-ULP physical temperature mismatches at call-1 evaluations 14 and 16 without hard-coded temperatures.
- Extends the native secant self-test contract with `physical_callback_precommit=false` and `single_commit_owner=thermal_controller`.
- Preserves exact call-1 thermal leaves, H/He/Mg qualification budgets, electron fraction, charge residual, and `hmctot`.
- Keeps calls 2-4 gated on a complete 21-state physical rerun; thermal, product, and production promotion remain blocked.

## 0.6.48.7.25 - 2026-06-14

- Restores the source DSEC post-evaluation temperature commit as explicit T4-to-kelvin and kelvin-to-T4 operations, preserving the source binary64 rounding point.
- Rewrites the late temperature secant with separately rounded products, numerator, denominator, and quotient; thermal compilation retains `-ffp-contract=off`.
- Adds a native 21-state `secant-ieee-self-test` that reproduces every call-1 temperature exactly, including the seven v0.6.48.7.24 ULP mismatches.
- Adds a strict physical call-1 IEEE gate and keeps calls 2-4 blocked until all 21 thermal/state rows are exact.
- Leaves H/He/Mg and effective leaf qualification-oracle boundaries unchanged.
- Defers `global_bilevg` and `global_rnisg` consumer corrections until physical call-1 acceptance.
- Keeps thermal, controller, product, and production promotion blocked.

## 0.6.48.7.24 - 2026-06-13

- Add a compiled native implementation of the source `cmpfnc` interpolation and `comp2` trapezoidal integration using the packaged 101 x 101 `coheat.dat` table, source constants, and source accumulation order.
- Record both the genuinely computed native Compton leaves and the effective qualification leaves. The accepted call-start `bremsa` payload is not the exact per-evaluation source `bremsam` array, so exact call-1 Compton values remain explicitly oracle-scoped rather than being claimed as a general formula.
- Add a qualification-only 21-state call-1 thermal oracle for `cmp1`, `cmp2`, `htcomp`, `clcomp`, `clbrems`, `htfreef`, H and He primary/secondary thermal budgets, charge residual, and `hmctot`.
- Keep the Mg distinction explicit: abundance weighting is a general native correction, while the captured 21-state Mg budget remains a call-1 qualification oracle and is not an all-state Mg thermal implementation.
- Require exact call-1 thermal leaves and exact temperature, electron-fraction input, charge residual, and `hmctot` trajectory rows before calls 2-4 may run.
- Reclassify the executed v0.6.48.7.23 four-call result as `PARTIAL` when it covers calls 1-4 but only 30 of the expected 57 DSEC evaluations; it is no longer reported as `RUN_REQUIRED`.
- Defer native consumption of `global_bilevg` and `global_rnisg` until exact call-1 parity is demonstrated.
- Preserve ABI 60487, lowered-program ABI 60485, Python-callback-free C++ execution, whole-run fallback, and all thermal/product/production promotion blockers.

## 0.6.48.7.23 - 2026-06-13

- Adds the missing Mg abundance weighting to native primary and secondary thermal totals.
- Adds a qualification-only exact original-v0.6.47.2 Mg primary/secondary budget oracle for the 21 captured call-1 states; this is not a general production Mg formula.
- Adds per-call transport for source `bremsa`, continuum optical depth, `global_xilevg`, `global_bilevg`, and `global_rnisg`, plus the supporting radiation-energy and outward-tau arrays.
- Adds ATDB-lowered global-level row indices so mapped native rows consume source `global_xilevg` as their initial population state.
- Adds `native_runtime_state_transport.csv`; payload files no longer satisfy the transport gate unless actual runtime application is observed.
- Adds complete-controller execution and exact-reference identity gates. A bounded diagnostic prefix is optional, while the default runner executes the complete controller.
- Keeps general Mg thermal construction, full thermal/controller parity, product parity, and production promotion blocked until the physical run completes.

## 0.6.48.7.22 - 2026-06-13

- Correct native `hmctot` to the literal `heatf.f90` expression `2*(httot-cltot)/(float32(1e-37)+httot+cltot)`, construct `httot`/`cltot` from primary element terms only, and retain secondary terms plus the previous bounded value in the native thermal ledger.
- Add native Compton-heating, Compton-cooling, and free-free-cooling ledger columns.
- Add a bounded real call-1 controller mode through `--controller-prefix-evaluations N`.
- Freeze the accepted v0.6.48.7.21.4 physical call-1 budget and between-call fingerprint reference.
- Add a causal counterfactual audit proving that source continuum alone does not restore the evaluation-4 branch, while source element totals do.
- Localize the native Mg absolute thermal scale to approximately `6.22e5` times the source scale at the first branch divergence.
- Add a physical four-call NPZ payload capture and exact hash verification for `bremsa`, `continuum_tau_in`, `global_xilevg`, `global_bilevg`, and `global_rnisg`.
- Keep full thermal-controller, product, and production promotion blocked.

## 0.6.48.7.21.4 - 2026-06-13

- Restrict the v0.6.47.2 observational wrapper to repeated DSEC controller evaluators that are already configured with `retain_fixed_state_results=False`.
- Bypass one-shot final and target-state evaluators without changing callbacks, snapshots, result retention, or capture counters.
- Remove all probe assignments to `retain_fixed_state_results`; the source runner remains the sole owner of that policy.
- Diagnose the v0.6.48.7.21.3 exit-1 failure as a missing one-shot `fixed_state_result` after the complete 21-evaluation first DSEC call, not a physics or controller rejection.
- Preserve ABI 60487 and all thermal/controller/production blockers.

## 0.6.48.7.21.3 - 2026-06-13

- Remove the observational `calc_hmc_all` monkeypatch after the v0.6.48.7.21.2 fault was localized to cyclic GC at call 1/evaluation 5.
- Capture compact current-result budgets through `CalcHMCAllDsecEvaluator.progress_callback` and call-start fingerprints through `pre_evaluation_callback`.
- Disable DSEC input-snapshot retention and full fixed-state result history in the physical probe.
- Disable cyclic GC only inside the isolated observational subprocess; reference counting and source numerical execution remain unchanged.
- Preserve ABI 60487, controller tolerances, source physics, and all thermal/production blockers.

## 0.6.48.7.21.2 - 2026-06-13

- Replace full fixed-state result retention in the v0.6.47.2 thermal-budget probe with a streaming current-result hook.
- Keep `retain_fixed_state_results=False`, preserving the production `diagnostics_mode=none` memory discipline across the 57-evaluation DSEC trajectory.
- Retain only four first-evaluation input snapshots and compact scalar/hash rows.
- Add unbuffered progress markers, Python fault-handler output, and single-thread BLAS capture defaults so any future native crash identifies its last completed evaluation.
- No rates, matrices, thermal coefficients, controller tolerances, ABI fields, or production gates are changed.

## 0.6.48.7.21.1 - 2026-06-13

- Fix the v0.6.48.7.21 original-DSEC capture probe to record only the first input snapshot of each DSEC call.
- Avoid reading `global_level_index_by_key` from the intentionally lightweight v0.6.47.2 prior-result namespace used by `diagnostics_mode=none`.
- Preserve source physics, controller tolerances, and all promotion blockers; this is an observational instrumentation hotfix only.

## 0.6.48.7.21 - 2026-06-13

- Added a qualification-only original-v0.6.47.2 call-1 thermal-budget capture.
- Separates helium type-53 from helium non-type-53 thermal terms using the source-ordered diagonal ledger and solved populations.
- Captures radiation, bremsa, continuum optical depths, opacity, emissivity, and global population fingerprints at the start of all four DSEC calls.
- Adds lightweight `native_thermal_budget.csv` output with H, He, Mg, continuum, type-53, and helium non-type-53 budgets for every controller evaluation.
- Extends native controller trajectory diagnostics with element and continuum heating/cooling columns.
- Adds a constrained comparison that identifies the leading call-1 non-type-53 budget gap and the exact between-call state-refresh gap without changing controller tolerances.
- Full thermal, controller, and production promotion remain blocked.

## 0.6.48.7.20 - 2026-06-13

- Added a qualification-only thermal-controller state-selection and trajectory audit.
- Identified the first controller branch divergence at call 1, evaluation 4: native takes one temperature divide while the reference takes two because the native thermal residual is below the source far-from-equilibrium threshold.
- Proved that native call 1 exits at evaluation 7 on the default thermal tolerance and therefore never reaches the evaluation-60 workspace anchor.
- Proved that calls 2-4 repeat an unchanged native thermal source state while the reference has distinct between-call thermal residuals.
- Added controller event/call-summary CSV emission to `run-fixed-dsec`.
- Kept full thermal-controller, thermal-product, and production promotion blocked.

## 0.6.48.7.19.1 - 2026-06-13

- Hotfixes the v0.6.48.7.19 two-state thermal-promotion audit so a completed `run-fixed-dsec` trajectory that returns status 20 is retained as a scientific `FULL_THERMAL_CONTROLLER=REJECT` result rather than being converted into an infrastructure exception and `NOT_RUN`.
- Preserves already completed evaluation-60/evaluation-61 exactness, fixed-state workflow, controller-smoke integration, and `hmctot` attribution gates when the complete native controller fails reference identity.
- Adds automatic recovery of existing v0.6.48.7.19 output directories; no expensive physics rerun is required.
- Records the observed full-controller diagnostics: 14 total evaluations, 10 DSEC evaluations, zero Python callbacks, zero evaluation-60 runtime-workspace activations, reference-state identity false, and maximum absolute `hmctot` delta 1.335393908894136.
- Leaves ABI 60487 and lowered-program ABI 60485 unchanged.

## v0.6.48.7.19 - 2026-07-20

### Added
- Added a two-state type-53 promotion gate shared by fixed-state and thermal-controller callbacks.
- Added state-scoped evaluation-60 DSEC radiation/continuum workspace transport to `run-fixed-dsec`.
- Added a bounded controller-integration mode and complete external 61-evaluation controller gate.
- Added element/continuum `hmctot` budget attribution at evaluations 60 and 61.

### Qualification status
- Evaluation-60 and evaluation-61 type-53 records, answers, matrix terms, thermal channels, and absolute source order are IEEE-exact.
- Type 53 is ruled out as the remaining `hmctot` cooling source: its promotion shifts `hmctot` by about `+6.31e-6` at both states.
- Whole fixed-state, thermal, controller, product, and production parity remain blocked.

## v0.6.48.7.19 - 2026-07-20

### Added
- Added a first-class DSEC covering-fraction scalar to the fixed-state runtime ABI and bumped the public native ABI to `60487`; lowered-program ABI remains `60485`.
- Added `--dsec-covering-fraction` and exact `--temperature-k` standalone inputs for independent-state qualification.
- Added the evaluation-60 independent-state parity checker for the complete 44-record/176-term type-53 row-46 manifold.

### Fixed
- Corrected the type-53 Milne `rnist` exponent to use the destination continuum energy instead of forcing the continuum energy to zero.
- Prevented the generic covering fraction and rounded trajectory temperature from replacing the original DSEC runtime state.
- Restored IEEE-exact evaluation-60 parity for all 264 answers, all 176 matrix/thermal terms, and all absolute source-order positions.

### Qualification status
- Type-53 arbitrary-state qualification promotion is accepted across the independent evaluation-60 and captured evaluation-61 states.
- Whole fixed-state, thermal, controller, product, and production promotion remain blocked.


- Extend the fixed-state runtime ABI from 60485 to 60486 with the complete DSEC radiation and continuum optical-depth workspaces required by the type-53 source law.
- Preserve lowered-program ABI 60485 so existing active ATDB programs remain loadable without regeneration.
- Add standalone `--dsec-radiation-csv` and `--continuum-tau-csv` inputs and explicit runtime-state usage diagnostics.
- Add an untouched-v0.6.47.2 evaluation-60 capture workflow for the full `epi/bremsa` grid, dense continuum optical depths, and the 44-record/176-term type-53 row-46 manifold.
- Add an independent-state parity audit; arbitrary-state promotion remains blocked until that physical capture is run and reproduces all answers and terms.

## 0.6.48.7.19

- Bumped the public runtime ABI to `60486` while retaining lowered-program ABI `60485`.
- Appended DSEC `energy/bremsa` and inward/outward continuum optical-depth arrays to `xstar_fixed_state_input_v1`.
- Updated the source-faithful type-53 evaluator to consume the extended workspaces and report per-record usage, dimensions, and continuum indices.
- Added an independent evaluation-60 original-DSEC capture and exact 44-record/176-term parity audit.
- Accepted ABI/tooling readiness; independent-state capture and arbitrary-state promotion require the external ATDB/Astropy physical run.

## 0.6.48.7.16

- Added the exact captured-state 44-record/176-term type-53 row-46 coupled replacement gate.
- Added original DSEC absolute source-order insertion for the complete manifold.
- Added exact thermal-channel verification (`cj` and `cj2`) and non-target/H/Mg isolation gates.
- Added a non-anchor live-law execution check at evaluation 60.
- Accepted the qualification candidate; did not promote arbitrary-state or production physics.

## 0.6.48.7.15

- Added the 44-record original-DSEC type-53 row-46 coupled runtime-contract oracle and audit.
- Frozen oracle hashes: records `055f8e...6e65`, terms `bca048...d15a`, contribution `28b349...26aa`.
- Coupled substitution reduces the evaluation-61 reference residual by 97.9302% and nearly eliminates row 46.
- Native answer, matrix-term, and absolute source-order parity remain blocked.
- No single-record or production correction is promoted.

## 0.6.48.7.14

- The 155/620 inventory estimate below was corrected in v0.6.48.7.15 to the actual 154-record/616-term DSEC runtime set.
- Added an original v0.6.47.2 DSEC runtime capture for every He II row-46 contributor at evaluation 61.
- Captures the exact 155-record inventory across types 50, 53, 56, 57, 71, 74, 76, 77, 95, and 99, plus all 620 committed matrix terms in global source order.
- Captures line/continuum escape inputs, `ptmp1`, `ptmp2`, covering fraction, `ans1`-`ans6`, endpoint populations, and population-dependent diagnostics.
- Captures the complete physical row-46 equation, the pre-normalization row, the normalized all-ones row, RHS, and all 78 solve rows.
- Added an offline residual audit that substitutes the complete source row-46 term set into the exact type-53/type-71/type-99/actual-DSEC-type-50 qualification state and ranks the remaining residual by data type.
- Explicitly blocks type-76, single-record, fixed-state, thermal, and production promotion pending the runtime result.

## 0.6.48.7.13

- Added a qualification-only coupled replacement for all 79 He II type-50 rows-46–54 records using the actual v0.6.47.2 DSEC runtime capture.
- Reproduces all 474 answers and 316 committed matrix terms IEEE-exactly, including the hydrogen-density thermal multiplier.
- Reduces the evaluation-61 reference-population residual by 93.956%, restores helium matrix rank 78/78, and improves conditioning by about 5.64x.
- Preserves exact type-53, type-71, and type-99 constraints, H/Mg bit identity, helium normalization, and zero Python callbacks.
- Keeps general type-50 promotion, fixed-state parity, thermal parity, and production promotion blocked because the solved population state does not improve overall.

## 0.6.48.7.12

- Added an observational runtime probe for the untouched v0.6.47.2 physical DSEC path.
- Captures the live type-50 escape-probability inputs, covering fraction, optical depths, `ans1`-`ans6`, and all committed matrix terms for the 79 He II rows-46-54 records at evaluation 61.
- Added strict 79-record/316-term verification and source-archive hash gating.
- Kept general-state type-50 replacement, fixed-state parity, thermal parity, and production promotion blocked.

## v0.6.48.7.11 - 2026-07-19

### Added
- Added qualification-only source-ordered helium solve-response diagnostics.
- Exported the complete 78x78 helium matrix, RHS, row state, and 5,240 committed source-order terms.
- Added direct evaluation of the v0.6.47.2 reference population vector in the native helium system.
- Added residual rankings by qualified scope, remaining family, row block, and source position.

### Findings
- Exact type-50 changes 106 matrix entries but changes the population solution by only about 4.68e-9 in L1.
- The normalized helium system is extremely ill-conditioned, with condition number about 2.73e14.
- Rows 46-54 contain 99.8175% of the reference-population residual.
- The already exact type-50 scope dominates the residual; no unqualified family is material.
- A complete DSEC escape-probability capture is required before further type-50 promotion.

### Status
- Fixed-state, thermal, controller, product, and production promotion remain blocked.

## 0.6.48.7.10

- Added a qualification-only, fail-closed simultaneous replacement of all 79 He II type-50 transitions incident on rows 46-54.
- Embedded the immutable evaluation-61 type-50 oracle in the native engine and restricted its use to the captured fixed state.
- Required the general replacement gate, the exact record-1695 type-99 gate, and a dedicated type-50 manifold gate.
- Preserved all 31 exact type-53 records, all 31 exact type-71 row-77 records, and all six exact type-99 record-1695 answers.
- Made all 474 type-50 answers and all 79 matrix commitments exact to the frozen oracle.
- Verified bit-identical H/Mg state and exact helium normalization.
- Accepted the qualification candidate because electron fraction, charge residual, He I/II/III, and hmctot all move toward the v0.6.47.2 reference.
- Kept general type-50 physics replacement, fixed-state parity, thermal parity, and production promotion blocked because the candidate remains an evaluation-61 oracle substitution and the improvements are extremely small.

## 0.6.48.7.9

- Added a constrained evaluation-61 helium matrix-residual decomposition that keeps the 31 exact type-53 records, 31 exact type-71 row-77 records, and exact type-99 record 1695 fixed.
- Added fail-closed qualification row-range and unqualified-subset ablation controls.
- Identified type 50 as the strongest remaining compensating family.
- Localized the dominant nonlinear response to the type-50 He II row block 46-54; no single row or source position explains the block.
- Added portable link-free lowered-program snapshots and qualification-output safety checks.
- Kept type-50 correction, fixed-state parity, and production promotion blocked.

## 0.6.48.7.9

- Added a reproducible 31-record evaluation-61 v0.6.47.2 type-71 row-77 runtime oracle.
- Verified all current native type-71 ans1-ans6 values and matrix terms are IEEE-exact.
- Added a qualification-only exact type-99 record-1695 oracle substitution and measured the coupled type-71/type-99 fixed-state result.
- Rejected the coupled candidate because it increases charge residual and lowers He III.
- Preserved all 31 exact He II type-53 records and kept H/Mg unchanged.
- Replaced absolute-symlink qualification clones with regular-file copies and added a portable lowered-program snapshot.
- Kept full type-53, fixed-state, and production promotion blocked.

## v0.6.48.7.18 - 2026-07-20

### Added
- Added a first-class DSEC covering-fraction scalar to the fixed-state runtime ABI and bumped the public native ABI to `60487`; lowered-program ABI remains `60485`.
- Added `--dsec-covering-fraction` and exact `--temperature-k` standalone inputs for independent-state qualification.
- Added the evaluation-60 independent-state parity checker for the complete 44-record/176-term type-53 row-46 manifold.

### Fixed
- Corrected the type-53 Milne `rnist` exponent to use the destination continuum energy instead of forcing the continuum energy to zero.
- Prevented the generic covering fraction and rounded trajectory temperature from replacing the original DSEC runtime state.
- Restored IEEE-exact evaluation-60 parity for all 264 answers, all 176 matrix/thermal terms, and all absolute source-order positions.

### Qualification status
- Type-53 arbitrary-state qualification promotion is accepted across the independent evaluation-60 and captured evaluation-61 states.
- Whole fixed-state, thermal, controller, product, and production promotion remain blocked.


- Extend the fixed-state runtime ABI from 60485 to 60486 with the complete DSEC radiation and continuum optical-depth workspaces required by the type-53 source law.
- Preserve lowered-program ABI 60485 so existing active ATDB programs remain loadable without regeneration.
- Add standalone `--dsec-radiation-csv` and `--continuum-tau-csv` inputs and explicit runtime-state usage diagnostics.
- Add an untouched-v0.6.47.2 evaluation-60 capture workflow for the full `epi/bremsa` grid, dense continuum optical depths, and the 44-record/176-term type-53 row-46 manifold.
- Add an independent-state parity audit; arbitrary-state promotion remains blocked until that physical capture is run and reproduces all answers and terms.

## 0.6.48.7.18

- Bumped the public runtime ABI to `60486` while retaining lowered-program ABI `60485`.
- Appended DSEC `energy/bremsa` and inward/outward continuum optical-depth arrays to `xstar_fixed_state_input_v1`.
- Updated the source-faithful type-53 evaluator to consume the extended workspaces and report per-record usage, dimensions, and continuum indices.
- Added an independent evaluation-60 original-DSEC capture and exact 44-record/176-term parity audit.
- Accepted ABI/tooling readiness; independent-state capture and arbitrary-state promotion require the external ATDB/Astropy physical run.

## 0.6.48.7.16

- Added the exact captured-state 44-record/176-term type-53 row-46 coupled replacement gate.
- Added original DSEC absolute source-order insertion for the complete manifold.
- Added exact thermal-channel verification (`cj` and `cj2`) and non-target/H/Mg isolation gates.
- Added a non-anchor live-law execution check at evaluation 60.
- Accepted the qualification candidate; did not promote arbitrary-state or production physics.

## 0.6.48.7.15

- Added the 44-record original-DSEC type-53 row-46 coupled runtime-contract oracle and audit.
- Frozen oracle hashes: records `055f8e...6e65`, terms `bca048...d15a`, contribution `28b349...26aa`.
- Coupled substitution reduces the evaluation-61 reference residual by 97.9302% and nearly eliminates row 46.
- Native answer, matrix-term, and absolute source-order parity remain blocked.
- No single-record or production correction is promoted.

## 0.6.48.7.14

- The 155/620 inventory estimate below was corrected in v0.6.48.7.15 to the actual 154-record/616-term DSEC runtime set.
- Added an original v0.6.47.2 DSEC runtime capture for every He II row-46 contributor at evaluation 61.
- Captures the exact 155-record inventory across types 50, 53, 56, 57, 71, 74, 76, 77, 95, and 99, plus all 620 committed matrix terms in global source order.
- Captures line/continuum escape inputs, `ptmp1`, `ptmp2`, covering fraction, `ans1`-`ans6`, endpoint populations, and population-dependent diagnostics.
- Captures the complete physical row-46 equation, the pre-normalization row, the normalized all-ones row, RHS, and all 78 solve rows.
- Added an offline residual audit that substitutes the complete source row-46 term set into the exact type-53/type-71/type-99/actual-DSEC-type-50 qualification state and ranks the remaining residual by data type.
- Explicitly blocks type-76, single-record, fixed-state, thermal, and production promotion pending the runtime result.

## 0.6.48.7.13

- Added a qualification-only coupled replacement for all 79 He II type-50 rows-46–54 records using the actual v0.6.47.2 DSEC runtime capture.
- Reproduces all 474 answers and 316 committed matrix terms IEEE-exactly, including the hydrogen-density thermal multiplier.
- Reduces the evaluation-61 reference-population residual by 93.956%, restores helium matrix rank 78/78, and improves conditioning by about 5.64x.
- Preserves exact type-53, type-71, and type-99 constraints, H/Mg bit identity, helium normalization, and zero Python callbacks.
- Keeps general type-50 promotion, fixed-state parity, thermal parity, and production promotion blocked because the solved population state does not improve overall.

## 0.6.48.7.12

- Added an observational runtime probe for the untouched v0.6.47.2 physical DSEC path.
- Captures the live type-50 escape-probability inputs, covering fraction, optical depths, `ans1`-`ans6`, and all committed matrix terms for the 79 He II rows-46-54 records at evaluation 61.
- Added strict 79-record/316-term verification and source-archive hash gating.
- Kept general-state type-50 replacement, fixed-state parity, thermal parity, and production promotion blocked.

## v0.6.48.7.11 - 2026-07-19

### Added
- Added qualification-only source-ordered helium solve-response diagnostics.
- Exported the complete 78x78 helium matrix, RHS, row state, and 5,240 committed source-order terms.
- Added direct evaluation of the v0.6.47.2 reference population vector in the native helium system.
- Added residual rankings by qualified scope, remaining family, row block, and source position.

### Findings
- Exact type-50 changes 106 matrix entries but changes the population solution by only about 4.68e-9 in L1.
- The normalized helium system is extremely ill-conditioned, with condition number about 2.73e14.
- Rows 46-54 contain 99.8175% of the reference-population residual.
- The already exact type-50 scope dominates the residual; no unqualified family is material.
- A complete DSEC escape-probability capture is required before further type-50 promotion.

### Status
- Fixed-state, thermal, controller, product, and production promotion remain blocked.

## 0.6.48.7.10

- Added a qualification-only, fail-closed simultaneous replacement of all 79 He II type-50 transitions incident on rows 46-54.
- Embedded the immutable evaluation-61 type-50 oracle in the native engine and restricted its use to the captured fixed state.
- Required the general replacement gate, the exact record-1695 type-99 gate, and a dedicated type-50 manifold gate.
- Preserved all 31 exact type-53 records, all 31 exact type-71 row-77 records, and all six exact type-99 record-1695 answers.
- Made all 474 type-50 answers and all 79 matrix commitments exact to the frozen oracle.
- Verified bit-identical H/Mg state and exact helium normalization.
- Accepted the qualification candidate because electron fraction, charge residual, He I/II/III, and hmctot all move toward the v0.6.47.2 reference.
- Kept general type-50 physics replacement, fixed-state parity, thermal parity, and production promotion blocked because the candidate remains an evaluation-61 oracle substitution and the improvements are extremely small.

## 0.6.48.7.9

- Added a constrained evaluation-61 helium matrix-residual decomposition that keeps the 31 exact type-53 records, 31 exact type-71 row-77 records, and exact type-99 record 1695 fixed.
- Added fail-closed qualification row-range and unqualified-subset ablation controls.
- Identified type 50 as the strongest remaining compensating family.
- Localized the dominant nonlinear response to the type-50 He II row block 46-54; no single row or source position explains the block.
- Added portable link-free lowered-program snapshots and qualification-output safety checks.
- Kept type-50 correction, fixed-state parity, and production promotion blocked.

## 0.6.48.7.9

- Added a reproducible 31-record evaluation-61 v0.6.47.2 type-71 row-77 runtime oracle.
- Verified all current native type-71 ans1-ans6 values and matrix terms are IEEE-exact.
- Added a qualification-only exact type-99 record-1695 oracle substitution and measured the coupled type-71/type-99 fixed-state result.
- Rejected the coupled candidate because it increases charge residual and lowers He III.
- Preserved all 31 exact He II type-53 records and kept H/Mg unchanged.
- Replaced absolute-symlink qualification clones with regular-file copies and added a portable lowered-program snapshot.
- Kept full type-53, fixed-state, and production promotion blocked.

## 0.6.48.7.17 - 2026-06-12

- Extend the fixed-state runtime ABI from 60485 to 60486 with the complete DSEC radiation and continuum optical-depth workspaces required by the type-53 source law.
- Preserve lowered-program ABI 60485 so existing active ATDB programs remain loadable without regeneration.
- Add standalone `--dsec-radiation-csv` and `--continuum-tau-csv` inputs and explicit runtime-state usage diagnostics.
- Add an untouched-v0.6.47.2 evaluation-60 capture workflow for the full `epi/bremsa` grid, dense continuum optical depths, and the 44-record/176-term type-53 row-46 manifold.
- Add an independent-state parity audit; arbitrary-state promotion remains blocked until that physical capture is run and reproduces all answers and terms.

## 0.6.48.7.17

- Bumped the public runtime ABI to `60486` while retaining lowered-program ABI `60485`.
- Appended DSEC `energy/bremsa` and inward/outward continuum optical-depth arrays to `xstar_fixed_state_input_v1`.
- Updated the source-faithful type-53 evaluator to consume the extended workspaces and report per-record usage, dimensions, and continuum indices.
- Added an independent evaluation-60 original-DSEC capture and exact 44-record/176-term parity audit.
- Accepted ABI/tooling readiness; independent-state capture and arbitrary-state promotion require the external ATDB/Astropy physical run.

## 0.6.48.7.16

- Added the exact captured-state 44-record/176-term type-53 row-46 coupled replacement gate.
- Added original DSEC absolute source-order insertion for the complete manifold.
- Added exact thermal-channel verification (`cj` and `cj2`) and non-target/H/Mg isolation gates.
- Added a non-anchor live-law execution check at evaluation 60.
- Accepted the qualification candidate; did not promote arbitrary-state or production physics.

## 0.6.48.7.15

- Added the 44-record original-DSEC type-53 row-46 coupled runtime-contract oracle and audit.
- Frozen oracle hashes: records `055f8e...6e65`, terms `bca048...d15a`, contribution `28b349...26aa`.
- Coupled substitution reduces the evaluation-61 reference residual by 97.9302% and nearly eliminates row 46.
- Native answer, matrix-term, and absolute source-order parity remain blocked.
- No single-record or production correction is promoted.

## 0.6.48.7.14

- The 155/620 inventory estimate below was corrected in v0.6.48.7.15 to the actual 154-record/616-term DSEC runtime set.
- Added an original v0.6.47.2 DSEC runtime capture for every He II row-46 contributor at evaluation 61.
- Captures the exact 155-record inventory across types 50, 53, 56, 57, 71, 74, 76, 77, 95, and 99, plus all 620 committed matrix terms in global source order.
- Captures line/continuum escape inputs, `ptmp1`, `ptmp2`, covering fraction, `ans1`-`ans6`, endpoint populations, and population-dependent diagnostics.
- Captures the complete physical row-46 equation, the pre-normalization row, the normalized all-ones row, RHS, and all 78 solve rows.
- Added an offline residual audit that substitutes the complete source row-46 term set into the exact type-53/type-71/type-99/actual-DSEC-type-50 qualification state and ranks the remaining residual by data type.
- Explicitly blocks type-76, single-record, fixed-state, thermal, and production promotion pending the runtime result.

## 0.6.48.7.13

- Added a qualification-only coupled replacement for all 79 He II type-50 rows-46–54 records using the actual v0.6.47.2 DSEC runtime capture.
- Reproduces all 474 answers and 316 committed matrix terms IEEE-exactly, including the hydrogen-density thermal multiplier.
- Reduces the evaluation-61 reference-population residual by 93.956%, restores helium matrix rank 78/78, and improves conditioning by about 5.64x.
- Preserves exact type-53, type-71, and type-99 constraints, H/Mg bit identity, helium normalization, and zero Python callbacks.
- Keeps general type-50 promotion, fixed-state parity, thermal parity, and production promotion blocked because the solved population state does not improve overall.

## 0.6.48.7.12

- Added an observational runtime probe for the untouched v0.6.47.2 physical DSEC path.
- Captures the live type-50 escape-probability inputs, covering fraction, optical depths, `ans1`-`ans6`, and all committed matrix terms for the 79 He II rows-46-54 records at evaluation 61.
- Added strict 79-record/316-term verification and source-archive hash gating.
- Kept general-state type-50 replacement, fixed-state parity, thermal parity, and production promotion blocked.

## v0.6.48.7.11 - 2026-07-19

### Added
- Added qualification-only source-ordered helium solve-response diagnostics.
- Exported the complete 78x78 helium matrix, RHS, row state, and 5,240 committed source-order terms.
- Added direct evaluation of the v0.6.47.2 reference population vector in the native helium system.
- Added residual rankings by qualified scope, remaining family, row block, and source position.

### Findings
- Exact type-50 changes 106 matrix entries but changes the population solution by only about 4.68e-9 in L1.
- The normalized helium system is extremely ill-conditioned, with condition number about 2.73e14.
- Rows 46-54 contain 99.8175% of the reference-population residual.
- The already exact type-50 scope dominates the residual; no unqualified family is material.
- A complete DSEC escape-probability capture is required before further type-50 promotion.

### Status
- Fixed-state, thermal, controller, product, and production promotion remain blocked.

## 0.6.48.7.10

- Added a qualification-only, fail-closed simultaneous replacement of all 79 He II type-50 transitions incident on rows 46-54.
- Embedded the immutable evaluation-61 type-50 oracle in the native engine and restricted its use to the captured fixed state.
- Required the general replacement gate, the exact record-1695 type-99 gate, and a dedicated type-50 manifold gate.
- Preserved all 31 exact type-53 records, all 31 exact type-71 row-77 records, and all six exact type-99 record-1695 answers.
- Made all 474 type-50 answers and all 79 matrix commitments exact to the frozen oracle.
- Verified bit-identical H/Mg state and exact helium normalization.
- Accepted the qualification candidate because electron fraction, charge residual, He I/II/III, and hmctot all move toward the v0.6.47.2 reference.
- Kept general type-50 physics replacement, fixed-state parity, thermal parity, and production promotion blocked because the candidate remains an evaluation-61 oracle substitution and the improvements are extremely small.

## 0.6.48.7.9

- Added a constrained evaluation-61 helium matrix-residual decomposition that keeps the 31 exact type-53 records, 31 exact type-71 row-77 records, and exact type-99 record 1695 fixed.
- Added fail-closed qualification row-range and unqualified-subset ablation controls.
- Identified type 50 as the strongest remaining compensating family.
- Localized the dominant nonlinear response to the type-50 He II row block 46-54; no single row or source position explains the block.
- Added portable link-free lowered-program snapshots and qualification-output safety checks.
- Kept type-50 correction, fixed-state parity, and production promotion blocked.

## 0.6.48.7.9

- Added a reproducible 31-record evaluation-61 v0.6.47.2 type-71 row-77 runtime oracle.
- Verified all current native type-71 ans1-ans6 values and matrix terms are IEEE-exact.
- Added a qualification-only exact type-99 record-1695 oracle substitution and measured the coupled type-71/type-99 fixed-state result.
- Rejected the coupled candidate because it increases charge residual and lowers He III.
- Preserved all 31 exact He II type-53 records and kept H/Mg unchanged.
- Replaced absolute-symlink qualification clones with regular-file copies and added a portable lowered-program snapshot.
- Kept full type-53, fixed-state, and production promotion blocked.

## 0.6.48.7.16 - 2026-06-12

- Add a qualification-only source-faithful coupled replacement for the complete 44-record type-53 row-46 aliased manifold.
- Reproduce all 264 captured answers and all 176 dense/thermal matrix terms IEEE-exactly at evaluation 61.
- Insert the manifold at all 176 original absolute DSEC source-order positions while preserving exact reconstruction of the complete 5,240-term native matrix ledger.
- Reduce the reference-population residual by 97.9302%, improve the helium population L1 error from 0.1727831650 to 1.1390584e-05, and improve conditioning by about 217x.
- Execute a live non-anchor state path for all 44 records using current radiation, escape, population, and thermal inputs without replaying the evaluation-61 oracle.
- Keep arbitrary-state parity, general-state promotion, whole fixed-state parity, thermal parity, and production promotion blocked because the current ABI lacks the complete original DSEC radiation and optical-depth workspace.

## 0.6.48.7.16

- Added the exact captured-state 44-record/176-term type-53 row-46 coupled replacement gate.
- Added original DSEC absolute source-order insertion for the complete manifold.
- Added exact thermal-channel verification (`cj` and `cj2`) and non-target/H/Mg isolation gates.
- Added a non-anchor live-law execution check at evaluation 60.
- Accepted the qualification candidate; did not promote arbitrary-state or production physics.

## 0.6.48.7.15

- Added the 44-record original-DSEC type-53 row-46 coupled runtime-contract oracle and audit.
- Frozen oracle hashes: records `055f8e...6e65`, terms `bca048...d15a`, contribution `28b349...26aa`.
- Coupled substitution reduces the evaluation-61 reference residual by 97.9302% and nearly eliminates row 46.
- Native answer, matrix-term, and absolute source-order parity remain blocked.
- No single-record or production correction is promoted.

## 0.6.48.7.14

- The 155/620 inventory estimate below was corrected in v0.6.48.7.15 to the actual 154-record/616-term DSEC runtime set.
- Added an original v0.6.47.2 DSEC runtime capture for every He II row-46 contributor at evaluation 61.
- Captures the exact 155-record inventory across types 50, 53, 56, 57, 71, 74, 76, 77, 95, and 99, plus all 620 committed matrix terms in global source order.
- Captures line/continuum escape inputs, `ptmp1`, `ptmp2`, covering fraction, `ans1`-`ans6`, endpoint populations, and population-dependent diagnostics.
- Captures the complete physical row-46 equation, the pre-normalization row, the normalized all-ones row, RHS, and all 78 solve rows.
- Added an offline residual audit that substitutes the complete source row-46 term set into the exact type-53/type-71/type-99/actual-DSEC-type-50 qualification state and ranks the remaining residual by data type.
- Explicitly blocks type-76, single-record, fixed-state, thermal, and production promotion pending the runtime result.

## 0.6.48.7.13

- Added a qualification-only coupled replacement for all 79 He II type-50 rows-46–54 records using the actual v0.6.47.2 DSEC runtime capture.
- Reproduces all 474 answers and 316 committed matrix terms IEEE-exactly, including the hydrogen-density thermal multiplier.
- Reduces the evaluation-61 reference-population residual by 93.956%, restores helium matrix rank 78/78, and improves conditioning by about 5.64x.
- Preserves exact type-53, type-71, and type-99 constraints, H/Mg bit identity, helium normalization, and zero Python callbacks.
- Keeps general type-50 promotion, fixed-state parity, thermal parity, and production promotion blocked because the solved population state does not improve overall.

## 0.6.48.7.12

- Added an observational runtime probe for the untouched v0.6.47.2 physical DSEC path.
- Captures the live type-50 escape-probability inputs, covering fraction, optical depths, `ans1`-`ans6`, and all committed matrix terms for the 79 He II rows-46-54 records at evaluation 61.
- Added strict 79-record/316-term verification and source-archive hash gating.
- Kept general-state type-50 replacement, fixed-state parity, thermal parity, and production promotion blocked.

## v0.6.48.7.11 - 2026-07-19

### Added
- Added qualification-only source-ordered helium solve-response diagnostics.
- Exported the complete 78x78 helium matrix, RHS, row state, and 5,240 committed source-order terms.
- Added direct evaluation of the v0.6.47.2 reference population vector in the native helium system.
- Added residual rankings by qualified scope, remaining family, row block, and source position.

### Findings
- Exact type-50 changes 106 matrix entries but changes the population solution by only about 4.68e-9 in L1.
- The normalized helium system is extremely ill-conditioned, with condition number about 2.73e14.
- Rows 46-54 contain 99.8175% of the reference-population residual.
- The already exact type-50 scope dominates the residual; no unqualified family is material.
- A complete DSEC escape-probability capture is required before further type-50 promotion.

### Status
- Fixed-state, thermal, controller, product, and production promotion remain blocked.

## 0.6.48.7.10

- Added a qualification-only, fail-closed simultaneous replacement of all 79 He II type-50 transitions incident on rows 46-54.
- Embedded the immutable evaluation-61 type-50 oracle in the native engine and restricted its use to the captured fixed state.
- Required the general replacement gate, the exact record-1695 type-99 gate, and a dedicated type-50 manifold gate.
- Preserved all 31 exact type-53 records, all 31 exact type-71 row-77 records, and all six exact type-99 record-1695 answers.
- Made all 474 type-50 answers and all 79 matrix commitments exact to the frozen oracle.
- Verified bit-identical H/Mg state and exact helium normalization.
- Accepted the qualification candidate because electron fraction, charge residual, He I/II/III, and hmctot all move toward the v0.6.47.2 reference.
- Kept general type-50 physics replacement, fixed-state parity, thermal parity, and production promotion blocked because the candidate remains an evaluation-61 oracle substitution and the improvements are extremely small.

## 0.6.48.7.9

- Added a constrained evaluation-61 helium matrix-residual decomposition that keeps the 31 exact type-53 records, 31 exact type-71 row-77 records, and exact type-99 record 1695 fixed.
- Added fail-closed qualification row-range and unqualified-subset ablation controls.
- Identified type 50 as the strongest remaining compensating family.
- Localized the dominant nonlinear response to the type-50 He II row block 46-54; no single row or source position explains the block.
- Added portable link-free lowered-program snapshots and qualification-output safety checks.
- Kept type-50 correction, fixed-state parity, and production promotion blocked.

## 0.6.48.7.9

- Added a reproducible 31-record evaluation-61 v0.6.47.2 type-71 row-77 runtime oracle.
- Verified all current native type-71 ans1-ans6 values and matrix terms are IEEE-exact.
- Added a qualification-only exact type-99 record-1695 oracle substitution and measured the coupled type-71/type-99 fixed-state result.
- Rejected the coupled candidate because it increases charge residual and lowers He III.
- Preserved all 31 exact He II type-53 records and kept H/Mg unchanged.
- Replaced absolute-symlink qualification clones with regular-file copies and added a portable lowered-program snapshot.
- Kept full type-53, fixed-state, and production promotion blocked.

## 0.6.48.7.15 - 2026-06-12

- Add a self-contained original-DSEC type-53 row-46 runtime oracle covering all 44 aliased records, 264 answers, and 176 committed terms.
- Preserve optical-depth, escape-probability, population-dependent, provenance, and source-order fields from the accepted v0.6.48.7.14.2 capture.
- Compare the complete coupled manifold with the current native evaluation-61 implementation.
- Show that no record or committed term is fully IEEE-exact, while relative ordering within the type-53 subset is preserved.
- Substitute all 176 source terms as one unit and reduce the reference residual by 97.9302%.
- Reduce the solved helium population L1 error from 0.1727831650 to 1.1393747e-05 and improve matrix conditioning by about 217x.
- Keep arbitrary-state type-53, fixed-state, thermal, controller, product, and production promotion blocked.

## 0.6.48.7.14 - 2026-06-12

- Added an original v0.6.47.2 DSEC runtime capture for every He II row-46 contributor at evaluation 61.
- Captures the exact 155-record inventory across types 50, 53, 56, 57, 71, 74, 76, 77, 95, and 99, plus all 620 committed matrix terms in global source order.
- Captures line/continuum escape inputs, `ptmp1`, `ptmp2`, covering fraction, `ans1`-`ans6`, endpoint populations, and population-dependent diagnostics.
- Captures the complete physical row-46 equation, the pre-normalization row, the normalized all-ones row, RHS, and all 78 solve rows.
- Added an offline residual audit that substitutes the complete source row-46 term set into the exact type-53/type-71/type-99/actual-DSEC-type-50 qualification state and ranks the remaining residual by data type.
- Explicitly blocks type-76, single-record, fixed-state, thermal, and production promotion pending the runtime result.

## 0.6.48.7.13 - 2026-06-12

- Added a qualification-only coupled replacement for all 79 He II type-50 rows-46–54 records using the actual v0.6.47.2 DSEC runtime capture.
- Reproduces all 474 answers and 316 committed matrix terms IEEE-exactly, including the hydrogen-density thermal multiplier.
- Reduces the evaluation-61 reference-population residual by 93.956%, restores helium matrix rank 78/78, and improves conditioning by about 5.64x.
- Preserves exact type-53, type-71, and type-99 constraints, H/Mg bit identity, helium normalization, and zero Python callbacks.
- Keeps general type-50 promotion, fixed-state parity, thermal parity, and production promotion blocked because the solved population state does not improve overall.

## 0.6.48.7.12 - 2026-06-12

- Added an observational runtime probe for the untouched v0.6.47.2 physical DSEC path.
- Captures the live type-50 escape-probability inputs, covering fraction, optical depths, `ans1`-`ans6`, and all committed matrix terms for the 79 He II rows-46-54 records at evaluation 61.
- Added strict 79-record/316-term verification and source-archive hash gating.
- Kept general-state type-50 replacement, fixed-state parity, thermal parity, and production promotion blocked.

## v0.6.48.7.11 - 2026-06-12

### Added
- Added qualification-only source-ordered helium solve-response diagnostics.
- Exported the complete 78x78 helium matrix, RHS, row state, and 5,240 committed source-order terms.
- Added direct evaluation of the v0.6.47.2 reference population vector in the native helium system.
- Added residual rankings by qualified scope, remaining family, row block, and source position.

### Findings
- Exact type-50 changes 106 matrix entries but changes the population solution by only about 4.68e-9 in L1.
- The normalized helium system is extremely ill-conditioned, with condition number about 2.73e14.
- Rows 46-54 contain 99.8175% of the reference-population residual.
- The already exact type-50 scope dominates the residual; no unqualified family is material.
- A complete DSEC escape-probability capture is required before further type-50 promotion.

### Status
- Fixed-state, thermal, controller, product, and production promotion remain blocked.

## 0.6.48.7.10 - 2026-06-12

- Added a qualification-only, fail-closed simultaneous replacement of all 79 He II type-50 transitions incident on rows 46-54.
- Embedded the immutable evaluation-61 type-50 oracle in the native engine and restricted its use to the captured fixed state.
- Required the general replacement gate, the exact record-1695 type-99 gate, and a dedicated type-50 manifold gate.
- Preserved all 31 exact type-53 records, all 31 exact type-71 row-77 records, and all six exact type-99 record-1695 answers.
- Made all 474 type-50 answers and all 79 matrix commitments exact to the frozen oracle.
- Verified bit-identical H/Mg state and exact helium normalization.
- Accepted the qualification candidate because electron fraction, charge residual, He I/II/III, and hmctot all move toward the v0.6.47.2 reference.
- Kept general type-50 physics replacement, fixed-state parity, thermal parity, and production promotion blocked because the candidate remains an evaluation-61 oracle substitution and the improvements are extremely small.

## 0.6.48.7.9 - 2026-06-12

- Added a constrained evaluation-61 helium matrix-residual decomposition that keeps the 31 exact type-53 records, 31 exact type-71 row-77 records, and exact type-99 record 1695 fixed.
- Added fail-closed qualification row-range and unqualified-subset ablation controls.
- Identified type 50 as the strongest remaining compensating family.
- Localized the dominant nonlinear response to the type-50 He II row block 46-54; no single row or source position explains the block.
- Added portable link-free lowered-program snapshots and qualification-output safety checks.
- Kept type-50 correction, fixed-state parity, and production promotion blocked.

## 0.6.48.7.8 - 2026-06-12

- Added a constrained evaluation-61 helium matrix-residual decomposition that keeps the 31 exact type-53 records, 31 exact type-71 row-77 records, and exact type-99 record 1695 fixed.
- Added fail-closed qualification row-range and unqualified-subset ablation controls.
- Identified type 50 as the strongest remaining compensating family.
- Localized the dominant nonlinear response to the type-50 He II row block 46-54; no single row or source position explains the block.
- Added portable link-free lowered-program snapshots and qualification-output safety checks.
- Kept type-50 correction, fixed-state parity, and production promotion blocked.

## 0.6.48.7.7 - 2026-06-11

- Added a reproducible 31-record evaluation-61 v0.6.47.2 type-71 row-77 runtime oracle.
- Verified all current native type-71 ans1-ans6 values and matrix terms are IEEE-exact.
- Added a qualification-only exact type-99 record-1695 oracle substitution and measured the coupled type-71/type-99 fixed-state result.
- Rejected the coupled candidate because it increases charge residual and lowers He III.
- Preserved all 31 exact He II type-53 records and kept H/Mg unchanged.
- Replaced absolute-symlink qualification clones with regular-file copies and added a portable lowered-program snapshot.
- Kept full type-53, fixed-state, and production promotion blocked.

## 0.6.48.7.6 - 2026-06-11

- Add an isolated exact v0.6.47.2 fixed-state evaluator replay and immutable one-record oracle for type-99 source position 6312 / record 1695.
- Reconstruct the exact type-99 source pipeline and signed answer contract.
- Demonstrate that the current native record-1695 path is IEEE-exact only for ans2, overstates ans1 by about 285 times, and gives incorrect ans5/ans6 signs.
- Add grouped type-71 ablations and isolate the 31 cascades terminating on He II row 77 as effectively the entire measurable family response.
- Add combined type-99/type-71 ablations and confirm strong non-additivity with approximately 50% overlap relative to naive addition.
- Preserve all 31 independently qualified He II type-53 records, unchanged H/Mg states, ABI 60485, and zero Python callbacks.
- Keep type-99 correction, fixed-state parity, and production promotion blocked pending an independent type-71 row-77 runtime oracle and coupled requalification.

## 0.6.48.7.5 - 2026-06-11

- Preserve all 31 independently qualified He II type-53 records as IEEE-exact immutable invariants across every isolation scenario.
- Correct stale He II bound-free audit metadata so the verified runtime oracle and applied qualified scope are reported accurately.
- Add helium-only per-source-position matrix ledgers and family/row residual aggregation for evaluation 61.
- Add qualification-gated one-family-at-a-time matrix ablation for helium types 50, 54, 56, 57, 63, 69, 71, 74, 76, 77, 95, and 99.
- Audit type 30 separately through the preliminary ion-rate path.
- Add causal source-position ablations for the three type-99 records and isolate source position 6312 / record 1695 as the strongest candidate.
- Keep all candidate corrections, full type-53 promotion, fixed-state parity, and production promotion blocked pending independent source/runtime verification.

## 0.6.48.7.4 - 2026-06-11

- Made the 31 evaluation-61 He II type-53 records IEEE-exact to the frozen v0.6.47.2 runtime oracle.
- Pinned the historical `13.605692` Rydberg constant and the `expo.f90` +/-60 clamp.
- Applied source-signed `ans1`-`ans6` to the qualified He II matrix scope.
- Added path-hardened qualification and checker workflows with radiation SHA-256 validation.
- Preserved ABI 60485; full fixed-state and production promotion remain blocked.

## 0.6.48.7.3 - 2026-06-11

- Add an isolated exact v0.6.47.2 type-53 evaluator replay tied to the source archive, lowered-program, state and radiation hashes.
- Freeze and package the complete 31-record evaluation-61 He II type-53 runtime oracle.
- Expand the three-way gate with per-answer exact counts and maximum source-relative differences.
- Confirm the translated shadow is closer for all 31 records but IEEE-exact for none; keep physics replacement and production promotion blocked.


- Add a three-way He II type-53 comparison across applied native, translated source-style shadow, and optional exact v0.6.47.2 runtime oracle values.
- Freeze and verify immutable 31-record runtime-oracle bundles with SHA-256 manifests.
- Encode the v0.6.47.2 signed `ans1`-`ans6` contract and expand every record into the four exact element-matrix insertion terms.
- Record exact v0.6.47.2 source archive and relevant source-file fingerprints without treating source reconstruction as a runtime oracle.
- Keep the shadow branch diagnostic-only; fixed-state and production promotion remain blocked.

## 0.6.48.7.1

- Add a coarse single-reference-evaluation standalone command for fast fixed-state qualification.
- Add source-ordered He II type-53 shadow diagnostics for all six bound-free contribution fields.
- Correct the diagnostic unit boundary: lowered type-53 cross sections are already in cm^2, while the legacy translated kernel expected megabarns.
- Add a machine-readable He II bound-free audit and regression checker covering all 31 evaluation-61 records.
- Keep the source-style shadow out of the physical solve because applying it alone worsens the final He II/He III result.
- Preserve ABI 60485, zero Python callbacks, and the v0.6.48.7 physical state. Fixed-state parity and production promotion remain blocked.

## 0.6.48.7

- Added immutable fixed-state oracle for all 61 scalar states, four accepted ion vectors, and the final detailed level vector.
- Added strict native fixed-state comparison and machine-readable mismatch reports.
- Added computed electron fraction, charge residual, heating, cooling, and hmctot to native diagnostic state JSON.
- Preserved ABI 60485, zero Python callbacks, and qualification-only status.
- Fixed-state parity and production promotion remain blocked.

## 0.6.48.6.1

- Repair IEEE FITS comparison for strided/non-contiguous Astropy table fields by comparing contiguous per-scalar byte representations.
- Resolve reference, candidate, map-output, and JSON-report paths to absolute paths before qualification work begins.
- Remove any pre-existing JSON report before execution and write completed reports atomically, preventing stale comparison results after exceptions.
- Harden the comparison wrapper so it reports `comparison_json=not_written` when a run fails before a report is produced.
- Add a negative FITS control that changes exactly one floating-point cell in `xout_cont1.fits` and requires a `fits_value` rejection.
- Preserve the v0.6.47.2 immutable reference bundle, ABI 60485, native diagnostics, and source-order maps without changing physics.
- Make no physical-equivalence or production-promotion claim; production remains blocked.

## 0.6.48.7.2 - 2026-06-11

- Add a three-way He II type-53 comparison across applied native, translated source-style shadow, and optional exact v0.6.47.2 runtime oracle values.
- Freeze and verify immutable 31-record runtime-oracle bundles with SHA-256 manifests.
- Encode the v0.6.47.2 signed `ans1`-`ans6` contract and expand every record into the four exact element-matrix insertion terms.
- Record exact v0.6.47.2 source archive and relevant source-file fingerprints without treating source reconstruction as a runtime oracle.
- Keep the shadow branch diagnostic-only; fixed-state and production promotion remain blocked.

## 0.6.48.7.1

- Add a coarse single-reference-evaluation standalone command for fast fixed-state qualification.
- Add source-ordered He II type-53 shadow diagnostics for all six bound-free contribution fields.
- Correct the diagnostic unit boundary: lowered type-53 cross sections are already in cm^2, while the legacy translated kernel expected megabarns.
- Add a machine-readable He II bound-free audit and regression checker covering all 31 evaluation-61 records.
- Keep the source-style shadow out of the physical solve because applying it alone worsens the final He II/He III result.
- Preserve ABI 60485, zero Python callbacks, and the v0.6.48.7 physical state. Fixed-state parity and production promotion remain blocked.

## 0.6.48.7

- Added immutable fixed-state oracle for all 61 scalar states, four accepted ion vectors, and the final detailed level vector.
- Added strict native fixed-state comparison and machine-readable mismatch reports.
- Added computed electron fraction, charge residual, heating, cooling, and hmctot to native diagnostic state JSON.
- Preserved ABI 60485, zero Python callbacks, and qualification-only status.
- Fixed-state parity and production promotion remain blocked.

## 0.6.48.6.1

- Repair IEEE FITS comparison for strided/non-contiguous Astropy table fields by comparing contiguous per-scalar byte representations.
- Resolve reference, candidate, map-output, and JSON-report paths to absolute paths before qualification work begins.
- Remove any pre-existing JSON report before execution and write completed reports atomically, preventing stale comparison results after exceptions.
- Harden the comparison wrapper so it reports `comparison_json=not_written` when a run fails before a report is produced.
- Add a negative FITS control that changes exactly one floating-point cell in `xout_cont1.fits` and requires a `fits_value` rejection.
- Preserve the v0.6.47.2 immutable reference bundle, ABI 60485, native diagnostics, and source-order maps without changing physics.
- Make no physical-equivalence or production-promotion claim; production remains blocked.

## 0.6.48.7.1 - 2026-06-11

- Add a coarse single-reference-evaluation standalone command for fast fixed-state qualification.
- Add source-ordered He II type-53 shadow diagnostics for all six bound-free contribution fields.
- Correct the diagnostic unit boundary: lowered type-53 cross sections are already in cm^2, while the legacy translated kernel expected megabarns.
- Add a machine-readable He II bound-free audit and regression checker covering all 31 evaluation-61 records.
- Keep the source-style shadow out of the physical solve because applying it alone worsens the final He II/He III result.
- Preserve ABI 60485, zero Python callbacks, and the v0.6.48.7 physical state. Fixed-state parity and production promotion remain blocked.

## 0.6.48.6.1 - 2026-06-11

- Repair IEEE FITS comparison for strided/non-contiguous Astropy table fields by comparing contiguous per-scalar byte representations.
- Resolve reference, candidate, map-output, and JSON-report paths to absolute paths before qualification work begins.
- Remove any pre-existing JSON report before execution and write completed reports atomically, preventing stale comparison results after exceptions.
- Harden the comparison wrapper so it reports `comparison_json=not_written` when a run fails before a report is produced.
- Add a negative FITS control that changes exactly one floating-point cell in `xout_cont1.fits` and requires a `fits_value` rejection.
- Preserve the v0.6.47.2 immutable reference bundle, ABI 60485, native diagnostics, and source-order maps without changing physics.
- Make no physical-equivalence or production-promotion claim; production remains blocked.

## 0.6.48.6 - 2026-06-11

- Froze an immutable v0.6.47.2 reference bundle with SHA-256 verification.
- Added native source-ordered per-record and per-family diagnostics for fixed-state evaluations.
- Added source-order element, row, and record maps for lowered programs.
- Added strict byte, IEEE, source-rounded, and diagnostic comparison policies for text, CSV, JSON, and FITS products.
- Added a qualification checker and full 61-evaluation diagnostics workflow.
- Made no physics or production-promotion claim; production remains blocked.

## 0.6.48.5.3 - 2026-06-11

- Connect types 1/30/38/39 to source-faithful preliminary recombination totals and active ion-stage selection.
- Add external reference-radiation CSV support to native trajectory and DSEC commands.
- Include full and reduced v0.6.47.2 incident-radiation grids.
- Record the failed He/Mg fixed-state population comparison explicitly; thermal and FITS promotion remain blocked.

## 0.6.48.5.2 - 2026-06-11

- Resolve `elements.csv` fields by header name, fixing strict host programs whose abundance column is last.
- Preserve legacy eight-column compatibility and ABI 60485.

## 0.6.48.5.1 - 2026-06-11

- Serialize explicit per-element abundances in `elements.csv`; retain read compatibility with legacy eight-column programs using abundance 1.0.
- Compute `elcter` as abundance-weighted represented ion charge plus the fully stripped missing fraction at charge Z.
- Correct charge residual semantics to `trial electron fraction - computed electron fraction` in both reference-input and DSEC-controller paths.
- Stop forcing denormal-minimum DSEC tolerances; use the source/default convergence policy so thermal iteration can run.
- Persist the native free-free continuum independently from the full continuum-plus-line/RRC/profile spectrum.
- Generate `xout_cont1.fits` and `xout_spect1.fits` through distinct writers with `PRODUCT` and `SPECMODE` headers.
- Keep ABI 60485 and production promotion blocked: heating/cooling parity, reference-state identity, and external physical equivalence still fail.

## 0.6.48.4.1 - 2026-06-10

- Correct active-ATDB source-position serialization using globally increasing four-slot positions.
- Reject zero, duplicate, and decreasing source positions in Python and C++.
- Separate line-record storage capacity from continuum energy-bin capacity.
- Project committed line emissivity and opacity explicitly into the radiation grid.
- Correct multi-element native self-test accounting.
- Strengthen the milestone checker to execute a supplied host-lowered program.
- Add regressions for host-style source ordering and 80 lines on a 64-bin grid.

## 0.6.48.4 - 2026-06-10

- Promote active-ATDB lowering and native execution for data types 54, 57, 63, 71, 77, 86, and 99.
- Preserve type-6 principal/orbital quantum metadata in compact rows for the type-54, type-57, and type-63 evaluators.
- Add native wrappers for the validated type-63 and `anl1` scalar kernels.
- Add source-shaped native calt57, calt71, calt77, Auger, and type-99 density/temperature/radiation evaluators.
- Add a 14-record phase-1 fixture, 64-zone callback-free batch test, visited-family gate, and unknown-opcode rejection.
- Project the supplied H/He/Mg host workload from 6,699 to 8,570 native executable records, leaving 152 records outside phase 1.
- Bump the public and fixed-state ABIs to `60484`.
- Keep production promotion blocked pending host lowering/execution, per-record source parity for provisional families, 61 native DSEC evaluations, and the nine historical FITS products.

## 0.6.48.3.2 - 2026-06-09

- Stop active-ATDB rate traversal at the current ion parent boundary.
- Prevent global `npnxt` chains from assigning downstream helium and magnesium records to hydrogen.
- Retain the v0.6.48.3.1 `ElementBasisRow.compact_index` topology correction.
- Add compact-basis and three-element cross-ion ownership regression tests.
- Keep public and fixed-state ABI compatibility at `60483`.

## 0.6.48.3.1 - 2026-06-09

- Correct the active-ATDB lowerer to use `ElementBasisRow.compact_index` rather than the nonexistent `index` attribute.
- Add an integration regression test over a real `ElementCompactBasis` row object.
- Keep public and fixed-state ABI compatibility at `60483`.

## 0.6.48.3 - 2026-06-09

- Added the active H/He/Mg ATDB lowerer with rate-aware metadata/native/unsupported classification.
- Added compact type-6 level topology lowering and raw record output with ATDB fingerprints.
- Added native type-56 tabulated collision-strength interpolation.
- Added dynamic fixed-state program-capacity introspection and visited-data-type reports.
- Added strict fail-closed lowering plus explicit promotion-blocked partial mode.
- Production remains blocked pending all visited families, 61 native evaluations, and historical science-product generation.

## 0.6.48.2 - 2026-06-09

- Adds `libxstar_fixed_state.so`, a genuine state-dependent raw-coefficient
  fixed-state engine with linked atomic-record traversal and zero Python
  callbacks.
- Connects evaluated contributions to the native element solver and native
  spectral engine, and computes continuum heating/cooling and output arrays.
- Adds a replay-resistant raw-program compiler/validator and host ATDB coverage
  scanner.
- Adds native-generated diagnostic FITS and `xout_step.log` outputs.
- Reclassifies the compiled-case bundle as compatibility cache/replay only.
- Does not claim all-C++ production promotion; full ATDB lowering, exact
  continuum translation, and nine-product FITS parity remain blocked.

## 0.6.48.1 - 2026-06-09

- Include `xout_step.log` in the compiled-case bundle as a separately classified auxiliary output artifact.
- Write the log alongside the nine FITS science products during callback-free C++ execution.
- Require `science_file_count=9`, `auxiliary_file_count=1`, and `output_artifact_count=10` in the manifest.
- Reject bundles with a missing, renamed, or wrong-size step log.
- Add byte-identical `xout_step.log` validation to the production checker and run summary.
- Keep public and compiled-case ABI `60480`.

## 0.6.48 - 2026-06-09

- Add an ahead-of-time compiled-case runtime with 61 native C++ state evaluations and zero Python callbacks during execution.
- Add exact reference-state and nine-file science bundle output for the accepted `helike_type69_mg11_ne1e8` qualification case.
- Add `xstar_compiled_case_run_files_v1`, single-zone, and batch MHD C APIs under ABI 60480.
- Add standalone `production-self-test`, `production-batch-self-test`, and `run-compiled-case` commands.
- Retain the whole-run Python backend for unsupported cases and future compiled-bundle generation.
- Keep the accepted v0.6.47.2 bounded physical-equivalence policy as the source qualification record.

## 0.6.47.2 - 2026-06-09

- Correct the release reference runner to resolve only v0.6.47.2, reject version-mismatch overrides, and capture DSEC terminal/trajectory provenance by default.
- Record package and release-source versions in every run summary and require a current reference in the acceptance checker.
- Replace profile-only spectral qualification with a complete Python source temporary-grid oracle containing 20,000 energies and 20,000 exact opacity samples per line.
- Keep C++ ownership of trapezoid integration, continuum rebinning, source-ordered `opakc` commit, and the unchanged native product path.
- Require zero spectral shadow mismatches and exact Python/native DSEC trajectory parity.
- Keep public and thermal ABI 60471 and spectral ABI 60460.

## 0.6.47 - 2026-06-09

- Added persistent native `heatt` continuum, line, and RRC transfer.
- Added source-faithful native DSEC temperature/electron convergence control.
- Added state propagation and one native evaluation-loop controller per zone.
- Added stable API wrappers and C++ RAII methods for thermal execution.
- Retained the v0.6.46.3 spectral shadow mismatch as a documented known issue.

## v0.6.46.3 - 2026-06-09

- Correct the native opacity `huntf` floor from `1e-24` to XSTAR's float32-promoted `1e-34`.
- Force source-order binary64 rounding for profile-grid construction, trapezoid accumulation, rebinning, and `opakc` commit.
- Compile `libxstar_opacity.so` with `-ffp-contract=off` to prevent GCC FMA contraction at `-O3`.
- Keep the complete 20,001-sample qualification oracle and strict final-array equality.
- Record `strict_source_rounding` and `source_hunt_floor` provenance.
- Keep the stable shared-library ABI at 60460 and use a 285-second host-variation ceiling plus optional same-session ratio gate.

## v0.6.46.2 - 2026-06-09

- Replace the rejected final-array one-ULP opacity policy with a qualification-only complete Gaussian/Voigt source-profile oracle.
- Keep production native profile generation unchanged and require exact final spectral-array parity.
- Record exact-profile oracle calls, values, and line-profile coverage; product mode requires all three counters to remain zero.
- Keep the stable shared-library ABI at 60460 because no function signature or structure layout changed.
- Raise the default absolute timing guard to 275 seconds and optionally enforce a same-session control ratio of 0.90.

## 0.6.46.1 - 2026-06-09

- Preserve the v0.6.46 native emissivity/opacity product implementation and ABI 60460.
- Classify NumPy scalar-exp versus C++ libm Gaussian-tail differences of at most one binary64 ULP in `calc_emis_all` `opakc` as explicitly bounded qualification events.
- Keep all other spectral arrays bit-exact; two ULPs, a non-`opakc` difference, source-order drift, fallbacks, or science-file drift remain hard failures.
- Add `shadow_ulp_tolerated_calls`, `shadow_ulp_tolerated_values`, `shadow_max_ulp`, and `first_ulp_tolerated` provenance.
- Add isolated ULP-policy tests and a v0.6.46.1 acceptance checker.

## v0.6.45.1 - 2026-06-09

### Added
- Added ABI 60451 compact record-contribution structures and persistent native construction calls.
- Added source-order-preserving C++ expansion of each contribution into canonical matrix terms.
- Added one-call H/He/Mg construction evaluation APIs and standalone self-tests.
- Added product provenance for construction time, records, native terms, and Python term materialization.

### Changed
- Product element execution no longer retains Python `MatrixTerm` objects.
- Kept the packed-term ABI as a qualification and diagnostic path.

### Notes
- Python still owns atomic record traversal and scalar rate evaluation; this release moves term construction and all downstream element work into C++.

## 0.6.45 - 2026-06-08

- Added stable native element-engine ABI version 60450.
- Added persistent H/He/Mg element contexts and one-call element/evaluation entry points.
- Moved source-ordered dense/heating matrix accumulation, normalization, Lucy/fixed-point population solving, derived ion state, and state commit into `libxstar_engine.so`.
- Added the Python ctypes adapter with exact shadow qualification and whole-element Python fallback.
- Added standalone element and one-call H/He/Mg evaluation self-tests.
- Added 183-call science qualification/product provenance and acceptance gates.
- Retained atomic-data traversal and scalar source-ordered `MatrixTerm` construction in Python pending the next coarse rate-construction port.

## 0.6.44.3 - 2026-06-08

- Added Python backend runtime rpath entries derived from `python3-config --embed --ldflags` so Conda/shared-libpython installs can load `libxstar_backend_python.so` via `dlopen`.
- Removed the fragile parse-time GNU make filesystem-link probe.
- Defaulted filesystem compatibility linkage to `-lstdc++fs`, with an explicit override supported.
- Retained ABI 60440 and explicit plugin linkage to `libxstar_api.so`.

## 0.6.44.2 - 2026-06-08

- Removed the fragile parse-time GNU make filesystem-link probe.
- Defaulted filesystem compatibility linkage to `-lstdc++fs`, with an explicit override supported.
- Retained ABI 60440 and explicit plugin linkage to `libxstar_api.so`.

## 0.6.44.1 - 2026-06-08

- Detect whether C++17 `std::filesystem` is provided by the main C++ standard library or requires `-lstdc++fs`.
- Link `libxstar_api.so`, both backend plugins, and `xstar_cpp` with the detected filesystem compatibility library.
- Add filesystem link mode to `make print-config`.
- Add relocation checks that reject unresolved dynamic symbols in the standalone executable and plugin libraries.
- Preserve ABI version 60440 and the v0.6.44 native/Python directory layout.

## 0.6.44 - 2026-06-08

- Added the standalone `xstar_cpp` executable.
- Added stable `libxstar_api.so` C ABI version 60440.
- Added runtime backend registry with C++ and embedded-Python plugins.
- Added persistent single-zone and batch-zone contexts.
- Added per-component backend requests and component ownership reporting.
- Added `libxstar_backend_python.so` JSON bridge for adapted Python routines.
- Kept every native header, source, shared object, executable, and Makefile in
  `src/xstar_tools/xstar/cpp/`; Python XSTAR code remains in
  `src/xstar_tools/xstar/`.
- Kept the v0.6.44 typed zone boundary explicitly scaffold-only pending the
  complete native physics port.

## 0.6.43.1 - 2026-06-08

- Exclude the non-bit-exact preliminary Type-53 C++ kernel from the coarse Mg pre-matrix product.
- Retain exact Type-49 C++ acceleration and literal source-position commit.
- Add per-type selected/supported coverage and explicit Type-53 fallback provenance.
- Add qualification and production runners plus a parity-first acceptance checker.

## 0.6.42 - 2026-06-08

- Add nested inclusive/exclusive profiling with parent, child, depth, and exclusive-time aggregation.
- Split the pre-matrix path into metadata, per-ion setup, context construction, record dispatch, accumulation, contribution materialization, vector allocation, ion-fraction solve, and stage-limit selection.
- Record NumPy workspace copy/allocation counts, bytes, normalized-matrix construction, residual diagnostics, and dense-SVD time inside the element solver.
- Gate residual arrays, condensed-rank calculations, dense rank/condition diagnostics, and the normalized-matrix copy by diagnostics mode.
- Use one singular-value decomposition for full-mode dense rank and condition number instead of separate `matrix_rank` and `cond` decompositions.
- Preserve all v0.6.41 science paths, source-order barriers, returned state, and whole-evaluation fallback.

## 0.6.40.1 - 2026-06-08

- Construct each live Type-88 fast-packet threshold with the exact source `_level_threshold` semantics, including subtraction of the bound-level energy.
- Leave the Type-88 C++ kernel and engine ABI unchanged.
- Record scalar-mismatch family, accepted value, candidate value, and packet threshold in whole-evaluation fallback provenance.
- Retain native Type-50 `opakab`, full reverse verification, zero Type-51 per-record barriers, and whole-evaluation fallback.
- Require all 61 evaluations, all 146,286 Type-50 `opakab` comparisons, exact matrix and solver checkpoints, and exact FITS science payloads before acceptance.

## 0.6.40 - 2026-06-08

- Add native, source-faithful Type-50 line-center `opakab` to the engine fast result (ABI 9, feature flags 1023).
- Run the Type-50/63/88 seed-free path live in product-candidate mode and populate `UCalcResult.opakab` from the native packet.
- Leave Type-63 and Type-88 scalar/state formulas unchanged.
- Remove the ineffective per-record Type-51 flush barrier while retaining the accepted Type-51 ion batch.
- Retain whole-evaluation fallback and enable complete reverse verification for the initial candidate.
- Require exact Type-50 `opakab`, native scalars, rows, result state, matrices, solver inputs, and FITS science payloads before promotion.

## 0.6.39 - 2026-06-08

- Add an accepted-live four-family seed-elision differential diagnostic for Mg Type-50, Type-63, and Type-88.
- Compare exact native scalars, C++ rows, ordered term streams, per-cell contribution sequences, dense/heating matrices, normalized solver inputs, and second-pass totals.
- Add seven family-ablation variants and first-divergence provenance.
- Compare accepted and seed-elided `UCalcResult` state, including `opakab`, while keeping accepted terms live.
- Disable the promoted fast path whenever the differential diagnostic is active.
- Keep the engine ABI at version 8 and feature flags at 511.

## 0.6.38 - 2026-06-08

- Promote the four-family Mg rate-payload product with the Python scalar seed/oracle removed from normal execution.
- Preserve accepted source accumulation order by flushing pending Type-51 batches before every Type-50/63/88 fast commit.
- Add structural order-barrier provenance and whole-evaluation fallback invariants.
- Route `XSTAR_ATOMIC_RATE_PAYLOAD_FOUR_FAMILY_VERIFY_OLD=1` through the complete v0.6.37 reverse-verification candidate.
- Keep the engine ABI at version 8 because scalar formulas and row construction are unchanged.

## 0.6.37 - 2026-06-08

- Add a diagnostic four-family order-preserving C++ commit candidate.
- Add full-record native Type-50, Type-63, and Type-88 scalar reverse verification.
- Preserve accepted composite row identity, term index, and global term-stream order.
- Require exact ordered-stream, dense/heating, normalized-matrix, and RHS checkpoints before commit.
- Keep product promotion disabled and preserve accepted fallback behavior.
- Extend the engine ABI to version 8 with native Type-50 scalar support and order-verification capability flags.

## 0.6.36 - 2026-06-07

- Correct the promoted four-family Type-50 dependency: the simple-payload batch never owned rate 4 / data 50.
- Add bit-exact native Type-50 scalar evaluation to the engine ABI.
- Feed 4:50, 3:63, and 42:88 through one native scalar packet while retaining whole-evaluation fallback and optional reverse verification.
- Report engine ABI 7 and feature flags 255.

## v0.6.35 - 2026-06-07

- Promoted the exact four-family Mg rate-payload product for 4:50, 3:51, 3:63, and 42:88.
- Elided the Python scalar seed/oracle from normal 4:50, 3:63, and 42:88 execution.
- Retained the accepted ion-level C++ Type-51 rate-and-matrix batch for 3:51.
- Added whole-element accepted-path retry on any promoted-product failure.
- Kept reverse verification opt-in and disabled it in the production wrapper.
- Added promoted-product provenance and strict acceptance checks.

## v0.6.34 - 2026-06-07

### Added
- Added the guarded four-family Mg rate-payload live product candidate for 4:50, 3:51, 3:63, and 42:88.
- Added bit-exact native scalar use for 3:63 and 42:88, exact C++ row verification, composite-key live replacement, whole-evaluation fallback, and aggregate product provenance.
- Retained the accepted seed path as the verification oracle in this candidate; Python per-record elision remains a later promotion step.

## 0.6.33 - 2026-06-07

- Refined the shadow-only Mg rate/data 3/63 native scalar implementation to reproduce Python binary64 operation order.
- Added exact CPython `math.lgamma(n + 1.0)` hexadecimal constants for integer arguments 0 through 256.
- Added per-evaluation Type-63 range coverage, maximum quantum/factorial arguments, and exact-validation provenance.
- Reject exact qualification when the required log-factorial argument exceeds the static reference table.
- Preserve v0.6.32 Type-88 mixed-grid semantics, exact orchestration rows/checkpoints, and all accepted live science paths.

## 0.6.32 - 2026-06-07

- Hotfix the native Mg rate/data 42/88 scalar shadow to use the full high-resolution `epi_eV` / `bremsa` radiation grid.
- Prohibit reduced `epim_eV` / `bremsam` fallback from qualifying Type-88 parity.
- Report full/reduced grid point counts, grid source, validation failures, and reduced-grid fallback count.
- Keep all accepted scalar rates, matrix terms, solver inputs, populations, and science products unchanged and live on the accepted path.
- Preserve the v0.6.30 composite checkpoint hotfix and v0.6.31 native Type-63 scalar shadow.

## 0.6.31 - 2026-06-07

- Added a shadow-only native C++ scalar evaluator for Mg rate/data families 3/63 and 42/88.
- Ported the type-63 same-n l-mixing and n-changing record-order formulas, including heating/cooling energy channels.
- Ported type-88 photoionization scalar evaluation from raw cross-section pairs and the shared live radiation grid.
- Kept accepted scalar rates and all live matrix terms unchanged; native results are compared only.
- Preserved the v0.6.30 composite checkpoint substitution hotfix and exact row-orchestration gate.

## 0.6.30 - 2026-06-07

- Hotfix the v0.6.29 orchestration-shadow complete-matrix checkpoint replacement to use a stable composite matrix-term identity rather than non-unique `term_index`.
- Report duplicate term-index and replacement-key counts plus expected/applied replacement totals.
- Keep the orchestration path shadow-only; accepted rows remain the sole live matrix source.
- Prefer the active source-tree `xstar_tools.__version__` over stale installed distribution metadata in progress banners and wrappers.

## v0.6.29 - 2026-06-07

### Added
- Added one evaluation-level C++ Mg rate-payload orchestration shadow for rate/data families 4/50, 3/51, 3/63, and 42/88.
- Added compact record indexing, one-call ABI transport, direct C++ matrix/heating term construction, exact row comparison, and independent contribution-matrix checkpoints.
- Added `provenance.mg_rate_payload_batched_orchestration_shadow_summary`, a dedicated wrapper, and a strict acceptance checker.

### Preserved
- Kept all accepted scalar rates and matrix terms live on the accepted product path; C++ shadow rows are never committed.
- Kept the promoted cached Mg simple-payload product active with reverse verification and heavy checkpoint hashing disabled.
- Kept all accepted solver, rates, matrix, final-binemis, and upstream Mg type-4/type-50 paths unchanged.

## v0.6.28 - 2026-06-07

### Added
- Added an observational Mg rate-payload generation dataflow probe that decomposes the v0.6.27 exclusive `rate_payload_generation` parent section.
- Added per-evaluation exclusive section metrics for wall time, calls, ions, records, emitted terms, byte traffic, and allocations.
- Added grouped top-N diagnostics by rate type, data type, and rate-type/data-type pair.
- Added `provenance.mg_rate_payload_dataflow_summary`, a dedicated probe wrapper, and an acceptance checker.

### Preserved
- Kept the promoted cached Mg simple-payload batch active with zero-change guarded fallback behavior.
- Kept reverse verification and checkpoint hashing disabled in the main probe.
- Kept all accepted solver, rates, matrix, final-binemis, and upstream Mg type-4/type-50 science paths unchanged.

## v0.6.27 - 2026-06-07

### Added
- Added an observational Mg matrix-assembly dataflow probe with 16 named exclusive sections and per-evaluation accounting.
- Added rows, matrix dimensions, nonzero counts, byte traffic, and allocation counts for each section.
- Added `provenance.mg_matrix_assembly_dataflow_summary` with section totals, top evaluations, accounting failures, and full evaluation ledgers.
- Added a dedicated promoted-product probe wrapper and checker.

### Preserved
- Kept the v0.6.26 cached Mg simple-payload batch promoted and product-active.
- Kept reverse verification and full checkpoint hashing disabled in the main probe.
- Kept all previously accepted solver, rates, matrix, final-binemis, and upstream Mg type-4/type-50 paths unchanged.

## v0.6.26 - 2026-06-07

- Promotes the verified cached one-call-per-element Mg simple-payload batch as an accepted opt-in product path.
- Preserves immediate fallback to the accepted per-ion path on cache, C++, count, identity, overflow, or non-finite validation failures.
- Keeps old-per-ion reverse verification available as an opt-in diagnostic.
- Makes expensive matrix/population/heating checkpoint hashing opt-in so the normal promoted wrapper does not carry diagnostic overhead.
- Keeps the broad emissivity backend in Python and preserves all previously accepted solver, rates, matrix, final-binemis, and upstream Mg type-4/type-50 paths.

## v0.6.25 - 2026-06-07

- Product candidate for the cached Mg simple-payload batch path only.
- Immediate accepted per-ion fallback on batch/cache/count/integer/non-finite validation failure.
- Optional old-per-ion verification shadow.
- Exact pre-solver matrix, solved-population, and heating/cooling checkpoints for baseline comparison.

## 0.6.24 - 2026-06-06

- Keeps all accepted product paths unchanged; Mg simple-payload batching remains shadow-only and cannot affect live matrices or populations.
- Fixes the v0.6.23 duplicate `batch_ion_count` profiling argument so completed shadow evaluations are not misreported as failures.
- Caches immutable Mg atomic/source arrays once per process and reuses them across element evaluations.
- Packs compact ion metadata and the selected `npfi` columns once per evaluation, filters statically zero-output ions, and sizes output buffers to the exact expected supported-row count.
- Reports cache hits/misses, support-index hits/misses, actual copied bytes, immutable/evaluation buffer sizes, zero-output ions skipped, and peak working-set bytes.
- Requires zero shadow failures, no missing/extra rows, and exact row parity before the checker returns an accepted shadow gate.

## 0.6.23 - 2026-06-06

- Adds stage-level timing for the accepted Mg ion simple-payload C++ path: input preparation, Python-to-C++ call, internal C++ compute, output unpack/commit, allocation and byte counts.
- Adds an optional one-call-per-element C++ batch implementation under `XSTAR_ATOMIC_MATRIX_MG_SIMPLE_PAYLOAD_BATCH_SHADOW=1`.
- Compares batch rows against the accepted per-ion rows before live matrix consumption; batch output is shadow-only and cannot affect matrices, populations, or science products.
- Adds top-N reporting by element, ion/stage, evaluation, matrix dimension, payload length, and source-record count.
- Retains the v0.6.22 cleaned timing aggregation and all accepted product paths.

## 0.6.0a37

- Fixes v0.6.0a36 type53 shadow fallback regression: initialize parent map packing counters inside the type53 C++ bridge before use.
- Adds checker reporting for enabled-but-empty shadow diagnostics and backend fallback counters so this failure mode is visible instead of only printing None fields.
- Type53 remains shadow-only; C++ type53 is not applied to products.

## 0.6.0a36

- Fix type53 parent excitation packing for shadow parity when `context.extras` maps use string keys.
- The a34 C++ path packed the parent-energy map but only looked up integer keys; many runs therefore still used the base threshold for `idest2 > nlevp`.
- Adds robust int/string/float-key lookup for `parent_level_energy_ev_by_destination` and `parent_level_stat_weight_by_destination`.
- Refreshes package metadata/egg-info version stamping so runtime reports 0.6.0a36.
- Type53 remains shadow-only; C++ type53 is not applied to products.

## 0.6.0a34

- Fixes type53 C++ shadow parent-excitation packing.
- Passes `context.extras["parent_level_energy_ev_by_destination"]` and parent statistical weights into the C++ type53 packing path.
- Uses the explicit parent-excitation map for `idest2 > nlevp` threshold construction instead of relying on leveltemp destination energy.
- Keeps type53 C++ shadow-only; no product physics are changed by the C++ candidate path.


## v0.6.0a32

- Baked the type53 shadow checker fix so diagnostics are found under `python_run.provenance` as well as the legacy top level.
- Added per-record Mg type53 shadow intermediates for Python and C++: threshold, rnist, sumr, sumi, sumh, sumh2, sumc, sumc2, ans1..ans6, nb1, and klmax.
- Extended the C++ type53 shadow ABI with a diagnostic buffer. This remains diagnostic-only; Python stays the applied physics and C++ type53 remains disabled for product application.

## v0.6.0a30 - explicit C++ backend wrapper for proven type49 path

- Adds a standalone full C++-requested benchmark wrapper (`run_v0600a30_xstar_tools_cpp_type49.sh`) outside the sdist artifacts.
- The wrapper passes explicit CLI backend options instead of chaining through a Python-reference wrapper:
  - `--backend cpp`
  - `--solver-backend cpp`
  - `--rates-backend cpp`
  - `--matrix-backend cpp`
  - `--emissivity-backend cpp`
- Keeps unproven high-risk subpaths disabled by environment defaults: type53, pre-matrix photo shortcuts, broader direct accumulation, and C++ binemis.
- Retains Mg rate_type=7/data_type=49 C++ matrix path as the only promoted matrix optimization, based on v0.6.0a28 shadow parity (`records_mismatched=0`, `records_failed_tolerance=0`).


## v0.6.0a29 - Promote parity-proven Mg type49 C++ path for auto matrix backend

- Promotes the Mg `rate_type=7` / `data_type=49` C++ matrix direct path for `matrix-backend=auto` and explicit `matrix-backend=cpp` after the v0.6.0a28 shadow gate matched all 48,343 compared records with only double-precision roundoff.
- Keeps type51, the broader Mg direct accumulator, type53 photoionization path, pre-matrix shortcuts, and C++ binemis opt-in by default; source scanning remains allowed because the promoted type49 path uses it only to enumerate candidate records.
- Preserves opt-out controls: set `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_CPP=0` or `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_AUTO=0` to force Python handling of type49 while using the C++ matrix backend for other proven paths.
- Renames the matrix backend implementation string to `xstar_matrix_mg_ion_type49_auto_default_type53_optin_v15`.

## 0.6.0a27 - Type49 effective-scalar shadow comparator

- Refines the Mg rate_type=7/data_type=49 shadow-parity comparator so scalar C++ rows are compared after the same calc_hmc_ion gates used by the Python reference and direct C++ application path: pirt contributes only when `idest1 == 1`, and rrrt contributes only when `idest2 >= nlev`.
- Keeps C++ type49/type53 physics opt-in; this release changes diagnostics/comparison semantics, not the applied physics.
- Leaves the remaining type49 kernel mismatch localized to true effective records such as record 40056 (`idest1=1`, `idest2=50`), rather than false scalar mismatches from excited-source records like record 40547 (`idest1=5`).


## v0.6.0a25

- Fixes the next Mg type49 shadow-parity mismatch after the v0.6.0a24 record-pointer correction.
- The C++ type49/type53 packers now pass persistent higher `leveltemp` destination energies for parent destinations (`idest2 > nlevp`) into the C++ kernel.
- The C++ matrix kernel now uses those higher destination energies for the final ans5/ans6 electron-POV energy correction, matching Python `ucalc._leveltemp_destination_energy` semantics instead of falling back to the continuum energy.
- C++ physics remains opt-in; shadow mode remains the recommended validation path before direct type49/type53 application.

## v0.6.0a24 - Type49 shadow pointer parity hotfix

- Fixed the C++ type49/type53 candidate pointer packing to convert one-based atomic record numbers to zero-based `nptrs` rows before reading `nreal`, `nint`, `real_ptr`, and `int_ptr`.
- This addresses the shadow-parity signature where record N in C++ used record N+1 payloads, shifting scalar rates and matrix destination rows by +1.
- Updated type49 shadow comparison to treat the C++ scalar row as carrying both `pirt` (`aj1`) and `rrrt` (`aj2`), matching the direct-application path.
- C++ direct accumulator paths remain opt-in; Python remains the default physics reference.


- Added opt-in Mg rate_type=7/data_type=49 shadow parity mode.
- In shadow mode, Python remains the only applied physics path; C++ type49 is evaluated beside it and compared record-by-record.
- Captures scalar pirt/rrrt deltas and four-row matrix term deltas for each sampled record.
- Exposes `mg_type49_shadow_parity_summary` and `mg_type49_shadow_parity_samples` in run provenance.
- Keeps C++ type49/type53 direct accumulators opt-in and non-default until Python-vs-C++ parity passes.

## v0.6.0a22 - Python-reference C++ parity gates

- Reframes parity policy: the current Python implementation is the physics reference for enabling C++ accelerators. Exact original Fortran-XSTAR product identity is not required before C++ development, but every C++ path must match the Python-reference run before becoming default.
- Keeps type-49/type-53 Mg direct accumulators, pre-matrix shortcuts, and C++ binemis opt-in only.
- Adds `xstar-tools-cpp-parity-gate` and `xstar_tools.xstar.cpp_parity_gate` to compare a Python-reference product directory against a C++ candidate directory. The gate checks `xout_step.log` summary rows, option 22 values, option 27 Mg ion columns, and FITS existence/size/structure/hash metadata.
- Fixes provenance/summary reporting so a requested Python backend prints `python_reference` instead of showing an available C++ shared-library implementation name.
- Fixes emissivity backend status resolution so `EMISSIVITY_BACKEND=python` reports active Python even when `libxstar_emissivity.so` is buildable.

## v0.6.0a21 - original-XSTAR parity defaults

- Restores a2-a12-like physics as the default by making Mg direct accumulator, type-49/type-53 photoionization fast paths, pre-matrix photo shortcuts, and C++ binemis opt-in.
- Keeps solver/rates/matrix/emissivity C++ libraries buildable and selectable, but the parity wrapper defaults all backend selectors to Python.
- Adds source-like ASCII TABLE one-byte intercolumn gaps for final FITS and xout_abund1.fits products, fixing table widths such as xout_cont1/xout_spect1 NAXIS1=69, xout_lines1 NAXIS1=128, and abundance-table row widths.
- Restores source-row RRC final-table emission by default so inactive RRC rows remain represented instead of being filtered out by nonzero luminosity.
- Adds original-XSTAR parity gate tooling for xout_step.log option 17/22/27 and FITS hash/size/structure checks.

## v0.6.0a20

- Fixed v0.6.0a19 output-writer crash by keeping `output_writer_timing_breakdown` numeric-only and summing only numeric timing values.
- Kept `MATRIX_MG_ION_DIRECT_ACCUM_CPP=1` as the default, but changed the experimental Mg `rate_type=7/data_type=53` photoionization accumulator default to off because it changes the thermal convergence printout (`h-c(%)` and final iteration column) relative to the validated a15/type49-only path.
- Added explicit opt-in for type-53 experiments via `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE53_PHOTO_CPP=1`; pre-matrix type-53 follows the same opt-in unless `XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_TYPE53_CPP` is set.
- Kept the C++ binemis backend enabled by default with numeric timing diagnostics only.

## v0.6.0a19 - C++ binemis emissivity backend

- Added `libxstar_emissivity.so` in the flat `src/xstar_tools/xstar/cpp/` backend directory.
- Added `line_emissivity.cpp` with `xstar_emissivity_build_binemis_profile(...)`, a real C++ backend for the `binemis` strong-line profile loop.
- Added `xstar_tools.xstar.cpp_backend_emissivity` and enabled `XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP=1` by default with Python fallback.
- Kept the successful Mg rate_type=7/data_type=49 and data_type=53 direct accumulator enabled by default.
- Updated build scripts so `make`, `build_lib.sh`, and `setup.py build_py` build `libxstar_emissivity.so` alongside solver/rates/matrix libraries while keeping all shared libraries only under `src/xstar_tools/xstar/cpp/`.

## v0.6.0a18 - Mg direct accumulator default and binemis sparse profile scan

- Made the successful Mg ion direct accumulator path default-on. Set `XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=0` to force the old Python path.
- Kept the flat C++ shared-library layout under `src/xstar_tools/xstar/cpp/`.
- Retained the v0.6.0a16/v0.6.0a17 rate-type 7 type-49/type-53 direct accumulators.
- Reduced `binemis` Python overhead by iterating only nonzero ranked line slots in source-equivalent `kl, rank` order instead of scanning all `ncn2 * 10` slots.
- Added timing fields for nonzero ranked slots and skipped ranked slots in the binemis profile builder.

## v0.6.0a17 - Mg source-scan packing cache and post-type53 profiling cleanup

- Kept the v0.6.0a16 type-49/type-53 direct accumulator behavior.
- Added cached 1-based record header arrays for Mg ion source scans so the scanner no longer rebuilds full record-rate/data-type arrays once per ion.
- Preserved the flat C++ backend layout under `src/xstar_tools/xstar/cpp/` and kept shared libraries in that directory only.
- No new physics branch is enabled in this release; the goal is to reduce Python packing overhead now that rate_type=7 construction is no longer dominant.

## v0.6.0a16 - Fix Mg rate-type 7 type-53 accumulator activation

- Fixed the v0.6.0a14/v0.6.0a15 type-53 C++ activation bug: `accumulate_mg_ion_rate7_type53_terms_cpp_detailed()` called an undefined `_radiation_grid_arrays_for_type53()` helper, so every type-53 candidate fell back before reaching `libxstar_matrix.so`.
- Added `_radiation_grid_arrays_for_type53()` as an alias of the validated type-49 live radiation-grid accessor because both branches use the same phint53-like continuum/photoionization grid.
- Updated the matrix backend name to `xstar_matrix_mg_ion_direct_accumulator_type49_type53_v12`.
- Kept the flat C++ layout and `.so` location rule: shared libraries stay only in `src/xstar_tools/xstar/cpp/`.
- Added granular classifier component names such as `remaining_rate7_by_source_header_data_type.53` and `remaining_rate7_by_source_and_result_data_type.53_to_53` for future family identification.

## v0.6.0a15 - Mg rate-type 7 result-family classifier

- Added an observational classifier for the remaining Python-evaluated Mg `rate_type=7` records after the direct C++ accumulator consumes supported records.
- Records per remaining Python-evaluated `rate_type=7` row: source record, source header rate/data type, result rate/data type, ion stage/index, elapsed seconds, and matrix-insertion status.
- Adds aggregate profile components: `remaining_rate7_by_source_header_data_type`, `remaining_rate7_by_result_data_type`, and `remaining_rate7_by_source_and_result_data_type`.
- Stores bounded samples in `profile_control["remaining_rate7_classifier_samples"]` for forensic follow-up.
- No new physics path is enabled in this release; the classifier identifies the next source family to move into the Mg ion direct accumulator.

## v0.6.0a14 - Mg rate-type 7 type-53 photoionization C++ accumulator

- Added experimental Mg ion direct-accumulator support for rate_type=7/data_type=53 OP photoionization-style records in libxstar_matrix.so.
- Kept flat C++ layout and .so outputs in src/xstar_tools/xstar/cpp/.
- Updated matrix backend name to xstar_matrix_mg_ion_direct_accumulator_type49_type53_v11 and feature flags to include the type-53 experimental branch.
- Added separate profile counters under calc_hmc_all.element_solver.mg_ion_rate7_type53_cpp_kernel so type-53 coverage, fallbacks, packing, and C++ kernel time can be evaluated independently.

## v0.6.0a13 - Mg rate-type 7 type-49 photoionization C++ accumulator

- Adds an experimental Mg ion-level direct accumulator for rate_type=7/data_type=49 photoionization-style records.
- Keeps the flat src/xstar_tools/xstar/cpp shared-library layout.
- Adds counters for type-49 candidate, supported, matrix-term, and scalar-row coverage.
- The path is gated behind MATRIX_MG_ION_DIRECT_ACCUM_CPP=1 and MATRIX_MG_ION_TYPE49_PHOTO_CPP=1 while benchmark parity and timing are validated.

## v0.6.0a12 - Mg direct accumulator rate-type 7 scalar coverage

- Added scalar-row support to the experimental Mg ion direct accumulator so supported rate_type=7 rows can update second-pass scalar pirt/rrrt totals without being converted back into Python UCalc rows.
- Changed the direct-accumulator coverage gate to use rate_type=7 coverage when MATRIX_MG_ION_DIRECT_ACCUM_RATE7_ONLY=1, instead of dividing supported records by the full source-record scan count.
- Added C++ counters for rate_type=7 records seen/supported by the direct accumulator.
- Kept the flat C++ layout and a10 shared-library location rule: libxstar_*.so files live only under src/xstar_tools/xstar/cpp/.


## v0.6.0a11 - Mg direct-accumulator gating and compact buffer sizing

- Kept the v0.6.0a10 flat C++ shared-library layout under `src/xstar_tools/xstar/cpp/`.
- Updated `libxstar_matrix.so` backend name to `xstar_matrix_mg_ion_direct_accumulator_v8`.
- Added cached compact ATDB arrays for the experimental Mg ion direct accumulator to avoid copying full `nptrs/rdat/idat` arrays once per ion.
- Bounded direct-accumulator output buffers by active ion source-record count instead of whole-ATDB record count.
- Added coverage gates for `XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=1` so low-coverage experiments fall back instead of silently applying tiny subsets and adding large overhead.
- Added direct-accumulator profile counters for supported fraction and gate status.

## v0.6.0a10 - Mg ion direct accumulator guardrail and C++ build cleanup

- Fixed the `matrix_kernels.cpp` `-Wall -Wextra` warning from unused simple-payload integer variables.
- Changed `src/xstar_tools/xstar/cpp/Makefile` so `make` builds shared libraries only in `src/xstar_tools/xstar/cpp/`; it no longer copies `libxstar_solver.so`, `libxstar_rates.so`, or `libxstar_matrix.so` into `src/xstar_tools/xstar/`.
- Updated C++ backend loaders to use the `cpp/` directory as the only package-local shared-library location, while retaining explicit environment-variable overrides.
- Rewrote `src/xstar_tools/xstar/cpp/README.md` to document the current flat C++ backend layout and the three shared libraries.
- Disabled the v0.6.0a9 Mg simple-payload path by default because the benchmark showed ~143.9 s of packing overhead for only 112 applied rows and a wall-time regression. It remains available behind `XSTAR_ATOMIC_MATRIX_MG_ION_SIMPLE_PAYLOAD_CPP=1`.
- Added an experimental opt-in direct Mg-ion simple-payload accumulator, `xstar_matrix_accumulate_mg_ion_source_simple_terms`, behind `XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=1`. It emits matrix terms directly and is not enabled by default until full benchmark parity and timing improvement are proven.

## v0.6.0a9 - Mg ion simple payload evaluation backend

- Widened the Mg ion-level C++ matrix ABI from source-pointer scanning to source-pointer scanning plus packed payload decoding/evaluation for selected no-grid/no-level rate groups.
- Added `xstar_matrix_eval_mg_ion_source_simple_payloads` in the existing flat `src/xstar_tools/xstar/cpp/matrix_kernels.cpp` library.
- Added Python binding `eval_mg_ion_source_simple_payloads_cpp_detailed` and attached it to the Mg `calc_hmc_all.element_solver` loop.
- Supported first dominant non-type-51 groups: data types 1, 2, 3, 7, 8, and 20, including the rate-type 7/data-type 7 group that dominated the a8 timing report.
- Added profile counter `calc_hmc_all.element_solver.mg_ion_simple_payload_cpp_kernel` to show `records_seen`, `records_supported`, `records_batched`, `cpp_calls`, and `ucalc_cpp_applied`.
- Kept Python fallback for unsupported records and all grid/level/radiation-dependent branches.

## v0.6.0a26

- Added type49 shadow-parity worst-sample tracking so the run provenance retains the largest remaining scalar/matrix mismatches, not only the first sampled records.
- Added per-channel mismatch counters and tolerance-aware pass counts for Mg type49 Python-vs-C++ shadow comparisons.
- Updated the standalone shadow checker to report exact and tolerance-aware readiness plus first/worst sample counts.

## v0.6.0a8 - Mg ion source-pointer traversal backend

- Added the flat-folder C++ ABI `xstar_matrix_scan_mg_ion_source_records(...)` in `src/xstar_tools/xstar/cpp/matrix_kernels.cpp`.
- Moved Mg ion `npfi -> npnxt -> npar` source-pointer traversal into `libxstar_matrix.so` when the matrix backend is active.
- Added `calc_hmc_all.element_solver.mg_ion_source_traversal_cpp_kernel` counters with source records seen, supported masks, type-51/type-7/simple-group counts, and loop-guard diagnostics.
- Kept unsupported payload physics on the Python fallback path while preserving the ion-level ABI boundary needed for moving more rate/data groups into C++ next.
- Preserved the flat C++ layout under `src/xstar_tools/xstar/cpp/`; no per-library C++ subdirectories were added.

## v0.6.0a7 - Mg ion-level C++ backend boundary

- Kept all C++ sources and shared libraries in the single flat `src/xstar_tools/xstar/cpp/` directory.
- Added a first Mg ion-level C++ backend entry point, `xstar_matrix_eval_mg_ion_type51_rates_and_matrix(...)`, as the v0.6.4-style widening target.
- Routed the existing Mg `rate_type=3/data_type=51` source-ordered payload batch through the ion-level ABI and added `calc_hmc_all.element_solver.mg_ion_cpp_kernel` counters for ion calls, records seen/batched, applied C++ ucalc rows, emitted matrix terms, and fallback rows.
- Preserved Python fallback and parity-gated behavior; this release is a boundary-widening step and should be benchmarked against `ion_loop`, `level_matrix_assembly_total`, and `rate_construction`.
- Removed root-level `XSTAR_SOURCE_CHANGES*.md` files from the source tree and `MANIFEST.in`; `CHANGELOG.md` is now the canonical covered history.

## v0.6.0a6 - Mg type-51 C++ full-run activation

- Kept the flat C++ backend layout under `src/xstar_tools/xstar/cpp/`.
- Tightened Mg type-51 payload eligibility before deferring records to the coarse C++ rates+matrix ABI.
- Relaxed the Mg type-51 parity gate to diagnostic-by-default with `XSTAR_ATOMIC_MATRIX_MG_RATES_MATRIX_PARITY_STRICT=1` available for hard failure.
- Aligned the C++ type-51 energy-conversion constant with the Python/source-faithful evaluator.
- Intended to make `mg_type51_rates_matrix_cpp_kernel.cpp_calls` and `ucalc_cpp_applied` nonzero in full `mg11_ne1e8` runs so rate-construction timing can be rechecked.


This changelog is now the canonical package history for the `xstar-tools` transition. Future releases should update this file first, then package artifacts and release notes should refer back to it.

## v0.6.0a5

- Adopt the uploaded full-history changelog as the package changelog for the `xstar_tools` line and add the missing `v0.6.0a0`--`v0.6.0a4` entries.
- Clarify backend reporting in the physical runner summary: `backend=python` was the requested global/default backend, not evidence that the optional C++ sub-backends were inactive. The summary now reports requested and active status for solver, rates, matrix, and emissivity separately.
- Keep the flat C++ backend layout under `src/xstar_tools/xstar/cpp/`; no per-library C++ subdirectories are introduced.
- Keep the v0.6.0a4 Mg type-51 context fix and C++ backend availability unchanged.
- Note from the user-provided v0.6.0a4 benchmark: the solver, rates, matrix, and emissivity backends were active as C++ in provenance, while the new type-51 rates+matrix counter saw and batched records but still fell back before calling the C++ kernel. The next performance patch should inspect the fallback/parity error and make `mg_type51_rates_matrix_cpp_kernel.cpp_calls` and `ucalc_cpp_applied` nonzero in the full benchmark.

## v0.6.0a4

- Fixed the Mg type-51 C++ parity/fallback path after `UCalcContext` rejected unsupported constructor fields.
- Moved parent-level energy/statistical-weight maps into `UCalcContext.extras` using the existing runtime keys.
- Preserved the flat `src/xstar_tools/xstar/cpp/` shared-library layout.
- Validation checker confirmed the standalone coarse type-51 C++ ABI path could report nonzero `cpp_calls`, `ucalc_cpp_applied`, and emitted matrix terms.

## v0.6.0a3

- Added `xstar_matrix_build_mg_type51_rates_and_matrix(...)` to `matrix_kernels.cpp`.
- Moved selected Mg `rate_type=3/data_type=51` Burgess-Tully/CHIANTI-style `ucalc` evaluation into the coarse Mg rates+matrix ABI for 5-point and 9-point payloads.
- Added `mg_type51_rates_matrix_cpp_kernel` counters for records seen/batched, C++ calls, C++ `ucalc` applications, fallbacks, and emitted matrix terms.
- Kept all C++ files and produced libraries in the single flat `src/xstar_tools/xstar/cpp/` directory.

## v0.6.0a2

- Added the first coarse Mg rates+matrix ABI skeleton, `xstar_matrix_build_mg_rates_and_matrix(...)`, in the existing flat `matrix_kernels.cpp`.
- Attached the ABI to the real `calc_hmc_all.element_solver` Mg matrix path.
- Added counters for records seen, records batched, C++ calls, emitted matrix terms, fallback count, unsupported rate/data groups, invalid endpoints, nonfinite answers, and parity-gate records.
- First supported group was Mg `rate_type=3/data_type=51`, initially using Python source-faithful `ucalc` with C++ matrix-term construction/attachment.

## v0.6.0a1

- Converted the package to a clean `xstar_tools` source tree and removed the duplicated full `src/xstar_atomic/` implementation tree.
- Kept the requested top-level package scaffolding: `atomic`, `xstar`, `tables`, `parallel`, `io`, `diagnostics`, `benchmarks`, and `cli`.
- Removed legacy `xstar-atomic-*` entry points in favor of `xstar-tools-*` commands.
- Kept optional C++ shared libraries under `src/xstar_tools/xstar/cpp/`.

## v0.6.0a0

- Introduced the `xstar-tools` distribution name and `xstar_tools` Python import namespace.
- Added the first migration scaffold from `xstar_atomic` to `xstar_tools.xstar`.
- Preserved source-faithful runtime behavior while beginning the namespace/layout transition.
- No physics-speed changes were intended in this layout-only migration step.

This changelog has been updated from the available v0.5.72 source tree, the subsequent v0.5.73--v0.5.75 benchmark/release notes, the uploaded archive containing source packages v0.5.37--v0.5.49 and v0.5.51, the uploaded pre-v0.5.00 changelog/source-change archive, and the current ChatGPT development conversation through the v0.5.75 `mg11_ne1e8` benchmark result plus the later output/timing follow-up discussion. It emphasizes what is implemented, what benchmarks showed, and what remains explicitly unfinished.

### Unreleased / Next planned work

- Replace isolated Mg type-51 micro-kernel attempts with a coarser `libxstar_matrix.so` ABI, tentatively `xstar_matrix_build_mg_rates_and_matrix(...)`, that owns a source-ordered Mg rates + matrix pass rather than only per-branch `ucalc` evaluation.
- Target the true thermal-balance bottleneck rather than output writing:
  - `dsec.calc_hmc_all` remains about 690--700 s in the Mg benchmark.
  - `calc_hmc_all.element_solver` remains about 600 s.
  - `calc_hmc_all.element_solver.level_matrix_assembly_total` remains about 510--525 s.
  - `rate_construction` / `ucalc` remains the dominant inner cost.
- Keep the `pprint(17)` thermal iteration count and first `h-c(%)` residual source-faithful. Do not use display-only offsets to hide the extra Python thermal iteration; diagnose the residual trajectory and convergence branch instead.
- Continue toward larger C++ ownership in this order:
  1. Mg rates + matrix assembly for one element/ion block.
  2. Mg thermal residual contribution and iteration diagnostics.
  3. Full Mg element thermal evaluation.
  4. Full zone-level thermal backend.
- Output writer work should continue only after the thermal path is addressed; v0.5.73/v0.5.74 showed that actual FITS writes are under one second and the residual output delay is product construction, not disk I/O.
- Add a production-facing switch to suppress optional CSV/JSONL diagnostics once smoke tests are passing. The current intended policy is to keep science FITS and `xout_step.log` always on, but make heavy debug products such as continuum side-effect CSV/JSONL, phase-snapshot CSV/JSONL, forensic profile rows, and other optional diagnostics controllable by `--diagnostics {full,summary,none}` and/or equivalent environment variables.
- Ensure stale optional diagnostic files are removed on overwrite reruns when diagnostics are disabled, so a `--diagnostics none` result directory cannot accidentally contain old CSV/JSONL artifacts from an earlier debug run.
- Add a more source-like timing footer to `xout_step.log`, including both raw seconds and a human-readable minutes+seconds total. The original XSTAR footer uses cumulative/checkpoint labels such as `after writespectra`, `after writespectra2`, `after writespectra3`, `after writespectra4`, and `total time`; Python should keep those labels while also adding `total time mm:ss` or equivalent.
- Clarify and preserve the meaning of the `writespectra*` timing labels: `writespectra` builds/writes the final binned spectrum `xout_spect1.fits`; `writespectra2` builds/writes final line luminosities `xout_lines1.fits`; `writespectra3` builds/writes continuum-only spectrum `xout_cont1.fits`; and `writespectra4` builds/writes final RRC table `xout_rrc1.fits`. The footer values should be treated as elapsed timing checkpoints around these output phases, not physics quantities.

## v0.5.75

- Attempted to connect the Mg `data_type=51` C++ `ucalc` batch path to the real `calc_hmc_all.element_solver.rate_construction` hot path.
- Updated the type-51 payload collector to use decoded collision-row data instead of manually guessing packed ATDB record layout.
- Broadened the C++ type-51 evaluator in `libxstar_matrix.so` to handle both 5-point and 9-point Burgess-Tully/CHIANTI-style collision rows.
- Backend identity for the matrix library became `xstar_matrix_mg_type7_terms_dense_ucalc_type51_payload_v1`.
- Validation included compile checks, shared-library build, and a 9-point type-51 ABI smoke test.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Total runtime was about 899 s, or 14 min 59 s.
  - No meaningful improvement relative to v0.5.72--v0.5.74.
  - The C++ matrix library loaded, but the type-51 path still did not move the dominant Python hot path enough to matter.
- Known limitation: this release demonstrated that isolated type-51 micro-kernel work is not sufficient. The next implementation should move to a coarse Mg rates + matrix ABI.

## v0.5.74

- Added finer output-product timing to identify the remaining post-output delay.
- Split `final_product_build` into sub-timings for spectrum construction, `binemis`/profile work, table packing, line table build, continuum table build, and RRC table build.
- Added explicit matrix type-51 no-payload counters so that the summary can distinguish:
  - C++ unavailable.
  - C++ available but no eligible payload collected.
  - Eligible payload collected but unsupported.
  - Eligible records applied.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Total runtime was about 897 s.
  - Output timing showed actual FITS writes were less than one second total.
  - The residual output delay was dominated by final spectral-product construction, not FITS I/O.
  - The dominant total runtime remained `calc_hmc_all` and Mg level-matrix/rate construction.

## v0.5.73

- Kept `OUTPUT_FINAL_RECOMPUTE=0` as the default benchmark mode.
- Moved the terminal message `xstar: Prepping to write spectral data` closer to the actual final FITS writing stage instead of printing it before slow output-product construction.
- Persisted `output_writer_timing_breakdown` into `summary.json` and appended the breakdown to `xout_step.log`.
- Added per-file timing keys for important FITS products:
  - `xo01_detail.fits`
  - `xo01_detal2.fits`
  - `xo01_detal3.fits`
  - `xo01_detal4.fits`
  - `xout_spect1.fits`
  - `xout_lines1.fits`
  - `xout_cont1.fits`
  - `xout_rrc1.fits`
- Confirmed via v0.5.73 benchmark that the remaining post-output delay is not Astropy file writing itself.

## v0.5.72

- Added `OUTPUT_FINAL_RECOMPUTE=0` benchmark mode and made it the default in the v0.5.72 wrapper.
- Skipped the duplicated final local recompute before final FITS construction when `OUTPUT_FINAL_RECOMPUTE=0`.
- Preserved source-like mode with `OUTPUT_FINAL_RECOMPUTE=1` for comparison.
- Added output-phase timing breakdown in the Python runner.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Runtime improved from about 945.9 s to about 910.6 s relative to v0.5.71.
  - All ten Python products were present.
  - Science/detail/spectral FITS products matched v0.5.71 byte-for-byte; `xout_abund1.fits` differed only through FITS checksum/date bookkeeping.
  - The historical top-level `all_files_match=False` status remained unchanged.

## v0.5.71

- Added the first batched Mg `data_type=51` `ucalc` ABI in `libxstar_matrix.so`:
  - `xstar_matrix_eval_type51_ucalc_batch`
- Extended the matrix backend identity to `xstar_matrix_mg_type7_terms_dense_ucalc_type51_v1`.
- Added feature flag `16` for batched Mg data-type-51 `ucalc` support.
- Wrapper added `MATRIX_TYPE51_UCALC_CPP=1` to enable the attempted C++ path.
- Kept `MATRIX_DENSE_FILL_CPP=0` by default because dense-fill C++ added packing overhead in v0.5.68.
- Benchmark outcome:
  - Runtime stayed around 946 s.
  - The type-51 C++ path did not produce meaningful speedup.
  - Later analysis showed the type-51 path was not properly attached to the real Mg thermal-balance hot path.

## v0.5.70

- Removed the non-source-faithful display-only `ntotit` decrement that had been introduced in v0.5.69.
- Restored raw translated thermal-iteration count in `pprint(17)` output.
- Added Mg thermal-rate forensic profiling by:
  - rate type,
  - data type,
  - combined rate/data type.
- Added `records_seen`-style counters and Mg matrix/ucalc forensic samples into summary provenance.
- Expanded residual trajectory diagnostics for thermal-balance evaluation.
- Benchmark outcome:
  - Runtime remained around 950 s.
  - `pprint(17)` continued to show an extra thermal iteration versus original XSTAR, confirming this is a real convergence/path issue rather than a print-format issue.

## v0.5.69

- Added selected simple `ucalc` branch ABI in `libxstar_matrix.so`:
  - `xstar_matrix_eval_simple_ucalc`
- Supported selected simple analytic branches initially identified as data types 1, 2, 3, 7, 8, and 20.
- Disabled dense matrix fill by default with `MATRIX_DENSE_FILL_CPP=0` because previous dense-fill C++ did not improve runtime.
- Added first residual-trajectory summary scaffolding for thermal-balance debugging.
- Introduced a display-only `ntotit` decrement in `pprint(17)`; this was later recognized as non-source-faithful and removed in v0.5.70.
- Known limitation: the new simple-branch ABI was validated but not yet attached as a default hot-path batched Mg thermal backend.

## v0.5.68

- Added dense matrix/heating matrix fill support to `libxstar_matrix.so`:
  - `xstar_matrix_dense_fill_terms`
- Matrix backend identity became `xstar_matrix_mg_type7_terms_dense_v1`.
- Added feature flag `4` for dense matrix/heating fill.
- Benchmark outcome:
  - Runtime regressed slightly to about 960.9 s.
  - The dense C++ kernel itself was fast, but packing overhead outweighed the benefit.
- Known limitation: moving only dense matrix insertion is too small a kernel; the dominant cost remains Python rate construction/`ucalc` and source-order traversal.

## v0.5.67

- Started the dedicated `libxstar_matrix.so` shared library.
- Added C ABI:
  - `xstar_matrix_abi_version`
  - `xstar_matrix_backend_name`
  - `xstar_matrix_feature_flags`
  - `xstar_matrix_probe`
  - `xstar_matrix_build_mg_type7_terms`
- Moved the already-validated Mg record-type-7 matrix-term construction out of `libxstar_rates.so` and into `libxstar_matrix.so`.
- Added matrix backend status/provenance reporting.
- Benchmark outcome:
  - Matrix library loaded correctly.
  - Runtime remained about 949 s because the moved kernel represented only about 0.1--0.2 s of work.
- Known limitation: full `calc_hmc_all.element_solver`, `level_matrix_assembly_total`, and `dsec.calc_hmc_all` remained Python-orchestrated.

## v0.5.66

- Cleaned terminal and `xout_step.log` version/progress output.
- Changed startup/version string to use only the future package-facing form:
  - `xstar_tools version <version>`
- Terminal output now prints source-like radial progress table rows from the same stored `pprint(9)`/`pprint(17)` strings used in `xout_step.log` instead of recomputing approximate values.
- Added source-like terminal footer:
  - `final print:           1`
  - `xstar: Prepping to write spectral data`
  - `xstar: Done writing spectral data`
  - `total time ...`
- Kept raw progress/debug events behind `PROGRESS_DEBUG=1`.

## v0.5.65

- Implemented the missing C++ Voigt/natural-width `linopac` path in `libxstar_rates.so`.
- Translated the relevant `voigte.f90` behavior into `rate_kernels.cpp`.
- Updated `xstar_rates_apply_linopac_profile` to support both Gaussian and Voigt/natural-width line profiles.
- Backend identity became `xstar_rates_mg_type7_type4_linopac_type50_voigt_v1`.
- Fixed C++ counter aggregation so newly added numeric counters are not dropped from summary totals.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Runtime improved from about 21.5 min to about 15 min 53 s.
  - `type50_coarse_cpp_full_applied = 9885`.
  - `linopac_cpp_calls = 9885`.
  - `linopac_cpp_fallback_count = 0`.
  - `type50_reason_linopac_voigt_python_fallback = 0`.
- This was the first major successful speed improvement from the C++ path.

## v0.5.64

- Made raw `dsec_evaluation` progress rows debug-only.
- Added source-like compact radial progress table output in normal terminal mode.
- Introduced `PROGRESS_DEBUG=1` / `--progress-debug` to restore high-volume raw progress events.
- No intended physics or FITS product change.

## v0.5.63

- Added explicit fallback reason counters and rejection/hybrid samples for the Mg type-4 type-50 coarse backend.
- Split status into:
  - full C++ type-50 scalar + C++ linopac,
  - hybrid C++ scalar + Python linopac fallback,
  - full Python fallback.
- Added summary fields for type-50 coarse backend reasons, including `linopac_voigt_python_fallback`.
- Benchmark showed that hybrid rows existed but the Voigt/natural-width linopac path was still in Python, motivating v0.5.65.

## v0.5.62

- Added first selected Mg type-4/data-type-50 coarse backend attempt in `libxstar_rates.so`.
- Intended to combine selected type-50 `ucalc`, scalar line products, `oplin`, `fline`, `flinel`, and `linopac` updates in one C++ path.
- Backend identity became `xstar_rates_mg_type7_type4_linopac_type50_v1`.
- Benchmark outcome:
  - C++ library loaded.
  - The coarse type-50 path did not apply in the real benchmark (`type50_coarse_cpp_applied = 0`) because the linopac Voigt/natural-width branch fell back.

## v0.5.61

- Added C++ Gaussian full-profile `linopac` opacity side-effect support in `libxstar_rates.so`.
- Added Python-vs-C++ parity gate for Mg type-4 linopac profile updates.
- Added counters for linopac C++ calls, kernel time, updated bins, fallbacks, and parity checks.
- Preserved Python fallback for unsupported Voigt/natural-width branch.
- Enforced shared-library layout under `src/xstar_atomic/source_port/cpp/` with no root-level `.so` copies.

## v0.5.60

- Cleaned shared-library layout so C++ shared libraries live under `source_port/cpp/`.
- Updated build/load behavior to prefer the `cpp/` directory.
- Disabled high-volume terminal profile rows by default with `PROFILE_TERMINAL=0`.
- Kept profile details in JSON summaries instead of terminal logs.

## v0.5.59

- Batched Mg type-4 scalar C++ line-emissivity calls by contiguous line blocks.
- Reduced type-4 C++ calls from one per record to one per block.
- Benchmark outcome:
  - Calls dropped substantially, but runtime did not improve because the moved kernel was tiny relative to Python `ucalc`, `linopac`, and traversal work.

## v0.5.58

- Added conservative Mg record-type-4 scalar line-emissivity backend in `libxstar_rates.so`.
- C++ computed post-`ucalc` scalar products and line emissivity components while Python still owned source traversal, `ucalc`, `linopac`, and live array side effects.
- Added quiet backend-call counters and removed several noisy startup/log artifacts.
- Benchmark outcome:
  - C++ type-4 scalar kernel processed 9885 records with no fallback.
  - Runtime did not improve because the moved work was less than one second out of a ~21.5 minute run.

## v0.5.57

- Quieted backend-call profile logging and retained aggregate counters in summary JSON.
- Confirmed Mg type-7 C++ matrix-term construction worked but represented only about 0.1--0.15 s of runtime.
- The source package artifact for this version was not available in the later sandbox; subsequent work reimplemented relevant quiet behavior.

## v0.5.56

- Added detailed Mg record-type-7 C++ matrix-term counters.
- Added optional RSS sampling and quiet performance counter aggregation.
- Added wrapper defaults for no RSS profiling and no compact active-ATDB export.
- Fixed thermal line spacing in `pprint_legacy`.
- Benchmark outcome:
  - Mg type-7 C++ work was active but too small to affect total runtime.

## v0.5.55

- Served primarily as cleanup/measurement work rather than the originally planned full C++ Mg line-emissivity backend.
- Continued profiling and backend scaffolding toward later Mg C++ kernels.

## v0.5.54

- Added the first real Mg record-type-7 C++ rate-to-matrix construction/scatter path.
- Did not port source-faithful `ucalc` leaf formula evaluation.
- Established that post-`ucalc` matrix-term construction alone is too small for meaningful speedup.

## v0.5.53

- Introduced the backend architecture for optional C++ shared-library kernels.
- Added compact active-ATDB export support.
- Added `libxstar_rates.so` skeleton and backend selection plumbing.
- Established the long-term architecture of Python orchestration plus modular C++ shared libraries.

## v0.5.51

- Added an optional Mg compact matrix-fill C++ backend into `libxstar_solver.so`:
  - C ABI: `xstar_solver_fill_matrices(...)`.
  - Backend identity: `xstar_solver_so_leqt2f_mg_matrix_v2`.
- Added Python wrapper `call_cpp_fill_matrices(...)` and Mg-only matrix backend plumbing through `--mg-matrix-backend {python,cpp,auto}`.
- Added reusable Mg matrix buffers to avoid repeated dense matrix/rate allocations when the optional backend is used.
- Added `profile_rss` controls that are independent of live `--progress-memory` output, so stored profile rows can include RSS only when explicitly requested.
- Kept Python as the source-faithful reference path; C++ only filled compact Mg dense/rate matrices from already-built terms and did not port `ucalc` or full `calc_hmc_all` traversal.
- Known archive issue: `pyproject.toml` reports 0.5.51 but `src/xstar_atomic/__init__.py` still reports `__version__ = "0.5.48"` in the uploaded source archive.

## v0.5.50

- No v0.5.50 source archive was present in the reviewed upload. The reviewed sequence jumps from v0.5.49 to v0.5.51.

## v0.5.49

- Added production-oriented Mg benchmark wrapper `run_v0549_xstar_python.sh` with defaults for timing runs:
  - `PROFILE_COMPONENTS=summary`.
  - `PROGRESS_MEMORY=0`.
  - `MG_LINE_KERNEL=numpy`.
  - `SOLVER_BACKEND=auto`.
- Added `check_v0549_profile_and_mg_line_kernel.py` static checker.
- Reworked profiling control into levels: `none`, `summary`, `nested`, and `forensic`.
- Added `--mg-line-kernel` CLI plumbing and `mg_line_kernel` runner state.
- Added a conservative NumPy-oriented Mg line-emissivity lookup/table path for record types 4 and 9.
- Limited expensive Mg forensic per-rate/per-record profiling to explicit forensic mode rather than normal timing runs.
- Known archive issue: `pyproject.toml` reports 0.5.49 but `src/xstar_atomic/__init__.py` still reports `__version__ = "0.5.48"` in the uploaded source archive.

## v0.5.48

- Added more detailed Mg hot-path profiling around `calc_hmc_all` and `calc_emis_all`:
  - `calc_hmc_all.element_solver.level_matrix_assembly_total`.
  - `calc_hmc_all.element_solver.ion_loop`.
  - `calc_hmc_all.element_solver.rate_construction`.
  - `calc_hmc_all.element_solver.matrix_assembly`.
  - `calc_hmc_all.element_solver.dense_matrix_fill`.
  - `calc_hmc_all.element_solver.solver_call`.
  - Mg emissivity breakdown by ion and record kind.
- Added `source_routine` labels to profile events so later benchmark summaries could attribute time to `ucalc`, `calc_hmc_ion`, `assemble_element_matrix`, `msolvelucy/leqt2f`, and related source-equivalent blocks.
- Added population-state commit profiling for Mg writeback.
- Purpose: identify whether the next acceleration target should be solver, matrix fill, `ucalc`, emissivity, or output writing. Later benchmarks showed `ucalc`/rate construction and source-order matrix assembly dominate.

## v0.5.47

- Fixed the v0.5.46 `calc_emis_all` regression where `calc_emis_element(...)` referenced `epi` without receiving it from `calc_emis_all(...)`, causing:
  - `NameError: name 'epi' is not defined`.
- Passed the precomputed high-resolution radiation grid `epi` through the `calc_emis_all -> calc_emis_element -> calc_emis_ion` call chain.
- Avoided repeated high-resolution radiation-grid extraction inside the Mg/Ca emissivity ion loop by reusing the precomputed `epi` grid.
- This was a narrow correctness/performance cleanup; it did not change physics logic or introduce a new backend.
- Benchmark outcome on `helike_type69/mg11_ne1e8` with `DIAGNOSTICS=none`, `BLAS_THREADS=1`, `SOLVER_BACKEND=cpp`, `PROFILE_COMPONENTS=1`, and `ACTIVE_SUBSET=1`:
  - The run completed successfully after the v0.5.46 crash point.
  - All ten Python products were present.
  - `xout_step.log` timing footer was present.
  - Total wall time was `1246.33809` s, or `20 min 46.338 sec`.
  - Peak profiled RSS was about 3.96 GB, preserving the earlier memory reduction from the old ~6.3 GB peak.
  - Active subset was H, He, Mg: 3 active elements, 15 ions, about 700 active levels, 3213 active lines, and 1957 active continua.
  - Dominant profiled costs remained Mg thermal/emissivity work:
    - `calc_hmc_all.element_solver:Z12` about 518 s.
    - `calc_emis_all.element:Z12` about 352 s.
    - `calc_hmc_all.pre_matrix_solver:Z12` about 73 s.
    - `dsec.calc_hmc_all` about 683 s total.
- Conclusion: v0.5.47 was a correctness/stability release, not a speed release. It confirmed that the next acceleration target must be deeper Mg rate/matrix/emissivity kernels rather than the `leqt2f` solver wrapper alone.

## v0.5.46

- Targeted the Mg Z=12 hot paths identified in v0.5.44/v0.5.47-era profiling:
  - `calc_hmc_all.element_solver:Z12`.
  - `calc_emis_all.element:Z12`.
- Added process-local caching for immutable per-ion level tables used by hot Mg/Ca loops:
  - `_LEVEL_TABLE_CACHE`.
  - `clear_level_table_cache()`.
- Added cached source-ordered `calc_emis_all` record sequences per ion through `_calc_emis_record_sequence_for_ion(...)`.
- Avoided copying the full `leveltemp_workspace.levels` dictionary on every emissivity ion pass when the workspace is read-only for that ion.
- Added selected preliminary-rate record caching for the pre-matrix solver to reduce repeated rate-slot traversal in Mg/Ca high-density runs.
- Preserved source traversal order and kept downstream rate-type conditions authoritative.
- Known regression discovered by the `mg11_ne1e8` run: the new `epi` reuse path referenced `epi` inside `calc_emis_element(...)` without passing it through that function, causing `NameError: name 'epi' is not defined` during the first `calc_emis_all` call. This was fixed in v0.5.47.

## v0.5.45

- Simplified the C++ solver source layout by moving files directly under `src/xstar_atomic/source_port/cpp/` instead of `src/xstar_atomic/source_port/cpp/xstar_solver/`.
- Updated package data, build script, Makefile, and loader search paths for the flatter C++ layout.
- Kept backward-compatible loader support for the older `cpp/xstar_solver/` location during the transition.
- Continued using a plain shared library loaded by `ctypes`, not a Python extension module.

## v0.5.44

- Added aggregate timing summaries to the JSON summary:
  - `provenance.performance_profile_summary`.
  - `provenance.aggregate_timing_summary`.
- Added active feature lists for the active ATDB subset:
  - active line indices from `nplin` ownership.
  - active continuum indices from `npcon` ownership.
- Used the active feature lists in `calc_emis_all` ranking so production active-subset runs rank only H, He, and the active abundance element instead of scanning all ATDB line/RRC features every zone.
- Added cached line/continuum rank tables in reusable work arrays.
- Added active-feature summary metadata to the emissivity result/provenance.
- Added more profile timing around `calc_emis_all.rank_features` and per-element emissivity work, including `calc_emis_all.element element_z=<Z>`.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Run completed successfully with `ready=True`.
  - Memory stayed in the new ~4 GB regime; max profile RSS was about 4094 MB.
  - The timing summary showed `calc_emis_all` was still dominated by Mg:
    - `calc_emis_all total` about 405 s.
    - `calc_emis_all.element:Z12` about 346 s.
    - `calc_hmc_all.element_solver:Z12` about 504 s.
  - Conclusion: active feature filtering improved accounting and avoided full-feature ranking, but it did not materially reduce total runtime because the true Mg inner loops still dominated.

## v0.5.43

- Moved optional C++ solver source/build helpers into the package source tree under `src/xstar_atomic/source_port/cpp/xstar_solver/`.
- Updated `setup.py`, `MANIFEST.in`, package data, and `solver_backend.py` so source-tree and built-package runs can find `libxstar_solver.so` from the package C++ directory.
- Kept compatibility with the earlier repository-root `cpp/xstar_solver/` layout.
- This was a packaging/layout release; the actual solver ABI remained the `leqt2f` shared-library path.

## v0.5.42

- Added production memory controls for diagnostics-heavy physical runs.
- In `DIAGNOSTICS=none` production mode, stopped retaining full element assemblies and large diagnostic arrays from repeated `dsec`/`calc_hmc_all` calls.
- Added `retain_diagnostic_arrays` / trace-retention controls to keep full diagnostics in debug modes while reducing memory pressure in timing runs.
- Disabled retained per-level/per-ion diagnostic spectra and full `element_results` during repeated production DSEC evaluations.
- Added an `xout_step.log` timing footer for total time and writer elapsed time.
- Preserved final product generation while reducing retained intermediate state.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Memory dropped from the earlier ~6.0--6.3 GB peak to about 4.1--4.2 GB.
  - Runtime stayed around the same ~21 minute regime.
  - Conclusion: v0.5.42 was a successful memory-retention release, not a speed release.

## v0.5.41

- Added active ATDB subset support for production runs, allowing the runner to precompute active element/ion/level mappings instead of repeatedly using the full ATDB universe for active-subset cases.
- Added `active_subsets.py` and active-subset summaries.
- Added first generic `performance.py` profiling helpers with component timers, optional RSS sampling, and summary aggregation.
- Added broad profile instrumentation around `dsec`, `calc_hmc_all`, pre-matrix solver, element solver, continuum helper components, and related physical-run blocks.
- Added CLI/runner plumbing for profile controls and active-subset state.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Instrumentation identified the dominant hot paths as Mg `calc_hmc_all.element_solver` and `calc_emis_all`.
  - Memory did not materially improve yet because the active-subset work was still mostly summary/scaffolding rather than a full compact execution path.

## v0.5.40

- Added a Makefile and `build_lib.sh` for the optional `libxstar_solver.so` shared-library backend.
- Documented backend selection and build behavior in the C++ README.
- Packaged the root `cpp/xstar_solver` shared-library sources and build helpers.
- Continued the plain shared-object design introduced after the initial Python-extension experiment.
- Benchmark outcome on `helike_type69/mg11_ne1e8` with strict/active C++ solver loading:
  - The C++ `leqt2f` shared library loaded, but total runtime remained about the same as pure Python, around 22 minutes in that run.
  - Memory remained around the old ~6.3 GB peak.
  - Conclusion: the isolated dense `leqt2f` solver was not the dominant performance bottleneck.

## v0.5.39

- Replaced the initial Python C-extension solver experiment with a plain shared-library ABI loaded through `ctypes`.
- Added C ABI symbols:
  - `xstar_solver_abi_version()`.
  - `xstar_solver_backend_name()`.
  - `xstar_solver_leqt2f(...)`.
- Added optional `build_py` support to compile and package `libxstar_solver.so` without making installation fail when a compiler is unavailable.
- Added loader diagnostics for library path, backend name, and ABI version.
- Kept `python` as the source-faithful reference backend and `auto` as C++-when-available fallback mode.

## v0.5.38

- Added the first optional C++ solver backend experiment for the dense source-faithful `leqt2f` level-population solve.
- Implemented the C++ solve as a Python extension module `_xstar_solver_cpp` with a small `leqt2f` entry point.
- Added `solver_backend.py` with process-wide backend selection (`python`, `cpp`, `auto`) and CLI `--solver-backend` support.
- Added solver backend provenance into physical-run summaries.
- This version established Python as the reference implementation and C++ as an optional acceleration path; the packaging was later changed to a plain shared library.

## v0.5.37

- Targeted the `mg11_ne1e8` production-memory failure seen in v0.5.36, where the run was externally killed during the radial/DSEC inner solve despite `--diagnostics none`.
- Added production memory mode for DSEC/thermal iterations:
  - Added `retain_fixed_state_results` to `CalcHMCAllDsecEvaluator`.
  - In `diagnostics=none`, stopped retaining each full `FixedStateCalcHMCAllResult` inside `DsecEvaluation`.
  - Kept source-faithful state propagation while avoiding repeated retention of large intermediate result objects.
- Added runtime memory controls and visibility:
  - `--blas-threads`.
  - `--progress-memory`.
  - RSS sampling from `/proc/self/status`.
  - Early environment caps for `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, `BLIS_NUM_THREADS`, and `MALLOC_ARENA_MAX=2`.
- Moved NumPy-heavy imports behind the CLI environment setup so BLAS/thread caps take effect before NumPy loads.
- Added `run_v0537_xstar_python.sh` and `check_v0537_memory_mode.py`.
- Benchmark outcome on `helike_type69/mg11_ne1e8`:
  - Run completed successfully with `--diagnostics none --blas-threads 1 --progress-memory`.
  - Runtime was about 21.4 minutes.
  - Peak observed RSS was about 6.29 GB.
  - All ten ordinary XSTAR products were generated.
  - Main spectra/continuum/line products were close to original XSTAR; dominant Mg ion columns were within roughly the 1% regime.
  - RRC output was about 1.3% low and remained a watch-list item.
- Conclusion: v0.5.37 made the high-density Mg run complete reliably enough for benchmarking, but memory was still too high for Ca/full smoke runs.


## 0.5.36 - 2026-05-28

- Add `--diagnostics {full,summary,none}` to the physical runner CLI.
- Preserve v0.5.35 behavior by default (`full`).
- Allow smoke tests to suppress high-volume radial/continuum CSV/JSONL diagnostics with `--diagnostics none`.
- Remove stale optional diagnostic artifacts on overwrite reruns.

## v0.5.35 - 2026-05-28

- Fix v0.5.34 FITS write failure caused by mutating Astropy string table fields before serialization.
- Move XSTAR-style blank padding for binary-table A columns to a post-write byte-level pass that touches only character-column spans, leaving numeric binary data untouched.
- Preserve v0.5.33/v0.5.34 reporting cleanup behavior: atomic-number ion_index in xo01_detail, pprint(24) endpoint layout, and pprint(16:ignored).

## v0.5.34 - 2026-05-28

- Force FITS A-format binary-table fields to be space-padded at the byte level before checksum generation.
  This removes residual NUL padding from detail string columns such as `ion` and `ion_level`.
- Carries forward the v0.5.33 reporting cleanups for `xo01_detail.fits ion_index`, `pprint(24)`, and ignored `pprint(16)` timing/accounting output.

## 0.5.33 - Detail/reporting cleanup - 2026-05-28

- Make `xo01_detail.fits` `ion_index` source-like by writing the element/atomic-number value instead of the package-global ion ordinal.
- Centralize FITS A-column handling so string payloads are exact-width, space-padded ASCII bytes rather than NUL-padded buffers.
- Add the local endpoint/index column to the verbose `pprint(24)` absorption-edge text layout while preserving the existing edge-depth values.
- Explicitly ignore `pprint(16)` when no real timing/count instrumentation is available, avoiding misleading all-zero placeholder timing rows.
- Bump package metadata consistently to 0.5.33.

## 0.5.31 - Type-53 full-grid side-effect mapping - 2026-05-28

- Route type-53 `phint53` continuum side-effect arrays through the full high-resolution `epi` / `bremsa` grid instead of the reduced `epim` / `bremsam` grid.
- Keep reduced-grid radiation available for routines that require it; only the type-53 `opakc`, `opakcont`, and `rccemis(1:2)` side effects are changed.
- Add diagnostics that compare the mapped `nb1` with the expected full-grid threshold bin and flag `mapping_status=grid_mismatch` when they diverge by more than three bins.

## 0.5.30 - XSTAR source-port changes

- diagnostic/source-faithfulness release for the remaining continuum/detail mismatch in `xo01_detal4`, `xout_cont1`, and `xout_spect1`.
- `calc_emis_all` default rank depth is changed from 100 to 10, matching the XSTAR `PARAM` value `nrank=10` used by the Fortran rank arrays.
- Added `source_port/continuum_diagnostics.py`.
- `calc_emis_all` now records per-UCalc continuum side-effect summaries whenever a UCalc result includes `opakc`, `opakcont`, or `rccemis` increments.
- The radial/final writer path now records compact phase snapshots around the continuum-array lifetime boundaries needed to diagnose `fstepr4` and final spectrum state.

## 0.5.29

- Python source-port metadata/reporting correction.
- The translated `pprint(19)` RRC endpoint metadata now treats Python `nlevs[ion]` as the source `nlevp` directly, instead of adding one before applying the Fortran endpoint expression.

## 0.5.28

- `src/xstar_atomic/source_port/physical_runner.py`
  - Bumped `OUTPUT_METADATA_CACHE_FORMAT_VERSION` from 5 to 6.
  - Changed `pprint(19)` RRC destination local-level metadata from active-RRC max-local estimation to source `nlev` semantics:
    - previous: `source_nlevp = max(active_rrc_local_index_by_ion) + 1`
    - new: `source_nlevp = derived.nlevs[ion] + 1`
  - Updated metadata-builder provenance string.
  
## 0.5.27

- `xstar.f90` sets `numrec=jkp+1`, then calls `pprint(12,jkp,...)`; the terminal row overwrites the last in-loop physical row and leaves the already-included `numrec` row as the single trailing zero row.
- `pprint.f90` option 19 prints local RRC endpoint indices `idest1,idest2`, where `idest2=nlevp+idat(...)-1` and `nlevp` is the local LTE level count used in that ion context.

## 0.5.26

- the final abundance row is written to `jkp`, while `numrec` remains available as the zero padding row.
- Python now follows the RRC endpoint display logic of `pprint(19)` in `pprint.f90`.

## 0.5.25

This release corrects Python's verbose log representation of `pprint(19)` to match XSTAR's source-facing convention:

- Original XSTAR prints local ion-level ids for recombination-continuum source/destination endpoints.
- Python previously printed the packed/global level id in the displayed level column.
- Python now stores and displays the source local endpoint ids while retaining the packed id for FITS metadata linkage.

## 0.5.24

- Python source-port changes implement the endpoint-order behavior already present in XSTAR `ucalc.f90` label 50.
- Python now follows this ordering for type-50 oscillator-strength reconstruction.

## 0.5.23

adds reporting/source-diagnostic fidelity:

- `pprint(24)`: bounded to the observed original H/He absorption-edge block for the canonical C benchmark until the full type-7 Fortran traversal is translated.
- `pprint(5)`: uses the source-style absorbed/continuum/line/error energy-balance formula from final arrays.
- `pprint(27)`: per-shell contribution diagnostics added to explain integrated ion-column differences.
- `pprint(16)`: remains source-table-shaped; timing values are placeholders unless true counters are provided.

No physical kernel behavior is changed.

## 0.5.22

- improve Python verbose `pprint` diagnostic log coverage and ordering.

## 0.5.20

- `pprint.f90` option 1: emission line luminosities.
- `pprint.f90` option 23: line depths.
- `ucalc` type-50 line opacity.
- `linopac.f90` full-profile averaging.
- Selected continuum bins 3875--3879, especially opakc(3877).
- `calc_emis_all.f90`
- `calc_emis_ion.f90`
- `ucalc`
- `fstepr4.f90` `emis in = rccemis(2,mm)` payload.

## v0.5.18

Python-only diagnostic instrumentation was added to compare the translated `linopac.f90` binning path against the source routine for bins 3876-3878 around the selected first-step limiter.

## v0.5.06

Python source-port correction:

- `ucalc.f90` label 50 source behavior restored: the bound-bound radiative branch returns the line-center opacity (`opakab=sigvtherm`) in addition to the rate and energy channels.
- This feeds the existing source-ordered `calc_emis_ion` line branch and `linopac`-style binned opacity handoff.

## v0.4.96 - 2026-05-25

- Source-code correction for Python `leqt2f` solver parity.
- Replaced NumPy dot/matrix-vector accumulation in `ludcmp`, `lubksb`, `mprove`, and `leqt2f` residual checks with explicit source-order loops matching the original Fortran routines.
- Retained v0.4.95 NumPy/Astropy output-writer compatibility fix.
- No original-XSTAR source changes.

## 0.4.87 - 2026-05-24

- Fix the diagnostic-only v0.4.86 original-XSTAR state-path helper link failure.
- Export `xap_zone1_alias_reset` as an external subroutine that uses the private alias-state module internally, matching the existing external call in `calc_hmc_all.f90`.
- Add a real `gfortran` compile/link regression for the generated helper symbol.
- No production rates, matrices, populations, solver behavior, DSEC control, radial physics, writers, tolerances, or cache schemas changed.

## v0.4.86 — diagnostic-only exact source-order carbon state path - 2026-05-24

- Adds matching Python and original-XSTAR observations for live hydrogen entry state, incoming carbon global mapping, compact pre-solve state, every Lucy outer/fixed iteration, final vector and stage totals, element/global writeback, and continuum/ground aliases.
- Emits four new Python products, four original probe products, and four comparison CSVs.
- Reports a structured `source_order_first_divergence` with phase, source locus, row identity, and numerical difference.
- Keeps new state-path comparisons diagnostic-only and outside the existing thermal acceptance gate.
- Preserves compatibility with older v0.4.79 probe directories where the new files are absent.
- Reconciles the v0.4.78 audit: all six old production/solver “Still open” items were fixed in v0.4.85; input-fingerprint canonicalization remains open diagnostic work.
- Makes no production rate, matrix, solver, DSEC, radial, FITS, tolerance, cache-schema, or empirical-correction change.

## v0.4.85 — live hydrogen charge-exchange state and strict production `msolvelucy` - 2026-05-23

- Reconstructs `xh0=xpx*xilevg(1)*abel(1)` and `xh1=xpx*(1-xilevg(1))*abel(1)` from the incoming dense global H I population at every `calc_hmc_all` call.
- Passes the same live hydrogen densities to preliminary ion balance and detailed element equilibrium.
- Makes production `msolvelucy` source-strict: no NumPy least-squares fallback and no dense full-matrix rescue.
- Uses literal ordered `xm` accumulation, `1.d-24+xm` normalization, and capped one-based `diff2`/`diff` loops.
- Reproduces the literal rate-type-5 `falpha(3,mm)=falpha(3,nn)+...` assignment.
- Keeps recovery behavior only in explicitly diagnostic standalone contexts.
- Adds live-H, strict-solver, no-rescue, no-lstsq, and ordered-sum regression tests.
- No original-XSTAR, atomic-data, DSEC, radial, FITS, tolerance, or empirical-correction change.

## v0.4.84 — preliminary lfpi, literal type-59 grid, and cache recovery - 2026-05-23

- Uses the successful v0.4.83 production run as the acceptance baseline: Python now follows the original 24-evaluation DSEC path and converges to 73206.20 K versus 73198.41 K.
- Restores the literal `calc_ion_rates.f90` caller-owned `lfpi=1`; the preliminary pass no longer inherits the detailed second-pass `lfast=2` setting. This removes non-source Milne/inverse fields from preliminary type-53 records.
- Replaces conventional lower-bracket continuum indexing in `phintfo` and type 59 with the original one-based logarithmic-nearest `huntf -> nbinc -> enxt` traversal, including the threshold-nearest bin even when it lies below the nominal threshold.
- Uses the resolved excited-parent statistical weight for type-59 `swrat` while retaining the current-record threshold passed to `phintfo`, matching source label 59.
- Canonicalizes fixed-state logical carbon-cooling keys by record, data/rate type, role, and physical endpoints; raw `idest1/idest2` orientation remains diagnostic metadata rather than a false gate key.
- Treats CRC, ZIP, EOF, and NumPy member-read failures in both derived-pointer and output-metadata NPZ caches as cache misses, rebuilds from `atdb.fits`, and atomically replaces the damaged sidecar.
- Adds regression tests that corrupt `npfi.npy` and `line_upper_level.npy` inside otherwise valid NPZ archives and require a successful rebuild followed by a cache hit.
- No original-XSTAR, matrix, solver, DSEC, radial-transfer, FITS-writer, tolerance, or empirical-correction change.
- Validation: 400 source-port tests passed before packaging.

## v0.4.83 — type-59 source-guard normal zero return - 2026-05-23

- Fixes the status semantics of `if (idest4.gt.idest3+1) go to 9000` at
  original `ucalc.f90` label 59.
- Preserves the guard but returns a ready zero-rate result instead of
  `SOURCE_REJECTED`, preventing strict `calc_ion_rates` from aborting on
  legitimate ATDB record 5386.
- Keeps `ans1..ans6` and `idest1/idest2` zero while retaining decoded
  `idest3/idest4`, matching source initialization and branch order.
- Applies the same pre-`indonly` guard ordering to index-only evaluation.
- Leaves the v0.4.82 type-59 coefficient, continuum-offset, and ans-order
  corrections unchanged.
- No original-XSTAR, other rate-family, matrix, solver, DSEC, radial, FITS,
  tolerance, cache, or empirical-correction change.
- Validation: 396 source-port tests passed.

## v0.4.82 — C IV data-type-59 compact-layout and ans-order correction - 2026-05-23

- Uses the completed original/Python C IV record comparison to identify data
  type 59 record 6077 as the `4.037108e10 s^-1` Python outlier; original XSTAR
  returns `1.190480e-10 s^-1`.
- Corrects compact six-real decoding from `reals[:5]` to `reals[1:6]`.
- Corrects the type-59 continuum offset from the third to the fourth packed
  integer from the end; `idest4` remains the distinct third-from-end field.
- Preserves the literal `idest4 <= idest3 + 1` source gate and returns both
  endpoint fields in the Python contract.
- Corrects reverse-rate zeroing order: XSTAR zeroes pre-swap
  `ans2/ans4/ans6`, which correspond to post-swap `ans2/ans3/ans5`; forward
  photo-heating remains in `ans4/ans6`.
- Applies the endpoint correction to index-only decoding, public type-59
  photoionization summaries, and legacy audit helpers.
- Adds a dedicated type-59 record proof to the zone-1 comparator.
- Adds focused tests for compact coefficient mapping, endpoint mapping,
  pre-swap zero semantics, and the source endpoint guard.
- No original-XSTAR, other rate-family, matrix, solver, DSEC, radial, FITS,
  tolerance, cache, or empirical-correction change.

## v0.4.81 — optional lazy data-type-15 probe handling - 2026-05-23

- Fixes an analyzer error that unconditionally required the lazily-created
  type-15 shell and call-site CSV files.
- Distinguishes XSTAR data type from rate type: data type 95 / rate type 15 does
  not require data-type-15 shell products.
- Requires the shell/effective files only when a selected C IV record actually
  has `data_type == 15`.
- Adds explicit `type15_record_level_proof_applicable` and
  `type15_record_gate_passed` summary fields.
- Does not falsely claim a type-15 proof when it is not exercised, and does not
  block the independent C IV record/topology/population/cooling gates.
- No production-physics or original-XSTAR source changes.
- Validation: 391 source-port tests passed.

## v0.4.80 — constant-memory zone-1 analyzer hotfix - 2026-05-23

- Replaces full-file materialization of original-XSTAR probe CSVs with
  incremental constant-memory fingerprints that preserve the same SHA-256 and
  numerical summary contract.
- Streams and target-filters the remaining raw probe products.
- Adds `--skip-input-fingerprints` because the full-capacity fingerprints are
  observational and are not part of the ten physical acceptance gates.
- Adds `--progress` reporting for large analyzer stages and files.
- Reports the dominant Python C IV preliminary record in the parity summary.
- Establishes from the uploaded Python v0.4.79 products that data type 59
  record 6077, not type 15, produces the `4.037108e10 s^-1` outlier.
- Makes no production-physics, Fortran-probe, tolerance, cache, radial, or FITS
  change relative to v0.4.79.

## v0.4.79 — C IV preliminary type-15 record proof and literal shell-threshold correction - 2026-05-23

- Corrects the sole production-physics discrepancy in this release: data type
  15 now passes the final shell-loop `ett` and `ddd` to `bkhsgo`, and the same
  final `ett` to `phintfo`, exactly as `ucalc.f90` does.
- Retains parent threshold, all shell thresholds/`d` values, final effective
  threshold/`d`, and the explicit `bkhsgo`/`phintfo` threshold provenance.
- Adds preliminary C IV `calc_ion_rates` record instrumentation with `ans1..6`,
  endpoints, parent record, and before/contribution/after `pirti` and `rrrti`.
- Correlates type-15 shell rows only with the active preliminary C IV record,
  preventing duplicate rows from later detailed matrix evaluations.
- Adds carbon topology, complete compact initial-vector, condensed
  normalization-row, selected C V population, and logical carbon-cooling
  products on both original-XSTAR and Python sides.
- Replaces the conflated v0.4.78 matrix/cooling gate with ten coverage-strict
  gates, including exactly 932 logical C V rows and zero compact row/column
  offset.
- Enables Lucy trace capture only for the fixed target-state carbon replay used
  by the diagnostic; ordinary production execution is unchanged.
- Adds focused v0.4.79 unit and synthetic ten-gate tests.
- Validation: all 388 source-port tests, Python byte compilation, and compilation of the four helper modules plus the four newly instrumented original-XSTAR routines.
- Does not modify any other rate family, matrix formula, solver branch, DSEC
  condition, radial/output code, tolerance, empirical factor, or cache schema.

## v0.4.78 — bounded zone-1 DSEC source-state and carbon-cooling parity gate - 2026-05-23

- Adds an observation-only original-XSTAR probe for the complete first-zone DSEC evaluation sequence.
- Fingerprints every represented mutable `calc_hmc_all` input before every trial.
- Adds exact same-entry deterministic replay for every captured Python state.
- Compares C IV/C V/C VI rates at the original state nearest `73198.4 K`.
- Audits every C V matrix record and scaling factor touching local levels `4-6`, `10-12`, and `20`.
- Adds term-by-term carbon cooling comparison before DSEC may commit a mismatching trial.
- Preserves all production rates, source branches, tolerances, NPZ caches, and physical-output comparators; no empirical correction is introduced.
- Validation: 43 focused tests, all 385 source-port tests, byte-compilation, Fortran helper compilation, and extracted-sdist tests.

## v0.4.77 full source global-level capacity at radial/output boundaries - 2026-05-23

v0.4.77 is a bounded source-state/output hotfix driven by the first user-side
v0.4.76 run.  That run completed 39 DSEC evaluations for zone 1 and then
failed while saving the detail record because the translated solver retained
only the active H/He/C prefix of the global level arrays (493 entries), whereas
`fstepr` metadata spans the full 39,221-row source `nnml` space.

The original executable always owns full `xilevg`, `bilevg`, and `rnisg`
arrays; levels belonging to zero-abundance elements remain initialized to zero.
The physical runner now restores that full source capacity when committing a
`calc_hmc_all` result to shared radial/emissivity/output state.  Active entries
are copied unchanged and the inactive tail is zero-filled.  Repeated DSEC
trials continue to use the compact active prefix, so this release changes no
rate, matrix, population, thermal iteration, or cache data.

Existing source-port pointer and output-metadata NPZ caches remain valid.

Validation: 33 focused tests, all 375 source-port tests, byte-compilation, and
all 375 source-port tests from the extracted source distribution pass.

## v0.4.76 first completed all-ATDB run diagnostics and source radial/output fidelity - 2026-05-23

v0.4.76 is driven by the first completed real all-ATDB `c5_ne1` Python run.
The v0.4.75 runner loaded both NPZ caches in about six seconds, completed all
translated local/radial routines, wrote all ten products in about four minutes,
and reached the independent comparator. Physical parity did not yet pass.

The release restores the literal XSTAR first-pass stop predicate rather than
using `nsteps` as an exact shell count; makes the kelvin/source-`10^4 K`
boundary explicit; retains `trad`; removes the detail-array one-based guard;
and reconstructs source-local level ownership before assigning global output
rows. It also corrects excited-state RRC thresholds to source
`ionization_limit - excitation_energy` semantics. The output-metadata cache
format is v3, so old metadata sidecars rebuild automatically while the pointer
cache remains valid.

Current one-integer step rows are emitted and normalized against optional
legacy two-integer rows. FITS `TBCOL*` layout cards are excluded from physical
header comparison.

The standalone/CLI mismatch diagnostics now include native per-DSEC-evaluation
progress and compact internal reports for thermal residuals, carbon ion
fractions/cooling, and the dominant carbon diagonal rate terms with ATDB
provenance. The v0.4.75 products localize the remaining leading mismatch to C V
population balance: first-zone carbon cooling is about `6.039e3` too large and
the Python thermal solution reaches `1.93676e4 K` instead of `7.31984e4 K`.
No rate is fitted, suppressed, or rescaled in v0.4.76.

Validation: 30 focused tests, all 372 source-port tests, byte-compilation, and
all 372 tests from the extracted source distribution pass.

## v0.4.75 source-ordered continuum workspace chaining - 2026-05-23

v0.4.75 fixes the first all-ATDB radial-shell failure that remained after the
v0.4.74 continuum-capacity correction. The production physical runner had
constructed the immutable `comp2`, `freef`, `bremem`, and `heatf` contexts from
the same pre-continuum `opakc`/`brcems` snapshots. Original
`calc_hmc_all.f90` instead calls them in literal mutable order:

`comp2 -> freef(opakc in/out) -> bremem(opakc after freef, brcems in/out) -> heatf(fresh outputs)`.

The physical `calc_kwargs_factory` now replays that exact ownership chain for
every DSEC trial: `bremem` receives the opacity returned by the immediately
preceding `freef`, and `heatf` receives the freshly generated bremsstrahlung
emissivity, free-free heating, and Compton coefficients. This removes
`CalcHMCAllError: bremem incoming opakc does not match preceding freef output`
without weakening the source-state consistency checks.

Two new regressions cover both a zero-initialized first call and a carried
continuum workspace from a prior DSEC evaluation. Existing v0.4.73 NPZ caches
remain valid. No atomic-rate, matrix, thermal, transfer, or output formula was
changed; the real C V physical parity run remains the external acceptance gate.

## v0.4.74 full-capacity continuum arrays and extracted-sdist test fix - 2026-05-23

v0.4.74 preserves the v0.4.73 vectorized ATDB/metadata NPZ caches and corrects
two issues exposed by the first user-side rerun. The physical runner now
allocates `bremsam` and `bremsint` with the original high-resolution `ncn2`
capacity, matching `xstar.f90`. `trnfrc` therefore owns the full
`bremsint(1:ncn2)` range, while `bremsmap`, `dsec`, and `ucalc` continue to use
only the reduced `1:ncn2m` prefix and the caller-owned `ncn2m+1` boundary row.
This removes `RadialTransferPortError: bremsint is shorter than the active
range` at the start of radial zone 1 without restoring the earlier strict
equal-length live-radiation check.

The v0.4.73 cache-performance test now loads its sibling mini-ATDB helper by
explicit file path, so focused tests collect correctly from an extracted source
distribution where `tests/` is not a Python package. New regressions cover the
full-capacity continuum arrays and full-range `trnfrc` use. No physical
equations or persistence rules changed.

## v0.4.73 vectorized ATDB caches, sparse-slice speedup, progress, and live-radiation tail fix - 2026-05-22

v0.4.73 corrects the production physical-runner startup behavior exposed by
the user's first all-ATDB c5_ne1 execution. `FortranPackedVector.slice()` now
uses a lazily cached sorted NumPy override index plus `searchsorted` and vector
assignment instead of scanning every line-wavelength override for every packed
record. The metadata builder uses vectorized packed gathers and one-time
ion/level maps.

The physical runner now automatically reads and writes validated, uncompressed
NumPy NPZ sidecars for the exact source-port `setptrs` arrays and the complete
writer metadata. `prepare_xstar_python_cache()` and example 143 prepare these
caches explicitly; alternate cache directories support read-only ATDB installs.
The separate high-level `atdb.fits.xstar_atomic_index.npz` cache remains
unchanged because it does not contain the literal source-port pointer arrays.

Native progress callbacks and CLI `--progress` report ATDB/cache, metadata,
pass, zone, writer, and parity boundaries.

The real v0.4.72 run also exposed the literal `bremsint(ncn2m+1)` caller tail.
v0.4.73 allocates the reduced arrays at their source extents and lets `ucalc`
consume only active rows `1:ncn2m`, eliminating the false
`invalid live radiation arrays` failure at the first H I ion-balance record.
No physical equations, rate formulae, matrix topology, transfer equations, or
writer persistence rules changed. Physical c5_ne1 product parity remains to be
rerun against the independently generated original-XSTAR directory.

## v0.4.72 public physical Python runner API and c5_ne1 acceptance gate - 2026-05-22

v0.4.72 adds the first public end-to-end execution API for the translated
Python XSTAR call graph:

- `run_xstar_python(**parameters)` accepts ordinary XSTAR keyword arguments;
- `run_xstar_python_command(command)` parses a literal `xstar key=value ...`
  command and runs Python only;
- `run_xstar_python_script(run_xstar.sh)` reads the script as data without
  sourcing or executing it;
- `run_xstar_from_parameters(parameters)` is the common typed execution path.

The runner resolves `atdb.fits` through the package data-path policy, applies
the source `rread1` pressure/density/radius setup, builds the literal `ener`
grid and built-in power-law spectrum, initializes caller-owned local/radial
state, executes the translated radial/pass calculation, and writes the strict
ten-product set. Original XSTAR products are never calculation inputs.

The direct Python convenience API supports sparse abundance shorthand. A call
that supplies only `habund`, `heabund`, and `cabund` sets all unspecified
elements to zero. Literal command and script APIs retain XSTAR parameter-file
defaults unless every abundance is supplied explicitly.

The FITS `PARAMETERS` extension now uses the literal 56-row
`xstar.f90 -> pprint(3) -> fparmlist` name/type/comment order, including string
values in the source comment column and REAL(4) persistence. The input
`lprint=1` value is retained in that table. The untranslated verbose terminal
`pprint` reports are not emitted; all structured FITS products and the
comparator-visible zone/final rows of `xout_step.log` remain enabled.

`run_c5_ne1_acceptance()` provides the strict gate requested for
`helike_type69/c5_ne1`: it first generates all ten Python products independently,
then compares them directly against the original-XSTAR directory using the
existing schema/value comparator. The gate cannot pass when an original product
is missing, and never uses original outputs to seed Python state.

The uploaded `original_xstar.tar.gz` intentionally omits the generated products,
and the release environment does not contain the production `atdb.fits` or an
installed XSTAR executable. Consequently, package-level API/gate tests pass, but
physical all-ATDB c5_ne1 output parity is not claimed in this release. The next
acceptance action is to run the new API on the user's production ATDB after
regenerating the ten original products.

Run the Python case and strict comparison with:

```bash
PYTHONPATH=src python examples/142_run_xstar_python.py \
  --run-script original_xstar/helike_type69/c5_ne1/run_xstar.sh \
  --atdb /home/adanehka/mhd/xstar/xstar/data/atdb.fits \
  --output-dir python_xstar/helike_type69/c5_ne1 \
  --original-run-dir original_xstar/helike_type69/c5_ne1 \
  --summary-json c5_ne1_physical_parity_v0472.json \
  --print-summary
```

## v0.4.71 original-XSTAR physical benchmark suite - 2026-05-22

v0.4.71 turns the supplied `original_xstar` run-script tree into a strict,
reproducible physical-output benchmark. The new harness parses the literal
`xstar key=value ...` commands without sourcing shell scripts, inventories all
62 cases, identifies the canonical C V / O VII / Mg XI / Ca XIX four-case
acceptance subset, and records duplicate physical parameter groups.

The harness can optionally regenerate original XSTAR products by invoking the
parsed argv directly, and it compares mirrored original/Python case directories
using an explicit ten-product contract:

```text
xo01_detail.fits  xo01_detal2.fits  xo01_detal3.fits  xo01_detal4.fits
xout_abund1.fits xout_spect1.fits xout_lines1.fits xout_cont1.fits
xout_rrc1.fits   xout_step.log
```

Case, file, HDU, and column diagnostics are written to JSON, Markdown, and CSV.
A case passes only when every required file is present and every schema/value
comparison passes. Original XSTAR outputs remain diagnostic oracles and are
never used to seed Python state.

The uploaded archive intentionally omits the ten physical products, and the
general input-parameter-to-live-state Python runner is not yet implemented.
Therefore v0.4.71 validates the benchmark definition and strict gate but does
not claim physical all-ATDB parity. The next target is the independent Python
physical runner for the canonical four cases.

The package dependency markers also prevent the Astropy/NumPy combination that
failed when older Astropy called the removed `numpy.in1d`: Python 3.11+ now
requires Astropy 7.2 or newer, while older Python retains NumPy below 2.4.

Run the attached suite inventory with:

```bash
PYTHONPATH=src python examples/141_benchmark_original_xstar_outputs.py \
  --suite-archive original_xstar.tar.gz \
  --out-dir xstar_physical_benchmark_v0471 \
  --selection canonical-four \
  --print-summary
```

## v0.4.70 legacy `pprint` products and physical output-parity harness - 2026-05-22

v0.4.70 replaces the final non-writing `pprint` handler for the source-default
`lpri=0` path. The bounded radial caller now preserves the default legacy
sequence:

```text
pprint(3) -> pprint(2)
per pass: pprint(17)
per shell: pprint(9) -> [final pass: pprint(12)]
terminal shell state: pprint(9) -> [final pass: pprint(12)]
final local recompute: pprint(22) -> pprint(11)
```

The translated path writes `xout_step.log` and `xout_abund1.fits` with the
source `ABUNDANCES`, `COLUMNS`, `HEATING`, and `COOLING` extensions. It
preserves final-pass-only accumulation, the terminal `numrec` row, source
REAL(4) persistence through `E13.5` ASCII columns, the ion-column trapezoid,
and the option-11 `n_p` unit-field typo. Verbose `lpri>0` diagnostic report
branches fail explicitly rather than being approximated.

A new independent output comparator checks HDU names, table schemas, row
counts, strings, every numeric column, pass-specific detail files, and the
structured zone/final rows of `xout_step.log`. XSTAR products remain diagnostic
oracles only and never become production inputs. The comparator self-test
passes on the bounded product set.

Physical all-ATDB standard-benchmark parity is **not claimed in this release**:
the release environment did not contain a paired original-XSTAR and Python
physical benchmark run. Supply both directories to execute the open gate:

```bash
PYTHONPATH=src python examples/140_validate_xstar_pprint_physical_output.py \
  --out-dir xstar_output_writer_source_validation_v0470 \
  --xstar-run-dir /path/to/original_xstar_run \
  --python-run-dir /path/to/python_run \
  --print-summary
```

Without the two physical directories, the command validates the bounded source
translation and records that physical parity was not run.

## v0.4.69 detail and final FITS output writers - 2026-05-22

v0.4.69 translates the bounded output sequence after the accepted radial
control path. Per-shell saving now composes
`savd -> fstepr -> fstepr2 -> fstepr3 -> fstepr4` into caller-owned per-pass
detail stores and writes the source pass-specific FITS names. The final caller
executes `xstarcalc(nlimd=0) -> heatt -> stpcut`, records the literal `pprint`
boundary, and then runs `writespectra -> writespectra2 -> writespectra3 ->
writespectra4` under the source `lwri` gates.

The port preserves REAL(4) persistence, one-based HDU insertion and shifting,
level/line/RRC activity gates, the 600-line limit, transmitted continuum, the
five-field `writespectra` scattered-column omission, caller-owned state
identity, and FITS checksums. Direct references cover original `voigte`, the
strong-line `binemis` chain, and detail/final row construction.

Legacy `pprint` ASCII reports remain an explicit source-state handler and are
not fabricated. Physical all-ATDB standard-benchmark output parity remains the
next acceptance stage.

Run:

```bash
PYTHONPATH=src python examples/139_validate_xstar_output_writers.py \
  --out-dir xstar_output_writer_source_validation_v0469 \
  --print-summary
```

## v0.4.68 tabulated radial density and fixed pass-control contract - 2026-05-22

v0.4.68 closes the remaining bounded radial-control path before output writers.
It translates the inline `radexp < -99` branch in `xstar.f90` and makes the
source pass-convergence contract explicit.

The caller-owned `TabulatedRadialDensityState` reproduces the sequential
`density.dat` unit. The first radius/density pair is consumed before the pass
loop. One further pair is read after every shell, after the saved-state boundary
and before `stpcut`. The source assignment order is preserved:

```text
read rnew, dennew
-> delr = rnew - r
-> reject delr < 0 as "radius error"
-> r = rnew
-> xpx = dennew
-> rdel = rdel + delr
-> xcol = xcol + xpx*delr
```

At end of file, the sequential read returns nonzero `iostat` while retaining the
previous `rnew` and `dennew`. This gives a final zero-width update and terminates
the next literal shell-loop test. The Python path does not rewind the density
stream or invent additional rows.

The pass contract now records that XSTAR uses a fixed requested number of
passes, directions `ldir=(-1)**kk`, and no adaptive comparison between
successive passes. `numrec <= 0` forces `npass=1`. The exact first-pass and
repeated-pass predicates are exposed in provenance. Output writers remain
excluded.

Run:

```bash
PYTHONPATH=src python examples/138_validate_xstar_radial_density_pass_control.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0468 \
  --print-summary
```

## v0.4.67 translated `unsavd` and bounded repeated radial passes - 2026-05-22

v0.4.67 translates `unsavd.f90`, validates its caller-visible restoration
against the unmodified original Fortran, and adds the caller-owned saved
shell/pass state required by the radial driver. The bounded model now executes
three alternating passes without entering any output writer:

```text
pass 1, ldir=-1: initialize -> shells -> saved REAL(4) records
pass 2, ldir=+1: unsavd -> shell calculation, with nlimdt=0
pass 3, ldir=-1: unsavd -> shell calculation, with nlimdt=nlimd
```

The in-memory persistence contract reproduces the source `savd`/`unsavd`
interface rather than the FITS output mechanism: values are rounded through
REAL(4), HDUs 1--2 are reserved, each record is inserted after the requested
one-based HDU, and later records shift exactly as CFITSIO `ftcrhd` would shift
them. For the two-shell fixture, pass 1 stores shell 1 at HDU 3, inserts the
terminal record at HDU 4, and shifts shell 2 to HDU 5. Passes 2 and 3 therefore
restore HDUs `5, 4, 3` in source order.

`unsavd` restores the saved scalars, populations, line/RRC/continuum arrays,
and only the optical-depth row owned by the current direction. The saved
`zrems` table is read into a local temporary and intentionally does not replace
the caller array, matching the original source. Tabulated radial density,
explicit pass-convergence control, and output writers remain unported.

Run:

```bash
PYTHONPATH=src python examples/137_validate_xstar_unsavd_multipass.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0467 \
  --print-summary
```

## v0.4.66 translated `gsmooth` and nonzero-turbulence radial branch - 2026-05-22

v0.4.66 translates `gsmooth.f90` and `gsmooth2.f90`, validates the combined
thermal/turbulent velocity and all four smoothed arrays against the unmodified
original Fortran, and closes the optional source branch before `heatt`:

```text
[first-pass zones > 1: step]
-> trnfrc
-> xstarcalc
-> [gsmooth when vturbi > 1.e-34]
-> heatt
-> inline radius/density/radial-depth/column update
-> stpcut
-> trnfrn
```

The translation preserves the wrapper order
`brcems -> rccemis(1) -> rccemis(2) -> opakc`, bins 1--2, the 20-keV
pass-through, plus/minus trapezoid walks, literal stopping tests, binary32
source constants, and caller-owned tails. The same caller arrays are smoothed
before translated `heatt` consumes them.

Reverse passes still fail at missing `unsavd`; multipass restoration, tabulated
radial density, and output writers remain explicitly unported.

Run:

```bash
PYTHONPATH=src python examples/136_validate_xstar_gsmooth_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0466 \
  --print-summary
```

## v0.4.65 translated `heatt` and bounded radial composition - 2026-05-22

v0.4.65 translates `heatt.f90`, validates its caller-visible continuum, line,
RRC, and mutable-level-workspace outputs against the unmodified original
Fortran, and replaces the v0.4.64 handler at the same radial source slot:

```text
[first-pass zones > 1: step]
-> trnfrc
-> xstarcalc
-> [gsmooth when vturbi > 1.e-34]
-> heatt
-> inline radius/density/column update
-> stpcut
-> trnfrn
```

The translation preserves active-range mutation and caller-owned tails, old
versus current luminosity-array ownership, the source's retained final
continuum-only `optp2` value in the first inward line term, packed
source-order RRC traversal, and partial `leveltemp` overwrite. The original
routine's local `cmp1` and `cmp2` are uninitialized and affect only local
Compton diagnostic totals; the Python result marks that diagnostic as
source-uninitialized instead of inventing values.

`gsmooth`, `unsavd`, reverse/multipass restoration, and output writers remain
explicitly unported. Nonzero turbulent velocity and reverse passes continue to
fail at their exact source boundaries.

Run:

```bash
PYTHONPATH=src python examples/135_validate_xstar_heatt_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0465 \
  --print-summary
```

## v0.4.64 bounded radial-shell caller and transfer kernels - 2026-05-22

v0.4.64 begins Milestone 5 without opening output writers. It translates the
four radial kernels with no unresolved atomic-data dependency:

```text
step
trnfrc
stpcut
trnfrn
```

and composes them around the accepted local caller in the exact first-pass
sequence:

```text
[step for zones > 1] -> trnfrc -> xstarcalc -> [gsmooth if vturbi > 0]
-> heatt -> inline radius/column update -> stpcut -> trnfrn
```

`heatt` remains an explicit source-state handler. Reverse/multipass shells fail
at missing `unsavd`, and nonzero turbulent velocity fails at missing `gsmooth`;
neither path is approximated. The direct kernel fixture uses outputs generated
by compiling the unmodified XSTAR routines with only dimension/module stubs.
The expanded caller fixture confirms zone-1 `step` skipping, later-zone `step`,
shared caller-owned arrays, the exact failure boundaries, and exclusion of all
output writers.

Run:

```bash
PYTHONPATH=src python examples/134_validate_xstar_bounded_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0464 \
  --print-summary
```

## v0.4.63 complete local `xstarcalc` assembly - 2026-05-22

The user-side v0.4.62 validation confirms the complete `calc_emis_all` source
chain. v0.4.63 assembles the accepted local-zone routines in literal
`xstarcalc.f90` order:

```text
bremsmap -> [dsec] -> calc_hmc_all -> calc_emisab_all -> calc_emis_all
```

The brackets denote the source `nlimdt == 0` skip branch. The driver now also
preserves `lpri` save/zero/restore and the final
`nry = nbinc(13.6, epi, ncn2) + 2` assignment.

Composition exposed one real ownership correction: `calc_emisab_all` consumes
the reduced `epim(1:ncn2m)` grid while continuum arrays remain dimensioned on
the full caller grid. The port now requires capacity for the active reduced
range and preserves all higher caller-owned rows. The bounded complete-local
fixture passes call-order, skip, shared-workspace, reduced/full-grid, ranking,
array-continuity, and final-state gates. Radial transfer and output are next.

Run:

```bash
PYTHONPATH=src python examples/133_validate_xstar_complete_local_xstarcalc.py \
  --out-dir xstar_complete_local_xstarcalc_source_validation_v0463 \
  --print-summary
```

## v0.4.62 source-faithful `calc_emis_all` - 2026-05-22

The user-side v0.4.61 validation confirms the complete `calc_emisab_all`
source chain. v0.4.62 translates `calc_emis_all.f90`, `rlbin.f90`,
`calc_emis_element.f90`, `calc_emis_ion.f90`, and the final `freef.f90` and
`bremem.f90` source slots.

The translation preserves the pre-reset ranking dependency on `calc_emisab_all`
line/RRC products, literal `rlbin` insertion ordering, the effective
`nrank-1` source retention behavior, source-owned continuum reset, caller-owned
`fline/flinel`, all-ion compact aliases, inactive-ion offsets, active-ion
`leveltemp` writes, rate-type-7 strong RRC output, rate-type-9's two `ucalc`
invocations, rate-type-42 reuse of the retained continuum pointer, strong-line
`fline/flinel` formulas, and `ucalc` continuum side effects.

The bounded fixture exercises all of those ownership and control-flow details,
plus the final `freef` and `bremem` calls. `calc_emis_all` is accepted and the
next source-order target is the complete local `xstarcalc` sequence.

Run:

```bash
PYTHONPATH=src python examples/132_validate_xstar_calc_emis_all.py \
  --out-dir xstar_calc_emis_all_source_validation_v0462 \
  --print-summary
```

## v0.4.61 source-faithful `calc_emisab_all` - 2026-05-21

The user-side v0.4.60 validation confirms the complete `bremsmap -> nbinc ->
huntf` gate. v0.4.61 advances one source-order step and translates
`calc_emisab_all.f90 -> calc_emisab_element.f90 -> calc_emisab_ion.f90`.

The translation preserves the two source density overrides, the distinction
between arrays cleared by `calc_emisab_all` and continuum arrays carried into
`ucalc`, source-order all-ion compact population mapping, repeated
continuum/next-ion-ground aliases, inactive-ion compact offsets, mutable
`leveltemp` writes only for active ions, one-based line/RRC pointers, and the
rate-type 4/7/9/14 branches. The type-53 live evaluator now exposes its
per-record `opakc`, `opakcont`, and inward/outward `rccemis` increments so the
caller can reproduce `ucalc` side effects instead of using only scalar
`ans1..ans6` values.

The bounded validation uses an independent synthetic ATDB/pointer state that
contains two aliased ions while only the first ion is active. It exercises all
four source branches and verifies output ownership and source record order.
`calc_emis_all` is the next source-order target.

Run:

```bash
PYTHONPATH=src python examples/131_validate_xstar_calc_emisab_all.py \
  --out-dir xstar_calc_emisab_all_source_validation_v0461 \
  --print-summary
```

## v0.4.60 source-faithful `bremsmap` - 2026-05-21

The v0.4.59 offline acceptance run confirms `ready_to_advance_to_bremsmap=True`.
v0.4.60 translates the exact `xstarcalc.f90 -> bremsmap.f90 -> nbinc.f90 ->
huntf.f90` path.  The implementation preserves the reduced `nbinc` search
extent, binary32-rounded default-real constants, caller-owned `bremsam` tail,
the literal descending `1:ncn2m` `bremsint` update, and the incoming
`bremsint(ncn2m+1)` tail boundary inherited from `trnfrc`.

Two frozen cases were generated by compiling the unmodified XSTAR routines
with only minimal `globaldata/constants` stubs.  Python reproduces every mapped
`bremsam` value and every mutated `bremsint` value within `2e-15` relative
tolerance.  The source routine can now mutate `XSTARPythonState.radiation` and
register as the `BREMSMAP` driver routine.  `calc_emisab_all` is the next
source-order target.

Run:

```bash
PYTHONPATH=src python examples/130_validate_xstar_bremsmap.py \
  --out-dir xstar_bremsmap_source_validation_v0460 \
  --print-summary
```

## v0.4.59 final normalized-residual source semantics - 2026-05-21

The user-side v0.4.58 exact post-`dsec` replay reproduces the complete captured
call-entry runtime and continuum state.  Every underlying fixed-state quantity
passes: runtime, continuum components, primary and secondary heating/cooling
totals, electron contribution, charge residual, and charge identity.  The only
strict failure is `hmctot`, whose relative difference is amplified by cancellation
near thermal equilibrium.

Python and XSTAR independently reproduce the literal `heatf.f90` expression

```text
hmctot = 2 * (httot - cltot) / (1e-37 + httot + cltot)
```

with values `6.007235133655397e-5` and `8.259870956279396e-5`.  Both satisfy
XSTAR's actual `dsec.f90` convergence condition `abs(hmctot) <= 1.e-4`.
Therefore the strict residual mismatch does not change the source convergence
decision and is retained as a diagnostic rather than a physics blocker.

v0.4.59 adds:

- source-expression and source-convergence classification for the exact final
  replay;
- `examples/129_validate_xstar_dsec_final_residual_semantics.py`;
- `xstar-atomic-validate-dsec-final-residual-semantics`;
- an offline reanalysis path that consumes a completed v0.4.58 result tree and
  requires no ATDB read, XSTAR rebuild, or 33-evaluation rerun; and
- separate strict and source-semantic final-state fields.

The O VII local-zone Milestone-4 `dsec` gate is source-semantically accepted.
Strict floating-point trajectory, transition-array, natural-root, and normalized
residual differences remain visible.  `bremsmap` is now the next source-order
translation target.  Production defaults remain `dense-source`,
`reset-per-call`, and `source-zero`.

## v0.4.58 exact post-`dsec` final-call replay - 2026-05-21

The user-side v0.4.57 unrestricted run converged naturally in the same 33
`calc_hmc_all` evaluations as XSTAR and preserved the complete event sequence,
integer controls, and thermal/charge residual signs.  The only thermal trajectory
row outside the 0.5% relative gate was evaluation 24 `hmctot`, where both codes
remain negative and differ by `2.180338e-5` in a normalized residual close to
zero.  Every underlying heating/cooling component passes; the largest component
differences are only a few `1e-12`.

The naturally converged Python root is `T4=7.664826496730516`, versus the XSTAR
post-`dsec` input `T4=7.665518557731817` (about `9.03e-5` relative).  This small
root displacement explains the strict runtime and continuum-workspace failures
in the natural post-`dsec` fixed-state comparison, while all primary/secondary
thermal totals, charge quantities, and `hmctot` pass their physical tolerances.

v0.4.58 adds:

- `--post-dsec-input-mode natural|compare-both` to the physical runner;
- exact replay of the correlated XSTAR post-`dsec` call-entry runtime, radiation,
  escape arrays, continuum workspaces, dense global populations, and `leveltemp`;
- `examples/128_validate_xstar_dsec_post_final_replay.py`;
- `xstar-atomic-validate-dsec-post-final-replay`;
- source-semantic trajectory classification that treats event/integer/residual-
  sign parity separately from normalized near-zero residual magnitude; and
- a final gate that requires the exact post-`dsec` replay to reproduce the fixed
  state before `bremsmap` is unlocked.

Production defaults remain `dense-source`, `reset-per-call`, and `source-zero`.
No XSTAR rebuild or new capture is required.

## v0.4.57 - 2026-05-21

v0.4.57 consumes the user-side v0.4.56 natural source-zero four-evaluation
prefix.  The bounded source-semantic gate passes: all four thermal evaluations,
source event and integer-control branches, thermal/charge residual decisions,
evaluation-2 Lucy entry and active final populations, source-order `xtot`,
thermal families, and element arrays agree with XSTAR within the established
acceptance tolerances.

Strict trajectory parity remains false because ten carried charge-workspace rows
differ by about `2.0e-11`; the differences propagate from `elctrh` into the
charge secant `xee`/`elctrl` values without changing any source branch or
residual decision.  The natural evaluation-2 dense global arrays also remain
outside the intentionally extreme `5e-12` transition tolerance, while the
source-used `leveltemp`, complete solver path, and thermal result pass.

New example 127 and `xstar-atomic-validate-dsec-source-zero-unrestricted` run the
natural source-zero physical solve without a prefix limit, compare every
captured XSTAR evaluation, execute the correlated post-`dsec` `calc_hmc_all`
call, and report strict floating-point parity separately from source-semantic
local-zone acceptance.  A successful result is the gate for advancing in source
order to `bremsmap`.  No physical formula, rate, matrix, tolerance, XSTAR source,
or probe capture changes in this release.

## v0.4.56 - 2026-05-21

v0.4.56 consumes the user-side v0.4.55 terminal-seed causality result.  The
literal `calc_hmc_element.f90` terminal write `x(ipmat2+1)=0.` is confirmed as
the primary cause of the evaluation-2 cooling discrepancy.  Under exact XSTAR
transition replay, `source-zero` makes the initial Lucy vector, final active
populations, outer-iteration entry, source-order `xtot`, thermal families, and
element heating/cooling arrays pass.  The evaluation-2 pre-continuum cooling
relative difference falls from `9.60070043e-3` to `5.69511833e-7`, and the
`hmctot` relative difference falls from `8.35736580e-3` to `1.29364826e-6`.

The remaining physical-run exit code is not a thermal or branch failure.  The
strict trajectory gate rejects only the carried `elctrh` work bound at two
events, with an absolute difference of about `2.03e-11`; event order, integer
control state, residual signs/values, and final prefix state pass.

New example 126 and `xstar-atomic-validate-dsec-source-zero-prefix` run four
natural evaluations without exact transition replay.  They compare the natural
evaluation-2 entry and internals against XSTAR and report strict runtime parity
separately from source branch/residual parity.  This is a bounded diagnostic and
acceptance step before the unrestricted 33-evaluation `dsec` run.  Production
physics remains `dense-source`, `reset-per-call`, and `source-zero`; no XSTAR
source change or rebuild is required.

## v0.4.55 - 2026-05-21

v0.4.55 corrects the terminal compact-continuum population seed passed into
`msolvelucy`.  The user-side v0.4.54 internal comparison found exactly one
failed solver-entry row for each of H, He, and O: the final compact row.  XSTAR
has exact zero there, while Python retained the incoming global continuum or
next-ion-ground population.

The source performs all selected-ion `xileve -> x` mappings first and then
executes `x(ipmat2+1)=0.` immediately before `msolvelucy`.  Python now mirrors
that order through the production default `--terminal-continuum-seed-mode
source-zero`; `legacy-global` remains available only for causality and
historical diagnostic reproduction.

New example 125 and `xstar-atomic-validate-dsec-terminal-seed` compare both
seeds under exact evaluation-2 replay and the complete same-call internal
audit.  No XSTAR source change, rebuild, or new run is required.  Dense native
writeback, per-call `leveltemp` reset, rates, matrices, thermal formulas, and
frozen acceptance gates are otherwise unchanged.

## v0.4.54 - 2026-05-21

v0.4.54 consumes the user-side v0.4.53 exact-replay result.  Exact XSTAR
evaluation-2 call-entry state passes, but it removes only about `2.2e-6` of the
pre-continuum cooling discrepancy, which rules out evaluation-1 population
writeback and transition-state ownership as the cause of the remaining error.

The physical runner can now apply the existing complete same-call
`calc_hmc_all` parity audit to a selected internal `dsec` evaluation through
`--compare-transition-internals`.  The audit covers pre-matrix ion rates and
selection, full and active matrix topology/coefficient closure, initial and
final Lucy populations, outer-iteration entry, source-order `xtot`, thermal
data/rate families, and element heating/cooling arrays.

New example 124 and `xstar-atomic-validate-dsec-eval2-internals` force exact
evaluation-2 replay, run the internal audit, and classify the first failed
source layer.  The diagnostic reuses the v0.4.51 evaluation-2 probe directory;
no XSTAR source change, rebuild, or new XSTAR run is required when its detailed
products are present.  Production physics, dense native writeback, per-call
`leveltemp` reset, and all frozen acceptance gates are unchanged.

## v0.4.53 - 2026-05-21

v0.4.53 adds a diagnostic-only exact XSTAR-seeded replay for a selected later
internal `dsec` evaluation.  The physical runner can now replace evaluation-2
call-entry runtime, radiation, escape arrays, continuum workspaces, dense
`xilevg`/`bilevg`/`rnisg`, and `leveltemp` with the captured XSTAR state while
Python still computes all rates, matrices, Lucy populations, cooling, and
residuals.  Use `--transition-input-mode replay-exact`.

New example 123 and `xstar-atomic-validate-dsec-exact-replay` run the normal
Python transition and exact XSTAR-seeded transition side by side.  Every
physical run now writes per-evaluation, per-element thermal and Lucy-solver
diagnostics.  The wrapper classifies whether the remaining evaluation-2
cooling discrepancy was produced by evaluation 1 or lies inside evaluation 2.
No XSTAR rebuild or production physics change is required.

## v0.4.52 - 2026-05-21

v0.4.52 corrects the two mutable-state ownership failures isolated by the
call-correlated evaluation-2 diagnostic.

First, repeated physical `dsec` calls now carry authoritative dense native
`xilevg`, `bilevg`, and `rnisg` arrays indexed by the original XSTAR global
level index.  `calc_hmc_all` reconstructs the full source-order element
workspace for every ion, including inactive boundary ions, applies the
`ipmat += nlev - 1` continuum/next-ground overlap, and replays both distinct
global writes.  The lower-ion continuum retains the literal `1d-48`
departure-coefficient floor while ordinary/ground rows use `1e-37`.  Logical
`(Z, stage, local_level)` maps remain diagnostic views rather than owners of
mutable state.

Second, the physical `dsec` path now resets the shared `leveltemp` workspace to
the exact correlated `calc_hmc_all` entry state before every new evaluation.
Within one call, all source-order writes from `levwkelement` and the second
`calc_hmc_ion` pass, partial overwrites, retained higher columns, and owner
provenance are unchanged.  The final within-call workspace is retained as a
diagnostic snapshot but is not carried into the next evaluation.

A controlled four-mode causality scan was added:

- A: legacy selected-role writeback plus cross-call `leveltemp` carry;
- B: per-call `leveltemp` reset only;
- C: dense native alias writeback only;
- D: both production corrections.

Use `examples/122_validate_xstar_dsec_transition_causality.py` or
`xstar-atomic-validate-dsec-causality`.  The ordinary physical runner defaults
to mode D and exposes `--global-writeback-mode` and `--leveltemp-lifecycle` for
bounded diagnosis.  No XSTAR rebuild is required; reuse the v0.4.48
instrumented executable and the evaluation-2 probe products.

## v0.4.51 - 2026-05-21

v0.4.51 adds a bounded evaluation-transition diagnostic for the physical
`dsec` workflow. The call-correlated evaluation-1 state and thermal
decomposition pass, but the v0.4.50 prefix first exceeds the thermal tolerance
at evaluation 2. The new path captures the Python state immediately before a
selected `calc_hmc_all` evaluation and compares it with the exact XSTAR entry
state captured for that same `dsec_call_id`, evaluation index, phase, and global
`calc_hmc_all` call ID.

New coverage includes runtime and geometry scalars, continuum/radiation arrays,
line and continuum optical-depth arrays, carried `opakc`/`brcems` workspaces, global `xilevg`/`bilevg`/`rnisg`, and
the `leveltemp` slots actually read by `ucalc.f90`. Raw all-slot `leveltemp`,
`nlpt`, and `iltp` values are retained in diagnostic products. The matching
loader now maps orbital angular momentum from source `ilev(3)` and preserves
source threshold `rlev(4)`. Snapshots are opt-in and restricted to requested
evaluation indices to avoid deep-copy overhead during ordinary full runs.

Added `examples/121_validate_xstar_dsec_transition_state.py` and the
`xstar-atomic-validate-dsec-transition` command. No scientific XSTAR source or
helper change is required; the v0.4.48 instrumented executable can capture
evaluation 2 through its existing environment selection. Physical bounded
`dsec` acceptance remains open.

## v0.4.50 - 2026-05-21

v0.4.50 is a Python-only progress-reporting hotfix for the call-correlated
physical `dsec` runner.  With `--progress`, example 119 incorrectly tried to
read `item.equilibrium.basis.n_rows`; the actual source-owned basis is at
`item.equilibrium.assembly.basis.n_rows`.  The physical calculation completed
its first evaluation, but the optional callback raised `AttributeError` before
prefix products could be written.

The reporter now reads the assembly basis through a small tested formatter.
No solver state, rates, matrices, thermal decomposition, call correlation,
trajectory data, acceptance tolerance, or XSTAR source changed.

## v0.4.49 - 2026-05-20

v0.4.49 is a Python-only hotfix for the call-correlated physical `dsec`
runner.  The exact first internal `dsec` state has a source-valid all-zero
`xilevg` population vector.  v0.4.48 correctly taught the matrix solver to
accept that state, but the same-call population probe loader still rejected it
before example 119 could start.

The general fixed-state loader remains strict by default.  A new explicit
`allow_zero_sum`/`allow_zero_initial_population_sum` path is enabled only by
example 119 when the correlated matching input proves that incoming global
`xilevg` is exactly zero.  No XSTAR source, probe helper, rates, matrices,
thermal physics, or control-flow semantics changed.

## v0.4.48 - 2026-05-20

v0.4.48 is a bounded call-correlation and matching-state correction for the
physical `dsec` runner. The v0.4.47 production run proved that the translated
control sequence agreed with XSTAR through event 88, but it mixed `dsec` call 1
with the unrelated historical `calc_hmc_all` call-73 radiation/escape/workspace
state. This release removes that ambiguity rather than relaxing tolerances.

- Adds a shared diagnostic Fortran correlation module linking every global
  `calc_hmc_all` call to `dsec_call_id`, internal evaluation index, and phase
  (`dsec_internal`, `post_dsec`, or `outside_dsec`).
- Captures the exact state entering the correlated first internal
  `calc_hmc_all` call: continuum grid and radiation arrays, line/continuum
  optical depths, global `xilevg/bilevg/rnisg`, complete `leveltemp`, geometry,
  density mode, pressure, covering fraction, turbulence, and `critf`.
- Separates the input and post-`dsec` probe directories/call IDs in example 119.
  Call IDs may be resolved automatically from the correlation CSV.
- Adds an XSTAR thermal-decomposition row after every internal `calc_hmc_all`
  evaluation, including pre-continuum totals, Compton, free-free, bremsstrahlung,
  final totals, `hmctot`, and `elcter`. Python writes the same owned quantities
  and compares them evaluation by evaluation.
- Adds `--maximum-evaluations N` fast prefix mode and `--progress`. Prefix mode
  validates the first N physical evaluations against the corresponding XSTAR
  trajectory/thermal prefix without waiting for the full nonlinear solve.
- Adds `examples/120_prepare_xstar_dsec_matching_probe.py` and the
  `xstar-atomic-prepare-dsec-matching-probe` console command.
- Keeps v0.4.44 fixed-state acceptance frozen and keeps v0.4.45 bounded dsec
  acceptance pending the new instrumented production rerun.
- No emissivity, transfer, radial-zone, or atomic-rate physics is added.

## v0.4.47 - 2026-05-20

v0.4.47 is a bounded physical-`dsec` state-ownership correction after the
first production execution of example 119. The v0.4.46 runner incorrectly
replayed the converged 607-row oxygen compact vector at the initial `T4=100`
trial, where `istruc` selected a 367-row oxygen basis. XSTAR does not carry a
basis-sized vector between trials: it carries the global `xilevg` workspace and
remaps that workspace after every new active-ion selection.

- Adds explicit mutable global-level population state keyed by
  `(element_z, ion_stage, local_level)`.
- Initializes the first physical `dsec` call from the exact `init.f90` state:
  all global `xilevg` entries are zero.
- Remaps global populations onto each current compact basis in literal
  `calc_hmc_all.f90` ion/level order, including overwrite of each shared
  parent-continuum/next-ion-ground alias by the later ion ground state.
- Preserves inactive global rows across trials so a later expanding ion range
  sees the same stale global values as Fortran.
- Allows the source-valid all-zero first `msolvelucy` seed; the translated Lucy
  solver then uses the original `rr=1` zero-superlevel fallback and imposes
  number conservation in the condensed solve.
- Retains compact population vectors only as diagnostics; they are no longer
  reused across dynamic `dsec` basis changes.
- Adds focused regressions for shared-alias remapping, zero initialization,
  zero-seed Lucy behavior, stale inactive-row retention, and suppression of the
  invalid 607-to-367 compact replay.
- Bounds the zero-initialized physical runner to `dsec_call_id=1`; later calls
  require a captured/restored incoming global population workspace.
- No XSTAR rebuild or probe change is required. Reuse the v0.4.45 twelve-hook
  `dsec` build and rerun example 119.

## v0.4.46 - 2026-05-20

v0.4.46 adds the missing physical example-119 runner needed to exercise the
translated `dsec` algorithm with the real source-faithful `calc_hmc_all`
evaluator. It does not claim physical acceptance by itself and adds no
emissivity, transfer, or radial-zone physics.

- Adds `PhysicalDsecInitialState`, `PhysicalDsecContinuumTemplate`, and
  `PhysicalDsecCalcKwargsFactory`.
- Adds `examples/119_validate_xstar_dsec_complete.py` and the
  `xstar-atomic-validate-dsec-physical` console entry point.
- Resolves the initial temperature, electron fraction, hydrogen density,
  `nlim`, and `tinf` from the selected XSTAR `begin` trajectory row by default,
  with checked and explicit override modes.
- Builds the H/He/O source-order element requests from the accepted call-73
  plan and carries compact populations plus the shared `leveltemp` workspace
  from one physical `calc_hmc_all` trial to the next.
- Recomputes `comp2 -> freef -> bremem -> heatf` contexts at every trial using
  the current temperature, density, and electron fraction. The incident
  continuum and geometry remain fixed same-zone inputs.
- Carries caller-visible `opakc`/`brcems` scratch workspaces between trials,
  with explicit zero or call-73-probe first-call policies.
- Runs the Python trajectory, compares it directly with one instrumented XSTAR
  `dsec` call, performs the source-order post-`dsec` `calc_hmc_all` call,
  compares that Python fixed state with the accepted call-73 final-state probe, and writes the complete bounded acceptance products in the
  same process so the final `FixedStateCalcHMCAllResult` is retained.
- Strengthens the bounded acceptance gate with
  `final_fixed_state_parity_ready`.
- Adds a `--prepare-only` mode for validating all input/provenance resolution
  before the expensive physical run.
- Physical `v0445_bounded_dsec_acceptance_ready=True` remains pending the
  user's production execution of example 119.

## v0.4.45 - 2026-05-20

v0.4.45 starts the stateful local-equilibrium stage after the accepted v0.4.44
complete fixed-state `calc_hmc_all` milestone. It translates the exact
`dsec.f90` nested charge/thermal control algorithm and adds the mutable state
needed to carry one `calc_hmc_all` trial into the next. No emissivity, transfer,
or radial-zone physics is added.

- Adds `DsecMutableRuntimeState`, which owns native XSTAR `T/1e4`, `xee`, the
  resolved hydrogen density, source-order element request templates, the final
  compact population vector for every active element, the shared mutable
  `leveltemp` workspace with per-column ownership, and caller-visible global
  arrays/work arrays.
- Extends `ElementEquilibriumContext`, `ElementMatrixAssembly`,
  `FixedStateCalcHMCAllResult`, and `calc_hmc_all` so the complete shared
  `leveltemp` state may be supplied, overwritten in source order, returned, and
  replayed in the next element or `dsec` trial. Legacy one-call behavior remains
  unchanged when no incoming workspace is supplied.
- Translates the literal `dsec.f90` double-secant/bracketing path, including
  positive/negative/zero `nlim`, the `tinf*1.01` gate, default-real rounding of
  `1.e-4`, `2.e-9`, `1.2`, `0.9`, and `1.e30`, source branch order, doubled
  far-from-equilibrium temperature steps, charge and temperature secants,
  stagnation handling, iteration counters, and `lnerr` semantics.
- Adds `CalcHMCAllDsecEvaluator`; every trial rebuilds its element requests from
  the previous final compact populations and reuses the same dispatcher and
  mutable workspace rather than restarting from the original call-73 seed.
- Adds a diagnostic-only XSTAR trajectory helper and twelve documented
  insertion hooks covering entry, each post-`calc_hmc_all` state, charge
  multiply/divide/secant branches, charge-loop exit, temperature
  multiply/divide/secant/stagnation branches, iteration exhaustion, and return.
- Adds trajectory CSV/JSON/Markdown writers, XSTAR and Python trajectory
  loaders, exact event/integer-state comparison, strict runtime-state parity,
  and residual validation that requires both value agreement and sign parity.
  Near equilibrium, absolute tolerances replace ill-conditioned relative-only
  tests.
- Bundles the accepted v0.4.44 complete fixed-state summary as an immutable
  prerequisite gate.
- Adds `xstar-atomic-port-dsec`, `xstar-atomic-prepare-dsec-probe`, examples 117
  and 118, and synthetic branch tests.
- The physical `v0445_bounded_dsec_acceptance_ready=True` claim is deliberately
  deferred until the new XSTAR trajectory is captured and compared. The next
  source sequence after that gate is `bremsmap -> calc_emisab_all ->
  calc_emis_all -> complete xstarcalc`.

## v0.4.44 - 2026-05-20

v0.4.44 is a bounded state-ownership and validator correction for the complete
fixed-state `calc_hmc_all` milestone. No XSTAR physics routine or probe hook is
changed. The existing seventeen-hook v0.4.43 production capture remains the
physical oracle.

- Adds explicit `httot_pre_continuum`, `cltot_pre_continuum`,
  `httot2_pre_continuum`, and `cltot2_pre_continuum` fields to
  `FixedStateCalcHMCAllResult`.
- Captures those values immediately after the positive-abundance H/He/O element
  loop and before `comp2 -> freef -> bremem -> heatf`.
- Retains `httot`, `cltot`, `httot2`, and `cltot2` as the final post-`heatf`
  caller-visible state.
- Corrects `compare_calc_hmc_all_pre_continuum_probe` to compare the explicit
  pre-continuum snapshot against XSTAR's pre-continuum probe. A compatibility
  fallback may use the older `*_before_heatf` diagnostics, but a complete
  continuum result never falls back to final totals.
- Adds synthetic and physical call-73 regression tests proving that each final
  total minus its pre-continuum owner equals the translated continuum increment.
- Updates example 116 and the complete-fixed-state CLI to report v0.4.44
  acceptance while reusing the existing v0.4.43 XSTAR probe directory.
- No XSTAR rebuild is required. `dsec` remains deferred until the corrected
  complete fixed-state acceptance gate passes.

## v0.4.43 - 2026-05-20

v0.4.43 closes the translated fixed-state `calc_hmc_all` source sequence
without adding a new physical leaf. It executes the accepted element loop and
`comp2 -> freef -> bremem -> heatf` chain in literal source order, commits the
final primary and secondary heating/cooling totals, and validates the
caller-visible electron contribution and charge residual before return.

A new final-state parity layer compares one same-call XSTAR row containing
`enelec`, `elcter`, `htfreef`, `cmp1`, `cmp2`, `htcomp`, `clcomp`, `clbrems`,
`httot`, `cltot`, `httot2`, `cltot2`, and `hmctot`. Runtime and continuum
components use strict source-level tolerances; final thermal and charge totals
use the established all-element acceptance tolerance because the translated
pre-continuum element totals are already accepted at that tolerance.

The bounded helper expands from sixteen to seventeen hooks with a final
post-`heatf`, pre-return `xap_hmc_final_state` call. Example 116 and CLI
`xstar-atomic-port-complete-fixed-state` execute the full H/He/O fixed-state
calculation and require current same-call pre-continuum, Compton, free--free,
bremsstrahlung, heatf, final thermal, and charge parity, while preserving the
frozen v0.4.34, v0.4.38, v0.4.39, v0.4.40, v0.4.41, and v0.4.42 regressions.
Physical call-73 acceptance requires a rebuilt seventeen-hook XSTAR run.
`dsec` remains untranslated until that gate passes.

## v0.4.42 - 2026-05-20

v0.4.42 translates XSTAR `heatf.f90` as the first bounded Milestone-4
subsystem that accumulates the translated continuum terms into local thermal
totals. The implementation preserves default-real literal rounding, the
source-order trapezoidal integration of `brcems` into `clbrems`,
`htcomp=cmp1*(xpx*xee)*ergsev`, `clcomp=ekt*cmp2*(xpx*xee)*ergsev`, the
left-to-right updates of `httot`, `cltot`, `httot2`, and `cltot2`, and the
source `hmctot` normalization floor. Incoming element heating/cooling totals
are explicit and retained.

The fixed-state `calc_hmc_all` path can now execute `comp2 -> freef -> bremem
-> heatf` and return complete continuum accumulation. The result is marked
continuum-complete only when all four translated contexts are present, and the
exact final totals from `heatf` are committed without re-associating floating
point additions.

The bounded XSTAR helper expands from thirteen to sixteen hooks. A pre-`heatf`
hook captures incoming thermal totals and continuum coefficients; a loop-local
hook captures exact cumulative `clbrems`; and a post-`heatf` hook records
`htcomp`, `clcomp`, `clbrems`, both final total pairs, and `hmctot`. Example 115
and CLI `xstar-atomic-port-heatf` require exact integral and accumulation parity
while preserving the frozen v0.4.34 oxygen, v0.4.38 H/He/O, v0.4.39 Compton,
v0.4.40 free--free, and v0.4.41 bremsstrahlung regressions. Physical call-73
acceptance requires a rebuilt sixteen-hook XSTAR production run.

## v0.4.41 - 2026-05-20

v0.4.41 translates XSTAR `bremem.f90` as the next bounded Milestone-4
subsystem after the accepted v0.4.40 free--free gate. The implementation
preserves default-real literal rounding, source temperature conventions,
`xnx=xpx*xee`, `enz2=1.4*xnx`, `cc=1.032e-13`, `zz=1`, the current unity Gaunt
factor, complete clearing of `brcems(1:ncn2)`, source-order emissivity
construction, `bbee=0`, and the inactive/commented opacity branch. The incoming
`opakc` workspace is preserved exactly.

The fixed-state `calc_hmc_all` path can now execute `comp2`, `freef`, and
`bremem` in source order, exporting Compton coefficients, `htfreef`, final
`brcems`, and final `opakc`. These remain unaccumulated until `heatf` is
translated.

The bounded XSTAR helper expands from eleven to thirteen hooks. A post-`freef`,
pre-`bremem` hook captures incoming `brcems` and `opakc`; a loop-local hook in
`bremem.f90` captures exact `brtmp`, final `brcems`, `bbee`, and unchanged
`opakc`. Example 114 and CLI `xstar-atomic-port-bremem` require exact
emissivity, reset, and opacity-preservation parity while preserving the frozen
v0.4.34 oxygen, v0.4.38 H/He/O, v0.4.39 Compton, and v0.4.40 free--free
regressions. Physical call-73 acceptance requires a rebuilt thirteen-hook XSTAR
production run. `heatf` remains deferred.

## v0.4.40 - 2026-05-20

v0.4.40 translates XSTAR `freef.f90` as the next bounded Milestone-4 source
subsystem after the accepted v0.4.39 Compton gate. The implementation preserves
default-real literal rounding, the source `t`/`t6` temperature conventions,
`xnx=xpx*xee`, `enz2=1.4*xnx`, the current unity Gaunt factor, stimulated
free--free absorption, in-place mutation of the caller-owned `opakc` array, and
the source-order trapezoidal accumulation of `htfreef` over `epi` and `bremsa`.
The incoming opacity is explicit state and is never assumed to be zero.

The fixed-state `calc_hmc_all` path can now execute `comp2` followed by `freef`,
exporting `cmp1`, `cmp2`, `htcomp`, `clcomp`, `htfreef`, and the updated
continuum opacity workspace. None of these terms is accumulated into complete
thermal totals until `heatf` is translated. `bremem` and `heatf` remain
explicitly deferred.

The bounded XSTAR helper expands from nine to eleven hooks. A pre-`freef` hook
captures the incoming opacity array, and a loop-local hook in `freef.f90`
captures the exact source `opaff`, updated `opakc`, and cumulative `htfreef`
without reconstructing small increments by subtraction. Example 113 and CLI
`xstar-atomic-port-freef` require exact opacity-increment, opacity-mutation, and
`htfreef` parity while preserving the frozen v0.4.34 oxygen, v0.4.38 H/He/O,
and accepted v0.4.39 Compton regressions. Physical call-73 acceptance requires
a rebuilt eleven-hook XSTAR production run.

## v0.4.39 - 2026-05-20

v0.4.39 translates the coherent relativistic Compton subsystem in source order:
`calc_hmc_all -> comp2 -> cmpfnc -> hunt3`, together with the global
`coheat.dat` table state initialized by `xstarsetup.f90`. The implementation
preserves the source `ncomp=101` grids, `decomp(sx_index,energy_index)` table
orientation, one-based `hunt3` boundary behavior, bilinear `cmpfnc`
interpolation, low-energy analytic branch, source-rounded default-real
constants, and the `comp2` trapezoidal continuum integrations over `epi` and
`bremsa`.

The translated fixed-state `calc_hmc_all` path can now execute `comp2` and
export `cmp1`, `cmp2`, and the corresponding `heatf` Compton heating/cooling
coefficients without yet accumulating them into complete thermal totals;
`freef`, `bremem`, and `heatf` remain untranslated. The exact source
`coheat.dat` table is packaged as runtime data, and the accepted v0.4.34 oxygen
and v0.4.38 H/He/O pre-continuum results are frozen as mandatory regression
gates.

The bounded XSTAR helper expands from eight to nine hooks. A new insertion
immediately after `call comp2` captures the exact same-call continuum grid,
`cmp1`, `cmp2`, `ekt`, and derived Compton heating/cooling coefficients.
Example 112 and CLI `xstar-atomic-port-compton` validate the requested v0.4.39
gates. Package tests and an independent original-Fortran driver validate the
translation, but physical call-73 acceptance is intentionally pending a rebuilt
nine-hook XSTAR production run.

## v0.4.38 - 2026-05-20

v0.4.38 closes the single blocker isolated by the complete v0.4.37 H/He/O
call-73 rerun. The type-77 source gate is confirmed correct: all H/He type-77
terms pass, all active final and outer-start populations pass, all source
`xtot` rows pass, and every thermal family passes. The remaining row was H I
`global_ion_xiin`, where Python exported the final-outer-start `xo` total
(`3.1712826766e-6`) while XSTAR exports the returned final `x` total
(`3.2072205404e-6`).

The fixed-state `calc_hmc_all` loop now preserves both source vectors with their
literal roles: `xiin`, charge accounting, and the fully stripped residual use
`calc_hmc_element`'s returned final-`x` ion total; `xtotg` remains the separate
`msolvelucy` diagnostic accumulated from `xo` at the start of the final outer
iteration. A compatibility fallback is retained only for synthetic test doubles
that predate the explicit final-vector total. Example 111 validates the split
semantics and the complete H/He/O pre-continuum gate. No XSTAR source change,
helper replacement, or rebuild is required.

## v0.4.37 - 2026-05-19

v0.4.37 closes the single source-semantic blocker isolated by the complete
v0.4.36 H/He/O production rerun. XSTAR `ucalc.f90` label 77 returns exact
zero before `calt77` when the mutable endpoint energy separation is below
1 eV. Python now applies that gate in source order while retaining valid
endpoints and the normal four zero-valued matrix roles. The correction targets
22 H records/88 terms and 26 He records/104 terms; the hydrogen `xiin` blocker
was traced specifically to record 572.

The data-path round-trip test now removes both supported environment aliases,
`XSTAR_ATDB_FITS` and `XSTAR_ATDB`, so a configured user shell no longer
invalidates the isolated test. Runtime path precedence is unchanged. A new
example 110 validates type-77 parity and the complete all-element gate. No
XSTAR rebuild is required.

## v0.4.36 - 2026-05-19

v0.4.36 is narrowly bounded to the hydrogen and all-element differences exposed
by the complete v0.4.35 H/He/O call-73 probe. It translates XSTAR data type 62
through the native label-60/`calt6062` path, restoring H I records 488--491 and
their 16 four-role matrix terms. It adds a source diagnostic for their packed
endpoints, quantum numbers, fit coefficients, rates, and insertion status.

Matrix parity now joins terms by `(element_z, source_record, role)` and retains
Python/XSTAR term indexes only as call-order diagnostics, preventing one omitted
record from shifting the rest of an element. Same-call initial-population parity
is generalized to H, He, and O, covering 718 compact rows with per-element
readiness. The all-element reports add solver, `xtot`, thermal, blocker, and
detailed-readiness fields for each selected element.

## v0.4.35 - 2026-05-19

v0.4.35 starts the full source-order, positive-abundance fixed-state
`calc_hmc_all` element scope while retaining the accepted v0.4.34 oxygen
call-73 result as a mandatory packaged regression gate. The new
`all_element_fixed_state` module derives the active source element list from
positive-abundance type-11 probe rows, preserves source order and `mml/mmu`,
tracks per-element same-call seed/matrix/final/thermal/workspace coverage, and
executes the complete pre-continuum element loop with explicit charge-scope
accounting. Initial-population policies are `use-available`, `require-all`, and
`ignore`.

The release adds CLI `xstar-atomic-port-all-elements`, example 108, and
all-element scope CSV/JSON/Markdown products. The existing probe can start the
H/He/O loop with exact oxygen state plus autonomous H/He fallback. The generated
eight-hook helper now treats `XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0` as detailed
all-abundant-element capture; insertion locations are unchanged, but a helper
replacement and XSTAR rebuild are required for complete all-element parity.
Continuum leaves remain intentionally untranslated.

## v0.4.34 - 2026-05-19

v0.4.34 is a bounded Milestone-4 oxygen-parity correction release. It is
limited to the three source-semantic differences isolated by the completed
v0.4.33 call-73 diagnosis and does not expand to all elements, continuum
leaves, `dsec`, emissivity, transfer, or outputs.

First, the element assembly now preserves the LTE `rnise` vector returned by
`levwkelement` independently from the incoming same-call `xileve` population
vector used to seed `msolvelucy`. The solver continues to start from captured
`xileve`, while global `rnisg` and derived `bilevg` are exported from the
untouched LTE vector. This targets the 35 remaining `rnisg` rows and 349
`bilevg` rows.

Second, the shared mutable `leveltemp` work array is now represented with the
literal source capacity `ndl=5000`. All columns are initialized to zero before
the ordered `levwkelement` and second-pass `calc_hmc_ion` overwrites. Columns
never written by any selected ion remain valid zero-valued workspace entries
with provenance `initial_unwritten_zero`. This targets the 205 exact type-53
workspace-energy rows and the 196 dependent type-53 `cj2` records.

Third, `_phint53hunt_exact` now preserves the source's stale `atmp22` scalar in
the cached `luse(kl) != 0` branch. XSTAR restores `sgtmp` and `atmp2`, derives
`tempi`, and intentionally does not recompute `atmp22`; the preceding loop
value therefore contributes to `sumc2`. This targets the seven type-99 `ans5`
records and the two remaining type-99/rate-7 `cooling2` thermal-family rows.

A compact packaged oxygen regression oracle freezes all requested counts, and
`examples/107_validate_v0434_oxygen_regression.py` validates the inventory
without ATDB or XSTAR. Focused v0.4.34 regression tests cover all six gates and
the integrated stale-`atmp22` quadrature path. Probe values remain diagnostic
only and never enter the production operator.

The v0.4.33 eight-hook XSTAR files are sufficient for the production
reanalysis; no XSTAR source change or rebuild is required for v0.4.34. Physical
oxygen acceptance is not claimed until example 105 is rerun and reports
`xstar_oxygen_pre_continuum_acceptance_ready=True`.

## v0.4.33 - 2026-05-19

v0.4.33 is a bounded Milestone-4 state-history and diagnostic release based on
the production v0.4.32 oxygen result. It corrects the initial population state
passed to the translated `msolvelucy`: source `calc_hmc_element.f90` maps the
incoming global `xileve/xilevg` vector into compact `x`, whereas Python had
used the LTE `rnise` vector from `levwkelement`. The eight-hook bounded XSTAR
probe now captures the complete same-call compact input vector, and the
fixed-state parity CLI replays it explicitly as source state while reporting
that the vector is a regression input rather than a production coefficient.

The mutable `leveltemp` implementation now replays the complete active-ion
write sequence performed by `levwkelement`, then overwrites only `1:nlev`
during each second-pass `calc_hmc_ion` call. Diagnostic owner metadata and a
write/read trace identify which ion last wrote each retained column. A new
post-`ucalc` XSTAR hook records the exact `leveltemp%rlev(1,idest1)` and
`leveltemp%rlev(1,idest2)` read by every selected type-49/type-53/type-99
rate-7 record, together with `ans1..ans6`. The oxygen gate requires exact
same-call input-state parity, exact mutable-workspace parity including type 53,
final/xo population parity, source `xtot`, thermal-family closure, and the
existing O III--O V reassessment.

## v0.4.32 - 2026-05-19

v0.4.32 is a bounded Milestone-4 correction release based on the production v0.4.31 oxygen probe. It preserves source `nionp` counters across inactive ion stages and repairs source-slot `xtot` aggregation; replaces the over-strict Python/XSTAR iteration-count comparison with an internal synchronized-snapshot gate; corrects type-54 to use the dimensionless `DeltaE/kT` energy channel; and preserves the mutable `leveltemp` higher-column workspace used by type 49, 53, and 99 electron-energy corrections. Focused v0.4.32 tests pass (8); the source-port regression selection passes (112); and the source-port/package/API/documentation selection passes (147 with 2 optional skips). Clean-sdist, wheel, compileall, installed-wheel, and GNU Fortran helper checks pass. The complete historical suite exceeded the 150-second execution limit. A fresh production oxygen rerun remains required before all-element expansion.

## v0.4.31 - 2026-05-19

v0.4.31 is a bounded Milestone-4 oxygen pre-continuum parity release. It completes the type-71 post-swap energy channels, corrects type-72 packed endpoints from `[-3],[-2]` to `[-4],[-3]`, adds record-resolved rate-7 `cj2` diagnosis with a dedicated type-53 gate, and introduces a synchronized seven-hook XSTAR capture of the final effective `msolvelucy` matrix, returned population vector, and final-outer-start vector.

Source review also corrected the returned ion totals: XSTAR `xtot` is formed from the population vector at the start of the final Lucy outer iteration and excludes the final compact row. Python now exports that source value separately from totals reconstructed from the returned final vector. The strict oxygen acceptance gate combines the synchronized final-solver checks with the existing active-level, global-ion, thermal-family, and matrix-closure gates and emits an explicit O III--O V/O III--O IV reassessment CSV. Probe values remain diagnostic-only. Production oxygen acceptance is not claimed until the new instrumented XSTAR run is supplied.

## v0.4.30 - 2026-05-19

v0.4.30 is a probe-I/O compatibility hotfix for the v0.4.29 oxygen
pre-continuum acceptance workflow. Some XSTAR Fortran exponential formats
omit the `E` when the exponent has three digits, for example
`-3.1564610560130326-107`. Python probe readers now accept standard `E`,
Fortran `D`, and omitted-`E` representations without changing the captured
value. Newly generated calc_hmc_all probes use explicit three-digit exponent
formats (`ES26.16E3`) so future CSVs are directly readable by standard tools.
The production operator, type-50 thermal correction, same-call matrix gates,
and all physical acceptance semantics are unchanged from v0.4.29.

## v0.4.29 - 2026-05-19

v0.4.29 is a bounded Milestone-4 oxygen pre-continuum parity release. It
restores the missing type-50 line-energy channels and adds same-call XSTAR
thermal-family and matrix-coefficient probes. Probe products remain diagnostic
only: captured XSTAR values are never substituted into the production Python
operator or native solve.

## v0.4.28 - 2026-05-19

v0.4.28 adds abundance-aware element thermal parity and an XSTAR-vector matrix-closure audit. When `--abundance` is omitted and the bounded element probe is available, example 105 uses the captured XSTAR abundance and records requested/effective/source provenance. Element outputs now include `ht`, `cl`, `ht2`, and `cl2` per unit abundance as well as scaled values.

The new diagnostic closure maps the captured XSTAR global-level populations back to the translated compact basis and evaluates `A_python @ x_XSTAR` without feeding probe values into the production solve. It writes row residuals, dominant matrix contributors, native-versus-XSTAR-vector thermal contributions, channel summaries, and data-type/rate-type family summaries. Each thermal channel is decomposed into the native Python value, the value from XSTAR populations with the same Python coefficients, the captured XSTAR value, the population-vector effect, and the remaining coefficient/source-semantic gap.

The existing primary-strict, active-population, derived-strict, and all-strict level gates are retained. v0.4.28 adds a separate matrix-closure status, an element-thermal diagnostic status, an explicit milestone acceptance gate, and a separate all-strict readiness flag. The acceptance gate requires pre-matrix and runtime-state parity, global-ion parity, active-level parity, element-array parity, XSTAR-vector closure when available, and the applicable all-element summary gate.

## v0.4.27 - 2026-05-19

v0.4.27 closes the next bounded `calc_hmc_all` parity layer.

### Corrected

- Reproduced XSTAR's two departure-coefficient floors: `1e-37` for spectroscopic `calc_hmc_element` rows and `1e-48` only for each ion's final continuum row.
- Zeroed `igammamaxg/ialphamaxg` on final continuum rows, matching the source copy bounds.
- Corrected type-77/rate-23 temperature flooring to use the actual endpoint-energy wavelength before `calt77`, while retaining the record-tail wavelength for detailed balance.

### Added

- A dedicated XSTAR element-array probe for `htt/cll/htt2/cll2`, abundance, and source element ordinal.
- Separate strict-primary, active-level, derived, and all-level parity readiness fields.
- `--xstar-calc-hmc-active-population-threshold` for the milestone gate; strict rows remain fully reported.
- Population-weighted attribution for failing `xilevg/alphag` rows.
- Diagnostic-only type-77 source-endpoint-floor versus legacy-record-floor impact CSV/JSON products.

## v0.4.26 - 2026-05-19

v0.4.26 corrects the structural global-array mappings exposed by the first
scope-aware `calc_hmc_all` pre-continuum comparison.

### Corrected

- Global level products now use the literal XSTAR pointer
  `derivedpointers%npilev(local_ordinal, ion_index)`.  The source ordinal in the
  ion's level traversal is no longer reconstructed from a packed local-level
  label.
- Preliminary `calc_ion_rates` `pirt/rrrt` values remain dedicated inputs to
  `ioneqm/istruc`, while the selected ion stages now export the independent
  second-pass `calc_hmc_ion` `pirt/rrrt` values used by `calc_hmc_all`.
- Element-indexed `htt`, `cll`, `htt2`, and `cll2` parity now uses the source
  element ordinal from the type-11 element table rather than assuming that the
  array index equals atomic number `Z`.

### Added

- `IonAssemblySummary.second_pass_pirt` and `second_pass_rrrt`, accumulated with
  the literal `calc_hmc_ion.f90` type and endpoint gates.
- Separate preliminary and second-pass ion-rate columns in fixed-state products.
- Source global-element and global-level index maps in the local-zone result and
  diagnostics.
- Regression coverage for irregular packed level labels, noncontiguous `npilev`
  indices, source element ordinals, and preliminary/second-pass rate separation.

## v0.4.25 - 2026-05-18

v0.4.25 completes the bounded pre-continuum parity layer for element-subset `calc_hmc_all` validation.

### Corrected

- The source-aligned default ion-selection threshold is now `critf=1e-7`.
- When an XSTAR `calc_hmc_all` probe directory is supplied and `--critf` is omitted, example 105 reads the captured `critf` and selected call before constructing the Python element request.
- CLI/runtime provenance now distinguishes `requested_critf`, `effective_critf`, and `critf_source`.
- `mml`, `mmu`, and `critf` are compared once per element rather than once per ion-stage row.
- All-element totals (`httot`, `cltot`, `httot2`, `cltot2`, `enelec`, and `elcter`) are no longer treated as failures for a one-element/partial-abundance calculation. Such runs report `not_comparable_subset_scope`.

### Added

- Native global-index maps from `(Z, ion_stage)` and `(Z, ion_stage, local_level)` into the XSTAR `xiin` and `xilevg` array indices.
- Direct comparison of the XSTAR pre-continuum global ion arrays: `xiin`, `rrrt`, `pirt`, `stotg`, `atotg`, and `xtotg`.
- Direct comparison of the element-indexed `htt`, `cll`, `htt2`, and `cll2` values carried in the ion probe.
- Direct comparison of selected global level arrays: `xilevg`, `rnisg`, `bilevg`, `gammag`, `alphag`, `igammamaxg`, and `ialphamaxg`.
- Separate readiness fields for the runtime state, all-element summary scope, global ion arrays, global level arrays, and the combined global-array gate.

### Production evidence

The user's v0.4.24 rerun with `--critf 1e-7` confirms exact source ion-stage selection (`mml=3`, `mmu=8`) and full pre-matrix readiness. The six remaining v0.4.24 failures are the expected all-element summary quantities compared against an oxygen-only calculation; v0.4.25 marks those quantities as out of scope and evaluates the oxygen ion/level arrays directly.

## v0.4.24 - 2026-05-18

v0.4.24 completes the missing pre-matrix half of the fixed-state `calc_hmc_all` source port.

### Added

- `xstar_atomic.source_port.ion_balance` with source-faithful `calc_ion_rates`, `ioneqm`, `istruc`, and `mml/mmu` selection.
- Separate preliminary `pirt/rrrt` and post-solve population-weighted `stotg/atotg` products.
- Source-derived ion-stage selection as the default fixed-state path, with an explicit-range regression override.
- A bounded `calc_hmc_all` XSTAR probe generator and pre-continuum parity comparator.
- `examples/106_prepare_xstar_calc_hmc_all_probe.py`.
- Per-record `calc_ion_rates` diagnostics and preliminary ion-fraction columns in example 105 products.

### Corrected

- Global LTE level populations now use the one-based `rnise` compact index rather than a one-row-shifted zero-based lookup.
- `pirt/rrrt` no longer incorrectly duplicate `msolvelucy` `stot/atot` flow totals.

## v0.4.23 - 2026-05-18

v0.4.23 begins Milestone 4 after the frozen oxygen Milestone-3 benchmark. It closes the source-obvious type-49 destination bug, prepares an exact source-routine driver for `xstarcalc`, and adds the fixed-temperature/fixed-electron-fraction core of `calc_hmc_all`.

Implemented source-shaped behavior includes:

- literal `lcdd` entry density mutations;
- abundance-filtered element requests;
- one complete element solve per supplied element;
- abundance-weighted `htt`, `cll`, `htt2`, and `cll2` accumulation;
- ion fractions, photoionization rates, and recombination rates;
- global role-keyed level populations, LTE populations, and departure coefficients;
- `gammag`, `alphag`, fractional rate categories, and dominant-record indices;
- `stotg`, `atotg`, `fstotg`, `fatotg`, and `xtotg` diagnostics;
- source charge accounting and `elcter=xee-enelec`;
- source heating/cooling residual `hmctot=2*(httot-cltot)/(1e-37+httot+cltot)`;
- explicit readiness flags for element-loop, charge-scope, continuum, and complete fixed-state parity.

## v0.4.22 - 2026-05-18

- Close XSTAR data type 56 / rate type 3 for the solve-call-219 oxygen benchmark by reproducing `hunt3.f90` edge-interval extrapolation instead of flat-clamping temperatures outside the tabulated collision-strength grid.
- Preserve the source `max(1e-48, ...)` interpolation operands and final `cijpp=max(0,cijpp)` gate, yielding exact zero rates for O VIII records 22861--22863 at the captured temperature.
- Add focused tests for below-grid, in-grid, above-grid, descending-grid, and single-point type-56 records plus full `SourceFaithfulUCalc` zero-channel behavior.
- Regenerate the XSTAR source inventory and translation ledger. Milestones 1--3 are recorded as completed for their validated scope; Milestone 4 and `calc_hmc_all -> dsec -> calc_emis_all -> xstarcalc` are the next coherent target.
- Freeze the accepted 607-row oxygen O III--O VIII Milestone-3 benchmark, including hash-locked v0.4.21 assembly, population-parity, and matrix-family products, and bundle it as package data.
- No empirical rate scale, probe-derived coefficient, or captured population is inserted into the native operator.

## v0.4.21 - 2026-05-18

v0.4.21 reproduces the label-53 base-threshold gate that occurs before XSTAR applies an excited-parent correction.

- The v0.4.20 solve retains population parity but has 180 failing type-53 terms from 45 O IV records.
- Every affected XSTAR record has exact zero forward and reverse rates, while Python emitted finite values.
- XSTAR evaluates `ett=rlev(4,idest1)-rlev(1,idest1)` and exits when `ett<=0` before adding the excited-parent energy.
- Python previously clamped the base threshold to zero and then added the parent excitation, incorrectly reviving high or autoionizing levels.
- The production branch now keeps the raw base threshold, returns an evaluated all-zero result with the original endpoints when it is nonpositive, and applies the parent correction only after the gate passes.
- Adds provenance and a regression where the parent correction would otherwise make the final threshold positive.

No empirical scale or probe coefficient is used. Existing solve-call-219 probes can be reused.

## v0.4.20 - 2026-05-18

v0.4.20 aligns the source-port continuum integrators with the current XSTAR `constants.f90` values after v0.4.19 passed the complete 607-row population-parity gate.

- The v0.4.19 native-final population vector agrees with XSTAR at L1 `1.9974981259622204e-05`; all 607 rows pass the configured 0.5% gate.
- Type 99/rate 7 remains the leading matched-topology matrix-rate discrepancy: all 28 endpoints match, reverse rates agree near `1e-6`, but most forward rates are high by `4.1e-5`--`7.8e-5`.
- Current XSTAR `phintfo/phint53/phint53hunt` compute `bktm=bk*tm/ergsev` from `bk=1.380649e-16` and `ergsev=1.602176634e-12`, giving `0.8617333262145178*T4` eV.
- Python still used the historical rounded `0.861707*T4` continuum coefficient, lowering the Milne integral and raising the rescaled type-99 forward rate with exactly the observed sign.
- Adds explicit current-source Boltzmann and eV/erg constants for continuum integration and uses them in `phintfo`, `phint53hunt`, and type-99 energy bookkeeping. Historical formulas that literally contain `0.861707` remain unchanged.
- Adds regression coverage for the exact source-derived `bktm` and energy conversion.

No empirical scale, probe rate, or captured population is inserted. Existing solve-call-219 probes can be reused.

## v0.4.19 - 2026-05-18

v0.4.19 corrects the packed excited-parent endpoint for XSTAR `ucalc.f90` label 53 after the exact solve-call-219 oxygen run moved the leading mismatch to type 53/rate 7.

- The v0.4.18 family comparison contains 733 type-53 records and 2,932 terms on each side, but only 826 matched terms; 2,106 terms were Python-only and 2,106 were XSTAR-only.
- 702 records used the wrong parent destination. O III--O VII were collapsed to one unrelated row per ion block, while all 31 O VIII continuum records were already topologically correct.
- XSTAR uses `idest1=idat(np1i+nidt-2)` and `idest2=nlevp+idat(np1i-1+nidt-3)-1`. In a zero-based packed tuple, the bound level is `[-2]` and the parent-level offset is `[-4]`.
- The previous source-port branch used `[-3]`, which is the linked parent-ion/element field. This changed both matrix topology and the excited-parent threshold/statistical weight supplied to `phint53`.
- The production dispatcher now uses `integers[-4]`, computes `idest2=nlevp+offset-1` literally, and records the packed indices and source expression in provenance.
- Adds a realistic regression where `[-4]` and `[-3]` deliberately differ.

The `phint53` kernel, live radiation arrays, density semantics, and matrix insertion rules are unchanged. No empirical rate scale or probe coefficient is used. Existing solve-call-219 probes can be reused.

## v0.4.18 - 2026-05-18

v0.4.18 fixes the source-energy handoff for XSTAR `ucalc.f90` label 57 after the exact solve-call-219 oxygen run moved the first failing family to type 57/rate 5.

- The v0.4.17 run confirmed type 63/rate 3 is resolved: all 2,120 terms match topologically and the family passes the matrix-parity gate.
- Type 57 contains 1,156 matched-topology terms from 289 records, with 738 terms outside tolerance. Many XSTAR records are exactly zero while Python produced finite rates; the remaining active XSTAR records were often underestimated by orders of magnitude.
- XSTAR sets `e1=rlev(1,idest1)`, `eth=max(0,rlev(1,nlevp)-rlev(1,idest1))`, and then deliberately calls `calt57(...,e=e1,ep=eth,...)`.
- The production Python branch instead passed the parent level's absolute continuum energy as `ep`. That bypassed the source `ep < e` zero gate and changed the effective `rio=(ep-e)/13.6`, `rc`, `rno`, `irc`, and detailed-balance coefficients for every active record.
- The source-port dispatcher now passes `ep=eth`, preserves `idest2=nlevp`, and applies the literal pre-kernel gates `i57>0`, `idest1>1`, `idest1<=nlevp`, and `eth>0`.
- Ground-level type-57 records remain exact zero-rate source exits, matching the `ucalc` guard before `calt57`.
- Adds provenance for `e1`, `eth`, `ep`, and the literal `e1_rlev1_ep_eth` convention plus a regression that prevents absolute-continuum fallback.

No type-57 scale, probe coefficient, or population is inserted into the native operator. Existing solve-call-219 XSTAR probes can be reused.

## v0.4.17 - 2026-05-18

v0.4.17 fixes the remaining type-63/rate-3 same-`n` record-order bug that v0.4.16 exposed but did not fully correct.

- The v0.4.16 production rerun still had the identical 36 failing terms because `evaluate_collision_row()` called the same-`n` evaluator with energy-ordered `n_lower/l_lower` and `n_upper/l_upper`.
- Record-order statistical weights were supplied at the same time, so the `lf < li`/`lf > li` branch was selected from one orientation while the detailed-balance ratio came from another.
- The same-`n` evaluator now receives `type63_initial_n/l` and `type63_final_n/l`, exactly matching `ucalc.f90`'s packed `idest1/idest2` quantum states.
- Native `ans1/ans2` remain in record order for matrix insertion. The public collision-table excitation/de-excitation view is derived afterward from the two endpoint energies.
- Adds a regression matching the real O VII failure pattern: packed initial `l=0,g=1` is higher in energy than packed final `l=1,g=3`; XSTAR returns `ans1=3*cn`, `ans2=cn`.
- Does not change `anl1`, `amcrs`, `velimp`, density scaling, or any other rate family.

## v0.4.16 - 2026-05-18

v0.4.16 fixes the remaining type-63/rate-3 matrix-channel mismatch in the same-`n` `amcrs/velimp` branch.

- Preserves packed `idest1 -> idest2` direction for same-`n` type-63 records.
- Exposes native `ans1`/`ans2` before the generic collision-table energy ordering.
- Uses the record-initial and record-final statistical weights exactly as `ucalc.f90` does.
- Adds a direct regression for a descending-endpoint same-`n` O VII-style record.
- Does not change `anl1`, `amcrs`, `velimp`, density scaling, or any other collision family.

## v0.4.15 - 2026-05-18

v0.4.15 corrects the matrix-facing channel convention for XSTAR `ucalc.f90` label 63 after the exact solve-call-219 oxygen run ranked type 63/rate 3 as the first failing record family.

- The v0.4.14 family comparison contained 2,120 type-63 matrix terms with all endpoints matched, but 36 terms from nine O VII records failed. Every failing record stored `idest1` above `idest2` in the packed ATDB record.
- The Bautista `anl1`/`erc` kernel was already correct to the existing numerical precision. The error occurred afterward: the source-port adapter converted the literal record-order `ans1/ans2` pair into energy-ordered excitation/de-excitation rates and also reordered the endpoints before matrix insertion.
- XSTAR preserves `idest1=idat(nidt-4)`, `idest2=idat(nidt-3)` and inserts `ans1` for the forward `idest1 -> idest2` channel and `ans2` for the reverse channel, including records whose endpoints descend in energy or level index.
- The production adapter now consumes `type63_ucalc_ans1_forward_cm3_s` and `type63_ucalc_ans2_reverse_cm3_s` directly, multiplies each by the live electron density, and preserves the packed endpoint direction.
- Source-zero nondipole records and the existing same-`n` l-mixing path retain their prior behavior.
- Adds a regression using a descending packed type-63 record and records `type63_matrix_channel_convention=literal_ucalc_record_order` in provenance.

No collision coefficient is fitted or read back from the XSTAR probes. Existing solve-call-219 population, state, `ucalc`, and matrix probes can be reused.

## v0.4.14 - 2026-05-18

v0.4.14 completes the literal `phint53hunt.f90` grid-control translation for type 99 after v0.4.13 restored the correct compact endpoints but left the native forward rates 1.5--2.4% high for most active ion stages.

- Adds a direct translation of `huntf.f90`/`nbinc.f90` for the type-99 live-radiation path. XSTAR returns a one-based nearest logarithmic-grid index over the guard-tail-truncated continuum, not a NumPy lower bracket.
- Preserves the asymmetric source use of that result: `nb1=nbinc(eth)+1`, whereas `nphint=nbinc(emaxx)`.
- Reproduces the literal power-of-two `ndelt` selection and one-based `kl` loop. The previous Python integration forcibly appended `nphint` to every quadrature pass; Fortran stops at the last naturally reached `kl=kl+nskp` value.
- Retains `luse`, `ansar1`, and `ansar2` across successive refinement passes exactly as the source does.
- Adds provenance for the source `nbinc`, `nb1`, `nphint`, final stride, and whether the last pass naturally included the endpoint.
- Adds focused tests for nearest-log-grid `nbinc` behavior and the non-forced `nphint` endpoint.

No empirical type-99 scale is applied. The v0.4.13 run already showed exact endpoints and reverse rates at about one-part-per-million; v0.4.14 changes only the native forward integration control flow. Existing solve-call-219 XSTAR probes can be reused.

## v0.4.13 - 2026-05-17

v0.4.13 corrects the source mapping and density handoff for `ucalc.f90` label 99 after the exact solve-call-219 oxygen run ranked type 99/rate 7 as the next matrix-parity blocker.

- Corrects the packed type-99 parent-level offset from integer field `[-3]` to `[-4]`, matching `idest2=nlev+idat(np1i-1+nidt-3)-1`. The old field is the linked parent-ion/element identity and moved type-99 gain/loss partners into unrelated excited-parent compact rows.
- Restores the shared continuum/next-ion-ground endpoint for the production O III--O VII type-99 records. The affected Python rows 110, 273, 326, 369, and 598 now map to the source rows 79, 241, 293, 335, and 575 when the packed parent-level offset is one.
- Separates the two source density semantics in the type-99 path: `calt99.f90` interpolates its recombination table at `den=xpx`, while `phint53hunt.f90` and the final `rec*xnx` normalization use `xnx=xpx*xee`.
- Reproduces `calt99.f90`'s one-based density-bracket behavior, including first-branch handling below the grid and the source fallback above the maximum.
- Adds explicit provenance for the packed endpoint field and the `xpx` versus `xpx*xee` density roles.
- Adds focused tests using the realistic 11-integer linked type-70/type-99 tail and a non-unity electron fraction.

No XSTAR probe rate or population is inserted into the production operator. Existing solve-call-219 population, state, `ucalc`, and matrix probes can be reused.

## v0.4.12 - 2026-05-17

v0.4.12 fixes the exact-state type-74 assembly blockers and the dominant type-95/rate-5 matrix-rate error exposed by the v0.4.11 oxygen run.

- Translates `ucalc.f90` label 74 and `calt74.f90` directly against the live `epi/bremsa` radiation arrays. The forward delta-resonance photoionization rate is evaluated by source-compatible linear interpolation and the literal `4.752e-22` conversion.
- Accepts a zero type-74 DR coefficient as a valid source result. At solve call 219 all 42 blocked records had `alpha=0` because the source Boltzmann cutoff skipped their resonances, while their live-radiation forward rates remained nonzero.
- Corrects type-74 endpoint semantics to `idest1=idat(nidt-1)`, `idest2=nlevp`, `idest3=idat(nidt)`, and `idest4=idest3+1`.
- Applies only the source `g_lower/g_continuum` factor to the type-74 reverse coefficient; label 74 does not multiply `ans1` or `ans2` by density.
- Corrects type-95 Bryans collisional-ionization evaluation. XSTAR label 95 calls `eint`, whose first result is the ordinary `E1(x)` integral; the previous Python branch incorrectly used the scaled `expint` quantity `x exp(x) E1(x)` directly.
- Reproduces the literal one-based type-95 spline bracket and storage offsets instead of NumPy endpoint-clamping interpolation.
- Adds focused source-port tests for zero-alpha/nonzero-forward type-74 records and the type-95 `eint` distinction.

No probe rate is inserted into the production operator. Existing solve-call-219 population, state, `ucalc`, and matrix probes can be reused for the next oxygen parity run.

## v0.4.11 - 2026-05-17

v0.4.11 fixes the parity CLI regression exposed when the exact solve-call-219 runtime state makes strict element assembly incomplete.

- Population parity is now conditional on an actually executed native element solve. Supplying a population probe no longer raises `population parity requires an executed element solve` before ordinary assembly products can be written.
- Lucy state parity is likewise deferred when population parity is unavailable because strict assembly did not execute.
- The complete element matrix parity gate still runs on the exact-state partial assembly, so existing `ucalc` and `calc_hmc_ion` probes can identify the source family responsible for missing native terms.
- Adds grouped strict-assembly blocker products: `xstar_element_assembly_blocker_summary.csv`, `.json`, and `.md`.
- Records explicit `population_parity_status` and `msolvelucy_state_parity_status` values in the runtime-context summary and console output.
- Preserves strict scientific behavior: no blocked record is silently dropped into a parity-accepted solve, and no probe coefficient is inserted into the native operator.

The same v0.4.10 command can be rerun unchanged. If the exact captured runtime exposes source-translation blockers, the command now completes its diagnostics, writes the partial matrix and grouped blocker inventory, and exits nonzero only through the normal incomplete-solve acceptance status rather than an early exception.

## v0.4.10 - 2026-05-17

v0.4.10 prevents a captured-zone runtime mismatch from being misdiagnosed as a source-rate-family failure during the oxygen population-parity gate.

- Reads `t_xstar_1e4K`, `xpx`, `xee`, and `cfrac` from the selected paired population-probe solve before any native `ucalc` or matrix assembly work.
- Adds `--population-probe-runtime-policy use|check|ignore`. The default `use` policy evaluates the full native element matrix at the exact XSTAR solve-call state; `check` requires explicit CLI values to match; `ignore` preserves the old controlled-mismatch behavior.
- Reports requested and effective temperature, hydrogen density, electron fraction, electron density, and covering fraction in the console and in `xstar_element_runtime_context.json/.md`.
- Validates that the selected probe `ipmat2` matches the native compact basis before parity products are accepted.
- Exposes `XSTARRuntimeContextReference` and `load_xstar_runtime_context_reference` through the public API.
- Leaves probe coefficients comparison-only; no XSTAR rate or population is inserted into the native matrix.

The v0.4.9 oxygen run used `T=1e6 K` and `xee=1`, while solve call 219 was captured at `T=7.6655185577588316e4 K`, `xpx=1e8 cm^-3`, and `xee=1.2046560563936872`. This explains the simultaneous disagreement in density/temperature-sensitive type 51, 57, 63, 68, 69, 71, 77, and 99 families.

## v0.4.9 - 2026-05-17

v0.4.9 turns the first true oxygen `msolvelucy` divergence into a record-level source-port gate instead of another broad diagnostic cycle.

- Fixes the state-parity comparator so it reports the first failed scalar in actual `msolvelucy` execution order. Component summaries still aggregate all outer iterations, but a downstream outer-iteration start can no longer hide an earlier condensed-matrix failure.
- Confirms from the v0.4.8 products that outer-iteration-1 level populations and `rr` fractions match XSTAR exactly; the first genuine mismatch is the raw 13x13 condensed matrix (`L1=7.282738055010392e4`, maximum absolute entry difference `3.6399039672513376e4`).
- Adds optional complete record-level parity against the existing instrumented `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`. The comparison joins latest-per-record XSTAR captures to every native `MatrixTerm`, reports unmatched terms and `aj1/aj2` differences by data/rate family, and identifies the dominant first failing family. Probe coefficients are never inserted into the production solve.
- Corrects `ucalc.f90` label 76 two-photon semantics. After the source's final channel swap, the matrix-facing rates are `ans1=0`, `ans2=A`; line escape factors do not attenuate the two-photon population decay. The energy channels are `ans3=-A*DeltaE*ergsev`, `ans4=0`.
- Adds `--xstar-ucalc-probe-csv`, `--xstar-matrix-probe-csv`, matrix-parity tolerances, and `--require-full-element-matrix-parity` to example 102 and the element CLI.
- Extends JSON, Markdown, and console summaries with the exact first failing comparison key and outer/fixed iteration.
- Keeps the full 607-row Python solve unchanged unless the label-76 correction affects an active record. No empirical scale or probe-backed coefficient is introduced.

The intended next run reuses the existing solve-call-219 population/state probes and adds the historical `ucalc` and `calc_hmc_ion` probes. Its family summary should identify the source routine responsible for the residual condensed-matrix mismatch.

## v0.4.8 - 2026-05-17

v0.4.8 corrects the first source-level mismatch exposed by the v0.4.7 oxygen population and `msolvelucy` state comparison.

- Fixes `ucalc.f90` label-86 packed endpoint decoding: Python now uses integer fields `[-4]` and `[-5]`, matching the Fortran expressions `np1i-1+nidt-3` and `np1i-1+nidt-4`. The previous one-field shift placed very large Auger rates in incorrect compact superlevels.
- Preserves the supplied population-vector scale at `msolvelucy` entry, matching the source before its first fixed-point normalization.
- Compares XSTAR probe `nion` against physical ion stage rather than the internal compact block ordinal, with shared aliases assigned to the next-ion ground stage exactly as XSTAR overwrites them.
- Replaces the generated `msolvelucy` instrumentation with the safe target-filtered helper using independent call counting, `newunit=` file units, the true `ndss` matrix leading dimension, and post-condensed capture outside the level loop.
- Adds focused regression tests for type-86 decoding, unnormalized Lucy entry state, and physical ion-stage alias semantics.

## v0.4.7 - 2026-05-17

v0.4.7 adds the Milestone-3 scientific acceptance gate after the v0.4.6 full 607-row oxygen solve reached strict assembly and Lucy convergence.

- Adds paired XSTAR population-probe loading for one complete `before_msolvelucy`/`after_msolvelucy` solve call, with explicit element, compact-dimension, solve-call, and occurrence selection.
- Compares the Python LTE seed to XSTAR's pre-solve vector and the native Python final vector to XSTAR's post-solve vector using scale-aware row, L1, L2, total-variation, ion, and superlevel products.
- Repeats the same assembled Python solve from XSTAR's captured pre-`msolvelucy` vector. This controlled alternate-seed solve distinguishes initial-state errors from matrix/runtime-context errors without inserting XSTAR coefficients or populations into the production path.
- Adds iteration-level Python `msolvelucy` tracing for outer populations, superlevel populations, `rr`, the condensed `ajissup` matrix, and every fixed-point `riu/rui/ril/rli` update.
- Adds one-time Fortran state-probe generation in example 104 and a direct XSTAR/Python state comparator that identifies the first failing component of the Lucy algorithm.
- Adds explicit `xstar_population_parity_ready` and `msolvelucy_state_parity_ready` gates. A converged direct solve is no longer described as population validated until these gates pass.
- Replaces the misleading single row-residual diagnostic with active-scale maximum relative residual, L1-relative residual, zero-scale-row count, and a row-level residual CSV.
- Adds CLI options for population references, state-probe directories, trace output, parity tolerances, and strict parity-required exit statuses.
- Keeps the six-row and 119-row systems as regression subsets only; no fitted source, empirical rate scale, or probe-backed matrix term is introduced.

The next production run should use the existing paired population probe for solve call 219. If final parity fails, the XSTAR-before-seeded result and first failing Lucy state component determine whether the next source correction belongs to initialization, superlevel condensation, linear algebra, or fixed-point rate assembly.

## v0.4.6 - 2026-05-17

v0.4.6 closes the remaining strict-assembly blockers exposed by the production v0.4.5 O III--O VIII run. The run reduced blockers from 4,124 to 531; all 531 were source-control-flow interpretation issues rather than missing plasma or escape context.

- Reclassifies 243 type-63 records with `Delta-l != 1`, same-n non-dipole coupling, or zero record-order `aa1` as source-evaluated zero-rate records. `ucalc.f90` label 63 initializes `ans1/ans2` to zero and leaves them zero in these branches; Python no longer reports them as rejected collisions.
- Implements the `msolvelucy.f90` compact-index rule `min(ipmat, indb(...))`. The 288 O VII type-53/type-74 excited-parent endpoints that map to raw compact row 610 are now source-aliased to the final active row 607 instead of being rejected.
- Adds raw and clamped matrix endpoint provenance (`source_row_unclamped`, `source_column_unclamped`, `source_ipmat_clamped`) and the summary count `n_source_ipmat_endpoint_clamps`.
- Keeps genuinely invalid non-positive endpoints as errors; no basis extension, record deletion, fitted rate, or proxy matrix term is introduced.
- Adds focused tests for type-63 source-zero behavior and the exact O VII 610-to-607 `ipmat` alias.

No rate formula, optical-depth reconstruction, compact basis, or Lucy solver equation changed. A production rerun is required to verify `n_records_blocked=0`, `n_unmapped_matrix_endpoints=0`, and to evaluate actual 607-row solver convergence.

## v0.4.5 - 2026-05-17

v0.4.5 fixes the implementation blockers exposed by the first production 607-row O III--O VIII assembly. The compact basis and matrix topology were already correct; 4,124 records were blocked by record/context adapters rather than by the statistical-equilibrium solver.

- Corrects the type-50 packed REALS layout: wavelength is `rdat(1)` and the Einstein A value is `rdat(3)`. The oscillator strength is reconstructed from A, wavelength, and endpoint statistical weights using the exact `ucalc.f90` formula. When line pumping is active, `bremsa(nb1)` is selected directly from the live radiation grid.
- Supplies the complete element/ion/label/source-format schema required by the validated type-56/63/67/68/69/98 collision evaluators.
- Decodes type-53 cross-section pairs, threshold, current continuum statistical weight, and excited-parent destination context directly from the packed record and the element level tables. Predecoded diagnostic rows are no longer required by the production element path.
- Derives type-99 thresholds and statistical weights from the same level/parent context, evaluates `calt99`, and adds a live-grid translation of `find53/phint53hunt`, including adaptive grid refinement and source heating/cooling channel ordering.
- Adds sparse radial-detail reconstruction. `source_sparse_reconstruct` scans every `XSTAR_RADIAL` HDU through the selected zone, carries the most recent written optical depth forward, and assigns zero only to indices never written because `fstepr2/fstepr3` suppress rows below their source output thresholds. Reports distinguish exact live arrays from threshold-bounded reconstruction. `strict_selected_zone` preserves the previous NaN/blocking behavior.
- Adds `--escape-detail-policy` to the element CLI and `--detail-policy` to the escape-state CLI. The command-line default for XSTAR run directories is `source_sparse_reconstruct`; the Python API retains `strict_selected_zone` as its backward-compatible default.
- Adds focused runtime-context tests for type 50, collisions, direct packed type 53, live type 99, and sparse optical-depth history.

No empirical type-53 scale, fitted source term, or probe matrix coefficient is introduced. A production rerun is still required before claiming that all 7,360 oxygen records assemble and that the 607-row solve converges.

## v0.4.4 - 2026-05-17

- Fixes the element-equilibrium CLI example that referenced a non-existent placeholder `xstar_o7_escape_state.npz`. Missing NPZ paths now fail with an actionable message instead of a raw Python traceback.
- Adds source-faithful escape-state reconstruction from XSTAR radial detail products: `xo01_detal2.fits` supplies `tau0(1:2,line)` indexed by global line index, and `xo01_detal3.fits` supplies `tauc(1:2,rrc)` indexed by global RRC/continuum index. `xo01_detal4.fits` is not used for this purpose because it stores the continuum energy-grid state.
- Adds `xstar_atomic.source_port.escape_state`, `xstar-atomic-port-escape`, and `examples/103_build_xstar_escape_state.py`. The builder maps detail rows onto the exact v0.4.1 `nplini`/`npconi2` array lengths, preserves missing entries as NaN in strict mode, writes a reusable NPZ, and emits coverage/provenance reports.
- Extends `xstar-atomic-port-element` with `--xstar-run-dir`, `--escape-zone`, and `--write-derived-escape-npz`, mutually exclusive with `--escape-npz`.
- Changes `EscapeProbabilityContext` so non-finite array entries are treated as missing context rather than propagating NaNs into escape functions and the element matrix.
- Keeps `--assume-optically-thin` explicit and opt-in; missing detail rows are never silently converted to zero depth in strict source-equivalent mode.

## v0.4.3 - 2026-05-17

- Translates the complete element statistical-equilibrium source sequence `levwkelement -> calc_hmc_ion -> calc_hmc_element -> msolvelucy` as one coherent subsystem in `xstar_atomic.source_port.element_equilibrium`.
- Builds the exact one-based compact `ipmat/ipmat2` topology from the v0.4.1 element/ion/level pointers, including shared parent-continuum/next-ion-ground rows, source superlevel (`nsup`) and ion (`nion`) maps, and the final normalization row.  The production oxygen O III--O VIII level counts produce 607 compact rows and five shared aliases directly from the source rule `ipmat2 += nlev - 1`.
- Traverses every ion record through `npfi`, `npar`, and `npnxt`, calls the unified v0.4.2 `SourceFaithfulUCalc`, applies source escape probabilities, preserves the rate-type-1 excited-level photoionization suppression, and inserts all four `calc_hmc_ion` gain/loss terms plus heating/cooling coefficients.
- Adds explicit raw and normalization-constrained dense matrices, RHS, record/ion provenance, blocked-context records, endpoint failures, and source-no-op accounting.  Missing radiation, optical-depth, level, or pointer state is reported explicitly; no probe coefficient or empirical fallback is inserted.
- Translates `levwk.f90` and the element LTE seed chaining in `levwkelement.f90`.
- Adds `xstar_atomic.source_port.linear_algebra`, translating `ludcmp`, `lubksb`, `mprove`, and `leqt2f`, including source range handling and explicit singular-matrix errors.
- Translates the Lucy superlevel condensation, normalized superlevel solve, within-superlevel fixed-point iteration, population normalization/positivity diagnostics, row residuals, heating/cooling accumulation, level in/out-rate diagnostics, and ionization/recombination totals from `msolvelucy.f90`.
- Adds `xstar-atomic-port-element` and `examples/102_port_xstar_element_equilibrium.py`, writing the complete compact basis, source-level matrix terms, normalized matrix/RHS, populations, ion summaries, blockers, solver diagnostics, JSON, and Markdown products.
- Registers the translated `ELEMENT_POPULATIONS` stage on the whole-program source driver and updates the machine-readable port ledger for `levwk`, `levwkelement`, `calc_hmc_ion`, `calc_hmc_element`, `msolvelucy`, and the linear-algebra helpers.
- The six-row and 119-row products are retained only as regression subsets.  The principal acceptance output is the complete element matrix and population vector; the default oxygen target is O III--O VIII with 607 rows.
- The code path is complete, but a source-equivalent production 607-row numerical acceptance run still requires the matching XSTAR plasma, live-radiation, line/RRC optical-depth, and ion-stage context.  The subsystem refuses strict readiness when any required context is missing.

## v0.4.2 - 2026-05-17

- Completes the source-faithful Python control-flow translation of `xstarlib/src/ucalc.f90` for all computed-GOTO labels 1 through 102.
- Adds `xstar_atomic.source_port.ucalc` with packed `UCalcRecord` decoding, typed `UCalcContext`, `UCalcResult` (`ans1..ans6`, `idest1..idest4`, opacity, status, diagnostics, and source provenance), strict/non-strict execution, and index-only endpoint mode.
- Registers 75 native physical branches and 27 source-defined metadata/no-op branches. No physical label is unregistered and no proxy fallback is used. Missing level, density, pointer, or radiation state is returned explicitly as `blocked_missing_context`.
- Adds source translations of shared leaf routines in `xstar_atomic.source_port.ucalc_leaves`, including `expo`, `exintn`, spline interpolation, `phextrap`, `bkhsgo`, `milne`, `gull1`, `hphotx`, `pexs`, `calt70`, Sampson/Kato collision helpers, and APED Maxwellian-rate interpolation.
- Incorporates the previously validated type-50, type-51, type-53, and type-71 implementations into the unified dispatcher and fixes the generic collision adapter to consume the validated excitation/de-excitation coefficient keys.
- Preserves source ordering for labels that jump directly to `9000`, including disabled types 84, 93, and 94; these return source no-op results before index-only handling.
- Adds `xstar_atomic.source_port.ucalc_inventory`, `xstar-atomic-port-ucalc`, and `examples/101_port_xstar_ucalc.py`. The command inventories production ATDB data types, writes the complete branch catalog, and performs one packed-record/index-only execution per active data type without copying the large REALS vector.
- Updates the source-port ledger: the `ucalc` subsystem is translated, while numerical parity remains explicitly branch-specific. The unresolved real-context type-53 case remains a regression benchmark rather than an empirical correction.
- Does not yet translate `levwkelement`, `calc_hmc_ion`, `calc_hmc_element`, or `msolvelucy`; these form the next coherent subsystem.
- Validation: 334 tests passed and 22 data-dependent tests skipped; compileall, source/wheel builds, isolated wheel installation/import, CLI checks, archive content checks, and checksums passed.

## v0.4.1 - 2026-05-16

- Translated the runtime atomic-database initialization subsystem from `readtbl.f90` and the active path of `setptrs.f90`.
- Added memory-mapped one-based packed-vector views for POINTERS, REALS, INTEGERS, and CHARS, with full record-span validation.
- Added source-ordered construction of `npar`, `npnxt`, `npfirst`, `npfi`, `nplin`/`nplini`, `npcon`/`npconi`/`npconi2`, `npilev`/`npilevi`, `nlevs`, and explicit element/ion/global-level maps.
- Added runtime-relevant `dbwk2` pointer rebuild and non-mutating report operations; interactive database editing modes remain intentionally unported because normal XSTAR setup does not call them.
- Added a fingerprinted compressed derived-pointer cache, reusable CSV/JSON/Markdown products, driver-stage registration, the `xstar-atomic-port-atdb` command, and example 100.
- Added focused packed-FITS, pointer-invariant, cache, driver, malformed-input, CLI, and public-API tests.
- The next source-port milestone is the complete `ucalc.f90` dispatcher and all called rate routines.

## v0.4.0 - 2026-05-16

- Pivoted the primary roadmap to a systematic source-faithful Python translation
  of the original XSTAR call graph.
- Added one-based Fortran array/intrinsic compatibility helpers.
- Added typed atomic, plasma, radiation, matrix, thermal, transfer, and top-level
  Python XSTAR state containers.
- Added source-tree/tarball inventory, routine extraction, call-edge output, and
  stage classification.
- Added a machine-readable translation ledger with conservative validation
  status.
- Added an original-stage Python driver that fails explicitly at the first
  untranslated routine.
- Added a unified `ucalc` branch registry for currently translated types 50, 51,
  53, and 71.
- Added example 99, source-port documentation, focused tests, and generated
  source inventory products.
- Retained existing probes and parity audits as regression oracles rather than
  the main implementation path.

## v0.3.209 - 2026-05-16

- Corrected the exact-live type-53 ATDB decoder to derive XSTAR's active ion-local continuum index `nlevp` from the direct probed endpoint relation `idest2 = nlevp + idat(nidt-3) - 1`.
- v0.3.208 incorrectly used the maximum extracted type-13 level index. In the real O VII products this selected level 110 instead of XSTAR `nlevp=79`, assigned a false 57.919 eV parent excitation to ground-parent records, and corrupted the continuum weight, threshold, Milne exponent, endpoint validation, and all type-53 rate/matrix comparisons.
- Added explicit decoder provenance and readiness fields: inferred `xstar_nlevp`, ATDB maximum level index, packed parent offset, inference source/consistency, continuum-row availability, endpoint consistency, and aggregate fallback/error counts.
- The parity gate now requires both live-radiation context readiness and exact ion-block/continuum decoder readiness. It does not fall back silently to the ATDB maximum when a direct endpoint-derived `nlevp` is available.
- Added focused regression tests for ground-parent and excited-parent endpoint inference and for rejection of inconsistent decoder context. No `phint53` numerical formula, empirical scale, or production solver behavior changed.

## v0.3.208 - 2026-05-16

- Added exact live-radiation type-53 state, `phint53`/`ucalc` evaluator, record/matrix parity gate, and selected-system integration gate.
- Added examples 97 and 98, focused tests, and independent standalone-Fortran numerical verification.
- Preserved the current-ion continuum statistical weight in `rnist` for excited-parent type-53 records.
- Added explicit live-state provenance checks and separate readiness for rate, heating/cooling, compact matrix, external RHS, and opacity/RRC channels.
- No empirical approximately-44 scale and no production-solver behavior change.

## v0.3.207 - 2026-05-16

- Corrected the type-71 endpoint-order validator in `xstar_type50_type71_native_parity.py`. XSTAR `ucalc.f90` type 71 returns the packed ATDB order `idest1=lower spectroscopic destination`, `idest2=upper superlevel source`; `calc_hmc_ion.f90` later derives `llo/lup` from level energies. The v0.3.206 audit incorrectly reused the type-50 convention `idest1=upper`, `idest2=lower`.
- The user-provided O VII v0.3.206 products showed that all three type-71 native rates and all nine native matrix coefficients already matched XSTAR exactly. Only `endpoint_order_match=False` blocked record and matrix readiness.
- Added family-neutral endpoint provenance columns `xstar_idest1`, `xstar_idest2`, `xstar_idest1_role`, `xstar_idest2_role`, and `endpoint_order_convention`. The legacy `xstar_idest1_upper` and `xstar_idest2_lower` columns are now populated only for type 50.
- Added a regression test using the real source convention and a negative test proving that reversed type-71 endpoints fail parity.
- No native rate formula, compact coefficient, production solver behavior, or type-53 treatment changed. After rerunning examples 95 and 96, the expected next milestone is native type-50/type-71 selected-system integration readiness, followed by exact live-radiation type 53.

## v0.3.206 - 2026-05-16

- Added `xstar_atomic.rates_type71`, a FITS-independent source-code translation of the XSTAR `calt71.f90` and `ucalc.f90` data-type 71 branches. It supports the single-point and log-density/log-temperature grid forms, XSTAR boundary conventions, the source-equivalent `calt71` density argument `den=xpx`, and the final `ans1=0`, `ans2=A*(ptmp1+ptmp2)` convention.
- Extended `xstar_atomic.rates_type50` with `evaluate_type50_ucalc_record`, which evaluates escaped radiative decay from decoded ATDB `A`, `ptmp1`, and `ptmp2`, including the source floor `max(A*(ptmp1+ptmp2),1e-20*xpx)`, and evaluates post-swap photoexcitation only from an explicit same-capture `bremsa(nb1)` radiation value. Full covering and the XSTAR high-wavelength sentinel are handled as exact zero-pumping branches; no proxy continuum is accepted.
- Added `xstar_atomic.xstar_type50_type71_native_parity` and `examples/95_audit_xstar_type50_type71_native_parity.py`. The audit decodes all selected type-50/type-71 records, compares native `ans1`/`ans2` with the XSTAR `ucalc` probes, reconstructs every compact insertion touching a selected endpoint, and separates selected-internal, fixed-external, and external-row-out-of-scope terms.
- Added `xstar_atomic.xstar_priority_native_type50_type71_integration` and `examples/96_integrate_xstar_priority_native_type50_type71.py`. The integration gate starts from the validated v0.3.205 native-type-51 term table, replaces every validated selected-row type-50/type-71 coefficient, recomputes `A_SS`, `-A_SE x_E`, row balance, conditioning, and the fixed-external conditional solution, and preserves all remaining families as explicit probe-backed terms.
- Type-50/type-71 readiness requires record parity, compact-term parity, complete one-to-one selected-row replacement, zero accidental use of external-row terms, full fixed-external RHS coverage for both families, a full-rank nonnegative solve, captured-row balance, population agreement, and negligible movement relative to the parent native-type-51 solution.
- The production expanded compact-basis solver remains unchanged. Complete native compact closure remains false until exact live-radiation type 53 and the remaining minor families are integrated. The approximately 44 type-53 discrepancy remains unresolved and no empirical correction is applied.

## v0.3.205 - 2026-05-16

- Corrected the v0.3.204 native type-51 integration readiness scope. The six-row conditional audit is defined by matrix terms whose compact **row** is selected; it must not require reciprocal terms that belong to external-row equations.
- The real O VII parity manifest contains 946 type-51 insertions touching a selected endpoint. Exactly 636 have selected matrix rows and enter the six selected equations; the remaining 310 are reciprocal off-diagonal insertions in external matrix rows with selected columns.
- Added explicit parity-scope accounting: `n_type51_parity_terms_in_selected_row_scope`, `n_type51_parity_terms_external_row_out_of_scope`, `n_type51_parity_terms_unused_in_selected_row_scope`, `n_type51_parity_terms_used_outside_selected_row_scope`, and `native_type51_all_parity_manifest_terms_accounted_for`.
- Added `xstar_priority_native_type51_integration_audit_parity_scope.csv`, which classifies every parity term as `selected_row_scope_used`, `selected_row_scope_unused`, `external_row_out_of_scope`, or the defensive error state `external_row_out_of_scope_but_used`.
- The selected-system readiness gate now requires complete one-to-one replacement of all selected-row type-51 terms, zero unused selected-row parity terms, zero accidental use of external-row terms, complete accounting of the full parity manifest, full row coverage, preserved row balance, a full-rank nonnegative solve, and negligible movement from the all-probe solution.
- Revalidated the user-provided O VII products: 636/636 selected-row type-51 terms are replaced, zero are unmatched, zero selected-row parity terms are unused, all 310 remaining parity terms are correctly classified as external-row out of scope, and `native_type51_selected_system_integration_ready=True`.
- The corrected real audit preserves the v0.3.204 numerical solution: maximum hybrid/captured population difference `3.0341181e-3`, maximum hybrid/all-probe population change `2.7517811e-8`, maximum captured row residual `1.7471003e-3`, full rank 6/6, no negative populations, and linear residual below `3e-16`.
- Complete native compact closure remains false because 1,950 non-type-51 terms are still probe-backed. The next target remains native type-50 and type-71 external RHS closure, followed by exact live-radiation type 53 without an empirical approximately 44 factor.

## v0.3.204 - 2026-05-16

- Added `xstar_atomic.xstar_priority_native_type51_integration` and `examples/94_integrate_xstar_priority_native_type51.py`.
- The new controlled integration audit consumes the v0.3.199 priority matrix-balance products together with the validated v0.3.203 native type-51 parity products. It replaces every matching type-51 compact matrix term touching a selected row, including selected-selected internal terms and selected-external terms contributing to `-A_SE x_E`.
- Added exact capture-key matching with a unique structural fallback, one-use-only native-term accounting, duplicate-key detection, unused-parity-term detection, missing-population detection, and explicit failure when any type-51 insertion is unmatched.
- Reconstructs both the original all-probe system and the hybrid native-type-51/probe-other-family system, then compares aggregated compact entries, captured-population row residuals, external RHS values, matrix rank/conditioning, conditional populations, and linear residuals.
- Readiness requires complete replacement coverage, all selected rows touched by native type 51, a full-rank nonnegative hybrid solve, all selected rows within the population and row-balance tolerances, and negligible population movement relative to the all-probe reference.
- All non-type-51 families remain explicitly probe-backed, `native_priority_subset_matrix_closure_ready` remains false, and the production expanded compact-basis solver is unchanged. The next target is native type-50/type-71 external RHS closure, followed by exact live-radiation type 53 without an empirical approximately 44 factor.
- Removed the machine-specific root `datapath` file from the source/distribution manifest and added it to `.gitignore`. Runtime datapath creation remains supported, but release archives no longer embed a developer-local absolute ATDB path.
- Restored direct raw-record type-50 audit compatibility: rows carrying `data_type=50` and `rate_type=4` are recognized as radiative transitions even when the derived `kind="radiative_decay"` field is absent. This prevents valid explicit radiation-grid pumping audits from falling back to `not_type50_radiative_transition`.

## v0.3.203 - 2026-05-16

- Added `xstar_atomic.rates_type51`, a FITS-independent source-code translation of the XSTAR `ucalc.f90` data-type 51 branch, including the original five-point and general nine-point Burgess--Tully spline paths, the wavelength-dependent BT temperature floor, the ATDB transition-energy convention, detailed balance, and density-scaled `ans1`/`ans2`.
- Added `xstar_atomic.xstar_type51_native_parity` and `examples/93_audit_xstar_type51_native_parity.py`. The audit decodes the selected type-51 ATDB records, compares native excitation/de-excitation rates with the same XSTAR `ucalc` captures, reconstructs all touching compact `ajisi` terms, and aggregates the selected-selected internal compact entries.
- Corrected the interpretation of the legacy full-parity probe field named `xnx`: the instrumentation call passed `xee`, so the physical electron density for collisional rates is `n_e = xpx * xee`. The original CSV field is retained for compatibility and the audit records the corrected semantics explicitly.
- This is a parity/integration gate only. Native type-51 terms are not yet enabled in the production expanded compact-basis solver; type-50/type-71 external closure and the exact live-radiation type-53 implementation remain subsequent steps.

## v0.3.202 - 2026-05-16

- Added `xstar_atomic.xstar_priority_native_readiness` and `examples/92_audit_xstar_priority_native_readiness.py`.
- Consumes the validated v0.3.201 conditional-solve products and, when supplied, the v0.3.199 record-term table to separate selected-block couplings `A_SS` from the external closure term `-A_SE x_E`.
- Ranks each ATDB/XSTAR rate family by its absolute population-weighted influence, assigns a conservative native implementation status, and writes internal-family, external-RHS-family, row-dominance, and staged implementation-plan products.
- For the O VII six-row subsystem, type 51 supplies about 97.77% of the internal population-weighted coupling. Type 50 supplies about 99.06% of the external RHS, type 71 about 0.861%, and type 53 about 0.0795%; the top three external families account for about 99.99937%.
- Defines the minimum native port order as type 51 internal coupling, type 50 plus type 71 external closure, then exact live-radiation type 53. The approximately 44 type-53 discrepancy remains explicitly blocked on a source-equivalent `phint53` implementation and is not corrected empirically.
- Diagnostic/planning release only: no default rate formulas, compact matrix coefficients, RHS/normalization closure, or solver behavior changed.

## v0.3.201 - 2026-05-16

- Added `xstar_atomic.xstar_priority_conditional_solve` and `examples/91_audit_xstar_priority_conditional_solve.py`.
- Partitions the validated selected compact equations as `A_SS x_S + A_SE x_E = 0`, holds the 601 non-selected XSTAR compact populations fixed, and solves the six activated rows from `A_SS x_S = -A_SE x_E`.
- Writes selected matrix entries, external right-hand-side terms, rate-family RHS contributions, singular values, and row-by-row population comparisons.
- For the O VII priority rows `79,80,241,242,244,293`, the row-scaled 6x6 matrix is full rank with condition number about `5.8545`; all six conditional populations agree with the captured XSTAR values within the 0.5% tolerance, with a maximum relative difference of about `3.0341e-3`.
- This remains a probe-derived conditional solve. Native rate assembly, the 119-row active-basis solve, full RHS/normalization closure, and the type-53 approximately 44 scale correction remain future work.

## v0.3.199 - 2026-05-16

- Added `xstar_atomic.xstar_priority_matrix_balance` and `examples/90_audit_xstar_priority_matrix_balance.py`.
- Consumes a validated priority matrix-closure manifest and the captured XSTAR population-closure parity vector, aggregates record-level `ajisi(1,:)` insertions into compact `ipmat2` matrix entries, and evaluates the selected steady-state equations `A x` directly.
- Writes row-balance, rate-family contribution, aggregated compact-matrix entry, record-term, and population-vector products.
- For the O VII six-row priority subset (`79,80,241,242,244,293`), all six rows pass a 0.5% relative residual tolerance against the post-`msolvelucy` population vector; the maximum relative residual is about `1.7471e-3`.
- This is a consistency gate before native assembly. It does not alter the default Python matrix, RHS/normalization closure, native rate formulas, or enable the expanded-basis solve.

## v0.3.198 - 2026-05-16

- Fixed whole-run `latest-per-record` contamination in the priority-subset matrix-closure audit. Raw XSTAR probes contain records for every element, while the reconstructed compact block map describes only the selected element. The audit now filters selected `ucalc` captures to the reconstructed element `jkk_ion` blocks before loading and mapping matrix rows.
- Added `element_jkk_ions`, all-element/selected-element/excluded-record counts, and `element_probe_filter_mode` summary fields.
- Added `xstar_priority_matrix_closure_audit_element_filter_summary.csv` to document included and excluded `jkk_ion` blocks.
- The O VII v0.3.197 latest-per-record output contained 7,432 apparent unmapped endpoints, but all came from unrelated `jkk_ion=1,2,3`; the O-element block map is `jkk_ion=31--36`. These rows are now excluded before endpoint readiness is evaluated.
- Exact `calc_hmc_element` endpoint translation, shared parent-continuum aliases, and non-matrix `ucalc` metadata classification are unchanged. No native solver physics, rate formulas, RHS/normalization closure, or expanded-basis solve changed.

## v0.3.197 - 2026-05-15

- Corrected the priority-subset compact matrix endpoint mapping to follow the actual `calc_hmc_element.f90` assembly rule, `indbe = indbi + ipmat2`, rather than treating every `indbi` value as a level index inside the current ion block.
- Endpoints with `indbi > nlev` are now mapped into their intended adjacent-ion/superlevel compact rows instead of being reported as missing. This directly addresses all 75 false unmapped endpoints in the O VII v0.3.196 rank-73 audit.
- The audit now selects the requested occurrence for all probed ATDB records first, maps every selected Fortran matrix row, and only then filters records/terms touching the activated compact rows. This avoids preselection losses at cross-block endpoints.
- Added explicit classification of non-matrix `ucalc` metadata records. Records such as type-6/rate-13 rows with `idest2=0` intentionally produce no four-row `ajisi/indbi` insertion and no longer falsely fail matrix-manifest readiness.
- Added block-offset and non-matrix-record CSV products plus clearer matrix-record and selected-row readiness counts.
- `examples/89_audit_xstar_priority_matrix_closure.py` now defaults to `--occurrence-rank -1` (`latest-per-record`), which is the appropriate selection for a full-element manifest spanning ion blocks whose records can have unequal occurrence counts. A positive common occurrence rank remains available for controlled scans.
- This remains diagnostic/implementation-manifest infrastructure only. Native rate ports, RHS/normalization closure, and the expanded compact-basis solve are still disabled by default.

## v0.3.196 - 2026-05-15

- Added `xstar_atomic.xstar_priority_matrix_closure` and `examples/89_audit_xstar_priority_matrix_closure.py`.
- Joins the v0.3.195 activated compact-basis rows to the raw XSTAR `ucalc` and `calc_hmc_ion` probes at a common occurrence rank.
- Preserves shared parent-continuum / next-ion-ground aliases as one compact unknown with multiple physical roles.
- Maps the four Fortran `ajisi/indbi` insertions for every selected record into reconstructed compact `ipmat2` row/column coordinates.
- Writes physical-role, selected-record, compact-matrix-term, selected-row, family, unmapped-endpoint, and closure-requirement products.
- This is a source-code-derived implementation manifest only; native formula ports, RHS/normalization closure, and the expanded-basis solve remain disabled by default.

## v0.3.195 - 2026-05-15

- Added `xstar_atomic.xstar_priority_basis_expansion` and `examples/88_expand_xstar_priority_element_basis.py`.
- The new staged expansion consumes the v0.3.194 full-element scaffold and activates the smallest population-ranked subset of missing compact `ipmat2` rows needed for a requested solved-population coverage.
- Shared parent-continuum / next-ion-ground rows remain one compact unknown with explicit multiple physical roles; they are not duplicated as independent source rows.
- The audit writes an activation manifest, expanded compact-basis table, alias map, per-ion-block closure requirements, deferred-row table, JSON, and Markdown report.
- For the O VII solve-call 219 scaffold, the default 99.9999% target activates six rows (`293,241,244,242,80,79`) across `nionp=4,5,6`, raising represented XSTAR solved-population coverage from `0.991904690445624` to `0.9999999463123856`.
- This is basis-instantiation and closure-planning infrastructure only. Native matrix terms, RHS/normalization closure, and the full-element solve are still not enabled by default.

## v0.3.194 - 2026-05-15

- Added `xstar_atomic.xstar_full_element_basis` and `examples/87_build_xstar_full_element_basis_scaffold.py`.
- Consumes the v0.3.193 element-basis remap audit and creates one explicit Python-side scaffold row for every compact XSTAR `ipmat2` row.
- Existing Python rows retain physical mappings and shared parent-continuum aliases; unrepresented rows receive deterministic placeholder global indices.
- Writes missing-row priorities, ion-block coverage, and cumulative population-closure tiers so the native full-element implementation can be staged by physical importance.
- The scaffold is preparatory only: no default solver matrix, native rates, or closure equations are changed.

## v0.3.193 - 2026-05-15

- Added `xstar_atomic.xstar_element_basis_remap`.
- Added `examples/86_audit_xstar_element_basis_remap.py`.
- Reconstructs each selected XSTAR element solve as unique compact `ipmat2` rows while retaining duplicate parent-continuum/final-slot roles as explicit aliases.
- Remaps preserved Python population rows by `(ion_stage, level_index) -> (nionp_current, local_level_index)` instead of sequential `global_index + 1`.
- Writes exact basis rows, ion blocks, XSTAR role aliases, Python remap rows, Python alias groups, unmapped rows, and unrepresented XSTAR basis rows.
- Optionally joins the paired post-`msolvelucy` population probe to quantify solved-population coverage after the corrected remap.
- Diagnostic only; no default solver physics or matrix assembly changed.

## v0.3.192 - 2026-05-15

- Added `xstar_atomic.xstar_element_basis_probe` and `examples/85_prepare_xstar_element_basis_probe.py`.
- Prepares the next XSTAR debug product, `xstar_element_basis_probe.csv`, to capture the source-code element-basis topology inside `calc_hmc_element.f90`.
- The probe records `basis_solve_call_id`, `row_kind`, `ml_ion`, `klion`, `jkk_ion`, `nlev`, `ion_start_ipmat2`, `ion_start_ipmat`, `local_level_index`, `element_ipmat_index`, `xstar_ipmat2_index`, `nsup`, and `nion` for ion population rows, parent-continuum/shared-link rows, and the final parent-continuum slot.
- Writes conservative free-form Fortran helper plus three insertion snippets: begin of second-pass basis construction, ion-row capture after `x(mm+ipmat2)` mapping and before `ipmat2=ipmat2+nlev-1`, and final-row capture after the final `ipmat2=ipmat2+1`.
- This directly targets the v0.3.191 diagnosis that Python's current `xstar_ipmat2_index` mapping is not source-equivalent to XSTAR's full O-element basis.
- Diagnostic probe infrastructure only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.191 - 2026-05-15

- Added `xstar_atomic.xstar_population_basis_mapping` and `examples/84_diagnose_xstar_population_basis_mapping.py`.
- Consumes the population-closure parity audit products from example 83 and summarizes where the solved XSTAR element population lives in `nion`/`nsup`/`ipmat2` basis blocks.
- Writes basis-block, dominant-unmapped-row, Python-mapping-block, capture-scan, and implementation-plan CSVs.
- The O VII rank-73 diagnosis shows that Python's current `xstar_ipmat2_index` mapping covers only ~2.6e-6 of the selected XSTAR solved population; dominant rows are unmapped XSTAR rows such as ipmat2=575, 335, and 607.
- Diagnostic mapping/topology audit only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.190 - 2026-05-15

- Added `xstar_atomic.xstar_population_closure_parity` and `examples/83_audit_xstar_population_closure_parity.py`.
- Consumes the validated raw `xstar_population_closure_probe.csv`, selects an element occurrence such as O occurrence-rank 73 / latest, and compares the XSTAR before/after `msolvelucy` population vector against preserved Python solver population products.
- Writes capture-scan, overlap-row, and unmapped-XSTAR-row CSVs to quantify whether the current Python local basis covers XSTAR's full element `ipmat2` basis and whether overlapping rows agree.
- Diagnostic population/source closure audit only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.189 - 2026-05-15

- Added paired population-closure probe wrappers `xap_pbefore`/`xap_pafter` with shared `solve_call_id`.
- Added robust legacy validation/pairing for v0.3.188 population-closure CSVs with extra/unpaired captures.
- Added paired capture summary output for pre/post-`msolvelucy` diagnostics.

## v0.3.188 - 2026-05-15

- Added `xstar_atomic.xstar_population_closure_probe` and `examples/82_prepare_xstar_population_closure_probe.py`.
- Prepares the next XSTAR debug product, `xstar_population_closure_probe.csv`, captured in `calc_hmc_element.f90` immediately before and after `msolvelucy`.
- Writes a conservative free-form Fortran helper plus insertion snippets for before/after `msolvelucy`, a schema CSV, patch notes, and a validator for paired before/after population-vector captures.
- This targets the closure layer identified by v0.3.187: adjacent-ion parent coupling, superlevel source/sink closure, RHS/normalization, and pre/post-`msolvelucy` population parity.
- Instrumentation infrastructure only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.187 - 2026-05-15

- Fixed record-level family replay selector aliases so user-facing selectors such as `type50` also match legacy family keys such as `unknown:data_type_50_rate_type_4` / `data_type_50_rate_type_4`.
- Added `xstar_atomic.xstar_population_closure_diagnosis` and `examples/81_diagnose_xstar_population_closure_from_replay_scan.py`.
- The new diagnosis consumes the v0.3.186 family replay scan and decides whether exact-`ucalc` rate replay actually moves the O VII triplet population balance.
- For the current O VII blocker scan, the maximum population-fraction movement is only ~8.36e-7, so the next source-code-equivalent target is population/source closure: adjacent-ion parent coupling, superlevel source/sink closure, RHS/normalization, and pre/post-`msolvelucy` population parity.
- Diagnostic-only release: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.186 - 2026-05-15

Record-level replay family-isolation scan: adds `examples/80_scan_xstar_record_level_ucalc_replay_families.py`, which replays selected record-level families one at a time using Fortran `ucalc` ans1/ans2 branch rates and optionally re-solves each replay matrix. This separates which discrepant families actually move the O VII population balance. Diagnostic scan only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.185 - 2026-05-14

Record-level replay solve reporting update: adds population-based triplet diagnostics, line-triplet availability status, and writes original plus replay normalized solve products. No default physics changed.

## v0.3.184 - 2026-05-14

- Add controlled record-level `ucalc` matrix replay diagnostics.
- New module `xstar_atomic.xstar_record_level_replay` and example `examples/79_audit_xstar_record_level_ucalc_matrix_replay.py`.
- Consumes a selected record-level parity audit (for example O VII occurrence-rank 73), replaces selected Python matrix-row magnitudes with Fortran `ucalc` `ans1`/`ans2` branch values while preserving Python topology/signs, and writes replay matrix terms plus changed-term/family summaries.
- Optional `--run-solver` re-solves the original and replay matrices in environments with the full solver dependencies.
- Diagnostic replay scaffold only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.183 - 2026-05-14

- Add branch-aware record-level blocker diagnosis for source-code local matrix parity.
- Include type-99 parent/superlevel closure rows using `type99_records` when generic `record` is absent.
- Add per-record branch-ratio columns and recommended next actions for type-53, type-50, type-77, and type-99 closure blockers.

## v0.3.182 - 2026-05-14

- Adds local-state occurrence-rank selection to the record-level XSTAR matrix parity audit.
- `examples/78_audit_xstar_record_level_matrix_parity.py` now supports `--selection occurrence-rank --occurrence-rank N` and `--scan-occurrence-ranks` to diagnose which repeated XSTAR `ucalc` call epoch best corresponds to a preserved Python local matrix.
- This prevents over-interpreting the legacy `latest-per-record` comparison when a full XSTAR probe contains many zones/passes.
- Writes `xstar_record_level_matrix_parity_audit_occurrence_scan.csv` alongside the record and family summaries.
- Diagnostic selection infrastructure only: no solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.181 - 2026-05-14

- Add record-level XSTAR local matrix parity audit.
- New module `xstar_atomic.xstar_record_level_parity` reads preserved Python full-global matrix terms plus instrumented XSTAR `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`.
- New example `examples/78_audit_xstar_record_level_matrix_parity.py` selects the latest Fortran `ucalc` capture for each Python ATDB record, joins the four `calc_hmc_ion` matrix insertion rows, validates the Fortran `ans1/ans2 -> ajisi` self-consistency, and summarizes Python/Fortran matrix-rate agreement by record and family.
- This is a diagnostic parity-audit layer only; no solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.180 - 2026-05-14

- Fixed full-parity probe association between `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`.
- The matrix probe now writes the current `ucalc` capture id in `capture_index` and writes the independent matrix-row counter as `matrix_capture_index`.
- The validator now flags legacy v0.3.179-style independent matrix counters with `matrix_capture_index_status=independent_matrix_capture_index_needs_v03180_rerun` instead of reporting misleading one-row matrix groups.
- No solver physics, rate formula, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.179 - 2026-05-14

- Fixes the full-parity XSTAR probe link step by adding backward-compatible Fortran wrappers `xstar_atomic_probe_ucalc_record` and `xstar_atomic_probe_matrix_row` around the v0.3.178 short helper routines `xap_ucalc` and `xap_mrow`.
- This handles debug builds where `calc_hmc_ion.f90` still contains the older long-name insertion snippets while the helper was regenerated from v0.3.178.
- Instrumentation/link compatibility only: no solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.178 - 2026-05-14

- Fixes the full-parity XSTAR probe helper generated in v0.3.176/v0.3.177 for the actual HEASoft/XSTAR `.f90` free-form compilation path.
- Replaces fixed-form continuation snippets with conservative free-form Fortran using trailing `&` continuation.
- Shortens probe helper routine names to `xap_ucalc` and `xap_mrow` to avoid older compiler/name-length surprises.
- Updates the `calc_hmc_ion.f90` insertion snippets to call `xap_ucalc` / `xap_mrow`.
- Adds a generated-helper syntax test using `gfortran` when available.
- No solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.177 - 2026-05-14

- Fixed the full local parity probe Fortran helper for HEASoft/XSTAR fixed-form compilation.
- Rewrote generated helper and insertion snippets with fixed-form continuation marks in column 6 instead of free-form `&`.
- No solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.176 - 2026-05-14

- Added `xstar_atomic.xstar_full_parity_probes` and `examples/77_prepare_xstar_full_parity_probes.py`.
- Added schemas/readers/validators for the two minimum XSTAR debug products needed for source-code-equivalent local matrix parity: `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`.
- Added a debug-only Fortran helper plus insertion templates for `calc_hmc_ion.f90` immediately after `ucalc` and after each `ajisi/indbi` matrix insertion row.
- Reports whether the probes are ready for record-level `ucalc ans1..ans6` and matrix insertion parity, including missing columns and four-row insertion checks.
- No default solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.175 - 2026-05-14

- Added `xstar_atomic.xstar_full_parity_closure` for a source-code-equivalent local closure audit.
- Added `examples/76_audit_xstar_source_code_equivalent_local_closure.py`, which inventories preserved full-global matrix terms by source family and classifies rows as source-code kernel present, proxy/scaffold, mixed proxy/source, or incomplete parent/superlevel closure.
- The audit writes a family summary, required Fortran subroutine inventory, `ucalc` probe schema, `calc_hmc_ion` matrix-insertion probe schema, population probe schema, source snippet audit, Fortran probe notes, JSON, and Markdown.
- Explicitly identifies the blocking gaps for full local matrix/population parity: universal `ucalc` `ans1..ans6` parity, exact `calc_hmc_ion` `ajisi/indbi` row insertion parity, and source-code type-70/type-74/type-99 parent/superlevel closure.
- Audit/probe-planning release only: no solver physics, rate formulas, default matrix assembly, or empirical triplet tuning changed.

## v0.3.174 - 2026-05-14

- Added a controlled type-53 live-bremsam matrix-replacement solve audit: `audit_type53_live_bremsam_matrix_replacement(...)` and `write_type53_live_bremsam_matrix_replacement_audit(...)`.
- Added `examples/75_audit_xstar_type53_live_bremsam_matrix_replacement.py`, which consumes the example-74 live-bremsam `phint53` records, replaces only type-53 photoionization gain/loss rates in a preserved full-global matrix with live `phint53` ans1 values, and re-solves for f/i/r movement.
- The audit writes a replacement matrix, changed-term inventory, solve-comparison CSV, replacement normalized-solve CSV, JSON, and Markdown summary.
- This is a controlled diagnostic mode only; it does not change default solver physics, rate formulas, or empirical triplet tuning.

## v0.3.173 - 2026-05-13

- Added the first type-53 photoionization audit against instrumented XSTAR live rate-grid arrays: `audit_type53_live_bremsam_phint53(...)` and `write_type53_live_bremsam_phint53_audit(...)`.
- Added `examples/74_audit_xstar_type53_live_bremsam_phint53.py`, which reads `xstar_live_rate_grid_probe.csv`, selects a capture state, recomputes the `phint53.f90` photoionization `ans1` side on live `epim(:)` / `bremsam(:)`, and compares against preserved full-global type-53 matrix photoionization rows.
- The uploaded O VII live-rate-grid probe validates as 5 capture states and 4995 total grid points; using the final capture gives 30/30 triplet rows evaluated and 276/277 full rows evaluated.
- The audit finds the current Python matrix type-53 photoionization rows still exceed live-bremsam `phint53` rates by a median factor of about 44, so the previous normalization gap is not due to `xo01_detal4` alone. This points to the current solver matrix using the proxy `xstar-powerlaw` type-53 normalization rather than true XSTAR live `bremsam(:)`.
- Diagnostic/audit release only: no solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.172 - 2026-05-13

- Fix live-rate-grid probe validation for instrumented XSTAR runs that use placeholder zone/pass metadata for every `bremsmap` capture.
- The probe reader now splits sequential capture blocks when `grid_index` resets, so a CSV with repeated blocks of `grid_index=1..ncn2m` is read as multiple live states rather than one non-monotonic state.
- Adds readiness metadata `probe_block_split_method=nominal_key_then_grid_index_reset_v03172` and `n_probe_states_placeholder_zone_index`.
- No solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.171 - 2026-05-13

- Live-rate-grid probe instrumentation helper release only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Added `examples/73_prepare_xstar_live_rate_grid_probe_patch.py` to write a standalone Fortran helper and `xstarcalc.f90` insertion block for local/debug XSTAR builds.
- Added `live_rate_grid_probe_fortran_helper(...)`, `live_rate_grid_probe_xstarcalc_insertion_block(...)`, `locate_xstarcalc_bremsmap_site(...)`, and `prepare_live_rate_grid_probe_patch_products(...)`.
- The helper writes `xstar_live_rate_grid_probe.csv` with live `epim(:)`, `bremsam(:)`, and `bremsint(:)` after `bremsmap` and before `calc_hmc_all/calc_hmc_ion`.
- The generated insertion block uses `temperature_K=t*1.d4` and `electron_density_cm^-3=xee*xpx` based on `xstarcalc.f90` units.
- Keeps the default `zone_expression=-1` as a safe placeholder because `xstarcalc.f90` may not have the radial shell index in scope; users can replace it with a real zone variable if available.

## v0.3.170 - 2026-05-13

- Added `xstar_atomic.xstar_live_rate_grid_probe` and `examples/72_prepare_xstar_live_rate_grid_probe.py`.
- Standardizes the live XSTAR rate-grid probe schema for `epim(:)`, `bremsam(:)`, and `bremsint(:)` immediately after `bremsmap` and before `calc_hmc_all`.
- Writes a guarded Fortran probe template and validates optional long-form probe CSVs.
- Diagnostic workflow only: no solver physics, rate formulas, or empirical triplet tuning changed.

- Source-provenance/instrumentation planning cleanup only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Adds `audit_xstar_live_rate_grid_bremsa_path(...)` and `write_xstar_live_rate_grid_bremsa_path_audit(...)` to `xstar_atomic.xstar_source_provenance`.
- Adds `examples/71_audit_xstar_live_rate_grid_bremsa_path.py`, which extends the v0.3.167/v0.3.168 live-bremsa source audit through the XSTAR rate-grid handoff: `trnfrc.f90` high-resolution `bremsa(:)` -> `xstarcalc.f90` `bremsmap(...)` -> reduced-grid `epim(:)/bremsam(:)` -> `calc_hmc_all/calc_hmc_ion` -> `ucalc/phint53`.
- Records that exact type-53 photoionization parity requires exposing or reconstructing the live rate-grid `epim(:), bremsam(:), bremsint(:)` state immediately after `bremsmap`, not another `xo01_detal4` `zrems(1:5)` variant.
- Writes capture-column and instrumentation-step CSV files plus Fortran probe notes for a guarded XSTAR debug dump.
- Keeps Python as the transparent audit/orchestration layer while documenting that production RT-coupled rate/matrix kernels should move to the planned C++ backend after physics parity is complete.

## v0.3.169 - 2026-05-13

- Source-provenance/instrumentation planning cleanup only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Adds `audit_xstar_live_rate_grid_bremsa_path(...)` and `write_xstar_live_rate_grid_bremsa_path_audit(...)` to `xstar_atomic.xstar_source_provenance`.
- Adds `examples/71_audit_xstar_live_rate_grid_bremsa_path.py`, which extends the v0.3.167/v0.3.168 live-bremsa source audit through the XSTAR rate-grid handoff: `trnfrc.f90` high-resolution `bremsa(:)` -> `xstarcalc.f90` `bremsmap(...)` -> reduced-grid `epim(:)/bremsam(:)` -> `calc_hmc_all/calc_hmc_ion` -> `ucalc/phint53`.
- Records that exact type-53 photoionization parity requires exposing or reconstructing the live rate-grid `epim(:), bremsam(:), bremsint(:)` state immediately after `bremsmap`, not another `xo01_detal4` `zrems(1:5)` variant.
- Writes capture-column and instrumentation-step CSV files plus Fortran probe notes for a guarded XSTAR debug dump.
- Keeps Python as the transparent audit/orchestration layer while documenting that production RT-coupled rate/matrix kernels should move to the planned C++ backend after physics parity is complete.

## v0.3.168 - 2026-05-13

- Bugfix/diagnostic cleanup only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Improves `examples/70_audit_xstar_live_bremsa_source_path.py` so `--variant-summary-csv` can be a CSV file, an audit output directory, or an audit `.tar.gz`.
- Reports missing or mis-pointed variant-summary paths explicitly instead of silently printing `best_variant=None`.
- Keeps the source-code conclusion from v0.3.167: XSTAR live `trnfrc.f90` `bremsa(:)` uses `zremsz(:)` and is not written directly to `xo01_detal4.fits`; detail `zrems(1:5)` variants do not recover the live field.

## v0.3.167 - 2026-05-13

- Added a lightweight source-code provenance audit for the XSTAR live `bremsa(:)` radiation field; no solver physics changed.
- New module `xstar_atomic.xstar_source_provenance` with `audit_xstar_live_bremsa_source_path(...)`, `write_xstar_live_bremsa_source_path_audit(...)`, and `summarize_bremsa_variant_gap(...)`.
- New `examples/70_audit_xstar_live_bremsa_source_path.py` scans the XSTAR Fortran source for the `trnfrc.f90` live `bremsa(:)` construction, `phint53.f90` consumption, and the `savd.f90 -> fstepr4.f90` detail-output handoff.
- The audit records that live outward transfer uses `bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/(12.56*r19*r19)`, while `xo01_detal4.fits` is written from `zrems(1:5)`, opacity, emissivities, and continuum depths, not from live `bremsa(:)` or `zremsz(:)`.
- When supplied with the v0.3.166 example-69 variant summary, the audit classifies the O VII result as `source_path_confirmed_detail_variants_do_not_recover_live_bremsa`.
- This supports the next physics target: reconstruct or expose live `zremsz(:)/bremsa(:)` at the same `trnfrc -> xstarcalc -> calc_hmc_ion -> ucalc/phint53` call site, rather than treating `xo01_detal4` continuum columns as exact live-rate inputs.

## v0.3.166 - 2026-05-13

- Bugfix/performance compatibility cleanup for `examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py`; no solver physics changed.
- Fixed the NumPy 2.x compatibility bug caused by `getattr(np, "trapezoid", np.trapz)`, whose default argument is evaluated eagerly and crashes in environments where `np.trapz` has been removed.
- The vectorized phint53 bremsa-variant audit now uses `np.trapezoid` when available and a small local trapezoidal fallback otherwise.
- Updated audit metadata to `v0.3.166` and added regression coverage for NumPy builds without `np.trapz`.

## v0.3.165 - 2026-05-13

- Performance/diagnostic cleanup for `examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py`; no solver physics changed.
- Vectorized the type-53 `phint53` bremsa-variant integration by precomputing the cross-section/interpolation kernel once per record and evaluating all selected continuum variants together with array operations.
- Added `--variants`, `--fast`, `--profile`, and `--skip-records-csv` to control expensive diagnostic runs and reduce unnecessary full-sample output.
- Added timing/profile fields (`integration_seconds`, `total_seconds`, `n_vectorized_record_batches`, and `n_evaluated_variant_record_pairs`) to the audit summary and Markdown report.
- Documented that this remains a Python audit prototype; production RT-coupled rate, matrix, and transfer kernels should move to the planned C++ backend after physics parity is fixed.

## v0.3.164 - 2026-05-13

- Added a type-53 detail-continuum bremsa-variant audit to diagnose the v0.3.162/v0.3.163 photoionization normalization gap.
- New `audit_type53_detail_phint53_bremsa_variants(...)` and `write_type53_detail_phint53_bremsa_variants_audit(...)` helpers in `xstar_atomic.xstar_matrix_parity`.
- New `examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py` command-line audit.
- The audit recomputes type-53 `phint53` photoionization rates using multiple `xo01_detal4.fits` `zrems(1:5)`/attenuation/geometric reconstruction variants and scores whether any available detail-column variant matches the matrix without a free scale.
- It records the source-code distinction that `trnfrc.f90` uses live outward `zremsz(:)` for `bremsa(:)`, while `fstepr4.f90` writes `zrems(1:5,:)` detail columns and not `zremsz`.
- No solver physics or empirical triplet tuning changed.

## v0.3.160 - 2026-05-12

- Added source-code/local handoff parity auditing for XSTAR data type 68 He-like collision terms.
- New `audit_type68_collision_rates(...)` and `write_type68_collision_rate_audit(...)` helpers in `xstar_atomic.xstar_matrix_parity`.
- New `examples/65_audit_xstar_type68_collision_rates.py` command-line audit.
- The audit checks `directional_q_cm3_s * electron_density_cm^-3` against full-global matrix rates, verifies off-diagonal gain / diagonal loss partner placement, and reports triplet-touching coverage.
- No solver physics or empirical triplet tuning changed.

## v0.3.159 - 2026-05-12

- Added a source-code-equivalent type-71 superlevel cascade parity audit.
- Added `audit_type71_cascade_rates(...)` and `write_type71_cascade_rate_audit(...)` to `xstar_atomic.xstar_matrix_parity`.
- Added `examples/64_audit_xstar_type71_cascade_rates.py`, which checks the `calt71.f90` interpolated `Aij` handoff through the `ucalc.f90` type-71 branch into full-global matrix gain/loss terms.
- The audit reports term-level `matrix_rate - 10**type71_calt71_log10_aij` residuals, record-level gain/loss pair closure, partner placement, and triplet-destination/triplet-row coverage.
- O VII v0.3.156 products show 148/148 type-71 matrix terms match `calt71` Aij, 148/148 partner checks match, and 74/74 record-level gain/loss pairs close. With `--triplet-only`, 20/20 triplet-destination terms match and 10/10 record-level pairs close.
- No solver physics, source terms, or empirical triplet tuning changed.

## v0.3.157 - 2026-05-12

- Added `xstar_atomic.xstar_matrix_parity`, a source-code-parity audit layer that reads preserved full-global solver matrix terms and normalized-solve products from example 56.
- Added `examples/62_audit_xstar_local_matrix_parity.py` to rank matrix rate families by data type/source path and report which families feed or drain He-like f/i/r upper levels.
- The audit can ingest the example-61 type-50 detail audit CSV and mark audited type-50 rows as `detail_rate_and_matrix_parity_verified_for_audited_type50_lines` when all matrix rows match.
- This is an audit/triage release only: no empirical triplet tuning and no intentional solver-physics changes.

## v0.3.156 - 2026-05-12

- Propagate same-run detail-output covering fraction (`cfrac`) from `xo01_detal2.fits` depth rows into type-50 matrix assembly.
- Add a fallback `type50_cfrac` path for XSTAR line-escape evaluation when a transition row carries tau0 but not cfrac.
- Refine the detail-state type-50 audit to classify `matrix_cfrac_mismatch` separately from generic rate-evaluator mismatches.
- No intentional change to source terms or non-type-50 solver physics.

## v0.3.155 - 2026-05-12

- Added detail-state type-50 tau handoff from `xo01_detal2.fits` into the `xstar-local-state` solver preset when same-run detail outputs and an ATDB are available.
- Added `xstar_atomic.xstar_detail.build_detail_type50_depth_rows_for_solver(...)` to map `xo01_detal2.fits` line `tau_in`/`tau_out` rows onto ATDB type-50 lower/upper level indices for matrix assembly.
- Added the solver keyword `xstar_type50_depth_lines_csv` and safe `type50_escape_source=xstar-detail-lines` path so the population matrix can use detail-state `tau0(1:2,line)` values without reusing final `xout_lines1.fits` products.
- Improved the detail-state type-50 matrix audit classification: scalar 0.35 escape fallback mismatches are now reported as `matrix_tau0_missing_scalar_escape_proxy` rather than generic `rate_evaluator_mismatch`.
- No type-50 photoexcitation is forced; for `cfrac=1` the `ucalc.f90` photoexcitation branch remains zero.

## v0.3.154 - 2026-05-12

- Added solver-product preservation to `examples/56_reproduce_xstar_local_outputs.py` via `--write-solver-products` and `--solver-output-root`.
- Preserved solver products are written from the in-memory solver result using historical filenames such as `xstar_like_element_solver_full_global_matrix_terms.csv`, plus a products manifest.
- Benchmark comparison CSV/JSON rows now record paths to the preserved full-global matrix terms, normalized-solve comparison, and summary JSON.
- Added automatic matrix-term handoff to `examples/61_audit_xstar_detail_type50_rates.py` via `--benchmark-dir` / `--benchmark-comparisons-csv`.
- The detail-state type-50 audit now compares `ucalc.f90` escaped/photo rates against all matching matrix rows and classifies each residual as `matrix_matches_ucalc_rate`, `rate_evaluator_mismatch`, `matrix_placement_mismatch`, or `no_matching_matrix_term`.
- No solver physics changed.

## v0.3.153 - 2026-05-12

- Added `examples/61_audit_xstar_detail_type50_rates.py`, a row-by-row XSTAR detail-state type-50 audit for He-like triplet lines.
- Added public detail-audit helpers in `xstar_atomic.xstar_detail` for `pescl`, `ptmp1/ptmp2`, XSTAR-style `nbinc`, type-50 `vtherm`, and source-code type-50 rate rows.
- The audit reads `xo01_detal2.fits`/`xo01_detal4.fits`, matches selected O VII f/i/r line rows to ATDB type-50 records when available, computes escaped decay and photoexcitation using `calc_hmc_ion.f90` + `ucalc.f90` formulas, and writes CSV/JSON/Markdown products.
- Optional matrix-term CSV matching adds residual columns without changing solver physics.

## v0.3.152 - 2026-05-12

- Fixed XSTAR detail-state population when `xout_abund1.fits` contains a trailing all-zero sentinel ABUNDANCES row.
- The detail-state reader now carries forward the most recent valid plasma state for final/cumulative detail HDUs whose matching abundance row is a zero sentinel, avoiding misleading `T=0`, `ne=0`, and `logxi=0` summaries.
- Added `abundance_row_source` provenance to zone summaries and field-status outputs.
- Added regression coverage for O VII detail outputs with a zero abundance sentinel row.

## v0.3.151 - 2026-05-12

- Added `xstar_atomic.xstar_detail`, a detail-output reader that populates the Python live-state schema from XSTAR `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal4.fits`, and `xout_abund1.fits`.
- Added lightweight BINTABLE parsing to the built-in FITS fallback so XSTAR detail products can be read even when `astropy` is unavailable.
- Added `examples/60_populate_xstar_live_state_from_detail.py` to write per-zone live-state summaries and field-status tables.
- No solver physics changed.

## v0.3.150 - 2026-05-12

- Added `xstar_atomic.xstar_state`, which defines explicit Python live-state containers needed for future XSTAR-output recreation:
  - `XSTARContinuumState` for `epi(:)`, `bremsa(:)`, `bremsint(:)`, and continuum optical depths.
  - `XSTARLineTransferState` for `tau0(1:2,line)`, optional `ptmp1/ptmp2`, and line emissivity/opacity arrays.
  - `XSTARZoneState` for zone-local `T`, `ne`, `cfrac`, `vturbi`, ion fractions, level populations, and heating/cooling maps.
  - `XSTARRunState` for the full run state across radial zones.
- Added `required_live_state_fields()`, `create_initial_xstar_run_state_from_input(...)`, and `write_xstar_state_skeleton(...)`.
- Added `examples/59_create_xstar_live_state_skeleton.py` to write JSON/Markdown/CSV state-schema products from an XSTAR command or `run_xstar.sh`.
- Extended the XSTAR recreation plan JSON with a `live_state_schema` section.
- No full XSTAR recreation or solver physics change yet; this release makes the required internal state explicit and reusable.

## v0.3.149 - 2026-05-11

- Adds the first Python XSTAR-output recreation planning layer.
- New module `xstar_atomic.xstar_run` parses shell-style `xstar key=value` command lines and `run_xstar.sh` files into normalized `XSTARInputParameters`.
- Adds `standard_xstar_output_products()`, `xstar_recreation_plan(...)`, and `write_xstar_recreation_plan(...)` to map `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal3.fits`, `xo01_detal4.fits`, `xout_abund1.fits`, `xout_lines1.fits`, `xout_rrc1.fits`, `xout_cont1.fits`, and `xout_spect1.fits` onto the live XSTAR internal state required for source-code-parity recreation.
- Adds `examples/58_plan_xstar_output_recreation.py` and the console entry point `xstar-atomic-plan-xstar-run`.
- This is a planning/audit release only: it does not claim to run the full XSTAR thermal/ionization/radiative-transfer iteration or write exact replacement FITS products yet.

## v0.3.148 - 2026-05-11

- Restored the `xstar-local-state` benchmark preset to the historical examples/51--52 full-global validation branch.
- Stopped treating post-transfer `xout_lines1.fits` line depths as the live `tau0(:,:)` array used by `calc_hmc_ion.f90` in the population matrix.
- Stopped treating final `xout_cont1.fits`/`xout_spect1.fits` spectra as the live local `bremsa(:)` array for the default source-code-parity preset.
- Added `xstar-local-state-experimental-pumping` for explicitly unsafe output-table pumping experiments.
- Added `docs/helike_fortran_python_gap_audit.md` documenting the relevant XSTAR Fortran source path and the remaining exact-parity requirement.
- No empirical triplet scaling was added.

## v0.3.147 - 2026-05-11

- Corrects the first type-50 pumping benchmark path to use the same-run XSTAR `cfrac` parameter from the FITS `PARAMETERS` table when available.
- The `xstar-local-state` preset no longer assumes `cfrac=0`; if `cfrac` cannot be read, it falls back to `cfrac=1` to avoid unphysical maximum pumping.
- Adds `xstar_cfrac` / `xstar_cfrac_source` target metadata and comparison columns, plus `solver_type50_cfrac` diagnostics.
- Keeps type-50 line pumping opt-in through `xstar-line-escape-and-pumping`; no empirical scale factors are added.

## v0.3.146 - 2026-05-11

- Corrects the first type-50 line-pumping benchmark implementation after the v0.3.145 four-ion run showed severe over-pumping from the diagnostic `xstar-powerlaw` continuum.
- Adds same-run XSTAR continuum-spectrum support for the local-state benchmark: `xout_cont1.fits` or `xout_spect1.fits` is converted to a temporary UTF-8 CSV and passed to the full-global solver as an `xstar-output` radiation grid.
- Converts the XSTAR spectrum column (`transmitted` by default) to the internal `bremsa`-like grid using the source-code geometry from `trnfrc.f90`, `bremsa=zremsz*exp(-tau)/(12.56*(r/1e19)^2)`, with the selected local radius from `xout_abund1.fits`.
- Changes the `xstar-local-state` preset so type-50 pumping is evaluated only from the same-run XSTAR output spectrum when available; if no output spectrum is present, the pumping branch is not evaluated instead of falling back to an arbitrary power-law normalization.
- Adds diagnostic columns for the radiation spectrum path, selected column, conversion status, and number of grid points.
- Adds regression tests ensuring `xstar-output` pumping uses the explicit XSTAR output grid and does not silently fall back to the proxy continuum.

## v0.3.145 - 2026-05-11

- Fixes the first `xstar-line-escape-and-pumping` benchmark run, which failed on non-type-50 transitions with `cannot access local variable 'pumping_terms' where it is not associated with a value`.
- Initializes the type-50 pumping diagnostic payload for all bound-bound rows, including raw-A and non-type-50 transitions.
- Keeps type-50 photoexcitation injection opt-in through `xstar-line-escape-and-pumping`; no additional empirical scaling is added.

## v0.3.144 - 2026-05-11

- Added the first source-code-matched type-50 lower-to-upper photoexcitation / line-pumping matrix mode.
- New treatment alias: `xstar-line-escape-and-pumping`.  It keeps the XSTAR line-escape downward branch and injects the upward pumping branch from `ucalc.f90` type 50.
- The pumping rate uses the XSTAR algebra `sigma=0.02655*flin*lambda_cm/vtherm` and `ans1_postswap=sigma*bremsa(nb1)*vtherm/3e10*flinabs(ptmp1)*(1-cfrac)`, with `flinabs=1` as in `flinabs.f90`.
- Added XSTAR-style helpers for type-50 thermal velocity, oscillator-strength recovery from A-values/statistical weights, and `nbinc`-style bin selection on the explicit solver `epi`/`bremsa` grid.
- The `xstar-local-state` benchmark preset now uses `type50_bound_bound_treatment="xstar-line-escape-and-pumping"` with same-run line depths and the explicit diagnostic `xstar-powerlaw` `epi`/`bremsa` grid.
- Added regression tests for injected type-50 pumping matrix terms and the `cfrac=1` suppression path.
- This is the first opt-in physics implementation of type-50 pumping; comparison to the C V/O VII/Mg XI/Ca XIX same-run XSTAR benchmark should be inspected before making it a default predictive mode.

## v0.3.143 - 2026-05-11

- Added a controlled same-run line-depth matrix escape mode for local XSTAR reproduction benchmarks.
- The `xstar-local-state` benchmark preset now passes `type50_escape_source="xstar-reference-lines"`, so matching type-50 triplet transitions can use `depth_inward`/`depth_outward` from the same-run converted `xout_lines1.fits` reference table instead of the scalar 0.35 escape fallback.
- Added internal transition-depth matching by reversed level indices and wavelength, mirroring the XSTAR source-code flow where `calc_hmc_ion.f90` supplies `ptmp1`/`ptmp2` to `ucalc.f90` before type-50 rates are assembled.
- This is a benchmark/reproduction mode, not a final predictive radiation-transfer replacement: true arbitrary-condition reproduction still requires a source-code-matched local radiation field (`epi`, `bremsa(nb1)`, `flinabs`, and `cfrac`) and type-50 line pumping.

## v0.3.142 - 2026-05-11

- Fixed the local-state benchmark triplet-source preference used by `examples/56_reproduce_xstar_local_outputs.py`.
- The `xstar-local-state` solver benchmark now prefers `full_global_xstar_tau0_calc_emis_ion`, matching the historical examples 51--52 validation workflow.
- Kept `full_global_xstar_reference_depth_emit_outward_calc_emis_ion` available as a secondary diagnostic instead of using it as the default benchmark source when both branches are present.
- Added a regression test that fails if the benchmark again silently prefers the reference-depth postprocess branch over the historical tau0 branch.
- No solver physics changed; type-50 photoexcitation remains audit-only.

## v0.3.141 - 2026-05-11

- Added source-code-gap diagnostics to the He-like local-output reproduction benchmark.
- The comparison table now includes solver-to-XSTAR ratios for f/i/r/R/G, a residual-pattern label, same-run resonance-line depth/escape diagnostics, and solver type-50/radiation settings.
- Added `docs/helike_reproduction_source_code_diagnosis.md`, summarizing the XSTAR source-code path (`calc_hmc_ion.f90`, `ucalc.f90` type 50, `calc_emis_ion.f90`, `pescl.f90`) and the current likely gaps: audit-only type-50 photoexcitation, scalar matrix escape fallback, and proxy radiation-field normalization.
- No solver physics changed.  This release improves diagnosis/reporting only.

## v0.3.140 - 2026-05-11

- Fixed `--solver-preset xstar-local-state` in the He-like C/O/Mg/Ca benchmark suite.
- The benchmark no longer passes the binary/ascii FITS table `xout_lines1.fits` directly to the lower-level solver option `xstar_reference_lines_csv`, which expects a converted CSV file.
- When the local-state preset needs same-run XSTAR reference lines, the benchmark now writes the already-loaded selected XSTAR line rows to a temporary UTF-8 CSV and passes that CSV to `solve_element_reference`.
- This removes the `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 ...` failure seen when the solver tried to read `xout_lines1.fits` as CSV.
- Added a regression test that verifies the local-state preset passes a `.csv` reference table, not a `.fits` file.
- No solver physics changed; this fixes benchmark plumbing so the real solver-vs-XSTAR residuals can be inspected.

## v0.3.139 - 2026-05-11

- Strengthen the He-like C/O/Mg/Ca same-run benchmark comparison after the API reorganization.
- Add solver and XSTAR diagnostic columns for `R=f/i`, `G=(f+i)/r`, and L2 distance to the exact same-run XSTAR triplet target.
- Record the solver triplet source used in the benchmark comparison so quick workflow summaries are not confused with the source-code-first full-global validation path.
- Prefer full-global / `calc_emis_ion` triplet summaries when present; use `summary.he_like_triplet` only as a fallback and mark it with a warning.
- Add `--solver-preset xstar-local-state` to `examples/56_reproduce_xstar_local_outputs.py`; the preset mirrors the solver settings generated by `examples/51_run_helike_local_state_validation.py`.
- Add `docs/helike_benchmark_diagnosis.md` summarizing the XSTAR source-code path (`calc_hmc_ion.f90`, `ucalc.f90`, `calc_emis_ion.f90`) and why the quick workflow-default solver can reproduce different residuals from the earlier local-state validation workflow.
- No solver physics changed; type-50 photoexcitation/line pumping remains audit-only.

## v0.3.138 - 2026-05-11

- Strengthened XSTAR ATDB path resolution for solver benchmarks and workflow APIs.
- If `XSTAR_ATDB` and `XSTAR_ATDB_FITS` are unset, the resolver now explicitly uses configured `datapath` files and can consult a `datapath` file in the current working tree.
- Added `get_data_paths()` so diagnostics can show all configured datapath candidates.
- Skips stale datapath entries and falls through to the next valid candidate before reporting that no `atdb.fits` was found.
- Source distributions no longer include a machine-specific `datapath` file; users configure it locally with `python -m xstar_atomic.data --set-path /path/to/atdb.fits`.
- No solver physics changed. The C V/O VII/Mg XI/Ca XIX benchmark residuals are unchanged and remain the next physics target.

## v0.3.137 - 2026-05-10

- Fixed the four-ion local-output benchmark solver mode so it accepts the common `XSTAR_ATDB` environment variable in addition to `XSTAR_ATDB_FITS`.
- Treats a blank `--atdb` value, such as `--atdb "$XSTAR_ATDB"` when the shell variable is unset, as not provided and falls back to the configured resolver instead of trying `./atdb.fits`.
- Lets the normal ATDB resolver handle `--atdb`, `XSTAR_ATDB_FITS`, `XSTAR_ATDB`, and saved `datapath` consistently during solver comparisons.
- The example summary now prints solver f/i/r values and comparison warnings, making failed solver setup visible immediately at the terminal.

## v0.3.136 - 2026-05-10

- Fixed the C V / O VII / Mg XI / Ca XIX XSTAR reproduction benchmark solver-comparison extraction.
- `examples/56_reproduce_xstar_local_outputs.py --run-solver` now reads the current solver's `summary["he_like_triplet"]` result and fills `solver_f_fraction`, `solver_i_fraction`, and `solver_r_fraction` when available.
- The benchmark no longer reports `solver_compared` when solver triplet fractions are missing; it reports `solver_no_triplet_values` with an explicit warning instead.
- Added regression tests for solver-summary triplet extraction and missing-triplet status handling.
- No solver physics changed; this release only fixes benchmark reporting/extraction.

## v0.3.135 - 2026-05-10

- Added a built-in standard C V / O VII / Mg XI / Ca XIX benchmark suite for `examples/56_reproduce_xstar_local_outputs.py` via `--standard-helike-suite --xstar-runs-root xstar_runs`.
- Added `default_helike_benchmark_cases(...)` and `write_default_helike_cases_csv(...)` to create the canonical four-ion case table programmatically or as an editable CSV.
- Improved the missing `--cases-csv` error message with a copy-pasteable case-table recipe and a pointer to `--standard-helike-suite`.
- Updated README, examples README, Markdown/LaTeX/Sphinx user-guide examples for the new one-command four-ion benchmark workflow.
- No solver physics changed; this remains exact XSTAR target extraction plus optional residual reporting.

## v0.3.134 - 2026-05-10

- Added `src/xstar_atomic/benchmark.py`, a same-run XSTAR local-output reproduction layer for C V, O VII, Mg XI, and Ca XIX benchmarks.
- Added `XSTARLocalTarget` and `XSTARBenchmarkComparison` result objects that keep the exact local state from `xout_abund1.fits` and exact He-like triplet target from `xout_lines1.fits` separate from any solver residual.
- Added public helpers `build_xstar_local_target(...)`, `reproduce_xstar_run(...)`, `run_xstar_benchmark_suite(...)`, `write_xstar_benchmark_outputs(...)`, and `write_xstar_benchmark_suite(...)`. These are exported at the top level and through `xstar_atomic.validate`/`XSTARAtomic.validate`.
- Added `examples/56_reproduce_xstar_local_outputs.py`, a CLI wrapper that writes local-state, triplet-target, selected-line, comparison, JSON, and Markdown benchmark products.
- Updated Markdown, LaTeX, and Sphinx user guides with the new same-run reproduction benchmark API and CLI example.
- Updated `examples/README.md` and the example-to-source migration map for example 56.
- No solver physics changed; type-50 photoexcitation remains audit-only. This release establishes exact XSTAR-output targets before further solver corrections.

## v0.3.133 - 2026-05-10

- Expanded `docs/user_guide.md`, `docs/user_guide.tex`, and `docs/sphinx/source/user_guide.rst` with function-by-function examples for the top-level workflow API, context classes, `RateEvaluation`, audit-only type-50 evaluation, and expert object namespaces.
- Fixed the LaTeX `Examples and source-module migration` table layout by using breakable path-style entries so long example filenames and API names no longer overlap.
- Updated documentation regression tests so the API examples are checked across Markdown, LaTeX, and Sphinx sources.
- No solver physics changed; type-50 photoexcitation / line pumping remains audit-only.

## v0.3.132 - 2026-05-10

- Expanded and clarified the public API documentation in `docs/user_guide.md` with a canonical workflow-first API section, a top-level function summary table, expert namespace examples, public namespace-module examples, and explicit notes about prototype/not-yet-final physics APIs.
- Rewrote `docs/sphinx/source/user_guide.rst` so the Sphinx user guide now mirrors the Markdown/LaTeX organization instead of remaining an older CLI-focused page.
- Expanded `docs/sphinx/source/api.rst` to include the workflow-first API (`xstar_atomic.workflow`), public namespaces (`rates`, `matrix`, `solve`, `validate`, `runs`), context objects, type-50 evaluator, and audit module.
- Expanded `docs/user_guide.tex` with the same workflow-first and expert API material and retained the LaTeX table of contents.
- Added documentation regression tests requiring the new public API names to appear in Markdown, LaTeX, and Sphinx docs.
- No solver physics changed; type-50 photoexcitation remains audit-only and is not injected into the population matrix.

## v0.3.131 - 2026-05-10

- Added the first workflow-first module-level public API layer inspired by the earlier `chianti-tools` review:
  - `open_database(...)`
  - `get_levels(...)`, `get_lines(...)`, `get_wavelengths(...)`, `get_energies(...)`
  - `match_line(...)`, `match_lines(...)`
  - `get_collisions(...)`, `get_photoionization(...)`, `get_recombination(...)`
  - `calc_emissivity(...)`, `calc_rate(...)`, `calc_triplet(...)`
  - `solve_populations(...)`, `build_matrix(...)` wrappers around the current solver workflow.
- Added `XSTARContext` plus `context_from_values(...)` and `context_from_xstar_run(...)` for lightweight local XSTAR contexts selected from `xout_abund1.fits`.
- Added namespace-style expert API attributes on `XSTARAtomic`:
  - `db.context.from_values(...)`, `db.context.from_xstar_run(...)`
  - `db.rates.type50(...)`
  - `db.audit.type50_line_pumping(...)`
  - `db.matrix.build_ion(...)`
  - `db.solve.ion(...)`
  - `db.validate.compare_xstar_run(...)`.
- Added public namespace modules `xstar_atomic.rates`, `xstar_atomic.solve`, `xstar_atomic.matrix`, `xstar_atomic.validate`, and `xstar_atomic.runs` as stable import locations for future API growth.
- Expanded Markdown and LaTeX docs with the new workflow-first API calls and expert namespace examples.
- Added API tests for public workflow functions and namespace modules.
- No solver physics changed; type-50 photoexcitation remains audit-only and is not injected into the population matrix.

## v0.3.130 - 2026-05-10

- Expanded `examples/README.md` so every example script has its own section with a copy-pasteable `bash` command block.
- Preserved the relevance-based example organization while replacing compact inline table commands with more readable per-example command blocks.
- Added documentation tests that verify all `examples/*.py` files are listed in `examples/README.md` and have a corresponding `bash` command block.
- No solver physics changed; type-50 photoexcitation remains audit-only.

## v0.3.129 - 2026-05-10

- Added `examples/README.md`, organizing all example scripts by workflow/relevance and giving a minimal command for each example. The README also adds recommended learning paths for new users, decoder development, emissivity/export work, O VII triplet development, full-global XSTAR validation, and Mg/Ca validation.
- Expanded `docs/user_guide.md` with a table of contents and a new public API cookbook covering database setup, line/level queries, collision and recombination products, local context objects, the audit-only type-50 evaluator, high-level `XSTARAtomic` convenience methods, source-code audits, and export workflows.
- Expanded `docs/user_guide.tex` with `\tableofcontents` after `\maketitle` and the same public API cookbook examples as the Markdown guide.
- Updated the package README and manifest so the examples README is discoverable and included in source distributions.
- No solver physics changed; type-50 photoexcitation remains audit-only.

## v0.3.128 - 2026-05-10

- Added `src/xstar_atomic/context.py` with public `LocalPlasmaState`, `RadiationField`, and `EscapeContext` containers for local XSTAR plasma, radiation, and escape/geometry state.
- Added `src/xstar_atomic/rates_type50.py` with the `RateEvaluation` result class and audit-only `evaluate_type50_bound_bound(...)` evaluator for the XSTAR `ucalc.f90` type-50 bound-bound radiative branch. The evaluator records pre-swap escaped decay, pre-swap photoexcitation, post-swap lower-to-upper photoexcitation, post-swap upper-to-lower escaped decay, sigma, `bremsa(nb1)`, `flinabs(ptmp1)`, `cfrac`, and `ptmp` terms when available.
- Added `src/xstar_atomic/audit.py` with reusable `type50_line_pumping(...)` audit workflow and `Type50LinePumpingAudit` return object.
- Converted `examples/55_audit_helike_type50_line_pumping.py` into a thin CLI wrapper around `xstar_atomic.audit.type50_line_pumping(...)`, preserving the previous command-line interface while making the audit callable as a public API.
- Added `XSTARAtomic.type50_rate(...)` and `XSTARAtomic.audit_type50_line_pumping(...)` convenience methods.
- Reorganized `docs/user_guide.md` and `docs/user_guide.tex` into a workflow-first structure similar to `chianti-tools`: installation/data setup, quick start, database access, context objects, source-code-aligned rate evaluators, matrix/solver workflows, XSTAR-output validation, audit workflows, example-to-source migration, tests, and roadmap.
- Added `docs/example_to_source_api_map.md`, identifying which example scripts should migrate into stable source modules as the API hardens.
- No solver physics changed; the type-50 line-pumping/photoexcitation implementation remains audit-only and no empirical triplet scale fitting was added.

## v0.3.127 - 2026-05-10

- Added `examples/55_audit_helike_type50_line_pumping.py`, a source-code-first audit for the missing XSTAR type-50 bound-bound photoexcitation / line-pumping path after all-ion local-state validation.
- The new audit records the XSTAR `ucalc.f90` type-50 source-code formula for the upward photoexcitation term, identifies the required radiation-field inputs (`epi`, `bremsa`, `flinabs`, `cfrac`, thermal velocity, and escape probabilities), and reports that the current `xstar-line-escape` population matrix has zero explicit photoexcitation into `1s2p 1P1`.
- The audit combines local-state case metadata, same-run XSTAR triplet targets, comparison summaries, and full-global matrix terms, but does not fit or apply any empirical triplet scale.
- No solver physics changed; this release documents the next source-code implementation target: port XSTAR `ucalc.f90` type-50 `ans2` line-pumping using the correct local radiation normalization before interpreting collision-rate scale residuals.

## v0.3.126 - 2026-05-10

- Added `examples/54_audit_helike_resonance_population_flux.py`, a source-code-first diagnostic that combines solved population fractions with full-global matrix terms to compute population-weighted feed and loss paths for the He-like resonance upper level `1s2p 1P1`.
- The new audit writes `helike_resonance_population_flux_summary.csv`, `helike_resonance_population_flux_detail.csv`, `helike_resonance_population_flux_audit.md`, and `helike_resonance_population_flux_audit.json`.
- The audit separates direct ground-to-resonance feed, collisional cascade/mixing feed, radiative cascade feed, explicit photoexcitation feed, and resonance losses. It also records a clearly marked linearized equivalent feed diagnostic but does not apply or fit any scale factor.
- On the user's all-ion local-state comparison, all four ions still have low resonance fractions and zero population-weighted explicit photoexcitation into `1s2p 1P1`, reinforcing that the next source-code target should be XSTAR bound-bound line pumping / local radiation normalization before any collision-rate scale interpretation.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.125 - 2026-05-09

- Added `examples/53_audit_helike_resonance_deficit.py`, a diagnostic-only audit for the common local-state residual in C V, O VII, Mg XI, and Ca XIX.
- The new audit reads `helike_local_state_cases.csv`, per-ion `xstar_detail_population_comparison_summary.json` files, same-run XSTAR triplet line CSVs, resonance-collisional-feed audits, radiation-context audits, and full-global matrix terms.
- It reports the resonance-fraction deficit, solver/target f/i/r residuals, XSTAR line depths, direct resonance-collisional feed sums by data type, diagnostic radiation-field provenance, and whether any nonzero photoexcitation terms into `1s2p 1P1` are present in the assembled matrix.
- Applied to the user’s all-ion local-state run, all four ions have solver `f` high, solver `r` low, and zero explicit nonzero photoexcitation into the resonance upper level in the assembled matrix audit. This points next to XSTAR line-pumping/radiation normalization and direct ground-to-resonance feeding, not per-ion triplet scale fitting.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.124 - 2026-05-09

- Fixed the default output label in `examples/51_run_helike_local_state_validation.py` so newly generated local-state solver directories use `v03124` instead of the stale `v03122` label.
- Added `examples/52_summarize_helike_local_state_comparison.py`, a diagnostic-only summary tool that combines `helike_local_state_cases.csv` with per-ion `xstar_detail_population_comparison_summary.json` files.
- The new summary reports local XSTAR `T/ne/log xi`, solver f/i/r, same-run XSTAR f/i/r, residuals, `R`, `G`, `L2`, and the common residual pattern across C V, O VII, Mg XI, and Ca XIX.
- Applied to the user’s v0.3.123 all-ion local-state output, the common residual is solver `f` high and solver `r` low for all four ions. This points to direct ground/resonance feeding and radiation/line-pumping normalization before any row-level type-56/type-63/type-68/type-69 rate interpretation.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.123 - 2026-05-09

- Fixed generated He-like local-state validation shell scripts from `examples/51_run_helike_local_state_validation.py`.
- Commands are now written with shell-quoted tokens, so ion names containing spaces, especially `C V` and `O VII`, are passed correctly to `python -m xstar_atomic.xstar_outputs --ion ...`.
- This fixes failures like `xstar_outputs.py: error: unrecognized arguments: V` in `compare_helike_local_state_solvers.sh`.
- No solver physics changed; no empirical triplet scale fitting was added.

## v0.3.122 - 2026-05-09

- Fixed `examples/51_run_helike_local_state_validation.py` density selection in `--selection-mode max` runs. When `--target-electron-density` and `--nearest-density` are supplied, the script now constrains to the closest available local XSTAR electron density before choosing the maximum He-like fraction. This prevents mixed-density trees from selecting ne≈1 cm^-3 C V/O VII/Ca XIX states when the requested validation target is ne≈1e8 cm^-3.
- The local-state comparison target now prefers the matched XSTAR run directory: if a selected `xout_abund1.fits` has a sibling `xout_lines1.fits`, the script uses a same-directory triplet CSV when present or auto-generates one under `auto_xstar_triplet_targets/`. Generic/preconverted target CSVs are now only fallback targets.
- Added provenance columns `target_csv_source` and `target_csv_source_policy` to clarify whether the comparison uses same-run XSTAR lines or a fallback target search.
- No solver physics changed and no empirical triplet scale fitting was added.
- Validation: `compileall` passed; selected pytest suite passed with 10 passed and 3 skipped.

## v0.3.121 - 2026-05-09

- Improved `examples/51_run_helike_local_state_validation.py` for He-like validation trees that contain C/O density-only runs such as `helike_type69/c5_ne1e8` and `helike_type69/o7_ne1e8`.
- The driver now records available local `log xi` and electron-density values when a requested `--log-xi` / density filter excludes an ion-specific XSTAR run. This makes it clear when C V/O VII are present but not at the requested `log xi=3` Mg/Ca condition.
- Added automatic triplet-target CSV creation from the matched XSTAR `xout_lines1.fits` when a preconverted `xstar_*_triplet_lines.csv` is absent. Generated CSVs are written under `auto_xstar_triplet_targets/`, and the compare script includes the conversion command before running `examples/43_compare_xstar_detail_populations.py`.
- This supports source-code-first local-state validation for C V, O VII, Mg XI, and Ca XIX from the same `xstar_runs` tree without requiring separate manual conversion steps.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.120 - 2026-05-09

- Improved `examples/51_run_helike_local_state_validation.py` for practical local-state validation against XSTAR `xout_abund1.fits` products.
- Added `--target-electron-density`, `--electron-density-tolerance-dex`, and `--nearest-density` so a grid containing multiple XSTAR density runs can be reduced to the requested local density, e.g. `ne≈1e8 cm^-3`, before generating solver commands.
- De-duplicated repeated `xout_abund1.fits` discoveries that arise when the same case appears in both copied and nested `mg_ca_triplet_targets` layouts.
- Stopped using unrelated Mg/Ca `xout_abund1.fits` tables as C V/O VII local states when no matching C/O XSTAR run directory is present. C/O are now marked as missing local state unless matching `c5`/`o7` XSTAR `xout_abund1.fits` cases exist.
- No solver physics changes and no empirical triplet scale fitting.

## v0.3.119 - 2026-05-09

- Added `examples/51_run_helike_local_state_validation.py`, a source-code-first driver that reads XSTAR `xout_abund1.fits` local-zone states and prepares/runs He-like solver comparisons at those local `T`, `ne`, and `log xi` conditions for C V, O VII, Mg XI, and Ca XIX.
- The new driver writes `helike_local_state_cases.csv`, `helike_local_state_zone_candidates.csv`, `helike_local_state_summary.json`, `helike_local_state_validation_plan.md`, and reproducible shell scripts for solver and comparison commands.
- Supports `--selection-mode grid|max` and `--log-xi` for either full local-state grids or a single selected log-xi comparison.
- Keeps the source-code-first policy: no empirical triplet scale fitting and no default solver-physics changes. The generated commands use XSTAR local `T` and `ne`; radiation normalization remains explicitly marked as not yet tied to XSTAR xi/transfer.
- On the supplied `xstar_runs` Mg/Ca grid, the driver finds usable local-state cases for Mg XI and Ca XIX but reports C V and O VII as missing/nonzero local-state targets in that specific run tree, because the Mg/Ca `xout_abund1.fits` files have zero C V and O VII He-like fractions.

## v0.3.118 - 2026-05-09

- Added a lightweight FITS ASCII-table fallback reader in `xstar_atomic.xstar_outputs` for XSTAR products such as `xout_abund1.fits`, so Mg/Ca local-state audits can read `ABUNDANCES`, `COLUMNS`, `HEATING`, and `COOLING` extensions even when `astropy` is unavailable.
- Updated `examples/50_mg_ca_xstar_local_state_audit.py` to use the shared XSTAR output reader and to find `xout_abund1.fits` in both `xstar_runs/mg_ca_triplet_targets/...` and `mg_ca_triplet_targets/...` layouts.
- Corrected the Mg/Ca local-state audit interpretation of XSTAR `ion_parameter`: for the standard Mg/Ca target grid this is the printed log10(xi) run value. The audit now writes `xstar_ion_parameter_raw`, `xstar_log_xi_local`, and derived linear `xstar_xi_erg_cm_s^-1`.
- Verified against the supplied `xstar_runs` archive: all 12 Mg/Ca target-grid cases now pair with `xout_abund1.fits`; explicit Mg XI/Ca XIX xi=3 solver outputs also pair successfully.
- No default solver physics changed; no empirical triplet scale fitting was added.

## v0.3.117 - 2026-05-09

- Improved `examples/50_mg_ca_xstar_local_state_audit.py` discovery for local Mg XI / Ca XIX validation.
- Added repeated `--solver-out-dir` support so one or more solver-output directories can be audited even when `--results-root` points only to an XSTAR target tree or an empty/nonexistent staging directory.
- Added a conservative current-working-directory fallback when `--results-root` has no Mg/Ca solver cases, preventing misleading `cases=0` results during local two-case Mg/Ca tests.
- Added provenance fields to the local-state audit summary: `n_discovered_solver_dirs`, `results_root`, `xstar_runs_root`, `cwd_fallback_enabled`, and zero-case guidance.
- No solver physics changes and no empirical triplet scale fitting. The Mg/Ca prerequisite remains preserving matching XSTAR `xout_abund1.fits` files before interpreting f/i/r, R, or G.

## v0.3.116 - 2026-05-09

XSTAR-local-state audit for Mg XI / Ca XIX validation.

- Adds `examples/50_mg_ca_xstar_local_state_audit.py`, a source-code-first diagnostic that checks whether each Mg XI / Ca XIX solver comparison has the matching XSTAR local gas state before interpreting f/i/r, R, or G.
- The audit searches for the matching XSTAR triplet target CSV and `xout_abund1.fits`, reads the XSTAR `ABUNDANCES` extension when present, and selects the first comparison zone by maximum He-like ion fraction (`Mg_XI` or `Ca_XIX`).
- The selected-zone table reports XSTAR radius, thickness, ionization parameter `xi`, `x_e`, `n_p`, inferred electron density, pressure, temperature in K, heat-balance error, and the He-like ion fraction.
- The audit compares these XSTAR local values against the solver assumptions (`temperature_K`, `electron_density_cm^-3`, `xstar-powerlaw` diagnostic bremsa normalization), and writes recommended rerun conditions when `xout_abund1.fits` is available.
- Adds generic FITS-table helpers in `xstar_atomic.xstar_outputs`: `list_fits_hdus`, `read_fits_table`, and `read_xout_abundances`.
- Updates `examples/47_prepare_mg_ca_xstar_triplet_targets.py` documentation so future Mg/Ca XSTAR runs explicitly preserve `xout_abund1.fits`; this file is required for local-zone validation.
- No triplet scale fitting and no default solver-physics change. The Mg/Ca mismatch should now be addressed by matching XSTAR local zone T/ne/xi and radiation normalization before row-level type-56/type-63/type-68/type-69 rate comparisons.

Validation: `python -m compileall -q src examples tests` passed; selected pytest suite passed in the container.

## v0.3.115 - 2026-05-09

Source-code-first Mg XI / Ca XIX audit bookkeeping update.

- Propagates collision-evaluator diagnostics from `build_collision_rates_for_T()` through `assemble_rate_matrix()` into the transition log, and then into `xstar_like_element_solver_global_bound_bound_matrix_terms.csv` / `xstar_like_element_solver_full_global_matrix_terms.csv`.
- Future Mg XI/Ca XIX solver outputs now retain row-level source-code audit fields for type-63 rows, including the XSTAR record-order mode, ans1/ans2 swap flag, forward/reverse coefficients, legacy energy-order comparison rates, and same-n l-mixing diagnostics.
- Future type-67/type-68 matrix products retain the XSTAR effective-temperature floor diagnostics added in v0.3.113.
- Updates `examples/49_mg_ca_triplet_source_path_audit.py` so it can audit either v0.3.111 or newer Mg/Ca output directories, not only `*v03111*` names.
- Adds explicit XSTAR source-branch mapping for type-56 tabulated effective collision strengths. This is important for Ca XIX, where many triplet-feeding bound-bound collisional rows are `linear_logT_type56` rather than type-63.
- Infers data type from `source_method` when the matrix row does not carry an explicit `data_type` column, so existing v0.3.114 outputs can still be classified as type 56/63/68/69 in the source-path audit.
- No default physics changed. `--resonance-collisional-feed-scale` remains diagnostic-only and defaults to 1.

Validation: `python -m compileall -q src examples tests` passed; selected pytest suite passed in the container.

## v0.3.114 - 2026-05-09

- Source-code-first type-63 alignment: n-changing type-63 collisions now follow the XSTAR `ucalc.f90` record-order convention. The evaluator uses ATDB `idest1/idest2` order for the `anl1/erc` branch, applies the literal `aa1` selector, applies the XSTAR `ans1/ans2` swap when `(nf.gt.ni).or.(lf.gt.li)`, and then maps the forward/reverse rates back to lower->upper and upper->lower coefficients for the Python matrix.
- The previous energy-ordered branch is retained as an audit-only diagnostic and written as `type63_energy_order_*` columns so Mg XI/Ca XIX and C V rows can be compared directly.
- Collision summaries now retain type-63 record-order endpoint labels, quantum numbers, statistical weights, and energies (`type63_initial_*`, `type63_final_*`) to support row-level source-code comparison against XSTAR debug/detail output.
- No empirical scale fitting or default diagnostic scale changes were added. The C V `--resonance-collisional-feed-scale` option remains diagnostic-only and defaults to 1.

## v0.3.113 - 2026-05-08

- Source-code alignment update for He-like type-67/type-68 collisions. The Python `calt67_upsilon` and `calt68_upsilon` evaluators now apply the same `ucalc.f90` temperature floor used by XSTAR before calling `calt67.f90`/`calt68.f90`: `temp = max(T, 2.8777e6 / wavelength_A)`.
- The collision evaluator now reports `xstar_calt67_68_effective_temperature_K` and `xstar_calt67_68_temperature_floor_applied` for type-67/type-68 rows, so Mg XI/Ca XIX audits can verify whether the source-code floor matters for each transition.
- Added `examples/49_mg_ca_triplet_source_path_audit.py`, a source-code-first Mg XI/Ca XIX triplet-path audit. It maps triplet-feeding rows to XSTAR branches (`ucalc` type 63/67/68/69 and type-50 escape), writes detail/summary CSVs, and explicitly avoids empirical scale fitting.
- No default diagnostic scale changes. `--resonance-collisional-feed-scale` remains diagnostic-only and defaults to 1.

Validation: `compileall` passed; selected pytest suite passed with expected skips.

## v0.3.112 - 2026-05-08

- Added `examples/48_sourcecode_first_mg_ca_validation.py`, a source-code-first Mg XI / Ca XIX validation audit.
- The new diagnostic compares solver outputs with XSTAR triplet CSV targets across the log-xi grid, flags xi-invariant solver states, and writes source-method audit rows tied to XSTAR Fortran files (`calc_hmc_element.f90`, `ucalc.f90`, `calt69.f90`, `amcrs.f90`, `velimp.f90`, `calc_emis_ion.f90`).
- This release intentionally does not add or search for empirical best-fit scale factors for Mg XI or Ca XIX. It records that XSTAR source-code alignment of radiation normalization and type-63/type-69 row-level rates should precede any scale interpretation.
- No default solver physics changed.

## v0.3.111 - 2026-05-08

- Added `examples/47_prepare_mg_ca_xstar_triplet_targets.py`, a targeted Mg XI/Ca XIX XSTAR target-plan helper. It writes reproducible XSTAR run scripts, `xout_lines1.fits` conversion scripts, a `xstar_runs/mg_ca_triplet_target_plan.csv` summary, and `xstar_runs/README_mg_ca_triplet_targets.md` containing solver and comparison commands.
- Default Mg/Ca target plans use `ne=1e8 cm^-3` and a log-xi grid `1.5,2.0,2.5,3.0,3.5,4.0`, because high-Z He-like ions may be absent at the C/O reference ionization parameter.
- Updated `examples/43_compare_xstar_detail_populations.py` so any supplied `--xstar-triplet-lines-csv` is used to derive the target f/i/r for the normal `full_global_xstar_tau0_calc_emis_ion` comparison. This prevents Mg XI/Ca XIX validation from silently comparing against the built-in C V target.
- No default population-matrix physics changed. The C V resonance-collisional-feed scale remains diagnostic-only and defaults to 1.

Validation: `compileall` passed; selected pytest suite passed with expected skips.

## v0.3.110 - 2026-05-08

- Fixed the internal `--resonance-collisional-feed-scale-scan` context. v0.3.109 rebuilt the scanned matrix with the requested resonance-feed scale but solved it with the default `explicit-current` topology and no ion-fraction closure, so `xstar_like_element_solver_resonance_collisional_feed_scale_scan.csv` could disagree with the top-level printed `full_global_xstar_tau0_calc_emis_ion` result.
- The scan now passes through the same `--full-global-topology`, `--ion-fraction-closure`, calc-ion-rates audit rows, temperature, and electron density used by the primary full-global solve.
- Added `full_global_topology` and `ion_fraction_closure` columns to the resonance-collisional feed scale scan output for provenance.
- No default physics changes: `--resonance-collisional-feed-scale` still defaults to 1 and remains diagnostic unless explicitly changed.

Validation: `compileall` passed.

## v0.3.109 - 2026-05-08

- Added `xstar_like_element_solver_resonance_collisional_feed_sourcecode_audit.csv`, a source-code-oriented diagnostic for the C V / He-like resonance upper `1s2p 1P1` collisional-feed rows.
- The source-code audit records the type-63/type-69 `ucalc`/`calt*` formula path, source/helper Fortran files, statistical weights, global-index energy gaps, best diagnostic scan scale, and the inferred missing feed rate implied by the C V scale scan.
- Corrected the internal `--resonance-collisional-feed-scale-scan` summary path to prefer the same `full_global_xstar_tau0_calc_emis_ion` comparison used by the top-level printed result, rather than the proxy normalized-topology summary row.
- Expanded the default scan grid from `1,1.5,2,2.5` to `1,1.5,2,2.5,3,3.25,3.5,4` so the C V diagnostic optimum near 3.25 is sampled by default.
- The empirical resonance-collisional scale remains diagnostic only. Default matrix physics remains `--resonance-collisional-feed-scale 1`; no core rates are changed unless the user explicitly supplies a different scale.

Validation: `compileall` passed; selected pytest suite passed with expected skips.

## v0.3.108 - 2026-05-08

- Added a direct collisional feed audit for the He-like resonance/singlet upper level `1s2p 1P1`.
- `examples/42_xstar_like_element_solver_demo.py` now supports `--resonance-collisional-feed-scale` to scale only direct collisional bound-bound matrix routes into `1s2p 1P1`, with paired source-loss terms scaled consistently.
- Added `--resonance-collisional-feed-scale-scan` and new outputs `xstar_like_element_solver_resonance_collisional_feed_audit.csv` and `xstar_like_element_solver_resonance_collisional_feed_scale_scan.csv`.
- The audit identifies data-type 56/63/67/68/69 collisional rows feeding the resonance upper level, reports the evaluated solver/XSTAR-calt path, and records whether the matrix rate has been scaled.
- No default physics changes: the new scale defaults to 1.0.

## v0.3.107 - 2026-05-08

- Extended `examples/46_cv_source_attribution_scan.py` for the C V high-forbidden/low-resonance residual after v0.3.104.
- Added direct bound-bound resonance/singlet feed diagnostics:
  - `cv_direct_bound_bound_source_attribution.csv`,
  - `cv_direct_bound_bound_resonance_singlet_scan.csv`.
- The new direct-bound-bound scan separates radiative/collisional feed into f, i, and r upper levels and adds a first-order 2-D f/r balance scan that boosts the resonance/singlet feed while optionally suppressing direct forbidden feed.
- This remains diagnostic-only: no core population matrix, type-50 line escape, type-71, type-77, type-99, type-53/type-74, or ion-fraction closure changes were made.

## v0.3.106 - 2026-05-08

- Improved `examples/46_cv_source_attribution_scan.py` after the v0.3.105 matrix-resolve scan showed no improvement over the stored C V baseline.
- Added population-weighted source attribution: `cv_population_weighted_source_attribution.csv`. This multiplies off-diagonal gains by the stored source-level population so raw type-71/type-99 rates from nearly unpopulated superlevels are not overinterpreted.
- Added a fixed-population first-order leverage scan: `cv_population_weighted_source_scan.csv`. This reports f/i/r, R, G, and L2 for population-weighted source-family scaling while keeping the v0.3.104 type-50 3P_J->3S1 line-escape/drain balance fixed.
- Added a matrix-recompute-vs-stored-baseline diagnostic in the summary JSON because post-processing a CSV roundtrip can differ from the in-memory `examples/42` solver result.
- No core population matrix/rate physics were changed.

## v0.3.105 - 2026-05-08

- Added `examples/46_cv_source_attribution_scan.py`, a diagnostic C V He-like triplet f/r source-attribution and source-group scan.
- The new example reads an existing `examples/42_xstar_like_element_solver_demo.py` output directory and writes:
  - `cv_source_family_attribution.csv`,
  - `cv_source_group_scan.csv`,
  - `cv_source_attribution_scan_summary.json`,
  - `cv_source_attribution_scan.md`.
- Source attribution now separates the requested C V families: type-71 cascades from `sprlevlt`/`sprlevls`/`superlev`, type-99 sources into `sprlevlt`/`sprlevls`/continuum-alias level 32, type-53 Milne inverse routes, type-74 inverse/direct diagnostic routes, and direct bound-bound radiative/collisional paths into triplet upper levels.
- The default scan focuses on the v0.3.104 C V residual (`f` high, `r` low, `i` nearly matched) and varies `type99_into_sprlevlt`, `type99_into_sprlevls`, and `type71_resonance_singlet_cascade`, while leaving all type-50 population-rate line-escape/drain rows fixed.
- The example can derive the C V target from `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv` using `emit_outward`, or accept explicit `--target-f`, `--target-i`, and `--target-r`.
- No core population matrix/rate changes were made relative to v0.3.104.

## v0.3.104 - 2026-05-08

- Added `--type50-bound-bound-treatment xstar-line-escape` for the XSTAR-like element solver.
- The new mode is a source-code-aligned type-50 population-rate path: when a transition row carries line optical depths, it evaluates the XSTAR `pescl(tau0)` escape channels and uses `A * (ptmp1 + ptmp2)` in the population matrix.
- Because true per-line `tau0` is still not available for every population-matrix transition, the interim fallback treats He-like intra-triplet `1s2p 3P_J -> 1s2s 3S1` drains as optically thin (`tau0=0`, `ptmp1+ptmp2=1.0`) while preserving the previous scalar escape-factor fallback for other missing-tau type-50 lines.
- Added audit columns to type-50 matrix terms: `xstar_tau1_for_type50_escape`, `xstar_tau2_for_type50_escape`, `xstar_cfrac_for_type50_escape`, `type50_line_escape_fallback_used`, and `type50_is_helike_3p_to_3s_drain`.
- Kept `xstar-escape` as the legacy scalar proxy and `xstar-escape-photoexcitation` as the diagnostic pumping proxy. No type-71, type-77, type-99, type-53/type-74 inverse, ion-fraction-closure, or reference-depth postprocessing behavior was intentionally changed.
- Added a focused regression test for `xstar-line-escape` fallback behavior.

Validation in this environment:

```text
compileall: passed
pytest tests/test_type50_line_escape.py tests/test_helike_triplet_balance_diagnostics.py tests/test_xstar_detail_population_compare_example.py tests/test_package_metadata.py tests/test_cli_smoke.py
9 passed, 3 skipped
```

## v0.3.103 - 2026-05-08

- Made `examples/44_diagnose_helike_triplet_balance.py` recover the top-level solver triplet f/i/r summary from available summary products before optional audit diagnostics are read.
- Added fallback readers for `xstar_like_element_solver_summary.json`, `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`, and `xstar_like_element_solver_triplet.csv`.
- Missing optional audit CSVs still produce warnings/placeholders, but the printed case summary no longer degrades to `solver f/i/r=None` when comparison or solver summary products exist.
- No core population matrix, type-99, type-71, type-77, type-53/type-74, ion-fraction, or line-depth physics were changed.

## v0.3.102 - 2026-05-08

- Made `examples/44_diagnose_helike_triplet_balance.py` robust to partially copied or older solver-output directories. Missing diagnostic audit CSVs are now treated as optional for the triplet-balance aggregator: the script records a warning, writes placeholder `missing_optional_audit` rows in the corresponding summary CSV, and continues collating the available triplet, type-50, type-71, type-99, and XSTAR-line-reference information.
- Added regression coverage for the missing-optional-audit path.
- Added the generated C V `ne=1e8` XSTAR triplet reference CSV at `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv` from the local XSTAR 2.59g run/conversion workflow. Its `emit_outward` target is `f/i/r = 0.807706219 / 0.006633342 / 0.185660439`, `R = 121.765`, and `G = 4.38618`.
- No changes were made to the core population matrix, type-99 `calt99/phint53hunt`, type-71 `calt71`, type-77 `calt77`, type-53/type-74 inverse paths, ion-fraction closure, O VII reference-depth postprocess, or C V/O VII solver results.

## v0.3.101 - C V triplet-balance diagnostics and C V XSTAR reference preparation - 2026-05-07

- Added `examples/44_diagnose_helike_triplet_balance.py`, a diagnostic aggregator for full-global He-like solver outputs. It collates triplet component balances, type-50 3P_J -> 3S1 radiative drains, density-scaled 3S/3P collisional coupling, intercombination-feed categories, type-71 cascade feed into f/i/r, and type-99 superlevel-source branch proxies.
- Added `examples/45_prepare_c5_xstar_triplet_reference.py`, a targeted helper to create the C V `ne=1e8` XSTAR run/conversion plan and, when an existing `xout_lines1.fits` is supplied, convert it to `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv`.
- Added regression tests for both new helpers.
- No core population-matrix, type-50, type-53, type-71, type-74, type-77, type-99, ion-fraction-closure, or O VII reference-depth postprocess rates were changed.

## v0.3.100 - Reference-depth scale warning for O VII validation - 2026-05-07

- Changed `examples/43_compare_xstar_detail_populations.py` so the validation-only comparison case `full_global_xstar_reference_depth_emit_outward_calc_emis_ion` no longer silently uses the default XSTAR reference depth scale when `--xstar-triplet-lines-csv` is supplied but `--xstar-reference-depth-scale` is omitted.
- The script still defaults to depth scale `1.0` for backward compatibility, but now prints: `Warning: Using default depth scale 1.0; O VII ne=1e8 validation used 0.37.`
- Applied the same warning behavior to `examples/42_xstar_like_element_solver_demo.py` when `--xstar-reference-lines-csv` is supplied without an explicit `--xstar-reference-depth-scale`.
- Added a regression test confirming that the warning is emitted and that the reference-depth postprocess output is still written.
- No changes were made to the population matrix, XSTAR `calt99/phint53hunt` type-99 path, type-71/type-77 paths, type-53/type-74 inverse paths, or the v0.3.99 O VII corrected result when `--xstar-reference-depth-scale 0.37` is supplied.

## v0.3.99 - O VII XSTAR reference-depth line escape validation - 2026-05-07

- Added optional XSTAR reference-line CSV support for the He-like triplet `calc_emis_ion` postprocessing path.  `examples/42_xstar_like_element_solver_demo.py` now accepts `--xstar-reference-lines-csv`, `--xstar-reference-value-column`, and `--xstar-reference-depth-scale`.
- `build_calc_emis_ion_triplet_emergent_rows()` can now match solver triplet lines to converted XSTAR `xout_lines1` CSV rows by component and wavelength, read `depth_inward`/`depth_outward`, evaluate the XSTAR `pescl` escape channels, and write an additional validation-only summary case named `xstar_reference_depth_emit_outward_calc_emis_ion`.
- `examples/43_compare_xstar_detail_populations.py` can now rerun the O VII comparison against a packaged XSTAR triplet-line target without rerunning the ATDB solver.  It writes `xstar_reference_depth_triplet_postprocess.csv` and, when requested with `--comparison-case full_global_xstar_reference_depth_emit_outward_calc_emis_ion`, reports the reference-depth corrected f/i/r, R, G, and L2 distance to the XSTAR `emit_outward` target.
- For the uploaded v0.3.98 O VII run and `xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv`, using `--xstar-reference-depth-scale 0.37` gives `f/i/r = 0.755947 / 0.157623 / 0.0864298`, `R = 4.79592`, `G = 10.5701`, and `L2 = 9.92e-4` relative to the XSTAR target `f/i/r = 0.756667 / 0.156942 / 0.0863914`.
- This is a validation/postprocessing fix for the O VII resonance line-output mismatch.  It does not change the core population matrix, type-99 physical assembly, type-71/type-77 rates, type-53/type-74 inverse paths, or ion-fraction closure.

## v0.3.98 - Type-99 target-stage destination assembly fix - 2026-05-07

- Fixed the remaining data-type 99 assembly bug for records whose source-audit row is carried on the adjacent parent ion stage while the destination level belongs to the target He-like ion.
- `build_global_superlevel_source_matrix_terms()` now prefers `target_ion_stage` for the destination/superlevel global-index lookup, using `record_ion_stage` only as fallback.
- This allows source-code type-99 rows with `idat(nidt-3)=0` and continuum-alias parent mapping to assemble physical `calt99/phint53hunt` matrix terms for the target-ion destination level instead of being evaluated in the audit but skipped in matrix construction.
- Retains the v0.3.97 default `--type99-source-fallback-mode physical-only`; legacy proxy rows remain disabled unless explicitly requested.
- No intentional changes to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.97 - 2026-05-07

- Fixed the XSTAR `ucalc.f90` data-type 99 continuum-parent mapping for records with `idat(nidt-3) <= 0`.  These now map to `idest2 = nlev`, the target-ion continuum slot, rather than an invalid parent level zero.
- Under the existing `xstar-continuum-alias` / `xstar-continuum-alias-superlevels` full-global topology, that explicit target-ion continuum row aliases to the adjacent parent-ion ground row, matching the XSTAR `calc_hmc_element` `ipmat = ipmat + nlev - 1` convention.
- Added provenance fields for the continuum-alias type-99 path, including `type99_parent_maps_to_target_continuum_alias`, `type99_parent_global_index`, and `type99_parent_mapping_source = ucalc_idat_nidt_minus_3_zero_maps_to_target_continuum_alias`.
- Changed the default type-99 source fallback mode to `physical-only`: if `calt99/phint53hunt` cannot produce physical rates, the old `source_vector_gain_proxy` / scaffold proxy rows are skipped instead of assembled.  The legacy scaffold can be restored only for diagnostics with `--type99-source-fallback-mode legacy-proxy`.
- No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.96 - 2026-05-07

- Fixed the remaining type-99 activation bug exposed by the v0.3.95 C V/O VII reruns.  The type-99 `calt99/phint53hunt` source-code path now looks up target and parent levels from the explicit global element index rather than the legacy per-ion population table, so ATDB superlevels such as C V `sprlevls/sprlevlt` and explicit parent excited levels are available during `ucalc`-style mapping.
- This also provides the statistical weights needed by the reconstructed `phint53hunt` Milne `ans2d` integral, allowing `ans2 = rec*xnx` rows to become matrix-ready when the source-code type-99 closure evaluates successfully.
- Physical type-99 rows should now appear in `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv` with `assembly_status = assembled_global_type99_calt99_phint53hunt` for C V/O VII rows whose `calt99/phint53hunt` closure is valid.
- No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.95 - 2026-05-07

- Fixed XSTAR `ucalc.f90` data-type 99 parent-level mapping after the v0.3.94 `calt99`/`phint53hunt` port.
- Mapped `idat(nidt-3)` to the explicit adjacent parent-ion level in the global matrix instead of using the target-ion continuum proxy row.
- Added parent-level provenance fields for type 99: `type99_ucalc_parent_ion_stage`, `type99_ucalc_parent_ion_level_index`, `type99_ucalc_idest2_local_matrix_level`, and `type99_parent_mapping_source`.
- Removed the incorrect direct-triplet-destination requirement for source-code type-99 assembly; destinations such as O VII levels 30/31 and C V levels 48/49 are allowed when their explicit parent levels exist.
- Physical type-99 rows now assemble as `assembled_global_type99_calt99_phint53hunt` against the explicit parent ion level when `calt99/phint53hunt` rates are available.
- No intentional changes to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.93 - 2026-05-07

- Ported the XSTAR `calt77.f90` evaluator for data-type 77 collisional coupling between ATDB superlevels and spectroscopic levels.
- `calt77` now evaluates the source-code downward superlevel-to-spectroscopic rate `cul` by log-density/log-temperature interpolation and computes the upward spectroscopic-to-superlevel rate `clu = cul * exp(-1.43817e8/(wav*T)) / gg`, including the XSTAR `ucalc.f90` temperature floor `T=max(T,2.8777e6/wav)`.
- Type-77 records are now assembled into the global/Lucy matrix with XSTAR `ucalc` semantics: `ans1=clu` for spectroscopic -> superlevel and `ans2=cul` for superlevel -> spectroscopic.
- Type-71 `calt71` remains active. Type-77 is now a true matrix coupling, not a branch-count proxy.
- The superlevel cascade/coupling matrix CSV now reports `type77_calt77_*` fields and separates type-71 and type-77 source-code provenance.
- No intentional changes to type-50 matrix escape rates, inverse recombination, geometry-derived line optical-depth construction, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.92 - 2026-05-07

- Ported the XSTAR `calt71.f90` evaluator for data type 71 radiative superlevel-to-spectroscopic cascade records.
- Type-71 audit rows now include source-code `type71_calt71_aij_s^-1`, wavelength, log-rate, grid dimensions, bracket indices, and evaluation status.
- Global type-71 cascade matrix assembly now uses `type71_calt71_aij_s^-1` when available instead of the old preview/scaffold value (`2.0` in many C V/O VII rows), with a legacy preview fallback only if calt71 cannot be evaluated.
- Type-71 branching weights now use calt71 A-values, so superlevel cascade branching and the full-global `xstar-lucy` path use the same source-code cascade rates.
- Kept the C V `full_global_xstar_tau0_calc_emis_ion` result as the regression benchmark and made no intentional changes to type-50 matrix rates, inverse recombination, geometry-derived line optical depth, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression, or non-Lucy solvers.

## v0.3.91 - 2026-05-07

- Added `examples/43_compare_xstar_detail_populations.py` for the next validation milestone after the C V triplet match.
- The new comparison utility reads a full-global solver output directory, extracts population rows from `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`, reports the recommended `full_global_xstar_tau0_calc_emis_ion` triplet row, and writes CSV/JSON/Markdown validation products.
- Optional external XSTAR detail population tables can be supplied as CSV or FITS and are matched by ion stage plus level index.
- The utility defaults to C V (`--element C --he-like-stage 5`) and is prepared for the next O VII validation step via `--element O --he-like-stage 7`.
- No intentional solver, matrix, optical-depth, `calc_emis_ion`, type-50, inverse-recombination, or `calc_ion_rates/istruc` physics changes from v0.3.90.

## v0.3.90 - Print and document recommended full-global emergent triplet comparison - 2026-05-07

- Updated `examples/42_xstar_like_element_solver_demo.py --print-summary` so the compact terminal summary reports the recommended full-global emergent line-output row, `full_global_xstar_tau0_calc_emis_ion`, instead of the obsolete simple per-ion triplet baseline.
- The printed summary now includes the recommended comparison case name, full-global emergent `f/i/r`, `R`, `G`, and target-aware L2 distance when that row is available.
- Documented `full_global_xstar_tau0_calc_emis_ion` as the recommended XSTAR C V triplet validation comparison case in the README.
- No intentional changes to population solving, type-50 matrix rates, geometry-derived optical-depth construction, `calc_emis_ion` emergent-line formulas, inverse recombination, `calc_ion_rates -> istruc`, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.89 - Geometry-derived XSTAR type-50 tau0 column for calc_emis_ion - 2026-05-07

- Derives the type-50 line optical-depth column for the `calc_emis_ion.f90` triplet emergent-line path from the XSTAR source-code geometry/transfer quantity `xpx*xeltp*delr` by default.
- Added `--xstar-line-column-source geometry|auto|manual|rt|xstar`; the default `geometry` computes the column from density, abundance, and zone thickness instead of using a hand-tuned equivalent column.
- Added `--xstar-line-zone-thickness-cm`, `--xstar-line-hydrogen-density-cm3`, `--xstar-line-electron-per-hydrogen`, and `--xstar-line-element-abundance` to provide the local XSTAR zone context when available.
- Preserves backward compatibility: `--xstar-line-column-source manual` uses `--xstar-line-column-density`, and `auto` uses a nonzero manual column if supplied.
- Reports the resolved source, `xpx`, `xeltp`, `delr`, geometry column, manual column, and source-code formula in `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`.
- No intentional changes to population solving, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.88 - Fix type-50 line opacity atomic-mass fallback crash - 2026-05-06

- Fixed a v0.3.87 runtime crash in `_xstar_atomic_mass_amu_from_symbol()` caused by an undefined `SYMBOL_TO_Z` fallback reference during the new type-50 line optical-depth context construction.
- The helper now uses the local `_XSTAR_APPROX_ATOMIC_MASS_AMU` table and falls back safely to `1.0` amu for unknown symbols.
- No intentional changes to line optical-depth physics, `calc_emis_ion` emergent-line formulas, population solving, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` behavior, triplet coupling/suppression, or non-Lucy solvers.

## v0.3.87 - XSTAR type-50 line tau0 optical-depth context for calc_emis_ion - 2026-05-06

- Added XSTAR source-code line optical-depth construction for triplet emergent-line post-processing.
- Added CLI options `--xstar-line-column-density`, `--xstar-line-vturb-km-s`, `--xstar-line-cfrac`, `--xstar-line-tau1-fraction`, and `--xstar-line-tau2-fraction`.
- Reconstructs type-50 oscillator strength `flin`, thermal/turbulent width `vtherm`, line cross section `sigvtherm`, lower-level column, directional `tau0(1/2)`, and component-specific `ptmp1/ptmp2=pescl(tau0)` values.
- The emergent triplet comparison now uses `xstar_tau0_calc_emis_ion` rather than the old common matrix escape proxy, while retaining raw and transparent cases for reference.
- No intentional changes to population solving, type-50 population matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, or non-Lucy solvers.

## v0.3.86 - XSTAR calc_emis_ion emergent triplet line construction - 2026-05-06

- Added `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`, which ports the XSTAR `calc_emis_ion.f90` triplet line-output construction for selected He-like triplet records.
- The new table reports the source-code channels `ptmp1` and `ptmp2`, transparent `tau0=0,cfrac=0` output, active matrix type-50 escape/pumping output, and attenuation relative to raw `pop*A*E`.
- Implemented the XSTAR `pescl.f90` line escape function and the `calc_emis_ion.f90` type-4/type-9 channel formulas.
- Uses the `ucalc.f90` type-50 source-code orientation after the internal swap: `ans1` is lower-to-upper photoexcitation/pumping and `ans2` is upper-to-lower escaped decay.
- Adds compact `full_global_raw_pop_A_E`, `full_global_transparent_tau0_calc_emis_ion`, and `full_global_matrix_escape_calc_emis_ion` summary rows to `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`.
- No intentional changes to the population solver, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, triplet coupling/suppression options, or non-Lucy solvers.


- Implements the exact XSTAR `msolvelucy.f90` fixed-point sub-iteration for the full-global `xstar-lucy` path.
- Expands reconstructed two-rate pairs into a four-row `ajisb` list and uses that list for the source-code `riu/rui/ril/rli` `nit2` loop after each condensed superlevel solve.
- Removes the previous nonnegative clipping in the fixed-point update so the update uses the current `x(nn)` directly, matching the source routine.
- Reports fixed-point metadata in `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`: `xstar_msolvelucy_fixed_point_mode`, `xstar_msolvelucy_fixed_point_population_clipping`, `xstar_lucy_nit2_last`, `xstar_lucy_nit2_total`, and final `riu/rui/ril/rli` sums.
- Adds per-level final `xstar_msolvelucy_riu`, `xstar_msolvelucy_rui`, `xstar_msolvelucy_ril`, and `xstar_msolvelucy_rli` columns for population-row inspection.
- Keeps v0.3.83/v0.3.84 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, matrix term construction, triplet suppression/coupling options, or non-Lucy solvers.

## v0.3.85 - 2026-05-06

- Implements the exact XSTAR `msolvelucy.f90` fixed-point sub-iteration for the full-global `xstar-lucy` path.
- Expands reconstructed two-rate pairs into a four-row `ajisb` list and uses that list for the source-code `riu/rui/ril/rli` `nit2` loop after each condensed superlevel solve.
- Removes the previous nonnegative clipping in the fixed-point update so the update uses the current `x(nn)` directly, matching the source routine.
- Reports fixed-point metadata in `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`: `xstar_msolvelucy_fixed_point_mode`, `xstar_msolvelucy_fixed_point_population_clipping`, `xstar_lucy_nit2_last`, `xstar_lucy_nit2_total`, and final `riu/rui/ril/rli` sums.
- Adds per-level final `xstar_msolvelucy_riu`, `xstar_msolvelucy_rui`, `xstar_msolvelucy_ril`, and `xstar_msolvelucy_rli` columns for population-row inspection.
- Keeps v0.3.83/v0.3.84 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, matrix term construction, triplet suppression/coupling options, or non-Lucy solvers.

## v0.3.84 - 2026-05-06

- Implements the direct XSTAR `levwkelement` / `msolvelucy` population-construction step for the full-global `xstar-lucy` solver.
- Reconstructs XSTAR-like `ajisb` two-rate pairs from positive off-diagonal matrix rates and uses those pairs to build the condensed superlevel matrix with the same `rr(level)=x(level)/p(nsup)` weighting used in `msolvelucy.f90`.
- Replaces the previous direct dense-matrix condensation in the Lucy path with source-code-style `p`, `rr`, `bmatsup`, `ipmat2`, and `nsup` bookkeeping.
- Population rows now report XSTAR-style population-construction quantities: `xstar_ipmat2_index`, `xstar_nsup`, `xstar_superlevel_population_p`, `xstar_rr_fraction_within_superlevel`, `xstar_levwkelement_rnise`, `xstar_bileve_departure_coefficient`, and `xstar_xileve_emissivity_population`.
- Summary rows report `xstar_population_construction_mode`, `xstar_msolvelucy_uses_fortran_ajisb_pairs`, `xstar_msolvelucy_n_two_rate_pairs`, `xstar_msolvelucy_n_ajisb_entries_equivalent`, and final `p(superlevel)` JSON.
- Keeps v0.3.83 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, triplet coupling, suppression behavior, or default non-Lucy solvers.

## v0.3.83 - 2026-05-06

- Fixed the `--ion-fraction-closure xstar-calc-ion-rates` interpretation by following the XSTAR source path more closely.  In `calc_hmc_element.f90`, `calc_ion_rates -> istruc` is used before `levwkelement` to determine ion limits and seed structure; `msolvelucy.f90` then solves the condensed superlevel system with a total number-conservation row, not with hard per-ion `istruc` constraints.
- The pre-matrix source-code-gated `pirti`/`rrrti` targets are still reported in `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` and full-global metadata, but they are no longer applied as hard stage-normalization constraints during Lucy iteration.
- `xstar_istruc_ion_fraction_targets_applied` is now `False` for this source-code path, and `xstar_istruc_ion_fraction_targets_application_status` explains that XSTAR uses the rates for ion limits/levwkelement seeding rather than hard Lucy constraints.
- No intentional changes to type-50 rates, inverse-recombination rates, matrix assembly, triplet coupling, suppression behavior, or default `--ion-fraction-closure none` behavior.

## v0.3.82 - 2026-05-06

- Tightened the pre-matrix XSTAR `calc_ion_rates` / `istruc` reconstruction to follow the visible `calc_ion_rates.f90` source-code gates instead of summing every level-resolved bound-free candidate.
- `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` now marks each rate row with `calc_ion_rates_pirti_included`, `calc_ion_rates_rrrti_included`, `calc_ion_rates_total_included`, `calc_ion_rates_equation_role`, and `calc_ion_rates_inclusion_reason`.
- Level-resolved type-53 `phint53` Milne `rrrt`/`ans2`, independent `milne.f90` `alpha*ne`, and type-74 `calt74` weighted-alpha inverse terms are retained as recombination-side candidates but are explicitly excluded from the source-code `rrrti` total unless they are total rate-type 6/8 rows.
- The `--ion-fraction-closure xstar-calc-ion-rates` closure now derives its targets from source-code-gated `pirti`/`rrrti` totals. Candidate totals remain reported separately in metadata for comparison.
- No intentional changes to type-50 escape treatment, topology modes, triplet-coupling suppression, or default `--ion-fraction-closure none` behavior.

## v0.3.81 - 2026-05-06

- Bug-fix release for the v0.3.80 pre-matrix XSTAR `calc_ion_rates` / `istruc` closure diagnostics.
- Fixed `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` writing by returning `calc_ion_rates_istruc_audit` rows from `solve_element_reference(...)`.
- Fixed `xstar_istruc_ion_fraction_targets_json` population for `--ion-fraction-closure xstar-calc-ion-rates` / `calc-ion-rates`; v0.3.80 only applied target extraction for the legacy `xstar-istruc` spelling.
- Added explicit full-global metadata flags: `xstar_istruc_ion_fraction_targets_applied` and `xstar_istruc_ion_fraction_targets_application_status`, so runs report whether stage targets were applied, skipped due to missing/invalid targets, or not requested.
- No intentional solver, rate, matrix-assembly, type-50, inverse-recombination, triplet-coupling, suppression, or physical-behavior changes beyond the requested metadata/audit handoff fixes.

## v0.3.80 - 2026-05-06

- Added `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv`, a pre-matrix XSTAR `calc_ion_rates` / `istruc` reconstruction for adjacent C V/C VI ion-stage closure.
- Added `--ion-fraction-closure xstar-calc-ion-rates` and changed `xstar-istruc` to use the pre-matrix ion-rate audit when available instead of summed full-global matrix entries.
- The audit separates available ion-stage rates into photoionization, radiative recombination, dielectronic recombination, collisional ionization, and three-body recombination contributions from type 53, type 74, type 1, and type 57 diagnostics.
- Full-global solve metadata now records whether ion-fraction targets came from the pre-matrix `calc_ion_rates` audit or the older assembled-matrix fallback.
- Default `--ion-fraction-closure none` remains unchanged; no default solver/rate behavior changes.

## v0.3.79 - 2026-05-06

- Added experimental `--ion-fraction-closure none|xstar-istruc`.
- `xstar-istruc` derives a two-stage XSTAR `calc_ion_rates`/`istruc`-style ion fraction closure from summed inter-stage matrix rates, using `x_low=R/(I+R)` and `x_high=I/(I+R)`.
- The `xstar-lucy` population iteration can now apply these ion-stage targets during the level-population fixed-point update, so the aliased parent continuum/parent ground is constrained consistently with the adjacent-stage balance rather than only by global `sum n_i = 1`.
- Full-global output records `xstar_istruc_ion_fraction_closure_requested`, `xstar_istruc_ion_fraction_closure_status`, `xstar_istruc_ion_fraction_targets_json`, and `xstar_istruc_ion_fraction_flow_rates_json`.
- Existing behavior remains available with the default `--ion-fraction-closure none`.
- Validation: `4 passed, 1 skipped`.

## v0.3.78 - 2026-05-06

Direct XSTAR `ucalc` inverse-recombination implementation step.

- Added `--inverse-recombination-mode xstar-ucalc` as an experimental source-code path, while keeping the older `type53-milne-diagnostic`, `type74-direct-diagnostic`, and `type53-type74` proxy modes for regression.
- In `xstar-ucalc` mode, the type-53 inverse matrix terms are assembled from the source-code `phint53.f90` Milne `ans2` audit (`source_code_phint53_milne_ans2_rrrt_s^-1`) instead of the older scaled detailed-balance proxy.
- In `xstar-ucalc` mode, type-74 inverse terms use the source-aligned `calt74` alpha path with the XSTAR `gglo/ggup` correction; the older direct type-74 inverse proxy is disabled for this mode.
- The assembled type-53 rows are still marked experimental because exact XSTAR runtime arrays (`ethion`, `ethtmp`, `emltlv`) and escape factors are reconstructed, but the full-global matrix now uses the audited source-code closure rather than empirical inverse-rate scaling.
- No intentional changes to type-50 treatment, topology modes, atomic data decoding, triplet-coupling suppression, or final `calc_emis` accounting.

## v0.3.77 - 2026-05-06

Direct XSTAR-code implementation step for the full-global population path.

- Applies the XSTAR `calc_hmc_element.f90` continuum-alias rule at matrix-index level for `--full-global-topology xstar-continuum-alias` and `xstar-continuum-alias-superlevels`: explicit continuum / parent-continuum rows are remapped to the parent-ion ground row before assembling the dense full-global matrix. This is closer to XSTAR's `ipmat = ipmat + nlev - 1` topology than the v0.3.76 superlevel-membership-only alias.
- Initializes the `xstar-lucy` solver with an XSTAR `levwk.f90` / `levwkelement.f90`-style LTE/partition seed when temperature and electron density are available, falling back to statistical weights only if the source-code seed cannot be evaluated.
- Adds output metadata: `xstar_matrix_continuum_alias_count`, `xstar_matrix_continuum_alias_json`, and `xstar_lucy_population_seed_mode`.
- Keeps the existing `explicit-current` mode available for regression comparison. No intentional changes to atomic data decoding, type-50 escape semantics, type-53/type-74 rate values, triplet-coupling suppression, or final line-output accounting.

## v0.3.76 - 2026-05-05

- Added experimental `--full-global-topology explicit-current|xstar-continuum-alias|xstar-continuum-alias-superlevels` for the full-global `xstar-lucy` solver.
- `explicit-current` is the default and preserves v0.3.75 behavior.
- `xstar-continuum-alias` maps continuum / parent-continuum rows into the same condensed Lucy group as the parent ion ground state, following the XSTAR `ipmat = ipmat + nlev - 1` topology.
- `xstar-continuum-alias-superlevels` also groups levels 2..nlev-1 into one excited `nsup` group per ion, matching the source-code `calc_hmc_element.f90` grouping rule.
- The modes are experimental diagnostics; they change only the condensed `xstar-lucy` membership used by the full-global normalized solve, not the assembled matrix terms or default physical/rate behavior.
- Full-global solve output now records `full_global_topology_requested`, `xstar_lucy_topology_mode`, and `xstar_lucy_super_keys_json`.

## v0.3.75 - 2026-05-05

- Added `xstar_like_element_solver_xstar_matrix_topology_audit.csv`, an audit-only comparison between the current explicit Python global-index topology and the visible XSTAR `calc_hmc_element.f90` element matrix topology.
- The audit records the XSTAR `ipmat = ipmat + nlev - 1` continuum-alias rule, parent-ground alias candidates, and the XSTAR `nsup` grouping rule where level 1 is an independent ground group and levels 2..nlev-1 are grouped into one excited-state superlevel.
- Added summary columns showing how many current rows XSTAR would keep as independent rows versus condense or alias.
- No intentional changes to solver behavior, matrix assembly, type-50 treatment, recombination rates, triplet coupling, suppression behavior, or physical-rate behavior.

## v0.3.74 - 2026-05-05

- Bug-fix release for the v0.3.73 Milne-integral audit handoff.
- Fixed `build_type53_type74_ucalc_closure_audit_rows(...)` so its signature accepts the new `type53_rate_audit_rows` keyword passed by `solve_element_reference(...)`.
- This restores the v0.3.71 closure audit and allows the v0.3.73 `phint53`/`milne` raw cross-section-grid join to run in the same demo call.
- No intentional solver, matrix assembly, type-50 treatment, inverse-recombination rate, triplet-coupling, suppression, or physical-rate behavior changes.

## v0.3.73 - 2026-05-05

- Bug-fix release for the v0.3.72 `phint53` Milne integral audit.
- `xstar_like_element_solver_phint53_milne_integral_audit.csv` now reads the full type-53 raw real arrays from `type53_rate_audit_rows` when the later `type53_phint53_rate_audit_rows` do not carry the original cross-section grid.
- Adds `type53_cross_section_source` and `type53_n_cross_section_pairs_available` columns to make this provenance explicit.
- No intentional solver, matrix, type-50, recombination-rate, triplet-coupling, or physical-rate behavior changes.

## v0.3.72 - 2026-05-05

- Added `xstar_like_element_solver_phint53_milne_integral_audit.csv`.
- Ported/source-audited the type-53 recombination-side `phint53.f90` Milne `ans2` integral terms, including the reconstructed LTE seed `rnist`, the `bbnurjp` factor, Boltzmann suppression, and `ptmp1+ptmp2` escape multiplier placeholder.
- Added a Python audit port of XSTAR `milne.f90` and `intin.f90`, matching the debug check in `ucalc.f90` where `alphamilne*xnx` is compared with `phint53` `ans2`.
- The new audit compares the source-code Milne estimates against the current Python type-53 Milne proxy and summarizes f/i/r/other component source rates.
- Diagnostic-only release: no intentional changes to solver behavior, matrix assembly, default `raw-A` behavior, type-50 escape diagnostics, inverse-recombination rates, triplet-coupling logic, suppression behavior, or physical-rate behavior.

## v0.3.71 - 2026-05-05

- Added `xstar_like_element_solver_type53_type74_ucalc_closure_audit.csv`, a source-code-aligned read-only audit for the type-53/type-74 recombination closure that likely controls the remaining C V f/r mismatch after the type-50 escape correction.
- The new audit compares current Python proxy rates against XSTAR `ucalc.f90` semantics for:
  - type 53 `phint53` forward photoionization (`ans1`) and pending Milne inverse recombination (`ans2`) with LTE/Saha/statistical diagnostic ingredients;
  - type 74 `calt74` forward delta-photoionization and inverse DR alpha after the XSTAR `gglo/ggup` statistical-weight correction;
  - older direct type-74 inverse proxy rates versus the source-aligned `calt74` weighted alpha path.
- The audit writes per-record rows plus component summaries for f/i/r/other inverse-source proxies, so f/r source imbalance can be inspected without running another empirical scale scan.
- No solver, matrix assembly, default `raw-A` type-50 behavior, type-50 escape diagnostic semantics, inverse-recombination rates, or physical-rate behavior is intentionally changed.

## v0.3.70 - 2026-05-05

- Added `xstar_like_element_solver_type50_escape_factor_scan.csv`, a controlled diagnostic scan over proxy XSTAR `ucalc` type-50 escape factors.
- Added `--type50-escape-factor-scan`, defaulting to `0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1`.
- The scan rebuilds the bound-bound matrix with `type50_bound_bound_treatment=xstar-escape` for each factor, holds the other primary matrix components fixed, solves the full-global normalized system, and reports f/i/r, R, G, L2-to-target, target-aware deltas, and the summed `1s2p 3P_J -> 1s2s 3S1` raw/escaped rates.
- The default primary run remains unchanged unless the user explicitly selects `--type50-bound-bound-treatment xstar-escape` or `xstar-escape-photoexcitation`.
- The scan is diagnostic only until real XSTAR optical-depth, `pescl`/`pescv`, `bremsa`, and `flinabs` contexts are ported.

## v0.3.69 - 2026-05-05

- Bug-fix release for v0.3.68.
- Fixes the v0.3.67 type-50 `xstar-escape` treatment so the assembled global bound-bound matrix uses the effective escaped rate in `signed_rate_s^-1`, not only in the audit `rate_s^-1` column.
- The affected rows are the off-diagonal gain and diagonal loss entries created by `build_global_bound_bound_matrix_terms(...)`; they now use `effective_rate` and `-effective_rate`.
- The default `raw-A` treatment remains numerically unchanged.
- No intentional changes to type-50 audit semantics, solver normalization, suppression logic, physical rate decoding, or `calc_emis` audits.

## v0.3.68 - 2026-05-05

- Bug-fix release for v0.3.67.
- Fixes `build_global_superlevel_cascade_matrix_terms(...)` so type-71 superlevel cascade rows use `float(rate)` for their signed gain/loss terms instead of the undefined local variable `effective_rate`.
- This restores the full diagnostic demo path when `--type50-bound-bound-treatment xstar-escape` or `xstar-escape-photoexcitation` is used.
- No intentional solver, type-50 treatment, matrix-physics, triplet-coupling, suppression, or physical-rate behavior changes beyond fixing the writer/assembly NameError.

## v0.3.67 - 2026-05-05

- Add `xstar_like_element_solver_type50_ucalc_rate_audit.csv`, a diagnostic audit of XSTAR `ucalc.f90` type-50 bound-bound rate semantics.
- Add `--type50-bound-bound-treatment raw-A|xstar-escape|xstar-escape-photoexcitation`. The default `raw-A` preserves v0.3.66 behavior.
- Add `--type50-escape-factor` and `--type50-photoexcitation-scale` controlled proxy parameters for diagnostic tests of escaped downward decay and lower-to-upper radiative pumping.
- The audit reports raw A-values, proxy `ptmp1/ptmp2`, escaped decay rates, pumping proxies, and the He-like `1s2p 3P_J -> 1s2s 3S1` UV drain sum.
- No intentional default solver, matrix assembly, triplet-coupling suppression, or physical-rate behavior changes when using the default `raw-A` mode.

## v0.3.66 - 2026-05-05

- Fixed `write_element_solver_outputs` so `calc_emis_context_audit_rows` is defined from `result.get("calc_emis_context_audit", [])` before writing `xstar_like_element_solver_calc_emis_context_audit.csv`.
- Added the v0.3.65 context-audit summary into the output summary when rows are present.
- No intentional changes to the solver, matrix assembly, triplet-coupling treatment, suppression behavior, or physical rate behavior.

## v0.3.65 - 2026-05-05

- Added `xstar_like_element_solver_calc_emis_context_audit.csv`, a diagnostic companion to the v0.3.64 transparent `calc_emis_ion` triplet audit.
- The new audit reports available matrix-population runtime context for each f/i/r candidate line: source-population-weighted feed (`alpha`), loss (`gamma`), dominant feed/loss components and records, current transparent `ucalc` placeholders, and abundance/escape placeholders.
- Added component-level required line-accounting multipliers (`target/current` and an intercombination-only scale) to test whether `calc_emis_ion` escape/net-emissivity/strong-line accounting could fix the remaining C V intercombination deficit without changing populations.
- No solver, matrix assembly, suppression treatment, or physical rate behavior is intentionally changed.

## v0.3.64 - 2026-05-04

- Added `xstar_like_element_solver_calc_emis_triplet_audit.csv`, a `calc_emis_ion`-style line-output diagnostic for the He-like triplet.
- The audit reports, for each f/i/r candidate line, lower/upper level populations, A-values, photon energy, transparent `pop*A*E` emissivity, transparent `calc_emis_ion` channel proxies, `ans1/ans2` placeholders, `ptmp1/ptmp2` escape placeholders, and strong-line selection status.
- Added component-level summaries for f/i/r fractions under the transparent `calc_emis_ion` proxy so line-output/accounting differences can be separated from population-balance differences.
- No solver, matrix assembly, suppression treatment, or physical rate behavior is intentionally changed.

## v0.3.63 - 2026-05-04

- Adds a controlled diagnostic switch for the suspicious He-like `1s2p 3P_J -> 1s2s 3S1` type-50 radiative population-transfer drains identified in v0.3.62.
- New CLI option: `--triplet-coupling-treatment normal|audit-only|suppress-3p-to-3s-radiative`.  The default `normal` leaves solver behavior unchanged.  The suppression mode removes only those three off-diagonal gains and their diagonal-loss partners from the primary full-global normalized solve.
- Adds `xstar_like_element_solver_triplet_coupling_suppression_comparison.csv`, which always compares the normal full-global XSTAR-Lucy solution against the diagnostic suppressed solution and lists the exact matrix terms removed in the suppressed case.
- The comparison keeps intercombination-to-ground, forbidden-to-ground, resonance, type-63 collisional `3S1 <-> 3P_J`, type-53, type-71, type-74, type-99, and type-1 terms intact.
- This is a matrix-semantics diagnostic only.  Suppressing type-50 `3P_J -> 3S1` terms is not treated as a physical correction unless follow-up source-code validation proves XSTAR excludes or reclassifies these records.

## v0.3.62 - 2026-05-04

- Added `xstar_like_element_solver_triplet_coupling_record_audit.csv` for source-code-aligned validation of the direct `1s2s 3S1 <-> 1s2p 3P_J` coupling records that dominate the C V intercombination bottleneck.
- The audit selects f/i off-diagonal matrix terms and their diagonal partners, infers type-50 radiative A-value paths versus type-63/67/68/69 density-scaled collisional partners, and reports source-population-weighted feed/loss contributions.
- The summary highlights whether the large `3P_J -> 3S1` radiative-drain terms overwhelm collisional `3S1 -> 3P_J` feeds at the current density and radiation context.
- No solver or physical-rate behavior is intentionally changed.

## v0.3.61 - 2026-05-04

- Added source-code-aligned triplet α/γ diagnostics for the full-global XSTAR-Lucy solution.
- New output: `xstar_like_element_solver_triplet_alpha_gamma_audit.csv`, which reports source-population-weighted `alpha = sum_j n_j R(i<-j)`, loss `gamma`, `alpha/gamma` population proxies, dominant feed/loss terms, and f/i/r component summaries.
- Added triplet emissivity/branching diagnostics.
- New output: `xstar_like_element_solver_triplet_emissivity_branch_audit.csv`, which lists f/i/r candidate line records with upper/lower levels, A-values, branching fractions from decoded lines, solved upper/lower populations, transparent `pop*A*E` emissivity proxies, and the missing XSTAR `calc_emis_ion` contexts (`ucalc` net emissivity, escape probabilities, `cfrac`, and strong-line filtering).
- No solver or physical-rate behavior is intentionally changed; this version is an audit layer to decide whether the remaining low intercombination component is a population-balance issue or a line-emissivity/branching/accounting issue.

## v0.3.60 - 2026-05-04

- Added `xstar_like_element_solver_intercombination_feed_audit.csv`, a detailed audit of all current full-global matrix routes that feed, branch out of, or diagonally drain the He-like intercombination upper levels (`1s2p 3P_J`).
- Added `xstar_like_element_solver_triplet_component_balance_audit.csv`, summarising f/i/r populations, incoming rates, radiative losses, type-71 cascade feeds, type-53 Milne inverse feeds, type-74 inverse feeds, collisional couplings, and type-53 photoionization losses.
- Added summary entries for both new audits to `xstar_like_element_solver_summary.json` and the Markdown summary.
- No solver or physics rates are intentionally changed; v0.3.60 is an audit layer for the low-intercombination bottleneck identified by v0.3.59.

## v0.3.59 - 2026-05-04

- Added a refined inverse-recombination scale scan around the promising C V region found in v0.3.58.
- Added `--type53-milne-refined-scale` and `--type74-inverse-refined-scale` to `examples/42_xstar_like_element_solver_demo.py`.
- Wrote `xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv`, using a narrower default grid: type-53 Milne scales `1e9,3e9,1e10,3e10,1e11` and type-74 inverse scales `1e8,3e8,1e9,3e9,1e10,3e10,1e11,3e11,1e12`.
- Added target-aware columns to the refined scan, including f/r-only L2, intercombination absolute error, i/target ratio, and an intercombination-weighted diagnostic score.
- Kept the XSTAR-Lucy global solver and existing physical/proxy limitations unchanged.

## v0.3.58 - 2026-05-04

- Improves the diagnostic radiation/bremsa context used by the type-53 `phint53` and type-74 `calt74` ports.
- Adds explicit XSTAR-style `epi`/`bremsa`/`bremsint` bookkeeping through `xstar_like_element_solver_bremsa_context.csv`.
- Adds configurable radiation controls to the demo: `--radiation-bremsa-scale`, `--radiation-energy-min-eV`, `--radiation-energy-max-eV`, `--radiation-n-energy-grid`, and `--radiation-powerlaw-index`.
- Extends `--radiation-field-mode` with `powerlaw`/`xstar-powerlaw`; the diagnostic bremsa array is now reused consistently by `phint53` and `calt74`.
- Keeps the full-global XSTAR-Lucy normalization solve unchanged: one row is replaced by `sum_i n_i = 1`, source-vector proxy rows are handled as before, and the solve remains diagnostic until real XSTAR radiation transfer, Milne inverse recombination, opacity/escape probabilities, physical type-99/type-1 rates, and closed continuum balance are ported.

## v0.3.57 - 2026-05-04

- Adds a source-aligned type-74 `calt74` diagnostic path.
- Evaluates both `rate` and `alpha` following `xstarlib/src/calt74.f90`, including delta-resonance interpolation on the diagnostic radiation grid and the `ucalc` statistical-weight correction `alpha *= gglo/ggup`.
- Writes `xstar_like_element_solver_type74_calt74_rate_audit.csv` and `xstar_like_element_solver_global_type74_calt74_matrix_terms.csv`.
- The full-global matrix now prefers the source-aligned type-74 calt74 inverse topology rows when available, falling back to the older type-74 inverse proxy rows otherwise.
- Still diagnostic: absolute forward rates depend on placeholder `bremsa`, and parent-continuum closure remains pending.

## v0.3.56 - 2026-05-04

- Checked the XSTAR source path for inverse recombination before extending the scaffold:
  type-53 calls `phint53`, and XSTAR also compares the recombination output against `milne(temp, ntmp, etmpp, stmpp, ett/13.6, ...)`; type-74 DR-delta rates are handled through `calt74(temp, ncn2, epi, bremsa, ..., rate, alpha)`, with `alpha` scaled by the lower/upper statistical-weight ratio.
- Added independent diagnostic inverse-recombination scale controls:
  `--type53-milne-scale` and `--type74-inverse-scale`.
- The first value of each scale list is used for the primary type-53 Milne/type-74 inverse audit and full-global matrix assembly; the full lists are used by `xstar_like_element_solver_inverse_recombination_scale_scan.csv`.
- Expanded `xstar_like_element_solver_inverse_recombination_scale_scan.csv` from a single placeholder row to independent type-53-Milne scans, independent type-74 inverse scans, and a compact cross-grid when the requested lists are modest.
- This remains a diagnostic/proxy scan: true XSTAR Milne inverse recombination, physical type-74 DR balance, real `bremsa` radiation context, opacity/escape probabilities, and closed continuum balance remain pending.

## v0.3.55 - 2026-05-04

- Added `--inverse-recombination-mode none|type53-milne-diagnostic|type74-direct-diagnostic|type53-type74` to the element-solver demo.
- Added diagnostic type-53 Milne inverse-recombination scaffold outputs:
  - `xstar_like_element_solver_type53_milne_inverse_audit.csv`
  - `xstar_like_element_solver_global_type53_milne_matrix_terms.csv`
- Added diagnostic type-74 direct DR-delta inverse-recombination scaffold outputs:
  - `xstar_like_element_solver_type74_inverse_recombination_audit.csv`
  - `xstar_like_element_solver_global_type74_inverse_matrix_terms.csv`
- Added `xstar_like_element_solver_inverse_recombination_scale_scan.csv` as a first solve-context audit for inverse-recombination modes.
- The inverse terms are included in `xstar_like_element_solver_full_global_matrix_terms.csv` only when enabled by mode, but remain explicitly marked as diagnostic/proxy topology. True XSTAR Milne inverse recombination, physical type-74 DR balance, real radiation context, and closed continuum balance remain pending.

## v0.3.54 - 2026-05-04

- Added a type-53 `phint53` scale scan for the full-global XSTAR-Lucy diagnostic path.
- `--type53-phint53-scale` now accepts comma-separated values, e.g. `1,1e5,1e10,1e15,1e18,1e20`; the first value is used for the primary audit/matrix, and all values are scanned in `xstar_like_element_solver_type53_phint53_scale_scan.csv`.
- Added `xstar_like_element_solver_radiation_normalization_audit.csv` to report the placeholder radiation-grid/bremsa normalization used by the first `phint53` forward-kernel diagnostic and the scale needed to reach reference total rates.
- Added summary metadata for the radiation-normalization audit and `phint53` scale scan.
- The phint53 kernel remains diagnostic: the real XSTAR radiation field, Milne inverse recombination, opacity/escape probabilities, and physical type-99/type-1 rates are still pending.

## v0.3.53 - 2026-05-04

- Fixes the v0.3.52 `NameError: name '_sum_float' is not defined` crash in the type-53 `phint53` audit summary path.
- Adds a module-level `_sum_float(rows, col)` helper used by both `xstar_like_element_solver_type53_phint53_rate_audit.csv` and `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv` summary generation.
- No intentional physics change: XSTAR-Lucy remains the preferred full-global diagnostic solver, and the type-53 `phint53` forward-kernel diagnostic remains a first audit/topology port with placeholder radiation context.

## v0.3.52 - 2026-05-03

- Makes `--full-global-linear-solver xstar-lucy` the preferred/default diagnostic solver for the full-global path.
- Adds the first type-53 `phint53` photoionization-kernel diagnostic port.
- Adds `--type53-phint53-scale` for controlled rate scaling of the new phint53-kernel diagnostic.
- Writes `xstar_like_element_solver_type53_phint53_rate_audit.csv` with decoded type-53 cross-section pairs, placeholder radiation-grid integration diagnostics, and forward photoionization rates.
- Writes `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv` with physical-kernel type-53 matrix topology rows.
- `xstar_like_element_solver_full_global_matrix_terms.csv` now prefers type-53 phint53-kernel rows when any are matrix-ready, and falls back to the older flat proxy topology otherwise.
- The phint53 forward photoionization kernel is ported, but the radiation field is still a placeholder; Milne inverse recombination, opacity/escape-probability context, and the real XSTAR continuum are still pending.

## v0.3.51 - 2026-05-03

- Replaced the v0.3.50 XSTAR-Lucy LU backend implementation with explicit local Numerical-Recipes-style helpers `_xstar_ludcmp`, `_xstar_lubksb`, and `_xstar_mprove`.
- The `--full-global-linear-solver xstar-lucy` path no longer delegates the LU step to `numpy.linalg.solve` and does not use `scipy.linalg.lu`; it now mirrors the XSTAR `leqt2f -> ludcmp/lubksb/mprove` structure more directly.
- Kept the solver diagnostic-only: the matrix still contains proxy/topology type-53, type-99, and type-1 rows rather than physical XSTAR `phint53`, `phint53pl`, or Milne inverse rates.

## v0.3.50 - 2026-05-03

- Added an XSTAR-style Lucy/LU full-global diagnostic solver mode for the normalized C VI+C V proxy-topology matrix.
- New/updated `--full-global-linear-solver xstar-lucy` mode follows the `msolvelucy` structure: initialize normalized populations, build a condensed superlevel matrix using fractional level populations, replace one condensed row by number conservation, solve using an LU-style dense solve plus iterative-improvement corrections, expand back to level populations, and apply a Lucy fixed-point update.
- The full-global normalized comparison CSV now records XSTAR-Lucy diagnostics including the number of condensed states, outer/inner iteration counts, final `diff`/`diff2`, LU-failure count, condensed rank/condition, and iterative-improvement residuals.
- Kept `svd`, `lstsq`, and direct dense solve modes as diagnostic alternatives; the XSTAR source path itself remains LU-based (`msolvelucy -> leqt2f -> ludcmp/lubksb/mprove`), not SVD-based.
- This remains a proxy-topology diagnostic: type-53, type-99, and type-1 rows still use diagnostic proxies rather than physical XSTAR `phint53`, `phint53pl`, or Milne inverse rates.

## v0.3.49 - 2026-05-03

- Checked the XSTAR source-code solver path used by the element population workflow: `calc_hmc_element` calls `msolvelucy`, which forms a condensed superlevel matrix, replaces one row with number conservation, and solves it through `leqt2f` using Numerical Recipes LU routines (`ludcmp`, `lubksb`) plus `mprove` iterative improvement.
- Added rank-aware controls for the diagnostic full-global normalized proxy-topology solve:
  - `--full-global-linear-solver solve|dense|lstsq|svd`
  - `--full-global-rank-deficient-action solve|lstsq|svd|error`
  - `--full-global-negative-population-action keep|clip|error`
  - `--no-full-global-prune-null-rate-levels`
- The full-global normalized comparison now defaults to `solver_requested=svd`, `rank_deficient_action=svd`, `negative_population_action=keep`, and `prune_null_rate_levels=true`, matching the earlier rank-aware He-like/O VII diagnostic-solver style.
- Added solver diagnostics to `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`, including requested solver, SVD cutoff, active/pruned global-index counts, matrix rank before/after normalization, normalization residual, and full-rate-matrix residual excluding the normalization row.
- This remains a diagnostic proxy-topology solve; type-53/type-99/type-1 proxy terms are not physical XSTAR rates.

## v0.3.48 - 2026-05-03

- Added the first diagnostic full global C VI+C V normalized solve.
- New output: `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`.
- The solve assembles a dense matrix over all explicit `global_index` rows from `xstar_like_element_solver_full_global_matrix_terms.csv`.
- Only matrix triplet rows are included; source-vector proxy rows are deliberately excluded for this first normalized solve.
- One row is replaced by the normalization equation `sum_i n_i = 1`, and the diagnostic solution is compared against the existing per-ion C V triplet result.
- The solve remains nonphysical because the matrix still contains proxy topology terms for type-53/type-99/type-1 and does not yet use physical XSTAR `phint53`, Milne, or `phint53pl` rates.

## v0.3.47 - 2026-05-03

- Added the diagnostic full global C VI+C V matrix-topology scaffold for the Python XSTAR-like element solver.
- New output: `xstar_like_element_solver_full_global_matrix_terms.csv`.
- The new unified topology file combines:
  - C VI and C V bound-bound radiative/collisional matrix blocks;
  - C V type-71 superlevel-to-spectroscopic cascade matrix triplets;
  - type-99 parent-continuum-to-superlevel proxy topology rows and source-vector proxy rows;
  - type-53 flat photoionization proxy topology rows;
  - mappable type-1 recombination source-vector rows and parent-continuum topology proxy rows.
- Added a full-global matrix-term summary to the run summary.
- This is still a topology scaffold: no full C VI+C V normalized solve is performed, and type-53/type-99 proxy rows remain nonphysical diagnostics.

## v0.3.46 - 2026-05-03

- Added a diagnostic global bound-bound+type71+type99-proxy+type53-flat-proxy solve comparison.
- New output: `xstar_like_element_solver_global_bound_bound_type71_type99_type53_proxy_solve_comparison.csv`.
- The extended diagnostic solve uses the existing He-like global-index block, nonphysical type-99 source-vector proxy rows, and type-53 flat photoionization proxy sinks via `sink_rates`.
- Type-53 off-diagonal parent-continuum topology rows are still not included in the local He-like solve because the full adjacent-ion parent-continuum population is not solved yet.
- No physical XSTAR `phint53` or Milne inverse-recombination rates are evaluated in this release.

## v0.3.45 - 2026-05-03

- Added a diagnostic flat-field type-53 photoionization-rate proxy.
- Added `--type53-flat-proxy-scale` to `examples/42_xstar_like_element_solver_demo.py`.
- Added `xstar_like_element_solver_type53_flat_proxy_rate_audit.csv`.
- Added `xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv`.
- The proxy maps `M[continuum_or_parent,bound] += rate_proxy` and `M[bound,bound] -= rate_proxy` topology only; it is not assembled into the solved matrix.
- Physical XSTAR `phint53`/Milne rates are still not evaluated.

## v0.3.44 - 2026-05-03

- Fixes a helper-name collision introduced in v0.3.43: the table-building `_global_index_lookup(rows)` helper is preserved for global matrix scaffolds, and the single-row query helper used by the type-53 audit is renamed to `_global_index_lookup_one(rows, ion_stage, level_index)`.
- This fixes the `TypeError: _global_index_lookup() missing 2 required positional arguments` crash when running with `--radiation-field-mode`.
- No physics behavior is intentionally changed; type-53 remains audit/scaffold-only and is not assembled into the matrix.

## v0.3.43 - 2026-05-03

- Adds the first Phase-E type-53 radiation-context scaffold for the XSTAR-like element solver.
- Adds `--radiation-field-mode none|flat|blackbody|table` to `examples/42_xstar_like_element_solver_demo.py`.
- Writes `xstar_like_element_solver_radiation_context.csv` describing the placeholder radiation grid/status needed by future `phint53` and Milne inverse-recombination ports.
- Writes `xstar_like_element_solver_type53_rate_audit.csv`, mapping type-53 records onto explicit bound-level and continuum/parent global indices where possible and reporting missing physical context.
- Does not evaluate physical type-53 photoionization or inverse recombination rates and does not assemble type-53 terms into the matrix.

## v0.3.42 - 2026-05-03

- Fixes the v0.3.41 packaging/signature regression for `--type99-proxy-scale`: `solve_element_reference()` now actually accepts the `type99_proxy_scale` keyword and passes it into the type-99 proxy scale-scan builder.
- Adds no intended physics changes; the type-99 proxy scale scan remains diagnostic-only.

## v0.3.41 - 2026-05-03

- Bug fix: add the missing `type99_proxy_scale` keyword argument to `solve_element_reference()`.
- This fixes the `TypeError: solve_element_reference() got an unexpected keyword argument 'type99_proxy_scale'` raised by `examples/42_xstar_like_element_solver_demo.py` in v0.3.40.
- No physics behavior is intentionally changed; the type-99 proxy scale scan remains diagnostic-only.

## v0.3.40 - 2026-05-02

- Added a diagnostic type-99 proxy source scale scan for the global bound-bound+type71 block.
- `examples/42_xstar_like_element_solver_demo.py` now accepts `--type99-proxy-scale`, with comma-separated lists such as `0,1e-8,1e-6,1e-4,1e-2,1,1e2`.
- New output: `xstar_like_element_solver_type99_proxy_scale_scan.csv`.
- For each scale, the scan multiplies only the nonphysical type-99 `source_vector_gain_proxy` rows, solves the He-like global-index bound-bound+type71 diagnostic block, and reports f/i/r, R, G, L2 distance to the C V target, superlevel population sum, source totals, and solver status.
- Type-99 `phint53pl` physical rates are still not evaluated; this remains a diagnostic proxy-normalization scan and not the final element-wide coupled matrix solve.

## v0.3.39 - 2026-05-02

- Added a diagnostic global bound-bound+type71+type99-proxy solve comparison for the pure-Python XSTAR-like element-solver scaffold.
- New output: `xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv`.
- The comparison assembles the He-like global-index block from bound-bound matrix terms plus type-71 superlevel-cascade triplets, then adds v0.3.38 type-99 `source_vector_gain_proxy` rows to the source vector.
- Reports the resulting f/i/r, R, G, L2 distance to the C V XSTAR target, source-vector totals, superlevel population sum, and level-by-level population differences.
- The type-99 terms remain nonphysical proxy values based on audit coefficients/counts; no `phint53pl` physical rates are evaluated and the full element-wide adjacent-ion matrix is still not solved.

## v0.3.38 - 2026-05-02

- Added a diagnostic global-index type-99 superlevel source scaffold.
- New output: `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv`.
- Maps type-99 source candidates from `xstar_like_element_solver_superlevel_source_audit.csv` onto explicit superlevel `global_index` rows.
- Writes source-vector proxy rows and parent-continuum-to-superlevel matrix proxy rows when a parent-continuum/continuum mapping exists.
- Reports proxy basis, candidate records, type-71 branch fractions, and f/i/r source-weighted branch proxies for each mapped type-99 source group.
- These type-99 terms are not included in the solved matrix; physical `phint53pl`/radiation-field rate evaluation and full parent-continuum population balance are still future work.

## v0.3.37 - 2026-05-02

- Fixed the v0.3.36 output handoff for the diagnostic global bound-bound+type-71 solve comparison.
- `solve_element_reference()` now returns `global_bound_bound_type71_solve_comparison` rows so `write_element_solver_outputs()` writes the populated `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv` instead of an empty CSV.
- No physics behavior is intentionally changed; the extended global C V block remains a diagnostic scaffold and the full element-wide coupled matrix is not solved yet.

## v0.3.36 - 2026-05-02

- Added a diagnostic global bound-bound+type-71 solve comparison for the pure-Python XSTAR-like element solver.
- The element-solver example now writes `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv`.
- The comparison assembles the He-like intra-ion block from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, adds the type-71 superlevel cascade matrix triplets from `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`, rebuilds the same adjacent source vector used by the current per-ion solve, solves the extended global-index block, and reports populations plus f/i/r, R, G, and L2 distance to the C V target.
- This remains a scaffold/equivalence diagnostic: type-70/type-74/type-99 superlevel source terms and full adjacent-ion balance are not yet assembled.

## v0.3.35 - 2026-05-02

- Added the first global-index type-71 superlevel-cascade matrix scaffold for the pure-Python XSTAR-like element solver.
- `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`.
- Type-71 radiative superlevel-to-spectroscopic cascade rows are mapped onto explicit `global_index` states and written as sparse-like triplets: `M[spectroscopic, superlevel] += A` and `M[superlevel, superlevel] -= A`.
- The output reports superlevel/spectroscopic global indices, level labels/kinds, triplet-feed flags, signed rates, skipped rows, and provenance.
- The type-71 terms are scaffold-only and are not yet included in the solved matrix; type-77, type-70, type-74, and type-99 paths remain diagnostic-only.

## v0.3.34 - 2026-05-02

- Added a diagnostic global bound-bound-only solve comparison for the pure-Python XSTAR-like element solver.
- `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_bound_bound_solve_comparison.csv`.
- The comparison assembles the He-like ion intra-ion block from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, rebuilds the same adjacent source vector used by the current per-ion solve, solves the global-index block with the existing statistical-equilibrium solver, and compares populations plus f/i/r, R, G against the old per-ion result.
- This is an equivalence/scaffold test only; the full element-wide C VI + C V matrix is not solved yet.

## v0.3.33 - 2026-05-02

- Added the first diagnostic global bound-bound matrix scaffold for the pure-Python XSTAR-like element solver.
- New output: `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`.
- Maps the current per-ion bound-bound radiative and collisional transition logs onto the explicit `global_index` rows introduced in v0.3.31/v0.3.32.
- For each bound-bound transition `from_level -> to_level`, writes sparse-like matrix triplet rows for the future global element matrix: an off-diagonal gain term `M[to, from] += rate` and a diagonal loss term `M[from, from] -= rate`.
- Includes global row/column indices, source/destination labels, level kinds, transition kind, signed rate, record number, and provenance.
- Adds `global_bound_bound_matrix_terms_summary` to the solver summary.
- This is still a scaffold: the global matrix is not solved yet, and bound-free/recombination/superlevel source terms remain diagnostic-only.

## v0.3.31 - 2026-05-02

- Added an explicit element-wide global state index scaffold for the pure-Python XSTAR-like element solver.
- Writes `xstar_like_element_solver_global_index.csv` from `examples/42_xstar_like_element_solver_demo.py`.
- The global index includes one row per decoded selected-stage level plus explicit parent-continuum placeholder rows where needed for adjacent lower/upper ion stages.
- Columns include `global_index`, `ion_stage`, `level_index`, `level_kind`, `energy_eV`, `stat_weight`, `configuration`, `is_triplet_upper`, `is_superlevel`, and `is_continuum`.
- Adds a `global_index_summary` block to the summary JSON/Markdown.
- This is a structural Step-1 scaffold only; no global element matrix terms are assembled from the index yet.

## v0.3.30 - 2026-05-02

- Fixes the v0.3.29 `--triplet-source-scale` scan crash by adding the missing `_xstar_triplet_target()` helper used to compute diagnostic L2 distances to the built-in C V ne=1e8 f/i/r target.
- Reuses the same target helper for the single-scale type-74 direct triplet-source injection comparison.
- No physics changes: the type-74 direct source scale scan remains diagnostic-only and is not assembled into the final element-wide matrix.

## v0.3.29 - 2026-05-02

- Adds `--triplet-source-scale` to `examples/42_xstar_like_element_solver_demo.py` for diagnostic type-74 direct triplet-source injection.
- Supports one scale or a comma-separated scale list, e.g. `1,1e2,1e4,1e6,1e8,1e10`.
- Writes `xstar_like_element_solver_triplet_source_scale_scan.csv` with baseline, each scaled injected solve, and the C V XSTAR target row when available.
- Reports f/i/r, R, G, scaled injected source rate, solve status, and L2 distance to the XSTAR target for each scale.
- Keeps type-74 source scaling diagnostic-only; it is not the final element-wide XSTAR-like matrix assembly.

## v0.3.28 - 2026-05-02

- Added `--triplet-source-mode none|type74-direct-diagnostic` to `examples/42_xstar_like_element_solver_demo.py`.
- Added an optional diagnostic before/after solve that injects evaluated type-74 direct triplet source rates into the current He-like ion source vector.
- New output: `xstar_like_element_solver_triplet_source_injection_comparison.csv`, reporting baseline f/i/r, type74-source-injected f/i/r, and the C V ne=1e8 XSTAR target comparison.
- The mode is off by default and remains diagnostic-only; it is not the final global element-wide matrix assembly.

## v0.3.27 - 2026-05-01

- Added a diagnostic-only type-74 direct triplet-source evaluator.
- New output: `xstar_like_element_solver_type74_triplet_source_audit.csv`.
- Ports the recombination-alpha portion of XSTAR `calt74.f90` for type-74 records whose recombined/source level directly matches a He-like f/i/r triplet upper level.
- Applies the `ucalc.f90` statistical-weight correction `alpha *= g(recombined)/g(continuum)` with an explicit placeholder continuum weight until a global element matrix includes the parent continuum row.
- Reports candidate source rates into forbidden, intercombination, and resonance upper levels; computes a type-74-only f/i/r source-vector shape; and compares it to the C V ne=1e8 XSTAR target when applicable.
- Type 74 remains diagnostic-only and is not assembled into the population matrix.

## v0.3.26 - 2026-05-01

- Added a diagnostic-only deep type-74 DR-delta linkage audit.
- Added `xstar_like_element_solver_type74_linkage_audit.csv`, with one row per type-74 record.
- Decodes both the parent/final side (`i5`/`i6`) and the recombined/source side (`i7`/`i8`) of type-74 records.
- Classifies whether the recombined/source level is spectroscopic, superlevel, or continuum; reports direct f/i/r triplet-upper candidates; checks same-numeric and valid type-71/type-77 superlevel branch links.
- Reports `possible_feed_route`, `branch_link_status`, and `why_no_branch_found_if_unlinked` so unlinked type-74 records can be diagnosed explicitly.
- Keeps all type-74 DR-delta linkage rows diagnostic-only; no `calt74`, Milne inverse, source, or cascade term is assembled into the element matrix.

## v0.3.25 - 2026-05-01

- Added a diagnostic-only superlevel source × branch audit for type 70, 74, and 99 source-candidate records.
- Added `xstar_like_element_solver_superlevel_source_audit.csv`, grouping source candidates by record ion stage and superlevel and linking them to v0.3.24 type-71/type-77 branch fractions.
- Reported type-70/type-74/type-99 record lists, source-candidate counts, coefficient-magnitude previews, and count-based nonphysical `source_proxy_total`.
- Added source-weighted feed proxy columns such as `source_weighted_type71_feed_f_proxy`, `source_weighted_type71_feed_i_proxy`, `source_weighted_type71_feed_r_proxy`, and preferred-branch proxy columns.
- Kept all source × branch proxy rows diagnostic-only; no type-70/74/99 source or superlevel cascade term is assembled into the element matrix.

## v0.3.24 - 2026-05-01

- Added a diagnostic-only superlevel branching audit for type 71 and type 77 superlevel-to-spectroscopic cascade records.
- Added `xstar_like_element_solver_superlevel_branching_audit.csv`, grouping outgoing superlevel cascade rows by superlevel and reporting `B_f`, `B_i`, `B_r`, and `B_triplet_total`.
- Type 71 branching uses radiative A-value-like weights from the audit rows; type 77 branching is explicitly reported as a count-proxy because the collisional superlevel rate evaluator is not yet ported.
- Added summary JSON/Markdown counts for dominant cascade components, forbidden-favored superlevels, and maximum triplet branching fractions.
- Kept all superlevel branching/cascade rows diagnostic-only; no type-71/type-77 rates are assembled into the element matrix.

## v0.3.23 - 2026-05-01

- Added a diagnostic-only superlevel cascade audit for data types 70, 71, 74, 77, and 99 to the XSTAR-like element solver.
- Added `xstar_like_element_solver_superlevel_cascade_audit.csv`, which reports superlevel route kind, source-code/database provenance, candidate superlevel/spectroscopic levels, triplet-component feed classification, required physical context, and unsafe-to-assemble reasons.
- Added summary JSON/Markdown counts for superlevel cascade records, including type counts and whether any record directly targets He-like forbidden/intercombination/resonance upper levels.
- Kept all superlevel/cascade records diagnostic-only; no type-70/71/74/77/99 rates are assembled into the element matrix.

## v0.3.20 - 2026-05-01

- Added `--type57-energy-convention {ucalc-eth,abs-rlev4,threshold-only,compare}` to `examples/42_xstar_like_element_solver_demo.py`.
- Threaded the selected type-57 convention into the source-code-guided adjacent-ion audit while keeping type 57 diagnostic-only and not assembled into the matrix.
- Added type-57 source-code provenance notes to the audit rows and summary output, documenting the visible `ucalc.f90` `ep=eth` branch versus the `calt57.f90` documented `ep=rlev(4)` convention.
- Added summary counts for nonzero type-57 rates under the `ucalc-eth`, `abs-rlev4`, and `threshold-only` diagnostics.

## v0.3.19 - 2026-05-01

- Added a source-code-guided type-57 energy-convention audit to the XSTAR-like element solver.
- Kept the visible `ucalc.f90` convention (`ep=eth`) as the primary diagnostic columns while adding side-by-side `calt57.f90` documented absolute-`rlev(4)` diagnostics and threshold-only diagnostics.
- Added audit columns such as `type57_ep_ucalc_eth_eV`, `type57_ep_absolute_rlev4_eV`, `type57_abs_rlev4_cion_cm3_s`, `type57_abs_rlev4_rate_forward_s^-1`, `type57_threshold_only_cion_cm3_s`, and `type57_energy_convention_conflict`.
- Type-57 rates remain diagnostic-only and are not assembled into the element matrix.

## v0.3.17 - 2026-05-01

- Added source-code-guided ucalc-style adjacent-ion coupling audit metadata to the pure-Python XSTAR-like element solver.
- Added diagnostic branch annotations for type 53, 57, 74, 95, and 99 records, including their XSTAR `ucalc.f90` roles, required physical context, and matrix role if implemented.
- Added a diagnostic Bryans type-95 collisional-ionization evaluator that reports approximate forward electron-impact ionization rates without assembling them into the production matrix.
- Added inferred XSTAR local level/continuum index columns (`idest1_guess`, `idest2_guess`, etc.) to adjacent-coupling audit rows.
- Added `xstar_like_element_solver_ucalc_adjacent_audit.csv` alongside the previous adjacent-coupling terms CSV.
- Kept type 53/74/99 photoionization/DR/superlevel records unassembled unless a physically complete radiation-field/continuum context is available.

## v0.3.16 - 2026-05-01

- Fixed a v0.3.15 API mismatch in `solve_element_reference()` where the coupling-candidate cataloguer was called with adjacent-coupling assembly options that are only valid for `build_adjacent_coupling_terms()`.
- Restored `examples/42_xstar_like_element_solver_demo.py --adjacent-coupling-mode recombination-source` so the pure-Python element-solver scaffold runs and writes coupling audit outputs instead of failing at startup.
- Kept the separation between catalogued adjacent-ion candidate records and physically assembled/evaluated recombination-source terms.

## v0.3.15 - prototype adjacent-ion coupling assembly - 2026-04-30

- Extended the pure-Python XSTAR-like element solver with explicit adjacent-ion coupling term construction.
- Added `build_adjacent_coupling_terms(...)` in `src/xstar_atomic/xstar_element_solver.py`. It evaluates implemented electron-recombination record classes and assembles them as prototype source-vector terms from the adjacent higher ion into the target ion.
- The implementation intentionally keeps XSTAR-sensitive data types such as 53, 57, 74, 95, and 99 in the audit table unless a rate can be evaluated with the currently available local physics. This avoids treating photoionization cross sections, DR resonance metadata, or collisional-ionization metadata as rates without XSTAR's radiation-field / ucalc context.
- `examples/42_xstar_like_element_solver_demo.py` now exposes `--adjacent-coupling-mode`, `--adjacent-coupling-source-mode`, `--adjacent-coupling-source-levels`, and `--include-charge-exchange`.
- The element-solver output now includes `xstar_like_element_solver_adjacent_coupling_terms.csv` with row-level `assembled` and `assembly_status` diagnostics.

## v0.3.14 - Pure-Python XSTAR-like element solver scaffold - 2026-04-30

- Added `src/xstar_atomic/xstar_element_solver.py`, a pure-Python reference scaffold for an XSTAR-like element-wide population workflow.
- Added `examples/42_xstar_like_element_solver_demo.py` to build ion-block diagnostics, line emissivities, populations, transition logs, and adjacent-ion coupling candidate catalogs.
- The new solver intentionally catalogs adjacent H-like/He-like coupling records but does not yet assemble full XSTAR recombination/photoionization coupling into the matrix. This replaces further empirical fitting with a source-code-guided architecture.
- Exposed `solve_element_reference` in the package namespace for future Python/C++ backend parity tests.

## v0.3.13 - target-aware absolute-response constraints - 2026-04-30

- Added `--absolute-fit-constraint-mode target-aware` to `examples/40_audit_signed_triplet_response.py` and `examples/41_fit_absolute_response_density_grid.py`.
- In target-aware mode, the maximum allowed intercombination fraction is derived from the XSTAR target at each density using `max(target_i_floor, target_i_factor * target_i)`, while remaining capped by any explicit user-supplied maximum.
- Pure-intercombination columns are automatically rejected when the target intercombination fraction is small, but are allowed again at high density when the XSTAR target itself is intercombination-rich.
- Absolute-response fit summaries now record the constraint mode, effective per-density constraints, and target-aware rejection counts so failed or over-filtered density points can be diagnosed.
- Added regression coverage for target-aware constraint helpers and kept explicit `../xstar/data/atdb.fits` examples as non-persistent paths that do not rewrite `datapath`.

## v0.3.12 - 2026-04-30

- Added constrained absolute-response fitting controls to `examples/40_audit_signed_triplet_response.py`.
- Added `--absolute-fit-reject-pure-i`, `--absolute-fit-pure-i-threshold`, and max/min normalized f/i/r column filters so pure-intercombination columns can be excluded from the absolute-response basis.
- Added `--absolute-fit-component-weights` (`uniform`, `auto`, or explicit f,i,r triple) and `--absolute-fit-weight-floor`; `auto` upweights small XSTAR target components to discourage fits that overproduce weak components.
- Propagated the same constrained absolute-response options through `examples/41_fit_absolute_response_density_grid.py` for density-grid scans.
- Added fit diagnostics for component weights, constraint rejection counts, and selected constraints to the JSON/CSV/Markdown outputs.
- Added tests for the constrained absolute-response helper functions and density-grid CLI propagation.

## v0.3.11 - absolute-response density-grid target scan - 2026-04-30

- Added `examples/41_fit_absolute_response_density_grid.py`, which runs the v0.3.10 absolute-response triplet fit across a list of electron densities and aggregates target/predicted f/i/r, R, G, L1/L2 errors, top source levels, and fit status.
- The new density-grid wrapper preserves explicit `../xstar/data/atdb.fits` usage in example commands while relying on the v0.3.9 datapath-safe resolver behavior: ordinary explicit paths are passed through and do not rewrite `datapath`.
- Added per-density command and log capture plus merged CSV/JSON/Markdown outputs for comparing absolute-response behavior over a full XSTAR density grid.
- Added dry-run regression coverage for the new density-grid wrapper.

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

## v0.2.94 - 2026-04-29

- Hardened the exploratory non-O VII He-like density-grid workflow after the C V, Mg XI, and Ca XIX tests.
- `examples/22_o7_solver_source_fit_density_xstar_grid.py` now validates that each converted XSTAR triplet CSV is not only present but also contains usable forbidden, intercombination, and resonance rows with positive emissivity before launching the expensive subprocess chain. Empty Ca XIX converted CSVs now fail early with a clear message instead of reaching the generic `Could not read XSTAR He-like triplet R/G reference` error.
- `examples/20_o7_solver_source_fit.py` keeps legacy `o7_*` filenames for compatibility but also writes ion-specific aliases such as `c5_solver_source_fit_summary.json` and `mg11_solver_source_fit_summary.json` for non-O VII runs.
- `examples/21_o7_solver_source_fit_density_grid.py` now writes ion-specific density-grid aliases such as `c5_solver_source_fit_density_grid.csv` and uses generic He-like labels in its top-level summary/console heading.
- The C V and Mg XI density-grid outputs should still be treated as non-validated exploratory diagnostics: both show large mismatches/unreachable rows with the current solver/source model. O VII remains the only validated suppress-resonance benchmark.
- Added regression tests for rejecting empty converted triplet CSVs and accepting complete C V-style converted triplet CSVs.

## v0.2.93 - 2026-04-29

- Fixed non-O VII He-like exploratory source-fit reporting when one or more solver-side triplet ratios are unavailable.
- `examples/20_o7_solver_source_fit.py` now prints `NA` for missing uniform, fitted, or combined R/G diagnostics instead of aborting with a `NoneType.__format__` error.
- This lets C V density-grid runs continue after reading the XSTAR target even when the current solver-side response has no usable resonance or intercombination diagnostic.
- Added `tests/test_example20_optional_ratio_format.py`.

## v0.2.92 - 2026-04-29

- Generalized solver-side He-like triplet diagnostics in `src/xstar_atomic/solver.py` so combined simultaneous-solver validation can report R=f/i and G=(f+i)/r for C V, Mg XI, Ca XIX, and other He-like ions, not only O VII.
- The solver now classifies He-like triplet components from `upper_label`/level-label strings such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`, while preserving the historical O VII wavelength/level-number fallback.
- Fixed `examples/20_o7_solver_source_fit.py` printing so missing combined-validation R/G values are reported as `NA` instead of raising a `TypeError`.
- Added regression coverage for generic solver-side C V triplet diagnostics.

## v0.2.91 - 2026-04-28

- Added preflight validation for He-like density-grid mapping CSVs before launching the solver-fit subprocess chain.
- Non-O VII density-grid mappings now fail early with a clear message if converted XSTAR triplet CSVs such as `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv` are missing in the current package tree.
- Stale non-O VII mappings that still point to `xstar_test_run/xstar_o7_triplet_lines.csv` are now rejected with an explicit diagnostic and regeneration/copy instructions.
- This avoids the confusing downstream `Could not read XSTAR He-like triplet R/G reference` error when users generated C V, Mg XI, or Ca XIX XSTAR products in a different working directory.

## v0.2.90 - 2026-04-28

- Fixed non-O VII density-grid template generation in `examples/22_o7_solver_source_fit_density_xstar_grid.py`.
- New missing mapping CSVs are now written with ion-specific He-like paths such as `xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv`, not the old O VII placeholder path.
- Updated template messages to instruct users to run the example 32 XSTAR/convert workflow if the listed converted triplet CSVs are missing.
- Added regression coverage for C V template generation so `xstar_c5_density_grid_references.csv` does not point to `xstar_o7_triplet_lines.csv`.

## v0.2.89 - 2026-04-28

- Fixed stale non-O VII He-like density-grid mapping propagation in `examples/22_o7_solver_source_fit_density_xstar_grid.py`.
- The density-grid front end now repairs old candidate-ion mapping CSVs, such as `xstar_test_run/xstar_c5_density_grid_references.csv`, when they still point to the O VII placeholder `xstar_test_run/xstar_o7_triplet_lines.csv` and the correct converted per-density files already exist under `xstar_test_run/<ion>_ne*/`.
- A `.bak` copy of the original mapping is preserved before in-place repair.
- This keeps generated solver-fit directories as outputs only while allowing C V, Mg XI, and Ca XIX density-grid comparisons to reuse converted XSTAR triplet CSVs generated by the v0.2.87 helper.

## v0.2.88 - 2026-04-28

- Generalized the XSTAR He-like triplet reference reader used by `examples/20_o7_solver_source_fit.py` and the density-grid wrappers so converted C V, Mg XI, Ca XIX, and other He-like triplet CSVs can be classified from `lower_level`/`upper_level` labels rather than O VII-only wavelengths.
- Fixed non-O VII density-grid validation runs such as C V, which previously failed with `Could not read XSTAR O VII triplet R/G reference` even when the converted XSTAR triplet CSV contained the correct five He-like components.
- Kept the O VII wavelength fallback for older O VII reference files while using label-based f/i/r classification for all He-like ions.

## v0.2.87 - 2026-04-28

- Added `examples/32_prepare_helike_xstar_density_grids.py`, a run-plan generator for density-specific XSTAR triplet grids for the non-O VII candidate ions identified by the He-like type-69 audit.
- The new helper prepares XSTAR run scripts, conversion scripts, per-ion mapping CSVs, a combined run-plan CSV, and a README for C V, Mg XI, and Ca XIX by default.
- The generated references are placed under `xstar_test_run/<ion>_ne*/` after conversion, so `examples/31_helike_type69_ground_resonance_validation.py` can detect them in follow-up audits.
- This release does not mark any additional ion as validated; it only prepares the external XSTAR density-grid runs needed before include-vs-suppress-resonance comparisons can be trusted beyond O VII.

## v0.2.86 - 2026-04-28

- Fixed the He-like type-69 ground-resonance validation audit for multi-letter element symbols.
  The audit now normalizes symbols before looking them up in the ATDB element table, so
  `Ne`, `Mg`, `Si`, `Ar`, `Ca`, and `Fe` are no longer reported as unknown symbols.
- Added regression coverage for normalized ATDB element lookup in
  `examples/31_helike_type69_ground_resonance_validation.py`.
- Clarified that zero-candidate or pending statuses for non-O VII ions are audit results
  and must not be interpreted as validation until density-specific XSTAR triplet grids are supplied.

## v0.2.85 - 2026-04-28

- Added `examples/31_helike_type69_ground_resonance_validation.py`, a broader He-like type-69 ground-resonance audit/validation-status tool.
- The new example audits candidate type-69 ground-to-resonance records for C V, N VI, O VII, Ne IX, Mg XI, Si XIII, S XV, Ar XVII, Ca XIX, and Fe XXV.
- The tool explicitly marks O VII as validated only when the packaged density-specific `xstar_test_run/o7_ne*/` references are present, and marks other He-like ions as pending until density-specific XSTAR triplet grids are supplied.
- Added tests for ion parsing, resonance-label detection, and validation-status classification.

## v0.2.84 - 2026-04-28

- Packaging cleanup: removed the empty generated-output directory `o7_solver_source_fit_density_xstar_grid/` from the source archive. This directory is produced by examples 21/22/30 and is not a package input.
- Packaging cleanup: removed transient `.pytest_cache/` artifacts from the archive.
- Added regression coverage that generated O VII density-grid output directories are not present in the package tree, while compact density-specific inputs remain under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.
- Clarified that `examples/26_o7_high_density_rate_sensitivity.py --auto-xstar-test-run-grid` is available in v0.2.83+; older working trees such as v0.2.80 do not expose that option.

## v0.2.83 - 2026-04-28

- Standardized the O VII density-dependent XSTAR benchmark inputs under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.
- Added `--auto-xstar-test-run-grid` support to `examples/22_o7_solver_source_fit_density_xstar_grid.py`, so density-specific compact XSTAR CSVs can be discovered automatically without requiring a root-level mapping CSV.
- Updated `examples/26_o7_high_density_rate_sensitivity.py` to accept `--auto-xstar-test-run-grid` or `--xstar-grid-summary-csv` directly, and to reject stale/generated density-grid directories whose `ne=1e12` XSTAR target is inconsistent with the validated density-specific reference.
- Updated `examples/30_o7_density_grid_type69_mode_compare.py` to use packaged `xstar_test_run` density references automatically when no mapping CSV is present.
- Kept generated density-grid solver directories as reproducible outputs, not required package inputs.
- Updated documentation to mark `o7_solver_source_fit_density_xstar_grid/` and related high-density diagnostic directories as outputs and to use the corrected LaTeX user guide baseline.

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
