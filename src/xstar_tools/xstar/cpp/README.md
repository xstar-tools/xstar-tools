# Native C++ XSTAR tree

This directory contains the native C++ XSTAR runtime and the standalone XSTAR/XSTAR2XSPEC frontends. The implementation is source-faithful to the accepted XSTAR scientific boundary; portability and orchestration changes are qualified independently from the frozen science.

## Accepted platform status

The non-MPI native path is formally qualified on:

| Platform | Toolchain | Status |
|---|---|---|
| Linux x86_64 | GCC + GNU Make | ACCEPT |
| macOS arm64 | Apple Clang + GNU Make | ACCEPT |
| macOS x86_64 | Apple Clang + GNU Make | ACCEPT |
| Windows x86_64 | MSYS2 UCRT64 + MinGW-w64 GCC + GNU Make | ACCEPT |

The current accepted cross-platform closure is `0.6.88.6.1.2.1`. Windows MPI is intentionally out of scope; use the local-process `xstar-xspec --processes N` path on Windows.

## Programs

The main native executables are:

```text
xstar-cpp             public one-model XSTAR frontend
xstar_cpp             compatibility/native production executable
xstar-xspec-initable  XSTAR2XSPEC grid planner
xstar-xspec-table     final XSPEC table assembler
xstar-xspec           complete serial/local-process XSTAR2XSPEC driver
xstar-xspec-mpi       true MPI XSTAR2XSPEC; opt-in build only
```

## Build

### Normal non-MPI build

From the repository root:

```bash
make -C src/xstar_tools/xstar/cpp -j4
```

or from this directory:

```bash
make -j4
```

Inspect the resolved platform/build configuration with:

```bash
make print-config
```

The build abstraction controls platform-specific extensions and linker behavior through variables including:

```text
PLATFORM
SHLIB_EXT
EXEEXT
SHLIB_LDFLAGS
PIC_FLAGS
DL_LIBS
THREAD_LIBS
RPATH_ORIGIN
FILESYSTEM_LIBS
```

### Linux

```bash
make -j4 PLATFORM=linux
```

Typical prerequisites are a C++17 compiler, GNU Make, Python development support, `pkg-config`, and CFITSIO development files.

### macOS

Install dependencies:

```bash
brew install cfitsio pkg-config
```

Build:

```bash
make -j4 PLATFORM=macos
```

The qualified Darwin build uses Apple Clang, `.dylib` shared libraries, `@rpath` install names, and `@loader_path` sibling-library lookup.

### Windows / MSYS2 UCRT64

Use an **MSYS2 UCRT64** terminal. Install the normal native toolchain:

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

Build:

```bash
make -j4 PLATFORM=windows
```

Windows produces `.dll`, `.dll.a`, and `.exe` files. The Win32 process backend uses `CreateProcessW` rather than emulating `fork`.

For a standalone-only build:

```bash
make -j4 PLATFORM=windows xstar-cpp.exe
```

See `../../../../docs/user/windows_installation_and_usage.md` for the complete Windows guide.

## `xstar-cpp`: one XSTAR calculation

### Using `xstar.par`

```bash
./xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

The parameter file may also be positional:

```bash
./xstar-cpp xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Values supplied after the file override file values:

```bash
./xstar-cpp \
  --input xstar.par \
  --output-dir run_override \
  density=1.0e+12 rlogxi=3 modelname=override_model
```

On Windows use `./xstar-cpp.exe`.

### Without `xstar.par`

Direct XSTAR-style `name=value` input is supported. A realistic example is:

