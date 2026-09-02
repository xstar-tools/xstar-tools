# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations. The canonical scientific oracle remains **FORTRAN XSTAR 2.59g**. Package, orchestration, performance, and interface work are qualified without silently changing that scientific boundary.

## Release status

- **`0.6.85.1` — formally accepted:** serial/local-process native XSTAR2XSPEC, output-directory coexistence, non-destructive failure products, restart success markers, and real-host local parallel closure.
- **`0.6.86` — formally accepted:** `TRUE_MPI_XSTAR2XSPEC`, adding the opt-in `xstar-xspec-mpi` executable. Real two-rank host qualification completed successfully with four XSTAR jobs and restart reuse.
- **`0.6.88.1` — formally accepted:** `PLATFORM_BUILD_ABSTRACTION`.
- **`0.6.88.2.2` — formally accepted:** `FIXED_STATE_REGRESSION_SCAFFOLD_CLOSURE`, completing Linux qualification of the portable dynamic-library layer after the historical `.88.2` and `.88.2.1` host rejections.
- **`0.6.88.3` — historical HOST REJECT:** native Apple-Clang compilation stopped on the nonportable Type-77 `::exp10` special path; the CI Python environment also lacked `pytest`.
- **`0.6.88.3.1` — historical HOST REJECT:** the Apple Type-77 compile closure worked, but native macOS linking exposed a missing direct `libxstar_opacity` dependency and the qualification checker re-resolved Homebrew Python 3.14 without `pytest`.
- **`0.6.88.4.2` — formally accepted:** `MACOS_WARNING_CLEANUP_SYNTAX_CLOSURE`, accepted on both macOS arm64 and x86_64.
- **`0.6.88.5` — historical Windows HOST REJECT:** native MinGW build exposed wide `std::filesystem::path` to narrow C-API boundaries.
- **`0.6.88.5.1` — historical Windows HOST REJECT:** most path boundaries closed, but two standalone path sites remained.
- **`0.6.88.5.2` — historical Windows HOST REJECT:** path boundary closure reached the local-zone/Python backend, exposing MinGW Type-85 `far`, Windows `::exp10`, and Python path portability defects.
- **`0.6.88.5.3` — historical Windows HOST REJECT:** the requested Type-85/Type-77/Python portability fixes all passed source qualification, but the later native Windows build still returned nonzero without surfacing the actionable compiler/linker diagnostic; the synthetic XSTAR2XSPEC pool was not run because the production build failed.
- **`0.6.88.5.4` — historical Windows HOST REJECT:** the diagnostic closure exposed a deterministic `xstar_xspec_parallel.cpp` compile failure on both parallel and serial MinGW builds because portable standard-library headers were incorrectly hidden inside `#if !defined(_WIN32)`; the direct Win32 process smoke still passed.
- **`0.6.88.5.5` — historical Windows HOST REJECT:** the standard-header closure fully fixed the native Windows build and the process/XSTAR2XSPEC gates, but the final regression failed when embedded CPython imported `_ctypes` because its extension-DLL dependency directory was not registered.
- **`0.6.88.5.6` — historical Windows HOST REJECT:** the DLL-search closure fixed `_ctypes` loading and all runtime/regression gates passed, but Python 3.14.7 warned that `Py_GetPrefix()` is deprecated, so the strict warning-free gate rejected the host run.
- **`0.6.88.5.7` — formally accepted:** `WINDOWS_EMBEDDED_PYTHON_PREFIX_API_CLOSURE`; the real MSYS2 UCRT64 host passed warning-free native build, process/XSTAR2XSPEC, fixed-state, embedded-Python, bridge, and full-regression gates.
- **`0.6.88.6` — historical cross-platform HOST REJECT:** Linux GCC and macOS Intel accepted; macOS arm64 and Windows UCRT64 rejected only because the first unified runner required Linux/x86-64 raw fixed-state hashes across unlike platforms.
- **`0.6.88.6.1` — current candidate:** `CROSS_PLATFORM_FIXED_STATE_EQUIVALENCE_CLOSURE`; qualification-only correction that preserves same-host byte determinism while using exact discrete-state checks plus strict floating equivalence across architectures. Windows MPI remains out of scope.
- **`0.6.88.3.2` — formally accepted:** `MACOS_NATIVE_BUILD_LINK_CLOSURE`, accepted on both `macos-15` arm64 and `macos-15-intel` x86_64.

