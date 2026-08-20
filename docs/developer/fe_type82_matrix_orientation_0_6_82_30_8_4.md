# 0.6.82.30.8.4 - Fe Type-82 UTA matrix orientation repair

## Evidence from the paired call-1 diagnostics

The `.30.8.2` run showed that at the common first state (`T4=100`, `xee=1`) H, He, Compton, bremsstrahlung, and free-free terms agree, while Fe has already collapsed to almost pure stage 16 in C++.

The `.30.8.3` matrix diagnostic initially reported an input-topology mismatch, but that headline was a comparator artifact: the FORTRAN log contains H, He, and Fe `msolvelucy` blocks, and the comparator merged all three; it also compared FORTRAN physical ion stage with the C++ local ion counter.  After isolating the `FE2_SOLVER 4456 33 519720` block and comparing C++ `ion_charge+1`, the 4456-row input topology is exact and the Fe matrix-record inventory is 129930/129930.

The genuine endpoint-identity mismatches are dominated by Type 82: 462 Fe UTA radiative records, each producing four matrix insertions, for 1848 transposed matrix terms.

## Canonical source semantics

For Type 82, canonical `ucalc.f90` energy-orders `idest1/idest2` as upper/lower and then swaps the returned `ans1/ans2`, leaving `ans1` as the upward photoexcitation rate and `ans2` as the downward radiative-decay rate.  `calc_hmc_ion.f90` treats rate type 4 with the normal energy-order branch and inserts the first term at `(upper,lower)`.

The C++ fixed-program contribution ABI has the opposite naming contract: `lower_row` must be the energy-low compact row and `upper_row` the energy-high compact row, because `element_engine.cpp` emits its first matrix term at `(upper_row,lower_row)`.

`.30.8.3` lowered Type 82 with `upper_lower_pair`, storing high in `lower_row` and low in `upper_row`.  This transposed every Type-82 matrix transition.

## Repair

`.30.8.4` changes only the Type-82 lowering orientation:

```cpp
case 82:
    ...
    energy_order_pair(ii[0], ii[1]);
```

The rate arithmetic, `ans1/ans2`, Type 75, Type 92, solver, thermal controller, transport, science revision, and ABIs are unchanged.

## Offline replay

Replaying the captured 129930-record Fe contribution stream through the native solver reproduces the rejected baseline: non-converged and nearly pure Fe XVI.  Swapping only Type-82 endpoints produces a converged solution whose stage-11 through stage-26 population vector matches the canonical FORTRAN call-1 vector to printed precision.  Swapping Type 92 alone does not repair the collapse; changing Type-75/rate-40 endpoints has no effect in this replay.  Therefore `.30.8.4` intentionally changes Type 82 only.
