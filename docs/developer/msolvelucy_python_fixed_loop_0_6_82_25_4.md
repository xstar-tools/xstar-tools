# 0.6.82.25.4 - Python `msolvelucy` `diff2` fixed-loop correction

Canonical FORTRAN `msolvelucy.f90` has two nested controls around the fixed-point update:

- the fixed-point loop continues while `nit2 < nitmx2` and `diff2 >= crit2`;
- the ordered per-row calculation of `diff2` stops scanning rows once cumulative `diff2 >= 1.e3`.

The pure-Python translation already implemented the second rule in `_source_fixed_difference()`, but then incorrectly executed an additional outer `break` when the returned `fixed_diff >= 1.e3`.  In the `cd_xi1` C5 case this prematurely stopped Carbon's first Lucy fixed-point cycle and produced the wrong population solution, thermal residual, and DSEC iteration count.

`0.6.82.25.4` removes only that erroneous outer `break`.  It does not change the ordered `diff2` scan, tolerance values, rate or matrix equations, DSEC, pressure logic, C++ science, science revision, or ABIs.

The direct regression forces fixed iteration 1 to return `diff2=1500` and fixed iteration 2 to return `0`; success requires two fixed-point iterations.  A separate regression confirms that `_source_fixed_difference()` itself still truncates its ordered row scan at cumulative `1.e3`.
