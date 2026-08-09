#!/usr/bin/env bash
set -euo pipefail

# Source-tree native example. No package installation is required.
PACKAGE=${PACKAGE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
CPP_DIR="$PACKAGE/src/xstar_tools/xstar/cpp"

make -C "$CPP_DIR" xstar-cpp

# Example:
#   ATDB=/path/to/xstar/data/atdb.fits \
#   COHEAT=/path/to/xstar/data/coheat.dat \
#   OUT=run_native \
#   bash examples/03_run_xstar_cpp.sh
: "${ATDB:?set ATDB=/path/to/atdb.fits}"
: "${COHEAT:?set COHEAT=/path/to/coheat.dat}"
OUT=${OUT:-run_native}

"$CPP_DIR/xstar-cpp" \
  --atomic-db "$ATDB" \
  --coheat "$COHEAT" \
  --output-dir "$OUT" \
  cfrac=1 temperature=100 density=1e8 spectrum=pow column=1e22 rlogxi=1.5
