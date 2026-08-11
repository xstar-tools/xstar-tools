# 0.6.82.10 Type-53 all-element live escape state

`calc_hmc_ion.f90` applies the Type-53/RRC escape factors from the live continuum optical depths and `cfrac` for every element. Earlier native code had grown from H+He+Mg qualification paths and later generic branches; Carbon still retained a default `ptmp1=ptmp2=0.5` in the production path until the low-`xi` H+He+C campaign exposed the error.

0.6.82.10 binds the record-local `tau_in`, `tau_out`, and effective DSEC covering fraction before any element-specific compatibility/audit branch:

- `ptmp1 = pescv(tau_in) * (1-cfrac)`
- `ptmp2 = pescv(tau_out) * (1-cfrac) + 2*pescv(tau_in+tau_out)*cfrac`
- `pescv(tau) = max(exp(-tau),1e-12)/2`

The correction is deliberately all-element. It keeps the explicit historical helium row-46 oracle override only where that captured contract is selected.

Host qualification at release creation uses `cfrac=1`. `rlogxi=-4,-1,0` are closed at the STEP/material level; `-3,-2` remain open and `-5` retains two `ntotit` mismatches despite material acceptance. `cfrac<1` remains an explicit future qualification axis; `cfrac=0.4` must be run in both canonical FORTRAN and C++.
