# Native C++ XSTAR tree

This directory contains the native XSTAR libraries and executables used by `xstar-tools`.

```text
src/xstar_tools/xstar/cpp/
  *.h, *.hpp, *.cpp
  Makefile
  libxstar_*.(so|dylib|dll)
  xstar_cpp
  xstar-cpp
  xstar-xspec-initable
  xstar-xspec-table
  xstar-xspec
  xstar-xspec-mpi       # opt-in MPI build only
```

The canonical scientific oracle remains FORTRAN XSTAR 2.59g. Native orchestration must not alter accepted scientific/controller ordering, contribution ordering, accumulation ordering, cutoffs, or publication semantics.

## Portable process layer (`0.6.88.4`)

Process/environment operations now pass through `xstar_process.hpp`. The POSIX implementation intentionally delegates to the historical `fork`, `execv`/`execvp`, `waitpid`, `kill`, `getpid`, `setenv`, and `unsetenv` calls without changing arguments or status semantics. This isolates the later Windows/MinGW backend from XSTAR science and orchestration sources. Linux behavior is the qualification baseline for this release; Windows process creation is not yet claimed as accepted.

## macOS native build (`0.6.88.3.2`)

`0.6.88.3.2` carries forward the Apple-Clang build and Type-77 compile closure and closes the Darwin direct-link defect found in `.88.3.1`. When `PLATFORM=macos` and the caller has not explicitly supplied `CXX`, the Makefile uses `clang++`. Shared libraries use `.dylib` and `-dynamiclib`; each dylib receives an `@rpath/libxstar_*.dylib` install name, while consumers carry `-Wl,-rpath,@loader_path` so sibling XSTAR libraries resolve relative to the loading image.

CFITSIO discovery first uses `pkg-config`. If that fails on macOS, the Makefile asks `brew --prefix cfitsio` and derives `-I<prefix>/include`, `-L<prefix>/lib -lcfitsio`, and the matching rpath. Typical setup and build:

```bash
brew install cfitsio pkg-config
make PLATFORM=macos print-config
make -j4 PLATFORM=macos
```

The runtime loader remains the `0.6.88.2` `dl*` implementation. No science source is modified by the macOS build work. MPI remains opt-in and is not part of the `.88.3.2` macOS acceptance gate. Apple builds use the frozen Type-77 exact value `0x1.c2ccf22133138p-4` only for the special exact-match record; Linux/non-Apple builds continue to call `::exp10(rec)` there. On macOS, `libxstar_local_zone.dylib` directly links `libxstar_opacity.dylib` because it directly calls the opacity ABI; Linux retains its accepted historical link command.

## Portable dynamic-library layer (`0.6.88.2`)

`0.6.88.2` keeps the accepted `0.6.88.1` Makefile platform contract and adds source-level portability for runtime shared-library discovery/loading. `xstar_platform.hpp` owns `.so` / `.dylib` / `.dll` naming and the platform path-list separator. `xstar_dynamic_library.hpp/.cpp` is the only layer that calls the native loader: `dlopen`/`dlsym`/`dlclose`/`dladdr` on Linux and macOS, and `LoadLibraryW`/`GetProcAddress`/`FreeLibrary`/`GetModuleFileNameW` on Windows. Callers no longer hard-code `.so` filenames or call the native loader directly.

`XSTAR_PLUGIN_PATH` uses `:` on Linux/macOS and `;` on Windows. Sibling-library discovery is based on the module containing the supplied symbol rather than the process working directory when the platform API can resolve it. Windows MPI remains intentionally unsupported. Windows process creation is still a later portability milestone, so `.88.2` does not claim a complete Windows `xstar-cpp`/`xstar-xspec` runtime port.

## Cross-platform build foundation (`0.6.88.1`, formally accepted)

The Makefile centralizes platform build nomenclature through `PLATFORM`, `SHLIB_EXT`, `EXEEXT`, `SHLIB_LDFLAGS`, `PIC_FLAGS`, `DL_LIBS`, `THREAD_LIBS`, `RPATH_ORIGIN`, and `FILESYSTEM_LIBS`. Linux defaults reproduce the accepted `0.6.87` command stream. Windows MPI is not supported.

