# He-like XSTAR Fortran/Python source-code parity audit

This note records the source-code comparison that motivated v0.3.148.

## Relevant XSTAR source path

For the He-like C V / O VII / Mg XI / Ca XIX local-state benchmark, the population matrix is assembled through:

```text
calc_hmc_all.f90
  -> calc_hmc_element.f90
     -> calc_hmc_ion.f90
        -> ucalc.f90
```

For rate type 4 / data type 50, `calc_hmc_ion.f90` obtains the live line optical depths from the internal `tau0(2, line)` array:

```fortran
tau1 = tau0(1, kkkl)
tau2 = tau0(2, kkkl)
ptmp1 = pescl(tau1) * (1. - cfrac)
ptmp2 = pescl(tau2) * (1. - cfrac) + 2. * pescl(tau1 + tau2) * cfrac
```

It then calls `ucalc.f90`.  In the type-50 branch, `ucalc` first computes the escaped downward rate and the lower-to-upper radiative excitation rate:

```fortran
ans1 = aij * (ptmp1 + ptmp2)
sigma = 0.02655 * flin * elin * 1.d-8 / vtherm
ans2 = sigma * bremsa(nb1) * vtherm / 3.e10 * flinabs(ptmp1)
ans2 = ans2 * max(0., 1.d0-cfrac)
```

At the end of the type-50 branch, XSTAR swaps the rates for the universal matrix assignment:

```fortran
anstmp = ans1
ans1 = ans2       ! lower -> upper photoexcitation
ans2 = anstmp     ! upper -> lower escaped decay
```

The important point is that `tau0(:,:)` and `bremsa(:)` are live internal arrays at the current local zone/iteration.  They are not generally identical to the post-transfer quantities written later to `xout_lines1.fits`, `xout_cont1.fits`, or `xout_spect1.fits`.

## Python mismatch found after v0.3.143

The experimental v0.3.143--v0.3.147 benchmark tried to substitute final output tables for XSTAR's live arrays:

```text
xout_lines1.fits depth_inward/depth_outward -> population-matrix tau0
xout_cont1.fits or xout_spect1.fits         -> population-matrix bremsa(nb1)
```

That is not source-code equivalent.  It can strongly over-suppress or over-pump the resonance transition, depending on `cfrac` and the final output depth/spectrum.  In the user's v0.3.147 run the XSTAR `cfrac` was 1, so the lower-to-upper line-pumping branch was correctly suppressed, but the post-transfer line depths still drove the matrix away from the historical local-state branch.

## v0.3.148 rule

The benchmark preset `--solver-preset xstar-local-state` is restored to the historical examples/51--52 local-state validation branch.  It does not force `xout_lines1` depths or final `xout_cont1/xout_spect1` spectra into the population matrix.

The unsafe output-table substitution is still available only as:

```bash
--solver-preset xstar-local-state-experimental-pumping
```

This is for diagnostics only and should not be treated as the source-code-parity solution.

## Remaining exact-parity requirement

To reproduce XSTAR exactly under arbitrary `Te`, `ne`, and `xi`, `xstar-atomic` must obtain or reconstruct the live local arrays passed to `ucalc.f90`:

```text
epi(:)
bremsa(:)
bremsint(:)
tau0(1:2, line)
tauc(1:2, continuum)
cfrac
vturbi
```

The standard `xout_*` products are sufficient for target extraction and postprocessing validation, but not sufficient by themselves for exact population-matrix parity.
