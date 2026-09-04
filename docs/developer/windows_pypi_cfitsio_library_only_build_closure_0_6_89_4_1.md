# 0.6.89.4.1 — WINDOWS_PYPI_CFITSIO_LIBRARY_ONLY_BUILD_CLOSURE

`0.6.89.4.1` is a narrow packaging closure on top of the Windows PyPI candidate `0.6.89.4`.

## Why 0.6.89.4 was rejected

All six Windows CPython selectors failed before xstar-tools native compilation. The pinned CFITSIO 4.6.2 source configured successfully under MSYS2 UCRT64, but `tools/packaging/build_windows_cfitsio.sh` invoked CFITSIO's default `make` target. That target builds both the library and helper programs. The helper `utilities/smem` includes `drvrsmem.h`, which requires Unix System V shared-memory headers including `sys/ipc.h`; those headers do not exist in MinGW-w64. The observed failure was therefore a CFITSIO helper-utility build boundary, not a regression in the accepted XSTAR Windows runtime.

## Closure

The Windows CFITSIO helper now performs:

```bash
CC=gcc CXX=g++ ./configure --prefix="${prefix}" --enable-reentrant
make -j"${jobs}" libcfitsio.la
make install-libLTLIBRARIES install-includeHEADERS install-pkgconfigDATA
```

It deliberately does **not** invoke either:

```bash
make -j"${jobs}"
make install
```

The first would build CFITSIO helper utilities such as `smem`; the second causes Automake `install-am` to depend on the complete `all-am` graph and can rebuild those helpers before installation.

The leaf install targets retain exactly what the XSTAR native build requires:

- the CFITSIO shared library and import library;
- the public CFITSIO headers;
- `cfitsio.pc` for pkg-config discovery.

The script still requires the installed CFITSIO DLL and pkg-config file before returning success.

## Retained release contract

This closure does not change the accepted Windows native implementation or publication contract:

- CPython 3.9–3.14, `win_amd64` only;
- MSYS2 UCRT64 / MinGW-w64 XSTAR native runtime;
- `XSTAR_TOOLS_NATIVE_PROFILE=pypi-windows`;
- `delvewheel` repair of packaged DLLs and EXEs;
- wheel-local CFITSIO and MinGW runtime DLLs;
- no `libxstar_backend_python.dll` in publication wheels;
- no MPI in ordinary wheels;
- `atdb.fits` remains external;
- GPL-3.0 license designation;
- science revision `0.6.48.12.3.45.3.3.8` unchanged;
- C API ABI `60487`, production-zone ABI `6048110`, fixed-state ABI `60486`, and XSPEC table ABI `1` unchanged.

`build_support.py` and `src/xstar_tools/native_runtime.py` are byte-identical to `0.6.89.4`.

## CI evidence improvements

The Windows workflow also installs MSYS2 `diffutils`, eliminating the predecessor's non-fatal missing `cmp` / `diff` configure warnings. The CFITSIO build is piped through `tee cfitsio-build.log` with `pipefail`, and that log is uploaded even when a selector fails before producing a wheel.

## Acceptance target

All six selectors must finish with:

```text
WINDOWS_PYPI_CFITSIO_LIBRARY_ONLY_BUILD_CLOSURE_068941_SMOKE_RESULT=ACCEPT
WINDOWS_PYPI_CFITSIO_LIBRARY_ONLY_BUILD_CLOSURE_068941_ARTIFACT_RESULT=ACCEPT
WINDOWS_PYPI_CFITSIO_LIBRARY_ONLY_BUILD_CLOSURE_068941_GITHUB_JOB_RESULT=ACCEPT
```

Only after the full six-selector matrix reaches those markers should `0.6.89.4.1` be promoted to formal acceptance.
