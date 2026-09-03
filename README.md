# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations. The canonical scientific oracle remains **FORTRAN XSTAR 2.59g**. Package, interface, portability, orchestration, and performance work are qualified without silently changing that scientific boundary.

## Current status

**Current formally accepted packaging baseline: `0.6.89.1.3` — `PIP_SOURCE_LINE_ENDING_EQUIVALENCE_CLOSURE`.** The full GitHub Actions matrix (Linux x86_64, macOS arm64, macOS Intel x86_64, and Windows UCRT64/AMD64) returned host ACCEPT.

**Current release-wheel candidate: `0.6.89.2.2` — `PYPI_LINUX_PROFILE_BUILD_TARGET_CLOSURE`.** It retains the `0.6.89.2` manylinux publication contract and the `0.6.89.2.1` preflight dependency fix, while correcting the native build boundary: the `pypi-linux` profile now invokes a dedicated Makefile target that never builds the standalone Python-embedding plugin. The candidate still targets repaired `manylinux_2_28_x86_64` native wheels for CPython 3.9 through 3.14, keeps MPI out of ordinary wheels, and keeps `atdb.fits` external.

The accepted cross-platform source-build contract remains non-MPI on Windows and supports `xstar-cpp` plus local-process `xstar-xspec --processes N`. True MPI remains an explicit Linux/HPC build.

## Pip / PyPI packaging

A Python-only source wheel remains explicit:

```bash
XSTAR_TOOLS_NATIVE=off python -m pip wheel . --no-deps
```

A normal native source wheel remains available when platform prerequisites are installed:

```bash
XSTAR_TOOLS_NATIVE=required python -m pip wheel . --no-deps
```

`0.6.89.2` introduced the Linux PyPI release profile; `0.6.89.2.1` fixed release-workflow preflight dependency ordering; `0.6.89.2.2` closes the first manylinux native-build failure by ensuring the PyPI profile excludes the standalone Python-embedding plugin at build time as well as staging time. Release wheels are built inside `manylinux_2_28_x86_64`, use a pinned CFITSIO 4.6.2 build, and are repaired so CFITSIO is wheel-local. The release profile contains `xstar-cpp`, `xstar-xspec-initable`, `xstar-xspec-table`, `xstar-xspec`, the C++ production libraries, and the public C API. It deliberately omits only the optional standalone Python-embedding plugin because a portable manylinux wheel must not depend on or vendor `libpythonX.Y`. Source/native installs retain the full plugin set.

The ordinary wheel still excludes `xstar-xspec-mpi`; `atdb.fits` remains external. See `docs/developer/pypi_native_wheel_linux_0_6_89_2.md` for the retained release-wheel contract, `docs/developer/pypi_native_wheel_linux_preflight_dependency_closure_0_6_89_2_1.md` for the preflight closure, and `docs/developer/pypi_linux_profile_build_target_closure_0_6_89_2_2.md` for the native build-target closure.

## Quick start

A normal native source build does not require MPI:

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

`--processes 2` means **two independent `xstar-cpp` operating-system processes**, not two threads and not two MPI ranks.

## Native build by platform

### Linux

Typical prerequisites on Debian/Ubuntu are a C++17 compiler, GNU Make, Python development tools, `pkg-config`, and CFITSIO development files. Then:

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

The qualified macOS build produces `.dylib` libraries with `@rpath` install names and `@loader_path` sibling-library lookup.

### Windows

Use an **MSYS2 UCRT64** terminal, not the plain MSYS shell. Install at least:

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

Windows produces `.dll`, `.dll.a`, and `.exe` artifacts. See `docs/user/windows_installation_and_usage.md` for the full setup and troubleshooting guide.

### Inspect the build contract

For any platform:

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

## Atomic data

Native scientific execution requires `atdb.fits` and `coheat.dat`. These files are external and are not silently downloaded.

The most explicit setup is:

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

or independent file selection:

```bash
xstar-cpp \
  --input xstar.par \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  --output-dir run_xstar
```

