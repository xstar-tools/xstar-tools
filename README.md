> **0.6.48.12.3.35.1 `ca19_xi2_ne1` attribution hotfix:** diagnostic-only one-model release. It corrects the Python Type-39 oracle to literal FORTRAN `EXP`, captures full owner surfaces at every accepted radial final, uses material-population floors, and traces only order-safe Ca VI Option-15/19 targets. The 22,919 common Option-15 line identities must remain in exact relative sequence while the 83 C++-only identities stay an inventory diagnostic. C++ production physics, Type50 arithmetic, sorting/ranking, `npilev`, energies, science FITS writers, and ABI `6048110` remain frozen.
> **0.6.48.12.3.34 STEP comparator repair:** qualification-only release. No XSTAR models are rerun and the complete C++ production source tree/ABI `6048110` remain byte-identical to 12.3.33. Option 15 now parses arbitrary-width exponents, Option 5 `err` is compared relatively, and Options 1/23 use rank-position normalized-L1 numerical arrays with line identity/order kept as separate diagnostics. Re-analysis of the existing 62 archived logs raises numerical STEP acceptance from 25/62 to 52/62; remaining numerical failures are confined to 10 Option-15 models, with Option 19 also failing only `ca19_xi2_ne1`.
> **0.6.48.12.3.33 all-62 cpp-zone xout_step requalification:** the 12.3.32 AVX2 `tmpop` and `tmpe` preparation experiments are rejected because both paired host repetitions were slower than frozen production. 12.3.33 makes no C++ science or performance change: the 12.3.32 production sources are hash-frozen. The new qualification layer reruns all 62 benchmark models in cpp-zone mode and compares each `xout_step.log` against its FORTRAN counterpart using source-identity alignment, exporting only true numeric >1% discrepancies separately from material-inventory and rank/order diagnostics.

> **0.6.48.12.3.31 Type-50 cursor-production promotion:** the bit-exact 12.3.30 cursor-advance consume path is now the normal AVX2 Type-50 production path. The exact 12.3.30 boundary-hint implementation remains an explicit fallback, while 12.3.25 science/publication, ABI 6048110, profile arithmetic, and sequential opacity-addition order remain frozen. The weaker cached-`next_epi` and local-`updated_bins` micro-experiments are retired from the new qualifier. A diagnostic-only five-phase decomposition measures AVX2 far-wing arithmetic, remaining scalar profile arithmetic, trapezoid arithmetic, boundary/rebin logic, and sequential `opakc` additions using coarse per-profile clocks and shadow work before the real cursor science update.

> **0.6.48.12.3.30 Type-50 boundary-hint promotion:** the independently accepted 12.3.29 likely-false boundary hint is now the normal AVX2 Type-50 consume path; the exact 12.3.28 consume path remains an opt-in qualification fallback and the 12.3.25 scalar science fallback remains intact. Three independent, non-default micro-experiments test cached `next_epi`, local `updated_bins`, and monotone `epi`/`opakc` cursors on `ca19_ne1e8`; register+hint, `ncut==4`, schedule caching, and heavy consume counters are retired from the new qualifier.

> **0.6.48.12.3.29 Type-50 consume-loop localization:** the accepted 12.3.28 inline far-wing AVX2 production path remains the default and 12.3.25 science/publication remains frozen. The failed `ncut==4` shortcut is removed from the new qualifier. Three opt-in, element-generic consume experiments are provided for `ca19_ne1e8`: register-resident source-order consume state with monotone `epi`/`opakc` pointers, an independent likely-false boundary hint, and their combination. A diagnostic counter mode measures consumed points, boundary true/false frequency, boundary events, bins advanced, and maximum span without changing science.

> **0.6.48.12.3.28 Type-50 production optimization:** the bit-exact 12.3.27 one-dispatch small-a far-wing AVX2 path is promoted to the normal standalone-C++ Type-50 kernel on AVX2-capable x86 CPUs, with the accepted 12.3.25 scalar kernel as exact runtime fallback. The rejected schedule-cache experiment is no longer linked. An opt-in generic `ncut==4` consume specialization and optimized-path phase decomposition are provided for `ca19_ne1e8` qualification only.

> **0.6.48.12.3.27 `ca19_ne1e8` Type-50 rebin/profile experiment:** 12.3.25 science/publication and the production Type-50 kernel remain frozen. Two opt-in, element-generic experiments are isolated from production: a source-exact geometry-only rebin-schedule cache and a one-dispatch inline small-a far-wing AVX2 path. The one-model qualifier runs baseline plus both experiments independently, requires nine-FITS bit equivalence, reports schedule/`ncut`/profile-family work, and runs the combined mode only if both individual Type-50 experiments win on the host.

