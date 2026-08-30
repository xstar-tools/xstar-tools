# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations.  The canonical scientific oracle remains **FORTRAN XSTAR 2.59g**; package, orchestration, performance, and interface work are qualified without silently changing that scientific boundary.

## Release status

- **`0.6.85.1` — formally accepted:** native serial/local-process XSTAR2XSPEC, standalone output-directory coexistence, non-destructive failure products, restart success markers, and real-host parallel closure.
- **`0.6.86` — development candidate:** `TRUE_MPI_XSTAR2XSPEC`, adding the opt-in `xstar-xspec-mpi` executable.  Normal non-MPI builds remain unchanged and do not require MPI.

The accepted optimized C++ science/performance lineage is retained from `0.6.82.40.2.46.1`.  Historical acceptance/rejection records are preserved in `CHANGELOG.md` and `docs/developer/`.

## Native build

The normal build does **not** compile or link MPI:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

Important native executables include:

```text
xstar-cpp             one XSTAR model
xstar-xspec-initable  XSPEC-table grid planner
xstar-xspec-table     final XSPEC table assembler
xstar-xspec           serial/local-process XSTAR2XSPEC
```

MPI is explicitly opt-in:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

This requires an MPI C++ compiler wrapper such as `mpic++`.  `xstar-xspec-mpi` is not part of the default `all` target.

## Running `xstar-cpp`

### With `xstar.par`

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output run_xstar
```

The positional parameter-file form is also accepted:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  xstar.par \
  --data-dir /path/to/xstar/data \
  --output run_xstar
```

### Without `xstar.par`: direct `key=value`

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output run_xstar_direct \
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

`key=value` arguments may also override values read from `--input`.

## Running `xstar-xspec`

`xstar-xspec` creates the grid with `xstar-xspec-initable`, runs independent `xstar-cpp` jobs, gathers them strictly by `loopcontrol`, and creates the four XSPEC tables.

### With `xstinitable.par`

Serial reference mode:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec_serial \
  --workers 1
```

Two-way local parallelism:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec_local2 \
  --workers 2
```

`--workers 2` means **two simultaneous OS child processes**, not two threads.  Each child is a separate `xstar-cpp` process.  On a host with available CPU capacity the operating system can schedule those processes on two logical CPUs concurrently; it does not pin them to particular physical cores unless CPU affinity is configured separately.

### Without `xstinitable.par`: direct `key=value`

This example creates a small 2 x 2 grid (four XSTAR jobs):

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --data-dir /path/to/xstar/data \
  --output-dir run_xspec_direct \
  --workers 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0 \
  spectrum=pow density=1e12 modelname=direct_xspec_example
```

The same `key=value` arguments may be used after `--input` to override values from `xstinitable.par`.

### Restart and products

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --output-dir run_xspec_local2 \
  --workers 2 \
  --restart
```

Per-job products remain in:

```text
run_xspec_local2/xstar2xspec-work/jobs/000001/
run_xspec_local2/xstar2xspec-work/jobs/000002/
...
```

A job is restart-reusable only when `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success` all exist.  Failed/partial XSTAR products are retained for inspection and are not automatically deleted.  Destructive work-tree removal is explicit-only with `--cleanup-work` after a fully successful run.

## True MPI XSTAR2XSPEC (`0.6.86` candidate)

Build explicitly:

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

Or use direct grid parameters:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_xspec_mpi \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

`xstar-xspec-mpi` has no `--workers` option: **`mpirun -np N` is the worker count**.  Every MPI rank may execute one `xstar-cpp` process at a time, including rank 0.  Rank 0 alone performs the final canonical STEP/spectrum gather and table publication.  The executable, output directory, and data paths must be visible from every MPI node; a shared filesystem is therefore required by the first implementation.

## Atomic-data discovery

The simplest and most reproducible choice is explicit:

```bash
--data-dir /path/to/xstar/data
```

That directory must contain:

```text
atdb.fits
coheat.dat
```

You may instead provide the files separately to `xstar-cpp`:

```bash
xstar-cpp --atomic-db /path/to/atdb.fits --coheat /path/to/coheat.dat ...
```

When explicit paths are omitted, the native runtime selects the **first existing file** in its search list.

`atdb.fits` discovery order is:

1. explicit parameter-envelope path (`atomic_database`, `atomic_db`, or `atdb`; this includes the path generated by `--atomic-db` / `--data-dir`);
2. `atdb.fits` beside the native parameter envelope;
3. `$XSTAR_ATOMIC_DB`;
4. `$XSTAR_ATDB_FITS`;
5. `$XSTAR_DATA/atdb.fits`;
6. `$HEADAS/refdata/atdb.fits`;
7. `$XSTAR_HOME/data/atdb.fits`;
8. executable-relative `../data/atdb.fits` and `../../data/atdb.fits`;
9. `src/xstar_tools/xstar/data/atdb.fits`;
10. `./atdb.fits`.

`coheat.dat` discovery order is analogous:

1. explicit parameter-envelope path (`coheat_file` or `coheat`; including `--coheat` / `--data-dir`);
2. `coheat.dat` beside the parameter envelope;
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
xstar-cpp --input xstar.par --output run_xstar
```

because `$HEADAS/refdata/atdb.fits` and `$HEADAS/refdata/coheat.dat` are valid fallbacks.  For multi-node MPI, an explicit shared `--data-dir` is recommended so every rank resolves the same files independent of MPI environment-export policy.

## Documentation

Start with:

- `docs/user/first_run.md`
- `docs/user/atomic_data.md`
- `docs/cpp/xstar_cpp.md`
- `docs/cpp/xstar_xspec.md`
- `docs/cpp/xstar_xspec_mpi.md`
- `docs/developer/true_mpi_xstar2xspec_0_6_86.md`

The project deliberately separates scientific acceptance, publication correctness, performance qualification, and orchestration changes.  Do not reinterpret a historical formal ACCEPT/REJECT when a later patch corrects a different contract.
