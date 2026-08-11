# 0.6.82.16 source-faithful ispec4 erg/eV normalization

Canonical XSTAR 2.59g `ispec4.f90` normalizes the built-in power law with the
`ergsev` parameter imported from `constants.f90`:

```fortran
real(8), parameter :: ergsev = 1.602176634e-12
...
const=xlum/sum/ergsev
```

The initializer is an unsuffixed default-REAL literal.  Under the canonical
compiler semantics used by the source, it is rounded to binary32 first and
then promoted into `REAL(8)`, yielding approximately
`1.602176616204154e-12` in binary64.

The Python and standalone-C++ built-in power-law paths had retained the older
`1.602197e-12` factor.  Version 0.6.82.16 changes only the ispec4-equivalent
power-law normalization to the source-rounded modern `ergsev`.  The historical
`ispcg2.f90` diagnostic/publication factor remains unchanged because it is a
different source surface.

This is a narrow source-concordance correction after 0.6.82.15 made the
H+He+C `rlogxi=-3` trajectory exact through row 67 in printed `h-c` and
`ntotit`, leaving only isolated late iteration-count differences.  Host
qualification at `rlogxi=-3` and `-2` remains required before closure.