> **0.6.48.12.3.26 `ca19_ne1e8` Type-50 measurement candidate:** 12.3.25 science is frozen, including a byte-identical production `opacity_kernels.cpp`. New code is isolated in a separate experimental translation unit. The targeted qualifier runs only `helike_type69/ca19_ne1e8` in three modes: baseline, phase decomposition (profile values vs trapezoid/rebin vs `opakc` range updates), and opt-in range-update AVX2. The remaining `detal2`/abundance/lines publication closure is tracked separately and is not modified in this candidate.

> **0.6.48.12.3.25 generic terminal-matrix + all-element seed policy:** detailed matrix endpoints now follow literal FORTRAN `min(ipmat,indb(...))`, mapped runtime `xilevg` seeds are preserved without pre-normalization for every element, and the source `calc_hmc_ion` rate-type exclusion gate is generic. Type-50 exact-bound localization is retained with scalar production default; bulk AVX2 is opt-in experimental only. The targeted qualifier runs `ca19_ne1`, `ca19_ne1e8`, O, Mg, and C and requires exact final C++/Python matrix-term presence plus Ca population closure.

> **0.6.48.12.3.24 Type-50 AVX2 + Ca population-state diagnostic:** generic Type-50 temporary-bound localization and runtime-dispatched AVX2 small-a far-wing Voigt evaluation accelerate only independent profile arithmetic; all source-order rebin/opacity accumulation is preserved and a scalar fallback is retained. The two-model qualifier runs `ca19_ne1` and `ca19_ne1e8`, requires nine-FITS bit-data A/B equivalence, reports Type-50 profile timing/work/vectorization, and corrects the diagnostic Python dense-`xilevg` replay while capturing last-DSEC, accepted-boundary, and detail-publication Ca population states.

> **0.6.48.12.3.21.2 diagnostic hotfix:** fixes the fixed-radial replay line-tau domain mismatch by preserving the source-aligned active-line prefix, discarding the native spare capacity slot, and zero-extending it to the full Python source `nlsvn` domain. It remains runnable directly from an unpacked source tree and can resume an existing 12.3.21/12.3.21.1 C++ capture without rerunning the model.

> **0.6.48.12.3.21.1 diagnostic hotfix:** fixes the pure-Python fixed-radial replay import and supports running directly from the unpacked source tree via `PYTHONPATH`; no installation is required. Existing 12.3.21 C++ diagnostic captures can be resumed without rerunning the C++ model.

> **0.6.48.12.3.21 diagnostic-only:** this revision does not change production science. It targets only `helike_type69/ca19_ne1` to attribute the remaining Ca XVIII/Ca XVII excited-level matrix discrepancy at the first published radial recompute and measure literal Type-50 `linopac` gate/work counts before any further repair.

> **0.6.48.12.3.20 targeted npilev + fstepr2 repair:** generalizes the FORTRAN `setptrs`/`npilev` source-ordinal row mapping from the historical Mg-only path to every element, fixing the Ca XVIII `xo01_detail.fits` K-shell tail association, and ports the accepted output-only Type-50 `fstepr2` publication shadow into the generic C++ detail writer to recover ultraweak `xo01_detal2.fits` identities without changing physical line workspaces or `xout_lines1.fits`. `xo01_detal3`, Option 19/`xout_rrc1`, Option 27, and `xo01_detal4` remain frozen.

> **0.6.48.12.3.19 detailed-FITS source inventory repair:** preserves the accepted 12.3.17 Option-19/RRC physics and adds source-role `npilev` identities for `xo01_detail.fits`, literal `fstepr2`/`fstepr3` detail eligibility for `xo01_detal2/3.fits`, and generic live Type53 `ptmp1/ptmp2` direction ownership. Qualification remains single-model `ca19_ne1`; `xout_rrc1`, Option 27, and `xo01_detal4` are frozen.

> **0.6.48.12.3.18 source-detail lifetime repair:** keeps the accepted 12.3.17 post-mapback Option-19/RRC physics, but reconstructs FORTRAN `calc_hmc_all` per-ion global `xilevg` writeback for `fstepr` from a separate compact active-window snapshot. This targets only `ca19_ne1` and requires the Ca XVIII `XSTAR_RADIAL` lifetime 32/32/31/0/0 with <=1% population/LTE parity.

