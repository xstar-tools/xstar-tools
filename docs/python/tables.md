# XSTAR2XSPEC from Python

The `xstar_tools.tables` package wraps the native XSTAR2XSPEC executables without reimplementing their scientific/table semantics in Python.

```python
from xstar_tools.tables import (
    XSpecTableProducts,
    build_xspec_tables,
    build_xstinitable,
    run_xstar2xspec,
)
```

## Build the grid plan

```python
build_xstinitable(
    input_file="xstinitable.par",
    data_dir="/path/to/xstar/data",
    output_dir="grid_plan",
    xstar="cpp",
)
```

This creates `xstinitable.lis` and `xstinitable.fits`. `xstar="fortran"` emits the canonical historical `xstar key=value` command contract instead of `xstar-cpp` commands.

## Run the complete pipeline

```python
run_xstar2xspec(
    input_file="xstinitable.par",
    data_dir="/path/to/xstar/data",
    output_dir="table_run",
    processes=4,
    restart=True,
)
```

`processes` is local OS-process concurrency, not a thread count and not MPI. The older `workers=` keyword remains a compatibility alias.

## Build tables from existing spectra

```python
build_xspec_tables(
    "grid_plan/xstinitable.fits",
    ["job1/xout_spect1.fits", "job2/xout_spect1.fits"],
    "tables",
    initable=True,
)

products = XSpecTableProducts.from_directory("tables")
print(products.ain)
print(products.aout)
print(products.mtable)
print(products.etable)
```

The input spectra must be supplied in the planner's `loopcontrol` order. For new production workflows, use the native/canonical `xstinitable.fits` contract (`initable=True`) rather than the older characterization metadata text format.
