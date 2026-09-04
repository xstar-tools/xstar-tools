# 0.6.89.4.2 — WINDOWS_PYPI_CFITSIO_SHARED_DLL_LINK_CLOSURE

`0.6.89.4.2` is a narrow Windows PyPI-wheel dependency-link closure on top of `0.6.89.4.1`.

## Predecessor result

`0.6.89.4.1` fixed the earlier Unix-only CFITSIO `smem` build failure: all six UCRT64 jobs reached the CFITSIO library link without compiling `utilities/smem`. The next failure was common to CPython 3.9–3.14: GNU libtool refused to emit a native Windows shared library because the CFITSIO libtool link did not declare `-no-undefined`. Libtool therefore built and installed only `libcfitsio.a`; the packaging script correctly rejected the missing CFITSIO DLL before xstar-tools wheel construction.

## Closure

The pinned dependency remains CFITSIO 4.6.2 with SHA-256:

```
66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb
```

The Windows dependency build now configures shared-only output:

```bash
./configure --enable-reentrant --enable-shared --disable-static
```

and builds only the library using CFITSIO's retained libtool ABI version plus the native-Windows DLL-clean declaration:

```bash
make -j"${jobs}" \
  libcfitsio_la_LDFLAGS="-version-info 10 -no-undefined" \
  libcfitsio.la
```

Installation remains leaf-only:

```bash
make install-libLTLIBRARIES install-includeHEADERS install-pkgconfigDATA
```

No CFITSIO helper utility is requested, and a Windows `*cfitsio*.dll` remains mandatory before the wheel build proceeds.

## Frozen publication contract

This closure does not alter the XSTAR Windows publication runtime. `build_support.py` and `src/xstar_tools/native_runtime.py` are byte-identical to `0.6.89.4.1`. The wheel target remains `pypi-windows`; ordinary wheels contain the 18 public DLL/EXE artifacts, exclude `libxstar_backend_python.dll` and MPI, leave `atdb.fits` external, and are repaired with delvewheel into normal CPython `win_amd64` wheels.

The frozen science revision is `0.6.48.12.3.45.3.3.8`; C API ABI is `60487`; production-zone ABI is `6048110`; fixed-state ABI is `60486`; XSPEC-table ABI is `1`; current license designation is `GPL-3.0`.

## Acceptance gate

The six selectors are:

```
cp39-win_amd64
cp310-win_amd64
cp311-win_amd64
cp312-win_amd64
cp313-win_amd64
cp314-win_amd64
```

Each must finish with:

```
WINDOWS_PYPI_CFITSIO_SHARED_DLL_LINK_CLOSURE_068942_SMOKE_RESULT=ACCEPT
WINDOWS_PYPI_CFITSIO_SHARED_DLL_LINK_CLOSURE_068942_ARTIFACT_RESULT=ACCEPT
WINDOWS_PYPI_CFITSIO_SHARED_DLL_LINK_CLOSURE_068942_GITHUB_JOB_RESULT=ACCEPT
```

Until all six real Windows jobs pass, `0.6.89.4.2` is a candidate rather than a formally accepted release-wheel milestone.
