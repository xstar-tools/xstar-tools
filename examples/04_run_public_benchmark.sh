#!/usr/bin/env bash
set -euo pipefail

# Run the public 62-case benchmark from an unpacked source tree.
PACKAGE=${PACKAGE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
export PYTHONPATH="$PACKAGE/src${PYTHONPATH:+:$PYTHONPATH}"

: "${DATA:?set DATA=/path/to/xstar/data}"
: "${SUITE:?set SUITE=/path/to/original_xstar_benchmark_run.tar.gz}"
: "${FORTRAN_REF:?set FORTRAN_REF=/path/to/original_xstar.tar.gz}"
OUT=${OUT:-benchmark_public_modes}

python -m xstar_tools.cli.main benchmark all \
  --package "$PACKAGE" \
  --data "$DATA" \
  --suite-archive "$SUITE" \
  --fortran-reference-archive "$FORTRAN_REF" \
  --out "$OUT" \
  --build-cpp \
  --resume