> **0.6.48.12.3.9 O VII generic terminal-seed repair:** promotes the source/Python `x(ipmat2+1)=0.` normalization-row seed to every element before `msolvelucy`; qualification is restricted to `o7_ne1e12` and verifies eval-2/25/26 seed zero plus FORTRAN trajectory/thermal closure.

> **0.6.48.12.3.8 O VII state-transition attribution:** freezes the 12.3.7 Type88 fix and compares Python/C++ call-1 state writeback through evaluation 24 for `o7_ne1e12`. It captures full O `xileve/rnise/bileve` state and selected detailed solves to distinguish LTE/writeback, remapping, and later same-state physics without changing DSEC tolerances or running broader suites.

> **0.6.48.12.3.4 focused O VII/xi=2 attribution-fix stage:** runs only `o7_ne1e12`, `ca19_xi2_ne1e8`, and `mg11_xi2_ne1e8`. The standalone post-loop zero-thickness recompute now activates the live source `tau0/tauc` line-escape state even for two-zone models, matching FORTRAN/final-recompute source lifetime without changing physical DSEC calls. O VII gets an automatic identical-trial pure-Python vs native-C++ call-1/eval-1 attribution that reports the first material element, data/rate family, and source record. No 15/62-model broad run, FITS qualification, or `cpp-all` entry is performed.

> **0.6.48.12.3.3 targeted repair stage:** the all-62 cpp-zone survey found 9 zone/DSEC failures and 9 >1% final thermal failures (3 overlap). `run_v06481233_cpp_zone_failed_targets.sh` reruns only the 15 failed benchmark IDs, freezes the other 47, skips FITS publication comparison, and captures call-1/eval-1, all-evaluation per-element, and final-thermal diagnostics. Exact zones/DSEC and <=1% T4/HTTOT/CLTOT are the blocking gates; option-17 display-only differences are diagnostic in this stage.

> **0.6.48.12.1 all-element C++ phase A:** the production native ATDB lowerer now accounts for all 78 physical UCalc data types (32 preserved legacy native paths, Type52/91 aliases, 44 additive generic paths). `run_v0648121_phase_a.sh` verifies the actual installed Z=1..30 ATDB inventory and captures matching Python/C++ per-element fixed-state ledgers. Numerical fixed-state parity is diagnostic in 12.1 and becomes blocking in 12.2; cpp-zone/controller/product qualification is 12.3. Whole-zone `cpp-all` is not part of this phase.

> **0.6.48.11.9.7 cpp-zone correction:** the persistent C++ zone path now matches Python/FORTRAN `calc_hmc_all` hydrogen entry state, recomputes live radial `log(xi)`, and uses literal `nbinc(13.6)+1` for option-17 depth sampling. `python-cpp-zone-one` also blocks on exact displayed option-17 parity with the accepted 11.9.5 C++-science/Python-zone reference. No Python science or whole-zone `cpp-all` behavior is changed.

> **0.6.48.11.9.6 qualification note:** `python-cpp-zone-one MODEL_ID` advances only zone ownership to the persistent `cpp-zone` context. It requires `XSTAR_CPP_SCIENCE_REFERENCE_DIR` pointing to the accepted C++-science/Python-zone products, and it never enters whole-zone `cpp-all`.

> **0.6.48.11.9.5 qualification note:** `python-cpp-one MODEL_ID` runs C++ scientific backends with `--zone-backend python` and compares against an accepted pure-Python product directory supplied by `XSTAR_PYTHON_REFERENCE_DIR`. No C++ production-zone backend is built or entered by this stage.

## 0.6.48.11.9.5 — restore accepted 11.9.3 Type50 detail-publication shadow

11.9.4 and 11.9.4.1 are rejected publication-shadow experiments.  Both regressed the previously accepted Ca XIX xi=2 `xo01_detal2` inventory from the 11.9.3 state (`12131/12131`, `12131/12131`, `15746/15747`, `15746/15747`) back toward the pre-shadow physical-only inventory.  The 11.9.4 raw-Type50 reconstruction changed the accepted endpoint-active publication semantics, and 11.9.4.1 additionally used the wrong interpretation of the downstream FORTRAN dummy argument named `abel`.

0.6.48.11.9.5 restores `src/xstar_tools/xstar/output_writers.py` **byte-for-byte from accepted 0.6.48.11.9.3**.  Therefore the production publication path again:

- uses `state.plasma.abundances`, matching the physical `ababs=abel*abcosmic` array passed by `xstar.f90` into `xstarcalc` and onward to `calc_emisab_*`;
- retains Type50/rate-4 rows when the source endpoint-abundance gate is active, preserving the accepted zero/negligible FORTRAN row inventory;
- reconstructs only the deterministic output-only stale carry from physical `oplin/source_abund1` for skipped calls;
- never injects stale/uninitialized source state into physical `rcem`, `oplin`, `tau0`, `opakc`, continuum/RRC, equilibrium, rates, or transport;
- contains no raw Type50 `opakb1` source reconstruction helper.

