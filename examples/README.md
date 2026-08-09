# Current xstar-tools examples

This directory contains only examples for the current `xstar_tools` public API and stable execution modes. The former numbered pre-productization/parity-campaign examples were preserved under `historical/examples/legacy_pre_productization/` and are intentionally excluded from lean distributions.

Run examples from an unpacked source checkout without installing the package:

```bash
PACKAGE=$(pwd)
export PYTHONPATH="$PACKAGE/src${PYTHONPATH:+:$PYTHONPATH}"
```

## 1. Backend capabilities

```bash
python examples/01_backend_capabilities.py
python examples/01_backend_capabilities.py --json
```

This is the Python equivalent of:

```bash
python -m xstar_tools.cli.main backends
python -m xstar_tools.cli.main doctor
```

## 2. Stable execution modes

Use the same script for `pure-python`, `zone-python`, `zone-cpp`, `zone-all`, or `xstar-cpp`:

```bash
python examples/02_run_public_mode.py \
  --mode zone-cpp \
  --run-script /path/to/model/run_xstar.sh \
  --atdb /path/to/xstar/data/atdb.fits \
  --coheat /path/to/xstar/data/coheat.dat \
  --output-dir run_zone_cpp
```

`pure-python` requires no C++ runtime. `zone-python`, `zone-cpp`, and `zone-all` require the corresponding native libraries. `xstar-cpp` requires the native frontend/executable.

## 3. Native `xstar-cpp`

```bash
ATDB=/path/to/xstar/data/atdb.fits \
COHEAT=/path/to/xstar/data/coheat.dat \
OUT=run_native \
bash examples/03_run_xstar_cpp.sh
```

The script builds only the public native target it needs and runs it directly from the source tree.

## 4. Public benchmark suite

```bash
DATA=/path/to/xstar/data \
SUITE=/path/to/original_xstar_benchmark_run.tar.gz \
FORTRAN_REF=/path/to/original_xstar.tar.gz \
OUT=benchmark_0663 \
bash examples/04_run_public_benchmark.sh
```

The default benchmark plan runs all 62 cases in `zone-cpp`, `zone-all`, and `xstar-cpp`, plus the configured fast subset in `pure-python` and `zone-python`. Reference archives stay external to the package.

## Validation reference outputs

`examples/reference_outputs/` is retained because current characterization tests and documentation still consume those CSV/JSON fixtures. It is not part of the archived legacy script collection.
