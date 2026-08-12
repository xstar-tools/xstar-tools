# 0.6.82.26 - `radexp` / `density.dat` source semantics

Canonical oracle: unmodified FORTRAN XSTAR 2.59g.

This milestone implements the radial-density branches that are inline in
`xstar.f90` without changing fixed-state atomic/thermal equations.

## Analytic branch

For the public constant-density mode (`lcpres=0`, source `lcdd=1`), XSTAR
captures `xpx0=xpx` and `r0=r` at first-shell entry. After each accepted shell
it first advances radius by the STEP-selected `delr`, then evaluates

`xpx = xpx0 * (r/r0)**radexp`.

The post-update density is then used by `xcol=xcol+xpx*delr` and by the next
local-zone evaluation. `radexp=0` remains the frozen constant-density path.

## Hidden tabulated branch

The executable source uses the literal condition `radexp < -99.0`, even though
stock `xstar.par` advertises the ordinary analytic interval `[-3,3]`. The public
ports therefore keep `[-3,3]` and additionally admit the disjoint hidden
sentinel domain `<-99`; values in `[-99,-3)` remain invalid.

For `radexp<-99` the fixed-name file `density.dat` is consumed sequentially:

1. row 1 replaces the initial radius and hydrogen density before pass 1;
2. HEATT still consumes the prior STEP `delr`;
3. after `pprint`/`savd`, the next table row replaces `delr` with `rnew-r`, then
   replaces `r` and `xpx`;
4. negative `delr` is the source `radius error`; equal radius is allowed;
5. radial depth, column, STPCUT and TRNFRN use the table-derived geometry;
6. EOF sets nonzero I/O status while retaining the preceding row values, so the
   normal source shell predicate terminates without an invented density cap.

Python accepts `--input-dir` through the public physical runner. Native
`xstar-cpp` also accepts `--input-dir`; both resolve `density.dat` there.

## Termination policy

No new cap is added for `radexp<=-1` or increasingly ionized flows. Existing
source predicates (column, electron fraction, temperature, record inventory,
I/O status) remain authoritative. The historical source `jkp>3999` hard stop is
not altered.

## Frozen identifiers

- science revision `0.6.48.12.3.45.3.3.8`
- C API ABI `60487`
- production-zone ABI `6048110`
- fixed-state ABI `60488`

The accepted `0.6.82.25.4` Python `msolvelucy` correction is retained.
