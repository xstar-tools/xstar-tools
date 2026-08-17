# xstar_tools 0.6.82.25.2 — pressure Python continuum / compare hotfix

## Scope

`0.6.82.25.2` is a narrow corrective successor to `0.6.82.25.1`.
The constant-pressure equations introduced in `.25` and the native STEP
publication repairs introduced in `.25.1` remain frozen.

## Pure-Python failure exposed by .25.1

The `.25.1` BREMSMAP row-1000 capacity repair allowed `cp_xim2` to advance
past the previous minimum-grid failure.  It then stopped in `calc_hmc_all`
with:

```text
CalcHMCAllError: bremem incoming opakc does not match preceding freef output
```

The physical-runner kwargs factory had prebuilt `comp2/freef/bremem` contexts
from the trial `runtime.hydrogen_density_cm3`.  Canonical `calc_hmc_all` first
mutates `xpx` under `lcdd=0` to

```text
pressure / (REAL4(1.38e-12) * T4)
```

before executing those continuum routines.  Because the prebuilt `freef`
context and the actual `calc_hmc_all` `freef` used slightly different density
values, the exact mutable-`opakc` sequence check rejected `bremem`.

`.25.2` resolves `continuum_xpx` with the same
`resolve_calc_hmc_all_density()` helper before prebuilding all three continuum
contexts.  Constant-density `lcdd=1` is unchanged.

## Compare harness defect

The `.25.1` compare loop treated a backend directory as a completed candidate.
A failed pure-Python run leaves its directory behind, so a C++-only comparison
could accept C++ and then crash opening the absent Python `xout_step.log`.

`.25.2` requires both `xout_step.log` and `xout_abund1.fits` before comparing a
backend/case and adds repeatable `--backend cpp|python`.  Missing products are
reported as `PENDING`; they are not a dependency of the other backend.

## Frozen identifiers

- science revision `0.6.48.12.3.45.3.3.8`
- C API ABI `60487`
- production-zone ABI `6048110`
- fixed-state ABI `60488`
