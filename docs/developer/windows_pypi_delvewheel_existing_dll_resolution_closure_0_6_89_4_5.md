# 0.6.89.4.5 — WINDOWS_PYPI_DELVEWHEEL_EXISTING_DLL_RESOLUTION_CLOSURE

`0.6.89.4.5` is the formally accepted Windows PyPI wheel-repair closure on `0.6.89.4.4`.

## Predecessor result

`0.6.89.4.4` reached the repaired-wheel boundary for the first time. CFITSIO built successfully, XSTAR native compilation succeeded, and the unrepaired `win_amd64` wheel contained the expected XSTAR DLL/executable payload. `delvewheel` then failed while analyzing `libxstar_backend_cpp.dll`:

```text
FileNotFoundError: Unable to find library: libxstar_api.dll
```

`libxstar_api.dll` was already present in the same wheel under `xstar_tools/xstar/cpp/`.

## Root cause

The `.89.4.4` repair command enabled `--analyze-existing` but not `--ignore-existing`.

In delvewheel 1.13.1, the case-insensitive map used to resolve DLLs already inside the extracted wheel is populated when `ignore_existing` is enabled. Without that map, dependency analysis falls through to external DLL search paths. The configured external paths contain CFITSIO and UCRT64 runtime DLLs, not the wheel's own `libxstar_*.dll` payload.

## Closure

The Windows repair command is now:

```text
delvewheel repair --ignore-existing --analyze-existing --analyze-existing-exes --add-path %XSTAR_TOOLS_WINDOWS_DLL_PATH% -w {dest_dir} -v {wheel}
```

The combination is intentional:

- `--ignore-existing` makes DLLs already in the wheel resolvable and keeps those XSTAR DLLs in place instead of re-vendoring/name-mangling them;
- `--analyze-existing` still analyzes the packaged XSTAR DLLs so their external dependencies are discovered;
- `--analyze-existing-exes` retains dependency analysis of the packaged native executables;
- `--add-path` continues to expose the pinned CFITSIO DLL directory and MSYS2 UCRT64 runtime directory so external dependencies can be copied into the delvewheel vendor directory.

No XSTAR C++ implementation, CFITSIO build script, native-runtime loader, science kernel, numerical ordering, or ABI changes in this closure.

## Formal host acceptance

All six Windows selectors are formally accepted:

```text
cp39-win_amd64   ACCEPT
cp310-win_amd64  ACCEPT
cp311-win_amd64  ACCEPT
cp312-win_amd64  ACCEPT
cp313-win_amd64  ACCEPT
cp314-win_amd64  ACCEPT
```

Each selector passed repaired-wheel artifact inspection and `twine check` and reached `WINDOWS_PYPI_DELVEWHEEL_EXISTING_DLL_RESOLUTION_CLOSURE_068945_GITHUB_JOB_RESULT=ACCEPT`. The accepted wheels use standard `win_amd64` tags, vendor CFITSIO plus the required MinGW runtime DLLs, keep canonical XSTAR DLLs in-package rather than duplicating them into the delvewheel vendor directory, exclude the Python-embedding plugin and MPI executable, and keep `atdb.fits` external.

This formally closes the Windows PyPI native-wheel line for CPython 3.9–3.14 AMD64 without changing science or public ABIs.