The repeated-`XSTAR_RADIAL` comparator, `python-one` workflow, source-default-REAL column boundary fix, production-zone ABI 6048110, and all other runtime files remain unchanged from the accepted 11.9.3 boundary apart from release/API version metadata.

The Ca XVIII line 88440 omission remaining in accepted 11.9.3 is now treated separately from deterministic Type50 physics: source inspection shows it is the first relevant line in a `calc_emisab_ion` invocation whose endpoint abundances are below the `1.e-34` `ucalc` gate, so the FORTRAN row depends on caller-local undefined/uninitialized `opakb1` publication state.  11.9.4.2 deliberately does **not** invent a physical reconstruction for that undefined-local artifact.

Run only `helike_type69/ca19_xi2_ne1` with `run_v06481195_multimodel.sh ... python-one`.  The immediate regression target is recovery of the accepted 11.9.3 inventory before any decision is made about the single 88440 compatibility row.
## REJECTED 0.6.48.11.9.4.1 Type50 publication-shadow `abel` ownership hotfix

11.9.4 regressed the previously-qualified `xo01_detal2` zero/negligible-row inventory because its new raw Type50 shadow used `state.plasma.abundances` (`ababs=abel*abcosmic`) in the source `calc_emisab_ion` abundance gate.  FORTRAN passes `xeltp=abel(jk)`, the user abundance multiplier.  For the Ca xi=2 case that distinction is `1` versus `2.1e-6`, enough to suppress thousands of source rows and to push line 88440 below the default-REAL `1.e-34` call gate.

11.9.4.1 changes only the output-publication shadow: it reads `state.control["abel"]`, preserves raw Type50 caller-local `opakb1` evolution, applies the caller's literal `oplin=opakb1*abund1` signal test, and enforces the source endpoint-validity predicate before stale state can be consumed.  Physical `rcem`, `oplin`, `opakc`, rates, equilibrium, continuum/RRC arrays, radial transport, and C++ science are unchanged.

Run only `helike_type69/ca19_xi2_ne1` with `run_v064811941_multimodel.sh ... python-one`.  Do not rerun the full smoke yet.

## 0.6.48.11.9.3 detail-line inventory / comparator closure

Pure-Python detail-line output now carries a source-only Type50/rate-4 publication activity shadow so FORTRAN-compatible zero/negligible rows can be retained in exact ATDB/source order without contaminating physical opacity. Qualification compares repeated `XSTAR_RADIAL` extensions by occurrence. Continue using `python-one <model-id>` and qualify the Ca XIX xi=2, xi=3.5, and xi=4 models individually before rerunning the full smoke.

# xstar_tools 0.6.48.11.8

### 0.6.48.11.9.2 pure-Python smoke

Use `run_v06481191_multimodel.sh ... python-smoke` to run the canonical 11-model smoke set using only the Python source-port backends. This stage is intentionally independent of standalone-C++ qualification and compares each Python result directly with the FORTRAN authority.


0.6.48.11.8 is a diagnostic-only follow-up to the accepted 0.6.48.11.7.1 frozen-Mg hotfix. The 11.7.1 host smoke restored all nine frozen `mg11_ne1e8` FITS products bit-exact while leaving the carbon trajectory unchanged. The remaining C V problem is therefore attributed downstream of preliminary active-window selection: the call-1 compact carbon solve converges to a C III lower-level population near 0.782, which drives Type50 record 5740 and the 12.709136 eV first-STEP opacity.

This release does **not** change the carbon matrix, Lucy-style normalization, Type50, GSSMOOTH, STEP, or generic Type7 physics. It adds a call-1 carbon solve attribution surface after the solve has completed.

## Standalone smoke

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.8)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648118_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648118_multimodel.sh" \
  "$PACKAGE" \
  "$DATA" \
  "$RUNS" \
  "$FORTRAN" \
  "$MGREF" \
  "$OUT" \
  standalone-smoke \
  2>&1 | tee v0648118_standalone_smoke.host.log
