# xstar_tools 0.6.48.10.1.1 — RRC terminal-state ownership correction

## Starting point

0.6.48.10.1 proved the native accelerated-Python final-recompute bridge is fast but failed public science:

- accepted 10.0 accelerated-Python total: 562.066443 s
- 10.1 candidate total: 503.465702 s
- accepted 10.0 `final_local_recompute`: 70.962107 s
- 10.1 bridge `final_local_recompute`: 9.871208 s
- 10.1 result: REJECT because `xout_rrc1.fits` had 1054 rows instead of the accepted 1052.

The four detail FITS products remained bit-exact. `xout_abund1`, `xout_cont1`, `xout_lines1`, and `xout_spect1` had zero >1% differences versus accepted 10.0. The rejection was isolated to the final RRC table.

## Attribution

A row-by-row identity comparison of the rejected 10.1 RRC table against accepted 10.0 found:

- accepted rows: 1052
- rejected 10.1 rows: 1054
- all 1052 common rows: identity- and numeric-exact
- exactly two extra rows:
  - continuum index 7062: Mg II, data type 49, ion stage 2
  - continuum index 7064: Mg II, data type 99, ion stage 2
- neighboring accepted Mg III Type49 rows 7066–7068 are ion stage 3.

The retained terminal Mg active-stage window is stages 3–12. The two additional rows therefore came from source-inactive Mg II spectral slots.

The 10.1 bridge creates a fresh native fixed-state context. Python/source `calc_hmc_all` retains the active `mml/mmu` ion-stage window into terminal `calc_emisab` and `calc_emis`; a fresh native context can preliminarily widen that window. The same issue also produced tiny inactive Mg II `rcem/oplin` values in the scientific step log, although they did not enter the public strongest-line table.

## 10.1.1 correction

The correction is intentionally in Python bridge projection, before HEATT:

1. Read the live retained `state.local_zone.calc_hmc_all.mml/mmu` stage limits.
2. Decode each continuum slot using immutable derived pointers:
   `npcon -> record -> npar -> parent ion -> ion_element_z/ion_stage`.
3. If a continuum slot belongs to an ion outside the retained source stage window, clear only the `calc_emisab`-owned slot state:
   - `cemab[0:2, slot]`
   - `cabab[slot]`
   - `opakab[slot]`
4. Decode each line slot through `nplin -> record -> npar -> parent ion` and similarly clear source-inactive `calc_emis` slot state:
   - `rcem[0:2, slot]`
   - `oplin[slot]`
5. Project the corrected native workspaces to the existing Python `RadialTransferWorkspace` and run the existing HEATT/STPCUT sequence unchanged.

This is generic across elements and stages. The runtime code does **not** hard-code Mg, indices 7062/7064, or the 3–12 window.

## Frozen science

The following remain byte-for-byte frozen from 10.1/accepted earlier baselines:

- native `final_recompute_bridge.cpp`
- native fixed-state engine
- Type49/53 rate/matrix path
- Type50 opacity/profile kernel
- thermal kernels
- native line-emissivity / accepted C++ `binemis` kernel
- accepted 10.0 `build_binemis_spectrum()` implementation
- Python zone/controller calculation

Only `cpp_backend_final_recompute.py` and writer timing/provenance markers change at runtime.

## Local validation

Readiness result:

```text
V06481011_RRC_ACTIVE_STAGE_MASK_PRESENT=ACCEPT
V06481011_RRC_MASK_USES_SOURCE_MML_MMU=ACCEPT
V06481011_RRC_MASK_USES_DERIVED_POINTERS=ACCEPT
V06481011_RRC_MASKS_CALC_EMISAB_OWNERS=ACCEPT
V06481011_LINE_MASKS_CALC_EMIS_OWNERS=ACCEPT
V06481011_RRC_MASK_BEFORE_WORKSPACE_PROJECTION=ACCEPT
V06481011_FROZEN_101_NATIVE_SCIENCE_SOURCES=ACCEPT
V06481011_FROZEN_101_NATIVE_SCIENCE_MISMATCH_COUNT=0
V06481011_BINEMIS_100_IMPLEMENTATION_FROZEN=ACCEPT
V06481011_NO_BUILD_ARTIFACTS=ACCEPT
V06481011_READINESS_RESULT=ACCEPT
```

