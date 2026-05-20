# Physical `dsec` runner (v0.4.47)

v0.4.47 corrects the population-state ownership used by
`examples/119_validate_xstar_dsec_complete.py`.

## Correct source state

XSTAR does not carry a fixed compact population vector between `dsec` trials.
It carries the global `xilevg` array. On every call to `calc_hmc_all`, the
current `istruc` result selects a possibly different active ion range, and
`calc_hmc_all.f90` maps the global levels into the current compact `xileve`
vector in source ion/level order.

The first selected `dsec` call in the bounded run is call 1. `init.f90` clears
all entries of `xilevg` to zero before this call. At `T4=100`, oxygen has a
367-row compact basis, so the converged call-73 607-row vector must not be
replayed.

v0.4.47 therefore:

- starts call 1 from an explicit empty/zero global population map;
- maps global populations after each dynamic active-ion selection;
- lets later-ion grounds overwrite shared previous-ion continuum rows;
- merges returned active rows back into the global workspace;
- preserves inactive/stale rows for later basis expansion;
- permits the source-valid all-zero first `msolvelucy` seed;
- rejects `dsec_call_id` values other than 1 until a later-call incoming global
  population capture is available.

## Rerun

Use the same example-119 command and the same v0.4.45 instrumented XSTAR build.
No Fortran source or probe change is required.
