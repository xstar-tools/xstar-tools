# xstar_solver optional C++ shared-library backend

This directory is intentionally aligned with the accepted future layout:

```text
xstar_tools.xstar.solver.backend
src/xstar_atomic/source_port/cpp/xstar_solver/
```

v0.5.43 exposes one optional C++ kernel for the source-faithful dense
`leqt2f` level-population solve. The Python implementation remains the
reference backend. Build/install environments without a C++ compiler keep the
pure-Python path.

The backend is a plain shared-object library, not a Python extension module.
Python loads it with `ctypes` through `xstar_atomic.source_port.solver_backend`.

## Build manually

From this directory:

```bash
./build_lib.sh
```

or:

```bash
make
```

Both commands build:

```text
src/xstar_atomic/source_port/cpp/xstar_solver/libxstar_solver.so
```

and copy it into the package runtime location:

```text
src/xstar_atomic/source_port/libxstar_solver.so
```

The package loader searches the runtime location by default. You can override
the path with:

```bash
export XSTAR_ATOMIC_SOLVER_LIB=/path/to/libxstar_solver.so
```

## Backend selection

```bash
--solver-backend python
--solver-backend cpp
--solver-backend auto
```

`python` is the source-faithful reference backend. `cpp` requires the shared
library. `auto` uses the shared library if available and otherwise falls back to
Python.

## Development note

Keep the C ABI small and stable. Python owns ATDB loading, runtime state,
radial stepping, diagnostics, and FITS writing. C++ should receive compact
numeric arrays and return compact numeric arrays. This makes the code easy to
move later into the accepted `xstar_tools.xstar.solver` package layout.
