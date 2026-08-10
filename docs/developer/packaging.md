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
3. validates Linux build prerequisites;
4. copies the self-contained `src/xstar_tools/xstar/cpp/` tree to a temporary staging directory;
5. runs `make clean` and then the retained `make all` there;
6. verifies every required runtime artifact exists;
7. copies only runtime binaries/libraries to the wheel build tree;
8. writes `native_build.json` with package/science/ABI/build provenance.

This design prevents old `.o`/`.so` files in a checkout from entering a wheel.

## Wheel contents

Normal wheels include only installed Python modules plus required runtime data:

- compact benchmark/reference fixtures still consumed by current tests/runtime;
- `coheat.dat`;
- `constants.def`;
- public C/production-zone ABI headers;
- built native runtime artifacts on native Linux wheels;
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
