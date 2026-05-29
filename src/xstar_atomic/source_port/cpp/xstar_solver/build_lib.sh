#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compiler="${CXX:-g++}"
target="${here}/libxstar_solver.so"
runtime_dir="$(cd "${here}/../.." && pwd)"
runtime_target="${runtime_dir}/libxstar_solver.so"

"${compiler}" -O3 -std=c++17 -fPIC -shared \
  "${here}/level_population.cpp" \
  -o "${target}"

echo "Built ${target}"
mkdir -p "${runtime_dir}"
cp "${target}" "${runtime_target}"
echo "Copied ${runtime_target}"
