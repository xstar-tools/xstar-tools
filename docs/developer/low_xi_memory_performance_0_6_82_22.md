# 0.6.82.22 low-ionization memory/performance optimization

This milestone is science-neutral. It follows the accepted C5 `cfrac=0`, `0.4`, and `1.0` campaigns and keeps the 0.6.82.20 Type-50 and 0.6.82.21 DSEC source-return repairs frozen.

The 0.6.82.21 `cfrac=0`, `rlogxi=-3` emult sweep exposed near-linear retained-memory growth with radial-zone count. `emult=0.25` retained 1.720 GB of product-array payload for 150 zones, while `emult=0.1` was killed with return code 137 after 289 C++ zones (FORTRAN completes 367).

0.6.82.22 compacts only completed, nonterminal sparse RRC source-address planes into the exact RRC identity order already used by the generic publication path. The newest/terminal accepted state remains full source-indexed. Reference and diagnostic trajectories are unchanged. It also avoids allocating opacity-producer diagnostic scratch buffers on every fixed-state evaluation when the corresponding diagnostics are disabled.

New cumulative timing markers cover all fixed-state evaluations rather than only the historical first controller slots. The emult runner records `/usr/bin/time -v` maximum RSS and uses a fixed CSV schema so an early failed run cannot break the final summary.

Host acceptance remains scientific first: FORTRAN and C++ must agree under the existing STEP/material/Option-1 criteria at identical emult. Performance and RSS are measured, not allowed to weaken science gates.
