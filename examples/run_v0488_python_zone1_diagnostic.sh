#!/usr/bin/env bash
set -euo pipefail

: "${XSTAR_ATDB:=/media/linux/mhd/xstar/xstar/data/atdb.fits}"
export XSTAR_ATDB

# v0.4.88 lightweight original-side history capture across all internal
# DSEC evaluations in call 1. Keep heavy target products selected normally.
export XSTAR_ATOMIC_DSEC_TARGET_CALL="${XSTAR_ATOMIC_DSEC_TARGET_CALL:-1}"
export XSTAR_ATOMIC_HMC_HISTORY_DSEC_CALL="${XSTAR_ATOMIC_HMC_HISTORY_DSEC_CALL:-1}"
export XSTAR_ATOMIC_HMC_TARGET_ELEMENT="${XSTAR_ATOMIC_HMC_TARGET_ELEMENT:-6}"

rm -rf python_zone1_diagnostic_v0488
find original_xstar/helike_type69/c5_ne1 -maxdepth 1 -name 'xstar_*probe.csv' -delete 2>/dev/null || true

PYTHONPATH=src python -u examples/145_diagnose_xstar_zone1_dsec.py \
  --run-script original_xstar/helike_type69/c5_ne1/run_xstar.sh \
  --atdb "$XSTAR_ATDB" \
  --output-dir python_zone1_diagnostic_v0488 \
  --xstar-probe-dir original_xstar/helike_type69/c5_ne1 \
  --summary-json python_zone1_diagnostic_v0488.json \
  --progress \
  --print-summary \
  2>&1 | tee python_zone1_diagnostic_v0488.log
