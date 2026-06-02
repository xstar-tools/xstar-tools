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
export XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=1  # default in v0.6.0a18+

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
export XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP=1   # default in v0.6.0a19+
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

`XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP=1` remains the default for the validated Mg direct accumulator, but `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE53_PHOTO_CPP` defaults to `0` because the fast type-53 path changed thermal convergence diagnostics (`h-c(%)` and final iteration column) relative to the a15/type49-only path. Enable it explicitly only for performance experiments until type-53 parity is corrected.

The binemis C++ backend stores only numeric timing fields so output-writer timing totals can be computed safely.
