# Packaging and native-wheel policy

## Authoritative configuration

`pyproject.toml` is authoritative for project metadata, dependencies, entry
points, package discovery, and installed static package data.

`setup.py` is deliberately thin. It registers only `XStarBuildPy` and
`XStarDistribution` from `build_support.py`; it contains no duplicated project
metadata. `setup.cfg` was removed in 0.6.71.
Setuptools may synthesize a minimal `[egg_info]` `setup.cfg` inside an sdist; that generated tag file contains no authoritative project metadata or build policy.

## Why setuptools remains the build backend

A scikit-build-core/CMake migration would require translating a mature Makefile
that carries qualification-sensitive compiler flags, per-translation-unit
floating-point controls, RPATH behavior, CFITSIO linking, and the standalone
shared-production architecture. Milestone 8 therefore chooses the lower-risk
path: retain setuptools and formalize the existing Makefile build as an
isolated wheel-build step.

A future CMake migration should be treated as its own science-neutral build
refactor with exact native product qualification.

## Native wheel construction

The build hook:

1. builds normal Python modules/package data;
2. evaluates `XSTAR_TOOLS_NATIVE`;
3. validates platform-native build prerequisites;
4. copies the self-contained `src/xstar_tools/xstar/cpp/` tree to a temporary staging directory;
5. runs `make clean` and then the retained `make all` there;
6. verifies every required runtime artifact exists;
7. copies only runtime binaries/libraries to the wheel build tree;
8. writes `native_build.json` with package/science/ABI/build provenance.

This design prevents old `.o`/`.so` files in a checkout from entering a wheel.

### PyPI Linux release profile (`0.6.89.2`, closures through `0.6.89.2.2`)

The `0.6.89.2.1` workflow first installs the declared PEP 517 build-backend requirements (`setuptools>=77` and `wheel`) into the qualification interpreter before importing `build_support.py`. `0.6.89.2.2` additionally maps the `pypi-linux` packaging profile to a dedicated `make pypi-linux` target so the standalone Python-embedding plugin is never built in the release-wheel path; ordinary `make all` remains unchanged. Public Linux release wheels are produced with cibuildwheel in a `manylinux_2_28_x86_64` container and repaired with auditwheel. CFITSIO 4.6.2 is built from a pinned official source archive inside the container and its runtime library is vendored into the repaired wheel.

`XSTAR_TOOLS_NATIVE_PROFILE=pypi-linux` changes only the staged binary payload: it omits `libxstar_backend_python.so`, whose standalone embedding contract links `libpythonX.Y` and therefore is not a valid portable manylinux dependency. The default `full` profile used by ordinary source/native installations is unchanged. The PyPI profile still contains the public C API, production-zone library, modular C++ libraries, `xstar-cpp`, and all non-MPI XSTAR2XSPEC executables.

The clean installed-wheel test exercises `zone-cpp`, so omission of the embedding plugin does not weaken the Python-to-native production path.


### Cross-platform PyPI release closure (`0.6.89.5`)

`0.6.89.5 — PYPI_CROSS_PLATFORM_RELEASE_CLOSURE` does not introduce a new science or native-runtime implementation. It advances package/version metadata and rebuilds the already-qualified `pypi-linux`, `pypi-macos`, and `pypi-windows` profiles under one version. The release workflow uses GitHub-hosted runners and produces exactly 24 native wheels plus one sdist:

- 6 CPython 3.9–3.14 `manylinux_2_28_x86_64` wheels;
- 6 CPython 3.9–3.14 `macosx_11_0_arm64` wheels;
- 6 CPython 3.9–3.14 `macosx_11_0_x86_64` wheels;
- 6 CPython 3.9–3.14 `win_amd64` wheels;
- 1 `xstar_tools-0.6.89.5.tar.gz` source distribution.

The aggregate gate rejects extra or missing distributions and specifically rejects a `py3-none-any` control wheel from the publication set. Each native wheel is clean-install tested by cibuildwheel on its platform before aggregation. The final aggregate job runs `twine check` and writes SHA-256 checksums. Publication itself remains a separate deliberate action so the same qualified bundle can be sent first to TestPyPI and then to PyPI.

No local Mac or Windows machine is required for release construction: macOS arm64/x86_64 and Windows AMD64 are built and tested on the corresponding GitHub-hosted runners.

## Wheel contents

Normal wheels include only installed Python modules plus required runtime data:

- compact benchmark/reference fixtures still consumed by current tests/runtime;
- `coheat.dat`;
- `constants.def`;
- public C/production-zone ABI headers;
- built native runtime artifacts on native wheels;
- `native_build.json`.

They exclude:

- top-level `historical/`;
- documentation source;
- tests and qualification reports;
- C++ implementation `.cpp` files and Makefile;
- object files, caches, and source-tree build products;
- `atdb.fits`.

The sdist retains source/build/qualification material required to reproduce and
validate a build, while still pruning the top-level historical archive.

## Data policy

`atdb.fits` is external scientific data. It is not bundled and is never fetched
silently during a run. Installed packages store configured data paths under the
user configuration directory (normally `~/.config/xstar-tools/datapath`) and
use a user data default (normally `~/.local/share/xstar-tools`) rather than
writing into site-packages.

## Release checks

Packaging CI must perform the equivalent of:

```bash
python -m build
python -m twine check dist/*
pip install dist/*.whl
xstar-tools doctor
```

Native Linux jobs additionally run:

```bash
xstar-cpp --abi
xstar-tools doctor --require zone-cpp
```

Clean-wheel characterization tests verify import/API/CLI behavior and wheel
payload policy without relying on the source checkout.

### Persistent release-build staging

For constrained release builders, `XSTAR_TOOLS_NATIVE_BUILD_DIR=/path` enables a
persistent staging directory. The hook fingerprints the complete native source
plus `pyproject.toml` and automatically discards the staging tree if that
fingerprint changes. This allows long qualified translation units to be built
incrementally without ever consuming unchecked object files from the source
checkout. Normal builds do not set this variable and use a temporary clean
stage.


## Conda packaging

The conda-forge recipe reuses this same build hook and native capability policy; see [Conda and conda-forge packaging](conda_packaging.md).

### Windows delvewheel in-wheel dependency resolution

For the `pypi-windows` profile, XSTAR DLLs are already packaged under `xstar_tools/xstar/cpp`. The repair command intentionally uses `--ignore-existing` together with `--analyze-existing --analyze-existing-exes`: the first enables resolution of DLLs already inside the wheel and keeps those XSTAR DLLs in place; the analysis flags still discover external CFITSIO and MinGW runtime dependencies for vendoring. The external search path remains `XSTAR_TOOLS_WINDOWS_DLL_PATH`.
