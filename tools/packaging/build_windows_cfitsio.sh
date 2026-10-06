#!/usr/bin/env bash
set -euo pipefail

version="${XSTAR_TOOLS_CFITSIO_VERSION:-4.6.2}"
prefix="${XSTAR_TOOLS_CFITSIO_PREFIX:-${PWD}/.xstar-cfitsio}"
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

work="$(mktemp -d "${TMPDIR:-/tmp}/xstar-cfitsio-windows.XXXXXX")"
trap 'rm -rf "${work}"' EXIT
archive="${work}/cfitsio-${version}.tar.gz"

curl --fail --location --silent --show-error "${url}" --output "${archive}"
actual="$(sha256sum "${archive}" | awk '{print $1}')"
if [[ "${actual}" != "${sha256}" ]]; then
  echo "CFITSIO SHA-256 mismatch: expected ${sha256}, got ${actual}" >&2
  exit 3
fi
printf 'XSTAR_TOOLS_CFITSIO_ARCHIVE_SHA256=%s\n' "${actual}"

tar -xzf "${archive}" -C "${work}"
cd "${work}/cfitsio-${version}"

# Build the same pinned CFITSIO release used by the accepted Linux/macOS wheel
# tracks, but with the accepted Windows UCRT64 MinGW-w64 compiler.  The prefix
# is kept under the GitHub workspace so native Windows Python/cibuildwheel can
# access the resulting pkg-config metadata and DLLs through ordinary Win32
# paths after this MSYS2 step completes.
CC=gcc CXX=g++ ./configure \
  --prefix="${prefix}" \
  --enable-reentrant \
  --enable-shared \
  --disable-static

# Build only the CFITSIO library.  The default Automake `all` target also
# builds helper utilities, including `smem`; that Unix shared-memory utility
# includes sys/ipc.h and is not portable to the accepted UCRT64/MinGW-w64
# Windows toolchain.  XSTAR wheels need only the library, public headers, and
# pkg-config metadata.
# Native PE/COFF shared libraries require the libtool `-no-undefined`
# declaration.  Without it libtool refuses to emit a DLL on MinGW even when
# all required libraries are present and silently falls back to static-only.
# CFITSIO 4.6.2 uses libtool version-info 10; preserve that upstream ABI value
# while adding only the Windows DLL-clean declaration.
make -j"${jobs}" \
  libcfitsio_la_LDFLAGS="-version-info 10 -no-undefined" \
  libcfitsio.la

# Install only the artifacts required by the xstar-tools native build.  Avoid
# top-level `make install`, whose install-am prerequisite first rebuilds the
# complete `all-am` graph (including the unsupported smem helper).
make install-libLTLIBRARIES install-includeHEADERS install-pkgconfigDATA

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

mapfile -t dlls < <(find "${prefix}" -type f -iname '*cfitsio*.dll' -print)
if [[ "${#dlls[@]}" -eq 0 ]]; then
  echo "CFITSIO installation did not produce a Windows DLL under ${prefix}" >&2
  exit 5
fi

printf 'XSTAR_TOOLS_CFITSIO_VERSION=%s\n' "${version}"
printf 'XSTAR_TOOLS_CFITSIO_PREFIX=%s\n' "${prefix}"
printf 'XSTAR_TOOLS_CFITSIO_PKGCONFIG=%s\n' "${pc}"
printf 'XSTAR_TOOLS_CFITSIO_DLL=%s\n' "${dlls[0]}"
