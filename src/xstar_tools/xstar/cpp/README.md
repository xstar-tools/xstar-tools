# xstar_tools.xstar C++ backend libraries

This directory is the single location for optional XSTAR C++ backend sources and shared libraries.

```text
src/xstar_tools/xstar/cpp/
  level_population.cpp   -> libxstar_solver.so
  rate_kernels.cpp       -> libxstar_rates.so
  matrix_kernels.cpp     -> libxstar_matrix.so
  build_lib.sh
  Makefile
```

Do not copy the built `.so` files into `src/xstar_tools/xstar/`.  The Python loaders search this `cpp/` directory first and the build scripts now leave the artifacts here.

## Build

From this directory:

```bash
./build_lib.sh
# or
make
```

Both commands build only:

```text
src/xstar_tools/xstar/cpp/libxstar_solver.so
src/xstar_tools/xstar/cpp/libxstar_rates.so
src/xstar_tools/xstar/cpp/libxstar_matrix.so
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

Thermal/statistical-equilibrium matrix backend.  Current implementation name after v0.6.0a10:

```text
xstar_matrix_mg_ion_direct_accumulator_v7
```

It contains:

- Mg type-7 matrix-term construction from Python-evaluated `ucalc` rows.
- Dense matrix fill helpers.
- Mg type-51 C++ `ucalc` + matrix-term construction.
- Mg ion source-pointer traversal.
- Experimental Mg ion direct accumulator for selected simple payloads.

The direct accumulator is opt-in until full product parity and runtime improvement are confirmed.

## Backend selection and library overrides

Normal runs use `auto` backend selection through the Python wrapper.  Explicit shared-library overrides are available when needed:

```bash
export XSTAR_ATOMIC_SOLVER_LIB=/path/to/libxstar_solver.so
export XSTAR_ATOMIC_RATES_LIB=/path/to/libxstar_rates.so
export XSTAR_ATOMIC_MATRIX_LIB=/path/to/libxstar_matrix.so
```

For source-tree runs, no override should be needed when the libraries are built in this directory.

## Development rules

- Keep all C++ backend files in this directory.
- Keep the ABI C-compatible and small.
- Prefer coarse ion/element-level kernels over per-record `ctypes` calls.
- Keep Python fallbacks available.
- Do not enable experimental kernels by default until they show both parity and timing improvement.