Inspect the active contract with:

```bash
make print-config
make PLATFORM=macos print-config
make PLATFORM=windows print-config
```


## Build

Normal build, with no MPI compiler/runtime requirement:

```bash
cd src/xstar_tools/xstar/cpp
make -j2
```

or build selected production commands:

```bash
make -j2 xstar-cpp xstar-xspec-initable xstar-xspec-table xstar-xspec
```

True MPI XSTAR2XSPEC is deliberately **not** in the default target. Build it only when requested:

```bash
make mpi
```

or:

```bash
make xstar-xspec-mpi
```

The MPI compiler wrapper defaults to `mpic++` and can be overridden:

```bash
make mpi MPICXX=/path/to/mpic++
```

`make clean` removes both normal and optional MPI artifacts.

## `xstar-cpp`: one XSTAR calculation

### Using `xstar.par`

```bash
./xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run1
```

Positional input is equivalent:

```bash
./xstar-cpp xstar.par --data-dir /path/to/xstar/data --output-dir run1
```

Values supplied after the file override file values:

```bash
./xstar-cpp \
  --input xstar.par \
  --output-dir run_override \
  density=1.0e+12 rlogxi=3 modelname='override_model'
```

### Without `xstar.par`: realistic direct parameter example

```bash
./xstar-cpp --output-dir run_xstar_direct \
  cfrac=0.4 temperature=100. lcpres=0 pressure=0.03 spectrum='pow' \
  spectun=0 trad=-1. density=1.0e+12 column=1.e+20 rlrad38=1.e+6 rlogxi=3 \
  habund=1 heabund=1 liabund=0 beabund=0 babund=0 cabund=1 \
  nabund=1 oabund=1 fabund=0 neabund=1 naabund=0 mgabund=1 \
  alabund=1 siabund=1 pabund=0 sabund=1 clabund=0 arabund=1 \
  kabund=0 caabund=1 scabund=0 tiabund=0 vabund=0 crabund=1 \
  mnabund=0 feabund=1 coabund=0 niabund=1 cuabund=0 znabund=0 \
  modelname='xstar_pg1211' abundtbl='xdef' nsteps=10 niter=99 \
  lwrite=1 lprint=1 lstep=0 emult=0.5 taumax=5. radexp=0. \
  xeemin=0.1 critf=1.e-6 vturbi=100. npass=1 ncn2=9999
```

Useful frontend options include:

```text
--input PATH
--data-dir DIR
--input-dir DIR
--output DIR / --output-dir DIR
--atomic-db PATH
--coheat PATH
--json-summary FILE
--provenance FILE
--progress none|text|json
--threads N
--profile FILE
--deterministic
--print-option N
--parameters-out FILE
--abi
--version
```

`--threads N` sets `OMP_NUM_THREADS` for one native XSTAR run. It is separate from XSTAR2XSPEC `--processes N`, which controls how many independent `xstar-cpp` OS processes may run simultaneously.

## Atomic data used by `xstar-cpp`

The simplest explicit configuration is:

```bash
./xstar-cpp --data-dir /path/to/xstar/data ...
```

where the directory contains `atdb.fits` and `coheat.dat`.

The files may also be given independently:

```bash
./xstar-cpp \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  ...
```

When no explicit data path is supplied, `xstar-cpp` searches for the first existing `atdb.fits` in this order:

1. explicit parameter-envelope path (`atomic_database`, `atomic_db`, `atdb`);
2. beside the parameter envelope;
3. `$XSTAR_ATOMIC_DB`;
4. `$XSTAR_ATDB_FITS`;
5. `$XSTAR_DATA/atdb.fits`;
6. `$HEADAS/refdata/atdb.fits`;
7. `$XSTAR_HOME/data/atdb.fits`;
8. executable-relative `../data` and `../../data`;
9. `src/xstar_tools/xstar/data`;
10. current directory.

`coheat.dat` uses the analogous sequence, with `$XSTAR_COHEAT` as its direct environment override and without `XSTAR_ATDB_FITS`.

Therefore after normal HEASoft initialization this can be sufficient:

```bash
heainit
./xstar-cpp --input xstar.par --output-dir run1
```

