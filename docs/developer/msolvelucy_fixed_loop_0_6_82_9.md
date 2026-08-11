# 0.6.82.9 source-faithful `msolvelucy` fixed-point control

## Scope

`0.6.82.9` removes one C++-only termination condition from the native element
population solver.  Canonical `msolvelucy.f90` computes `diff2` by scanning
rows until `diff2 >= 1.e3`, but that condition only ends the inner row scan.
The surrounding fixed-point loop continues while `nit2 < nitmx2` and
`diff2 >= crit2`.

The pre-0.6.82.9 C++ translation incorrectly did:

```cpp
fixed_diff = source_fixed_difference(...);
if (fixed_diff >= 1.0e3) break;
```

The `break` has no FORTRAN counterpart and prematurely terminates difficult
low-ionization Carbon solves.

## Direct Carbon proof

For H+He+C, density `1e12`, `cfrac=1`, `column=1e20`, `xdef`, `rlogxi=0`,
call 1 / evaluation 1 (`T4=100`, `xee=1`):

| Solver | Lucy outer | fixed total | Carbon heat | Carbon cool |
|---|---:|---:|---:|---:|
| C++ 0.6.82.8 | 5 | 603 | 481.8847 | 21456.0737 |
| C++ with source loop | 3 | 600 | 508.0654 | 9231.9349 |
| FORTRAN 2.59g | 3 | 600 | ~508.1 | ~9232 |

The correction therefore closes the first fixed-state thermal discrepancy before
DSEC chooses a different root-search branch.

## Host status

The corrected native run reproduces the canonical first-row `h-c=-0.05` and
`ntotit=42` and matches the FORTRAN STEP sequence through most of the `rlogxi=0`
trajectory.  A later divergence remains open beginning near `log(N)=19.80`:
FORTRAN has `h-c=0.00, ntotit=8`, while C++ has `h-c=0.13, ntotit=16`.
`0.6.82.9` therefore does **not** claim full low-ionization closure.

## Frozen adjacent changes

- 0.6.82.8 persistent source `rnisi(nd=20000)` workspace
- 0.6.82.7 Type-63 `delt > 50` cutoff
- 0.6.82.6 canonical terminal STEP endpoint
- public ABIs and unrelated rate/matrix/transport algorithms

The rejected Type-73 exponential and DSEC temperature round-trip experiments are
not included in this release.
