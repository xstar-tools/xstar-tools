#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compiler="${CXX:-g++}"
runtime_dir="$(cd "${here}/.." && pwd)"

build_one() {
  local source="$1"
  local target="$2"
  local runtime_target="${runtime_dir}/${target}"
  "${compiler}" -O3 -std=c++17 -fPIC -shared \
    "${here}/${source}" \
    -o "${here}/${target}"
  echo "Built ${here}/${target}"
  mkdir -p "${runtime_dir}"
  cp "${here}/${target}" "${runtime_target}"
  echo "Copied ${runtime_target}"
}

build_one level_population.cpp libxstar_solver.so
build_one rate_kernels.cpp libxstar_rates.so
