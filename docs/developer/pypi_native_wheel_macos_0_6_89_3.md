# 0.6.89.3 — PYPI_NATIVE_WHEEL_MACOS

`0.6.89.3` is the macOS PyPI release-wheel milestone after the formally accepted
`0.6.89.2.2` Linux manylinux closure. It is packaging/licensing work only; the
frozen XSTAR science revision and public ABIs are unchanged.

## Architecture policy

Release wheels are architecture-specific, not `universal2`:

```text
Apple Silicon:  macosx_11_0_arm64
Intel:          macosx_11_0_x86_64
```

The GitHub Actions matrix builds CPython 3.9 through 3.14 on native runners:
`macos-15` for arm64 and `macos-15-intel` for x86_64. This avoids the historical
host-wheel problem where single-architecture payloads were labeled
`universal2`.

`MACOSX_DEPLOYMENT_TARGET=11.0` is applied to XSTAR and CFITSIO builds so both
architectures have one explicit minimum supported macOS release.

## Native wheel profile

The wheel build sets:

```text
XSTAR_TOOLS_NATIVE=required
XSTAR_TOOLS_NATIVE_PROFILE=pypi-macos
```

`pypi-macos` omits only `libxstar_backend_python.dylib`, the optional standalone
Python-embedding plugin. This prevents a Python-framework/libpython dependency
from entering the distributable wheel. The ordinary `full` profile and
`make all` remain unchanged and continue to build the plugin for direct source
builds.

The wheel retains the public C API, production-zone and modular C++ runtime,
`libxstar_backend_cpp.dylib`, `xstar_cpp`, `xstar-cpp`, `xstar-xspec-initable`,
`xstar-xspec-table`, and `xstar-xspec`. MPI remains opt-in and is not part of an
ordinary PyPI wheel.

## CFITSIO and delocate

CFITSIO 4.6.2 is built from the HEASARC source archive using the pinned SHA-256:

```text
66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb
```

It is installed into `/tmp/xstar-cfitsio` during cibuildwheel production.
`delocate-wheel --require-archs` then copies non-system dylib dependencies into
the wheel and rewrites Mach-O load paths. `REPAIR_LIBRARY_PATH` is used to
carry the CFITSIO prefix across the macOS SIP boundary during repair.

`atdb.fits` remains external scientific data and is never bundled.

## License policy from 0.6.89.3 onward

The project license designation is `GPL-3.0`. `pyproject.toml` declares:

```toml
license = "GPL-3.0"
license-files = ["LICENSE"]
```

`LICENSE` contains the supplied GNU General Public License, Version 3,
29 June 2007. Historical release notes describing the prior MIT declaration are
retained as history; current package metadata and generated wheel/sdist metadata
must report `GPL-3.0`.

## Clean-wheel qualification

Each repaired wheel is installed in cibuildwheel's test environment and must
pass:

- `pip check`;
- `xstar-cpp --version` / `--abi` and `xstar-xspec --version`;
- `xstar-tools doctor --require zone-cpp --json`;
- direct `ctypes` C API ABI `60487` validation;
- `lipo -archs` showing exactly one architecture matching the runner;
- no leaked `/tmp/xstar-cfitsio`, Homebrew Cellar, `libpython`, or
  `Python.framework` dependency in XSTAR Mach-O payloads;
- vendored CFITSIO under a delocate `.dylibs` directory;
- a pinned offline `bremem` science leaf;
- no bundled `atdb.fits`;
- installed `License-Expression: GPL-3.0` and GNU GPL v3 license text.

The post-build wheel checker independently requires the correct CPython and
`macosx_11_0_arm64` / `macosx_11_0_x86_64` tags, rejects `universal2`, checks
native metadata/artifacts, vendored CFITSIO, MPI exclusion, external atomic
data, and license metadata.

## GitHub Actions

Run:

```text
.github/workflows/pypi-native-wheel-macos.yml
```

A successful matrix selector ends with:

```text
PYPI_NATIVE_WHEEL_MACOS_06893_SMOKE_RESULT=ACCEPT
PYPI_NATIVE_WHEEL_MACOS_06893_ARTIFACT_RESULT=ACCEPT
PYPI_NATIVE_WHEEL_MACOS_06893_GITHUB_JOB_RESULT=ACCEPT
```

Source-only qualification is available without a macOS wheel build:

```bash
python tools/qualification/run_pypi_native_wheel_macos_host_0_6_89_3.py \
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
