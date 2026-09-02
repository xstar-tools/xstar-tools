# 0.6.88.5.6 — WINDOWS_EMBEDDED_PYTHON_DLL_SEARCH_CLOSURE

## Purpose

Close the embedded-Python runtime failure exposed after the real `0.6.88.5.5` MSYS2/UCRT64 build, PE/export/discovery/process, and XSTAR2XSPEC process-pool gates all accepted. The remaining failure occurred only when the embedded backend imported `_ctypes`; the standalone MSYS2 Python installation itself is not changed by this release.

## Root cause and boundary

The Windows backend initializes CPython inside `libxstar_backend_python.dll`. On the supported MSYS2/UCRT64 layout, Python extension dependencies such as `libffi` live beside the Python runtime under `<python-prefix>/bin`. The embedded interpreter did not register that directory for extension-module dependency resolution before importing `xstar_tools`, so importing `ctypes` through the package initialization path failed at `_ctypes`.

The fix belongs to the embedder. On `_WIN32`, after `Py_Initialize()` and after acquiring the GIL but before modifying `sys.path` or importing `xstar_tools`, `xstar_backend_python.cpp`:

1. obtains the initialized Python prefix with `Py_GetPrefix()`;
2. selects `<prefix>/bin`, falling back to `<prefix>` when that directory is absent;
3. calls Python's Windows `os.add_dll_directory()` for that directory;
4. stores the returned handle on the `sys` module so the directory remains registered for the interpreter lifetime;
5. treats registration failure as a backend-load failure with the existing Python error-text path.

Registration is idempotent through a private `sys._xstar_windows_dll_directory_handle` attribute. The entire helper and call site are `_WIN32`-guarded, so Linux/macOS runtime behavior is unchanged.

## Production scope

The only functional production-source change relative to `.5.5` is `xstar_backend_python.cpp`. `Makefile`, `xstar_xspec_parallel.cpp`, and `xstar_xspec_mpi.cpp` change only package-version metadata. The `.5.5` standard-header closure, `.5.3` local-zone/path fixes, Win32 process layer, XSTAR2XSPEC scheduler, scientific arithmetic/order, publication behavior, and public ABI values remain unchanged.

No workflow dependency is added to mask the problem; in particular the workflow does not explicitly add a new `libffi` package beyond the existing Python package dependency graph.

## Windows host acceptance

The host runner retains all `.5.5` native build/PE/export/discovery/process/XSTAR2XSPEC gates and adds explicit regression attribution:

```text
PYTHON_RUNTIME_CTYPES_IMPORT
FIXED_STATE_SELF_TEST
FIXED_STATE_BATCH_SELF_TEST
FIXED_STATE_OUTPUT
PYTHON_BACKEND_SELF_TEST
PYTHON_BRIDGE_TEST
WINDOWS_REGRESSION
```

`PYTHON_RUNTIME_CTYPES_IMPORT` is an external-Python control. The three fixed-state gates prove the C++ fixed-state scaffold independently of the embedded backend. The two Python gates test the embedded backend directly before the unchanged full `make test` regression.

Windows MPI remains out of scope.