```bash
./xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output-dir run_direct \
  cfrac=0.4 temperature=100 lcpres=0 pressure=0.03 spectrum=pow \
  spectun=0 trad=-1 density=1.0e12 column=1e20 rlrad38=1e6 rlogxi=3 \
  habund=1 heabund=1 liabund=0 beabund=0 babund=0 cabund=1 \
  nabund=1 oabund=1 fabund=0 neabund=1 naabund=0 mgabund=1 \
  alabund=1 siabund=1 pabund=0 sabund=1 clabund=0 arabund=1 \
  kabund=0 caabund=1 scabund=0 tiabund=0 vabund=0 crabund=1 \
  mnabund=0 feabund=1 coabund=0 niabund=1 cuabund=0 znabund=0 \
  modelname=xstar_pg1211 abundtbl=xdef nsteps=10 niter=99 \
  lwrite=1 lprint=1 lstep=0 emult=0.5 taumax=5 radexp=0 \
  xeemin=0.1 critf=1e-6 vturbi=100 npass=1 ncn2=9999
```

The public frontend preserves values as strings until the accepted native parameter reader interprets them.

### Terminal output and debugging

Normal `xstar-cpp` execution prints the compact FORTRAN-style pass header, radial-zone progress, final-print/publication messages, and total runtime. Internal version-tagged qualification diagnostics such as `V064895_...` are hidden from the terminal by default.

To restore the complete development/qualification diagnostic stream for troubleshooting, use:

```bash
./xstar-cpp --debug --output-dir run_debug name=value ...
```

or set `XSTAR_CPP_DEBUG=1`. Explicit `--progress json` remains available for machine-readable frontend progress.

Normal mode also hides legacy first-evaluation and profiling output such as `V0648117_...`, `V064896_TYPE50_MODE`, `DETAIL_*_SECONDS`, and `PUBLIC_*_SECONDS`. These remain available with `--debug` or `XSTAR_CPP_DEBUG=1`.

## Atomic data used by `xstar-cpp`

A production model requires `atdb.fits` and `coheat.dat`. Prefer an explicit directory when reproducibility matters:

```bash
./xstar-cpp --input xstar.par --data-dir /path/to/xstar/data --output-dir run1
```

or select the files independently:

```bash
./xstar-cpp \
  --input xstar.par \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  --output-dir run1
```

When explicit paths are omitted, `atdb.fits` is searched in this order:

1. parameter-envelope `atomic_database`, `atomic_db`, or `atdb`;
2. `atdb.fits` beside the parameter envelope;
3. `$XSTAR_ATOMIC_DB`;
4. `$XSTAR_ATDB_FITS`;
5. `$XSTAR_DATA/atdb.fits`;
6. `$HEADAS/refdata/atdb.fits`;
7. `$XSTAR_HOME/data/atdb.fits`;
8. executable-relative `../data/atdb.fits`;
9. executable-relative `../../data/atdb.fits`;
10. `src/xstar_tools/xstar/data/atdb.fits`;
11. `./atdb.fits`.

`coheat.dat` uses the analogous order:

1. parameter-envelope `coheat_file` or `coheat`;
2. `coheat.dat` beside the parameter envelope;
3. `$XSTAR_COHEAT`;
4. `$XSTAR_DATA/coheat.dat`;
5. `$HEADAS/refdata/coheat.dat`;
6. `$XSTAR_HOME/data/coheat.dat`;
7. executable-relative `../data/coheat.dat`;
8. executable-relative `../../data/coheat.dat`;
9. `src/xstar_tools/xstar/data/coheat.dat`;
10. `./coheat.dat`.

After `heainit`, `$HEADAS/refdata` is therefore a valid fallback. A valid explicit path or `XSTAR_DATA` location has precedence over it.

## `xstar-xspec`: complete serial/local-process XSTAR2XSPEC

`xstar-xspec` owns the native pipeline:

```text
xstar-xspec-initable
        -> independent xstar-cpp jobs
        -> loopcontrol-ordered gather
        -> xstar-xspec-table
```

### With `xstinitable.par`

Serial reference mode:

```bash
./xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_serial \
  --processes 1
```

Two simultaneous local XSTAR processes:

```bash
./xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_local2 \
  --processes 2
```

`--processes N` counts independent **operating-system child processes**, not C++ threads. The OS or batch scheduler maps them to CPUs. `--workers N` and `-j N` remain compatibility aliases; new commands should use `--processes N`. `-np` is reserved for MPI launchers.

