# Troubleshooting

## Data validation fails

Confirm the selected directory contains readable `atdb.fits` and `coheat.dat`:

```bash
xstar-tools doctor --data-dir /path/to/xstar/data
```

## A C++ mode is unavailable

Inspect the installed native-build metadata and capabilities:

```bash
xstar-tools backends
xstar-tools doctor --require zone-cpp
```

For a source checkout, build with `make -C src/xstar_tools/xstar/cpp -j2`. For a Linux source/wheel installation that must contain native support, reinstall with `XSTAR_TOOLS_NATIVE=required`. Python-only installations intentionally expose only `pure-python`.

## Output directory already exists

Stable runs reject non-empty output directories by default. Choose a new directory or explicitly request replacement with Python `overwrite=True` / CLI `--overwrite`.

## Package version and science revision differ

That is expected during productization. Use `xstar-tools version`; do not infer the scientific baseline from the distribution version.

## A comparison reports inventory differences

The qualification framework intentionally separates material numerical science from identity/order/inventory diagnostics. Known accepted structural exceptions are encoded in the parity-freeze metadata rather than hidden by broad tolerances.

## Need development diagnostics

Use `xstar-tools dev ...` or `xstar-tools qualify ...`. Normal user workflows should not depend on qualification marker strings.

## `xstar-xspec --workers 2` does not create MPI ranks

That option creates two independent local `xstar-cpp` child **processes**. It is not a thread count and it does not call `mpirun`. Use `xstar-xspec-mpi` for true MPI.

## `make mpi` says `mpic++` is missing

MPI is optional and is intentionally excluded from the default build. Install/load an MPI implementation that provides a C++ wrapper, or point the build at the correct wrapper:

```bash
make -C src/xstar_tools/xstar/cpp mpi MPICXX=/path/to/mpic++
```

## MPI ranks cannot see the plan, data, or job directories

The first `xstar-xspec-mpi` implementation requires a shared filesystem. Use paths visible from every node and prefer an explicit shared atomic-data directory:

```bash
mpirun -np 4 xstar-xspec-mpi \
  --input /shared/model/xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/results/run1
```