because `$HEADAS/refdata` is an accepted fallback. If `$XSTAR_DATA` exists, it is checked before `$HEADAS/refdata`.

## `xstar-xspec`: complete serial/local-process XSTAR2XSPEC

`xstar-xspec` performs:

```text
xstar-xspec-initable
        -> independent xstar-cpp grid jobs
        -> canonical loopcontrol gather
        -> xstar-xspec-table
        -> xout_ain.fits / xout_aout.fits / xout_mtable.fits / xout_etable.fits
```

### With `xstinitable.par`

Serial:

```bash
./xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_serial \
  --processes 1
```

Two simultaneous XSTAR processes:

```bash
./xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_local2 \
  --processes 2
```

`--processes N` is **process parallelism**, not C++ thread parallelism. Each slot launches one independent `xstar-cpp` child process. The operating system or batch scheduler maps runnable processes to logical CPUs; `xstar-xspec` itself does not pin to physical cores.

Compatibility aliases are retained:

```text
--workers N
-j N
```

New usage should prefer `--processes N`. `-np` is kept for MPI launcher semantics.

### Without `xstinitable.par`: realistic direct grid example

```bash
./xstar-xspec \
  --output-dir run_xspec_direct \
  --processes 2 cfrac=0.4 \
  temperature=100. lcpres=0 pressure=0.03 spectrum='pow' \
  spectun=0 trad=-1. density=1.0e+12 densitytyp=0 \
  columnsof=1.0e+20 columntyp=2 column=1.e+24 columnnst=9 columnint=1 \
  rlrad38=1.e+6 rlogxityp=2 rlogxisof=0 rlogxi=5 rlogxinst=6 rlogxiint=0 \
  habund=1 heabund=1 liabund=0 beabund=0 babund=0 cabund=1 \
  nabund=1 oabund=1 fabund=0 neabund=1 naabund=0 mgabund=1 \
  alabund=1 siabund=1 pabund=0 sabund=1 clabund=0 arabund=1 \
  kabund=0 caabund=1 scabund=0 tiabund=0 vabund=0 crabund=1 \
  mnabund=0 feabund=1 coabund=0 niabund=1 cuabund=0 znabund=0 \
  modelname='xstar_pg1211' abundtbl='xdef' nsteps=10 niter=99 \
  lwrite=0 lprint=1 lstep=0 emult=0.5 taumax=5. radexp=0. \
  xeemin=0.1 critf=1.e-6 vturbi=100. npass=1 ncn2=9999
```

A file and direct overrides may also be combined.

### Restart and preservation

```bash
./xstar-xspec \
  --input xstinitable.par \
  --output-dir run_local2 \
  --processes 2 \
  --restart
```

The visible work tree is:

```text
run_local2/xstar2xspec-work/jobs/000001/
run_local2/xstar2xspec-work/jobs/000002/
...
```

A reusable successful job requires `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success`. Failure is non-destructive: partial/invalid XSTAR products remain available for inspection. `--cleanup-work` is an explicit post-success cleanup request.

## `xstar-xspec-mpi`: true MPI

`0.6.86` established and host-qualified true MPI XSTAR2XSPEC. Build it only when requested:

```bash
make mpi
```

Run one distributed grid with:

```bash
mpirun -np 4 ./xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

or direct grid parameters:

```bash
mpirun -np 4 ./xstar-xspec-mpi \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

MPI concurrency comes from the communicator size:

```text
mpirun -np 2  -> 2 MPI ranks -> up to 2 simultaneous xstar-cpp children
mpirun -np 4  -> 4 MPI ranks -> up to 4 simultaneous xstar-cpp children
```

There is no local `--processes` option in `xstar-xspec-mpi`. MPI rank count is selected by `mpirun/mpiexec -np N`. Rank and completion order never determine scientific table placement; canonical `loopcontrol` does.

The file-backed MPI implementation requires shared visibility of the executable, output/work directory, atomic data, and any external model files used by the grid.

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

The local-process path writes `xstar2xspec.log` and `xstar2xspec_scheduler.log`. The MPI path writes `xstar2xspec-mpi.log`, `xstar2xspec-mpi-scheduler.log`, and per-rank logs.