The accepted optimized C++ science/performance lineage remains rooted in `0.6.82.40.2.46.1`. Historical ACCEPT/REJECT records are preserved in `CHANGELOG.md` and `docs/developer/`.

## Native build

The normal build does **not** compile or link MPI:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

Important native executables are:

```text
xstar-cpp             one XSTAR model
xstar-xspec-initable  XSPEC-table grid planner
xstar-xspec-table     final XSPEC table assembler
xstar-xspec           serial/local-process XSTAR2XSPEC
xstar-xspec-mpi       true MPI XSTAR2XSPEC; opt-in build only
```

Build MPI only when requested:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

The MPI target uses `MPICXX ?= mpic++`. It is not part of the normal `all` target.


### Portable process layer (`0.6.88.4`)

`0.6.88.4` introduces `xstar_process.hpp` as the sole native boundary for `fork`, `execv`/`execvp`, `waitpid`, `kill`, `getpid`, `setenv`, and `unsetenv`. Linux and macOS wrappers call the same POSIX primitives with unchanged arguments, wait-status decoding, signal choices, and orchestration order. The Windows process backend is deliberately deferred to the MinGW native-build milestone; this release first requires Linux build/regression and source-preservation closure before Windows behavior is implemented.

### Native macOS build (`0.6.88.3.2`)

On macOS, the native build defaults to Apple `clang++`, produces `.dylib` libraries, uses `@rpath` install names with an `@loader_path` runtime search path, and discovers CFITSIO through `pkg-config` with a Homebrew fallback. Typical prerequisites are:

```bash
brew install cfitsio pkg-config
```

Then:

```bash
cd src/xstar_tools/xstar/cpp
make PLATFORM=macos print-config
make -j4 PLATFORM=macos
```

CFITSIO discovery order is explicit `CFITSIO_*` overrides, `pkg-config`, `brew --prefix cfitsio` on macOS, then linker-default `-lcfitsio`. The default macOS build remains non-MPI; MPI is not part of the `0.6.88.3.2` acceptance gate.

The Apple Type-77 exact-value closure from `0.6.88.3.1` remains unchanged: Apple and Windows builds use `0x1.c2ccf22133138p-4` for the special exact-match record, while Linux retains `::exp10(rec)`. `0.6.88.3.2` additionally links `libxstar_local_zone.dylib` directly to `libxstar_opacity.dylib` on macOS; Linux keeps its historical local-zone link command.

## Running `xstar-cpp`

`xstar-cpp` performs one XSTAR calculation.

### With `xstar.par`

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

The positional parameter-file form is also accepted:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Values supplied after the file override values from the file:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --output-dir run_xstar_override \
  density=1.0e+12 rlogxi=3 modelname='override_model'
```

### Without `xstar.par`: realistic direct `key=value` example

```bash
src/xstar_tools/xstar/cpp/xstar-cpp --output-dir run_xstar_direct \
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

If `--data-dir` is omitted, `xstar-cpp` performs native atomic-data discovery as described below.

## Running `xstar-xspec`

`xstar-xspec` creates an XSTAR2XSPEC grid with `xstar-xspec-initable`, executes independent `xstar-cpp` jobs, gathers the spectra and STEP logs strictly by `loopcontrol`, and creates the four final XSPEC tables.

### With `xstinitable.par`

Serial reference mode:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec_serial \
  --processes 1
```

Two simultaneous local XSTAR processes:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec_local2 \
  --processes 2
```

`--processes 2` means **two simultaneous `xstar-cpp` OS processes**, not two C++ threads. Linux/the batch scheduler may run those processes on two logical CPUs when resources are available. `xstar-xspec` does not pin them to specific physical cores.

Compatibility aliases remain available:

```text
--workers N
-j N
```

New scripts should use `--processes N`. The spelling `-np` is intentionally reserved for MPI launchers such as `mpirun -np N`.

### Without `xstinitable.par`: realistic direct `key=value` grid example

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
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

The same `key=value` arguments may follow `--input xstinitable.par` to override file values.

### Restart and retained products

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --output-dir run_xspec_local2 \
  --processes 2 \
  --restart
