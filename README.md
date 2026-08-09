# xstar_tools

`xstar_tools` is a source-faithful Python/C++ implementation and productization layer for XSTAR photoionization calculations. The project keeps the accepted scientific behavior tied to XSTAR Fortran 2.59g while exposing stable Python, accelerated Python, shared C++, and native standalone execution modes.

The current distribution is **0.6.69**. The accepted scientific revision remains **0.6.48.12.3.45.3.3.8**, the frozen all-62 C++ scientific baseline remains **0.6.48.12.3.44**, the public C API ABI is **60487**, and the production-zone ABI is **6048110**.

User-facing controller logs now label the **package version** and **science revision** separately. For backward compatibility, the legacy Python `xstar_tools.__version__` symbol remains the frozen science revision; use `xstar_tools.__package_version__` or `xstar-tools version` for the distribution version.

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

The native frontend uses C++17 `std::filesystem`. GNU/libstdc++ builds link the compatibility library through `FILESYSTEM_LIBS` (default `-lstdc++fs`) so older GCC toolchains work as well as current ones. If a non-GNU standard library does not provide that compatibility archive, override it explicitly, for example `make -C src/xstar_tools/xstar/cpp FILESYSTEM_LIBS=`.

Check the installation with:

```bash
xstar-tools backends
xstar-tools doctor
xstar-tools doctor --require zone-cpp
xstar-tools version
```

The primary Milestone-5 command tree is:

```text
xstar-tools run
xstar-tools inspect
xstar-tools data
xstar-tools backends
xstar-tools compare
xstar-tools doctor
xstar-tools version
```

Advanced development and release qualification interfaces live under `xstar-tools dev ...` and `xstar-tools qualify ...`. Legacy console scripts remain installed for one deprecation cycle.

Normal `xstar-tools run` execution uses standard Python logging plus human-readable science progress. Add `--json-log FILE.jsonl` for structured run-start/run-completion/failure events with final provenance, and `--summary-json FILE.json` for the stable `XStarResult` payload. The CLI constructs `XStarConfig` and calls the same `run_xstar(config)` orchestration layer as the public Python API.

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
xstar-tools run "$RUN" \
  --mode pure-python \
  --data-dir "$DATA" \
  --output-dir "$OUT/pure-python" \
  --summary-json "$OUT/pure-python/summary.json"
```

For expensive development runs, an explicit reusable cache directory can be supplied:

```bash
xstar-tools run "$RUN" \
  --mode pure-python \
  --data-dir "$DATA" \
  --cache-dir "$OUT/cache" \
  --output-dir "$OUT/pure-python"
```

## `zone-python`

`zone-python` retains the Python controller and source-faithful orchestration but enables the qualified modular C++ kernels. This is the normal accelerated Python mode.

```bash
xstar-tools run "$RUN" \
  --mode zone-python \
  --data-dir "$DATA" \
  --output-dir "$OUT/zone-python" \
  --summary-json "$OUT/zone-python/summary.json"
```

The mode resolver explicitly selects C++ for the solver, rates, matrix, emissivity, opacity, thermal, and engine backends while leaving the radial controller in Python.

## `zone-cpp`

`zone-cpp` is the stable public name for the frozen `cpp-zone` concept. Python provides the invocation/interface, while a persistent shared C++ production-zone context advances the run zone by zone.

```bash
xstar-tools run "$RUN" \
  --mode zone-cpp \
  --data-dir "$DATA" \
  --output-dir "$OUT/zone-cpp" \
  --summary-json "$OUT/zone-cpp/summary.json"
```

The legacy equivalent remains available for compatibility:

```bash
xstar-tools dev legacy-run \
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
xstar-tools run "$RUN" \
  --mode zone-all \
  --data-dir "$DATA" \
  --output-dir "$OUT/zone-all" \
  --summary-json "$OUT/zone-all/summary.json"
```

Use this mode when the complete shared C++ production path is desired but Python should still own invocation, capability checks, and provenance collection.

## `xstar-cpp`

`xstar-cpp` is the first-class native standalone executable. Normal runs do not require a Python runtime.

After building:

```bash
make -C src/xstar_tools/xstar/cpp -j2
src/xstar_tools/xstar/cpp/xstar-cpp --help
```

Run a standard HEASoft/IRAF-style parameter file directly:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir "$DATA" \
  --output "$OUT/xstar-cpp"
```

XSTAR-style `name=value` parameters remain valid without a `.par` file:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --data-dir "$DATA" \
  --output "$OUT/xstar-cpp" \
  spectrum=pow nsteps=10 niter=99 density=1e10 temperature=100 \
  column=1e20 rlogxi=1.5 habund=1 heabund=1 oabund=1
