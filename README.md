# xstar_tools

`xstar_tools` is a source-faithful Python/C++ implementation and productization layer for XSTAR photoionization calculations. The project keeps the accepted scientific behavior tied to XSTAR Fortran 2.59g while exposing stable Python, accelerated Python, shared C++, and native standalone execution modes.

The current distribution is **0.6.61**. The accepted scientific revision remains **0.6.48.12.3.45.3.3.8**, the frozen all-62 C++ scientific baseline remains **0.6.48.12.3.44**, the public C API ABI is **60487**, and the production-zone ABI is **6048110**.

## Stable execution modes

Use one of these five public modes instead of the older backend-flag combinations:

| Mode | Controller / radial flow | Local-zone science | Python runtime required during the run? | Intended use |
|---|---|---|---|---|
| `pure-python` | Python | Python | Yes | Source-faithful reference/debug mode |
| `zone-python` | Python | Qualified modular C++ kernels | Yes | Normal accelerated Python mode |
| `zone-cpp` | Shared C++ production-zone evaluator called from Python | C++ | Yes for invocation | Frozen `cpp-zone` behavior |
| `zone-all` | Shared C++ full production path called from Python | C++ | Yes for invocation | Frozen `cpp-all` behavior |
| `xstar-cpp` | Native standalone executable | C++ | No | Native production runs |

The older `--backend`, `--solver-backend`, `--zone-backend`, `--rates-backend`, `--matrix-backend`, and `--emissivity-backend` flags are retained as advanced compatibility aliases. New scripts should use `--mode`.

## Installation

A source checkout is recommended while the public execution and benchmark interfaces are being stabilized.

```bash
python -m pip install -e .
```

The Python package requires NumPy and Astropy. To build the native libraries and `xstar-cpp` frontend:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

The build uses CFITSIO and a C++17 compiler. `zone-python`, `zone-cpp`, `zone-all`, and `xstar-cpp` require the corresponding C++ libraries/executable to be built. `pure-python` does not require the C++ runtime.

Check the installation with:

```bash
xstar-tools backends
xstar-tools doctor
xstar-tools doctor --require zone-cpp
xstar-tools version
```

## Atomic data

For explicit, reproducible runs, provide the XSTAR data directory containing at least:

```text
atdb.fits
coheat.dat
```

For example:

```bash
export XSTAR_DATA=/media/linux/mhd/xstar/xstar/data
```

The examples below use:

```bash
DATA=/media/linux/mhd/xstar/xstar/data
RUN=original_xstar/helike_type69/o7_ne1e10/run_xstar.sh
OUT=$(pwd)/run-o7
```

`run_xstar.sh` is parsed as data; it is not sourced by the Python runner.

## `pure-python`

`pure-python` keeps the Python controller/radial flow, Python local-zone implementation, and all modular science backends in Python. It is the primary source-faithful reference and debugging mode.

```bash
xstar-tools run \
  --mode pure-python \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --output-dir "$OUT/pure-python" \
  --summary-json "$OUT/pure-python/summary.json" \
  --print-summary
```

For expensive development runs, an explicit reusable cache directory can be supplied:

```bash
xstar-tools run \
  --mode pure-python \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --cache-dir "$OUT/cache" \
  --output-dir "$OUT/pure-python"
```

## `zone-python`

`zone-python` retains the Python controller and source-faithful orchestration but enables the qualified modular C++ kernels. This is the normal accelerated Python mode.

```bash
xstar-tools run \
  --mode zone-python \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --output-dir "$OUT/zone-python" \
  --summary-json "$OUT/zone-python/summary.json" \
  --print-summary
```

The mode resolver explicitly selects C++ for the solver, rates, matrix, emissivity, opacity, thermal, and engine backends while leaving the radial controller in Python.

## `zone-cpp`

`zone-cpp` is the stable public name for the frozen `cpp-zone` concept. Python provides the invocation/interface, while a persistent shared C++ production-zone context advances the run zone by zone.

```bash
xstar-tools run \
  --mode zone-cpp \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --output-dir "$OUT/zone-cpp" \
  --summary-json "$OUT/zone-cpp/summary.json" \
  --print-summary
```

The legacy equivalent remains available for compatibility:

```bash
xstar-tools run \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --output-dir "$OUT/legacy-cpp-zone" \
  --backend cpp \
  --solver-backend cpp \
  --rates-backend cpp \
  --matrix-backend cpp \
  --emissivity-backend cpp \
  --zone-backend cpp-zone
```

Prefer `--mode zone-cpp` in new work.

## `zone-all`

`zone-all` is the public name for the current `cpp-all` shared production path.

```bash
xstar-tools run \
  --mode zone-all \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --output-dir "$OUT/zone-all" \
  --summary-json "$OUT/zone-all/summary.json" \
  --print-summary
```

Use this mode when the complete shared C++ production path is desired but Python should still own invocation, capability checks, and provenance collection.

