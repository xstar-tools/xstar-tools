# 0.6.82.5 broad multi-element thermal/STEP closure

`0.6.82.5` follows the host rejection of `0.6.82.4`.  The 15-element
ATDB/lowering, radius/log-xi, and live-zone progress surfaces remain retained;
this revision addresses the four concrete defects exposed by the canonical
XSTAR 2.59g comparison.

1. Type-85 keeps the `0.6.82.4` energy-ordered endpoint ownership but restores
   the source label-85 post-`phintfo` channel rearrangement: `ans4=-ph.ans[2]`
   and `ans6=-ph.ans[4]`, with reverse channels zero.
2. The actual `standalone_iteration_evaluator()` production DSEC path sets
   `XSTAR_FIXED_RUNTIME_STATE_DSEC_HMC_ONLY`, matching `dsec.f90` ownership of
   `calc_hmc_all` and leaving emission/profile projection to accepted/final
   `xstarcalc` boundaries.
3. The thermal engine's literal `stats.ntotit` is retained per accepted radial
   zone and is the sole source for both live progress and STEP Option 17.
4. STEP Option 17 owns only physical controller boundaries.  The terminal
   synthetic/reset publication row no longer expands the STEP trajectory.

The canonical broad host fixture remains an external gate because the release
environment does not bundle `atdb.fits`.  Science acceptance remains `<1%`
material discrepancy against the preserved FORTRAN 2.59g oracle; performance
is reported independently against the supplied 869.676651 s FORTRAN runtime.
