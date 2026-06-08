# xstar_tools.xstar C++ backend libraries

This directory is the single location for optional XSTAR C++ backend sources and shared libraries.

```text
src/xstar_tools/xstar/cpp/
  level_population.cpp   -> libxstar_solver.so
  rate_kernels.cpp       -> libxstar_rates.so
  matrix_kernels.cpp     -> libxstar_matrix.so
  line_emissivity.cpp    -> libxstar_emissivity.so
  build_lib.sh
  Makefile
```

Do not copy the built `.so` files into `src/xstar_tools/xstar/`.  The Python loaders search this `cpp/` directory first; keep shared objects in the cpp/ directory and the build scripts now leave the artifacts here.

## Build

From this directory:

```bash
./build_lib.sh
# or
make
```

Both commands build only in this directory:

```text
src/xstar_tools/xstar/cpp/libxstar_solver.so
src/xstar_tools/xstar/cpp/libxstar_rates.so
src/xstar_tools/xstar/cpp/libxstar_matrix.so
src/xstar_tools/xstar/cpp/libxstar_emissivity.so
```

## Libraries

### `libxstar_solver.so`

Level-population / matrix-solve backend.  Current implementation name reported by provenance:

```text
xstar_solver_so_leqt2f_v1
```

It accelerates the source-faithful `leqt2f`-style level-population solve while keeping the Python solver as fallback.

### `libxstar_rates.so`

Rates/emissivity/opacity helper backend.  Current implementation name reported by provenance:

```text
xstar_rates_mg_type7_type4_linopac_type50_voigt_v1
```

It contains selected Mg line/emissivity/opacity helpers, including type-4 line emissivity, line-profile/linopac work, and type-50 related kernels.

### `libxstar_matrix.so`

Thermal/statistical-equilibrium matrix backend.  Current implementation name after v0.6.0a14:

```text
xstar_matrix_mg_ion_direct_accumulator_type49_type53_v11
```

It contains:

- Mg type-7 matrix-term construction from Python-evaluated `ucalc` rows.
- Dense matrix fill helpers.
- Mg type-51 C++ `ucalc` + matrix-term construction.
- Mg ion source-pointer traversal.
- Experimental Mg ion direct accumulator for selected simple payloads.
- Experimental Mg rate_type=7/data_type=49 photoionization-style direct accumulator.

The direct accumulator is opt-in and coverage-gated until full product parity and runtime improvement are confirmed.  The v0.6.0a11 path avoids the a9/a10 whole-ATDB per-ion allocation by caching compact arrays and sizing output buffers from the active ion source-record count.  v0.6.0a14 adds an experimental rate_type=7/data_type=49 photoionization branch that decodes packed type-49 cross-section payloads and evaluates a phint53-like rate integral in C++.


Useful experimental controls:

```bash
# Keep disabled for normal runs unless testing the direct accumulator.
export XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=1  # opt-in in v0.6.0a21+

# Default coverage gate; prevents low-coverage experiments from slowing runs.
export XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_MIN_SUPPORTED_FRACTION=0.05
export XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_MIN_RECORDS=8
export XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_RATE7_ONLY=1

# Enable the experimental type-49 photoionization branch inside the direct accumulator.
export XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_CPP=1
export XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_MIN_RECORDS=1
```


### `libxstar_emissivity.so`

Output/emissivity backend.  Current implementation name reported by the C ABI:

```text
xstar_emissivity_binemis_profile_v1
```

It moves the `binemis` strong-line profile loop from Python into C++ while Python still performs source-faithful line ranking and FITS/table packing.  This targets the post-a18 bottleneck:

```text
final_product_build.spectrum.binemis_profile_seconds ~43-44 s
```

Useful controls:

```bash
export XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP=1   # opt-in in v0.6.0a21+
export XSTAR_ATOMIC_EMISSIVITY_LIB=/path/to/libxstar_emissivity.so
```

## Backend selection and library overrides

Normal runs use `auto` backend selection through the Python wrapper.  Explicit shared-library overrides are available when needed:

```bash
export XSTAR_ATOMIC_SOLVER_LIB=/path/to/libxstar_solver.so
export XSTAR_ATOMIC_RATES_LIB=/path/to/libxstar_rates.so
export XSTAR_ATOMIC_MATRIX_LIB=/path/to/libxstar_matrix.so
export XSTAR_ATOMIC_EMISSIVITY_LIB=/path/to/libxstar_emissivity.so
```

For source-tree runs, no override should be needed when the libraries are built in this directory.

## Development rules

- Keep all C++ backend files in this directory.
- Keep the ABI C-compatible and small.
- Prefer coarse ion/element-level kernels over per-record `ctypes` calls.
- Keep Python fallbacks available.
- Do not enable experimental kernels by default until they show both parity and timing improvement.


## v0.6.0a20 parity note

`XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP`, type-49/type-53 direct accumulators, pre-matrix photo shortcuts, and C++ binemis are opt-in in v0.6.0a21 because original-XSTAR parity, not Python-version-to-Python-version parity, is now the default gate.

The binemis C++ backend stores only numeric timing fields so output-writer timing totals can be computed safely.

## v0.6.0a21 parity-first defaults

C++ shared libraries remain buildable in the flat cpp directory, but the benchmark wrapper now defaults new C++ physics and output accelerators to opt-in only until original-XSTAR xout_step.log and FITS parity gates pass.  Enable individual paths explicitly for experiments, for example `XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=1`, `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_CPP=1`, `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE53_PHOTO_CPP=1`, or `XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP=1`.
## v0.6.29 engine orchestration shadow

`libxstar_engine.so` exports `xstar_engine_eval_mg_rate_payload_shadow_v1`, an evaluation-level diagnostic ABI for compact Mg rate-payload records. It supports rate/data families 4/50, 3/51, 3/63, and 42/88, returns four compact matrix/heating terms per valid record, and is never product-active in v0.6.29. The accepted path supplies exact scalar channels and remains the sole live owner.


## v0.6.31 native scalar-rate shadow

`libxstar_engine.so` ABI version 4 adds
`xstar_engine_eval_mg_rate_payload_native_scalars_v1`. The diagnostic call
computes native scalar channels for Mg rate/data 3/63 and 42/88 from compact
quantum/plasma context, raw type-88 cross-section pairs, and one shared live
radiation grid. It remains shadow-only: accepted scalar rates and matrix terms
are the sole live source.

## v0.6.33 Type-88 full-grid hotfix

`libxstar_engine.so` ABI version 5 preserves the accepted mixed-grid Type-88 contract: the reduced mapped-grid point count limits `phextrap` extension, while the full high-resolution `epi_eV` / `bremsa` arrays are used for continuum integration. Reduced-grid integration is not a qualifying fallback.
## v0.6.33 Type-63 exact-order diagnostic

`libxstar_engine` ABI 6 adds no live product path. It refines the native 3/63 scalar shadow with Python-equivalent operation grouping and a static CPython `math.lgamma` binary64 table through integer argument 256. Feature bit 6 reports this exactness refinement.



## v0.6.37 native Type-50 and ordered verification

`libxstar_engine.so` ABI 8 extends `xstar_engine_eval_mg_rate_payload_native_scalars_v1` with native rate 4/data 50 scalar channels. The diagnostic Python boundary performs full reverse verification and order-preserving row replacement; the C++ ABI itself remains a compact scalar and row-construction engine.
