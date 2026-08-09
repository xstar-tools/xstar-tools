# Performance expectations

Performance depends strongly on element, ionization regime, density, spectrum, host CPU, compiler, and which scientific paths are active. The project therefore avoids promising one universal speedup.

General guidance:

- `pure-python` prioritizes source-faithful transparency and is normally the slowest public mode;
- `zone-python` keeps Python orchestration but uses qualified modular C++ kernels;
- `zone-cpp` and `zone-all` use the shared native production implementation;
- direct `xstar-cpp` removes the Python runtime from normal standalone execution.

For reproducible performance work, record the mode, compiler/native build, CPU features, thread count, science revision, atomic-data hashes, and input model. Scientific acceptance and performance are separate gates.

Historical optimization measurements are preserved under `historical/documentation/performance/`; they are development evidence, not performance guarantees for arbitrary systems.
