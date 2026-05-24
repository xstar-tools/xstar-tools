#!/usr/bin/env bash
set -euo pipefail

case_dir="${1:-original_xstar/helike_type69/c5_ne1}"

find "$case_dir" -maxdepth 1 -name 'xstar_*probe.csv' -delete 2>/dev/null || true
find "$case_dir" -maxdepth 1 -name 'xstar_dsec_*.csv' -delete 2>/dev/null || true
find "$case_dir" -maxdepth 1 -name 'xstar_calc_*.csv' -delete 2>/dev/null || true

export XSTAR_ATOMIC_DSEC_TARGET_CALL="${XSTAR_ATOMIC_DSEC_TARGET_CALL:-1}"
export XSTAR_ATOMIC_HMC_HISTORY_DSEC_CALL="${XSTAR_ATOMIC_HMC_HISTORY_DSEC_CALL:-1}"
export XSTAR_ATOMIC_HMC_TARGET_DSEC_CALL="${XSTAR_ATOMIC_HMC_TARGET_DSEC_CALL:-1}"
export XSTAR_ATOMIC_HMC_TARGET_DSEC_EVALUATION="${XSTAR_ATOMIC_HMC_TARGET_DSEC_EVALUATION:-24}"
export XSTAR_ATOMIC_HMC_TARGET_DSEC_PHASE="${XSTAR_ATOMIC_HMC_TARGET_DSEC_PHASE:-dsec_internal}"
export XSTAR_ATOMIC_HMC_TARGET_ELEMENT="${XSTAR_ATOMIC_HMC_TARGET_ELEMENT:-6}"

(cd "$case_dir" && ./run_xstar.sh)
