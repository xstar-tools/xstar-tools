# 0.6.82.19 Type-50 cfrac<1 caller-grid ownership

Canonical `xstarcalc.f90` executes `calc_hmc_all` and `calc_emisab_all` with the reduced `epim/bremsam` radiation workspace, then executes `calc_emis_all` with the full `epi/bremsa` workspace. `calc_emis_ion.f90` explicitly calls `ucalc` again for selected Type-50 lines before forming `fline`; Type-50 `ucalc.f90` samples `bremsa(nbinc(abs(eeup-eelo)))` and multiplies the photoexcitation rate by `max(0,1-cfrac)`.

At `cfrac=1` that photoexcitation channel is identically zero, so reusing the earlier reduced-grid Type-50 answer in the C++ line-emissivity stage was invisible. At `cfrac=0.4` the bug becomes active and strongly biases transmitted/reflected line luminosities. Python also ignored its full-grid calc-emis role and sampled Type-50 pumping from the reduced workspace; several fast packets additionally used wavelength-derived energy rather than the live endpoint difference.

0.6.82.19 keeps the reduced Type-50 answer for calc_hmc/matrix ownership, retains a distinct full-grid Type-50 calc-emis answer for fline/rcem publication, and uses the live endpoint energy for `nbinc` in C++ and Python. No ABI identifier is changed.
