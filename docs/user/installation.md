# Installation

## pip installation

`pyproject.toml` is the authoritative package metadata/build configuration. The
small `setup.py` file exists only to register the native setuptools build hook;
`setup.cfg` is no longer part of the active build configuration.

Install a released wheel in the normal way:

```bash
python -m pip install xstar-tools
```

For a source archive or checkout:

```bash
python -m pip install .
```

On **Linux**, the default build policy compiles the qualified native runtime and
bundles the shared libraries plus the native `xstar-cpp` executable in the
wheel. Native builds require:

- a C++17 compiler;
- `make`;
- `python3-config`;
- CFITSIO development headers/libraries with `pkg-config` metadata.

For Debian/Ubuntu systems, the system dependency is normally provided by
`libcfitsio-dev`.

The build deliberately retains the qualified Makefile/compiler defaults rather
than migrating the scientific code to a new build system in this milestone.

### Python-only installation

A Python-only build is explicit:

```bash
XSTAR_TOOLS_NATIVE=off python -m pip install .
```

This produces a pure Python wheel. `pure-python` remains available; C++ modes
and the `xstar-cpp` command report that the native runtime is unavailable.

### Require native compilation

Release/native builders can make native support mandatory:

```bash
XSTAR_TOOLS_NATIVE=required python -m pip install .
```

A missing compiler, CFITSIO development package, or other native prerequisite
then fails the build instead of silently falling back.

`XSTAR_TOOLS_NATIVE_JOBS=N` controls the Make parallelism used by the wheel
build. The default is `2`.

## Platform support in 0.6.72

| Platform | Wheel/runtime policy |
|---|---|
| Linux x86_64 | Native wheel target; release CI enforces the build/install contract |
| Linux aarch64 | Native build contract and CI target |
| macOS arm64/x86_64 | Python-only wheel for this milestone |
| Windows | Python-only wheel for this milestone |

The native Makefile still has Linux-specific linker assumptions (`-ldl`, ELF
RPATH, `.so` naming). macOS/Windows native support should be added as a
separate portability qualification rather than hidden behind an untested build
translation.

## Editable development checkout

```bash
python -m pip install -e '.[dev]'
```

For documentation:

```bash
python -m pip install -e '.[docs]'
```

## Verify the installed package

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

On a native Linux installation:

```bash
xstar-cpp --abi
xstar-tools doctor --require zone-cpp
```

`xstar-tools backends` includes native-build metadata when the runtime came from
a wheel build.


## Conda / conda-forge

Milestone 9 adds a conda-forge-ready recipe under `conda/recipe/`. Until the
feedstock is accepted and published, build it locally from the source checkout
with conda-build; after publication the normal user command will be:

```bash
conda install -c conda-forge xstar-tools
```

The conda package follows the same capability policy as pip packaging: Linux
builds carry the qualified native runtime, while macOS and Windows remain
explicit Python-only builds for this milestone. `atdb.fits` remains external.
See the [conda packaging guide](../developer/conda_packaging.md).

## Atomic data is separate

`atdb.fits` is intentionally **not bundled** in wheels or sdists. Normal runs do
not download it as a side effect. See [Atomic-data setup](atomic_data.md).
