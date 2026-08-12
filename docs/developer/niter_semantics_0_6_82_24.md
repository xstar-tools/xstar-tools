# 0.6.82.24 niter semantics

Canonical FORTRAN maps public `niter` to `nlimd` in `rread1.f90`.
`xstarcalc.f90` calls `dsec` only when `nlimdt != 0`. Therefore `niter=0`
keeps the input temperature and source electron-fraction coordinate (`xee=1`
at first-pass initialization), then executes the ordinary final `calc_hmc_all`,
`calc_emisab_all`, and `calc_emis_all` sequence.

Inside `dsec.f90`, `nlimt=max(nlim,0)` and `nlimx=abs(nlim)`. Negative `niter`
therefore permits charge iterations but no temperature iteration. Positive
`niter` permits both.

C++ 0.6.82.24 preserves the requested integer unchanged and implements the
zero branch by skipping the thermal controller rather than calling it with
`nlim=0`, which would introduce an extra `calc_hmc_all` evaluation not present
in `xstarcalc.f90`.

Python already contained the same source branches; 0.6.82.24 adds explicit
source and host qualification gates rather than altering its science kernels.
