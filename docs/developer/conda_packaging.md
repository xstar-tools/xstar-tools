# Conda packaging

The `0.6.90` conda campaign is closed. The accepted public conda-forge package
is `xstar-tools 0.6.89.5` build 1 on `linux-64`, `osx-arm64`, and `osx-64`.
Windows conda packages are not supported.

The repository copy under `conda/recipe/` is retained as the accepted recipe
reference. `tools/packaging/prepare_local_conda_recipe.py` can prepare that
`recipe.yaml` for local qualification work. The closed `0.6.90.1` and
`0.6.90.2` host/release-closure workflows are no longer carried in the active
workflow directory; their exact definitions remain available from the
corresponding repository history/tag.

The scientific/runtime policy is unchanged: conda uses external conda-forge
CFITSIO, `atdb.fits` stays external, ordinary packages are non-MPI, and native
scientific behavior remains governed by the parity freeze.
