# 0.6.82.21 DSEC source-return acceptance

Canonical FORTRAN `dsec.f90` can leave its inner charge loop when `nnxx >= nlimxx`, then accept the current thermal state when `abs(hmctot) <= epst`. `xstarcalc.f90` does not add a second post-return rejection based on an independently reconstructed charge-convergence flag or on `lnerr`.

`0.6.82.20` reproduced the source controller endpoint for H+He+C, `cfrac=0`, `rlogxi=-2` at 124 evaluations with `hmctot=9.2932e-05`, but generic C++ production rejected it because `charge_converged` was false.

`0.6.82.21` removes only that non-source post-return veto. Native controller execution failures still fail. Reference-trajectory assertions remain strict. Convergence flags, residuals, `lnerr`, and `ntotit` remain diagnostics.

The first host gate is only `cfrac=0`, `rlogxi=-2`. Wide `cfrac=0` and the `emult=0.1,0.25,0.5,1.0` sweep remain blocked until this case closes against original unmodified FORTRAN XSTAR 2.59g.
