#!/usr/bin/env bash
set -euo pipefail

rm -rf xstar_zone1_analysis_v0488 zone1_parity_v0488

PYTHONPATH=src python -u examples/147_analyze_xstar_zone1_dsec_probe.py \
  --xstar-probe-dir original_xstar/helike_type69/c5_ne1 \
  --out-dir xstar_zone1_analysis_v0488 \
  --python-diagnostic-dir python_zone1_diagnostic_v0488 \
  --compare-out-dir zone1_parity_v0488 \
  --skip-input-fingerprints \
  --progress \
  2>&1 | tee zone1_analysis_v0488.log
