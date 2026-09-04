# 0.6.89.4.4 — WINDOWS_PYPI_PKG_CONFIG_QUALIFICATION_LAUNCHER_CLOSURE

`0.6.89.4.4` is a qualification-only closure on `0.6.89.4.3`.

The six `.89.4.3` Windows jobs did not reach cibuildwheel. Source qualification created a temporary POSIX shell script to act as fake `pkg-config` and passed that script directly to native Windows `subprocess.run`. Windows `CreateProcess` cannot execute a shebang script directly and returned `WinError 193`.

The production implementation from `.89.4.3` is retained byte-for-byte. The checker now patches only the `subprocess.run` boundary used by `_pkg_config_cfitsio_make_variables()` and verifies the exact calls:

```text
pkg-config --cflags cfitsio
pkg-config --variable=libdir cfitsio
pkg-config --libs cfitsio
```

It also retains the expected normalization from Windows backslashes to forward slashes before the metadata is passed into GNU Make.

Unchanged contracts:

- CFITSIO 4.6.2 shared-DLL prebuild and SHA-256;
- `pypi-windows` native profile and `win_amd64` wheel target;
- CPython 3.9 through 3.14 selectors;
- science revision `0.6.48.12.3.45.3.3.8`;
- C API ABI `60487` and production-zone ABI `6048110`;
- ordinary-wheel MPI exclusion;
- external `atdb.fits`;
- GPL-3.0.

Formal acceptance requires all six Windows selectors to pass source qualification, native build, delvewheel repair, clean-install smoke, and artifact qualification.
