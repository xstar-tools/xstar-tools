#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CPP="$ROOT/src/xstar_tools/xstar/cpp"
TEST="$ROOT/tests/v67_standalone"
WORK=${1:-"$TEST/regression_output"}
rm -rf "$WORK"
mkdir -p "$WORK"
make -C "$CPP" -j1 xstar_cpp
c++ -O2 -std=c++17 "$TEST/create_multielement_atdb.cpp" -lcfitsio -o "$WORK/create_multielement_atdb"
"$WORK/create_multielement_atdb" "$WORK/atdb.fits" >/dev/null
COHEAT="$ROOT/src/xstar_tools/xstar/data/coheat.dat"
for name in h he both mg; do
  case "$name" in
    h) abundance='[1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]' ;;
    he) abundance='[0.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]' ;;
    both) abundance='[1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]' ;;
    mg) abundance='[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.0]' ;;
  esac
  cat > "$WORK/parameters_${name}.json" <<JSON
{
  "atomic_database": "atdb.fits",
  "coheat_file": "$COHEAT",
  "physical_abundances": $abundance,
  "habund": 1.0,
  "heabund": 1.0,
  "mgabund": 1.0,
  "density": 1.0e8,
  "pressure": 0.03,
  "temperature": 10.0,
  "temperature_k": 1.0e5,
  "column": 1.0e14,
  "rlogxi": 1.0,
  "rlrad38": 1.0e6,
  "trad": -1.0,
  "spectrum": "pow",
  "initial_radius_cm": 1.0e15,
  "cfrac": 1.0,
  "xee": 1.0,
  "critf": 10.0,
  "ncn2": 64,
  "nsteps": 1,
  "npass": 1,
  "niter": 4
}
JSON
  "$CPP/xstar_cpp" run-production \
    --parameters "$WORK/parameters_${name}.json" \
    --output-dir "$WORK/products_${name}" > "$WORK/run_${name}.log" 2>&1
  test "$(find "$WORK/products_${name}" -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 10
  test "$(find "$WORK/products_${name}" -mindepth 1 -maxdepth 1 | wc -l)" -eq 10
  grep -q 'RESULT=ACCEPT_GENERAL_STANDALONE_PRODUCTION' "$WORK/run_${name}.log"
  grep -q 'SOURCE_RRC_IDENTITIES=' "$WORK/run_${name}.log"
done
"$CPP/xstar_cpp" run-production \
  --parameters "$WORK/parameters_both.json" \
  --output-dir "$WORK/products_full" \
  --artifact-profile full > "$WORK/run_full.log" 2>&1
test -f "$WORK/products_full/standalone_diagnostics/audits/atdb_lowering_audit.json"
test -f "$WORK/products_full/standalone_diagnostics/accepted_checkpoints/zone_0001.json"
test -f "$WORK/products_full/standalone_diagnostics/controller_trajectory.csv"
python3 - "$WORK/products_both" "$WORK/products_full" <<'PYCOMPARE'
from pathlib import Path
import sys

def normalized_fits_bytes(path: Path) -> bytes:
    data = bytearray(path.read_bytes())
    # DATE and CHECKSUM cards legitimately contain the wall-clock write time.
    # Remove only those volatile cards before requiring exact profile equality.
    for offset in range(0, len(data) - 79, 80):
        key = bytes(data[offset:offset + 8]).decode("ascii", "ignore").strip()
        if key in {"DATE", "CHECKSUM", "DATASUM"}:
            data[offset:offset + 80] = b" " * 80
    return bytes(data)

left, right = map(Path, sys.argv[1:3])
files = [
    "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
    "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits",
    "xout_spect1.fits",
]
for name in files:
    if normalized_fits_bytes(left / name) != normalized_fits_bytes(right / name):
        raise SystemExit(f"profile changed FITS science content: {name}")
PYCOMPARE
printf '%s\n' 'V048746255172567_SYNTHETIC_H=ACCEPT' \
  'V048746255172567_SYNTHETIC_HE=ACCEPT' \
  'V048746255172567_SYNTHETIC_H_HE=ACCEPT' \
  'V048746255172567_SYNTHETIC_MG=ACCEPT' \
  'V048746255172567_TYPE53_RRC=ACCEPT' \
  'V048746255172567_FILE_SILENT_DEFAULT=ACCEPT' \
  'V048746255172567_ARTIFACT_PROFILE_FULL=ACCEPT' \
  'V048746255172567_FITS_PROFILE_INDEPENDENCE=ACCEPT' \
  'V048746255172567_RESULT=ACCEPT'
