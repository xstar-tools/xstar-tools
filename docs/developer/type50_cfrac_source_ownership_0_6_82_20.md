# 0.6.82.20 cfrac<1 Type-50 source ownership

`0.6.82.20` is a narrow source-concordance successor to `0.6.82.19`.

Canonical FORTRAN XSTAR 2.59g fixes the reduced DSEC radiation workspace at
`ncn2m=999`. `xstarcalc.f90` remaps the current full `epi/bremsa` state into
`epim/bremsam` and passes that reduced pair to `calc_hmc_all`. Type-50 pumping
inside that call must therefore use the 999-bin reduced caller grid. Later,
`calc_emis_ion.f90` invokes `ucalc` again on the live transported full
`epi/bremsa` pair.

The `.19` native implementation still sampled the wrong owner at both stages:
DSEC Type-50 used the original full input arrays, while its full-grid shadow
sampled the incident controller spectrum rather than the live transported
`bremsa`.

This release also removes the historical port-only semantic split in which
`emult` could populate a fixed-state covering-fraction field. In FORTRAN,
`cfrac` owns emission/escape/thermal physics; `emult` is only the radial STEP
Courant multiplier. ABI field names are retained, but fixed-state callers now
populate/use them from `cfrac`.

The first host science gate is deliberately one point only:

- H + He + C
- `ne=1e12 cm^-3`
- `column=1e20 cm^-2`
- `cfrac=0.4`
- `rlogxi=-3`

Do not widen the grid until Option 1 and Option 17 materially move toward stock
FORTRAN. DSEC convergence limits, Type-53 algebra, `pescl`, science revision,
and ABI identifiers remain frozen.
