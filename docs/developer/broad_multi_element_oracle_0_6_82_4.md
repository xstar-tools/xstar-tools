# 0.6.82.4 broad multi-element FORTRAN-oracle closure

`0.6.82.4` follows the host rejection of `0.6.82.3`.  The `0.6.82.3`
15-element run proved that native ATDB lowering, Type-51 fallback, live zone
printing, and the source-derived radius/log-xi were working, but it still
reported essentially zero first-zone Fe heating (`1.50024e-13`) instead of the
XSTAR 2.59g value (`8.1714`), different thermal-convergence diagnostics, and a
runtime of about 3145 s versus 870 s for FORTRAN.

This successor has three source-concordance changes.

1. **Type-85 endpoint ownership.**  `ucalc.f90` publishes Type-85 with
   `idest1` from the source record and `idest2=1`.  `calc_hmc_ion.f90` then
   applies its universal energy ordering (except rate types 7 and 41) before
   putting `ans4*xpx`/`ans6*xpx` on the lower-level thermal diagonal.  The
   native lowerer now performs the same ordering for Type-85.  This is distinct
   from the already-correct `0.6.82.3` post-`phintfo` channel mapping.

2. **STEP iteration-count semantics.**  XSTAR `pprint.f90` writes the literal
   DSEC `ntotit`.  Native live progress and Option 17 now publish the retained
   DSEC evaluation count directly, with no `-1` display adjustment.  The
   numerical `h-c(%)` columns continue to come from the actual retained
   thermal/radiation residuals; they are not cosmetically altered.

3. **DSEC hot path.**  Source `dsec.f90` calls `calc_hmc_all` only.  The
   emission/opacity projection (`calc_emisab_all`, `calc_emis_all`, including
   Type-50 line profiles) is performed by `xstarcalc.f90` after DSEC reaches an
   accepted boundary.  Native production now marks DSEC trial evaluations as
   HMC-only and skips the previously duplicated spectral projection on those
   trials.  Accepted-boundary and final product evaluations still execute the
   complete projection path.

The permanent oracle for this milestone is the supplied 14-row FORTRAN 2.59g
Option-17 trajectory.  The version-locked host runner additionally checks the
first-row element heating/cooling budget against the supplied FORTRAN product,
using the established `<1%` material criterion.  It reports science and
performance separately and requires both for overall host ACCEPT.

The host runtime target is measured against the supplied FORTRAN run
(`869.676651 s`).  A default ratio limit of 1.25 is used for this broad fixture.
That performance threshold is a release qualification target, not a scientific
comparator threshold.

Accepted historical science and ABI boundaries remain unchanged.  This
milestone qualifies a broad multi-element surface that was explicitly rejected
in `0.6.82.3`; it does not reopen the frozen all-62/Ca/O/C5 surfaces.