```

Do not run `standalone-all` until the smoke reaches 11/11 ACCEPT.

## C call-1 compact solve attribution

For `helike_type69/c5_ne1e10`, the runner sets `XSTAR_V0648118_C_SOLVE_ATTRIBUTION_DIR` and the fixed-state engine writes the final call-1 carbon diagnostic state into six CSV files:

- `manifest.csv`: active rows/superlevels/ions, normalization row, solve method/status, residuals, fixed-point iteration counts, and contribution inventory.
- `rows.csv`: compact/full/global identity, source ion stage, superlevel, stage-ground and normalization flags, and populations at each solve phase.
- `stage_totals.csv`: preliminary `xitp` versus final solved population by carbon ion stage, including the fully stripped state.
- `matrix_terms.csv`: exact native committed matrix terms with source position, record, rate/data type, row/stage/superlevel endpoints, coefficients, fixed-point branch, and high-ion/terminal ownership flags.
- `fixed_point_rows.csv`: reconstructed `riu/rui/ril/rli` budgets, raw and normalized fixed-point candidates, and final row deltas.
- `condensed_matrix.csv`: final condensed superlevel matrix after normalization-row replacement, including stage/terminal ownership of each superlevel.

The writer runs only after the carbon element solve has completed and never mutates production arrays.

## Frozen contracts

- Frozen `mg11_ne1e8` retains the 11.7.1 reference-only preliminary-Type7 compatibility path.
- Generic models retain the literal Type7 source endpoint predicate from 11.7.
- The frozen Mg all-nine-FITS bit-exact comparator remains blocking.
- Production-zone ABI remains 6048110.
- The runtime STEP diagnostic marker prefix remains `V0648117_STEP_*`; 11.8 qualification parses that intentionally frozen prefix.

## 0.6.48.11.9.2 single-model pure-Python qualification

The Python radial controller now preserves source default-REAL precision for the input column limit.  Iterative multi-element repair should use `run_v06481192_multimodel.sh ... python-one <model-id>` rather than rerunning the full 11-model smoke after each patch.  `XSTAR_QUALIFICATION_CACHE_DIR` may point at an accepted existing `python_cache` directory.

### Full cpp-zone benchmark survey (0.6.48.12.3.2.2)

`run_v064812322_cpp_zone_all_benchmarks.sh` runs all 62 benchmark models with the production cpp-zone backend and compares zone/DSEC trajectories, print option 17, final thermal totals, and diagnostic products directly against FORTRAN. It emits dedicated CSV records for trajectory and >1% thermal failures and can resume an interrupted run with an optional `--resume` argument.

### O VII call-1 DSEC attribution (0.6.48.12.3.5)

`run_v06481235_o7_call1_dsec_attribution.sh` is a single-model diagnostic run for `helike_type69/o7_ne1e12`. It keeps the accepted 12.3.4 xi=2 final-thermal correction frozen and does not rerun xi=2 or the wider benchmark suite.

The runner captures the complete source-faithful pure-Python and cpp-zone call-1 DSEC sequences. For oxygen it compares stage fractions, preliminary ionization/recombination rates, data/rate thermal families, source-semantic record contributions, compact populations, trial `T`/`xee`, `HMCTOT`, and charge residuals. Record alignment uses ion stage rather than implementation-specific ion index.

## 0.6.48.12.3.5.2 O VII DSEC snapshot hotfix

12.3.5.2 fixes the evaluation-2 crash in the O VII pure-Python DSEC attribution capture. In production-memory mode the retained prior result is intentionally reduced, so full-input snapshots now take `global_level_index_by_key` from the current mutable DSEC runtime—the state that actually enters the next trial. O science and the accepted xi=2 fix remain frozen. Use `run_v064812352_o7_call1_dsec_attribution.sh ... --resume` against the existing 12.3.5 output to reuse the completed C++ run.

## 0.6.48.12.3.5.1 O VII attribution hotfix

The 12.3.5 O-only attribution workflow is repaired without changing science. Use `run_v064812351_o7_call1_dsec_attribution.sh`; `--resume` can reuse a completed 12.3.5 cpp-zone output and rerun only the failed Python capture/comparison.

## 0.6.48.12.3.6 O VII eval-1 detailed solve attribution

This release freezes production science and adds a one-model diagnostic that compares the pure-Python and standalone-C++ O VIII/O VII detailed population solve at the identical first DSEC trial state. Use `run_v06481236_o7_eval1_solve_attribution.sh`; the comparison stops at the first material basis/input/matrix/Lucy/fixed-point/final-population locus.

### 0.6.48.12.3.7 targeted O VII Type88 qualification

Use `run_v06481237_o7_type88_fix.sh` for the one-model `o7_ne1e12` repair gate. This release corrects a second `/10` reduction of the already-reduced Type88 `phextrap` caller capacity and does not run the broader benchmark suites.
