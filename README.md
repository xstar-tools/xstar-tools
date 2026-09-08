# xstar-tools

Python/C++ tools for XSTAR atomic data and high-performance runtimes

[![PyPI](https://img.shields.io/pypi/v/xstar-tools.svg)](https://pypi.org/project/xstar-tools/)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/xstar-tools.svg)](https://anaconda.org/conda-forge/xstar-tools)
[![Conda Platforms](https://img.shields.io/conda/pn/conda-forge/xstar-tools.svg)](https://anaconda.org/conda-forge/xstar-tools)

**xstar-tools** is a Python/C++ implementation of X-ray photoionization calculations using the [XSTAR atomic database](https://ui.adsabs.harvard.edu/abs/2001ApJS..134..139B/abstract). It provides Python/C++ tools for the XSTAR atomic data and high-performance runtime. The scientific oracle remains the official [XSTAR](https://heasarc.gsfc.nasa.gov/docs/software/xstar/xstar.html) FORTRAN program (version 2.59g) originally developed by [Timothy Kallman](https://ui.adsabs.harvard.edu/abs/2001ApJS..133..221K/abstract) and distributed through the [HEASoft](https://heasarc.gsfc.nasa.gov/docs/software/lheasoft/) software package by NASA's High Energy Astrophysics Science Archive Research Center ([HEASARC](https://heasarc.gsfc.nasa.gov)). The XSTAR atomic database ([`atdb.fits`](https://heasarc.gsfc.nasa.gov/FTP/software/lheasoft/lheasoft6.36/heasoft-6.36/ftools/xstar/data/)) is not bundled with the package; it remains external and is discovered through the documented data-path contract.

## Status

The `0.6.90 — CONDA_PACKAGING_REFRESH` is accepted and closed. It qualified the conda build contract on Linux x86_64, macOS arm64, and macOS Intel x86_64, and verified the public conda-forge `0.6.89.5` build-1 packages on `linux-64`, `osx-arm64`, and `osx-64`. All three public installs passed build, platform, external-CFITSIO, ABI, and offline-science checks. Windows conda packages are not supported. Windows support remains available through the accepted PyPI/MSYS2 UCRT64/MinGW-w64.

| Platform | Release wheels | Conda-forge | Accepted platform baseline |
|---|---|---|---|
| Linux x86_64 | CPython 3.9–3.14, `manylinux_2_28_x86_64` | `linux-64` — accepted | `0.6.89.2.2` |
| macOS arm64 | CPython 3.9–3.14, `macosx_11_0_arm64` | `osx-arm64` — accepted | `0.6.89.3` |
| macOS x86_64 | CPython 3.9–3.14, `macosx_11_0_x86_64` | `osx-64` — accepted | `0.6.89.3` |
| Windows AMD64 | CPython 3.9–3.14, `win_amd64` | not supported | `0.6.89.4.5` |

Project links:

- GitHub: <https://github.com/xstar-tools/xstar-tools>
- PyPI: <https://pypi.org/project/xstar-tools/>
- Conda-forge: <https://anaconda.org/conda-forge/xstar-tools>

The accepted cross-platform source-build is non-MPI on Windows and supports `xstar-cpp` plus local-process `xstar-xspec --processes N`. True MPI remains an explicit Linux/macOS/HPC build.

## Install with conda-forge

The package is available from conda-forge on Linux and macOS. Windows conda packages are not supported; Windows users should use the PyPI/MSYS2 UCRT64/MinGW-w64 path. Install conda-forge builds with:

```bash
conda install -c conda-forge xstar-tools
```

Then verify the native runtime:

```bash
xstar-cpp --version
xstar-xspec --version
xstar-tools doctor --require zone-cpp --json
```

The conda-forge package currently tracks the published PyPI `0.6.89.5` source. `0.6.90.1` qualified the conda build, and `0.6.90.2` verified clean public installation and native runtime behavior on `linux-64`, `osx-arm64`, and `osx-64`.

## Install from PyPI

Python **3.9 or newer** is supported. For a normal installation, use:

```bash
pip install xstar-tools
```

Equivalent explicit-Python form:

```bash
python -m pip install xstar-tools
```

Verify the installed native tools with:

```bash
xstar-cpp --version
xstar-xspec --version
xstar-tools doctor --require zone-cpp --json
```

The release wheels include the native XSTAR runtime and its repaired platform dependencies. `atdb.fits` remains external by design, so runs should provide the XSTAR atomic-data path explicitly, for example with `--data-dir /path/to/xstar/data`, or through the documented discovery environment.

## Quick start

A normal source build does not require MPI:

```bash
make -C src/xstar_tools/xstar/cpp -j4
```

Run one XSTAR calculation:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Run a local two-process XSTAR2XSPEC grid:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec \
  --processes 2
```

`--processes 2` means 2 independent `xstar-cpp` processes. It does not mean two threads or two MPI ranks.

## Python / wheel builds

Python requires **3.9 or newer**.

Build a Python-only wheel explicitly:

```bash
XSTAR_TOOLS_NATIVE=off python -m pip wheel . --no-deps
```

Build a native wheel when platform prerequisites are available:

```bash
XSTAR_TOOLS_NATIVE=required python -m pip wheel . --no-deps
```

The release-wheel profiles are deliberately narrower than a full source build:

- Linux uses `pypi-linux`;
- macOS uses `pypi-macos`;
- Windows uses `pypi-windows`;
- all ordinary release wheels exclude `xstar-xspec-mpi`;
- all release profiles exclude the standalone Python-embedding native plugin;
- `atdb.fits` is never bundled into ordinary wheels;
- CFITSIO is vendored into repaired release wheels.

The detailed qualification history is in `docs/developer/packaging.md` and the platform-specific milestone documents under `docs/developer/`.

The complete cross-platform release is built by:

```text
.github/workflows/pypi-cross-platform-release.yml
```

The final `xstar-tools-0.6.89.5-pypi-release` contains the native wheels, the sdist, and a checksum manifest. A Python-only `py3-none-any` control wheel is explicitly excluded from the publication set.

For maintainers preparing a future release, validate the aggregate bundle and publish the **same native-wheel + sdist set** first to TestPyPI and then to PyPI:

```bash
python -m pip install --upgrade twine
python -m twine check release-dist/*
python -m twine upload --repository testpypi release-dist/*
# after installation testing from TestPyPI:
python -m twine upload release-dist/*
```

Do not upload the local `py3-none-any` control wheel; it is only a packaging qualification artifact.

## Native build by platform

### Linux

Typical prerequisites are a C++17 compiler, GNU Make, Python development support, `pkg-config`, and CFITSIO development files.

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=linux
```

### macOS

Install the native dependencies:

```bash
brew install cfitsio pkg-config
```

Build with Apple Clang:

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=macos
```

The qualified Darwin build uses `.dylib` libraries, `@rpath` install names, and `@loader_path` sibling-library lookup.

### Windows

Use an MSYS2 UCRT64 terminal, not the plain MSYS shell. A normal source build can use the packaged MSYS2 CFITSIO development package:

```bash
pacman -S --needed \
  make \
  mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-binutils \
  mingw-w64-ucrt-x86_64-cfitsio \
  mingw-w64-ucrt-x86_64-pkgconf \
  mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-python-pytest
```

Then build:

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=windows
```

Windows produces `.dll`, `.dll.a`, and `.exe` artifacts. The source-runtime backend uses native Win32 process creation. See `docs/user/windows_installation_and_usage.md` for the complete setup and troubleshooting guide.

### Inspect the resolved build contract

```bash
make -C src/xstar_tools/xstar/cpp print-config
```

## Native executables

The main native programs are:

```text
xstar-cpp             one XSTAR model
xstar-xspec-initable  XSTAR2XSPEC grid planner
xstar-xspec-table     final XSPEC table assembler
xstar-xspec           serial/local-process XSTAR2XSPEC
xstar-xspec-mpi       true MPI XSTAR2XSPEC; opt-in build only
```

The compatibility executable `xstar_cpp` is also retained.

When installed through the Python package, the primary native console entry points are:

```text
xstar-cpp
xstar-xspec-initable
xstar-xspec-table
xstar-xspec
```

Useful package inspection commands include:

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

## Atomic data

Native execution requires `atdb.fits` and `coheat.dat`, which are distributed by the oracle XSTAR FORTRAN program through the HEASoft software package (see [XSTAR atomic data](https://heasarc.gsfc.nasa.gov/FTP/software/lheasoft/lheasoft6.36/heasoft-6.36/ftools/xstar/data/). These files are not silently downloaded, and `atdb.fits` remains external to ordinary wheels.

The clearest setup is:

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

or select the two files independently:

```bash
xstar-cpp \
  --input xstar.par \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  --output-dir run_xstar
```

When explicit paths are omitted, discovery includes parameter paths, `XSTAR_ATOMIC_DB` / `XSTAR_ATDB_FITS`, `XSTAR_COHEAT`, `XSTAR_DATA`, `$HEADAS/refdata`, `XSTAR_HOME/data`, executable/package-relative fallbacks, and finally the current directory. See `docs/user/atomic_data.md` for the exact precedence.

## `xstar-cpp`

### With `xstar.par`

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

The positional input form is also accepted:

```bash
xstar-cpp xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Values supplied after the file override values from the file:

```bash
xstar-cpp \
  --input xstar.par \
  --output-dir run_override \
  density=1.0e+12 rlogxi=3 modelname=override_model
```

### Without `xstar.par`

Direct XSTAR-style `key=value` parameters are supported:

```bash
xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output-dir run_direct \
  spectrum=pow spectun=0 trad=-1 \
  temperature=100 pressure=0.03 density=1e12 \
  column=1e20 rlrad38=1e6 rlogxi=1 cfrac=0.4 \
  habund=1 heabund=1 cabund=1 \
  modelname=direct_example abundtbl=xdef \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 \
  emult=0.5 taumax=5 xeemin=0.1 critf=1e-6 \
  vturbi=100 npass=1 ncn2=9999
```

For the complete parameter and output contract, see `src/xstar_tools/xstar/cpp/README.md` and `docs/cpp/xstar_cpp.md`.

## `xstar-xspec`

`xstar-xspec` owns the complete local XSTAR2XSPEC pipeline:

```text
xstar-xspec-initable
        -> independent xstar-cpp jobs
        -> loopcontrol-ordered gather
        -> xstar-xspec-table
```

Parameter-file grid:

```bash
xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec \
  --processes 2
```

A direct 2 x 2 grid can be launched without `xstinitable.par`:

```bash
xstar-xspec \
  --data-dir /path/to/xstar/data \
  --output-dir run_grid \
  --processes 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

The `N` local processes are launched using `--processes N`; `--workers N` and `-j N` remain compatibility aliases. `-np` is reserved for MPI launchers.

Restart a local grid with:

```bash
xstar-xspec \
  --input xstinitable.par \
  --output-dir run_xspec \
  --processes 2 \
  --restart
```

A job is reusable only when its required products and `xstar-cpp.success` marker are present. Partial or failed products are retained for inspection rather than deleted.

## True MPI XSTAR2XSPEC

`xstar-xspec-mpi` is optional and is not part of normal `make` or ordinary PyPI wheels:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

Typical Linux/HPC execution is:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

MPI concurrency comes from the communicator size. There is no local `--processes` option in `xstar-xspec-mpi`. The current file-backed MPI path requires shared visibility of executables, output directories, atomic data, and external model files. Windows MPI is not supported. Windows native parallel execution remains the non-MPI `xstar-xspec --processes N` built with MSYS2 UCRT64/MinGW-w64.

## Outputs

A successful `xstar-cpp` run can publish products such as:

```text
xout_abund1.fits
xout_cont1.fits
xout_lines1.fits
xout_rrc1.fits
xout_spect1.fits
xout_step.log
xstar_execution_provenance.json
```

A successful XSTAR2XSPEC run additionally publishes:

```text
xout_ain.fits
xout_aout.fits
xout_mtable.fits
xout_etable.fits
```

The local-process scheduler keeps its work tree under `xstar2xspec-work/jobs/NNNNNN/`.

## Scientific and ABI freeze

Important accepted identities are:

```text
canonical oracle         FORTRAN XSTAR 2.59g
accepted science freeze  0.6.48.12.3.45.3.3.8
public C API ABI          60487
production-zone ABI      6048110
fixed-state program ABI  60486
XSPEC table ABI           1
```

Cross-platform qualification preserves scientific arithmetic/order, controller decisions, traversal/contribution order, publication semantics, output schema, and public ABIs unless a later explicitly qualified scientific change says otherwise.

## Documentation

Start with:

- `docs/user/index.md` — installation and normal use;
- `docs/user/atomic_data.md` — atomic-data discovery and precedence;
- `docs/user/windows_installation_and_usage.md` — Windows/MSYS2 UCRT64 source-build guide;
- `src/xstar_tools/xstar/cpp/README.md` — native C++ programs and detailed examples;
- `docs/cpp/index.md` — native C++/CLI reference;
- `docs/developer/packaging.md` — packaging architecture and release-wheel policy;
- `docs/developer/cross_platform_portability_status.md` — accepted source-build portability status;
- `CHANGELOG.md` — chronological release history.

Historical qualification failures and their closure evidence intentionally live in `docs/developer/` rather than this top-level README.

## Development rule of thumb

Use the narrowest qualification gate that covers the changed boundary. Packaging/documentation changes should not reopen science or performance work. Scientific or orchestration changes should begin with representative fast fixtures and preserve the frozen oracle/ABI contracts before any expensive broad qualification.

## License

The active package metadata uses the non-deprecated SPDX expression `GPL-3.0-only`. The authoritative license text is the top-level `LICENSE` file (GNU General Public License, Version 3).

