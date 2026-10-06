#!/usr/bin/env bash
set -euo pipefail

version="${XSTAR_TOOLS_CFITSIO_VERSION:-4.6.2}"
prefix="${XSTAR_TOOLS_CFITSIO_PREFIX:-/opt/xstar-cfitsio}"
jobs="${XSTAR_TOOLS_CFITSIO_JOBS:-2}"
url="https://heasarc.gsfc.nasa.gov/FTP/software/fitsio/c/cfitsio-${version}.tar.gz"

case "${version}" in
  4.6.2)
    sha256="66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb"
    ;;
  *)
    echo "unsupported CFITSIO version ${version}; add a pinned SHA-256 first" >&2
    exit 2
    ;;
esac

work="$(mktemp -d /tmp/xstar-cfitsio.XXXXXX)"
trap 'rm -rf "${work}"' EXIT
archive="${work}/cfitsio-${version}.tar.gz"

python - "${url}" "${archive}" "${sha256}" <<'PY'
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
import urllib.request

url, output, expected = sys.argv[1:]
with urllib.request.urlopen(url) as response:
    data = response.read()
actual = hashlib.sha256(data).hexdigest()
if actual != expected:
    raise SystemExit(f"CFITSIO SHA-256 mismatch: expected {expected}, got {actual}")
Path(output).write_bytes(data)
print(f"XSTAR_TOOLS_CFITSIO_ARCHIVE_SHA256={actual}")
PY

tar -xzf "${archive}" -C "${work}"
cd "${work}/cfitsio-${version}"

# The manylinux image intentionally provides only the minimal development
# dependencies installed by cibuildwheel.  In particular, libcurl-devel is not
# installed, so CFITSIO does not acquire a large network-library dependency
# closure that would otherwise need to be vendored into the wheel.
./configure --prefix="${prefix}" --enable-reentrant
make -j"${jobs}"
make install

pc=""
for candidate in "${prefix}/lib/pkgconfig/cfitsio.pc" "${prefix}/lib64/pkgconfig/cfitsio.pc"; do
  if [[ -f "${candidate}" ]]; then
    pc="${candidate}"
    break
  fi
done
if [[ -z "${pc}" ]]; then
  echo "CFITSIO installation did not produce cfitsio.pc under ${prefix}" >&2
  exit 3
fi

echo "XSTAR_TOOLS_CFITSIO_VERSION=${version}"
echo "XSTAR_TOOLS_CFITSIO_PREFIX=${prefix}"
echo "XSTAR_TOOLS_CFITSIO_PKGCONFIG=${pc}"
