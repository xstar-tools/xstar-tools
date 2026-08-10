# Conda and conda-forge packaging

Milestone 9 adds a conda-forge-ready single-package recipe without changing the
scientific implementation or the retained native compiler semantics.

## Format decision

The repository uses the mature conda-build `meta.yaml` recipe format. The newer
v1 `recipe.yaml` format is intentionally deferred because the current
productization priority is a conservative packaging layer around already
qualified native code.

The feedstock seed lives in:

```text
conda/
  README.md
  conda-forge.yml
  recipe/
    meta.yaml
    build.sh
    bld.bat
    tests/offline_science_smoke.py
```

`conda/` is not included in the PyPI sdist. The committed recipe points to the
PyPI source archive and pins its SHA-256, which avoids a checksum self-reference
between the recipe and its own source archive.

## Build policy

Linux conda packages set `XSTAR_TOOLS_NATIVE=required` and reuse the retained
qualified Makefile through the same setuptools build hook as native pip wheels.
The recipe declares the conda-forge C++ compiler/stdlib activation, `make`,
`pkg-config`, and CFITSIO.

macOS and Windows use `XSTAR_TOOLS_NATIVE=off` and expose the same explicit
Python-only capability behavior as Milestone 8. Native portability on those
platforms remains a separate qualification project.

## Dependencies

Hard runtime dependencies are:

- Python >= 3.11;
- NumPy >= 1.24;
- Astropy >= 7.2;
- CFITSIO on Linux native builds.

Optional Python features remain optional:

- `h5py >= 3` (`hdf5` extra);
- `scipy >= 1.8` (`sparse` extra).

The recipe expresses those optional compatibility ranges through
`run_constrained`; it does not install them for every user.

## Offline test

Conda tests include imports, `pip check`, public CLI/version/doctor checks, Linux
native ABI checks, and `offline_science_smoke.py`. The smoke executes the
source-faithful XSTAR `bremem.f90` bremsstrahlung leaf against pinned numerical
results without requiring `atdb.fits` or network access.

## Atomic data and package splitting

`atdb.fits` remains external and is not a conda package payload. Do not create a
separate `xstar-data` package until licensing, size, update cadence, and XSTAR
data-version policy are explicit.

Likewise, `xstar-cpp` remains part of `xstar-tools`: it uses the same release,
science revision, C API, production-zone ABI, and native core. Splitting it now
would add dependency/version coupling without an independent lifecycle.

## Staged-recipes / feedstock workflow

1. Publish the exact `xstar_tools-<version>.tar.gz` sdist whose SHA-256 is pinned
   in `conda/recipe/meta.yaml`.
2. Copy `conda/recipe/` into a new `recipes/xstar-tools/` directory in
   `conda-forge/staged-recipes` and submit the PR.
3. After acceptance, use the generated feedstock and copy the seed
   `conda/conda-forge.yml` settings as appropriate before rerendering.
4. Let conda-smithy own generated CI files thereafter.

Project CI tests the same recipe before PyPI publication by replacing only the
source URL/SHA in a temporary recipe copy with the exact locally built sdist.
