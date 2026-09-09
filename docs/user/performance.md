# Performance expectations

Performance depends strongly on element, ionization regime, density, spectrum, host CPU, compiler, and which scientific paths are active. The project therefore avoids promising one universal speedup.

General guidance:

- `pure-python` prioritizes source-faithful transparency and is normally the slowest public mode;
- `zone-python` keeps Python orchestration but uses qualified modular C++ kernels;
- `zone-cpp` and `zone-all` use the shared native production implementation;
- direct `xstar-cpp` removes the Python runtime from normal standalone execution.

For reproducible performance work, record the mode, compiler/native build, CPU features, thread count, science revision, atomic-data hashes, and input model. Scientific acceptance and performance are separate gates.

Historical optimization measurements remain available through version-control history and release tags; they are development evidence, not performance guarantees for arbitrary systems.


## XSTAR2XSPEC concurrency

`xstar-xspec --processes N` is process parallelism, not thread parallelism. N independent `xstar-cpp` processes may be runnable at the same time, which can consume approximately N times the per-model memory in the worst case. The OS chooses logical CPUs unless the user or batch system applies affinity.

`xstar-xspec-mpi` uses one XSTAR child per MPI rank. `mpirun -np N` therefore permits up to N concurrent XSTAR calculations. On clusters, choose rank count from both CPU and memory limits; do not infer a safe rank count from CPU count alone.
