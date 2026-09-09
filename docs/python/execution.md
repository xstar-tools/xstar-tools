# Running XSTAR from Python

The stable application API is exported from `xstar_tools`:

```python
from xstar_tools import BackendMode, XStarConfig, XStarData, run_xstar
```

## From `xstar.par`

```python
from xstar_tools import XStarConfig, run_xstar

config = XStarConfig.from_par_file(
    "xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    mode="zone-cpp",
    threads=1,
)
config.validate()
result = run_xstar(config)

print(result.success)
print(result.status)
print(result.runtime_seconds)
print(result.products.spectrum)
```

## From a parameter mapping

```python
config = XStarConfig.from_mapping(
    {
        "spectrum": "pow",
        "density": "1e12",
        "column": "1e20",
        "rlogxi": "1",
        "npass": "1",
        "modelname": "python_example",
    },
    data_dir="/path/to/xstar/data",
    output_dir="run_mapping",
    mode="pure-python",
)
```

Textual numeric values can be retained as strings when preserving source input spelling matters.

## From an existing FORTRAN run directory

```python
config = XStarConfig.from_fortran_run_directory(
    "/path/to/fortran/run",
    data_dir="/path/to/xstar/data",
    output_dir="run_from_fortran_inputs",
    mode="zone-cpp",
)
```

The directory must contain `run_xstar.sh`.

## Inspect or serialize the configuration

```python
mapping = config.parameter_mapping()
command = config.to_xstar_command()
config.to_par_file("normalized_xstar.par")
```

`validate()` checks the input source, selected execution mode, and local XSTAR data without running the scientific calculation.

## Results

`run_xstar(XStarConfig(...))` returns `XStarResult`. Useful fields include:

```python
result.success
result.status
result.return_code
result.output_dir
result.runtime_seconds
result.provenance
result.diagnostics
result.warnings
result.products.expected_fits()
result.products.produced_fits()
result.as_dict()
```

`XStarProducts` provides deterministic paths for the standard XSTAR products, including abundance, line, RRC, continuum, spectrum, detail FITS products, and `xout_step.log`.

## Output directory policy

A non-empty output directory is rejected by default. Use `overwrite=True` when deliberate replacement is wanted:

```python
config = XStarConfig.from_par_file(
    "xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    overwrite=True,
)
```

## Stable modes

`BackendMode` exposes `PURE_PYTHON`, `ZONE_PYTHON`, `ZONE_CPP`, `ZONE_ALL`, and `XSTAR_CPP`. `ExecutionMode` is also exported for the underlying execution classification; applications normally choose `BackendMode`/its string values through `XStarConfig`.

The older keyword-style call remains available for compatibility:

```python
run_xstar(mode="zone-cpp", run_script="run_xstar.sh", atdb_path="/path/to/atdb.fits")
```

New applications should prefer the `XStarConfig` form because it returns the typed `XStarResult` contract.