## `xstar-cpp`

`xstar-cpp` is the native standalone executable. Normal runs do not require a Python runtime.

After building:

```bash
make -C src/xstar_tools/xstar/cpp -j2
src/xstar_tools/xstar/cpp/xstar-cpp --help
```

It accepts XSTAR-style `name=value` arguments directly:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --atomic-db "$DATA/atdb.fits" \
  --coheat "$DATA/coheat.dat" \
  --output-dir "$OUT/xstar-cpp" \
  spectrum=pow \
  nsteps=10 \
  niter=99 \
  density=1e10 \
  temperature=100 \
  column=1e20 \
  rlogxi=1.5 \
  habund=1 \
  heabund=1 \
  oabund=1
```

For machine-readable workflows, the qualified native payload remains available:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp run-production \
  --parameters parameters.json \
  --output-dir "$OUT/xstar-cpp"
```

You can also invoke the same native path through the Python public interface:

```bash
xstar-tools run \
  --mode xstar-cpp \
  --run-script "$RUN" \
  --atdb "$DATA/atdb.fits" \
  --coheat-data "$DATA/coheat.dat" \
  --output-dir "$OUT/xstar-cpp-via-python" \
  --print-summary
```

The native frontend writes `xstar_execution_provenance.json` with the package/science revisions, ABIs, native executable identity, CPU dispatch information, fallbacks, return code, and supplied atomic-data hashes.

## Python API

The stable execution modes are also available directly from Python:

```python
from xstar_tools import BackendMode, run_xstar

result = run_xstar(
    mode=BackendMode.ZONE_CPP,
    run_script="original_xstar/helike_type69/o7_ne1e10/run_xstar.sh",
    atdb_path="/media/linux/mhd/xstar/xstar/data/atdb.fits",
    coheat_path="/media/linux/mhd/xstar/xstar/data/coheat.dat",
    output_dir="run-o7-zone-cpp",
)

print(result.ready)
print(result.mode)
print(result.summary["provenance"]["execution"])
```

Available modes and runtime capabilities can be queried programmatically:

```python
from xstar_tools import backends

print(backends.available())
print(backends.describe())
```

## Run provenance

Every stable public run reports, where applicable:

```text
requested_mode
actual_mode
package_version
science_revision
C API ABI
production-zone ABI
C++ library/executable identity
CPU feature / Type50 dispatch path
fallback events
atomic database path and SHA-256
coheat.dat path and SHA-256
```

The distribution version and scientific revision are intentionally separate. Productization releases may change interfaces, packaging, comments, or tooling while the accepted scientific revision remains frozen.

# Canonical 62-model benchmark suite

`0.6.61` adds a public benchmark harness for the canonical 62-case suite. The benchmark inputs and reference archives are **external inputs** and are not bundled in the package.

Expected external files:

```text
original_xstar_benchmark_run.tar.gz       # 62 run_xstar.sh benchmark cases
original_xstar.tar.gz                     # XSTAR Fortran 2.59g reference products
v064812344_all62_three_mode.tar.gz        # accepted 0.6.48.12.3.44 C++ reference, optional
```

The supplied benchmark archive is expected to contain exactly 62 `run_xstar.sh` files: 50 under `helike_type69` and 12 under `mg_ca_triplet_targets`.

## Benchmark execution plan

By default the harness runs all 62 cases in:

```text
zone-cpp
zone-all
xstar-cpp
```

That is 186 full-suite runs.

It also runs this representative O/Mg/Ca subset in both `pure-python` and `zone-python`:

```text
helike_type69/o7_ne1e10
helike_type69/mg11_ne1e8
helike_type69/ca19_xi2_ne1
```

The subset intentionally avoids routine C5 reruns and the retired slow `helike_type69/ca19_ne1e8` smoke case. You can replace the subset with repeated `--python-case` arguments.

## List the benchmark cases

```bash
xstar-tools benchmark list \
  --suite-archive /path/to/original_xstar_benchmark_run.tar.gz
```

## Run the benchmark suite

```bash
PACKAGE=$(pwd)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=/path/to/original_xstar_benchmark_run.tar.gz
OUT=$(pwd)/benchmark-0.6.61

xstar-tools benchmark run \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --out "$OUT" \
  --build-cpp \
  --resume
```

`--resume` reuses completed cases whose state records report success and whose ten standard products are present. Runs are sequential by default. `--jobs N` can be used deliberately when the host has enough CPU and memory.

To run only the three full C++ modes and skip the Python subset:

```bash
xstar-tools benchmark run \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --out "$OUT" \
  --no-python-modes \
  --resume
```

To change the subset, repeat `--python-case`; for example:

```bash
xstar-tools benchmark run \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --out "$OUT" \
  --python-case helike_type69/o7_ne1e10 \
  --python-case helike_type69/ca19_xi2_ne1 \
  --resume
```

To test the orchestration without executing science:

