# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations. It preserves an accepted scientific baseline tied to XSTAR Fortran 2.59g while providing a stable Python API, one primary CLI, accelerated/shared C++ modes, and a native standalone `xstar-cpp` executable.

**Distribution:** `0.6.70`  
**Accepted science revision:** `0.6.48.12.3.45.3.3.8`  
**Frozen C++ all-62 baseline:** `0.6.48.12.3.44`  
**C API ABI:** `60487`  
**Production-zone ABI:** `6048110`

Product/package versions can advance without changing the frozen science revision. Use `xstar-tools version` to see both.

## 1. What `xstar-tools` is

The project exposes the qualified XSTAR implementation through five stable execution modes:

| Mode | What runs the calculation | Typical use |
|---|---|---|
| `pure-python` | Python controller, local-zone solve, and Python science kernels | Reference/debugging |
| `zone-python` | Python controller with qualified modular C++ kernels | Accelerated Python |
| `zone-cpp` | Shared C++ production-zone evaluator, invoked from Python | Production shared-zone path |
| `zone-all` | Shared C++ full production path, invoked from Python | Production shared-all path |
| `xstar-cpp` | Native standalone executable | Python-free native runs |

The stable public API and CLI are productization layers. They do not duplicate the qualified scientific algorithms in `xstar_tools.xstar` and the native C++ core.

## 2. Relationship to XSTAR

XSTAR Fortran 2.59g remains the canonical executable source authority when new source behavior needs interpretation. Accepted qualification evidence is the authority for behavior that has already been closed. XSTAR papers and manuals provide the scientific explanation and context.

The accepted parity boundary is documented in [`PARITY_FREEZE.md`](PARITY_FREEZE.md) and `qualification/parity_freeze.json`. Productization work must not silently change that boundary.

## 3. Installation

Milestone 8 will formalize binary wheels/native packaging. For the current source release, install from the extracted source tree:

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e '.[dev]'
```

`pure-python` needs no C++ runtime. To build the native libraries and `xstar-cpp` used by the C++ modes:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

The native build requires a C++17 compiler and CFITSIO. GNU/libstdc++ builds use `FILESYSTEM_LIBS` (default `-lstdc++fs`) for compatibility with older toolchains.

Check the installation:

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

## 4. Atomic-data setup

Runs are local-data-only: they do not silently download scientific data. Point the run at an XSTAR data directory containing at least:

```text
atdb.fits
coheat.dat
```

The package also validates its shipped `src/xstar_tools/xstar/cpp/constants.def`.

```bash
DATA=/path/to/xstar/data
xstar-tools doctor --data-dir "$DATA"
```

In Python:

```python
from xstar_tools.data import XStarData

data = XStarData.from_directory("/path/to/xstar/data")
validation = data.validate()
print(validation.valid)
```

See the [atomic-data guide](docs/user/atomic_data.md) for validation, configured paths, and the explicit download helper.

## 5. Five-minute Python example

```python
from xstar_tools import XStarConfig, BackendMode, run_xstar

config = XStarConfig(
    input_file="xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    mode=BackendMode.ZONE_PYTHON,
)

result = run_xstar(config)
print(result.success)
print(result.products.spectrum)
print(result.step_log)
```

`XStarConfig.from_mapping(...)` and `XStarConfig.from_fortran_run_directory(...)` are also supported. The API rejects a non-empty output directory by default; set `overwrite=True` when replacement is intentional.

## 6. Five-minute CLI example

The primary CLI is:

```text
xstar-tools run
xstar-tools inspect
xstar-tools data
xstar-tools backends
xstar-tools compare
xstar-tools doctor
xstar-tools version
```

Run a parameter file:

```bash
xstar-tools run xstar.par \
  --mode zone-python \
  --data-dir /path/to/xstar/data \
  --output-dir run1
