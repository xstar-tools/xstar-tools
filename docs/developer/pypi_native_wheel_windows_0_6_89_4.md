# 0.6.89.4 — PYPI_NATIVE_WHEEL_WINDOWS

`0.6.89.4` is the Windows PyPI release-wheel milestone after the formally
accepted Linux `0.6.89.2.2` and macOS `0.6.89.3` publication closures. It is
packaging/runtime-discovery work only; the frozen XSTAR science revision and
public ABIs remain unchanged.

## Wheel and toolchain policy

The published wheel tag is the ordinary CPython Windows tag:

```text
cp39-cp39-win_amd64
...
cp314-cp314-win_amd64
```

The wheel is built by official CPython/cibuildwheel on `windows-latest`, while
the bundled XSTAR native runtime remains the accepted MSYS2 UCRT64 / MinGW-w64
GCC implementation. This deliberately replaces the earlier MSYS2-Python-only
`mingw_x86_64_ucrt_gnu` development-wheel tag with a normal `win_amd64` release
wheel that ordinary Python.org CPython and pip can install.

Windows x86 and Windows ARM64 are not part of this milestone. The accepted
native Windows portability baseline is AMD64/UCRT64.

## Native wheel profile

The release build sets:

```text
XSTAR_TOOLS_NATIVE=required
XSTAR_TOOLS_NATIVE_PROFILE=pypi-windows
```

`pypi-windows` invokes `make pypi-windows` and omits only
`libxstar_backend_python.dll`, the optional standalone Python-embedding plugin.
The public C API, Python-to-C++ backend, production/science DLLs,
`xstar_cpp.exe`, `xstar-cpp.exe`, `xstar-xspec-initable.exe`,
`xstar-xspec-table.exe`, and `xstar-xspec.exe` remain present.

Because the embedding plugin is absent, official Python.org CPython does not
need an MSYS2 `python-config` helper during this packaging profile. The ordinary
`full` profile and `make all` retain the historical Python embedding plugin and
its Python-development prerequisite.

## CFITSIO and delvewheel

CFITSIO 4.6.2 is built from the same pinned HEASARC archive used by the accepted
Linux/macOS release-wheel tracks:

```text
66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb
```

It is compiled with the UCRT64 MinGW-w64 toolchain. `delvewheel` repairs the
wheel with both `--analyze-existing` and `--analyze-existing-exes`, because
XSTAR ships DLLs and executable programs rather than a conventional `.pyd`
extension module. The repair search path includes the pinned CFITSIO prefix and
the UCRT64 compiler runtime directory, allowing CFITSIO, `libstdc++`, `libgcc`,
and `libwinpthread` dependencies to be vendored.

The installed Python runtime also discovers delvewheel's `xstar_tools*.libs`
directory. `ctypes` DLL loads register that directory with
`os.add_dll_directory`, and native executable wrappers prepend it to child
`PATH` so packaged EXEs resolve the same repaired runtime closure.

`atdb.fits` remains external. MPI remains opt-in and unsupported on Windows.

## Clean-wheel qualification

Each repaired wheel is installed by cibuildwheel and must pass:

- `pip check`;
- `xstar-cpp --version` / `--abi` and `xstar-xspec --version`;
- `xstar-tools doctor --require zone-cpp --json`;
- direct C API ABI `60487` loading;
- wheel-local CFITSIO and MinGW runtime DLL discovery;
- no bundled Python runtime DLL;
- no `libxstar_backend_python.dll` or `xstar-xspec-mpi.exe`;
- a pinned offline `bremem` science leaf;
- no bundled `atdb.fits`;
- installed `License-Expression: GPL-3.0` and GNU GPL v3 license text.

The post-build artifact checker independently requires `win_amd64` CPython
tags, AMD64 PE machine type for all XSTAR DLL/EXE payloads, expected native
metadata/artifacts, delvewheel vendor payloads, GPL-3.0 metadata, MPI exclusion,
and the external atomic-data contract.

## GitHub Actions

Run:

```text
.github/workflows/pypi-native-wheel-windows.yml
```

The matrix contains CPython 3.9 through 3.14 on AMD64. A successful selector
ends with:

```text
PYPI_NATIVE_WHEEL_WINDOWS_06894_SMOKE_RESULT=ACCEPT
PYPI_NATIVE_WHEEL_WINDOWS_06894_ARTIFACT_RESULT=ACCEPT
PYPI_NATIVE_WHEEL_WINDOWS_06894_GITHUB_JOB_RESULT=ACCEPT
```

Source-only qualification is available on any host with GNU Make:

```bash
python tools/qualification/run_pypi_native_wheel_windows_host_0_6_89_4.py \
  --package "$PWD" \
  --source-only
```

## License and frozen boundaries

The `GPL-3.0` project license designation introduced in `0.6.89.3` remains in
force for this and later releases.

```text
scientific oracle      FORTRAN XSTAR 2.59g
science revision       0.6.48.12.3.45.3.3.8
public C API ABI        60487
production-zone ABI    6048110
fixed-state ABI         60486
XSPEC table ABI         1
```
