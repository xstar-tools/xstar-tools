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

## Cross-platform qualification (`0.6.88.6`)

`0.6.88.6 — CROSS_PLATFORM_QUALIFICATION` freezes production behavior to the formally accepted `.5.7` Windows closure and runs one host contract across Linux GCC, macOS arm64/x86_64 Apple Clang, and Windows MSYS2 UCRT64/MinGW-w64. The normal build remains non-MPI on Windows; Windows MPI is out of scope.

Windows users should follow `docs/user/windows_installation_and_usage.md` for MSYS2 UCRT64 prerequisites, `PLATFORM=windows`, native build commands, atomic-data setup, included examples, local-process `xstar-xspec`, and troubleshooting.

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

The runtime loader remains the `0.6.88.2` `dl*` implementation. No science source is modified by the macOS build work. MPI remains opt-in and is not part of the `.88.3.2` macOS acceptance gate. Apple and Windows builds use the frozen Type-77 exact value `0x1.c2ccf22133138p-4` only for the special exact-match record; Linux continues to call `::exp10(rec)` there. On macOS, `libxstar_local_zone.dylib` directly links `libxstar_opacity.dylib` because it directly calls the opacity ABI; Linux retains its accepted historical link command.

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

### Windows embedded-Python DLL-search closure (0.6.88.5.6)

`0.6.88.5.5` closed the native MinGW build defect: the real UCRT64 build, PE/import/export/version/discovery checks, Win32 process smoke, and synthetic local-process XSTAR2XSPEC pool all accepted. The remaining host rejection occurred only in the embedded Python backend when `_ctypes` could not load a dependent DLL.

`0.6.88.5.6 — WINDOWS_EMBEDDED_PYTHON_DLL_SEARCH_CLOSURE` adds a `_WIN32`-only embedder step in `xstar_backend_python.cpp`. After CPython initialization and before package import, it registers `<Py_GetPrefix()>/bin` using `os.add_dll_directory()` (falling back to the prefix when necessary) and retains the returned handle on `sys`. No scheduler/process/science/ABI behavior changes. Use `.github/workflows/windows-build.yml` or `tools/qualification/run_windows_embedded_python_dll_search_closure_host_0_6_88_5_6.py`.

### Windows XSTAR2XSPEC standard-header closure (0.6.88.5.5)

`0.6.88.5.5 — WINDOWS_XSPEC_STANDARD_HEADER_CLOSURE` moved `<fstream>`, `<iostream>`, `<map>`, `<sstream>`, `<stdexcept>`, `<string>`, and `<vector>` outside the Windows exclusion guard while leaving only POSIX headers guarded. Its real UCRT64 run accepted the native build, DLL/export/discovery checks, Win32 process smoke, and synthetic XSTAR2XSPEC pool, then rejected only when the embedded Python backend imported `_ctypes`. `.5.5` remains a historical Windows HOST REJECT; `.5.6` is the narrow embedder follow-up.

### Windows build-failure diagnostic closure (0.6.88.5.4)

`0.6.88.5.4 — WINDOWS_BUILD_FAILURE_DIAGNOSTIC_CLOSURE` is qualification-only. It preserves the `.5.3` Type-85, Type-77, Python path-adapter, and CreateProcessW production code and changes only package-version metadata. The Windows host runner now emits the native-build return code, compiler/linker failure contexts, and a substantial `make all` log tail, while classifying build-dependent downstream gates as `SKIP_BUILD_FAILED`. Use `.github/workflows/windows-build.yml` or `tools/qualification/run_windows_build_failure_diagnostic_closure_host_0_6_88_5_4.py`.

### Windows local-zone portability closure (0.6.88.5.3)

`0.6.88.5.3 — WINDOWS_LOCAL_ZONE_PORTABILITY_CLOSURE` is a narrow follow-up to the real UCRT64 host rejection of 0.6.88.5.2. It renames the Type-85 local identifier `far` to `far_coeff`, extends the existing exact Type-77 special-value branch to `_WIN32`, and sends the Python backend `addition` filesystem path through `XSTAR_C_PATH` before `PyUnicode_FromString`. Linux/macOS arithmetic and process behavior are intentionally unchanged. Qualification also audits the Python backend for direct path `c_str()` use and prints detailed synthetic `xstar-xspec` pool diagnostics on failure. Use `.github/workflows/windows-build.yml` or `tools/qualification/run_windows_local_zone_portability_closure_host_0_6_88_5_3.py`.