### Without `xstinitable.par`

A small direct 2 x 2 grid is:

```bash
./xstar-xspec \
  --data-dir /path/to/xstar/data \
  --output-dir run_grid \
  --processes 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

A larger direct grid can include the same physical, abundance, convergence, and output-control parameters accepted by `xstar-cpp`, plus the XSTAR2XSPEC grid-control fields.

If `--data-dir` is omitted, each child `xstar-cpp` performs the normal native atomic-data discovery independently.

### Restart and preservation

```bash
./xstar-xspec \
  --input xstinitable.par \
  --output-dir run_local2 \
  --processes 2 \
  --restart
```

A job is reusable only when `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success` are present. Partial or failed products are retained for forensic inspection. Unrelated pre-existing files in a job directory do not cause valid XSTAR products to be deleted.

## `xstar-xspec-mpi`: true MPI

The MPI executable is **not** built by default:

```bash
make
```

does not require MPI.

Build explicitly on an MPI-capable Linux/HPC system:

```bash
make mpi
```

or:

```bash
make xstar-xspec-mpi
```

Override the wrapper when needed:

```bash
make mpi MPICXX=/path/to/mpic++
```

Run:

```bash
mpirun -np 4 ./xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

MPI rank count controls concurrency. There is no local `--processes` option in `xstar-xspec-mpi`. Rank/completion order never determines table placement; canonical `loopcontrol` does.

The current implementation uses job directories as the inter-stage product boundary, so every rank must see the same executables, work/output directory, atomic-data directory, and any external model files. A shared filesystem is therefore required.

**Windows MPI is deferred and intentionally unsupported by the accepted Windows build contract.**

## Process and thread distinctions

These controls are different:

```text
xstar-cpp --threads N       threads inside one model where supported
xstar-xspec --processes N   N independent local xstar-cpp processes
mpirun -np N xstar-xspec-mpi   N MPI ranks
```

Do not run the local `xstar-xspec` executable under `mpirun`; use `xstar-xspec-mpi` for true MPI.

## Output products

A normal successful `xstar-cpp` run can produce:

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

The local-process path uses the visible work tree `xstar2xspec-work/jobs/NNNNNN/`. The MPI path also preserves rank/job logs for diagnostics.

## Shared-library portability boundaries

Cross-platform support is concentrated in narrow infrastructure layers rather than spread through the scientific kernels:

- `xstar_dynamic_library.*` / platform helpers own dynamic-library loading;
- `xstar_process.hpp` owns process creation, wait, termination, PID, and environment mutation;
- `xstar_path_compat.hpp` adapts `std::filesystem::path` at existing narrow C APIs on Windows;
- the Makefile owns platform extensions, linker flags, import libraries, and runtime search-path policy.

Linux/macOS retain POSIX semantics; Windows uses the corresponding Win32 implementation. Scientific traversal/order and public ABIs remain frozen across these portability layers.

## Cross-platform fixed-state qualification

The accepted `0.6.88.6.1.2.1` contract requires:

- warning-free native builds;
- correct ELF/Mach-O/PE artifacts and exports;
- sibling/plugin discovery;
- direct process smoke tests;
- local-process XSTAR2XSPEC scheduler smoke tests;
- fixed-state same-host raw-byte determinism;
- exact cross-platform discrete state and FITS structure;
- text comparison after CRLF/CR -> LF normalization;
- finite differing numerical values within both `1e-13` relative difference and `64 ULP`;
- Python backend/bridge and regression closure.

Observed accepted behavior:

```text
Linux x86_64        canonical fixed-state bytes
macOS Intel x86_64  canonical fixed-state bytes
Windows UCRT64      canonical FITS; text differs only by CRLF serialization
macOS arm64         same-host deterministic; max observed 4.56e-15 relative / 39 ULP
```

For current platform status, see `../../../../docs/developer/cross_platform_portability_status.md`. Closed version-specific qualification records are retained in repository history/tags and summarized chronologically in `../../../../CHANGELOG.md`.
