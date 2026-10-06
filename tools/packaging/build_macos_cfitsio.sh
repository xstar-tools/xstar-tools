#!/usr/bin/env bash
set -euo pipefail

version="${XSTAR_TOOLS_CFITSIO_VERSION:-4.6.2}"
prefix="${XSTAR_TOOLS_CFITSIO_PREFIX:-/tmp/xstar-cfitsio}"
jobs="${XSTAR_TOOLS_CFITSIO_JOBS:-2}"
deployment_target="${MACOSX_DEPLOYMENT_TARGET:-11.0}"
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

curl --fail --location --silent --show-error "${url}" --output "${archive}"
actual="$(shasum -a 256 "${archive}" | awk '{print $1}')"
if [[ "${actual}" != "${sha256}" ]]; then
  echo "CFITSIO SHA-256 mismatch: expected ${sha256}, got ${actual}" >&2
  exit 3
fi
printf 'XSTAR_TOOLS_CFITSIO_ARCHIVE_SHA256=%s\n' "${actual}"

tar -xzf "${archive}" -C "${work}"
cd "${work}/cfitsio-${version}"

# Build the same pinned CFITSIO release for both native macOS architectures.
# The deployment target is exported before configure so every copied dylib is
# eligible for the same wheel tag.  Avoid Homebrew here: delocate should repair
# against one reproducible prefix rather than a runner-specific Cellar path.
export MACOSX_DEPLOYMENT_TARGET="${deployment_target}"
CC=clang CXX=clang++ ./configure --prefix="${prefix}" --enable-reentrant
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
  exit 4
fi

printf 'XSTAR_TOOLS_CFITSIO_VERSION=%s\n' "${version}"
printf 'XSTAR_TOOLS_CFITSIO_PREFIX=%s\n' "${prefix}"
printf 'XSTAR_TOOLS_CFITSIO_PKGCONFIG=%s\n' "${pc}"
printf 'XSTAR_TOOLS_MACOSX_DEPLOYMENT_TARGET=%s\n' "${deployment_target}"
