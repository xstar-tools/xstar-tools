# 0.6.82.14 - source-faithful `pescl` high-tau constant

Canonical XSTAR 2.59g `pescl.f90` declares `pi` as `real(8)` but initializes it with the default-REAL literal `3.1415927`. On the supported IEEE implementation this promotes the binary32-rounded value `3.1415927410125732` into the double-precision calculation.

The native C++ port accidentally contained `3.1451653589793238...`. Because the `tau >= 1` branch contains `1/sqrt(pi)`, this biased every optically thick line escape probability by about `-5.68115e-4` (-0.0568%). The low-`tau` branch does not use `pi`.

At H+He+C, density `1e12`, column `1e20`, `cfrac=1`, `rlogxi=-3`, the first finite-zone H Type-50 records 186/187 have `tau` approximately 2.181 and 4.362. Their observed C++/FORTRAN `ans2` errors were about -0.055%. Combining the independently measured FORTRAN/C++ `tau` values with the erroneous C++ `pi` predicts the record-186 observed ratio to within 0.1 ppm. This identifies the constant as a real source-concordance bug rather than a heuristic adjustment.

0.6.82.14 changes only `pescl` constant semantics in C++ and Python. The accepted science revision and public ABIs remain frozen. Host qualification must rerun `rlogxi=-3` first, then `-2`; no low-ionization closure is claimed before those runs.
