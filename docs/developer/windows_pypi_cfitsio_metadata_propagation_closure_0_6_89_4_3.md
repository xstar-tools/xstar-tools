# 0.6.89.4.3 — WINDOWS_PYPI_CFITSIO_METADATA_PROPAGATION_CLOSURE

## Scope

`0.6.89.4.2` successfully built and exposed the pinned CFITSIO 4.6.2 Windows DLL, then all six `cp39`–`cp314` `win_amd64` jobs reached the native XSTAR build. They failed at the first CFITSIO-using XSTAR target:

```text
xstar_xspec_table.cpp:24:10: fatal error: fitsio.h: No such file or directory
```

The emitted link line contained only `-lcfitsio`, showing that Make's internal `pkg-config` shell re-discovery had fallen back and lost the include/library prefix.

## Closure

The Python build backend already validates that `pkg-config --exists cfitsio` succeeds. For the `pypi-windows` profile only, it now resolves:

```text
pkg-config --cflags cfitsio
pkg-config --variable=libdir cfitsio
pkg-config --libs cfitsio
```

and passes the resulting values explicitly to Make as:

```text
CFITSIO_CFLAGS=...
CFITSIO_LIBDIR=...
CFITSIO_LIBS=...
```

Windows backslashes returned by `pkg-config` are normalized to forward slashes before the Make boundary. This removes the fragile second discovery through `$(shell ...)` while preserving the accepted Makefile fallback behavior for non-PyPI/native builds.

## Frozen behavior

No science code, ABI, numerical policy, atomic-data policy, MPI policy, or CFITSIO source/build recipe is changed. Linux and macOS PyPI profiles retain their existing paths. `atdb.fits` remains external and ordinary wheels remain MPI-free.

## Acceptance

The candidate is source/local qualified only until all six Windows selectors (`cp39` through `cp314`) build, repair, clean-install smoke, and pass the wheel artifact checker on GitHub Actions.