When explicit paths are omitted, native discovery includes direct parameter/envelope paths, `XSTAR_ATOMIC_DB` / `XSTAR_ATDB_FITS`, `XSTAR_COHEAT`, `XSTAR_DATA`, `$HEADAS/refdata`, `XSTAR_HOME/data`, executable/package-local fallbacks, and finally the current directory. See `docs/user/atomic_data.md` for the exact precedence.

## `xstar-cpp`

### With `xstar.par`

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

The positional input form is also accepted:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Values after the file override values from the file:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --output-dir run_override \
  density=1.0e+12 rlogxi=3 modelname=override_model
```

### Without `xstar.par`

Direct XSTAR-style `key=value` parameters are supported:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
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

For the complete parameter examples and output contract, see `src/xstar_tools/xstar/cpp/README.md` and `docs/cpp/xstar_cpp.md`.

## `xstar-xspec`

`xstar-xspec` owns the complete native local XSTAR2XSPEC pipeline:

```text
xstar-xspec-initable
        -> independent xstar-cpp jobs
        -> loopcontrol-ordered gather
        -> xstar-xspec-table
```

### Parameter-file grid

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec \
  --processes 2
```

The canonical spelling is `--processes N`; `--workers N` and `-j N` remain compatibility aliases. `-np` is reserved for MPI launchers.

### Direct grid

A small 2 x 2 grid can be launched without `xstinitable.par`:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --data-dir /path/to/xstar/data \
  --output-dir run_grid \
  --processes 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

### Restart and retained products

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --output-dir run_xspec \
  --processes 2 \
  --restart
```

A job is reusable only when its required scientific products and `xstar-cpp.success` marker are present. Partial/failed products are retained for inspection rather than deleted merely because unrelated files coexist in the job directory.

## True MPI XSTAR2XSPEC

`xstar-xspec-mpi` is an **optional** build and is not part of normal `make`:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

The MPI compiler wrapper defaults to `MPICXX=mpic++` and can be overridden.

Typical Linux/HPC execution is:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

MPI concurrency comes from the communicator size. There is no local `--processes` option in `xstar-xspec-mpi`. The current file-backed MPI path requires shared visibility of executables, work/output directories, atomic data, and external model files. **Windows MPI is deferred and is not part of the accepted Windows contract.**

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

The local-process scheduler keeps its visible work tree under `xstar2xspec-work/jobs/NNNNNN/`.

## Python interfaces

The established Python package remains available alongside the native executables. Stable execution modes include `pure-python`, `zone-python`, `zone-cpp`, `zone-all`, and `xstar-cpp`.

Useful inspection commands are:

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

See `docs/user/backends.md` and `docs/developer/execution_modes.md` for ownership boundaries and compatibility aliases.

## Scientific and ABI freeze

The portability work does not redefine the scientific baseline. Important frozen identities include:

```text
canonical oracle         FORTRAN XSTAR 2.59g
accepted science freeze  0.6.48.12.3.45.3.3.8
public C API ABI          60487
production-zone ABI      6048110
fixed-state program ABI  60486
XSPEC table ABI           1
```

Cross-platform qualification preserves scientific arithmetic/order, controller decisions, traversal/contribution order, cutoffs, publication semantics, output schema, and public ABIs unless a later explicitly qualified scientific change says otherwise.

## Documentation

Start with:

- `docs/user/index.md` — installation and normal use;
- `docs/user/windows_installation_and_usage.md` — MSYS2 UCRT64 Windows guide;
- `docs/cpp/index.md` — native C++/CLI reference;
- `docs/developer/index.md` — architecture, qualification, portability, and release history;
- `docs/developer/cross_platform_portability_status.md` — current platform support and accepted portability closure;
- `CHANGELOG.md` — chronological release history.

The long portability investigation and historical host rejections are intentionally kept out of this top-level README; their detailed evidence remains in `docs/developer/`.

## Development rule of thumb

For documentation/API/build-system changes, run the narrow qualification gates that cover the changed boundary. For scientific or orchestration changes, begin with representative fast fixtures and preserve the frozen oracle/ABI contracts. Expensive broad or multi-element qualification should be reserved for changes that actually require it.