```

Optional native orchestration features include:

```text
--json-summary FILE
--provenance FILE
--progress {none,text,json}
--threads N
--profile FILE
--deterministic
--print-option N
```

These are `xstar-cpp` extensions, not required XSTAR inputs. `--print-option` is read-only and extracts a section from the completed `xout_step.log`; it does not change STEP science.

Runtime ABI compatibility is explicit:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp --abi
```

Packaged builds query the linked C API (`60487`) and production-zone ABI (`6048110`) before science and fail clearly on mismatch.

For machine-readable compatibility workflows, the qualified native payload remains available:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp run-production \
  --parameters parameters.json \
  --output-dir "$OUT/xstar-cpp"
```

You can also invoke the same native scientific path through the Python public interface:

```bash
xstar-tools run "$RUN" \
  --mode xstar-cpp \
  --data-dir "$DATA" \
  --output-dir "$OUT/xstar-cpp-via-python"
```

The public frontend contains no scientific algorithms. It delegates to the compatibility `xstar_cpp run-production` executable, while `zone-cpp`/`zone-all` use the same frozen standalone production operator through `libxstar_production_zone.so`. See `docs/developer/xstar_cpp.md` and `docs/developer/c_abi.md`.

## Python API

The recommended stable Python API is configuration-driven:

```python
from xstar_tools import XStarConfig, BackendMode, run_xstar

config = XStarConfig(
    input_file="xstar.par",
    data_dir="/media/linux/mhd/xstar/xstar/data",
    output_dir="run1",
    mode=BackendMode.ZONE_PYTHON,
)

result = run_xstar(config)

print(result.success)
print(result.return_code)
print(result.products.spectrum)
print(result.step_log)
print(result.provenance["execution"])
```

The same object can be constructed from an in-memory mapping:

```python
config = XStarConfig.from_mapping(
    {
        "spectrum": "pow",
        "density": "1e10",
        "temperature": "100",
        "column": "1e20",
        "rlogxi": "1.5",
    },
    data_dir="/media/linux/mhd/xstar/xstar/data",
    output_dir="run-mapping",
    mode=BackendMode.PURE_PYTHON,
)
```

Or from an original Fortran run directory containing `run_xstar.sh`:

```python
config = XStarConfig.from_fortran_run_directory(
    "original_xstar/helike_type69/o7_ne1e10",
    data_dir="/media/linux/mhd/xstar/xstar/data",
    output_dir="run-o7",
    mode=BackendMode.ZONE_CPP,
)
result = run_xstar(config)
```

Canonical HEASoft-style parameter files can be read/written without running science:

```python
config = XStarConfig.from_par_file(
    "xstar.par",
    data_dir="/media/linux/mhd/xstar/xstar/data",
    output_dir="run1",
)
config.to_par_file("canonical-xstar.par")
```

Local scientific data has one explicit locator and validator:

```python
from xstar_tools.data import XStarData

data = XStarData.from_directory("/media/linux/mhd/xstar/xstar/data")
data.validate()
```

`XStarData.validate()` never downloads `atdb.fits` or other large data. Downloads remain explicit user actions.

The public result is `XStarResult`; `result.products` is an `XStarProducts` accessor for the nine principal FITS outputs and `xout_step.log`. The default API refuses to run into a non-empty output directory; pass `overwrite=True` in `XStarConfig` to replace that directory deterministically.

The Milestone-3 keyword-style form remains available for compatibility with existing benchmark and CLI code:

```python
from xstar_tools import run_xstar

legacy = run_xstar(
    mode="zone-cpp",
    run_script="run_xstar.sh",
    atdb_path="/path/to/atdb.fits",
    coheat_path="/path/to/coheat.dat",
    output_dir="run-legacy",
)
```

Available modes and runtime capabilities can still be queried programmatically:

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
xstar-tools qualify benchmark list \
  --suite-archive /path/to/original_xstar_benchmark_run.tar.gz
```

## Run the benchmark suite

```bash
PACKAGE=$(pwd)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=/path/to/original_xstar_benchmark_run.tar.gz
OUT=$(pwd)/benchmark-0.6.61

xstar-tools qualify benchmark run \
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
xstar-tools qualify benchmark run \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$RUNS" \
  --out "$OUT" \
  --no-python-modes \
  --resume
```

To change the subset, repeat `--python-case`; for example:

```bash
xstar-tools qualify benchmark run \
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
xstar-tools qualify benchmark run \
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

xstar-tools compare \
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

xstar-tools compare \
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
xstar-tools qualify benchmark all \
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
xstar-tools qualify benchmark all \
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
