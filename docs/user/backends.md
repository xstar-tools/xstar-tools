# Choosing a backend

| Mode | Python controller | C++ science | Standalone | Recommended role |
|---|---:|---:|---:|---|
| `pure-python` | yes | no | no | source-faithful reference/debugging |
| `zone-python` | yes | modular kernels | no | accelerated Python |
| `zone-cpp` | invocation only | shared zone production | no | production shared-zone runs |
| `zone-all` | invocation only | shared all-zone production | no | production shared-all runs |
| `xstar-cpp` | no for direct run | native production | yes | Python-free native execution |

Use:

```bash
xstar-tools backends
```

to see host availability and native identities.

The old internal backend flags remain advanced compatibility aliases for the current deprecation period. New scripts should use the stable mode names.

A public mode name is intentionally stronger than a convenience alias: `zone-cpp`, `zone-all`, and `xstar-cpp` cannot be mixed with modular backend overrides.


## Native platform scope

The native non-MPI path is qualified on Linux GCC x86_64, macOS Apple Clang arm64/x86_64, and Windows MSYS2 UCRT64/AMD64. `xstar-xspec --processes N` is the accepted local parallel table path on all of those hosts. True MPI is an explicit Linux/HPC-oriented build and Windows MPI is deferred.
