# `xstar-xspec-mpi`

`xstar-xspec-mpi` is the accepted true-MPI XSTAR2XSPEC executable. It is separate from local-process `xstar-xspec`. The production use case is Linux/HPC; **Windows MPI is not planned**.

## Build

MPI is not part of the default build:

```bash
make -C src/xstar_tools/xstar/cpp
```

Build it explicitly:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

Override the MPI compiler wrapper when needed:

```bash
make -C src/xstar_tools/xstar/cpp mpi MPICXX=/path/to/mpic++
```

## Run

```bash
mpirun -np 4 xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

Direct `key=value` grid input is also accepted.

## Options

`xstar-xspec-mpi` accepts `--input`, `--data-dir`, `--output-dir`/`--output`, `--save`, `--cleanup-work`, `--restart`, `--verbose`, `--initable-bin`, `--xstar-cpp`, `--table-bin`, `--version`, and `--help` with the same meanings as the corresponding local-process driver.

There is deliberately **no** `--processes`, `--workers`, or `-j` process-count option. Concurrency is selected by `mpirun`/`mpiexec -np N`; attempts to use local process-count options are rejected.

## Rank model

Every rank, including rank 0, participates in XSTAR job execution. Jobs are claimed dynamically through an MPI-3 RMA queue, with at most one `xstar-cpp` child per rank.

Rank 0 additionally owns planning, final success checking, canonical STEP concatenation, loopcontrol-ordered spectrum gathering, and the final `xstar-xspec-table` invocation. Rank identity/completion order never determines scientific placement; `loopcontrol` does.

## Filesystem requirement

The current MPI implementation uses job directories as the inter-stage scientific boundary, so all ranks must see the same executables, output directory, atomic-data directory, and any referenced spectrum/density input files. A shared filesystem and an explicit shared `--data-dir` are recommended for multi-node use.

## Failure and restart

A failing rank marks the distributed queue failed; other ranks stop claiming work and active children are terminated when peer failure is observed. Final XSPEC tables are not published for a failed MPI run, while partial products remain for inspection.

`--restart` reuses a job only when `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success` all exist.