```

Other stable modes use the same command:

```bash
xstar-tools run xstar.par --mode pure-python --data-dir "$DATA" --output-dir run-py
xstar-tools run xstar.par --mode zone-cpp   --data-dir "$DATA" --output-dir run-zcpp
xstar-tools run xstar.par --mode zone-all   --data-dir "$DATA" --output-dir run-zall
xstar-tools run xstar.par --mode xstar-cpp  --data-dir "$DATA" --output-dir run-native
```

The CLI constructs `XStarConfig` and calls the same `run_xstar(config)` orchestration layer as the Python API.

## 7. Backend modes

Use `xstar-tools backends` to see which modes are available on the current host. Use `xstar-tools doctor --require MODE` when a workflow requires a specific native capability.

`pure-python` is the reference/debug path. `zone-python` is the normal accelerated Python path. `zone-cpp` and `zone-all` expose the frozen shared C++ production paths. `xstar-cpp` is the standalone native frontend.

See [choosing a backend](docs/user/backends.md) for selection guidance and compatibility aliases.

## 8. `xstar-cpp` example

After building the native target:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output run-native
```

XSTAR-style `name=value` inputs are also accepted. Optional `xstar-cpp` extensions include `--json-summary`, `--provenance`, `--progress`, `--threads`, `--profile`, `--deterministic`, `--print-option`, and `--abi`.

The frontend contains no independent scientific implementation: it delegates to the same frozen native production operator used by the shared production paths.

## 9. Output products

`XStarResult.products` provides deterministic paths for the nine principal FITS products plus `xout_step.log`:

```text
xout_abund1.fits
xout_lines1.fits
xout_rrc1.fits
xout_cont1.fits
xout_spect1.fits
xo01_detail.fits
xo01_detal2.fits
xo01_detal3.fits
xo01_detal4.fits
xout_step.log
```

See [output products](docs/user/outputs.md) for typed accessors and output-directory behavior.

## 10. Reproducibility and provenance

Stable runs record, where applicable, the requested/actual mode, package and science revisions, C/zone ABI versions, native identities, CPU dispatch information, fallback events, and scientific-data paths/hashes.

CLI runs can emit both a stable result summary and structured event log:

```bash
xstar-tools run xstar.par \
  --mode zone-python \
  --data-dir "$DATA" \
  --output-dir run1 \
  --summary-json run1-summary.json \
  --json-log run1-events.jsonl
```

## 11. Documentation

The documentation is layered by audience:

- [User guide](docs/user/index.md) — installation, first run, configuration, backends, outputs, performance, troubleshooting;
- [Python API](docs/api/index.md) — generated stable Python API reference;
- [C++/CLI reference](docs/cpp/index.md) — `xstar-cpp`, C ABI, and native build reference;
- [Developer guide](docs/developer/index.md) — architecture, source concordance, qualification, performance, and version/freeze policy;
- [Science guide](docs/science/index.md) — algorithm overview, XSTAR literature, and data/rate semantics;
- [Historical guide](docs/history/index.md) — how to find preserved historical qualification evidence.

Build the Sphinx site with:

```bash
python -m pip install -e '.[docs]'
make -C docs/sphinx html
```

Release documentation uses warnings-as-errors. Link checking is available with `make -C docs/sphinx linkcheck`.

## 12. Development and qualification

Advanced interfaces are grouped under:

```text
xstar-tools dev ...
xstar-tools qualify ...
```

Legacy console scripts remain for the current deprecation cycle. Release/science qualification lives under `tools/qualification/`; historical attribution evidence lives under `historical/` and is intentionally separate from normal user documentation.

The accepted all-62 C++ baseline established exact cross-mode C++ products before productization. Do not reopen frozen scientific behavior unless a new material discrepancy is demonstrated.

## 13. Citation and license

The package metadata declares the project under the **MIT** license. This source tree does not assert a project DOI. When publishing science produced with `xstar-tools`, record the package version and science revision and cite the relevant XSTAR literature listed in the [XSTAR references](docs/science/xstar_references.md).

For the exact software identity used in a run:

```bash
xstar-tools version
```
