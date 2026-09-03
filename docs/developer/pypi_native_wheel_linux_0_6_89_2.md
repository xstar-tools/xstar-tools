# 0.6.89.2 — PYPI_NATIVE_WHEEL_LINUX

`0.6.89.2` is the first publishable-wheel closure after the accepted
`0.6.89.1.3` pip-packaging-refresh series.  It does not change XSTAR science, public ABIs, MPI policy, or atomic-data policy. It adds one PyPI-specific binary staging profile while leaving the normal source/native profile intact.

## Linux wheel policy

Linux release wheels are built with `cibuildwheel` in the
`manylinux_2_28_x86_64` image rather than being built directly on the GitHub
Ubuntu host.  The supported CPython wheel set is:

```text
cp39
cp310
cp311
cp312
cp313
cp314
```

Free-threaded CPython builds are intentionally excluded from this first native
release-wheel milestone.

The wheel build sets `XSTAR_TOOLS_NATIVE=required` and `XSTAR_TOOLS_NATIVE_PROFILE=pypi-linux`, so failure to build the native runtime is fatal rather than silently degrading to a Python-only wheel. The retained Makefile `all` target is still the only ordinary-wheel native build target; `xstar-xspec-mpi` remains excluded.

The `pypi-linux` profile omits only `libxstar_backend_python.so`. That optional plugin embeds CPython and links `libpythonX.Y`, which is not a portable manylinux dependency. The default `full` native profile remains unchanged for source/native installs. The PyPI wheel still includes the public C API, production-zone and modular C++ libraries, `xstar-cpp`, and all non-MPI XSTAR2XSPEC executables.

## CFITSIO

The manylinux build bootstraps CFITSIO 4.6.2 from the official HEASARC source
archive with pinned SHA-256:

```text
66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb
```

It installs into `/opt/xstar-cfitsio` inside the build container.  The build
image deliberately does not install `libcurl-devel`, avoiding an unnecessary
network-library dependency closure.  `auditwheel repair` then vendors the
CFITSIO runtime into the wheel and rewrites loader paths as required by the
manylinux policy.

This vendoring is a binary runtime dependency action only.  `atdb.fits` remains
external scientific data and is not bundled.

## Clean-wheel qualification

Each repaired wheel is installed by cibuildwheel into a clean test environment.
The installed-wheel smoke requires:

- `pip check`;
- `xstar-cpp --version` and `xstar-cpp --abi`;
- `xstar-xspec --version`;
- `xstar-tools doctor --require zone-cpp --json`;
- direct `ctypes` loading of `libxstar_api.so` and C API ABI `60487`;
- `ldd` closure for every packaged XSTAR ELF library/executable;
- CFITSIO resolving from the installed wheel, not `/usr/lib` or `/lib`;
- a pinned offline `bremem` science leaf calculation;
- absence of `atdb.fits`.

The post-build artifact checker additionally requires a
`manylinux_2_28_x86_64` filename/WHEEL tag, the complete native runtime payload,
vendored CFITSIO under `xstar_tools.libs`, ordinary-wheel MPI exclusion, and
external `atdb.fits` policy.

## GitHub Actions

Run `.github/workflows/pypi-native-wheel-linux.yml`.  It builds the six CPython
wheels as separate jobs so the large native compilation can run in parallel.
Each successful job uploads one repaired wheel named by its cibuildwheel
selector.

For a focused local/Docker qualification where `cibuildwheel` is installed:

```bash
python tools/qualification/run_pypi_native_wheel_linux_host_0_6_89_2.py \
  --package "$PWD" \
  --selector cp313-manylinux_x86_64 \
  --output-root "$PWD/run_pypi_native_wheel_linux_06892_host"
```

Source-only qualification does not require Docker:

```bash
python tools/qualification/run_pypi_native_wheel_linux_host_0_6_89_2.py \
  --package "$PWD" \
  --source-only
```

## Frozen boundaries

```text
scientific oracle      FORTRAN XSTAR 2.59g
science revision       0.6.48.12.3.45.3.3.8
public C API ABI        60487
production-zone ABI    6048110
fixed-state ABI         60486
XSPEC table ABI         1
```
