# 0.6.82.24.3 pure-Python first `h-c(%)` source-stage ownership

Canonical XSTAR 2.59g calls `xstarcalc`, which optionally runs `dsec`, then **always** runs one final `calc_hmc_all`. `xstar.f90` calls `heatt` and only then `pprint(9)`. Therefore the first printed `h-c(%)` value is `100*hmctot` from the final `calc_hmc_all`, not the residual returned by the preceding DSEC controller.

Before 0.6.82.24.3, pure Python assigned `legacy_pprint_hc1_percent` inside the DSEC handler from `DsecResult.final_hmctot`. This was one source stage too early. On the accepted C5 `niter=99` run all 18 second `h-c(%)` values and all `ntotit` values matched FORTRAN, while selected first-column values differed by up to 0.40 percentage point.

0.6.82.24.3 removes DSEC ownership of that display snapshot and writes it in the final `calc_hmc_all` handler from `FixedStateCalcHMCAllResult.hmctot`. No thermal/charge controller arithmetic, rates, transfer, second `h-c(%)`, FITS science, or accepted `niter` semantics change.
