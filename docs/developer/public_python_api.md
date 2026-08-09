# Stable public Python API

Milestone 4 introduces a deliberately small public application interface over the already-qualified execution paths.

## Public namespace

The supported user-facing surface is:

```python
from xstar_tools import (
    BackendMode,
    XStarConfig,
    XStarData,
    XStarProducts,
    XStarResult,
    run_xstar,
)
```

`xstar_tools.xstar.*` remains the scientific/source-faithful implementation layer.  Qualification scripts remain under `tools/qualification/`; they are not normal runtime APIs.  Historical attribution and parity campaign interfaces remain outside the installed source tree under `historical/`.

## Configuration

```python
config = XStarConfig(
    input_file="xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    mode=BackendMode.ZONE_PYTHON,
)
```

Exactly one parameter source is accepted:

- `input_file=...` for a HEASoft/IRAF-style `.par` file or command-style input file;
- `XStarConfig.from_mapping({...})`;
- `XStarConfig.from_fortran_run_directory(...)`, which consumes that directory's `run_xstar.sh` as data.

`XStarConfig.to_par_file()` writes deterministic HEASoft/IRAF-style rows in canonical parameter-name order.  Textual numeric literals read from a `.par`/command source are kept as text so values such as `1.23456789E+22` are not needlessly round-tripped through binary64 before the source-faithful parameter path sees them.

The default output policy is conservative: a non-empty target directory raises `FileExistsError`.  Set `overwrite=True` to remove and recreate the run directory before execution.  Repeating the same configuration with `overwrite=True` is therefore deterministic with respect to standard product paths.

## Data locator

```python
from xstar_tools.data import XStarData

data = XStarData.from_directory("/path/to/xstar/data")
data.validate()
```

Validation is local-only and requires:

- `atdb.fits` in the selected data directory;
- `coheat.dat` in the selected data directory;
- the package `xstar/cpp/constants.def` file.

Optional cache paths may be registered explicitly.  Validation never downloads large scientific data.  Existing download helpers remain explicit user actions rather than run-time side effects.

## Execution and result

```python
result = run_xstar(config)

print(result.success)
print(result.return_code)
print(result.output_dir)
print(result.runtime_seconds)
print(result.provenance)
print(result.products.spectrum)
print(result.products.lines)
print(result.step_log)
```

`XStarProducts` exposes deterministic paths for the nine principal FITS products plus `xout_step.log`.  `produced_fits` contains only files actually present after the run.

`XStarResult` contains:

- success/status/return code;
- output directory and typed product paths;
- elapsed runtime and any underlying timing mapping;
- execution/data provenance;
- diagnostics and warnings;
- the underlying runner summary for advanced debugging.

## Stable modes and advanced overrides

`BackendMode` contains the five Milestone-3 modes: `PURE_PYTHON`, `ZONE_PYTHON`, `ZONE_CPP`, `ZONE_ALL`, and `XSTAR_CPP`.

Advanced modular backend overrides are accepted only for the Python-controller modes (`pure-python` and `zone-python`).  They are validated before execution and make `actual_mode` report `advanced`.  Overrides are rejected for the monolithic `zone-cpp`, `zone-all`, and `xstar-cpp` paths so those names continue to mean exactly the frozen qualified behavior.

## Repeated runs and process isolation

The public wrapper restores run-scoped environment variables after every invocation.  In particular, thread/reproducibility settings do not persist into the next call.  Backend environment isolation remains owned by the Milestone-3 execution layer.

Repeated calls in one Python process are supported.  Output reuse is explicit through `overwrite=True`; without it, a non-empty output directory is rejected before science executes.

## Compatibility

The Milestone-3 keyword-style API remains available:

```python
run_xstar(mode="zone-cpp", run_script="run_xstar.sh", ...)
```

It continues to return `PublicRunResult` for compatibility with the benchmark/CLI layer.  New applications should use `run_xstar(XStarConfig(...))`, which returns `XStarResult`.

## Refactor gate

A change to the public wrapper is acceptable only if `tools/qualification/check_public_python_api.py` passes.  The gate requires:

1. the stable public objects are exported from `xstar_tools`;
2. parameter/data/output policies remain deterministic;
3. the five stable modes still resolve through the Milestone-3 mapping;
4. invalid combinations fail before execution;
5. run-scoped environment variables are restored;
6. the frozen scientific C++ source/header set remains unchanged;
7. current source-characterization/parity gates continue to pass.
