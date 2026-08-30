# `xstar-xspec-mpi`

`xstar-xspec-mpi` is the `0.6.86` true-MPI XSTAR2XSPEC candidate. It is separate from accepted local-process `xstar-xspec`.

## Build

MPI is not part of the default build:

```bash
make -C src/xstar_tools/xstar/cpp
```

does not require `mpic++` or MPI libraries.

Build the MPI executable explicitly:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

Override the compiler wrapper if needed:

```bash
make -C src/xstar_tools/xstar/cpp mpi MPICXX=/path/to/mpic++
```

## Run

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

Direct `key=value` input is also supported:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

## Rank model

There is no `--workers` option. The MPI launcher defines concurrency:

```text
mpirun -np 2 -> up to two concurrent xstar-cpp processes
mpirun -np 4 -> up to four concurrent xstar-cpp processes
```

Every rank, including rank 0, participates in XSTAR job execution. Jobs are claimed dynamically through an MPI-3 RMA queue. Each rank runs no more than one `xstar-cpp` child at a time.

Rank 0 additionally owns:

1. `xstar-xspec-initable` planning;
2. the final success check;
3. canonical STEP concatenation;
4. canonical spectrum ordering;
5. the final `xstar-xspec-table` invocation.

Rank identity and completion order never determine science placement; `loopcontrol` does.

## Filesystem requirement

The first implementation uses job directories as the inter-stage scientific product boundary, so all ranks must see the same:

- `xstar-xspec-mpi`, `xstar-cpp`, `xstar-xspec-initable`, and `xstar-xspec-table` installation;
- output directory;
- atomic-data directory;
- any spectrum/density input files referenced by jobs.

A shared filesystem is therefore required. An explicit shared `--data-dir` is recommended for multi-node runs.

## Failure behavior

A failing rank marks the distributed queue failed. Other ranks poll that state while their child runs; active children are terminated when a peer failure is observed, and no new jobs are claimed. Final XSPEC tables are not published for the failed MPI run. Existing/partial XSTAR products remain on disk for inspection.

## Restart

`--restart` preserves the accepted `.85.1` success-marker rule: a job is reusable only when `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success` all exist.
