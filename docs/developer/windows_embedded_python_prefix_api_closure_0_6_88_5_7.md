# 0.6.88.5.7 — WINDOWS_EMBEDDED_PYTHON_PREFIX_API_CLOSURE

## Purpose

Close the only remaining rejection from the real `0.6.88.5.6` MSYS2/UCRT64 run. `.5.6` successfully fixed embedded `_ctypes` loading and all runtime/regression gates accepted, but Python 3.14.7 emitted a deprecation warning for `Py_GetPrefix()`, causing the strict warning-free gate to reject the host run.

## Root cause and boundary

The `.5.6` DLL-search helper obtained the initialized Python prefix through `Py_GetPrefix()`. The runtime semantics were correct, but that legacy interpreter-configuration API is deprecated on the tested Python 3.14 toolchain.

`.5.7` keeps the embedder-owned DLL-search algorithm unchanged and replaces only that prefix lookup. Inside the existing `_WIN32` helper it:

1. reads `sys.base_prefix` from the already-imported `sys` module;
2. verifies it is a Python Unicode object;
3. converts it to an owned wide-character buffer with `PyUnicode_AsWideCharString()`;
4. constructs the existing `std::filesystem::path` from that buffer;
5. frees the Python-owned allocation with `PyMem_Free()`;
6. continues the unchanged `.5.6` `<prefix>/bin` selection, prefix fallback, `os.add_dll_directory()` call, and retained-handle lifetime.

`Py_GetPrefix()` is absent from the production backend. No warning suppression is added.

## Production scope

The only functional production-source change relative to `.5.6` is `xstar_backend_python.cpp`. `Makefile`, `xstar_xspec_parallel.cpp`, and `xstar_xspec_mpi.cpp` change only package-version metadata.

The `.5.6` DLL-search mechanism, `.5.5` XSTAR2XSPEC standard-header fix, `.5.3` Windows local-zone/path fixes, Win32 process layer, scheduler, fixed-state implementation, science arithmetic/order, output formats, and ABI values remain unchanged.

## Windows host acceptance

The `.5.7` host runner preserves all `.5.6` evidence, including:

```text
WARNING_FREE_BUILD
PYTHON_RUNTIME_CTYPES_IMPORT
FIXED_STATE_SELF_TEST
FIXED_STATE_BATCH_SELF_TEST
FIXED_STATE_OUTPUT
PYTHON_BACKEND_SELF_TEST
PYTHON_BRIDGE_TEST
WINDOWS_REGRESSION
XSPEC_PROCESS_POOL
```

Formal acceptance requires all of them to ACCEPT on the real MSYS2/UCRT64 host. Windows MPI remains out of scope.