```

Per-job products are kept under:

```text
run_xspec_local2/xstar2xspec-work/jobs/000001/
run_xspec_local2/xstar2xspec-work/jobs/000002/
...
```

A job is restart-reusable only when all of these exist:

```text
xout_spect1.fits
xout_step.log
xstar-cpp.success
```

Failed or partial XSTAR products are preserved for inspection and are not automatically deleted. Work-tree removal is explicit-only with `--cleanup-work` after a fully successful run.

## True MPI XSTAR2XSPEC

`0.6.86` established the accepted true-MPI executable. Build it explicitly:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

Then distribute one XSTAR2XSPEC grid across MPI ranks:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_xspec_mpi
```

Or supply grid parameters directly:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_xspec_mpi \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

`xstar-xspec-mpi` has no local `--processes` setting. **`mpirun/mpiexec -np N` selects N MPI ranks.** Every rank may execute one `xstar-cpp` child at a time, including rank 0; rank 0 alone performs the final canonical `loopcontrol`-ordered gather/table publication.

For the current file-backed MPI implementation, the executable, output directory, atomic data, and any external model files must be visible from every MPI rank. A shared filesystem is therefore required for multi-node execution.

## Atomic-data discovery

The most explicit and reproducible choice is:

```bash
--data-dir /path/to/xstar/data
```

The directory should contain:

```text
atdb.fits
coheat.dat
```

You can instead supply the files separately to `xstar-cpp`:

```bash
xstar-cpp \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  ...
```

When explicit paths are omitted, the runtime selects the **first existing file** in the search sequence.

### `atdb.fits` discovery order

1. explicit parameter-envelope path (`atomic_database`, `atomic_db`, or `atdb`; this includes `--atomic-db` and `--data-dir`);
2. `atdb.fits` beside the native parameter envelope;
3. `$XSTAR_ATOMIC_DB`;
4. `$XSTAR_ATDB_FITS`;
5. `$XSTAR_DATA/atdb.fits`;
6. `$HEADAS/refdata/atdb.fits`;
7. `$XSTAR_HOME/data/atdb.fits`;
8. executable-relative `../data/atdb.fits` and `../../data/atdb.fits`;
9. `src/xstar_tools/xstar/data/atdb.fits`;
10. `./atdb.fits`.

### `coheat.dat` discovery order

1. explicit parameter-envelope path (`coheat_file` or `coheat`; including `--coheat` and `--data-dir`);
2. `coheat.dat` beside the native parameter envelope;
3. `$XSTAR_COHEAT`;
4. `$XSTAR_DATA/coheat.dat`;
5. `$HEADAS/refdata/coheat.dat`;
6. `$XSTAR_HOME/data/coheat.dat`;
7. executable-relative `../data/coheat.dat` and `../../data/coheat.dat`;
8. `src/xstar_tools/xstar/data/coheat.dat`;
9. `./coheat.dat`.

With HEASoft initialized, this commonly works without `--data-dir`:

```bash
heainit
src/xstar_tools/xstar/cpp/xstar-cpp --input xstar.par --output-dir run_xstar
```

because `$HEADAS/refdata/atdb.fits` and `$HEADAS/refdata/coheat.dat` are accepted fallbacks. If `$XSTAR_DATA` is also defined and contains both files, it has precedence over `$HEADAS/refdata`.

For multi-node MPI, an explicit shared `--data-dir` is recommended so every rank resolves the same files independently of launcher environment-export policy.

## Documentation

Start with:

- `docs/user/first_run.md`
- `docs/user/atomic_data.md`
- `docs/user/performance.md`
- `docs/cpp/xstar_cpp.md`
- `docs/cpp/xstar_xspec.md`
- `docs/cpp/xstar_xspec_mpi.md`
- `docs/developer/execution_modes.md`
- `docs/developer/true_mpi_xstar2xspec_0_6_86.md`
- `docs/developer/process_count_cli_0_6_87.md`

The project deliberately separates scientific acceptance, publication correctness, performance qualification, and orchestration/interface changes. Historical formal ACCEPT/REJECT records are never rewritten when a later release changes a different contract.

### Windows / MinGW native build (0.6.88.5.1)

