# Execution modes

The stable single-model public modes are:

| Mode | Controller | Scientific execution |
|---|---|---|
| `pure-python` | Python | source-faithful Python implementation |
| `zone-python` | Python | Python controller with qualified modular native kernels |
| `zone-cpp` | Python | shared production-zone native implementation |
| `zone-all` | Python | all-native zone path under the public Python controller |
| `xstar-cpp` | native C++ | standalone native controller |

Use the same names from Python:

```python
config = XStarConfig.from_par_file(
    "xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    mode="zone-cpp",
)
result = run_xstar(config)
```

or from the unified CLI:

```bash
xstar-tools run xstar.par \
  --mode zone-cpp \
  --data-dir /path/to/xstar/data \
  --output-dir run1
```

Advanced per-kernel backend overrides are limited to the Python-controller modes and are not accepted for the monolithic native modes.

## XSTAR2XSPEC concurrency is separate

`xstar-xspec --processes N` runs a bounded pool of independent `xstar-cpp` OS processes; it does not create N threads or MPI ranks. `xstar-xspec-mpi` uses MPI ranks selected by `mpirun/mpiexec -np N` and deliberately does not accept local process-count options.

Any implementation refactor that changes a stable mode-to-runtime mapping must update characterization/regression coverage before changing behavior.
