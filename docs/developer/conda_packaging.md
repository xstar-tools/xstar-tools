# Conda packaging

The `0.6.90` conda campaign established the accepted initial conda-forge
package, `xstar-tools 0.6.89.5` build 1, for `linux-64`, `osx-arm64`, and
`osx-64`. Subsequently, `0.6.91.5` added **published `linux-aarch64` support**;
its public channel offers `xstar-tools 0.6.90.5.8` for Python 3.11–3.15.
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

## Linux ARM64 enablement (0.6.91.5 ACCEPT)

The independent [xstar-tools feedstock](https://github.com/conda-forge/xstar-tools-feedstock)
enabled `provider.linux_aarch64: default`, rerendered its platform CI in
[PR #6](https://github.com/conda-forge/xstar-tools-feedstock/pull/6), and
published `linux-aarch64` builds. Public-channel verification on 2026-10-09:

```bash
conda search --override-channels -c conda-forge --subdir linux-aarch64 xstar-tools
```

This lists xstar-tools `0.6.90.5.8` for Python 3.11–3.15. The optional native
`ubuntu-24.04-arm` source-repository conda workflow remains available as a
diagnostic but is **not** a prerequisite for conda-forge publication
acceptance. Conda uses its own CFITSIO dependency, never bundles `atdb.fits`,
and preserves the frozen scientific implementation. The feedstock must always
reference a genuinely published source archive and its verified SHA-256;
acceptance of the platform does not mean source release 0.6.91.5 has been
published on conda-forge.

See {doc}`conda_linux_arm64_0_6_91_5` for commands and acceptance policy.