`0.6.88.5` established the native UCRT64/MinGW build and Win32 `CreateProcessW` process backend, but its first Windows host run stopped at `std::filesystem::path` to narrow C-API boundaries because MinGW uses `wchar_t` as the native path value type. `0.6.88.5.1 — WINDOWS_PATH_ENCODING_CLOSURE` keeps the process backend unchanged and adapts only filesystem paths passed to existing narrow `const char*` CFITSIO/XSTAR interfaces. Windows builds produce `.dll` libraries, `.dll.a` import libraries, and `.exe` programs; Windows MPI remains out of scope. Use `.github/workflows/windows-build.yml` or the `run_windows_path_encoding_closure_host_0_6_88_5_1.py` host runner for UCRT64 qualification.

### 0.6.88.5.6 Windows embedded-Python DLL-search closure

`0.6.88.5.5` is now a historical Windows-host rejection even though its native build, PE/import/export/version/discovery, Win32 process smoke, and local XSTAR2XSPEC process-pool gates all accepted. Its remaining failure was isolated to embedded CPython: `_ctypes` could not load one of its dependent DLLs during the Python-backend regression, after the fixed-state C++ scaffold had already accepted.

`0.6.88.5.6 — WINDOWS_EMBEDDED_PYTHON_DLL_SEARCH_CLOSURE` kept that successful native Windows path unchanged and fixed only the embedder. Its real UCRT64 run confirmed external `ctypes`, embedded-Python, fixed-state, Python-bridge, XSTAR2XSPEC process-pool, and full-regression ACCEPT. The host still rejected because Python 3.14.7 warned that the `.5.6` `Py_GetPrefix()` call is deprecated, violating the strict warning-free build contract.

### 0.6.88.6 cross-platform qualification

`0.6.88.6 — CROSS_PLATFORM_QUALIFICATION` unified the native qualification contract across Linux GCC, macOS arm64/x86_64 Apple Clang, and Windows MSYS2 UCRT64/MinGW-w64. Linux GCC and macOS Intel accepted. macOS arm64 and Windows UCRT64 rejected only at the unconditional raw fixed-state hash gate: Windows differed solely by CRLF text serialization while its FITS payload was byte-identical; macOS arm64 preserved exact discrete state and differed only at last-bit floating-point scale. `.88.6` is therefore retained as a historical host rejection.

### 0.6.88.6.1 cross-platform fixed-state equivalence closure

`0.6.88.6.1 — CROSS_PLATFORM_FIXED_STATE_EQUIVALENCE_CLOSURE` changes qualification only. Each host must reproduce its own three fixed-state products byte-for-byte on a repeat run. Cross-host comparison normalizes text line endings, requires exact visited-record contents, exact discrete step-log state, exact FITS HDU/schema/row structure, and compares every finite floating value against the canonical x86-64 reference with both relative error `<=1e-13` and ULP distance `<=64`. Raw canonical hashes remain diagnostic evidence, not a cross-architecture failure gate. Windows MPI remains out of scope.

For Windows native setup, build commands, atomic-data configuration, examples, XSTAR2XSPEC use, and troubleshooting, see `docs/user/windows_installation_and_usage.md`.

### 0.6.88.5.7 Windows embedded-Python prefix-API closure

`0.6.88.5.7 — WINDOWS_EMBEDDED_PYTHON_PREFIX_API_CLOSURE` preserves the accepted `.5.6` `os.add_dll_directory()` behavior and changes only how the initialized Python prefix is obtained: it reads `sys.base_prefix`, converts it with `PyUnicode_AsWideCharString()`, and releases that temporary buffer with `PyMem_Free()`. No warning suppression is added; Linux/macOS, scheduler/process behavior, fixed-state/science behavior, and ABI values are unchanged.

### 0.6.88.5.5 Windows XSTAR2XSPEC standard-header closure

`0.6.88.5.4 — WINDOWS_BUILD_FAILURE_DIAGNOSTIC_CLOSURE` is now a historical Windows-host rejection. Its parallel and serial MinGW builds both failed deterministically in `xstar_xspec_parallel.cpp`: portable standard-library headers such as `<fstream>` and `<iostream>` were inside `#if !defined(_WIN32)`, leaving Windows compilation without complete stream declarations or `std::cout`.

`0.6.88.5.5 — WINDOWS_XSPEC_STANDARD_HEADER_CLOSURE` moved the portable C++ headers outside that guard and left only POSIX headers guarded. Its real UCRT64 host run then fully accepted the native build and process/XSTAR2XSPEC gates, but the final embedded-Python regression rejected at `_ctypes`; `.5.5` is therefore preserved as a historical Windows HOST REJECT and `.5.6` owns that new runtime closure.
