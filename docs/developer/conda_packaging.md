# Conda and conda-forge packaging

`0.6.90 — CONDA_PACKAGING_REFRESH` modernizes the historical conda packaging
layer without changing scientific arithmetic, controller behavior, public ABIs,
or the external atomic-data contract.

## Current format and source

The upstream seed is:

```text
conda/
  README.md
  recipe/
    recipe.yaml
    build.sh
    tests/offline_science_smoke.py
```

The recipe uses the conda v1 `recipe.yaml` format. Its source is the official,
versioned PyPI sdist:

```text
https://pypi.org/packages/source/x/xstar-tools/xstar_tools-${version}.tar.gz
```

with an exact SHA-256. The `conda/` directory is deliberately excluded from the
PyPI sdist, so the recipe can pin that sdist hash without a checksum
self-reference.

## Native build policy

Linux `linux-64`, macOS `osx-64`, and macOS `osx-arm64` build the native runtime
with:

```text
XSTAR_TOOLS_NATIVE=required
XSTAR_TOOLS_NATIVE_PROFILE=conda
```

The `conda` profile maps to `make conda`. It preserves the normal public C API,
Python-to-C++ backend, scientific/runtime libraries, `xstar-cpp`, and serial
XSTAR2XSPEC programs while excluding:

- the optional standalone Python-embedding plugin;
- `xstar-xspec-mpi` from the ordinary package.

Windows conda packaging is intentionally deferred. The accepted native Windows
source/PyPI contract uses MSYS2 UCRT64 / MinGW-w64 GCC, while conda-forge's normal
native Windows toolchain contract is MSVC. The existing accepted Windows source
and PyPI support are unchanged.

## CFITSIO and linking

CFITSIO is a conda `host`/`run` dependency and is not vendored into the conda
package. `0.6.90` also carries the upstream link correction discovered during
the initial staged-recipes qualification: the public `xstar-cpp` frontend link
now repeats `$(CFITSIO_LIBS) $(CFITSIO_RPATH)` when linking against
`libxstar_production_zone`. This removes the feedstock-only GNU `-rpath-link`
workaround that was required for the immutable `0.6.89.5` PyPI source archive.

## Python dependency policy

Because this is a platform-specific native package, conda-forge owns the Python
build matrix. The recipe therefore uses an unconstrained `python` host/run
requirement and does not redefine `python_min`. Runtime numerical dependencies
retain the upstream Python-version split:

- Python < 3.11: NumPy `>=1.23,<2.4`, Astropy base `>=5.0`;
- Python >= 3.11: NumPy `>=1.24`, Astropy base `>=7.2`.

The conda package uses `astropy-base`, following conda-forge packaging guidance,
while upstream PyPI metadata continues to depend on `astropy`.

## License

The active project and conda recipe SPDX expression is `GPL-3.0-only`. The
project ships the GNU General Public License Version 3 text in top-level
`LICENSE`. A commented historical `GPL-3.0` marker remains in `pyproject.toml`
only so qualification for the already-published 0.6.89.x artifacts can be
replayed accurately.

## Atomic data and science smoke

`atdb.fits` remains external. It is neither embedded in the Python package nor
the conda package. The conda test suite includes a deterministic offline
`bremem` bremsstrahlung smoke that requires no atomic database or network
access, plus installed import/CLI/ABI/doctor checks.

## Local qualification

Repository CI builds the exact local sdist and rewrites only the source URL and
SHA in a temporary recipe copy:

```bash
python -m build --sdist
python tools/packaging/prepare_local_conda_recipe.py \
  --recipe conda/recipe \
  --sdist dist/xstar_tools-0.6.90.tar.gz \
  --out run_conda_recipe
rattler-build build --recipe-dir run_conda_recipe
```

The checked-in recipe itself always remains pointed at PyPI.

## staged-recipes, feedstock, and automatic updates

The initial recipe is submitted under `recipes/xstar-tools/` in
`conda-forge/staged-recipes`. After acceptance, conda-forge automatically
creates `conda-forge/xstar-tools-feedstock`; generated CI files are then owned by
conda-smithy and should not be copied back into the upstream repository.

The versioned PyPI source URL is intentionally bot-discoverable. When a new
`xstar-tools` version is released to PyPI, `regro-cf-autotick-bot` detects the
release and opens a feedstock PR updating the version/source hash. If fully
automatic merging of passing bot PRs is desired, request conda-forge bot
automerge in the generated feedstock with:

```text
@conda-forge-admin, please add bot automerge
```

That automerge setting belongs to the conda-forge feedstock, not this upstream
source tree.