### Windows path-boundary completion (0.6.88.5.2)

`0.6.88.5.2 — WINDOWS_PATH_BOUNDARY_COMPLETION` closes two remaining `std::filesystem::path` to narrow `const char*` C-API call sites reported by the real UCRT64 host run of 0.6.88.5.1. It also removes two Win32-only misleading-indentation warnings and corrects the synthetic XSTAR2XSPEC host qualification to read the actual root-level `xstar2xspec_scheduler.log`. The CreateProcessW backend and scientific code paths are unchanged. Use `.github/workflows/windows-build.yml` or `tools/qualification/run_windows_path_boundary_completion_host_0_6_88_5_2.py`.

### Windows / MinGW native build (0.6.88.5.1)

`0.6.88.5` established the native UCRT64/MinGW build and Win32 `CreateProcessW` process backend, but its first Windows host run stopped at `std::filesystem::path` to narrow C-API boundaries because MinGW uses `wchar_t` as the native path value type. `0.6.88.5.1 — WINDOWS_PATH_ENCODING_CLOSURE` keeps the process backend unchanged and adapts only filesystem paths passed to existing narrow `const char*` CFITSIO/XSTAR interfaces. Windows builds produce `.dll` libraries, `.dll.a` import libraries, and `.exe` programs; Windows MPI remains out of scope. Use `.github/workflows/windows-build.yml` or the `run_windows_path_encoding_closure_host_0_6_88_5_1.py` host runner for UCRT64 qualification.

### Windows build failure diagnostic closure (0.6.88.5.4)

`0.6.88.5.4 — WINDOWS_BUILD_FAILURE_DIAGNOSTIC_CLOSURE` is qualification-only. It preserves the `.5.3` local-zone, Python path, and Win32 process implementation unchanged while improving the Windows host runner. A failed parallel `make -jN all PLATFORM=windows` now reports its exact return code, failure-context lines, and a large delimited log tail, then performs an evidence-only `make -j1 all PLATFORM=windows` replay without cleaning. The serial replay never promotes the original build result; it exists only to expose a deterministic compiler/linker error or show that the failure is parallel/resource-sensitive.

### Windows embedded-Python prefix-API closure (0.6.88.5.7)

`0.6.88.5.7 — WINDOWS_EMBEDDED_PYTHON_PREFIX_API_CLOSURE` is formally accepted on MSYS2 UCRT64. It preserves the `.5.6` Windows DLL-search behavior but removes deprecated `Py_GetPrefix()` usage. The embedder reads `sys.base_prefix`, converts it with `PyUnicode_AsWideCharString()`, frees the owned buffer with `PyMem_Free()`, then continues the existing `<prefix>/bin`/prefix fallback and retained `os.add_dll_directory()` handle. No warning suppression, scheduler/process, science, or ABI behavior changes. Use `.github/workflows/windows-build.yml` or `tools/qualification/run_windows_embedded_python_prefix_api_closure_host_0_6_88_5_7.py`.

### 0.6.88.6.1.1 cross-platform workflow discovery closure

`0.6.88.6.1.1` is qualification-only relative to `0.6.88.6.1`. The cross-platform checker discovers the active GitHub Actions workflow by content from either `.yml` or `.yaml` files instead of hard-coding one filename. No scientific, loader, process, Python-backend, scheduler, fixed-state comparator, tolerance, or ABI behavior changes.

### 0.6.88.6.1 cross-platform fixed-state equivalence closure

`0.6.88.6.1` is qualification-only relative to `0.6.88.6`. Native C++ implementation and scientific behavior are unchanged except package-version metadata. The cross-platform host runner now separates same-host raw-byte determinism from cross-architecture fixed-state equivalence: text line endings are normalized for comparison, discrete traversal/state remains exact, FITS structure remains exact, and finite numerical fields use a strict `1e-13` relative plus `64 ULP` envelope. Windows MPI remains out of scope.


### 0.6.88.6.1.2 Windows reference payload line-ending closure

`0.6.88.6.1.2` is qualification-only relative to `0.6.88.6.1.1`. Windows Git checkout had rewritten the checked-in canonical text fixtures to CRLF, causing only the source fixture hash test to reject. `.gitattributes` now protects those fixture bytes and the text-fixture hash test normalizes line endings defensively. Native C++ production behavior and public ABIs are unchanged.
