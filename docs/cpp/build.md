# Native build

## pip/wheel build

Milestone 8 makes setuptools the authoritative PEP 517 backend while preserving
the already-qualified native Makefile and compiler defaults.

On Linux:

```bash
XSTAR_TOOLS_NATIVE=required python -m build --wheel
```

The build hook copies the native source into an isolated temporary directory,
runs the retained Makefile there, and copies **only runtime artifacts** into the
wheel. It does not build in or contaminate the source checkout.

The installed native payload contains the shared libraries required by the
public C++ modes, `xstar_cpp`, `xstar-cpp`, `constants.def`, public ABI headers,
and `native_build.json`. C++ implementation sources, object files, Makefiles,
historical qualification data, and caches are not wheel payload.

Build policy is controlled by:

```text
XSTAR_TOOLS_NATIVE=auto|required|off
XSTAR_TOOLS_NATIVE_JOBS=N
```

`auto` is the default. In 0.6.71 it enables native compilation on Linux and
selects Python-only packaging on unsupported platforms. `required` converts an
unavailable native prerequisite into a build failure. `off` creates a pure
Python wheel.

## Source checkout build

The direct source build remains available and uses the same Makefile:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

Requirements:

- a C++17 compiler;
- CFITSIO development headers/libraries;
- `python3-config` for the Python backend plugin;
- a standard library with C++17 filesystem support.

For GNU/libstdc++ compatibility the retained Makefile exposes:

```text
FILESYSTEM_LIBS ?= -lstdc++fs
```

Override it only when required by the host toolchain:

```bash
make -C src/xstar_tools/xstar/cpp FILESYSTEM_LIBS= -j2
```

The packaging layer does not alter the frozen default scientific compiler flags
or introduce CMake/scikit-build translation in this milestone.

## Optional MPI build

`0.6.86` adds `xstar-xspec-mpi` as an explicitly optional target. The default native build and wheel build do not require MPI and do not compile the MPI source.

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

The compiler wrapper is configurable:

```bash
make -C src/xstar_tools/xstar/cpp mpi MPICXX=/path/to/mpic++
```

A normal:

```bash
make -C src/xstar_tools/xstar/cpp
```

must remain MPI-free. This separation prevents an MPI development package/runtime from becoming a dependency of ordinary `xstar-cpp` or local-process `xstar-xspec` users.