```bash
xstar-tools benchmark run \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --out "$OUT-dry-run" \
  --dry-run
```

## Compare with the Fortran reference

After the runs finish:

```bash
FORTRAN=/path/to/original_xstar.tar.gz

xstar-tools benchmark compare \
  --package "$PACKAGE" \
  --run-root "$OUT" \
  --fortran-reference-archive "$FORTRAN" \
  --out "$OUT/comparisons"
```

The Fortran comparison uses the frozen qualification policy:

- FITS material science is compared using normalized-L1 `< 1%` surfaces;
- identity inventory, order, metadata, and attachment are reported separately;
- the two documented Ca/O `xo01_detal3` structural exceptions are read from `qualification/parity_freeze.json`;
- STEP is compared with the frozen Option-23 comparator;
- `step_numeric_science_accept` is the scientific STEP gate, while inventory/rank/order differences remain diagnostics.

Outputs include:

```text
comparisons/comparison_summary.json
comparisons/fortran_model_summary.csv
comparisons/fortran_product_summary.csv
comparisons/fortran/<mode>/<case>/step.json
comparisons/fortran/<mode>/<case>/step.log
```

## Compare with the accepted C++ 0.6.48.12.3.44 reference

When `v064812344_all62_three_mode.tar.gz` is available:

```bash
CPP44=/path/to/v064812344_all62_three_mode.tar.gz

xstar-tools benchmark compare \
  --package "$PACKAGE" \
  --run-root "$OUT" \
  --fortran-reference-archive "$FORTRAN" \
  --cpp-reference-archive "$CPP44" \
  --out "$OUT/comparisons"
```

The reference mapping is:

| Current public mode | 0.6.48.12.3.44 reference mode |
|---|---|
| `zone-cpp` | `cpp-zone` |
| `zone-all` | `cpp-all` |
| `xstar-cpp` | `standalone-cpp` |

For this frozen C++ reference, the harness checks all nine FITS HDU data payloads for bit-exact equality and requires normalized `xout_step.log` equality after removing measurement/version-only records. It also compares the three newly generated C++ public modes pairwise.

Outputs additionally include:

```text
comparisons/cpp44_exact_summary.csv
comparisons/current_cpp_cross_mode_exact.csv
```

## Run and compare in one command

With only the Fortran reference available:

```bash
xstar-tools benchmark all \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --fortran-reference-archive "$FORTRAN" \
  --out "$OUT" \
  --build-cpp \
  --resume
```

After the C++ 0.6.48.12.3.44 reference archive is available:

```bash
xstar-tools benchmark all \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --fortran-reference-archive "$FORTRAN" \
  --cpp-reference-archive "$CPP44" \
  --out "$OUT" \
  --build-cpp \
  --resume
```

Equivalent source-checkout wrapper:

```bash
tools/benchmarks/run_public_mode_benchmarks.sh \
  "$PACKAGE" \
  "$DATA" \
  "$RUNS" \
  "$FORTRAN" \
  "$OUT" \
  "$CPP44"
```

If the C++ reference is not available yet, omit the sixth wrapper argument. Later, compare the already completed runs without rerunning them:

```bash
tools/benchmarks/compare_public_mode_benchmarks.sh \
  "$PACKAGE" \
  "$OUT" \
  "$FORTRAN" \
  "$OUT/comparisons" \
  "$CPP44"
```

## Benchmark output layout

A benchmark run produces a mirrored case hierarchy:

```text
benchmark-0.6.61/
  run_summary.json
  run_manifest.csv
  runs/
    zone-cpp/<group>/<case>/
    zone-all/<group>/<case>/
    xstar-cpp/<group>/<case>/
    pure-python/<group>/<selected-case>/
    zone-python/<group>/<selected-case>/
  logs/<mode>/<case-slug>.log
  state/<mode>/<case-slug>.json
  comparisons/
```

The benchmark input archive and reference archives remain external. They are extracted only into the benchmark output/work directory and are never copied into the source package or release sdist.

## Science and refactor policy

The project uses this authority hierarchy:

1. accepted qualification evidence for already-closed behavior;
2. canonical XSTAR Fortran 2.59g executable semantics;
3. XSTAR papers/manuals for explanation and scientific context.

Scientific refactors must identify the corresponding source-concordance entry and have characterization tests proving preserved behavior before implementation changes are accepted.

The current source concordance is documented in:

```text
docs/developer/architecture.md
docs/developer/fortran_source_map.md
docs/developer/python_cpp_fortran_concordance.md
docs/science/xstar_references.md
```

## Development and qualification

The active parity boundary can be checked with:

```bash
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
python tools/qualification/check_public_execution_modes.py
python tools/qualification/check_public_benchmark_suite.py
```

For normal productization work, do not rerun all 62 scientific cases after every source-neutral interface/documentation change. The all-62 suite is intended for manual/nightly/release-candidate qualification or intentional scientific/backend changes.

## License

See `LICENSE`.
