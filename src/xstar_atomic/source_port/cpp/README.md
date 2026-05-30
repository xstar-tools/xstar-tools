# Optional C++ shared-library backend

This directory is intentionally aligned with the accepted future layout:

```text
xstar_tools.xstar.solver.backend
src/xstar_atomic/source_port/cpp/
```

v0.5.45 keeps one optional C++ kernel for the source-faithful dense
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
src/xstar_atomic/source_port/cpp/libxstar_solver.so
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


## v0.5.45 path change

The C++ sources and build files now live directly under `src/xstar_atomic/source_port/cpp/`. The extra `xstar_solver/` subdirectory was removed because the shared-library name `libxstar_solver.so` already identifies the backend purpose. The loader searches both `src/xstar_atomic/source_port/libxstar_solver.so` and `src/xstar_atomic/source_port/cpp/libxstar_solver.so` for source-tree runs.

## v0.5.53 modular rates backend skeleton

The source tree now builds a second plain shared library:

```bash
cd src/xstar_atomic/source_port/cpp
./build_lib.sh
# or: make
```

Artifacts copied beside the Python runtime modules:

- `libxstar_solver.so` — existing level-population solver backend
- `libxstar_rates.so` — new skeleton rates backend ABI

The rates ABI currently verifies loading and dimensions only.  It is the stable
entry point for future compact-array Mg rate-construction kernels and can later
be linked into a standalone `xstar_tools_engine` executable.
