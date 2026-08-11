# 0.6.82.7 canonical Type-63 source cutoff

Canonical XSTAR 2.59g `ucalc.f90`, Type 63, computes the transition wavelength
from the packed endpoint energies, then `ekt=0.861707*T4` and
`delt=12398.4016/elin/ekt`.  It exits before both the same-n and n-changing
branches when, and only when, `delt.gt.50.`.

The 0.6.82.6 native helper omitted this gate.  In the accepted first state of
the C5 `ne=1e12`, `rlogxi=1.2` diagnostic, canonical FORTRAN zeroed 16 C V
Type-63 records while C++ committed nonzero rates.  The first source record is
6600 (idest1=7, idest2=29, DeltaE about 70.41159 eV).

0.6.82.7 restores the literal source operation order in C++ and Python.  It
does not alter the 0.6.82.6 terminal STEP endpoint repair.

## Qualification sequence

1. Direct kernel cutoff tests: T4=1.351 zero; T4=2.110 evaluates; delt=50
   evaluates; the next representable value above 50 zeros.
2. Host C5 `ne=1e12` at rlogxi=1.2 and 1.3 against FORTRAN 2.59g.
3. If both close, rerun rlogxi=1.0..1.5.
4. Re-run the five historical rlogxi=1.5 densities.
5. Only after that, widen the normal qualification range to rlogxi=-5..+5.
