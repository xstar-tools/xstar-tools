# Native C++ XSTAR tree

This directory contains the native XSTAR libraries and executables used by `xstar-tools`.

```text
src/xstar_tools/xstar/cpp/
  *.h, *.hpp, *.cpp
  Makefile
  libxstar_*.so
  xstar_cpp
  xstar-cpp
  xstar-xspec-initable
  xstar-xspec-table
  xstar-xspec
  xstar-xspec-mpi       # opt-in MPI build only
```

The canonical scientific oracle remains FORTRAN XSTAR 2.59g.  Native orchestration must not alter the accepted scientific/controller ordering, contribution ordering, accumulation ordering, cutoffs, or publication semantics.

## Build

Normal build (no MPI compiler/runtime required):

```bash
cd src/xstar_tools/xstar/cpp
make -j2
```

or build selected production commands:

```bash
make -j2 xstar-cpp xstar-xspec-initable xstar-xspec-table xstar-xspec
```

True MPI XSTAR2XSPEC is deliberately **not** in the default target.  Build it only when requested:

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
  --output run1
```

Positional input is equivalent:

```bash
./xstar-cpp xstar.par --data-dir /path/to/xstar/data --output run1
```

### Without a parameter file

Pass ordinary XSTAR parameters directly as `key=value` arguments:

```bash
./xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output run_direct \
  spectrum=pow \
  temperature=100 \
  density=1e8 \
  column=1e20 \
  rlogxi=1 \
  cfrac=1 \
  niter=0 \
  ncn2=9999 \
  modelname=direct_cpp_example
```

A file and overrides can be combined:

```bash
./xstar-cpp \
  --input xstar.par \
  --output run_override \
  density=1e10 rlogxi=2 modelname=override_example
```

Useful frontend options:

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

`--threads N` sets `OMP_NUM_THREADS` for the native run.  It is separate from XSTAR2XSPEC `--workers N`.  The current XSTAR2XSPEC worker pool is process-based.

## Atomic data

The most explicit setup is:

```bash
./xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output run1
```

`--data-dir DIR` selects `DIR/atdb.fits` and `DIR/coheat.dat`.  The files can instead be selected independently:

```bash
./xstar-cpp \
  --input xstar.par \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  --output run1
```

If explicit paths are omitted, the runtime uses the first existing candidate.

### `atdb.fits` search order

1. parameter-envelope `atomic_database`, `atomic_db`, or `atdb`;
2. `atdb.fits` beside the parameter envelope;
3. `$XSTAR_ATOMIC_DB`;
4. `$XSTAR_ATDB_FITS`;
5. `$XSTAR_DATA/atdb.fits`;
6. `$HEADAS/refdata/atdb.fits`;
7. `$XSTAR_HOME/data/atdb.fits`;
8. executable-relative `../data/atdb.fits`, then `../../data/atdb.fits`;
9. `src/xstar_tools/xstar/data/atdb.fits`;
10. `./atdb.fits`.

### `coheat.dat` search order

1. parameter-envelope `coheat_file` or `coheat`;
2. `coheat.dat` beside the parameter envelope;
3. `$XSTAR_COHEAT`;
4. `$XSTAR_DATA/coheat.dat`;
5. `$HEADAS/refdata/coheat.dat`;
6. `$XSTAR_HOME/data/coheat.dat`;
7. executable-relative `../data/coheat.dat`, then `../../data/coheat.dat`;
8. `src/xstar_tools/xstar/data/coheat.dat`;
9. `./coheat.dat`.

With HEASoft initialized, `$HEADAS/refdata` is therefore a supported fallback:

```bash
heainit
./xstar-cpp --input xstar.par --output run_headas
```

The runtime prints/search-records the resolved atomic-data paths and provenance so the selected files can be audited.

## `xstar-xspec`: serial and local process parallelism

### Using `xstinitable.par`

Serial:

```bash
./xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_serial \
  --workers 1
```

Two simultaneous local XSTAR processes:

```bash
./xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_parallel \
  --workers 2
```

`--workers 2` means **two child processes**, not two threads.  Each worker launches a separate `xstar-cpp`.  The operating system can schedule them on two logical CPUs concurrently if resources are available.  There is no automatic physical-core pinning.

### Without `xstinitable.par`

A four-job 2 x 2 example:

```bash
./xstar-xspec \
  --data-dir /path/to/xstar/data \
  --output-dir run_direct_grid \
  --workers 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0 \
  spectrum=pow density=1e12 modelname=direct_grid
```

When `--data-dir` is present it is emitted into every planned `xstar-cpp` job.  When it is absent, each child performs the normal atomic-data discovery described above.

### Restart and preservation

```bash
./xstar-xspec \
  --input xstinitable.par \
  --output-dir run_parallel \
  --workers 2 \
  --restart
```

The work tree is visible and preserved by default:

```text
run_parallel/xstar2xspec-work/jobs/000001/
run_parallel/xstar2xspec-work/jobs/000002/
...
```

Failed or partial XSTAR products are never automatically deleted.  Restart requires:

```text
xout_spect1.fits
xout_step.log
xstar-cpp.success
```

Explicit successful-run cleanup is available with `--cleanup-work`.

## `xstar-xspec-mpi`: true MPI (`0.6.86` candidate)

Build:

```bash
make mpi
```

Run one grid across four MPI ranks:

```bash
mpirun -np 4 ./xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

Direct grid parameters are also accepted:

```bash
mpirun -np 4 ./xstar-xspec-mpi \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

The MPI rank count replaces local `--workers`:

```text
mpirun -np 2  -> up to 2 simultaneous xstar-cpp processes
mpirun -np 4  -> up to 4 simultaneous xstar-cpp processes
```

Every rank, including rank 0, can claim a grid job.  Rank 0 creates the plan and, after all jobs succeed, gathers spectra and STEP logs strictly by `loopcontrol` and runs `xstar-xspec-table`.  The first MPI implementation requires a shared filesystem for the executable/data/output paths.

## Native ABI and libraries

Public C/C++ interfaces remain in `xstar_api.h`, `xstar_api.hpp`, and the other versioned public headers.  The retained libraries include:

```text
libxstar_solver.so
libxstar_rates.so
libxstar_matrix.so
libxstar_emissivity.so
libxstar_opacity.so
libxstar_thermal.so
libxstar_engine.so
libxstar_local_zone.so
libxstar_production_zone.so
libxstar_xspec_table.so
```

Keep Python implementations under `src/xstar_tools/xstar/`; do not copy shared libraries out of this native directory.
