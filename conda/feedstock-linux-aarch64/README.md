# Accepted conda-forge Linux ARM64 feedstock configuration

This directory is **not** automatically consumed by conda-forge. Upstream
feedstock: <https://github.com/conda-forge/xstar-tools-feedstock>.

The separate feedstock adopted `provider.linux_aarch64: default` and
rerendered its CI in [PR #6](https://github.com/conda-forge/xstar-tools-feedstock/pull/6).
The public `linux-aarch64` channel now contains `xstar-tools 0.6.90.5.8` for
Python 3.11–3.15. This directory retains a configuration example and does **not**
automatically update the live feedstock. Future recipe upgrades must reference
a published source archive with its verified SHA-256.

The source-repository native ARM64 conda qualification workflow remains an
optional diagnostic; feedstock CI and public-channel artifacts supply the
acceptance evidence. Windows conda and MPI remain outside the package contract.
The external `atdb.fits` database is not bundled, and the frozen science source
is unchanged.