Synthetic projection test confirms inactive stage-2 continuum and line slots are zeroed while stage-3 slots remain unchanged.

Benchmark topology attribution:

```text
V06481011_WATCH_CONTINUUM_7062_DATA_TYPE=49
V06481011_WATCH_CONTINUUM_7062_ION_STAGE=2
V06481011_WATCH_CONTINUUM_7064_DATA_TYPE=99
V06481011_WATCH_CONTINUUM_7064_ION_STAGE=2
V06481011_WATCH_CONTINUUM_7066_ION_STAGE=3
V06481011_WATCH_CONTINUUM_7067_ION_STAGE=3
V06481011_WATCH_CONTINUUM_7068_ION_STAGE=3
V06481011_REJECTED_101_EXTRA_SLOTS_STAGE2=ACCEPT
V06481011_NEIGHBOR_ACCEPTED_SLOTS_STAGE3=ACCEPT
V06481011_RUNTIME_FILTER_HARDCODED=NO
V06481011_RRC_TERMINAL_ATTRIBUTION_RESULT=ACCEPT
```

A local native bridge rebuild was attempted, but this execution environment timed out while recompiling the unchanged large `fixed_state_engine.cpp`; there was no compiler error before termination. The C++ numerical sources are unchanged and the blocking full build/run remains the host qualification.

## Blocking host qualification

Use the accepted 10.0 full-test archive as the exact accelerated-Python reference:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.10.1.1)
DATA=/media/linux/mhd/xstar/xstar/data
RUN_SCRIPT=$(realpath mg11_ne1e8/run_xstar.sh)
CACHE_DIR=$(pwd)/v06481011_python_cache

REF100=$(realpath v064810_full_test.tar.gz)
FORTRAN=$(realpath mg11_ne1e8.tar.gz)
PYPURE=$(realpath v0648951_full_test.python_pure_reference.tar.gz)
CPPREF=$(realpath v0648951_full_test.cpp_reference.tar.gz)

rm -rf v06481011_full_test v06481011_full_test.tar.gz "$CACHE_DIR"

"$PACKAGE/run_v06481011_python_accel_rrc_ownership.sh" \
  "$PACKAGE" "$DATA" "$RUN_SCRIPT" "$CACHE_DIR" \
  "$REF100" "$FORTRAN" "$PYPURE" "$CPPREF" \
  v06481011_full_test \
  2>&1 | tee v06481011_full_test.host.log
```

The runner performs both the corrected native bridge run and the forced accepted-10.0 Python final-recompute fallback.

Blocking targets:

```text
V06481011_FORCED_100_ALL_FITS_DATA_BIT_EXACT=ACCEPT
V06481011_FORCED_100_STEP_SCIENCE_LOG_IDENTICAL=ACCEPT
V06481011_ALL_REF100_FITS_DATA_BIT_EXACT=ACCEPT
V06481011_RRC_REF100_DATA_BIT_EXACT=ACCEPT
V06481011_RRC_CANDIDATE_ROWS=1052
V06481011_RRC_ROW_COUNT_RESTORED=ACCEPT
V06481011_AUTO_CPP_FINAL_RECOMPUTE_PROMOTION=ACCEPT
V06481011_RRC_TERMINAL_ACTIVE_STAGE_OWNERSHIP=ACCEPT
V06481011_FINAL_RECOMPUTE_TARGET_LE_10_SECONDS=ACCEPT
V06481011_BINEMIS_100_PROMOTION_FROZEN=ACCEPT
V82_PATCH52094_STRUCTURAL_PRODUCT_PARITY=ACCEPT
V06481011_PUBLIC_SCIENCE_CLOSURE=ACCEPT
V06481011_RESULT=ACCEPT_RRC_TERMINAL_STATE_OWNERSHIP_CORRECTION
V06481011_FINAL_RETURN_CODE=0
```

Expected performance is approximately the 10.1 rejected candidate (~503 s whole accelerated run, ~10 s final recompute), because this correction adds only pointer-table masking over compact source slot arrays before HEATT.
