# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations. The canonical scientific oracle remains **FORTRAN XSTAR 2.59g**. Package, orchestration, performance, and interface work are qualified without silently changing that scientific boundary.

## Release status

- **`0.6.85.1` — formally accepted:** serial/local-process native XSTAR2XSPEC, output-directory coexistence, non-destructive failure products, restart success markers, and real-host local parallel closure.
- **`0.6.86` — formally accepted:** `TRUE_MPI_XSTAR2XSPEC`, adding the opt-in `xstar-xspec-mpi` executable. Real two-rank host qualification completed successfully with four XSTAR jobs and restart reuse.
- **`0.6.88.1` — formally accepted:** `PLATFORM_BUILD_ABSTRACTION`.
- **`0.6.88.2.2` — formally accepted:** `FIXED_STATE_REGRESSION_SCAFFOLD_CLOSURE`, completing Linux qualification of the portable dynamic-library layer after the historical `.88.2` and `.88.2.1` host rejections.
- **`0.6.88.3` — historical HOST REJECT:** native Apple-Clang compilation stopped on the nonportable Type-77 `::exp10` special path; the CI Python environment also lacked `pytest`.
- **`0.6.88.3.1` — historical HOST REJECT:** the Apple Type-77 compile closure worked, but native macOS linking exposed a missing direct `libxstar_opacity` dependency and the qualification checker re-resolved Homebrew Python 3.14 without `pytest`.
- **`0.6.88.3.2` — current candidate:** `MACOS_NATIVE_BUILD_LINK_CLOSURE`, adding the direct opacity link only on macOS and keeping qualification subprocesses on the setup-python interpreter.

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

The Apple Type-77 exact-value closure from `0.6.88.3.1` remains unchanged: Apple builds use `0x1.c2ccf22133138p-4`, while non-Apple builds retain `::exp10(rec)`. `0.6.88.3.2` additionally links `libxstar_local_zone.dylib` directly to `libxstar_opacity.dylib` on macOS; Linux keeps its historical local-zone link command.

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
