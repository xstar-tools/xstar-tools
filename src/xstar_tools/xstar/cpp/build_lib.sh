#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compiler="${CXX:-g++}"
build_one() {
  local source="$1"
  local target="$2"
  "${compiler}" -O3 -std=c++17 -fPIC -shared \
    "${here}/${source}" \
    -o "${here}/${target}"
  echo "Built ${here}/${target}"
}

build_one level_population.cpp libxstar_solver.so
build_one rate_kernels.cpp libxstar_rates.so
build_one matrix_kernels.cpp libxstar_matrix.so
build_one line_emissivity.cpp libxstar_emissivity.so
