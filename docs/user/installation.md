# Installation

`pyproject.toml` is the authoritative Python package metadata/build configuration. The small `setup.py` file exists only to register the native setuptools build hook.

`0.6.89.1.3 — PIP_SOURCE_LINE_ENDING_EQUIVALENCE_CLOSURE` is formally accepted across Linux x86_64, macOS arm64, macOS Intel x86_64, and Windows UCRT64/AMD64. `0.6.89.2 — PYPI_NATIVE_WHEEL_LINUX` is the current release-wheel candidate. It builds CPython 3.9–3.14 Linux x86_64 wheels in a `manylinux_2_28` container and repairs them with auditwheel so CFITSIO is wheel-local. The frozen science revision and public ABIs are unchanged.

The PyPI Linux binary profile deliberately omits only `libxstar_backend_python.so`, the optional standalone Python-embedding plugin, because it directly links `libpythonX.Y`. The default source/native installation profile remains full. Python-driven `zone-cpp`, the public C API, `xstar-cpp`, and XSTAR2XSPEC executables remain present in the PyPI Linux wheel. MPI remains opt-in and `atdb.fits` remains external.

## Python package installation

For a released package:

```bash
python -m pip install xstar-tools
```

For a source archive or checkout:

```bash
python -m pip install .
```

A Python-only installation is explicit:

```bash
XSTAR_TOOLS_NATIVE=off python -m pip install .
```

To require native compilation instead of allowing fallback:

```bash
XSTAR_TOOLS_NATIVE=required python -m pip install .
```

The native packaging hook stages `xstar-cpp`, `xstar-xspec-initable`, `xstar-xspec-table`, and `xstar-xspec` plus their platform-native shared libraries. It does not stage `xstar-xspec-mpi`, and it does not bundle `atdb.fits`.

`XSTAR_TOOLS_NATIVE_JOBS=N` controls Make parallelism used by the Python build hook.

The wheel/packaging policy is separate from the direct native source-build qualification described below; do not infer source-build support from an older wheel-policy milestone.

## Native source builds

The current accepted source tree is qualified on four non-MPI hosts:

| Platform | Toolchain | Status |
|---|---|---|
| Linux x86_64 | GCC / GNU Make | ACCEPT |
| macOS arm64 | Apple Clang / GNU Make | ACCEPT |
| macOS x86_64 | Apple Clang / GNU Make | ACCEPT |
| Windows x86_64 | MSYS2 UCRT64 / MinGW-w64 GCC / GNU Make | ACCEPT |

The accepted portability baseline is `0.6.88.6.1.2.1`.

### Linux

Typical prerequisites are:

- a C++17 compiler;
- GNU Make;
- Python development support / `python3-config`;
- CFITSIO development headers/libraries;
- `pkg-config`.

On Debian/Ubuntu, CFITSIO development files are normally provided by `libcfitsio-dev`.

Build:

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=linux
```

### macOS

Install:

```bash
brew install cfitsio pkg-config
```

Build:

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=macos
```

The qualified macOS build uses Apple Clang, `.dylib` libraries, `@rpath` install names, and `@loader_path` sibling discovery.

### Windows

Use an **MSYS2 UCRT64** terminal. The accepted dependency set and detailed build/run instructions are in {doc}`windows_installation_and_usage`.

The normal build is:

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=windows
```

Windows MPI is not part of the accepted Windows contract.

## Optional MPI build

MPI is not part of the normal build. On an MPI-capable Linux/HPC environment:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

The wrapper can be overridden with `MPICXX=/path/to/mpic++`.

## Editable development checkout

```bash
python -m pip install -e '.[dev]'
```

For documentation dependencies:

```bash
python -m pip install -e '.[docs]'
```

## Verify the installation

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

For native binaries:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp --version
src/xstar_tools/xstar/cpp/xstar-cpp --abi
```

## Atomic data is separate

`atdb.fits` and `coheat.dat` are not silently downloaded as part of a normal model run. See {doc}`atomic_data` for explicit setup and discovery precedence.
