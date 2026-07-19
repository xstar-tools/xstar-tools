#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CPP="$ROOT/src/xstar_tools/xstar/cpp"
TEST="$ROOT/tests/v72_atdb_layouts"
FIXED_SRC="$ROOT/tests/v67_standalone/create_multielement_atdb.cpp"
WORK=${1:-"$TEST/regression_output"}
rm -rf "$WORK"
mkdir -p "$WORK"
make -C "$CPP" -j1 xstar_cpp
c++ -O2 -std=c++17 "$FIXED_SRC" -lcfitsio -o "$WORK/create_fixed_atdb"
c++ -O2 -std=c++17 "$TEST/create_variable_atdb.cpp" -lcfitsio -o "$WORK/create_variable_atdb"
"$WORK/create_fixed_atdb" "$WORK/fixed_atdb.fits" >/dev/null
"$WORK/create_variable_atdb" "$WORK/variable_atdb.fits" >/dev/null
COHEAT="$ROOT/src/xstar_tools/xstar/data/coheat.dat"
for layout in fixed variable; do
cat > "$WORK/parameters_${layout}.json" <<JSON
{
  "atomic_database": "${layout}_atdb.fits",
  "coheat_file": "$COHEAT",
  "physical_abundances": [1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.0],
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
  "niter": 4,
  "standalone_charge_tolerance": 10.0,
  "standalone_thermal_tolerance": 10.0
}
JSON
"$CPP/xstar_cpp" run-production \
  --parameters "$WORK/parameters_${layout}.json" \
  --output-dir "$WORK/products_${layout}" > "$WORK/run_${layout}.log" 2>&1
test "$(find "$WORK/products_${layout}" -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 10
grep -q 'RESULT=ACCEPT_GENERAL_STANDALONE_CANDIDATE' "$WORK/run_${layout}.log"
done
python3 - "$WORK/products_fixed" "$WORK/products_variable" <<'PYCOMPARE'
from pathlib import Path
import sys

def normalized_fits_bytes(path: Path) -> bytes:
    data = bytearray(path.read_bytes())
    for offset in range(0, len(data) - 79, 80):
        key = bytes(data[offset:offset + 8]).decode("ascii", "ignore").strip()
        if key in {"DATE", "CHECKSUM", "DATASUM"}:
            data[offset:offset + 80] = b" " * 80
    return bytes(data)

left, right = map(Path, sys.argv[1:3])
for name in [
    "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
    "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits",
    "xout_spect1.fits",
]:
    if normalized_fits_bytes(left / name) != normalized_fits_bytes(right / name):
        raise SystemExit(f"fixed/variable ATDB layout changed science content: {name}")
def normalized_step(path: Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("native_step_log_formatter "):
            continue
        if stripped.startswith("native_controller_and_fits "):
            continue
        if stripped.startswith("total time "):
            continue
        if stripped.startswith("total time human "):
            continue
        out.append(line)
    return out
if normalized_step(left / "xout_step.log") != normalized_step(right / "xout_step.log"):
    raise SystemExit("fixed/variable ATDB layout changed xout_step.log science content")
PYCOMPARE
printf '%s\n' \
  'V048746255172572_FIXED_WIDTH_PACKED_COLUMNS=ACCEPT' \
  'V048746255172572_VARIABLE_LENGTH_PACKED_COLUMNS=ACCEPT' \
  'V048746255172572_PACKED_LAYOUT_SCIENCE_EQUIVALENCE=ACCEPT' \
  'V048746255172572_FILE_SILENT_PRODUCTS=ACCEPT' \
  'V048746255172572_RESULT=ACCEPT'
