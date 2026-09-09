# C++ and native CLI reference

The non-MPI native CLI is qualified on Linux GCC, macOS Apple Clang (arm64 and x86_64), and Windows MSYS2 UCRT64/MinGW-w64. True MPI remains an explicit Linux/HPC-oriented build. Windows MPI and MSVC are not planned; Windows local parallel execution uses `xstar-xspec --processes N`.

```{toctree}
:maxdepth: 2

build
xstar_cpp
xstar_xspec_initable
xstar_xspec_table
xstar_xspec
xstar_xspec_mpi
c_abi
```
