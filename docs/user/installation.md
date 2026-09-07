# Installation

`pyproject.toml` is the authoritative Python package metadata/build configuration. The small `setup.py` file exists only to register the native setuptools build hook.

The accepted native-wheel baselines cover CPython 3.9–3.14 on Linux x86_64 (`manylinux_2_28_x86_64`), macOS arm64 and x86_64 (`macosx_11_0_*`), and Windows AMD64 (`win_amd64`). `0.6.89.5 — PYPI_CROSS_PLATFORM_RELEASE_CLOSURE` rebuilds those accepted profiles under one release version so PyPI can select the appropriate wheel automatically for `pip install xstar-tools`. The frozen science revision and public ABIs are unchanged.

The PyPI Linux, macOS, and Windows binary profiles omit the optional standalone Python-embedding plugin so distributable wheels do not acquire a Python-runtime library dependency. The default source/native installation profile remains full. Python-driven `zone-cpp`, the public C API, `xstar-cpp`, and XSTAR2XSPEC executables remain present. MPI remains opt-in and `atdb.fits` remains external. Package metadata uses the SPDX expression `GPL-3.0-only` and ships the GNU GPL Version 3 `LICENSE` file. Native macOS and Windows release wheels are built/tested on GitHub-hosted runners; local access to those operating systems is not required.

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

## Conda packaging

`0.6.90.1 — CONDA_NATIVE_HOST_QUALIFICATION` qualifies the refreshed conda-forge v1 recipe natively on Linux x86_64, macOS arm64, and macOS Intel x86_64. CFITSIO is resolved from the conda environment rather than vendored. MPI, the standalone Python-embedding plugin, and `atdb.fits` are not part of the ordinary conda package. Windows conda-native remains deferred; Windows native PyPI support is unchanged.

The public conda-forge package is available now. Install with:

```bash
conda install -c conda-forge xstar-tools
```

The current feedstock release is based on the published PyPI `0.6.89.5` source; `0.6.90.1` is the host-qualification/source milestone and is not assumed to exist on PyPI.

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
