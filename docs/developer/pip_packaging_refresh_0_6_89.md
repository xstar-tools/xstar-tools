# 0.6.89 — PIP_PACKAGING_REFRESH

`0.6.89` is a packaging/productization milestone branching from the formally
accepted `0.6.88.6.1.2.1` four-host non-MPI portability baseline. It does not
reopen the frozen XSTAR science implementation.

## Scope

The milestone makes the existing setuptools native-wheel hook consistent with
the native platforms already qualified by the source build:

- Linux: `.so` shared libraries and unsuffixed executables;
- macOS: `.dylib` shared libraries and unsuffixed executables;
- Windows/MSYS2 UCRT64: `.dll` shared libraries and `.exe` executables.

The ordinary native wheel stages these runtime programs:

```text
xstar_cpp
xstar-cpp
xstar-xspec-initable
xstar-xspec-table
xstar-xspec
```

and the corresponding `libxstar_*` runtime libraries. `xstar-xspec-mpi` is
intentionally absent. The retained Makefile `all` target remains the wheel
build boundary; MPI remains an explicit `make mpi` / `make xstar-xspec-mpi`
HPC operation.

## Central native-runtime discovery

`src/xstar_tools/native_runtime.py` now owns platform-neutral names and paths
for packaged native libraries and executables. Python `ctypes` backends use this
single resolver instead of embedding Linux `.so` paths independently.

On Windows the resolver retains `os.add_dll_directory()` handles for the
package-local `cpp/` directory (and an explicit library override directory when
needed), so sibling XSTAR DLL dependencies remain discoverable for the process
lifetime.

Executable discovery is package-local before `PATH`. This prevents a pip
console-script wrapper such as `xstar-xspec` from rediscovering itself instead
of the packaged native executable.

## Public pip console commands

Native wheels expose package launchers for:

```text
xstar-cpp
xstar-xspec-initable
xstar-xspec-table
xstar-xspec
```

The pre-existing `xstar-tools-*` compatibility/user commands remain available.

## Atomic-data policy

This milestone does **not** bundle `atdb.fits`. Native scientific runs retain
the accepted external atomic-data discovery contract, including explicit
`--data-dir`, XSTAR environment variables, and `$HEADAS/refdata` fallback.
`coheat.dat` remains the small package fallback already present before this
milestone.

## Scientific and ABI boundary

Unchanged:

```text
scientific oracle      FORTRAN XSTAR 2.59g
science revision       0.6.48.12.3.45.3.3.8
public C API ABI        60487
production-zone ABI    6048110
fixed-state ABI         60486
XSPEC table ABI         1
```

No scientific cutoff, traversal/contribution/accumulation order, publication
schema, or floating-point policy is changed by this milestone.

## Qualification intent

`0.6.89` validates the packaging contract itself. Later release-wheel closures
(`0.6.89.1+`) may add PyPI-specific repair/tagging policy such as manylinux,
macOS dependency repair, and Windows wheel dependency repair without changing
this artifact/discovery contract.
